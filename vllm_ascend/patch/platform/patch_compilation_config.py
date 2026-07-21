# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM-Ascend project

"""Defensive wrapper around CompilationConfig.resolve_cudagraph_mode_and_sizes.

Upstream raises a ValueError when a Mamba/GDN model has fewer KV cache blocks
than ``max_num_reqs`` while FULL cudagraphs are requested.  On Ascend this is
too strict: edge-cloud splits and Mamba page-size padding can leave the cloud
worker with a small ``num_blocks`` even though the service can still run with
piecewise graphs.  Instead of failing startup, downgrade the cudagraph mode.
"""

import vllm.config.compilation
from vllm.config import CUDAGraphMode
from vllm.logger import logger

_orig_resolve_cudagraph_mode_and_sizes = (
    vllm.config.compilation.CompilationConfig.resolve_cudagraph_mode_and_sizes
)


def _ascend_resolve_cudagraph_mode_and_sizes(self, *args, **kwargs):
    """Resolve cudagraph mode, downgrading on insufficient Mamba cache blocks."""
    requested_mode = self.cudagraph_mode
    try:
        return _orig_resolve_cudagraph_mode_and_sizes(self, *args, **kwargs)
    except ValueError as exc:
        msg = str(exc)
        if "Mamba cache blocks" not in msg or not requested_mode.has_full_cudagraphs():
            raise

        # Downgrade to a mode that does not require FULL decode cudagraphs.
        if requested_mode == CUDAGraphMode.FULL:
            downgraded_mode = CUDAGraphMode.PIECEWISE
        elif requested_mode == CUDAGraphMode.FULL_DECODE_ONLY:
            downgraded_mode = CUDAGraphMode.NONE
        elif requested_mode == CUDAGraphMode.FULL_AND_PIECEWISE:
            downgraded_mode = CUDAGraphMode.PIECEWISE
        else:
            downgraded_mode = CUDAGraphMode.NONE

        logger.warning(
            "Insufficient Mamba cache blocks for FULL cudagraphs "
            "(requested max_num_reqs=%s, num_blocks=%s). "
            "Downgrading cudagraph_mode from %s to %s. "
            "If you need FULL graphs, increase gpu_memory_utilization or "
            "reduce max_num_seqs. Original error: %s",
            kwargs.get("max_num_reqs") or (args[5] if len(args) > 5 else "?"),
            kwargs.get("kv_cache_config") and kwargs["kv_cache_config"].num_blocks
            or (getattr(args[3], "num_blocks", "?") if len(args) > 3 else "?"),
            requested_mode,
            downgraded_mode,
            exc,
        )
        self.cudagraph_mode = downgraded_mode
        return downgraded_mode


vllm.config.compilation.CompilationConfig.resolve_cudagraph_mode_and_sizes = (
    _ascend_resolve_cudagraph_mode_and_sizes
)
