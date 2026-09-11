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

    def init_device(self):
        super().init_device()
        # channel-global DOWN seqno counter (worker layer, send-time alloc)
        self._lwd_down_next_seqno = 0
        # req_id -> posted UP recv futures (consumed by take_lwd_up_embeds)
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

    # ------------------------------------------------------------------ #
    # Engine step wiring                                                  #
    # ------------------------------------------------------------------ #

    def execute_model(self, scheduler_output):
        if self.enable_lwd:
            # Auto-register newly scheduled LWD requests into the
            # collector (so their rows are collected into DOWN packets
            # from the first sampled step).  No control-plane glue
            # needed: scheduled_new_reqs is itself the admission signal.
            collector = self.model_runner.lwd_cloud_collector
            if collector is not None:
                for req_data in scheduler_output.scheduled_new_reqs:
                    collector.open_request(req_data.req_id, 0)
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

        HCCL rendezvous makes the edge's isend wait for this post, so
        no separate notification is needed.  A mismatched/missing batch
        is skipped (non-LWD step or control-plane error)."""
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
        logger.debug(
            "[lwd] posted UP recv batch_seqno=%d reqs=%d tokens=%d",
            batch.seqno, len(meta.req_ids), num_tokens,
        )

    def take_lwd_up_embeds(self, batch_seqno: int):
        """Wait for and return one LWD_EMBED batch's UP embeds.

        Returns ``(embeds, meta)`` where ``embeds`` is the concatenated
        ``[total_tokens, H]`` tensor and ``meta`` is the batch's
        ``LwdEmbedBatch`` (per-request token lists, used by the runner
        to split rows back to requests).  Returns ``(None, None)`` when
        nothing was posted for this seqno."""
        item = self._lwd_up_recv_futures.pop(batch_seqno, None)
        if item is None:
            return None, None
        future, meta = item
        result = future.wait()
        assert result.tensor is not None
        hidden_size = self.model_config.get_hidden_size()
        return result.tensor.view(-1, hidden_size), meta

    @torch.inference_mode()
    def sample_tokens(self, grammar_output: "GrammarOutput") -> ModelRunnerOutput | AsyncModelRunnerOutput:
        output = self.model_runner.sample_tokens(grammar_output)
        # LWD cloud: the DOWN wire carries ONLY the hidden tensor — the
        # runner built it during sampling; we send it here (all LWD wire
        # actions live at the worker layer).  The step metadata (ranks /
        # num_accepted / req_ids) rides back to the scheduler on
        # output.lwd_c2e_meta; the control plane forwards it to the edge
        # ahead of the tensor.
        if self.enable_lwd:
            hidden = self.model_runner.take_lwd_pending_down_packet()
            seqno = None
            if hidden is not None:
                seqno = self._lwd_next_down_seqno()
                get_lwd_comm_service().submit_send(
                    LwdCommRequest(
                        channel=LwdChannelType.DOWN,
                        op="send",
                        num_elements=hidden.numel(),
                        tensor=hidden,
                        seqno=seqno,
                    )
                )
            meta = self.model_runner.take_lwd_pending_c2e_meta()
            if meta is not None and output is not None:
                # Carry the DOWN seqno back so the edge can post its
                # matching irecv (tag-less HCCL pairing).
                if seqno is not None:
                    meta.down_seqno = seqno
                output.lwd_c2e_meta = meta
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
        collector = self.model_runner.lwd_cloud_collector
        embeds_map = self.model_runner.input_batch.req_prompt_embeds
        req_id_to_index = self.model_runner.input_batch.req_id_to_index
        for req_id in finished_req_ids:
            if collector is not None:
                collector.drop(req_id)
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
