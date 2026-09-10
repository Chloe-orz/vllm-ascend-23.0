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
        """每步收集批内在途 LWD 请求的 (hidden, 全局秩, accepted)，组包入槽
        供 worker 层发送；元信息随 ModelRunnerOutput.lwd_c2e_meta 回调度器。"""
        collector = self.lwd_cloud_collector
        if collector.num_live_slots() == 0 or logits is None:
            return
        entries = self._lwd_collect_batch(
            collector, sample_hidden_states, logits,
            spec_decode_metadata, sampler_output,
        )
        if entries:
            hidden, meta = collector.build_hidden_payload(entries)
            self._lwd_pending_down_packet = hidden
            self._lwd_pending_c2e_meta = meta

    def take_lwd_pending_down_packet(self):
        """worker 层取走本步 DOWN hidden 张量（单槽覆盖写，每步必被取走）。"""
        packet = self._lwd_pending_down_packet
        self._lwd_pending_down_packet = None
        return packet

    def take_lwd_pending_c2e_meta(self):
        """worker 层取走本步元信息（ranks/accepted/req_ids）。"""
        meta = self._lwd_pending_c2e_meta
        self._lwd_pending_c2e_meta = None
        return meta

    def _lwd_collect_batch(
        self, collector, sample_hidden_states, logits,
        spec_decode_metadata, sampler_output,
    ) -> list:
        """产出 entries: (req_id, hidden_rows, ranks, accepted)，行序 = input_batch 序。

        非 spec 每请求 1 行（accepted=0）；spec verify 每请求 accepted+1 行
        （rejection 后有效行是该请求 verify 段的前缀，段界 cu_num_sampled_tokens）。
        行过滤：has_slot（已注册）x ~discard_request_mask（本步真采样）。
        """
        sampled = sampler_output.sampled_token_ids  # [B, k+1], -1 为无效位
        if sampled is None or sampled.dim() != 2:
            logger.warning_once("[lwd] bad sampled_token_ids; skip c2e stream")
            return []
        batch_req_ids = self.input_batch.req_ids
        assert sampled.shape[0] == len(batch_req_ids), (
            sampled.shape, len(batch_req_ids))
        valid = ~self.discard_request_mask.np[: len(batch_req_ids)]

        if spec_decode_metadata is None:
            idx = [i for i, r in enumerate(batch_req_ids)
                   if collector.has_slot(r) and valid[i]]
            if not idx:
                return []
            ranks = self._lwd_global_ranks(
                self._lwd_full_vocab_logits(logits[idx]), sampled[idx][:, 0]
            )
            return [
                (batch_req_ids[i], sample_hidden_states[i : i + 1],
                 ranks[j : j + 1], 0)
                for j, i in enumerate(idx)
            ]

        counts = (sampled != -1).sum(dim=1).tolist()  # accepted+1
        cu = spec_decode_metadata.cu_num_sampled_tokens.tolist()
        entries, seg_start = [], 0
        for i, req_id in enumerate(batch_req_ids):
            seg_end = cu[i]
            rows = counts[i]
            if collector.has_slot(req_id) and valid[i] and rows >= 1:
                seg_logits = self._lwd_full_vocab_logits(
                    logits[seg_start : seg_start + rows]
                )
                entries.append((
                    req_id,
                    sample_hidden_states[seg_start : seg_start + rows],
                    self._lwd_global_ranks(seg_logits, sampled[i, :rows]),
                    rows - 1,
                ))
            seg_start = seg_end
        return entries

    @staticmethod
    def _lwd_full_vocab_logits(logits_rows: torch.Tensor) -> torch.Tensor:
        """lmhead TP 时按词表维 all_gather 归约出全词表 fp32 logits（否则直通）。"""
        tp = get_tp_group()
        rows_f32 = logits_rows.float()
        if tp.world_size > 1 and lmhead_tp_enable():
            return tp.all_gather(rows_f32, dim=-1)
        return rows_f32

    @staticmethod
    def _lwd_global_ranks(logits_rows: torch.Tensor,
                          sampled_ids: torch.Tensor) -> torch.Tensor:
        """采样 token 的全局秩 = 全词表中严格超过其 logit 的条目数（int32）。"""
        lg = logits_rows.float()
        thresh = lg.gather(1, sampled_ids.long().unsqueeze(1))
        return (lg > thresh).sum(dim=1).to(torch.int32)

