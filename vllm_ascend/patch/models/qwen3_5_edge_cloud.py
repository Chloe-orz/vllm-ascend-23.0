#
# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
# This file is a part of the vllm-ascend project.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Edge-cloud collaborative inference patch for Qwen3.5.

复用 Llama 分支的核心逻辑，仅适配 Qwen3.5 的 DecoderLayer 参数顺序：
  - Llama: layer(positions, hidden_states, residual)
  - Qwen3.5: layer(hidden_states, residual, positions)

其余逻辑（embedding、islice、norm、IntermediateTensors 输出）与 Llama 版完全一致。
"""

from itertools import islice
from typing import Any

import torch
from vllm.distributed.parallel_state import get_pp_group
from vllm.model_executor.models.qwen3_5 import Qwen3_5ForCausalLM, Qwen3_5Model
from vllm.sequence import IntermediateTensors


def _forward_edge_cloud_segment_qwen3_5(
    self: Qwen3_5Model,
    start_layer: int,
    end_layer: int,
    input_ids: torch.Tensor | None,
    positions: torch.Tensor,
    intermediate_tensors: IntermediateTensors | None = None,
    inputs_embeds: torch.Tensor | None = None,
    **extra_layer_kwargs: Any,
) -> torch.Tensor | IntermediateTensors:
    """Edge-cloud segment forward for Qwen3.5.

    与 Llama 版唯一区别：layer 调用时使用 Qwen3.5 原生参数顺序
    (hidden_states, residual, positions) 而非 Llama 的
    (positions, hidden_states, residual)。
    """
    num_layers = len(self.layers)
    assert 0 <= start_layer < end_layer <= num_layers, (
        f"Invalid segment range: [{start_layer}, {end_layer}) "
        f"for {num_layers} layers"
    )

    is_first_segment = (start_layer == 0 and get_pp_group().is_first_rank)
    is_last_segment = (end_layer == num_layers and get_pp_group().is_last_rank)

    # ----- Embedding or restore intermediate state -----
    if is_first_segment:
        if inputs_embeds is not None:
            hidden_states = inputs_embeds
        else:
            embed_fn = getattr(self, "embed_input_ids", None)
            if embed_fn is not None:
                hidden_states = embed_fn(input_ids)
            else:
                hidden_states = self.embed_tokens(input_ids)
        residual = None
    else:
        assert intermediate_tensors is not None, (
            "intermediate_tensors required for non-first segment"
        )
        hidden_states = intermediate_tensors["hidden_states"]
        residual = intermediate_tensors["residual"]

    # ----- Execute layers in [start_layer, end_layer) -----
    # 关键适配：Qwen3.5 原生参数顺序为 (hidden_states, residual, positions)
    for idx, layer in enumerate(islice(self.layers, start_layer, end_layer)):
        hidden_states, residual = layer(
            hidden_states, residual, positions, **extra_layer_kwargs
        )

    # ----- Return intermediate state or final hidden_states -----
    if not is_last_segment:
        return IntermediateTensors(
            {"hidden_states": hidden_states, "residual": residual}
        )

    # Last segment: apply norm
    hidden_states, _ = self.norm(hidden_states, residual)
    return hidden_states


def _qwen3_5_forward_edge_cloud_segment_wrapper(
    self: Qwen3_5ForCausalLM,
    start_layer: int,
    end_layer: int,
    input_ids: torch.Tensor | None,
    positions: torch.Tensor,
    intermediate_tensors: IntermediateTensors | None = None,
    inputs_embeds: torch.Tensor | None = None,
) -> torch.Tensor | IntermediateTensors:
    """Qwen3_5ForCausalLM-style wrapper that delegates to Qwen3_5Model."""
    return self.model.forward_edge_cloud_segment(
        start_layer,
        end_layer,
        input_ids,
        positions,
        intermediate_tensors,
        inputs_embeds,
    )


# ── Monkey Patch: runtime binding ──
Qwen3_5Model.forward_edge_cloud_segment = _forward_edge_cloud_segment_qwen3_5
Qwen3_5ForCausalLM.forward_edge_cloud_segment = _qwen3_5_forward_edge_cloud_segment_wrapper
