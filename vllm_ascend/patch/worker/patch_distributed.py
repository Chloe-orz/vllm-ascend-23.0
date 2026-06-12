#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# This file is a part of the vllm-ascend project.
#

from __future__ import annotations

import logging
import pickle
from functools import wraps
from typing import Any, Callable, cast

import torch
import vllm
from torch.distributed import Backend
from vllm.distributed.parallel_state import (
    GroupCoordinator,
    TensorMetadata,
    _get_unique_name,
    _register_group,
    _split_tensor_dict,
)

from vllm_ascend.distributed.device_communicators.npu_communicator import NPUCommunicator
from vllm_ascend.patch.worker._hccl_pg_registry import HcclPgKey, HcclPgRegistry, make_hccl_pg_key
from vllm_ascend.utils import create_hccl_pg_options

_HCCL_PG_REGISTRY = HcclPgRegistry()
logger = logging.getLogger(__name__)


def _normalize_backend(backend: str | Backend) -> str:
    return str(backend)


def _resolve_reuse_domain(group_name: str) -> str:
    group_base_name = group_name.split(":")[0]
    if "eplb" in group_base_name or group_base_name == "mc2":
        return group_base_name
    return "shared"


def _create_device_group(
    ranks: list[int],
    backend: str,
    hccl_pg_options: object,
):
    return torch.distributed.new_group(
        ranks,
        backend=backend,
        pg_options=hccl_pg_options,
    )


def _acquire_hccl_group(
    *,
    ranks: list[int],
    backend: str,
    hccl_pg_options: object,
    reuse_domain: str,
):
    # Coordinator construction must remain process-serial and globally ordered:
    # new_group is collective, and the registry only deduplicates equivalent
    # HCCL groups within that ordering contract. It is not a concurrent PG factory.
    hccl_key = make_hccl_pg_key(ranks, backend, hccl_pg_options, reuse_domain)
    device_group = _HCCL_PG_REGISTRY.acquire(
        ranks=ranks,
        backend=backend,
        pg_options=hccl_pg_options,
        reuse_domain=reuse_domain,
        create_fn=lambda: _create_device_group(ranks, backend, hccl_pg_options),
    )
    return device_group, hccl_key


def _wrap_destroy_distributed_environment(destroy_fn):
    if getattr(cast(Any, destroy_fn), "_hccl_registry_clearing_wrapped", False) is True:
        return destroy_fn

    @wraps(destroy_fn)
    def wrapped(*args, **kwargs):
        try:
            return destroy_fn(*args, **kwargs)
        finally:
            _HCCL_PG_REGISTRY.clear()

    cast(Any, wrapped)._hccl_registry_clearing_wrapped = True
    return wrapped


def _patch_destroy_distributed_environment():
    destroy_fn = _wrap_destroy_distributed_environment(vllm.distributed.parallel_state.destroy_distributed_environment)
    vllm.distributed.parallel_state.destroy_distributed_environment = destroy_fn
    vllm.distributed.destroy_distributed_environment = destroy_fn


class GroupCoordinatorPatch(GroupCoordinator):
    def __init__(
        self,
        group_ranks: list[list[int]],
        local_rank: int,
        torch_distributed_backend: str | Backend,
        use_device_communicator: bool,  # whether to use device communicator
        use_message_queue_broadcaster: bool = False,
        group_name: str | None = None,
    ):
        group_name = group_name or "anonymous"
        self.unique_name = _get_unique_name(group_name)
        _register_group(self)

        self.rank = torch.distributed.get_rank()
        self.local_rank = local_rank
        # Store all group_ranks so that create_alternate_groups can
        # iterate over every subgroup — torch.distributed.new_group
        # is a collective on the default group and must be called by
        # every rank, even for subgroups it does not belong to.
        self._all_group_ranks = group_ranks

        self.backend = _normalize_backend(torch_distributed_backend)
        self._acquired_hccl_keys: list[HcclPgKey] = []
        self._unshared_hccl_groups: list[object] = []
        self.use_device_communicator = use_device_communicator
        self.device_communicator: NPUCommunicator | None = None
        self.mq_broadcaster = None
        self.cpu_group = None
        self.device_group = None
        self.device = None
        self.use_custom_op_call = True
        self.use_cpu_custom_send_recv = False
        self.group_name = group_name
        self.group_ranks = group_ranks

        try:
            self._init_device_groups(create_cpu_group=True)
            assert self.cpu_group is not None
            assert self.device_group is not None

            # Alternate device/cpu groups for dual-channel PP communication.
            # When set, these provide a second independent communication channel
            # over the same ranks. Used in PP to separate decode from
            # non-decode traffic.
            self.alt_device_group: torch.distributed.ProcessGroup | None = None
            self.alt_cpu_group: torch.distributed.ProcessGroup | None = None
            # Phase6 hidden data-plane channels. The default device/cpu groups
            # are PREFILL_1, the legacy alt groups are DECODE, and the extra
            # hidden groups below are PREFILL_2.
            self.prefill2_device_group: torch.distributed.ProcessGroup | None = None
            self.prefill2_cpu_group: torch.distributed.ProcessGroup | None = None

            self.device = torch.npu.current_device()
            if use_device_communicator and self.world_size > 1:
                self.device_communicator = NPUCommunicator(
                    cpu_group=self.cpu_group,
                    device=self.device,
                    device_group=self.device_group,
                    unique_name=self.unique_name,
                )

            from vllm.distributed.device_communicators.shm_broadcast import MessageQueue

            if use_message_queue_broadcaster and self.world_size > 1:
                self.mq_broadcaster = MessageQueue.create_from_process_group(
                    self.cpu_group,
                    1 << 22,
                    6,
                )
        except Exception:
            try:
                self.destroy()
            except Exception:
                logger.exception("Failed to clean up partially initialized GroupCoordinatorPatch")
            raise

    def _init_device_groups(self, create_cpu_group: bool) -> None:
        reuse_domain = _resolve_reuse_domain(self.group_name)
        self_device_group = None
        for ranks in self.group_ranks:
            hccl_pg_options = create_hccl_pg_options(self.group_name)
            device_group, hccl_key = _acquire_hccl_group(
                ranks=ranks,
                backend=self.backend,
                hccl_pg_options=hccl_pg_options,
                reuse_domain=reuse_domain,
            )
            if hccl_key is not None:
                self._acquired_hccl_keys.append(hccl_key)
            elif self.backend == "hccl" and self.rank in ranks:
                self._unshared_hccl_groups.append(device_group)

            cpu_group = torch.distributed.new_group(ranks, backend="gloo") if create_cpu_group else None
            if self.rank in ranks:
                if create_cpu_group:
                    self.ranks = ranks
                    self.world_size = len(ranks)
                    self.rank_in_group = ranks.index(self.rank)
                    self.cpu_group = cpu_group
                self_device_group = device_group

        if self_device_group is not None:
            self.device_group = self_device_group

    def _init_device_communicator(self) -> None:
        self.device = torch.npu.current_device()
        if self.use_device_communicator and self.world_size > 1:
            self.device_communicator = NPUCommunicator(
                cpu_group=self.cpu_group,
                device=self.device,
                device_group=self.device_group,
                unique_name=self.unique_name,
            )

    def _release_hccl_resources(self) -> bool:
        destroyed = False
        device_communicator = getattr(self, "device_communicator", None)
        if device_communicator is not None:
            device_communicator.destroy()
            self.device_communicator = None
            destroyed = True

        if hasattr(self, "_acquired_hccl_keys"):
            for hccl_key in reversed(self._acquired_hccl_keys):
                _HCCL_PG_REGISTRY.release(hccl_key)
            self._acquired_hccl_keys = []
            destroyed = True

        if hasattr(self, "_unshared_hccl_groups"):
            for device_group in reversed(self._unshared_hccl_groups):
                torch.distributed.destroy_process_group(device_group)
            self._unshared_hccl_groups = []
            destroyed = True

        return destroyed

    def destroy(self):
        if getattr(self, "mq_broadcaster", None) is not None:
            self.mq_broadcaster = None

        self._release_hccl_resources()

        device_group = getattr(self, "device_group", None)
        if device_group is not None and self.backend != "hccl":
            torch.distributed.destroy_process_group(device_group)
        if hasattr(self, "device_group"):
            del self.device_group

        cpu_group = getattr(self, "cpu_group", None)
        if cpu_group is not None:
            torch.distributed.destroy_process_group(cpu_group)
        if hasattr(self, "cpu_group"):
            del self.cpu_group

        alt_cpu_group = getattr(self, "alt_cpu_group", None)
        if alt_cpu_group is not None:
            torch.distributed.destroy_process_group(alt_cpu_group)
            self.alt_cpu_group = None

        alt_device_group = getattr(self, "alt_device_group", None)
        if alt_device_group is not None:
            torch.distributed.destroy_process_group(alt_device_group)
            self.alt_device_group = None

        prefill2_cpu_group = getattr(self, "prefill2_cpu_group", None)
        if prefill2_cpu_group is not None:
            torch.distributed.destroy_process_group(prefill2_cpu_group)
            self.prefill2_cpu_group = None

        prefill2_device_group = getattr(self, "prefill2_device_group", None)
        if prefill2_device_group is not None:
            torch.distributed.destroy_process_group(prefill2_device_group)
            self.prefill2_device_group = None

        alt_cpu_group = getattr(self, "alt_cpu_group", None)
        if alt_cpu_group is not None:
            torch.distributed.destroy_process_group(alt_cpu_group)
            self.alt_cpu_group = None

        alt_device_group = getattr(self, "alt_device_group", None)
        if alt_device_group is not None:
            torch.distributed.destroy_process_group(alt_device_group)
            self.alt_device_group = None

        prefill2_cpu_group = getattr(self, "prefill2_cpu_group", None)
        if prefill2_cpu_group is not None:
            torch.distributed.destroy_process_group(prefill2_cpu_group)
            self.prefill2_cpu_group = None

        prefill2_device_group = getattr(self, "prefill2_device_group", None)
        if prefill2_device_group is not None:
            torch.distributed.destroy_process_group(prefill2_device_group)
            self.prefill2_device_group = None

        if getattr(self, "mq_broadcaster", None) is not None:
            self.mq_broadcaster = None

    def create_alternate_groups(
        self,
        torch_distributed_backend: str | Backend,
    ) -> None:
        """Create alternate device and cpu groups over the same ranks.

        Must be called collectively by all ranks in the **default** group
        (i.e. every rank that participates in ``torch.distributed``), because
        ``torch.distributed.new_group`` is a collective operation on the
        default group. After calling this, communication methods can use
        ``use_alt_group=True`` to route through the alternate
        communication channel.
        """
        assert self.alt_device_group is None, (
            "Alternate groups already created"
        )
        hccl_pg_options = create_hccl_pg_options("pp_alt")
        self_alt_device_group = None
        self_alt_cpu_group = None
        # Iterate over ALL subgroups so that every rank participates in
        # every new_group call (required because new_group is collective
        # on the default group).  Only save the group this rank belongs to.
        for ranks in self._all_group_ranks:
            alt_device_group = torch.distributed.new_group(
                ranks,
                backend=torch_distributed_backend,
                pg_options=hccl_pg_options,
            )
            alt_cpu_group = torch.distributed.new_group(
                ranks, backend="gloo"
            )
            if self.rank in ranks:
                self_alt_device_group = alt_device_group
                self_alt_cpu_group = alt_cpu_group
        assert self_alt_device_group is not None
        assert self_alt_cpu_group is not None
        self.alt_device_group = self_alt_device_group
        self.alt_cpu_group = self_alt_cpu_group

    def create_hidden_channel_groups(
        self,
        torch_distributed_backend: str | Backend,
    ) -> None:
        """Create the extra Phase6 PREFILL_2 group.

        The default pp group is PREFILL_1 and the existing alternate group is
        DECODE.  This method adds PREFILL_2 as the third independent data-plane
        channel over the same ranks.
        """
        assert self.prefill2_device_group is None, (
            "PREFILL_2 hidden channel group already created"
        )
        hccl_pg_options = create_hccl_pg_options("pp_prefill2")
        prefill2_device_group = None
        prefill2_cpu_group = None
        for ranks in self._all_group_ranks:
            device_group = torch.distributed.new_group(
                ranks,
                backend=torch_distributed_backend,
                pg_options=hccl_pg_options,
            )
            cpu_group = torch.distributed.new_group(ranks, backend="gloo")
            if self.rank in ranks:
                prefill2_device_group = device_group
                prefill2_cpu_group = cpu_group
        assert prefill2_device_group is not None
        assert prefill2_cpu_group is not None
        self.prefill2_device_group = prefill2_device_group
        self.prefill2_cpu_group = prefill2_cpu_group

    def _hidden_channel_groups(self, channel: Any):
        value = getattr(channel, "value", channel)
        if value == "prefill_1":
            return self.device_group, self.cpu_group
        if value == "decode":
            assert self.alt_device_group is not None
            assert self.alt_cpu_group is not None
            return self.alt_device_group, self.alt_cpu_group
        if value == "prefill_2":
            assert self.prefill2_device_group is not None
            assert self.prefill2_cpu_group is not None
            return self.prefill2_device_group, self.prefill2_cpu_group
        raise ValueError(f"Unknown hidden channel: {channel}")

    def send_object_on_hidden_channel(
        self, obj: Any, dst: int, channel: Any
    ) -> None:
        """Synchronous send of a pickled object (used by tests/fallback)."""
        _, cpu_group = self._hidden_channel_groups(channel)
        object_tensor = torch.frombuffer(
            bytearray(pickle.dumps(obj)), dtype=torch.uint8
        )
        size_tensor = torch.tensor(
            [object_tensor.numel()], dtype=torch.long, device="cpu"
        )
        torch.distributed.send(size_tensor, dst=self.ranks[dst], group=cpu_group)
        torch.distributed.send(object_tensor, dst=self.ranks[dst], group=cpu_group)

    def send_object_on_hidden_channel_async(
        self, obj: Any, dst: int, channel: Any
    ) -> list[Any]:
        """Asynchronous send of a pickled object; returns isend handles."""
        _, cpu_group = self._hidden_channel_groups(channel)
        object_tensor = torch.frombuffer(
            bytearray(pickle.dumps(obj)), dtype=torch.uint8
        )
        size_tensor = torch.tensor(
            [object_tensor.numel()], dtype=torch.long, device="cpu"
        )
        h1 = torch.distributed.isend(
            size_tensor, dst=self.ranks[dst], group=cpu_group
        )
        h2 = torch.distributed.isend(
            object_tensor, dst=self.ranks[dst], group=cpu_group
        )
        return [h1, h2]

    def recv_object_on_hidden_channel(self, src: int, channel: Any) -> Any:
        _, cpu_group = self._hidden_channel_groups(channel)
        size_tensor = torch.empty(1, dtype=torch.long, device="cpu")
        torch.distributed.recv(size_tensor, src=self.ranks[src], group=cpu_group)
        object_tensor = torch.empty(
            size_tensor.item(), dtype=torch.uint8, device="cpu"
        )
        torch.distributed.recv(object_tensor, src=self.ranks[src], group=cpu_group)
        return pickle.loads(object_tensor.numpy().tobytes())

    def isend_tensor_dict_on_hidden_channel(
        self,
        tensor_dict: dict[str, torch.Tensor | Any],
        channel: Any,
        dst: int | None = None,
    ) -> list[Any]:
        if self.world_size <= 1:
            return []
        if dst is None:
            dst = (self.rank_in_group + 1) % self.world_size
        assert dst < self.world_size, f"Invalid dst rank ({dst})"
        device_group, cpu_group = self._hidden_channel_groups(channel)
        metadata_list, tensor_list = _split_tensor_dict(tensor_dict)
        # Use async send for metadata so the edge head segment can return
        # immediately even when the cloud worker has not yet reached the
        # matching recv (e.g. it is still executing earlier prefill slices).
        handles = self.send_object_on_hidden_channel_async(
            metadata_list, dst, channel
        )

        tensor_keys = [k for k, v in tensor_dict.items() if isinstance(v, torch.Tensor)]
        assert len(tensor_keys) == len(tensor_list)
        for tensor in tensor_list:
            if tensor.numel() == 0:
                continue
            group = cpu_group if tensor.is_cpu else device_group
            if tensor.device.type == "npu":
                tensor.record_stream(torch.npu.current_stream(tensor.device))
            handles.append(torch.distributed.isend(
                tensor, dst=self.ranks[dst], group=group
            ))
        return handles

    def irecv_tensor_dict_on_hidden_channel(
        self,
        channel: Any,
        src: int | None = None,
    ) -> tuple[dict[str, torch.Tensor | Any] | None,
               list[Any], list[Callable[[], None]]]:
        if not torch.distributed.is_initialized() or self.world_size == 1:
            return None, [], []
        if src is None:
            src = (self.rank_in_group - 1) % self.world_size
        assert src < self.world_size, f"Invalid src rank ({src})"
        device_group, cpu_group = self._hidden_channel_groups(channel)
        recv_metadata_list = self.recv_object_on_hidden_channel(src, channel)
        tensor_dict: dict[str, Any] = {}
        handles = []
        for key, value in recv_metadata_list:
            if isinstance(value, TensorMetadata):
                tensor = torch.empty(value.size, dtype=value.dtype, device=value.device)
                tensor_dict[key] = tensor
                if tensor.numel() == 0:
                    continue
                group = cpu_group if tensor.is_cpu else device_group
                handles.append(torch.distributed.irecv(
                    tensor, src=self.ranks[src], group=group
                ))
            else:
                tensor_dict[key] = value
        return tensor_dict, handles, []

    def all_to_all(
        self,
        input_: torch.Tensor,
        scatter_dim: int = 0,
        gather_dim: int = -1,
        scatter_sizes: list[int] | None = None,
        gather_sizes: list[int] | None = None,
    ) -> torch.Tensor:
        if self.world_size == 1:
            return input_
        assert -input_.dim() <= scatter_dim < input_.dim(), (
            f"Invalid scatter dim ({scatter_dim}) for input tensor with shape {input_.size()}"
        )
        assert -input_.dim() <= gather_dim < input_.dim(), (
            f"Invalid gather dim ({gather_dim}) for input tensor with shape {input_.size()}"
        )
        assert self.device_communicator is not None, "device_communicator should be initialized when world_size > 1"
        return self.device_communicator.all_to_all(input_, scatter_dim, gather_dim, scatter_sizes, gather_sizes)


vllm.distributed.parallel_state.GroupCoordinator = GroupCoordinatorPatch
_patch_destroy_distributed_environment()
