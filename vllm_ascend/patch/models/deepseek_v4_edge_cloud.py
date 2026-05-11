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

"""DeepSeek-V4 模型的边云协同 Monkey Patch。

DeepSeek-V4 与标准 Llama 架构存在以下关键差异，需单独实现分段 forward：
1. DecoderLayer 签名为 layer(x, positions, input_ids)，不接收/返回 residual。
2. 残差管理在层内部通过 hc_pre / hc_post（Hybrid Connection）完成。
3. 首层 Embedding 输出后需 unsqueeze 为 [num_tokens, hc_mult, hidden_size]。
4. 尾层需执行 hc_head + norm，而非标准 RMSNorm。
5. 中间层需要 input_ids 用于 Hash MoE routing。

加载方式：
    import vllm_ascend.patch.models.deepseek_v4_edge_cloud  # noqa

当 edge_cloud_config.enabled 为 True 且模型类型为 deepseek_v4 时自动加载。
"""

from itertools import islice

import torch
from vllm.distributed.parallel_state import get_pp_group
from vllm.model_executor.models.deepseek_v4 import (
    DeepseekV4ForCausalLM,
    DeepseekV4Model,
    hc_head,
)
from vllm.sequence import IntermediateTensors


def _forward_edge_cloud_segment_v4(
    self,
    start_layer: int,
    end_layer: int,
    input_ids: torch.Tensor | None,
    positions: torch.Tensor,
    intermediate_tensors: IntermediateTensors | None = None,
    inputs_embeds: torch.Tensor | None = None,
    **extra_layer_kwargs,
) -> torch.Tensor | IntermediateTensors:
    """DeepSeek-V4 专用：通用分段 forward。

    与标准 Llama 分段 forward 的核心差异：
    - 无 residual 传递，层内部通过 hc_pre/hc_post 管理残差。
    - Embedding 输出需 unsqueeze 为 [num_tokens, hc_mult, hidden_size]。
    - 尾段需执行 hc_head + norm。
    - 中间状态需携带 input_ids（Hash MoE routing 所需）。
    """
    num_layers = len(self.layers)
    assert 0 <= start_layer < end_layer <= num_layers, (
        f"Invalid layer range: start={start_layer}, end={end_layer}, "
        f"num_layers={num_layers}"
    )

    is_first_segment = (
        start_layer == 0 and get_pp_group().is_first_rank
    )
    is_last_segment = (
        end_layer == num_layers and get_pp_group().is_last_rank
    )

    # Embedding 或恢复中间状态
    if is_first_segment:
        if inputs_embeds is not None:
            hidden_states = inputs_embeds
        else:
            hidden_states = self.embed_input_ids(input_ids)
        hidden_states = hidden_states.unsqueeze(-2).repeat(1, self.hc_mult, 1)
        if self.use_mega_moe:
            input_ids = input_ids.to(torch.int64)
    else:
        assert intermediate_tensors is not None, (
            "intermediate_tensors must be provided for non-first segment"
        )
        hidden_states = intermediate_tensors["hidden_states"]
        # 非首段需从中间状态恢复 input_ids（Hash MoE routing 需要）
        if "input_ids" in intermediate_tensors:
            input_ids = intermediate_tensors["input_ids"]

    # islice 遍历指定范围的层
    for idx, layer in enumerate(islice(self.layers, start_layer, end_layer)):
        hidden_states = layer(
            hidden_states,
            positions,
            input_ids,
        )

    # 如果不是尾段，返回中间状态（携带 hidden_states + input_ids）
    if not is_last_segment:
        return IntermediateTensors(
            {"hidden_states": hidden_states, "input_ids": input_ids}
        )

    # 尾段：hc_head + norm
    num_tokens = hidden_states.shape[0]
    if hasattr(self, "_mtp_hidden_buffer"):
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
    self,
    start_layer: int,
    end_layer: int,
    input_ids: torch.Tensor | None,
    positions: torch.Tensor,
    intermediate_tensors: IntermediateTensors | None = None,
    inputs_embeds: torch.Tensor | None = None,
) -> torch.Tensor | IntermediateTensors:
    """DeepseekV4ForCausalLM 透传包装器：将调用委托给 DeepseekV4Model。"""
    return self.model.forward_edge_cloud_segment(
        start_layer,
        end_layer,
        input_ids,
        positions,
        intermediate_tensors,
        inputs_embeds,
    )


# ── Monkey Patch：运行时动态绑定 ──
DeepseekV4Model.forward_edge_cloud_segment = _forward_edge_cloud_segment_v4
DeepseekV4ForCausalLM.forward_edge_cloud_segment = (
    _deepseek_v4_forward_edge_cloud_segment_wrapper
)
