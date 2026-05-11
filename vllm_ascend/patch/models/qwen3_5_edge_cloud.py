# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
# This file is a part of the vllm-ascend project.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Qwen3.5 边云协同专用 Monkey Patch.

Qwen3.5 的 DecoderLayer.forward 签名与 Llama 不同：
  - Llama: layer(positions, hidden_states, residual, **kwargs)
  - Qwen3.5: layer(hidden_states, residual, positions=None, **kwargs)

为便于理解和学习，另开一套专用实现。逻辑与 Llama 版完全相同，
仅 layer 调用使用位置参数（适配 Qwen3.5 原生顺序）。
"""

from itertools import islice
from typing import TYPE_CHECKING

import torch
from vllm.distributed import get_pp_group
from vllm.model_executor.models.utils import (
    is_pp_missing_parameter,
    make_empty_intermediate_tensors_factory,
    make_layers,
)

if TYPE_CHECKING:
    from vllm.model_executor.models.qwen3_5 import (
        Qwen3_5ForCausalLM,
        Qwen3_5Model,
    )
    from vllm.sequence import IntermediateTensors


def _forward_edge_cloud_segment_qwen3_5(
    self,
    start_layer: int,
    end_layer: int,
    input_ids: torch.Tensor | None,
    positions: torch.Tensor,
    intermediate_tensors: "IntermediateTensors" | None = None,
    inputs_embeds: torch.Tensor | None = None,
    **extra_layer_kwargs,
) -> torch.Tensor | "IntermediateTensors":
    """Qwen3.5 边云协同专用：通用分段 forward.

    三段（A/C/E）统一通过 islice(self.layers, start_layer, end_layer) 遍历。
    与 Llama 版逻辑一致，仅 layer 调用使用 Qwen3.5 原生位置参数顺序。
    """
    num_layers = len(self.layers)
    assert 0 <= start_layer < end_layer <= num_layers

    # 判断当前分段是否是首段（需要 embed）
    is_first_segment = (
        start_layer == 0 and get_pp_group().is_first_rank
    )
    # 判断当前分段是否是尾段（需要 norm）
    is_last_segment = (
        end_layer == num_layers and get_pp_group().is_last_rank
    )

    # Embedding 或恢复中间状态
    if is_first_segment:
        if inputs_embeds is not None:
            hidden_states = inputs_embeds
        else:
            hidden_states = self.embed_input_ids(input_ids)
        residual = None
    else:
        assert intermediate_tensors is not None
        hidden_states = intermediate_tensors["hidden_states"]
        residual = intermediate_tensors["residual"]

    # 【核心】islice 遍历指定范围的层，使用 Qwen3.5 原生位置参数顺序
    for idx, layer in enumerate(
        islice(self.layers, start_layer, end_layer)
    ):
        # Qwen3.5: layer(hidden_states, residual, positions, **kwargs)
        hidden_states, residual = layer(
            hidden_states, residual, positions, **extra_layer_kwargs
        )

    # 如果不是尾段，返回中间状态给下一段/对端节点
    if not is_last_segment:
        return IntermediateTensors(
            {"hidden_states": hidden_states, "residual": residual}
        )

    # 尾段做 norm，输出最终 hidden_states
    hidden_states, _ = self.norm(hidden_states, residual)
    return hidden_states


def _qwen3_5_forward_edge_cloud_segment_wrapper(
    self,
    start_layer: int,
    end_layer: int,
    input_ids: torch.Tensor | None,
    positions: torch.Tensor,
    intermediate_tensors: "IntermediateTensors" | None = None,
    inputs_embeds: torch.Tensor | None = None,
) -> torch.Tensor | "IntermediateTensors":
    """Qwen3_5ForCausalLM 透传至 Qwen3_5Model"""
    return self.model.forward_edge_cloud_segment(
        start_layer, end_layer,
        input_ids, positions, intermediate_tensors, inputs_embeds
    )


# ── Monkey Patch：运行时动态绑定 ──
try:
    from vllm.model_executor.models.qwen3_5 import (
        Qwen3_5ForCausalLM,
        Qwen3_5Model,
    )

    Qwen3_5Model.forward_edge_cloud_segment = (
        _forward_edge_cloud_segment_qwen3_5
    )
    Qwen3_5ForCausalLM.forward_edge_cloud_segment = (
        _qwen3_5_forward_edge_cloud_segment_wrapper
    )
except ImportError:
    # vllm 版本未包含 Qwen3.5 模型定义，跳过 patch
    pass
