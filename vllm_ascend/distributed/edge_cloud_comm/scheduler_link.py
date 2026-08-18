# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""Scheduler-process glue for decoupled data-plane recv scheduling.

This module is the scheduler-process half of the early-recv design:

* ``post_irecv_hint(hint)`` — forward a recv request to the *local*
  worker's comm thread.  The actual transport (a dedicated hint MQ whose
  handle lives in the executor) is injected at engine-core init time via
  ``register_hint_sender`` so this module stays import-light and free of
  process-global executor state.
* ``is_irecv_complete(channel, seqno)`` — per-channel watermark query.
  The worker's comm thread reports every completed recv as
  ``(channel, seqno)`` over the reverse MQ; the engine core drains it
  once per step and calls ``record_irecv_completions``.  Per-channel
  completion is FIFO in-order (``CommChannel.reap``: if the head is not
  done, nothing behind it is), so the completed set is always a prefix
  and a single max watermark represents it exactly.

Hint schema (produced by edge EngineCore / cloud PassiveEC, consumed by
the worker comm thread -> ``NPUWorker.start_early_irecv``)::

    {
        "batch_type": BatchType,        # FIRST = UP head payload,
                                        # LAST = DOWN tail payload
        "draft_prefill_phase": bool,    # draft channel-pair selection
        "seqno": int,                   # per-channel sequence number,
                                        # stamped by the edge scheduler
        "num_tokens": int,              # dim-0 of the payload
        "has_mrope": bool,              # include mrope_positions
        "draft_step_idx": int | None,   # draft step index (draft batches
                                        # only; drives the draft wire-meta
                                        # derivation on the worker)
    }

Watermark semantics: ``is_irecv_complete(channel, seqno)`` is exactly
``seqno <= watermark[channel]``.  It is a readiness predicate only — it
never participates in task prioritization.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable

from vllm_ascend.distributed.edge_cloud_comm.types import CommChannelType

_hint_sender: Callable[[dict], None] | None = None
_gating_enabled: bool = True
_watermarks: dict[CommChannelType, int] = {}
_lock = threading.Lock()


def register_hint_sender(sender: Callable[[dict], None]) -> None:
    """Install the transport used by ``post_irecv_hint``.

    Called once per engine-core process (edge EngineCore patch / cloud
    PassiveEngineCoreProc) with a closure that reliably enqueues the hint
    onto the local hint MQ.  Blocking delivery is required: with
    readiness gating active, a lost hint means the recv is never posted,
    the watermark never advances, and the tail is never dispatched.
    """
    global _hint_sender
    _hint_sender = sender


def post_irecv_hint(hint: dict) -> None:
    """Send one recv hint to the local worker's comm thread."""
    if _hint_sender is None:
        raise RuntimeError(
            "post_irecv_hint called before register_hint_sender: the "
            "engine-core patch must install the hint transport at init."
        )
    _hint_sender(hint)


def set_readiness_gating_enabled(enabled: bool) -> None:
    """Disable readiness gating on topologies without hint/feedback
    infrastructure (e.g. shared-model single-NPU edge, which is not
    covered this period).  When disabled, ``is_irecv_complete`` is
    always True."""
    global _gating_enabled
    _gating_enabled = enabled


def record_irecv_completions(
    items: Iterable[tuple[CommChannelType, int]],
) -> None:
    """Advance per-channel watermarks from drained completion reports."""
    with _lock:
        for channel, seqno in items:
            if seqno > _watermarks.get(channel, -1):
                _watermarks[channel] = seqno


def is_irecv_complete(channel: CommChannelType, seqno: int) -> bool:
    """True once the recv stamped ``seqno`` on ``channel`` has completed."""
    if not _gating_enabled:
        return True
    with _lock:
        return seqno <= _watermarks.get(channel, -1)
