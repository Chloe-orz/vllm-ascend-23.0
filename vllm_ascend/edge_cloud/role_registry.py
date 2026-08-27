# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
# Edge-cloud multi-instance role registry (2E1C scenario).
#
# The registry is the single source of truth shared by all instances at
# startup: who is edge / cloud, their addresses, ZMQ port planning and the
# static KV partition.  Loaded once per process from a YAML file mounted
# identically on every instance.
"""Static role registry for multi-edge edge-cloud deployment (2E1C)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import yaml

from vllm.logger import init_logger
from vllm_ascend.edge_cloud.kv_partition import KvPartition

logger = init_logger(__name__)


@dataclass(frozen=True)
class PeerInfo:
    """One instance's entry in the registry.

    ``ranks`` are the instance's **global ranks** in the torch.distributed
    world (HCCL groups are built over global ranks).  Physical NPU selection
    on each host is a deployment concern and is NOT here — operators pick
    cards via ``ASCEND_RT_VISIBLE_DEVICES`` at launch time.
    """

    id: int
    addr: str
    ranks: list[int]          # 全局 rank 列表（不是物理 NPU 号）
    zmq_base_port: int


@dataclass(frozen=True)
class WorldInfo:
    master_addr: str
    master_port: int


class RoleRegistry:
    """Static registry of all edges/clouds in the deployment.

    All instances load the same YAML file at startup.  The registry answers
    three questions: who am I (self_role), who are my peers (edges/clouds),
    and which ZMQ endpoint should a given (edge, cloud, kind) channel use.
    """

    def __init__(self, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        self._world = WorldInfo(**cfg["world"])
        self._edges = {int(e["id"]): PeerInfo(ranks=list(e["ranks"]), **{
            k: v for k, v in e.items() if k != "ranks"})
            for e in cfg["edges"]}
        self._clouds = {int(c["id"]): PeerInfo(ranks=list(c["ranks"]), **{
            k: v for k, v in c.items() if k != "ranks"})
            for c in cfg["clouds"]}
        # kv_partition supports two YAML forms:
        #   ratio: {0: 0.5, 1: 0.5}          (preferred — resolved at startup
        #                                     once the cloud's real block
        #                                     count is known)
        #   num_blocks_total + split: {...}  (absolute, pre-computed)
        self._kv_partition_raw = cfg.get("kv_partition")
        self._kv_partition: KvPartition | None = None
        if self._kv_partition_raw is not None and "split" in self._kv_partition_raw:
            self._kv_partition = KvPartition.from_config(self._kv_partition_raw)
        # Canonical digest of the whole config; all instances must compute
        # the same value (startup consistency check).
        self._config_digest = hashlib.sha256(
            json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:16]

        logger.info(
            "RoleRegistry loaded from %s: edges=%s clouds=%s digest=%s",
            path, sorted(self._edges), sorted(self._clouds),
            self._config_digest,
        )

    # ------------------------------------------------------------------ #
    # Identity / membership
    # ------------------------------------------------------------------ #
    @property
    def world(self) -> WorldInfo:
        return self._world

    @property
    def kv_partition(self) -> KvPartition:
        """The materialized partition.  When the YAML used ratios, call
        ``resolve_kv_partition(num_blocks_total)`` first (once the cloud's
        real block count is known)."""
        if self._kv_partition is None:
            raise RuntimeError(
                "kv_partition is ratio-based and not yet resolved; call "
                "resolve_kv_partition(num_blocks_total) first"
            )
        return self._kv_partition

    def resolve_kv_partition(self, num_blocks_total: int) -> KvPartition:
        """Materialize ratio-based partition into absolute block ranges."""
        if self._kv_partition is not None:
            return self._kv_partition
        raw = self._kv_partition_raw
        if raw is None:
            raise RuntimeError("no kv_partition in registry")
        self._kv_partition = KvPartition.from_ratios(
            {int(k): float(v) for k, v in raw["ratio"].items()},
            num_blocks_total,
        )
        logger.info(
            "kv partition resolved: total=%d split=%s",
            num_blocks_total, self._kv_partition.split,
        )
        return self._kv_partition

    @property
    def config_digest(self) -> str:
        return self._config_digest

    @property
    def edge_ids(self) -> list[int]:
        return sorted(self._edges)

    @property
    def cloud_ids(self) -> list[int]:
        return sorted(self._clouds)

    def edge(self, edge_id: int) -> PeerInfo:
        return self._edges[edge_id]

    def cloud(self, cloud_id: int) -> PeerInfo:
        return self._clouds[cloud_id]

    def validate_self(self, role: str, instance_id: int) -> None:
        """Check that this process's declared (role, id) exists in the table."""
        table = self._edges if role == "edge" else self._clouds
        if instance_id not in table:
            raise ValueError(
                f"role={role} id={instance_id} not found in registry; "
                f"known ids={sorted(table)}"
            )

    def assert_rank_membership(self, role: str, instance_id: int,
                               global_rank: int) -> None:
        """Assert this process's actual global rank matches the registry.

        The registry declares which global ranks each instance owns; the
        actual rank comes from the distributed rendezvous (RANK env or join
        order).  If they disagree, pair/EP groups would be built over the
        wrong processes — fail fast at startup instead of hanging at the
        first P2P rendezvous.
        """
        table = self._edges if role == "edge" else self._clouds
        expected = table[instance_id].ranks
        if global_rank not in expected:
            raise ValueError(
                f"rank/registry mismatch: role={role} id={instance_id} "
                f"process has global_rank={global_rank}, but registry says "
                f"ranks={expected}.  Fix launch (explicit RANK per instance) "
                f"or the registry."
            )

    # ------------------------------------------------------------------ #
    # ZMQ endpoint planning (single source of truth)
    # ------------------------------------------------------------------ #
    def endpoint(self, edge_id: int, cloud_id: int, kind: str) -> str:
        """ZMQ endpoint for a control-plane channel.

        Args:
            edge_id: edge instance id.
            cloud_id: cloud instance id.
            kind: "pre_out" (edge -> cloud SchedulerOutput) or
                "post_out" (cloud -> edge returns).

        Channel layout (per pair):
            pre_out:  edge binds  tcp://*:<edge.zmq_base_port>
                      cloud connects tcp://<edge.addr>:<...>
            post_out: cloud binds tcp://*:<cloud.zmq_base_port + edge_id * 2>
                      edge connects tcp://<cloud.addr>:<...>
        """
        if kind == "pre_out":
            port = self._edges[edge_id].zmq_base_port
            return f"tcp://{self._edges[edge_id].addr}:{port}"
        if kind == "post_out":
            port = self._clouds[cloud_id].zmq_base_port + edge_id * 2
            return f"tcp://{self._clouds[cloud_id].addr}:{port}"
        raise ValueError(f"unknown endpoint kind: {kind}")


# ---------------------------------------------------------------------- #
# Process-level singleton
# ---------------------------------------------------------------------- #
_REGISTRY: RoleRegistry | None = None


def init_role_registry(path: str) -> RoleRegistry:
    """Load (once) and return the process-wide RoleRegistry."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = RoleRegistry(path)
    return _REGISTRY


def get_role_registry() -> RoleRegistry | None:
    """Return the loaded registry, or None when multi-instance mode is off."""
    return _REGISTRY
