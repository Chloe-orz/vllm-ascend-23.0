# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

import queue
import threading

from fastapi.testclient import TestClient

from vllm_ascend.edge_cloud.cloud_control import (
    CloudControlBridge,
    CloudControlProcessor,
    create_cloud_control_app,
)
from vllm_ascend.edge_cloud.prefix_protocol import (
    PrefixHasher,
    ProbeResult,
    UsageInfo,
)


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
    manifest = PrefixHasher(b"tenant-a-secret-key-material", 4).build_manifest(
        "req-1", [1, 2, 3, 4]
    )
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
