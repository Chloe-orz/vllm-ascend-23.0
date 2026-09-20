# SPDX-License-Identifier: Apache-2.0
"""Replay target/draft interleaving through the real KV lifecycle on CPU.

Only NPU compute, address calculation and transport are stubbed. The upstream
binding/finalization mixin, cloud draft entry point, producer's layer queue and
sender's terminal-layer completion decision execute from their actual sources.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import importlib.util
import queue
import random
import time
import unittest
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[3]
CONNECTOR = ROOT / "vllm_ascend/distributed/kv_transfer/kv_p2p/mooncake_layerwise_connector.py"
RUNNER = ROOT / "vllm_ascend/worker/model_runner_v1.py"
VLLM = ROOT.parent / "vllm/vllm"
if not VLLM.exists():
    VLLM = Path(importlib.util.find_spec("vllm").origin).parent


@dataclass
class TargetBatch:
    head_token: str
    kv_connector_metadata: object
    num_scheduled_tokens: dict
    finished_req_ids: set = field(default_factory=set)
    batch_type: str = "prefill"


class Positions:
    shape = (1,)

    def __getitem__(self, _):
        return self

    def clone(self):
        return self


def load_class(path, name, namespace, methods=None, bases=()):
    tree = ast.parse(path.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    cls.bases = [ast.Name(id=base, ctx=ast.Load()) for base in bases]
    if methods is not None:
        cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in methods]
    module = ast.Module(
        body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), cls],
        type_ignores=[],
    )
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
    return namespace[name]


class TestCloudKVTaskContext(unittest.TestCase):
    TARGET_LAYERS = 64
    DRAFT_STEPS = 3

    def setUp(self):
        self.log = MagicMock()
        ns = dict(
            __name__=__name__,
            dataclass=dataclass,
            field=field,
            replace=replace,
            copy=copy,
            _freeze_scheduled_state=copy.deepcopy,
            CloudDraftPositionState=NS,
            BatchType=NS(PREFILL_FIRST="prefill"),
            contextlib=contextlib,
            contextmanager=contextlib.contextmanager,
            nullcontext=contextlib.nullcontext,
            logger=self.log,
            time=time,
            PD_TRACE_PREFIX="[PD-TRACE]",
            get_external_request_id=lambda req: req,
            _block_counts=lambda blocks: list(map(len, blocks)),
            MambaSpec=type("MambaSpec", (), {}),
            KVConnectorOutput=NS,
            has_kv_transfer_group=lambda: True,
            get_kv_transfer_group=lambda: self.connector,
            get_forward_context=lambda: NS(),
            is_forward_context_available=lambda: False,
            is_edge_device=lambda: False,
            CUDAGraphMode=NS(NONE=None),
            BatchDescriptor=lambda _: None,
            set_ascend_forward_context=lambda **_: contextlib.nullcontext(),
            IntermediateTensors=NS,
        )
        self.ns = ns
        for name in ("SendTask", "TransferMeta", "MooncakeLayerwiseConnectorMetadata"):
            load_class(CONNECTOR, name, ns)
        base = load_class(
            VLLM / "distributed/kv_transfer/kv_connector/v1/base.py",
            "KVConnectorBase_V1",
            ns,
            {
                "bind_connector_metadata",
                "clear_connector_metadata",
                "has_connector_metadata",
                "_get_connector_metadata",
            },
        )
        ns["KVConnectorBase"] = base
        worker_type = load_class(CONNECTOR, "MooncakeLayerwiseConnectorWorker", ns, {"start_load_kv", "save_kv_layer"})
        worker = worker_type()
        worker.current_layer = -1  # Also run this harness against the pre-fix implementation.
        worker.total_layers = self.TARGET_LAYERS + 1
        worker.engine_id = "P-cloud"
        worker.vllm_config = NS(kv_transfer_config=NS(is_kv_consumer=False, is_kv_producer=True))
        worker.kv_cache_specs = [object()]
        worker.num_kv_cache_groups = 1
        worker.pd_head_ratio = 1
        worker.enable_kv_quant = worker.enable_c8_quant = False
        names = [f"target.{i}" for i in range(self.TARGET_LAYERS)] + ["mtp.0"]
        worker.layer_metadata = {name: NS(tensor_group_idx=[0]) for name in names}
        worker.index_to_name = {i: [name] for i, name in enumerate(names)}
        worker._align_remote_block_ids = MagicMock()
        worker._get_kv_split_metadata = lambda *_: {
            ("D", 30200): dict(local_block_ids=[1], remote_block_ids=[2], trans_count=1)
        }
        worker._get_kernel_block_ids = lambda blocks: blocks
        worker.update_decoder_info = lambda _, meta: meta
        worker.kv_send_layer_thread = NS(send_queue=queue.Queue())
        self.worker = worker
        connector_type = load_class(
            CONNECTOR,
            "MooncakeLayerwiseConnector",
            ns,
            {"start_load_kv", "save_kv_layer", "wait_for_save"},
            bases=("KVConnectorBase_V1",),
        )
        self.connector = connector_type()
        self.connector.connector_worker = worker
        self.connector._connector_metadata = None
        self.connector.get_finished = lambda _: (set(), set())
        for name in (
            "get_block_ids_with_load_errors",
            "get_kv_connector_stats",
            "get_kv_connector_kv_cache_events",
            "build_connector_worker_meta",
        ):
            setattr(self.connector, name, lambda: None)
        load_class(
            VLLM / "v1/worker/kv_connector_model_runner_mixin.py",
            "KVConnectorModelRunnerMixin",
            ns,
            {"maybe_get_kv_connector_output", "_get_kv_connector_output", "finalize_kv_connector"},
        )
        runner_type = load_class(
            RUNNER,
            "NPUModelRunner",
            ns,
            {
                "_run_edge_cloud_draft_middle_segment",
                "_finalize_cloud_draft_kv_connector",
                "_cloud_draft_kv_context",
                "_purge_invalidated_cloud_draft_metadata",
                "_cache_cloud_spec_decode_metadata",
            },
            bases=("KVConnectorModelRunnerMixin",),
        )
        self.runner = runner_type()
        self.runner.num_spec_tokens = self.DRAFT_STEPS
        self.runner.speculative_config = NS(method="mtp")
        self.runner.vllm_config = worker.vllm_config
        self.runner._uses_scheduled_edge_cloud_draft = lambda: True
        self.runner._edge_cloud_enabled = True
        self.runner._cloud_pending_request_corrections = {}
        self.runner._cloud_spec_decode_metadata_cache_max = 32
        self.runner._cloud_actual_num_computed_by_req = {}
        self.runner._cloud_latest_target_generation_by_req = {}
        self.runner._cloud_target_generation = 0
        self.runner._reconstruct_cloud_draft_positions = lambda *_: None
        self.runner._sync_edge_cloud_draft_intermediate_tensors = lambda _, tensors: tensors
        self.runner._chunk_deepseek_v4_mtp_draft_positions = lambda pos: pos
        self.runner._build_edge_cloud_draft_attn_metadata = lambda *_: None
        for name in (
            "_cloud_scheduler_output_by_task",
            "_cloud_spec_decode_metadata_by_task",
            "_cloud_draft_position_state_by_task",
            "_cloud_target_generation_by_task",
            "_eagle3_cloud_aux_hidden_states_by_task",
        ):
            setattr(self.runner, name, {})
        self.runner._edge_cloud_draft_segments = {"c": self.draft_compute}
        self.observed_bindings = []
        self.attn_metadata = NS(reshape_cache_event=MagicMock())
        sender_type = load_class(CONNECTOR, "KVCacheSendingLayerThread", ns, {"_transfer_kv_cache"})
        self.sender = sender_type()
        self.sender.layer_metadata = worker.layer_metadata
        self.sender.pd_head_ratio = 1
        self.sender.total_layers = worker.total_layers
        self.sender.failed_reqs = set()
        self.sender.get_transfer_meta = lambda *_: ([100], [200], [16])
        self.sender.engine = NS(batch_transfer_sync_write=lambda *_: 0)
        self.completed = []
        self.sender.callback_func = lambda req, *_args, **_kwargs: self.completed.append(req)

    def scheduler(self, task, chunk_finish=True):
        cache = self.runner._cloud_scheduler_output_by_task
        if task not in cache:
            meta = self.ns["MooncakeLayerwiseConnectorMetadata"]()
            meta.requests[task] = NS(
                local_block_ids=[[1]],
                remote_block_ids=[[2]],
                remote_engine_id="D",
                remote_host="D",
                remote_port=30200,
                remote_te_rpc_port=12345,
                chunk_finish=chunk_finish,
            )
            target = TargetBatch(head_token=task, kv_connector_metadata=meta, num_scheduled_tokens={task: 1})
            self.runner.input_batch = NS(req_ids=[task], num_computed_tokens_cpu=[0])
            self.runner._cache_cloud_spec_decode_metadata(target, NS(), 1, Positions())
            self.assertIsNot(cache[task], target)
            self.assertIs(cache[task].kv_connector_metadata, meta)
        return cache[task]

    def target(self, task, start=0, end=TARGET_LAYERS, chunk_finish=True):
        scheduler = self.scheduler(task, chunk_finish)
        # Same context used by execute_model and _execute_layerwise_continuation.
        with self.runner.maybe_get_kv_connector_output(scheduler, defer_finalize=True):
            for i in range(start, end):
                # Include unnamed GDN callbacks: their lookup also depends on the cursor.
                name = "" if i % 4 != 3 else f"target.{i}"
                self.connector.save_kv_layer(name, [], self.attn_metadata)

    def draft_compute(self, **kwargs):
        bound = self.connector._connector_metadata
        self.observed_bindings.append(tuple(bound.requests) if bound is not None else ())
        # Match attention's has_connector_metadata guard (which hid the original bug).
        if self.connector.has_connector_metadata():
            self.connector.save_kv_layer("mtp.0", [], self.attn_metadata)
        return NS(tensors={})

    def draft(self, task, step):
        self.runner._run_edge_cloud_draft_middle_segment(
            NS(draft_task_id=task, draft_step_idx=step, num_accepted_tokens=None, valid_sampled_token_count=None),
            NS(tensors={"hidden_states": NS(shape=(1, 1))}),
        )

    def drain(self):
        tasks = []
        while not self.worker.kv_send_layer_thread.send_queue.empty():
            task = self.worker.kv_send_layer_thread.send_queue.get_nowait()
            tasks.append(task)
            self.sender._transfer_kv_cache(task)
        return tasks

    def test_serial_control(self):
        for task in ("A", "B"):
            self.target(task)
            for step in range(self.DRAFT_STEPS):
                self.draft(task, step)
        self.drain()
        self.assertEqual(self.completed, ["A", "B"])

    def test_deployed_order_completes_a_and_b_exactly_once(self):
        self.target("A")
        self.target("B")
        for task in ("A", "B"):
            for step in range(self.DRAFT_STEPS):
                self.draft(task, step)
        tasks = self.drain()
        self.assertEqual(self.completed, ["A", "B"])
        self.assertEqual(self.observed_bindings, [("A",)] * 3 + [("B",)] * 3)
        for request in ("A", "B"):
            self.assertEqual([t.layer_idx for t in tasks if request in t.send_request], list(range(65)))

    def test_interleaved_draft_steps_keep_b_after_a_finalizes(self):
        self.target("A")
        self.target("B")
        for step in range(self.DRAFT_STEPS):
            self.draft("A", step)
            self.draft("B", step)
        self.drain()
        self.assertEqual(self.completed, ["A", "B"])
        self.assertEqual(self.observed_bindings, [("A",), ("B",)] * 3)

    def test_layer_slices_do_not_restart_or_reexpand_transfer_plan(self):
        self.target("A", end=16)
        self.target("B")
        self.target("A", start=16)
        for task in ("A", "B"):
            for step in range(self.DRAFT_STEPS):
                self.draft(task, step)
        tasks = self.drain()
        self.assertEqual(self.completed, ["A", "B"])
        self.assertEqual(self.worker._align_remote_block_ids.call_count, 2)
        self.assertEqual(
            [t.layer_name for t in tasks if "A" in t.send_request], [f"target.{i}" for i in range(64)] + ["mtp.0"]
        )

    def test_empty_poll_between_steps_does_not_replace_a_or_b(self):
        self.target("A")
        self.target("B")
        for task in ("A", "B"):
            for step in range(self.DRAFT_STEPS):
                empty = self.ns["MooncakeLayerwiseConnectorMetadata"]()
                with self.runner.maybe_get_kv_connector_output(
                    NS(kv_connector_metadata=empty, finished_req_ids=set()),
                ):
                    pass
                self.draft(task, step)
        self.drain()
        self.assertEqual(self.completed, ["A", "B"])
        self.assertFalse(self.runner._cloud_scheduler_output_by_task)
        self.assertFalse(self.connector.has_connector_metadata())

    def test_missing_task_does_not_silently_use_b(self):
        self.target("B")
        with self.assertRaisesRegex(RuntimeError, "no matching target KV metadata"):
            self.draft("missing", 0)
        self.assertFalse(self.observed_bindings)
        self.drain()
        self.assertFalse(self.completed)

    def test_compute_error_unbinds_a_without_deleting_b(self):
        self.target("A")
        self.target("B")
        self.runner._edge_cloud_draft_segments["c"] = MagicMock(side_effect=RuntimeError("compute failed"))
        with self.assertRaisesRegex(RuntimeError, "compute failed"):
            self.draft("A", 0)
        self.assertFalse(self.connector.has_connector_metadata())
        self.assertEqual(self.runner._cloud_scheduler_output_by_task["B"].kv_connector_metadata.current_layer, 64)
        self.runner._edge_cloud_draft_segments["c"] = self.draft_compute
        for step in range(self.DRAFT_STEPS):
            self.draft("B", step)
        self.drain()
        self.assertEqual(self.completed, ["B"])

    def test_invalidated_task_releases_snapshot_but_not_queued_transfers(self):
        self.target("A")
        self.draft("A", 0)
        self.target("B")
        self.runner._purge_invalidated_cloud_draft_metadata(["A"])
        self.assertNotIn("A", self.runner._cloud_scheduler_output_by_task)
        for step in range(self.DRAFT_STEPS):
            self.draft("B", step)
        self.drain()
        self.assertEqual(self.completed, ["A", "B"])

    def test_evicted_task_cannot_borrow_latest_transfer_plan(self):
        self.runner._cloud_spec_decode_metadata_cache_max = 1
        self.target("A")
        self.target("B")
        self.assertNotIn("A", self.runner._cloud_scheduler_output_by_task)
        with self.assertRaisesRegex(RuntimeError, "no matching target KV metadata"):
            self.draft("A", 0)
        for step in range(self.DRAFT_STEPS):
            self.draft("B", step)
        self.drain()
        self.assertEqual(self.completed, ["B"])

    def test_nonfinal_chunk_never_emits_request_completion(self):
        self.target("chunk", chunk_finish=False)
        for step in range(self.DRAFT_STEPS):
            self.draft("chunk", step)
        self.target("last")
        for step in range(self.DRAFT_STEPS):
            self.draft("last", step)
        self.drain()
        self.assertEqual(self.completed, ["last"])

    def test_nonproducer_and_no_connector_keep_legacy_path(self):
        for producer, has_group, scheduled in ((False, True, True), (True, False, True), (True, True, False)):
            with self.subTest(producer=producer, has_group=has_group, scheduled=scheduled):
                self.worker.vllm_config.kv_transfer_config.is_kv_producer = producer
                self.ns["has_kv_transfer_group"] = lambda enabled=has_group: enabled
                self.runner._uses_scheduled_edge_cloud_draft = lambda enabled=scheduled: enabled
                with self.runner._cloud_draft_kv_context(NS(draft_task_id="no-target", draft_step_idx=0)):
                    pass

    def test_unprepared_metadata_fails_before_queuing(self):
        self.connector.bind_connector_metadata(self.scheduler("A").kv_connector_metadata)
        with self.assertRaisesRegex(RuntimeError, "before preparing this batch"):
            self.connector.save_kv_layer("mtp.0", [], self.attn_metadata)
        self.assertTrue(self.worker.kv_send_layer_thread.send_queue.empty())

    def test_no_speculation_new_batches_each_complete(self):
        # The conventional producer uses the same metadata-local counter.
        self.worker.total_layers = self.sender.total_layers = self.TARGET_LAYERS
        for task in ("A", "B"):
            with self.runner.maybe_get_kv_connector_output(self.scheduler(task), defer_finalize=False):
                for i in range(self.TARGET_LAYERS):
                    self.connector.save_kv_layer(f"target.{i}", [], self.attn_metadata)
        self.drain()
        self.assertEqual(self.completed, ["A", "B"])

    def test_task_key_is_not_request_id_and_batched_requests_share_cursor(self):
        for task in ("task-A", "task-B"):
            meta = self.scheduler(task).kv_connector_metadata
            request = meta.requests.pop(task)
            meta.requests = {f"request-{task}-1": request, f"request-{task}-2": copy.deepcopy(request)}
            self.target(task)
        for task in ("task-A", "task-B"):
            for step in range(self.DRAFT_STEPS):
                self.draft(task, step)
        self.drain()
        self.assertEqual(
            self.completed, ["request-task-A-1", "request-task-A-2", "request-task-B-1", "request-task-B-2"]
        )

    def test_randomized_hundred_requests_twenty_active_tasks(self):
        rng = random.Random(20260920)
        active = {}
        admitted = 0
        request_count = 100
        max_active = 20
        while admitted < request_count or active:
            if admitted < request_count and (not active or (len(active) < max_active and rng.random() < 0.6)):
                task = f"task-{admitted}"
                admitted += 1
                self.target(task)
                active[task] = 0
            else:
                task = rng.choice(list(active))
                step = active[task]
                self.draft(task, step)
                if step + 1 == self.DRAFT_STEPS:
                    del active[task]
                else:
                    active[task] += 1
            if rng.random() < 0.25:
                self.drain()
        self.drain()
        self.assertCountEqual(self.completed, [f"task-{i}" for i in range(request_count)])
        self.assertFalse(self.runner._cloud_scheduler_output_by_task)


if __name__ == "__main__":
    unittest.main()
