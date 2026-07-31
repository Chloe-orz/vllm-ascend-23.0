# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
# This file is a part of the vllm-ascend project.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Unit tests for edge-cloud payload metadata and receive postprocessing."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
import torch
from vllm.distributed.parallel_state import TensorMetadata

import vllm_ascend.envs as envs_ascend
# Tests run on CPU; force the merged buffer allocator to use cpu instead of npu.
# We patch _allocate_merged_recv_buffer below per-test, but the simpler shape
# checks just inspect EdgeCloudTensorMeta fields, so most tests do not need NPU.
from vllm_ascend.distributed import parallel_state as ps


@pytest.fixture(autouse=True)
def _reset_meta():
    """Each test gets a fresh edge-cloud tensor meta."""
    saved_e2c = ps._EDGE_CLOUD_TENSOR_META_E2C
    saved_c2e = ps._EDGE_CLOUD_TENSOR_META_C2E
    saved = ps._EDGE_CLOUD_TENSOR_META
    ps._EDGE_CLOUD_TENSOR_META_E2C = None
    ps._EDGE_CLOUD_TENSOR_META_C2E = None
    ps._EDGE_CLOUD_TENSOR_META = None
    try:
        yield
    finally:
        ps._EDGE_CLOUD_TENSOR_META_E2C = saved_e2c
        ps._EDGE_CLOUD_TENSOR_META_C2E = saved_c2e
        ps._EDGE_CLOUD_TENSOR_META = saved


# ---------------------------------------------------------------------------
# init_edge_cloud_tensor_meta
# ---------------------------------------------------------------------------

def test_init_meta_merge_enabled_2d():
    """Standard 2D case: hidden_states + residual cat along dim=-1."""
    with patch.object(
        envs_ascend,
        "VLLM_ASCEND_EDGE_CLOUD_MERGE_PAYLOAD",
        True,
    ):
        ps.init_edge_cloud_tensor_meta(
            hidden_size=128,
            hidden_dtype=torch.bfloat16,
            has_residual=True,
            hc_mult=1,
        )
    meta = ps.get_edge_cloud_tensor_meta()
    assert meta.tensor_keys == ["hidden_states", "residual"]
    assert meta.merge_payload is True
    assert meta.merged_dtype == torch.bfloat16
    # 2D model: leading dim is num_tokens (placeholder 0); merged_shape_tail
    # drops dim 0, so it should be just (256,) = 128 + 128 along dim=-1.
    assert meta.merged_shape_tail == (256,)
    assert meta.split_sizes == [128, 128]


def test_init_meta_merge_enabled_3d_hc_mult():
    """DeepSeek V4 case: hidden + residual are (N, hc_mult, hidden)."""
    ps.init_edge_cloud_tensor_meta(
        hidden_size=128,
        hidden_dtype=torch.bfloat16,
        has_residual=True,
        hc_mult=4,
    )
    meta = ps.get_edge_cloud_tensor_meta()
    assert meta.merge_payload is True
    # 3D model: shape is (0, hc_mult, hidden), merged_shape_tail drops dim 0.
    # Cat is along dim=-1 (hidden), so tail becomes (hc_mult, 2 * hidden).
    assert meta.merged_shape_tail == (4, 256)
    assert meta.split_sizes == [128, 128]


def test_init_meta_merge_disabled_single_tensor():
    """has_residual=False → only one tensor → no merge."""
    ps.init_edge_cloud_tensor_meta(
        hidden_size=128,
        hidden_dtype=torch.bfloat16,
        has_residual=False,
        hc_mult=1,
    )
    meta = ps.get_edge_cloud_tensor_meta()
    assert meta.tensor_keys == ["hidden_states"]
    assert meta.merge_payload is False
    assert meta.split_sizes is None


def test_init_meta_merge_disabled_via_env(monkeypatch):
    """Env switch off → merge_payload stays False even with 2 tensors."""
    monkeypatch.setenv("VLLM_ASCEND_EDGE_CLOUD_MERGE_PAYLOAD", "0")
    # Reload the envs module so the lambda re-reads the env var.
    import importlib

    import vllm_ascend.envs as envs_ascend
    importlib.reload(envs_ascend)
    importlib.reload(ps)
    ps.init_edge_cloud_tensor_meta(
        hidden_size=128,
        hidden_dtype=torch.bfloat16,
        has_residual=True,
        hc_mult=1,
    )
    meta = ps.get_edge_cloud_tensor_meta()
    assert meta.merge_payload is False


# ---------------------------------------------------------------------------
# Round-trip: cat + narrow recover the original tensors exactly
# ---------------------------------------------------------------------------

def _build_meta_2d(hidden_size: int, dtype=torch.bfloat16):
    """Helper: build a 2D EdgeCloudTensorMeta directly (without env)."""
    tensor_shape = (0, hidden_size)
    metadata_list = [
        ("hidden_states", TensorMetadata("cpu", dtype, tensor_shape)),
        ("residual", TensorMetadata("cpu", dtype, tensor_shape)),
    ]
    return ps.EdgeCloudTensorMeta(
        metadata_list=metadata_list,
        tensor_keys=["hidden_states", "residual"],
        hc_mult=1,
        merge_payload=True,
        merged_dtype=dtype,
        merged_shape_tail=(2 * hidden_size,),
        split_sizes=[hidden_size, hidden_size],
    )


def test_cat_then_narrow_roundtrip_2d():
    """Verify that the receiver's split logic recovers the sender's tensors."""
    H = 64
    N = 17  # odd to catch any stride bug
    meta = _build_meta_2d(H)

    hidden = torch.randn(N, H, dtype=torch.bfloat16)
    residual = torch.randn(N, H, dtype=torch.bfloat16)

    # Sender-side cat (matches edge_cloud_isend_tensor_dict's merge path).
    merged = torch.cat([hidden, residual], dim=-1)
    assert merged.shape == (N, 2 * H)
    assert merged.is_contiguous()

    # Receiver-side split (use the real helper, force contiguous=True).
    split = ps._split_merged_buffer_into_dict(merged, meta, contiguous=True)
    assert torch.equal(split["hidden_states"], hidden)
    assert torch.equal(split["residual"], residual)
    assert split["hidden_states"].is_contiguous()
    assert split["residual"].is_contiguous()


def test_split_view_only_shares_storage():
    """contiguous=False should give zero-copy views into the merged buffer."""
    H = 32
    N = 8
    meta = _build_meta_2d(H)

    merged = torch.zeros(N, 2 * H, dtype=torch.bfloat16)
    split = ps._split_merged_buffer_into_dict(merged, meta, contiguous=False)

    # Views share the merged buffer's storage; writes through the merged
    # buffer must be visible through the views.
    merged[0, 0] = 1.0
    merged[0, H] = 2.0
    assert split["hidden_states"][0, 0].item() == 1.0
    assert split["residual"][0, 0].item() == 2.0
    # Last-dim narrow is NOT contiguous (stride is 2H, not H).
    assert not split["hidden_states"].is_contiguous()


def test_split_3d_hc_mult_layout():
    """DeepSeek V4 layout: cat along dim=-1 of (N, hc_mult, H)."""
    H = 32
    N = 4
    hc_mult = 3
    meta = ps.EdgeCloudTensorMeta(
        metadata_list=[
            ("hidden_states", TensorMetadata("cpu", torch.bfloat16, (0, hc_mult, H))),
            ("residual", TensorMetadata("cpu", torch.bfloat16, (0, hc_mult, H))),
        ],
        tensor_keys=["hidden_states", "residual"],
        hc_mult=hc_mult,
        merge_payload=True,
        merged_dtype=torch.bfloat16,
        merged_shape_tail=(hc_mult, 2 * H),
        split_sizes=[H, H],
    )
    hidden = torch.randn(N, hc_mult, H, dtype=torch.bfloat16)
    residual = torch.randn(N, hc_mult, H, dtype=torch.bfloat16)
    merged = torch.cat([hidden, residual], dim=-1)
    assert merged.shape == (N, hc_mult, 2 * H)

    split = ps._split_merged_buffer_into_dict(merged, meta, contiguous=True)
    assert torch.equal(split["hidden_states"], hidden)
    assert torch.equal(split["residual"], residual)


# ---------------------------------------------------------------------------
# Direction-aware meta: embedding_only drops residual on edge→cloud only
# ---------------------------------------------------------------------------

def test_init_meta_direction_aware_embedding_only():
    """embedding_only: e2c omits residual on the wire but receiver still
    allocates a zero residual buffer; c2e keeps it on the wire."""
    ps.init_edge_cloud_tensor_meta(
        hidden_size=128,
        hidden_dtype=torch.bfloat16,
        has_residual=True,
        hc_mult=1,
        mode="embedding_only",
    )
    e2c = ps.get_edge_cloud_tensor_meta("e2c")
    c2e = ps.get_edge_cloud_tensor_meta("c2e")
    # Receiver allocates both buffers so model layers stay unchanged.
    assert e2c.tensor_keys == ["hidden_states", "residual"]
    # Sender only puts hidden_states on the wire.
    assert e2c.send_tensor_keys == ["hidden_states"]
    assert e2c.merge_payload is False  # only one tensor is sent
    assert c2e.tensor_keys == ["hidden_states", "residual"]
    assert c2e.send_tensor_keys == ["hidden_states", "residual"]
    # Backward-compatible (no-arg) accessor returns the dense c2e meta.
    assert ps.get_edge_cloud_tensor_meta().tensor_keys == c2e.tensor_keys


def test_init_meta_direction_aware_head_tail():
    """head_tail: both directions carry residual (identical)."""
    with patch.object(
        envs_ascend,
        "VLLM_ASCEND_EDGE_CLOUD_MERGE_PAYLOAD",
        True,
    ):
        ps.init_edge_cloud_tensor_meta(
            hidden_size=128,
            hidden_dtype=torch.bfloat16,
            has_residual=True,
            hc_mult=1,
            mode="head_tail",
        )
    e2c = ps.get_edge_cloud_tensor_meta("e2c")
    c2e = ps.get_edge_cloud_tensor_meta("c2e")
    assert e2c.tensor_keys == ["hidden_states", "residual"]
    assert e2c.send_tensor_keys == ["hidden_states", "residual"]
    assert c2e.tensor_keys == ["hidden_states", "residual"]
    assert c2e.send_tensor_keys == ["hidden_states", "residual"]
    assert e2c.merge_payload is True
    assert c2e.merge_payload is True


def test_init_meta_materialized_boundary_omits_residual():
    """materialized boundary: both directions transfer hidden_states only."""
    with patch.object(
        envs_ascend,
        "VLLM_ASCEND_EDGE_CLOUD_MERGE_PAYLOAD",
        True,
    ):
        ps.init_edge_cloud_tensor_meta(
            hidden_size=128,
            hidden_dtype=torch.bfloat16,
            has_residual=True,
            hc_mult=1,
            mode="head_tail",
            materialize_residual_boundary=True,
        )
    e2c = ps.get_edge_cloud_tensor_meta("e2c")
    c2e = ps.get_edge_cloud_tensor_meta("c2e")
    assert e2c.tensor_keys == ["hidden_states"]
    assert e2c.send_tensor_keys == ["hidden_states"]
    assert c2e.tensor_keys == ["hidden_states"]
    assert c2e.send_tensor_keys == ["hidden_states"]
    assert e2c.merge_payload is False
    assert c2e.merge_payload is False


# ---------------------------------------------------------------------------
# Non-merge receive: SP chunk must run after recv + TP broadcast
# ---------------------------------------------------------------------------

class _RecordingHandle:
    def __init__(self, events, event, on_wait=None):
        self.events = events
        self.event = event
        self.on_wait = on_wait

    def wait(self):
        self.events.append(self.event)
        if self.on_wait is not None:
            self.on_wait()


def _materialized_meta(hidden_size=4):
    return ps.EdgeCloudTensorMeta(
        metadata_list=[
            (
                "hidden_states",
                TensorMetadata("cpu", torch.float32, (0, hidden_size)),
            ),
        ],
        tensor_keys=["hidden_states"],
        hc_mult=1,
        merge_payload=False,
        merged_dtype=None,
        merged_shape_tail=None,
        split_sizes=None,
        send_tensor_keys=["hidden_states"],
    )


def test_non_merge_pp_rank_chunks_after_recv_and_broadcast():
    """PP rank 0 must not clone an unfilled async receive buffer."""
    events = []
    recv_tensor = torch.zeros(2, 4)
    recv_handle = _RecordingHandle(
        events,
        "recv_wait",
        on_wait=lambda: recv_tensor.fill_(1),
    )

    def fake_broadcast(*args, **kwargs):
        events.append("broadcast_start")
        return _RecordingHandle(events, "broadcast_wait")

    def fake_sp_chunk(tensor_dict):
        events.append("sp_chunk")
        assert torch.equal(tensor_dict["hidden_states"], torch.ones(2, 4))

    with (
        patch.object(ps, "get_pp_group", return_value=SimpleNamespace(world_size=2)),
        patch.object(
            ps,
            "get_tp_group",
            return_value=SimpleNamespace(
                ranks=[0],
                cpu_group=object(),
                device_group=object(),
            ),
        ),
        patch.object(ps, "_select_edge_cloud_meta_for_recv",
                     return_value=_materialized_meta()),
        patch.object(
            ps,
            "edge_cloud_irecv_tensor_dict_on_hidden_channel",
            return_value=(
                {"hidden_states": recv_tensor},
                [recv_handle],
                [],
            ),
        ),
        patch.object(torch.distributed, "broadcast", side_effect=fake_broadcast),
        patch.object(ps, "_apply_sp_chunk_inplace", side_effect=fake_sp_chunk),
    ):
        tensor_dict, handles, postprocess = ps.edge_cloud_broadcast_recv(
            num_tokens=2,
            sp_chunk=True,
        )

        assert tensor_dict["hidden_states"].sum().item() == 0
        assert events == []
        for handle in handles:
            handle.wait()
        for callback in postprocess:
            callback()

    assert events == [
        "recv_wait",
        "broadcast_start",
        "broadcast_wait",
        "sp_chunk",
    ]


def test_non_merge_non_pp_rank_chunks_after_broadcast():
    """Other TP ranks must chunk only after their broadcast buffer is filled."""
    events = []

    def fake_broadcast(tensor, *args, **kwargs):
        events.append("broadcast_start")
        return _RecordingHandle(
            events,
            "broadcast_wait",
            on_wait=lambda: tensor.fill_(2),
        )

    def fake_sp_chunk(tensor_dict):
        events.append("sp_chunk")
        expected = torch.full((2, 4), 2.0)
        assert torch.equal(tensor_dict["hidden_states"], expected)

    with (
        patch.object(ps, "get_pp_group", return_value=SimpleNamespace(world_size=1)),
        patch.object(
            ps,
            "get_tp_group",
            return_value=SimpleNamespace(
                ranks=[0],
                cpu_group=object(),
                device_group=object(),
            ),
        ),
        patch.object(ps, "_select_edge_cloud_meta_for_recv",
                     return_value=_materialized_meta()),
        patch.object(ps, "_pad_num_tokens_to_tp_multiple", return_value=2),
        patch.object(torch.distributed, "broadcast", side_effect=fake_broadcast),
        patch.object(ps, "_apply_sp_chunk_inplace", side_effect=fake_sp_chunk),
    ):
        tensor_dict, handles, postprocess = ps.edge_cloud_broadcast_recv(
            num_tokens=2,
            sp_chunk=True,
        )

        assert handles == []
        assert events == []
        for callback in postprocess:
            callback()

    assert events == ["broadcast_start", "broadcast_wait", "sp_chunk"]
