"""
网络面带宽测试 —— 纯 TCP socket (隔离物理网络带宽)

与 data_face_*.py (HCCL 数据面) 互补:
  - data_face: 走 HCCL 栈, 含协议/拷贝/ACK 开销 = 推理实战能跑到的带宽
  - net_face:  走裸 TCP, 不经 HCCL/torch = 物理网络面的上限

对比两者:
  - net_face >> data_face  → 正常 (HCCL 有额外开销)
  - net_face 本身就低      → 网络面有问题 (网卡/线缆/拓扑/MTU/RDMA 配置)
  - net_face 高但 data_face 低 → HCCL 配置/版本问题, 网络没病

只依赖 Python 标准库 (socket), 不需要 torch/npu/cuda, 可在任何机器跑。

用法 (双机):
    # receiver (机器B, 先起)
    python net_face.py --role receiver --port 5001

    # sender (机器A, 后起)
    python net_face.py --role sender --host <B_ip> --port 5001 \
        --size-bytes 1048576,4194304,16777216,67108864,268435456 \
        --iters 20 --warmup 5

带宽 = payload / 发送耗时 (sender 端 socket.sendall 完成时间)。
大消息下 sendall 等价于把数据交给内核 TCP 栈, 接近网络吞吐上限。
"""

import argparse
import socket
import statistics
import sys
import time

# Windows 控制台默认 GBK, 强制 stdout 用 utf-8 避免中文乱码。
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

MIB = 1024 * 1024
GIB = 1024 ** 3


def parse_sizes(raw: str) -> list[int]:
    out = []
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            continue
        out.append(int(tok))
    seen = set()
    uniq = []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return sorted(uniq)


def recv_all(sock: socket.socket, n: int) -> int:
    """从 sock 读满 n 字节, 返回实际读取字节数。连接关闭则提前返回。"""
    got = 0
    while got < n:
        chunk = sock.recv(min(n - got, 1 << 20))
        if not chunk:
            break
        got += len(chunk)
    return got


def run_receiver(port: int, sizes: list[int], iters: int, warmup: int):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(1)
    print(f"[net_face/recv] listening on 0.0.0.0:{port} "
          f"sizes(MiB)={[s/MIB for s in sizes]} iters={iters} warmup={warmup}")
    conn, addr = srv.accept()
    with conn:
        print(f"[net_face/recv] sender connected from {addr}")
        # 先收 size 协商 (8 字节小端, 一个 size 一个 size 收 iters+warmup 轮)
        for size_bytes in sizes:
            total_rounds = warmup + iters
            payload = size_bytes  # 网络面 count 固定 1, 每轮一个 size
            for r in range(total_rounds):
                got = recv_all(conn, payload)
                if got != payload:
                    print(f"[net_face/recv] size={size_bytes} round={r} "
                          f"short read {got}/{payload}, sender 可能已断开")
                    conn.close()
                    srv.close()
                    return
            print(f"[net_face/recv] size={size_bytes/MIB:>7.3f} MiB  done")
    srv.close()
    print("[net_face/recv] all done")


def run_sender(host: str, port: int, sizes: list[int], iters: int, warmup: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # 关闭 Nagle, 大块发送更接近裸带宽
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except (AttributeError, OSError):
        pass
    # 加大 socket 发送缓冲, 减少小包握手对大消息测量的干扰
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8 * MIB)
    except OSError:
        pass
    print(f"[net_face/send] connecting {host}:{port} "
          f"sizes(MiB)={[s/MIB for s in sizes]} iters={iters} warmup={warmup}")
    sock.connect((host, port))
    print(f"[net_face/send] connected")

    print("=" * 78)
    print(f"{'size(MiB)':>10} {'payload(MiB)':>13} {'lat_min(ms)':>12} "
          f"{'lat_avg(ms)':>12} {'bw_peak(GiB/s)':>15} {'bw_avg(GiB/s)':>14} "
          f"{'bw_avg(GB/s)':>13}")
    print("-" * 78)

    for size_bytes in sizes:
        payload = size_bytes  # 网络面 count=1
        data = bytes(payload)  # 全零, 内容无所谓

        # warmup (不计入)
        for w in range(warmup):
            sock.sendall(data)
        # 让 receiver 同步对齐 (靠 recv 侧已收满 warmup 即对齐, 无需额外握手)

        latencies = []
        for it in range(iters):
            t0 = time.perf_counter()
            sock.sendall(data)
            t1 = time.perf_counter()
            latencies.append(t1 - t0)

        # 本 size 结束, 稍等 receiver 收完 (receiver 收满即进入下一 size)
        lat_min = min(latencies)
        lat_avg = statistics.fmean(latencies)
        bw_peak_gib = payload / lat_min / GIB
        bw_avg_gib = payload / lat_avg / GIB
        bw_avg_gb = payload / lat_avg / 1e9

        print(f"{size_bytes/MIB:>10.3f} {payload/MIB:>13.3f} "
              f"{lat_min*1e3:>12.4f} {lat_avg*1e3:>12.4f} "
              f"{bw_peak_gib:>15.3f} {bw_avg_gib:>14.3f} {bw_avg_gb:>13.3f}")

    print("=" * 78)
    print("[net_face/send] 解读:")
    print("  - 这是裸 TCP 网络面带宽 (物理上限参考)。")
    print("  - 与 data_face (HCCL) 对比: net_face 应 >= data_face。")
    print("  - 若 net_face 本身低, 查网卡速率/线缆/MTU/RDMA/拓扑。")
    sock.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True, choices=["sender", "receiver"])
    parser.add_argument("--host", default=None,
                        help="sender: receiver 的 IP; receiver: 不用")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument(
        "--size-bytes",
        default="1048576,4194304,16777216,67108864,268435456",
        help="每轮发送字节数, 逗号分隔",
    )
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=5)
    args = parser.parse_args()

    sizes = parse_sizes(args.size_bytes)

    if args.role == "receiver":
        run_receiver(args.port, sizes, args.iters, args.warmup)
    else:
        if not args.host:
            parser.error("sender 角色需要 --host <receiver_ip>")
        run_sender(args.host, args.port, sizes, args.iters, args.warmup)


if __name__ == "__main__":
    main()
