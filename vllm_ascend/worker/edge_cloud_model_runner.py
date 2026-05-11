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

"""Edge-Cloud collaborative model runners.

Implements EdgeModelRunner and CloudModelRunner that extend NPUModelRunner
with edge-cloud layer sharding, segmented ACLGraphWrapper, and HCCL communication.

Design (from V3 doc):
- EdgeModelRunner: keeps head K + tail K layers, runs Segment A (graph),
  sends to Cloud, receives back, runs Segment E (graph).
- CloudModelRunner: keeps middle layers, receives from Edge, runs Segment C
  (graph), sends back to Edge.

V3 核心改进（加载时裁剪）：
- 不再调用 super().load_model()（全量加载），而是自定义四阶段加载流程：
  1. initialize_model()     — 创建模型结构
  2. apply_sharding()       — 非本侧层替换为 PPMissingLayer（跳过权重加载）
  3. load_weights()         — AutoWeightsLoader 自动跳过 PPMissingLayer
  4. process_weights_after_loading() — 后处理 + convert_to_execution_layers()
- 相比 v2 "先全量加载再释放"，Edge K=1 时权重加载峰值降低约 95%。

All communication (send/recv) happens in Eager mode (outside graphs).
"""

from typing import Any

import torch
from vllm.config import CUDAGraphMode
from vllm.forward_context import get_forward_context
from vllm.logger import logger
from vllm.sequence import IntermediateTensors

from vllm_ascend.ascend_config import get_ascend_config
from vllm_ascend.ascend_forward_context import get_forward_context as get_ascend_forward_context
from vllm_ascend.compilation.acl_graph import ACLGraphWrapper
from vllm_ascend.edge_cloud.edge_cloud_ctrl_comm import EdgeCloudCtrlComm
from vllm_ascend.edge_cloud.hidden_states_transfer_hccl import HiddenStatesTransferHCCL
from vllm_ascend.edge_cloud.manager import EdgeCloudManager
from vllm_ascend.model_loader.layer_shard_loader import EdgeCloudLayerPlan, LayerShardLoader
from vllm_ascend.worker.model_runner_v1 import NPUModelRunner


class EdgeCloudModelRunnerBase(NPUModelRunner):
    """边云模型执行器基类：封装 Edge 和 Cloud 共用的通信接口、配置和自定义加载流程。"""

    def __init__(self, vllm_config, device):
        super().__init__(vllm_config, device)
        # 读取边云配置（来自 additional_config.edge_cloud_config）
        self.edge_cloud_cfg = get_ascend_config().edge_cloud_config
        # 初始化并启动边云通信管理器（TCP + HCCL）
        self.edge_cloud_mgr = EdgeCloudManager(vllm_config)
        self.edge_cloud_mgr.initialize()

        # 数据面：HCCL 隐藏状态传输
        self.transfer: HiddenStatesTransferHCCL = self.edge_cloud_mgr.data_comm
        # 控制面：TCP 控制信号传输
        self.ctrl_comm: EdgeCloudCtrlComm = self.edge_cloud_mgr.ctrl_comm

        # K：Edge 侧首尾各保留的层数（默认 1，可通过配置调整）
        self.k = getattr(self.edge_cloud_cfg, "edge_head_tail_layers", 1)

        # 模型总层数，在 load_model 后设置
        self.num_layers: int = 0

        # 分段计算模块及其 ACLGraphWrapper（在子类 load_model 中创建）
        self.segment_a = None
        self.segment_a_wrapper = None
        self.segment_e = None
        self.segment_e_wrapper = None
        self.segment_c = None
        self.segment_c_wrapper = None

        # 模型类型检测：DeepSeek-V4 有独立的分段 forward 和通信逻辑
        self._is_deepseek_v4 = (
            getattr(self.model_config.hf_config, "model_type", "") == "deepseek_v4"
        )

    def _is_dummy_or_profile_run(self) -> bool:
        """检测当前是否处于 dummy_run / profile_run / capture 阶段。

        在这些阶段，边云通信链路可能尚未就绪（如对端未启动），
        或不需要真实通信（仅需捕获各段 ACL Graph）。此时跳过
        HCCL/TCP 通信，用本地 zeros 模拟中间状态，避免同步阻塞。
        """
        forward_context = get_forward_context()
        if forward_context is None:
            return False
        return getattr(forward_context, "in_profile_run", False)

    def _load_edge_cloud_model(self, role: str) -> torch.nn.Module:
        """边云协同自定义模型加载流程（V3 加载时裁剪版）。

        替代标准 get_model()/super().load_model() 的全量加载，实现：
        1. initialize_model() — 创建模型结构（随机初始化占位，权重尚未加载）
        2. apply_sharding()   — 非本侧层替换为 PPMissingLayer
        3. load_weights()     — AutoWeightsLoader 遇到 PPMissingLayer 直接 return
        4. post-process       — process_weights_after_loading + convert_to_execution_layers

        为什么不用 super().load_model()？
        - 父类调用 get_model()，会加载所有层权重到 NPU，Edge 侧无法容纳大模型。
        - 自定义流程在加载前裁剪，非本侧层权重根本不会被加载，峰值内存大幅降低。

        Args:
            role: "edge" 或 "cloud"，决定保留哪些层。

        Returns:
            加载完成的模型（nn.Module），其中非本侧层为 EdgeCloudMissingLayer。
        """
        from vllm.model_executor.model_loader import get_model_loader
        from vllm.model_executor.model_loader.base_loader import (
            _has_online_quant,
            log_model_inspection,
        )
        from vllm.model_executor.model_loader.reload.layerwise import (
            finalize_layerwise_processing,
        )
        from vllm.model_executor.model_loader.utils import (
            initialize_model,
            process_weights_after_loading,
        )
        from vllm.utils.torch_utils import set_default_torch_dtype

        logger.info(
            "[EdgeCloud] Starting custom load_model for role=%s, k=%d",
            role,
            self.k,
        )

        target_device = self.device

        # 步骤 1：初始化模型结构（在目标设备和默认 dtype 下创建）
        with set_default_torch_dtype(self.model_config.dtype):
            with target_device:
                model = initialize_model(
                    vllm_config=self.vllm_config,
                    model_config=self.model_config,
                )

        log_model_inspection(model)
        self.num_layers = len(model.model.layers)

        # 步骤 2：层裁剪 — 非本侧层替换为 PPMissingLayer()
        # 关键：在 load_weights() 之前完成，使这些层的权重直接跳过
        layer_plan = EdgeCloudLayerPlan(
            role=role,
            total_layers=self.num_layers,
            k=self.k,
        )
        LayerShardLoader.apply_sharding(model, layer_plan)

        # 步骤 3：加载权重 — AutoWeightsLoader 自动跳过 PPMissingLayer
        loader = get_model_loader(self.vllm_config.load_config)
        loader.load_weights(model, self.model_config)

        # 步骤 4a：在线量化后处理（如果启用）
        if _has_online_quant(model):
            finalize_layerwise_processing(model, self.model_config)

        # 步骤 4b：通用权重后处理（quantization、weight cache 等）
        process_weights_after_loading(model, self.model_config, target_device)

        # 步骤 4c：将 PPMissingLayer 替换为 EdgeCloudMissingLayer
        # 原因：PPMissingLayer.forward(*args) 返回 args[0]，在 Transformer 层签名
        # layer(positions, hidden_states, residual) 下会返回 positions，导致
        # prefill 阶段遍历所有层时出错。EdgeCloudMissingLayer 返回 (hidden_states,
        # residual)，可安全透传。
        LayerShardLoader.convert_to_execution_layers(model)

        logger.info(
            "[EdgeCloud] Custom load_model finished. role=%s, layers=%d, k=%d",
            role,
            self.num_layers,
            self.k,
        )
        return model


class EdgeModelRunner(EdgeCloudModelRunnerBase):
    """Edge 侧模型执行器。

    保留模型首尾各 K 层 + Embedding/Norm/LM Head。
    Decode 时分两段执行：
      Segment A（Graph）: Embedding + 首 K 层
      Segment E（Graph）: 尾 K 层 + Norm
    两段之间通过 HCCL 与 Cloud 交换中间状态。
    """

    def load_model(self) -> None:
        # 使用自定义加载流程，实现加载时裁剪
        raw_model = self._load_edge_cloud_model(role="edge")

        # 创建分段计算 lambda，基于 Monkey Patch 的 forward_edge_cloud_segment
        if self._is_deepseek_v4:
            # DeepSeek-V4：无 residual，中间状态需携带 input_ids
            # Segment A：islice(0, K) → Layers 0 ~ K-1（含 Embedding + hc_mult unsqueeze）
            self.segment_a = lambda input_ids, positions: \
                raw_model.forward_edge_cloud_segment(
                    0, self.k, input_ids, positions)

            # Segment E：islice(N-K, N) → Layers N-K ~ N-1（含 hc_head + norm）
            self.segment_e = lambda hidden_states, input_ids, positions: \
                raw_model.forward_edge_cloud_segment(
                    self.num_layers - self.k, self.num_layers,
                    None, positions,
                    intermediate_tensors=IntermediateTensors({
                        "hidden_states": hidden_states,
                        "input_ids": input_ids,
                    }))
        else:
            # 标准模型（Llama / Qwen / DeepSeek-V2 / V3 等）
            # Segment A：islice(0, K) → Layers 0 ~ K-1（含 Embedding）
            self.segment_a = lambda input_ids, positions: \
                raw_model.forward_edge_cloud_segment(
                    0, self.k, input_ids, positions)

            # Segment E：islice(N-K, N) → Layers N-K ~ N-1（含 Norm）
            self.segment_e = lambda hidden_states, residual, positions: \
                raw_model.forward_edge_cloud_segment(
                    self.num_layers - self.k, self.num_layers,
                    None, positions,
                    intermediate_tensors=IntermediateTensors({
                        "hidden_states": hidden_states,
                        "residual": residual,
                    }))

        # 为分段模块包装 ACLGraphWrapper，实现 Decode 阶段的图捕获/重放
        # 受 enable_decode_graph 配置控制（默认 True）
        enable_decode_graph = getattr(
            self.edge_cloud_cfg, "enable_decode_graph", True
        )
        if enable_decode_graph and self.compilation_config.cudagraph_mode.has_full_cudagraphs():
            self.segment_a_wrapper = ACLGraphWrapper(
                self.segment_a,
                self.vllm_config,
                runtime_mode=CUDAGraphMode.FULL,
                use_eagle=self.use_eagle,
                enable_enpu=self.enable_enpu,
            )
            self.segment_e_wrapper = ACLGraphWrapper(
                self.segment_e,
                self.vllm_config,
                runtime_mode=CUDAGraphMode.FULL,
                use_eagle=self.use_eagle,
                enable_enpu=self.enable_enpu,
            )
            logger.info(
                "[EdgeCloud] Edge segment ACLGraphWrappers created. k=%d, v4=%s",
                self.k,
                self._is_deepseek_v4,
            )

        # 保存 model 引用，供 compute_logits 等后续方法使用
        self.model = raw_model

        # 预热 HCCL 通信通道
        hidden_size = raw_model.model.config.hidden_size
        self.edge_cloud_mgr.warmup(hidden_size)

    def execute_model(self, scheduler_output, intermediate_tensors=None):
        """统一入口：Prefill 和 Decode 都通过重写 _model_forward 实现分段执行。

        复用父类 execute_model 的输入准备和后续 logits/采样逻辑，
        仅将中间的 _model_forward 替换为边云分段执行逻辑。
        """
        return super().execute_model(scheduler_output, intermediate_tensors)

    def _model_forward(
        self,
        num_tokens_padded: int,
        input_ids: torch.Tensor | None = None,
        positions: torch.Tensor | None = None,
        intermediate_tensors: IntermediateTensors | None = None,
        inputs_embeds: torch.Tensor | None = None,
        **model_kwargs: dict[str, Any],
    ):
        """重写 _model_forward，Prefill 和 Decode 均执行分段计算。

        - Prefill（cudagraph_runtime_mode=NONE）：Eager 执行 Segment A → 通信 → Segment E
        - Decode（cudagraph_runtime_mode=FULL）：Graph 执行 Segment A → 通信 → Segment E
        """
        forward_context = get_forward_context()
        assert forward_context is not None

        if forward_context.cudagraph_runtime_mode == CUDAGraphMode.NONE:
            # ==================== Prefill 分段执行（Eager）===================
            return self._prefill_forward(input_ids, positions)

        # ==================== Decode 分段执行（Graph）===================
        if self._is_deepseek_v4:
            # DeepSeek-V4：无 residual，需传递 input_ids
            result = self.segment_a_wrapper(input_ids, positions)
            hidden_states = result["hidden_states"]
            seg_input_ids = result["input_ids"]
            hidden_states = self._postprocess_hidden(hidden_states)

            if self._is_dummy_or_profile_run():
                # dummy_run / profile_run：跳过通信，用本地 zeros 模拟对端回传
                recv_hidden = torch.zeros_like(hidden_states)
                recv_input_ids = torch.zeros_like(seg_input_ids)
            else:
                # 图外 Eager 通信：发送 (hidden_states, input_ids) 到 Cloud
                self.transfer.send_hidden(
                    "d", hidden_states, residual=None, input_ids=seg_input_ids
                )
                self.ctrl_comm.send_decode()

                # 图外 Eager 通信：接收 Cloud 回传的中间状态
                expected_shape = hidden_states.shape
                recv_hidden, _, recv_input_ids = self.transfer.recv_hidden(
                    "d", expected_shape, input_ids_shape=seg_input_ids.shape
                )

            # 关键：在 Segment E 前手动重置 layer_idx
            ascend_ctx = get_ascend_forward_context()
            if ascend_ctx is not None:
                ascend_ctx.layer_idx = self.num_layers - self.k

            hidden_states = self.segment_e_wrapper(
                recv_hidden, recv_input_ids, positions
            )
        else:
            # 标准模型：传递 (hidden_states, residual)
            result = self.segment_a_wrapper(input_ids, positions)
            hidden_states = result["hidden_states"]
            residual = result["residual"]

            # 后处理 hidden_states（如 flashcomm gather/unpad）
            hidden_states = self._postprocess_hidden(hidden_states)

            if self._is_dummy_or_profile_run():
                # dummy_run / profile_run：跳过通信，用本地 zeros 模拟对端回传
                recv_hidden = torch.zeros_like(hidden_states)
                recv_residual = torch.zeros_like(residual) if residual is not None else None
            else:
                # 图外 Eager 通信：发送 (hidden_states, residual) 到 Cloud
                self.transfer.send_hidden("d", hidden_states, residual=residual)
                self.ctrl_comm.send_decode()

                # 图外 Eager 通信：接收 Cloud 回传的中间状态
                expected_shape = hidden_states.shape
                recv_hidden, recv_residual, _ = self.transfer.recv_hidden(
                    "d", expected_shape
                )

            # 关键：在 Segment E 前手动重置 layer_idx，使 weight_prefetch 定位到尾段起始层
            ascend_ctx = get_ascend_forward_context()
            if ascend_ctx is not None:
                ascend_ctx.layer_idx = self.num_layers - self.k

            # Segment E（Graph）：尾 K 层 + Norm
            hidden_states = self.segment_e_wrapper(
                recv_hidden, recv_residual, positions
            )

        return hidden_states

    def _prefill_forward(
        self,
        input_ids: torch.Tensor | None,
        positions: torch.Tensor | None,
    ) -> torch.Tensor:
        """Prefill 分段执行（Eager）：Segment A → 通信 → Segment E。

        与 Decode 的区别：
        - 不走 ACL Graph，直接调用 segment_a / segment_e lambda（Eager）
        - 通信相位为 'p'（prefill）
        - 仍需重置 layer_idx（Segment A 执行后 layer_idx 递增到 K，需重置为 N-K）

        dummy_run / profile_run 时跳过边云通信，用本地 zeros 模拟中间状态，
        避免两侧启动时序不一致导致的 HCCL/TCP 阻塞。
        """
        if self._is_deepseek_v4:
            # DeepSeek-V4：无 residual，需传递 input_ids
            result = self.segment_a(input_ids, positions)
            hidden_states = result["hidden_states"]
            seg_input_ids = result["input_ids"]
            hidden_states = self._postprocess_hidden(hidden_states)

            if self._is_dummy_or_profile_run():
                recv_hidden = torch.zeros_like(hidden_states)
                recv_input_ids = torch.zeros_like(seg_input_ids)
            else:
                self.transfer.send_hidden(
                    "p", hidden_states, residual=None, input_ids=seg_input_ids
                )
                self.ctrl_comm.send_prefill()

                expected_shape = hidden_states.shape
                recv_hidden, _, recv_input_ids = self.transfer.recv_hidden(
                    "p", expected_shape, input_ids_shape=seg_input_ids.shape
                )
                self.ctrl_comm.recv_prefill()

            ascend_ctx = get_ascend_forward_context()
            if ascend_ctx is not None:
                ascend_ctx.layer_idx = self.num_layers - self.k

            hidden_states = self.segment_e(
                recv_hidden, recv_input_ids, positions
            )
        else:
            # 标准模型：传递 (hidden_states, residual)
            result = self.segment_a(input_ids, positions)
            hidden_states = result["hidden_states"]
            residual = result["residual"]

            # 后处理 hidden_states
            hidden_states = self._postprocess_hidden(hidden_states)

            if self._is_dummy_or_profile_run():
                recv_hidden = torch.zeros_like(hidden_states)
                recv_residual = torch.zeros_like(residual) if residual is not None else None
            else:
                # 图外 Eager 通信：发送 (hidden_states, residual) 到 Cloud
                self.transfer.send_hidden("p", hidden_states, residual=residual)
                self.ctrl_comm.send_prefill()

                # 图外 Eager 通信：接收 Cloud 回传的中间状态
                expected_shape = hidden_states.shape
                recv_hidden, recv_residual, _ = self.transfer.recv_hidden(
                    "p", expected_shape
                )
                self.ctrl_comm.recv_prefill()

            # 关键：在 Segment E 前手动重置 layer_idx
            ascend_ctx = get_ascend_forward_context()
            if ascend_ctx is not None:
                ascend_ctx.layer_idx = self.num_layers - self.k

            # Segment E（Eager）：尾 K 层 + Norm
            hidden_states = self.segment_e(
                recv_hidden, recv_residual, positions
            )

        return hidden_states

    def _postprocess_hidden(self, hidden_states: torch.Tensor) -> torch.Tensor:
        """Segment A 后的 hidden_states 后处理。

        集成父类 NPUModelRunner 的 SP all-gather 和 unpad 逻辑，
        确保在 Sequence Parallelism 场景下 hidden_states 形状正确。
        """
        # 复用父类静态方法：all-gather + unpad（SP 场景）
        return NPUModelRunner._all_gather_hidden_states(hidden_states)


class CloudModelRunner(EdgeCloudModelRunnerBase):
    """Cloud 侧模型执行器。

    保留模型中间层 Layers K ~ N-K-1。
    Decode 时执行 Segment C（Graph），接收 Edge 的中间状态，计算后再发送回去。
    """

    def load_model(self) -> None:
        # 使用自定义加载流程，实现加载时裁剪
        raw_model = self._load_edge_cloud_model(role="cloud")

        if self._is_deepseek_v4:
            # DeepSeek-V4：无 residual，中间状态携带 input_ids
            self.segment_c = lambda hidden_states, positions, input_ids: \
                raw_model.forward_edge_cloud_segment(
                    self.k, self.num_layers - self.k,
                    None, positions,
                    intermediate_tensors=IntermediateTensors({
                        "hidden_states": hidden_states,
                        "input_ids": input_ids,
                    }))
        else:
            # 标准模型：传递 (hidden_states, residual)
            self.segment_c = lambda hidden_states, residual, positions: \
                raw_model.forward_edge_cloud_segment(
                    self.k, self.num_layers - self.k,
                    None, positions,
                    intermediate_tensors=IntermediateTensors({
                        "hidden_states": hidden_states,
                        "residual": residual,
                    }))

        # 包装 ACLGraphWrapper，实现 Decode 图捕获/重放
        enable_decode_graph = getattr(
            self.edge_cloud_cfg, "enable_decode_graph", True
        )
        if enable_decode_graph and self.compilation_config.cudagraph_mode.has_full_cudagraphs():
            self.segment_c_wrapper = ACLGraphWrapper(
                self.segment_c,
                self.vllm_config,
                runtime_mode=CUDAGraphMode.FULL,
                use_eagle=self.use_eagle,
                enable_enpu=self.enable_enpu,
            )
            logger.info(
                "[EdgeCloud] Cloud segment ACLGraphWrapper created. k=%d, v4=%s",
                self.k,
                self._is_deepseek_v4,
            )

        # 保存 model 引用
        self.model = raw_model

        # 预热 HCCL 通信通道
        hidden_size = raw_model.model.config.hidden_size
        self.edge_cloud_mgr.warmup(hidden_size)

    def execute_model(self, scheduler_output, intermediate_tensors=None):
        if scheduler_output.is_prefill:
            return self._execute_cloud_prefill(scheduler_output, intermediate_tensors)
        return self._execute_cloud_decode(scheduler_output, intermediate_tensors)

    def _execute_cloud_prefill(self, scheduler_output, intermediate_tensors=None):
        """Cloud Prefill：接收 Edge 传来的中间状态，执行中间层后回传。

        Prefill 不走 Graph，直接调用 segment_c lambda（Eager）。

        dummy_run / profile_run 时跳过边云通信，用本地 zeros 模拟输入，
        避免两侧启动时序不一致导致的 HCCL/TCP 阻塞。
        """
        is_dummy = self._is_dummy_or_profile_run()

        if self._is_deepseek_v4:
            if not is_dummy:
                # DeepSeek-V4：接收 (hidden_states, input_ids)
                recv_hidden, _, recv_input_ids = self.transfer.recv_hidden(
                    "p", None, recv_input_ids=True
                )
                self.ctrl_comm.recv_prefill()
            else:
                # dummy_run：构造 zeros 输入，shape 与真实场景一致即可
                num_tokens = scheduler_output.total_num_scheduled_tokens
                hidden_size = self.model_config.hidden_size
                device = self.device
                recv_hidden = torch.zeros(
                    num_tokens, hidden_size, device=device, dtype=self.model_config.dtype
                )
                recv_input_ids = torch.zeros(
                    num_tokens, device=device, dtype=torch.long
                )

            # Cloud 的 embed_tokens 和 norm 已被裁剪，Prefill 直接跑 Segment C（中间层）
            dummy_positions = torch.zeros(
                (recv_hidden.shape[0],),
                dtype=torch.int64,
                device=recv_hidden.device,
            )
            result = self.segment_c(
                recv_hidden, dummy_positions, recv_input_ids
            )

            # segment_c 返回 IntermediateTensors（非尾段），需提取 hidden_states 和 input_ids
            if isinstance(result, IntermediateTensors):
                hidden_states = result["hidden_states"]
                input_ids = result["input_ids"]
            else:
                hidden_states = result
                input_ids = None

            if not is_dummy:
                # 将结果回传给 Edge（传递 hidden_states 和 input_ids）
                self.transfer.send_hidden(
                    "p", hidden_states, residual=None, input_ids=input_ids
                )
                self.ctrl_comm.send_prefill()
        else:
            if not is_dummy:
                # 标准模型：接收 (hidden_states, residual)
                recv_hidden, recv_residual, _ = self.transfer.recv_hidden("p", None)
                self.ctrl_comm.recv_prefill()
            else:
                num_tokens = scheduler_output.total_num_scheduled_tokens
                hidden_size = self.model_config.hidden_size
                device = self.device
                recv_hidden = torch.zeros(
                    num_tokens, hidden_size, device=device, dtype=self.model_config.dtype
                )
                recv_residual = torch.zeros(
                    num_tokens, hidden_size, device=device, dtype=self.model_config.dtype
                )

            # Cloud 的 embed_tokens 和 norm 已被裁剪，Prefill 直接跑 Segment C（中间层）
            dummy_positions = torch.zeros(
                (recv_hidden.shape[0],),
                dtype=torch.int64,
                device=recv_hidden.device,
            )
            result = self.segment_c(
                recv_hidden, recv_residual, dummy_positions
            )

            # segment_c 返回 IntermediateTensors（非尾段），需提取 hidden_states 和 residual
            if isinstance(result, IntermediateTensors):
                hidden_states = result["hidden_states"]
                residual = result["residual"]
            else:
                hidden_states = result
                residual = None

            if not is_dummy:
                # 将结果回传给 Edge（传递 hidden_states 和 residual）
                self.transfer.send_hidden("p", hidden_states, residual=residual)
                self.ctrl_comm.send_prefill()

        # Cloud 不计算 logits
        return None

    def _execute_cloud_decode(self, scheduler_output, intermediate_tensors=None):
        """Cloud Decode：接收 → Graph 计算 → 发送。

        不调用父类 execute_model，独立管理 HCCL 收发和 Graph 执行。

        dummy_run / profile_run 时跳过边云通信，用本地 zeros 模拟输入，
        使 segment_c_wrapper 独立 Capture，避免两侧启动时序不一致导致的阻塞。
        """
        # 构建 batch_descriptor，作为 Graph 缓存的 key
        num_scheduled_tokens = scheduler_output.total_num_scheduled_tokens
        batch_desc = self._get_decode_batch_descriptor(num_scheduled_tokens)
        is_dummy = self._is_dummy_or_profile_run()

        # Segment C 的 layer.forward 需要 positions 参数，这里使用 dummy
        # 生产环境应从父类输入准备中获取真实 positions
        from vllm_ascend.ascend_forward_context import set_ascend_forward_context

        if self._is_deepseek_v4:
            if not is_dummy:
                # 图外 Eager：接收 Edge 发来的 (hidden_states, input_ids)
                recv_hidden, _, recv_input_ids = self.transfer.recv_hidden("d", None)
            else:
                # dummy_run：构造 zeros 输入，shape 与真实场景一致即可
                device = self.device
                hidden_size = self.model_config.hidden_size
                recv_hidden = torch.zeros(
                    num_scheduled_tokens, hidden_size, device=device, dtype=self.model_config.dtype
                )
                recv_input_ids = torch.zeros(
                    num_scheduled_tokens, device=device, dtype=torch.long
                )

            with set_ascend_forward_context(
                # TODO: Cloud 侧需从 Edge 同步 attn_metadata（含 KV cache 布局），
                # 当前传 None 会导致 attention 无法正确读取 KV cache。
                # 短期方案：Edge 侧将 attn_metadata 通过控制面同步到 Cloud。
                None,
                self.vllm_config,
                num_tokens=num_scheduled_tokens,
                aclgraph_runtime_mode=CUDAGraphMode.FULL,
                batch_descriptor=batch_desc,
                model_instance=self.model,
            ):
                dummy_positions = torch.zeros(
                    (recv_hidden.shape[0],),
                    dtype=torch.int64,
                    device=recv_hidden.device,
                )
                result = self.segment_c_wrapper(
                    recv_hidden, dummy_positions, recv_input_ids
                )
                hidden_states = result["hidden_states"]

            # 后处理
            hidden_states = self._postprocess_hidden(hidden_states)

            if not is_dummy:
                # 图外 Eager：将结果发送回 Edge（携带 input_ids）
                self.transfer.send_hidden(
                    "d", hidden_states, residual=None, input_ids=recv_input_ids
                )
                self.ctrl_comm.send_decode()
        else:
            if not is_dummy:
                # 图外 Eager：接收 Edge 发来的 (hidden_states, residual)
                recv_hidden, recv_residual, _ = self.transfer.recv_hidden("d", None)
            else:
                device = self.device
                hidden_size = self.model_config.hidden_size
                recv_hidden = torch.zeros(
                    num_scheduled_tokens, hidden_size, device=device, dtype=self.model_config.dtype
                )
                recv_residual = torch.zeros(
                    num_scheduled_tokens, hidden_size, device=device, dtype=self.model_config.dtype
                )

            with set_ascend_forward_context(
                None,  # attn_metadata（Cloud 侧独立管理）
                self.vllm_config,
                num_tokens=num_scheduled_tokens,
                aclgraph_runtime_mode=CUDAGraphMode.FULL,
                batch_descriptor=batch_desc,
                model_instance=self.model,
            ):
                dummy_positions = torch.zeros(
                    (recv_hidden.shape[0],),
                    dtype=torch.int64,
                    device=recv_hidden.device,
                )
                result = self.segment_c_wrapper(
                    recv_hidden, recv_residual, dummy_positions
                )
                hidden_states = result["hidden_states"]
                residual = result["residual"]

            # 后处理
            hidden_states = self._postprocess_hidden(hidden_states)

            if not is_dummy:
                # 图外 Eager：将结果发送回 Edge
                self.transfer.send_hidden("d", hidden_states, residual=residual)
                self.ctrl_comm.send_decode()

        # Cloud 不计算 logits，返回 None
        return None

    def _get_decode_batch_descriptor(self, num_tokens: int):
        """构建 Decode Graph 缓存的 batch_descriptor（以 num_tokens 为 key）。"""
        from vllm.forward_context import BatchDescriptor
        return BatchDescriptor(
            num_tokens=num_tokens,
            num_reqs=None,
        )

    def _postprocess_hidden(self, hidden_states: torch.Tensor) -> torch.Tensor:
        """Segment C 后的 hidden_states 后处理。

        集成父类 NPUModelRunner 的 SP all-gather 和 unpad 逻辑。
        """
        return NPUModelRunner._all_gather_hidden_states(hidden_states)
