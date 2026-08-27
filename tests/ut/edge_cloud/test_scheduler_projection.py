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

import vllm_ascend

# The real ``vllm_ascend.patch.platform`` package __init__ installs every
# platform patch and imports NPU-only dependencies (torch_npu, einops, ...)
# that are absent on CPU-only dev machines. These tests only need the pure
# functions in ``patch_engine_core`` (which is still imported for real), so
# while this module runs, a lightweight stand-in for the package (same
# __path__, no __init__ side effects) is registered in sys.modules. The
# stand-in is installed and removed by the fixture below, so other test
# modules in the same pytest process still see the real package. The names
# imported under the stub are bound to module globals by that fixture
# before the first test runs.
_PLATFORM_PACKAGE = "vllm_ascend.patch.platform"

PDSeparatedScheduler = None
PrefixHasher = None
_make_cloud_safe_scheduler_output = None
_publish_to_cloud = None


@pytest.fixture(scope="module", autouse=True)
def _import_tested_modules_with_platform_stub():
    monkeypatch = pytest.MonkeyPatch()
    if _PLATFORM_PACKAGE not in sys.modules:
        package = types.ModuleType(_PLATFORM_PACKAGE)
        package.__path__ = [str(Path(vllm_ascend.__file__).parent / "patch" / "platform")]
        monkeypatch.setitem(sys.modules, _PLATFORM_PACKAGE, package)

    global PDSeparatedScheduler, PrefixHasher
    global _make_cloud_safe_scheduler_output, _publish_to_cloud
    from vllm_ascend.core.pd_separated_scheduler import (
        PDSeparatedScheduler as scheduler_cls,
    )
    from vllm_ascend.edge_cloud.prefix_protocol import PrefixHasher as hasher_cls
    from vllm_ascend.patch.platform.patch_engine_core import (
        _make_cloud_safe_scheduler_output as make_cloud_safe,
    )
    from vllm_ascend.patch.platform.patch_engine_core import (
        _publish_to_cloud as publish_to_cloud,
    )

    PDSeparatedScheduler = scheduler_cls
    PrefixHasher = hasher_cls
    _make_cloud_safe_scheduler_output = make_cloud_safe
    _publish_to_cloud = publish_to_cloud
    try:
        yield
    finally:
        monkeypatch.undo()


class _RecordingChannel:
    def __init__(self):
        self.outputs = []

    def publish(self, scheduler_output):
        self.outputs.append(scheduler_output)


def test_cloud_projection_preserves_lengths_without_token_values():
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

    cloud_output = _make_cloud_safe_scheduler_output(scheduler_output)

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


def test_mtp_withheld_finish_republishes_accounting_with_request_id():
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

    scheduler = PDSeparatedScheduler.__new__(PDSeparatedScheduler)
    scheduler._edge_cloud_draft_retention_enabled = True
    scheduler._edge_cloud_draft_req_tasks = {request_id: {draft_task_id}}
    scheduler._edge_cloud_draft_task_reqs = {draft_task_id: {request_id}}
    scheduler._draft_retained_requests = {draft_task_id: {request_id: request}}
    scheduler._cloud_withheld_finished_req_ids = set()
    scheduler._cloud_released_finished_req_ids = set()
    scheduler._pending_cloud_draft_invalidations = []
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
    _publish_to_cloud(engine_core, scheduled)

    assert channel.outputs[0].finished_req_ids == set()
    assert not channel.outputs[0].edge_cloud_finished_requests
    assert scheduler._edge_cloud_finished_request_data == {request_id: finish}

    scheduler.release_draft_retained_blocks(draft_task_id)
    next_output = SchedulerOutput.make_empty()
    next_output.batch_type = BatchType.DECODE_FIRST
    scheduler._schedule_pd_separated = lambda: next_output

    scheduled = scheduler.schedule()
    _publish_to_cloud(engine_core, scheduled)

    assert channel.outputs[1].finished_req_ids == {request_id}
    assert channel.outputs[1].edge_cloud_finished_requests == {request_id: finish}
    assert scheduler._edge_cloud_finished_request_data == {}


def test_cloud_projection_clears_multimodal_fields_but_keeps_mrope_flag():
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

    cloud_output = _make_cloud_safe_scheduler_output(scheduler_output)

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


def test_cloud_projection_still_rejects_prompt_embeds():
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
        _make_cloud_safe_scheduler_output(scheduler_output)


_FINISH_TENANT_KEY = b"finish-test-tenant-key-0"
_FINISH_BLOCK_SIZE = 16
_FINISH_PROCESSOR_FINGERPRINT = bytes(range(32))


def _finish_scheduler():
    scheduler = PDSeparatedScheduler.__new__(PDSeparatedScheduler)
    scheduler._edge_cloud_prefix_hasher = PrefixHasher(
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


def test_finish_recompute_matches_media_aware_manifest():
    scheduler = _finish_scheduler()
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


def test_finish_recompute_without_media_matches_v1_manifest():
    scheduler = _finish_scheduler()
    scheduler._record_edge_cloud_finish(_finish_request([]))

    record = scheduler._edge_cloud_finished_request_data["engine-1"]
    expected = scheduler._edge_cloud_prefix_hasher.build_manifest(
        "control-1",
        list(range(40)),
    )
    assert record.full_block_hashes == expected.full_block_hashes
    assert record.publish_cache is True


@pytest.mark.parametrize("mm_hash", ["zz" * 32, "ab" * 16, ""])
def test_finish_recompute_fails_closed_on_bad_mm_hash(mm_hash):
    scheduler = _finish_scheduler()
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


def test_finish_recompute_fails_closed_on_unknown_modality():
    scheduler = _finish_scheduler()
    feature = _mm_feature()
    feature.modality = "audio"
    scheduler._record_edge_cloud_finish(_finish_request([feature]))

    record = scheduler._edge_cloud_finished_request_data["engine-1"]
    assert record.full_block_hashes == ()
    assert record.publish_cache is False
