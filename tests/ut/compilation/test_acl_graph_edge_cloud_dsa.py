# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
import torch

import vllm_ascend.compilation.acl_graph_edge_cloud as edge_cloud_graph
from vllm_ascend.compilation.acl_graph import ACLGraphWrapper
from vllm_ascend.compilation.acl_graph_edge_cloud import (
    EdgeCloudACLGraphWrapper,
    _collect_dsa_block_tables,
    _copy_graph_captured_block_tables,
    _filter_segment_dsa_metadata,
    _segment_layer_range,
    _uses_deepseek_v4_dsa,
)


@dataclass
class _Metadata:
    block_table: torch.Tensor
    block_tables: torch.Tensor


def test_only_deepseek_v4_enables_dsa_refresh():
    deepseek_config = SimpleNamespace(
        model_config=SimpleNamespace(hf_text_config=SimpleNamespace(model_type="deepseek_v4"))
    )
    qwen_config = SimpleNamespace(model_config=SimpleNamespace(hf_text_config=SimpleNamespace(model_type="qwen3_5")))

    assert _uses_deepseek_v4_dsa(deepseek_config)
    assert not _uses_deepseek_v4_dsa(qwen_config)


def test_filter_keeps_only_segment_dsa_metadata():
    metadata = {
        "model.layers.1.self_attn.attn": object(),
        "model.layers.2.self_attn.attn": object(),
        "model.layers.2.self_attn.swa_cache": object(),
        "model.layers.3.self_attn": object(),
    }

    filtered = _filter_segment_dsa_metadata(metadata, (2, 3))

    assert list(filtered) == [
        "model.layers.2.self_attn.attn",
        "model.layers.2.self_attn.swa_cache",
    ]


def test_segment_layer_range_unwraps_compiled_segment():
    segment = SimpleNamespace(_start_layer=61, _end_layer=62)
    compiled_segment = SimpleNamespace(_segment=segment)

    assert _segment_layer_range(compiled_segment) == (61, 62)


def test_copy_restores_overwritten_block_table_and_deduplicates_aliases():
    captured_block_table = torch.full((4, 3), 99, dtype=torch.int32)
    current_block_table = torch.arange(12, dtype=torch.int32).view(4, 3)
    captured_ptr = captured_block_table.data_ptr()

    captured = _collect_dsa_block_tables(_Metadata(captured_block_table, captured_block_table))
    current = _collect_dsa_block_tables(_Metadata(current_block_table, current_block_table))
    copies = _copy_graph_captured_block_tables(captured, current)

    assert copies == 1
    assert captured_block_table.data_ptr() == captured_ptr
    torch.testing.assert_close(captured_block_table, current_block_table)


def test_copy_fails_closed_on_shape_mismatch():
    with pytest.raises(RuntimeError, match="tensor mismatch"):
        _copy_graph_captured_block_tables(
            _collect_dsa_block_tables(
                _Metadata(
                    torch.zeros((4, 3), dtype=torch.int32),
                    torch.zeros((4, 3), dtype=torch.int32),
                )
            ),
            _collect_dsa_block_tables(
                _Metadata(
                    torch.zeros((5, 3), dtype=torch.int32),
                    torch.zeros((5, 3), dtype=torch.int32),
                )
            ),
        )


def test_wrapper_refreshes_concrete_capture_address_before_replay(
    monkeypatch,
):
    batch_descriptor = object()
    layer_key = "model.layers.2.self_attn.attn"
    captured_block_table = torch.zeros((4, 3), dtype=torch.int32)
    captured_metadata = {layer_key: _Metadata(captured_block_table, captured_block_table)}
    forward_context = SimpleNamespace(
        batch_descriptor=batch_descriptor,
        attn_metadata=captured_metadata,
        cudagraph_runtime_mode=edge_cloud_graph.CUDAGraphMode.FULL,
    )
    monkeypatch.setattr(edge_cloud_graph, "get_forward_context", lambda: forward_context)
    monkeypatch.setattr(edge_cloud_graph._EXTRA_CTX, "is_draft_model", False)

    wrapper = object.__new__(EdgeCloudACLGraphWrapper)
    wrapper._refresh_dsa_metadata_before_replay = True
    wrapper.runtime_mode = edge_cloud_graph.CUDAGraphMode.FULL
    wrapper._segment_layer_range = (2, 3)
    wrapper._captured_dsa_block_tables = {}
    wrapper.concrete_aclgraph_entries = {}
    wrapper.graph_params = None
    wrapper.draft_graph_params = None

    def _base_call(self, *args, **kwargs):
        if batch_descriptor not in self.concrete_aclgraph_entries:
            self.concrete_aclgraph_entries[batch_descriptor] = SimpleNamespace(aclgraph=object())
        return "ok"

    monkeypatch.setattr(ACLGraphWrapper, "__call__", _base_call)

    assert wrapper() == "ok"
    captured_paths = wrapper._captured_dsa_block_tables[batch_descriptor]
    assert any(tensor.data_ptr() == captured_block_table.data_ptr() for tensor in captured_paths.values())

    captured_block_table.fill_(99)
    expected_block_table = torch.arange(12, dtype=torch.int32).view(4, 3)
    forward_context.attn_metadata = {layer_key: _Metadata(expected_block_table, expected_block_table)}

    assert wrapper() == "ok"
    torch.testing.assert_close(captured_block_table, expected_block_table)
