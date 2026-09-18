# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""prefill_only LWD model runner subclass (cloud side, token_id 版).

token_id 回传版:采样 token 经 c2e 通告直付边侧,云侧无 DOWN 采集
(原 collect/rank-replay 代码整体退场)。runner 仅保留远端 prompt
embeds 的设备侧注入(UP 通道消费,prefill 前向仍需)。

Selected via ``LwdCloudWorker`` (worker_cls), which swaps the model
runner class at init_device when ``lwd_config`` enables prefill_only.
"""

from __future__ import annotations

import time

import torch
from vllm.logger import logger

from vllm_ascend.worker.model_runner_v1 import NPUModelRunner


class LwdCloudModelRunner(NPUModelRunner):
    """NPUModelRunner + prefill_only LWD cloud-side runner logic."""

    def __init__(self, vllm_config, device, worker=None):
        super().__init__(vllm_config, device)
        self.worker = worker  # LwdCloudWorker ref (UP recv futures live there)

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

        for batch_seqno in list(posted.keys()):
            item = worker._lwd_up_recv_futures.pop(batch_seqno, None)
            if item is None:
                continue
            future, meta = item
            _t_wait = time.monotonic()
            import torch.distributed as dist
            _lwd_cfg = worker.parallel_config.lwd_config
            _is_endpoint = worker.rank == _lwd_cfg.edge_npu_count
            numel = sum(len(t) for t in meta.token_ids) * hidden_size
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
                # demo 同款:直接用框架 TP 通信域(建组顺序由框架保证,
                # PD 分离路径已验证),不再使用自建 _LWD_EMBED_BCAST_GROUP。
                work = dist.broadcast(
                    up_flat,
                    src=_tp.ranks[0],
                    group=_tp.device_group,
                    async_op=True,
                )
                work.wait()  # 桥接广播完成到当前(计算)流,后续 copy 有序
            logger.info(
                "[Lwd][perf] cloud up-recv-wait seqno=%s dur=%.2fms",
                batch_seqno, (time.monotonic() - _t_wait) * 1000,
            )
            embeds = up_flat.view(-1, hidden_size)
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
                row += n
            # 跨流生命周期登记:端点 recv buffer 由通道流分配与复用
            # (同尺寸 chunk 下分配器几乎总给同一块),本步 copy 在计算流。
            # 不登记 record_stream,分配器可在本批 copy 尚未执行时把块交给
            # 下一 seqno 的 irecv 覆写——深异步队列下表现为跨 seqno 串
            # 数据(多请求乱码)。登记后复用即被正确排序。
            up_flat.record_stream(torch.npu.current_stream())

