# SPDX-License-Identifier: Apache-2.0
"""CPU replay of overlapping draft chains through real scheduler/channel code.

Only model execution, lifecycle bookkeeping and device I/O are stubbed. AST
loading avoids importing the NPU runtime; enqueue, admission, reservation, pick
and the channel reorder buffer execute the repository's actual methods.
Run directly with Python or with pytest --confcutdir=tests/ut/core.
"""

from __future__ import annotations

import ast
import importlib.util
import logging
import random
import sys
import threading
import unittest
from collections import deque
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]


def load_class(path, class_name, namespace, methods=None):
    tree = ast.parse(path.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    cls.bases = []
    if methods is not None:
        cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in methods]
    module = ast.Module(
        body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), cls],
        type_ignores=[],
    )
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
    return namespace[class_name]


def load_output():
    source = ROOT.parent / "vllm/vllm/v1/core/sched/output.py"
    if not source.exists():
        spec = importlib.util.find_spec("vllm")
        source = Path(spec.origin).parent / "v1/core/sched/output.py"
    spec = importlib.util.spec_from_file_location("_pd_order_test_output", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


class TestDraftChannelOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = load_output()
        bt = cls.output.BatchType
        cls.scheduler_type = load_class(
            ROOT / "vllm_ascend/core/pd_separated_scheduler.py",
            "PDSeparatedScheduler",
            dict(
                replace=replace,
                uuid4=uuid4,
                logger=logging.getLogger(__name__),
                BatchType=bt,
                _DRAFT_LAST_TYPES=(bt.PREFILL_DRAFT_LAST, bt.DECODE_DRAFT_LAST),
            ),
            {
                "_reserve_draft_seqnos",
                "enqueue_draft_first",
                "_enqueue_next_draft_first",
                "_pick_draft_first_batch",
                "_can_schedule_prefill_draft_first",
                "_can_schedule_decode_draft_first",
                "_pregenerate_draft_chain",
                "_next_draft_first_index",
            },
        )
        cls.channel_type = load_class(
            ROOT / "vllm_ascend/distributed/edge_cloud_comm/channel.py",
            "CommChannel",
            dict(
                threading=threading,
                deque=deque,
                logger=logging.getLogger(__name__),
                CommFuture=SimpleNamespace(deferred=lambda req: SimpleNamespace(request=req)),
            ),
        )

    def make_scheduler(self, steps=3):
        s = self.scheduler_type.__new__(self.scheduler_type)
        s.num_spec_tokens = steps
        s._prefill_draft_comm_seqno = s._decode_comm_seqno = 30
        s._reserved_draft_seqno_base = {}
        s._draft_seqno_order = {True: deque(), False: deque()}
        s._check_scheduled_edge_cloud_draft = lambda: True
        s._uses_async_scheduled_mtp_placeholders = lambda: True
        s._pregenerated_draft_task_ids = set()
        s._pregenerated_draft_req_ids = {}
        s._dead_draft_task_ids = set()
        s._dead_chain_publish_to_release = []
        s._draft_publish_pending = {}
        s._draft_publish_scalars_patched = set()
        s._draft_publish_dispatched = set()
        s._draft_remote_pending_limit = 2
        s.decode_or_draft_inflight_count = s.decode_head_inflight_count = 0
        s._force_decode_last = False
        s._is_stale_draft_output = lambda so: so.parent_req_id not in s.requests
        s._register_pd_flight = lambda so: None
        s._make_empty_batch = self.output.SchedulerOutput.make_empty
        s.requests = {}
        for lane in ("prefill", "decode"):
            setattr(s, f"{lane}_drafts_first_ready", deque())
            setattr(s, f"{lane}_drafts_last_ready", deque())
            setattr(s, f"{lane}_draft_remote_pending_count", 0)
            setattr(s, f"_force_{lane}_draft_last", False)
        return s

    def reserve(self, s, task, prefill=True):
        bt = self.output.BatchType
        parent = self.output.SchedulerOutput.make_empty()
        parent.batch_type = bt.PREFILL_FIRST if prefill else bt.DECODE_FIRST
        parent.head_token = task
        parent.num_scheduled_tokens = {task: 4105}
        parent.total_num_scheduled_tokens = 4105
        s.requests[task] = object()
        s._reserve_draft_seqnos(parent)
        parent.batch_type = bt.PREFILL_LAST if prefill else bt.DECODE_LAST
        return parent

    def enqueue(self, s, parent):
        s.enqueue_draft_first(parent, draft_task_id=parent.head_token, draft_step_idx=0)

    def can_pick(self, s, prefill=True):
        return (s._can_schedule_prefill_draft_first if prefill else s._can_schedule_decode_draft_first)()

    def take_tail(self, s, prefill=True):
        lane = "prefill" if prefill else "decode"
        tail = getattr(s, f"{lane}_drafts_last_ready").popleft()
        setattr(s, f"_force_{lane}_draft_last", False)
        # DRAFT_FIRST's local execution has completed, but its response may
        # still be in flight. Remote credit is returned only by finish_tail.
        if not prefill:
            s.decode_or_draft_inflight_count -= 1
        return tail

    def finish_tail(self, s, tail, prefill=True):
        attr = f"{'prefill' if prefill else 'decode'}_draft_remote_pending_count"
        setattr(s, attr, getattr(s, attr) - 1)
        s._enqueue_next_draft_first(tail)

    def drain(self, s, count, prefill=True):
        wire = self.channel_type(SimpleNamespace(value="prefill_draft_up" if prefill else "decode_up"))
        wire._next_seqno = 30
        sent = []
        wire._execute_next = lambda req, **kw: sent.append(req.seqno)
        for expected in range(30, 30 + count):
            self.assertTrue(self.can_pick(s, prefill), f"cannot dispatch expected seqno={expected}")
            head = s._pick_draft_first_batch(prefill)
            wire._submit_sequenced(SimpleNamespace(seqno=head.comm_seqno, op="send"))
            self.assertFalse(wire._held, f"wire stranded at {expected}: held={list(wire._held)}")
            self.assertEqual(sent[-1], expected)
            self.finish_tail(s, self.take_tail(s, prefill), prefill)
        self.assertFalse(s._draft_seqno_order[prefill])
        return sent

    def test_overlapping_dynamic_chains_follow_reserved_wire_order(self):
        for prefill in (True, False):
            with self.subTest(prefill=prefill):
                s = self.make_scheduler()
                for task in ("A", "B"):
                    self.enqueue(s, self.reserve(s, task, prefill))
                self.assertEqual(self.drain(s, 6, prefill), list(range(30, 36)))

    def test_reserved_parent_without_a_draft_task_blocks_later_chain(self):
        s = self.make_scheduler()
        a = self.reserve(s, "A")
        b = self.reserve(s, "B")
        self.enqueue(s, b)
        self.assertFalse(self.can_pick(s))
        self.assertEqual(s._pick_draft_first_batch(True).batch_type, self.output.BatchType.EMPTY)
        self.assertEqual(s.prefill_draft_remote_pending_count, 0)
        self.enqueue(s, a)
        self.drain(s, 6)

    def test_pregenerated_chain_cannot_overtake_unmaterialized_continuation(self):
        s = self.make_scheduler()
        a = self.reserve(s, "A")
        b = self.reserve(s, "B")
        self.enqueue(s, a)
        self.assertEqual(s._pick_draft_first_batch(True).comm_seqno, 30)
        tail = self.take_tail(s)
        # Both queues are empty, although A still owns seqnos 31 and 32.
        s._pregenerate_draft_chain(b)
        self.assertIn("B", s._pregenerated_draft_task_ids)
        self.assertFalse(self.can_pick(s))
        self.assertEqual(s._pick_draft_first_batch(True).batch_type, self.output.BatchType.EMPTY)
        self.finish_tail(s, tail)
        self.assertTrue(self.can_pick(s))
        self.assertEqual(s._pick_draft_first_batch(True).comm_seqno, 31)

    def test_pregenerated_chain_retains_one_step_lookahead(self):
        s = self.make_scheduler()
        s._pregenerate_draft_chain(self.reserve(s, "A"))
        self.assertTrue(self.can_pick(s))
        self.assertEqual(s._pick_draft_first_batch(True).comm_seqno, 30)
        tail = self.take_tail(s)
        self.assertTrue(self.can_pick(s))
        self.assertEqual(s._pick_draft_first_batch(True).comm_seqno, 31)
        self.take_tail(s)
        self.assertFalse(self.can_pick(s))  # remote credit exhausted
        self.finish_tail(s, tail)
        self.assertTrue(self.can_pick(s))

    def test_dead_chain_drains_before_live_chain(self):
        s = self.make_scheduler()
        a = self.reserve(s, "A")
        b = self.reserve(s, "B")
        self.enqueue(s, a)
        self.enqueue(s, b)
        s.requests.pop("A")
        self.drain(s, 6)
        self.assertIn("A", s._dead_draft_task_ids)

    def test_channel_lanes_are_independent(self):
        s = self.make_scheduler()
        self.reserve(s, "pending-prefill")
        self.enqueue(s, self.reserve(s, "ready-decode", prefill=False))
        self.drain(s, 3, prefill=False)

    def test_single_chain_and_mtp1_controls(self):
        for steps, tasks in ((3, ("A",)), (1, ("A", "B"))):
            with self.subTest(steps=steps):
                s = self.make_scheduler(steps)
                for task in tasks:
                    self.enqueue(s, self.reserve(s, task))
                self.drain(s, steps * len(tasks))

    def test_no_speculation_does_not_reserve_a_wire_range(self):
        s = self.make_scheduler(steps=0)
        self.reserve(s, "A")
        self.assertFalse(s._reserved_draft_seqno_base)
        self.assertFalse(s._draft_seqno_order[True])

    def test_legacy_unreserved_draft_still_uses_pick_time_seqno(self):
        s = self.make_scheduler(steps=1)
        s._check_scheduled_edge_cloud_draft = lambda: False
        self.enqueue(s, self.reserve(s, "A"))
        self.drain(s, 1)

    def test_channel_gap_logging_preserves_reorder_buffer(self):
        wire = self.channel_type(SimpleNamespace(value="prefill_draft_up"))
        wire._next_seqno = 30
        sent = []
        wire._execute_next = lambda req, **kw: sent.append(req.seqno)
        with self.assertLogs(__name__, level="WARNING") as logs:
            wire._submit_sequenced(SimpleNamespace(seqno=31, op="send"))
        self.assertIn("event=send_gap", logs.output[0])
        self.assertEqual(sent, [])
        self.assertEqual(list(wire._held), [31])
        with self.assertLogs(__name__, level="INFO") as logs:
            wire._submit_sequenced(SimpleNamespace(seqno=30, op="send"))
        self.assertIn("event=send_gap_released", logs.output[0])
        self.assertEqual(sent, [30, 31])
        self.assertFalse(wire._held)

    def test_randomized_ready_order_twenty_chains(self):
        for seed in range(100):
            with self.subTest(seed=seed):
                s = self.make_scheduler()
                parents = [self.reserve(s, str(i)) for i in range(20)]
                random.Random(seed).shuffle(parents)
                for parent in parents:
                    self.enqueue(s, parent)
                self.drain(s, 60)


if __name__ == "__main__":
    unittest.main()
