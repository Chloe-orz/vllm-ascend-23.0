# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

import pytest

from vllm_ascend.edge_cloud.prefix_protocol import (
    BLOCK_HASH_PREFIX,
    HEADER_BLOCK_SIZE,
    HEADER_PROTOCOL,
    HEADER_REQUEST_ID,
    PROTOCOL_VERSION,
    TAIL_HASH_PREFIX,
    PrefixHasher,
    PrefixManifest,
    ProbeResult,
    UsageInfo,
)

TENANT_KEY = b"tenant-a-secret-key-material"


def test_prefix_hash_chain_has_stable_golden_vector():
    manifest = PrefixHasher(TENANT_KEY, 4).build_manifest(
        "req-1", [1, 2, 3, 4, 5, 6]
    )

    assert [digest.hex() for digest in manifest.full_block_hashes] == [
        "2a1a033908d2afed05b5dfb1c64d8cde722d9d900d89987c9cf7c1f1165ecd6b"
    ]
    assert manifest.tail_hash is not None
    assert manifest.tail_hash.hex() == (
        "49f73f7a8236524cf76750b78645c0ce553094c2158a714671fecb3a6c4551bd"
    )


def test_prefix_hash_chain_is_tenant_scoped_and_prefix_stable():
    hasher = PrefixHasher(TENANT_KEY, 4)
    short = hasher.build_manifest("short", [1, 2, 3, 4])
    long = hasher.build_manifest("long", [1, 2, 3, 4, 5, 6, 7, 8])
    other_tenant = PrefixHasher(b"tenant-b-secret-key-material", 4).build_manifest(
        "other", [1, 2, 3, 4]
    )

    assert short.full_block_hashes == long.full_block_hashes[:1]
    assert short.full_block_hashes != other_tenant.full_block_hashes


@pytest.mark.parametrize(
    ("tokens", "full_blocks", "has_tail"),
    [([], 0, False), ([1], 0, True), ([1, 2, 3, 4], 1, False)],
)
def test_manifest_marks_only_partial_tail(tokens, full_blocks, has_tail):
    manifest = PrefixHasher(TENANT_KEY, 4).build_manifest("req", tokens)

    assert manifest.full_block_count == full_blocks
    assert (manifest.tail_hash is not None) is has_tail


def test_manifest_round_trips_through_openai_request():
    manifest = PrefixHasher(TENANT_KEY, 4).build_manifest(
        "req-1", [1, 2, 3, 4, 5]
    )
    body = {
        "model": "Qwen/Qwen3.5-9B",
        "messages": manifest.to_messages(),
        "stream": True,
        "stream_options": {"include_usage": True},
        "edge_cloud_prompt_tokens": manifest.prompt_tokens,
    }

    parsed = PrefixManifest.from_openai_request(manifest.to_headers(), body)

    assert parsed == manifest
    assert body["messages"][0]["content"].startswith(BLOCK_HASH_PREFIX)
    assert body["messages"][1]["content"].startswith(TAIL_HASH_PREFIX)


def test_manifest_parser_rejects_non_hash_content():
    headers = {
        HEADER_PROTOCOL: PROTOCOL_VERSION,
        HEADER_REQUEST_ID: "req-1",
        HEADER_BLOCK_SIZE: "4",
    }
    body = {
        "messages": [{"role": "user", "content": "original secret prompt"}],
        "edge_cloud_prompt_tokens": 1,
    }

    with pytest.raises(ValueError, match="not an edge-cloud hash"):
        PrefixManifest.from_openai_request(headers, body)


def test_probe_result_round_trips_case_insensitive_headers():
    result = ProbeResult(
        request_id="req-1",
        instance_id="cloud-a",
        block_size=16,
        hit_blocks=3,
        hit_tokens=48,
    )

    parsed = ProbeResult.from_headers(
        {key.lower(): value for key, value in result.to_headers().items()}
    )

    assert parsed == result


def test_usage_uses_openai_cached_token_shape():
    usage = UsageInfo(prompt_tokens=100, completion_tokens=20, cached_tokens=64)

    assert usage.to_openai_dict() == {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
        "prompt_tokens_details": {"cached_tokens": 64},
    }


def test_token_id_must_fit_uint32():
    hasher = PrefixHasher(TENANT_KEY, 4)

    with pytest.raises(ValueError, match="unsigned 32-bit"):
        hasher.build_manifest("req", [0, 1, 2, 2**32])
