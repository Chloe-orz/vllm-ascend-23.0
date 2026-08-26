# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""CommChannel: one strict FIFO per physical (type, direction, peer) wire.

A channel is keyed by its physical ``(device group, peer)`` identity.
The six directional channels each own a dedicated communicator carrying
exactly one task type in one direction, so a single rank's ops on one
channel are homogeneous (all sends or all recvs) and HCCL P2P matching
order per wire is nothing but the channel's submission order.

Ordering guarantee: every wire op is followed inside the launch-stream
context by ``handle.wait()`` (CPU returns immediately; bridges HCCL
completion onto the channel stream) and an event record. The next op
waits for the previous completion event on its actual launch stream,
preserving device order across host threads.

Sequenced submission (``CommRequest.seqno``): the scheduler is the
single ordering authority and stamps a per-channel sequence number on
every request.  Ops submitted ahead of their seqno turn (e.g. a guard
thread racing ahead of another submitter) are held in a reorder buffer
and posted only when all lower seqnos have been submitted, so the send
order and the peer's recv-post order agree no matter which host thread
wins the race.  Held requests return deferred futures that bind in
place when their turn arrives (see :class:`CommFuture`).

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
from vllm_ascend.distributed.edge_cloud_comm.mapping import transport_for
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
        # Sequenced-submission state: requests with a seqno ahead of
        # _next_seqno are held (with their deferred futures) until the
        # missing predecessors are submitted.
        self._next_seqno: int | None = None
        self._held: dict[int, tuple[CommRequest, CommFuture]] = {}

    # ------------------------------------------------------------------ #
    # Submission                                                          #
    # ------------------------------------------------------------------ #

    def submit(self, request: CommRequest) -> CommFuture:
        """Execute the wire op and enqueue the future.

        Reaps completed predecessors first (lazy reclamation: this is what
        releases send-buffer keepalives without any background thread).
        Sequenced requests (``seqno`` set) may be held instead of posted;
        the returned deferred future binds when their turn arrives.
        """
        finalized = self._reap()
        self._finalize_many(finalized)
        if request.op == "send":
            request = self._snapshot_send(request)
        with self._submission_lock:
            if request.seqno is not None:
                return self._submit_sequenced(request)
            future = self._execute_next(request)
            return future

    @staticmethod
    def _snapshot_send(request: CommRequest) -> CommRequest:
        """Give the comm layer ownership of the send payload.

        Graph replay and model-runner staging buffers may overwrite the
        same storage on the next batch.  Holding a reference only stops
        allocator reuse, so the comm layer must own a payload snapshot.
        Done at submit-entry (not at wire-execution time) so held
        (out-of-order sequenced) sends are also safe against producer
        buffer reuse while they wait for their seqno turn.
        """
        assert request.tensor_dict is not None, "send requires tensor_dict"
        owned_tensor_dict = {
            key: value.detach().clone()
            if isinstance(value, torch.Tensor)
            else value
            for key, value in request.tensor_dict.items()
        }
        return replace(request, tensor_dict=owned_tensor_dict)

    # ------------------------------------------------------------------ #
    # Sequenced submission (reorder buffer)                               #
    # ------------------------------------------------------------------ #

    def _submit_sequenced(self, request: CommRequest) -> CommFuture:
        """Post in per-channel seqno order.  Caller holds the submission
        lock."""
        seqno = request.seqno
        assert seqno is not None
        if self._next_seqno is None:
            # Scheduler contract: per-channel seqno counters start at 0.
            self._next_seqno = 0
        if seqno < self._next_seqno:
            raise RuntimeError(
                f"duplicate or replayed seqno {seqno} on channel "
                f"{self.channel_type.value} (next expected "
                f"{self._next_seqno})"
            )
        if seqno > self._next_seqno:
            future = CommFuture.deferred(request)
            self._held[seqno] = (request, future)
            logger.debug(
                "[edge-cloud-comm] held out-of-order %s %s seqno=%d "
                "(next=%d)",
                self.channel_type.value,
                request.op,
                seqno,
                self._next_seqno,
            )
            return future
        future = self._execute_next(request)
        self._next_seqno += 1
        # Drain consecutive held requests now that their predecessors
        # exist.  Held futures bind in place and join the pending queue.
        while self._next_seqno in self._held:
            held_request, held_future = self._held.pop(self._next_seqno)
            self._execute_next(held_request, into=held_future)
            self._next_seqno += 1
        return future

    def _execute_next(
        self,
        request: CommRequest,
        into: CommFuture | None = None,
    ) -> CommFuture:
        """Execute one wire op as the channel's new tail.  Caller holds
        the submission lock."""
        with self._lock:
            predecessor = self._pending[-1] if self._pending else None
        future = self._execute(request, predecessor, into=into)
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
            if self._held:
                # Held requests never posted (their seqno predecessors
                # never arrived); their deferred futures stay pending
                # and are the caller's responsibility to abandon.
                logger.warning(
                    "[edge-cloud-comm] shutdown on channel %s with %d "
                    "held (never-posted) request(s); lowest missing "
                    "seqno=%s",
                    self.channel_type.value,
                    len(self._held),
                    self._next_seqno,
                )
                self._held.clear()
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
        into: CommFuture | None = None,
    ) -> CommFuture:
        """Issue the wire op, bridge it onto the channel stream, record the
        completion event.  When ``into`` is given (a deferred future from
        the reorder buffer), bind the result into it instead of creating
        a new future."""
        tensor_dict: dict[str, Any] | None = None
        postprocess: list = []
        keepalive: Any = None
        if req.op == "send":
            assert req.tensor_dict is not None, "send requires tensor_dict"
            # req.tensor_dict is already a communication-owned snapshot
            # (see submit/_snapshot_send).
            self._order_after(predecessor, req)
            handles = self._wire_send(req)
            keepalive = req.tensor_dict
        else:
            self._order_after(predecessor, req)
            tensor_dict, handles, postprocess = self._wire_recv(req)
            # Recv-buffer lifetime: allocated on the channel stream inside
            # the wire helper; handed to the consumer stream via
                # record_stream in the postprocess (see design doc 4.5).
        done_event = self._bridge_and_record(handles, req)
        future_request = replace(req, tensor_dict=None) if req.op == "send" else req
        if into is None:
            return CommFuture(
                request=future_request,
                handles=handles,
                done_event=done_event,
                tensor_dict=tensor_dict,
                postprocess=postprocess,
                keepalive=keepalive,
            )
        into._request = future_request
        into._bind(
            handles=handles,
            done_event=done_event,
            tensor_dict=tensor_dict,
            postprocess=postprocess,
            keepalive=keepalive,
        )
        return into

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
        return ps._get_hidden_channel_stream(transport_for(req.channel))

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
            return ps.edge_cloud_send_tensor_dict(
                req.tensor_dict,
                channel=transport_for(req.channel),
                num_tokens=req.num_tokens,
                dst=req.src_dst,
                include_mrope=req.include_mrope,
            )
        if wire == "draft":
            return ps.edge_cloud_send_tensor_dict_scheduled_draft(
                req.tensor_dict,
                channel=transport_for(req.channel),
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
            return ps.edge_cloud_broadcast_recv_scheduled_draft(
                channel=transport_for(req.channel),
                tensor_meta=req.draft_meta,
                src=req.src_dst,
            )
        if wire == "draft_dynamic":
            # Legacy metadata-exchanging variant (Gloo metadata +
            # irecv), used by the fused in-model draft proposer.
            return ps.edge_cloud_broadcast_recv_draft(src=req.src_dst)
        if wire in ("hidden", "plain"):
            transport = (
                transport_for(req.channel) if wire == "hidden" else None
            )
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
            "[edge-cloud-comm] bridged %d handle(s) on channel %s",
            len(handles),
            req.channel.value,
        )
        return event
