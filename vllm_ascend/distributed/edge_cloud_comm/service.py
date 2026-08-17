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
from typing import Protocol, runtime_checkable

from vllm.logger import logger
from vllm.v1.core.sched.output import HiddenChannelType

from vllm_ascend.distributed.edge_cloud_comm.channel import CommChannel
from vllm_ascend.distributed.edge_cloud_comm.future import CommFuture
from vllm_ascend.distributed.edge_cloud_comm.mapping import default_transport
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

    _instance: "EdgeCloudCommService | None" = None
    _instance_lock = threading.Lock()

    @classmethod
    def instance(cls) -> "EdgeCloudCommService":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        # Keyed by transport (wire identity), not logical channel type:
        # HCCL P2P FIFO matching is per (device group, peer).
        self._channels: dict[HiddenChannelType, CommChannel] = {}
        self._lock = threading.Lock()
        self._sinks: list[SchedulerCommSink] = []

    # ------------------------------------------------------------------ #
    # Submission                                                          #
    # ------------------------------------------------------------------ #

    def submit_send(self, request: CommRequest) -> CommFuture:
        assert request.op == "send", "submit_send requires op='send'"
        return self._channel_for(request).submit(request)

    def submit_recv(self, request: CommRequest) -> CommFuture:
        """Submit a recv.  The irecv is posted immediately — "early" is a
        property of when you submit, not a separate API.  The caller (worker
        or scheduler, via the reserved 8.3-1 interface) simply holds the
        returned future until the consume point."""
        assert request.op == "recv", "submit_recv requires op='recv'"
        return self._channel_for(request).submit(request)

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
        with self._lock:
            self._sinks.append(sink)

    def unregister_sink(self, sink: SchedulerCommSink) -> None:
        with self._lock:
            if sink in self._sinks:
                self._sinks.remove(sink)

    # ------------------------------------------------------------------ #
    # Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    def shutdown(self) -> None:
        with self._lock:
            channels = list(self._channels.values())
            self._channels.clear()
            self._sinks.clear()
        for channel in channels:
            for future in channel.reap():
                pass  # drain completed
        logger.info("[edge-cloud-comm] service shut down")

    # ------------------------------------------------------------------ #
    # Internal                                                            #
    # ------------------------------------------------------------------ #

    def _channel_for(self, request: CommRequest) -> CommChannel:
        transport = request.transport or default_transport(request.channel)
        with self._lock:
            channel = self._channels.get(transport)
            if channel is None:
                channel = CommChannel(request.channel, transport)
                self._channels[transport] = channel
                logger.info(
                    "[edge-cloud-comm] created channel %s (transport=%s)",
                    request.channel.value,
                    transport,
                )
        return channel

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
