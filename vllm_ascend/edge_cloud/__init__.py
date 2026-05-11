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

# 边云协同推理模块的入口文件，统一暴露对外接口
from vllm_ascend.edge_cloud.edge_cloud_ctrl_comm import EdgeCloudCtrlComm
from vllm_ascend.edge_cloud.hidden_states_transfer import HiddenStatesTransfer
from vllm_ascend.edge_cloud.hidden_states_transfer_hccl import HiddenStatesTransferHCCL
from vllm_ascend.edge_cloud.manager import EdgeCloudManager

__all__ = [
    # TCP 控制面通信：Prefill/Decode 完成信号、shape 协商
    "EdgeCloudCtrlComm",
    # 隐藏状态传输抽象基类
    "HiddenStatesTransfer",
    # HCCL 数据面实现：基于 torch.distributed.send/recv
    "HiddenStatesTransferHCCL",
    # 边云协同生命周期管理器：初始化 TCP + HCCL 链路并 warmup
    "EdgeCloudManager",
]
