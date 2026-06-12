# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import pytest

from vllm_ascend.scheduler_conflicts import validate_pd_separation_scheduler_conflicts


def _vllm_config(enable_pd_separation=True):
    return SimpleNamespace(
        scheduler_config=SimpleNamespace(enable_pd_separation=enable_pd_separation),
    )


def _ascend_config(
    *,
    recompute_scheduler_enable=False,
    slo_limits_for_dynamic_batch=-1,
    profiling_chunk_enabled=False,
):
    return SimpleNamespace(
        recompute_scheduler_enable=recompute_scheduler_enable,
        SLO_limits_for_dynamic_batch=slo_limits_for_dynamic_batch,
        profiling_chunk_config=SimpleNamespace(enabled=profiling_chunk_enabled),
    )


@pytest.mark.parametrize(
    ("ascend_config", "expected"),
    [
        pytest.param(
            _ascend_config(recompute_scheduler_enable=True),
            "recompute_scheduler_enable",
            id="recompute-scheduler",
        ),
        pytest.param(
            _ascend_config(slo_limits_for_dynamic_batch=100),
            "SLO_limits_for_dynamic_batch",
            id="dynamic-batch",
        ),
        pytest.param(
            _ascend_config(profiling_chunk_enabled=True),
            "profiling_chunk_config",
            id="profiling-chunk",
        ),
    ],
)
def test_pd_separation_rejects_ascend_scheduler_overrides(ascend_config, expected):
    with pytest.raises(ValueError, match=expected):
        validate_pd_separation_scheduler_conflicts(_vllm_config(), ascend_config)


def test_pd_separation_allows_default_ascend_scheduler_config():
    validate_pd_separation_scheduler_conflicts(_vllm_config(), _ascend_config())


def test_scheduler_conflict_check_is_noop_when_pd_separation_disabled():
    validate_pd_separation_scheduler_conflicts(
        _vllm_config(enable_pd_separation=False),
        _ascend_config(
            recompute_scheduler_enable=True,
            slo_limits_for_dynamic_batch=100,
            profiling_chunk_enabled=True,
        ),
    )
