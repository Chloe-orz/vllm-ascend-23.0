# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

"""Edge HTTP client for prefix-cache negotiation and usage accounting."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterable, AsyncIterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import aiohttp
from vllm.engine.protocol import EdgeCloudMediaItem, EdgeCloudPrefixResult
from vllm.logger import logger

from vllm_ascend import envs
from vllm_ascend.edge_cloud.mm_identity import mm_abi_header_value
from vllm_ascend.edge_cloud.observability import format_event, log_event
from vllm_ascend.edge_cloud.prefix_protocol import (
    HEADER_EDGE_ID,
    HEADER_MM_ABI,
    HEADER_PROTOCOL,
    PROTOCOL_VERSION,
    PROTOCOL_VERSION_MM,
    PrefixHasher,
    ProbeResult,
)

_IMAGE_CONTENT_TYPES = frozenset(
    {
        "image_url",
        "input_image",
        "image_pil",
    }
)
_UNSUPPORTED_CONTENT_TYPES = frozenset(
    {
        "image_embeds",
        "audio_url",
        "input_audio",
        "audio_embeds",
        "video_url",
        "prompt_embeds",
    }
)
_UNSUPPORTED_CONTENT_FIELDS = frozenset(
    {
        "image_embeds",
        "audio_url",
        "input_audio",
        "audio_embeds",
        "video_url",
        "prompt_embeds",
    }
)


_MAX_CONTROL_MESSAGE_CHARS = 16 * 1024


async def _iter_sse_data(content: AsyncIterable[bytes]) -> AsyncIterator[str]:
    """Read SSE events, preserving multiline data and ignoring heartbeats."""
    data: list[str] = []
    size = 0
    async for raw_line in content:
        line = raw_line.decode("utf-8").rstrip("\r\n")
        if not line:
            if data:
                payload = "\n".join(data)
                data.clear()
                size = 0
                yield payload
        elif line == "data" or line.startswith("data:"):
            value = line.partition(":")[2].removeprefix(" ")
            size += len(value) + 1
            if size > _MAX_CONTROL_MESSAGE_CHARS:
                raise ValueError("edge-cloud SSE event exceeds the control message limit")
            data.append(value)
    if data:
        yield "\n".join(data)


class EdgePrefixClient:
    """Open and drain one internal OpenAI stream per external request."""

    def __init__(
        self,
        *,
        control_url: str,
        tenant_key_file: str,
        block_size: int,
        connect_timeout: float,
        probe_timeout: float = 30.0,
        edge_id: int | None = None,
        processor_fingerprint: bytes | None = None,
    ) -> None:
        tenant_key = Path(tenant_key_file).read_bytes().strip()
        self._hasher = PrefixHasher(tenant_key, block_size, processor_fingerprint)
        self._mm_abi_header = mm_abi_header_value(processor_fingerprint) if processor_fingerprint is not None else None
        self._control_url = control_url
        api_key = envs.VLLM_ASCEND_EDGE_CLOUD_API_KEY
        if api_key is not None:
            if (
                not api_key
                or not api_key.isascii()
                or not api_key.isprintable()
                or any(character.isspace() for character in api_key)
            ):
                raise ValueError(
                    "VLLM_ASCEND_EDGE_CLOUD_API_KEY must contain a non-empty ASCII API token without whitespace"
                )
        self._api_key: str | None = api_key
        self._connect_timeout = connect_timeout
        self._probe_timeout = probe_timeout
        # Self-reported identity only: the edge never sees the cloud-side
        # namespace prefix; the cloud wraps/unwraps request ids internally.
        self._edge_id = edge_id
        self._streams: dict[str, asyncio.Task[None]] = {}
        # Covers both the HTTP probe and the subsequently drained usage stream.
        # Check-and-add happens before the first await in negotiate(), making
        # duplicate request IDs atomic within the owning event loop.
        self._request_ids_in_use: set[str] = set()
        log_event(
            logger,
            "info",
            "edge_client_initialized",
            authenticated=self._api_key is not None,
            block_size=block_size,
            connect_timeout=connect_timeout,
            edge_id=edge_id,
        )

    @property
    def block_size(self) -> int:
        """Return the KV block size used by the hash manifest."""
        return self._hasher.block_size

    def build_control_request(
        self,
        request_id: str,
        prompt_token_ids: Sequence[int],
        openai_request: Mapping[str, Any],
        *,
        media_items: Sequence[EdgeCloudMediaItem] = (),
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """Scrub the prompt and build an OpenAI-compatible request."""
        try:
            self._validate_phase_one_request(openai_request, media_items)
        except ValueError as exc:
            log_event(
                logger,
                "warning",
                "edge_request_rejected",
                request_id=request_id,
                reason=str(exc),
            )
            raise
        manifest = self._hasher.build_manifest(request_id, prompt_token_ids, media_items)
        # Keep the shadow body OpenAI-compatible; control metadata such as
        # prompt length travels in headers. Sampling parameters, metadata and
        # original messages (which may embed media URLs or base64) never cross.
        body: dict[str, Any] = {
            "messages": manifest.to_messages(),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        model = openai_request.get("model")
        if model is not None:
            body["model"] = model
        headers = manifest.to_headers()
        if media_items:
            headers[HEADER_PROTOCOL] = PROTOCOL_VERSION_MM
            assert self._mm_abi_header is not None
            headers[HEADER_MM_ABI] = self._mm_abi_header
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if self._edge_id is not None:
            headers[HEADER_EDGE_ID] = str(self._edge_id)
        return headers, body

    async def negotiate(
        self,
        request_id: str,
        prompt_token_ids: Sequence[int],
        openai_request: Mapping[str, Any],
        *,
        media_items: Sequence[EdgeCloudMediaItem] = (),
    ) -> EdgeCloudPrefixResult:
        """Reserve a cloud prefix and leave its accounting stream open."""
        if request_id in self._request_ids_in_use:
            log_event(
                logger,
                "warning",
                "edge_duplicate_request",
                request_id=request_id,
            )
            raise ValueError(f"duplicate edge-cloud request ID {request_id!r}")
        self._request_ids_in_use.add(request_id)
        try:
            headers, body = self.build_control_request(
                request_id,
                prompt_token_ids,
                openai_request,
                media_items=media_items,
            )
        except BaseException:
            self._request_ids_in_use.discard(request_id)
            raise
        log_event(
            logger,
            "info",
            "edge_negotiate_start",
            request_id=request_id,
            prompt_tokens=len(prompt_token_ids),
            full_blocks=len(prompt_token_ids) // self.block_size,
            tail_tokens=len(prompt_token_ids) % self.block_size,
            block_size=self.block_size,
        )
        timeout = aiohttp.ClientTimeout(total=None, connect=self._connect_timeout)
        session: aiohttp.ClientSession | None = None
        response: aiohttp.ClientResponse | None = None
        try:
            session = aiohttp.ClientSession(timeout=timeout)

            async def receive_probe() -> tuple[ProbeResult, AsyncIterator[str]]:
                nonlocal response
                response = await session.post(
                    self._control_url,
                    headers={**headers, "Accept": "text/event-stream"},
                    json=body,
                )
                if response.status != 200:
                    log_event(
                        logger,
                        "warning",
                        "edge_probe_http_failed",
                        request_id=request_id,
                        http_status=response.status,
                    )
                    raise RuntimeError(f"edge-cloud prefix negotiation failed with HTTP {response.status}")
                sse_data = _iter_sse_data(response.content)
                probe = await self._read_probe(sse_data, multimodal=bool(media_items))
                return probe, sse_data

            probe, sse_data = await asyncio.wait_for(receive_probe(), timeout=self._probe_timeout)
            if probe.request_id != request_id:
                raise RuntimeError("cloud returned a different request ID")
            if probe.block_size != self.block_size:
                raise RuntimeError(
                    f"edge/cloud KV block-size mismatch: edge={self.block_size}, cloud={probe.block_size}"
                )
            if probe.hit_tokens > len(prompt_token_ids):
                raise RuntimeError("cloud prefix hit exceeds the prompt length")

            assert response is not None
            task = asyncio.create_task(
                self._drain_stream(request_id, response, session, sse_data),
                name=f"edge-cloud-usage-{request_id}",
            )
        except BaseException as exc:
            logger.exception(
                "%s",
                format_event(
                    "edge_probe_failed",
                    request_id=request_id,
                    error_type=type(exc).__name__,
                ),
            )
            try:
                if response is not None:
                    response.close()
            except BaseException as cleanup_exc:
                logger.exception(
                    "%s",
                    format_event(
                        "edge_probe_cleanup_failed",
                        request_id=request_id,
                        resource="response",
                        error_type=type(cleanup_exc).__name__,
                    ),
                )
            try:
                if session is not None:
                    await session.close()
            except BaseException as cleanup_exc:
                logger.exception(
                    "%s",
                    format_event(
                        "edge_probe_cleanup_failed",
                        request_id=request_id,
                        resource="session",
                        error_type=type(cleanup_exc).__name__,
                    ),
                )
            finally:
                self._request_ids_in_use.discard(request_id)
            raise

        log_event(
            logger,
            "info",
            "edge_probe_response",
            request_id=request_id,
            instance_id=probe.instance_id,
            hit_tokens=probe.hit_tokens,
            hit_blocks=probe.hit_blocks,
            block_size=probe.block_size,
        )

        self._streams[request_id] = task
        task.add_done_callback(lambda completed, rid=request_id: self._finish_stream(rid, completed))
        log_event(
            logger,
            "debug",
            "edge_usage_stream_started",
            request_id=request_id,
        )
        return EdgeCloudPrefixResult(
            request_id=probe.request_id,
            instance_id=probe.instance_id,
            block_size=probe.block_size,
            hit_tokens=probe.hit_tokens,
        )

    def _finish_stream(
        self,
        request_id: str,
        completed: asyncio.Task[None],
    ) -> None:
        """Release one request ID only for its currently registered task."""
        if self._streams.get(request_id) is completed:
            self._streams.pop(request_id, None)
            self._request_ids_in_use.discard(request_id)

    async def _drain_stream(
        self,
        request_id: str,
        response: aiohttp.ClientResponse,
        session: aiohttp.ClientSession,
        sse_data: AsyncIterator[str] | None = None,
    ) -> None:
        usage: dict[str, Any] | None = None
        try:
            async for payload in sse_data if sse_data is not None else _iter_sse_data(response.content):
                if payload == "[DONE]":
                    break
                chunk = json.loads(payload)
                if chunk.get("usage") is not None:
                    usage = chunk["usage"]
            if usage is None:
                log_event(
                    logger,
                    "error",
                    "edge_usage_missing",
                    request_id=request_id,
                )
            else:
                details = usage.get("prompt_tokens_details") or {}
                log_event(
                    logger,
                    "info",
                    "edge_usage_received",
                    request_id=request_id,
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                    total_tokens=usage.get("total_tokens"),
                    cached_tokens=details.get("cached_tokens"),
                )
        except asyncio.CancelledError:
            log_event(
                logger,
                "warning",
                "edge_usage_stream_cancelled",
                request_id=request_id,
            )
            raise
        except Exception as exc:
            logger.exception(
                "%s",
                format_event(
                    "edge_usage_stream_failed",
                    request_id=request_id,
                    error_type=type(exc).__name__,
                ),
            )
        finally:
            try:
                response.close()
            except BaseException as cleanup_exc:
                logger.exception(
                    "%s",
                    format_event(
                        "edge_usage_cleanup_failed",
                        request_id=request_id,
                        resource="response",
                        error_type=type(cleanup_exc).__name__,
                    ),
                )
            try:
                await session.close()
            except BaseException as cleanup_exc:
                logger.exception(
                    "%s",
                    format_event(
                        "edge_usage_cleanup_failed",
                        request_id=request_id,
                        resource="session",
                        error_type=type(cleanup_exc).__name__,
                    ),
                )
            log_event(
                logger,
                "debug",
                "edge_usage_stream_closed",
                request_id=request_id,
            )

    async def _read_probe(self, sse_data: AsyncIterator[str], *, multimodal: bool) -> ProbeResult:
        """Consume the Probe delta before handing this same iterator to usage."""
        content = ""
        async for payload in sse_data:
            if payload == "[DONE]":
                break
            chunk = json.loads(payload)
            if chunk.get("usage") is not None or chunk.get("error") is not None:
                raise RuntimeError("cloud stream returned usage or an error before the Probe")
            for choice in chunk.get("choices", []):
                fragment = choice.get("delta", {}).get("content")
                if fragment is None:
                    continue
                if not isinstance(fragment, str):
                    raise ValueError("cloud Probe delta.content must be a string")
                content += fragment
                if len(content) > _MAX_CONTROL_MESSAGE_CHARS:
                    raise ValueError("cloud Probe exceeds the control message limit")
                try:
                    message = json.loads(content)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    raise ValueError("cloud Probe must contain a JSON object")
                protocol = PROTOCOL_VERSION_MM if multimodal else PROTOCOL_VERSION
                if message.get("protocol") != protocol:
                    raise RuntimeError(f"cloud did not acknowledge {protocol}")
                if multimodal:
                    if message.get("mm_abi") is None:
                        raise RuntimeError("cloud Probe is missing MM-ABI")
                    if message["mm_abi"] != self._mm_abi_header:
                        raise RuntimeError("cloud MM-ABI fingerprint does not match the local processor fingerprint")
                elif "mm_abi" in message:
                    raise RuntimeError("cloud returned MM-ABI for a text-only Probe")
                return ProbeResult.from_control_message(message)
        raise RuntimeError("cloud stream ended before a complete Probe control message")

    @staticmethod
    def _validate_phase_one_request(
        openai_request: Mapping[str, Any],
        media_items: Sequence[EdgeCloudMediaItem],
    ) -> None:
        if openai_request.get("n", 1) != 1:
            raise ValueError("edge-cloud prefix coordination currently requires n=1")
        if openai_request.get("use_beam_search", False):
            raise ValueError("edge-cloud prefix coordination does not support beam search")
        if openai_request.get("prompt_logprobs") is not None:
            raise ValueError("edge-cloud prefix coordination does not support prompt logprobs")
        messages = openai_request.get("messages")
        if not isinstance(messages, list):
            raise ValueError("edge-cloud coordination requires chat messages")
        has_unsupported, has_image = EdgePrefixClient._scan_message_content(messages)
        if has_unsupported:
            raise ValueError(
                "edge-cloud prefix coordination does not support audio, video, prompt embeds, or media embeds"
            )
        if media_items:
            if not has_image:
                raise ValueError("edge-cloud media descriptions require an image request")
            if openai_request.get("cache_salt") is not None:
                raise ValueError("edge-cloud prefix coordination does not support cache_salt for multimodal requests")
        elif has_image:
            raise ValueError("edge-cloud image request is missing media placeholder descriptions")

    @staticmethod
    def _scan_message_content(messages: Sequence[Any]) -> tuple[bool, bool]:
        """Return ``(has_unsupported_content, has_image_content)``."""
        has_unsupported = False
        has_image = False
        for message in messages:
            if not isinstance(message, Mapping):
                continue
            if message.get("audio") is not None:
                has_unsupported = True
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, Mapping):
                    continue
                if part.get("type") in _IMAGE_CONTENT_TYPES:
                    has_image = True
                elif part.get("type") in _UNSUPPORTED_CONTENT_TYPES:
                    has_unsupported = True
                if _UNSUPPORTED_CONTENT_FIELDS.intersection(part):
                    has_unsupported = True
        return has_unsupported, has_image
