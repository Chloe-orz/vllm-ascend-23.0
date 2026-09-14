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
from vllm.logger import logger
from vllm.v1.lwd_debug import LwdDebug

from vllm_ascend.worker.model_runner_v1 import NPUModelRunner


class LwdCloudModelRunner(NPUModelRunner):
    """NPUModelRunner + prefill_only LWD cloud-side runner logic."""

    def __init__(self, vllm_config, device, worker=None):
        super().__init__(vllm_config, device)
        self.worker = worker  # LwdCloudWorker ref (UP recv futures live there)
        # token 直传模式:云侧不做任何采样收集——控制面(引擎)直接从
        # ModelRunnerOutput 取 sampled_token_ids 发边;本 runner 只保留
        # UP embeds 注入(prefill 输入)相关逻辑。

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
                    LwdDebug.cloud_embeds_injected(req_id, idx, start, n, buf)  # [lwd-debug]
                row += n
            # Drop the NPU chunk reference promptly (the recv buffer is
            # reaped by the comm layer once no future/result holds it).
            del embeds
