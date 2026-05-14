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

"""Edge-cloud collaborative inference patch for standard Llama-style models.

This module monkey-patches ``forward_edge_cloud_segment`` onto
``LlamaModel`` and ``LlamaForCausalLM`` so that the edge-cloud
ModelRunner can execute arbitrary layer ranges without modifying upstream vLLM.

Unlike DeepSeek-V4 which uses ``layer(x, positions, input_ids)`` signature,
standard Llama models use ``layer(positions, hidden_states, residual)``.
"""

from itertools import islice
from typing import Any

import torch
from vllm.distributed.parallel_state import get_pp_group
from vllm.model_executor.models.llama import LlamaForCausalLM, LlamaModel
from vllm.sequence import IntermediateTensors


def _forward_edge_cloud_segment(
    self: LlamaModel,
    start_layer: int,
    end_layer: int,
    input_ids: torch.Tensor | None,
    positions: torch.Tensor,
    intermediate_tensors: IntermediateTensors | None = None,
    inputs_embeds: torch.Tensor | None = None,
    **extra_layer_kwargs: Any,
) -> torch.Tensor | IntermediateTensors:
    """Edge-cloud segment forward for standard Llama-style models.

    Args:
        start_layer: First layer index to execute (inclusive).
        end_layer: Last layer index to execute (exclusive).
        input_ids: Token IDs for embedding (first segment).
        positions: Position IDs.
        intermediate_tensors: Carries ``hidden_states`` and ``residual``
            from the previous segment.
        inputs_embeds: Optional pre-computed embeddings.

    Returns:
        ``IntermediateTensors`` for non-last segments, or final
        ``hidden_states`` for the last segment.
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
            # Try model-specific embed method first, fallback to embed_tokens
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
    for idx, layer in enumerate(islice(self.layers, start_layer, end_layer)):
        hidden_states, residual = layer(
            positions, hidden_states, residual, **extra_layer_kwargs
        )

    # ----- Return intermediate state or final hidden_states -----
    if not is_last_segment:
        return IntermediateTensors(
            {"hidden_states": hidden_states, "residual": residual}
        )

    # Last segment: apply norm
    hidden_states, _ = self.norm(hidden_states, residual)
    return hidden_states


def _llama_forward_edge_cloud_segment_wrapper(
    self: LlamaForCausalLM,
    start_layer: int,
    end_layer: int,
    input_ids: torch.Tensor | None,
    positions: torch.Tensor,
    intermediate_tensors: IntermediateTensors | None = None,
    inputs_embeds: torch.Tensor | None = None,
) -> torch.Tensor | IntermediateTensors:
    """LlamaForCausalLM-style wrapper that delegates to LlamaModel."""
    return self.model.forward_edge_cloud_segment(
        start_layer,
        end_layer,
        input_ids,
        positions,
        intermediate_tensors,
        inputs_embeds,
    )


# ── Monkey Patch: runtime binding ──
LlamaModel.forward_edge_cloud_segment = _forward_edge_cloud_segment
LlamaForCausalLM.forward_edge_cloud_segment = _llama_forward_edge_cloud_segment_wrapper
