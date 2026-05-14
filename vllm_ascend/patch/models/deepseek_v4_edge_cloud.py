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

"""Edge-cloud collaborative inference patch for DeepSeek-V4.

This module monkey-patches ``forward_edge_cloud_segment`` onto
``DeepseekV4Model`` and ``DeepseekV4ForCausalLM`` so that the edge-cloud
ModelRunner can execute arbitrary layer ranges without modifying upstream vLLM.

Key differences from standard Llama-style models:
  - DecoderLayer signature: ``layer(x, positions, input_ids)``
  - Residual managed internally via ``hc_pre`` / ``hc_post``
  - Embedding needs ``unsqueeze(-2).repeat(1, hc_mult, 1)``
  - Tail segment needs ``hc_head()`` + ``norm()``
  - Intermediate tensors carry ``input_ids`` for Hash MoE routing
"""

from itertools import islice
from typing import Any

import torch
import torch.nn as nn
from vllm.distributed.parallel_state import get_pp_group
from vllm.model_executor.models.deepseek_v4 import (
    DeepseekV4ForCausalLM,
    DeepseekV4Model,
    hc_head,
)
from vllm.sequence import IntermediateTensors


class DeepSeekV4MissingLayer(nn.Module):
    """Placeholder layer for non-local layers in DeepSeek-V4 edge-cloud inference.

    ``PPMissingLayer.forward(*args)`` returns ``args[0]``, which happens to be
    safe for V4's ``layer(x, positions, input_ids)`` call (returns ``x``).
    This class is provided for explicit semantic clarity.
    """

    def __init__(self, *args, **kwargs):
        super().__init__()

    def forward(self, x: torch.Tensor, positions: torch.Tensor,
                input_ids: torch.Tensor | None, **kwargs) -> torch.Tensor:
        return x


def _forward_edge_cloud_segment_v4(
    self: DeepseekV4Model,
    start_layer: int,
    end_layer: int,
    input_ids: torch.Tensor | None,
    positions: torch.Tensor,
    intermediate_tensors: IntermediateTensors | None = None,
    inputs_embeds: torch.Tensor | None = None,
    **extra_layer_kwargs: Any,
) -> torch.Tensor | IntermediateTensors:
    """Edge-cloud segment forward for DeepSeek-V4.

    Args:
        start_layer: First layer index to execute (inclusive).
        end_layer: Last layer index to execute (exclusive).
        input_ids: Token IDs for embedding (first segment) or Hash MoE routing.
        positions: Position IDs.
        intermediate_tensors: Carries ``hidden_states`` and optionally
            ``input_ids`` from the previous segment.
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
            hidden_states = self.embed_input_ids(input_ids)
        hidden_states = hidden_states.unsqueeze(-2).repeat(1, self.hc_mult, 1)

        if self.use_mega_moe and input_ids is not None:
            input_ids = input_ids.to(torch.int64)
    else:
        assert intermediate_tensors is not None, (
            "intermediate_tensors required for non-first segment in V4"
        )
        hidden_states = intermediate_tensors["hidden_states"]
        # input_ids is optional: non-first segment may not need Hash MoE routing
        input_ids = intermediate_tensors.get("input_ids")

    # ----- Execute layers in [start_layer, end_layer) -----
    for idx, layer in enumerate(islice(self.layers, start_layer, end_layer)):
        hidden_states = layer(
            hidden_states,
            positions,
            input_ids,
        )

    # ----- Return intermediate state or final hidden_states -----
    # In the "head-3 / tail-1" edge-cloud scheme, all Hash MoE layers reside
    # on the edge side (segment A).  The cloud side (segment C) and the edge
    # tail (segment E) do not need ``input_ids``.  Therefore we only pass
    # ``hidden_states`` across the network to avoid leaking token IDs.
    if not is_last_segment:
        return IntermediateTensors({"hidden_states": hidden_states})

    # Last segment: stash pre-hc_head residual for MTP, then hc_head + norm
    num_tokens = hidden_states.shape[0]
    self._mtp_hidden_buffer[:num_tokens].copy_(hidden_states.flatten(1))

    hidden_states = hc_head(
        hidden_states,
        self.hc_head_fn,
        self.hc_head_scale,
        self.hc_head_base,
        self.rms_norm_eps,
        self.hc_eps,
    )
    hidden_states = self.norm(hidden_states)
    return hidden_states


def _deepseek_v4_forward_edge_cloud_segment_wrapper(
    self: DeepseekV4ForCausalLM,
    start_layer: int,
    end_layer: int,
    input_ids: torch.Tensor | None,
    positions: torch.Tensor,
    intermediate_tensors: IntermediateTensors | None = None,
    inputs_embeds: torch.Tensor | None = None,
) -> torch.Tensor | IntermediateTensors:
    """LlamaForCausalLM-style wrapper that delegates to DeepseekV4Model."""
    return self.model.forward_edge_cloud_segment(
        start_layer,
        end_layer,
        input_ids,
        positions,
        intermediate_tensors,
        inputs_embeds,
    )


# ── Monkey Patch: runtime binding ──
DeepseekV4Model.forward_edge_cloud_segment = _forward_edge_cloud_segment_v4
DeepseekV4ForCausalLM.forward_edge_cloud_segment = (
    _deepseek_v4_forward_edge_cloud_segment_wrapper
)
