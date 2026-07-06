# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project.
"""Behavioral tests for ``PDSeparatedScheduler``'s deferred-finish logic.

When a request is aborted/finished while its edge tail segment (PL/DL) is
still in flight on the cloud, the finish must be *deferred* until the tail
returns.  Finishing immediately would pop the req from the worker's
``self.requests``/``input_batch`` before the tail's ``_update_states`` runs,
causing a ``KeyError`` (and data-plane token misalignment in
``_prepare_inputs``), because the cloud has already committed hidden tensors
sized to ``total_num_scheduled_tokens`` for that req.

These tests exercise the scheduler-side defer / flush state machine directly,
without a full VllmConfig / cloud round-trip.
"""
from unittest.mock import patch

from vllm.v1.core.sched.scheduler import Scheduler
from vllm.v1.request import RequestStatus

from vllm_ascend.core.pd_separated_scheduler import PDSeparatedScheduler


class _FakeReq:
    """Minimal stand-in for vllm.Request used by the defer logic."""

    def __init__(self, req_id: str, client_index: int = 0) -> None:
        self.request_id = req_id
        self.client_index = client_index
        self.status = RequestStatus.RUNNING

    def is_finished(self) -> bool:
        return RequestStatus.is_finished(self.status)


def _bare_scheduler() -> PDSeparatedScheduler:
    """A PDSeparatedScheduler instance with only the attributes the
    defer/flush logic touches — no VllmConfig / kv_cache_manager needed."""
    s = object.__new__(PDSeparatedScheduler)
    s._in_flight_tail_req_ids = set()
    s._deferred_finish = {}
    s.requests = {}
    s.running = []
    s.chunk_prefill_first = []
    s.prefill_last_pending = []
    return s


def _recording_parent():
    """Build a stand-in for ``Scheduler.finish_requests`` that records calls
    and returns a parent-shaped result without touching KV blocks."""
    calls = []

    def fake(self, request_ids, finished_status):
        calls.append((request_ids, finished_status))
        if request_ids is None:
            ids = list(self.requests.keys())
        elif isinstance(request_ids, str):
            ids = [request_ids]
        else:
            ids = list(request_ids)
        return [(r, self.requests[r].client_index)
                for r in ids if r in self.requests]

    return fake, calls


def test_abort_in_flight_tail_is_deferred():
    """An abort for a req whose tail is in flight must NOT reach the parent;
    it is recorded as deferred and removed from running, but kept in
    self.requests for the in-flight tail."""
    s = _bare_scheduler()
    a = _FakeReq("A", client_index=1)
    b = _FakeReq("B", client_index=2)
    s.requests = {"A": a, "B": b}
    s.running = [a, b]
    s._in_flight_tail_req_ids = {"A"}  # A's tail (PL/DL) is in flight

    fake, calls = _recording_parent()
    with patch.object(Scheduler, "finish_requests", new=fake):
        result = s.finish_requests({"A", "B"}, RequestStatus.FINISHED_ABORTED)

    # Only B (not in flight) is finished immediately via the parent.
    assert len(calls) == 1
    assert calls[0][0] == {"B"}
    assert calls[0][1] == RequestStatus.FINISHED_ABORTED
    # A is deferred, not finished.
    assert s._deferred_finish == {"A": RequestStatus.FINISHED_ABORTED}
    # A removed from running so it is not re-scheduled...
    assert a not in s.running
    # ...but still tracked in self.requests (kept for the in-flight tail).
    assert "A" in s.requests
    # Both reported as aborted to the caller.
    assert {r[0] for r in result} == {"A", "B"}


def test_abort_not_in_flight_finishes_immediately():
    s = _bare_scheduler()
    a = _FakeReq("A")
    s.requests = {"A": a}
    s.running = [a]
    # A not in _in_flight_tail_req_ids.

    fake, calls = _recording_parent()
    with patch.object(Scheduler, "finish_requests", new=fake):
        s.finish_requests({"A"}, RequestStatus.FINISHED_ABORTED)

    assert len(calls) == 1
    assert calls[0] == ({"A"}, RequestStatus.FINISHED_ABORTED)
    assert s._deferred_finish == {}


def test_flush_is_noop_while_tail_in_flight_then_completes_on_return():
    s = _bare_scheduler()
    a = _FakeReq("A")
    s.requests = {"A": a}
    s._deferred_finish = {"A": RequestStatus.FINISHED_ABORTED}
    s._in_flight_tail_req_ids = {"A"}

    fake, calls = _recording_parent()
    with patch.object(Scheduler, "finish_requests", new=fake):
        # Tail still in flight -> flush is a no-op.
        s._flush_completed_deferred_finishes()
        assert calls == []
        assert "A" in s._deferred_finish

        # Tail returns -> A no longer in flight -> flush completes the finish.
        s._in_flight_tail_req_ids.discard("A")
        s._flush_completed_deferred_finishes()

    assert len(calls) == 1
    assert calls[0] == ({"A"}, RequestStatus.FINISHED_ABORTED)
    assert "A" not in s._deferred_finish


def test_deferred_prefill_req_is_removed_from_prefill_last_pending():
    """A deferred prefill req must be removed from prefill_last_pending so the
    PL routing loop does not re-route it to running."""
    s = _bare_scheduler()
    a = _FakeReq("A")
    s.requests = {"A": a}
    s.prefill_last_pending = [a]
    s._in_flight_tail_req_ids = {"A"}

    fake, calls = _recording_parent()
    with patch.object(Scheduler, "finish_requests", new=fake):
        s.finish_requests({"A"}, RequestStatus.FINISHED_ABORTED)

    assert calls == []  # nothing finished immediately
    assert a not in s.prefill_last_pending
    assert s._deferred_finish == {"A": RequestStatus.FINISHED_ABORTED}


def test_double_abort_does_not_double_defer():
    s = _bare_scheduler()
    a = _FakeReq("A", client_index=3)
    s.requests = {"A": a}
    s.running = [a]
    s._in_flight_tail_req_ids = {"A"}
    s._deferred_finish = {"A": RequestStatus.FINISHED_ABORTED}

    fake, calls = _recording_parent()
    with patch.object(Scheduler, "finish_requests", new=fake):
        result = s.finish_requests({"A"}, RequestStatus.FINISHED_ABORTED)

    assert calls == []  # already deferred -> parent not called
    assert all(r[0] != "A" for r in result)
    assert s._deferred_finish == {"A": RequestStatus.FINISHED_ABORTED}


def test_finish_all_force_clears_deferred():
    """finish_requests(None) (shutdown) force-completes deferred reqs whose
    tails will never return."""
    s = _bare_scheduler()
    a = _FakeReq("A")
    s.requests = {"A": a}
    s._deferred_finish = {"A": RequestStatus.FINISHED_ABORTED}
    s._in_flight_tail_req_ids = {"A"}

    fake, calls = _recording_parent()
    with patch.object(Scheduler, "finish_requests", new=fake):
        s.finish_requests(None, RequestStatus.FINISHED_ABORTED)

    assert len(calls) == 1
    assert calls[0][0] is None
    assert s._deferred_finish == {}
    assert s._in_flight_tail_req_ids == set()
