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
        """Device-side embeds injection AFTER the base fill loop.

        The base fill loop + copy_to_gpu run first (they only see the
        zero buffer); the received UP embeds are then written straight
        into ``inputs_embeds.gpu`` on the current stream, ordered after
        the channel-completion event via ``wait_for_comm()`` — no host
        wait, no host-side tensor reads anywhere on this path.
        """
        out = super()._prepare_inputs(scheduler_output, num_scheduled_tokens)
        if self._lwd_enabled():
            self._lwd_release_consumed_prompt_embeds()
            self._lwd_inject_remote_embeds(scheduler_output, num_scheduled_tokens)
        return out

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

    def _lwd_inject_remote_embeds(self, scheduler_output, num_scheduled_tokens) -> None:
        """Device-side inject: write the received UP embeds straight into
        ``inputs_embeds.gpu`` at each request's scheduled window.

        No host wait / no host tensor reads: ``future.result()`` only
        surfaces channel errors (raises), ``future.wait_for_comm()`` then
        orders the current stream after the channel-completion event, and
        all row copies are issued on that stream (non_blocking).  The
        flattened output offsets reproduce the native fill loop's
        accumulation (per-request scheduled segment start), so rows land
        exactly where the prompt-embeds branch expects them.  The CPU
        assembly buffer is also filled via an on-stream D2H copy — its
        only downstream consumer (draft first-pass provider) reads it
        with stream-ordered H2D copies, so no host sync is needed there
        either.  The base fill loop may have copied stale buffer content
        earlier; our device write happens after it and is authoritative.
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
        hidden_size = self.model_config.get_hidden_size()
        gpu_embeds = self.inputs_embeds.gpu

        # Flattened output offset per request (native fill loop 同款累计):
        # 每个请求的调度段在扁平 token 序列中的起点。
        out_offset: dict[str, int] = {}
        off = 0
        for i, req_id in enumerate(self.input_batch.req_ids):
            out_offset[req_id] = off
            off += int(num_scheduled_tokens[i]) if i < len(num_scheduled_tokens) else 0

        for batch_seqno in list(posted.keys()):
            item = worker._lwd_up_recv_futures.pop(batch_seqno, None)
            if item is None:
                continue
            future, meta = item
            res = future.result()  # 通道错误在此 fail-fast;数据可仍在途
            if res.tensor is None:
                continue
            embeds = res.tensor.view(-1, hidden_size)
            # 纯 device 排序:后续 copy 在通道完成事件之后执行,CPU 不阻塞
            future.wait_for_comm()
            logger.info(
                "[Lwd][cloud-runner] UP embeds consumed seqno=%s rows=%s "
                "reqs=%s",
                batch_seqno, embeds.shape[0], meta.req_ids,
            )
            row = 0
            for req_id, token_ids in zip(meta.req_ids, meta.token_ids):
                n = len(token_ids)
                idx = self.input_batch.req_id_to_index.get(req_id)
                if idx is None:
                    logger.warning(
                        "[Lwd][cloud-runner] INJECT DROP req=%s seqno=%s "
                        "rows=%d: req not in input_batch (batch=%s)",
                        req_id, batch_seqno, n, self.input_batch.req_ids,
                    )
                if idx is not None and n > 0:
                    start = int(computed[idx])
                    out = out_offset.get(req_id, 0)
                    # stream 上直接写 inputs_embeds.gpu 的调度窗口
                    gpu_embeds[out : out + n].copy_(
                        embeds[row : row + n], non_blocking=True
                    )
                    # CPU 组装缓冲同 stream D2H(供 draft provider 用)
                    prompt_len = int(num_prompt[idx])
                    buf = embeds_map.get(idx)
                    if buf is not None and buf.shape[0] == prompt_len:
                        buf[start : start + n].copy_(
                            embeds[row : row + n], non_blocking=True
                        )
                    self.input_batch.is_token_ids[idx, start : start + n] = False
                    if buf is not None:
                        LwdDebug.cloud_embeds_injected(req_id, idx, start, n, buf)  # [lwd-debug]
                row += n

    # ------------------------------------------------------------------ #
    # Collect probe (measurement only; output discarded, protocol        #
    # still returns token_ids directly)                                   #
    # ------------------------------------------------------------------ #

    def _sample(self, logits, spec_decode_metadata):
        """Capture the sampler output for the collect probe
        (the base sample_tokens clears execute_model_state on return)."""
        sampler_output = super()._sample(logits, spec_decode_metadata)
        self._lwd_captured_sampler_output = sampler_output
        return sampler_output

    @torch.inference_mode()
    def sample_tokens(self, grammar_output) -> ModelRunnerOutput:
        captured = None
        if self.execute_model_state is not None:
            # ExecuteModelState layout (see model_runner_v1.sample_tokens):
            # (scheduler_output, logits, spec_decode_metadata,
            #  spec_decode_common_attn_metadata, hidden_states,
            #  sample_hidden_states, ...)
            state = self.execute_model_state
            captured = (state[5], state[1], state[2])  # sample_hidden, logits, spec_meta
        self._lwd_captured_sampler_output = None
        output = super().sample_tokens(grammar_output)
        if captured is not None and self._lwd_captured_sampler_output is not None:
            self._lwd_pending_down_payload = self._lwd_collect_down_payload(
                captured[0], captured[1], captured[2],
                self._lwd_captured_sampler_output,
            )
        return output

    def take_lwd_pending_down_payload(self):
        """worker 层取走本步 DOWN payload(单槽覆盖写,每步必被取走)。"""
        payload = getattr(self, "_lwd_pending_down_payload", None)
        self._lwd_pending_down_payload = None
        return payload

    @torch.inference_mode()
    def _lwd_collect_down_payload(
        self, sample_hidden_states, logits, spec_decode_metadata, sampler_output,
    ):
        """生产级 DOWN 采集(rank-replay):hidden 组包 + 全局秩 + num_accepted。

        廉价计算:bf16 直比(logits 原生 bf16,与 cast 后逐位等价)、
        批全覆盖时整行直接算(不做高级索引取材)、ranks/counts 拼单个
        设备张量;物化走 边流 non_blocking -> pinned 缓冲 + event,
        关键路径零新增同步——host 读取推迟到引擎侧(那里本来就有
        get_output 的同步点)。返回:
          (hidden_packet, pinned_view, meta_event, req_ids, rows_per_req)
        或 None(本步无在途请求)。
        """
        from vllm_ascend.distributed import lwd_timing

        sampled = sampler_output.sampled_token_ids
        if sampled is None or sampled.dim() != 2 or logits is None:
            return None
        batch_req_ids = self.input_batch.req_ids
        valid = ~self.discard_request_mask.np[: len(batch_req_ids)]
        is_spec = spec_decode_metadata is not None

        t0 = lwd_timing.synced_now(sync=False)
        rows_list, ranks_list, accepted = [], [], []
        lg = logits  # bf16 原生,直接比较(cast 无精度增益)
        full_cover = all(valid[: len(batch_req_ids)])
        if not is_spec:
            idx = [i for i in range(len(batch_req_ids)) if valid[i]]
            if not idx:
                return None
            lg_sel = lg if full_cover else lg[idx]
            sm_sel = sampled[:, 0] if full_cover else sampled[idx][:, 0]
            thresh = lg_sel.gather(1, sm_sel.long().unsqueeze(1))
            ranks_list.append((lg_sel > thresh).sum(dim=1).to(torch.int32))
            rows_list.extend(sample_hidden_states[i : i + 1] for i in idx)
            accepted.extend([1] * len(idx))
        else:
            counts = (sampled != -1).sum(dim=1)
            cu = spec_decode_metadata.cu_num_sampled_tokens.tolist()
            seg_start = 0
            for i in range(len(batch_req_ids)):
                rows = int(counts[i])
                if valid[i] and rows >= 1:
                    seg_lg = lg[seg_start : seg_start + rows]
                    thresh = seg_lg.gather(
                        1, sampled[i, :rows].long().unsqueeze(1))
                    ranks_list.append((seg_lg > thresh).sum(dim=1).to(torch.int32))
                    rows_list.append(
                        sample_hidden_states[seg_start : seg_start + rows])
                    accepted.append(rows)
                seg_start = cu[i]
        if not rows_list:
            return None

        hidden_packet = torch.cat(rows_list)
        meta_dev = torch.cat(
            ranks_list + [torch.tensor(accepted, dtype=torch.int32,
                                       device=logits.device)]
        )
        # 边流 pinned 物化:等主流算完后异步 D2H,记录事件给引擎侧
        n_meta = meta_dev.numel()
        pinned = self._lwd_meta_pinned(n_meta)
        side = self._lwd_meta_side_stream()
        current = torch.npu.current_stream()
        with torch.npu.stream(side):
            side.wait_stream(current)
            pinned[:n_meta].copy_(meta_dev, non_blocking=True)
            event = torch.npu.Event()
            event.record(side)
        lwd_timing.log_duration(
            f"[Lwd][timing] collect payload rows={hidden_packet.shape[0]} "
            f"meta={n_meta}", t0, sync=False,
        )
        return (
            hidden_packet,
            pinned[:n_meta],
            event,
            [r for i, r in enumerate(batch_req_ids) if valid[i]],
            accepted,
        )

    def _lwd_meta_pinned(self, n: int):
        """轮换 pinned 缓冲(深度 4 > batch_queue 深度 2 + 引擎滞后 1):
        避免下一/N+2 步的边流拷贝覆盖引擎尚未读完的上一步 meta。"""
        ring = getattr(self, "_lwd_pinned_ring", None)
        if ring is None or ring[0].numel() < n:
            ring = [
                torch.empty(max(n, 4096), dtype=torch.int32, pin_memory=True)
                for _ in range(4)
            ]
            self._lwd_pinned_ring = ring
            self._lwd_pinned_ring_idx = 0
        idx = self._lwd_pinned_ring_idx
        self._lwd_pinned_ring_idx = (idx + 1) % len(ring)
        return ring[idx]

    def _lwd_meta_side_stream(self):
        s = getattr(self, "_lwd_side_stream", None)
        if s is None:
            s = torch.npu.Stream()
            self._lwd_side_stream = s
        return s

