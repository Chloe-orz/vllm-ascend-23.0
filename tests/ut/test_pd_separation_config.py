from unittest.mock import patch

import pytest

from vllm_ascend.ascend_config import EdgeCloudConfig, PDSeparationConfig


def test_legacy_edge_cloud_pd_mix_does_not_require_kv_engine_id() -> None:
    config = EdgeCloudConfig(
        {
            "enabled": True,
            "role": "edge",
            "mode": "head_tail",
            "edge_head_tail_layers": 1,
            "pd_separation": {"enabled": True},
        }
    )

    assert config.enabled
    assert config.pd_separation.enabled
    assert config.kv_engine_id is None


def test_pd_channel_config_uses_explicit_values() -> None:
    with patch.dict(
        "os.environ",
        {
            "VLLM_PP_PRE_OUT_ZMQ_PORT": "6000",
            "VLLM_PP_POST_OUT_ZMQ_PORT": "6001",
            "VLLM_PP_PASSIVE_DISPATCH_POLICY": "decode_first",
        },
    ):
        config = PDSeparationConfig(
            {
                "enabled": True,
                "pre_out_port": 7000,
                "post_out_port": 7001,
                "dispatch_policy": "expect_alternation",
            }
        )

    assert config.enabled
    assert config.pre_out_port == 7000
    assert config.post_out_port == 7001
    assert config.dispatch_policy == "expect_alternation"


def test_pd_channel_config_retains_environment_fallback() -> None:
    with patch.dict(
        "os.environ",
        {
            "VLLM_PP_PRE_OUT_ZMQ_PORT": "6100",
            "VLLM_PP_POST_OUT_ZMQ_PORT": "6101",
            "VLLM_PP_PASSIVE_DISPATCH_POLICY": "prefill_first",
        },
    ):
        config = PDSeparationConfig({"enabled": True})

    assert config.pre_out_port == 6100
    assert config.post_out_port == 6101
    assert config.dispatch_policy == "prefill_first"


def test_disabled_pd_config_ignores_channel_environment() -> None:
    with patch.dict(
        "os.environ",
        {
            "VLLM_PP_PRE_OUT_ZMQ_PORT": "not-a-port",
            "VLLM_PP_POST_OUT_ZMQ_PORT": "also-not-a-port",
            "VLLM_PP_PASSIVE_DISPATCH_POLICY": "unknown",
        },
    ):
        config = PDSeparationConfig()

    assert not config.enabled


@pytest.mark.parametrize(
    "user_config, message",
    [
        (
            {"enabled": True, "pre_out_port": 0},
            "pre_out_port must be in",
        ),
        (
            {
                "enabled": True,
                "pre_out_port": 6000,
                "post_out_port": 6000,
            },
            "must be different",
        ),
        (
            {"enabled": True, "dispatch_policy": "unknown"},
            "dispatch_policy must be one of",
        ),
        (
            {"enabled": True, "max_chunk_prefill_ahead": -1},
            "must be non-negative",
        ),
    ],
)
def test_pd_channel_config_rejects_invalid_values(
    user_config: dict, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        PDSeparationConfig(user_config)
