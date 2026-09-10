#
# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
# This file is a part of the vllm-ascend project.
"""LWD (layerwise disaggregated) prefill_only mode edge worker."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

import torch

from vllm.v1.core.sched.output import (
    LwdBatchType,
    LwdEmbedBatch,
    LwdUnembedBatch,
)
from vllm.v1.outputs import ModelRunnerOutput
from vllm_ascend.worker.worker import NPUWorker

if TYPE_CHECKING:
    from vllm.v1.core.sched.output import SchedulerOutput
    from vllm.v1.kv_cache_interface import KVCacheSpec

#TODO: import LwdChannelType LwdCommRequest and ...


# ---- token recovery / logit-rank lookup ----
def select_token(logits: torch.Tensor, top_id_th: int) -> int:
    """Map ``top_id_th`` (0-based ordinal in descending logits) back to a token id."""
    logits = logits.reshape(-1)
    return int(torch.argsort(logits, descending=True)[top_id_th].item())


def compute_top_id_th(logits: torch.Tensor, token_id: int) -> int:
    """Look up the descending-logits ordinal of ``token_id`` (cloud side)."""
    logits = logits.reshape(-1)
    order = torch.argsort(logits, descending=True)
    return int((order == token_id).nonzero()[0].item())


# ---- edge worker ----
class LwdEdgeWorker(NPUWorker):
    """LWD edge worker: embed (prefill) + unembed (token recovery) only."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.comm_service = get_lwd_comm_service() # TODO: import lwd_comm

    def get_kv_cache_spec(self) -> dict[str, "KVCacheSpec"]:
        """The LWD edge runs no attention/transformer, so it needs no KV cache."""
        return {}

    def execute_model(self, scheduler_output: "SchedulerOutput"):
        lwd_batch = scheduler_output.lwd_batch
        if lwd_batch.batch_type == LwdBatchType.LWD_EMBED:
            return self._execute_lwd_embed(lwd_batch.seqno, lwd_batch.batch_meta)
        if lwd_batch.batch_type == LwdBatchType.LWD_UNEMBED:
            return self._execute_lwd_unembed(lwd_batch.seqno, lwd_batch.batch_meta)

        return None

    def _execute_lwd_embed(self, seqno: int, batch_meta: LwdEmbedBatch) -> None:
        model = self.model_runner.get_model()
        device = self.model_runner.device
        if not batch_meta.token_ids:
            return

        # Flatten all requests' prompt tokens into one batch (order = req_ids).
        flat_token_ids = [tid for token_ids in batch_meta.token_ids for tid in token_ids]
        token_ids_tensor = torch.tensor(flat_token_ids, dtype=torch.long, device=device)
        embeds = model.embed_input_ids(token_ids_tensor)      # (total_N, H)
        request = LwdCommRequest(
            channel=LwdChannelType.UP,
            op="send",
            num_elements=embeds.numel(),                     # total_N * H
            tensor=embeds,
            seqno=seqno,
            src_dst=self.rank + 1,  # edge rank + 1 = cloud first card
        )
        self.comm_service.submit_send(request)

    def _execute_lwd_unembed(
        self, seqno: int, batch_meta: LwdUnembedBatch
    ) -> ModelRunnerOutput:
        model = self.model_runner.get_model()
        if not batch_meta.req_ids:
            return ModelRunnerOutput(req_ids=[], req_id_to_index={}, sampled_token_ids=[])

        request = LwdCommRequest(
            channel=LwdChannelType.DOWN,
            op="recv",
            num_elements=batch_meta.recv_num_elements,
            seqno=seqno,
            src_dst=self.rank + 1,  # edge rank + 1 = cloud first card
        )
        self.comm_service.submit_recv(request)
        comm_result = self.comm_service.wait()
        while comm_result.status != LwdCommStatus.OK: # TODO: check is the status
            time.sleep(0.001)

        hidden_states = comm_result.tensor
        logits = model.lm_head(hidden_states)

        sampled_token_ids: list[list[int]] = []
        row_offset = 0
        for num_accept_tokens, top_id_ths in zip(
            batch_meta.num_accept_tokens, batch_meta.top_id_ths
        ):
            num_rows = len(top_id_ths)
            token_ids = [
                select_token(logits[row_offset + row], top_id_ths[row])
                for row in range(num_accept_tokens)
            ]
            sampled_token_ids.append(token_ids)
            row_offset += num_rows

        req_id_to_index = {
            req_id: index for index, req_id in enumerate(batch_meta.req_ids)
        }
        return ModelRunnerOutput(
            req_ids=batch_meta.req_ids,
            req_id_to_index=req_id_to_index,
            sampled_token_ids=sampled_token_ids,
        )
