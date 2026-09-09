# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

from types import SimpleNamespace

import pytest

from vllm_ascend.ascend_config import EdgeCloudConfig


def _vllm_config(
    *,
    model_type="qwen3_5_text",
    hf_model_type=None,
    multimodal_config=None,
    lora_config=None,
    speculative_config=None,
    enable_prefix_caching=True,
):
    if hf_model_type is None:
        hf_model_type = model_type
    return SimpleNamespace(
        model_config=SimpleNamespace(
            hf_config=SimpleNamespace(model_type=hf_model_type),
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
    assert config.prefix_cache_coordination.probe_timeout == 30.0


def test_accepts_qwen35_dense_cloud_configuration_without_tenant_key():
    config = _config(role="cloud")
    del config["prefix_cache_coordination"]["tenant_key_file"]
    del config["prefix_cache_coordination"]["control_url"]

    parsed = EdgeCloudConfig(config, _vllm_config())

    assert parsed.prefix_cache_coordination.instance_id == "cloud-a"
    assert parsed.prefix_cache_coordination.enforce_mm_abi_match is False


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_rejects_invalid_probe_timeout(value):
    with pytest.raises(ValueError, match="probe_timeout"):
        EdgeCloudConfig(_config(probe_timeout=value), _vllm_config())


def test_cloud_coordination_can_enforce_mm_abi_match():
    config = _config(role="cloud", enforce_mm_abi_match=True)
    del config["prefix_cache_coordination"]["tenant_key_file"]
    del config["prefix_cache_coordination"]["control_url"]

    parsed = EdgeCloudConfig(config, _vllm_config())

    assert parsed.prefix_cache_coordination.enforce_mm_abi_match is True


@pytest.mark.parametrize("value", [1, "true", None])
def test_cloud_coordination_rejects_non_boolean_mm_abi_match(value):
    config = _config(role="cloud", enforce_mm_abi_match=value)
    del config["prefix_cache_coordination"]["tenant_key_file"]
    del config["prefix_cache_coordination"]["control_url"]

    with pytest.raises(ValueError, match="enforce_mm_abi_match must be a bool"):
        EdgeCloudConfig(config, _vllm_config())


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


def test_accepts_qwen35_image_capable_vl_variant():
    # The image-capable Dense VL deployment reports model_type "qwen3_5" at
    # the top level (Qwen3_5ForConditionalGeneration) while its text backbone
    # stays "qwen3_5_text".
    config = EdgeCloudConfig(
        _config(),
        _vllm_config(hf_model_type="qwen3_5", model_type="qwen3_5_text"),
    )

    assert config.prefix_cache_coordination.enabled


def test_rejects_qwen35_moe_vl_variant():
    with pytest.raises(ValueError, match="Qwen3.5-Dense"):
        EdgeCloudConfig(
            _config(),
            _vllm_config(hf_model_type="qwen3_5_moe", model_type="qwen3_5_moe_text"),
        )


@pytest.mark.parametrize(
    ("vllm_overrides", "message"),
    [
        ({"model_type": "qwen3_5_moe_text"}, "Qwen3.5-Dense"),
        ({"lora_config": object()}, "LoRA"),
        (
            {"speculative_config": SimpleNamespace(method="eagle3")},
            "only MTP speculative decoding",
        ),
        ({"enable_prefix_caching": False}, "enable_prefix_caching"),
    ],
)
def test_rejects_unsupported_phase_one_features(vllm_overrides, message):
    with pytest.raises(ValueError, match=message):
        EdgeCloudConfig(_config(), _vllm_config(**vllm_overrides))


def test_accepts_mtp_with_prefix_cache_coordination():
    parsed = EdgeCloudConfig(
        _config(),
        _vllm_config(
            speculative_config=SimpleNamespace(
                method="mtp",
                num_speculative_tokens=3,
            )
        ),
    )

    assert parsed.prefix_cache_coordination.enabled


def test_coordination_requires_pd_separation():
    config = _config()
    config["pd_separation"]["enabled"] = False

    with pytest.raises(ValueError, match="pd_separation.enabled=True"):
        EdgeCloudConfig(config, _vllm_config())


@pytest.mark.parametrize("algorithm", ["blake3", "sha256"])
def test_edge_coordination_accepts_32_byte_mm_hasher(algorithm, monkeypatch):
    monkeypatch.setenv("VLLM_MM_HASHER_ALGORITHM", algorithm)

    config = EdgeCloudConfig(_config(), _vllm_config())

    assert config.prefix_cache_coordination.enabled


def test_edge_coordination_rejects_oversized_mm_hasher_digest(monkeypatch):
    monkeypatch.setenv("VLLM_MM_HASHER_ALGORITHM", "sha512")

    with pytest.raises(ValueError, match="digest"):
        EdgeCloudConfig(
            _config(),
            _vllm_config(
                hf_model_type="qwen3_5",
                multimodal_config=SimpleNamespace(language_model_only=False),
            ),
        )


@pytest.mark.parametrize(
    "multimodal_config",
    [None, SimpleNamespace(language_model_only=True)],
)
def test_text_only_edge_coordination_does_not_gate_mm_hasher_digest(
    monkeypatch,
    multimodal_config,
):
    monkeypatch.setenv("VLLM_MM_HASHER_ALGORITHM", "sha512")

    parsed = EdgeCloudConfig(
        _config(),
        _vllm_config(multimodal_config=multimodal_config),
    )

    assert parsed.prefix_cache_coordination.enabled


def test_cloud_coordination_does_not_gate_mm_hasher_digest(monkeypatch):
    # Only the edge sends media content digests; the cloud is gated through
    # the MM-ABI fingerprint comparison instead.
    monkeypatch.setenv("VLLM_MM_HASHER_ALGORITHM", "sha512")
    config = _config(role="cloud")
    del config["prefix_cache_coordination"]["tenant_key_file"]
    del config["prefix_cache_coordination"]["control_url"]

    parsed = EdgeCloudConfig(config, _vllm_config())

    assert parsed.prefix_cache_coordination.enabled
