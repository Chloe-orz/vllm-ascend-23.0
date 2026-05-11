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

"""Llama 模型的边云协同 Monkey Patch。

通过运行时动态绑定，为 LlamaModel / LlamaForCausalLM 新增
`forward_edge_cloud_segment(start_layer, end_layer)` 方法，
无需修改上游 vllm 源码。

加载方式：
    import vllm_ascend.patch.models.llama_edge_cloud  # noqa

当 edge_cloud_config.enabled 为 True 时，patch 在 vllm-ascend patch 初始化阶段自动加载。
"""

from itertools import islice

import torch
from vllm.distributed.parallel_state import get_pp_group
from vllm.model_executor.models.llama import LlamaModel, LlamaForCausalLM
from vllm.sequence import IntermediateTensors


def _forward_edge_cloud_segment(
    self,
    start_layer: int,
    end_layer: int,
    input_ids: torch.Tensor | None,
    positions: torch.Tensor,
    intermediate_tensors: IntermediateTensors | None = None,
    inputs_embeds: torch.Tensor | None = None,
    **extra_layer_kwargs,
) -> torch.Tensor | IntermediateTensors:
    """边云协同专用：通用分段 forward。

    三段（A/C/E）统一通过 islice(self.layers, start_layer, end_layer) 遍历，
    层范围由调用方参数决定，支持任意 K 配置。

    典型配置（K=1，首尾各 1 层）：
      Segment A: start=0,   end=1      → islice(layers, 0, 1)    → Layer 0
      Segment C: start=1,   end=N-1    → islice(layers, 1, N-1)  → Layers 1~N-2
      Segment E: start=N-1, end=N      → islice(layers, N-1, N)  → Layer N-1

    典型配置（K=2，首尾各 2 层）：
      Segment A: start=0, end=2        → islice(layers, 0, 2)    → Layers 0,1
      Segment C: start=2, end=N-2      → islice(layers, 2, N-2)  → Layers 2~N-3
      Segment E: start=N-2, end=N      → islice(layers, N-2, N)  → Layers N-2,N-1
    """
    num_layers = len(self.layers)
    assert 0 <= start_layer < end_layer <= num_layers, (
        f"Invalid layer range: start={start_layer}, end={end_layer}, "
        f"num_layers={num_layers}"
    )

    # 判断当前分段是否是首段（需要 embed）
    # start_layer == 0 且当前是 PP 第一个 rank 时，执行 Embedding
    is_first_segment = (
        start_layer == 0 and get_pp_group().is_first_rank
    )
    # 判断当前分段是否是尾段（需要 norm）
    # end_layer == num_layers 且当前是 PP 最后一个 rank 时，执行 Norm
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
        assert intermediate_tensors is not None, (
            "intermediate_tensors must be provided for non-first segment"
        )
        hidden_states = intermediate_tensors["hidden_states"]
        residual = intermediate_tensors["residual"]

    # 【核心】islice 遍历指定范围的层
    # Segment A: islice(0, K)       → Layers 0 ~ K-1
    # Segment C: islice(K, N-K)     → Layers K ~ N-K-1
    # Segment E: islice(N-K, N)     → Layers N-K ~ N-1
    #
    # 使用关键字参数调用 layer，兼容不同模型的参数顺序：
    # - 标准 Llama/Qwen2/DeepSeek-V2/V3: layer(positions, hidden_states, residual)
    # - Qwen3.5: layer(hidden_states, residual, positions=None)
    for idx, layer in enumerate(
        islice(self.layers, start_layer, end_layer)
    ):
        hidden_states, residual = layer(
            positions=positions,
            hidden_states=hidden_states,
            residual=residual,
            **extra_layer_kwargs,
        )

    # 如果不是尾段，返回中间状态给下一段/对端节点
    if not is_last_segment:
        return IntermediateTensors(
            {"hidden_states": hidden_states, "residual": residual}
        )

    # 尾段做 norm，输出最终 hidden_states
    hidden_states, _ = self.norm(hidden_states, residual)
    return hidden_states


def _llama_forward_edge_cloud_segment_wrapper(
    self,
    start_layer: int,
    end_layer: int,
    input_ids: torch.Tensor | None,
    positions: torch.Tensor,
    intermediate_tensors: IntermediateTensors | None = None,
    inputs_embeds: torch.Tensor | None = None,
) -> torch.Tensor | IntermediateTensors:
    """LlamaForCausalLM 透传包装器：将调用委托给 LlamaModel。"""
    return self.model.forward_edge_cloud_segment(
        start_layer,
        end_layer,
        input_ids,
        positions,
        intermediate_tensors,
        inputs_embeds,
    )


# ── Monkey Patch：运行时动态绑定 ──
# 绑定后，所有 LlamaModel / LlamaForCausalLM 实例均可调用 forward_edge_cloud_segment
LlamaModel.forward_edge_cloud_segment = _forward_edge_cloud_segment
LlamaForCausalLM.forward_edge_cloud_segment = (
    _llama_forward_edge_cloud_segment_wrapper
)
