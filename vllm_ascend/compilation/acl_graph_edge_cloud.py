# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

import torch
from vllm.config import VllmConfig
from vllm.compilation.cuda_graph import CUDAGraphOptions
from vllm.config import CUDAGraphMode

from vllm_ascend.compilation import acl_graph as _acl_graph
from vllm_ascend.compilation.acl_graph import (
    ACLGraphWrapper,
    GraphParams,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any


# ============================================================
#  GraphParams 作用域管理
#  —— 通过直接交换 acl_graph._graph_params / _draft_graph_params
#     来影响 get_graph_params() 的返回值。
#     attention 后端通过 from-import 获取的函数引用不受影响，
#     因为函数体内读取的是模块级变量。
# ============================================================

def make_graph_params(aclgraph_capture_sizes: list[int]) -> GraphParams:
    """创建 GraphParams 实例（供边云 segment wrapper 初始化独立参数）。"""
    return GraphParams(
        {size: [] for size in aclgraph_capture_sizes},
        {size: None for size in aclgraph_capture_sizes},
        {size: [] for size in aclgraph_capture_sizes},
        {size: [] for size in aclgraph_capture_sizes},
    )


@contextmanager
def graph_params_scope(
    graph_params: GraphParams | None,
    draft_graph_params: GraphParams | None = None,
):
    """临时将 acl_graph 的 _graph_params / _draft_graph_params 替换为指定参数。

    所有通过 get_graph_params() / get_draft_graph_params() 或 global 语句
    访问这些模块级变量的代码（包括 attention 后端和 ACLGraphWrapper）
    都会自动感知到替换后的值。

    退出时同步 NPU 流并恢复原值，防止后续 segment 读到错误参数。
    """
    old_graph_params = _acl_graph._graph_params
    old_draft_graph_params = _acl_graph._draft_graph_params
    if graph_params is not None:
        _acl_graph._graph_params = graph_params
    if draft_graph_params is not None:
        _acl_graph._draft_graph_params = draft_graph_params
    try:
        yield
    finally:
        if graph_params is not None:
            torch.npu.current_stream().synchronize()
        _acl_graph._graph_params = old_graph_params
        _acl_graph._draft_graph_params = old_draft_graph_params


# ============================================================
#  边云分段 ACLGraphWrapper
#  —— 继承标准 ACLGraphWrapper，在 __call__ 中注入
#     graph_params_scope，使图捕获/回放期间 attention 后端
#     获取到本 segment 的独立 GraphParams。
# ============================================================

class EdgeCloudACLGraphWrapper(ACLGraphWrapper):
    """边云分段 ACL 图包装器。

    与标准 ACLGraphWrapper 的唯一区别：__call__ 中通过 graph_params_scope
    将 acl_graph 的 _graph_params 临时替换为本 segment 的独立 GraphParams，
    确保 attention 后端在 capture/replay 期间操作正确的参数集。
    """

    def __init__(
        self,
        runnable: Callable,
        vllm_config: VllmConfig,
        runtime_mode: CUDAGraphMode,
        cudagraph_options: CUDAGraphOptions | None = None,
        *,
        use_eagle: bool = False,
        enable_enpu: bool = False,
    ):
        super().__init__(
            runnable, vllm_config, runtime_mode, cudagraph_options,
            use_eagle=use_eagle, enable_enpu=enable_enpu,
        )
        # 每个 segment wrapper 持有独立的 GraphParams，
        # 避免 segment_a / segment_e / segment_c 的
        # task handle / event / attn_params 混入同一全局列表
        self.graph_params: GraphParams | None = None
        self.draft_graph_params: GraphParams | None = None

    def __call__(self, *args, **kwargs):
        with graph_params_scope(self.graph_params, self.draft_graph_params):
            return super().__call__(*args, **kwargs)


# ============================================================
#  边云分段图参数更新
# ============================================================

def update_segment_graph_params(
    attn_backend: Any,
    update_stream: Any,
    forward_context: Any,
    num_tokens: int,
    vllm_config: Any,
    layer_indices: list[int],
    graph_params: GraphParams,
    draft_graph_params: GraphParams | None = None,
    speculative_config: Any = None,
    num_dcp_pcp_tokens: int | None = None,
    draft_attn_metadatas: Any = None,
) -> None:
    """边云分段流程：使用 segment 独立 GraphParams 更新指定层的 attention 图参数。

    本函数自包含 graph_params_scope：将 acl_graph._graph_params 临时替换为
    当前 segment 的独立 GraphParams，使 impl_cls.update_graph_params 内部
    通过 get_graph_params() 获取到正确的 (events, workspaces, handles, attn_params)。

    处理 attention metadata 的两层过滤：
    1. 剔除 skip_graph_params_update 标记的 DSA 层
    2. 按 layer_indices 过滤仅保留当前 segment 的层
    """
    assert layer_indices == sorted(layer_indices), (
        "layer_indices must be in ascending natural order to align with "
        "graph_params.attn_params append order."
    )

    original_attn_metadata = forward_context.attn_metadata

    # Step 1: 剔除 DSA 层（skip_graph_params_update）
    working_metadata = original_attn_metadata
    if original_attn_metadata:
        filtered = {
            k: v for k, v in original_attn_metadata.items()
            if not getattr(v, 'skip_graph_params_update', False)
        }
        if len(filtered) != len(original_attn_metadata):
            forward_context.attn_metadata = filtered
            working_metadata = filtered

    # Step 2: 按 layer_indices 过滤
    forward_context.attn_metadata = _filter_attn_metadata_for_layers(
        working_metadata, layer_indices
    )

    # 将当前 segment 的 GraphParams 设为活跃，使 impl_cls.update_graph_params
    # 通过 get_graph_params() 获取到正确的 segment 参数。
    # scope 退出时自动 synchronize + 恢复全局 GraphParams。
    with graph_params_scope(graph_params, draft_graph_params):
        impl_cls = attn_backend.get_impl_cls()
        try:
            impl_cls.update_graph_params(
                update_stream,
                forward_context,
                num_tokens,
                vllm_config,
                speculative_config,
                num_dcp_pcp_tokens,
                draft_attn_metadatas,
            )
        finally:
            forward_context.attn_metadata = original_attn_metadata
    # scope 退出时已完成 synchronize，确保异步 attention 参数更新在返回前完成


def _filter_attn_metadata_for_layers(
    attn_metadata: dict,
    layer_indices: list[int],
) -> dict:
    """返回仅包含指定层索引对应条目的 dict，key 顺序与 layer_indices 一致。

    attn_metadata 的 key 格式通常为 ``"model.layers.3.self_attn"``。
    通过匹配 ``.layers.{idx}.`` 子串来定位目标层。
    """
    result: dict = {}
    skipped_no_key_layers: list[int] = []
    for idx in layer_indices:
        needle = f".layers.{idx}."
        matched_keys = [k for k in attn_metadata if needle in k]
        if not matched_keys:
            skipped_no_key_layers.append(idx)
            continue
        if len(matched_keys) > 1:
            raise ValueError(
                f"Layer {idx} has multiple attention metadata keys: {matched_keys}. "
                f"This breaks the 1:1 alignment between attn_metadata and attn_params."
            )
        result[matched_keys[0]] = attn_metadata[matched_keys[0]]

    return result
