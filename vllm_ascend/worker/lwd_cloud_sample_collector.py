# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""LwdCloudSampleCollector: cloud-side per-step packet builder for the
DOWN stream (streaming mode, v2 rank-replay).

There is NO accumulation at all — after prefill and after EVERY decode
step, the step's data items (final hidden rows / sampled ranks /
num_accepted) are packed into one fixed-size wire packet per request
and returned to the caller for immediate sending.  The only per-request
state kept is ``num_prompt_tokens`` (packet header) and open/closed
bookkeeping.

Every request's DOWN stream is a sequence of fixed-size step packets;
request finish/abort is signaled by the control plane (no FIN packet).
"""

from __future__ import annotations

import threading

import torch

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
        max_rows: int = 1,
        device: str = "npu",
    ) -> None:
        self._device = device
        self._hidden_size = hidden_size
        self._max_rows = max_rows
        # Fixed on-the-wire size: every DOWN packet has exactly this many
        # bf16 elements, so the edge can pre-post a recv ring without
        # per-step size knowledge.
        self._wire_num_elements = lwd_down_wire_num_elements(
            hidden_size, max_rows
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
        ranks: torch.Tensor,                # [B] int32/int64
        num_accepted: torch.Tensor | None = None,  # [B] int32; None -> 0
    ) -> dict[str, torch.Tensor]:
        """Pack this step's data for every request (streaming: one packet
        per request per step, sent immediately by the caller).

        Non-spec fast path: exactly one row per request.  Spec/MTP verify
        steps use ``build_step_packet`` (variable R = accepted+1 rows).
        """
        packets: dict[str, torch.Tensor] = {}
        if not req_ids:
            return packets
        B = len(req_ids)
        assert hidden_rows.shape[0] == B, (hidden_rows.shape, B)
        assert ranks.shape[0] == B
        ranks = ranks.to(torch.int32)
        with self._lock:
            prompt_tokens = [self._prompt_tokens.get(r, 0) for r in req_ids]
        for i, req_id in enumerate(req_ids):
            accepted = 0
            if num_accepted is not None:
                # NOTE: per-request D2H here is acceptable in the spec
                # path; the non-spec default passes None (no sync).
                accepted = int(num_accepted[i])
            packets[req_id] = self._pack_one(
                req_id,
                hidden=hidden_rows[i : i + 1],
                ranks=ranks[i : i + 1],
                num_accepted=accepted,
                prompt_tokens=prompt_tokens[i],
            )
        return packets

    def build_step_packet(
        self,
        req_id: str,
        *,
        hidden: torch.Tensor,        # [R, H], R = accepted+1 (spec verify)
        ranks: torch.Tensor,         # [R] int32/int64
        num_accepted: int,
    ) -> torch.Tensor | None:
        """Single-request packet with variable row count (spec/MTP verify
        steps).  Returns None for unregistered requests."""
        R = hidden.shape[0]
        if R < 1 or R > self._max_rows:
            raise ValueError(
                f"row count {R} out of [1, {self._max_rows}] for {req_id!r}"
            )
        assert ranks.shape[0] == R
        with self._lock:
            prompt_tokens = self._prompt_tokens.get(req_id)
        if prompt_tokens is None:
            return None
        return self._pack_one(
            req_id,
            hidden=hidden,
            ranks=ranks.to(torch.int32),
            num_accepted=num_accepted,
            prompt_tokens=prompt_tokens,
        )

    # ------------------------------------------------------------------ #
    # Internal                                                            #
    # ------------------------------------------------------------------ #

    def _pack_one(
        self,
        req_id: str,
        *,
        hidden: torch.Tensor,
        ranks: torch.Tensor,
        num_accepted: int,
        prompt_tokens: int,
    ) -> torch.Tensor:
        return pack_lwd_down_packet(
            hidden=hidden,
            ranks=ranks,
            num_prompt_tokens=prompt_tokens,
            num_accepted=num_accepted,
            request_id=req_id,
            wire_num_elements=self._wire_num_elements,
        )

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
