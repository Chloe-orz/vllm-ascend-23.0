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
        # Normalize the candidate width to the fixed wire width K.
        #
        # The sampler sidecar's width is dynamic per batch (request top_k,
        # or the full local vocab when unset) and, with TP>1, is the
        # PER-RANK-concatenation of each rank's local top-k — globally
        # unsorted.  Blindly truncating the first K entries would ship
        # rank-0-local candidates, not the global top-K, so reduce by
        # logit first: a top-K over the (logit, id) pairs is correct for
        # any layout of the sidecar.
        #
        # Invalid candidates (masked by top-k/top-p as -inf, or absent
        # when the sidecar is narrower than K) are represented as
        # logit=-inf; the edge MUST ignore -inf-logit entries (wire
        # contract, see lwd_down_packet).  Zero-padding logits would be
        # indistinguishable from a real candidate for token id 0.
        K = self._topk_k
        W = cand_ids.shape[1]
        if W >= K:
            top = torch.topk(cand_logits.float(), k=K, dim=1)
            cand_logits = top.values.to(torch.bfloat16)
            cand_ids = cand_ids.gather(1, top.indices).to(torch.int32)
        else:
            pad_ids = torch.zeros(B, K - W, dtype=torch.int32,
                                  device=cand_ids.device)
            pad_logits = torch.full((B, K - W), float("-inf"),
                                    dtype=torch.bfloat16,
                                    device=cand_logits.device)
            cand_ids = torch.cat([cand_ids.to(torch.int32), pad_ids], dim=1)
            cand_logits = torch.cat(
                [cand_logits.to(torch.bfloat16), pad_logits], dim=1)
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

    def num_live_slots(self) -> int:
        """Number of open (registered, not yet dropped) requests — the
        fast-path gate for the per-step collection point."""
        return self.num_live_requests()

    def has_slot(self, req_id: str) -> bool:
        """Whether the request is currently registered — used by the
        collection point to skip unregistered traffic."""
        with self._lock:
            return req_id in self._prompt_tokens

    @property
    def wire_num_elements(self) -> int:
        return self._wire_num_elements
