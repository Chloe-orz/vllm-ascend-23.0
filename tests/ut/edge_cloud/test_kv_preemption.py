# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

"""Flow-level simulation of the KV-capacity fault model (stall/preempt/retry).

Mirrors the cloud-side of a KV-full incident end to end:
gate (can_admit) -> admission -> decode growth failure -> preempt victim ->
retry reclaim from _preempted -> finish.  Also covers the F4 orphan-finish
reservation release.
"""

from types import SimpleNamespace

import pytest
import torch
from vllm.sampling_params import SamplingParams
from vllm.v1.core.kv_cache_utils import init_none_hash
from vllm.v1.core.sched.output import (
    BatchType,
    CachedRequestData,
    EdgeCloudFinishedRequest,
    NewRequestData,
    SchedulerOutput,
)
from vllm.v1.kv_cache_interface import (
    FullAttentionSpec,
    KVCacheConfig,
    KVCacheGroupSpec,
)

from vllm_ascend.edge_cloud.cloud_kv import CloudKVRequestManager
from vllm_ascend.edge_cloud.prefix_protocol import PrefixHasher


def _vllm_config(block_size):
    return SimpleNamespace(
        cache_config=SimpleNamespace(
            block_size=block_size,
            hash_block_size=None,
            enable_prefix_caching=True,
        ),
        kv_transfer_config=None,
        scheduler_config=SimpleNamespace(max_num_batched_tokens=128),
        parallel_config=SimpleNamespace(
            decode_context_parallel_size=1,
            prefill_context_parallel_size=1,
        ),
        model_config=SimpleNamespace(max_model_len=128),
        speculative_config=None,
    )


def _kv_cache_config(block_size, num_blocks=16):
    return KVCacheConfig(
        num_blocks=num_blocks,
        kv_cache_tensors=[],
        kv_cache_groups=[
            KVCacheGroupSpec(
                ["layer"],
                FullAttentionSpec(
                    block_size=block_size,
                    num_kv_heads=1,
                    head_size=1,
                    dtype=torch.float32,
                ),
            )
        ],
    )


def _scheduler_output(
    new_request=None,
    *,
    cached_req_ids=(),
    finished=None,
    finish_data=None,
    num_scheduled_tokens=8,
):
    scheduled_new_reqs = [] if new_request is None else [new_request]
    num_scheduled = dict.fromkeys(cached_req_ids, num_scheduled_tokens)
    if new_request is not None:
        num_scheduled[new_request.req_id] = num_scheduled_tokens
    return SchedulerOutput(
        scheduled_new_reqs=scheduled_new_reqs,
        scheduled_cached_reqs=CachedRequestData.make_empty(),
        num_scheduled_tokens=num_scheduled,
        total_num_scheduled_tokens=sum(num_scheduled.values()),
        scheduled_spec_decode_tokens={},
        scheduled_encoder_inputs={},
        num_common_prefix_blocks=[],
        finished_req_ids=finished or set(),
        free_encoder_mm_hashes=[],
        batch_type=(
            BatchType.EMPTY
            if new_request is None and not cached_req_ids
            else BatchType.PREFILL_FIRST
        ),
        edge_cloud_finished_requests=finish_data,
    )


def _new_request(req_id, control_id, tokens=8):
    return NewRequestData(
        req_id=req_id,
        prompt_token_ids=[0] * tokens,
        mm_features=[],
        sampling_params=SamplingParams(max_tokens=4),
        pooling_params=None,
        block_ids=([99, 100],),
        num_computed_tokens=0,
        lora_request=None,
        edge_cloud_request_id=control_id,
    )


def _manager(block_size=4, num_blocks=16):
    init_none_hash(lambda value: str(value).encode().ljust(32, b"0")[:32])
    return CloudKVRequestManager(
        kv_cache_config=_kv_cache_config(block_size, num_blocks),
        vllm_config=_vllm_config(block_size),
        instance_id="cloud-a",
    )


def _admit(manager, hasher, req_id, control_id, tokens=8):
    manager.probe(hasher.build_manifest(control_id, list(range(tokens))))
    out, _ = manager.rewrite_scheduler_output(
        _scheduler_output(_new_request(req_id, control_id, tokens))
    )
    manager.complete_scheduler_output(out)
    return out


def test_can_admit_gates_on_free_pool():
    manager = _manager()
    # 16 free blocks; a batch scheduling 8 tokens (2 blocks) passes.
    small = _scheduler_output(_new_request("r1", "c1"))
    assert manager.can_admit(small) is True
    # A batch scheduling 8 tokens per request over 9 requests (18 blocks)
    # exceeds the pool.
    big = _scheduler_output(cached_req_ids=[f"r{i}" for i in range(9)])
    assert manager.can_admit(big) is False


def test_preempt_frees_blocks_and_retry_reclaims_reservation():
    block_size = 4
    manager = _manager(block_size)
    hasher = PrefixHasher(b"tenant-a-secret-key-material", block_size)
    tokens = list(range(8))

    # Two requests admitted; pool now partially used.
    _admit(manager, hasher, "internal-1", "control-1")
    _admit(manager, hasher, "internal-2", "control-2")
    free_before = manager._kv.block_pool.get_num_free_blocks()

    # Preempt the most recent victim (epoch increments).
    result = manager.preempt_request("internal-2")
    assert result is not None
    control_id, new_epoch = result
    assert control_id == "control-2"
    assert new_epoch == 1
    assert "internal-2" not in manager._requests
    assert manager._kv.block_pool.get_num_free_blocks() > free_before
    # Reservation kept pinned for the retry.
    assert "control-2" in manager._preempted

    # Retry: admission with the same control id reclaims the reservation,
    # with the same hit and start position as the first admission.
    out, _ = manager.rewrite_scheduler_output(
        _scheduler_output(_new_request("internal-2", "control-2"))
    )
    assert "control-2" not in manager._preempted
    assert "internal-2" in manager._requests
    manager.complete_scheduler_output(out)

    # Finish the retried request: accounting still works.
    final = hasher.build_manifest("control-2", tokens + [9])
    finish = EdgeCloudFinishedRequest(
        control_request_id="control-2",
        prompt_tokens=8,
        completion_tokens=1,
        full_block_hashes=final.full_block_hashes,
    )
    _, usage = manager.rewrite_scheduler_output(
        _scheduler_output(
            finished={"internal-2"},
            finish_data={"internal-2": finish},
        )
    )
    assert usage and usage[0][0] == "control-2"


def test_orphan_finish_releases_reservation():
    block_size = 4
    manager = _manager(block_size)
    hasher = PrefixHasher(b"tenant-a-secret-key-material", block_size)

    manifest = hasher.build_manifest("control-1", list(range(8)))
    manager.probe(manifest)
    assert "control-1" in manager._reservations
    free_before = manager._kv.block_pool.get_num_free_blocks()

    # Finish arrives for an engine request that was never admitted
    # (client abort window): the reservation must be released (F4).
    final = hasher.build_manifest("control-1", list(range(8)) + [9])
    finish = EdgeCloudFinishedRequest(
        control_request_id="control-1",
        prompt_tokens=8,
        completion_tokens=1,
        full_block_hashes=final.full_block_hashes,
    )
    manager.rewrite_scheduler_output(
        _scheduler_output(
            finished={"internal-never-admitted"},
            finish_data={"internal-never-admitted": finish},
        )
    )
    assert "control-1" not in manager._reservations
    # Pinned reservation blocks returned to the pool.
    assert manager._kv.block_pool.get_num_free_blocks() > free_before


def test_preempt_candidates_are_recency_ordered():
    manager = _manager()
    hasher = PrefixHasher(b"tenant-a-secret-key-material", 4)
    _admit(manager, hasher, "internal-1", "control-1")
    _admit(manager, hasher, "internal-2", "control-2")
    _admit(manager, hasher, "internal-3", "control-3")
    assert manager.preemption_candidates() == [
        "internal-3",
        "internal-2",
        "internal-1",
    ]
