#
# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
# This file is a part of the vllm-ascend project.
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
#

"""
PD-separation (Edge-Cloud Pipeline Parallel disaggregation) configuration.

This module provides configuration for the edge-cloud bidirectional
ZMQ channels used in PD-separation deployments. Configuration is loaded
from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class PDSeparationConfig:
    """
    Configuration for PD-separation (Edge-Cloud disaggregated inference).

    This configuration controls the ZMQ communication channels between
    edge node (rank 0, hosting head/tail layers) and cloud node
    (rank 1, hosting middle layers with PassiveEngineCore).
    """

    # PRE_OUT channel: Edge → Cloud (publishes SchedulerOutputs with *_FIRST)
    # Default port: 5558
    pre_out_port: int = 5558

    # POST_OUT channel: Cloud → Edge (publishes SchedulerOutputs with *_LAST)
    # Default port: 5559
    post_out_port: int = 5559

    # Dispatch policy for PassiveScheduler on the cloud side.
    # Valid options: "expect_alternation", "prefill_first", "decode_first", "pdmix_first"
    # Default: "expect_alternation" - implements EEP/EED PD-covering state machine
    dispatch_policy: str = "expect_alternation"

    # Legacy single-channel ZMQ address for Phase 1 PD-separation.
    # Deprecated in Phase 2-3 in favor of dual-port (PRE_OUT/POST_OUT) topology.
    scheduler_zmq_addr: Optional[str] = None

    @classmethod
    def from_env(cls) -> "PDSeparationConfig":
        """
        Load PD-separation configuration from environment variables.

        Environment variables:
            VLLM_PP_PRE_OUT_ZMQ_PORT: PRE_OUT channel port (default: 5558)
            VLLM_PP_POST_OUT_ZMQ_PORT: POST_OUT channel port (default: 5559)
            VLLM_PP_PASSIVE_DISPATCH_POLICY: PassiveScheduler dispatch policy
            VLLM_PP_SCHEDULER_ZMQ_ADDR: Legacy single-channel ZMQ address

        Returns:
            PDSeparationConfig: Loaded configuration
        """
        return cls(
            pre_out_port=int(os.getenv("VLLM_PP_PRE_OUT_ZMQ_PORT", cls.pre_out_port)),
            post_out_port=int(os.getenv(
                "VLLM_PP_POST_OUT_ZMQ_PORT", cls.post_out_port
            )),
            dispatch_policy=os.getenv(
                "VLLM_PP_PASSIVE_DISPATCH_POLICY", cls.dispatch_policy
            ),
            scheduler_zmq_addr=os.getenv("VLLM_PP_SCHEDULER_ZMQ_ADDR"),
        )

    def get_pre_out_bind_addr(self) -> str:
        """Get ZMQ bind address for PRE_OUT channel (edge side)."""
        return f"tcp://*:{self.pre_out_port}"

    def get_post_out_bind_addr(self) -> str:
        """Get ZMQ bind address for POST_OUT channel (cloud side)."""
        return f"tcp://*:{self.post_out_port}"

    def get_pre_out_connect_addr(self, host: str) -> str:
        """Get ZMQ connect address for PRE_OUT channel (cloud side)."""
        return f"tcp://{host}:{self.pre_out_port}"

    def get_post_out_connect_addr(self, host: str) -> str:
        """Get ZMQ connect address for POST_OUT channel (edge side)."""
        return f"tcp://{host}:{self.post_out_port}"
