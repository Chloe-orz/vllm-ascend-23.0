# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

"""Cloud-owned KV block tables for edge-cloud collaborative inference."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from itertools import chain
from typing import Any

import numpy as np
from vllm.logger import logger
from vllm.sampling_params import SamplingParams
from vllm.v1.core.kv_cache_manager import KVCacheBlocks, KVCacheManager
from vllm.v1.core.kv_cache_utils import BlockHash, resolve_kv_cache_block_sizes
from vllm.v1.core.sched.output import (
    BatchType,
    EdgeCloudFinishedRequest,
    NewRequestData,
    SchedulerOutput,
)
from vllm.v1.kv_cache_interface import KVCacheConfig
from vllm.v1.request import Request

from vllm_ascend.edge_cloud.id_adapter import (
    is_wrapped_req_id,
    parse_req_edge_id,
    wrap_req_id,
)
from vllm_ascend.edge_cloud.observability import log_event
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
        scheduler_block_size, hash_block_size = resolve_kv_cache_block_sizes(kv_cache_config, vllm_config)
        if scheduler_block_size != hash_block_size:
            raise ValueError("edge-cloud prefix coordination currently requires equal scheduler and hash block sizes")
        self.block_size = hash_block_size
        self.instance_id = instance_id
        scheduler_config = vllm_config.scheduler_config
        parallel_config = vllm_config.parallel_config
        speculative_config = getattr(vllm_config, "speculative_config", None)
        self._mtp_enabled = bool(
            speculative_config is not None and getattr(speculative_config, "method", None) == "mtp"
        )
        self._num_speculative_tokens = speculative_config.num_speculative_tokens if self._mtp_enabled else 0
        self._kv = KVCacheManager(
            kv_cache_config=kv_cache_config,
            max_model_len=vllm_config.model_config.max_model_len,
            scheduler_block_size=scheduler_block_size,
            hash_block_size=hash_block_size,
            max_num_batched_tokens=scheduler_config.max_num_batched_tokens,
            enable_caching=True,
            use_eagle=self._mtp_enabled,
            log_stats=False,
            dcp_world_size=parallel_config.decode_context_parallel_size,
            pcp_world_size=parallel_config.prefill_context_parallel_size,
        )
        self._reservations: dict[str, _Reservation] = {}
        self._requests: dict[str, _CloudRequest] = {}
        self._completed_hashes: set[bytes] = set()
        self._mtp_actual_computed_by_task: dict[str, dict[str, int]] = {}
        self._needs_kv_cache_zeroing = kv_cache_config.needs_kv_cache_zeroing
        log_event(
            logger,
            "info",
            "cloud_kv_initialized",
            instance_id=instance_id,
            block_size=self.block_size,
            kv_cache_groups=self._kv.num_kv_cache_groups,
            kv_blocks_total=kv_cache_config.num_blocks,
            kv_blocks_free=self._kv.block_pool.get_num_free_blocks(),
            mtp_enabled=self._mtp_enabled,
            num_speculative_tokens=self._num_speculative_tokens,
        )

    def probe(self, manifest: PrefixManifest) -> ProbeResult:
        """Find and pin the longest completed prefix for one HTTP request."""
        log_event(
            logger,
            "debug",
            "cloud_kv_probe_start",
            request_id=manifest.request_id,
            prompt_tokens=manifest.prompt_tokens,
            full_blocks=manifest.full_block_count,
            block_size=manifest.block_size,
        )
        if manifest.block_size != self.block_size:
            raise ValueError(f"edge/cloud KV block-size mismatch: edge={manifest.block_size}, cloud={self.block_size}")
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
        log_event(
            logger,
            "info",
            "cloud_kv_probe_reserved",
            request_id=manifest.request_id,
            instance_id=self.instance_id,
            candidate_blocks=completed_blocks,
            hit_blocks=hit_tokens // self.block_size,
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
        is_mtp_draft = self._mtp_enabled and scheduler_output.batch_type == BatchType.DRAFT_FIRST
        # This manager runs outside vLLM's Scheduler, which normally advances
        # the KV manager lifecycle at the beginning of every target-model
        # scheduling step. Independently scheduled MTP draft passes are not
        # Scheduler steps and must not advance Mamba's cache lifecycle.
        if not is_mtp_draft:
            self._kv.new_step_starts()
        self._discard_invalidated_mtp_tasks(scheduler_output)
        usage = self._finish_requests(
            scheduler_output.finished_req_ids,
            scheduler_output.edge_cloud_finished_requests or {},
        )
        if scheduler_output.total_num_scheduled_tokens == 0:
            if scheduler_output.finished_req_ids:
                log_event(
                    logger,
                    "debug",
                    "cloud_kv_finish_only_batch",
                    finished_requests=len(scheduler_output.finished_req_ids),
                    usage_records=len(usage),
                )
            return scheduler_output, usage

        if is_mtp_draft:
            return self._rewrite_mtp_draft_output(scheduler_output), usage

        rewritten = copy.copy(scheduler_output)
        rewritten.scheduled_new_reqs = [
            self._admit_new_request(data, scheduler_output) for data in scheduler_output.scheduled_new_reqs
        ]
        rewritten.scheduled_cached_reqs = copy.copy(scheduler_output.scheduled_cached_reqs)
        cached = rewritten.scheduled_cached_reqs
        cached.new_block_ids = list(cached.new_block_ids)
        cached.num_computed_tokens = list(cached.num_computed_tokens)
        cached.new_token_ids = [[0] * len(token_ids) for token_ids in cached.new_token_ids]
        cached.all_token_ids = {
            request_id: np.zeros(len(token_ids), dtype=np.int32)
            for request_id, token_ids in cached.all_token_ids.items()
        }
        rewritten.scheduled_spec_decode_tokens = {
            request_id: [0] * len(token_ids)
            for request_id, token_ids in scheduler_output.scheduled_spec_decode_tokens.items()
        }

        for index, request_id in enumerate(cached.req_ids):
            state = self._requests.get(request_id)
            if state is None:
                log_event(
                    logger,
                    "error",
                    "cloud_kv_request_state_missing",
                    engine_request_id=request_id,
                    phase="allocate",
                )
                raise RuntimeError(f"cloud has no KV request state for {request_id!r}")
            self._sync_output_length(
                state.request,
                cached.num_output_tokens[index],
                allow_shrink=self._mtp_enabled,
            )
            edge_num_computed_tokens = cached.num_computed_tokens[index]
            if state.request.num_computed_tokens != edge_num_computed_tokens:
                log_event(
                    logger,
                    "info",
                    "cloud_kv_computed_tokens_reconciled",
                    engine_request_id=request_id,
                    cloud_tokens=state.request.num_computed_tokens,
                    edge_tokens=edge_num_computed_tokens,
                )
                state.request.num_computed_tokens = edge_num_computed_tokens
            num_scheduled = scheduler_output.num_scheduled_tokens[request_id]
            new_blocks = self._kv.allocate_slots(
                state.request,
                num_new_tokens=num_scheduled,
                num_lookahead_tokens=self._num_speculative_tokens,
                delay_cache_blocks=True,
            )
            if new_blocks is None:
                log_event(
                    logger,
                    "error",
                    "cloud_kv_allocation_failed",
                    engine_request_id=request_id,
                    num_scheduled_tokens=num_scheduled,
                    kv_blocks_total=self._kv.block_pool.num_gpu_blocks,
                    kv_blocks_free=self._kv.block_pool.get_num_free_blocks(),
                )
                raise RuntimeError("cloud KV cache has insufficient free blocks")
            cached.new_block_ids[index] = new_blocks.get_block_ids(allow_none=True)
            log_event(
                logger,
                "debug",
                "cloud_kv_slots_allocated",
                engine_request_id=request_id,
                num_scheduled_tokens=num_scheduled,
                num_computed_tokens=state.request.num_computed_tokens,
            )

        rewritten.num_common_prefix_blocks = self._common_prefix_blocks(rewritten)
        rewritten.new_block_ids_to_zero = (
            self._kv.take_new_block_ids() or None if self._needs_kv_cache_zeroing else None
        )
        log_event(
            logger,
            "debug",
            "cloud_kv_scheduler_output_rewritten",
            new_requests=len(rewritten.scheduled_new_reqs),
            cached_requests=len(cached.req_ids),
            scheduled_tokens=rewritten.total_num_scheduled_tokens,
            usage_records=len(usage),
        )
        return rewritten, usage

    def complete_scheduler_output(self, scheduler_output: SchedulerOutput) -> None:
        """Make blocks reusable only after the cloud worker acknowledges them."""
        if self._mtp_enabled and scheduler_output.batch_type == BatchType.DRAFT_FIRST:
            self._complete_mtp_draft_output(scheduler_output)
            return

        start_tokens = self._num_computed_tokens_by_request(scheduler_output)
        for request_id, num_scheduled in scheduler_output.num_scheduled_tokens.items():
            state = self._requests.get(request_id)
            if state is None:
                continue
            request = state.request
            request.num_computed_tokens = start_tokens[request_id] + num_scheduled
            self._cache_known_blocks(request)
            completed_prompt_blocks = self._mark_completed_prompt_blocks(state)
            log_event(
                logger,
                "debug",
                "cloud_kv_worker_ack_applied",
                control_request_id=state.manifest.request_id,
                engine_request_id=request_id,
                acknowledged_tokens=num_scheduled,
                num_computed_tokens=request.num_computed_tokens,
                completed_prompt_blocks=completed_prompt_blocks,
            )

    @staticmethod
    def _cloud_control_id(engine_request_id: str, control_request_id: str) -> str:
        """Map an edge-side control request id into the cloud namespace.

        Multi-edge scheduler outputs wrap engine request ids with the edge
        prefix at ingress, while the control-plane id embedded in the
        payload stays raw; reservations are keyed by the HTTP-ingress
        wrapped id, so the match key must be re-wrapped here. Legacy
        single-edge deployments leave both ids unwrapped.
        """
        if is_wrapped_req_id(engine_request_id):
            return wrap_req_id(
                parse_req_edge_id(engine_request_id), control_request_id
            )
        return control_request_id

    def _admit_new_request(
        self,
        data: NewRequestData,
        scheduler_output: SchedulerOutput,
    ) -> NewRequestData:
        if data.edge_cloud_request_id is None:
            log_event(
                logger,
                "error",
                "cloud_kv_control_id_missing",
                engine_request_id=data.req_id,
            )
            raise RuntimeError("new cloud request has no control-plane request ID")
        control_request_id = self._cloud_control_id(
            data.req_id, data.edge_cloud_request_id
        )
        reservation = self._reservations.pop(control_request_id, None)
        if reservation is None:
            log_event(
                logger,
                "error",
                "cloud_kv_reservation_missing",
                control_request_id=control_request_id,
                engine_request_id=data.req_id,
            )
            raise RuntimeError(f"cloud has no prefix reservation for {control_request_id!r}")
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
        request.block_hashes = [BlockHash(digest) for digest in reservation.manifest.full_block_hashes]
        common_hit_tokens = data.num_computed_tokens
        log_event(
            logger,
            "info",
            "cloud_kv_admission_start",
            control_request_id=control_request_id,
            engine_request_id=data.req_id,
            reserved_hit_tokens=reservation.hit_tokens,
            common_hit_tokens=common_hit_tokens,
            prompt_tokens=reservation.manifest.prompt_tokens,
        )
        if common_hit_tokens > reservation.hit_tokens:
            self._release_reservation(reservation)
            raise RuntimeError("edge common prefix exceeds the cloud reservation")
        raw_common_blocks, verified_common_hit = self._kv.coordinator.find_longest_cache_hit(
            request.block_hashes,
            common_hit_tokens,
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
                num_lookahead_tokens=self._num_speculative_tokens,
                delay_cache_blocks=True,
            )
            if new_blocks is None:
                log_event(
                    logger,
                    "error",
                    "cloud_kv_allocation_failed",
                    control_request_id=control_request_id,
                    engine_request_id=data.req_id,
                    num_scheduled_tokens=num_scheduled,
                    kv_blocks_total=self._kv.block_pool.num_gpu_blocks,
                    kv_blocks_free=self._kv.block_pool.get_num_free_blocks(),
                )
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
        log_event(
            logger,
            "info",
            "cloud_kv_admission_complete",
            control_request_id=control_request_id,
            engine_request_id=data.req_id,
            cached_tokens=common_hit_tokens,
            num_scheduled_tokens=num_scheduled,
        )
        return rewritten

    def _rewrite_mtp_draft_output(
        self,
        scheduler_output: SchedulerOutput,
    ) -> SchedulerOutput:
        """Project an MTP pass onto existing cloud-owned block tables.

        DRAFT_FIRST reuses the target batch's request shape, but it is not a
        second target-model scheduling decision. Target allocation already
        includes MTP lookahead slots, so allocating or advancing here would
        duplicate the whole target batch once per speculative step.
        """
        self._record_mtp_acceptance(scheduler_output)
        rewritten = copy.copy(scheduler_output)
        rewritten.scheduled_new_reqs = []
        for data in scheduler_output.scheduled_new_reqs:
            self._require_request_state(data.req_id, phase="draft")
            draft_data = copy.copy(data)
            draft_data.prompt_token_ids = None if data.prompt_token_ids is None else [0] * len(data.prompt_token_ids)
            if data.prefill_token_ids is not None:
                draft_data.prefill_token_ids = [0] * len(data.prefill_token_ids)
            draft_data.block_ids = self._kv.get_block_ids(data.req_id)
            rewritten.scheduled_new_reqs.append(draft_data)

        cached = copy.copy(scheduler_output.scheduled_cached_reqs)
        for request_id in cached.req_ids:
            self._require_request_state(request_id, phase="draft")
        cached.new_block_ids = [None] * len(cached.req_ids)
        cached.new_token_ids = [[0] * len(token_ids) for token_ids in cached.new_token_ids]
        cached.all_token_ids = {
            request_id: np.zeros(len(token_ids), dtype=np.int32)
            for request_id, token_ids in cached.all_token_ids.items()
        }
        rewritten.scheduled_cached_reqs = cached
        rewritten.scheduled_spec_decode_tokens = {
            request_id: [0] * len(token_ids)
            for request_id, token_ids in (scheduler_output.scheduled_spec_decode_tokens.items())
        }
        rewritten.new_block_ids_to_zero = None
        rewritten.num_common_prefix_blocks = self._common_prefix_blocks(rewritten)
        log_event(
            logger,
            "debug",
            "cloud_kv_mtp_draft_rewritten",
            draft_task_id=scheduler_output.draft_task_id,
            draft_step_idx=scheduler_output.draft_step_idx,
            request_count=len(scheduler_output.num_scheduled_tokens),
        )
        return rewritten

    def _record_mtp_acceptance(
        self,
        scheduler_output: SchedulerOutput,
    ) -> None:
        if int(scheduler_output.draft_step_idx or 0) != 0:
            return
        valid_counts = scheduler_output.valid_sampled_token_count
        task_id = scheduler_output.draft_task_id
        if valid_counts is None or task_id is None:
            return

        request_ids = list(scheduler_output.num_scheduled_tokens)
        if isinstance(valid_counts, dict):
            valid_by_request = valid_counts
        else:
            if len(valid_counts) != len(request_ids):
                raise RuntimeError("MTP acceptance count does not match the draft batch")
            valid_by_request = dict(zip(request_ids, valid_counts))
        start_tokens = self._num_computed_tokens_by_request(scheduler_output)
        actual_by_request: dict[str, int] = {}
        for request_id in request_ids:
            num_draft_tokens = len(scheduler_output.scheduled_spec_decode_tokens.get(request_id, ()))
            if num_draft_tokens == 0 or request_id not in valid_by_request:
                continue
            valid_count = int(valid_by_request[request_id])
            if not 1 <= valid_count <= num_draft_tokens + 1:
                raise RuntimeError("MTP acceptance count is outside the scheduled draft range")
            actual_by_request[request_id] = start_tokens[request_id] + valid_count
        if actual_by_request:
            self._mtp_actual_computed_by_task[task_id] = actual_by_request
            log_event(
                logger,
                "debug",
                "cloud_kv_mtp_acceptance_recorded",
                draft_task_id=task_id,
                corrected_requests=len(actual_by_request),
            )

    def _complete_mtp_draft_output(
        self,
        scheduler_output: SchedulerOutput,
    ) -> None:
        draft_step_idx = int(scheduler_output.draft_step_idx or 0)
        if draft_step_idx + 1 < self._num_speculative_tokens:
            return
        task_id = scheduler_output.draft_task_id
        corrections = self._mtp_actual_computed_by_task.pop(task_id, {}) if task_id is not None else {}
        completed_prompt_blocks = 0
        for request_id in scheduler_output.num_scheduled_tokens:
            state = self._requests.get(request_id)
            if state is None:
                continue
            request = state.request
            actual_num_computed = corrections.get(request_id)
            if actual_num_computed is not None:
                request.num_computed_tokens = actual_num_computed
                self._cache_known_blocks(request)
            completed_prompt_blocks += self._mark_completed_prompt_blocks(
                state,
                mtp_ready=True,
            )
        log_event(
            logger,
            "debug",
            "cloud_kv_mtp_draft_chain_completed",
            draft_task_id=task_id,
            corrected_requests=len(corrections),
            completed_prompt_blocks=completed_prompt_blocks,
        )

    def _mark_completed_prompt_blocks(
        self,
        state: _CloudRequest,
        *,
        mtp_ready: bool = False,
    ) -> int:
        if self._mtp_enabled and not mtp_ready:
            # The target ACK alone is insufficient: the matching MTP draft
            # chain must populate its KV group before the hash becomes safe to
            # advertise. The final DRAFT ACK calls this method again.
            return 0
        completed_prompt_blocks = (
            min(
                state.request.num_computed_tokens,
                state.manifest.prompt_tokens,
            )
            // self.block_size
        )
        self._completed_hashes.update(state.manifest.full_block_hashes[:completed_prompt_blocks])
        return completed_prompt_blocks

    def _cache_known_blocks(self, request: Request) -> None:
        """Cache only blocks whose opaque hash is already available.

        The cloud does not receive generated token IDs, so output-bearing
        block hashes arrive only in the final EOS manifest. KVCacheManager's
        normal eager cache path assumes Request can hash every full block and
        would either assert or publish a placeholder hash during decoding.
        """
        known_hashed_tokens = len(request.block_hashes) * self.block_size
        self._kv.cache_blocks(
            request,
            min(request.num_computed_tokens, known_hashed_tokens),
        )

    def _discard_invalidated_mtp_tasks(
        self,
        scheduler_output: SchedulerOutput,
    ) -> None:
        task_ids = scheduler_output.cloud_draft_invalidate_task_ids or []
        discarded = 0
        for task_id in task_ids:
            if self._mtp_actual_computed_by_task.pop(task_id, None) is not None:
                discarded += 1
        if discarded:
            log_event(
                logger,
                "debug",
                "cloud_kv_mtp_tasks_invalidated",
                task_count=discarded,
            )

    def _require_request_state(
        self,
        request_id: str,
        *,
        phase: str,
    ) -> _CloudRequest:
        state = self._requests.get(request_id)
        if state is None:
            log_event(
                logger,
                "error",
                "cloud_kv_request_state_missing",
                engine_request_id=request_id,
                phase=phase,
            )
            raise RuntimeError(f"cloud has no KV request state for {request_id!r}")
        return state

    @staticmethod
    def _num_computed_tokens_by_request(
        scheduler_output: SchedulerOutput,
    ) -> dict[str, int]:
        result = {data.req_id: data.num_computed_tokens for data in scheduler_output.scheduled_new_reqs}
        result.update(
            zip(
                scheduler_output.scheduled_cached_reqs.req_ids,
                scheduler_output.scheduled_cached_reqs.num_computed_tokens,
            )
        )
        missing = set(scheduler_output.num_scheduled_tokens).difference(result)
        if missing:
            raise RuntimeError(f"cloud scheduler output has no computed-token start for requests {sorted(missing)}")
        return result

    def _finish_requests(
        self,
        finished_request_ids: set[str],
        finish_data: dict[str, EdgeCloudFinishedRequest],
    ) -> list[tuple[str, UsageInfo]]:
        finished: list[tuple[str, UsageInfo]] = []
        for request_id in finished_request_ids:
            state = self._requests.get(request_id)
            if state is None:
                log_event(
                    logger,
                    "warning",
                    "cloud_kv_finish_state_missing",
                    engine_request_id=request_id,
                )
                continue
            request = state.request
            final = finish_data.get(request_id)
            if final is None:
                log_event(
                    logger,
                    "error",
                    "cloud_kv_finish_accounting_missing",
                    engine_request_id=request_id,
                    finish_record_count=len(finish_data),
                )
                raise RuntimeError(f"cloud finish for {request_id!r} has no accounting data")
            if self._cloud_control_id(request_id, final.control_request_id) != state.manifest.request_id:
                raise RuntimeError("cloud finish has a different control request ID")
            if final.prompt_tokens != state.manifest.prompt_tokens:
                raise RuntimeError("cloud finish has a different prompt length")
            expected_hashes = (final.prompt_tokens + final.completion_tokens) // self.block_size
            if len(final.full_block_hashes) != expected_hashes:
                raise RuntimeError("cloud finish hash count is inconsistent")
            prompt_hash_count = len(state.manifest.full_block_hashes)
            if final.full_block_hashes[:prompt_hash_count] != state.manifest.full_block_hashes:
                raise RuntimeError("cloud finish hash chain changed the prompt prefix")
            self._sync_output_length(
                request,
                final.completion_tokens,
                allow_shrink=self._mtp_enabled,
            )
            max_safe_computed_tokens = max(
                0,
                final.prompt_tokens + final.completion_tokens - 1,
            )
            request.num_computed_tokens = min(
                request.num_computed_tokens,
                max_safe_computed_tokens,
            )
            request.block_hashes = [BlockHash(digest) for digest in final.full_block_hashes]
            self._kv.cache_blocks(request, request.num_computed_tokens)
            completed_blocks = request.num_computed_tokens // self.block_size
            self._completed_hashes.update(final.full_block_hashes[:completed_blocks])
            self._kv.free(request)
            self._requests.pop(request_id, None)
            for task_id, corrections in list(self._mtp_actual_computed_by_task.items()):
                corrections.pop(request_id, None)
                if not corrections:
                    self._mtp_actual_computed_by_task.pop(task_id, None)
            log_event(
                logger,
                "info",
                "cloud_kv_request_finished",
                control_request_id=state.manifest.request_id,
                engine_request_id=request_id,
                prompt_tokens=state.manifest.prompt_tokens,
                completion_tokens=final.completion_tokens,
                cached_tokens=state.cached_tokens,
                completed_blocks=completed_blocks,
            )
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
        log_event(
            logger,
            "debug",
            "cloud_kv_reservation_released",
            request_id=reservation.manifest.request_id,
            hit_tokens=reservation.hit_tokens,
        )

    @staticmethod
    def _sync_output_length(
        request: Request,
        output_tokens: int,
        *,
        allow_shrink: bool = False,
    ) -> None:
        current = request.num_output_tokens
        if output_tokens < current:
            if not allow_shrink:
                raise RuntimeError("cloud output-token count moved backwards")
            del request._output_token_ids[output_tokens:]
            del request._all_token_ids[request.num_prompt_tokens + output_tokens :]
            request._cached_all_token_ids_np = None
        if output_tokens > current:
            request.append_output_token_ids([0] * (output_tokens - current))
