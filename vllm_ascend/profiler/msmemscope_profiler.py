#
# Copyright (c) 2026 Huawei Technologies Co., Ltd. All Rights Reserved.
# Copyright 2023 The vLLM team.
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
# This file is a part of the vllm-ascend project.
#
"""msMemScope Python API wrapper for vLLM-Ascend worker startup profiling.

msMemScope (MindStudio MemScope) hooks ``aclrtMalloc`` at the CANN/acl
layer, so it captures NPU memory allocations that bypass PyTorch's caching
allocator (notably HCCL communication buffers). This makes it suitable for
diagnosing communication memory usage during service startup, which
``torch.npu.memory_allocated()`` / ``memory_snapshot()`` cannot see.

Typical usage (driven by ``MSMEMSCOPE_ENABLE=1`` in
``vllm_ascend/worker/worker.py``)::

    profiler = get_ms_memscope_profiler()
    profiler.start(output_path="/tmp/memscope_out")
    with profiler.mark("distributed_init"):
        init_distributed_environment(...)
    with profiler.mark("warmup"):
        compile_or_warm_up_model()
    profiler.snapshot(name="after_warmup")
    profiler.stop()

Before enabling, install msMemScope and run
``source msmemscope --load-api-env`` to set up ``LD_PRELOAD`` /
``LD_LIBRARY_PATH`` (must be done before launching vLLM, since
``LD_PRELOAD`` only takes effect at process start).

Reference: https://github.com/mindstudio-docs/master/blob/master/msmemscope
"""

from __future__ import annotations

import contextlib
import threading
from typing import Any

from vllm.logger import logger


class MsMemScopeProfiler:
    """Thin wrapper around the ``msmemscope`` Python API.

    The wrapper is safe to construct and call even when the ``msmemscope``
    package is not installed: every method no-ops and logs a warning on the
    first ``start()`` attempt, so production code paths are unaffected.

    The class is process-wide single-instance (``get_instance``), because
    msMemScope maintains global collection state (``config`` / ``start`` /
    ``stop`` are module-level in the ``msmemscope`` package).
    """

    _instance: "MsMemScopeProfiler | None" = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._msmemscope: Any = None
        self._import_attempted: bool = False
        self._started: bool = False

    @classmethod
    def get_instance(cls) -> "MsMemScopeProfiler":
        """Return the process-wide profiler instance."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _import_msmemscope(self) -> Any:
        """Lazily import the ``msmemscope`` package; cache the result.

        Returns the ``msmemscope`` module on success, or ``None`` if the
        package is not installed (the error is logged once).
        """
        if self._import_attempted:
            return self._msmemscope
        self._import_attempted = True
        try:
            import msmemscope  # type: ignore[import-not-found]
        except ImportError as e:
            logger.warning(
                "MSMEMSCOPE_ENABLE is set but the msmemscope package is not "
                "available (import error: %s). msMemScope collection is "
                "disabled. Install msMemScope and run "
                "'source msmemscope --load-api-env' before launching vLLM.",
                e,
            )
            return None
        self._msmemscope = msmemscope
        return msmemscope

    @property
    def started(self) -> bool:
        """Whether msMemScope collection is currently active."""
        return self._started

    def start(
        self,
        output_path: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> bool:
        """Configure and start msMemScope collection.

        Args:
            output_path: Directory for dump files. If ``None``, msMemScope's
                default ``memscopeDumpResults`` is used.
            config: Optional dict of keyword arguments forwarded to
                ``msmemscope.config(...)``. These override the defaults below.

        Returns:
            ``True`` if collection was started, ``False`` if it was skipped
            (already started, package missing, or configuration failed).

        The default config captures alloc/free/launch events with C + Python
        call stacks on all NPUs, and enables leak + decompose analysis. The
        output format is ``db`` for use with MindStudio Insight.
        """
        if self._started:
            logger.warning("msMemScope is already started; ignoring start().")
            return False

        msmemscope = self._import_msmemscope()
        if msmemscope is None:
            return False

        config_kwargs: dict[str, Any] = {
            "call_stack": "c:10,python:5",
            "events": "launch,alloc,free",
            "level": "op",
            "device": "npu",
            "analysis": "leaks,decompose",
            "data_format": "db",
        }
        if output_path:
            config_kwargs["output"] = output_path
        if config and isinstance(config, dict):
            config_kwargs.update(config)

        try:
            msmemscope.config(**config_kwargs)
            msmemscope.start()
            self._started = True
            logger.info(
                "msMemScope collection started (output=%s, config=%s).",
                config_kwargs.get("output"),
                {k: v for k, v in config_kwargs.items() if k != "output"},
            )
            return True
        except Exception as e:  # noqa: BLE001 - configuration is best-effort
            logger.exception("Failed to start msMemScope: %s", e)
            return False

    def stop(self) -> None:
        """Stop msMemScope collection and trigger report generation.

        Safe to call when collection is not active (no-op).
        """
        if not self._started:
            return
        if self._msmemscope is None:
            return
        try:
            self._msmemscope.stop()
            self._started = False
            logger.info("msMemScope collection stopped; report generated.")
        except Exception as e:  # noqa: BLE001 - stop must not crash shutdown
            logger.exception("Failed to stop msMemScope: %s", e)
            self._started = False

    @contextlib.contextmanager
    def mark(self, name: str):
        """Mark a code block with an msMemScope ``RecordFunction``.

        If collection is not active or ``msmemscope`` is unavailable, the
        context manager yields without marking. Exceptions from
        ``RecordFunction`` are swallowed so they never affect the wrapped
        code path.
        """
        if not self._started or self._msmemscope is None:
            yield
            return
        record_fn = getattr(self._msmemscope, "RecordFunction", None)
        if record_fn is None:
            yield
            return
        try:
            with record_fn(name):
                yield
        except Exception as e:  # noqa: BLE001 - marking must not crash work
            logger.warning(
                "msMemScope RecordFunction(%s) failed: %s; continuing without mark.",
                name, e,
            )

    def snapshot(self, name: str | None = None, device_mask: int = 0) -> None:
        """Take an msMemScope memory snapshot.

        ``take_snapshot`` is independent of ``start``/``stop`` and can be
        called inside an active collection to capture the current allocator
        state (device free/total, etc.). The snapshot lands in the same
        ``memscope_dump_{timestamp}.csv`` as other events.

        Args:
            name: Optional custom event name for the snapshot.
            device_mask: Device id to snapshot (default 0). Use a list/tuple
                for multiple devices per the msMemScope API.
        """
        if not self._started or self._msmemscope is None:
            return
        take_snapshot = getattr(self._msmemscope, "take_snapshot", None)
        if take_snapshot is None:
            return
        kwargs: dict[str, Any] = {"device_mask": device_mask}
        if name:
            kwargs["name"] = name
        try:
            take_snapshot(**kwargs)
        except Exception as e:  # noqa: BLE001 - snapshot must not crash work
            logger.warning("msMemScope take_snapshot failed: %s", e)


def get_ms_memscope_profiler() -> MsMemScopeProfiler:
    """Return the process-wide :class:`MsMemScopeProfiler` singleton."""
    return MsMemScopeProfiler.get_instance()
