# SPDX-License-Identifier: Apache-2.0
"""Import-free regressions for the Ascend GDN KKT launch contract."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
DEVICE_OP = ROOT / "vllm_ascend" / "device" / "device_op.py"


class _KernelSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[int, ...], dict[str, object]]] = []

    def __getitem__(self, grid: tuple[int, ...]):
        def launch(**kwargs: object) -> None:
            self.calls.append((grid, kwargs))

        return launch


def _load_kkt_launcher(class_name: str):
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
        and node.name == "chunk_scaled_dot_kkt_fwd"
    )
    method.decorator_list = []
    method.returns = None
    for arg in method.args.args:
        arg.annotation = None

    kernel = _KernelSpy()
    namespace = {"chunk_scaled_dot_kkt_fwd_kernel": kernel}
    extracted = ast.fix_missing_locations(
        ast.Module(body=[method], type_ignores=[])
    )
    exec(compile(extracted, str(DEVICE_OP), "exec"), namespace)
    return namespace["chunk_scaled_dot_kkt_fwd"], kernel


def _launch(launcher, *, num_core: int, task_num: int, tokens: int) -> None:
    launcher(
        num_core=num_core,
        bh_step=2,
        task_num=task_num,
        k=object(),
        beta=object(),
        g_cumsum=object(),
        A=object(),
        cu_seqlens=object(),
        chunk_indices=object(),
        T=tokens,
        B=1,
        H=2,
        Hg=1,
        K=128,
        BT=64,
        BK=128,
    )


def test_kkt_multibuffering_stays_disabled_across_sequential_shapes() -> None:
    for class_name in ("BaseDeviceAdaptor", "A5DeviceAdaptor"):
        launcher, kernel = _load_kkt_launcher(class_name)

        _launch(launcher, num_core=2, task_num=2, tokens=19)
        _launch(launcher, num_core=4, task_num=48, tokens=1513)

        assert [grid for grid, _ in kernel.calls] == [(2,), (4,)]
        assert all(
            call["multibuffer"] is False for _, call in kernel.calls
        )

