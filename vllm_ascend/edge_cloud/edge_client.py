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
from vllm.logger import init_logger

from vllm_ascend.edge_cloud.prefix_protocol import PrefixHasher, ProbeResult

logger = init_logger(__name__)


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
        self._validate_phase_one_request(openai_request)
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
            raise ValueError(f"duplicate edge-cloud request ID {request_id!r}")
        headers, body = self.build_control_request(
            request_id, prompt_token_ids, openai_request
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
                detail = (await response.text())[:1024]
                raise RuntimeError(
                    "edge-cloud prefix negotiation failed with HTTP "
                    f"{response.status}: {detail}"
                )
            probe = ProbeResult.from_headers(response.headers)
            if probe.request_id != request_id:
                raise RuntimeError("cloud returned a different request ID")
            if probe.block_size != self.block_size:
                raise RuntimeError(
                    "edge/cloud KV block-size mismatch: "
                    f"edge={self.block_size}, cloud={probe.block_size}"
                )
            if probe.hit_tokens > len(prompt_token_ids):
                raise RuntimeError("cloud prefix hit exceeds the prompt length")
        except BaseException:
            await session.close()
            raise

        task = asyncio.create_task(
            self._drain_stream(request_id, response, session),
            name=f"edge-cloud-usage-{request_id}",
        )
        self._streams[request_id] = task
        task.add_done_callback(lambda _task: self._streams.pop(request_id, None))
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
                logger.error(
                    "Edge-cloud stream ended without usage for request %s",
                    request_id,
                )
            else:
                logger.info(
                    "Edge-cloud usage received for request %s: %s",
                    request_id,
                    usage,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Failed while draining edge-cloud stream for request %s",
                request_id,
            )
        finally:
            response.close()
            await session.close()

    @staticmethod
    def _validate_phase_one_request(openai_request: Mapping[str, Any]) -> None:
        if openai_request.get("n", 1) != 1:
            raise ValueError("edge-cloud prefix coordination currently requires n=1")
        if openai_request.get("use_beam_search", False):
            raise ValueError(
                "edge-cloud prefix coordination does not support beam search"
            )
        if openai_request.get("prompt_logprobs") is not None:
            raise ValueError(
                "edge-cloud prefix coordination does not support prompt logprobs"
            )
        messages = openai_request.get("messages")
        if not isinstance(messages, list):
            raise ValueError("edge-cloud coordination requires chat messages")
