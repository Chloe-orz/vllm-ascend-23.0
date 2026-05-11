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

"""隐藏状态传输抽象层：定义 Edge 与 Cloud 之间张量传输的公共接口。"""

from abc import ABC, abstractmethod
from typing import Tuple

import torch


class HiddenStatesTransfer(ABC):
    """Edge-Cloud 隐藏状态传输抽象基类。

    所有通信操作（send/recv）均在 Eager 模式下执行，严禁在 torch.npu.NPUGraph
    捕获/重放阶段调用，避免 HCCL 与 NPU Graph 死锁。
    """

    def __init__(self, dtype: torch.dtype = torch.bfloat16, batch_p_num: int = 1):
        self.dtype = dtype
        self.batch_p_num = batch_p_num
        self.role: str | None = None  # "master" 对应 Edge，"slave" 对应 Cloud
        self.init_finish = False

    @abstractmethod
    def send_hidden(
        self,
        stage: str,
        hidden_states: torch.Tensor,
        residual: torch.Tensor | None = None,
        input_ids: torch.Tensor | None = None,
    ) -> None:
        """发送隐藏状态（及可选的 residual / input_ids）到对端节点。

        Args:
            stage: 'p' 表示 prefill 阶段，'d' 表示 decode 阶段。
            hidden_states: 待发送的隐藏状态张量。
            residual: decode 阶段需一并发送的 residual 张量，prefill 时为 None。
            input_ids: DeepSeek-V4 等需要 input_ids 做 Hash MoE routing 的模型
                       需一并发送 input_ids（prefill/decode 均可能需传递）。
        """
        raise NotImplementedError

    @abstractmethod
    def recv_hidden(
        self,
        stage: str,
        expected_shape: torch.Size | tuple,
        input_ids_shape: torch.Size | None = None,
        recv_input_ids: bool = False,
    ) -> Tuple[torch.Tensor, torch.Tensor | None, torch.Tensor | None]:
        """从对端节点接收隐藏状态（及可选的 residual / input_ids）。

        Args:
            stage: 'p' 表示 prefill 阶段，'d' 表示 decode 阶段。
            expected_shape: 接收 hidden_states 的期望 shape，用于预分配 buffer。
            input_ids_shape: 若显式指定，则按该 shape 接收 input_ids；
                             若传入 None 且 recv_input_ids=True，则按 hidden_states.shape[0] 自动推断。
            recv_input_ids: 是否在接收 hidden_states 后自动接收 input_ids（用于 Cloud 侧
                            预先不知道 input_ids_shape 的场景）。

        Returns:
            (hidden_states, residual, input_ids)。
            prefill 阶段 residual 为 None；非 V4 模型 input_ids 为 None。
        """
        raise NotImplementedError

    @abstractmethod
    def init(self) -> None:
        """初始化传输后端（如 HCCL 通信域、TCP 连接等）。"""
        raise NotImplementedError

    @abstractmethod
    def warmup(self, hidden_size: int) -> None:
        """预热传输通道：发送一个 dummy 张量，完成底层资源分配。"""
        raise NotImplementedError
