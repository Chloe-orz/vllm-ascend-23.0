# SPDX-License-Identifier: Apache-2.0

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType


_PATCH_PATH = (
    Path(__file__).parents[4]
    / "vllm_ascend"
    / "patch"
    / "platform"
    / "patch_engine_core.py"
)


def _install_fake_modules(monkeypatch):
    calls = []

    class FakeEngineCore:
        def __init__(self, *args, **kwargs):
            self.vllm_config = kwargs.get("vllm_config")

        def shutdown(self):
            pass

        def step(self):
            pass

        def step_with_batch_queue(self):
            pass

    class FakeEngineCoreProc:
        @staticmethod
        def run_engine_core(*args, dp_rank=0, local_dp_rank=0, **kwargs):
            calls.append((args, dp_rank, local_dp_rank, kwargs))
            return "original-result"

        def _process_input_queue(self):
            pass

    fake_core = ModuleType("vllm.v1.engine.core")
    fake_core.EngineCore = FakeEngineCore
    fake_core.EngineCoreProc = FakeEngineCoreProc

    fake_config = ModuleType("vllm.config")

    class FakeParallelConfig:
        pass

    fake_config.ParallelConfig = FakeParallelConfig

    fake_logger_mod = ModuleType("vllm.logger")

    class FakeLogger:
        def info(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass

        def debug(self, *args, **kwargs):
            pass

        def exception(self, *args, **kwargs):
            pass

        def isEnabledFor(self, level):
            return False

    fake_logger_mod.init_logger = lambda name: FakeLogger()

    fake_sched_output = ModuleType("vllm.v1.core.sched.output")

    class FakeBatchType:
        PREFILL_FIRST = "prefill_first"
        DECODE_FIRST = "decode_first"
        EMPTY = "empty"
        PREFILL_LAST = "prefill_last"
        DECODE_LAST = "decode_last"

    fake_sched_output.BatchType = FakeBatchType
    fake_sched_output.SchedulerOutput = object

    fake_outputs = ModuleType("vllm.v1.outputs")
    fake_outputs.ModelRunnerOutput = object

    fake_passive_core = ModuleType("vllm_ascend.v1.engine.passive_core")

    class FakePPSchedulerZmqChannel:
        pass

    fake_passive_core.PPSchedulerZmqChannel = FakePPSchedulerZmqChannel

    modules = {
        "vllm": ModuleType("vllm"),
        "vllm.config": fake_config,
        "vllm.logger": fake_logger_mod,
        "vllm.v1": ModuleType("vllm.v1"),
        "vllm.v1.core": ModuleType("vllm.v1.core"),
        "vllm.v1.core.sched": ModuleType("vllm.v1.core.sched"),
        "vllm.v1.core.sched.output": fake_sched_output,
        "vllm.v1.engine": ModuleType("vllm.v1.engine"),
        "vllm.v1.engine.core": fake_core,
        "vllm.v1.outputs": fake_outputs,
        "vllm_ascend": ModuleType("vllm_ascend"),
        "vllm_ascend.v1": ModuleType("vllm_ascend.v1"),
        "vllm_ascend.v1.engine": ModuleType("vllm_ascend.v1.engine"),
        "vllm_ascend.v1.engine.passive_core": fake_passive_core,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    return fake_core, calls


def _load_patch_module():
    spec = importlib.util.spec_from_file_location(
        "test_patch_engine_core_module", _PATCH_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_run_engine_core_wrapper_preserves_child_process_patch_without_legacy_env(monkeypatch):
    legacy_env_name = "VLLM_PP_" + "SCHEDULER_ZMQ_ADDR"
    monkeypatch.delenv(legacy_env_name, raising=False)
    fake_core, calls = _install_fake_modules(monkeypatch)

    _load_patch_module()

    assert hasattr(fake_core.EngineCoreProc.run_engine_core, "__wrapped__")
    result = fake_core.EngineCoreProc.run_engine_core(
        "arg", dp_rank=1, local_dp_rank=2, vllm_config=object()
    )

    assert result == "original-result"
    assert len(calls) == 1
    assert calls[0][0] == ("arg",)
    assert calls[0][1] == 1
    assert calls[0][2] == 2
    assert legacy_env_name not in os.environ
