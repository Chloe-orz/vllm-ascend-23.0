# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
# Edge-cloud multi-instance static KV partition (2E1C scenario).
#
# TEMPORARY SCAFFOLDING: this module is the single place that knows about the
# static per-edge KV block partition.  When the cloud-side self-managed KV
# (CloudKVStore) lands, this whole module is deleted and the pool becomes
# shared; do NOT spread partition knowledge anywhere else.
"""Static KV block partition across edges (temporary 2E1C scheme)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KvPartition:
    """Static KV block partition across edges.

    The cloud physically allocates ``num_blocks_total`` blocks; each edge's
    scheduler manages only its own half-open range ``[start, end)`` as if it
    were the whole pool.  Block ids produced by an edge's KVCacheManager stay
    edge-local; the cloud adds the edge's offset when materializing physical
    block tables (single translation point in the inbound adapter).
    """

    num_blocks_total: int
    split: dict[int, tuple[int, int]]  # edge_id -> (start, end)

    def __post_init__(self) -> None:
        prev_end = 0
        for edge_id in sorted(self.split):
            start, end = self.split[edge_id]
            if start != prev_end:
                raise ValueError(
                    f"kv_partition ranges must be contiguous and ordered: "
                    f"edge {edge_id} starts at {start}, expected {prev_end}"
                )
            if end <= start:
                raise ValueError(
                    f"kv_partition edge {edge_id}: empty range "
                    f"[{start}, {end})"
                )
            prev_end = end
        if prev_end != self.num_blocks_total:
            raise ValueError(
                f"kv_partition must cover exactly num_blocks_total="
                f"{self.num_blocks_total}, got coverage end={prev_end}"
            )

    @classmethod
    def from_config(cls, cfg: dict) -> "KvPartition":
        return cls(
            num_blocks_total=int(cfg["num_blocks_total"]),
            split={int(k): (int(v[0]), int(v[1]))
                   for k, v in cfg["split"].items()},
        )

    @classmethod
    def from_ratios(cls, ratios: dict[int, float],
                    num_blocks_total: int) -> "KvPartition":
        """Materialize absolute ranges from per-edge ratios.

        The registry YAML carries *ratios* (the cloud's real num_blocks is
        only known after memory profiling at startup); this resolves them
        into absolute block ranges once the total is known.  Ranges are
        contiguous in ascending edge_id order and always cover
        ``[0, num_blocks_total)`` exactly (last edge takes the remainder).
        """
        total = 0.0
        for r in ratios.values():
            if r <= 0:
                raise ValueError(f"kv partition ratio must be > 0, got {r}")
            total += r
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"kv partition ratios must sum to 1.0, got {total}")
        split: dict[int, tuple[int, int]] = {}
        start = 0
        ids = sorted(ratios)
        for i, edge_id in enumerate(ids):
            if i == len(ids) - 1:
                end = num_blocks_total  # last edge takes the remainder
            else:
                end = start + int(num_blocks_total * ratios[edge_id])
            split[edge_id] = (start, end)
            start = end
        return cls(num_blocks_total=num_blocks_total, split=split)

    def range_of(self, edge_id: int) -> tuple[int, int]:
        """Return (offset, num_blocks) for the given edge."""
        start, end = self.split[edge_id]
        return start, end - start

    def num_blocks_of(self, edge_id: int) -> int:
        """Edge-local pool size (what the edge's KVCacheManager sees)."""
        return self.range_of(edge_id)[1]

    def to_physical(self, edge_id: int, local_block_ids: list[int]) -> list[int]:
        """Translate edge-local block ids to cloud-physical block ids."""
        offset, num_blocks = self.range_of(edge_id)
        for b in local_block_ids:
            if b < 0 or b >= num_blocks:
                raise ValueError(
                    f"local block id {b} out of range [0, {num_blocks}) "
                    f"for edge {edge_id}"
                )
        return [offset + b for b in local_block_ids]
