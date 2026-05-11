#
# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
# This file is a part of the vllm-ascend project.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""TCP 控制通信：Edge 与 Cloud 之间的 out-of-band 控制面，用于同步阶段状态。"""

import json
import socket
import struct
from typing import Any

from vllm.logger import logger

# 默认 TCP 超时（秒）：连接建立、收发消息的最大等待时间
_DEFAULT_TCP_TIMEOUT = 30


class EdgeCloudCtrlComm:
    """TCP 控制通信。

    控制面与数据面分离：
    - 数据面：HiddenStatesTransferHCCL 负责传输 hidden_states（大流量）
    - 控制面：本类负责传输 Prefill/Decode 完成信号、shape 协商等（小流量、低延迟）

    通信模型：Edge 作为 TCP Server，Cloud 作为 TCP Client。
    """

    def __init__(self, tls_config: dict | None = None):
        self.tls_enable = False
        if tls_config is not None:
            self.tls_enable = tls_config.get("tls_enable", "0") == "1"
        self.socket: socket.socket | None = None
        self.conn: socket.socket | None = None
        self.role: str | None = None
        self.server_ip: str | None = None
        self.server_port: int | None = None

    def init_tcp_link(
        self,
        rank: int,
        role: str,
        server_ip: str,
        server_port: int,
        timeout: float = _DEFAULT_TCP_TIMEOUT,
    ) -> None:
        """初始化 TCP 连接。

        Args:
            rank: 当前进程 rank。
            role: "edge" 或 "cloud"。
            server_ip: Edge 节点监听的 IP 地址。
            server_port: TCP 控制端口。
            timeout: socket 超时时间（秒）。
        """
        self.role = role
        self.server_ip = server_ip
        self.server_port = server_port

        if role == "edge":
            # Edge 作为 TCP Server，等待 Cloud 连接
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.settimeout(timeout)
            self.socket.bind((server_ip, server_port))
            self.socket.listen(1)
            logger.info(
                "[EdgeCloud] Edge waiting for Cloud connection on %s:%d (timeout=%.1fs)",
                server_ip, server_port, timeout,
            )
            self.conn, addr = self.socket.accept()
            self.conn.settimeout(timeout)
            logger.info(
                "[EdgeCloud] Cloud connected from %s", addr,
            )
        else:
            # Cloud 作为 TCP Client，主动连接 Edge
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(timeout)
            self.socket.connect((server_ip, server_port))
            self.conn = self.socket
            self.conn.settimeout(timeout)
            logger.info(
                "[EdgeCloud] Cloud connected to Edge at %s:%d (timeout=%.1fs)",
                server_ip, server_port, timeout,
            )

    def _send_msg(self, msg: bytes) -> None:
        """发送长度前缀消息：先发送 4 字节长度，再发送消息体。"""
        if self.conn is None:
            raise ConnectionError("TCP connection not initialized.")
        try:
            self.conn.sendall(struct.pack("!I", len(msg)))
            self.conn.sendall(msg)
        except socket.timeout:
            raise ConnectionError("TCP send timeout.")

    def _recv_msg(self) -> bytes:
        """接收长度前缀消息。"""
        if self.conn is None:
            raise ConnectionError("TCP connection not initialized.")
        raw_len = self._recvall(4)
        msg_len = struct.unpack("!I", raw_len)[0]
        return self._recvall(msg_len)

    def _recvall(self, n: int) -> bytes:
        """循环读取直到收满 n 字节。"""
        if self.conn is None:
            raise ConnectionError("TCP connection not initialized.")
        data = b""
        while len(data) < n:
            try:
                packet = self.conn.recv(n - len(data))
            except socket.timeout:
                raise ConnectionError(
                    f"TCP recv timeout: expected {n} bytes, got {len(data)} bytes."
                )
            if not packet:
                raise ConnectionError("TCP connection closed unexpectedly.")
            data += packet
        return data

    def send_prefill(self) -> None:
        """发送 prefill 阶段完成信号。"""
        self._send_msg(b"prefill_done")

    def recv_prefill(self) -> None:
        """接收 prefill 阶段完成信号。"""
        msg = self._recv_msg()
        assert msg == b"prefill_done", f"Unexpected msg: {msg}"

    def send_decode(self) -> None:
        """发送 decode 阶段完成信号。"""
        self._send_msg(b"decode_done")

    def recv_decode(self) -> None:
        """接收 decode 阶段完成信号。"""
        msg = self._recv_msg()
        assert msg == b"decode_done", f"Unexpected msg: {msg}"

    def send_shape(self, shape: tuple) -> None:
        """发送张量 shape 信息（用于收发前协商 buffer 大小）。

        使用 JSON 替代 pickle，避免反序列化安全风险。
        """
        self._send_msg(json.dumps(shape).encode("utf-8"))

    def recv_shape(self) -> tuple:
        """接收张量 shape 信息。"""
        return tuple(json.loads(self._recv_msg().decode("utf-8")))

    def close(self) -> None:
        """关闭 TCP 连接。"""
        if self.conn is not None:
            self.conn.close()
            self.conn = None
        if self.socket is not None:
            self.socket.close()
            self.socket = None
