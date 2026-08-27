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
        consumer_id="enterprise-a",
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
    assert headers["X-Mse-Consumer"] == "enterprise-a"


def test_build_control_request_accepts_structured_text_content(client):
    _, body = client.build_control_request(
        "req-1",
        [1, 2, 3, 4],
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "private prompt"},
                        {"type": "thinking", "thinking": "private reasoning"},
                    ],
                }
            ]
        },
    )

    assert "private" not in str(body)


@pytest.mark.parametrize(
    "content_part",
    [
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,AA=="},
        },
        {"type": "video_url", "video_url": {"url": "https://example/video.mp4"}},
        {"type": "audio_url", "audio_url": {"url": "https://example/audio.wav"}},
        {"type": "input_audio", "input_audio": {"data": "AA==", "format": "wav"}},
        {"type": "image_embeds", "image_embeds": "AA=="},
        {"type": "audio_embeds", "audio_embeds": "AA=="},
        {"type": "prompt_embeds", "data": "AA=="},
    ],
)
def test_phase_one_rejects_media_and_prompt_embeds(client, content_part):
    request = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe this"},
                    content_part,
                ],
            }
        ]
    }

    with pytest.raises(ValueError, match="text-only requests"):
        client.build_control_request("req-1", [1], request)


@pytest.mark.parametrize(
    ("request_field", "value", "message"),
    [
        ("n", 2, "requires n=1"),
        ("use_beam_search", True, "beam search"),
        ("prompt_logprobs", 1, "prompt logprobs"),
    ],
)
def test_phase_one_rejects_unsupported_request_features(client, request_field, value, message):
    request = {"messages": [], request_field: value}

    with pytest.raises(ValueError, match=message):
        client.build_control_request("req-1", [1], request)
