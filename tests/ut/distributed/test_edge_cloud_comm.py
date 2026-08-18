# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""CPU-only tests for edge-cloud communication ownership and ordering."""

import threading
import time
from types import SimpleNamespace

import torch

from vllm_ascend.distributed.edge_cloud_comm.channel import CommChannel
from vllm_ascend.distributed.edge_cloud_comm.future import CommFuture
from vllm_ascend.distributed.edge_cloud_comm.service import EdgeCloudCommService
from vllm_ascend.distributed.edge_cloud_comm.types import (
    BatchKind,
    CommChannelType,
    CommRequest,
)


def _send_request(*, peer: int = 1, value: torch.Tensor | None = None):
    return CommRequest(
        channel=CommChannelType.PREFILL_UP,
        op="send",
        kind=BatchKind.PREFILL,
        num_tokens=1,
        tensor_dict={"hidden_states": value if value is not None else torch.tensor([1.0])},
        src_dst=peer,
        wire="plain",
    )


def _completed_future(request: CommRequest) -> CommFuture:
    return CommFuture(
        request=request,
        handles=[],
        done_event=None,
        tensor_dict=None,
        postprocess=[],
        keepalive=None,
    )


def test_send_uses_owned_tensor_snapshot(monkeypatch):
    channel = CommChannel(CommChannelType.PREFILL_UP)
    source = torch.tensor([1.0, 2.0])
    captured = {}

    def capture_send(request):
        captured.update(request.tensor_dict)
        return []

    monkeypatch.setattr(channel, "_wire_send", capture_send)
    monkeypatch.setattr(channel, "_bridge_and_record", lambda handles, request: None)

    future = channel.submit(_send_request(value=source))
    source.fill_(99)

    sent = captured["hidden_states"]
    assert sent.data_ptr() != source.data_ptr()
    torch.testing.assert_close(sent, torch.tensor([1.0, 2.0]))
    assert future.request.tensor_dict is None


def test_submit_serializes_complete_wire_launch(monkeypatch):
    channel = CommChannel(CommChannelType.PREFILL_UP)
    state_lock = threading.Lock()
    active = 0
    max_active = 0

    def fake_execute(request, predecessor, into=None):
        nonlocal active, max_active
        with state_lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.02)
        with state_lock:
            active -= 1
        return _completed_future(request)

    monkeypatch.setattr(channel, "_execute", fake_execute)
    threads = [threading.Thread(target=channel.submit, args=(_send_request(),)) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_active == 1


def test_service_separates_default_group_peers(monkeypatch):
    service = EdgeCloudCommService()
    pp_group = SimpleNamespace(
        rank_in_group=0,
        world_size=3,
        device_group=object(),
    )
    monkeypatch.setattr(
        "vllm_ascend.distributed.edge_cloud_comm.service.ps.get_pp_group",
        lambda: pp_group,
    )

    peer_one, _ = service._channel_for(_send_request(peer=1))
    peer_two, _ = service._channel_for(_send_request(peer=2))
    peer_one_again, _ = service._channel_for(_send_request(peer=1))

    assert peer_one is peer_one_again
    assert peer_one is not peer_two


def test_service_shutdown_waits_for_active_submission(monkeypatch):
    service = EdgeCloudCommService()
    pp_group = SimpleNamespace(
        rank_in_group=0,
        world_size=2,
        device_group=object(),
    )
    monkeypatch.setattr(
        "vllm_ascend.distributed.edge_cloud_comm.service.ps.get_pp_group",
        lambda: pp_group,
    )
    channel, _ = service._channel_for(_send_request())
    submit_entered = threading.Event()
    release_submit = threading.Event()
    shutdown_done = threading.Event()

    def blocking_submit(request):
        submit_entered.set()
        assert release_submit.wait(timeout=1.0)
        return _completed_future(request)

    def shutdown_service():
        service.shutdown(timeout=1.0)
        shutdown_done.set()

    monkeypatch.setattr(channel, "submit", blocking_submit)
    monkeypatch.setattr(channel, "shutdown", lambda timeout=None: [])

    submit_thread = threading.Thread(target=service.submit_send, args=(_send_request(),))
    shutdown_thread = threading.Thread(target=shutdown_service)
    submit_thread.start()
    assert submit_entered.wait(timeout=1.0)
    shutdown_thread.start()

    assert not shutdown_done.wait(timeout=0.05)
    release_submit.set()
    submit_thread.join()
    shutdown_thread.join()

    assert shutdown_done.is_set()


def test_channel_shutdown_waits_before_dropping_pending():
    channel = CommChannel(CommChannelType.PREFILL_UP)
    waited = threading.Event()

    class PendingFuture:
        complete = False

        def done(self):
            return self.complete

        def wait(self, timeout=None):
            waited.set()
            self.complete = True

        def _finalize(self):
            return True

    future = PendingFuture()
    channel._pending.append(future)

    drained = channel.shutdown(timeout=1.0)

    assert waited.is_set()
    assert drained == [future]
    assert not channel._pending


def test_plain_recv_uses_default_group(monkeypatch):
    channel = CommChannel(CommChannelType.PREFILL_DOWN)
    captured = {}

    def recv(**kwargs):
        captured.update(kwargs)
        return {}, [], []

    monkeypatch.setattr(
        "vllm_ascend.distributed.edge_cloud_comm.channel.ps.edge_cloud_broadcast_recv",
        recv,
    )
    request = CommRequest(
        channel=CommChannelType.PREFILL_DOWN,
        op="recv",
        kind=BatchKind.PREFILL,
        num_tokens=1,
        wire="plain",
    )

    channel._wire_recv(request)

    assert captured["channel"] is None


def _recv_request(*, seqno: int | None = None):
    return CommRequest(
        channel=CommChannelType.PREFILL_UP,
        op="recv",
        kind=BatchKind.PREFILL,
        num_tokens=1,
        seqno=seqno,
        wire="plain",
    )


def test_sequenced_submit_reorders_out_of_order_arrivals(monkeypatch):
    channel = CommChannel(CommChannelType.PREFILL_UP)
    executed: list[int | None] = []

    def fake_recv(request):
        executed.append(request.seqno)
        return {}, [], []

    monkeypatch.setattr(channel, "_wire_recv", fake_recv)
    monkeypatch.setattr(channel, "_bridge_and_record", lambda handles, request: None)

    deferred = channel.submit(_recv_request(seqno=2))
    # Out-of-order: held, not posted, future not bound.
    assert executed == []
    assert not deferred.done()

    channel.submit(_recv_request(seqno=0))
    assert executed == [0]
    assert not deferred.done()

    channel.submit(_recv_request(seqno=1))
    # Submitting the missing predecessor drains the held request in order.
    assert executed == [0, 1, 2]
    assert deferred.done()
    assert deferred.wait(timeout=1.0).status.value == "ok"


def test_sequenced_submit_rejects_replayed_seqno(monkeypatch):
    channel = CommChannel(CommChannelType.PREFILL_UP)
    monkeypatch.setattr(channel, "_wire_recv", lambda request: ({}, [], []))
    monkeypatch.setattr(channel, "_bridge_and_record", lambda handles, request: None)

    channel.submit(_recv_request(seqno=0))
    try:
        channel.submit(_recv_request(seqno=0))
    except RuntimeError:
        pass
    else:
        raise AssertionError("replayed seqno was not rejected")


def test_deferred_consumer_blocks_until_bound(monkeypatch):
    channel = CommChannel(CommChannelType.PREFILL_UP)
    executed = []

    def fake_recv(request):
        executed.append(request.seqno)
        return {"x": 1}, [], []

    monkeypatch.setattr(channel, "_wire_recv", fake_recv)
    monkeypatch.setattr(channel, "_bridge_and_record", lambda handles, request: None)

    deferred = channel.submit(_recv_request(seqno=1))
    got = {}

    def consumer():
        # Blocks on binding until seqno=0 is submitted, then materializes.
        got["tensors"] = deferred.as_intermediate_tensors().tensors

    thread = threading.Thread(target=consumer)
    thread.start()
    time.sleep(0.05)
    assert executed == [] and "tensors" not in got
    channel.submit(_recv_request(seqno=0))
    thread.join(timeout=2.0)
    assert executed == [0, 1]
    assert got["tensors"] == {"x": 1}


def test_hidden_wire_resolves_identity_transport(monkeypatch):
    # wire="hidden" recv must resolve the channel's own communicator
    # (identity mapping): channel kwarg is the HiddenChannelType of the
    # same value.
    from vllm.v1.core.sched.output import HiddenChannelType

    channel = CommChannel(CommChannelType.PREFILL_UP)
    captured = {}

    def recv(**kwargs):
        captured.update(kwargs)
        return {}, [], []

    monkeypatch.setattr(
        "vllm_ascend.distributed.edge_cloud_comm.channel.ps.edge_cloud_broadcast_recv",
        recv,
    )
    channel._wire_recv(
        CommRequest(
            channel=CommChannelType.PREFILL_UP,
            op="recv",
            kind=BatchKind.PREFILL,
            num_tokens=4,
        )
    )
    assert captured["channel"] is HiddenChannelType.PREFILL_UP
