# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""Edge-cloud communication service: decoupled data-plane comm for
edge-cloud PD separation.

Public surface (intentionally minimal):

* :class:`EdgeCloudCommService` — ``submit_send`` / ``submit_recv`` /
  ``poll_completions`` / ``shutdown``;
* :class:`CommFuture` — ``done()`` / ``wait()`` / ``add_callback()`` /
  ``as_intermediate_tensors()``;
* :class:`CommRequest` and the ``CommChannelType`` / ``BatchKind`` enums.

Design doc: ``edge_cloud_comm_design.md`` at the repo root.
"""

from vllm_ascend.distributed.edge_cloud_comm.future import CommFuture
from vllm_ascend.distributed.edge_cloud_comm.mapping import (
    channel_for,
    channel_for_direction,
    default_transport,
    kind_for_batch_type,
)
from vllm_ascend.distributed.edge_cloud_comm.service import (
    EdgeCloudCommService,
    SchedulerCommSink,
    get_comm_service,
)
from vllm_ascend.distributed.edge_cloud_comm.types import (
    BatchKind,
    CommChannelType,
    CommRequest,
    CommResult,
    CommStatus,
)

__all__ = [
    "BatchKind",
    "CommChannelType",
    "CommFuture",
    "CommRequest",
    "CommResult",
    "CommStatus",
    "EdgeCloudCommService",
    "SchedulerCommSink",
    "channel_for",
    "channel_for_direction",
    "default_transport",
    "get_comm_service",
    "kind_for_batch_type",
]
