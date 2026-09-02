#!/usr/bin/env python3
"""Validated launcher for the 2-card edge P + 2-card cloud P + 2-card D topology."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shlex
import socket
import sys
from pathlib import Path
from typing import Any


ROLES = ("p-edge", "p-cloud", "decode", "proxy")
NPU_ROLES = ROLES[:-1]
LAYERWISE_PROXY = (
    Path(__file__).resolve().parents[1]
    / "disaggregated_prefill_v1"
    / "load_balance_proxy_layerwise_server_example.py"
)


def _require(config: dict[str, Any], key: str) -> Any:
    if key not in config:
        raise ValueError(f"Missing required deployment config key: {key}")
    return config[key]


def _validate_ip(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an IP address string")
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise ValueError(f"{name} is not a valid IP address: {value}") from error
    if address.version != 4:
        raise ValueError(
            f"{name} must be IPv4 for the current edge-cloud ZMQ endpoints"
        )
    if address.is_unspecified or address.is_multicast or address.is_loopback:
        raise ValueError(
            f"{name} must be reachable from the other deployment nodes; "
            f"got {value}"
        )
    return value


def _validate_port(name: str, value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer TCP port")
    if not 1 <= value <= 65535:
        raise ValueError(f"{name} must be in [1, 65535], got {value}")
    return value


def _validate_model(config: dict[str, Any]) -> None:
    model = str(_require(config, "model"))
    model_path = Path(model).expanduser()
    identifiers = [model.lower()]
    if model_path.is_absolute() and not model_path.exists():
        raise ValueError(f"Local model path does not exist: {model_path}")
    if model_path.exists():
        config_path = model_path / "config.json"
        if not config_path.is_file():
            raise ValueError(f"Local model has no config.json: {model_path}")
        with config_path.open(encoding="utf-8") as file:
            model_config = json.load(file)
        text_config = model_config.get("text_config") or {}
        model_types = {
            model_config.get("model_type"),
            text_config.get("model_type"),
        }
        if not model_types.intersection({"qwen3_5", "qwen3_5_text"}):
            raise ValueError(
                "Only the dense Qwen3.5 model family is supported; "
                f"config model types are {sorted(str(x) for x in model_types)}"
            )
        if model_types.intersection({"qwen3_5_moe", "qwen3_5_moe_text"}):
            raise ValueError("Qwen3.5 MoE weights are outside this deployment scope")
        identifiers.append(str(model_config.get("_name_or_path", "")).lower())

    is_qwen_35_27b = any(
        "qwen3.5" in identifier and "27b" in identifier
        for identifier in identifiers
    )
    if not is_qwen_35_27b and not config.get("allow_unverified_27b", False):
        raise ValueError(
            "The model identifier must contain both 'Qwen3.5' and '27B'. "
            "For a renamed local Qwen3.5-27B directory, first verify the "
            "weights and set allow_unverified_27b=true."
        )


def validate_config(config: dict[str, Any]) -> None:
    _validate_model(config)
    served_model_name = _require(config, "served_model_name")
    if not isinstance(served_model_name, str) or not served_model_name.strip():
        raise ValueError("served_model_name must be a non-empty string")
    p_engine_id = _require(config, "p_engine_id")
    if not isinstance(p_engine_id, str) or len(p_engine_id.strip()) < 8:
        raise ValueError(
            "p_engine_id must be a unique, non-empty deployment identifier"
        )
    if _require(config, "weight_format") not in {"bf16", "ascend-w8a8"}:
        raise ValueError("weight_format must be 'bf16' or 'ascend-w8a8'")

    node_ips = []
    for name in ("p_edge_ip", "p_cloud_ip", "decode_ip", "proxy_ip"):
        node_ips.append(_validate_ip(name, _require(config, name)))
    if len(set(node_ips[:3])) != 3:
        raise ValueError("P-edge, P-cloud, and D must use three distinct IPs")

    devices = _require(config, "devices")
    interfaces = _require(config, "network_interfaces")
    for role in NPU_ROLES:
        role_devices = _require(devices, role)
        if (
            not isinstance(role_devices, list)
            or len(role_devices) != 2
            or len(set(role_devices)) != 2
            or any(
                not isinstance(device, int)
                or isinstance(device, bool)
                or device < 0
                for device in role_devices
            )
        ):
            raise ValueError(
                f"devices.{role} must contain exactly two distinct, "
                "non-negative NPU IDs"
            )
        interface = _require(interfaces, role)
        if not isinstance(interface, str) or not interface.strip():
            raise ValueError(
                f"network_interfaces.{role} must be a non-empty name"
            )

    ports = _require(config, "ports")
    port_names = (
        "p_api",
        "decode_api",
        "proxy",
        "p_master",
        "pd_pre_out",
        "pd_post_out",
        "kv",
    )
    resolved_ports = {
        name: _validate_port(f"ports.{name}", _require(ports, name))
        for name in port_names
    }
    # The P rendezvous also consumes master+1 for cloud-address discovery.
    if resolved_ports["p_master"] == 65535:
        raise ValueError("ports.p_master must leave p_master+1 available")
    p_edge_ports = {
        resolved_ports["p_api"],
        resolved_ports["p_master"],
        resolved_ports["p_master"] + 1,
        resolved_ports["pd_pre_out"],
    }
    if len(p_edge_ports) != 4:
        raise ValueError("P-edge API/rendezvous/PRE_OUT ports must be distinct")
    p_cloud_ports = {
        resolved_ports["pd_post_out"],
        resolved_ports["kv"],
        resolved_ports["kv"] + 1,
    }
    if resolved_ports["kv"] == 65535 or len(p_cloud_ports) != 3:
        raise ValueError(
            "P-cloud POST_OUT and the two Mooncake TP ports must be valid "
            "and distinct"
        )
    decode_ports = {
        resolved_ports["decode_api"],
        resolved_ports["kv"],
        resolved_ports["kv"] + 1,
    }
    if len(decode_ports) != 3:
        raise ValueError(
            "D API and the two Mooncake TP ports must be distinct"
        )
    bindings = (
        (config["p_edge_ip"], resolved_ports["p_api"], "P API"),
        (config["p_edge_ip"], resolved_ports["p_master"], "P rendezvous"),
        (config["p_edge_ip"], resolved_ports["p_master"] + 1, "P IP discovery"),
        (config["p_edge_ip"], resolved_ports["pd_pre_out"], "PD PRE_OUT"),
        (config["p_cloud_ip"], resolved_ports["pd_post_out"], "PD POST_OUT"),
        (config["p_cloud_ip"], resolved_ports["kv"], "P Mooncake rank 0"),
        (config["p_cloud_ip"], resolved_ports["kv"] + 1, "P Mooncake rank 1"),
        (config["decode_ip"], resolved_ports["decode_api"], "D API"),
        (config["decode_ip"], resolved_ports["kv"], "D Mooncake rank 0"),
        (config["decode_ip"], resolved_ports["kv"] + 1, "D Mooncake rank 1"),
        (config["proxy_ip"], resolved_ports["proxy"], "Proxy API"),
    )
    occupied: dict[tuple[str, int], str] = {}
    for host, port, purpose in bindings:
        address = (host, port)
        if previous := occupied.get(address):
            raise ValueError(
                f"Port collision on {host}:{port}: {previous} and {purpose}"
            )
        occupied[address] = purpose

    mtp_tokens = _require(config, "mtp_num_speculative_tokens")
    if (
        not isinstance(mtp_tokens, int)
        or isinstance(mtp_tokens, bool)
        or not 1 <= mtp_tokens <= 14
    ):
        raise ValueError("mtp_num_speculative_tokens must be in [1, 14]")

    for name in ("max_model_len", "max_num_batched_tokens", "max_num_seqs"):
        value = _require(config, name)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    utilization = _require(config, "gpu_memory_utilization")
    if not isinstance(utilization, (int, float)) or not 0 < utilization < 1:
        raise ValueError("gpu_memory_utilization must be between 0 and 1")
    for name, default in (
        ("hccl_connect_timeout", 120),
        ("hccl_exec_timeout", 204),
    ):
        value = config.get(name, default)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        config = json.load(file)
    if not isinstance(config, dict):
        raise ValueError("Deployment config root must be a JSON object")
    validate_config(config)
    return config


def _json_arg(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"))


def _common_vllm_args(config: dict[str, Any]) -> list[str]:
    args = [
        "vllm",
        "serve",
        str(config["model"]),
        "--served-model-name",
        str(config["served_model_name"]),
        "--max-model-len",
        str(config["max_model_len"]),
        "--max-num-batched-tokens",
        str(config["max_num_batched_tokens"]),
        "--max-num-seqs",
        str(config["max_num_seqs"]),
        "--gpu-memory-utilization",
        str(config["gpu_memory_utilization"]),
        "--no-enable-prefix-caching",
        "--async-scheduling",
        "--speculative-config",
        _json_arg(
            {
                "method": "qwen3_5_mtp",
                "num_speculative_tokens": config[
                    "mtp_num_speculative_tokens"
                ],
            }
        ),
        "--compilation-config",
        _json_arg({"cudagraph_mode": "FULL_DECODE_ONLY"}),
    ]
    if config["weight_format"] == "ascend-w8a8":
        args.extend(("--quantization", "ascend"))
    if config.get("trust_remote_code", False):
        args.append("--trust-remote-code")
    return args


def _kv_transfer_config(
    role: str, port: int, engine_id: str | None = None
) -> dict[str, Any]:
    transfer_config: dict[str, Any] = {
        "kv_connector": "MooncakeLayerwiseConnector",
        "kv_role": role,
        "kv_port": port,
        "kv_connector_extra_config": {
            "use_ascend_direct": True,
            "prefill": {"dp_size": 1, "tp_size": 2},
            "decode": {"dp_size": 1, "tp_size": 2},
        },
    }
    if engine_id is not None:
        transfer_config["engine_id"] = engine_id
    return transfer_config


def _p_additional_config(
    config: dict[str, Any], role: str
) -> dict[str, Any]:
    return {
        "enable_cpu_binding": True,
        "edge_cloud_config": {
            "enabled": True,
            "role": role,
            "mode": "embedding_only",
            "edge_head_tail_layers": 0,
            "enable_decode_graph": True,
            "kv_engine_id": config["p_engine_id"],
            "pd_separation": {
                "enabled": True,
                "pre_out_port": config["ports"]["pd_pre_out"],
                "post_out_port": config["ports"]["pd_post_out"],
                "dispatch_policy": "expect_alternation",
            },
        },
    }


def build_command(config: dict[str, Any], role: str) -> list[str]:
    if role not in ROLES:
        raise ValueError(f"Unknown role {role!r}; expected one of {ROLES}")
    ports = config["ports"]
    if role == "proxy":
        return [
            sys.executable,
            str(LAYERWISE_PROXY),
            "--host",
            config["proxy_ip"],
            "--port",
            str(ports["proxy"]),
            "--prefiller-hosts",
            config["p_edge_ip"],
            "--prefiller-ports",
            str(ports["p_api"]),
            "--decoder-hosts",
            config["decode_ip"],
            "--decoder-ports",
            str(ports["decode_api"]),
        ]

    command = _common_vllm_args(config)
    if role in ("p-edge", "p-cloud"):
        edge_cloud_role = "edge" if role == "p-edge" else "cloud"
        command.extend(
            (
                "--enable-edge-cloud",
                "--edge-npu-count",
                "2",
                "--cloud-npu-count",
                "2",
                "--nnodes",
                "2",
                "--node-rank",
                "0" if role == "p-edge" else "1",
                "--master-addr",
                config["p_edge_ip"],
                "--master-port",
                str(ports["p_master"]),
                "--additional-config",
                _json_arg(_p_additional_config(config, edge_cloud_role)),
                "--kv-transfer-config",
                _json_arg(
                    _kv_transfer_config(
                        "kv_producer",
                        ports["kv"],
                        config["p_engine_id"],
                    )
                ),
            )
        )
        if role == "p-edge":
            command.extend(
                (
                    "--host",
                    config["p_edge_ip"],
                    "--port",
                    str(ports["p_api"]),
                    "--enable-request-id-headers",
                )
            )
        else:
            command.append("--headless")
        return command

    command.extend(
        (
            "--host",
            config["decode_ip"],
            "--port",
            str(ports["decode_api"]),
            "--tensor-parallel-size",
            "2",
            "--enable-request-id-headers",
            "--additional-config",
            _json_arg(
                {
                    "enable_cpu_binding": True,
                    "require_aclgraph": True,
                }
            ),
            "--kv-transfer-config",
            _json_arg(_kv_transfer_config("kv_consumer", ports["kv"])),
        )
    )
    return command


def build_environment(
    config: dict[str, Any], role: str
) -> dict[str, str]:
    environment = os.environ.copy()
    if role == "proxy":
        return environment
    interface = config["network_interfaces"][role]
    local_ip = config[
        {"p-edge": "p_edge_ip", "p-cloud": "p_cloud_ip", "decode": "decode_ip"}[
            role
        ]
    ]
    environment.update(
        {
            "ASCEND_RT_VISIBLE_DEVICES": ",".join(
                str(device) for device in config["devices"][role]
            ),
            "GLOO_SOCKET_IFNAME": interface,
            "TP_SOCKET_IFNAME": interface,
            "HCCL_SOCKET_IFNAME": interface,
            "HCCL_IF_IP": local_ip,
            # Used by cloud-address discovery and Mooncake side-channel
            # metadata. Pin it explicitly on multi-homed hosts.
            "VLLM_HOST_IP": local_ip,
            "HCCL_CONNECT_TIMEOUT": str(
                config.get("hccl_connect_timeout", 120)
            ),
            "HCCL_EXEC_TIMEOUT": str(config.get("hccl_exec_timeout", 204)),
            "PYTORCH_NPU_ALLOC_CONF": "expandable_segments:True",
        }
    )
    return environment


def validate_local_runtime(config: dict[str, Any], role: str) -> None:
    """Check the selected local address, interface, and listener ports."""
    local_ip = config[
        {
            "p-edge": "p_edge_ip",
            "p-cloud": "p_cloud_ip",
            "decode": "decode_ip",
            "proxy": "proxy_ip",
        }[role]
    ]
    if role != "proxy":
        interface = config["network_interfaces"][role]
        available_interfaces = {name for _, name in socket.if_nameindex()}
        if interface not in available_interfaces:
            raise ValueError(
                f"Network interface {interface!r} is not present on {role}; "
                f"available interfaces are {sorted(available_interfaces)}"
            )

    ports = config["ports"]
    role_ports = {
        "p-edge": (
            ports["p_api"],
            ports["p_master"],
            ports["p_master"] + 1,
            ports["pd_pre_out"],
        ),
        "p-cloud": (
            ports["pd_post_out"],
            ports["kv"],
            ports["kv"] + 1,
        ),
        "decode": (
            ports["decode_api"],
            ports["kv"],
            ports["kv"] + 1,
        ),
        "proxy": (ports["proxy"],),
    }[role]
    for port in role_ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind((local_ip, port))
        except OSError as error:
            raise ValueError(
                f"Cannot bind {role} listener {local_ip}:{port}: {error}"
            ) from error


def _print_command(command: list[str], environment: dict[str, str], role: str) -> None:
    if role != "proxy":
        for key in (
            "ASCEND_RT_VISIBLE_DEVICES",
            "GLOO_SOCKET_IFNAME",
            "TP_SOCKET_IFNAME",
            "HCCL_SOCKET_IFNAME",
            "HCCL_IF_IP",
            "VLLM_HOST_IP",
        ):
            print(f"{key}={shlex.quote(environment[key])}")
    print(shlex.join(command))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=ROLES)
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to the shared deployment JSON copied to every node.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the command without starting the process.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    command = build_command(config, args.role)
    environment = build_environment(config, args.role)
    _print_command(command, environment, args.role)
    if not args.dry_run:
        validate_local_runtime(config, args.role)
        os.execvpe(command[0], command, environment)


if __name__ == "__main__":
    main()
