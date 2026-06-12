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

import sys


def install_ascend_pd_scheduler_shims() -> None:
    """Route upstream PD scheduler imports to vllm-ascend implementations.

    vLLM keeps the shared SchedulerOutput schema, while vllm-ascend owns the
    scheduler implementations. Some upstream glue imports the historical vLLM
    module paths lazily, so install aliases before those paths are resolved.
    """
    try:
        import vllm_ascend.core.passive_scheduler as passive_scheduler
        import vllm_ascend.core.pd_separated_scheduler as pd_separated_scheduler
    except ImportError:
        return

    sys.modules["vllm.v1.core.sched.passive_scheduler"] = passive_scheduler
    sys.modules["vllm.v1.core.sched.pd_separated_scheduler"] = pd_separated_scheduler


install_ascend_pd_scheduler_shims()
