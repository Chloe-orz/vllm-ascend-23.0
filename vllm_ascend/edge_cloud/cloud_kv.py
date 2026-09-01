# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

"""Cloud-owned KV block tables for edge-cloud collaborative inference."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from itertools import chain
import os
import time
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
    CloudAllocationFailed,
    PrefixManifest,
    ProbeResult,
    UsageInfo,
)


@dataclass
class _Reservation:
    manifest: PrefixManifest
    blocks: KVCacheBlocks
    hit_tokens: int
    epoch: int = 0
    created_at: float = field(default_factory=time.monotonic)


@dataclass
class _CloudRequest:
    request: Request
    manifest: PrefixManifest
    cached_tokens: int
    epoch: int = 0


class CloudKVRequestManager:
    """Own cloud KV allocation, prefix reservations, and private block IDs."""

    def __init__(
        self,
        *,
        kv_cache_config: KVCacheConfig,
        vllm_config: Any,
        instance_id: str,
        num_edges: int = 1,
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
        # Admission governance (KV-full fault model):
        # - watermark: fresh (non-retry) admissions must leave this fraction
        #   of the pool free, so released retries and in-flight growth are
        #   not starved by new traffic (single-machine FCFS priority for
        #   preempted work).  Retry admissions (pinned in _preempted) are
        #   exempt — their capacity is already accounted for.
        # - per-edge soft share: one edge may not hold more than
        #   factor * (pool / num_edges) blocks while others compete
        #   (bounded borrowing; retries exempt as well).
        self._admission_watermark = float(
            os.environ.get("EDGE_CLOUD_ADMISSION_WATERMARK", "0.9")
        )
        self._edge_share_factor = float(
            os.environ.get("EDGE_CLOUD_EDGE_SHARE_FACTOR", "1.5")
        )
        self._num_edges = max(1, num_edges)
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
        # Reservations of preempted requests, kept pinned so a retry sees
        # the same prefix hit and start position as the first admission.
        self._preempted: dict[str, _Reservation] = {}
        # Bounded ledger of recent state removals, used to classify
        # missing-state occurrences (preempted vs finished) in diagnostics.
        self._recent_state_removals: dict[str, str] = {}
        self._requests: dict[str, _CloudRequest] = {}
        self._completed_hashes: set[bytes] = set()
        self._mtp_actual_computed_by_task: dict[str, dict[str, int]] = {}
        self._mtp_request_ids_by_task: dict[str, set[str]] = {}
        self._mtp_cache_publish_suppressed_request_ids: set[str] = set()
        self._needs_kv_cache_zeroing = kv_cache_config.needs_kv_cache_zeroing
        # Void-run projection pool (protocol resource): members of a voided
        # incarnation (epoch < current or marked) are rewritten to
        # num_computed=0 + these blocks + zeroed tokens, keeping channel
        # shapes and ack flow while their output is discarded by epoch
        # rules.  Permanently allocated; never shared with live requests.
        self._void_tokens = max(
            self.block_size, 4 * (1 + self._num_speculative_tokens)
        )
        void_request = Request(
            request_id="__edge_cloud_void_run__",
            prompt_token_ids=[0] * self._void_tokens,
            sampling_params=SamplingParams(),
            pooling_params=None,
        )
        # delay_cache_blocks=True: the void pool is a pure projection
        # resource and must never enter the prefix cache (the synthetic
        # request has no block hasher, so the caching path would also
        # trip the cache_full_blocks assertion on empty block_hashes).
        void_blocks = self._kv.allocate_slots(
            void_request,
            num_new_tokens=self._void_tokens,
            delay_cache_blocks=True,
        )
        if void_blocks is None:
            raise RuntimeError(
                "cloud KV pool too small for the void-run projection pool"
            )
        self._void_request = void_request
        self._void_block_ids = void_blocks.get_block_ids(allow_none=True)
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
        existing = self._reservations.get(manifest.request_id)
        if existing is not None:
            # Idempotent probe: the edge retries transparently after probe
            # timeouts, and the first attempt may already have reserved.
            # Re-answer from the existing reservation instead of erroring
            # (a duplicate error would loop the retry forever).
            log_event(
                logger,
                "info",
                "cloud_kv_probe_replayed",
                request_id=manifest.request_id,
                instance_id=self.instance_id,
                hit_tokens=existing.hit_tokens,
            )
            return ProbeResult(
                request_id=manifest.request_id,
                instance_id=self.instance_id,
                block_size=self.block_size,
                hit_blocks=existing.hit_tokens // self.block_size,
                hit_tokens=existing.hit_tokens,
            )

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

    def _estimate_required_blocks(
        self,
        scheduler_output: SchedulerOutput,
        skip_req_ids: set[str] | None = None,
    ) -> int:
        """Conservative upper bound of new blocks a batch will allocate.

        Per-request charge: scheduled suffix blocks plus per-request MTP
        lookahead (allocate_slots charges num_lookahead_tokens per request).
        Reservation-pinned prefix blocks are already outside the free pool,
        so they are not charged again.
        """
        lookahead_blocks = (
            -(-self._num_speculative_tokens // self.block_size)
            if self._num_speculative_tokens
            else 0
        )
        needed = 0
        for request_id, num_scheduled in scheduler_output.num_scheduled_tokens.items():
            if skip_req_ids and request_id in skip_req_ids:
                continue
            needed += -(-num_scheduled // self.block_size) + lookahead_blocks
        return needed

    def _stale_epoch_members(self, scheduler_output: SchedulerOutput) -> set[str]:
        """Members whose batch epoch is OLDER than the admitted
        incarnation's epoch.

        A batch from a previous incarnation that arrives after the request
        was re-admitted finds a live state under the same request id;
        without this check it would be treated as a live member and its
        stale tokens/positions would be written into the NEW incarnation's
        blocks — silent corruption.  Such members must void-run instead.
        A batch epoch AHEAD of the state epoch is a protocol error: the
        edge learns epochs only from cloud notices, so it can never
        legitimately lead."""
        epochs = scheduler_output.edge_cloud_epoch_by_req
        if not epochs:
            return set()
        stale: set[str] = set()
        for request_id, batch_epoch in epochs.items():
            state = self._requests.get(request_id)
            if state is None:
                continue
            if batch_epoch < state.epoch:
                stale.add(request_id)
            elif batch_epoch > state.epoch:
                raise RuntimeError(
                    f"edge epoch {batch_epoch} is ahead of the cloud "
                    f"incarnation epoch {state.epoch} for {request_id!r}"
                )
        return stale

    def _non_allocating_members(self, scheduler_output: SchedulerOutput) -> set[str]:
        """Batch members that consume no new blocks in the rewrite:
        void-incarnation members (removal record) plus stale-epoch members
        (older incarnation than the live state)."""
        members = set(scheduler_output.num_scheduled_tokens)
        skip = {
            rid for rid in members if self._is_void_incarnation(rid)
        }
        skip.update(self._stale_epoch_members(scheduler_output))
        return skip

    def _is_retry_admission(self, scheduler_output: SchedulerOutput) -> bool:
        """True when any new request of this batch reclaims a pinned
        preemption reservation — a retry whose capacity is already
        accounted for, exempt from watermark/share admission governance."""
        for data in scheduler_output.scheduled_new_reqs:
            if data.edge_cloud_request_id is None:
                continue
            control_id = self._cloud_control_id(
                data.req_id, data.edge_cloud_request_id
            )
            if control_id in self._preempted:
                return True
        return False

    def _edge_pool_usage(self) -> dict[int, int]:
        """Approximate per-edge block ownership: admitted request tables
        plus pinned reservation blocks, keyed by wrapped-id edge prefix."""
        usage: dict[int, int] = {}

        def charge(req_id: str, blocks: int) -> None:
            if blocks <= 0 or not is_wrapped_req_id(req_id):
                return
            edge_id = parse_req_edge_id(req_id)
            usage[edge_id] = usage.get(edge_id, 0) + blocks

        for req_id in self._requests:
            block_ids = self._kv.get_block_ids(req_id)
            charge(req_id, sum(len(ids) for ids in block_ids))
        for table in (self._reservations, self._preempted):
            for control_id, reservation in table.items():
                charge(
                    control_id,
                    sum(len(ids) for ids in reservation.blocks.blocks),
                )
        return usage

    def can_admit(self, scheduler_output: SchedulerOutput) -> bool:
        """Estimate whether this batch fits the free pool, applying the
        admission governance for the KV-full fault model:

        - void-run members allocate nothing (projection pool) — a fully
          void batch always fits and can drain as a comm shell even while
          the pool is full;
        - retry admissions (pinned in _preempted) always fit — their
          capacity is already reserved;
        - fresh admissions must respect the watermark (leave a free
          fraction for retries / in-flight growth) and the per-edge soft
          share (bounded borrowing, so one edge cannot monopolize the
          pool while the other starves).
        """
        needed = self._estimate_required_blocks(
            scheduler_output,
            skip_req_ids=self._non_allocating_members(scheduler_output),
        )
        if needed == 0:
            return True
        free_blocks = self._kv.block_pool.get_num_free_blocks()
        if free_blocks < needed:
            return False
        if self._is_retry_admission(scheduler_output):
            return True
        total_blocks = self._kv.block_pool.num_gpu_blocks
        if free_blocks - needed < total_blocks * (
            1.0 - self._admission_watermark
        ):
            return False
        member_edges = {
            parse_req_edge_id(rid)
            for rid in scheduler_output.num_scheduled_tokens
            if is_wrapped_req_id(rid)
        }
        if member_edges:
            share_cap = (
                total_blocks / self._num_edges
            ) * self._edge_share_factor
            usage = self._edge_pool_usage()
            for edge_id in member_edges:
                if usage.get(edge_id, 0) + needed > share_cap:
                    return False
        return True

    def preemption_candidates(self) -> list[str]:
        """Engine request ids, most-recently admitted first, excluding
        requests referenced by any in-flight MTP draft task (their draft
        metadata lives here, so preemption would orphan it)."""
        draft_referenced: set[str] = set()
        for members in self._mtp_actual_computed_by_task.values():
            draft_referenced.update(members)
        return [
            request_id
            for request_id in reversed(list(self._requests))
            if request_id not in draft_referenced
        ]

    def preempt_request(self, request_id: str) -> tuple[str, int] | None:
        """Free one admitted request for capacity and pin its prefix for
        retry.  The request's incarnation is voided (epoch incremented);
        its in-flight batches drain via void-run on the projection pool.
        Returns (control request id, new epoch) for the preempt notice, or
        None when the request cannot be preempted safely (its prefix can no
        longer be re-pinned at the original hit length)."""
        state = self._requests.get(request_id)
        if state is None:
            return None
        raw_blocks, hit_tokens = self._kv.coordinator.find_longest_cache_hit(
            [BlockHash(digest) for digest in state.manifest.full_block_hashes],
            state.cached_tokens,
        )
        if hit_tokens != state.cached_tokens:
            # The prefix was partially evicted: retrying would hit a start
            # position mismatch with the edge.  Refuse this victim.
            log_event(
                logger,
                "warning",
                "cloud_kv_preempt_refused_prefix_evicted",
                engine_request_id=request_id,
                cached_tokens=state.cached_tokens,
                repinnable_hit_tokens=hit_tokens,
            )
            return None
        control_request_id = state.manifest.request_id
        new_epoch = state.epoch + 1
        blocks = self._kv.create_kv_cache_blocks(raw_blocks)
        self._kv.block_pool.touch(chain.from_iterable(blocks.blocks))
        self._preempted[control_request_id] = _Reservation(
            manifest=state.manifest,
            blocks=blocks,
            hit_tokens=hit_tokens,
            epoch=new_epoch,
        )
        self._kv.free(state.request)
        self._requests.pop(request_id, None)
        self._record_state_removal(request_id, "preempted")
        for task_id, corrections in list(self._mtp_actual_computed_by_task.items()):
            corrections.pop(request_id, None)
            if not corrections:
                self._mtp_actual_computed_by_task.pop(task_id, None)
        log_event(
            logger,
            "info",
            "cloud_kv_request_preempted",
            engine_request_id=request_id,
            control_request_id=control_request_id,
            repinned_hit_tokens=hit_tokens,
            epoch=new_epoch,
        )
        return control_request_id, new_epoch

    def expire_stale_reservations(
        self, ttl_seconds: float, now: float | None = None
    ) -> list[str]:
        """TTL janitor for reservations that will never be consumed.

        A reservation leaks when the edge dies or wedges between probe and
        admission (``_reservations``) or when a preempted request's edge
        never retries (``_preempted``); its pinned blocks would otherwise
        stay out of the pool forever.  Expiry frees the blocks and returns
        the expired CONTROL request ids so the caller can notify the edge
        (reason "reservation_expired") — the edge must abort the matching
        local request, otherwise a late admission would hit a missing
        reservation, which remains a protocol error.
        """
        now = time.monotonic() if now is None else now
        expired: list[str] = []
        for table, is_preempted in (
            (self._reservations, False),
            (self._preempted, True),
        ):
            for control_id, reservation in list(table.items()):
                age = now - reservation.created_at
                if age < ttl_seconds:
                    continue
                table.pop(control_id, None)
                self._release_reservation(reservation)
                expired.append(control_id)
                log_event(
                    logger,
                    "error",
                    "cloud_kv_reservation_expired",
                    control_request_id=control_id,
                    age_seconds=round(age, 3),
                    preempted=is_preempted,
                )
        return expired

    def release_for_abort(self, request_id: str) -> str | None:
        """Free an admitted request without preserving anything (park
        escalation / abort path — the request will not be retried).
        Returns the control request id for the abort notice, or None
        when the request has no cloud state."""
        state = self._requests.pop(request_id, None)
        if state is None:
            return None
        control_request_id = state.manifest.request_id
        self._kv.free(state.request)
        self._record_state_removal(request_id, "aborted")
        for task_id, corrections in list(self._mtp_actual_computed_by_task.items()):
            corrections.pop(request_id, None)
            if not corrections:
                self._mtp_actual_computed_by_task.pop(task_id, None)
        log_event(
            logger,
            "warning",
            "cloud_kv_request_aborted",
            engine_request_id=request_id,
            control_request_id=control_request_id,
        )
        return control_request_id

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
        self._record_mtp_target_task(scheduler_output)
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

        # Atomicity precheck: raise before ANY admission/allocation so a
        # capacity failure never leaves partially admitted requests or
        # half-allocated block tables behind (a later relief retry can then
        # safely reprocess the whole batch).  Void-incarnation and
        # stale-epoch members are excluded: they execute on the projection
        # pool, not the free pool.
        non_allocating = self._non_allocating_members(scheduler_output)
        required = self._estimate_required_blocks(
            scheduler_output,
            skip_req_ids=non_allocating,
        )
        if self._kv.block_pool.get_num_free_blocks() < required:
            log_event(
                logger,
                "info",
                "cloud_kv_rewrite_capacity_shortfall",
                required_blocks=required,
                kv_blocks_free=self._kv.block_pool.get_num_free_blocks(),
            )
            raise CloudAllocationFailed(
                list(scheduler_output.num_scheduled_tokens))
        rewritten = copy.copy(scheduler_output)
        void_req_ids: list[str] = []
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
                if self._is_void_incarnation(request_id):
                    self._log_void_run(
                        request_id,
                        phase="allocate",
                        scheduler_output=scheduler_output,
                    )
                    cached.num_computed_tokens[index] = 0
                    cached.new_block_ids[index] = self._void_block_ids
                    void_req_ids.append(request_id)
                    continue
                log_event(
                    logger,
                    "error",
                    "cloud_kv_request_state_missing",
                    engine_request_id=request_id,
                    phase="allocate",
                    **self._missing_state_diagnostics(
                        request_id, scheduler_output),
                )
                raise RuntimeError(f"cloud has no KV request state for {request_id!r}")
            if request_id in non_allocating:
                # Stale epoch: a batch of the PREVIOUS incarnation arriving
                # after re-admission.  Void-run it WITHOUT touching the new
                # incarnation's state — its output is discarded by the edge
                # and its tokens must never reach the new blocks.
                log_event(
                    logger,
                    "warning",
                    "cloud_kv_stale_epoch_void",
                    engine_request_id=request_id,
                    phase="allocate",
                    state_epoch=state.epoch,
                )
                cached.num_computed_tokens[index] = 0
                cached.new_block_ids[index] = self._void_block_ids
                void_req_ids.append(request_id)
                continue
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
                raise CloudAllocationFailed([request_id])
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
        if void_req_ids:
            rewritten.cloud_void_req_ids = void_req_ids
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
            # Retry of a preempted request: its reservation was kept pinned
            # so the prefix hit and start position match the first admission.
            reservation = self._preempted.pop(control_request_id, None)
            if reservation is not None:
                log_event(
                    logger,
                    "info",
                    "cloud_kv_preempted_reclaimed",
                    control_request_id=control_request_id,
                    engine_request_id=data.req_id,
                )
        if reservation is None and self._is_void_incarnation(data.req_id):
            # Void-incarnation member (e.g. park-escalated): project onto
            # the projection pool instead of admitting — shapes and acks
            # drain, output discarded by epoch rules.
            self._log_void_run(
                data.req_id, phase="admission", scheduler_output=scheduler_output)
            projected = copy.copy(data)
            projected.prompt_token_ids = (
                None if data.prompt_token_ids is None else [0] * len(data.prompt_token_ids)
            )
            if projected.prefill_token_ids is not None:
                projected.prefill_token_ids = [0] * len(projected.prefill_token_ids)
            projected.num_computed_tokens = 0
            projected.block_ids = self._void_block_ids
            return projected
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
        batch_epochs = scheduler_output.edge_cloud_epoch_by_req or {}
        if (
            data.req_id in batch_epochs
            and batch_epochs[data.req_id] != reservation.epoch
        ):
            # A new admission MUST carry exactly the reservation's epoch:
            # older means a stale incarnation's prefill, newer is
            # impossible (the edge learns epochs from cloud notices).
            self._release_reservation(reservation)
            raise RuntimeError(
                f"admission epoch {batch_epochs[data.req_id]} does not "
                f"match reservation epoch {reservation.epoch} for "
                f"{control_request_id!r}"
            )
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
                raise CloudAllocationFailed([data.req_id])
            request.num_computed_tokens = common_hit_tokens
            self._requests[data.req_id] = _CloudRequest(
                request=request,
                manifest=reservation.manifest,
                cached_tokens=common_hit_tokens,
                epoch=reservation.epoch,
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
        stale_members = self._stale_epoch_members(scheduler_output)
        rewritten = copy.copy(scheduler_output)
        void_req_ids: list[str] = []
        rewritten.scheduled_new_reqs = []
        for data in scheduler_output.scheduled_new_reqs:
            if data.req_id not in self._requests:
                if not self._is_void_incarnation(data.req_id):
                    self._require_request_state(
                        data.req_id, phase="draft", scheduler_output=scheduler_output)
                self._log_void_run(
                    data.req_id, phase="draft", scheduler_output=scheduler_output)
                void_req_ids.append(data.req_id)
                draft_data = copy.copy(data)
                draft_data.prompt_token_ids = None if data.prompt_token_ids is None else [0] * len(data.prompt_token_ids)
                if data.prefill_token_ids is not None:
                    draft_data.prefill_token_ids = [0] * len(data.prefill_token_ids)
                draft_data.num_computed_tokens = 0
                draft_data.block_ids = self._void_block_ids
                rewritten.scheduled_new_reqs.append(draft_data)
                continue
            if data.req_id in stale_members:
                # Stale epoch: previous-incarnation draft after re-admission;
                # void-run without touching the new incarnation's state.
                log_event(
                    logger,
                    "warning",
                    "cloud_kv_stale_epoch_void",
                    engine_request_id=data.req_id,
                    phase="draft",
                )
                void_req_ids.append(data.req_id)
                draft_data = copy.copy(data)
                draft_data.prompt_token_ids = None if data.prompt_token_ids is None else [0] * len(data.prompt_token_ids)
                if data.prefill_token_ids is not None:
                    draft_data.prefill_token_ids = [0] * len(data.prefill_token_ids)
                draft_data.num_computed_tokens = 0
                draft_data.block_ids = self._void_block_ids
                rewritten.scheduled_new_reqs.append(draft_data)
                continue
            draft_data = copy.copy(data)
            draft_data.prompt_token_ids = None if data.prompt_token_ids is None else [0] * len(data.prompt_token_ids)
            if data.prefill_token_ids is not None:
                draft_data.prefill_token_ids = [0] * len(data.prefill_token_ids)
            draft_data.block_ids = self._kv.get_block_ids(data.req_id)
            rewritten.scheduled_new_reqs.append(draft_data)

        cached = copy.copy(scheduler_output.scheduled_cached_reqs)
        cached.new_block_ids = [None] * len(cached.req_ids)
        cached.num_computed_tokens = list(cached.num_computed_tokens)
        for index, request_id in enumerate(cached.req_ids):
            if request_id in stale_members:
                log_event(
                    logger,
                    "warning",
                    "cloud_kv_stale_epoch_void",
                    engine_request_id=request_id,
                    phase="draft",
                )
                void_req_ids.append(request_id)
                cached.num_computed_tokens[index] = 0
                cached.new_block_ids[index] = self._void_block_ids
                continue
            if request_id in self._requests:
                continue
            if not self._is_void_incarnation(request_id):
                self._require_request_state(
                    request_id, phase="draft", scheduler_output=scheduler_output)
            self._log_void_run(
                request_id, phase="draft", scheduler_output=scheduler_output)
            void_req_ids.append(request_id)
            cached.num_computed_tokens[index] = 0
            cached.new_block_ids[index] = self._void_block_ids
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
        if void_req_ids:
            rewritten.cloud_void_req_ids = void_req_ids
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

    def _record_mtp_target_task(self, scheduler_output: SchedulerOutput) -> None:
        """Remember which requests require a matching final draft ACK."""
        if (
            not self._mtp_enabled
            or scheduler_output.batch_type == BatchType.DRAFT_FIRST
            or not scheduler_output.head_token
        ):
            return
        self._mtp_request_ids_by_task[scheduler_output.head_token] = set(scheduler_output.num_scheduled_tokens)

    def _complete_mtp_draft_output(
        self,
        scheduler_output: SchedulerOutput,
    ) -> None:
        draft_step_idx = int(scheduler_output.draft_step_idx or 0)
        if draft_step_idx + 1 < self._num_speculative_tokens:
            return
        task_id = scheduler_output.draft_task_id
        corrections = self._mtp_actual_computed_by_task.pop(task_id, {}) if task_id is not None else {}
        if task_id is not None:
            self._mtp_request_ids_by_task.pop(task_id, None)
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
            had_correction = self._mtp_actual_computed_by_task.pop(task_id, None) is not None
            request_ids = self._mtp_request_ids_by_task.pop(task_id, set())
            self._mtp_cache_publish_suppressed_request_ids.update(request_ids)
            if had_correction or request_ids:
                discarded += 1
        if discarded:
            log_event(
                logger,
                "debug",
                "cloud_kv_mtp_tasks_invalidated",
                task_count=discarded,
            )

    def _log_void_run(
        self,
        request_id: str,
        *,
        phase: str,
        scheduler_output: SchedulerOutput,
    ) -> None:
        log_event(
            logger,
            "warning",
            "cloud_kv_void_run_member",
            engine_request_id=request_id,
            phase=phase,
            **self._missing_state_diagnostics(request_id, scheduler_output),
        )

    def _is_void_incarnation(self, request_id: str) -> bool:
        """A member may be void-run only if its state was removed by a
        defined transition (preempted / finished / aborted).  Anything
        else is a protocol error, never void-run."""
        return request_id in self._recent_state_removals

    def _record_state_removal(self, request_id: str, reason: str) -> None:
        self._recent_state_removals[request_id] = reason
        # Bound the ledger: keep only the most recent 256 entries.
        while len(self._recent_state_removals) > 256:
            self._recent_state_removals.pop(
                next(iter(self._recent_state_removals)))

    def _missing_state_diagnostics(
        self,
        request_id: str,
        scheduler_output: SchedulerOutput | None,
    ) -> dict[str, Any]:
        """Classify a missing-state occurrence for diagnostics:

        - recent_removal_reason: "preempted" (P-A) / "finished" (P-B) /
          None (state vanished by an unclassified path);
        - batch composition: live members vs total, which tells whether
          this was a mixed batch (P-C) the edge could not drop."""
        info: dict[str, Any] = {
            "recent_removal_reason": self._recent_state_removals.get(request_id)
        }
        if scheduler_output is not None:
            members = list(scheduler_output.num_scheduled_tokens)
            info["batch_total_members"] = len(members)
            info["batch_live_members"] = sum(
                1 for rid in members if rid in self._requests
            )
        return info

    def _require_request_state(
        self,
        request_id: str,
        *,
        phase: str,
        scheduler_output: SchedulerOutput | None = None,
    ) -> _CloudRequest:
        state = self._requests.get(request_id)
        if state is None:
            log_event(
                logger,
                "error",
                "cloud_kv_request_state_missing",
                engine_request_id=request_id,
                phase=phase,
                **self._missing_state_diagnostics(request_id, scheduler_output),
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
                # Orphan finish (client abort / edge-side finish before the
                # first admission): release the matching reservation so its
                # pinned blocks do not leak.
                final = finish_data.get(request_id)
                released = False
                if final is not None:
                    control_id = self._cloud_control_id(
                        request_id, final.control_request_id)
                    # Also check the preempted store: an aborted retry
                    # holds its reservation there and must be released too.
                    for store in (self._reservations, self._preempted):
                        reservation = store.pop(control_id, None)
                        if reservation is not None:
                            self._release_reservation(reservation)
                            released = True
                log_event(
                    logger,
                    "info" if released else "warning",
                    "cloud_kv_orphan_finish_reservation_released"
                    if released else "cloud_kv_finish_state_missing",
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
            publish_cache = final.publish_cache and request_id not in self._mtp_cache_publish_suppressed_request_ids
            if publish_cache:
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
            if publish_cache:
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
            else:
                # Fail-closed finish (e.g. the edge could not reconstruct the
                # media identity): complete accounting and release the request,
                # but publish no additional blocks from FINISH. Prompt blocks
                # already made visible after worker ACKs are not revoked.
                completed_blocks = 0
                log_event(
                    logger,
                    "warning",
                    "cloud_finish_cache_publish_suppressed",
                    control_request_id=state.manifest.request_id,
                    engine_request_id=request_id,
                    prompt_tokens=state.manifest.prompt_tokens,
                    completion_tokens=final.completion_tokens,
                    mtp_draft_invalidated=(request_id in self._mtp_cache_publish_suppressed_request_ids),
                )
            self._kv.free(request)
            self._requests.pop(request_id, None)
            self._record_state_removal(request_id, "finished")
            self._mtp_cache_publish_suppressed_request_ids.discard(request_id)
            for task_id, request_ids in list(self._mtp_request_ids_by_task.items()):
                request_ids.discard(request_id)
                if not request_ids:
                    self._mtp_request_ids_by_task.pop(task_id, None)
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
