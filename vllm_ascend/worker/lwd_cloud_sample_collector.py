# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""LwdCloudSampleCollector: cloud-side per-step packet builder for the
DOWN stream (streaming mode, v2.5).

Semantics changed from the v2.2 single-slot collector: there is NO
accumulation at all — after prefill and after EVERY decode step, the
step's three data items (final hidden rows / topk candidates /
num_accepted) are packed into one fixed-size wire packet per request
and returned to the caller for immediate sending.  The only per-request
state kept is ``num_prompt_tokens`` (packet header) and open/closed
bookkeeping.

Every request's DOWN stream is a sequence of fixed-size step packets;
request finish/abort is signaled by the control plane (no FIN packet,
removed in v2.6 as redundant with per-packet notification).
"""

from __future__ import annotations

import threading

import torch
from vllm.logger import logger

from vllm_ascend.worker.lwd_down_packet import (
    lwd_down_wire_num_elements,
    pack_lwd_down_packet,
)


class LwdCloudSampleCollector:
    """Per-step packet builder (cloud side, wire endpoint rank only
    sends; other TP ranks may call build for parity but never send).

    Thread model: called from the runner's sample path; a lock guards
    the bookkeeping maps for the abort/drop path.
    """

    def __init__(
        self,
        hidden_size: int,
        topk_k: int,
        max_rows: int = 1,
        device: str = "npu",
    ) -> None:
        self._device = device
        self._hidden_size = hidden_size
        self._topk_k = topk_k
        self._max_rows = max_rows
        # Fixed on-the-wire size: every DOWN packet (data or FIN) has
        # exactly this many bf16 elements, so the edge can pre-post a
        # recv ring without per-step size knowledge.
        self._wire_num_elements = lwd_down_wire_num_elements(
            hidden_size, topk_k, max_rows
        )
        self._prompt_tokens: dict[str, int] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    def open_request(self, req_id: str, num_prompt_tokens: int) -> None:
        with self._lock:
            self._prompt_tokens.setdefault(req_id, num_prompt_tokens)

    def drop(self, req_id: str) -> None:
        with self._lock:
            self._prompt_tokens.pop(req_id, None)

    def num_live_requests(self) -> int:
        with self._lock:
            return len(self._prompt_tokens)

    # ------------------------------------------------------------------ #
    # Per-step packing                                                    #
    # ------------------------------------------------------------------ #

    def build_step_packets(
        self,
        req_ids: list[str],
        *,
        hidden_rows: torch.Tensor,          # [B, H] bf16
        cand_ids: torch.Tensor,             # [B, W] int32/int64
        cand_logits: torch.Tensor,          # [B, W]
        num_accepted: torch.Tensor | None,  # [B] int32; None -> 0
    ) -> dict[str, torch.Tensor]:
        """Pack this step's data for every request (streaming: one packet
        per request per step, sent immediately by the caller).

        The candidate width W is dynamic per batch (request top_k, or
        ~vocab when unset) and is normalized to the fixed wire width K
        (narrow -> zero-pad, wider -> truncate; top_k > K requests are
        rejected at admission).
        """
        packets: dict[str, torch.Tensor] = {}
        if not req_ids:
            return packets
        B = len(req_ids)
        assert hidden_rows.shape[0] == B, (hidden_rows.shape, B)
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
        else:
            cand_ids = cand_ids.to(torch.int32)
            cand_logits = cand_logits.to(torch.bfloat16)
        with self._lock:
            prompt_tokens = [self._prompt_tokens.get(r, 0) for r in req_ids]
        for i, req_id in enumerate(req_ids):
            accepted = 0
            if num_accepted is not None:
                # NOTE: per-request D2H here is acceptable in the spec
                # path (P3); the non-spec default passes None (no sync).
                accepted = int(num_accepted[i])
            packets[req_id] = pack_lwd_down_packet(
                hidden=hidden_rows[i : i + 1],
                topk_ids=cand_ids[i : i + 1],
                topk_logits=cand_logits[i : i + 1],
                num_prompt_tokens=prompt_tokens[i],
                num_accepted=accepted,
                request_id=req_id,
                wire_num_elements=self._wire_num_elements,
            )
        return packets

    @property
    def wire_num_elements(self) -> int:
        return self._wire_num_elements
