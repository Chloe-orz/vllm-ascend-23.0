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

from vllm.triton_utils import HAS_TRITON

from vllm_ascend.utils import is_310p, vllm_version_is

if HAS_TRITON:
    import vllm_ascend.patch.worker.patch_triton
    import vllm_ascend.patch.worker.patch_v2.patch_triton  # noqa


# isort: off
import vllm_ascend.patch.worker.patch_weight_utils  # noqa
import vllm_ascend.patch.platform.patch_sched_yield  # noqa
import vllm_ascend.patch.worker.patch_bert  # noqa
import vllm_ascend.patch.worker.patch_distributed  # noqa
import vllm_ascend.patch.worker.patch_minimax_m2  # noqa
import vllm_ascend.patch.worker.patch_minimax_m2_linear_attn  # noqa
import vllm_ascend.patch.worker.patch_mamba_utils  # noqa
import vllm_ascend.patch.worker.patch_multimodal_merge  # noqa
import vllm_ascend.patch.worker.patch_qwen3_next_mtp  # noqa

if not is_310p():
    import vllm_ascend.patch.worker.patch_qwen3_5  # noqa
    import vllm_ascend.patch.worker.patch_gdn_attn  # noqa

    if not vllm_version_is("0.19.0"):
        import vllm_ascend.patch.worker.patch_qwen3_dflash  # noqa

    # 边云协同推理：当 edge_cloud_config.enabled 为 True 时，
    # 动态加载对应模型的 Monkey Patch，添加 forward_edge_cloud_segment 方法，
    # 支持分段 islice 遍历。
    try:
        from vllm_ascend.ascend_config import get_ascend_config
        edge_cloud_cfg = get_ascend_config().edge_cloud_config
        if edge_cloud_cfg.enabled:
            # 通用 Patch（Llama / Qwen2 / DeepSeek-V2 / V3 等）
            import vllm_ascend.patch.models.llama_edge_cloud  # noqa

            # Qwen3.5 专用 Patch（参数顺序不同，另开实现便于理解）
            try:
                import vllm_ascend.patch.models.qwen3_5_edge_cloud  # noqa
            except Exception:
                # vllm 版本中可能不存在 qwen3_5，忽略
                pass

            # DeepSeek-V4 专用 Patch（架构差异大，需独立分段 forward）
            try:
                import vllm_ascend.patch.models.deepseek_v4_edge_cloud  # noqa
            except Exception:
                # vllm 版本中可能不存在 deepseek_v4，忽略
                pass
    except Exception:
        # ascend_config 未初始化时不加载（如单元测试场景）
        pass

import vllm_ascend.patch.worker.patch_rejection_sampler  # noqa
import vllm_ascend.patch.worker.patch_v2.patch_uva  # noqa
import vllm_ascend.patch.worker.patch_huanyuan_vl  # noqa
import vllm_ascend.patch.worker.patch_routed_experts_capturer  # noqa
import vllm_ascend.patch.worker.patch_npugraph_ex_triton  # noqa
import vllm_ascend.patch.worker.patch_kimi_k25  # noqa
import vllm_ascend.patch.worker.patch_draft_quarot  # noqa
import vllm_ascend.patch.worker.patch_cudagraph  # noqa
import vllm_ascend.patch.worker.patch_deepseek_mtp  # noqa
import vllm_ascend.patch.worker.patch_v2.patch_input_batch  # noqa
import vllm_ascend.patch.worker.patch_v2.patch_model_state  # noqa
import vllm_ascend.patch.worker.patch_v2.patch_block_table  # noqa
import vllm_ascend.patch.worker.patch_gqa_c8  # noqa
import vllm_ascend.patch.worker.patch_qwen3vl  # noqa
import vllm_ascend.patch.worker.patch_v2.patch_attn_utils  # noqa
import vllm_ascend.patch.worker.patch_bailing_moe_linear  # noqa
