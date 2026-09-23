# Copyright (c) 2026 Huawei Technologies Co., Ltd. All Rights Reserved.
"""Device-independent, deterministic LWD data-plane group plan.

Connection keys are internal identifiers, not a ZMQ envelope format. The
control/scheduler adapter must supply the same edge/cloud/DP IDs on both ends.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vllm.config.lwd_topology import LwdTopology


@dataclass(frozen=True, order=True)
class LwdConnectionKey:
    edge_id: int
    cloud_id: int
    dp_idx: int

    def __post_init__(self) -> None:
        for name in ("edge_id", "cloud_id", "dp_idx"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"[LWD] {name} must be a non-negative integer")


@dataclass(frozen=True)
class LwdWireConnection:
    key: LwdConnectionKey
    edge_rank: int
    cloud_ranks: tuple[int, ...]

    @property
    def cloud_leader_rank(self) -> int:
        return self.cloud_ranks[0]

    @property
    def endpoint_ranks(self) -> tuple[int, int]:
        return self.edge_rank, self.cloud_leader_rank

    def peer_for(self, rank: int) -> int:
        if rank == self.edge_rank:
            return self.cloud_leader_rank
        if rank == self.cloud_leader_rank:
            return self.edge_rank
        raise ValueError(f"[LWD] rank={rank} is not a P2P endpoint of {self.key}")

    def includes(self, rank: int) -> bool:
        return rank == self.edge_rank or rank in self.cloud_ranks


def build_lwd_wire_plan(topology: LwdTopology) -> tuple[LwdWireConnection, ...]:
    """Expand ALL links, not just local links, in a global creation order.

    Identical endpoint pairs on distinct logical links deliberately remain
    distinct entries: they must not share a communicator or a FIFO.
    Cloud broadcast domains, in contrast, are shared by all links to that DP
    and reuse its framework TP group (validated separately at runtime).
    """
    topology.validate_layout()
    connections = []
    for link in sorted(topology.instance_links, key=lambda item: (item.edge, item.cloud)):
        edge = topology.instance("edge", link.edge)
        for dp in sorted(edge.dp, key=lambda item: item.dp_idx):
            if len(dp.ranks) != 1:
                raise ValueError(
                    "[LWD] A wire edge endpoint must have exactly one rank; "
                    f"edge={edge.id} dp={dp.dp_idx} ranks={dp.ranks}"
                )
            cloud_dp = topology.dp("cloud", link.cloud, dp.dp_idx)
            connections.append(
                LwdWireConnection(
                    LwdConnectionKey(link.edge, link.cloud, dp.dp_idx),
                    dp.ranks[0],
                    cloud_dp.ranks,
                )
            )
    return tuple(connections)


def bind_lwd_worker_connections(config, rank: int) -> dict[tuple[int, int, int], LwdConnectionKey]:
    """Bind logical identity once, before accepting scheduled work.

    This runtime binding is restricted to single-instance, single-DP use.
    The pure topology plan above remains available for configuration checks.
    """
    effective = config.lwd_config
    effective.topology.validate_single_dp_runtime()
    dp_idx = effective.dp.dp_idx
    bindings = {}
    for item in effective.connections:
        if item.dp_idx != dp_idx:
            continue
        ranks = item.edge.ranks if effective.is_edge else item.cloud.ranks
        if rank not in ranks:
            raise ValueError("[LWD] Worker rank does not belong to its logical DP")
        key = LwdConnectionKey(item.edge_id, item.cloud_id, item.dp_idx)
        bindings[(key.edge_id, key.cloud_id, key.dp_idx)] = key
    if not bindings:
        raise ValueError("[LWD] Worker has no connection for its instance/DP")
    return bindings


def resolve_lwd_batch_connection(batch, bindings) -> LwdConnectionKey:
    """Do not fall back to physical rank when metadata loses its identity."""
    key = batch.connection_key
    if (
        not isinstance(key, tuple)
        or len(key) != 3
        or any(type(value) is not int or value < 0 for value in key)
        or key not in bindings
    ):
        raise ValueError(f"[LWD] Batch connection {key!r} is not bound to this worker")
    return bindings[key]


def select_lwd_wire_connection(
    plan: tuple[LwdWireConnection, ...],
    rank: int,
    key: LwdConnectionKey | None = None,
) -> LwdWireConnection:
    """Allow an omitted key only when this rank has exactly one connection."""
    if key is not None and not isinstance(key, LwdConnectionKey):
        raise ValueError("[LWD] connection_key must be a LwdConnectionKey")
    candidates = [item for item in plan if item.includes(rank) and (key is None or item.key == key)]
    if len(candidates) != 1:
        raise ValueError(
            f"[LWD] rank={rank} connection_key={key}: expected one connection, "
            f"found {len(candidates)}; supply an explicit edge/cloud/DP key "
            "belonging to this rank"
        )
    return candidates[0]
