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

"""层分片加载器：边云协同场景下，在加载阶段裁剪非本侧层，降低内存峰值。

V3 核心改进（加载时裁剪）：
- 旧方案（v2）：先全量加载所有层权重 → 再释放非本侧层 → 峰值仍达全量
- 新方案（v3）：initialize_model() 后替换为 PPMissingLayer() → load_weights() 自动跳过
  → 非本侧层权重根本不会被加载到 NPU → 峰值大幅降低（Edge K=1 时降低约 95%）

关键时序：
  1. initialize_model()      — 创建模型结构（随机初始化占位）
  2. apply_sharding()        — 非本侧层替换为 PPMissingLayer（跳过权重加载）
  3. load_weights()          — AutoWeightsLoader 遇到 PPMissingLayer 直接 return
  4. process_weights_after_loading() — 对已加载层做后处理（量化等）
  5. convert_to_execution_layers()   — PPMissingLayer → EdgeCloudMissingLayer（prefill 安全透传）
"""

from dataclasses import dataclass

import torch
import torch.nn as nn
from vllm.logger import logger
from vllm.model_executor.models.utils import PPMissingLayer

"""
 与 PPMissingLayer 的区别：
    - PPMissingLayer 继承 nn.Identity，forward(*args) 返回 args[0]
      在 Transformer 层签名 layer(positions, hidden_states, residual) 下
      会返回 positions 而非 hidden_states，导致 prefill 出错。
    - EdgeCloudMissingLayer 显式返回 (hidden_states, residual)，与
      Transformer 层 forward 签名一致，prefill 遍历时安全透传。
"""

class EdgeCloudMissingLayer(nn.Module):
    """边云场景专用的占位层，用于 prefill 阶段安全透传中间状态。

    时序说明：
    - 权重加载前用 PPMissingLayer（AutoWeightsLoader 自动跳过）
    - 权重加载后用本类替换 PPMissingLayer（保证 prefill 执行正确）
    """

    def forward(self, positions, hidden_states, residual, **kwargs):
        # 直接透传 hidden_states 和 residual，不做任何计算
        return hidden_states, residual


class DeepSeekV4MissingLayer(nn.Module):
    """DeepSeek-V4 专用占位层。

    V4 DecoderLayer 的 forward 签名为 layer(x, positions, input_ids)，
    不接收也不返回 residual。PPMissingLayer.forward(*args) 返回 args[0] = x，
    恰好就是 hidden_states，因此理论上是安全的。但为了明确语义并防御后续
    可能的参数扩展，仍提供本专用占位层。
    """

    def forward(self, x, positions, input_ids, **kwargs):
        return x


@dataclass
class EdgeCloudLayerPlan:
    """边云协同场景下的层加载策略。

    将总层数 N 划分为：
    - Edge 侧：Layers 0~K-1（首 K 层） + Layers N-K~N-1（尾 K 层）
    - Cloud 侧：Layers K~N-K-1（中间层）
    其中 K = edge_head_tail_layers，默认值为 1。
    """

    role: str  # "edge" 或 "cloud"
    total_layers: int
    k: int = 1  # Edge 侧首尾各保留 K 层

    def get_local_layers(self) -> set[int]:
        """返回本节点需要保留真实权重的层索引集合。"""
        if self.role == "edge":
            return set(range(self.k)) | set(
                range(self.total_layers - self.k, self.total_layers)
            )
        else:
            return set(range(self.k, self.total_layers - self.k))

    def get_released_layers(self) -> set[int]:
        """返回本节点可以跳过加载的层索引集合。"""
        all_layers = set(range(self.total_layers))
        return all_layers - self.get_local_layers()

    def validate(self) -> None:
        """验证层分片策略的合法性：Edge 和 Cloud 的层集合应互斥且覆盖全部。"""
        edge_layers = set(range(self.k)) | set(
            range(self.total_layers - self.k, self.total_layers)
        )
        cloud_layers = set(range(self.k, self.total_layers - self.k))
        assert edge_layers | cloud_layers == set(range(self.total_layers))
        assert edge_layers & cloud_layers == set()


class LayerShardLoader:
    """层权重分片加载管理器（V3 加载时裁剪版）。

    核心职责：
    1. apply_sharding()：在 load_weights() 之前，将非本侧层替换为 PPMissingLayer
       使 AutoWeightsLoader 自动跳过这些层的权重加载。
    2. convert_to_execution_layers()：在 load_weights() 之后，将 PPMissingLayer
       替换为 EdgeCloudMissingLayer，确保 prefill 阶段遍历时安全透传。

    注意：V3 不再需要 release_layer_weights()，因为权重根本不会被加载。
    """

    @staticmethod
    def release_layer_weights(layer: nn.Module) -> None:
        """（v2 遗留方法，V3 不再调用）释放单个层的参数和 buffer。

        保留此方法仅用于向后兼容或调试场景。
        """
        for param in list(layer.parameters()):
            if param.data is not None and param.data.numel() > 0:
                param.data = torch.empty(
                    0, device=param.device, dtype=param.dtype
                )
        for buf in list(layer.buffers()):
            if buf.data is not None and buf.data.numel() > 0:
                buf.data = torch.empty(
                    0, device=buf.device, dtype=buf.dtype
                )

    @classmethod
    def apply_sharding(
        cls,
        model: nn.Module,
        layer_plan: EdgeCloudLayerPlan,
    ) -> None:
        """对模型应用层分片策略（在 load_weights 之前调用）。

        执行流程：
        1. 非本地层替换为 PPMissingLayer —— AutoWeightsLoader 遇到后直接 return，
           不会尝试加载该层及其子模块的任何权重。
        2. 保留本地层不变，等待 load_weights() 正常加载。

        为什么用 PPMissingLayer 而非 EdgeCloudMissingLayer？
        - AutoWeightsLoader._load_module() 对 PPMissingLayer 有专门的 isinstance
          检查，直接 return 跳过。
        - EdgeCloudMissingLayer 是普通 nn.Module，_load_module 会递归遍历其子模块
          并尝试匹配权重，可能导致报错。
        """
        num_layers = len(model.model.layers)
        local_layers = layer_plan.get_local_layers()

        for i in range(num_layers):
            if i not in local_layers:
                old_layer = model.model.layers[i]
                if isinstance(old_layer, (PPMissingLayer, EdgeCloudMissingLayer)):
                    continue
                # 替换为 PPMissingLayer：权重加载器会自动跳过
                model.model.layers[i] = PPMissingLayer()
                del old_layer

        # Cloud 侧不调用 embed_tokens / norm / lm_head，将它们也替换为 PPMissingLayer
        # 使 AutoWeightsLoader 跳过这些模块的权重加载，进一步降低 Cloud 侧内存峰值
        # Edge 侧保留这些模块（用于 Embedding 和 Norm/LM Head 计算）
        if layer_plan.role == "cloud":
            for module_name in ["embed_tokens", "norm"]:
                module = getattr(model.model, module_name, None)
                if module is not None and not isinstance(module, PPMissingLayer):
                    setattr(model.model, module_name, PPMissingLayer())
            if hasattr(model, "lm_head") and model.lm_head is not None \
                    and not isinstance(model.lm_head, PPMissingLayer):
                model.lm_head = PPMissingLayer()

        logger.info(
            "[LayerShardLoader] Role=%s, kept_layers=%s, skipped_layers=%s",
            layer_plan.role,
            sorted(local_layers),
            sorted(layer_plan.get_released_layers()),
        )

    @classmethod
    def convert_to_execution_layers(cls, model: nn.Module) -> None:
        """将模型中的 PPMissingLayer 替换为对应类型的 MissingLayer（用于执行阶段）。

        调用时机：必须在 load_weights() 和 process_weights_after_loading() 之后。

        原因：
        - PPMissingLayer.forward(*args) 返回 args[0]，在 Transformer 层签名
          layer(positions, hidden_states, residual) 下会返回 positions，导致
          prefill 阶段遍历所有层时出错。
        - EdgeCloudMissingLayer 返回 (hidden_states, residual)，可安全透传
          标准 Transformer 层。
        - DeepSeekV4MissingLayer 返回 x，可安全透传 V4 的 DecoderLayer。

        注意：Cloud 侧的 segment 通过 islice 只遍历本地层，理论上不需要此替换。
        但为了统一和防御性编程，仍对所有 PPMissingLayer 进行替换。
        """
        # 根据模型类型选择占位层类
        model_cls_name = model.__class__.__name__
        if "DeepseekV4" in model_cls_name:
            missing_layer_cls = DeepSeekV4MissingLayer
        else:
            missing_layer_cls = EdgeCloudMissingLayer

        num_converted = 0
        for i, layer in enumerate(model.model.layers):
            if isinstance(layer, PPMissingLayer):
                model.model.layers[i] = missing_layer_cls()
                num_converted += 1

        if num_converted > 0:
            logger.info(
                "[LayerShardLoader] Converted %d PPMissingLayers to %s "
                "for safe prefill execution.",
                num_converted,
                missing_layer_cls.__name__,
            )
