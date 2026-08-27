# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

"""Attach the Ascend edge-cloud prefix client to upstream AsyncLLM."""

from collections.abc import Mapping, Sequence
from typing import Any

from vllm.engine.protocol import EdgeCloudMediaItem, EdgeCloudPrefixResult
from vllm.logger import logger
from vllm.v1.engine.async_llm import AsyncLLM

from vllm_ascend.ascend_config import get_ascend_config
from vllm_ascend.edge_cloud.edge_client import EdgePrefixClient
from vllm_ascend.edge_cloud.mm_identity import compute_processor_fingerprint
from vllm_ascend.edge_cloud.observability import log_event

_INSTALLED_FLAG = "_vllm_ascend_edge_prefix_client_installed"


async def _negotiate_edge_cloud_prefix(
    self: AsyncLLM,
    request_id: str,
    prompt_token_ids: list[int],
    openai_request: Mapping[str, Any],
    *,
    media_items: Sequence[EdgeCloudMediaItem] = (),
) -> EdgeCloudPrefixResult | None:
    edge_cloud_config = get_ascend_config().edge_cloud_config
    coordination = edge_cloud_config.prefix_cache_coordination
    if not edge_cloud_config.enabled or edge_cloud_config.role != "edge" or not coordination.enabled:
        return None

    client = getattr(self, "_edge_cloud_prefix_client", None)
    if client is None:
        assert coordination.control_url is not None
        assert coordination.tenant_key_file is not None
        assert coordination.consumer_id is not None
        client = EdgePrefixClient(
            control_url=coordination.control_url,
            tenant_key_file=coordination.tenant_key_file,
            consumer_id=coordination.consumer_id,
            block_size=self.vllm_config.cache_config.block_size,
            connect_timeout=coordination.connect_timeout,
            processor_fingerprint=compute_processor_fingerprint(self.vllm_config.model_config),
        )
        self._edge_cloud_prefix_client = client
        log_event(
            logger,
            "info",
            "edge_admission_client_created",
            block_size=client.block_size,
        )
    result = await client.negotiate(request_id, prompt_token_ids, openai_request, media_items=media_items)
    log_event(
        logger,
        "info",
        "edge_admission_complete",
        request_id=request_id,
        instance_id=result.instance_id,
        cloud_hit_tokens=result.hit_tokens,
    )
    return result


def install() -> None:
    """Install the optional client hook once per process."""
    if getattr(AsyncLLM, _INSTALLED_FLAG, False):
        return
    AsyncLLM.negotiate_edge_cloud_prefix = _negotiate_edge_cloud_prefix
    AsyncLLM._edge_cloud_prefix_negotiation_enabled = True
    setattr(AsyncLLM, _INSTALLED_FLAG, True)


install()
