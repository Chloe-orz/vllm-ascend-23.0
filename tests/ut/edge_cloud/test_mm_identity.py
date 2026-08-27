# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

import base64
from types import SimpleNamespace

import pytest

from vllm_ascend.edge_cloud.mm_identity import (
    MM_ABI_VERSION,
    compute_processor_fingerprint,
    mm_abi_header_value,
)


class _FakeMultiModalConfig(SimpleNamespace):
    def compute_hash(self):
        return (
            self.graph_hash,
            getattr(self, "mm_encoder_fp8_scale_path", None),
        )


class _FakeModelConfig(SimpleNamespace):
    def compute_hash(self):
        return (
            self.graph_hash,
            self.model,
            self.model_weights,
            self.tokenizer,
            self.hf_config._name_or_path,
            self.hf_text_config._name_or_path,
        )


def _model_config(
    model="Qwen/Qwen3.5-9B",
    model_type="qwen3_5",
    mm_processor_kwargs=None,
    revision="model-revision-a",
    image_processor_config=None,
    model_config_hash="model-graph-a",
    multimodal_config_hash="mm-encoder-a",
):
    mm_config = _FakeMultiModalConfig(
        mm_processor_kwargs=mm_processor_kwargs,
        media_io_kwargs={},
        limit_per_prompt={"image": {"count": 2}},
        interleave_mm_strings=False,
        video_pruning_rate=None,
        graph_hash=multimodal_config_hash,
        mm_encoder_fp8_scale_path=None,
    )
    return _FakeModelConfig(
        model=model,
        model_weights=model,
        revision=revision,
        code_revision="code-revision-a",
        tokenizer=model,
        tokenizer_revision="tokenizer-revision-a",
        hf_config=SimpleNamespace(
            _commit_hash="resolved-commit-a",
            _name_or_path=model,
        ),
        hf_text_config=SimpleNamespace(
            model_type=model_type,
            _name_or_path=model,
        ),
        hf_image_processor_config=image_processor_config or {},
        _architecture="Qwen3_5ForConditionalGeneration",
        multimodal_config=mm_config,
        graph_hash=model_config_hash,
    )


def test_fingerprint_is_deterministic_and_32_bytes():
    first = compute_processor_fingerprint(_model_config())
    second = compute_processor_fingerprint(_model_config())

    assert first == second
    assert len(first) == 32


def test_fingerprint_changes_with_mm_processor_kwargs():
    base = compute_processor_fingerprint(_model_config(mm_processor_kwargs={"min_pixels": 1024}))
    other = compute_processor_fingerprint(_model_config(mm_processor_kwargs={"min_pixels": 2048}))

    assert base != other


def test_fingerprint_changes_with_model_type():
    base = compute_processor_fingerprint(_model_config())

    assert base != compute_processor_fingerprint(_model_config(model_type="qwen2_vl"))


def test_fingerprint_ignores_local_model_and_tokenizer_mount_paths():
    edge = _model_config(model="/home/extra/Qwen3.5-9B")
    cloud = _model_config(model="/weight/Qwen3.5-9B")
    cloud.model_weights = "/weight/Qwen3.5-9B"
    cloud.tokenizer = "/weight/Qwen3.5-9B"

    assert compute_processor_fingerprint(edge) == compute_processor_fingerprint(cloud)


def test_fingerprint_changes_with_model_and_processor_revisions():
    base = compute_processor_fingerprint(_model_config())

    assert base != compute_processor_fingerprint(_model_config(revision="model-revision-b"))
    assert base != compute_processor_fingerprint(_model_config(image_processor_config={"size": 1024}))


def test_fingerprint_changes_with_model_and_mm_encoder_graph_config():
    base = compute_processor_fingerprint(_model_config())

    assert base != compute_processor_fingerprint(_model_config(model_config_hash="model-graph-b"))
    assert base != compute_processor_fingerprint(_model_config(multimodal_config_hash="mm-encoder-b"))


def test_fingerprint_works_without_multimodal_config():
    config = SimpleNamespace(
        model="Qwen/Qwen3-8B",
        hf_text_config=SimpleNamespace(model_type="qwen3"),
        multimodal_config=None,
    )

    assert len(compute_processor_fingerprint(config)) == 32


def test_mm_abi_header_value_roundtrip():
    fingerprint = compute_processor_fingerprint(_model_config())
    value = mm_abi_header_value(fingerprint)

    version, separator, encoded = value.partition(":")
    assert separator == ":"
    assert version == MM_ABI_VERSION
    raw = encoded.encode("ascii")
    assert base64.b64decode(raw + b"=" * (-len(raw) % 4), altchars=b"-_") == fingerprint


def test_mm_abi_header_value_rejects_wrong_length():
    with pytest.raises(ValueError, match="32 bytes"):
        mm_abi_header_value(b"too-short")
