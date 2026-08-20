# SPDX-License-Identifier: Apache-2.0
"""Source-level regressions for edge-cloud Mamba align prefix caching.

The failing path depends on an NPU edge-cloud runtime, but the regression is a
Python control-flow bug. Keep these checks import-free so they run in lightweight
environments while guarding the hand-off between ``cloud_prepare_early`` and
``execute_model``.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODEL_RUNNER = ROOT / "vllm_ascend" / "worker" / "model_runner_v1.py"
BATCHED_MODEL_RUNNER = ROOT / "vllm_ascend" / "worker" / "edge_cloud" / "batched_model_runner.py"


def _method(name: str, path: Path = MODEL_RUNNER) -> ast.FunctionDef:
    module = ast.parse(path.read_text())
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"method {name} not found in {path}")


def _src(name: str, path: Path = MODEL_RUNNER) -> str:
    return ast.unparse(_method(name, path))


def _if_branch(method_name: str, condition: str) -> ast.If:
    for node in ast.walk(_method(method_name)):
        if isinstance(node, ast.If) and ast.unparse(node.test) == condition:
            return node
    raise AssertionError(f"if branch {condition!r} not found in {method_name}")


def _guards_for_call(method_name: str, call: str, path: Path = MODEL_RUNNER) -> set[str]:
    guards: set[str] = set()
    for node in ast.walk(_method(method_name, path)):
        if not isinstance(node, ast.If):
            continue
        body_src = "\n".join(ast.unparse(stmt) for stmt in node.body)
        if call in body_src:
            guards.add(ast.unparse(node.test))
    return guards


def test_cloud_fast_path_restores_deferred_mamba_copy_buffer() -> None:
    early_prepare_src = _src("cloud_prepare_early")
    cloud_fast_path_src = ast.unparse(_if_branch("execute_model", "_cloud_fast_path"))

    assert "cache['mamba_preprocess_bufs'] = mamba_preprocess_bufs" in early_prepare_src
    assert "mamba_preprocess_bufs = cache['mamba_preprocess_bufs']" in cloud_fast_path_src


def test_mamba_copy_runs_only_for_metadata_pending_in_this_forward() -> None:
    execute_model_src = _src("execute_model")
    pending_copy_src = ast.unparse(_if_branch("execute_model", "mamba_preprocess_bufs is not None"))
    edge_fast_path_body = "\n".join(ast.unparse(node) for node in _if_branch("execute_model", "_fast_path").body)

    assert "mamba_preprocess_bufs = None" in execute_model_src
    assert "mamba_preprocess_bufs = mamba_bufs.preprocess" in execute_model_src
    assert "mamba_utils.do_mamba_copy_block(mamba_preprocess_bufs)" in pending_copy_src
    assert "mamba_preprocess_bufs =" not in edge_fast_path_body
    assert "do_mamba_copy_block(preprocess_bufs)" not in execute_model_src


def test_embedding_only_edge_skips_mamba_copy_preprocessing() -> None:
    initialize_src = _src("initialize_kv_cache")
    expected_guard = "self.cache_config.mamba_cache_mode == 'align' and self.need_accepted_tokens"

    # An embedding-only edge owns no attention/Mamba layers or cache tensors.
    # It retains the merged full-model KV config only for scheduler block-table
    # compatibility, so attempting to preprocess those remote layers raises a
    # KeyError when the request crosses a Mamba state-block boundary.
    assert "self.need_accepted_tokens = False" in initialize_src
    assert expected_guard in _guards_for_call("execute_model", "mamba_utils.preprocess_mamba")
    assert expected_guard in _guards_for_call("cloud_prepare_early", "mamba_utils.preprocess_mamba")
    assert expected_guard in _guards_for_call(
        "execute_model_pre",
        "mamba_utils.preprocess_mamba",
        BATCHED_MODEL_RUNNER,
    )
