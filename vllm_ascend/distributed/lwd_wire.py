# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""prefill_only duplex data-plane wire layer.

Owns two HCCL groups (UP/DOWN) per YAML edge/cloud/DP connection.
All bootstrap-world ranks create the full group plan in the same order;
only the two endpoints submit P2P. Cloud fanout reuses the matching TP
group, never the edge-cloud world or a two-stage PP group.

Only prefill_only mode builds these groups; other modes never reach
here (gated by ``LwdConfig.is_prefill_only``).
"""

from __future__ import annotations

import torch
import torch.distributed as dist
from vllm.distributed.parallel_state import get_tp_group, get_world_group
from vllm.logger import logger

from vllm_ascend.distributed.lwd_comm.topology import (
    LwdConnectionKey,
    LwdWireConnection,
    build_lwd_wire_plan,
    select_lwd_wire_connection,
)
from vllm_ascend.distributed.lwd_comm.types import LwdChannelType

# (connection, channel) -> (device_group, peer_global_rank).
# Existing process-local storage; this is NOT a shared-rank process arbiter.
_LWD_CHANNEL_GROUPS: dict[tuple[LwdConnectionKey, LwdChannelType], tuple[dist.ProcessGroup, int]] = {}
_LWD_CHANNEL_STREAMS: dict[tuple[LwdConnectionKey, LwdChannelType], "torch.npu.Stream"] = {}
_LWD_ENDPOINTS: tuple[LwdWireConnection, ...] = ()
_INITIALIZED = False


def _get_lwd_bootstrap_world_group():
    """取 LWD 建组/warmup 用的引导世界组。

    vllm 侧 LWD 分支会把原 9-rank 世界组存为
    ``parallel_state._LWD_BOOTSTRAP_WORLD`` 并提供
    ``get_lwd_bootstrap_world()`` 访问器(此后 ``_WORLD`` 被替换为
    实例 TP 组);旧版 vllm 无该访问器时回退 ``get_world_group()``。
    """
    from vllm.distributed import parallel_state

    accessor = getattr(parallel_state, "get_lwd_bootstrap_world", None)
    if accessor is not None:
        return accessor()
    return get_world_group()


def init_lwd_duplex_channels() -> None:
    """Build the global YAML group plan after framework parallel groups.

    Only single-instance, single-DP execution is supported. Other layouts
    can be inspected as pure configuration plans, but must not create groups.
    """
    global _INITIALIZED, _LWD_ENDPOINTS
    if _INITIALIZED:
        return
    if _LWD_CHANNEL_GROUPS:
        raise RuntimeError("[LWD] Previous channel initialization failed; restart workers")
    from vllm.config import get_current_vllm_config

    config = get_current_vllm_config().lwd_config
    if config is None or config.topology is None:
        raise ValueError("[LWD] Data-plane initialization requires the parsed topology YAML")
    config.topology.validate_single_dp_runtime()
    plan = build_lwd_wire_plan(config.topology)
    bootstrap = _get_lwd_bootstrap_world_group()
    expected_world = config.topology.deployment.hccl_world_size
    if tuple(bootstrap.ranks) != tuple(range(expected_world)):
        raise ValueError("[LWD] Bootstrap world ranks do not match the topology YAML")
    backend = dist.get_backend(bootstrap.device_group)
    my_rank = dist.get_rank()
    # Validate the existing broadcast domain before creating any wire groups.
    # Multiple links to one cloud DP reuse this same domain.
    for connection in plan:
        if my_rank in connection.cloud_ranks:
            _validate_cloud_tp_group(connection)
    for connection in plan:
        ranks = list(connection.endpoint_ranks)
        for channel in (LwdChannelType.UP, LwdChannelType.DOWN):
            # Even non-members call every new_group, in this global order.
            group = dist.new_group(ranks, backend=backend)
            peer = connection.peer_for(my_rank) if my_rank in ranks else -1
            key = (connection.key, channel)
            _LWD_CHANNEL_GROUPS[key] = (group, peer)
            if peer >= 0:
                _LWD_CHANNEL_STREAMS[key] = torch.npu.Stream()
        logger.info(
            "[lwd-wire] duplex channels created connection=%s ranks=%s (my_rank=%d)",
            connection.key, ranks, my_rank,
        )
    _LWD_ENDPOINTS = plan
    warmup_lwd_duplex_channels()
    _INITIALIZED = True


def warmup_lwd_duplex_channels() -> None:
    """Warm each link's UP P2P -> cloud broadcast -> DOWN P2P in order.

    Uses small buffers, not model-sized payloads. Runtime broadcast remains
    on the compute stream in the model runner, after the P2P readiness gate.
    """
    my_rank = dist.get_rank()
    for connection in _LWD_ENDPOINTS:
        for channel in (LwdChannelType.UP, LwdChannelType.DOWN):
            payload = None
            group, peer = _LWD_CHANNEL_GROUPS[(connection.key, channel)]
            if peer >= 0:
                payload = torch.zeros(8, dtype=torch.bfloat16, device="npu")
                sender = connection.edge_rank if channel is LwdChannelType.UP else connection.cloud_leader_rank
                if my_rank == sender:
                    handle = dist.isend(payload, dst=peer, group=group)
                else:
                    handle = dist.irecv(payload, src=peer, group=group)
                handle.wait()
            if channel is LwdChannelType.UP and my_rank in connection.cloud_ranks:
                tp = _validate_cloud_tp_group(connection)
                if payload is None:
                    payload = torch.zeros(8, dtype=torch.bfloat16, device="npu")
                if tp.world_size > 1:
                    dist.broadcast(
                        payload, src=connection.cloud_leader_rank,
                        group=tp.device_group, async_op=True,
                    ).wait()
    _get_lwd_bootstrap_world_group().barrier()
    logger.info("[lwd-wire] duplex channels warmed up (UP + cloud TP broadcast + DOWN)")


def lwd_channels_initialized() -> bool:
    return _INITIALIZED


def get_lwd_wire_connection(connection_key: LwdConnectionKey | None = None) -> LwdWireConnection:
    if not _INITIALIZED:
        raise RuntimeError("[LWD] Data-plane channels are not initialized")
    return select_lwd_wire_connection(_LWD_ENDPOINTS, dist.get_rank(), connection_key)


def _validate_cloud_tp_group(connection: LwdWireConnection):
    tp = get_tp_group()
    if tuple(tp.ranks) != connection.cloud_ranks:
        raise ValueError(
            f"[LWD] Cloud TP ranks {tp.ranks} do not match "
            f"{connection.key} broadcast domain {connection.cloud_ranks}"
        )
    return tp


def get_lwd_cloud_tp_group(connection_key: LwdConnectionKey | None = None):
    connection = get_lwd_wire_connection(connection_key)
    if dist.get_rank() not in connection.cloud_ranks:
        raise ValueError("[LWD] Edge rank must not join the cloud broadcast")
    return _validate_cloud_tp_group(connection)


def _channel_key(channel: LwdChannelType, connection_key: LwdConnectionKey | None):
    connection = get_lwd_wire_connection(connection_key)
    connection.peer_for(dist.get_rank())  # Reject non-endpoint P2P before HCCL.
    return connection.key, channel


def resolve_lwd_channel_operation(
    channel: LwdChannelType, op: str, connection_key: LwdConnectionKey | None = None,
) -> LwdConnectionKey:
    """Resolve and validate a P2P operation before allocating/queuing work."""
    if not isinstance(channel, LwdChannelType) or op not in ("send", "recv"):
        raise ValueError(f"[LWD] Invalid channel operation: {channel}/{op}")
    connection = get_lwd_wire_connection(connection_key)
    sender = connection.edge_rank if channel is LwdChannelType.UP else connection.cloud_leader_rank
    expected = sender if op == "send" else connection.peer_for(sender)
    if dist.get_rank() != expected:
        raise ValueError(f"[LWD] {connection.key} {channel.value}/{op} requires rank={expected}")
    return connection.key


def get_lwd_channel_device_group(
    channel: LwdChannelType, connection_key: LwdConnectionKey | None = None,
) -> dist.ProcessGroup:
    group, _ = _LWD_CHANNEL_GROUPS[_channel_key(channel, connection_key)]
    return group


def get_lwd_channel_peer(channel: LwdChannelType, connection_key: LwdConnectionKey | None = None) -> int:
    """Global rank of this process's P2P peer on the channel."""
    _, peer = _LWD_CHANNEL_GROUPS[_channel_key(channel, connection_key)]
    return peer


def get_lwd_channel_stream(
    channel: LwdChannelType, connection_key: LwdConnectionKey | None = None,
) -> "torch.npu.Stream":
    return _LWD_CHANNEL_STREAMS[_channel_key(channel, connection_key)]


def destroy_lwd_duplex_channels() -> None:
    global _INITIALIZED, _LWD_ENDPOINTS
    for key, (group, peer) in list(_LWD_CHANNEL_GROUPS.items()):
        if peer < 0:
            continue  # NON_GROUP_MEMBER is not a process group to destroy.
        try:
            dist.destroy_process_group(group)
        except Exception:
            logger.warning(
                "[lwd-wire] failed to destroy group for %s", key
            )
    _LWD_CHANNEL_GROUPS.clear()
    _LWD_CHANNEL_STREAMS.clear()
    _LWD_ENDPOINTS = ()
    _INITIALIZED = False


def dump_tensor(tag: str, tensor: "torch.Tensor") -> None:
    """调试:张量摘要打印(head10/tail10/sum/mean/shape/dtype),
    供边云两端成对对比数值。"""
    import numpy as np

    flat = tensor.detach().to("cpu", torch.float32).numpy().reshape(-1)
    with np.printoptions(threshold=np.inf, linewidth=10000, precision=8):
        logger.info(
            "%s shape=%s dtype=%s head10=%s tail10=%s sum=%.6f mean=%.8f",
            tag, tuple(tensor.shape), tensor.dtype,
            flat[:10], flat[-10:], float(flat.sum()), float(flat.mean()),
        )
