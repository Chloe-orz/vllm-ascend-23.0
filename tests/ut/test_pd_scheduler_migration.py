# SPDX-License-Identifier: Apache-2.0

import importlib
from types import SimpleNamespace


def test_pd_separated_scheduler_module_is_owned_by_vllm_ascend():
    module = importlib.import_module("vllm_ascend.core.pd_separated_scheduler")

    assert module.PDSeparatedScheduler.__module__ == "vllm_ascend.core.pd_separated_scheduler"
    assert module.AsyncPDSeparatedScheduler.__module__ == "vllm_ascend.core.pd_separated_scheduler"


def test_passive_scheduler_module_is_owned_by_vllm_ascend():
    module = importlib.import_module("vllm_ascend.core.passive_scheduler")

    assert module.PassiveScheduler.__module__ == "vllm_ascend.core.passive_scheduler"
    assert module.DispatchPolicy.EXPECT_ALTERNATION.value == "expect_alternation"


def test_pd_scheduler_cls_is_set_to_ascend_path():
    from vllm_ascend.platform import NPUPlatform

    vllm_config = SimpleNamespace(
        scheduler_config=SimpleNamespace(
            enable_pd_separation=True,
            async_scheduling=False,
            scheduler_cls=None,
        )
    )

    NPUPlatform._configure_pd_separation_scheduler(vllm_config)

    assert vllm_config.scheduler_config.scheduler_cls == (
        "vllm_ascend.core.pd_separated_scheduler.PDSeparatedScheduler"
    )


def test_async_pd_scheduler_cls_is_set_to_ascend_path():
    from vllm_ascend.platform import NPUPlatform

    vllm_config = SimpleNamespace(
        scheduler_config=SimpleNamespace(
            enable_pd_separation=True,
            async_scheduling=True,
            scheduler_cls=None,
        )
    )

    NPUPlatform._configure_pd_separation_scheduler(vllm_config)

    assert vllm_config.scheduler_config.scheduler_cls == (
        "vllm_ascend.core.pd_separated_scheduler.AsyncPDSeparatedScheduler"
    )


def test_install_passive_scheduler_shim_aliases_upstream_import():
    import sys
    import vllm_ascend.patch.platform.patch_serve_headless as patch_serve_headless

    patch_serve_headless._install_ascend_passive_scheduler_shim()

    assert sys.modules["vllm.v1.core.sched.passive_scheduler"] is sys.modules[
        "vllm_ascend.core.passive_scheduler"
    ]
