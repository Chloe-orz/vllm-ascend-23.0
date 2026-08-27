# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from vllm.sampling_params import SamplingParams
from vllm.v1.core.sched.output import (
    BatchType,
    CachedRequestData,
    EdgeCloudFinishedRequest,
    NewRequestData,
    SchedulerOutput,
)
from vllm.v1.engine.core import EngineCore, EngineCoreProc

import vllm_ascend

# The real ``vllm_ascend.patch.platform`` package __init__ installs every
# platform patch and imports NPU-only dependencies (torch_npu, einops, ...)
# that are absent on CPU-only dev machines. These tests only need the pure
# functions in ``patch_engine_core`` (which is still imported for real), so
# while this module runs, a lightweight stand-in for the package (same
# __path__, no __init__ side effects) is registered in sys.modules. The
# stand-in is installed and removed by the fixture below, so other test
# modules in the same pytest process still see the real package. The fixture
# returns the imported objects directly and does not mutate module globals.
_PLATFORM_PACKAGE = "vllm_ascend.patch.platform"
_ENGINE_CORE_PATCHED_ATTRIBUTES = (
    "__init__",
    "_drain_pd_channel_inbox",
    "_publish_to_cloud",
    "_maybe_publish_pre_out",
    "_release_deferred_draft_pre_out",
    "_close_draft_pre_out",
    "_ensure_pd_head_token",
    "_needs_sample_tokens",
    "_stash_empty_worker_cleanup",
    "_merge_pending_worker_cleanup",
    "_finish_empty_batch",
    "_defer_empty_batch",
    "_pop_deferred_empty_batch",
    "_advance_edge_cloud_draft",
    "_clear_pending_edge_cloud_draft_for_finished_requests",
    "_register_edge_cloud_draft_parent",
    "_uses_scheduled_edge_cloud_draft",
    "_has_unresolved_edge_cloud_draft_parent",
    "step",
    "step_with_batch_queue",
    "shutdown",
    "_vllm_ascend_engine_core_patched",
)
_ENGINE_CORE_PROC_PATCHED_ATTRIBUTES = (
    "run_engine_core",
    "_process_input_queue",
    "_process_engine_step",
)


def _snapshot_attributes(cls, names):
    return {name: (name in vars(cls), vars(cls).get(name)) for name in names}


def _restore_attributes(cls, snapshot):
    for name, (existed, value) in snapshot.items():
        if existed:
            setattr(cls, name, value)
        elif name in vars(cls):
            delattr(cls, name)


@pytest.fixture(scope="module")
def _import_tested_modules_with_platform_stub():
    monkeypatch = pytest.MonkeyPatch()
    existing_platform_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == _PLATFORM_PACKAGE or name.startswith(f"{_PLATFORM_PACKAGE}.")
    }
    engine_core_snapshot = _snapshot_attributes(EngineCore, _ENGINE_CORE_PATCHED_ATTRIBUTES)
    engine_core_proc_snapshot = _snapshot_attributes(EngineCoreProc, _ENGINE_CORE_PROC_PATCHED_ATTRIBUTES)
    try:
        if _PLATFORM_PACKAGE not in sys.modules:
            package = types.ModuleType(_PLATFORM_PACKAGE)
            package.__path__ = [str(Path(vllm_ascend.__file__).parent / "patch" / "platform")]
            monkeypatch.setitem(sys.modules, _PLATFORM_PACKAGE, package)

        from vllm_ascend.core.pd_separated_scheduler import (
            PDSeparatedScheduler as scheduler_cls,
        )
        from vllm_ascend.edge_cloud.prefix_protocol import PrefixHasher as hasher_cls
        from vllm_ascend.patch.platform.patch_engine_core import (
            _make_cloud_safe_scheduler_output as make_cloud_safe,
        )
        from vllm_ascend.patch.platform.patch_engine_core import (
            _maybe_publish_pre_out as maybe_publish,
        )
        from vllm_ascend.patch.platform.patch_engine_core import (
            _patched_step_with_batch_queue as step_with_batch_queue,
        )
        from vllm_ascend.patch.platform.patch_engine_core import (
            _publish_to_cloud as publish_to_cloud,
        )

        yield SimpleNamespace(
            scheduler_cls=scheduler_cls,
            hasher_cls=hasher_cls,
            make_cloud_safe=make_cloud_safe,
            maybe_publish=maybe_publish,
            publish_to_cloud=publish_to_cloud,
            step_with_batch_queue=step_with_batch_queue,
        )
    finally:
        _restore_attributes(EngineCore, engine_core_snapshot)
        _restore_attributes(EngineCoreProc, engine_core_proc_snapshot)
        monkeypatch.undo()
        for name in list(sys.modules):
            if (
                name == _PLATFORM_PACKAGE or name.startswith(f"{_PLATFORM_PACKAGE}.")
            ) and name not in existing_platform_modules:
                sys.modules.pop(name, None)
        sys.modules.update(existing_platform_modules)


class _RecordingChannel:
    def __init__(self):
        self.outputs = []
        self.control_outputs = []
        self.fail_next = False

    def publish(self, scheduler_output):
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("injected PRE_OUT publish failure")
        self.outputs.append(scheduler_output)

    def publish_control(self, scheduler_output):
        self.publish(scheduler_output)
        self.control_outputs.append(scheduler_output)


def test_async_batch_queue_forwards_control_only_empty(
    _import_tested_modules_with_platform_stub,
):
    scheduler_output = SchedulerOutput.make_empty()
    scheduler_output.cloud_draft_invalidate_task_ids = ["draft-1"]
    published = []
    scheduler = SimpleNamespace(
        has_requests=lambda: True,
        schedule=lambda: scheduler_output,
        _uses_async_scheduled_mtp_placeholders=lambda: False,
    )
    engine_core = SimpleNamespace(
        batch_queue=[],
        batch_queue_size=1,
        scheduler=scheduler,
        _has_unresolved_edge_cloud_draft_parent=lambda: False,
        _drain_pd_channel_inbox=lambda: None,
        _ensure_pd_head_token=lambda output: None,
        _maybe_publish_pre_out=published.append,
        _finish_empty_batch=lambda output: ("finished", output),
    )

    result = _import_tested_modules_with_platform_stub.step_with_batch_queue(
        engine_core,
    )

    assert published == [scheduler_output]
    assert result == ("finished", scheduler_output)


def test_cloud_projection_preserves_lengths_without_token_values(
    _import_tested_modules_with_platform_stub,
):
    new_request = NewRequestData(
        req_id="req-1",
        prompt_token_ids=[11, 12, 13],
        mm_features=[],
        sampling_params=SamplingParams(max_tokens=4),
        pooling_params=None,
        block_ids=([1],),
        num_computed_tokens=0,
        lora_request=None,
        prefill_token_ids=[11, 12],
    )
    cached = CachedRequestData(
        req_ids=["req-2"],
        resumed_req_ids=set(),
        new_token_ids=[[21]],
        all_token_ids={"req-2": np.array([31, 32], dtype=np.int32)},
        new_block_ids=[None],
        num_computed_tokens=[2],
        num_output_tokens=[1],
    )
    scheduler_output = SchedulerOutput(
        scheduled_new_reqs=[new_request],
        scheduled_cached_reqs=cached,
        num_scheduled_tokens={"req-1": 3, "req-2": 1},
        total_num_scheduled_tokens=4,
        scheduled_spec_decode_tokens={"req-2": [41, 42]},
        scheduled_encoder_inputs={},
        num_common_prefix_blocks=[0],
        finished_req_ids=set(),
        free_encoder_mm_hashes=[],
    )

    cloud_output = _import_tested_modules_with_platform_stub.make_cloud_safe(scheduler_output)

    assert cloud_output.scheduled_new_reqs[0].prompt_token_ids == [0, 0, 0]
    assert cloud_output.scheduled_new_reqs[0].prefill_token_ids == [0, 0]
    assert cloud_output.scheduled_cached_reqs.new_token_ids == [[0]]
    assert cloud_output.scheduled_cached_reqs.all_token_ids["req-2"].tolist() == [
        0,
        0,
    ]
    assert scheduler_output.scheduled_new_reqs[0].prompt_token_ids == [11, 12, 13]
    assert scheduler_output.scheduled_cached_reqs.new_token_ids == [[21]]
    assert cloud_output.scheduled_spec_decode_tokens == {"req-2": [0, 0]}
    assert scheduler_output.scheduled_spec_decode_tokens == {"req-2": [41, 42]}


def test_mtp_withheld_finish_republishes_accounting_with_request_id(
    _import_tested_modules_with_platform_stub,
):
    request_id = "engine-1"
    draft_task_id = "draft-1"
    finish = EdgeCloudFinishedRequest(
        control_request_id="control-1",
        prompt_tokens=8,
        completion_tokens=1,
        full_block_hashes=(b"prompt-block", b"output-block"),
    )
    request = SimpleNamespace(
        request_id=request_id,
        is_finished=lambda: True,
    )

    scheduler_cls = _import_tested_modules_with_platform_stub.scheduler_cls
    scheduler = scheduler_cls.__new__(scheduler_cls)
    scheduler._edge_cloud_draft_retention_enabled = True
    scheduler._edge_cloud_draft_req_tasks = {request_id: {draft_task_id}}
    scheduler._edge_cloud_draft_task_reqs = {draft_task_id: {request_id}}
    scheduler._draft_retained_requests = {draft_task_id: {request_id: request}}
    scheduler._cloud_withheld_finished_req_ids = set()
    scheduler._cloud_released_finished_req_ids = set()
    scheduler._pending_cloud_draft_invalidations = []
    scheduler._cloud_reported_draft_invalidations = set()
    scheduler._edge_cloud_finished_request_data = {request_id: finish}
    scheduler.requests = {request_id: request}
    scheduler._free_blocks = lambda retained: scheduler.requests.pop(retained.request_id)

    first_output = SchedulerOutput.make_empty()
    first_output.finished_req_ids = {request_id}
    scheduler._schedule_pd_separated = lambda: first_output

    channel = _RecordingChannel()
    engine_core = SimpleNamespace(
        scheduler=scheduler,
        _pp_pd_channel=channel,
        vllm_config=SimpleNamespace(
            additional_config={"edge_cloud_config": {"prefix_cache_coordination": {"enabled": True}}}
        ),
    )

    scheduled = scheduler.schedule()
    _import_tested_modules_with_platform_stub.publish_to_cloud(engine_core, scheduled)

    assert channel.outputs[0].finished_req_ids == set()
    assert not channel.outputs[0].edge_cloud_finished_requests
    assert scheduler._edge_cloud_finished_request_data == {request_id: finish}

    scheduler.release_draft_retained_blocks(draft_task_id)
    scheduler.invalidate_cloud_draft_tasks([draft_task_id])
    next_output = SchedulerOutput.make_empty()
    scheduler._schedule_pd_separated = lambda: next_output
    engine_core._publish_to_cloud = lambda output: (
        _import_tested_modules_with_platform_stub.publish_to_cloud(
            engine_core,
            output,
        )
    )

    channel.fail_next = True
    scheduled = scheduler.schedule()
    assert scheduled.batch_type == BatchType.EMPTY
    assert scheduled.cloud_draft_invalidate_task_ids == [draft_task_id]
    with pytest.raises(RuntimeError, match="injected PRE_OUT publish failure"):
        _import_tested_modules_with_platform_stub.maybe_publish(engine_core, scheduled)

    assert len(channel.outputs) == 1
    assert scheduler._cloud_released_finished_req_ids == {request_id}
    assert scheduler._edge_cloud_finished_request_data == {request_id: finish}
    assert scheduler._pending_cloud_draft_invalidations == [draft_task_id]
    assert scheduler._cloud_reported_draft_invalidations == set()

    retry_output = SchedulerOutput.make_empty()
    scheduler._schedule_pd_separated = lambda: retry_output
    scheduled = scheduler.schedule()
    assert scheduled.cloud_draft_invalidate_task_ids == [draft_task_id]
    _import_tested_modules_with_platform_stub.maybe_publish(engine_core, scheduled)

    assert channel.outputs[1].finished_req_ids == {request_id}
    assert channel.outputs[1].edge_cloud_finished_requests == {request_id: finish}
    assert channel.outputs[1].cloud_draft_invalidate_task_ids == [draft_task_id]
    assert channel.control_outputs == [channel.outputs[1]]
    assert scheduler._edge_cloud_finished_request_data == {}
    # The control manager has seen the invalidation, but it remains queued for
    # the next worker-executed FIRST batch to purge cached runner metadata.
    assert scheduler._pending_cloud_draft_invalidations == [draft_task_id]
    assert scheduler._cloud_reported_draft_invalidations == {draft_task_id}

    first_output = SchedulerOutput.make_empty()
    first_output.batch_type = BatchType.DECODE_FIRST
    scheduler._schedule_pd_separated = lambda: first_output

    scheduled = scheduler.schedule()

    assert scheduled.cloud_draft_invalidate_task_ids == [draft_task_id]
    assert scheduler._pending_cloud_draft_invalidations == [draft_task_id]
    assert scheduler._cloud_reported_draft_invalidations == {draft_task_id}

    _import_tested_modules_with_platform_stub.maybe_publish(engine_core, scheduled)

    assert scheduler._pending_cloud_draft_invalidations == []
    assert scheduler._cloud_reported_draft_invalidations == set()


def test_cloud_projection_clears_multimodal_fields_but_keeps_mrope_flag(
    _import_tested_modules_with_platform_stub,
):
    mm_feature = SimpleNamespace(
        modality="image",
        mm_hash="ab" * 32,
        mm_position=SimpleNamespace(offset=2, length=4),
    )
    new_request = NewRequestData(
        req_id="req-mm",
        prompt_token_ids=[11, 12, 13],
        mm_features=[mm_feature],
        sampling_params=SamplingParams(max_tokens=4),
        pooling_params=None,
        block_ids=([1],),
        num_computed_tokens=0,
        lora_request=None,
        prompt_is_token_ids=[True, True, True],
    )
    scheduler_output = SchedulerOutput(
        scheduled_new_reqs=[new_request],
        scheduled_cached_reqs=CachedRequestData.make_empty(),
        num_scheduled_tokens={"req-mm": 3},
        total_num_scheduled_tokens=3,
        scheduled_spec_decode_tokens={},
        scheduled_encoder_inputs={"req-mm": [0]},
        num_common_prefix_blocks=[0],
        finished_req_ids=set(),
        free_encoder_mm_hashes=["ab" * 32],
    )
    # Stamped dynamically by PDSeparatedScheduler; must survive the
    # projection so the cloud can align its M-RoPE data-plane recv.
    scheduler_output.has_mrope = True

    cloud_output = _import_tested_modules_with_platform_stub.make_cloud_safe(scheduler_output)

    cloud_request = cloud_output.scheduled_new_reqs[0]
    assert cloud_request.prompt_token_ids == [0, 0, 0]
    assert cloud_request.mm_features == []
    assert cloud_request.prompt_is_token_ids is None
    assert cloud_request.prompt_embeds is None
    assert cloud_output.scheduled_encoder_inputs == {}
    assert cloud_output.free_encoder_mm_hashes == []
    assert cloud_output.has_mrope is True

    # The worker-side original SchedulerOutput is untouched.
    assert scheduler_output.scheduled_new_reqs[0].mm_features == [mm_feature]
    assert scheduler_output.scheduled_new_reqs[0].prompt_token_ids == [11, 12, 13]
    assert scheduler_output.scheduled_encoder_inputs == {"req-mm": [0]}
    assert scheduler_output.free_encoder_mm_hashes == ["ab" * 32]


def test_cloud_projection_still_rejects_prompt_embeds(
    _import_tested_modules_with_platform_stub,
):
    new_request = NewRequestData(
        req_id="req-embeds",
        prompt_token_ids=[11, 12],
        mm_features=[],
        sampling_params=SamplingParams(max_tokens=4),
        pooling_params=None,
        block_ids=([1],),
        num_computed_tokens=0,
        lora_request=None,
        prompt_embeds=SimpleNamespace(shape=(2, 8)),
    )
    scheduler_output = SchedulerOutput(
        scheduled_new_reqs=[new_request],
        scheduled_cached_reqs=CachedRequestData.make_empty(),
        num_scheduled_tokens={"req-embeds": 2},
        total_num_scheduled_tokens=2,
        scheduled_spec_decode_tokens={},
        scheduled_encoder_inputs={},
        num_common_prefix_blocks=[0],
        finished_req_ids=set(),
        free_encoder_mm_hashes=[],
    )

    with pytest.raises(ValueError, match="prompt_embeds"):
        _import_tested_modules_with_platform_stub.make_cloud_safe(scheduler_output)


_FINISH_TENANT_KEY = b"finish-test-tenant-key-0"
_FINISH_BLOCK_SIZE = 16
_FINISH_PROCESSOR_FINGERPRINT = bytes(range(32))


def _finish_scheduler(tested_modules):
    scheduler_cls = tested_modules.scheduler_cls
    scheduler = scheduler_cls.__new__(scheduler_cls)
    scheduler._edge_cloud_prefix_hasher = tested_modules.hasher_cls(
        _FINISH_TENANT_KEY,
        _FINISH_BLOCK_SIZE,
        processor_fingerprint=_FINISH_PROCESSOR_FINGERPRINT,
    )
    scheduler._edge_cloud_finished_request_data = {}
    return scheduler


def _finish_request(mm_features, token_count=40, prompt_tokens=32):
    return SimpleNamespace(
        request_id="engine-1",
        edge_cloud_request_id="control-1",
        all_token_ids=list(range(token_count)),
        num_prompt_tokens=prompt_tokens,
        num_output_tokens=token_count - prompt_tokens,
        mm_features=mm_features,
    )


def _mm_feature(mm_hash="ab" * 32, offset=8, length=16):
    return SimpleNamespace(
        modality="image",
        mm_hash=mm_hash,
        mm_position=SimpleNamespace(offset=offset, length=length),
    )


def test_finish_recompute_matches_media_aware_manifest(
    _import_tested_modules_with_platform_stub,
):
    scheduler = _finish_scheduler(_import_tested_modules_with_platform_stub)
    scheduler._record_edge_cloud_finish(_finish_request([_mm_feature()]))

    record = scheduler._edge_cloud_finished_request_data["engine-1"]
    expected = scheduler._edge_cloud_prefix_hasher.build_manifest(
        "control-1",
        list(range(40)),
        media_items=[
            SimpleNamespace(
                modality="image",
                digest=bytes.fromhex("ab" * 32),
                offset=8,
                length=16,
            )
        ],
    )
    assert record.control_request_id == "control-1"
    assert record.prompt_tokens == 32
    assert record.completion_tokens == 8
    assert record.full_block_hashes == expected.full_block_hashes
    assert record.publish_cache is True


def test_finish_recompute_without_media_matches_v1_manifest(
    _import_tested_modules_with_platform_stub,
):
    scheduler = _finish_scheduler(_import_tested_modules_with_platform_stub)
    scheduler._record_edge_cloud_finish(_finish_request([]))

    record = scheduler._edge_cloud_finished_request_data["engine-1"]
    expected = scheduler._edge_cloud_prefix_hasher.build_manifest(
        "control-1",
        list(range(40)),
    )
    assert record.full_block_hashes == expected.full_block_hashes
    assert record.publish_cache is True


@pytest.mark.parametrize("mm_hash", ["zz" * 32, "ab" * 16, ""])
def test_finish_recompute_fails_closed_on_bad_mm_hash(mm_hash, _import_tested_modules_with_platform_stub):
    scheduler = _finish_scheduler(_import_tested_modules_with_platform_stub)
    scheduler._record_edge_cloud_finish(_finish_request([_mm_feature(mm_hash=mm_hash)]))

    # Fail closed: a finish record IS emitted (so the cloud can release the
    # request and close out usage) but with publish_cache=False and no hash
    # chain, so the cloud publishes nothing.
    record = scheduler._edge_cloud_finished_request_data["engine-1"]
    assert record.control_request_id == "control-1"
    assert record.prompt_tokens == 32
    assert record.completion_tokens == 8
    assert record.full_block_hashes == ()
    assert record.publish_cache is False


def test_finish_recompute_fails_closed_on_unknown_modality(
    _import_tested_modules_with_platform_stub,
):
    scheduler = _finish_scheduler(_import_tested_modules_with_platform_stub)
    feature = _mm_feature()
    feature.modality = "audio"
    scheduler._record_edge_cloud_finish(_finish_request([feature]))

    record = scheduler._edge_cloud_finished_request_data["engine-1"]
    assert record.full_block_hashes == ()
    assert record.publish_cache is False
