# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""prefill_only c2e (DOWN) batch-packet wire format (v3: rank replay,
per-step batching).

ONE packet per cloud step per channel — not one packet per request.
The packet carries every LWD request of that step's batch:

    ① final hidden states (post-norm, lm_head input)   [R_tot, H] bf16
    ② sampled ranks (the "which-th largest" replay key) [R_tot] int32
    ③ per-request row counts + num_accepted            request table

Replay contract: the sampled token is NOT on the wire.  The edge
recomputes logits locally (packet hidden -> edge lm_head) and picks the
token with exactly ``rank`` vocabulary entries above it (argsort
descending, index ``rank``).  Rank is invariant under any monotone
logit transform (temperature), so the edge needs neither the cloud's
temperature nor its RNG seed.  It is NOT invariant under reordering
logits processors (penalties, grammar bitmasks, logit bias) — replay
assumes those are absent (or applied identically on the edge).

Layout (all sizes in bf16 elements; int32 fields are bit-packed into
bf16 slot pairs):

    header: 32 bf16 slots = 16 x int32:
        [0] magic (LWD_DOWN_MAGIC)
        [1] version (3)
        [2] M      requests in this packet (>= 1)
        [3] R_tot  total rows (>= M; spec requests contribute accepted+1)
        [4]        reserved (0)
        [5] H      hidden size
        [6]        reserved (0)
        [7] flags  (0, reserved)
        [8-15] reserved (0)
    request table: M entries x 4 int32 (= 8 bf16 slots each):
        [fp_lo, fp_hi, R_i, accepted_i]
        — fp = blake2b(request_id) 64-bit fingerprint; the edge demuxes
        rows to its live requests by matching fingerprints.
    payload: R_tot rows x S, S = H + 2 bf16 elements:
        [0   : H)     final hidden    bf16 x H
        [H   : H+2)   sampled_rank    int32 x 1 bit-packed
        Rows are grouped by request in table order; within a request,
        verify positions in chain order (accepted prefix + bonus row).

The on-the-wire size VARIES per step (M and R_tot vary); the receiver
learns the exact numel from the control-plane notification preceding
every send (HCCL P2P requires matching numel on both ends).  There is
NO FIN packet — request finish/abort is signaled by the control plane.

Fidelity note: the cloud computes ``rank`` on its fp32 sampling logits;
the edge re-ranks on bf16-hidden-derived logits.  Near-ties (the rank-th
and (rank+1)-th logits closer than the precision gap) may resolve to an
adjacent token on the edge — "near-fidelity" replay by design.  Greedy
traffic (rank 0 with a top-2 margin) is exact in practice.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import torch

LWD_DOWN_MAGIC = 0x70C2E002  # "POC2E002"
LWD_DOWN_VERSION = 3

LWD_HEADER_I32 = 16              # int32 fields
LWD_HEADER_BF16 = LWD_HEADER_I32 * 2  # 32 bf16 slots

# Request table entry: (fp_lo, fp_hi, num_rows, num_accepted).
LWD_REQ_TABLE_I32 = 4
LWD_REQ_TABLE_BF16 = LWD_REQ_TABLE_I32 * 2

# Per-row rank field width in bf16 slots (one int32).
LWD_RANK_BF16 = 2


def lwd_row_stride(hidden_size: int) -> int:
    """Per-row stride S in bf16 elements: H + 2 (rank int32 -> 2 bf16
    slots)."""
    return hidden_size + LWD_RANK_BF16


def lwd_batch_packet_num_elements(
    num_reqs: int, num_rows: int, hidden_size: int
) -> int:
    """Total bf16 element count of a batch packet (recv-side buffer
    sizing — the control-plane notification carries this number)."""
    return (
        LWD_HEADER_BF16
        + num_reqs * LWD_REQ_TABLE_BF16
        + num_rows * lwd_row_stride(hidden_size)
    )


def lwd_request_fingerprint(request_id: str) -> int:
    """64-bit fingerprint for cross-request-mixup detection and for the
    edge-side demux (request_id is not on the wire)."""
    digest = hashlib.blake2b(request_id.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "little")


@dataclass
class LwdDownEntry:
    """One request's slice of a batch packet (views into the recv
    buffer except where dtype re-interpretation forces a copy)."""

    fingerprint: int
    num_rows: int
    num_accepted: int
    hidden: torch.Tensor   # [R_i, H] bf16
    ranks: torch.Tensor    # [R_i] int32


@dataclass
class LwdDownBatchPacket:
    """Decoded view of one step's batch packet."""

    num_reqs: int
    num_rows: int
    hidden_size: int
    flags: int = 0
    entries: list[LwdDownEntry] = field(default_factory=list)


def _u32(x: int) -> int:
    """Unsigned 32-bit -> signed int32 (torch has no uint32)."""
    x &= 0xFFFFFFFF
    return x - (1 << 32) if x >= (1 << 31) else x


def pack_lwd_down_batch_packet(
    *,
    entries: list[tuple[str, torch.Tensor, torch.Tensor, int]],
) -> torch.Tensor:
    """Assemble one step's flat bf16 wire tensor (device-side, no D2H).

    ``entries``: ``(request_id, hidden [R_i, H] bf16, ranks [R_i] int32,
    num_accepted)`` in batch order.  Rows are laid out in the same
    order, so the edge demuxes purely by the request table.
    """
    M = len(entries)
    assert M >= 1, "batch packet needs at least one request"
    H = entries[0][1].shape[1]
    device = entries[0][1].device
    R_tot = 0
    table: list[int] = []
    for req_id, hidden, ranks, accepted in entries:
        R_i = hidden.shape[0]
        assert hidden.dim() == 2 and hidden.dtype == torch.bfloat16
        assert hidden.shape[1] == H, "mixed hidden sizes in one packet"
        assert ranks.shape == (R_i,) and ranks.dtype == torch.int32
        fp = lwd_request_fingerprint(req_id)
        table.extend([_u32(fp), _u32(fp >> 32), R_i, accepted])
        R_tot += R_i

    buf = torch.zeros(
        lwd_batch_packet_num_elements(M, R_tot, H),
        dtype=torch.bfloat16,
        device=device,
    )

    # header + request table (one H2D per step)
    header = torch.tensor(
        [
            LWD_DOWN_MAGIC,
            LWD_DOWN_VERSION,
            M,
            R_tot,
            0,  # reserved
            H,
            0,  # reserved
            0,  # flags
            0, 0, 0, 0, 0, 0, 0, 0,
        ],
        dtype=torch.int32,
    )
    meta = torch.cat([header, torch.tensor(table, dtype=torch.int32)])
    buf[: LWD_HEADER_BF16 + M * LWD_REQ_TABLE_BF16].view(torch.int32).copy_(
        meta.to(device=device)
    )

    # payload: R_tot rows x S
    S = lwd_row_stride(H)
    rows = buf[LWD_HEADER_BF16 + M * LWD_REQ_TABLE_BF16:].view(R_tot, S)
    rows[:, :H].copy_(torch.cat([e[1] for e in entries], dim=0))
    rows[:, H:H + LWD_RANK_BF16].copy_(
        torch.cat([e[2] for e in entries], dim=0).unsqueeze(1).view(torch.bfloat16)
    )
    return buf


def unpack_lwd_down_batch_packet(
    buf: torch.Tensor,
    *,
    hidden_size: int | None = None,
    max_reqs: int | None = None,
    max_rows: int | None = None,
) -> LwdDownBatchPacket:
    """Parse + validate a received batch packet.  Any validation failure
    raises before anything touches the replay path (anti cross-request
    mixup / malformed-payload defense)."""
    assert buf.dtype == torch.bfloat16 and buf.dim() == 1
    if buf.numel() < LWD_HEADER_BF16:
        raise ValueError(f"c2e packet malformed length: {buf.numel()}")
    hdr = buf[:LWD_HEADER_BF16].view(torch.int32).cpu()
    magic, version, M, R_tot, _r0, H, _r1, flags = (int(x) for x in hdr[:8])

    if magic != LWD_DOWN_MAGIC:
        raise ValueError(f"c2e packet bad magic: {magic:#x}")
    if version != LWD_DOWN_VERSION:
        raise ValueError(f"c2e packet unsupported version: {version}")
    if M < 1:
        raise ValueError(f"c2e packet empty request table: M={M}")
    if R_tot < M:
        raise ValueError(
            f"c2e packet row count under request count: R_tot={R_tot} < M={M}"
        )
    if hidden_size is not None and H != hidden_size:
        raise ValueError(f"c2e packet H mismatch: {H} != {hidden_size}")
    if max_reqs is not None and M > max_reqs:
        raise ValueError(f"c2e packet M over limit: {M} > {max_reqs}")
    if max_rows is not None and R_tot > max_rows:
        raise ValueError(f"c2e packet R_tot over limit: {R_tot} > {max_rows}")
    expected = lwd_batch_packet_num_elements(M, R_tot, H)
    if buf.numel() < expected:
        raise ValueError(
            f"c2e packet truncated: {buf.numel()} < {expected} elements"
        )

    table = (
        buf[LWD_HEADER_BF16:LWD_HEADER_BF16 + M * LWD_REQ_TABLE_BF16]
        .view(torch.int32)
        .cpu()
        .view(M, LWD_REQ_TABLE_I32)
    )
    S = lwd_row_stride(H)
    rows = buf[
        LWD_HEADER_BF16 + M * LWD_REQ_TABLE_BF16:
        LWD_HEADER_BF16 + M * LWD_REQ_TABLE_BF16 + R_tot * S
    ].view(R_tot, S)
    hidden_all = rows[:, :H]
    # NB: copy into a fresh truly-contiguous buffer before the dtype
    # re-interpretation — .contiguous() is a no-op for R_tot == 1
    # (size-1 dim strides are ignored by is_contiguous) and would
    # corrupt the view.
    ranks_bf16 = torch.empty(R_tot, LWD_RANK_BF16, dtype=torch.bfloat16,
                             device=buf.device)
    ranks_bf16.copy_(rows[:, H:H + LWD_RANK_BF16])
    ranks_all = ranks_bf16.view(torch.int32).squeeze(1)

    entries: list[LwdDownEntry] = []
    offset = 0
    row_sum = 0
    for j in range(M):
        t = table[j]
        fp = (int(t[0]) & 0xFFFFFFFF) | ((int(t[1]) & 0xFFFFFFFF) << 32)
        R_i, accepted = int(t[2]), int(t[3])
        if R_i < 1:
            raise ValueError(
                f"c2e packet table entry {j} has zero rows"
            )
        entries.append(
            LwdDownEntry(
                fingerprint=fp,
                num_rows=R_i,
                num_accepted=accepted,
                hidden=hidden_all[offset:offset + R_i],
                ranks=ranks_all[offset:offset + R_i],
            )
        )
        offset += R_i
        row_sum += R_i
    if row_sum != R_tot:
        raise ValueError(
            f"c2e packet table rows {row_sum} != header R_tot {R_tot}"
        )
    return LwdDownBatchPacket(
        num_reqs=M,
        num_rows=R_tot,
        hidden_size=H,
        flags=flags,
        entries=entries,
    )
