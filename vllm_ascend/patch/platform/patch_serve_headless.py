#
# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
# This file is a part of the vllm-ascend project.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import vllm
from vllm.entrypoints.cli import serve
from vllm.usage.usage_lib import UsageContext

from vllm_ascend.edge_cloud.observability import log_event

_original_run_headless = serve.run_headless


def _install_ascend_passive_scheduler_shim() -> None:
    import sys

    import vllm_ascend.core.passive_scheduler as passive_scheduler

    sys.modules["vllm.v1.core.sched.passive_scheduler"] = passive_scheduler


def _run_passive_engine_core_with_ascend_shims(**kwargs):
    _install_ascend_passive_scheduler_shim()
    # Re-attach PassiveEngineCoreProc + ZMQ classes to the upstream
    # ``vllm.v1.engine.core`` module path so the legacy import below
    # resolves even when this code runs in a freshly-spawned subprocess
    # (no ascend platform __init__ side-effects guaranteed yet).
    from vllm_ascend.patch.platform.patch_pd_scheduler_shim import (
        install_ascend_passive_engine_core_shims,
    )

    install_ascend_passive_engine_core_shims()

    from vllm.v1.engine.core import PassiveEngineCoreProc

    return PassiveEngineCoreProc.run_passive_engine_core(**kwargs)


def _launch_passive_engine_core(vllm_config, shutdown_requested: bool) -> None:
    from vllm.utils.system_utils import get_mp_context

    from vllm_ascend.ascend_config import init_ascend_config

    _install_ascend_passive_scheduler_shim()
    from vllm.version import __version__ as VLLM_VERSION

    parallel_config = vllm_config.parallel_config
    host = parallel_config.master_addr
    head_node_address = f"{host}:{parallel_config.master_port}"

    serve.logger.info(
        "Launching vLLM (v%s) headless passive EngineCore, "
        "with head node address %s for torch.distributed process group.",
        VLLM_VERSION,
        head_node_address,
    )

    context = get_mp_context()
    ready_reader, ready_writer = context.Pipe(duplex=False)
    edge_cloud_config = init_ascend_config(vllm_config).edge_cloud_config
    coordination = edge_cloud_config.prefix_cache_coordination
    coordination_enabled = bool(
        edge_cloud_config.enabled and edge_cloud_config.role == "cloud" and coordination.enabled
    )
    command_queue = context.Queue() if coordination_enabled else None
    event_queue = context.Queue() if coordination_enabled else None
    if coordination_enabled:
        log_event(
            serve.logger,
            "info",
            "cloud_coordination_launch",
            instance_id=coordination.instance_id,
            listen_host=coordination.listen_host,
            listen_port=coordination.listen_port,
            block_size=vllm_config.cache_config.block_size,
        )

    proc = context.Process(
        target=_run_passive_engine_core_with_ascend_shims,
        kwargs={
            "vllm_config": vllm_config,
            "ready_pipe": ready_writer,
            "cloud_control_command_queue": command_queue,
            "cloud_control_event_queue": event_queue,
        },
        name="PassiveEngineCore",
    )
    proc.start()
    ready_writer.close()

    try:
        response = ready_reader.recv()
        if response.get("status") != "READY":
            raise RuntimeError(f"PassiveEngineCore failed to start. Response: {response}")
    except EOFError:
        raise RuntimeError("PassiveEngineCore process died during startup. Check logs for details.") from None
    finally:
        ready_reader.close()

    serve.logger.info("PassiveEngineCore is ready.")
    if coordination_enabled:
        log_event(
            serve.logger,
            "info",
            "cloud_passive_core_ready",
            instance_id=coordination.instance_id,
            block_size=response.get("block_size"),
        )

    try:
        if coordination_enabled:
            from vllm_ascend.edge_cloud.cloud_control import (
                CloudControlBridge,
                run_cloud_control_server,
            )
            from vllm_ascend.edge_cloud.mm_identity import compute_processor_fingerprint

            assert command_queue is not None and event_queue is not None
            bridge = CloudControlBridge(command_queue, event_queue)
            serve.logger.info(
                "Starting edge-cloud OpenAI control endpoint on %s:%d (instance_id=%s, block_size=%s)",
                coordination.listen_host,
                coordination.listen_port,
                coordination.instance_id,
                response.get("block_size"),
            )
            run_cloud_control_server(
                bridge,
                coordination.listen_host,
                coordination.listen_port,
                proc,
                processor_fingerprint=compute_processor_fingerprint(vllm_config.model_config),
            )
        else:
            proc.join()
        if proc.exitcode and proc.exitcode != 0:
            serve.logger.error("PassiveEngineCore exited with code %d", proc.exitcode)
            if coordination_enabled:
                log_event(
                    serve.logger,
                    "error",
                    "cloud_passive_core_exited",
                    exit_code=proc.exitcode,
                )
    finally:
        timeout = None
        if shutdown_requested:
            timeout = vllm_config.shutdown_timeout
            serve.logger.info("Waiting up to %d seconds for PassiveEngineCore to exit", timeout)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=timeout)
        for ipc_queue in (command_queue, event_queue):
            if ipc_queue is not None:
                ipc_queue.close()
                ipc_queue.join_thread()
        if coordination_enabled:
            log_event(
                serve.logger,
                "info",
                "cloud_coordination_stopped",
                instance_id=coordination.instance_id,
                exit_code=proc.exitcode,
            )
        serve.logger.info("Shutting down.")


def _run_headless_with_passive_engine(args):
    engine_args = vllm.AsyncEngineArgs.from_cli_args(args)
    usage_context = UsageContext.OPENAI_API_SERVER
    vllm_config = engine_args.create_engine_config(usage_context=usage_context, headless=True)

    parallel_config = vllm_config.parallel_config
    if parallel_config.node_rank_within_dp > 0:
        if engine_args.data_parallel_hybrid_lb:
            raise ValueError("data_parallel_hybrid_lb is not applicable in headless mode")
        if parallel_config.data_parallel_size_local <= 0:
            raise ValueError("data_parallel_size_local must be > 0 in headless mode")
        _launch_passive_engine_core(vllm_config, shutdown_requested=False)
        return

    return _original_run_headless(args)


serve.run_headless = _run_headless_with_passive_engine
