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

from typing import Any


def validate_pd_separation_scheduler_conflicts(vllm_config: Any, ascend_config: Any) -> None:
    scheduler_config = getattr(vllm_config, "scheduler_config", None)
    if not getattr(scheduler_config, "enable_pd_separation", False):
        return

    if getattr(ascend_config, "recompute_scheduler_enable", False):
        raise ValueError(
            "scheduler_config.enable_pd_separation is incompatible with "
            "additional_config.recompute_scheduler_enable. Disable one of them."
        )

    if getattr(ascend_config, "SLO_limits_for_dynamic_batch", -1) != -1:
        raise ValueError(
            "scheduler_config.enable_pd_separation is incompatible with "
            "additional_config.SLO_limits_for_dynamic_batch. Disable one of them."
        )

    profiling_chunk_config = getattr(ascend_config, "profiling_chunk_config", None)
    if getattr(profiling_chunk_config, "enabled", False):
        raise ValueError(
            "scheduler_config.enable_pd_separation is incompatible with "
            "additional_config.profiling_chunk_config.enabled. Disable one of them."
        )
