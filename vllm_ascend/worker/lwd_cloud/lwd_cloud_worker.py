# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""prefill_only LWD (edge-cloud) worker subclass.

All LWD worker-side logic lives here (moved out of ``worker.py``):
init bring-up of the duplex channels + recv managers, the EDGE_EMBED
dispatch hook, the cloud finished-flush, the abort hook, and the
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

from vllm_ascend.ascend_config import get_ascend_config
from vllm_ascend.distributed.lwd_comm.service import get_lwd_comm_service
from vllm_ascend.distributed.lwd_comm.types import LwdChannelType, LwdCommRequest
from vllm_ascend.worker.lwd_cloud.lwd_cloud_model_runner import LwdCloudModelRunner
from vllm_ascend.worker.worker import NPUWorker


class LwdCloudWorker(NPUWorker):
    """NPUWorker + prefill_only LWD data-plane wiring (cloud & edge)."""

    def init_device(self):
        super().init_device()
        self._lwd_cfg = get_ascend_config().lwd_config
        # channel-global DOWN seqno counter (worker layer, send-time alloc)
        self._lwd_down_next_seqno = 0
        self._lwd_edge_sent_embeds: dict[str, int] = {}  # req_id -> chunks sent
        self._lwd_edge_aborted: set[str] = set()         # aborted req tombstones
        if not self._lwd_cfg.is_prefill_only:
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
        self.model_runner = LwdCloudModelRunner(self.vllm_config, self.device)
        from vllm_ascend.distributed import lwd_wire
        from vllm_ascend.worker.lwd_cloud.lwd_recv_manager import init_lwd_recv_managers

        lwd_wire.init_lwd_duplex_channels()
        init_lwd_recv_managers(self.model_config.get_hidden_size())

    # ------------------------------------------------------------------ #
    # Engine step wiring                                                  #
    # ------------------------------------------------------------------ #

    def execute_model(self, scheduler_output):
        # prefill_only cloud: finished requests trigger local cleanup
        # (collector bookkeeping + UP chunk table); finished_req_ids is
        # the engine's own liveness signal.
        if (self._lwd_cfg.is_cloud_node
                and scheduler_output.finished_req_ids):
            self._lwd_cloud_flush_finished(scheduler_output.finished_req_ids)

        if self._lwd_cfg.is_prefill_only:
            get_lwd_comm_service().poll_completions()  # lazy keepalive reap
        return super().execute_model(scheduler_output)

    @torch.inference_mode()
    def sample_tokens(self, grammar_output: "GrammarOutput") -> ModelRunnerOutput | AsyncModelRunnerOutput:
        output = self.model_runner.sample_tokens(grammar_output)
        # LWD cloud: the DOWN wire carries ONLY the hidden tensor — the
        # runner built it during sampling; we send it here (all LWD wire
        # actions live at the worker layer).  The step metadata (ranks /
        # num_accepted / req_ids) rides back to the scheduler on
        # output.lwd_c2e_meta; the control plane forwards it to the edge
        # ahead of the tensor.
        if self._lwd_cfg.is_cloud_node:
            hidden = self.model_runner.take_lwd_pending_down_packet()
            if hidden is not None:
                get_lwd_comm_service().submit_send(
                    LwdCommRequest(
                        channel=LwdChannelType.DOWN,
                        op="send",
                        num_elements=hidden.numel(),
                        tensor=hidden,
                        seqno=self._lwd_next_down_seqno(),
                    )
                )
            meta = self.model_runner.take_lwd_pending_c2e_meta()
            if meta is not None and output is not None:
                output.lwd_c2e_meta = meta
        return output

    # ------------------------------------------------------------------ #
    # LWD housekeeping (control-plane glue)                               #
    # ------------------------------------------------------------------ #

    def _lwd_cloud_flush_finished(self, finished_req_ids) -> None:
        """Cloud side (streaming): a finished request's DOWN stream simply
        STOPS (its last step packet already went out with that step).
        No FIN packet -- request termination is signaled by the control
        plane (v2.6).  Here we drop the collector bookkeeping AND release
        the UP-side chunk table (prompt embeds recv buffers on device) —
        finished_req_ids is the engine's own liveness signal, so this
        cleanup does not depend on the control plane."""
        from vllm_ascend.worker.lwd_cloud.lwd_recv_manager import (
            get_lwd_up_recv_manager,
        )

        collector = self.model_runner.lwd_cloud_collector
        up_manager = get_lwd_up_recv_manager()
        for req_id in finished_req_ids:
            if collector is not None:
                collector.drop(req_id)
            up_manager.pop_request(req_id)

    def abort_lwd_request(self, req_id: str) -> None:
        """prefill_only control-plane abort hook (streaming semantics).

        MUST be driven on BOTH peers for the same request:
          * edge: mark the request aborted on the DOWN recv side (its
            in-flight rows ride inside shared per-step batch packets and
            are filtered at demux — DOWN seqnos are dense by
            construction, so there is NO seqno to skip) and clear the
            per-request send bookkeeping (unsent embed chunks are simply
            never dispatched);
          * cloud: drop the UP recv side (skips the recv seqnos of
            chunks the edge will never send) and destroy the collector
            bookkeeping — the request's rows simply stop appearing in
            the per-step batch packets (they are built from live
            registrations only, and the DOWN seqno is assigned at send
            time from a channel-global counter, so an aborted request
            leaves NO hole in the send sequence).

        A send already posted to HCCL cannot be un-posted — the control
        plane must abort before dispatching the request's tail.
        """
        if not self._lwd_cfg.is_prefill_only:
            return
        from vllm_ascend.worker.lwd_cloud.lwd_recv_manager import (
            get_lwd_down_recv_manager,
            get_lwd_up_recv_manager,
        )

        if self._lwd_cfg.is_edge_node:
            self._lwd_edge_aborted.add(req_id)
            self._lwd_edge_sent_embeds.pop(req_id, None)
            get_lwd_down_recv_manager().drop(req_id)
        elif self._lwd_cfg.is_cloud_node:
            get_lwd_up_recv_manager().drop(req_id)
            collector = self.model_runner.lwd_cloud_collector
            if collector is not None:
                collector.drop(req_id)

    def _lwd_next_down_seqno(self) -> int:
        seqno = self._lwd_down_next_seqno
        self._lwd_down_next_seqno += 1
        return seqno
