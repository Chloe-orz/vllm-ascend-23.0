# SPDX-License-Identifier: Apache-2.0

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from vllm.v1.core.sched.output import BatchType, SchedulerOutput

from vllm_ascend.worker.model_runner_v1 import NPUModelRunner


@patch(
    "vllm_ascend.worker.model_runner_v1.has_ec_transfer",
    return_value=False,
)
@patch("vllm_ascend.worker.model_runner_v1.get_kv_transfer_group")
@patch(
    "vllm_ascend.worker.model_runner_v1.has_kv_transfer_group",
    return_value=True,
)
@patch("vllm_ascend.worker.model_runner_v1.get_pp_group")
def test_empty_input_batch_still_polls_kv_connector(
    mock_get_pp_group,
    _mock_has_kv_transfer_group,
    mock_get_kv_transfer_group,
    _mock_has_ec_transfer,
):
    runner = NPUModelRunner.__new__(NPUModelRunner)
    runner.vllm_config = SimpleNamespace(model_config=SimpleNamespace(enable_return_routed_experts=False))
    runner.model_config = SimpleNamespace(is_encoder_decoder=False)
    runner.ascend_config = SimpleNamespace(profiling_chunk_config=SimpleNamespace(need_timing=False))
    runner.parallel_config = SimpleNamespace(
        distributed_executor_backend="mp",
        data_parallel_size=1,
    )
    runner.execute_model_state = None
    runner._edge_cloud_enabled = False
    runner.input_batch = SimpleNamespace(num_reqs=0, req_ids=[])
    runner.speculative_config = None
    runner.use_async_scheduling = False
    runner.num_spec_tokens = 0
    runner.pcp_size = 1
    runner.supports_mm_inputs = False
    runner._start_dump_data = MagicMock()
    runner.synchronize_input_prep = MagicMock(return_value=nullcontext())
    runner._update_states = MagicMock(return_value=None)
    expected_output = object()
    runner.kv_connector_no_forward = MagicMock(return_value=expected_output)

    scheduler_output = SchedulerOutput.make_empty()
    scheduler_output.batch_type = BatchType.PD_MIX
    scheduler_output.kv_connector_metadata = object()
    mock_get_pp_group.return_value = SimpleNamespace(
        world_size=1,
        is_first_rank=True,
        is_last_rank=True,
    )

    result = runner.execute_model(scheduler_output)

    assert result is expected_output
    runner.kv_connector_no_forward.assert_called_once_with(scheduler_output, runner.vllm_config)
    mock_get_kv_transfer_group.return_value.handle_preemptions.assert_called_once_with(
        scheduler_output.kv_connector_metadata
    )
