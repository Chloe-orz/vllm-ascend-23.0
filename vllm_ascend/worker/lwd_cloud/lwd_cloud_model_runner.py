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

import time

import torch
from vllm.distributed.parallel_state import get_tp_group
from vllm.forward_context import get_forward_context
from vllm.logger import logger
from vllm.v1.lwd_control.control_communication.lwd_id_adapter import parse_edge_id
from vllm.v1.outputs import ModelRunnerOutput

from vllm_ascend.worker.lwd_hash.lwd_hash_routing import (
    LwdHashRoutingState,
    hash_layer_count,
    hash_payload_numel,
    unpack_hash_payload,
)
from vllm_ascend.worker.model_runner_v1 import NPUModelRunner


class LwdCloudModelRunner(NPUModelRunner):
    """NPUModelRunner + prefill_only LWD cloud-side runner logic."""

    def __init__(self, vllm_config, device, worker=None):
        super().__init__(vllm_config, device)
        self.worker = worker  # LwdCloudWorker ref (UP recv futures live there)
        self._lwd_pending_down_payload = None
        self.lwd_hash_state = None
        # 用空值表示尚未准备真实批次，区分 dummy 前向。
        self._lwd_hash_step_tokens = None
        config = self.model_config.hf_config
        num_hash_layers = hash_layer_count(config)
        lwd_config = getattr(vllm_config, "lwd_config", None)
        if num_hash_layers and lwd_config is not None and lwd_config.enabled and lwd_config.mode == "prefill_only":
            # UP currently broadcasts one edge's batch to one cloud TP group.
            # CP/DP need additional request-to-rank layouts before supporting V4.
            parallel = vllm_config.parallel_config
            if (parallel.data_parallel_size != 1 or parallel.prefill_context_parallel_size != 1
                    or parallel.decode_context_parallel_size != 1):
                raise ValueError("LWD V4 Hash routing currently requires DP=PCP=DCP=1 (TP/EP are supported)")
            self.lwd_hash_state = LwdHashRoutingState(
                num_hash_layers, config.num_experts_per_tok, config.n_routed_experts,
            )
            # Persistent buffers are populated before model execution, so graph
            # capture and replay see the same addresses for prompt and decode.
            self._lwd_hash_experts = torch.zeros(
                self.max_num_tokens, num_hash_layers, config.num_experts_per_tok,
                dtype=torch.int32, device=device,
            )
            self._lwd_hash_prompt_mask = torch.zeros(self.max_num_tokens, dtype=torch.bool, device=device)
            self._lwd_hash_token_ids = torch.zeros(self.max_num_tokens, dtype=torch.int64, device=device)

    # ------------------------------------------------------------------ #
    # Remote embeds injection (cloud input has NO token ids — the prompt   #
    # embeddings arrive over the UP channel and must drive forward)        #
    # ------------------------------------------------------------------ #

    def _prepare_inputs(self, scheduler_output, num_scheduled_tokens):
        """Device-side embeds injection AFTER the base fill loop.

        The base fill loop + copy_to_gpu run first (they only see the
        zero buffer); the received UP embeds are then written straight
        into ``inputs_embeds.gpu`` on the current stream, ordered after
        the channel-completion event via ``future.wait_for_comm()`` —
        non-blocking, recv 等待另有 [Lwd][perf] up-recv-wait 计时可见。
        """
        out = super()._prepare_inputs(scheduler_output, num_scheduled_tokens)
        if self._lwd_enabled():
            self._lwd_release_consumed_prompt_embeds()
            self._lwd_inject_remote_embeds(scheduler_output, num_scheduled_tokens)
        if self.lwd_hash_state is not None:
            num_reqs = self.input_batch.num_reqs
            batch, mask = self.lwd_hash_state.build_batch(
                self.input_batch.req_ids, num_scheduled_tokens[:num_reqs],
                self.input_batch.num_computed_tokens_cpu[:num_reqs],
                self.input_batch.num_prompt_tokens[:num_reqs],
            )
            self._lwd_hash_step_tokens = batch.shape[0]
            # 清空上一批次专家数据，保证补齐区域没有残留。
            self._lwd_hash_experts.zero_()
            self._lwd_hash_prompt_mask.zero_()
            self._lwd_hash_experts[:batch.shape[0]].copy_(batch)
            self._lwd_hash_prompt_mask[:mask.shape[0]].copy_(mask)
        return out

    def _preprocess(self, scheduler_output, num_input_tokens, intermediate_tensors=None):
        """在异步投机位置修正后刷新 decode 掩码，再准备模型输入。"""
        if (self.use_async_spec_decode and self.enable_prompt_embeds
                and intermediate_tensors is None and self.pcp_size == 1):
            self._lwd_refresh_decode_embedding_mask(scheduler_output)
        return super()._preprocess(scheduler_output, num_input_tokens, intermediate_tensors)

    def _lwd_refresh_decode_embedding_mask(self, scheduler_output):
        """根据设备上的实际位置重建掩码，避免 decode 行复用旧 embedding。

        异步投机接受或拒绝后，CPU token 表可能滞后于设备上的输入和位置。
        保留远端 prompt embedding，仅标记 decode 行需要重新计算 embedding。
        此处主动同步读取设备位置，以保证掩码与本次模型输入一致。
        """
        count = scheduler_output.total_num_scheduled_tokens
        positions = self.positions[:count].detach().cpu().numpy()
        start = 0
        for idx, req_id in enumerate(self.input_batch.req_ids):
            end = start + scheduler_output.num_scheduled_tokens[req_id]
            self.is_token_ids.np[start:end] = positions[start:end] >= self.input_batch.num_prompt_tokens[idx]
            start = end
        self.is_token_ids.copy_to_gpu(count)

    # 在云侧模拟前向前清除真实批次标记，防止复用上次请求路由。
    def _dummy_run(self, *args, **kwargs):
        """清除真实批次的 Hash 路由标记，再执行模拟前向。"""
        # 用空值表示尚未准备真实批次，区分 dummy 前向。
        self._lwd_hash_step_tokens = None
        return super()._dummy_run(*args, **kwargs)

    def _model_forward(self, num_tokens_padded, input_ids=None, positions=None,
                       intermediate_tensors=None, inputs_embeds=None, **model_kwargs):
        """按 SP 布局切分 embedding，并将完整 Hash 路由数据写入前向上下文。"""
        context = get_forward_context()
        if (inputs_embeds is not None and intermediate_tensors is None
                and context.flash_comm_v1_enabled and not self.supports_mm_inputs):
            # 直接传入 embedding 会绕过原生嵌入层，需要在此补上序列切分。
            tp_group = get_tp_group()
            if tp_group.world_size > 1:
                if inputs_embeds.shape[0] != num_tokens_padded:
                    raise ValueError("LWD SP expects full-token inputs_embeds before slicing")
                if context.pad_size:
                    inputs_embeds = torch.nn.functional.pad(inputs_embeds, (0, 0, 0, context.pad_size))
                inputs_embeds = inputs_embeds.chunk(tp_group.world_size, dim=0)[tp_group.rank_in_group]
            # 位置、注意力元数据和 Hash 路由表保持完整 token 布局。
        if self.lwd_hash_state is not None:
            # 先初始化路由索引缓存，确保补齐行使用合法零索引。
            self._lwd_hash_token_ids.zero_()
            if self._lwd_hash_step_tokens is None:
                # Synthetic forwards have no remote prompt; route dummy token 0.
                self._lwd_hash_prompt_mask.zero_()
            else:
                count = self._lwd_hash_step_tokens
                if count > num_tokens_padded:
                    raise ValueError("LWD Hash routing rows exceed model input rows")
                # Native input preparation retains real decode IDs even when
                # model input_ids=None because the model consumes embeddings.
                self._lwd_hash_token_ids[:count].copy_(self.input_ids.gpu[:count])
            context.input_ids = self._lwd_hash_token_ids[:num_tokens_padded]
            context.lwd_hash_expert_ids = self._lwd_hash_experts[:num_tokens_padded]
            context.lwd_hash_prompt_mask = self._lwd_hash_prompt_mask[:num_tokens_padded]
        return super()._model_forward(
            num_tokens_padded, input_ids, positions, intermediate_tensors, inputs_embeds, **model_kwargs,
        )

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
        if self.lwd_hash_state is not None:
            for req_id in list(self.lwd_hash_state.requests):
                request = self.requests.get(req_id)
                if request is None or request.num_computed_tokens >= request.num_prompt_tokens:
                    self.lwd_hash_state.discard(req_id)
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

        The recv uses ``future.wait_for_comm()`` (non-blocking device
        ordering; channel errors surface via ``future.result()``), with
        row copies issued on the current stream (non_blocking) after it.  The
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

        for key in list(posted.keys()):
            edge_id, batch_seqno = key
            item = worker._lwd_up_recv_futures.pop(key, None)
            if item is None:
                continue
            future, meta = item
            _t_wait = time.monotonic()
            import torch.distributed as dist
            from vllm_ascend.distributed import lwd_wire
            from vllm_ascend.distributed.lwd_comm.types import LwdChannelType

            _is_endpoint = lwd_wire.is_lwd_channel_endpoint(
                LwdChannelType.UP, edge_id=edge_id, cloud_id=None
            )
            num_tokens = sum(len(t) for t in meta.token_ids)
            config = self.model_config.hf_config
            num_hash_layers = hash_layer_count(config)
            numel = hash_payload_numel(
                num_tokens, hidden_size, num_hash_layers,
                getattr(config, "num_experts_per_tok", 0),
            )
            # UP 第二段(TP 组内广播)按 prefill_only_demo_br 范式在消费
            # 时刻、本卡计算流上原子完成:launch + handle.wait() 同一流
            # 上下文(torch_npu 的 wait 桥接到调用时当前流),不依赖两个
            # HCCL op 之间的跨流排序——那是此前广播段交付残缺的根因。
            if _is_endpoint:
                # 端点:先过 host 就绪门(demo 的 wait gate):done_event
                # 轮询通过即 P2P 数据已完整落 buffer;超时显式报错而非
                # 静默乱码。门通过后再广播,广播读到的必然是完整数据。
                res = future.wait(timeout=60.0)
                up_flat = res.tensor
                if up_flat is None:
                    continue
            else:
                # 非端点:现场分配接收 buffer,等端点广播转发。
                up_flat = torch.empty(
                    numel, dtype=torch.bfloat16, device="npu"
                )
            from vllm.distributed.parallel_state import get_tp_group
            _tp = get_tp_group()
            if _tp.world_size > 1:
                # 端点随 edge_id 轮转:广播源 = 本通信域的云端点 rank,
                # 而非固定 TP0(不同边对应不同端点卡,见 lwd_wire 建组)。
                _, cloud_endpoint = lwd_wire.get_lwd_channel_endpoint_rank(
                    edge_id=edge_id, cloud_id=None
                )
                work = dist.broadcast(
                    up_flat,
                    src=cloud_endpoint,
                    group=_tp.device_group,
                    async_op=True,
                )
                work.wait()  # 桥接广播完成到当前(计算)流,后续 copy 有序
            logger.info(
                "[Lwd][perf] cloud up-recv-wait seqno=%s dur=%.2fms",
                batch_seqno, (time.monotonic() - _t_wait) * 1000,
            )
            expert_ids = None
            if num_hash_layers:
                # 广播整个载荷后再拆分，确保每张 TP 卡收到相同的专家 ID。
                embeds, expert_ids = unpack_hash_payload(
                    up_flat, num_tokens, hidden_size, num_hash_layers,
                    config.num_experts_per_tok,
                )
            else:
                embeds = up_flat.view(-1, hidden_size)
            offsets = getattr(meta, "token_offsets", [])
            if len(meta.req_ids) != len(meta.token_ids):
                raise ValueError("LWD UP request and token metadata lengths do not match")
            if (num_hash_layers or offsets) and len(offsets) != len(meta.req_ids):
                raise ValueError("LWD requires one explicit prompt chunk offset per request")
            logger.info(
                "[Lwd][cloud-runner] UP embeds consumed seqno=%s rows=%s "
                "reqs=%s",
                batch_seqno, embeds.shape[0], meta.req_ids,
            )
            row = 0
            for meta_idx, (req_id, token_ids) in enumerate(zip(meta.req_ids, meta.token_ids)):
                n = len(token_ids)
                idx = self.input_batch.req_id_to_index.get(req_id)
                if idx is None:
                    # fail-fast:embeds 已收齐但请求不在本步 batch——继续
                    # 走下去该请求将用未注入的脏 embeds 解码(静默乱码),
                    # 必须当场暴露而非丢弃。出现即调度/数据面时序契约
                    # 被破坏,需要修的是上游而不是这里。
                    raise RuntimeError(
                        f"[Lwd][cloud-runner] INJECT req={req_id} seqno="
                        f"{batch_seqno} rows={n}: req not in input_batch "
                        f"(batch={self.input_batch.req_ids})"
                    )
                if n > 0:
                    # fail-fast:本 chunk 行数必须恰等于该请求本步调度 token
                    # 数。不等(调度窗口 ≠ 边侧 chunk,如预算挤压截断)时
                    # 注入会越窗踩邻请求行/留下未注入尾巴——静默乱码源,
                    # 直接暴露。
                    scheduled = (
                        int(num_scheduled_tokens[idx])
                        if idx < len(num_scheduled_tokens) else 0
                    )
                    if n != scheduled:
                        raise RuntimeError(
                            f"[Lwd][cloud-runner] INJECT window mismatch "
                            f"req={req_id} seqno={batch_seqno}: chunk rows="
                            f"{n} != scheduled={scheduled} (computed="
                            f"{int(computed[idx])} prompt="
                            f"{int(num_prompt[idx])})"
                        )
                    start = int(offsets[meta_idx]) if offsets else int(computed[idx])
                    prompt_len = int(num_prompt[idx])
                    if start != int(computed[idx]) or not 0 <= start <= start + n <= prompt_len:
                        raise ValueError(
                            f"LWD prompt chunk offset mismatch for {req_id}: "
                            f"start={start}, computed={int(computed[idx])}, rows={n}, prompt={prompt_len}"
                        )
                    if self.lwd_hash_state is not None:
                        if expert_ids is None:
                            raise ValueError(f"Missing LWD V4 expert payload for {req_id}")
                        self.lwd_hash_state.add_chunk(req_id, prompt_len, start, expert_ids[row:row + n])
                    out = out_offset.get(req_id, 0)
                    # stream 上直接写 inputs_embeds.gpu 的调度窗口
                    gpu_embeds[out : out + n].copy_(
                        embeds[row : row + n], non_blocking=True
                    )
                    # CPU 组装缓冲同 stream D2H(供 draft provider 用)
                    buf = embeds_map.get(idx)
                    if buf is not None and buf.shape[0] == prompt_len:
                        buf[start : start + n].copy_(
                            embeds[row : row + n], non_blocking=True
                        )
                    self.input_batch.is_token_ids[idx, start : start + n] = False
                row += n
            # 跨流生命周期登记:端点 recv buffer 由通道流分配与复用
            # (同尺寸 chunk 下分配器几乎总给同一块),本步 copy 在计算流。
            # 不登记 record_stream,分配器可在本批 copy 尚未执行时把块交给
            # 下一 seqno 的 irecv 覆写——深异步队列下表现为跨 seqno 串
            # 数据(多请求乱码)。登记后复用即被正确排序。
            up_flat.record_stream(torch.npu.current_stream())

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
        # 端点随 edge_id 轮转后,不同 edge 的 DOWN 端点落在不同云 rank,
        # 因此每卡都可能是某些 edge 的端点——采集改在全部 TP rank 上进行,
        # 发送侧再按 edge_id 过滤到对应端点(见 LwdCloudWorker.sample_tokens)。
        captured = None
        if self.execute_model_state is not None:
            # ExecuteModelState layout (see model_runner_v1.sample_tokens):
            # (scheduler_output, logits, spec_decode_metadata,
            #  spec_decode_common_attn_metadata, hidden_states,
            #  sample_hidden_states, ...)
            state = self.execute_model_state
            # 批序/掩码也一并快照:batch queue 重叠时,下一步的
            # _prepare_inputs 可能在 collect 前重排 input_batch,
            # 现读会拿到批序B去切批序A的张量(高并发错位根因)
            captured = (
                state[5], state[1], state[2], state[0],
                list(self.input_batch.req_ids),
                self.discard_request_mask.np.copy(),
            )
        self._lwd_captured_sampler_output = None
        output = super().sample_tokens(grammar_output)
        if captured is not None and self._lwd_captured_sampler_output is not None:
            self._lwd_pending_down_payload = self._lwd_collect_down_payload(
                captured[0], captured[1], captured[2], captured[3],
                captured[4], captured[5], self._lwd_captured_sampler_output,
            )
        return output

    def take_lwd_pending_down_payload(self):
        """worker 层取走本步 DOWN payload 列表(per-edge,单槽覆盖写)。"""
        payload = getattr(self, "_lwd_pending_down_payload", None)
        self._lwd_pending_down_payload = None
        return payload

    @torch.inference_mode()
    def _lwd_collect_down_payload(
        self, sample_hidden_states, logits, spec_decode_metadata,
        scheduler_output, batch_req_ids, discard_mask_np, sampler_output,
    ):
        """生产级 DOWN 采集(rank-replay),按来源边拆分回传。

        混在多边 batch 里的结果按 ``wrapped_req_id`` 解析出 ``edge_id``,
        同一条边的 hidden/秩/counts/seg_lens 归到一起,返回 per-edge
        载荷列表 ``[(edge_id, hidden_packet, pinned_view, None, req_ids,
        None)]``;单边场景自然退化为单元素列表,与原实现行为一致。

        廉价计算:bf16 直比(logits 原生 bf16,与 cast 后逐位等价)、
        批全覆盖时整行直接算(不做高级索引取材)、ranks/counts/seg_lens
        拼单个设备张量;meta 经 pinned 在主流末尾异步拷贝,worker 属性上
        紧随记录就绪事件,由响应入队处 synchronize 后引擎侧解码。
        批序/掩码取捕获时刻快照(防 batch queue 重叠重排)。
        """
        _t0 = time.monotonic()
        sampled = sampler_output.sampled_token_ids
        if sampled is None or sampled.dim() != 2 or logits is None:
            return None
        # batch_req_ids/discard_mask 来自捕获时刻快照(与 logits/hidden
        # 同批序),不读活的 input_batch
        valid = ~discard_mask_np[: len(batch_req_ids)]
        is_spec = spec_decode_metadata is not None

        # edge_id -> {rows, ranks, req_ids, counts, seg_lens}
        buckets: dict[int, dict[str, list]] = {}
        lg = logits  # bf16 原生,直接比较(cast 无精度增益)

        def _bucket(edge_id: int) -> dict[str, list]:
            b = buckets.get(edge_id)
            if b is None:
                b = {"rows": [], "ranks": [], "req_ids": [],
                     "counts": [], "seg_lens": []}
                buckets[edge_id] = b
            return b

        if not is_spec:
            idx = [i for i in range(len(batch_req_ids)) if valid[i]]
            if not idx:
                return None
            full_cover = all(valid[: len(batch_req_ids)])
            lg_sel = lg if full_cover else lg[idx]
            sm_sel = sampled[:, 0] if full_cover else sampled[idx][:, 0]
            thresh = lg_sel.gather(1, sm_sel.long().unsqueeze(1))
            ranks_all = (lg_sel > thresh).sum(dim=1).to(torch.int32)
            for k, i in enumerate(idx):
                edge_id, _ = parse_edge_id(batch_req_ids[i])
                b = _bucket(edge_id)
                b["rows"].append(sample_hidden_states[i : i + 1])
                b["ranks"].append(ranks_all[k : k + 1])
                b["req_ids"].append(batch_req_ids[i])
                one = torch.ones(1, dtype=torch.int32, device=logits.device)
                b["counts"].append(one)
                b["seg_lens"].append(one)
        else:
            # 全零同步 spec 路径:段长取 spec_decode_metadata.num_draft_tokens
            # (host list,运行期真实布局,与 sample_hidden_states 段结构一致);
            # counts 用框架每步已算好的 num_accepted_tokens(纯 device)。
            seg_lens = [
                d + 1 for d in spec_decode_metadata.num_draft_tokens
            ]
            counts_all = (sampled != -1).sum(dim=1)
            seg_start = 0
            for i in range(len(batch_req_ids)):
                seg_len = seg_lens[i]
                seg_lg = lg[seg_start : seg_start + seg_len]
                seg_hidden = sample_hidden_states[seg_start : seg_start + seg_len]
                rows_i = seg_hidden.shape[0]
                if valid[i] and rows_i >= 1:
                    seg_sm = sampled[i, :rows_i]
                    thresh = seg_lg.gather(1, seg_sm.long().unsqueeze(1))
                    rank = (seg_lg > thresh).sum(dim=1).to(torch.int32)
                    count = torch.clamp(counts_all[i : i + 1], max=rows_i)
                    seg_len_t = torch.tensor(
                        [rows_i], dtype=torch.int32, device=logits.device
                    )
                    edge_id, _ = parse_edge_id(batch_req_ids[i])
                    b = _bucket(edge_id)
                    b["rows"].append(seg_hidden)
                    b["ranks"].append(rank)
                    b["req_ids"].append(batch_req_ids[i])
                    b["counts"].append(count)
                    b["seg_lens"].append(seg_len_t)
                seg_start += seg_len

        if not buckets:
            return None

        _t_pack = time.monotonic()
        payloads = []
        for edge_id in sorted(buckets):
            b = buckets[edge_id]
            hidden_packet = torch.cat(b["rows"])
            counts_dev = torch.cat(b["counts"]).to(torch.int32)
            seg_lens_dev = torch.cat(b["seg_lens"]).to(torch.int32)
            meta_dev = torch.cat(b["ranks"] + [counts_dev, seg_lens_dev])
            n_meta = meta_dev.numel()
            pinned = self._lwd_meta_pinned(n_meta, min_depth=len(buckets) * 4)
            pinned[:n_meta].copy_(meta_dev, non_blocking=True)
            payloads.append(
                (edge_id, hidden_packet, pinned[:n_meta], None,
                 list(b["req_ids"]), None)
            )

        self.worker._lwd_meta_ready_event = torch.npu.Event()
        self.worker._lwd_meta_ready_event.record()
        # [Lwd][perf] 采集分段:rank=秩+行收集;pinned=meta 拼包+拷贝
        logger.info(
            "[Lwd][perf] collect edges=%d rows=%d rank=%.2f pinned=%.2f "
            "total=%.2fms",
            len(payloads),
            sum(p[1].shape[0] for p in payloads),
            (_t_pack - _t0) * 1000,
            (time.monotonic() - _t_pack) * 1000,
            (time.monotonic() - _t0) * 1000,
        )
        return payloads

    def _lwd_meta_pinned(self, n: int, min_depth: int = 4):
        """轮换 pinned 缓冲;深度随单步边数放大,避免多边拆分后覆盖
        引擎尚未读完的上一步 meta。"""
        depth = max(4, min_depth)
        ring = getattr(self, "_lwd_pinned_ring", None)
        if ring is None or ring[0].numel() < n or len(ring) < depth:
            ring = [
                torch.empty(max(n, 4096), dtype=torch.int32, pin_memory=True)
                for _ in range(depth)
            ]
            self._lwd_pinned_ring = ring
            self._lwd_pinned_ring_idx = 0
        idx = self._lwd_pinned_ring_idx
        self._lwd_pinned_ring_idx = (idx + 1) % len(ring)
        return ring[idx]

