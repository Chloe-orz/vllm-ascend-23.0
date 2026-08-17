# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""CommChannel: one strict FIFO per physical wire.

A channel is keyed by its physical ``(device group, peer)`` identity,
because HCCL P2P matching is ordered per wire. ``HiddenChannelType`` alone
is insufficient: shared-model virtual workers use one transport with
different peers, while ``plain`` and ``draft_dynamic`` use the default PP
group rather than their logical transport.

Ordering guarantee (replaces ``_wait_pp_send_work``): every wire op is
followed inside the launch-stream context by ``handle.wait()`` (CPU
returns immediately; bridges HCCL completion onto the channel stream) and
an event record. The next op waits for the previous completion event on
its actual launch stream, preserving device order across host threads.

Execution model (v1): payload snapshotting and the wire op are issued at
submit time on the calling thread. HCCL calls remain asynchronous; moving
the clone/allocation and launch work to a dedicated thread can be done
inside :meth:`CommChannel.submit` if profiling shows host launch cost is
material.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import replace
from typing import Any

import torch
from vllm.logger import logger

from vllm_ascend.distributed import parallel_state as ps
from vllm_ascend.distributed.edge_cloud_comm.future import CommFuture
from vllm_ascend.distributed.edge_cloud_comm.types import (
    BatchKind,
    CommChannelType,
    CommRequest,
)

_DRAFT_KINDS = (BatchKind.PREFILL_DRAFT, BatchKind.DECODE_DRAFT)


class CommChannel:
    """One FIFO of pending requests for a physical group/peer wire."""

    def __init__(self, channel_type: CommChannelType) -> None:
        self.channel_type = channel_type
        self._pending: deque[CommFuture] = deque()
        self._lock = threading.Lock()
        # The pending-queue lock alone cannot prevent two host threads from
        # interleaving the per-key HCCL calls of separate tensor dictionaries.
        self._submission_lock = threading.Lock()

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
        with self._submission_lock:
            with self._lock:
                predecessor = self._pending[-1] if self._pending else None
            future = self._execute(request, predecessor)
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

    def shutdown(self, timeout: float | None = None) -> list[CommFuture]:
        """Wait for pending operations before releasing owned buffers."""
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._submission_lock:
            with self._lock:
                pending = list(self._pending)
            for future in pending:
                remaining = (
                    None
                    if deadline is None
                    else max(0.0, deadline - time.monotonic())
                )
                future.wait(timeout=remaining)
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

    def _execute(
        self,
        req: CommRequest,
        predecessor: CommFuture | None,
    ) -> CommFuture:
        """Issue the wire op, bridge it onto the channel stream, record the
        completion event."""
        tensor_dict: dict[str, Any] | None = None
        postprocess: list = []
        keepalive: Any = None
        if req.op == "send":
            assert req.tensor_dict is not None, "send requires tensor_dict"
            # Graph replay and model-runner staging buffers may overwrite the
            # same storage on the next batch.  Holding a reference only stops
            # allocator reuse, so the comm layer must own a payload snapshot.
            owned_tensor_dict = {
                key: value.detach().clone()
                if isinstance(value, torch.Tensor)
                else value
                for key, value in req.tensor_dict.items()
            }
            req = replace(req, tensor_dict=owned_tensor_dict)
            self._order_after(predecessor, req)
            handles = self._wire_send(req)
            keepalive = owned_tensor_dict
        else:
            self._order_after(predecessor, req)
            tensor_dict, handles, postprocess = self._wire_recv(req)
            # Recv-buffer lifetime: allocated on the channel stream inside
            # the wire helper; handed to the consumer stream via
                # record_stream in the postprocess (see design doc 4.5).
        done_event = self._bridge_and_record(handles, req)
        future_request = replace(req, tensor_dict=None) if req.op == "send" else req
        return CommFuture(
            request=future_request,
            handles=handles,
            done_event=done_event,
            tensor_dict=tensor_dict,
            postprocess=postprocess,
            keepalive=keepalive,
        )

    @staticmethod
    def wire_for_request(req: CommRequest) -> str:
        if req.wire is not None:
            return req.wire
        return "draft" if req.kind in _DRAFT_KINDS else "hidden"

    @classmethod
    def _stream_for(cls, req: CommRequest):
        wire = cls.wire_for_request(req)
        if wire in ("plain", "draft_dynamic"):
            return torch.npu.current_stream()
        assert req.transport is not None, (
            "transport-backed wire requires a resolved transport"
        )
        return ps._get_hidden_channel_stream(req.transport)

    @classmethod
    def _order_after(
        cls,
        predecessor: CommFuture | None,
        req: CommRequest,
    ) -> None:
        if predecessor is None or predecessor._done_event is None:
            return
        cls._stream_for(req).wait_event(predecessor._done_event)

    def _wire_send(self, req: CommRequest) -> list[Any]:
        wire = self.wire_for_request(req)
        if wire == "hidden":
            assert req.transport is not None
            return ps.edge_cloud_send_tensor_dict(
                req.tensor_dict,
                channel=req.transport,
                num_tokens=req.num_tokens,
                dst=req.src_dst,
                include_mrope=req.include_mrope,
            )
        if wire == "draft":
            assert req.transport is not None
            return ps.edge_cloud_send_tensor_dict_scheduled_draft(
                req.tensor_dict,
                channel=req.transport,
                tensor_meta=req.draft_meta,
                dst=req.src_dst,
            )
        if wire == "draft_dynamic":
            # Fused in-model draft proposer path: per-step dynamic
            # tensor dict on the default PP group (unchanged from the
            # legacy caller).
            return ps.get_pp_group().isend_tensor_dict(
                req.tensor_dict, dst=req.src_dst
            )
        if wire == "plain":
            return ps.edge_cloud_isend_tensor_dict(
                req.tensor_dict,
                dst=req.src_dst,
                num_tokens=req.num_tokens,
                include_mrope=req.include_mrope,
            )
        raise ValueError(f"Unsupported edge-cloud wire type: {wire!r}")

    def _wire_recv(self, req: CommRequest):
        wire = self.wire_for_request(req)
        if wire == "draft":
            assert req.transport is not None
            return ps.edge_cloud_broadcast_recv_scheduled_draft(
                channel=req.transport,
                tensor_meta=req.draft_meta,
                src=req.src_dst,
            )
        if wire == "draft_dynamic":
            # Legacy metadata-exchanging variant (Gloo metadata +
            # irecv), used by the fused in-model draft proposer.
            return ps.edge_cloud_broadcast_recv_draft(src=req.src_dst)
        if wire in ("hidden", "plain"):
            if wire == "hidden":
                assert req.transport is not None
                transport = req.transport
            else:
                transport = None
            return ps.edge_cloud_broadcast_recv(
                num_tokens=req.num_tokens,
                channel=transport,
                sp_chunk=req.sp_chunk,
                src=req.src_dst,
                include_mrope=req.include_mrope,
            )
        raise ValueError(f"Unsupported edge-cloud wire type: {wire!r}")

    def _bridge_and_record(self, handles: list[Any], req: CommRequest):
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
        stream = self._stream_for(req)
        with torch.npu.stream(stream):
            for handle in handles:
                handle.wait()
            event = torch.npu.Event()
            event.record()
        logger.debug(
            "[edge-cloud-comm] bridged %d handle(s) on channel %s "
            "(transport=%s)",
            len(handles),
            req.channel.value,
            req.transport,
        )
        return event
