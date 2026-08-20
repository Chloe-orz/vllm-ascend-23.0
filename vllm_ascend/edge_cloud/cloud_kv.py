# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

"""Cloud-owned KV block tables for edge-cloud collaborative inference."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from itertools import chain
from typing import Any

import numpy as np
from vllm.sampling_params import SamplingParams
from vllm.v1.core.kv_cache_manager import KVCacheBlocks, KVCacheManager
from vllm.v1.core.kv_cache_utils import BlockHash, resolve_kv_cache_block_sizes
from vllm.v1.core.sched.output import (
    EdgeCloudFinishedRequest,
    NewRequestData,
    SchedulerOutput,
)
from vllm.v1.kv_cache_interface import KVCacheConfig
from vllm.v1.request import Request

from vllm_ascend.edge_cloud.prefix_protocol import (
    PrefixManifest,
    ProbeResult,
    UsageInfo,
)


@dataclass
class _Reservation:
    manifest: PrefixManifest
    blocks: KVCacheBlocks
    hit_tokens: int


@dataclass
class _CloudRequest:
    request: Request
    manifest: PrefixManifest
    cached_tokens: int


class CloudKVRequestManager:
    """Own cloud KV allocation, prefix reservations, and private block IDs."""

    def __init__(
        self,
        *,
        kv_cache_config: KVCacheConfig,
        vllm_config: Any,
        instance_id: str,
    ) -> None:
        scheduler_block_size, hash_block_size = resolve_kv_cache_block_sizes(
            kv_cache_config, vllm_config
        )
        if scheduler_block_size != hash_block_size:
            raise ValueError(
                "edge-cloud prefix coordination currently requires equal "
                "scheduler and hash block sizes"
            )
        self.block_size = hash_block_size
        self.instance_id = instance_id
        scheduler_config = vllm_config.scheduler_config
        parallel_config = vllm_config.parallel_config
        self._kv = KVCacheManager(
            kv_cache_config=kv_cache_config,
            max_model_len=vllm_config.model_config.max_model_len,
            scheduler_block_size=scheduler_block_size,
            hash_block_size=hash_block_size,
            max_num_batched_tokens=scheduler_config.max_num_batched_tokens,
            enable_caching=True,
            use_eagle=False,
            log_stats=False,
            dcp_world_size=parallel_config.decode_context_parallel_size,
            pcp_world_size=parallel_config.prefill_context_parallel_size,
        )
        self._reservations: dict[str, _Reservation] = {}
        self._requests: dict[str, _CloudRequest] = {}
        self._completed_hashes: set[bytes] = set()

    def probe(self, manifest: PrefixManifest) -> ProbeResult:
        """Find and pin the longest completed prefix for one HTTP request."""
        if manifest.block_size != self.block_size:
            raise ValueError(
                "edge/cloud KV block-size mismatch: "
                f"edge={manifest.block_size}, cloud={self.block_size}"
            )
        if manifest.request_id in self._reservations:
            raise ValueError(f"duplicate reservation {manifest.request_id!r}")

        completed_blocks = 0
        for digest in manifest.full_block_hashes:
            if digest not in self._completed_hashes:
                break
            completed_blocks += 1
        max_hit_tokens = min(
            completed_blocks * self.block_size,
            max(0, manifest.prompt_tokens - 1),
        )
        raw_blocks, hit_tokens = self._kv.coordinator.find_longest_cache_hit(
            [BlockHash(digest) for digest in manifest.full_block_hashes],
            max_hit_tokens,
        )
        blocks = self._kv.create_kv_cache_blocks(raw_blocks)
        self._kv.block_pool.touch(chain.from_iterable(blocks.blocks))
        self._reservations[manifest.request_id] = _Reservation(
            manifest=manifest,
            blocks=blocks,
            hit_tokens=hit_tokens,
        )
        return ProbeResult(
            request_id=manifest.request_id,
            instance_id=self.instance_id,
            block_size=self.block_size,
            hit_blocks=hit_tokens // self.block_size,
            hit_tokens=hit_tokens,
        )

    def rewrite_scheduler_output(
        self, scheduler_output: SchedulerOutput
    ) -> tuple[SchedulerOutput, list[tuple[str, UsageInfo]]]:
        """Replace edge block tables with cloud-owned tables and scrub tokens."""
        usage = self._finish_requests(
            scheduler_output.finished_req_ids,
            scheduler_output.edge_cloud_finished_requests or {},
        )
        if scheduler_output.total_num_scheduled_tokens == 0:
            return scheduler_output, usage

        rewritten = copy.copy(scheduler_output)
        rewritten.scheduled_new_reqs = [
            self._admit_new_request(data, scheduler_output)
            for data in scheduler_output.scheduled_new_reqs
        ]
        rewritten.scheduled_cached_reqs = copy.copy(
            scheduler_output.scheduled_cached_reqs
        )
        cached = rewritten.scheduled_cached_reqs
        cached.new_block_ids = list(cached.new_block_ids)
        cached.num_computed_tokens = list(cached.num_computed_tokens)
        cached.new_token_ids = [
            [0] * len(token_ids) for token_ids in cached.new_token_ids
        ]
        cached.all_token_ids = {
            request_id: np.zeros(len(token_ids), dtype=np.int32)
            for request_id, token_ids in cached.all_token_ids.items()
        }

        for index, request_id in enumerate(cached.req_ids):
            state = self._requests.get(request_id)
            if state is None:
                raise RuntimeError(
                    f"cloud has no KV request state for {request_id!r}"
                )
            self._sync_output_length(state.request, cached.num_output_tokens[index])
            cached.num_computed_tokens[index] = state.request.num_computed_tokens
            num_scheduled = scheduler_output.num_scheduled_tokens[request_id]
            new_blocks = self._kv.allocate_slots(
                state.request,
                num_new_tokens=num_scheduled,
            )
            if new_blocks is None:
                raise RuntimeError("cloud KV cache has insufficient free blocks")
            cached.new_block_ids[index] = new_blocks.get_block_ids(allow_none=True)

        rewritten.num_common_prefix_blocks = self._common_prefix_blocks(rewritten)
        return rewritten, usage

    def complete_scheduler_output(self, scheduler_output: SchedulerOutput) -> None:
        """Make blocks reusable only after the cloud worker acknowledges them."""
        for request_id, num_scheduled in scheduler_output.num_scheduled_tokens.items():
            state = self._requests.get(request_id)
            if state is None:
                continue
            request = state.request
            request.num_computed_tokens += num_scheduled
            self._kv.cache_blocks(request, request.num_computed_tokens)
            completed_prompt_blocks = min(
                request.num_computed_tokens,
                state.manifest.prompt_tokens,
            ) // self.block_size
            self._completed_hashes.update(
                state.manifest.full_block_hashes[:completed_prompt_blocks]
            )

    def _admit_new_request(
        self,
        data: NewRequestData,
        scheduler_output: SchedulerOutput,
    ) -> NewRequestData:
        control_request_id = data.edge_cloud_request_id
        if control_request_id is None:
            raise RuntimeError("new cloud request has no control-plane request ID")
        reservation = self._reservations.pop(control_request_id, None)
        if reservation is None:
            raise RuntimeError(
                f"cloud has no prefix reservation for {control_request_id!r}"
            )
        if data.req_id in self._requests:
            self._release_reservation(reservation)
            raise RuntimeError(f"duplicate cloud request {data.req_id!r}")
        if not isinstance(data.sampling_params, SamplingParams):
            self._release_reservation(reservation)
            raise ValueError("cloud prefix coordination supports generation only")

        request = Request(
            request_id=data.req_id,
            prompt_token_ids=[0] * reservation.manifest.prompt_tokens,
            sampling_params=data.sampling_params,
            pooling_params=None,
            edge_cloud_request_id=control_request_id,
            edge_cloud_prefix_hit_tokens=data.num_computed_tokens,
        )
        request.block_hashes = [
            BlockHash(digest) for digest in reservation.manifest.full_block_hashes
        ]
        common_hit_tokens = data.num_computed_tokens
        if common_hit_tokens > reservation.hit_tokens:
            self._release_reservation(reservation)
            raise RuntimeError("edge common prefix exceeds the cloud reservation")
        raw_common_blocks, verified_common_hit = (
            self._kv.coordinator.find_longest_cache_hit(
                request.block_hashes,
                common_hit_tokens,
            )
        )
        if verified_common_hit != common_hit_tokens:
            self._release_reservation(reservation)
            raise RuntimeError("reserved cloud prefix changed before admission")
        common_blocks = self._kv.create_kv_cache_blocks(raw_common_blocks)
        num_scheduled = scheduler_output.num_scheduled_tokens[data.req_id]
        try:
            new_blocks = self._kv.allocate_slots(
                request,
                num_new_tokens=num_scheduled,
                num_new_computed_tokens=common_hit_tokens,
                new_computed_blocks=common_blocks,
            )
            if new_blocks is None:
                raise RuntimeError("cloud KV cache has insufficient free blocks")
            request.num_computed_tokens = common_hit_tokens
            self._requests[data.req_id] = _CloudRequest(
                request=request,
                manifest=reservation.manifest,
                cached_tokens=common_hit_tokens,
            )
        finally:
            self._release_reservation(reservation)

        rewritten = copy.copy(data)
        rewritten.prompt_token_ids = [0] * reservation.manifest.prompt_tokens
        if rewritten.prefill_token_ids is not None:
            rewritten.prefill_token_ids = [0] * len(rewritten.prefill_token_ids)
        rewritten.block_ids = self._kv.get_block_ids(data.req_id)
        rewritten.num_computed_tokens = common_hit_tokens
        return rewritten

    def _finish_requests(
        self,
        finished_request_ids: set[str],
        finish_data: dict[str, EdgeCloudFinishedRequest],
    ) -> list[tuple[str, UsageInfo]]:
        finished: list[tuple[str, UsageInfo]] = []
        for request_id in finished_request_ids:
            state = self._requests.pop(request_id, None)
            if state is None:
                continue
            request = state.request
            final = finish_data.get(request_id)
            if final is None:
                raise RuntimeError(
                    f"cloud finish for {request_id!r} has no accounting data"
                )
            if final.control_request_id != state.manifest.request_id:
                raise RuntimeError("cloud finish has a different control request ID")
            if final.prompt_tokens != state.manifest.prompt_tokens:
                raise RuntimeError("cloud finish has a different prompt length")
            expected_hashes = (
                final.prompt_tokens + final.completion_tokens
            ) // self.block_size
            if len(final.full_block_hashes) != expected_hashes:
                raise RuntimeError("cloud finish hash count is inconsistent")
            prompt_hash_count = len(state.manifest.full_block_hashes)
            if (
                final.full_block_hashes[:prompt_hash_count]
                != state.manifest.full_block_hashes
            ):
                raise RuntimeError("cloud finish hash chain changed the prompt prefix")
            self._sync_output_length(request, final.completion_tokens)
            request.block_hashes = [
                BlockHash(digest) for digest in final.full_block_hashes
            ]
            self._kv.cache_blocks(request, request.num_computed_tokens)
            completed_blocks = request.num_computed_tokens // self.block_size
            self._completed_hashes.update(
                final.full_block_hashes[:completed_blocks]
            )
            self._kv.free(request)
            finished.append(
                (
                    state.manifest.request_id,
                    UsageInfo(
                        prompt_tokens=state.manifest.prompt_tokens,
                        completion_tokens=final.completion_tokens,
                        cached_tokens=state.cached_tokens,
                    ),
                )
            )
        return finished

    def _common_prefix_blocks(self, scheduler_output: SchedulerOutput) -> list[int]:
        request_ids = list(scheduler_output.num_scheduled_tokens)
        if not request_ids:
            return [0] * self._kv.num_kv_cache_groups
        return self._kv.get_num_common_prefix_blocks(request_ids[0])

    def _release_reservation(self, reservation: _Reservation) -> None:
        self._kv.block_pool.free_blocks(chain.from_iterable(reservation.blocks.blocks))

    @staticmethod
    def _sync_output_length(request: Request, output_tokens: int) -> None:
        current = request.num_output_tokens
        if output_tokens < current:
            raise RuntimeError("cloud output-token count moved backwards")
        if output_tokens > current:
            request.append_output_token_ids([0] * (output_tokens - current))
