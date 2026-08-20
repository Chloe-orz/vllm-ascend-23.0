# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

from pathlib import Path

import pytest

from vllm_ascend.edge_cloud.edge_client import EdgePrefixClient
from vllm_ascend.edge_cloud.prefix_protocol import BLOCK_HASH_PREFIX, TAIL_HASH_PREFIX


@pytest.fixture
def client(tmp_path: Path):
    key_file = tmp_path / "tenant-key"
    key_file.write_bytes(b"tenant-a-secret-key-material")
    return EdgePrefixClient(
        control_url="http://cloud.example/v1/chat/completions",
        tenant_key_file=str(key_file),
        block_size=4,
        connect_timeout=1.0,
    )


def test_build_control_request_removes_original_prompt(client):
    headers, body = client.build_control_request(
        "req-1",
        [1, 2, 3, 4, 5],
        {
            "model": "Qwen/Qwen3.5-9B",
            "messages": [
                {"role": "system", "content": "private system prompt"},
                {"role": "user", "content": "private user prompt"},
            ],
            "temperature": 0.2,
        },
    )

    serialized = str(body)
    assert "private system prompt" not in serialized
    assert "private user prompt" not in serialized
    assert body["messages"][0]["content"].startswith(BLOCK_HASH_PREFIX)
    assert body["messages"][1]["content"].startswith(TAIL_HASH_PREFIX)
    assert body["temperature"] == 0.2
    assert body["stream"] is True
    assert body["stream_options"] == {"include_usage": True}
    assert headers["X-Edge-Cloud-Request-ID"] == "req-1"


@pytest.mark.parametrize(
    ("request_field", "value", "message"),
    [
        ("n", 2, "requires n=1"),
        ("use_beam_search", True, "beam search"),
        ("prompt_logprobs", 1, "prompt logprobs"),
    ],
)
def test_phase_one_rejects_unsupported_request_features(
    client, request_field, value, message
):
    request = {"messages": [], request_field: value}

    with pytest.raises(ValueError, match=message):
        client.build_control_request("req-1", [1], request)
