# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""prefill_only c2e (DOWN) 线相关工具。

当前 DOWN 数据面只传 hidden 张量（无 header/请求表/秩），此前的批组包/
解包线格式已随 hidden-only 改造移除。仅保留 abort 簿记在用的请求指纹。
"""

from __future__ import annotations

import hashlib


def lwd_request_fingerprint(request_id: str) -> int:
    """64-bit request fingerprint (blake2b), used by the recv managers'
    abort bookkeeping (``_aborted_fps`` / dropped tombstones)."""
    digest = hashlib.blake2b(request_id.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "little")
