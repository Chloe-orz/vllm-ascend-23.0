# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""LwdCloudSampleCollector: cloud-side unified collection point for the c2e
packet's three data items.

Per the v2.3 design:
  * ONE collection call site per decode step (``collect_batch`` at the
    tail of the runner's sample path); scatter points (execute_model /
    sampler sidecar / num_accepted buffer) only expose, never store.
  * NO per-step accumulation: every request owns a single slot that is
    overwritten each step — only the LAST decode step survives.
    Memory = max_num_seqs x (k+1) x (H+3K) x 2B, capped regardless of
    output length.
  * ``finalize`` is idempotent and triggered by the worker execution
    layer on ``SchedulerOutput.finished_req_ids`` (the finish decision
    is only known to the engine AFTER sampling), NOT inside
    sample_tokens itself.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import torch
from vllm.logger import logger

from vllm_ascend.worker.lwd_down_packet import pack_lwd_down_packet


@dataclass
class _Slot:
    capacity_rows: int
    hidden: torch.Tensor       # [cap, H] bf16
    topk_ids: torch.Tensor     # [cap, K] int32
    topk_logits: torch.Tensor  # [cap, K] bf16
    num_prompt_tokens: int = 0
    rows: int = 0
    # [1] int32 on device; D2H happens once at finalize (never per step).
    num_accepted_t: torch.Tensor | None = None
    finalized: bool = False


class LwdCloudSampleCollector:
    """Per-request single-slot collector (cloud side, TP rank 0 only).

    Thread model: called from the runner's sample path (engine thread
    context); no cross-thread access — a lock is kept anyway for the
    abort/drop path which may be driven by a comm thread.
    """

    def __init__(self, hidden_size: int, topk_k: int, device: str = "npu"):
        self._hidden_size = hidden_size
        self._topk_k = topk_k
        self._device = device
        self._slots: dict[str, _Slot] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    def open_request(
        self,
        req_id: str,
        num_prompt_tokens: int,
        rows_capacity: int = 1,
    ) -> None:
        """Create the request's slot at admission.  rows_capacity =
        num_speculative_tokens + 1 (1 when spec is off)."""
        with self._lock:
            if req_id in self._slots:
                return
            self._slots[req_id] = _Slot(
                capacity_rows=rows_capacity,
                hidden=torch.zeros(
                    rows_capacity, self._hidden_size,
                    dtype=torch.bfloat16, device=self._device,
                ),
                topk_ids=torch.zeros(
                    rows_capacity, self._topk_k,
                    dtype=torch.int32, device=self._device,
                ),
                topk_logits=torch.zeros(
                    rows_capacity, self._topk_k,
                    dtype=torch.bfloat16, device=self._device,
                ),
                num_prompt_tokens=num_prompt_tokens,
                num_accepted_t=torch.zeros(
                    1, dtype=torch.int32, device=self._device
                ),
            )

    def drop(self, req_id: str) -> None:
        """Destroy the slot (abort / after send)."""
        with self._lock:
            self._slots.pop(req_id, None)

    # ------------------------------------------------------------------ #
    # Collection (overwrite-in-place; only the last step survives)        #
    # ------------------------------------------------------------------ #

    def collect_batch(
        self,
        req_ids: list[str],
        *,
        hidden_rows: torch.Tensor,      # [B, H] bf16 (non-spec; one row per req)
        cand_ids: torch.Tensor,         # [B, K] int32
        cand_logits: torch.Tensor,      # [B, K] bf16
        num_accepted: torch.Tensor | None,  # [B] int32; None -> non-spec (0)
    ) -> None:
        """Record this decode step for every scheduled request.

        Rows follow the batch order (input_batch row order == req_ids).
        Non-spec: one row per request, num_accepted = 0 (invariant
        rows == num_accepted + 1).  Spec/MTP reshape is a P3 item; the
        wire format already supports R > 1.
        """
        if not req_ids:
            return
        B = len(req_ids)
        assert hidden_rows.shape[0] == B, (hidden_rows.shape, B)
        # Normalize the candidate width to the fixed wire width K: the
        # sampler sidecar's width is dynamic per batch (request top_k, or
        # full vocab when unset).  Narrower -> zero-pad; wider -> truncate
        # (requests with top_k > K are rejected at admission).
        K = self._topk_k
        if cand_ids.shape[1] != K:
            w = min(cand_ids.shape[1], K)
            padded_ids = torch.zeros(B, K, dtype=torch.int32,
                                     device=cand_ids.device)
            padded_ids[:, :w] = cand_ids[:, :w].to(torch.int32)
            padded_logits = torch.zeros(B, K, dtype=torch.bfloat16,
                                        device=cand_logits.device)
            padded_logits[:, :w] = cand_logits[:, :w].to(torch.bfloat16)
            cand_ids, cand_logits = padded_ids, padded_logits
        with self._lock:
            for i, req_id in enumerate(req_ids):
                slot = self._slots.get(req_id)
                if slot is None or slot.finalized:
                    continue
                assert slot.capacity_rows >= 1
                slot.hidden[0].copy_(hidden_rows[i])
                slot.topk_ids[0].copy_(cand_ids[i])
                slot.topk_logits[0].copy_(cand_logits[i])
                slot.rows = 1
                if num_accepted is not None:
                    slot.num_accepted_t.copy_(num_accepted[i])
                else:
                    slot.num_accepted_t.zero_()

    # ------------------------------------------------------------------ #
    # Finalize (idempotent; triggered by finished_req_ids)                #
    # ------------------------------------------------------------------ #

    def finalize(self, req_id: str) -> torch.Tensor | None:
        """Pack the request's slot into the flat wire tensor.

        Returns None when the request is unknown or already finalized —
        together with ``drop`` after send this is the duplicate-send
        guard (a second entry for the same request falls through)."""
        with self._lock:
            slot = self._slots.get(req_id)
            if slot is None or slot.finalized or slot.rows == 0:
                return None
            slot.finalized = True
            num_accepted = int(slot.num_accepted_t.item())  # one D2H per request
            packed = pack_lwd_down_packet(
                hidden=slot.hidden[: slot.rows],
                topk_ids=slot.topk_ids[: slot.rows],
                topk_logits=slot.topk_logits[: slot.rows],
                num_prompt_tokens=slot.num_prompt_tokens,
                num_accepted=num_accepted,
                request_id=req_id,
            )
        logger.debug(
            "[lwd-collector] finalized req=%s rows=%d accepted=%d",
            req_id, slot.rows, num_accepted,
        )
        return packed

    def num_live_slots(self) -> int:
        with self._lock:
            return len(self._slots)
