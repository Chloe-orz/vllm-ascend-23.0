# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

import queue
import threading

import pytest
from vllm.v1.core.sched.output import SchedulerOutput

import vllm_ascend.v1.engine.passive_core as passive_core
from vllm_ascend.v1.engine.passive_core import PPSchedulerZmqPublisher


class _RecordingPush:
    def __init__(self, error=None):
        self.error = error
        self.messages = []

    def send_multipart(self, message):
        if self.error is not None:
            raise self.error
        self.messages.append(message)


def _start_publisher(push):
    publisher = PPSchedulerZmqPublisher.__new__(PPSchedulerZmqPublisher)
    publisher._queue = queue.Queue(maxsize=2)
    publisher._running = True
    publisher._seq = 0
    publisher._push = push
    publisher._thread = threading.Thread(
        target=publisher._publisher_thread,
        daemon=True,
    )
    publisher._thread.start()
    return publisher


def _stop_publisher(publisher):
    publisher._running = False
    publisher._queue.put_nowait(None)
    publisher._thread.join(timeout=1.0)


def test_control_publish_waits_for_successful_zmq_handoff():
    push = _RecordingPush()
    publisher = _start_publisher(push)
    try:
        publisher.publish_control(SchedulerOutput.make_empty())
    finally:
        _stop_publisher(publisher)

    assert len(push.messages) == 1


@pytest.mark.parametrize("failure", ["serialize", "send"])
def test_control_publish_surfaces_background_failure(failure, monkeypatch):
    push = _RecordingPush(RuntimeError("send failed") if failure == "send" else None)
    if failure == "serialize":

        def fail_dumps(*args, **kwargs):
            raise RuntimeError("serialize failed")

        monkeypatch.setattr(
            passive_core.pickle,
            "dumps",
            fail_dumps,
        )
    publisher = _start_publisher(push)
    try:
        with pytest.raises(RuntimeError, match="control publish failed"):
            publisher.publish_control(SchedulerOutput.make_empty())
    finally:
        _stop_publisher(publisher)


def test_control_publish_rejects_stopped_publisher():
    publisher = PPSchedulerZmqPublisher.__new__(PPSchedulerZmqPublisher)
    publisher._running = False

    with pytest.raises(RuntimeError, match="stopped"):
        publisher.publish_control(SchedulerOutput.make_empty())


def test_control_publish_rejects_full_bridge_queue():
    publisher = PPSchedulerZmqPublisher.__new__(PPSchedulerZmqPublisher)
    publisher._running = True
    publisher._seq = 0
    publisher._queue = queue.Queue(maxsize=1)
    publisher._queue.put_nowait((0, SchedulerOutput.make_empty(), None))

    with pytest.raises(RuntimeError, match="queue is full"):
        publisher.publish_control(SchedulerOutput.make_empty())
