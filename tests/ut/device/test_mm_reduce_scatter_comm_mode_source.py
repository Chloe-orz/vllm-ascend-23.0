# SPDX-License-Identifier: Apache-2.0
"""Import-free regressions for MM+ReduceScatter communication modes."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
DEVICE_OP = ROOT / "vllm_ascend" / "device" / "device_op.py"
LINEAR_OP = ROOT / "vllm_ascend" / "ops" / "linear_op.py"


def _load_method(class_name: str):
    module = ast.parse(DEVICE_OP.read_text())
    class_node = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    method = next(
        node
        for node in class_node.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "npu_mm_reduce_scatter_base"
    )
    method.decorator_list = []
    method.returns = None
    for arg in (
        method.args.args
        + method.args.posonlyargs
        + method.args.kwonlyargs
    ):
        arg.annotation = None

    calls = []

    def fake_mm_reduce_scatter(*args, **kwargs):
        calls.append((args, kwargs))
        return "output"

    namespace = {
        "os": os,
        "torch_npu": SimpleNamespace(
            npu_mm_reduce_scatter_base=fake_mm_reduce_scatter
        ),
    }
    extracted = ast.fix_missing_locations(
        ast.Module(body=[method], type_ignores=[])
    )
    exec(compile(extracted, str(DEVICE_OP), "exec"), namespace)
    return namespace["npu_mm_reduce_scatter_base"], calls


def test_base_device_keeps_aiv_comm_mode() -> None:
    method, calls = _load_method("BaseDeviceAdaptor")

    assert method("x1", "x2", "hcom", 2) == "output"
    assert calls[0][1]["comm_mode"] == "aiv"


def test_a5_device_uses_supported_comm_modes() -> None:
    method, calls = _load_method("A5DeviceAdaptor")

    with mock.patch.dict(os.environ, {}, clear=True):
        assert method("x1", "x2", "hcom", 2) == "output"
    assert calls[-1][1]["comm_mode"] == "ai_cpu"

    with mock.patch.dict(
        os.environ, {"HCCL_OP_EXPANSION_MODE": "CCU_SCHED"}, clear=True
    ):
        assert method("x1", "x2", "hcom", 2) == "output"
    assert calls[-1][1]["comm_mode"] == "ccu"


def test_sequence_row_parallel_uses_device_adaptor() -> None:
    module = ast.parse(LINEAR_OP.read_text())
    class_node = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef)
        and node.name == "SequenceRowParallelOp"
    )
    method = next(
        node
        for node in class_node.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "matmul_and_reduce"
    )
    calls = [
        node.func
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
    ]

    assert any(
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "DeviceOperator"
        and func.attr == "npu_mm_reduce_scatter_base"
        for func in calls
    )
    assert not any(
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "torch_npu"
        and func.attr == "npu_mm_reduce_scatter_base"
        for func in calls
    )
