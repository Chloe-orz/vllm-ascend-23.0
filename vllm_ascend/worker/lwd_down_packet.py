# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""prefill_only c2e (DOWN) combined-packet wire format.

One flat bf16 tensor per request, carrying the LAST decode step's:

    ① final hidden states (post-norm, logits input)   [R, H] bf16
    ② topk candidates (ids + logits)                  [R, K] int32 + bf16
    ③ num_accepted_tokens (draft hits of that step)   scalar int32

Layout (all sizes in bf16 elements; int32 fields are bit-packed into
bf16 slot pairs):

    header: 32 bf16 slots = 16 x int32:
        [0] magic (LWD_DOWN_MAGIC)
        [1] version
        [2] N      prompt tokens
        [3] R      rows (== num_accepted + 1; 1 for non-spec)
        [4] K      topk width (global config, fixed stride basis)
        [5] H      hidden size
        [6] num_accepted
        [7] flags  (bit0: topk_logits are fp32-packed pairs)
        [8-9]  req_fingerprint (lo/hi int32 of a 64-bit id hash)
        [10-15] reserved (0)
    payload: R rows x S, S = H + 3K bf16 elements (constant for any
        spec config):
        [0      : H)     final hidden           bf16 x H
        [H      : H+2K)  topk_token_ids         int32 x K bit-packed
        [H+2K   : H+3K)  topk_logits            bf16 x K

    Candidate semantics (wire contract): topk_logits are sorted by logit
    descending (a true GLOBAL top-K reduction, correct for TP>1 where
    the sampler's candidate set is a per-rank concatenation).  Padded /
    masked-out entries carry logit == -inf and MUST be ignored by the
    receiver — there is deliberately no separate valid-count field, the
    -inf marker is unambiguous per row and survives the bf16 cast.

Both sides derive S from config (H, K); R comes from the header — so the
parser never needs the spec k.  The receiver learns R before posting the
irecv from the control-plane notification (HCCL needs exact numel).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import torch

LWD_DOWN_MAGIC = 0x70C2E002  # "POC2E002"
LWD_DOWN_VERSION = 1

LWD_HEADER_I32 = 16              # int32 fields
LWD_HEADER_BF16 = LWD_HEADER_I32 * 2  # 32 bf16 slots

# flags: currently all zero (reserved).  There is NO FIN packet —
# request finish/abort is signaled by the control plane (v2.6).


def lwd_row_stride(hidden_size: int, topk_k: int) -> int:
    """Per-row stride S in bf16 elements: H + 3K (K ids are int32 -> 2K
    bf16 slots, K logits bf16)."""
    return hidden_size + 3 * topk_k


def lwd_packet_num_elements(num_rows: int, hidden_size: int, topk_k: int) -> int:
    """Total bf16 element count of a packet carrying ``num_rows`` rows."""
    return LWD_HEADER_BF16 + num_rows * lwd_row_stride(hidden_size, topk_k)


def lwd_down_wire_num_elements(hidden_size: int, topk_k: int, max_rows: int) -> int:
    """FIXED on-the-wire packet size (streaming mode): every DOWN packet
    occupies exactly this many bf16 elements (R_max rows, padding
    unused), so the receiver can pre-post a ring of recvs without
    per-step size knowledge.  R_max = num_speculative_tokens + 1 (1 when
    spec is off)."""
    return lwd_packet_num_elements(max_rows, hidden_size, topk_k)


def lwd_request_fingerprint(request_id: str) -> int:
    """64-bit fingerprint for cross-request-mixup detection."""
    digest = hashlib.blake2b(request_id.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "little")


@dataclass
class LwdDownPacket:
    """Decoded view of one c2e packet (zero-copy views into the recv
    buffer except where dtype re-interpretation forces a copy)."""

    num_prompt_tokens: int
    num_rows: int
    topk_k: int
    hidden_size: int
    num_accepted: int
    fingerprint: int
    flags: int = 0
    hidden: torch.Tensor | None = None      # [R, H] bf16
    topk_ids: torch.Tensor | None = None    # [R, K] int32
    topk_logits: torch.Tensor | None = None # [R, K] bf16


def _u32(x: int) -> int:
    """Unsigned 32-bit -> signed int32 (torch has no uint32)."""
    x &= 0xFFFFFFFF
    return x - (1 << 32) if x >= (1 << 31) else x


def pack_lwd_down_packet(
    *,
    hidden: torch.Tensor,        # [R, H] bf16
    topk_ids: torch.Tensor,      # [R, K] int32
    topk_logits: torch.Tensor,   # [R, K] bf16
    num_prompt_tokens: int,
    num_accepted: int,
    request_id: str,
    flags: int = 0,
    wire_num_elements: int | None = None,
) -> torch.Tensor:
    """Assemble the flat bf16 wire tensor (device-side, no D2H).

    Streaming mode: pass ``wire_num_elements`` =
    ``lwd_down_wire_num_elements(H, K, R_max)`` so every packet on the
    wire has the SAME fixed size (padded) and the receiver can pre-post
    a recv ring without per-step size knowledge.
    """
    assert hidden.dim() == 2 and hidden.dtype == torch.bfloat16
    R, H = hidden.shape
    K = topk_ids.shape[1]
    assert topk_ids.shape == (R, K) and topk_logits.shape == (R, K)
    assert topk_ids.dtype == torch.int32 and topk_logits.dtype == torch.bfloat16

    total = lwd_packet_num_elements(R, H, K)
    if wire_num_elements is not None:
        assert wire_num_elements >= total, (
            wire_num_elements, total)
        total = wire_num_elements
    buf = torch.zeros(total, dtype=torch.bfloat16, device=hidden.device)

    # header (H2D once per request, at finalize only)
    fp = lwd_request_fingerprint(request_id)
    header = torch.tensor(
        [
            LWD_DOWN_MAGIC,
            LWD_DOWN_VERSION,
            num_prompt_tokens,
            R,
            K,
            H,
            num_accepted,
            flags,
            _u32(fp),
            _u32(fp >> 32),
            0, 0, 0, 0, 0, 0,
        ],
        dtype=torch.int32,
    ).to(device=hidden.device)
    buf[:LWD_HEADER_BF16].view(torch.int32).copy_(header)

    # payload: R rows x S
    S = lwd_row_stride(H, K)
    rows = buf[LWD_HEADER_BF16:].view(R, S)
    rows[:, :H].copy_(hidden)
    rows[:, H:H + 2 * K].copy_(topk_ids.view(torch.bfloat16))
    rows[:, H + 2 * K:H + 3 * K].copy_(topk_logits)
    return buf


def unpack_lwd_down_packet(
    buf: torch.Tensor,
    *,
    expected_fingerprint: int | None = None,
    max_rows: int | None = None,
    max_topk_k: int | None = None,
    hidden_size: int | None = None,
) -> LwdDownPacket:
    """Parse + validate a received packet.  Any validation failure raises
    before anything touches the sampling path (anti cross-request
    mixup / malformed-payload defense)."""
    assert buf.dtype == torch.bfloat16 and buf.dim() == 1
    if buf.numel() < LWD_HEADER_BF16:
        raise ValueError(f"c2e packet malformed length: {buf.numel()}")
    hdr = buf[:LWD_HEADER_BF16].view(torch.int32).cpu()
    magic, version, N, R, K, H, accepted, flags = (int(x) for x in hdr[:8])
    fp = (int(hdr[8]) & 0xFFFFFFFF) | ((int(hdr[9]) & 0xFFFFFFFF) << 32)

    if magic != LWD_DOWN_MAGIC:
        raise ValueError(f"c2e packet bad magic: {magic:#x}")
    if version != LWD_DOWN_VERSION:
        raise ValueError(f"c2e packet unsupported version: {version}")
    if R < 1:
        raise ValueError(f"c2e packet empty payload: R={R}")
    if K < 1:
        raise ValueError(f"c2e packet bad topk width: K={K}")
    if hidden_size is not None and H != hidden_size:
        raise ValueError(f"c2e packet H mismatch: {H} != {hidden_size}")
    if max_topk_k is not None and K > max_topk_k:
        raise ValueError(f"c2e packet K over limit: {K} > {max_topk_k}")
    if max_rows is not None and R > max_rows:
        raise ValueError(f"c2e packet R over limit: {R} > {max_rows}")
    if expected_fingerprint is not None and fp != expected_fingerprint:
        raise ValueError(
            "c2e packet fingerprint mismatch: cross-request mixup guard"
        )
    expected = lwd_packet_num_elements(R, H, K)
    if buf.numel() < expected:
        raise ValueError(
            f"c2e packet truncated: {buf.numel()} < {expected} elements"
        )

    S = lwd_row_stride(H, K)
    rows = buf[LWD_HEADER_BF16:LWD_HEADER_BF16 + R * S].view(R, S)
    hidden = rows[:, :H]
    # NB: .contiguous() is a no-op for R == 1 (size-1 dim strides are
    # ignored by is_contiguous), which breaks the dtype re-interpretation
    # below — copy into a fresh truly-contiguous buffer instead.
    ids_bf16 = torch.empty(R, 2 * K, dtype=torch.bfloat16, device=buf.device)
    ids_bf16.copy_(rows[:, H:H + 2 * K])
    topk_ids = ids_bf16.view(torch.int32)
    topk_logits = rows[:, H + 2 * K:H + 3 * K]
    return LwdDownPacket(
        num_prompt_tokens=N,
        num_rows=R,
        topk_k=K,
        hidden_size=H,
        num_accepted=accepted,
        fingerprint=fp,
        flags=flags,
        hidden=hidden,
        topk_ids=topk_ids,
        topk_logits=topk_logits,
    )


