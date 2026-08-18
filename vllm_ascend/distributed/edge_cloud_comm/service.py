# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""EdgeCloudCommService: singleton entry point of the comm layer.

Compute side only ever calls ``submit_send`` / ``submit_recv`` and
consumes ``CommFuture`` notifications.  ``poll_completions`` is meant to
be invoked from an existing host loop head (worker busy loop / scheduler
loop); it drives completion callbacks and the ``SchedulerCommSink``
interface reserved for event-driven tail scheduling.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Protocol, runtime_checkable

from vllm.logger import logger

from vllm_ascend.distributed import parallel_state as ps
from vllm_ascend.distributed.edge_cloud_comm.channel import CommChannel
from vllm_ascend.distributed.edge_cloud_comm.future import CommFuture
from vllm_ascend.distributed.edge_cloud_comm.mapping import transport_for
from vllm_ascend.distributed.edge_cloud_comm.types import (
    BatchKind,
    CommChannelType,
    CommRequest,
    CommResult,
)


@runtime_checkable
class SchedulerCommSink(Protocol):
    """Reserved worker/comm -> scheduler completion-feedback interface.

    This period's scheduler-side implementation is intentionally a no-op;
    it exists so event-driven tail scheduling (design doc section 6) can be
    switched on later without touching the comm layer.
    """

    def on_comm_complete(
        self,
        channel: CommChannelType,
        kind: BatchKind,
        result: CommResult,
    ) -> None: ...


class EdgeCloudCommService:
    """Process-wide singleton.  All public methods are thread-safe."""

    _instance: EdgeCloudCommService | None = None
    _instance_lock = threading.Lock()

    @classmethod
    def instance(cls) -> EdgeCloudCommService:
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        # HCCL ordering is per physical (process group, peer).  Each
        # directional channel owns its communicator, and shared-model
        # virtual workers share those communicators with different
        # explicit peers — so the FIFO key is the pair, not the channel
        # type alone.
        self._channels: dict[tuple[Any, int], CommChannel] = {}
        self._lock = threading.Lock()
        self._submission_condition = threading.Condition(self._lock)
        self._active_submissions = 0
        self._sinks: list[SchedulerCommSink] = []
        self._shutting_down = False

    # ------------------------------------------------------------------ #
    # Submission                                                          #
    # ------------------------------------------------------------------ #

    def submit_send(self, request: CommRequest) -> CommFuture:
        assert request.op == "send", "submit_send requires op='send'"
        return self._submit(request)

    def submit_recv(self, request: CommRequest) -> CommFuture:
        """Submit a recv.  The irecv is posted immediately — "early" is a
        property of when you submit, not a separate API.  The caller (worker
        or scheduler, via the reserved 8.3-1 interface) simply holds the
        returned future until the consume point."""
        assert request.op == "recv", "submit_recv requires op='recv'"
        return self._submit(request)

    # ------------------------------------------------------------------ #
    # Completion driving                                                  #
    # ------------------------------------------------------------------ #

    def poll_completions(self) -> int:
        """Reap every channel once and notify registered sinks.

        Call from an existing loop head; costs one head-of-line
        ``event.query()`` per channel with pending traffic.
        """
        with self._lock:
            channels = list(self._channels.values())
        completed = 0
        for channel in channels:
            for future in channel.reap():
                completed += 1
                self._notify_sinks(future)
        return completed

    def register_sink(self, sink: SchedulerCommSink) -> None:
        """Register a completion sink.  Type-idempotent: a second instance
        of the same class is ignored, so shared-model virtual workers
        co-located in one process don't pile up duplicate sinks."""
        with self._lock:
            if any(type(s) is type(sink) for s in self._sinks):
                return
            self._sinks.append(sink)

    def unregister_sink(self, sink: SchedulerCommSink) -> None:
        with self._lock:
            if sink in self._sinks:
                self._sinks.remove(sink)

    # ------------------------------------------------------------------ #
    # Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    def shutdown(self, timeout: float | None = None) -> None:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._submission_condition:
            if self._shutting_down:
                return
            self._shutting_down = True
            while self._active_submissions:
                remaining = (
                    None
                    if deadline is None
                    else deadline - time.monotonic()
                )
                if remaining is not None and remaining <= 0:
                    self._shutting_down = False
                    raise TimeoutError(
                        "edge-cloud comm shutdown timed out waiting for "
                        "active submissions"
                    )
                self._submission_condition.wait(timeout=remaining)
            channels = list(self._channels.values())
        try:
            for channel in channels:
                remaining = (
                    None
                    if deadline is None
                    else max(0.0, deadline - time.monotonic())
                )
                for future in channel.shutdown(timeout=remaining):
                    self._notify_sinks(future)
        except BaseException:
            with self._lock:
                self._shutting_down = False
            raise
        with self._lock:
            self._channels.clear()
            self._sinks.clear()
            self._shutting_down = False
        logger.info("[edge-cloud-comm] service shut down")

    # ------------------------------------------------------------------ #
    # Internal                                                            #
    # ------------------------------------------------------------------ #

    def _submit(self, request: CommRequest) -> CommFuture:
        channel, request = self._channel_for(request, reserve=True)
        try:
            return channel.submit(request)
        finally:
            with self._submission_condition:
                self._active_submissions -= 1
                self._submission_condition.notify_all()

    def _channel_for(
        self, request: CommRequest, *, reserve: bool = False
    ) -> tuple[CommChannel, CommRequest]:
        wire = CommChannel.wire_for_request(request)
        pp_group = ps.get_pp_group()
        peer = request.src_dst
        if peer is None:
            rank = pp_group.rank_in_group
            if request.op == "send":
                peer = (rank + 1) % pp_group.world_size
            else:
                peer = (rank - 1) % pp_group.world_size

        if pp_group.world_size <= 1 or wire in ("plain", "draft_dynamic"):
            device_group = pp_group.device_group
        elif wire in ("hidden", "draft"):
            # Identity resolution: the channel owns its communicator.
            device_group = ps._get_edge_cloud_hidden_channel_device_group(
                pp_group, channel=transport_for(request.channel)
            )
        else:
            raise ValueError(f"Unsupported edge-cloud wire type: {wire!r}")
        key = (device_group, peer)
        with self._lock:
            if self._shutting_down:
                raise RuntimeError("edge-cloud comm service is shutting down")
            channel = self._channels.get(key)
            if channel is None:
                channel = CommChannel(request.channel)
                self._channels[key] = channel
                logger.info(
                    "[edge-cloud-comm] created channel %s "
                    "(peer=%s wire=%s)",
                    request.channel.value,
                    peer,
                    wire,
                )
            if reserve:
                self._active_submissions += 1
        return channel, request

    def _notify_sinks(self, future: CommFuture) -> None:
        with self._lock:
            sinks = list(self._sinks)
        if not sinks:
            return
        result = future.result()
        for sink in sinks:
            try:
                sink.on_comm_complete(
                    future.request.channel, future.request.kind, result
                )
            except Exception:
                logger.exception(
                    "[edge-cloud-comm] sink notification failed: %s %s",
                    future.request.channel,
                    future.request.op,
                )


def get_comm_service() -> EdgeCloudCommService:
    return EdgeCloudCommService.instance()
