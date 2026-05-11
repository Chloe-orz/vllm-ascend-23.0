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

"""HCCL 隐藏状态传输实现：基于 torch.distributed.send/recv 完成 Edge↔Cloud 数据交换。"""

from typing import Tuple

import torch
import torch.distributed as dist
from vllm.logger import logger

from vllm_ascend.edge_cloud.hidden_states_transfer import HiddenStatesTransfer


class HiddenStatesTransferHCCL(HiddenStatesTransfer):
    """HCCL 隐藏状态传输实现。

    关键约束：所有 send/recv 必须在 Eager 模式执行，禁止在 NPUGraph 内部调用。
    原因：HCCL 集合通信与 torch.npu.NPUGraph 同时执行会导致死锁。

    超时说明：
    - torch.distributed.send/recv 本身不提供单条消息的超时参数。
    - 通信超时由 torch.distributed.init_process_group() 的 timeout 参数控制。
    - 若需更细粒度的超时检测，应在初始化 HCCL group 时设置合理的 timeout。
    """
    # 默认 HCCL 通信超时（仅作文档说明，实际由 init_process_group 控制）
    _DEFAULT_HCCL_TIMEOUT_SECONDS = 30

    def __init__(self, dtype: torch.dtype = torch.bfloat16, batch_p_num: int = 1):
        super().__init__(dtype=dtype, batch_p_num=batch_p_num)
        self.peer_rank: int | None = None  # 对端在 HCCL group 中的 rank
        self.comm_group = None  # HCCL process group（支持自定义）

    def init(self, peer_rank: int, comm_group=None) -> None:
        """初始化 HCCL 通信参数。

        Args:
            peer_rank: 对端进程在 HCCL group 中的 rank 号。
            comm_group: 可选的 HCCL process group，默认使用 WORLD group。
        """
        self.peer_rank = peer_rank
        self.comm_group = comm_group
        self.init_finish = True
        logger.info(
            "[EdgeCloud] HCCL transfer initialized. Peer rank: %s", peer_rank
        )

    def warmup(self, hidden_size: int) -> None:
        """Warmup HCCL 通信：收发一次 dummy 张量，触发底层通信资源初始化。"""
        if not self.init_finish:
            raise RuntimeError("HCCL transfer not initialized.")
        dummy = torch.zeros(
            (1, hidden_size), dtype=self.dtype, device="npu"
        )
        # Edge 先发送再接收，Cloud 先接收再发送，成对完成一次 ping-pong
        if self.role == "master":  # Edge
            dist.send(dummy, dst=self.peer_rank, group=self.comm_group)
            dist.recv(dummy, src=self.peer_rank, group=self.comm_group)
        else:  # Cloud
            dist.recv(dummy, src=self.peer_rank, group=self.comm_group)
            dist.send(dummy, dst=self.peer_rank, group=self.comm_group)
        logger.info("[EdgeCloud] HCCL warmup finished.")

    def send_hidden(
        self,
        stage: str,
        hidden_states: torch.Tensor,
        residual: torch.Tensor | None = None,
        input_ids: torch.Tensor | None = None,
    ) -> None:
        """通过 HCCL 发送隐藏状态。

        NOTE: 必须在图外 Eager 执行。调用方需确保当前不在 NPUGraph capture/replay 阶段。
        """
        if not self.init_finish:
            raise RuntimeError("HCCL transfer not initialized.")
        assert self.peer_rank is not None

        # 发送主 hidden_states
        dist.send(hidden_states, dst=self.peer_rank, group=self.comm_group)

        # decode 阶段额外发送 residual
        if residual is not None:
            dist.send(residual, dst=self.peer_rank, group=self.comm_group)

        # DeepSeek-V4 等模型需额外发送 input_ids（Hash MoE routing）
        if input_ids is not None:
            dist.send(input_ids, dst=self.peer_rank, group=self.comm_group)

    def recv_hidden(
        self,
        stage: str,
        expected_shape: torch.Size | tuple,
        input_ids_shape: torch.Size | None = None,
        recv_input_ids: bool = False,
    ) -> Tuple[torch.Tensor, torch.Tensor | None, torch.Tensor | None]:
        """通过 HCCL 接收隐藏状态。

        按 expected_shape 在 NPU 上预分配 buffer，再执行同步 recv。
        NOTE: 必须在图外 Eager 执行。
        """
        if not self.init_finish:
            raise RuntimeError("HCCL transfer not initialized.")
        assert self.peer_rank is not None

        # 预分配 hidden_states buffer 并接收
        hidden_states = torch.empty(
            expected_shape, dtype=self.dtype, device="npu"
        )
        dist.recv(hidden_states, src=self.peer_rank, group=self.comm_group)

        # decode 阶段额外接收 residual
        residual = None
        if stage == "d":
            residual = torch.empty(
                expected_shape, dtype=self.dtype, device="npu"
            )
            dist.recv(residual, src=self.peer_rank, group=self.comm_group)

        # 可选：接收 input_ids（DeepSeek-V4 等模型）
        input_ids = None
        if input_ids_shape is not None or recv_input_ids:
            if input_ids_shape is None:
                input_ids_shape = (hidden_states.shape[0],)
            input_ids = torch.empty(
                input_ids_shape, dtype=torch.int64, device="npu"
            )
            dist.recv(input_ids, src=self.peer_rank, group=self.comm_group)

        return hidden_states, residual, input_ids
