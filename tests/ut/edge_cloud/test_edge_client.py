# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from multidict import CIMultiDict

import vllm_ascend.edge_cloud.edge_client as edge_client_module
from vllm_ascend.edge_cloud.edge_client import EdgePrefixClient
from vllm_ascend.edge_cloud.mm_identity import mm_abi_header_value
from vllm_ascend.edge_cloud.prefix_protocol import (
    BLOCK_HASH_PREFIX,
    HEADER_MM_ABI,
    HEADER_PROTOCOL,
    PROTOCOL_VERSION,
    PROTOCOL_VERSION_MM,
    TAIL_HASH_PREFIX,
    PrefixHasher,
    ProbeResult,
)

TENANT_KEY = b"tenant-a-secret-key-material"
PROCESSOR_FINGERPRINT = hashlib.sha256(b"processor-config").digest()
IMAGE_DIGEST = hashlib.sha256(b"image-a").digest()


@dataclass(frozen=True)
class MediaItem:
    """Duck-typed stand-in for the edge-cloud media identity description."""

    modality: str
    digest: bytes
    offset: int
    length: int


@pytest.fixture
def client(tmp_path: Path):
    key_file = tmp_path / "tenant-key"
    key_file.write_bytes(TENANT_KEY)
    return EdgePrefixClient(
        control_url="http://cloud.example/v1/chat/completions",
        tenant_key_file=str(key_file),
        consumer_id="enterprise-a",
        block_size=4,
        connect_timeout=1.0,
    )


@pytest.fixture
def mm_client(tmp_path: Path):
    key_file = tmp_path / "tenant-key"
    key_file.write_bytes(TENANT_KEY)
    return EdgePrefixClient(
        control_url="http://cloud.example/v1/chat/completions",
        tenant_key_file=str(key_file),
        consumer_id="enterprise-a",
        block_size=4,
        connect_timeout=1.0,
        processor_fingerprint=PROCESSOR_FINGERPRINT,
    )


def _image_request(**extra):
    request = {
        "model": "Qwen/Qwen3.5-9B",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe this"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,PRIVATEIMAGE"},
                    },
                ],
            }
        ],
    }
    request.update(extra)
    return request


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
            "metadata": {"tenant": "private-metadata"},
            "user": "private-user",
        },
    )

    serialized = str(body)
    assert "private system prompt" not in serialized
    assert "private user prompt" not in serialized
    # The shadow body is whitelisted: sampling parameters, metadata and the
    # user field from the original request must not leak across the edge.
    assert set(body) == {
        "model",
        "messages",
        "stream",
        "stream_options",
        "edge_cloud_prompt_tokens",
    }
    assert body["model"] == "Qwen/Qwen3.5-9B"
    assert body["messages"][0]["content"].startswith(BLOCK_HASH_PREFIX)
    assert body["messages"][1]["content"].startswith(TAIL_HASH_PREFIX)
    assert body["stream"] is True
    assert body["stream_options"] == {"include_usage": True}
    assert body["edge_cloud_prompt_tokens"] == 5
    assert headers[HEADER_PROTOCOL] == PROTOCOL_VERSION
    assert HEADER_MM_ABI not in headers
    assert headers["X-Edge-Cloud-Request-ID"] == "req-1"
    assert headers["X-Mse-Consumer"] == "enterprise-a"
    # No registry identity configured: the edge-id header stays absent so
    # the cloud keeps the legacy single-edge (unwrapped) namespace.
    assert "X-Edge-Cloud-Edge-Id" not in headers


def test_build_control_request_self_reports_edge_id(tmp_path: Path):
    key_file = tmp_path / "tenant-key"
    key_file.write_bytes(b"tenant-a-secret-key-material")
    edge_client = EdgePrefixClient(
        control_url="http://cloud.example/v1/chat/completions",
        tenant_key_file=str(key_file),
        consumer_id="enterprise-a",
        block_size=4,
        connect_timeout=1.0,
        edge_id=1,
    )
    headers, _ = edge_client.build_control_request(
        "req-1",
        [1, 2, 3, 4, 5],
        {
            "model": "Qwen/Qwen3.5-9B",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    # The edge only self-reports its identity; the request id itself stays
    # raw and the cloud wraps/unwraps the namespace internally.
    assert headers["X-Edge-Cloud-Edge-Id"] == "1"
    assert headers["X-Edge-Cloud-Request-ID"] == "req-1"


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


def test_image_request_uses_v2_protocol_and_media_manifest(mm_client):
    tokens = [1, 2, 3, 4, 5, 6, 7, 8]
    media_items = [MediaItem("image", IMAGE_DIGEST, 4, 4)]

    headers, body = mm_client.build_control_request("req-mm-1", tokens, _image_request(), media_items=media_items)

    assert headers[HEADER_PROTOCOL] == PROTOCOL_VERSION_MM
    assert headers[HEADER_MM_ABI] == mm_abi_header_value(PROCESSOR_FINGERPRINT)
    # Two full blocks, no tail; the media URL never crosses the edge.
    assert [message["content"][:5] for message in body["messages"]] == [
        BLOCK_HASH_PREFIX,
        BLOCK_HASH_PREFIX,
    ]
    assert "PRIVATEIMAGE" not in str(body)
    assert set(body) == {
        "model",
        "messages",
        "stream",
        "stream_options",
        "edge_cloud_prompt_tokens",
    }
    # The media-free first block keeps the byte-identical v1 digest; the
    # block covering the image diverges from the token-only chain.
    v1_manifest = PrefixHasher(TENANT_KEY, 4).build_manifest("req-mm-1", tokens)
    v1_contents = [message["content"] for message in v1_manifest.to_messages()]
    mm_contents = [message["content"] for message in body["messages"]]
    assert mm_contents[0] == v1_contents[0]
    assert mm_contents[1] != v1_contents[1]


@pytest.mark.parametrize(
    "content_part",
    [
        {"type": "image_url", "image_url": {"url": "https://example/image.png"}},
        {"type": "input_image", "image_url": {"url": "https://example/image.png"}},
        {"type": "image_pil", "image_pil": {"url": "https://example/image.png"}},
    ],
)
def test_image_content_parts_are_accepted(mm_client, content_part):
    request = {
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "describe"}, content_part],
            }
        ]
    }
    media_items = [MediaItem("image", IMAGE_DIGEST, 0, 2)]

    headers, _ = mm_client.build_control_request("req-1", [1, 2], request, media_items=media_items)

    assert headers[HEADER_PROTOCOL] == PROTOCOL_VERSION_MM


@pytest.mark.parametrize(
    "content_part",
    [
        {"type": "video_url", "video_url": {"url": "https://example/video.mp4"}},
        {"type": "audio_url", "audio_url": {"url": "https://example/audio.wav"}},
        {"type": "input_audio", "input_audio": {"data": "AA==", "format": "wav"}},
        {"type": "image_embeds", "image_embeds": "AA=="},
        {"type": "audio_embeds", "audio_embeds": "AA=="},
        {"type": "prompt_embeds", "data": "AA=="},
    ],
)
def test_phase_one_rejects_unsupported_media_and_prompt_embeds(client, content_part):
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

    with pytest.raises(ValueError, match="does not support"):
        client.build_control_request("req-1", [1], request)


def test_phase_one_rejects_message_level_audio(client):
    request = {"messages": [{"role": "user", "content": "hi", "audio": {"id": "a"}}]}

    with pytest.raises(ValueError, match="does not support"):
        client.build_control_request("req-1", [1], request)


def test_image_request_without_media_items_is_rejected(mm_client):
    with pytest.raises(ValueError, match="missing media placeholder"):
        mm_client.build_control_request("req-1", [1, 2], _image_request())


def test_media_items_without_image_request_are_rejected(mm_client):
    media_items = [MediaItem("image", IMAGE_DIGEST, 0, 2)]
    request = {"messages": [{"role": "user", "content": "text only"}]}

    with pytest.raises(ValueError, match="require an image request"):
        mm_client.build_control_request("req-1", [1, 2], request, media_items=media_items)


def test_media_items_without_processor_fingerprint_are_rejected(client):
    media_items = [MediaItem("image", IMAGE_DIGEST, 0, 2)]

    with pytest.raises(ValueError, match="processor_fingerprint is required"):
        client.build_control_request("req-1", [1, 2], _image_request(), media_items=media_items)


def test_multimodal_cache_salt_is_rejected(mm_client):
    media_items = [MediaItem("image", IMAGE_DIGEST, 0, 2)]
    request = _image_request(cache_salt="tenant-salt")

    with pytest.raises(ValueError, match="cache_salt"):
        mm_client.build_control_request("req-1", [1, 2], request, media_items=media_items)


@pytest.mark.parametrize(
    "uuid",
    [
        "0123456789abcdef0123456789abcdef",
        None,
    ],
)
def test_content_part_uuid_follows_upstream_identity_semantics(mm_client, uuid):
    request = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe this"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example/image.png"},
                        "uuid": uuid,
                    },
                ],
            }
        ]
    }
    media_items = [MediaItem("image", IMAGE_DIGEST, 0, 2)]

    _, body = mm_client.build_control_request("req-1", [1, 2], request, media_items=media_items)

    assert "uuid" not in json.dumps(body)


def test_multimodal_media_io_kwargs_follow_upstream_identity_semantics(mm_client):
    media_items = [MediaItem("image", IMAGE_DIGEST, 0, 2)]
    request = _image_request(media_io_kwargs={"rgba_background_color": [255, 255, 255]})

    _, body = mm_client.build_control_request("req-1", [1, 2], request, media_items=media_items)

    assert "media_io_kwargs" not in body


def test_text_only_media_io_kwargs_are_allowed(client):
    # Without media there is nothing to decode, so request-level media IO
    # kwargs cannot change the executed input and must not false-reject.
    request = {
        "model": "Qwen/Qwen3.5-9B",
        "messages": [{"role": "user", "content": "hi"}],
        "media_io_kwargs": {"rgba_background_color": [255, 255, 255]},
    }

    headers, _ = client.build_control_request("req-1", [1, 2], request)

    assert headers[HEADER_PROTOCOL] == PROTOCOL_VERSION


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


class _FakeContent:
    def __init__(self, lines):
        self._lines = iter(lines)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._lines)
        except StopIteration:
            raise StopAsyncIteration from None


class _FakeResponse:
    def __init__(self, headers):
        self.status = 200
        self.headers = CIMultiDict(headers)
        usage = json.dumps({"usage": {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10}}).encode()
        self.content = _FakeContent([b"data: " + usage + b"\n", b"data: [DONE]\n"])
        self.closed = False

    def close(self):
        self.closed = True


class _FakeSession:
    def __init__(self, response):
        self._response = response
        self.closed = False
        self.last_headers = None
        self.last_body = None

    async def post(self, url, headers=None, json=None):
        self.last_headers = headers
        self.last_body = json
        return self._response

    async def close(self):
        self.closed = True


def _probe_headers(request_id, protocol=PROTOCOL_VERSION, mm_abi=None):
    headers = ProbeResult(
        request_id=request_id,
        instance_id="cloud-a",
        block_size=4,
        hit_blocks=0,
        hit_tokens=0,
    ).to_headers()
    headers[HEADER_PROTOCOL] = protocol
    if mm_abi is not None:
        headers[HEADER_MM_ABI] = mm_abi
    return headers


def _install_fake_session(monkeypatch, response):
    session = _FakeSession(response)
    monkeypatch.setattr(edge_client_module.aiohttp, "ClientSession", lambda timeout: session)
    return session


def _run_negotiate(client, *args, **kwargs):
    async def run():
        result = await client.negotiate(*args, **kwargs)
        tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        await asyncio.gather(*tasks)
        return result

    return asyncio.run(run())


def test_v1_negotiate_unchanged(client, monkeypatch):
    response = _FakeResponse(_probe_headers("req-1"))
    session = _install_fake_session(monkeypatch, response)
    request = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}

    result = _run_negotiate(client, "req-1", [1, 2, 3, 4, 5], request)

    assert result.instance_id == "cloud-a"
    assert session.last_headers[HEADER_PROTOCOL] == PROTOCOL_VERSION
    assert HEADER_MM_ABI not in session.last_headers
    assert session.closed is True


def test_v2_negotiate_accepts_matching_mm_abi_echo(mm_client, monkeypatch):
    mm_abi = mm_abi_header_value(PROCESSOR_FINGERPRINT)
    response = _FakeResponse(_probe_headers("req-mm", protocol=PROTOCOL_VERSION_MM, mm_abi=mm_abi))
    session = _install_fake_session(monkeypatch, response)
    media_items = [MediaItem("image", IMAGE_DIGEST, 4, 4)]

    result = _run_negotiate(
        mm_client,
        "req-mm",
        [1, 2, 3, 4, 5, 6, 7, 8],
        _image_request(),
        media_items=media_items,
    )

    assert result.instance_id == "cloud-a"
    assert session.last_headers[HEADER_PROTOCOL] == PROTOCOL_VERSION_MM
    assert session.last_headers[HEADER_MM_ABI] == mm_abi
    assert session.closed is True


def test_v2_negotiate_rejects_missing_mm_abi_echo(mm_client, monkeypatch):
    response = _FakeResponse(_probe_headers("req-mm", protocol=PROTOCOL_VERSION_MM))
    session = _install_fake_session(monkeypatch, response)
    media_items = [MediaItem("image", IMAGE_DIGEST, 4, 4)]

    with pytest.raises(RuntimeError, match="missing"):
        _run_negotiate(
            mm_client,
            "req-mm",
            [1, 2, 3, 4, 5, 6, 7, 8],
            _image_request(),
            media_items=media_items,
        )
    assert response.closed is True
    assert session.closed is True


def test_v2_negotiate_rejects_mismatched_mm_abi_echo(mm_client, monkeypatch):
    other_abi = mm_abi_header_value(hashlib.sha256(b"other-config").digest())
    response = _FakeResponse(_probe_headers("req-mm", protocol=PROTOCOL_VERSION_MM, mm_abi=other_abi))
    session = _install_fake_session(monkeypatch, response)
    media_items = [MediaItem("image", IMAGE_DIGEST, 4, 4)]

    with pytest.raises(RuntimeError, match="does not match"):
        _run_negotiate(
            mm_client,
            "req-mm",
            [1, 2, 3, 4, 5, 6, 7, 8],
            _image_request(),
            media_items=media_items,
        )
    assert response.closed is True
    assert session.closed is True


def test_v2_negotiate_rejects_legacy_cloud_without_downgrade(mm_client, monkeypatch):
    # An old cloud answers with the v1 protocol marker: the edge must reject
    # instead of degrading to a token-only interpretation of the reservation.
    response = _FakeResponse(_probe_headers("req-mm", protocol=PROTOCOL_VERSION))
    session = _install_fake_session(monkeypatch, response)
    media_items = [MediaItem("image", IMAGE_DIGEST, 4, 4)]

    with pytest.raises(RuntimeError, match="did not acknowledge"):
        _run_negotiate(
            mm_client,
            "req-mm",
            [1, 2, 3, 4, 5, 6, 7, 8],
            _image_request(),
            media_items=media_items,
        )
    assert response.closed is True
    assert session.closed is True


def test_aiohttp_timeout_kwarg_still_used(client, monkeypatch):
    # Guard the fake session signature against the real constructor call.
    captured = {}

    class _RecordingSession(_FakeSession):
        def __init__(self, timeout):
            captured["timeout"] = timeout
            super().__init__(_FakeResponse(_probe_headers("req-1")))

    monkeypatch.setattr(edge_client_module.aiohttp, "ClientSession", _RecordingSession)
    request = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}

    _run_negotiate(client, "req-1", [1, 2, 3, 4, 5], request)

    assert captured["timeout"].connect == 1.0


def test_concurrent_duplicate_request_id_is_rejected_atomically(client, monkeypatch):
    async def run():
        started = asyncio.Event()
        release = asyncio.Event()
        response = _FakeResponse(_probe_headers("req-1"))

        class _BlockingSession(_FakeSession):
            async def post(self, url, headers=None, json=None):
                self.last_headers = headers
                self.last_body = json
                started.set()
                await release.wait()
                return self._response

        session = _BlockingSession(response)
        monkeypatch.setattr(
            edge_client_module.aiohttp,
            "ClientSession",
            lambda timeout: session,
        )
        request = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
        first = asyncio.create_task(client.negotiate("req-1", [1, 2, 3, 4], request))
        await started.wait()

        with pytest.raises(ValueError, match="duplicate"):
            await client.negotiate("req-1", [1, 2, 3, 4], request)

        release.set()
        result = await first
        await client._streams["req-1"]
        await asyncio.sleep(0)
        return result

    result = asyncio.run(run())

    assert result.request_id == "req-1"
    assert client._streams == {}
    assert client._request_ids_in_use == set()


def test_session_construction_failure_releases_request_id(client, monkeypatch):
    def fail_session(*, timeout):
        raise RuntimeError("session construction failed")

    monkeypatch.setattr(edge_client_module.aiohttp, "ClientSession", fail_session)
    request = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}

    with pytest.raises(RuntimeError, match="session construction failed"):
        asyncio.run(client.negotiate("req-1", [1, 2, 3, 4], request))

    assert client._streams == {}
    assert client._request_ids_in_use == set()


def test_cleanup_failures_do_not_mask_probe_error_or_leak_request_id(
    mm_client,
    monkeypatch,
):
    class _FailingCloseResponse(_FakeResponse):
        def close(self):
            raise RuntimeError("response close failed")

    class _FailingCloseSession(_FakeSession):
        async def close(self):
            raise RuntimeError("session close failed")

    response = _FailingCloseResponse(
        _probe_headers("req-mm", protocol=PROTOCOL_VERSION),
    )
    session = _FailingCloseSession(response)
    monkeypatch.setattr(
        edge_client_module.aiohttp,
        "ClientSession",
        lambda timeout: session,
    )
    media_items = [MediaItem("image", IMAGE_DIGEST, 4, 4)]

    with pytest.raises(RuntimeError, match="did not acknowledge"):
        asyncio.run(
            mm_client.negotiate(
                "req-mm",
                [1, 2, 3, 4, 5, 6, 7, 8],
                _image_request(),
                media_items=media_items,
            )
        )

    assert mm_client._streams == {}
    assert mm_client._request_ids_in_use == set()


def test_usage_cleanup_failures_do_not_mask_cancellation(client):
    class _CancelledContent:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise asyncio.CancelledError

    class _FailingCloseResponse(_FakeResponse):
        def __init__(self):
            super().__init__(_probe_headers("req-1"))
            self.content = _CancelledContent()
            self.close_called = False

        def close(self):
            self.close_called = True
            raise RuntimeError("response close failed")

    class _FailingCloseSession(_FakeSession):
        def __init__(self, response):
            super().__init__(response)
            self.close_called = False

        async def close(self):
            self.close_called = True
            raise RuntimeError("session close failed")

    response = _FailingCloseResponse()
    session = _FailingCloseSession(response)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(client._drain_stream("req-1", response, session))

    assert response.close_called is True
    assert session.close_called is True
