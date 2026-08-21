# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

"""Structured, privacy-safe logging for edge-cloud prefix coordination."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

LOG_MARKER = "[EDGE_CLOUD_PREFIX]"

_FORBIDDEN_FIELDS = frozenset(
    {
        "body",
        "hash",
        "hashes",
        "hash_values",
        "prompt",
        "prompt_text",
        "prompt_token_ids",
        "request_body",
        "tenant_key",
        "token_ids",
    }
)
_LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def format_event(event: str, /, **fields: object) -> str:
    """Format one searchable event without accepting sensitive field names."""
    _validate_name("event", event)
    parts = [LOG_MARKER, f"event={event}"]
    for name, value in fields.items():
        _validate_name("field", name)
        if name in _FORBIDDEN_FIELDS:
            raise ValueError(f"sensitive edge-cloud log field is forbidden: {name}")
        if value is None:
            continue
        parts.append(f"{name}={_format_value(value)}")
    return " ".join(parts)


def log_event(logger: Any, level: str, event: str, /, **fields: object) -> None:
    """Emit one event through a vLLM/Python logger."""
    numeric_level = _LOG_LEVELS.get(level)
    method = getattr(logger, level, None)
    if numeric_level is None or method is None:
        raise ValueError(f"unknown log level {level!r}")
    is_enabled_for = getattr(logger, "isEnabledFor", None)
    if is_enabled_for is not None and not is_enabled_for(numeric_level):
        return
    method("%s", format_event(event, **fields))


def _validate_name(kind: str, value: str) -> None:
    if not value or not value.replace("_", "").isalnum():
        raise ValueError(f"invalid edge-cloud {kind} name {value!r}")


def _format_value(value: object) -> str:
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    return repr(str(value))
