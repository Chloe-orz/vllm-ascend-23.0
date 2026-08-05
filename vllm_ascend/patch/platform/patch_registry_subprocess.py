
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
"""Keep ms_service_profiler out of the model-inspection subprocess.

vLLM derives ``_ModelInfo`` from a model class in a short-lived subprocess
spawned by ``vllm.model_executor.models.registry._run_in_subprocess`` (kept
off-process to avoid initializing CUDA).  When ``SERVICE_PROF_CONFIG_PATH`` is
set, ``ms_service_profiler`` auto-starts in *every* Python process via its
sitecustomize hook -- including this inspection subprocess.  There the
profiler's C++ thread fires a ctypes callback into Python; because the process
is about to exit, the callback hits an inconsistent interpreter state and
segfaults in ``PyGILState_Ensure`` -> ``new_threadstate`` (SIGSEGV, callback
address ``0xffffffffffffffff``).  The crash kills the inspection, so model
architectures such as ``Qwen3_5MTP`` "fail to be inspected" and
``SpeculativeConfig`` validation aborts service startup.  This is why enabling
profiling breaks MTP (and only MTP): the speculative draft-model architecture
is the inspection path triggered during ``create_engine_config``.

The inspection subprocess never runs inference and has no use for profiling.
Temporarily scrub the profiler env vars from ``os.environ`` for the duration of
the subprocess spawn so the profiler does not auto-load there, then restore
them.  Other subprocesses (engine core, workers) are spawned by separate code
paths and keep profiling.

This wraps the module-level ``_run_in_subprocess`` symbol; the only call site
(``_LazyRegisteredModel.inspect_model_cls``) resolves it through the registry
module globals at call time, so the replacement takes effect.
"""

import os
import threading

from vllm.logger import logger
from vllm.model_executor.models import registry as vllm_registry

# Env vars that trigger ms_service_profiler auto-load.  Unsetting them in the
# inspection subprocess prevents the profiler from starting there.
#   - SERVICE_PROF_CONFIG_PATH : master on/off + config path (the trigger)
#   - PROFILING_SYMBOLS_PATH   : symbols YAML; scrubbed too so no partial load
_PROFILER_ENV_VARS = ("SERVICE_PROF_CONFIG_PATH", "PROFILING_SYMBOLS_PATH")

_orig_run_in_subprocess = vllm_registry._run_in_subprocess

# Serializes the env scrub so concurrent inspections cannot interleave their
# save/restore windows -- without it a later caller could re-inherit the
# profiler vars (restored by an earlier caller) and segfault.  Inspections are
# already sequential during create_engine_config; this lock is just insurance.
_subprocess_scrub_lock = threading.Lock()


def _run_in_subprocess_no_profiler(fn):
    present = [v for v in _PROFILER_ENV_VARS if v in os.environ]
    # Fast path: profiling not configured -- nothing to scrub, no lock needed.
    if not present:
        return _orig_run_in_subprocess(fn)

    with _subprocess_scrub_lock:
        saved = {v: os.environ.pop(v) for v in present}
        logger.info(
            "Scrubbing %s from model-inspection subprocess env to prevent "
            "ms_service_profiler segfault (restored after spawn).",
            ", ".join(present),
        )
        try:
            return _orig_run_in_subprocess(fn)
        finally:
            for v, val in saved.items():
                os.environ[v] = val


vllm_registry._run_in_subprocess = _run_in_subprocess_no_profiler
