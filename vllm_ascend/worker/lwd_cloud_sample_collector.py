# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""LwdCloudSampleCollector: cloud-side per-step batch-packet builder for
the DOWN stream (v3: rank replay, per-step batching).

There is NO accumulation at all — after prefill and after EVERY decode
step, the step's data (final hidden rows / sampled ranks / per-request
accepted) for ALL live LWD requests of the batch is packed into ONE
wire packet and returned to the caller for immediate sending.  The only
per-request state kept is the registration bookkeeping itself (which
requests are LWD, for the collection point's filter).

Every cloud step produces at most one DOWN packet; request finish/abort
is signaled by the control plane (no FIN packet).
"""

from __future__ import annotations

import threading

import torch

from vllm_ascend.worker.lwd_down_packet import pack_lwd_down_batch_packet


class LwdCloudSampleCollector:
    """Per-step batch packet builder (cloud side, wire endpoint rank
    only sends; other TP ranks never build).

    Thread model: called from the runner's sample path; a lock guards
    the bookkeeping maps for the abort/drop path.
    """

    def __init__(self) -> None:
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

    def build_batch_packet(
        self,
        entries: list[tuple[str, torch.Tensor, torch.Tensor, int]],
    ) -> torch.Tensor | None:
        """Pack one step's data for the batch's live LWD requests.

        ``entries``: ``(req_id, hidden [R_i, H], ranks [R_i], accepted)``
        in batch order — one row per request for non-spec, accepted+1
        rows for spec verify steps.  Unregistered entries are dropped
        (defense in depth; the runner already filters).  Returns None
        when nothing live remains.
        """
        live = [e for e in entries if self.has_slot(e[0])]
        if not live:
            return None
        return pack_lwd_down_batch_packet(entries=live)

    def num_live_slots(self) -> int:
        """Number of open (registered, not yet dropped) requests — the
        fast-path gate for the per-step collection point."""
        return self.num_live_requests()

    def has_slot(self, req_id: str) -> bool:
        """Whether the request is currently registered — used by the
        collection point to skip unregistered traffic."""
        with self._lock:
            return req_id in self._prompt_tokens
