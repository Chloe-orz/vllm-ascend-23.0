from unittest.mock import patch

import pytest

from vllm_ascend.ascend_config import PDSeparationConfig


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
        config = PDSeparationConfig()

    assert config.pre_out_port == 6100
    assert config.post_out_port == 6101
    assert config.dispatch_policy == "prefill_first"


@pytest.mark.parametrize(
    "user_config, message",
    [
        (
            {"pre_out_port": 0},
            "pre_out_port must be in",
        ),
        (
            {"pre_out_port": 6000, "post_out_port": 6000},
            "must be different",
        ),
        (
            {"dispatch_policy": "unknown"},
            "dispatch_policy must be one of",
        ),
        (
            {"max_chunk_prefill_ahead": -1},
            "must be non-negative",
        ),
    ],
)
def test_pd_channel_config_rejects_invalid_values(
    user_config: dict, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        PDSeparationConfig(user_config)
