# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
"""prefill_only duplex recv managers.

Two per-process singletons mirroring the two channels:

  * ``LwdCloudUpRecvManager`` (cloud side, UP channel): whole-prompt
    embeddings, **transport-chunked** — a request's prompt is sent as
    ``num_chunks`` independent messages (per-chunk seqno + per-chunk
    recv buffer + per-chunk readiness gate), mirroring the demo
    branch's recv manager.  Consumption is driven by the runner's fill
    loop via ``gather(req_id, start, num_tokens)``: only the chunks
    covering the requested token range are waited on (the cloud may
    start computing chunk 0 while later chunks are still in flight),
    a ``cat`` happens only when the range spans a chunk boundary, and
    fully consumed chunks are released one by one (memory shrinks with
    prefill progress).  The request stays ONE request in the cloud
    scheduler — chunking is a pure transport-layer concept.
  * ``LwdEdgeDownRecvManager`` (edge side, DOWN channel): one recv per
    request for the combined c2e packet (single message per request).

TP>1 (both sides symmetric): only TP rank 0 (the wire endpoint) posts
the HCCL P2P recv; every rank passes the readiness gate, then the
payload is distributed inside the TP group via ``broadcast(src=0)``.

Abort pairing: ``drop`` keeps posted recvs alive (a late send still
pairs, payload discarded) and advances the channel past the aborted
request's seqnos; notifications arriving AFTER a drop are skipped
without posting (no permanent seqno hole).
"""

from __future__ import annotations

import threading
import time

import torch
from vllm.logger import logger

from vllm_ascend import envs
from vllm_ascend.distributed.lwd_comm.future import LwdCommFuture
from vllm_ascend.distributed.lwd_comm.service import get_lwd_comm_service
from vllm_ascend.distributed.lwd_comm.types import LwdChannelType, LwdCommRequest
from vllm_ascend.worker.lwd_down_packet import (
    LwdDownPacket,
    lwd_packet_num_elements,
    lwd_request_fingerprint,
    unpack_lwd_down_packet,
)


def _tp_group_or_none():
    """TP group when TP>1, else None.  Imported lazily to stay usable in
    engine-side processes without initialized groups."""
    try:
        from vllm.distributed.parallel_state import get_tp_group

        group = get_tp_group()
        return group if group.world_size > 1 else None
    except Exception:
        return None


class LwdEmbedsTimeoutError(RuntimeError):
    """Raised when a readiness gate times out (fail the request instead
    of wedging the channel)."""


class _Entry:
    """One wire recv (one chunk).  ``future`` is None on non-endpoint TP
    ranks (their payload arrives via the TP-group broadcast)."""

    __slots__ = ("future", "num_elements", "seqno", "num_tokens", "dropped")

    def __init__(
        self,
        future: LwdCommFuture | None,
        num_elements: int,
        seqno: int,
        num_tokens: int,
    ) -> None:
        self.future = future
        self.num_elements = num_elements
        self.seqno = seqno
        self.num_tokens = num_tokens
        self.dropped = False


class _ReqChunks:
    """Per-request chunk table (UP direction)."""

    __slots__ = ("chunks", "sizes", "num_chunks", "consumed_upto", "dropped")

    def __init__(self, num_chunks: int) -> None:
        self.chunks: dict[int, _Entry] = {}   # live (not yet released) chunks
        # chunk_idx -> num_tokens, kept even after release so the
        # token-range geometry stays stable
        self.sizes: dict[int, int] = {}
        self.num_chunks = num_chunks
        # chunks [0, consumed_upto) have been fully consumed and released
        self.consumed_upto = 0
        self.dropped = False


class _LwdDuplexRecvManagerBase:
    """Shared bookkeeping: expect (post recv) / wait (readiness gate) /
    drop (pairing-safe discard)."""

    _CHANNEL: LwdChannelType

    def __init__(self, hidden_size: int, topk_k: int) -> None:
        self._hidden_size = hidden_size
        self._topk_k = topk_k
        self._reqs: dict[str, _ReqChunks] = {}
        # Requests dropped BEFORE their notification arrived: a late
        # expect_* for these must skip the seqno without posting a recv,
        # otherwise the never-sent payload leaves a permanent hole in the
        # channel FIFO.
        self._dropped_req_ids: set[str] = set()
        self._lock = threading.Lock()

    # -- TP endpoint helpers -------------------------------------------- #

    @property
    def _tp_group(self):
        return _tp_group_or_none()

    @property
    def _is_tp_endpoint(self) -> bool:
        """Only TP rank 0 talks to the HCCL P2P wire; other TP ranks
        receive payloads via the TP-group broadcast."""
        group = self._tp_group
        return group is None or group.rank_in_group == 0

    # -- posting -------------------------------------------------------- #

    def _post_recv(
        self,
        req_id: str,
        seqno: int,
        num_tokens: int,
        chunk_idx: int,
        num_chunks: int,
        num_elements: int | None = None,
    ) -> None:
        """Register/post one chunk's recv.  Idempotent per
        (req_id, chunk_idx); skip-without-post for dropped requests.

        ``num_elements`` defaults to ``num_tokens * hidden_size`` (UP
        embeds chunks); the DOWN packet passes its own exact size."""
        if num_elements is None:
            num_elements = num_tokens * self._hidden_size
        with self._lock:
            if req_id in self._dropped_req_ids:
                if self._is_tp_endpoint:
                    get_lwd_comm_service().skip_seqno(
                        self._CHANNEL, seqno, op="recv"
                    )
                return
            req = self._reqs.get(req_id)
            if req is None:
                req = _ReqChunks(num_chunks)
                self._reqs[req_id] = req
            elif req.num_chunks != num_chunks:
                raise ValueError(
                    f"{self._CHANNEL.value}: num_chunks changed for "
                    f"{req_id!r}: {req.num_chunks} -> {num_chunks}"
                )
            if chunk_idx in req.chunks:
                return  # duplicate notification
            if not 0 <= chunk_idx < num_chunks:
                raise ValueError(
                    f"{self._CHANNEL.value}: chunk_idx {chunk_idx} out of "
                    f"range [0, {num_chunks}) for {req_id!r}"
                )
            future = None
            if self._is_tp_endpoint:
                future = get_lwd_comm_service().submit_recv(
                    LwdCommRequest(
                        channel=self._CHANNEL,
                        op="recv",
                        num_elements=num_elements,
                        seqno=seqno,
                    )
                )
            req.chunks[chunk_idx] = _Entry(
                future, num_elements, seqno, num_tokens
            )
            req.sizes[chunk_idx] = num_tokens

    # -- waiting --------------------------------------------------------- #

    def _wait_chunk(self, req: _ReqChunks, chunk_idx: int, deadline: float) -> torch.Tensor:
        """Readiness gate for one chunk; returns its [n, H] buffer."""
        entry = req.chunks.get(chunk_idx)
        if entry is None:
            raise KeyError(
                f"{self._CHANNEL.value}: chunk {chunk_idx} not registered"
            )
        if req.dropped or entry.dropped:
            raise LwdEmbedsTimeoutError(f"{self._CHANNEL.value}: dropped")
        group = self._tp_group
        if group is None:
            return self._wait_wire(entry, deadline)
        if self._is_tp_endpoint:
            tensor = self._wait_wire(entry, deadline)
        else:
            tensor = torch.empty(
                entry.num_elements, dtype=torch.bfloat16, device="npu"
            )
        group.broadcast(tensor, src=0)
        return tensor

    def _wait_wire(self, entry: _Entry, deadline: float) -> torch.Tensor:
        assert entry.future is not None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LwdEmbedsTimeoutError(
                f"{self._CHANNEL.value}: recv timed out"
            )
        try:
            result = entry.future.wait(timeout=remaining)
        except TimeoutError as exc:
            raise LwdEmbedsTimeoutError(
                f"{self._CHANNEL.value}: recv timed out after "
                f"{envs.VLLM_ASCEND_LWD_EMBEDS_TIMEOUT_S}s"
            ) from exc
        assert result.tensor is not None
        # Order the consumer's current stream after the channel-stream
        # completion event (device-side ordering for zero-copy reads).
        entry.future.wait_for_comm()
        return result.tensor

    # -- drop / abort ----------------------------------------------------- #

    def drop(self, req_id: str) -> None:
        """Abort: keep posted recvs alive (a late send still pairs, its
        payload is discarded), skip the request's seqnos on the wire
        (endpoint rank only), and record the request so LATE
        notifications are skipped without posting (no permanent hole)."""
        with self._lock:
            self._dropped_req_ids.add(req_id)
            req = self._reqs.get(req_id)
            if req is None:
                return
            req.dropped = True
            seqnos = [e.seqno for e in req.chunks.values()]
            for entry in req.chunks.values():
                entry.dropped = True
        if self._is_tp_endpoint:
            for seqno in seqnos:
                get_lwd_comm_service().skip_seqno(self._CHANNEL, seqno, op="recv")

    def is_dropped(self, req_id: str) -> bool:
        with self._lock:
            if req_id in self._dropped_req_ids:
                return True
            req = self._reqs.get(req_id)
            return bool(req and req.dropped)


class LwdCloudUpRecvManager(_LwdDuplexRecvManagerBase):
    """Cloud side: chunked whole-prompt embeddings on the UP channel."""

    _CHANNEL = LwdChannelType.UP

    def expect_embeds(
        self,
        req_id: str,
        seqno: int,
        num_tokens: int,
        chunk_idx: int = 0,
        num_chunks: int = 1,
    ) -> None:
        """Called on the per-chunk control-plane notification
        ``(req_id, chunk_idx, num_tokens, seqno)``.  Idempotent per
        chunk; the irecv is posted immediately (early), so the transfer
        overlaps cloud-side compute of earlier chunks."""
        self._post_recv(req_id, seqno, num_tokens, chunk_idx, num_chunks)

    def gather(
        self, req_id: str, start_token: int, num_tokens: int
    ) -> torch.Tensor:
        """Return embeds for ``[start_token, start_token + num_tokens)``.

        Driven by the runner's fill loop at ``num_computed_tokens``
        offsets.  Waits only on the chunks covering the range (earlier
        chunks are already consumed, later ones may still be in flight);
        cats only when the range spans a chunk boundary (one D2D copy).
        """
        if num_tokens <= 0:
            raise ValueError(f"empty gather range for {req_id!r}")
        deadline = time.monotonic() + envs.VLLM_ASCEND_LWD_EMBEDS_TIMEOUT_S
        with self._lock:
            req = self._reqs.get(req_id)
            if req is None:
                raise KeyError(f"lwd_up: no chunks registered for {req_id!r}")
            # chunk geometry from the PERMANENT size table (stable even
            # after earlier chunks were released)
            sizes = dict(req.sizes)
        # locate covering chunks
        end_token = start_token + num_tokens
        offset = 0
        covering: list[tuple[int, int, int]] = []  # (chunk_idx, lo, hi)
        for idx in sorted(sizes):
            size = sizes[idx]
            chunk_lo, chunk_hi = offset, offset + size
            if chunk_hi > start_token and chunk_lo < end_token:
                covering.append(
                    (idx, max(start_token, chunk_lo) - chunk_lo,
                     min(end_token, chunk_hi) - chunk_lo)
                )
            offset = chunk_hi
        if not covering or offset < end_token:
            raise KeyError(
                f"lwd_up: range [{start_token}, {end_token}) not covered by "
                f"registered chunks of {req_id!r}"
            )
        parts = []
        with self._lock:
            req = self._reqs[req_id]
            chunk_entries = dict(req.chunks)
        for idx, lo, hi in covering:
            if idx not in chunk_entries:
                raise KeyError(
                    f"lwd_up: chunk {idx} of {req_id!r} not registered yet"
                )
            buf = self._wait_chunk(req, idx, deadline)
            parts.append(buf.view(-1, self._hidden_size)[lo:hi])
        return parts[0] if len(parts) == 1 else torch.cat(parts, dim=0)

    def release_upto(self, req_id: str, chunk_upto: int) -> None:
        """Release chunks [0, chunk_upto) — fully consumed.  Buffers are
        referenced only by the chunk table, so dropping the reference
        frees them (the channel already reaped the futures)."""
        with self._lock:
            req = self._reqs.get(req_id)
            if req is None:
                return
            for idx in list(req.chunks):
                if idx < chunk_upto:
                    del req.chunks[idx]
            req.consumed_upto = max(req.consumed_upto, chunk_upto)

    def wait_embeds(self, req_id: str) -> torch.Tensor:
        """Convenience for the degenerate single-chunk case: the whole
        prompt in one tensor."""
        with self._lock:
            req = self._reqs.get(req_id)
            if req is None or not req.sizes:
                raise KeyError(f"lwd_up: no chunks registered for {req_id!r}")
            total = sum(req.sizes.values())
        return self.gather(req_id, 0, total)

    def has_pending(self, req_id: str) -> bool:
        with self._lock:
            return req_id in self._reqs

    def pop_request(self, req_id: str) -> None:
        """Request finished/consumed: drop all bookkeeping."""
        with self._lock:
            self._reqs.pop(req_id, None)


class LwdEdgeDownRecvManager(_LwdDuplexRecvManagerBase):
    """Edge side: combined c2e packets on the DOWN channel (single
    message per request — the degenerate one-chunk case)."""

    _CHANNEL = LwdChannelType.DOWN

    def expect_packet(self, req_id: str, seqno: int, num_rows: int) -> None:
        """Called on the control-plane notification carrying the packet's
        row count R (HCCL needs exact numel)."""
        self._post_recv(
            req_id,
            seqno,
            num_rows,  # num_tokens bookkeeping only
            0,
            1,
            num_elements=lwd_packet_num_elements(
                num_rows, self._hidden_size, self._topk_k
            ),
        )

    def wait_packet(self, req_id: str, *, max_rows: int) -> LwdDownPacket:
        """Readiness gate + parse + validate.  ``max_rows`` =
        num_speculative_tokens + 1 (1 when spec is off).  The header
        fingerprint is verified against ``req_id`` — a mismatch means
        cross-request mixup and fails closed."""
        deadline = time.monotonic() + envs.VLLM_ASCEND_LWD_EMBEDS_TIMEOUT_S
        buf = self._wait_chunk(self._get_req(req_id), 0, deadline)
        return unpack_lwd_down_packet(
            buf,
            expected_fingerprint=lwd_request_fingerprint(req_id),
            max_rows=max_rows,
            max_topk_k=self._topk_k,
            hidden_size=self._hidden_size,
        )

    def _get_req(self, req_id: str) -> _ReqChunks:
        with self._lock:
            req = self._reqs.get(req_id)
        if req is None:
            raise KeyError(f"lwd_down: no packet registered for {req_id!r}")
        return req


_UP_MANAGER: LwdCloudUpRecvManager | None = None
_DOWN_MANAGER: LwdEdgeDownRecvManager | None = None
_MANAGER_LOCK = threading.Lock()


def init_lwd_recv_managers(hidden_size: int, topk_k: int) -> None:
    """Create both managers (idempotent).  Each process uses only the
    one matching its role, but creating both keeps init trivial."""
    global _UP_MANAGER, _DOWN_MANAGER
    with _MANAGER_LOCK:
        if _UP_MANAGER is None:
            _UP_MANAGER = LwdCloudUpRecvManager(hidden_size, topk_k)
            _DOWN_MANAGER = LwdEdgeDownRecvManager(hidden_size, topk_k)
            logger.info(
                "[lwd-recv] managers initialized (H=%d, K=%d)",
                hidden_size, topk_k,
            )


def get_lwd_up_recv_manager() -> LwdCloudUpRecvManager:
    assert _UP_MANAGER is not None, "init_lwd_recv_managers() first"
    return _UP_MANAGER


def get_lwd_down_recv_manager() -> LwdEdgeDownRecvManager:
    assert _DOWN_MANAGER is not None, "init_lwd_recv_managers() first"
    return _DOWN_MANAGER
