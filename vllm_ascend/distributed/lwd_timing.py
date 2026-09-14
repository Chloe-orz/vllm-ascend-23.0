# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""LWD 性能计时工具(环境变量开关)。

开关:``VLLM_ASCEND_LWD_TIMING=1`` 开启,缺省关闭(零开销)。
每个计时段前后做 ``torch.npu.synchronize()``,确保异步 NPU 任务
全部落地后再取差值,测的是真实耗时而非入队耗时。

用法::

    t0 = lwd_timing.synced_now()
    ... 被测代码 ...
    lwd_timing.log_duration("[Lwd][timing] edge unembed seqno=%d" % s, t0)
"""

from __future__ import annotations

import os
import time

import torch
from vllm.logger import init_logger

logger = init_logger(__name__)

_ENABLED = os.environ.get("VLLM_ASCEND_LWD_TIMING", "0") == "1"

# 计时日志落地目录(环境变量指定;未设置则只走 logger 不写文件)。
# 每进程一个文件(lwd_timing_<pid>.log),边/云各自成链,天然隔离。
_TIMING_DIR = os.environ.get("VLLM_ASCEND_LWD_TIMING_DIR", "")
_timing_file = None

# 同进程(同侧)时间链:上一个计时点的结束时刻,用于打印点间差值。
# 只在单进程内串联——边/云各自成链,不做跨机时间对齐。
_last_end: dict[str, float] = {}


def _file():
    global _timing_file
    if _timing_file is None and _TIMING_DIR:
        os.makedirs(_TIMING_DIR, exist_ok=True)
        _timing_file = open(
            os.path.join(_TIMING_DIR, f"lwd_timing_{os.getpid()}.log"),
            "a",
            buffering=1,  # line buffered
            encoding="utf-8",
        )
    return _timing_file


def _emit(line: str) -> None:
    logger.info("%s", line)
    f = _file()
    if f is not None:
        f.write(line + "\n")


def enabled() -> bool:
    return _ENABLED


def synced_now(*, sync: bool = True) -> float:
    """取当前时间戳(计时起点);关闭时返回 0.0。

    sync=True(通信段)先 torch.npu.synchronize() 再取时间;
    sync=False(计算段)不打断异步流水线,日志照常输出。
    """
    if not _ENABLED:
        return 0.0
    if sync:
        torch.npu.synchronize()
    return time.perf_counter()


def log_duration(tag: str, t0: float, *, chain: str = "lwd", sync: bool = True) -> None:
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
