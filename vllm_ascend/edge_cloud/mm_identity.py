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
import copy
import hashlib
import json
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from vllm import envs

MM_ABI_VERSION = "mm1"

_FINGERPRINT_SIZE = hashlib.sha256().digest_size
_PROCESSOR_SOFTWARE_PACKAGES = (
    "vllm",
    "vllm-ascend",
    "transformers",
    "pillow",
)

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
    """Return a 32-byte digest identifying the multimodal deployment ABI.

    This fingerprints the resolved model/processor configuration visible at
    startup plus the principal preprocessing package versions. It detects
    ordinary Edge/Cloud deployment drift; it is not a proof that two media
    inputs are execution-equivalent (the accepted upstream ``mm_hash`` risk).
    """
    mm_config = getattr(model_config, "multimodal_config", None)
    hf_config = getattr(model_config, "hf_config", None)
    hf_text_config = getattr(model_config, "hf_text_config", None)
    payload: dict[str, Any] = {
        # Do not fingerprint model/tokenizer location strings: the same model
        # artifact is routinely mounted at different local paths on Edge and
        # Cloud. Resolved revisions and config hashes below capture stable
        # deployment identity without turning mount layout into an ABI field.
        "revision": getattr(model_config, "revision", None),
        "code_revision": getattr(model_config, "code_revision", None),
        "tokenizer_revision": getattr(model_config, "tokenizer_revision", None),
        "hf_config_commit": getattr(hf_config, "_commit_hash", None),
        "model_type": getattr(hf_text_config, "model_type", None),
        "architecture": getattr(model_config, "_architecture", None),
        # vLLM's config hashes cover computation-graph choices that are easy
        # to miss when enumerating fields here (dtype/quantization and the MM
        # encoder attention backend/TP/FP8 settings in particular).
        "model_config_hash": _config_hash(
            model_config,
            neutralized_fields={
                "model": "<model-artifact>",
                "model_weights": "<model-artifact>",
                "tokenizer": "<tokenizer-artifact>",
            },
            scrub_hf_locations=True,
        ),
        "multimodal_config_hash": _config_hash(
            mm_config,
            neutralized_fields={
                "mm_encoder_fp8_scale_path": _file_content_identity(
                    getattr(mm_config, "mm_encoder_fp8_scale_path", None)
                )
            },
        ),
        "hf_image_processor_config": getattr(model_config, "hf_image_processor_config", None),
        "mm_hasher_algorithm": envs.VLLM_MM_HASHER_ALGORITHM,
        "software_versions": {package: _package_version(package) for package in _PROCESSOR_SOFTWARE_PACKAGES},
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


def _package_version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def _config_hash(
    config: Any,
    *,
    neutralized_fields: dict[str, Any] | None = None,
    scrub_hf_locations: bool = False,
) -> str | None:
    if config is None:
        return None
    stable_config = copy.copy(config)
    for field, value in (neutralized_fields or {}).items():
        if hasattr(stable_config, field):
            setattr(stable_config, field, value)
    if scrub_hf_locations:
        for field in ("hf_config", "hf_text_config"):
            hf_config = getattr(stable_config, field, None)
            if hf_config is None:
                continue
            stable_hf_config = copy.deepcopy(hf_config)
            _scrub_name_or_path(stable_hf_config, set())
            setattr(stable_config, field, stable_hf_config)
    compute_hash = getattr(stable_config, "compute_hash", None)
    if not callable(compute_hash):
        return None
    return str(compute_hash())


def _scrub_name_or_path(value: Any, seen: set[int]) -> None:
    """Remove node-local Hugging Face resource paths from a copied config."""
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return
    identity = id(value)
    if identity in seen:
        return
    seen.add(identity)
    if isinstance(value, dict):
        if "_name_or_path" in value:
            value["_name_or_path"] = "<model-artifact>"
        for nested in value.values():
            _scrub_name_or_path(nested, seen)
        return
    if isinstance(value, (list, tuple, set)):
        for nested in value:
            _scrub_name_or_path(nested, seen)
        return
    attributes = getattr(value, "__dict__", None)
    if not isinstance(attributes, dict):
        return
    if "_name_or_path" in attributes:
        attributes["_name_or_path"] = "<model-artifact>"
    for nested in attributes.values():
        _scrub_name_or_path(nested, seen)


def _file_content_identity(path: Any) -> str | None:
    """Identify a graph input by bytes instead of its node-local path."""
    if path is None:
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def mm_abi_header_value(fingerprint: bytes) -> str:
    """Render a fingerprint as the ``X-Edge-Cloud-MM-ABI`` header value."""
    if len(fingerprint) != _FINGERPRINT_SIZE:
        raise ValueError(f"fingerprint must contain {_FINGERPRINT_SIZE} bytes")
    encoded = base64.urlsafe_b64encode(fingerprint).rstrip(b"=").decode("ascii")
    return f"{MM_ABI_VERSION}:{encoded}"
