# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

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


def _scheduler_output(
    new_request=None,
    *,
    finished=None,
    finish_data=None,
    num_scheduled_tokens=8,
):
    scheduled_new_reqs = [] if new_request is None else [new_request]
    num_scheduled = {} if new_request is None else {new_request.req_id: num_scheduled_tokens}
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
        batch_type=(BatchType.EMPTY if new_request is None else BatchType.PREFILL_FIRST),
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
