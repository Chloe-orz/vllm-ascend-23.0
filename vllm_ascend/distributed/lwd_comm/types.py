# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""Type definitions for the prefill_only duplex comm package."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Literal


class LwdChannelType(enum.Enum):
    """The two physical data-plane channels, direction-only.

    Each channel maps 1:1 to a dedicated HCCL communicator + NPU stream
    (see ``vllm_ascend.distributed.lwd_wire``).  HCCL P2P matching order
    per (communicator, peer) is exactly the per-channel ``seqno``
    submission order — HCCL does not support tags.
    """

    UP = "lwd_up"      # edge -> cloud: prompt embeddings
    DOWN = "lwd_down"  # cloud -> edge: combined c2e packet


class LwdCommStatus(enum.Enum):
    PENDING = "pending"
    OK = "ok"
    ERROR = "error"


@dataclass
class LwdCommRequest:
    """One communication task submitted to the service.

    Everything the comm layer needs travels with the request — it never
    reaches back into scheduler/model state.
    """

    channel: LwdChannelType
    op: Literal["send", "recv"]
    # Number of bf16 elements of the payload (UP: N*H; DOWN:
    # 32 + R*(H+3K)).  recv: used to allocate the exact-size buffer
    # (HCCL P2P requires matching numel on both ends).
    num_elements: int
    # send: payload tensor (snapshotted into a communication-owned buffer
    # at submit time).  recv: None.
    tensor: Any | None = None
    # Per-channel request-level sequence number.  Contract: each
    # channel's counter starts at 0 and increments by one per request on
    # both peers; ops are posted to HCCL only once all lower seqnos have
    # been submitted, so send order and the peer's recv-post order always
    # agree.  Do not mix sequenced and unsequenced requests on one
    # channel.
    seqno: int | None = None
    # Explicit global peer rank; None -> the channel's configured peer.
    src_dst: int | None = None
    # 多边多云数据面选路维度:指定该次通信属于哪个 (edge, cloud) 通信域。
    # None -> 单边一云默认域(与旧行为逐位一致);上层按路由结果/来源边回填。
    edge_id: int | None = None
    cloud_id: int | None = None


@dataclass
class LwdCommResult:
    """Outcome of a completed request (cross-node P2P finished on device)."""

    status: LwdCommStatus
    tensor: Any | None = None
    error: BaseException | None = None
