# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

import ast
import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).parents[3] / "vllm_ascend" / "edge_cloud" / "observability.py"
_SPEC = importlib.util.spec_from_file_location("edge_cloud_observability", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
format_event = _MODULE.format_event
log_event = _MODULE.log_event

_COORDINATION_SOURCES = (
    "vllm_ascend/edge_cloud/edge_client.py",
    "vllm_ascend/edge_cloud/cloud_control.py",
    "vllm_ascend/edge_cloud/cloud_kv.py",
    "vllm_ascend/patch/platform/patch_async_llm_edge_cloud.py",
    "vllm_ascend/patch/platform/patch_engine_core.py",
    "vllm_ascend/v1/engine/passive_core.py",
    "vllm_ascend/core/pd_separated_scheduler.py",
)


def test_format_event_has_marker_stable_fields_and_escaped_strings():
    message = format_event(
        "edge_probe_response",
        request_id="req\n1",
        hit_tokens=32,
        reserved=True,
        optional=None,
    )

    assert message == ("[EDGE_CLOUD_PREFIX] event=edge_probe_response request_id='req\\n1' hit_tokens=32 reserved=true")


@pytest.mark.parametrize(
    "field",
    ["prompt", "prompt_token_ids", "token_ids", "hashes", "tenant_key", "body"],
)
def test_format_event_rejects_sensitive_fields(field):
    with pytest.raises(ValueError, match="sensitive"):
        format_event("unsafe_event", **{field: "secret"})


def test_log_event_uses_requested_level():
    calls = []

    class Recorder:
        def info(self, pattern, message):
            calls.append((pattern, message))

    log_event(Recorder(), "info", "cloud_probe_reserved", request_id="req-1")

    assert calls == [
        (
            "%s",
            "[EDGE_CLOUD_PREFIX] event=cloud_probe_reserved request_id='req-1'",
        )
    ]


def test_log_event_skips_formatting_when_level_is_disabled():
    class NotFormattable:
        def __str__(self):
            raise AssertionError("disabled log field must not be formatted")

    class Recorder:
        def isEnabledFor(self, _level):
            return False

        def debug(self, _pattern, _message):
            raise AssertionError("disabled logger must not be called")

    log_event(Recorder(), "debug", "hot_path_event", payload=NotFormattable())


def test_coordination_lifecycle_and_failure_paths_keep_stable_events():
    expected_events = {
        "edge_negotiate_start",
        "edge_probe_response",
        "cloud_http_probe_reserved",
        "cloud_kv_probe_reserved",
        "edge_scheduler_request_published",
        "cloud_kv_admission_complete",
        "cloud_worker_ack_received",
        "cloud_prefill_ack_published",
        "edge_prefill_ack_received",
        "edge_finish_manifest_created",
        "cloud_kv_request_finished",
        "cloud_sse_usage_ready",
        "edge_usage_received",
        "edge_probe_failed",
        "edge_probe_http_failed",
        "edge_scheduler_publish_failed",
        "cloud_kv_reservation_missing",
        "cloud_scheduler_output_failed",
        "cloud_prefill_ack_source_missing",
        "edge_usage_missing",
    }

    observed_events = set()
    sensitive_fields = set(_MODULE._FORBIDDEN_FIELDS)
    for relative_path in _COORDINATION_SOURCES:
        tree = ast.parse((Path(__file__).parents[3] / relative_path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            event_index = {"format_event": 0, "log_event": 2}.get(node.func.id)
            if event_index is None or len(node.args) <= event_index:
                continue
            logged_fields = {keyword.arg for keyword in node.keywords if keyword.arg is not None}
            assert logged_fields.isdisjoint(sensitive_fields)
            event = node.args[event_index]
            if isinstance(event, ast.Constant) and isinstance(event.value, str):
                observed_events.add(event.value)

    assert expected_events <= observed_events
