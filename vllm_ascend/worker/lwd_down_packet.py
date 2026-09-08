# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""prefill_only c2e (DOWN) combined-packet wire format (v2: rank replay).

One flat bf16 tensor per request per step, carrying that step's:

    ① final hidden states (post-norm, lm_head input)   [R, H] bf16
    ② sampled rank (the "which-th largest" replay key) [R] int32
    ③ num_accepted_tokens (draft hits of that step)    scalar int32

Replay contract: the sampled token is NOT on the wire.  The edge
recomputes logits locally (packet hidden -> edge lm_head) and picks the
token with exactly ``rank`` vocabulary entries above it (argsort
descending, index ``rank``).  Rank is invariant under any monotone
logit transform (temperature), so the edge needs neither the cloud's
temperature nor its RNG seed.  It is NOT invariant under reordering
logits processors (penalties, grammar bitmasks, logit bias) — replay
assumes those are absent (or applied identically on the edge).

Layout (all sizes in bf16 elements; the int32 rank is bit-packed into a
bf16 slot pair):

    header: 32 bf16 slots = 16 x int32:
        [0] magic (LWD_DOWN_MAGIC)
        [1] version (2)
        [2] N      prompt tokens
        [3] R      rows (== num_accepted + 1; 1 for non-spec)
        [4]        reserved (0; was topk width K in v1)
        [5] H      hidden size
        [6] num_accepted
        [7] flags  (0, reserved)
        [8-9]  req_fingerprint (lo/hi int32 of a 64-bit id hash)
        [10-15] reserved (0)
    payload: R rows x S, S = H + 2 bf16 elements (constant for any
        spec config):
        [0   : H)     final hidden    bf16 x H
        [H   : H+2)   sampled_rank    int32 x 1 bit-packed

Both sides derive S from config (H); R comes from the header — so the
parser never needs the spec k.  The on-the-wire size is FIXED at
R_max = num_speculative_tokens + 1 rows (streaming mode), so the edge
can pre-post a recv ring without per-step size knowledge.

Fidelity note: the cloud computes ``rank`` on its fp32 sampling logits;
the edge re-ranks on bf16-hidden-derived logits.  Near-ties (the rank-th
and (rank+1)-th logits closer than the precision gap) may resolve to an
adjacent token on the edge — "near-fidelity" replay by design.  Greedy
traffic (rank 0 with a top-2 margin) is exact in practice.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import torch

LWD_DOWN_MAGIC = 0x70C2E002  # "POC2E002"
LWD_DOWN_VERSION = 2

LWD_HEADER_I32 = 16              # int32 fields
LWD_HEADER_BF16 = LWD_HEADER_I32 * 2  # 32 bf16 slots

# flags: currently all zero (reserved).  There is NO FIN packet —
# request finish/abort is signaled by the control plane (v2.6).

# Per-row rank field width in bf16 slots (one int32).
LWD_RANK_BF16 = 2


def lwd_row_stride(hidden_size: int) -> int:
    """Per-row stride S in bf16 elements: H + 2 (rank int32 -> 2 bf16
    slots)."""
    return hidden_size + LWD_RANK_BF16


def lwd_packet_num_elements(num_rows: int, hidden_size: int) -> int:
    """Total bf16 element count of a packet carrying ``num_rows`` rows."""
    return LWD_HEADER_BF16 + num_rows * lwd_row_stride(hidden_size)


def lwd_down_wire_num_elements(hidden_size: int, max_rows: int) -> int:
    """FIXED on-the-wire packet size (streaming mode): every DOWN packet
    occupies exactly this many bf16 elements (R_max rows, padding
    unused), so the receiver can pre-post a ring of recvs without
    per-step size knowledge.  R_max = num_speculative_tokens + 1 (1 when
    spec is off)."""
    return lwd_packet_num_elements(max_rows, hidden_size)


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
    hidden_size: int
    num_accepted: int
    fingerprint: int
    flags: int = 0
    hidden: torch.Tensor | None = None   # [R, H] bf16
    ranks: torch.Tensor | None = None    # [R] int32


def _u32(x: int) -> int:
    """Unsigned 32-bit -> signed int32 (torch has no uint32)."""
    x &= 0xFFFFFFFF
    return x - (1 << 32) if x >= (1 << 31) else x


def pack_lwd_down_packet(
    *,
    hidden: torch.Tensor,        # [R, H] bf16
    ranks: torch.Tensor,         # [R] int32
    num_prompt_tokens: int,
    num_accepted: int,
    request_id: str,
    flags: int = 0,
    wire_num_elements: int | None = None,
) -> torch.Tensor:
    """Assemble the flat bf16 wire tensor (device-side, no D2H).

    Streaming mode: pass ``wire_num_elements`` =
    ``lwd_down_wire_num_elements(H, R_max)`` so every packet on the wire
    has the SAME fixed size (padded) and the receiver can pre-post a
    recv ring without per-step size knowledge.
    """
    assert hidden.dim() == 2 and hidden.dtype == torch.bfloat16
    R, H = hidden.shape
    assert ranks.shape == (R,) and ranks.dtype == torch.int32

    total = lwd_packet_num_elements(R, H)
    if wire_num_elements is not None:
        assert wire_num_elements >= total, (
            wire_num_elements, total)
        total = wire_num_elements
    buf = torch.zeros(total, dtype=torch.bfloat16, device=hidden.device)

    # header (H2D once per packet)
    fp = lwd_request_fingerprint(request_id)
    header = torch.tensor(
        [
            LWD_DOWN_MAGIC,
            LWD_DOWN_VERSION,
            num_prompt_tokens,
            R,
            0,  # reserved (v1: topk width K)
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

    # payload: R rows x S (the wire buffer may be padded to R_max rows)
    S = lwd_row_stride(H)
    rows = buf[LWD_HEADER_BF16:LWD_HEADER_BF16 + R * S].view(R, S)
    rows[:, :H].copy_(hidden)
    rows[:, H:H + LWD_RANK_BF16].copy_(ranks.unsqueeze(1).view(torch.bfloat16))
    return buf


def unpack_lwd_down_packet(
    buf: torch.Tensor,
    *,
    expected_fingerprint: int | None = None,
    max_rows: int | None = None,
    hidden_size: int | None = None,
) -> LwdDownPacket:
    """Parse + validate a received packet.  Any validation failure raises
    before anything touches the replay path (anti cross-request
    mixup / malformed-payload defense)."""
    assert buf.dtype == torch.bfloat16 and buf.dim() == 1
    if buf.numel() < LWD_HEADER_BF16:
        raise ValueError(f"c2e packet malformed length: {buf.numel()}")
    hdr = buf[:LWD_HEADER_BF16].view(torch.int32).cpu()
    magic, version, N, R, _reserved, H, accepted, flags = (
        int(x) for x in hdr[:8])
    fp = (int(hdr[8]) & 0xFFFFFFFF) | ((int(hdr[9]) & 0xFFFFFFFF) << 32)

    if magic != LWD_DOWN_MAGIC:
        raise ValueError(f"c2e packet bad magic: {magic:#x}")
    if version != LWD_DOWN_VERSION:
        raise ValueError(f"c2e packet unsupported version: {version}")
    if R < 1:
        raise ValueError(f"c2e packet empty payload: R={R}")
    if hidden_size is not None and H != hidden_size:
        raise ValueError(f"c2e packet H mismatch: {H} != {hidden_size}")
    if max_rows is not None and R > max_rows:
        raise ValueError(f"c2e packet R over limit: {R} > {max_rows}")
    if expected_fingerprint is not None and fp != expected_fingerprint:
        raise ValueError(
            "c2e packet fingerprint mismatch: cross-request mixup guard"
        )
    expected = lwd_packet_num_elements(R, H)
    if buf.numel() < expected:
        raise ValueError(
            f"c2e packet truncated: {buf.numel()} < {expected} elements"
        )

    S = lwd_row_stride(H)
    rows = buf[LWD_HEADER_BF16:LWD_HEADER_BF16 + R * S].view(R, S)
    hidden = rows[:, :H]
    # NB: copy into a fresh truly-contiguous buffer before the dtype
    # re-interpretation — .contiguous() is a no-op for R == 1 (size-1
    # dim strides are ignored by is_contiguous) and would corrupt the
    # view.
    ranks_bf16 = torch.empty(R, LWD_RANK_BF16, dtype=torch.bfloat16,
                             device=buf.device)
    ranks_bf16.copy_(rows[:, H:H + LWD_RANK_BF16])
    ranks = ranks_bf16.view(torch.int32).squeeze(1)
    return LwdDownPacket(
        num_prompt_tokens=N,
        num_rows=R,
        hidden_size=H,
        num_accepted=accepted,
        fingerprint=fp,
        flags=flags,
        hidden=hidden,
        ranks=ranks,
    )
