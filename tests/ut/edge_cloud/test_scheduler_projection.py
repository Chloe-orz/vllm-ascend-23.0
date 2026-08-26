# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

import numpy as np
from vllm.sampling_params import SamplingParams
from vllm.v1.core.sched.output import (
    CachedRequestData,
    NewRequestData,
    SchedulerOutput,
)

from vllm_ascend.patch.platform.patch_engine_core import (
    _make_cloud_safe_scheduler_output,
)


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
