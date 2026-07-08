# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
import enum
import os
import time
from collections import deque

import numpy as np
from collections.abc import Iterable
from typing import Any
from uuid import uuid4

from vllm.logger import logger
from vllm.v1.core.sched.async_scheduler import AsyncScheduler
from vllm.v1.core.sched.interface import PauseState
from vllm.v1.core.sched.output import BatchType, HiddenChannelType, SchedulerOutput
from vllm.v1.core.sched.request_queue import create_request_queue
from vllm.v1.core.sched.scheduler import Scheduler
from vllm.v1.core.sched.utils import remove_all
from vllm.v1.engine import EngineCoreEventType
from vllm.v1.outputs import ModelRunnerOutput
from vllm.v1.request import Request, RequestStatus


class PrefillState(enum.Enum):
    """Edge-side prefill in-flight state machine.

    See Phase5 design in ``PDbatch分离边云协同Phase5&7详细设计.md``.
    """
    IDLE = "idle"       # prefill_inflight_count == 0
    LOW = "low"         # prefill_inflight_count == 1
    HIGH = "high"       # prefill_inflight_count >= prefill_inflight_limit


class HiddenChannelManager:
    """Manages data-plane hidden tensor channels for edge-cloud PD separation.

    Two prefill channels (PREFILL_1 / PREFILL_2) support 2P1D; one decode
    channel (DECODE) supports single in-flight decode. Channels are allocated
    in FIFO order and freed when the tail segment completes.
    """

    def __init__(self) -> None:
        self._free_prefills: deque[HiddenChannelType] = deque([
            HiddenChannelType.PREFILL_1,
            HiddenChannelType.PREFILL_2,
        ])
        # Mapping from head_token to the allocated channel.  Only prefill
        # batches are recorded here; decode batches always use DECODE and
        # do not need a mapping.
        self._head_token_to_channel: dict[str, HiddenChannelType] = {}

    # ------------------------------------------------------------------ #
    # Prefill channel allocation / release                               #
    # ------------------------------------------------------------------ #
    def allocate_prefill(self, head_token: str) -> HiddenChannelType:
        """Allocate a free prefill channel for the batch identified by
        ``head_token``. Raises if none available."""
        if not self._free_prefills:
            raise RuntimeError(
                "No free prefill hidden channel available"
            )
        channel = self._free_prefills.popleft()
        self._head_token_to_channel[head_token] = channel
        return channel

    def release_prefill(self, head_token: str) -> HiddenChannelType | None:
        """Release the prefill channel previously allocated for
        ``head_token``. Returns the freed channel (or None if not found)."""
        channel = self._head_token_to_channel.pop(head_token, None)
        if channel is None:
            return None
        self._free_prefills.append(channel)
        return channel

    def has_free_prefill(self) -> bool:
        return bool(self._free_prefills)

    # ------------------------------------------------------------------ #
    # Decode channel (always DECODE, no free-list)                        #
    # ------------------------------------------------------------------ #
    @staticmethod
    def decode_channel() -> HiddenChannelType:
        return HiddenChannelType.DECODE

    # ------------------------------------------------------------------ #
    # Introspection                                                      #
    # ------------------------------------------------------------------ #
    def get_channel(self, head_token: str) -> HiddenChannelType | None:
        return self._head_token_to_channel.get(head_token)

    @property
    def in_use_prefills(self) -> list[HiddenChannelType]:
        return list(self._head_token_to_channel.values())


class PDSeparatedScheduler(Scheduler):
    """Scheduler that separates prefill and decode into distinct steps.

    In edge-cloud PD-separated mode the four cardinal phases are:
      - PREFILL_FIRST  (edge head segment)
      - PREFILL_LAST   (edge tail segment, sourced from cloud-returned outputs)
      - DECODE_FIRST   (Phase 4)
      - DECODE_LAST    (Phase 4)

    This class owns the request bookkeeping for *first* segments
    (``chunk_prefill_first`` + parent's ``waiting`` / ``running``) and the
    ready queues for *last* segments (``prefills_last_ready`` /
    ``decodes_last_ready``), which are filled by the EngineCore from the
    POST_OUT channel before each ``schedule()`` call.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Requests that have started their P-first segment but have not yet
        # been fully consumed (still chunking, or still in flight on cloud).
        self.chunk_prefill_first: list[Request] = []

        # SchedulerOutputs returned from cloud (POST_OUT channel) carrying
        # the metadata needed to execute the edge tail segment.
        # Populated by EngineCore.step() before calling self.schedule().
        self.prefills_last_ready: deque[SchedulerOutput] = deque()
        self.decodes_last_ready: deque[SchedulerOutput] = deque()

        self._step_counter: int = 0

        # In-flight prefill limit (head-segment batches).
        self.prefill_inflight_limit: int = getattr(
            self.scheduler_config, "pd_prefill_inflight_limit", 1
        )
        self.prefill_inflight_count: int = 0
        self.decode_inflight_limit: int = 1
        self.decode_inflight_count: int = 0

        # Phase6 data-plane channel manager.  Two prefill hidden channels are
        # available for 2P1D; decode uses a dedicated fixed channel.
        self.hidden_channel_manager = HiddenChannelManager()

        # Buffer queue: requests whose P-first segment is done but P-last
        # segment has not yet returned from the cloud.  Not eligible for
        # decode scheduling until PL completes and they are moved to running.
        self.prefill_last_pending: list[Request] = []

        # Requests whose head segment (PF/DF) has been scheduled but whose
        # tail segment (PL/DL) has not yet completed on the cloud round-trip.
        # Aborts/finishes for these reqs are *deferred* (see ``finish_requests``
        # and ``_flush_completed_deferred_finishes``): the cloud has already
        # committed hidden tensors sized to ``total_num_scheduled_tokens`` for
        # them, so the edge tail must still process those tokens.  Finishing
        # immediately would pop the req from the worker's
        # ``self.requests``/``input_batch`` and break data-plane alignment
        # (KeyError in ``_update_states`` + token misalignment in
        # ``_prepare_inputs``).  We keep KV blocks + ``self.requests`` until
        # the matching PL/DL returns, then complete the finish.
        self._in_flight_tail_req_ids: set[str] = set()
        # req_id -> finished_status for reqs whose finish was deferred because
        # their tail was in flight.  Flushed in ``update_from_output`` once the
        # matching PL/DL completes.
        self._deferred_finish: dict[str, RequestStatus] = {}

        # [新增] DECODE_LAST 延迟调度计时器。
        # D首 pick 后启动，D尾 在延迟到期前不可被调度。
        self._decode_last_delay_start_ts: float | None = None
        self._decode_last_delay_schedule_ms: int = 30

        # [新增] 强制调度 D尾 标记。
        # D首 调度后置 True，D尾 调度后置 False。
        # True 时禁止调度 D首，严格保证 DF -> DL 交替时序。
        self._force_decode_last: bool = False

        self._layer_slice_config_path: str | None = None
        self._layer_slice_config_mtime: float = 0.0
        self._load_layer_slice_config()

    def schedule(self) -> SchedulerOutput:
        return self._schedule_pd_separated()

    def _make_empty_batch(self) -> SchedulerOutput:
        scheduler_output = SchedulerOutput.make_empty()
        scheduler_output.finished_req_ids = self.finished_req_ids
        self.finished_req_ids = set()
        return scheduler_output

    def _schedule_pd_separated(self) -> SchedulerOutput:
        state = self._prefill_state()
        scheduler_output = self._pick_by_state(state)
        has_work = scheduler_output.total_num_scheduled_tokens > 0
        is_tail = scheduler_output.batch_type in (
            BatchType.PREFILL_LAST,
            BatchType.DECODE_LAST,
        )
        if has_work or is_tail:
            self._log_scheduler_state(state, scheduler_output.batch_type)
        return scheduler_output

    def _pick_by_state(self, state: PrefillState) -> SchedulerOutput:
        # D尾必须无条件优先于 D首，防止 decode_inflight_count 在 D首
        # 完成后立即释放导致 D尾 starvation。
        if state == PrefillState.IDLE:
            # IDLE: P首/chunk0首 > D尾 > D首 > Empty.
            if self._can_schedule_prefill_first():
                so = self._pick_prefill_first_batch()
                if so.total_num_scheduled_tokens > 0:
                    return so
                # P首 returned empty (e.g. KV cache exhausted). Preserve
                # finished_req_ids and fall through to decode tasks to avoid
                # a tight busy-loop where the edge spins on empty prefill.
                logger.warning(
                    "PREFILL_FIRST returned empty batch (total_num_scheduled_tokens=0). "
                    "This usually means KV cache blocks are exhausted by running decode "
                    "requests. Prefill work will be deferred until resources are freed."
                )
                self.finished_req_ids.update(so.finished_req_ids)
            if self.decodes_last_ready and self._can_schedule_decode_last():
                return self._pick_decode_last_batch()
            if self._can_schedule_decode_first():
                return self._pick_decode_first_batch()
            return self._make_empty_batch()

        if state == PrefillState.LOW:
            # LOW: chunk/P首(when slot available) > D尾 > D首 > P尾 > Empty.
            if self._can_schedule_prefill_first():
                so = self._pick_prefill_first_batch()
                if so.total_num_scheduled_tokens > 0:
                    return so
                logger.warning(
                    "PREFILL_FIRST returned empty batch (total_num_scheduled_tokens=0). "
                    "This usually means KV cache blocks are exhausted by running decode "
                    "requests. Prefill work will be deferred until resources are freed."
                )
                self.finished_req_ids.update(so.finished_req_ids)
            if self.decodes_last_ready and self._can_schedule_decode_last():
                return self._pick_decode_last_batch()
            if self._can_schedule_decode_first():
                return self._pick_decode_first_batch()
            if self.prefills_last_ready:
                return self._pick_prefill_last_batch()
            return self._make_empty_batch()

        # HIGH: D尾 > D首 > P尾 > Empty. New P首 is forbidden.
        if self.decodes_last_ready and self._can_schedule_decode_last():
            return self._pick_decode_last_batch()
        if self._can_schedule_decode_first():
            return self._pick_decode_first_batch()
        if self.prefills_last_ready:
            return self._pick_prefill_last_batch()
        return self._make_empty_batch()

    def is_waiting_for_remote_tail(self) -> bool:
        """True when local requests exist only as remote in-flight work.

        In this state the edge has no local batch to execute until POST_OUT
        returns a PREFILL_LAST/DECODE_LAST, so the EngineCore should yield
        instead of tight-loop scheduling EMPTY batches.
        """
        return bool(
            (self.prefill_inflight_count > 0 or self.decode_inflight_count > 0)
            and not self.prefills_last_ready
            and not self.decodes_last_ready
            and not self._can_schedule_prefill_first()
            and not self._can_schedule_decode_first()
        )

    def _prefill_state(self) -> PrefillState:
        if self.prefill_inflight_count <= 0:
            return PrefillState.IDLE
        if (
            self.prefill_inflight_limit > 1
            and self.prefill_inflight_count >= self.prefill_inflight_limit
        ):
            return PrefillState.HIGH
        return PrefillState.LOW

    def _has_prefill_work(self) -> bool:
        return bool(self.chunk_prefill_first or self.waiting)

    def _can_schedule_prefill_first(self) -> bool:
        # When running decode requests already fill max_num_running_reqs,
        # super().schedule() inside _pick_prefill_first_batch will return an
        # empty batch, causing a tight-loop.  Pre-check capacity to avoid
        # the useless call.
        effective_capacity = self.max_num_running_reqs - len(self.running)
        return (
            self._has_prefill_work()
            and self.prefill_inflight_count < self.prefill_inflight_limit
            and self.hidden_channel_manager.has_free_prefill()
            and effective_capacity > 0
        )

    def _can_schedule_decode_first(self) -> bool:
        return bool(
            self.running
            and self.decode_inflight_count < self.decode_inflight_limit
            and not self._force_decode_last
        )

    def _log_scheduler_state(self, state: PrefillState, batch_type: BatchType) -> None:
        self._step_counter += 1
        logger.info(
            f"[PD] Step{self._step_counter}, state is {state}, batch_type is {batch_type}, "
            f"waiting[]: {len(self.waiting)}, "
            f"chunk_prefill_first[]: {len(self.chunk_prefill_first)}, "
            f"prefill_last_pending[]: {len(self.prefill_last_pending)}, "
            f"running[]: {len(self.running)}, "
            f"prefills_last_ready[]: {len(self.prefills_last_ready)}, "
            f"decodes_last_ready[]: {len(self.decodes_last_ready)}, "
            f"prefill_inflight: {self.prefill_inflight_count}/{self.prefill_inflight_limit}, "
            f"decode_inflight: {self.decode_inflight_count}/{self.decode_inflight_limit}",
        )

    # ------------------------------------------------------------------ #
    # Layer-slice config loading (Edge side)                             #
    # ------------------------------------------------------------------ #
    def _load_layer_slice_config(self) -> None:
        """Load decode_last_delay_schedule_ms from layer_slice_config.yaml."""
        yaml_path = os.environ.get("VLLM_LAYER_SLICE_CONFIG")
        if yaml_path is None:
            yaml_path = os.path.join(
                os.path.dirname(__file__), "layer_slice_config.yaml"
            )
        if not os.path.exists(yaml_path):
            self._layer_slice_config_path = None
            self._layer_slice_config_mtime = 0.0
            return
        try:
            import yaml
            with open(yaml_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            if not isinstance(raw, dict):
                logger.warning(
                    "Layer-slice config %s is not a dict; ignoring.", yaml_path
                )
                return
            _key = "decode_last_delay_schedule_ms"
            if _key in raw:
                try:
                    self._decode_last_delay_schedule_ms = int(raw[_key])
                    logger.info(
                        "[PDSeparatedScheduler] %s set to %d from %s",
                        _key, self._decode_last_delay_schedule_ms, yaml_path,
                    )
                except (ValueError, TypeError):
                    logger.warning(
                        "Invalid %s value %r in %s; keeping %d",
                        _key, raw[_key], yaml_path,
                        self._decode_last_delay_schedule_ms,
                    )
            self._layer_slice_config_path = yaml_path
            self._layer_slice_config_mtime = os.path.getmtime(yaml_path)
        except Exception:
            logger.exception("Failed to load layer-slice config from %s", yaml_path)

    def _maybe_hot_reload_layer_slice_config(self) -> None:
        """Check whether the YAML config file has changed on disk and reload."""
        path = self._layer_slice_config_path
        if path is None:
            return
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return
        if mtime != self._layer_slice_config_mtime:
            old_value = self._decode_last_delay_schedule_ms
            self._load_layer_slice_config()
            if self._decode_last_delay_schedule_ms != old_value:
                logger.info(
                    "[PDSeparatedScheduler] Layer-slice config hot-reloaded: "
                    "%s=%d",
                    "decode_last_delay_schedule_ms",
                    self._decode_last_delay_schedule_ms,
                )

    # ------------------------------------------------------------------ #
    # DECODE_LAST delay scheduling                                       #
    # ------------------------------------------------------------------ #
    def _start_decode_last_delay(self) -> None:
        """Start the timer when DECODE_FIRST is picked.
        DECODE_LAST cannot be scheduled until the delay expires."""
        self._decode_last_delay_start_ts = time.monotonic()

    def _can_schedule_decode_last(self) -> bool:
        """Return True if the delay since DECODE_FIRST has elapsed."""
        if self._decode_last_delay_start_ts is None:
            return True
        elapsed_ms = (time.monotonic() - self._decode_last_delay_start_ts) * 1000
        if elapsed_ms >= self._decode_last_delay_schedule_ms:
            self._decode_last_delay_start_ts = None
            return True
        logger.info(
            "[PD] DECODE_LAST delayed: elapsed=%.1f ms < limit=%d ms",
            elapsed_ms, self._decode_last_delay_schedule_ms,
        )
        return False

    def _pick_prefill_first_batch(self) -> SchedulerOutput:
        saved_running = self.running
        saved_chunk_prefill_first = self.chunk_prefill_first
        saved_max_num_running_reqs = self.max_num_running_reqs

        self.running = list(saved_chunk_prefill_first)
        self.chunk_prefill_first = []
        self.max_num_running_reqs -= len(saved_running)

        scheduler_output = None
        try:
            scheduler_output = super().schedule()
        finally:
            self.max_num_running_reqs = saved_max_num_running_reqs

            if scheduler_output is not None:
                if scheduler_output.total_num_scheduled_tokens == 0:
                    scheduler_output.batch_type = BatchType.EMPTY
                    # No request was actually scheduled this round.
                    # self.running currently holds saved_chunk_prefill_first
                    # (requests already scheduled at least once before),
                    # plus any newly-scheduled requests appended by the base
                    # class. Since total_num_scheduled_tokens == 0, the latter
                    # set is empty, so we only restore the former.
                    for req in self.running:
                        if req.is_prefill_chunk:
                            self.chunk_prefill_first.append(req)
                        else:
                            # Prefill finished but not yet moved to running.
                            self.prefill_last_pending.append(req)
                else:
                    scheduler_output.batch_type = BatchType.PREFILL_FIRST
                    scheduler_output.head_token = uuid4().hex
                    scheduler_output.hidden_channel = (
                        self.hidden_channel_manager.allocate_prefill(
                            scheduler_output.head_token
                        )
                    )
                    self.prefill_inflight_count += 1

                    # === 核心修改 ===
                    # All requests scheduled in this PF batch enter
                    # prefill_last_pending immediately. They may NOT be
                    # re-scheduled for the next chunk until the cloud
                    # returns the matching PL (PREFILL_LAST).
                    scheduled_req_ids = set(
                        scheduler_output.num_scheduled_tokens.keys()
                    )
                    # Mark these reqs as having an in-flight tail so that an
                    # abort/finish arriving before PL returns is deferred
                    # (see finish_requests / _flush_completed_deferred_finishes).
                    self._in_flight_tail_req_ids.update(scheduled_req_ids)
                    for req in self.running:
                        if req.request_id in scheduled_req_ids:
                            self.prefill_last_pending.append(req)
                        elif req.is_prefill_chunk:
                            # Not scheduled this round (e.g. token budget
                            # exhausted), keep in chunk_prefill_first.
                            self.chunk_prefill_first.append(req)
                        else:
                            # Completed but not scheduled – defensive.
                            self.prefill_last_pending.append(req)
                    # ================

                self.running = saved_running


            else:
                self.chunk_prefill_first = saved_chunk_prefill_first
                self.running = saved_running

        return scheduler_output  # type: ignore[return-value]

    def _pick_prefill_last_batch(self) -> SchedulerOutput:
        """Pop one cloud-returned SchedulerOutput from prefills_last_ready.

        The cloud has already rewritten ``batch_type=PREFILL_LAST`` and kept
        all original KV / sampling metadata intact, so the edge worker can
        directly run segment_e + sampler on it. We also remove the involved
        requests from ``chunk_prefill_first`` so the parent class's
        ``update_from_output`` does not double-account them.
        """
        if not self.prefills_last_ready:
            return self._make_empty_batch()
        so = self.prefills_last_ready.popleft()
        assert so.batch_type == BatchType.PREFILL_LAST, (
            f"prefills_last_ready expects PREFILL_LAST, got {so.batch_type}"
        )
        # Drop these reqs from chunk_prefill_first. Keep them in
        # prefill_last_pending until update_from_output() moves them to running.
        last_req_ids = set(so.num_scheduled_tokens.keys())
        if last_req_ids:
            self.chunk_prefill_first = [
                req for req in self.chunk_prefill_first
                if req.request_id not in last_req_ids
            ]
        self._validate_prefill_tail_channel(so)
        return so

    def _validate_prefill_tail_channel(self, scheduler_output: SchedulerOutput) -> None:
        token = scheduler_output.head_token
        channel = scheduler_output.hidden_channel
        if not token:
            raise RuntimeError("PREFILL_LAST missing head_token")
        if channel not in (HiddenChannelType.PREFILL_1, HiddenChannelType.PREFILL_2):
            raise RuntimeError(
                f"PREFILL_LAST expects a prefill hidden channel, got {channel}"
            )
        expected = self.hidden_channel_manager.get_channel(token)
        if expected != channel:
            raise RuntimeError(
                f"PREFILL_LAST hidden channel mismatch: expected {expected}, "
                f"got {channel}, head_token={token}"
            )

    def _validate_decode_tail_channel(self, scheduler_output: SchedulerOutput) -> None:
        if scheduler_output.hidden_channel != HiddenChannelType.DECODE:
            raise RuntimeError(
                "DECODE_LAST expects decode hidden channel, got "
                f"{scheduler_output.hidden_channel}"
            )

    def _pick_decode_last_batch(self) -> SchedulerOutput:
        if not self.decodes_last_ready:
            return self._make_empty_batch()
        so = self.decodes_last_ready.popleft()
        assert so.batch_type == BatchType.DECODE_LAST, (
            f"decodes_last_ready expects DECODE_LAST, got {so.batch_type}"
        )
        self._validate_decode_tail_channel(so)
        self._force_decode_last = False
        return so

    def _ensure_cached_all_token_ids(
        self, scheduler_output: SchedulerOutput,
    ) -> None:
        """Ensure every cached decode req carries all_token_ids.

        In PD-separated mode the edge worker's persistent input_batch may not
        retain a request across the PF → PL → DF transitions (the tail segment
        may have been skipped by ``_update_states``), yet the async-scheduling
        model runner requires ``all_token_ids`` to reconstruct
        ``output_token_ids`` for any resumed (req_index is None) request with
        ``num_output_tokens > 0``.

        The base ``_make_cached_request_data`` only fills ``all_token_ids``
        when the request was *not* scheduled in the previous step
        (``prev_step_scheduled_req_ids``).  Because PD separation interleaves
        PF / PL / DF / DL phases — and PL/DL are popped from cloud-returned
        queues without going through ``super().schedule()`` — the scheduler's
        ``prev_step_scheduled_req_ids`` can be stale or misleading, causing
        ``all_token_ids`` to be omitted for requests that the worker actually
        needs it for.

        This helper unconditionally back-fills ``all_token_ids`` for any
        cached request that has output tokens but is missing from the dict.
        The extra payload is cheap (control-plane only) and avoids the
        ``KeyError`` in ``gpu_model_runner._update_states``.
        """
        cached_reqs = scheduler_output.scheduled_cached_reqs
        for req_id, num_output_tokens in zip(
            cached_reqs.req_ids,
            cached_reqs.num_output_tokens,
        ):
            if num_output_tokens > 0 and req_id not in cached_reqs.all_token_ids:
                # Use the Request-level cached np.ndarray to avoid repeated
                # np.asarray() conversion of the Python list (dominant
                # bottleneck on long-sequence decode batches).
                cached_reqs.all_token_ids[req_id] = (
                    self.requests[req_id].cached_all_token_ids_np)

    def _pick_decode_first_batch(self) -> SchedulerOutput:
        if not self.running:
            return self._make_empty_batch()

        saved_chunk_prefill_first = self.chunk_prefill_first
        saved_waiting = self.waiting
        saved_skipped = self.skipped_waiting

        self.chunk_prefill_first = []
        self.waiting = create_request_queue(self.policy)
        self.skipped_waiting = create_request_queue(self.policy)

        scheduler_output = None
        try:
            scheduler_output = super().schedule()
        finally:
            if scheduler_output is not None:
                if scheduler_output.total_num_scheduled_tokens == 0:
                    scheduler_output.batch_type = BatchType.EMPTY
                    logger.debug(
                        "DECODE_FIRST race: empty batch due to async "
                        "update_from_output delay, running=%d",
                        len(self.running),
                    )
                else:
                    scheduler_output.batch_type = BatchType.DECODE_FIRST
                    scheduler_output.head_token = uuid4().hex
                    scheduler_output.hidden_channel = (
                        self.hidden_channel_manager.decode_channel()
                    )
                    self._ensure_cached_all_token_ids(scheduler_output)
                    self.decode_inflight_count += 1
                    self._force_decode_last = True
                    self._start_decode_last_delay()
                    # Mark these reqs as having an in-flight tail (DL) so an
                    # abort/finish arriving before DL returns is deferred
                    # (see finish_requests / _flush_completed_deferred_finishes).
                    self._in_flight_tail_req_ids.update(
                        scheduler_output.num_scheduled_tokens.keys()
                    )
                for req in list(self.waiting):
                    saved_waiting.prepend_request(req)
                self.chunk_prefill_first = saved_chunk_prefill_first
                self.waiting = saved_waiting
                self.skipped_waiting = saved_skipped
            else:
                self.chunk_prefill_first = saved_chunk_prefill_first
                self.waiting = saved_waiting
                self.skipped_waiting = saved_skipped

        return scheduler_output  # type: ignore[return-value]

    def _migrate_prefill_to_running(self) -> None:
        completed = [
            req for req in self.chunk_prefill_first if not req.is_prefill_chunk
        ]
        for req in completed:
            self.chunk_prefill_first.remove(req)
            self.running.append(req)

    def _preempt_request(self, request: Request, timestamp: float) -> None:
        assert request.status == RequestStatus.RUNNING, (
            "Only running requests can be preempted"
        )
        self.kv_cache_manager.free(request)
        self.encoder_cache_manager.free(request)
        request.status = RequestStatus.PREEMPTED
        request.num_preemptions += 1
        if request.spec_token_ids:
            request.spec_token_ids = []
        if self.log_stats:
            request.record_event(EngineCoreEventType.PREEMPTED, timestamp)

        if request.is_prefill_chunk:
            self.chunk_prefill_first.append(request)
        else:
            request.num_computed_tokens = 0
            self.waiting.prepend_request(request)

    def _update_after_schedule(self, scheduler_output: SchedulerOutput) -> None:
        was_prefill_map = {}
        for req_id in scheduler_output.num_scheduled_tokens:
            was_prefill_map[req_id] = self.requests[req_id].is_prefill_chunk

        super()._update_after_schedule(scheduler_output)

        for req_id, num_scheduled_token in scheduler_output.num_scheduled_tokens.items():
            if was_prefill_map[req_id] and num_scheduled_token > 0:
                self.requests[req_id].chunk_num += 1

        self._migrate_prefill_to_running()
        self.finished_req_ids = set()

    def update_from_output(
        self,
        scheduler_output: SchedulerOutput,
        model_runner_output: ModelRunnerOutput,
    ) -> dict[int, Any]:
        if scheduler_output.batch_type == BatchType.PREFILL_LAST:
            if self.prefill_inflight_count > 0:
                self.prefill_inflight_count -= 1
            if scheduler_output.head_token:
                self.hidden_channel_manager.release_prefill(
                    scheduler_output.head_token
                )
            # === 核心修改 ===
            # Requests whose PL just returned are removed from
            # prefill_last_pending and routed directly:
            #   - still has more chunks -> chunk_prefill_first
            #   - prefill fully done    -> running
            completed_req_ids = set(scheduler_output.num_scheduled_tokens.keys())
            # The tail segment for these reqs has now executed on the worker,
            # so they are no longer in flight.  Deferred aborts/finishes for
            # any of them are completed below (see
            # _flush_completed_deferred_finishes) before super().update_from_output
            # runs, so the worker no longer needs them in self.requests.
            self._in_flight_tail_req_ids -= completed_req_ids
            newly_running: list[Request] = []
            newly_chunked: list[Request] = []
            remaining_pending: list[Request] = []
            for req in self.prefill_last_pending:
                if req.request_id in completed_req_ids:
                    if req.is_prefill_chunk:
                        self.chunk_prefill_first.append(req)
                        newly_chunked.append(req)
                    else:
                        self.running.append(req)
                        newly_running.append(req)
                else:
                    remaining_pending.append(req)
            self.prefill_last_pending = remaining_pending
            # ================

            logger.info(
                f"[PD] update_from_output PREFILL_LAST done, "
                f"prefill_inflight: {self.prefill_inflight_count}/{self.prefill_inflight_limit}, "
                f"moved {len(newly_running)} reqs to running[], "
                f"moved {len(newly_chunked)} reqs to chunk_prefill_first[], "
                f"running[]: {len(self.running)}, "
                f"chunk_prefill_first[]: {len(self.chunk_prefill_first)}",
            )
        if scheduler_output.batch_type == BatchType.DECODE_FIRST:
            # D首完成后立即释放 inflight 计数，使下一个 D首可以
            # 在 D尾仍在 batch_queue 中时就被调度，消除 Cloud idle gap。
            if self.decode_inflight_count > 0:
                self.decode_inflight_count -= 1
            logger.info(
                f"[PD] update_from_output DECODE_FIRST done, "
                f"decode_inflight: {self.decode_inflight_count}/{self.decode_inflight_limit}",
            )
        if scheduler_output.batch_type == BatchType.DECODE_LAST:
            # decode_inflight_count 已在 DECODE_FIRST 的 update_from_output
            # 中释放，此处不再重复减 1。
            # The tail segment (DL) for these reqs has now executed on the
            # worker, so they are no longer in flight.  Deferred aborts/
            # finishes for any of them are completed below.
            self._in_flight_tail_req_ids -= set(
                scheduler_output.num_scheduled_tokens.keys()
            )
            logger.info(
                f"[PD] update_from_output DECODE_LAST done, "
                f"decode_inflight: {self.decode_inflight_count}/{self.decode_inflight_limit}",
            )
        # Complete any deferred finishes whose tail segment has now returned.
        # This must run before super().update_from_output so that aborted reqs
        # are already finished (and thus skipped by the parent loop) instead of
        # having their sampled token appended.  It also releases KV blocks and
        # delivers finished_req_ids to the worker for the next batch.
        self._flush_completed_deferred_finishes()
        outputs = super().update_from_output(scheduler_output, model_runner_output)
        self.chunk_prefill_first = [
            req for req in self.chunk_prefill_first if not req.is_finished()
        ]
        self.prefill_last_pending = [
            req for req in self.prefill_last_pending if not req.is_finished()
        ]
        return outputs

    def get_request_counts(self) -> tuple[int, int]:
        num_running, num_waiting = super().get_request_counts()
        return (
            num_running
            + len(self.chunk_prefill_first)
            + len(self.prefill_last_pending),
            num_waiting,
        )

    def get_num_unfinished_requests(self) -> int:
        if self._pause_state == PauseState.PAUSED_ALL:
            return 0
        return (
            super().get_num_unfinished_requests()
            + len(self.chunk_prefill_first)
            + len(self.prefill_last_pending)
            # Deferred finishes still hold KV blocks + a worker self.requests
            # entry until their in-flight tail returns, so they count as
            # unfinished work for the engine loop.
            + len(self._deferred_finish)
        )

    def finish_requests(
        self, request_ids: str | Iterable[str] | None, finished_status: RequestStatus
    ) -> list[tuple[str, int]]:
        result = super().finish_requests(request_ids, finished_status)
        if isinstance(request_ids, str):
            request_ids = (request_ids,)
        elif request_ids is not None:
            request_ids = set(request_ids)
        else:
            request_ids = self.requests.keys()

        # Finish-all (e.g. shutdown): the in-flight tails will not return, so
        # force-complete deferred finishes and clear the in-flight tracking.
        if request_ids is None:
            if self._deferred_finish:
                logger.warning(
                    "PD scheduler shutdown with %d deferred-finish reqs "
                    "whose tails never returned (cloud failure?); "
                    "force-finishing them: %s",
                    len(self._deferred_finish),
                    sorted(self._deferred_finish.keys()),
                )
            result = super().finish_requests(None, finished_status)
            self._deferred_finish.clear()
            self._in_flight_tail_req_ids.clear()
            return result

        if isinstance(request_ids, str):
            norm: set[str] = {request_ids}
        else:
            norm = set(request_ids)

        # Split: reqs whose tail is still in flight must be deferred (the
        # cloud already committed hidden tensors for them); the rest finish
        # immediately via the parent.
        defer_ids = {r for r in norm if r in self._in_flight_tail_req_ids}
        finish_now_ids = norm - defer_ids

        result: list[tuple[str, int]] = []
        if finish_now_ids:
            result = super().finish_requests(finish_now_ids, finished_status)

        for req_id in defer_ids:
            # Already deferred by an earlier abort: keep the first status and
            # do not append to the result twice.
            if req_id in self._deferred_finish:
                continue
            req = self.requests.get(req_id)
            if req is None or req.is_finished():
                continue
            # Remove from all scheduling queues so the aborted req is not
            # re-scheduled (e.g. picked into another DF/PF), but KEEP its KV
            # blocks and self.requests entry: the in-flight tail segment still
            # needs them for data-plane-aligned attention/sampling.  The
            # status is intentionally left as-is (RUNNING) so the deferred
            # finish can be completed later via super().finish_requests (which
            # skips already-finished reqs).  The real finish (block free +
            # finished_req_ids delivery) happens in
            # _flush_completed_deferred_finishes once the tail returns.
            self.running = remove_all(self.running, {req})
            self.chunk_prefill_first = remove_all(self.chunk_prefill_first, {req})
            if req in self.prefill_last_pending:
                self.prefill_last_pending = [
                    r for r in self.prefill_last_pending if r is not req
                ]
            self._deferred_finish[req_id] = finished_status
            result.append((req_id, req.client_index))
            logger.info(
                "[PD] Deferring finish (%s) for req %s: tail segment still "
                "in flight on cloud; will complete once PL/DL returns.",
                finished_status.name, req_id,
            )

        # Preserve existing cleanup: drop delay-free finished reqs from
        # chunk_prefill_first (parent only clears running/waiting).
        to_remove = set()
        for req_id in finish_now_ids:
            req = self.requests.get(req_id)
            if req and req.is_finished():
                to_remove.add(req)
        if to_remove:
            self.chunk_prefill_first = remove_all(
                self.chunk_prefill_first, to_remove
            )

        return result

    def _flush_completed_deferred_finishes(self) -> None:
        """Complete deferred aborts/finishes whose tail segment has returned.

        Called from ``update_from_output`` after the PL/DL branch has removed
        the just-completed req ids from ``_in_flight_tail_req_ids``.  By now
        the tail has executed on the worker, so it is safe to release KV
        blocks and deliver ``finished_req_ids`` to the worker (the req is no
        longer needed for data-plane alignment).  Must run before
        ``super().update_from_output`` so aborted reqs are skipped there.
        """
        if not self._deferred_finish:
            return
        to_flush = [
            (r, s) for r, s in self._deferred_finish.items()
            if r not in self._in_flight_tail_req_ids
        ]
        if not to_flush:
            return
        # Group by finished_status: super().finish_requests takes one status.
        by_status: dict[RequestStatus, set[str]] = {}
        for req_id, status in to_flush:
            self._deferred_finish.pop(req_id, None)
            by_status.setdefault(status, set()).add(req_id)
        for status, ids in by_status.items():
            logger.info(
                "[PD] Completing deferred finish (%s) for %d req(s) whose "
                "tail just returned: %s",
                status.name, len(ids), sorted(ids),
            )
            super().finish_requests(ids, status)

    def reset_prefix_cache(
        self, reset_running_requests: bool = False, reset_connector: bool = False
    ) -> bool:
        if reset_running_requests:
            timestamp = time.monotonic()
            while self.chunk_prefill_first:
                request = self.chunk_prefill_first.pop()
                self.kv_cache_manager.free(request)
                self.encoder_cache_manager.free(request)
                request.status = RequestStatus.PREEMPTED
                request.num_computed_tokens = 0
                if request.spec_token_ids:
                    request.spec_token_ids = []
                request.num_preemptions += 1
                if self.log_stats:
                    request.record_event(EngineCoreEventType.PREEMPTED, timestamp)
                request.num_output_placeholders = 0
                request.discard_latest_async_tokens = True
                self.waiting.prepend_request(request)

        return super().reset_prefix_cache(reset_running_requests, reset_connector)

    def make_stats(self, *args, **kwargs):
        stats = super().make_stats(*args, **kwargs)
        if stats is not None:
            stats.num_running_reqs += len(self.chunk_prefill_first)
            # Deferred-finish reqs still occupy KV blocks until their
            # in-flight tail returns; count them as running for stats.
            stats.num_running_reqs += len(self._deferred_finish)
        return stats

    def _handle_invalid_blocks(self, invalid_block_ids: set[int]) -> set[str]:
        saved_running = self.running
        self.running = list(self.running) + [
            r for r in self.chunk_prefill_first if r not in self.running
        ]
        try:
            result = super()._handle_invalid_blocks(invalid_block_ids)
        finally:
            self.running = saved_running
        return result


class AsyncPDSeparatedScheduler(AsyncScheduler, PDSeparatedScheduler):
    """Async scheduler with PD separation."""
    pass
