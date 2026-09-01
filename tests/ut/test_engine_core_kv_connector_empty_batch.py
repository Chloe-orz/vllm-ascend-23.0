# SPDX-License-Identifier: Apache-2.0

import copy
from collections import deque
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from vllm.v1.core.sched.output import SchedulerOutput
from vllm.v1.outputs import EMPTY_MODEL_RUNNER_OUTPUT, KVConnectorOutput

from vllm_ascend.patch.platform.patch_engine_core import (
    _patched_step,
    _patched_step_with_batch_queue,
)

pytestmark = pytest.mark.cpu_test


def _completed_future(value):
    future = Future()
    future.set_result(value)
    return future


def _make_engine(*, kv_transfer_config):
    scheduler_output = SchedulerOutput.make_empty()
    model_output = copy.copy(EMPTY_MODEL_RUNNER_OUTPUT)
    model_output.kv_connector_output = KVConnectorOutput(finished_recving={"decode-request"})

    engine = MagicMock()
    engine.vllm_config = SimpleNamespace(kv_transfer_config=kv_transfer_config)
    engine.scheduler.has_requests.return_value = True
    engine.scheduler.schedule.return_value = scheduler_output
    engine.scheduler.update_from_output.return_value = {}
    engine.model_executor.execute_model.return_value = _completed_future(model_output)
    engine._finish_empty_batch.return_value = ({}, False)
    return engine, scheduler_output, model_output


def test_empty_batch_polls_kv_connector_worker():
    engine, scheduler_output, model_output = _make_engine(kv_transfer_config=object())

    _patched_step(engine)

    engine.model_executor.execute_model.assert_called_once_with(scheduler_output, non_block=True)
    engine.scheduler.update_from_output.assert_called_once_with(scheduler_output, model_output)
    engine._finish_empty_batch.assert_not_called()


def test_empty_batch_without_kv_connector_keeps_fast_path():
    engine, _, _ = _make_engine(kv_transfer_config=None)

    result = _patched_step(engine)

    assert result == ({}, False)
    engine._finish_empty_batch.assert_called_once()
    engine.model_executor.execute_model.assert_not_called()


def test_async_empty_batch_polls_kv_connector_worker():
    engine, scheduler_output, model_output = _make_engine(kv_transfer_config=object())
    engine.batch_queue = deque()
    engine.batch_queue_size = 1
    engine.scheduler._uses_async_scheduled_mtp_placeholders.return_value = False
    engine._has_unresolved_edge_cloud_draft_parent.return_value = False
    engine.is_ec_consumer = False
    engine.is_pooling_model = False
    engine._pop_deferred_empty_batch.return_value = None

    _patched_step_with_batch_queue(engine)

    engine.model_executor.execute_model.assert_called_once_with(scheduler_output, non_block=True)
    engine.scheduler.update_from_output.assert_called_once_with(scheduler_output, model_output)
    engine._finish_empty_batch.assert_not_called()


def test_async_empty_batch_without_kv_connector_keeps_fast_path():
    engine, _, _ = _make_engine(kv_transfer_config=None)
    engine.batch_queue = deque()
    engine.batch_queue_size = 1
    engine.scheduler._uses_async_scheduled_mtp_placeholders.return_value = False
    engine._has_unresolved_edge_cloud_draft_parent.return_value = False

    result = _patched_step_with_batch_queue(engine)

    assert result == ({}, False)
    engine._finish_empty_batch.assert_called_once()
    engine.model_executor.execute_model.assert_not_called()
