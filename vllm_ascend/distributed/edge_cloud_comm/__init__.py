# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""Edge-cloud communication service: decoupled data-plane comm for
edge-cloud PD separation.

Public surface (intentionally minimal):

* :class:`EdgeCloudCommService` — ``submit_send`` / ``submit_recv`` /
  ``poll_completions`` / ``shutdown``;
* :class:`CommFuture` — ``done()`` / ``wait()`` / ``add_callback()`` /
  ``as_intermediate_tensors()``;
* :class:`CommRequest` and the ``CommChannelType`` / ``BatchKind`` enums;
* scheduler interface (design doc 8.3): ``make_recv_hint`` /
  ``recv_request_from_hint`` / ``build_recv_request`` /
  ``SchedulerCommSink`` / ``LoggingSchedulerCommSink``.

Design doc: ``edge_cloud_comm_design.md`` at the repo root.

Import weight: types / mapping / scheduler_api are import-light and safe
for scheduler-side (engine core) processes.  The worker-side machinery
(CommFuture / CommChannel / EdgeCloudCommService — torch, HCCL wire
layer) is exported lazily via PEP 562 so that importing this package
from a scheduler process does not pull in the wire layer.
"""

from vllm_ascend.distributed.edge_cloud_comm.mapping import (
    channel_for,
    channel_for_direction,
    default_transport,
    kind_for_batch_type,
)
from vllm_ascend.distributed.edge_cloud_comm.scheduler_api import (
    LoggingSchedulerCommSink,
    build_recv_request,
    make_recv_hint,
    recv_request_from_hint,
)
from vllm_ascend.distributed.edge_cloud_comm.types import (
    BatchKind,
    CommChannelType,
    CommRequest,
    CommResult,
    CommStatus,
)

_LAZY_EXPORTS = {
    "CommFuture": "vllm_ascend.distributed.edge_cloud_comm.future",
    "EdgeCloudCommService": "vllm_ascend.distributed.edge_cloud_comm.service",
    "SchedulerCommSink": "vllm_ascend.distributed.edge_cloud_comm.service",
    "get_comm_service": "vllm_ascend.distributed.edge_cloud_comm.service",
}

__all__ = [
    "BatchKind",
    "CommChannelType",
    "CommFuture",
    "CommRequest",
    "CommResult",
    "CommStatus",
    "EdgeCloudCommService",
    "LoggingSchedulerCommSink",
    "SchedulerCommSink",
    "build_recv_request",
    "channel_for",
    "channel_for_direction",
    "default_transport",
    "get_comm_service",
    "kind_for_batch_type",
    "make_recv_hint",
    "recv_request_from_hint",
]


def __getattr__(name: str):
    module = _LAZY_EXPORTS.get(name)
    if module is None:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        )
    import importlib

    return getattr(importlib.import_module(module), name)
