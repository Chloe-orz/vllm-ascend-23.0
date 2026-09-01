# SPDX-License-Identifier: Apache-2.0
"""Import-free regressions for the A3 layerwise-P MMRS fallback."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
FORWARD_CONTEXT = ROOT / "vllm_ascend" / "ascend_forward_context.py"


def _load_fallback_predicate(device_type: str):
    module = ast.parse(FORWARD_CONTEXT.read_text())
    function = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "_disable_mmrs_fusion_for_a3_layerwise_prefill"
    )
    function.decorator_list = []
    function.returns = None
    for arg in function.args.args + function.args.posonlyargs + function.args.kwonlyargs:
        arg.annotation = None

    namespace = {
        "AscendDeviceType": SimpleNamespace(A3="A3"),
        "get_ascend_device_type": lambda: device_type,
        "torch": SimpleNamespace(bfloat16="bfloat16"),
    }
    extracted = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    exec(compile(extracted, str(FORWARD_CONTEXT), "exec"), namespace)
    return namespace["_disable_mmrs_fusion_for_a3_layerwise_prefill"]


def _make_config(
    *,
    connector: str = "MooncakeLayerwiseConnector",
    role: str = "kv_producer",
    dtype: str = "bfloat16",
    quant_config=None,
):
    return SimpleNamespace(
        kv_transfer_config=SimpleNamespace(
            kv_connector=connector,
            kv_role=role,
        ),
        model_config=SimpleNamespace(dtype=dtype),
        quant_config=quant_config,
    )


def test_a3_bf16_layerwise_prefill_disables_fused_mmrs() -> None:
    predicate = _load_fallback_predicate("A3")

    assert predicate(_make_config())


def test_fallback_does_not_change_other_mmrs_paths() -> None:
    a3_predicate = _load_fallback_predicate("A3")
    a2_predicate = _load_fallback_predicate("A2")

    assert not a2_predicate(_make_config())
    assert not a3_predicate(_make_config(role="kv_consumer"))
    assert not a3_predicate(_make_config(connector="MooncakeConnectorV1"))
    assert not a3_predicate(_make_config(dtype="float16"))
    assert not a3_predicate(_make_config(quant_config=object()))


def test_forward_context_applies_layerwise_mmrs_fallback() -> None:
    module = ast.parse(FORWARD_CONTEXT.read_text())
    function = next(
        node
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "set_ascend_forward_context"
    )

    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_disable_mmrs_fusion_for_a3_layerwise_prefill"
        for node in ast.walk(function)
    )
