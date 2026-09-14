# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""LWD 性能计时工具(环境变量开关)。

开关:``VLLM_ASCEND_LWD_TIMING=1`` 开启,缺省关闭(零开销)。
输出:仅控制台,error 级别(可用日志级别把计时行单独过滤出来)。

用法::

    t0 = lwd_timing.synced_now()
    ... 被测代码 ...
    lwd_timing.log_duration("[Lwd][timing] xxx", t0)
"""

from __future__ import annotations

import os
import time

import torch
from vllm.logger import init_logger

logger = init_logger(__name__)

_ENABLED = os.environ.get("VLLM_ASCEND_LWD_TIMING", "0") == "1"

# 同进程(同侧)时间链:上一个计时点的结束时刻,用于打印点间差值。
# 只在单进程内串联——边/云各自成链,不做跨机时间对齐。
_last_end: dict[str, float] = {}


def _emit(line: str) -> None:
    # error 级别输出,便于用日志级别把计时行单独过滤出来
    logger.error("%s", line)


def enabled() -> bool:
    return _ENABLED


def synced_now(*, sync: bool = False) -> float:
    """取当前时间戳(计时起点);关闭时返回 0.0。

    sync=True(通信段)先 torch.npu.synchronize() 再取时间;
    sync=False(计算段)不打断异步流水线,日志照常输出。
    """
    if not _ENABLED:
        return 0.0
    if sync:
        torch.npu.synchronize()
    return time.perf_counter()


def log_duration(tag: str, t0: float, *, chain: str = "lwd", sync: bool = False) -> None:
    """打印 t0 至今的耗时,以及与同侧上一个计时点的间隔。

    输出形如 ``tag: 1.234 ms (+5.678 ms since prev)``;
    chain 相同的点构成一条时间链(默认全进程一条,如需多链可显式分键);
    sync=True 打印前再做一次 synchronize(通信段),False 则不做(计算段)。
    """
    if not _ENABLED:
        return
    if sync:
        torch.npu.synchronize()
    now = time.perf_counter()
    prev = _last_end.get(chain)
    _last_end[chain] = now
    if prev is None:
        _emit(f"{tag}: {(now - t0) * 1e3:.3f} ms")
    else:
        _emit(
            f"{tag}: {(now - t0) * 1e3:.3f} ms "
            f"(+{(now - prev) * 1e3:.3f} ms since prev)"
        )
