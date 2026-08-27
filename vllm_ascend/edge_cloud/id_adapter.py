# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
# Edge-cloud multi-instance id adapter (2E1C scenario).
#
# Cloud-side namespace isolation: with multiple edges, client-supplied or
# edge-generated request ids / head_tokens can collide across edges.  The
# cloud wraps every inbound id with the source edge prefix at the single
# ingress point, and strips the prefix on every outbound path, so edges stay
# completely unaware of the multi-edge namespace.
"""Cloud-side id wrap/unwrap adapter for multi-edge isolation."""

from __future__ import annotations

import re

from vllm.logger import init_logger

logger = init_logger(__name__)

# Wrapped forms:  req_id: "e{edge_id}-{orig}"   head_token: "{edge_id}:{orig}"
_REQ_RE = re.compile(r"^e(\d+)-(.*)$")
_TOKEN_RE = re.compile(r"^(\d+):(.*)$")


def wrap_req_id(edge_id: int, req_id: str) -> str:
    """Wrap a raw edge-side request id with its edge prefix."""
    return f"e{edge_id}-{req_id}"


def wrap_head_token(edge_id: int, head_token: str) -> str:
    """Wrap a raw edge-side head token with its edge prefix."""
    return f"{edge_id}:{head_token}"


def unwrap_req_id(wrapped: str) -> str:
    """Strip the edge prefix from a wrapped request id."""
    m = _REQ_RE.match(wrapped)
    if m is None:
        raise ValueError(f"not a wrapped req_id: {wrapped!r}")
    return m.group(2)


def parse_req_edge_id(wrapped: str) -> int:
    """Return the edge id embedded in a wrapped request id."""
    m = _REQ_RE.match(wrapped)
    if m is None:
        raise ValueError(f"not a wrapped req_id: {wrapped!r}")
    return int(m.group(1))


def parse_token_edge_id(wrapped: str) -> int:
    """Return the edge id embedded in a wrapped head token."""
    m = _TOKEN_RE.match(wrapped)
    if m is None:
        raise ValueError(f"not a wrapped head_token: {wrapped!r}")
    return int(m.group(1))


def is_wrapped_req_id(req_id: str) -> bool:
    return _REQ_RE.match(req_id) is not None


def unwrap_head_token(wrapped: str) -> str:
    """Strip the edge prefix from a wrapped head token."""
    m = _TOKEN_RE.match(wrapped)
    if m is None:
        raise ValueError(f"not a wrapped head_token: {wrapped!r}")
    return m.group(2)


def unwrap_scheduler_output_ids(so) -> None:
    """Strip edge prefixes from all req_id/head_token fields of a
    cloud-returned SchedulerOutput, in place (the SO is a per-message copy).

    Called on the cloud egress path (POST_OUT publish) so the edge receives
    its own original ids and stays unaware of the multi-edge namespace.
    """
    if getattr(so, "head_token", None):
        so.head_token = unwrap_head_token(so.head_token)
    if getattr(so, "num_scheduled_tokens", None):
        so.num_scheduled_tokens = {
            unwrap_req_id(rid): n
            for rid, n in so.num_scheduled_tokens.items()
        }
    for req_data in getattr(so, "scheduled_new_reqs", None) or []:
        req_data.req_id = unwrap_req_id(req_data.req_id)
    cached = getattr(so, "scheduled_cached_reqs", None)
    if cached is not None:
        if getattr(cached, "req_ids", None):
            cached.req_ids = [unwrap_req_id(rid) for rid in cached.req_ids]
        if getattr(cached, "resumed_req_ids", None):
            cached.resumed_req_ids = {
                unwrap_req_id(rid) for rid in cached.resumed_req_ids
            }
        if getattr(cached, "all_token_ids", None):
            cached.all_token_ids = {
                unwrap_req_id(rid): ids
                for rid, ids in cached.all_token_ids.items()
            }
    if getattr(so, "finished_req_ids", None):
        so.finished_req_ids = {
            unwrap_req_id(rid) for rid in so.finished_req_ids
        }
    # Live SchedulerOutput field name is scheduled_spec_decode_tokens;
    # scheduled_spec_token_ids is the stale alias kept for compat.
    if getattr(so, "scheduled_spec_decode_tokens", None):
        so.scheduled_spec_decode_tokens = {
            unwrap_req_id(rid): ids
            for rid, ids in so.scheduled_spec_decode_tokens.items()
        }
    if getattr(so, "scheduled_spec_token_ids", None):
        so.scheduled_spec_token_ids = {
            unwrap_req_id(rid): ids
            for rid, ids in so.scheduled_spec_token_ids.items()
        }
    if getattr(so, "structured_output_request_ids", None):
        so.structured_output_request_ids = {
            unwrap_req_id(rid): v
            for rid, v in so.structured_output_request_ids.items()
        }
    # draft_task_id lives in the wrapped (cloud) namespace after ingress
    # wrapping; strip it so the edge keeps seeing its own raw ids.  Guard on
    # the wrapped form for robustness against ids that never crossed ingress.
    if getattr(so, "draft_task_id", None) and _TOKEN_RE.match(so.draft_task_id):
        so.draft_task_id = unwrap_head_token(so.draft_task_id)
    if getattr(so, "cloud_draft_invalidate_task_ids", None):
        so.cloud_draft_invalidate_task_ids = [
            unwrap_head_token(tid) if _TOKEN_RE.match(tid) else tid
            for tid in so.cloud_draft_invalidate_task_ids
        ]
    # Accepted-count dicts keyed by req_id (DRAFT_FIRST step 0): unwrap keys.
    for field in ("num_accepted_tokens", "valid_sampled_token_count"):
        value = getattr(so, field, None)
        if isinstance(value, dict):
            setattr(
                so,
                field,
                {
                    unwrap_req_id(rid) if is_wrapped_req_id(rid) else rid: v
                    for rid, v in value.items()
                },
            )
