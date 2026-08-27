# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

"""Processor fingerprint for the edge-cloud multimodal hash ABI.

The fingerprint identifies everything that determines how a piece of media
is turned into placeholder tokens and content digests: the model, its
multimodal processor configuration and the media digest algorithm. Every
edge process of one deployment (API process and EngineCore processes) must
compute the same fingerprint; a configuration change must change it.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from vllm import envs

MM_ABI_VERSION = "mm1"

_FINGERPRINT_SIZE = hashlib.sha256().digest_size

# MultiModalConfig fields that influence media preprocessing, placeholder
# layout or content digests, and therefore the media-aware hash identity.
_MM_CONFIG_FIELDS = (
    "mm_processor_kwargs",
    "media_io_kwargs",
    "limit_per_prompt",
    "interleave_mm_strings",
    "video_pruning_rate",
)


def compute_processor_fingerprint(model_config: Any) -> bytes:
    """Return a 32-byte digest identifying the multimodal processor config."""
    mm_config = getattr(model_config, "multimodal_config", None)
    hf_text_config = getattr(model_config, "hf_text_config", None)
    payload: dict[str, Any] = {
        "model": getattr(model_config, "model", None),
        "model_type": getattr(hf_text_config, "model_type", None),
        "mm_hasher_algorithm": envs.VLLM_MM_HASHER_ALGORITHM,
    }
    for field in _MM_CONFIG_FIELDS:
        value = getattr(mm_config, field, None)
        if value is None:
            # mm_processor_kwargs and media_io_kwargs reach ModelConfig as
            # InitVars; fall back to the model-level attribute so a missing
            # MultiModalConfig still fingerprints consistently.
            value = getattr(model_config, field, None)
        payload[field] = value
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=repr,
    )
    return hashlib.sha256(canonical.encode("utf-8")).digest()


def mm_abi_header_value(fingerprint: bytes) -> str:
    """Render a fingerprint as the ``X-Edge-Cloud-MM-ABI`` header value."""
    if len(fingerprint) != _FINGERPRINT_SIZE:
        raise ValueError(f"fingerprint must contain {_FINGERPRINT_SIZE} bytes")
    encoded = base64.urlsafe_b64encode(fingerprint).rstrip(b"=").decode("ascii")
    return f"{MM_ABI_VERSION}:{encoded}"
