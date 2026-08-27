# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

from types import SimpleNamespace

import numpy as np
from vllm.sampling_params import SamplingParams
from vllm.v1.core.sched.output import (
    BatchType,
    CachedRequestData,
    EdgeCloudFinishedRequest,
    NewRequestData,
    SchedulerOutput,
)

from vllm_ascend.core.pd_separated_scheduler import PDSeparatedScheduler
from vllm_ascend.patch.platform.patch_engine_core import (
    _make_cloud_safe_scheduler_output,
    _publish_to_cloud,
)


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
