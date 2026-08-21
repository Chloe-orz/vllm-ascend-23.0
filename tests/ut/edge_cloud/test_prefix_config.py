# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

from types import SimpleNamespace

import pytest

from vllm_ascend.ascend_config import EdgeCloudConfig


def _vllm_config(
    *,
    model_type="qwen3_5_text",
    multimodal_config=None,
    lora_config=None,
    speculative_config=None,
    enable_prefix_caching=True,
):
    return SimpleNamespace(
        model_config=SimpleNamespace(
            hf_text_config=SimpleNamespace(model_type=model_type),
            multimodal_config=multimodal_config,
        ),
        parallel_config=SimpleNamespace(
            prefill_context_parallel_size=1,
            decode_context_parallel_size=1,
        ),
        lora_config=lora_config,
        speculative_config=speculative_config,
        cache_config=SimpleNamespace(enable_prefix_caching=enable_prefix_caching),
    )


def _config(role="edge", **coordination):
    defaults = {
        "enabled": True,
        "control_url": "http://cloud.example/v1/chat/completions",
        "tenant_key_file": "/run/secrets/tenant-key",
        "instance_id": "cloud-a",
    }
    defaults.update(coordination)
    return {
        "enabled": True,
        "role": role,
        "pd_separation": {"enabled": True},
        "prefix_cache_coordination": defaults,
    }


@pytest.mark.parametrize("model_type", ["qwen3_5", "qwen3_5_text"])
def test_accepts_qwen35_dense_edge_configuration(model_type):
    config = EdgeCloudConfig(_config(), _vllm_config(model_type=model_type))

    assert config.prefix_cache_coordination.enabled
    assert config.prefix_cache_coordination.control_url == ("http://cloud.example/v1/chat/completions")


def test_accepts_qwen35_dense_cloud_configuration_without_tenant_key():
    config = _config(role="cloud")
    del config["prefix_cache_coordination"]["tenant_key_file"]
    del config["prefix_cache_coordination"]["control_url"]

    parsed = EdgeCloudConfig(config, _vllm_config())

    assert parsed.prefix_cache_coordination.instance_id == "cloud-a"


@pytest.mark.parametrize("language_model_only", [False, True])
def test_accepts_qwen35_conditional_generation_checkpoint(language_model_only):
    config = EdgeCloudConfig(
        _config(),
        _vllm_config(
            model_type="qwen3_5",
            multimodal_config=SimpleNamespace(language_model_only=language_model_only),
        ),
    )

    assert config.prefix_cache_coordination.enabled


@pytest.mark.parametrize(
    ("vllm_overrides", "message"),
    [
        ({"model_type": "qwen3_5_moe_text"}, "Qwen3.5-Dense"),
        ({"lora_config": object()}, "LoRA"),
        ({"speculative_config": object()}, "speculative decoding"),
        ({"enable_prefix_caching": False}, "enable_prefix_caching"),
    ],
)
def test_rejects_unsupported_phase_one_features(vllm_overrides, message):
    with pytest.raises(ValueError, match=message):
        EdgeCloudConfig(_config(), _vllm_config(**vllm_overrides))


def test_coordination_requires_pd_separation():
    config = _config()
    config["pd_separation"]["enabled"] = False

    with pytest.raises(ValueError, match="pd_separation.enabled=True"):
        EdgeCloudConfig(config, _vllm_config())
