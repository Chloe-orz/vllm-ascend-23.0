# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

import base64
import hashlib
import queue
import threading

import pytest
from fastapi.testclient import TestClient

from vllm_ascend.edge_cloud.cloud_control import (
    CloudControlBridge,
    CloudControlProcessor,
    create_cloud_control_app,
)
from vllm_ascend.edge_cloud.mm_identity import mm_abi_header_value
from vllm_ascend.edge_cloud.prefix_protocol import (
    HEADER_MM_ABI,
    HEADER_PROTOCOL,
    PROTOCOL_VERSION,
    PROTOCOL_VERSION_MM,
    PrefixHasher,
    ProbeResult,
    UsageInfo,
)

TENANT_KEY = b"tenant-a-secret-key-material"
PROCESSOR_FINGERPRINT = hashlib.sha256(b"processor-config").digest()
MM_ABI = mm_abi_header_value(PROCESSOR_FINGERPRINT)


class _KVManager:
    def probe(self, manifest):
        return ProbeResult(
            request_id=manifest.request_id,
            instance_id="cloud-a",
            block_size=manifest.block_size,
            hit_blocks=0,
            hit_tokens=0,
        )


def test_processor_routes_probe_and_usage_events():
    commands = queue.Queue()
    events = queue.Queue()
    processor = CloudControlProcessor(commands, events)
    manifest = PrefixHasher(TENANT_KEY, 4).build_manifest("req-1", [1, 2, 3, 4])
    commands.put({"type": "probe", "manifest": manifest})

    processor.poll(_KVManager())
    probe_event = events.get_nowait()

    assert probe_event["ok"] is True
    assert probe_event["result"].request_id == "req-1"

    processor.publish_usage("req-1", UsageInfo(4, 2, 0))
    usage_event = events.get_nowait()
    assert usage_event["usage"].to_openai_dict()["total_tokens"] == 6


def test_http_probe_wraps_namespace_and_strips_prefix_on_response():
    """Edge self-reports edge_id; cloud wraps internally and strips it in
    every response visible to the edge."""
    commands: queue.Queue = queue.Queue()
    events: queue.Queue = queue.Queue()
    bridge = CloudControlBridge(commands, events)
    app = create_cloud_control_app(bridge)

    hasher = PrefixHasher(b"tenant-a-secret-key-material", 4)
    manifest = hasher.build_manifest("req-1", [1, 2, 3, 4])
    body = {
        "model": "edge-cloud-internal",
        "messages": manifest.to_messages(),
        "edge_cloud_prompt_tokens": 4,
    }
    seen_wrapped: list[str] = []

    def responder() -> None:
        command = commands.get(timeout=10)
        wrapped = command["manifest"].request_id
        seen_wrapped.append(wrapped)
        events.put({
            "type": "probe",
            "request_id": wrapped,
            "ok": True,
            "result": ProbeResult(
                request_id=wrapped,
                instance_id="cloud-a",
                block_size=4,
                hit_blocks=0,
                hit_tokens=0,
            ),
        })
        events.put({
            "type": "usage",
            "request_id": wrapped,
            "usage": UsageInfo(4, 2, 0),
        })

    thread = threading.Thread(target=responder, daemon=True)
    thread.start()
    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/v1/chat/completions",
            headers={**manifest.to_headers(), "X-Edge-Cloud-Edge-Id": "1"},
            json=body,
        ) as response:
            assert response.status_code == 200
            # The edge gets its own raw request id back.
            assert response.headers["X-Edge-Cloud-Request-ID"] == "req-1"
            content = "".join(response.iter_text())
    thread.join(timeout=10)

    # Internally the probe was keyed by the wrapped, edge-namespaced id.
    assert seen_wrapped == ["e1-req-1"]
    assert '"total_tokens":6' in content
    assert '"id":"req-1"' in content


@pytest.fixture
def control_client():
    commands = queue.Queue()
    events = queue.Queue()
    bridge = CloudControlBridge(commands, events)
    app = create_cloud_control_app(bridge, processor_fingerprint=PROCESSOR_FINGERPRINT)
    with TestClient(app) as client:
        yield client, commands, events


def _control_payload(protocol=PROTOCOL_VERSION, mm_abi=None):
    manifest = PrefixHasher(TENANT_KEY, 4).build_manifest("req-1", [1, 2, 3, 4])
    headers = manifest.to_headers()
    headers[HEADER_PROTOCOL] = protocol
    if mm_abi is not None:
        headers[HEADER_MM_ABI] = mm_abi
    body = {
        "messages": manifest.to_messages(),
        "stream": True,
        "stream_options": {"include_usage": True},
        "edge_cloud_prompt_tokens": manifest.prompt_tokens,
    }
    return headers, body


def _start_responder(commands, events):
    def respond():
        command = commands.get(timeout=5)
        manifest = command["manifest"]
        result = ProbeResult(
            request_id=manifest.request_id,
            instance_id="cloud-a",
            block_size=manifest.block_size,
            hit_blocks=0,
            hit_tokens=0,
        )
        events.put(
            {
                "type": "probe",
                "request_id": manifest.request_id,
                "ok": True,
                "result": result,
            }
        )
        events.put(
            {
                "type": "usage",
                "request_id": manifest.request_id,
                "usage": UsageInfo(4, 2, 0),
            }
        )

    thread = threading.Thread(target=respond, daemon=True)
    thread.start()
    return thread


def test_v1_request_still_accepted(control_client):
    client, commands, events = control_client
    headers, body = _control_payload()
    _start_responder(commands, events)

    response = client.post("/v1/chat/completions", headers=headers, json=body)

    assert response.status_code == 200
    assert response.headers[HEADER_PROTOCOL] == PROTOCOL_VERSION
    assert HEADER_MM_ABI not in response.headers
    assert "data: [DONE]" in response.text


def test_v1_request_with_mm_abi_header_is_rejected(control_client):
    client, _, _ = control_client
    headers, body = _control_payload(mm_abi=MM_ABI)

    response = client.post("/v1/chat/completions", headers=headers, json=body)

    assert response.status_code == 400


def test_v2_request_without_mm_abi_header_is_rejected(control_client):
    client, _, _ = control_client
    headers, body = _control_payload(protocol=PROTOCOL_VERSION_MM)

    response = client.post("/v1/chat/completions", headers=headers, json=body)

    assert response.status_code == 400


@pytest.mark.parametrize(
    "mm_abi",
    [
        "mm2:" + MM_ABI.partition(":")[2],
        "mm1",
        "mm1:",
        "mm1:not-valid-base64!!!",
        "mm1:" + base64.urlsafe_b64encode(b"too-short").rstrip(b"=").decode("ascii"),
    ],
)
def test_v2_request_with_malformed_mm_abi_header_is_rejected(control_client, mm_abi):
    client, _, _ = control_client
    headers, body = _control_payload(protocol=PROTOCOL_VERSION_MM, mm_abi=mm_abi)

    response = client.post("/v1/chat/completions", headers=headers, json=body)

    assert response.status_code == 400


def test_v2_request_accepted_and_echoes_mm_abi(control_client):
    client, commands, events = control_client
    headers, body = _control_payload(protocol=PROTOCOL_VERSION_MM, mm_abi=MM_ABI)
    _start_responder(commands, events)

    response = client.post("/v1/chat/completions", headers=headers, json=body)

    assert response.status_code == 200
    assert response.headers[HEADER_PROTOCOL] == PROTOCOL_VERSION_MM
    assert response.headers[HEADER_MM_ABI] == MM_ABI
    assert "data: [DONE]" in response.text


def test_v2_request_with_mismatched_fingerprint_is_rejected(control_client):
    client, commands, _ = control_client
    other_abi = mm_abi_header_value(hashlib.sha256(b"other-processor-config").digest())
    headers, body = _control_payload(protocol=PROTOCOL_VERSION_MM, mm_abi=other_abi)

    response = client.post("/v1/chat/completions", headers=headers, json=body)

    assert response.status_code == 400
    # The mismatched edge never probes (and pins) cloud KV blocks.
    assert commands.empty()


def test_v2_request_is_rejected_when_cloud_has_no_local_fingerprint():
    commands = queue.Queue()
    events = queue.Queue()
    bridge = CloudControlBridge(commands, events)
    app = create_cloud_control_app(bridge)
    headers, body = _control_payload(protocol=PROTOCOL_VERSION_MM, mm_abi=MM_ABI)

    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", headers=headers, json=body)

    assert response.status_code == 400
    assert commands.empty()


def test_unknown_protocol_version_is_rejected(control_client):
    client, _, _ = control_client
    headers, body = _control_payload(protocol="edge-cloud-prefix-v9")

    response = client.post("/v1/chat/completions", headers=headers, json=body)

    assert response.status_code == 400

