# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from typing import TYPE_CHECKING, Any

import torch
from vllm.compilation.cuda_graph import CUDAGraphOptions
from vllm.config import CUDAGraphMode, VllmConfig
from vllm.forward_context import BatchDescriptor, get_forward_context

from vllm_ascend.ascend_forward_context import _EXTRA_CTX
from vllm_ascend.compilation import acl_graph as _acl_graph
from vllm_ascend.compilation.acl_graph import ACLGraphWrapper, GraphParams, _is_dsa_kv_metadata_keys

if TYPE_CHECKING:
    from collections.abc import Callable


GraphMetadataPath = tuple[str | int, ...]
GraphTensorKey = tuple[
    int,
    tuple[int, ...],
    tuple[int, ...],
    torch.dtype,
    torch.device,
]
_DSA_GRAPH_REFRESH_FIELDS = frozenset({"block_table", "block_tables"})


def _uses_deepseek_v4_dsa(vllm_config: VllmConfig) -> bool:
    hf_config = getattr(vllm_config.model_config, "hf_text_config", None)
    return getattr(hf_config, "model_type", "") == "deepseek_v4"


def _segment_layer_range(runnable: Callable) -> tuple[int, int] | None:
    """Find the layer range through an optional compiled-segment wrapper."""
    current = runnable
    while current is not None:
        start_layer = getattr(current, "_start_layer", None)
        end_layer = getattr(current, "_end_layer", None)
        if isinstance(start_layer, int) and isinstance(end_layer, int):
            return start_layer, end_layer
        current = getattr(current, "_segment", None)
    return None


def _filter_segment_dsa_metadata(
    attn_metadata: Any,
    layer_range: tuple[int, int] | None,
) -> dict[str, Any]:
    """Return only DSA KV metadata consumed by this edge-cloud segment."""
    if not isinstance(attn_metadata, dict) or layer_range is None:
        return {}

    start_layer, end_layer = layer_range
    result: dict[str, Any] = {}
    for layer_idx in range(start_layer, end_layer):
        needle = f".layers.{layer_idx}."
        matched_keys = [key for key in attn_metadata if needle in key]
        if not _is_dsa_kv_metadata_keys(matched_keys, layer_idx):
            continue
        for key in matched_keys:
            result[key] = attn_metadata[key]
    return result


def _collect_dsa_block_tables(
    value: Any,
    *,
    path: GraphMetadataPath = (),
) -> dict[GraphMetadataPath, torch.Tensor]:
    """Collect the DSA block-table tensors that become graph inputs."""
    result: dict[GraphMetadataPath, torch.Tensor] = {}
    if is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            item = getattr(value, field.name)
            field_path = (*path, field.name)
            if field.name in _DSA_GRAPH_REFRESH_FIELDS and item is not None:
                if not isinstance(item, torch.Tensor):
                    raise RuntimeError(
                        "DSA graph block table is not a tensor at "
                        f"{field_path}: {type(item).__name__}"
                    )
                result[field_path] = item
            result.update(_collect_dsa_block_tables(item, path=field_path))
    elif isinstance(value, dict):
        for key, item in value.items():
            result.update(
                _collect_dsa_block_tables(item, path=(*path, str(key)))
            )
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            result.update(
                _collect_dsa_block_tables(item, path=(*path, index))
            )
    return result


def _copy_graph_captured_block_tables(
    captured: dict[GraphMetadataPath, torch.Tensor],
    current: dict[GraphMetadataPath, torch.Tensor],
) -> int:
    """Refresh exact graph-captured DSA block-table addresses."""
    if captured.keys() != current.keys():
        raise RuntimeError(
            "DSA graph block-table paths changed before replay: "
            f"captured_only={sorted(captured.keys() - current.keys())}, "
            f"current_only={sorted(current.keys() - captured.keys())}"
        )

    memo: set[GraphTensorKey] = set()
    copies = 0
    for path, dst in captured.items():
        src = current[path]
        if not (
            dst.shape == src.shape
            and dst.dtype == src.dtype
            and dst.device == src.device
        ):
            raise RuntimeError(
                f"DSA graph block-table tensor mismatch at {path}: "
                f"captured=({tuple(dst.shape)}, {dst.dtype}, {dst.device}), "
                f"current=({tuple(src.shape)}, {src.dtype}, {src.device})"
            )
        key: GraphTensorKey = (
            dst.data_ptr(),
            tuple(dst.shape),
            tuple(dst.stride()),
            dst.dtype,
            dst.device,
        )
        if key in memo:
            continue
        memo.add(key)
        if dst.data_ptr() != src.data_ptr():
            dst.copy_(src, non_blocking=True)
            copies += 1
    return copies


# ============================================================
#  GraphParams 作用域管理
#  —— 通过直接交换 acl_graph._graph_params / _draft_graph_params
#     来影响 get_graph_params() 的返回值。
#     attention 后端通过 from-import 获取的函数引用不受影响，
#     因为函数体内读取的是模块级变量。
# ============================================================

def make_graph_params(aclgraph_capture_sizes: list[int]) -> GraphParams:
    """创建 GraphParams 实例（供边云 segment wrapper 初始化独立参数）。

    与 acl_graph.set_graph_params 字段完全一致（7 字段），
    但不写入全局 _graph_params，而是返回独立实例供每个
    EdgeCloudACLGraphWrapper 持有，实现 segment 间参数隔离。
    """
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


@contextmanager
def graph_params_scope_no_sync(
    graph_params: GraphParams | None,
    draft_graph_params: GraphParams | None = None,
):
    """与 graph_params_scope 相同，但退出时不同步 NPU 主 stream。

    仅用于 update_full_graph_params 等已知 work 全在独立 update_stream 上、
    且不需要阻塞主 stream 的场景。图回放前仍需由调用方保证 update_stream
    上的参数更新已全部完成。
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

    通过 graph_params_scope 将 acl_graph 的 _graph_params 临时替换为本
    segment 的独立 GraphParams，确保 attention 后端在 capture/replay 期间
    操作正确的参数集。DeepSeek-V4 FULL 图还会在 replay 前刷新该具体图捕获
    的 DSA metadata 地址，隔离边云批次穿插造成的共享 buffer 覆盖。
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
        self._refresh_dsa_metadata_before_replay = (
            runtime_mode == CUDAGraphMode.FULL
            and _uses_deepseek_v4_dsa(vllm_config)
        )
        self._segment_layer_range = _segment_layer_range(runnable)
        self._captured_dsa_block_tables: dict[
            BatchDescriptor, dict[GraphMetadataPath, torch.Tensor]
        ] = {}

    def __call__(self, *args, **kwargs):
        if (
            self._refresh_dsa_metadata_before_replay
            and not _EXTRA_CTX.is_draft_model
        ):
            forward_context = get_forward_context()
            if forward_context.cudagraph_runtime_mode == self.runtime_mode:
                batch_descriptor = forward_context.batch_descriptor
                current_metadata = _filter_segment_dsa_metadata(
                    forward_context.attn_metadata,
                    self._segment_layer_range,
                )
                entry = self.concrete_aclgraph_entries.get(batch_descriptor)
                is_capture = entry is None or entry.aclgraph is None
                current_block_tables = _collect_dsa_block_tables(
                    current_metadata
                )
                if is_capture:
                    # Keep the exact views that the DSA custom op consumes
                    # during this concrete graph capture.
                    if current_block_tables:
                        self._captured_dsa_block_tables[batch_descriptor] = (
                            current_block_tables
                        )
                    else:
                        self._captured_dsa_block_tables.pop(
                            batch_descriptor, None
                        )
                else:
                    captured_block_tables = self._captured_dsa_block_tables.get(
                        batch_descriptor
                    )
                    if captured_block_tables is None and current_block_tables:
                        raise RuntimeError(
                            "Missing DeepSeek-V4 edge-cloud DSA block tables for "
                            f"ACL graph replay: {batch_descriptor}"
                        )
                    if captured_block_tables is not None:
                        # Submitted on the current stream immediately before
                        # replay, preserving copy -> graph execution order.
                        _copy_graph_captured_block_tables(
                            captured_block_tables,
                            current_block_tables,
                        )

        # 使用 no_sync 变体：capture 时仅切换 _graph_params 指针供 attention 后端
        # 填充本 segment 参数，replay 时指针切换无副作用（replay 不再读取全局指针）。
        # 不在退出时同步主 stream，避免 replay 后 host-block 破坏 CPU-NPU 掩盖。
        with graph_params_scope_no_sync(self.graph_params, self.draft_graph_params):
            return super().__call__(*args, **kwargs)
