# SPDX-License-Identifier: Apache-2.0

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


_LAYERWISE_ENV_KEYS = (
    "VLLM_PP_NON_LEADER_ENGINE_CORE",
    "VLLM_PP_SCHEDULER_ZMQ_ADDR",
    "VLLM_PP_PRE_OUT_ZMQ_PORT",
    "VLLM_PP_POST_OUT_ZMQ_PORT",
    "VLLM_LAYER_SLICE_SIZE",
    "VLLM_PP_PASSIVE_DISPATCH_POLICY",
)

_PATCH_PATH = (
    Path(__file__).parents[4]
    / "vllm_ascend"
    / "patch"
    / "platform"
    / "patch_envs_layerwise.py"
)


class FakeVllmEnvs(ModuleType):
    def __init__(self):
        super().__init__("vllm.envs")
        self.env_variables = {}

    def __getattr__(self, name):
        if name in self.env_variables:
            return self.env_variables[name]()
        raise AttributeError(name)


def _install_fake_vllm_envs(monkeypatch):
    fake_vllm = ModuleType("vllm")
    fake_envs = FakeVllmEnvs()
    fake_vllm.envs = fake_envs
    monkeypatch.setitem(sys.modules, "vllm", fake_vllm)
    monkeypatch.setitem(sys.modules, "vllm.envs", fake_envs)
    return fake_envs


def _load_patch_module():
    spec = importlib.util.spec_from_file_location(
        "test_patch_envs_layerwise", _PATCH_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_layerwise_env_patch_registers_missing_vllm_envs(monkeypatch):
    fake_envs = _install_fake_vllm_envs(monkeypatch)

    patch_module = _load_patch_module()
    patch_module.apply_layerwise_env_patch()

    for key in _LAYERWISE_ENV_KEYS:
        assert key in fake_envs.env_variables

    monkeypatch.setenv("VLLM_PP_NON_LEADER_ENGINE_CORE", "1")
    monkeypatch.setenv("VLLM_PP_SCHEDULER_ZMQ_ADDR", "tcp://127.0.0.1:6000")
    monkeypatch.setenv("VLLM_PP_PRE_OUT_ZMQ_PORT", "6001")
    monkeypatch.setenv("VLLM_PP_POST_OUT_ZMQ_PORT", "6002")
    monkeypatch.setenv("VLLM_LAYER_SLICE_SIZE", "4")
    monkeypatch.setenv("VLLM_PP_PASSIVE_DISPATCH_POLICY", "decode_first")

    assert fake_envs.VLLM_PP_NON_LEADER_ENGINE_CORE is True
    assert fake_envs.VLLM_PP_SCHEDULER_ZMQ_ADDR == "tcp://127.0.0.1:6000"
    assert fake_envs.VLLM_PP_PRE_OUT_ZMQ_PORT == 6001
    assert fake_envs.VLLM_PP_POST_OUT_ZMQ_PORT == 6002
    assert fake_envs.VLLM_LAYER_SLICE_SIZE == 4
    assert fake_envs.VLLM_PP_PASSIVE_DISPATCH_POLICY == "decode_first"


def test_layerwise_env_patch_keeps_existing_vllm_envs(monkeypatch):
    fake_envs = _install_fake_vllm_envs(monkeypatch)
    custom_reader = lambda: 99
    fake_envs.env_variables["VLLM_LAYER_SLICE_SIZE"] = custom_reader

    patch_module = _load_patch_module()
    patch_module.apply_layerwise_env_patch()

    assert fake_envs.env_variables["VLLM_LAYER_SLICE_SIZE"] is custom_reader
    assert fake_envs.VLLM_LAYER_SLICE_SIZE == 99
