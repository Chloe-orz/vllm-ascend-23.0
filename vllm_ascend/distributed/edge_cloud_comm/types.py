# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""Type definitions for the edge-cloud communication service.

Decouples edge-cloud data-plane communication from compute: the compute
side only submits send/recv requests and receives completion notifications
via CommFuture.  See ``edge_cloud_comm_design.md`` at the repo root for the
full design.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from vllm.v1.core.sched.output import HiddenChannelType

if TYPE_CHECKING:
    # Annotation only — keep this module importable from scheduler-side
    # (engine core) processes without pulling in the HCCL wire layer.
    from vllm_ascend.distributed.parallel_state import ScheduledDraftTensorMeta


class CommChannelType(enum.Enum):
    """The six logical data-plane channels: three request/response pairs.

    DECODE and DECODE_DRAFT share the DECODE pair (they never co-exist in
    flight); PREFILL_DRAFT carries the scheduled-draft round trip of the
    prefill phase.
    """

    PREFILL_UP = "prefill_up"
    PREFILL_DOWN = "prefill_down"
    PREFILL_DRAFT_UP = "prefill_draft_up"
    PREFILL_DRAFT_DOWN = "prefill_draft_down"
    DECODE_UP = "decode_up"
    DECODE_DOWN = "decode_down"


class BatchKind(enum.Enum):
    """Business kind of a request.  Draft kinds select the scheduled-draft
    wire format (``ScheduledDraftTensorMeta``) instead of the generic
    hidden-tensor format (``EdgeCloudTensorMeta``)."""

    PREFILL = "prefill"
    PREFILL_DRAFT = "prefill_draft"
    DECODE = "decode"
    DECODE_DRAFT = "decode_draft"


class CommStatus(enum.Enum):
    PENDING = "pending"
    OK = "ok"
    ERROR = "error"


@dataclass
class CommRequest:
    """One communication task submitted to the service.

    Everything the comm layer needs travels with the request — it never
    reaches back into scheduler/model state.
    """

    channel: CommChannelType
    op: Literal["send", "recv"]
    kind: BatchKind
    num_tokens: int
    # send: tensors to transmit (owned by the caller; the returned future
    # keeps them alive until the send completes).  recv: None — buffers are
    # pre-allocated by the comm layer on the channel stream.
    tensor_dict: dict[str, Any] | None = None
    # Physical wire channel assigned by the scheduler
    # (SchedulerOutput.hidden_channel).  None -> default transport for the
    # logical channel (see mapping.default_transport).
    transport: HiddenChannelType | None = None
    include_mrope: bool = True
    sp_chunk: bool = False
    # Dynamic wire schema for draft kinds (build_scheduled_draft_tensor_meta).
    draft_meta: ScheduledDraftTensorMeta | None = None
    # Wire-format override; None derives from kind ("hidden" for
    # PREFILL/DECODE, "draft" for the draft kinds):
    #   "draft_dynamic": legacy metadata-exchanging draft wire (plain
    #       pp_group.isend_tensor_dict / edge_cloud_broadcast_recv_draft),
    #       used by the fused in-model draft proposer whose per-step
    #       payloads are not described by any pre-computed schema.
    #   "plain": channel-less PP wire (edge_cloud_isend_tensor_dict with
    #       channel=None -> default device group, caller's current
    #       stream), used by the shared-model edge worker's head send.
    #       Identical to "hidden" on the recv side.
    wire: Literal["hidden", "draft", "draft_dynamic", "plain"] | None = None
    # Explicit peer rank in the PP group; None -> next (send) / previous
    # (recv) rank.
    src_dst: int | None = None


@dataclass
class CommResult:
    """Outcome of a completed request.

    Completion means the cross-node P2P op has finished on the device.  For
    recv, the TP-broadcast/SP-chunk postprocess is NOT included — it runs
    lazily when the consumer materializes the tensors (see
    CommFuture.as_intermediate_tensors).
    """

    status: CommStatus
    tensor_dict: dict[str, Any] | None = None
    error: BaseException | None = None
