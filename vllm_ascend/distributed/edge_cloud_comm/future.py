# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""CommFuture: completion-notification vehicle of the comm service.

Completion semantics (see design doc section 4):

* The HCCL op runs on an internal HCCL stream.  ``Work.wait()`` only
  bridges the HCCL completion event onto the *current* stream and returns
  immediately on the CPU — it never means "finished".
* At submit time the channel bridges the handles onto the channel stream
  (``handle.wait()`` inside the channel-stream context) and records
  ``done_event`` right after the bridge.  ``done_event`` therefore fires
  exactly when the P2P op completes.
* ``query()`` on that event is the ONLY reliable CPU-side completion
  observation (``is_completed()`` is not — it only means "queued").
* Consumers must NOT rely on ``query()`` for data readiness: they order
  their stream behind the event with ``wait_event`` (device-side), which
  is what :class:`_CommSyncedIntermediateTensors` does.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import torch
from vllm.logger import logger
from vllm.v1.worker.gpu_worker import AsyncIntermediateTensors

from vllm_ascend.distributed.edge_cloud_comm.types import (
    CommRequest,
    CommResult,
    CommStatus,
)


class _CommSyncedIntermediateTensors(AsyncIntermediateTensors):
    """AsyncIntermediateTensors whose sync point is a recorded NPU event.

    Equivalent to the legacy ``handle.wait()`` in ``wait_for_comm`` — but
    the bridge already happened on the channel stream at submit time, so
    ordering the consumer stream behind ``done_event`` achieves the same
    device-side ordering without touching HCCL handles here.
    """

    def __init__(
        self,
        tensors: dict[str, torch.Tensor],
        done_event: torch.npu.Event | None,
        comm_postprocess: list[Callable[[], None]] | None,
    ) -> None:
        super().__init__(
            tensors, comm_handles=None, comm_postprocess=comm_postprocess
        )
        self._done_event = done_event

    def wait_for_comm(self) -> None:
        if self._comm_waited:
            return
        if self._done_event is not None:
            # Device-side ordering only; returns immediately on the CPU.
            torch.npu.current_stream().wait_event(self._done_event)
        for fn in self._comm_postprocess or []:
            fn()
        self._comm_waited = True


class CommFuture:
    """Handle to one submitted communication request.

    * ``done()`` — pure CPU-side query (event.query()), no side effects.
    * ``wait()`` — blocking convenience for legacy/debug paths.
    * ``add_callback()`` — fired once on completion (by the channel reaper
      or by ``wait()``); callbacks must be cheap and non-blocking.
    * ``as_intermediate_tensors()`` — recv only: bridge into the existing
      lazy-consumption path of the model runner.

    For send requests the future owns a communication-layer payload copy
    (``_keepalive``) until completion.  The producer may therefore replay a
    graph or reuse its staging buffers without overwriting data that HCCL is
    still reading.

    Deferred futures (sequenced submission): when a request arrives with
    a ``seqno`` ahead of the channel's next expected one, the channel
    holds the request and returns a *deferred* future — not yet bound
    to any HCCL op.  The future binds in-place once the missing
    predecessors are submitted and the wire op is actually posted (see
    :meth:`_bind`).  ``done()`` is False while unbound; ``wait()`` and
    ``as_intermediate_tensors()`` block the CPU until binding (an
    out-of-order consumer has no device event to order behind yet —
    binding is normally instantaneous because early submission means
    the op was posted long before the consume point).
    """

    def __init__(
        self,
        request: CommRequest,
        handles: list[Any],
        done_event: torch.npu.Event | None,
        tensor_dict: dict[str, Any] | None,
        postprocess: list[Callable[[], None]],
        keepalive: Any,
    ) -> None:
        self._request = request
        self._handles = handles
        self._done_event = done_event
        self._tensor_dict = tensor_dict
        self._postprocess = postprocess
        self._keepalive = keepalive
        self._status = CommStatus.PENDING
        self._error: BaseException | None = None
        self._callbacks: list[Callable[[CommResult], None]] = []
        self._lock = threading.Lock()
        self._bound = True
        self._bind_event = threading.Event()
        self._bind_event.set()
        if done_event is None:
            # No cross-node op on this rank (non-PP-rank0 / world_size 1):
            # nothing to wait for; postprocess collectives still run at
            # consumption time via as_intermediate_tensors().
            self._status = CommStatus.OK
            self._keepalive = None

    @classmethod
    def deferred(cls, request: CommRequest) -> CommFuture:
        """Create an unbound future for a held (out-of-order) request."""
        self = cls.__new__(cls)
        self._request = request
        self._handles = None
        self._done_event = None
        self._tensor_dict = None
        self._postprocess = None
        self._keepalive = None
        self._status = CommStatus.PENDING
        self._error = None
        self._callbacks = []
        self._lock = threading.Lock()
        self._bound = False
        self._bind_event = threading.Event()
        return self

    def _bind(
        self,
        *,
        handles: list[Any],
        done_event: torch.npu.Event | None,
        tensor_dict: dict[str, Any] | None,
        postprocess: list[Callable[[], None]],
        keepalive: Any,
    ) -> None:
        """Bind a deferred future to its just-posted wire op.

        Called by the channel under its submission lock when the held
        request's seqno turn arrives.  From here on the future lives in
        the channel's pending queue and is reaped/finalized like any
        other.
        """
        with self._lock:
            assert not self._bound, "CommFuture._bind called twice"
            self._handles = handles
            self._done_event = done_event
            self._tensor_dict = tensor_dict
            self._postprocess = postprocess
            self._keepalive = keepalive
            self._bound = True
            if done_event is None:
                # No cross-node op on this rank: complete immediately,
                # same as the eager constructor path.
                self._status = CommStatus.OK
                self._keepalive = None
        self._bind_event.set()

    def _await_binding(self, timeout: float | None = None) -> None:
        if not self._bind_event.wait(timeout=timeout):
            raise TimeoutError(
                f"CommFuture binding timed out after {timeout}s: "
                f"{self._request.channel} {self._request.op} "
                f"seqno={self._request.seqno} (predecessor submissions "
                "missing?)"
            )

    # ------------------------------------------------------------------ #
    # Queries                                                             #
    # ------------------------------------------------------------------ #

    @property
    def request(self) -> CommRequest:
        return self._request

    def done(self) -> bool:
        """CPU-side, non-blocking.  Pure query — never fires callbacks."""
        if self._status != CommStatus.PENDING:
            return True
        if not self._bound:
            return False
        event = self._done_event
        return event is not None and event.query()

    def result(self) -> CommResult:
        return CommResult(
            status=self._status,
            tensor_dict=self._tensor_dict,
            error=self._error,
        )

    # ------------------------------------------------------------------ #
    # Synchronization                                                     #
    # ------------------------------------------------------------------ #

    def wait(self, timeout: float | None = None) -> CommResult:
        """Block the calling thread until completion (debug/legacy path).

        Production consume paths should use ``as_intermediate_tensors()``
        (device-side ordering, no CPU blocking past binding).
        """
        start = time.monotonic()
        self._await_binding(timeout=timeout)
        deadline = None if timeout is None else start + timeout
        while not self.done():
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError(
                    f"CommFuture.wait timed out after {timeout}s: "
                    f"{self._request.channel} {self._request.op}"
                )
            time.sleep(0.001)
        self._finalize()
        return self.result()

    def add_callback(self, fn: Callable[[CommResult], None]) -> None:
        with self._lock:
            if self._status is CommStatus.PENDING:
                self._callbacks.append(fn)
                return
        fn(self.result())

    # ------------------------------------------------------------------ #
    # Consumption bridge                                                  #
    # ------------------------------------------------------------------ #

    def as_intermediate_tensors(self) -> AsyncIntermediateTensors:
        """Recv only: wrap the received tensors for lazy consumption.

        Data readiness is enforced device-side (``wait_event``) the first
        time ``.tensors`` is accessed — no CPU-side ``query()`` needed.
        A still-deferred future (sequenced submission held behind missing
        predecessors) blocks the CPU here until the op is posted: there
        is no device event to order behind before that, and a consumer
        reaching this point genuinely cannot proceed without the recv.
        """
        assert self._request.op == "recv", (
            "as_intermediate_tensors() is only valid for recv requests"
        )
        self._await_binding()
        return _CommSyncedIntermediateTensors(
            self._tensor_dict, self._done_event, self._postprocess
        )

    # ------------------------------------------------------------------ #
    # Internal                                                            #
    # ------------------------------------------------------------------ #

    def _finalize(self, error: BaseException | None = None) -> bool:
        """Transition to a terminal state exactly once; fire callbacks.

        Called by the channel reaper (head-of-line query) and by
        ``wait()``. Releases the communication-owned send-buffer keepalive.
        """
        with self._lock:
            if self._status is not CommStatus.PENDING:
                return False
            self._status = CommStatus.ERROR if error else CommStatus.OK
            self._error = error
            self._keepalive = None
            callbacks, self._callbacks = self._callbacks, []
        result = self.result()
        for cb in callbacks:
            try:
                cb(result)
            except Exception:
                logger.exception(
                    "[edge-cloud-comm] completion callback failed: %s %s",
                    self._request.channel,
                    self._request.op,
                )
        return True
