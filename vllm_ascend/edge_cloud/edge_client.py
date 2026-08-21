# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

"""Edge HTTP client for prefix-cache negotiation and usage accounting."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import aiohttp
from vllm.engine.protocol import EdgeCloudPrefixResult
from vllm.logger import logger

from vllm_ascend.edge_cloud.observability import format_event, log_event
from vllm_ascend.edge_cloud.prefix_protocol import PrefixHasher, ProbeResult

_UNSUPPORTED_CONTENT_TYPES = frozenset(
    {
        "input_image",
        "image_url",
        "image_pil",
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
        "image_url",
        "image_pil",
        "image_embeds",
        "audio_url",
        "input_audio",
        "audio_embeds",
        "video_url",
        "prompt_embeds",
    }
)


class EdgePrefixClient:
    """Open and drain one internal OpenAI stream per external request."""

    def __init__(
        self,
        *,
        control_url: str,
        tenant_key_file: str,
        block_size: int,
        connect_timeout: float,
    ) -> None:
        tenant_key = Path(tenant_key_file).read_bytes().strip()
        self._hasher = PrefixHasher(tenant_key, block_size)
        self._control_url = control_url
        self._connect_timeout = connect_timeout
        self._streams: dict[str, asyncio.Task[None]] = {}
        log_event(
            logger,
            "info",
            "edge_client_initialized",
            block_size=block_size,
            connect_timeout=connect_timeout,
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
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """Scrub the prompt and build an OpenAI-compatible request."""
        try:
            self._validate_phase_one_request(openai_request)
        except ValueError as exc:
            log_event(
                logger,
                "warning",
                "edge_request_rejected",
                request_id=request_id,
                reason=str(exc),
            )
            raise
        manifest = self._hasher.build_manifest(request_id, prompt_token_ids)
        body = dict(openai_request)
        body["messages"] = manifest.to_messages()
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
        body["edge_cloud_prompt_tokens"] = manifest.prompt_tokens
        return manifest.to_headers(), body

    async def negotiate(
        self,
        request_id: str,
        prompt_token_ids: Sequence[int],
        openai_request: Mapping[str, Any],
    ) -> EdgeCloudPrefixResult:
        """Reserve a cloud prefix and leave its accounting stream open."""
        if request_id in self._streams:
            log_event(
                logger,
                "warning",
                "edge_duplicate_request",
                request_id=request_id,
            )
            raise ValueError(f"duplicate edge-cloud request ID {request_id!r}")
        headers, body = self.build_control_request(request_id, prompt_token_ids, openai_request)
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
        session = aiohttp.ClientSession(timeout=timeout)
        try:
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
                response.close()
                raise RuntimeError(f"edge-cloud prefix negotiation failed with HTTP {response.status}")
            probe = ProbeResult.from_headers(response.headers)
            if probe.request_id != request_id:
                raise RuntimeError("cloud returned a different request ID")
            if probe.block_size != self.block_size:
                raise RuntimeError(
                    f"edge/cloud KV block-size mismatch: edge={self.block_size}, cloud={probe.block_size}"
                )
            if probe.hit_tokens > len(prompt_token_ids):
                raise RuntimeError("cloud prefix hit exceeds the prompt length")
        except BaseException as exc:
            logger.exception(
                "%s",
                format_event(
                    "edge_probe_failed",
                    request_id=request_id,
                    error_type=type(exc).__name__,
                ),
            )
            await session.close()
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

        task = asyncio.create_task(
            self._drain_stream(request_id, response, session),
            name=f"edge-cloud-usage-{request_id}",
        )
        self._streams[request_id] = task
        task.add_done_callback(lambda _task: self._streams.pop(request_id, None))
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

    async def _drain_stream(
        self,
        request_id: str,
        response: aiohttp.ClientResponse,
        session: aiohttp.ClientSession,
    ) -> None:
        usage: dict[str, Any] | None = None
        try:
            async for raw_line in response.content:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                payload = line.removeprefix("data:").strip()
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
            response.close()
            await session.close()
            log_event(
                logger,
                "debug",
                "edge_usage_stream_closed",
                request_id=request_id,
            )

    @staticmethod
    def _validate_phase_one_request(openai_request: Mapping[str, Any]) -> None:
        if openai_request.get("n", 1) != 1:
            raise ValueError("edge-cloud prefix coordination currently requires n=1")
        if openai_request.get("use_beam_search", False):
            raise ValueError("edge-cloud prefix coordination does not support beam search")
        if openai_request.get("prompt_logprobs") is not None:
            raise ValueError("edge-cloud prefix coordination does not support prompt logprobs")
        messages = openai_request.get("messages")
        if not isinstance(messages, list):
            raise ValueError("edge-cloud coordination requires chat messages")
        if EdgePrefixClient._contains_unsupported_content(messages):
            raise ValueError(
                "edge-cloud prefix coordination supports text-only requests; media and prompt embeds are not supported"
            )

    @staticmethod
    def _contains_unsupported_content(messages: Sequence[Any]) -> bool:
        for message in messages:
            if not isinstance(message, Mapping):
                continue
            if message.get("audio") is not None:
                return True
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, Mapping):
                    continue
                if part.get("type") in _UNSUPPORTED_CONTENT_TYPES:
                    return True
                if _UNSUPPORTED_CONTENT_FIELDS.intersection(part):
                    return True
        return False
