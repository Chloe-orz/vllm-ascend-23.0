# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

import queue

from vllm_ascend.edge_cloud.cloud_control import CloudControlProcessor
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
