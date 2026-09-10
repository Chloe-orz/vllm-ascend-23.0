# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""prefill_only LWD model runner subclass (cloud side).

All LWD runner-side logic lives here (moved out of
``model_runner_v1.py``): the per-step cloud-side collection of the
DOWN payload (hidden-only tensor) plus the step metadata (global ranks
/ num_accepted / req_ids) that rides back to the scheduler on
``ModelRunnerOutput.lwd_c2e_meta``.

Selected via ``LwdCloudWorker`` (worker_cls), which swaps the model
runner class at init_device when ``lwd_config`` enables prefill_only.
"""

from __future__ import annotations

import torch
from vllm.distributed.parallel_state import get_tp_group
from vllm.logger import logger
from vllm.v1.outputs import ModelRunnerOutput

from vllm_ascend.utils import lmhead_tp_enable
from vllm_ascend.worker.model_runner_v1 import NPUModelRunner


class LwdCloudModelRunner(NPUModelRunner):
    """NPUModelRunner + prefill_only LWD cloud-side runner logic."""

    def __init__(self, vllm_config, device, worker=None):
        super().__init__(vllm_config, device)
        self.worker = worker  # LwdCloudWorker ref (UP recv futures live there)
        # prefill_only LWD data plane (cloud side): per-step payload
        # builder for the DOWN stream, plus the two pending slots the
        # worker layer drains.
        self.lwd_cloud_collector = None
        self._lwd_pending_down_packet = None
        self._lwd_pending_c2e_meta = None
        self._lwd_captured_sampler_output = None
        # This runner class is only instantiated on the cloud side
        # (see platform worker_cls selection); no role check needed.
        from vllm_ascend.worker.lwd_cloud.lwd_cloud_sample_collector import (
            LwdCloudSampleCollector,
        )

        # Only TP rank 0 talks to the wire; skip collector creation on
        # the other ranks (their packets would never be sent).
        if get_tp_group().is_first_rank:
            self.lwd_cloud_collector = LwdCloudSampleCollector()

    # ------------------------------------------------------------------ #
    # Remote embeds injection (cloud input has NO token ids — the prompt   #
    # embeddings arrive over the UP channel and must drive forward)        #
    # ------------------------------------------------------------------ #

    def _prepare_inputs(self, scheduler_output, num_scheduled_tokens):
        """Inject the edge-computed prompt embeddings into the native
        prompt-embeds machinery BEFORE the base fill loop runs.

        The cloud receives no token ids for LWD requests: their whole
        prompt arrives as embeddings over the UP channel.  Here we wait
        for and place them into ``input_batch.req_prompt_embeds`` with
        the ``is_token_ids`` mask cleared, so the base runner's native
        fill loop (per-request ``num_computed_tokens`` offsets) feeds
        them to forward as ``inputs_embeds`` — chunked prefill included.
        """
        if self._lwd_enabled():
            self._lwd_inject_remote_embeds()
        return super()._prepare_inputs(scheduler_output, num_scheduled_tokens)

    def _lwd_enabled(self) -> bool:
        cfg = getattr(self.vllm_config, "lwd_config", None)
        return bool(cfg is not None and cfg.enabled)

    def _lwd_inject_remote_embeds(self) -> None:
        worker = self.worker
        if worker is None:
            return
        posted = getattr(worker, "_lwd_up_recv_futures", None)
        if not posted:
            return
        for batch_seqno in list(posted.keys()):
            embeds, meta = worker.take_lwd_up_embeds(batch_seqno)
            if embeds is None:
                continue
            # Split the concatenated batch rows back per request
            # (rows follow batch_meta order).
            row = 0
            for req_id, token_ids in zip(meta.req_ids, meta.token_ids):
                n = len(token_ids)
                idx = self.input_batch.req_id_to_index.get(req_id)
                if idx is not None and n > 0:
                    self.input_batch.req_prompt_embeds[idx] = embeds[row: row + n]
                    self.input_batch.is_token_ids[idx, :n] = False
                row += n

    def _sample(self, logits, spec_decode_metadata):
        """Capture the sampler output for the post-sample collection
        (the base sample_tokens clears execute_model_state on return)."""
        sampler_output = super()._sample(logits, spec_decode_metadata)
        self._lwd_captured_sampler_output = sampler_output
        return sampler_output

    @torch.inference_mode()
    def sample_tokens(self, grammar_output) -> ModelRunnerOutput:
        captured = None
        if self.lwd_cloud_collector is not None and \
                self.execute_model_state is not None:
            # ExecuteModelState layout (see model_runner_v1.sample_tokens):
            # (scheduler_output, logits, spec_decode_metadata,
            #  spec_decode_common_attn_metadata, hidden_states,
            #  sample_hidden_states, ...)
            state = self.execute_model_state
            captured = (
                state[0],   # scheduler_output
                state[5],   # sample_hidden_states
                state[1],   # logits
                state[2],   # spec_decode_metadata
            )
        self._lwd_captured_sampler_output = None
        output = super().sample_tokens(grammar_output)
        if captured is not None and self._lwd_captured_sampler_output is not None:
            self._lwd_cloud_collect_step(
                captured[0], captured[1], captured[2], captured[3],
                self._lwd_captured_sampler_output,
            )
        return output

    # ------------------------------------------------------------------ #
    # Collection (cloud)                                                  #
    # ------------------------------------------------------------------ #

    def _lwd_cloud_collect_step(
        self,
        scheduler_output,
        sample_hidden_states: torch.Tensor,
        logits: torch.Tensor | None,
        spec_decode_metadata,
        sampler_output,
    ) -> None:
        """Streaming collect (cloud): after prefill and after EVERY decode
        step, pack this step's data for ALL live LWD requests of the batch
        into one hidden-only DOWN payload + one metadata record.

        Payload rows: each position's pre-lm_head hidden; the metadata
        (carried on ModelRunnerOutput.lwd_c2e_meta, forwarded to the edge
        ahead via the ZMQ control plane) carries the GLOBAL RANK of each
        sampled token + per-request row counts and num_accepted.  The
        token id itself is never on the wire.

        Non-spec: one row per request.  Spec/MTP verify steps:
        accepted+1 rows per request — the accepted rows are a PREFIX of
        the request's verify segment (accepted draft positions + bonus
        row are contiguous), segments delimited by cu_num_sampled_tokens;
        each row's rank is computed against that row's target logits
        (the distribution the rejection sampler verified against).
        """
        collector = self.lwd_cloud_collector
        # Fast path: no remote-embeds request in flight -> zero per-step
        # cost (no rank computation, no row filtering).
        if collector.num_live_slots() == 0:
            return
        if spec_decode_metadata is None:
            entries = self._lwd_collect_nonspec(
                collector, sample_hidden_states, logits, sampler_output)
        else:
            entries = self._lwd_collect_spec(
                collector, sample_hidden_states, logits,
                spec_decode_metadata, sampler_output)
        if entries:
            # Data plane layering: the runner ONLY extracts per-step
            # data.  The DOWN wire carries ONLY the hidden tensor
            # (hidden_cat); ranks / num_accepted / req_ids ride back to
            # the scheduler on ModelRunnerOutput.lwd_c2e_meta (control
            # plane forwards them ahead).  Both are drained by the worker
            # layer (LwdCloudWorker.sample_tokens).
            hidden, meta = collector.build_hidden_payload(entries)
            self._lwd_pending_down_packet = hidden
            self._lwd_pending_c2e_meta = meta

    def take_lwd_pending_down_packet(self):
        """Worker layer drains the hidden tensor built by
        ``_lwd_cloud_collect_step`` (single-slot, overwritten per step —
        the worker's sample_tokens runs once per step, so it is always
        drained before the next build)."""
        packet = self._lwd_pending_down_packet
        self._lwd_pending_down_packet = None
        return packet

    def take_lwd_pending_c2e_meta(self):
        """Worker layer drains the step metadata (ranks / num_accepted /
        req_ids) that rides ModelRunnerOutput.lwd_c2e_meta back to the
        scheduler (control plane forwards it to the edge ahead)."""
        meta = self._lwd_pending_c2e_meta
        self._lwd_pending_c2e_meta = None
        return meta

    def _lwd_sampled_valid_mask(self, num_reqs: int):
        """Per-row mask: whether the request's last token was scheduled
        this step (i.e. its sampled token is real, not a discarded
        partial-prefill artifact).  Streaming sends every step
        immediately, so discarded rows MUST be filtered here — the old
        single-slot design masked them via last-write-wins, the stream
        cannot."""
        return ~self.discard_request_mask.np[:num_reqs]

    @staticmethod
    def _lwd_global_ranks(logits_rows: torch.Tensor,
                          sampled_ids: torch.Tensor) -> torch.Tensor:
        """Global rank of each sampled token: the number of vocab
        entries with a logit STRICTLY greater than the sampled token's
        logit.  Monotone-transform invariant (temperature-safe); the
        edge re-resolves it to a token via its own lm_head ranking."""
        lg = logits_rows.float()
        thresh = lg.gather(1, sampled_ids.long().unsqueeze(1))
        return (lg > thresh).sum(dim=1).to(torch.int32)

    def _lwd_collect_nonspec(self, collector, sample_hidden_states, logits,
                             sampler_output) -> list:
        """Non-spec step -> one entry per live LWD request (R=1)."""
        if logits is None:
            logger.warning_once(
                "[lwd] step without logits; skipping c2e stream"
            )
            return []
        if lmhead_tp_enable():
            # With lmhead TP the logits here are vocab SHARDS — a global
            # rank needs a cross-rank reduction (not implemented).  Skip
            # rather than ship shard-local ranks.
            logger.warning_once(
                "[lwd] rank collection is not supported with lmhead TP "
                "(logits are vocab shards); skipping c2e stream"
            )
            return []
        sampled = sampler_output.sampled_token_ids  # [B, 1]
        batch_req_ids = self.input_batch.req_ids
        valid = self._lwd_sampled_valid_mask(len(batch_req_ids))
        idx = [i for i, r in enumerate(batch_req_ids)
               if collector.has_slot(r) and valid[i]]
        if not idx:
            return []
        ranks = self._lwd_global_ranks(logits[idx], sampled[idx][:, 0])
        return [
            (batch_req_ids[i], sample_hidden_states[i : i + 1], ranks[j : j + 1], 0)
            for j, i in enumerate(idx)
        ]

    def _lwd_collect_spec(
        self, collector, sample_hidden_states, logits,
        spec_decode_metadata, sampler_output,
    ) -> list:
        """Spec verify step -> one entry per live LWD request
        (R = accepted+1 rows)."""
        if logits is None:
            logger.warning_once(
                "[lwd] spec step without logits; skipping c2e stream"
            )
            return []
        tp = get_tp_group()
        if tp.world_size > 1:
            # The ranks here would be computed over THIS rank's vocab
            # shard (lmhead TP) — not a global rank.  Skip rather than
            # ship shard-local ranks.
            logger.warning_once(
                "[lwd] spec collection is not supported with lmhead TP>1 "
                "(ranks would be shard-local); skipping c2e stream"
            )
            return []
        sampled = sampler_output.sampled_token_ids  # [B, max_spec_len+1], -1 = invalid
        if sampled is None or sampled.dim() != 2:
            logger.warning_once(
                "[lwd] unexpected sampled_token_ids shape in spec step; "
                "skipping c2e stream"
            )
            return []
        batch_req_ids = self.input_batch.req_ids
        assert sampled.shape[0] == len(batch_req_ids), (
            sampled.shape, len(batch_req_ids))
        valid = self._lwd_sampled_valid_mask(len(batch_req_ids))
        # accepted+1 == number of valid (non -1) entries per row; one D2H
        # for the whole batch per spec step.
        counts = (sampled != -1).sum(dim=1)
        counts_cpu = counts.tolist()
        cu = spec_decode_metadata.cu_num_sampled_tokens.tolist()
        entries = []
        seg_start = 0
        for i, req_id in enumerate(batch_req_ids):
            seg_end = cu[i]
            if not collector.has_slot(req_id) or not valid[i]:
                seg_start = seg_end
                continue
            rows = int(counts_cpu[i])          # accepted+1
            if rows < 1:
                seg_start = seg_end
                continue
            seg_hidden = sample_hidden_states[seg_start: seg_start + rows]
            seg_logits = logits[seg_start: seg_start + rows]
            seg_sampled = sampled[i, :rows]
            entries.append(
                (
                    req_id,
                    seg_hidden,
                    self._lwd_global_ranks(seg_logits, seg_sampled),
                    rows - 1,
                )
            )
            seg_start = seg_end
        return entries
