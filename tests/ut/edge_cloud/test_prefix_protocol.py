# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

import hashlib
import hmac
import struct
from dataclasses import dataclass

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
    _MODALITY_IDS,
)

TENANT_KEY = b"tenant-a-secret-key-material"
PROCESSOR_FINGERPRINT = bytes(range(32))
OTHER_PROCESSOR_FINGERPRINT = bytes(reversed(range(32)))
IMAGE_A_DIGEST = hashlib.sha256(b"image-a").digest()
IMAGE_B_DIGEST = hashlib.sha256(b"image-b").digest()


@dataclass(frozen=True)
class MediaItem:
    """Duck-typed stand-in for the edge-cloud media identity description."""

    modality: str
    digest: bytes
    offset: int
    length: int


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


def test_media_block_hash_chain_has_stable_golden_vector():
    # K=4, one image covering blocks [0,4) and [4,8); tail [8,10) is
    # media-free and keeps the v1 tail domain.
    manifest = PrefixHasher(
        TENANT_KEY, 4, PROCESSOR_FINGERPRINT
    ).build_manifest(
        "req-mm-1",
        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        [MediaItem("image", IMAGE_A_DIGEST, 2, 5)],
    )

    assert [digest.hex() for digest in manifest.full_block_hashes] == [
        "b932342107e21e632db1514a246992173e448af3055c15b74ab183b2c790a8de",
        "aa98ce7f2d553fc5a2df2f6fea241b13ba1b4a89e9f3770d164c8bcd02bec0f6",
    ]
    assert manifest.tail_hash is not None
    assert manifest.tail_hash.hex() == (
        "403395638d987710ec3b461ada8df1c2ab064b312186392553d6fc00d78a3775"
    )


def test_media_tail_hash_chain_has_stable_golden_vector():
    # K=4, one full text block followed by a tail that covers the image.
    manifest = PrefixHasher(
        TENANT_KEY, 4, PROCESSOR_FINGERPRINT
    ).build_manifest(
        "req-mm-2",
        [1, 2, 3, 4, 5, 6],
        [MediaItem("image", IMAGE_A_DIGEST, 4, 2)],
    )

    # The media-free full block matches the v1 golden vector byte for byte.
    assert [digest.hex() for digest in manifest.full_block_hashes] == [
        "2a1a033908d2afed05b5dfb1c64d8cde722d9d900d89987c9cf7c1f1165ecd6b"
    ]
    assert manifest.tail_hash is not None
    assert manifest.tail_hash.hex() == (
        "9754d69038cd22925564f0515609b5f4b481527843f64a351579680f9e9f6f23"
    )


def test_media_chain_is_reproducible_for_same_image_text_and_position():
    tokens = list(range(1, 13))
    items = [MediaItem("image", IMAGE_A_DIGEST, 2, 5)]
    first = PrefixHasher(TENANT_KEY, 4, PROCESSOR_FINGERPRINT).build_manifest(
        "first", tokens, items
    )
    second = PrefixHasher(TENANT_KEY, 4, PROCESSOR_FINGERPRINT).build_manifest(
        "second", tokens, items
    )

    assert first.full_block_hashes == second.full_block_hashes
    assert first.tail_hash == second.tail_hash


def test_different_image_diverges_from_first_media_block():
    tokens = list(range(1, 13))
    hasher = PrefixHasher(TENANT_KEY, 4, PROCESSOR_FINGERPRINT)
    image_a = hasher.build_manifest(
        "a", tokens, [MediaItem("image", IMAGE_A_DIGEST, 4, 4)]
    )
    image_b = hasher.build_manifest(
        "b", tokens, [MediaItem("image", IMAGE_B_DIGEST, 4, 4)]
    )

    # Block 0 is pure text and shared; block 1 covers the image and forks.
    assert image_a.full_block_hashes[0] == image_b.full_block_hashes[0]
    assert image_a.full_block_hashes[1] != image_b.full_block_hashes[1]
    assert image_a.full_block_hashes[2] != image_b.full_block_hashes[2]


def test_same_image_at_different_offset_diverges_media_block():
    tokens = list(range(1, 13))
    hasher = PrefixHasher(TENANT_KEY, 4, PROCESSOR_FINGERPRINT)
    early = hasher.build_manifest(
        "early", tokens, [MediaItem("image", IMAGE_A_DIGEST, 4, 4)]
    )
    late = hasher.build_manifest(
        "late", tokens, [MediaItem("image", IMAGE_A_DIGEST, 8, 4)]
    )

    assert early.full_block_hashes[0] == late.full_block_hashes[0]
    assert early.full_block_hashes[1] != late.full_block_hashes[1]


def test_different_processor_fingerprint_diverges_media_blocks_only():
    tokens = list(range(1, 13))
    items = [MediaItem("image", IMAGE_A_DIGEST, 4, 4)]
    baseline = PrefixHasher(TENANT_KEY, 4, PROCESSOR_FINGERPRINT).build_manifest(
        "baseline", tokens, items
    )
    other = PrefixHasher(
        TENANT_KEY, 4, OTHER_PROCESSOR_FINGERPRINT
    ).build_manifest("other", tokens, items)

    # The pre-media text block is fingerprint-independent.
    assert baseline.full_block_hashes[0] == other.full_block_hashes[0]
    assert baseline.full_block_hashes[1] != other.full_block_hashes[1]
    assert baseline.full_block_hashes[2] != other.full_block_hashes[2]


def test_text_blocks_before_media_match_plain_text_request():
    tokens = list(range(1, 13))
    media = PrefixHasher(TENANT_KEY, 4, PROCESSOR_FINGERPRINT).build_manifest(
        "mm", tokens, [MediaItem("image", IMAGE_A_DIGEST, 8, 4)]
    )
    plain = PrefixHasher(TENANT_KEY, 4).build_manifest("text", tokens)

    # Blocks 0-1 precede the image and are interoperable with text requests.
    assert media.full_block_hashes[:2] == plain.full_block_hashes[:2]
    assert media.full_block_hashes[2] != plain.full_block_hashes[2]


def test_hasher_without_media_items_never_uses_media_domains():
    tokens = list(range(1, 13))
    v1 = PrefixHasher(TENANT_KEY, 4).build_manifest("v1", tokens)
    fingerprint_only = PrefixHasher(
        TENANT_KEY, 4, PROCESSOR_FINGERPRINT
    ).build_manifest("fp", tokens)

    assert fingerprint_only.full_block_hashes == v1.full_block_hashes
    assert fingerprint_only.tail_hash == v1.tail_hash


def test_multiple_images_in_one_block_all_mix_into_hash():
    tokens = list(range(1, 9))
    hasher = PrefixHasher(TENANT_KEY, 4, PROCESSOR_FINGERPRINT)
    both = hasher.build_manifest(
        "both",
        tokens,
        [
            MediaItem("image", IMAGE_A_DIGEST, 4, 2),
            MediaItem("image", IMAGE_B_DIGEST, 6, 2),
        ],
    )
    only_a = hasher.build_manifest(
        "only-a", tokens, [MediaItem("image", IMAGE_A_DIGEST, 4, 2)]
    )
    only_b = hasher.build_manifest(
        "only-b", tokens, [MediaItem("image", IMAGE_B_DIGEST, 6, 2)]
    )

    assert both.full_block_hashes[1] != only_a.full_block_hashes[1]
    assert both.full_block_hashes[1] != only_b.full_block_hashes[1]
    assert both.full_block_hashes[0] == only_a.full_block_hashes[0]


def test_image_spanning_multiple_blocks_mixes_into_each_covered_block():
    tokens = list(range(1, 13))
    hasher = PrefixHasher(TENANT_KEY, 4, PROCESSOR_FINGERPRINT)
    spanning = hasher.build_manifest(
        "spanning", tokens, [MediaItem("image", IMAGE_A_DIGEST, 3, 6)]
    )
    plain = hasher.build_manifest("plain", tokens, [])

    # The image [3, 9) intersects blocks 0, 1 and 2; all of them fork.
    assert spanning.full_block_hashes[0] != plain.full_block_hashes[0]
    assert spanning.full_block_hashes[1] != plain.full_block_hashes[1]
    assert spanning.full_block_hashes[2] != plain.full_block_hashes[2]


def test_image_at_block_boundary_is_covered_by_intersection():
    tokens = list(range(1, 9))
    hasher = PrefixHasher(TENANT_KEY, 4, PROCESSOR_FINGERPRINT)
    aligned = hasher.build_manifest(
        "aligned", tokens, [MediaItem("image", IMAGE_A_DIGEST, 4, 4)]
    )
    plain = hasher.build_manifest("plain", tokens, [])

    # The image starts exactly at block 1 and does not leak into block 0.
    assert aligned.full_block_hashes[0] == plain.full_block_hashes[0]
    assert aligned.full_block_hashes[1] != plain.full_block_hashes[1]


def test_image_at_prompt_offset_zero_uses_media_domain_on_first_block():
    tokens = list(range(1, 9))
    hasher = PrefixHasher(TENANT_KEY, 4, PROCESSOR_FINGERPRINT)
    leading = hasher.build_manifest(
        "leading", tokens, [MediaItem("image", IMAGE_A_DIGEST, 0, 2)]
    )
    plain = hasher.build_manifest("plain", tokens, [])

    assert leading.full_block_hashes[0] != plain.full_block_hashes[0]


def test_media_free_tail_after_media_block_keeps_v1_tail_domain():
    tokens = list(range(1, 11))
    hasher = PrefixHasher(TENANT_KEY, 4, PROCESSOR_FINGERPRINT)
    with_media = hasher.build_manifest(
        "mm", tokens, [MediaItem("image", IMAGE_A_DIGEST, 0, 4)]
    )

    # Recompute the expected v1-domain tail on top of the media parent.
    parent = with_media.full_block_hashes[-1]
    tail_bytes = b"".join(struct.pack(">I", token) for token in [9, 10])
    expected_tail = hmac.digest(
        TENANT_KEY, b"\x02" + parent + struct.pack(">I", 2) + tail_bytes, "sha256"
    )
    assert with_media.tail_hash == expected_tail


def test_media_covering_tail_uses_media_tail_domain():
    tokens = [1, 2, 3, 4, 5, 6]
    hasher = PrefixHasher(TENANT_KEY, 4, PROCESSOR_FINGERPRINT)
    media_tail = hasher.build_manifest(
        "mm", tokens, [MediaItem("image", IMAGE_A_DIGEST, 4, 2)]
    )
    plain_tail = hasher.build_manifest("plain", tokens, [])

    assert media_tail.full_block_hashes == plain_tail.full_block_hashes
    assert media_tail.tail_hash != plain_tail.tail_hash


def test_media_items_require_processor_fingerprint():
    hasher = PrefixHasher(TENANT_KEY, 4)

    with pytest.raises(ValueError, match="processor_fingerprint is required"):
        hasher.build_manifest(
            "req", [1, 2, 3, 4], [MediaItem("image", IMAGE_A_DIGEST, 0, 2)]
        )


def test_processor_fingerprint_must_be_32_bytes():
    with pytest.raises(ValueError, match="processor_fingerprint must contain"):
        PrefixHasher(TENANT_KEY, 4, b"short-fingerprint")


@pytest.mark.parametrize(
    "media_item",
    [
        MediaItem("video", IMAGE_A_DIGEST, 0, 2),
        MediaItem("image", b"", 0, 2),
        MediaItem("image", b"x" * 65, 0, 2),
        MediaItem("image", IMAGE_A_DIGEST, -1, 2),
        MediaItem("image", IMAGE_A_DIGEST, 0, 0),
        MediaItem("image", IMAGE_A_DIGEST, 3, 2),
    ],
)
def test_invalid_media_item_is_rejected(media_item):
    hasher = PrefixHasher(TENANT_KEY, 4, PROCESSOR_FINGERPRINT)

    with pytest.raises(ValueError):
        hasher.build_manifest("req", [1, 2, 3, 4], [media_item])


def test_overlapping_media_items_are_rejected():
    hasher = PrefixHasher(TENANT_KEY, 4, PROCESSOR_FINGERPRINT)
    overlapping = [
        MediaItem("image", IMAGE_B_DIGEST, 4, 4),
        MediaItem("image", IMAGE_A_DIGEST, 2, 4),
    ]

    with pytest.raises(ValueError, match="must not overlap"):
        hasher.build_manifest("req", list(range(1, 9)), overlapping)


def test_adjacent_media_items_do_not_overlap():
    hasher = PrefixHasher(TENANT_KEY, 4, PROCESSOR_FINGERPRINT)
    adjacent = [
        MediaItem("image", IMAGE_A_DIGEST, 0, 2),
        MediaItem("image", IMAGE_B_DIGEST, 2, 2),
    ]

    manifest = hasher.build_manifest("req", [1, 2, 3, 4], adjacent)

    assert manifest.full_block_count == 1


@pytest.mark.parametrize(
    "raw_digest",
    [
        hashlib.sha256(b"image-a").digest(),
        hashlib.sha512(b"image-a").digest(),
        b"short-digest",
    ],
    ids=["sha256-32-bytes", "sha512-64-bytes", "short-12-bytes"],
)
def test_source_digest_is_normalized_to_sha256(raw_digest):
    # The external ABI media identity is always SHA-256(source content
    # digest): any non-empty raw digest up to 64 bytes is accepted and the
    # chain mixes in exactly its 32-byte SHA-256 normalization, decoupling
    # the protocol from the configured vLLM hasher algorithm.
    tokens = list(range(1, 9))
    manifest = PrefixHasher(TENANT_KEY, 4, PROCESSOR_FINGERPRINT).build_manifest(
        "req", tokens, [MediaItem("image", raw_digest, 4, 4)]
    )

    parent = manifest.full_block_hashes[0]
    media_fields = (
        PROCESSOR_FINGERPRINT
        + struct.pack(">I", 1)
        + bytes([_MODALITY_IDS["image"]])
        + hashlib.sha256(raw_digest).digest()
        + struct.pack(">I", 4)
        + struct.pack(">I", 4)
    )
    block_bytes = b"".join(struct.pack(">I", token) for token in [5, 6, 7, 8])
    expected = hmac.digest(
        TENANT_KEY,
        b"\x04" + parent + struct.pack(">I", 4) + block_bytes + media_fields,
        "sha256",
    )
    assert manifest.full_block_hashes[1] == expected


def test_same_source_digest_produces_identical_manifest():
    raw_digest = hashlib.sha512(b"image-a").digest()
    tokens = list(range(1, 9))
    hasher = PrefixHasher(TENANT_KEY, 4, PROCESSOR_FINGERPRINT)
    first = hasher.build_manifest(
        "first", tokens, [MediaItem("image", raw_digest, 4, 4)]
    )
    second = hasher.build_manifest(
        "second", tokens, [MediaItem("image", raw_digest, 4, 4)]
    )

    assert first.full_block_hashes == second.full_block_hashes
    assert first.tail_hash == second.tail_hash


def test_different_source_digests_fork_the_media_chain():
    tokens = list(range(1, 9))
    hasher = PrefixHasher(TENANT_KEY, 4, PROCESSOR_FINGERPRINT)
    image_a = hasher.build_manifest(
        "a",
        tokens,
        [MediaItem("image", hashlib.sha512(b"image-a").digest(), 4, 4)],
    )
    image_b = hasher.build_manifest(
        "b",
        tokens,
        [MediaItem("image", hashlib.sha512(b"image-b").digest(), 4, 4)],
    )

    assert image_a.full_block_hashes[0] == image_b.full_block_hashes[0]
    assert image_a.full_block_hashes[1] != image_b.full_block_hashes[1]


def test_modality_ids_mapping_is_immutable():
    with pytest.raises(TypeError):
        _MODALITY_IDS["audio"] = 2
