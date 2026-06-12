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
#

import os
from collections.abc import Callable
from typing import Any

from vllm import envs


_LAYERWISE_ENV_VARIABLES: dict[str, Callable[[], Any]] = {
    # Whether this is a non-leader PP rank running with a passive EngineCore.
    "VLLM_PP_NON_LEADER_ENGINE_CORE": lambda: bool(
        int(os.getenv("VLLM_PP_NON_LEADER_ENGINE_CORE", "0"))
    ),
    # ZMQ address for PP scheduler output communication between engine cores.
    "VLLM_PP_SCHEDULER_ZMQ_ADDR": lambda: os.getenv("VLLM_PP_SCHEDULER_ZMQ_ADDR", None),
    # ZMQ port for the edge-cloud PD-separation PRE_OUT channel.
    "VLLM_PP_PRE_OUT_ZMQ_PORT": lambda: int(os.getenv("VLLM_PP_PRE_OUT_ZMQ_PORT", "5558")),
    # ZMQ port for the edge-cloud PD-separation POST_OUT channel.
    "VLLM_PP_POST_OUT_ZMQ_PORT": lambda: int(os.getenv("VLLM_PP_POST_OUT_ZMQ_PORT", "5559")),
    # Layer slice size for non-leader PP ranks.
    "VLLM_LAYER_SLICE_SIZE": lambda: int(os.getenv("VLLM_LAYER_SLICE_SIZE", "0")),
    # Dispatch policy for the non-leader PP rank's passive scheduler.
    "VLLM_PP_PASSIVE_DISPATCH_POLICY": lambda: os.getenv(
        "VLLM_PP_PASSIVE_DISPATCH_POLICY", "expect_alternation"
    ),
}


def apply_layerwise_env_patch() -> None:
    for name, reader in _LAYERWISE_ENV_VARIABLES.items():
        envs.env_variables.setdefault(name, reader)


apply_layerwise_env_patch()
