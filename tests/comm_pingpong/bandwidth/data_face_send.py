"""
数据面 (HCCL) 带宽测试 —— 发送端 (rank 0)

测的是 **HCCL 点对点 isend/irecv 的单端发送带宽** (数据面):
  payload = size_bytes * count
  时间窗 = (起跑 barrier 之后) 发起 isend -> 全部 handle.wait() ->
           device_synchronize() 完成
  带宽 = payload / 时间窗

为什么不测 "网络面": HCCL isend 走的是 HCCl/网卡的 RDMA/TCP 栈, 已含协议开销、
拷贝、ACK 等 —— 这正是 vllm 边云 P2P 通信实际走的路径, 测它得到的带宽就是
**真实推理时数据面能跑到的带宽**, 比 raw TCP 网络面更贴近实战。

设计要点 (避免污染带宽分母):
  - 用 dist.barrier() 对齐每轮起跑线, 但 barrier 不计入时间窗。
  - **不**加 ACK barrier 收尾 (raw_oneway_send 那种 end-to-end 含 ACK 会把
    一次额外往返算进带宽, 偏低)。receiver 端只对称地收齐即可。
  - 大消息走 HCCL rendezvous, sender wait() 完成即数据已到对端, 故 sender
    单端 wait 时间 ≈ 单向传输时间, 带宽 = payload / 该时间。
  - 带宽只由 sender 算并打印 (两端时钟/口径不同会打架); receiver 不算。

带宽口径:
  - GiB/s = payload / time / 1024^3  (二进制, 与显存/内存厂商口径一致)
  - GB/s  = payload / time / 1e9     (十进制, 网络带宽常用)
  - peak  = payload / min(各轮 time)  (最佳, 排除抖动)
  - avg   = payload / mean(各轮 time)

用法 (双机, 两端各一进程):
    # sender (机器A, 假设 A 是 master)
    python data_face_send.py \
        --master-addr <A_ip> --master-port 3004 \
        --size-bytes 1048576,4194304,16777216,67108864,268435456 \
        --count 1 --iters 20 --warmup 5

    # receiver (机器B)
    python data_face_recv.py \
        --master-addr <A_ip> --master-port 3004 \
        --size-bytes 1048576,4194304,16777216,67108864,268435456 \
        --count 1 --iters 20 --warmup 5

注意: --master-addr 两端都填 *sender* IP (PyTorch 约定 master 是 rank0)。
两端 --size-bytes / --count / --iters / --warmup 必须完全一致。
"""

import argparse
import os
import statistics
import time

import torch
import torch.distributed as dist

try:
    import torch_npu  # noqa: F401
    DEVICE = "npu"
    BACKEND = "hccl"

    def device_synchronize():
        torch.npu.synchronize()

    def set_device(i):
        torch.npu.set_device(i)
except ImportError:
    DEVICE = "cuda"
    BACKEND = "nccl"

    def device_synchronize():
        torch.cuda.synchronize()

    def set_device(i):
        torch.cuda.set_device(i)


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--master-addr", required=True)
    parser.add_argument("--master-port", default="29500")
    parser.add_argument(
        "--size-bytes",
        default="1048576,4194304,16777216,67108864,268435456",
        help="每个 tensor 的字节大小, 逗号分隔 (会自动去重排序)",
    )
    parser.add_argument("--count", type=int, default=1,
                        help="一轮里发送的 tensor 个数 (count>1 摊薄 per-tensor 开销)")
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--local-device", type=int, default=0)
    args = parser.parse_args()

    sizes = parse_sizes(args.size_bytes)

    set_device(args.local_device)

    os.environ["MASTER_ADDR"] = args.master_addr
    os.environ["MASTER_PORT"] = args.master_port
    os.environ["RANK"] = "0"
    os.environ["WORLD_SIZE"] = "2"

    dist.init_process_group(backend=BACKEND, rank=0, world_size=2)

    DST = 1
    elem = torch.tensor([], dtype=torch.float16).element_size()

    print("=" * 78)
    print(f"[data_face_send] backend={BACKEND} device={DEVICE} "
          f"count={args.count} iters={args.iters} warmup={args.warmup}")
    print(f"[data_face_send] sizes (MiB) = "
          f"{[s / 1024 / 1024 for s in sizes]}")
    print(f"[data_face_send] 带宽 = payload / (isend_issue..wait_all..sync)")
    print(f"[data_face_send]   payload = size_bytes * count = "
          f"{[s * args.count for s in sizes]} bytes")
    print("=" * 78)
    print(f"{'size(MiB)':>10} {'payload(MiB)':>13} {'lat_min(ms)':>12} "
          f"{'lat_avg(ms)':>12} {'bw_peak(GiB/s)':>15} {'bw_avg(GiB/s)':>14} "
          f"{'bw_avg(GB/s)':>13}")
    print("-" * 78)

    for size_bytes in sizes:
        numel = size_bytes // elem
        payload = size_bytes * args.count

        def make_buf():
            return torch.zeros(numel, dtype=torch.float16, device=DEVICE)

        # ----------------------- warmup -----------------------
        for w in range(args.warmup):
            send_handles = []
            bufs = [make_buf() for _ in range(args.count)]
            for buf in bufs:
                send_handles.append(dist.isend(buf, dst=DST))
            for h in send_handles:
                h.wait()
            device_synchronize()
            dist.barrier()
        dist.barrier()  # 起跑线对齐

        # ----------------------- measure -----------------------
        latencies = []  # 秒
        for it in range(args.iters):
            send_handles = []
            bufs = [make_buf() for _ in range(args.count)]
            # 时间窗: 从开始 issue 到全部 wait + sync 完成。
            # barrier 已在上一轮/起跑线对齐过, 不在窗内。
            t0 = time.perf_counter()
            for buf in bufs:
                send_handles.append(dist.isend(buf, dst=DST))
            for h in send_handles:
                h.wait()
            device_synchronize()
            t1 = time.perf_counter()
            latencies.append(t1 - t0)
            dist.barrier()  # 与 receiver 对齐下一轮起跑线 (不计入时间窗)

        dist.barrier()  # 本 size 结束同步

        lat_min = min(latencies)
        lat_avg = statistics.fmean(latencies)
        bw_peak_gib = payload / lat_min / (1024 ** 3)
        bw_avg_gib = payload / lat_avg / (1024 ** 3)
        bw_avg_gb = payload / lat_avg / 1e9

        print(f"{size_bytes/1024/1024:>10.3f} {payload/1024/1024:>13.3f} "
              f"{lat_min*1e3:>12.4f} {lat_avg*1e3:>12.4f} "
              f"{bw_peak_gib:>15.3f} {bw_avg_gib:>14.3f} {bw_avg_gb:>13.3f}")

    print("=" * 78)
    print("[data_face_send] 解读:")
    print("  - 大消息 (>=16MiB) 的 bw_avg 接近链路极限 = 数据面健康。")
    print("  - 若大消息带宽远低于网络面 (见 net_face_*), 说明 HCCL 栈开销大。")
    print("  - count>1 时 per-tensor 开销被摊薄, 带宽偏高, 勿直接对比 count=1。")
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
