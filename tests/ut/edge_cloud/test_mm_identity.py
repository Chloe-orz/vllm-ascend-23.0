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


def _model_config(
    model="Qwen/Qwen3.5-9B",
    model_type="qwen3_5",
    mm_processor_kwargs=None,
):
    mm_config = SimpleNamespace(
        mm_processor_kwargs=mm_processor_kwargs,
        media_io_kwargs={},
        limit_per_prompt={"image": {"count": 2}},
        interleave_mm_strings=False,
        video_pruning_rate=None,
    )
    return SimpleNamespace(
        model=model,
        hf_text_config=SimpleNamespace(model_type=model_type),
        multimodal_config=mm_config,
    )


def test_fingerprint_is_deterministic_and_32_bytes():
    first = compute_processor_fingerprint(_model_config())
    second = compute_processor_fingerprint(_model_config())

    assert first == second
    assert len(first) == 32


def test_fingerprint_changes_with_mm_processor_kwargs():
    base = compute_processor_fingerprint(
        _model_config(mm_processor_kwargs={"min_pixels": 1024})
    )
    other = compute_processor_fingerprint(
        _model_config(mm_processor_kwargs={"min_pixels": 2048})
    )

    assert base != other


def test_fingerprint_changes_with_model_and_model_type():
    base = compute_processor_fingerprint(_model_config())

    assert base != compute_processor_fingerprint(_model_config(model="Qwen/Qwen3.5-4B"))
    assert base != compute_processor_fingerprint(_model_config(model_type="qwen2_vl"))


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
