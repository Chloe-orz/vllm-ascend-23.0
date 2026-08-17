# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""CommChannel: one strict FIFO per physical wire.

A channel is keyed by its *transport* (the concrete ``HiddenChannelType``,
i.e. the (device group, peer) identity), because HCCL P2P matching is
ordered per wire.  Several logical ``CommChannelType`` values may share a
transport default (e.g. DECODE_UP / DECODE_DOWN both default to
``HiddenChannelType.decode(1)``), but up/down directions use distinct
device groups and never share a FIFO in practice — the scheduler either
assigns distinct transports or the defaults already differ per direction
pool.

Ordering guarantee (replaces ``_wait_pp_send_work``): every wire op is
followed — inside the channel-stream context — by ``handle.wait()`` (CPU
returns immediately; bridges HCCL completion onto the channel stream) and
an event record.  The next op on the same channel therefore lands behind
the previous op's completion *on the device*, with zero CPU involvement.

Execution model (v1): the wire op is issued synchronously at submit time
on the calling thread.  All HCCL calls involved are async launches — the
CPU never blocks — so this is behavior-identical to the legacy inline
code.  Moving execution onto a dedicated thread is a drop-in change
inside :meth:`CommChannel.submit` if profiling later shows the launch
CPU cost (cat/alloc + HCCL call) matters.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

import torch
from vllm.logger import logger
from vllm.v1.core.sched.output import HiddenChannelType

from vllm_ascend.distributed import parallel_state as ps
from vllm_ascend.distributed.edge_cloud_comm.future import CommFuture
from vllm_ascend.distributed.edge_cloud_comm.types import (
    BatchKind,
    CommChannelType,
    CommRequest,
)

_DRAFT_KINDS = (BatchKind.PREFILL_DRAFT, BatchKind.DECODE_DRAFT)


class CommChannel:
    """One FIFO of pending requests bound to a dedicated NPU stream."""

    def __init__(
        self, channel_type: CommChannelType, transport: HiddenChannelType
    ) -> None:
        self.channel_type = channel_type
        self.transport = transport
        self._pending: deque[CommFuture] = deque()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Submission                                                          #
    # ------------------------------------------------------------------ #

    def submit(self, request: CommRequest) -> CommFuture:
        """Execute the wire op and enqueue the future.

        Reaps completed predecessors first (lazy reclamation: this is what
        releases send-buffer keepalives without any background thread).
        """
        finalized = self._reap()
        self._finalize_many(finalized)
        future = self._execute(request)
        with self._lock:
            self._pending.append(future)
        return future

    # ------------------------------------------------------------------ #
    # Reaping (head-of-line query)                                        #
    # ------------------------------------------------------------------ #

    def reap(self) -> list[CommFuture]:
        """Pop and finalize every completed request from the head.

        FIFO completion is in-order: if the head is not done, nothing
        behind it can be done either, so one ``event.query()`` per call
        per channel suffices.
        """
        finalized = self._reap()
        self._finalize_many(finalized)
        return finalized

    def _reap(self) -> list[CommFuture]:
        done: list[CommFuture] = []
        with self._lock:
            while self._pending and self._pending[0].done():
                done.append(self._pending.popleft())
        return done

    @staticmethod
    def _finalize_many(futures: list[CommFuture]) -> None:
        for future in futures:
            future._finalize()

    # ------------------------------------------------------------------ #
    # Wire execution                                                      #
    # ------------------------------------------------------------------ #

    def _execute(self, req: CommRequest) -> CommFuture:
        """Issue the wire op, bridge it onto the channel stream, record the
        completion event."""
        tensor_dict: dict[str, Any] | None = None
        postprocess: list = []
        keepalive: Any = None
        if req.op == "send":
            assert req.tensor_dict is not None, "send requires tensor_dict"
            handles = self._wire_send(req)
            # Hold the source tensors until the send completes: the caching
            # allocator would otherwise hand the same block to the next
            # batch while the HCCL internal stream is still reading it.
            keepalive = req.tensor_dict
        else:
            tensor_dict, handles, postprocess = self._wire_recv(req)
            # Recv-buffer lifetime: allocated on the channel stream inside
            # the wire helper; handed to the consumer stream via
            # record_stream in the postprocess (see design doc 4.5).
        done_event = self._bridge_and_record(handles)
        return CommFuture(
            request=req,
            handles=handles,
            done_event=done_event,
            tensor_dict=tensor_dict,
            postprocess=postprocess,
            keepalive=keepalive,
        )

    @staticmethod
    def _wire_of(req: CommRequest) -> str:
        if req.wire is not None:
            return req.wire
        return "draft" if req.kind in _DRAFT_KINDS else "hidden"

    def _wire_send(self, req: CommRequest) -> list[Any]:
        wire = self._wire_of(req)
        if wire == "hidden":
            return ps.edge_cloud_send_tensor_dict(
                req.tensor_dict,
                channel=self.transport,
                num_tokens=req.num_tokens,
                dst=req.src_dst,
                include_mrope=req.include_mrope,
            )
        if wire == "draft":
            return ps.edge_cloud_send_tensor_dict_scheduled_draft(
                req.tensor_dict,
                channel=self.transport,
                tensor_meta=req.draft_meta,
            )
        if wire == "draft_dynamic":
            # Fused in-model draft proposer path: per-step dynamic
            # tensor dict on the default PP group (unchanged from the
            # legacy caller).
            return ps.get_pp_group().isend_tensor_dict(req.tensor_dict)
        # "plain": shared-model head send — channel=None, default device
        # group, caller's current stream (unchanged from the legacy call).
        return ps.edge_cloud_isend_tensor_dict(
            req.tensor_dict,
            dst=req.src_dst,
            num_tokens=req.num_tokens,
            include_mrope=req.include_mrope,
        )

    def _wire_recv(self, req: CommRequest):
        wire = self._wire_of(req)
        if wire == "draft":
            return ps.edge_cloud_broadcast_recv_scheduled_draft(
                channel=self.transport,
                tensor_meta=req.draft_meta,
            )
        if wire == "draft_dynamic":
            # Legacy metadata-exchanging variant (Gloo metadata +
            # irecv), used by the fused in-model draft proposer.
            return ps.edge_cloud_broadcast_recv_draft()
        # "hidden" / "plain": identical on the recv side.
        return ps.edge_cloud_broadcast_recv(
            num_tokens=req.num_tokens,
            channel=self.transport,
            sp_chunk=req.sp_chunk,
            src=req.src_dst,
            include_mrope=req.include_mrope,
        )

    def _bridge_and_record(self, handles: list[Any]):
        """Bridge HCCL completion onto the channel stream and record an
        event right behind it.

        ``handle.wait()`` here is the non-blocking HCCL semantics: it makes
        the *current* (channel) stream depend on the HCCL end event and
        returns immediately on the CPU.  Must run with the channel stream
        current — bridging binds to whatever stream is current at call
        time, so doing this outside the context would order the wrong
        stream.  Requires HCCL_BLOCKING_WAIT to stay unset (it is, in the
        target deployments).
        """
        if not handles:
            return None
        stream = ps._get_hidden_channel_stream(self.transport)
        with torch.npu.stream(stream):
            for handle in handles:
                handle.wait()
            event = torch.npu.Event()
            event.record()
        logger.debug(
            "[edge-cloud-comm] bridged %d handle(s) on channel %s "
            "(transport=%s)",
            len(handles),
            self.channel_type.value,
            self.transport,
        )
        return event
