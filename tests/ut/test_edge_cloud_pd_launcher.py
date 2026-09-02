import json
from pathlib import Path

import pytest

from examples.edge_cloud_pd_disaggregated_qwen3_5.launch import (
    build_command,
    load_config,
    validate_config,
)


EXAMPLE_CONFIG = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "edge_cloud_pd_disaggregated_qwen3_5"
    / "deployment.example.json"
)


def _json_option(command: list[str], option: str) -> dict:
    return json.loads(command[command.index(option) + 1])


def test_example_config_builds_target_topology() -> None:
    config = load_config(EXAMPLE_CONFIG)

    edge = build_command(config, "p-edge")
    cloud = build_command(config, "p-cloud")
    decode = build_command(config, "decode")
    proxy = build_command(config, "proxy")

    for command in (edge, cloud):
        assert "--enable-edge-cloud" in command
        assert command[command.index("--edge-npu-count") + 1] == "2"
        assert command[command.index("--cloud-npu-count") + 1] == "2"
        kv_config = _json_option(command, "--kv-transfer-config")
        assert kv_config["kv_connector"] == "MooncakeLayerwiseConnector"
        assert kv_config["kv_role"] == "kv_producer"
        assert kv_config["kv_connector_extra_config"]["prefill"] == {
            "dp_size": 1,
            "tp_size": 2,
        }
        additional = _json_option(command, "--additional-config")
        assert additional["edge_cloud_config"]["mode"] == "embedding_only"
        assert additional["edge_cloud_config"]["pd_separation"]["enabled"]
        assert additional["edge_cloud_config"]["kv_engine_id"] == (
            config["p_engine_id"]
        )
        assert kv_config["engine_id"] == config["p_engine_id"]

    assert "--headless" not in edge
    assert "--headless" in cloud
    assert edge[edge.index("--node-rank") + 1] == "0"
    assert cloud[cloud.index("--node-rank") + 1] == "1"

    assert "--enable-edge-cloud" not in decode
    assert "--enforce-eager" not in decode
    assert decode[decode.index("--tensor-parallel-size") + 1] == "2"
    assert _json_option(decode, "--compilation-config") == {
        "cudagraph_mode": "FULL_DECODE_ONLY"
    }
    assert _json_option(decode, "--additional-config")[
        "require_aclgraph"
    ]
    assert _json_option(decode, "--kv-transfer-config")["kv_role"] == (
        "kv_consumer"
    )

    edge_mtp = _json_option(edge, "--speculative-config")
    decode_mtp = _json_option(decode, "--speculative-config")
    assert edge_mtp == decode_mtp == {
        "method": "qwen3_5_mtp",
        "num_speculative_tokens": 3,
    }
    assert proxy[1].endswith(
        "load_balance_proxy_layerwise_server_example.py"
    )


def test_config_requires_exactly_two_devices_per_compute_role() -> None:
    config = load_config(EXAMPLE_CONFIG)
    config["devices"]["decode"] = [0]

    with pytest.raises(ValueError, match="exactly two"):
        validate_config(config)


def test_config_rejects_port_collision_on_decode() -> None:
    config = load_config(EXAMPLE_CONFIG)
    config["ports"]["decode_api"] = config["ports"]["kv"]

    with pytest.raises(ValueError, match="D API"):
        validate_config(config)
