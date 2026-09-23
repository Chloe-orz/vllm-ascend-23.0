# Copyright (c) 2026 Huawei Technologies Co., Ltd. All Rights Reserved.
"""CPU/mocked contracts for topology-driven LWD; no NPU collectives run."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from vllm.config.lwd_topology import LwdLink, LwdTopology
from vllm.config.lwd import LwdConfig
from vllm.v1.core.sched.output import LwdBatch, LwdBatchType, LwdEmbedBatch
from vllm_ascend.distributed import lwd_wire
from vllm_ascend.distributed.lwd_comm.channel import LwdChannel
from vllm_ascend.distributed.lwd_comm.future import LwdCommFuture
from vllm_ascend.distributed.lwd_comm.service import LwdCommService
from vllm_ascend.distributed.lwd_comm.topology import (
    LwdConnectionKey,
    build_lwd_wire_plan,
    select_lwd_wire_connection,
    bind_lwd_worker_connections,
    resolve_lwd_batch_connection,
)
from vllm_ascend.distributed.lwd_comm.types import LwdChannelType, LwdCommRequest


def make_topology(scene="edge_share", dps=2):
    """The eight HTML example layouts, without an external bundle dependency."""
    edge_count = 1 if scene == "single_instance" else 2
    cloud_count = 2 if scene in ("edge_share", "lwd_cluster") else 1
    edge_cards = 1 if scene in ("single_instance", "edge_share") else 2
    edges = [
        {"id": edge, "dp": [
            {"dp_idx": dp, "addr": f"10.0.0.{rank + 1}", "ranks": [rank]}
            for dp in range(dps)
        ]}
        for edge in range(edge_count)
        for rank in [0 if scene == "edge_share" else edge]
    ]
    clouds = [
        {"id": cloud, "dp": [
            {"dp_idx": dp, "addr": f"10.1.0.{cloud + 1}", "ctrl_port": 5550 + dp,
             "ranks": list(range(start, start + 8 // dps))}
            for dp in range(dps)
            for start in [edge_cards + cloud * 8 + dp * (8 // dps)]
        ]}
        for cloud in range(cloud_count)
    ]
    links = [
        {"edge": edge, "cloud": cloud}
        for edge in range(edge_count)
        for cloud in range(cloud_count)
        if scene != "edge_share" or edge == cloud
    ]
    return LwdTopology.from_dict({
        "deployment": {"mode": 0, "scene": scene, "hccl_world_size": edge_cards + 8 * cloud_count,
                       "edges_num": edge_count, "clouds_num": cloud_count},
        "feature_ctrl": {}, "edges": edges, "clouds": clouds, "instance_links": links,
    })


@pytest.mark.parametrize("scene,links,domains,world", [
    ("single_instance", 1, 1, 9), ("edge_share", 2, 2, 17),
    ("cloud_share", 2, 1, 10), ("lwd_cluster", 4, 2, 18),
])
@pytest.mark.parametrize("dps", [1, 2])
def test_eight_example_plans(scene, links, domains, world, dps):
    topology = make_topology(scene, dps)
    plan = build_lwd_wire_plan(topology)
    assert topology.deployment.hccl_world_size == world
    assert len(plan) == links * dps
    assert len({(item.key.cloud_id, item.key.dp_idx) for item in plan}) == domains * dps
    assert [item.key for item in plan] == sorted(item.key for item in plan)
    for item in plan:
        assert item.edge_rank == topology.dp("edge", item.key.edge_id, item.key.dp_idx).ranks[0]
        assert item.cloud_ranks == topology.dp("cloud", item.key.cloud_id, item.key.dp_idx).ranks
        assert item.peer_for(item.edge_rank) == item.cloud_leader_rank
        assert item.peer_for(item.cloud_leader_rank) == item.edge_rank


def test_group_plan_does_not_depend_on_input_link_order():
    topology = make_topology("lwd_cluster", 2)
    reordered = replace(topology, instance_links=tuple(reversed(topology.instance_links)))
    assert build_lwd_wire_plan(topology) == build_lwd_wire_plan(reordered)


def test_single_dp_binding_requires_logical_identity():
    topology = make_topology("single_instance", 1)
    config = SimpleNamespace(
        lwd_config=LwdConfig(enabled=True, role="edge", topology=topology),
    )
    bindings = bind_lwd_worker_connections(config, rank=0)
    key = (0, 0, 0)
    batch = LwdBatch(LwdBatchType.LWD_EMBED, 0, LwdEmbedBatch(), connection_key=key)
    assert resolve_lwd_batch_connection(batch, bindings) == LwdConnectionKey(*key)
    for bad_key in (None, (1, 1, 0), (True, 0, 0)):
        with pytest.raises(ValueError, match="not bound"):
            resolve_lwd_batch_connection(replace(batch, connection_key=bad_key), bindings)
    with pytest.raises(ValueError, match="does not belong"):
        bind_lwd_worker_connections(config, rank=1)


def test_distinct_logical_links_with_identical_endpoints_are_not_merged():
    topology = make_topology("edge_share", 1)
    topology = replace(
        topology, instance_links=(LwdLink(0, 0), LwdLink(1, 0), LwdLink(1, 1))
    )
    first, second, _ = build_lwd_wire_plan(topology)
    assert first.endpoint_ranks == second.endpoint_ranks
    assert first.key != second.key


def test_selection_is_explicit_for_shared_rank_or_fan_in():
    plan = build_lwd_wire_plan(make_topology())
    with pytest.raises(ValueError, match="supply an explicit"):
        select_lwd_wire_connection(plan, 0)
    key = LwdConnectionKey(1, 1, 1)
    assert select_lwd_wire_connection(plan, 0, key).cloud_leader_rank == 13
    # Non-leader cloud ranks still need to select the same broadcast domain.
    assert select_lwd_wire_connection(plan, 16).key == key
    with pytest.raises(ValueError, match="found 0"):
        select_lwd_wire_connection(plan, 1, key)
    with pytest.raises(ValueError, match="not a P2P endpoint"):
        select_lwd_wire_connection(plan, 16).peer_for(16)
    cloud_share = build_lwd_wire_plan(make_topology("cloud_share", 1))
    with pytest.raises(ValueError, match="found 2"):
        select_lwd_wire_connection(cloud_share, 2)


@pytest.mark.parametrize("value", [-1, True, "0"])
def test_invalid_connection_ids(value):
    with pytest.raises(ValueError):
        LwdConnectionKey(value, 0, 0)


@pytest.fixture
def runtime(monkeypatch):
    topology = make_topology("single_instance", 1)
    rank = [0]
    bootstrap = SimpleNamespace(ranks=list(range(9)), device_group=object(), barrier=Mock())
    config = SimpleNamespace(lwd_config=SimpleNamespace(topology=topology))
    monkeypatch.setattr("vllm.config.get_current_vllm_config", lambda: config)
    monkeypatch.setattr(lwd_wire, "_get_lwd_bootstrap_world_group", lambda: bootstrap)
    monkeypatch.setattr(lwd_wire.dist, "get_rank", lambda: rank[0])
    monkeypatch.setattr(lwd_wire.dist, "get_backend", lambda group: "hccl")
    create_group = Mock(side_effect=lambda ranks, backend: SimpleNamespace(ranks=ranks))
    monkeypatch.setattr(lwd_wire.dist, "new_group", create_group)
    monkeypatch.setattr(lwd_wire, "_LWD_CHANNEL_GROUPS", {})
    monkeypatch.setattr(lwd_wire, "_LWD_CHANNEL_STREAMS", {})
    monkeypatch.setattr(lwd_wire, "_LWD_ENDPOINTS", ())
    monkeypatch.setattr(lwd_wire, "_INITIALIZED", False)
    monkeypatch.setattr(lwd_wire.torch.npu, "Stream", Mock())
    real_warmup = lwd_wire.warmup_lwd_duplex_channels
    warmup = Mock()
    monkeypatch.setattr(lwd_wire, "warmup_lwd_duplex_channels", warmup)

    def tp_group():
        for cloud in topology.clouds:
            for dp in cloud.dp:
                if rank[0] in dp.ranks:
                    return SimpleNamespace(ranks=dp.ranks, world_size=len(dp.ranks), device_group=dp.ranks)
        raise AssertionError("Edge rank must not query cloud TP group")

    monkeypatch.setattr(lwd_wire, "get_tp_group", tp_group)
    return SimpleNamespace(rank=rank, create_group=create_group, bootstrap=bootstrap,
                           config=config, warmup=warmup, real_warmup=real_warmup)


@pytest.mark.parametrize("rank", range(9))
def test_every_rank_creates_same_complete_group_plan(runtime, rank):
    runtime.rank[0] = rank
    lwd_wire.init_lwd_duplex_channels()
    assert [call.args[0] for call in runtime.create_group.call_args_list] == [
        [0, 1], [0, 1],
    ]
    lwd_wire.init_lwd_duplex_channels()  # Idempotent after successful warmup.
    assert runtime.create_group.call_count == 2


@pytest.mark.parametrize("scene,dps", [
    ("single_instance", 2), ("edge_share", 1), ("edge_share", 2),
    ("cloud_share", 1), ("lwd_cluster", 2),
])
def test_unsupported_topologies_never_create_channels(runtime, scene, dps):
    topology = make_topology(scene, dps)
    runtime.config.lwd_config.topology = topology
    with pytest.raises(ValueError, match="topology was parsed"):
        lwd_wire.init_lwd_duplex_channels()
    runtime.create_group.assert_not_called()
    runtime.warmup.assert_not_called()
    config = SimpleNamespace(
        lwd_config=LwdConfig(enabled=True, role="edge", topology=topology)
    )
    with pytest.raises(ValueError, match="topology was parsed"):
        bind_lwd_worker_connections(config, rank=0)


def test_initialization_checks_bootstrap_world_and_cloud_domain(runtime, monkeypatch):
    runtime.bootstrap.ranks = list(range(17))
    with pytest.raises(ValueError, match="Bootstrap world"):
        lwd_wire.init_lwd_duplex_channels()
    runtime.create_group.assert_not_called()
    runtime.bootstrap.ranks = list(range(9))
    runtime.rank[0] = 1
    monkeypatch.setattr(lwd_wire, "get_tp_group", lambda: SimpleNamespace(ranks=[1, 2]))
    with pytest.raises(ValueError, match="broadcast domain"):
        lwd_wire.init_lwd_duplex_channels()
    runtime.create_group.assert_not_called()


def test_warmup_failure_does_not_mark_initialized(runtime):
    runtime.warmup.side_effect = RuntimeError("warmup failed")
    with pytest.raises(RuntimeError, match="warmup failed"):
        lwd_wire.init_lwd_duplex_channels()
    assert not lwd_wire.lwd_channels_initialized()
    with pytest.raises(RuntimeError, match="restart workers"):
        lwd_wire.init_lwd_duplex_channels()


@pytest.mark.parametrize("rank,ops", [
    (0, ["send", "recv"]),
    (1, ["recv", "broadcast", "send"]),
    (2, ["broadcast"]),
    (8, ["broadcast"]),
])
def test_warmup_uses_p2p_broadcast_p2p(runtime, monkeypatch, rank, ops):
    runtime.rank[0] = rank
    lwd_wire.init_lwd_duplex_channels()
    calls = []
    monkeypatch.setattr(lwd_wire.torch, "zeros", lambda *args, **kwargs: object())

    def operation(name):
        def post(*args, **kwargs):
            calls.append(name)
            return SimpleNamespace(wait=Mock())
        return post

    monkeypatch.setattr(lwd_wire.dist, "isend", operation("send"))
    monkeypatch.setattr(lwd_wire.dist, "irecv", operation("recv"))
    monkeypatch.setattr(lwd_wire.dist, "broadcast", operation("broadcast"))
    runtime.real_warmup()
    assert calls == ops
    runtime.bootstrap.barrier.assert_called_once()


def test_group_peer_and_stream_are_selected_together(runtime):
    lwd_wire.init_lwd_duplex_channels()
    key = LwdConnectionKey(0, 0, 0)
    assert lwd_wire.get_lwd_channel_peer(LwdChannelType.UP, key) == 1
    up = lwd_wire.get_lwd_channel_device_group(LwdChannelType.UP, key)
    down = lwd_wire.get_lwd_channel_device_group(LwdChannelType.DOWN, key)
    assert up.ranks == [0, 1] and down.ranks == [0, 1]
    assert up is not down
    assert lwd_wire.get_lwd_channel_stream(LwdChannelType.UP, key) is not None
    assert lwd_wire.get_lwd_channel_peer(LwdChannelType.UP) == 1
    with pytest.raises(ValueError, match="requires rank=1"):
        lwd_wire.resolve_lwd_channel_operation(LwdChannelType.UP, "recv", key)


@pytest.mark.parametrize("op,rank,peer", [("send", 0, 1), ("recv", 1, 0)])
def test_main_and_aux_frames_use_selected_group_and_global_peer(runtime, monkeypatch, op, rank, peer):
    runtime.rank[0] = rank
    lwd_wire.init_lwd_duplex_channels()
    key = LwdConnectionKey(0, 0, 0)
    channel = LwdChannel(LwdChannelType.UP, op, key)
    group = lwd_wire.get_lwd_channel_device_group(LwdChannelType.UP, key)
    monkeypatch.setattr(lwd_wire.dist, "get_process_group_ranks", lambda item: item.ranks)
    send, recv = Mock(), Mock()
    monkeypatch.setattr(lwd_wire.dist, "isend", send)
    monkeypatch.setattr(lwd_wire.dist, "irecv", recv)
    main, aux = Mock(), Mock()
    main.contiguous.return_value = main
    main.shape = (8,)
    aux.contiguous.return_value = aux
    request = LwdCommRequest(
        LwdChannelType.UP, op, 8, tensor=main, aux_tensor=aux,
        aux_num_elements=3, connection_key=key,
    )
    if op == "send":
        channel._wire_send(request)
        assert [call.args[0] for call in send.call_args_list] == [main, aux]
        assert [call.kwargs for call in send.call_args_list] == [{"dst": peer, "group": group}] * 2
        recv.assert_not_called()
    else:
        monkeypatch.setattr(lwd_wire.torch, "empty", Mock(side_effect=[main, aux]))
        result, aux_result, handles = channel._wire_recv(request)
        assert result is main and aux_result is aux and len(handles) == 2
        assert [call.kwargs for call in recv.call_args_list] == [{"src": peer, "group": group}] * 2
        send.assert_not_called()


def test_service_fifo_and_skip_before_first_submit(runtime, monkeypatch):
    lwd_wire.init_lwd_duplex_channels()
    service = LwdCommService()
    first = LwdConnectionKey(0, 0, 0)
    posted = []

    def execute(channel, request, predecessor, into=None):
        posted.append((request.connection_key, request.seqno))
        return into or LwdCommFuture.deferred(request)

    # Keep the real FIFO/reorder implementation, replace only device work.
    monkeypatch.setattr(LwdChannel, "_execute", execute)
    service.skip_seqno(LwdChannelType.DOWN, 0, connection_key=first)
    service.submit_recv(LwdCommRequest(LwdChannelType.DOWN, "recv", 8, seqno=1, connection_key=first))
    assert posted == [(first, 1)]
    assert len(service._channels) == 1
    service.submit_recv(LwdCommRequest(LwdChannelType.DOWN, "recv", 8, seqno=3, connection_key=first))
    assert posted[-1] == (first, 1)
    service.skip_seqno(LwdChannelType.DOWN, 2, connection_key=first)
    assert posted[-1] == (first, 3)
    with pytest.raises(ValueError, match="does not match"):
        service.submit_recv(LwdCommRequest(
            LwdChannelType.DOWN, "recv", 8, seqno=4, src_dst=8, connection_key=first,
        ))


def test_legacy_single_connection_request_resolves_to_explicit_key(runtime):
    runtime.config.lwd_config.topology = make_topology("single_instance", 1)
    runtime.bootstrap.ranks = list(range(9))
    lwd_wire.init_lwd_duplex_channels()
    key = lwd_wire.resolve_lwd_channel_operation(LwdChannelType.UP, "send")
    assert key == LwdConnectionKey(0, 0, 0)
    assert lwd_wire.get_lwd_channel_peer(LwdChannelType.UP) == 1


def test_nonmembers_do_not_destroy_invalid_group_handles(runtime, monkeypatch):
    runtime.rank[0] = 2
    lwd_wire.init_lwd_duplex_channels()
    destroy = Mock()
    monkeypatch.setattr(lwd_wire.dist, "destroy_process_group", destroy)
    lwd_wire.destroy_lwd_duplex_channels()
    destroy.assert_not_called()
    assert not lwd_wire.lwd_channels_initialized()
