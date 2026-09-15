# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""prefill_only LWD (edge-cloud) worker subclass.

All LWD worker-side logic lives here (moved out of ``worker.py``):
init bring-up of the duplex channels + recv managers, the EDGE_EMBED
dispatch hook, the cloud finished-flush, and the
DOWN send (draining the runner's per-step hidden payload + attaching
``lwd_c2e_meta`` to the ModelRunnerOutput).

Selected via ``parallel_config.worker_cls`` (see platform.py:
``vllm_ascend.worker.lwd_cloud_worker.LwdCloudWorker``) when
``lwd_config`` enables prefill_only.
"""

from __future__ import annotations

import torch
from vllm.logger import logger
from vllm.v1.core.sched.output import GrammarOutput  # noqa: F401  (type)
from vllm.v1.outputs import AsyncModelRunnerOutput, ModelRunnerOutput
from vllm.distributed import (
    ensure_model_parallel_initialized,
    init_distributed_environment,
)
from vllm.distributed.ec_transfer import ensure_ec_transfer_initialized

from vllm_ascend.batch_invariant import init_batch_invariance
from vllm_ascend.distributed.lwd_comm.lwd_parallel_init import (
    init_lwd_ascend_model_parallel,
)
from vllm_ascend.distributed.lwd_comm.service import get_lwd_comm_service
from vllm_ascend.distributed.lwd_comm.types import LwdChannelType, LwdCommRequest

# ops 须先于 model_runner 链初始化，否则 device_op 与 ops 包循环导入
#（对齐 worker.py 的导入顺序）
import vllm_ascend.ops  # noqa: F401
from vllm_ascend.worker.lwd_cloud.lwd_cloud_model_runner import LwdCloudModelRunner
from vllm_ascend.worker.worker import NPUWorker


class LwdCloudWorker(NPUWorker):
    """NPUWorker + LWD data-plane wiring (cloud side only).

    This subclass is selected by ``platform.py`` only when the LWD
    deployment enables LWD on a cloud process, so no role/mode checks
    are needed here — ``self.enable_lwd`` (set by NPUWorker.__init__
    from vllm_config.lwd_config) is the single switch."""

    def _init_worker_distributed_environment(self) -> None:
        """覆写原生入口(worker.py):ascend 侧并行组按 Lwd 布局构建。

        vllm 侧分组由 parallel_state.initialize_model_parallel 的 Lwd
        分支完成;ascend 侧原生 init_ascend_model_parallel 按 (dp, pp,
        pcp, tp) 均匀网格切分,表达不了非对称边云拓扑,故以
        init_lwd_ascend_model_parallel 替代(构建 MC2 等组后注入)。
        其余步骤与原生 worker.py 保持一致。"""
        init_batch_invariance()
        init_distributed_environment(
            self.parallel_config.world_size,
            self.rank,
            self.distributed_init_method,
            self.local_rank,
            "hccl",
        )
        ensure_model_parallel_initialized(
            self.parallel_config.tensor_parallel_size,
            self.parallel_config.pipeline_parallel_size,
            self.parallel_config.prefill_context_parallel_size,
            self.parallel_config.decode_context_parallel_size,
        )
        init_lwd_ascend_model_parallel(self.parallel_config)
        ensure_ec_transfer_initialized(self.vllm_config)

    def init_device(self):
        super().init_device()
        # channel-global DOWN seqno counter (worker layer, send-time alloc)
        self._lwd_down_next_seqno = 0
        # req_id -> posted UP recv futures (consumed by the runner's device-side inject)
        self._lwd_up_recv_futures: dict[str, list] = {}

        if not self.enable_lwd:
            return
        if self.use_v2_model_runner:
            # The LWD hooks live on the V1 model runner; the V2 runner
            # (separate class) lacks them entirely — fail fast at bring-up
            # instead of AttributeError at first request.
            raise RuntimeError(
                "prefill_only (LWD) data plane requires the V1 model runner; "
                "use_v2_model_runner is not supported"
            )
        # Swap in the LWD model runner BEFORE any model load/usage.
        # The cloud feeds on edge-computed prompt embeddings (no token
        # ids on its input), so the native prompt-embeds path must be
        # enabled for the runner to allocate inputs_embeds buffers.
        self.model_config.enable_prompt_embeds = True
        self.model_runner = LwdCloudModelRunner(
            self.vllm_config, self.device, worker=self
        )
        from vllm_ascend.distributed import lwd_wire

        lwd_wire.init_lwd_duplex_channels()
        self._register_lwd_prompt_embeds_provider()

    def load_model(self):
        """加载后打实际切片:层数/首末层名/pp 切层参数,启动期即可裁决
        半模型嫌疑(全量且从 layer 0 起 = 正常;减半/起始非 0 = pp 切错)。"""
        super().load_model()
        model = self.model_runner.get_model()
        backbone = getattr(model, "model", model)
        layers = getattr(backbone, "layers", None) or getattr(
            backbone, "decoder_layers", None
        )
        pc = self.vllm_config.parallel_config
        layer_names = [
            n for n, _ in model.named_modules()
            if n.count("layers.") == 1 and n.endswith(tuple("0123456789"))
        ]
        logger.info(
            "[Lwd][cloud-model] loaded layers=%s first=%s last=%s "
            "(config pp=%d tp=%d, my rank=%d) — 全量应覆盖 layer 0 起的全部层",
            len(layers) if layers is not None else "?",
            layer_names[0] if layer_names else "?",
            layer_names[-1] if layer_names else "?",
            pc.pipeline_parallel_size, pc.tensor_parallel_size, self.rank,
        )

    # ------------------------------------------------------------------ #
    # Engine step wiring                                                  #
    # ------------------------------------------------------------------ #

    def execute_model(self, scheduler_output):
        if self.enable_lwd:
            # cloud: post the exact-size UP irecv for every incoming
            # LWD_EMBED batch (control info rides scheduler_output.lwd_batch).
            self._lwd_up_post_recvs(scheduler_output)

        # cloud: finished requests trigger local cleanup (collector
        # bookkeeping + UP chunk table); finished_req_ids is the
        # engine's own liveness signal.
        if scheduler_output.finished_req_ids:
            self._lwd_cloud_flush_finished(scheduler_output.finished_req_ids)

        get_lwd_comm_service().poll_completions()  # lazy keepalive reap
        return super().execute_model(scheduler_output)

    def _lwd_up_post_recvs(self, scheduler_output) -> None:
        """Post the UP irecv for an incoming LWD_EMBED batch.

        All control info rides the SchedulerOutput (edge -> cloud
        control plane fills it in):
          * ``scheduler_output.lwd_batch.batch_type == LWD_EMBED``
          * ``batch.seqno`` — the edge dispatch seqno of THIS batch
            (one UP hidden message per dispatch)
          * ``batch.batch_meta.token_ids`` — per-request token lists;
            the batch's hidden rows are the concatenation of these
            prompts, so the recv size is ``sum(len) x H``.

        Every cloud rank irecvs its own copy directly from the edge
        (channel._wire_recv UP = plain P2P pairing, no leader relay /
        no collective fanout).  HCCL rendezvous makes the edge's isends
        wait for these posts, so no separate notification is needed.
        A mismatched/missing batch is skipped (non-LWD step or
        control-plane error)."""
        from vllm.v1.core.sched.output import LwdBatchType

        batch = getattr(scheduler_output, "lwd_batch", None)
        if batch is None or batch.batch_type is not LwdBatchType.LWD_EMBED:
            return
        meta = batch.batch_meta
        if meta is None or not meta.req_ids:
            return
        hidden_size = self.model_config.get_hidden_size()
        num_tokens = sum(len(t) for t in meta.token_ids)
        if num_tokens <= 0:
            return
        future = get_lwd_comm_service().submit_recv(
            LwdCommRequest(
                channel=LwdChannelType.UP,
                op="recv",
                num_elements=num_tokens * hidden_size,
                seqno=batch.seqno,
            )
        )
        self._lwd_up_recv_futures[batch.seqno] = (future, meta)
        logger.info(
            "[Lwd][cloud-worker] UP recv posted seqno=%d reqs=%d tokens=%d",
            batch.seqno, len(meta.req_ids), num_tokens,
        )

    @torch.inference_mode()
    def sample_tokens(self, grammar_output: "GrammarOutput") -> ModelRunnerOutput | AsyncModelRunnerOutput:
        output = self.model_runner.sample_tokens(grammar_output)
        # rank-replay DOWN:hidden 包通道异步发送;meta 的物化(等事件+
        # 读值)不在此处做——RPC 忙等线程必须即刻返回,否则下一步
        # execute_model 派发被推迟,设备步间出现空泡(单请求 +3ms 的
        # 根源)。物化挂到 async_output 侧线程的 get_output 钩子上,
        # 与上游 sampled_token_ids 同款时序。
        if self.enable_lwd:
            payload = self.model_runner.take_lwd_pending_down_payload()
            if payload is not None and output is not None:
                hidden, meta_host, meta_ev, req_ids, _accepted = payload
                seqno = self._lwd_next_down_seqno()
                logger.info(
                    "[Lwd][cloud-worker] DOWN send seqno=%d numel=%d",
                    seqno, hidden.numel(),
                )
                get_lwd_comm_service().submit_send(
                    LwdCommRequest(
                        channel=LwdChannelType.DOWN,
                        op="send",
                        num_elements=hidden.numel(),
                        tensor=hidden,
                        seqno=seqno,
                    )
                )
                target = getattr(output, "_model_runner_output", output)

                def _lwd_finalize_meta(
                    _target=target, _buf=meta_host, _ev=meta_ev,
                    _req_ids=req_ids, _seqno=seqno, _numel=hidden.numel(),
                ):
                    """meta 物化:等 D2H 落地后读主机内存。

                    D2H 已在 collect 时随步入队(默认流,环版同款快路径);
                    _buf 是每步私有 pinned 张量,无共享缓冲。本函数只能
                    被 MQ 发送路径调用(async:get_output 侧线程;
                    非 async:本线程兜底),pickle 之前物化为纯数值。"""
                    from vllm.v1.outputs import LwdC2eMeta

                    _ev.synchronize()
                    n = len(_req_ids)
                    meta_host = _buf.tolist()
                    total = len(meta_host)
                    seg_lens = meta_host[total - n :]
                    counts = meta_host[total - 2 * n : total - n]
                    ranks_flat = meta_host[: total - 2 * n]
                    top_id_ths, off = [], 0
                    for s in seg_lens:
                        top_id_ths.append(ranks_flat[off : off + s])
                        off += s
                    if off != len(ranks_flat) or any(c == 0 for c in counts):
                        # 布局错位自检(修复后不应出现;出现即三块未对齐或
                        # 环被覆盖,直接证据链锚点)
                        logger.warning(
                            "[Lwd][meta-mismatch] seqno=%s ranks=%d "
                            "consumed=%d counts=%s seg_lens=%s",
                            _seqno, len(ranks_flat), off, counts, seg_lens,
                        )
                    _target.lwd_c2e_meta = LwdC2eMeta(
                        hidden_num_elements=_numel,
                        top_id_ths=top_id_ths,
                        num_accepted_tokens=counts,
                        req_ids=_req_ids,
                        down_seqno=_seqno,
                    )

                if isinstance(output, AsyncModelRunnerOutput):
                    # async 调度:覆写实例 get_output,enqueue_output 在
                    # 侧线程调用它——先物化上游输出,再挂 meta,之后才
                    # 进 MQ pickle。RPC 忙等线程不参与任何设备等待。
                    _orig_get_output = output.get_output

                    def _get_output_with_meta(_orig=_orig_get_output):
                        inner = _orig()
                        _lwd_finalize_meta()
                        return inner

                    output.get_output = _get_output_with_meta
                else:
                    # 非 async 调度兜底:enqueue_output 前无侧线程可用,
                    # 在本线程物化(正确性与旧同步版一致)
                    _lwd_finalize_meta()
        return output

    # ------------------------------------------------------------------ #
    # LWD housekeeping (control-plane glue)                               #
    # ------------------------------------------------------------------ #

    def _lwd_cloud_flush_finished(self, finished_req_ids) -> None:
        """Cloud side (streaming): a finished request's DOWN stream simply
        STOPS (its last step packet already went out with that step).
        No FIN packet -- request termination is signaled by the control
        plane (v2.6).  Here we drop the collector bookkeeping —
        finished_req_ids is the engine's own liveness signal, so this
        cleanup does not depend on the control plane.  Also releases the
        request's prompt-embeds assembly buffer (backstop for abort
        mid-prefill; normal prefill completion frees it in the runner's
        ``_lwd_release_consumed_prompt_embeds``)."""
        embeds_map = self.model_runner.input_batch.req_prompt_embeds
        req_id_to_index = self.model_runner.input_batch.req_id_to_index
        logger.info(
            "[Lwd][cloud-worker] flush finished reqs=%s", list(finished_req_ids)
        )
        for req_id in finished_req_ids:
            idx = req_id_to_index.get(req_id)
            if idx is not None:
                embeds_map.pop(idx, None)

    def _register_lwd_prompt_embeds_provider(self) -> None:
        """Wire the draft proposer's first-pass prompt-embeds provider.

        The provider resolves the request's prompt embeds from the
        runner's ``input_batch.req_prompt_embeds`` (already injected by
        ``_lwd_inject_remote_embeds`` during prefill); a missing entry
        (not scheduled / not LWD) returns None and the proposer falls
        back to the token-id path.
        """
        from vllm_ascend.spec_decode.llm_base_proposer import (
            AscendSpecDecodeBaseProposer,
        )

        runner = self.model_runner

        def _lwd_prompt_embeds_provider(req_id: str):
            idx = runner.input_batch.req_id_to_index.get(req_id)
            if idx is None:
                return None
            return runner.input_batch.req_prompt_embeds.get(idx)

        AscendSpecDecodeBaseProposer.set_lwd_prompt_embeds_provider(
            _lwd_prompt_embeds_provider
        )

    def _lwd_next_down_seqno(self) -> int:
        seqno = self._lwd_down_next_seqno
        self._lwd_down_next_seqno += 1
        return seqno
