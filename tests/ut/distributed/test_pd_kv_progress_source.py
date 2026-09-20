# SPDX-License-Identifier: Apache-2.0
"""CPU regressions for bounded, non-mutating remote-KV wait diagnostics."""

from __future__ import annotations

import ast
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "vllm_ascend/distributed/kv_transfer/kv_p2p/mooncake_layerwise_connector.py"


def load_methods(class_name, names, namespace):
    tree = ast.parse(SOURCE.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    cls.bases = []
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(cls.body) == len(names)
    module = ast.Module(
        body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), cls],
        type_ignores=[],
    )
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)
    return namespace[class_name]


class TestKVReceiveProgress(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.log = MagicMock()
        namespace = dict(
            time=SimpleNamespace(monotonic=lambda: self.now),
            logger=self.log,
            PD_TRACE_PREFIX="[PD-TRACE]",
            KV_RECV_WAIT_LOG_INTERVAL_S=30.0,
            KV_RECV_WAIT_LOG_SAMPLE_SIZE=3,
            get_external_request_id=lambda req: req[:-9],
            _block_counts=lambda blocks: [len(group) for group in blocks],
        )
        receiver_type = load_methods(
            "KVCacheRecvingLayerThread",
            {
                "get_receive_progress",
                "update_done_task",
                "get_and_clear_done_requests",
                "get_and_clear_failed_requests",
            },
            namespace,
        )
        receiver = receiver_type()
        receiver.lock = threading.Lock()
        receiver.done_requests = set()
        receiver.failed_requests = set()
        receiver.task_tracker = {}
        receiver.local_engine_id = "D-test"
        receiver.tp_rank = 1
        receiver.is_alive = lambda: True
        self.receiver = receiver
        worker_type = load_methods(
            "MooncakeLayerwiseConnectorWorker",
            {"start_load_kv", "get_finished", "_log_pending_kv_receives"},
            namespace,
        )
        worker = worker_type()
        worker.vllm_config = SimpleNamespace(kv_transfer_config=SimpleNamespace(is_kv_consumer=True))
        worker.engine_id = "D-test"
        worker.tp_rank = 1
        worker.kv_recv_layer_thread = receiver
        worker.request_map = {}
        worker._recving_metadata = {}
        worker._recv_started_at = {}
        worker._last_recv_wait_log_ts = 0.0
        worker._invalid_block_ids = set()
        worker.virtual_request = set()
        self.worker = worker

    def register(self, req="request", virtual=False):
        internal_id = req + "-12345678"
        metadata = SimpleNamespace(
            requests={internal_id: SimpleNamespace(do_virtual=virtual, local_block_ids=[[1, 2]])}
        )
        self.worker.start_load_kv(metadata)
        return internal_id

    def test_snapshot_preserves_partial_and_completed_signals(self):
        self.receiver.update_done_task("partial", 2, "P-edge")
        self.receiver.update_done_task("complete", 1, "P-cloud")
        before = {key: value.copy() for key, value in self.receiver.task_tracker.items()}
        snapshot = self.receiver.get_receive_progress(["missing", "partial", "complete"])
        self.assertEqual(snapshot["missing"]["received_signals"], 0)
        self.assertEqual(snapshot["partial"]["received_signals"], 1)
        self.assertTrue(snapshot["complete"]["ready_for_collection"])
        self.assertEqual(self.receiver.task_tracker, before)
        self.assertEqual(self.receiver.done_requests, {"complete"})

    def test_wait_log_is_bounded_rate_limited_and_does_not_unblock(self):
        for i in range(20):
            self.register(str(i))
        self.worker.get_finished()
        self.log.warning.assert_not_called()
        self.now += 31
        self.assertEqual(self.worker.get_finished(), (set(), set()))
        self.log.warning.assert_called_once()
        args = self.log.warning.call_args.args
        self.assertIn("event=kv_receive_wait", args[0])
        self.assertEqual(args[4], 20)
        self.assertEqual(len(args[6]), 3)
        self.assertEqual(args[6][0]["wait_s"], 31.0)
        self.assertEqual(len(self.worker.request_map), 20)
        self.now += 1
        self.worker.get_finished()
        self.log.warning.assert_called_once()
        self.now += 30
        self.worker.get_finished()
        self.assertEqual(self.log.warning.call_count, 2)

    def test_repeated_registration_does_not_reset_wait_age(self):
        req = self.register()
        self.now += 10
        self.register()
        self.assertEqual(self.worker._recv_started_at[req], 100.0)

    def test_completion_clears_wait_and_returns_internal_id(self):
        req = self.register()
        self.receiver.update_done_task("request", 1, "P-cloud")
        self.assertEqual(self.worker.get_finished(), (set(), {req}))
        self.assertFalse(self.worker.request_map)
        self.assertFalse(self.worker._recv_started_at)
        self.now += 60
        self.worker.get_finished()
        self.log.warning.assert_not_called()

    def test_failure_clears_wait_without_claiming_success(self):
        self.register()
        self.receiver.failed_requests.add("request")
        self.assertEqual(self.worker.get_finished(), (set(), set()))
        self.assertEqual(self.worker._invalid_block_ids, {1, 2})
        self.assertFalse(self.worker._recv_started_at)

    def test_virtual_receive_never_enters_wait_diagnostics(self):
        req = self.register(virtual=True)
        self.assertFalse(self.worker._recv_started_at)
        self.assertEqual(self.worker.get_finished(), (set(), {req}))


if __name__ == "__main__":
    unittest.main()
