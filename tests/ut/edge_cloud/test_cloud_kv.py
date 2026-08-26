# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

import copy
from types import SimpleNamespace

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
    MambaSpec,
)

from vllm_ascend.edge_cloud.cloud_kv import CloudKVRequestManager
from vllm_ascend.edge_cloud.prefix_protocol import PrefixHasher


def _vllm_config(block_size, *, mtp_tokens=0):
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
        speculative_config=(
            SimpleNamespace(
                method="mtp",
                num_speculative_tokens=mtp_tokens,
            )
            if mtp_tokens
            else None
        ),
    )


def _kv_cache_config(block_size):
    return KVCacheConfig(
        num_blocks=16,
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


def _hybrid_kv_cache_config(block_size):
    return KVCacheConfig(
        num_blocks=16,
        kv_cache_tensors=[],
        kv_cache_groups=[
            KVCacheGroupSpec(
                ["attention_layer"],
                FullAttentionSpec(
                    block_size=block_size,
                    num_kv_heads=1,
                    head_size=1,
                    dtype=torch.float32,
                ),
            ),
            KVCacheGroupSpec(
                ["mamba_layer"],
                MambaSpec(
                    block_size=block_size,
                    shapes=((block_size,),),
                    dtypes=(torch.float32,),
                ),
            ),
        ],
    )


def _hybrid_mtp_kv_cache_config(block_size):
    full_attention_spec = FullAttentionSpec(
        block_size=block_size,
        num_kv_heads=1,
        head_size=1,
        dtype=torch.float32,
    )
    return KVCacheConfig(
        num_blocks=32,
        kv_cache_tensors=[],
        kv_cache_groups=[
            KVCacheGroupSpec(
                ["attention_layer"],
                full_attention_spec,
            ),
            KVCacheGroupSpec(
                ["mamba_layer"],
                MambaSpec(
                    block_size=block_size,
                    shapes=((block_size,),),
                    dtypes=(torch.float32,),
                ),
            ),
            KVCacheGroupSpec(
                ["mtp_layer"],
                full_attention_spec,
                is_eagle_group=True,
            ),
        ],
    )


def _scheduler_output(
    new_request=None,
    *,
    finished=None,
    finish_data=None,
    num_scheduled_tokens=8,
    batch_type=None,
    scheduled_spec_decode_tokens=None,
):
    scheduled_new_reqs = [] if new_request is None else [new_request]
    num_scheduled = {} if new_request is None else {new_request.req_id: num_scheduled_tokens}
    return SchedulerOutput(
        scheduled_new_reqs=scheduled_new_reqs,
        scheduled_cached_reqs=CachedRequestData.make_empty(),
        num_scheduled_tokens=num_scheduled,
        total_num_scheduled_tokens=sum(num_scheduled.values()),
        scheduled_spec_decode_tokens=scheduled_spec_decode_tokens or {},
        scheduled_encoder_inputs={},
        num_common_prefix_blocks=[],
        finished_req_ids=finished or set(),
        free_encoder_mm_hashes=[],
        batch_type=(
            batch_type
            if batch_type is not None
            else (BatchType.EMPTY if new_request is None else BatchType.PREFILL_FIRST)
        ),
        edge_cloud_finished_requests=finish_data,
    )


def test_cloud_owns_blocks_and_reuses_only_acknowledged_prefix():
    block_size = 4
    init_none_hash(lambda value: str(value).encode().ljust(32, b"0")[:32])
    manager = CloudKVRequestManager(
        kv_cache_config=_kv_cache_config(block_size),
        vllm_config=_vllm_config(block_size),
        instance_id="cloud-a",
    )
    hasher = PrefixHasher(b"tenant-a-secret-key-material", block_size)
    manifest = hasher.build_manifest("control-1", list(range(8)))

    miss = manager.probe(manifest)
    assert miss.hit_tokens == 0

    new_request = NewRequestData(
        req_id="internal-1",
        prompt_token_ids=[0] * 8,
        mm_features=[],
        sampling_params=SamplingParams(max_tokens=4),
        pooling_params=None,
        block_ids=([99, 100],),
        num_computed_tokens=0,
        lora_request=None,
        edge_cloud_request_id="control-1",
    )
    edge_output = _scheduler_output(new_request)
    cloud_output, usage = manager.rewrite_scheduler_output(edge_output)

    assert usage == []
    assert cloud_output.scheduled_new_reqs[0].block_ids != ([99, 100],)
    manager.complete_scheduler_output(cloud_output)

    final_manifest = hasher.build_manifest("control-1", list(range(8)) + [9])
    finish = EdgeCloudFinishedRequest(
        control_request_id="control-1",
        prompt_tokens=8,
        completion_tokens=1,
        full_block_hashes=final_manifest.full_block_hashes,
    )
    _, usage = manager.rewrite_scheduler_output(
        _scheduler_output(
            finished={"internal-1"},
            finish_data={"internal-1": finish},
        )
    )

    assert usage[0][0] == "control-1"
    assert usage[0][1].completion_tokens == 1

    replay = hasher.build_manifest("control-2", list(range(8)))
    hit = manager.probe(replay)
    assert hit.hit_tokens == block_size


def test_cloud_mamba_prefix_replay_starts_new_kv_cache_step():
    block_size = 4
    init_none_hash(lambda value: str(value).encode().ljust(32, b"0")[:32])
    manager = CloudKVRequestManager(
        kv_cache_config=_hybrid_kv_cache_config(block_size),
        vllm_config=_vllm_config(block_size),
        instance_id="cloud-a",
    )
    hasher = PrefixHasher(b"tenant-a-secret-key-material", block_size)
    first_manifest = hasher.build_manifest("control-1", list(range(8)))

    assert manager.probe(first_manifest).hit_tokens == 0
    first_request = NewRequestData(
        req_id="internal-1",
        prompt_token_ids=[0] * 8,
        mm_features=[],
        sampling_params=SamplingParams(max_tokens=4),
        pooling_params=None,
        block_ids=([99, 100], [101, 102]),
        num_computed_tokens=0,
        lora_request=None,
        edge_cloud_request_id="control-1",
    )
    first_output, _ = manager.rewrite_scheduler_output(_scheduler_output(first_request))
    manager.complete_scheduler_output(first_output)

    final_manifest = hasher.build_manifest("control-1", list(range(8)) + [9])
    finish = EdgeCloudFinishedRequest(
        control_request_id="control-1",
        prompt_tokens=8,
        completion_tokens=1,
        full_block_hashes=final_manifest.full_block_hashes,
    )
    manager.rewrite_scheduler_output(
        _scheduler_output(
            finished={"internal-1"},
            finish_data={"internal-1": finish},
        )
    )

    replay_manifest = hasher.build_manifest("control-2", list(range(8)))
    hit = manager.probe(replay_manifest)
    assert hit.hit_tokens == block_size
    replay_request = NewRequestData(
        req_id="internal-2",
        prompt_token_ids=[0] * 8,
        mm_features=[],
        sampling_params=SamplingParams(max_tokens=4),
        pooling_params=None,
        block_ids=([99, 100], [101, 102]),
        num_computed_tokens=hit.hit_tokens,
        lora_request=None,
        edge_cloud_request_id="control-2",
    )

    replay_output, _ = manager.rewrite_scheduler_output(
        _scheduler_output(
            replay_request,
            num_scheduled_tokens=8 - hit.hit_tokens,
        )
    )

    assert replay_output.scheduled_new_reqs[0].num_computed_tokens == block_size


def test_cloud_mtp_draft_reuses_target_allocation_and_delays_prefix_hit():
    block_size = 4
    init_none_hash(lambda value: str(value).encode().ljust(32, b"0")[:32])
    manager = CloudKVRequestManager(
        kv_cache_config=_kv_cache_config(block_size),
        vllm_config=_vllm_config(block_size, mtp_tokens=3),
        instance_id="cloud-a",
    )
    hasher = PrefixHasher(b"tenant-a-secret-key-material", block_size)
    manifest = hasher.build_manifest("control-1", list(range(16)))
    assert manager.probe(manifest).hit_tokens == 0

    new_request = NewRequestData(
        req_id="internal-1",
        prompt_token_ids=[0] * 16,
        mm_features=[],
        sampling_params=SamplingParams(max_tokens=8),
        pooling_params=None,
        block_ids=([99, 100, 101, 102],),
        num_computed_tokens=0,
        lora_request=None,
        edge_cloud_request_id="control-1",
    )
    target = _scheduler_output(
        new_request,
        num_scheduled_tokens=16,
    )
    cloud_target, _ = manager.rewrite_scheduler_output(target)
    target_block_ids = cloud_target.scheduled_new_reqs[0].block_ids
    assert len(target_block_ids[0]) == 5
    manager.complete_scheduler_output(cloud_target)

    before_draft = hasher.build_manifest("control-2", list(range(16)))
    assert manager.probe(before_draft).hit_tokens == 0

    draft = _scheduler_output(
        new_request,
        num_scheduled_tokens=16,
        batch_type=BatchType.DRAFT_FIRST,
    )
    draft.draft_task_id = "target-1"
    draft.draft_step_idx = 2
    cloud_draft, _ = manager.rewrite_scheduler_output(draft)

    assert cloud_draft.scheduled_new_reqs[0].block_ids == target_block_ids
    assert cloud_draft.new_block_ids_to_zero is None
    assert manager._requests["internal-1"].request.num_computed_tokens == 16
    manager.complete_scheduler_output(cloud_draft)
    assert manager._requests["internal-1"].request.num_computed_tokens == 16

    after_draft = hasher.build_manifest("control-3", list(range(16)))
    assert manager.probe(after_draft).hit_tokens > 0


def test_cloud_mtp_hybrid_groups_use_cloud_blocks_and_zeroing_metadata():
    block_size = 4
    init_none_hash(lambda value: str(value).encode().ljust(32, b"0")[:32])
    manager = CloudKVRequestManager(
        kv_cache_config=_hybrid_mtp_kv_cache_config(block_size),
        vllm_config=_vllm_config(block_size, mtp_tokens=3),
        instance_id="cloud-a",
    )
    hasher = PrefixHasher(b"tenant-a-secret-key-material", block_size)
    manifest = hasher.build_manifest("control-1", list(range(8)))
    assert manager.probe(manifest).hit_tokens == 0
    new_request = NewRequestData(
        req_id="internal-1",
        prompt_token_ids=[0] * 8,
        mm_features=[],
        sampling_params=SamplingParams(max_tokens=8),
        pooling_params=None,
        block_ids=([90, 91], [92, 93], [94, 95]),
        num_computed_tokens=0,
        lora_request=None,
        edge_cloud_request_id="control-1",
    )

    rewritten, _ = manager.rewrite_scheduler_output(_scheduler_output(new_request))

    block_ids = rewritten.scheduled_new_reqs[0].block_ids
    assert len(block_ids) == 3
    assert block_ids != new_request.block_ids
    assert rewritten.new_block_ids_to_zero


def test_cloud_mtp_applies_rejection_correction_after_draft_chain():
    block_size = 4
    init_none_hash(lambda value: str(value).encode().ljust(32, b"0")[:32])
    manager = CloudKVRequestManager(
        kv_cache_config=_kv_cache_config(block_size),
        vllm_config=_vllm_config(block_size, mtp_tokens=3),
        instance_id="cloud-a",
    )
    hasher = PrefixHasher(b"tenant-a-secret-key-material", block_size)
    manifest = hasher.build_manifest("control-1", list(range(8)))
    assert manager.probe(manifest).hit_tokens == 0
    new_request = NewRequestData(
        req_id="internal-1",
        prompt_token_ids=[0] * 8,
        mm_features=[],
        sampling_params=SamplingParams(max_tokens=8),
        pooling_params=None,
        block_ids=([99, 100],),
        num_computed_tokens=0,
        lora_request=None,
        edge_cloud_request_id="control-1",
    )
    prefill, _ = manager.rewrite_scheduler_output(_scheduler_output(new_request))
    manager.complete_scheduler_output(prefill)

    cached = CachedRequestData(
        req_ids=["internal-1"],
        resumed_req_ids=set(),
        new_token_ids=[[]],
        all_token_ids={},
        new_block_ids=[None],
        num_computed_tokens=[8],
        num_output_tokens=[1],
    )
    target = _scheduler_output()
    target.scheduled_cached_reqs = cached
    target.num_scheduled_tokens = {"internal-1": 4}
    target.total_num_scheduled_tokens = 4
    target.scheduled_spec_decode_tokens = {"internal-1": [101, 102, 103]}
    target.batch_type = BatchType.DECODE_FIRST
    target.head_token = "target-2"
    cloud_target, _ = manager.rewrite_scheduler_output(target)
    assert cloud_target.scheduled_spec_decode_tokens == {"internal-1": [0, 0, 0]}
    manager.complete_scheduler_output(cloud_target)
    assert manager._requests["internal-1"].request.num_computed_tokens == 12

    draft = copy.copy(target)
    draft.batch_type = BatchType.DRAFT_FIRST
    draft.draft_task_id = "target-2"
    draft.draft_step_idx = 0
    draft.valid_sampled_token_count = {"internal-1": 2}
    cloud_draft, _ = manager.rewrite_scheduler_output(draft)
    assert cloud_draft.scheduled_spec_decode_tokens == {"internal-1": [0, 0, 0]}
    manager.complete_scheduler_output(cloud_draft)
    assert manager._requests["internal-1"].request.num_computed_tokens == 12

    final_draft = copy.copy(draft)
    final_draft.draft_step_idx = 2
    cloud_final_draft, _ = manager.rewrite_scheduler_output(final_draft)
    manager.complete_scheduler_output(cloud_final_draft)
    assert manager._requests["internal-1"].request.num_computed_tokens == 10
