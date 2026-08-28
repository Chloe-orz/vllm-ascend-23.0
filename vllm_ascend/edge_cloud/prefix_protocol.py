# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

"""Wire protocol for privacy-preserving edge-cloud prefix negotiation.

The protocol intentionally uses ordinary OpenAI chat messages and response
headers. This lets an unmodified OpenAI-compatible gateway forward and account
for the internal request while keeping the original prompt on the edge.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = "edge-cloud-prefix-v1"
BLOCK_HASH_PREFIX = "ecb1:"
TAIL_HASH_PREFIX = "ect1:"
DIGEST_SIZE = hashlib.sha256().digest_size

HEADER_PROTOCOL = "X-Edge-Cloud-Protocol"
HEADER_REQUEST_ID = "X-Edge-Cloud-Request-ID"
HEADER_EDGE_ID = "X-Edge-Cloud-Edge-Id"
HEADER_INSTANCE_ID = "X-Edge-Cloud-Instance-ID"
HEADER_BLOCK_SIZE = "X-Edge-Cloud-Block-Size"
HEADER_HIT_BLOCKS = "X-Edge-Cloud-Prefix-Hit-Blocks"
HEADER_HIT_TOKENS = "X-Edge-Cloud-Prefix-Hit-Tokens"

_FULL_BLOCK_DOMAIN = b"\x01"
_TAIL_BLOCK_DOMAIN = b"\x02"
_UINT32 = struct.Struct(">I")


def _encode_digest(digest: bytes) -> str:
    if len(digest) != DIGEST_SIZE:
        raise ValueError(f"digest must contain {DIGEST_SIZE} bytes")
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _decode_digest(value: str) -> bytes:
    try:
        raw = value.encode("ascii")
        digest = base64.b64decode(
            raw + b"=" * (-len(raw) % 4), altchars=b"-_", validate=True
        )
    except (UnicodeEncodeError, ValueError) as exc:
        raise ValueError("invalid base64url digest") from exc
    if len(digest) != DIGEST_SIZE:
        raise ValueError(f"digest must contain {DIGEST_SIZE} bytes")
    return digest


def _encode_tokens(token_ids: Sequence[int]) -> bytes:
    encoded = bytearray()
    for token_id in token_ids:
        if not isinstance(token_id, int) or isinstance(token_id, bool):
            raise TypeError("token IDs must be integers")
        if not 0 <= token_id <= 0xFFFFFFFF:
            raise ValueError("token IDs must fit in an unsigned 32-bit integer")
        encoded.extend(_UINT32.pack(token_id))
    return bytes(encoded)


@dataclass(frozen=True)
class PrefixManifest:
    """Opaque hash chain sent from an edge to a cloud endpoint."""

    request_id: str
    prompt_tokens: int
    block_size: int
    full_block_hashes: tuple[bytes, ...]
    tail_hash: bytes | None = None

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("request_id must not be empty")
        if self.prompt_tokens < 0:
            raise ValueError("prompt_tokens must not be negative")
        if self.block_size <= 0:
            raise ValueError("block_size must be positive")
        expected_blocks = self.prompt_tokens // self.block_size
        if len(self.full_block_hashes) != expected_blocks:
            raise ValueError(
                "full block hash count does not match prompt_tokens and block_size"
            )
        for digest in self.full_block_hashes:
            if len(digest) != DIGEST_SIZE:
                raise ValueError(f"digest must contain {DIGEST_SIZE} bytes")
        has_partial_tail = self.prompt_tokens % self.block_size != 0
        if has_partial_tail != (self.tail_hash is not None):
            raise ValueError("tail_hash must be present exactly for a partial block")
        if self.tail_hash is not None and len(self.tail_hash) != DIGEST_SIZE:
            raise ValueError(f"tail digest must contain {DIGEST_SIZE} bytes")

    @property
    def full_block_count(self) -> int:
        """Return the number of cacheable full blocks in the prompt."""
        return len(self.full_block_hashes)

    def to_messages(self) -> list[dict[str, str]]:
        """Render the manifest as OpenAI-compatible chat messages."""
        messages = [
            {"role": "user", "content": BLOCK_HASH_PREFIX + _encode_digest(digest)}
            for digest in self.full_block_hashes
        ]
        if self.tail_hash is not None:
            messages.append(
                {
                    "role": "user",
                    "content": TAIL_HASH_PREFIX + _encode_digest(self.tail_hash),
                }
            )
        return messages

    def to_headers(self) -> dict[str, str]:
        """Return request headers required to parse the OpenAI body."""
        return {
            HEADER_PROTOCOL: PROTOCOL_VERSION,
            HEADER_REQUEST_ID: self.request_id,
            HEADER_BLOCK_SIZE: str(self.block_size),
        }

    @classmethod
    def from_openai_request(
        cls, headers: Mapping[str, str], body: Mapping[str, Any]
    ) -> PrefixManifest:
        """Parse and validate a manifest from an OpenAI chat request."""
        normalized_headers = {key.lower(): value for key, value in headers.items()}

        def required_header(name: str) -> str:
            try:
                return normalized_headers[name.lower()]
            except KeyError as exc:
                raise ValueError(f"missing required header {name}") from exc

        protocol = required_header(HEADER_PROTOCOL)
        if protocol != PROTOCOL_VERSION:
            raise ValueError(f"unsupported edge-cloud protocol {protocol!r}")
        request_id = required_header(HEADER_REQUEST_ID)
        try:
            block_size = int(required_header(HEADER_BLOCK_SIZE))
        except ValueError as exc:
            raise ValueError("edge-cloud block size must be an integer") from exc

        messages = body.get("messages")
        if not isinstance(messages, list):
            raise ValueError("messages must be a list")
        full_hashes: list[bytes] = []
        tail_hash: bytes | None = None
        for index, message in enumerate(messages):
            if not isinstance(message, Mapping) or message.get("role") != "user":
                raise ValueError("every manifest message must have role=user")
            content = message.get("content")
            if not isinstance(content, str):
                raise ValueError("every manifest message must have string content")
            if content.startswith(BLOCK_HASH_PREFIX):
                if tail_hash is not None:
                    raise ValueError("a full block hash cannot follow the tail hash")
                full_hashes.append(_decode_digest(content[len(BLOCK_HASH_PREFIX) :]))
            elif content.startswith(TAIL_HASH_PREFIX):
                if tail_hash is not None or index != len(messages) - 1:
                    raise ValueError("the tail hash must be the final unique message")
                tail_hash = _decode_digest(content[len(TAIL_HASH_PREFIX) :])
            else:
                raise ValueError("message content is not an edge-cloud hash")

        prompt_tokens_value = body.get("edge_cloud_prompt_tokens")
        if not isinstance(prompt_tokens_value, int) or isinstance(
            prompt_tokens_value, bool
        ):
            raise ValueError("edge_cloud_prompt_tokens must be an integer")
        return cls(
            request_id=request_id,
            prompt_tokens=prompt_tokens_value,
            block_size=block_size,
            full_block_hashes=tuple(full_hashes),
            tail_hash=tail_hash,
        )


class PrefixHasher:
    """Build a tenant-scoped HMAC-SHA256 chain at KV block boundaries."""

    def __init__(self, tenant_key: bytes, block_size: int) -> None:
        if len(tenant_key) < 16:
            raise ValueError("tenant_key must contain at least 16 bytes")
        if block_size <= 0:
            raise ValueError("block_size must be positive")
        self._tenant_key = tenant_key
        self.block_size = block_size
        self._seed = hmac.digest(tenant_key, PROTOCOL_VERSION.encode(), "sha256")

    def build_manifest(
        self, request_id: str, prompt_token_ids: Sequence[int]
    ) -> PrefixManifest:
        """Hash a tokenized prompt and return its wire manifest."""
        token_bytes = _encode_tokens(prompt_token_ids)
        parent = self._seed
        full_hashes: list[bytes] = []
        full_count = len(prompt_token_ids) // self.block_size
        encoded_block_size = _UINT32.pack(self.block_size)

        for index in range(full_count):
            start = index * self.block_size * _UINT32.size
            end = start + self.block_size * _UINT32.size
            parent = hmac.digest(
                self._tenant_key,
                _FULL_BLOCK_DOMAIN + parent + encoded_block_size + token_bytes[start:end],
                "sha256",
            )
            full_hashes.append(parent)

        remainder = len(prompt_token_ids) % self.block_size
        tail_hash = None
        if remainder:
            tail_bytes = token_bytes[full_count * self.block_size * _UINT32.size :]
            tail_hash = hmac.digest(
                self._tenant_key,
                _TAIL_BLOCK_DOMAIN + parent + _UINT32.pack(remainder) + tail_bytes,
                "sha256",
            )

        return PrefixManifest(
            request_id=request_id,
            prompt_tokens=len(prompt_token_ids),
            block_size=self.block_size,
            full_block_hashes=tuple(full_hashes),
            tail_hash=tail_hash,
        )


@dataclass(frozen=True)
class ProbeResult:
    """Cloud instance selection and reserved prefix returned to the edge."""

    request_id: str
    instance_id: str
    block_size: int
    hit_blocks: int
    hit_tokens: int

    def __post_init__(self) -> None:
        if not self.request_id or not self.instance_id:
            raise ValueError("request_id and instance_id must not be empty")
        if self.block_size <= 0 or self.hit_blocks < 0 or self.hit_tokens < 0:
            raise ValueError("invalid prefix hit values")
        if self.hit_tokens != self.hit_blocks * self.block_size:
            raise ValueError("hit_tokens must equal hit_blocks * block_size")

    def to_headers(self) -> dict[str, str]:
        """Render the result as response headers visible to a gateway."""
        return {
            HEADER_PROTOCOL: PROTOCOL_VERSION,
            HEADER_REQUEST_ID: self.request_id,
            HEADER_INSTANCE_ID: self.instance_id,
            HEADER_BLOCK_SIZE: str(self.block_size),
            HEADER_HIT_BLOCKS: str(self.hit_blocks),
            HEADER_HIT_TOKENS: str(self.hit_tokens),
        }

    @classmethod
    def from_headers(cls, headers: Mapping[str, str]) -> ProbeResult:
        """Parse a cloud prefix result from case-insensitive HTTP headers."""
        values = {key.lower(): value for key, value in headers.items()}

        def required(name: str) -> str:
            try:
                return values[name.lower()]
            except KeyError as exc:
                raise ValueError(f"missing required header {name}") from exc

        if required(HEADER_PROTOCOL) != PROTOCOL_VERSION:
            raise ValueError("unsupported edge-cloud protocol")
        try:
            return cls(
                request_id=required(HEADER_REQUEST_ID),
                instance_id=required(HEADER_INSTANCE_ID),
                block_size=int(required(HEADER_BLOCK_SIZE)),
                hit_blocks=int(required(HEADER_HIT_BLOCKS)),
                hit_tokens=int(required(HEADER_HIT_TOKENS)),
            )
        except ValueError as exc:
            raise ValueError("cloud prefix result contains invalid integers") from exc


@dataclass(frozen=True)
class UsageInfo:
    """Usage counters returned in the final OpenAI streaming chunk."""

    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int

    def __post_init__(self) -> None:
        if min(self.prompt_tokens, self.completion_tokens, self.cached_tokens) < 0:
            raise ValueError("usage counters must not be negative")
        if self.cached_tokens > self.prompt_tokens:
            raise ValueError("cached_tokens must not exceed prompt_tokens")

    def to_openai_dict(self) -> dict[str, Any]:
        """Render counters using the OpenAI chat completion usage shape."""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "prompt_tokens_details": {"cached_tokens": self.cached_tokens},
        }
