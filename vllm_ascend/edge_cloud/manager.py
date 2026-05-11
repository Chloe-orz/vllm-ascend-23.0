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

"""边云协同生命周期管理器：负责解析配置、初始化控制链路和数据链路并预热。"""

import torch
from vllm.config import VllmConfig
from vllm.logger import logger

from vllm_ascend.ascend_config import get_ascend_config
from vllm_ascend.edge_cloud.edge_cloud_ctrl_comm import EdgeCloudCtrlComm
from vllm_ascend.edge_cloud.hidden_states_transfer_hccl import (
    HiddenStatesTransferHCCL,
)


class EdgeCloudManager:
    """边云协同生命周期管理器。

    职责：
    1. 解析 edge_cloud_config（role、IP、port、rank table 等）
    2. 初始化 TCP 控制链路（ctrl_comm.init_tcp_link）
    3. 初始化 HCCL 数据链路（data_comm.init_hccl）
    4. warmup HCCL 通信（data_comm.hccl_comm_warmup）
    """

    def __init__(self, vllm_config: VllmConfig):
        self.cfg = get_ascend_config().edge_cloud_config
        self.role = self.cfg.role

        # 初始化 TCP 控制面
        self.ctrl_comm = EdgeCloudCtrlComm(tls_config={})

        # 初始化 HCCL 数据面
        self.data_comm = HiddenStatesTransferHCCL(
            dtype=getattr(self.cfg, "hidden_dtype", torch.bfloat16),
            batch_p_num=getattr(self.cfg, "batch_p_num", 1),
        )
        # Edge 为 master，Cloud 为 slave
        self.data_comm.role = "master" if self.role == "edge" else "slave"

    def initialize(self) -> None:
        """初始化所有通信通道（TCP + HCCL）。"""
        transfer_cfg = getattr(self.cfg, "transfer_config", {})
        backend = transfer_cfg.get("backend", "hccl")
        peer_addrs = transfer_cfg.get("peer_addrs", [])

        if backend != "hccl":
            raise ValueError(
                f"Unsupported transfer backend: {backend}. "
                "Only 'hccl' is supported."
            )

        # 步骤 1：初始化 TCP 控制链路
        # Edge 作为 Server，Cloud 作为 Client
        server_ip = transfer_cfg.get("server_ip", "0.0.0.0")
        server_port = transfer_cfg.get("server_port", 9010)
        self.ctrl_comm.init_tcp_link(
            rank=0,
            role=self.role,
            server_ip=server_ip,
            server_port=server_port,
        )

        # 步骤 2：初始化 HCCL 数据链路
        peer_rank = transfer_cfg.get("peer_rank", 1)
        self.data_comm.init(peer_rank=peer_rank)

        logger.info(
            "[EdgeCloud] EdgeCloudManager initialized. Role=%s, backend=%s",
            self.role, backend,
        )

    def warmup(self, hidden_size: int) -> None:
        """预热 HCCL 通信通道，完成底层资源分配。"""
        self.data_comm.warmup(hidden_size)

    def shutdown(self) -> None:
        """关闭所有通信通道。"""
        self.ctrl_comm.close()
        logger.info("[EdgeCloud] EdgeCloudManager shutdown.")
