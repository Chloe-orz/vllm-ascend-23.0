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
        prompt arrives as embeddings over the UP channel.  Chunks are
        assembled into a per-request FULL-prompt host buffer (written at
        the request's ``num_computed_tokens`` offset), so the base
        runner's native fill loop (global-offset slicing) reads the
        right rows for every chunk — chunked prefill included.  Buffers
        whose prompt was fully consumed are released here (draft has
        already read them during the previous step's sampling).
        """
        if self._lwd_enabled():
            self._lwd_release_consumed_prompt_embeds()
            self._lwd_inject_remote_embeds()
        return super()._prepare_inputs(scheduler_output, num_scheduled_tokens)

    def _lwd_enabled(self) -> bool:
        cfg = getattr(self.vllm_config, "lwd_config", None)
        return bool(cfg is not None and cfg.enabled)

    def _lwd_release_consumed_prompt_embeds(self) -> None:
        """Release assembly buffers whose prompt was fully consumed.

        A buffer becomes releasable once the request's computed tokens
        cover the whole prompt: the last chunk's rows were consumed by
        the previous step's fill loop, and the draft proposer read its
        window during that step's sampling (which precedes this call).
        Decode steps never read prompt embeds, so dropping the entry
        here cannot corrupt anything.  Entries follow native index
        compaction (condense/swap), so keying by idx stays correct.

        Also drops orphan entries whose slot no longer holds a live
        request (preemption removes the request without finishing it, so
        the flush hook never fires): a stale buffer at a recycled index
        would otherwise be mistaken for the new occupant's embeds.
        """
        embeds_map = self.input_batch.req_prompt_embeds
        if not embeds_map:
            return
        num_prompt = self.input_batch.num_prompt_tokens
        computed = self.input_batch.num_computed_tokens_cpu
        slot_req_ids = self.input_batch.req_ids
        for idx in list(embeds_map.keys()):
            if idx >= len(computed):
                embeds_map.pop(idx)
                continue
            if idx >= len(slot_req_ids) or slot_req_ids[idx] is None:
                embeds_map.pop(idx)
                continue
            if computed[idx] >= num_prompt[idx]:
                embeds_map.pop(idx)

    def _lwd_inject_remote_embeds(self) -> None:
        """Assemble UP chunks into per-request full-prompt host buffers.

        First chunk allocates ``[prompt_len, H]`` on CPU (zero NPU
        memory); every chunk copies its rows into its own global window
        ``[num_computed, num_computed + n)`` — old rows are never
        rewritten and never re-read, so there is no overwrite hazard.
        Only the current chunk's ``is_token_ids`` range is cleared.
        """
        worker = self.worker
        if worker is None:
            return
        posted = getattr(worker, "_lwd_up_recv_futures", None)
        if not posted:
            return
        embeds_map = self.input_batch.req_prompt_embeds
        num_prompt = self.input_batch.num_prompt_tokens
        computed = self.input_batch.num_computed_tokens_cpu
        for batch_seqno in list(posted.keys()):
            embeds, meta = worker.take_lwd_up_embeds(batch_seqno)
            if embeds is None:
                continue
            logger.info(
                "[Lwd][cloud-runner] UP embeds consumed seqno=%s rows=%s "
                "reqs=%s",
                batch_seqno, embeds.shape[0] if embeds is not None else 0,
                meta.req_ids,
            )
            # Split the concatenated batch rows back per request
            # (rows follow batch_meta order).
            row = 0
            for req_id, token_ids in zip(meta.req_ids, meta.token_ids):
                n = len(token_ids)
                idx = self.input_batch.req_id_to_index.get(req_id)
                if idx is not None and n > 0:
                    prompt_len = int(num_prompt[idx])
                    buf = embeds_map.get(idx)
                    if buf is not None and buf.shape[0] != prompt_len:
                        # Stale entry at a recycled index (previous
                        # occupant preempted/removed): reallocate.
                        buf = None
                    if buf is None:
                        # First chunk: allocate the full-prompt host buffer
                        buf = torch.empty(
                            (prompt_len, embeds.shape[-1]),
                            dtype=embeds.dtype,
                        )
                        embeds_map[idx] = buf
                    start = int(computed[idx])
                    buf[start : start + n].copy_(embeds[row : row + n])
                    self.input_batch.is_token_ids[idx, start : start + n] = False
                row += n
            # Drop the NPU chunk reference promptly (the recv buffer is
            # reaped by the comm layer once no future/result holds it).
            del embeds

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
            logger.debug(
                "[Lwd][cloud-runner] collect skipped: live_slots=%s logits=%s",
                collector.num_live_slots(), logits is not None,
            )
            return
        entries = self._lwd_collect_batch(
            collector, sample_hidden_states, logits,
            spec_decode_metadata, sampler_output,
        )
        if entries:
            hidden, meta = collector.build_hidden_payload(entries)
            self._lwd_pending_down_packet = hidden
            self._lwd_pending_c2e_meta = meta
            logger.info(
                "[Lwd][cloud-runner] DOWN packet built: reqs=%s rows=%d numel=%d",
                getattr(meta, "req_ids", None),
                hidden.shape[0] if hidden is not None else 0,
                hidden.numel() if hidden is not None else 0,
            )
        else:
            logger.debug("[Lwd][cloud-runner] collect: no LWD entries this step")

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

    def _lwd_detokenize(self, token_ids: list[int]) -> str:
        """调试:把云侧采样 token ids 解码成最终返回用户形态的文本。"""
        if getattr(self, "_lwd_tokenizer", None) is None:
            from transformers import AutoTokenizer
            self._lwd_tokenizer = AutoTokenizer.from_pretrained(
                self.vllm_config.model_config.model,
                trust_remote_code=self.vllm_config.model_config.trust_remote_code,
            )
        return self._lwd_tokenizer.decode(token_ids)

    def _lwd_collect_batch(
        self, collector, sample_hidden_states, logits,
        spec_decode_metadata, sampler_output,
    ) -> list:
        """产出 entries: (req_id, hidden_rows, ranks, accepted)，行序 = input_batch 序。

        accepted 语义 = 本步返回行数:非 spec 每请求 1 行(accepted=1);
        spec verify 每请求 accepted+1 行(rejection 后有效行是该请求
        verify 段的前缀,段界 cu_num_sampled_tokens)。
        行过滤:has_slot(已注册)x ~discard_request_mask(本步真采样)。
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
            logger.info(
                "[Lwd][DUMP][req=%s] SEND DOWN cloud sampled text: %s",
                [batch_req_ids[i] for i in idx],
                [self._lwd_detokenize(ids)
                 for ids in sampled[idx][:, 0].tolist()],
            )
            return [
                # num_accepted 语义 = 本步返回行数(非 spec 恒 1 行)
                (batch_req_ids[i], sample_hidden_states[i : i + 1],
                 ranks[j : j + 1], 1)
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
                seg_ranks = self._lwd_global_ranks(seg_logits, sampled[i, :rows])
                logger.info(
                    "[Lwd][DUMP][req=%s] SEND DOWN cloud sampled text: %s",
                    req_id,
                    self._lwd_detokenize(sampled[i, :rows].tolist()),
                )
                entries.append((
                    req_id,
                    sample_hidden_states[seg_start : seg_start + rows],
                    seg_ranks,
                    # num_accepted 语义 = 本步返回行数(spec verify =
                    # accepted+1 行,即有效 sampled 数),与 top_id_ths
                    # 行数恒等,边侧按行数还原 token 不会取错
                    rows,
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

