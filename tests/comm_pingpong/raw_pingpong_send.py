"""
isend / irecv 原生接口 NPU 阻塞测试 —— 发送端 (rank 0)

使用 ``torch.distributed.isend / irecv`` 原生接口直接发送/接收 tensor，
跳过 vllm 的 ``GroupCoordinator.isend_tensor_dict`` 中的 metadata 握手
(send_object / recv_object)、TensorMetadata 拆分、all-gather 优化等中间层，
直接触及底层 HCCL / NCCL ProcessGroup 的 P2P 行为。

如果原生版本也是串行的，则串行原因在 HCCL ProcessGroup 内部，与 vllm
的 metadata 握手无关；如果原生版本能并行，则说明瓶颈在 vllm 的同步握手阶段。

用法:
    python raw_pingpong_send.py \
        --master-addr <sender_ip> --master-port 3004 \
        --size-bytes 4194304 --count 2 --iters 20 --warmup 5

输出三段时间（与 pingpong_send.py 格式一致）:
    * ``CPU issue``      : N 个 isend + N 个 irecv 的下发时间
                            (无 metadata 握手, 纯排队入列)
    * ``HCCL wait``      : 所有 handle wait + device_synchronize,
                            代表 NPU 上 HCCL 的串/并行行为
    * ``full round-trip``: 端到端 RTT
"""

import argparse
import os
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--master-addr", required=True)
    parser.add_argument("--master-port", default="29500")
    parser.add_argument("--size-bytes", type=int, default=4 * 1024 * 1024,
                        help="每个 tensor 的大小 (字节, 默认 4 MiB = 4194304)")
    parser.add_argument("--count", type=int, default=1,
                        help="一轮里发送/接收的 tensor 个数")
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--local-device", type=int, default=0)
    args = parser.parse_args()

    set_device(args.local_device)

    os.environ["MASTER_ADDR"] = args.master_addr
    os.environ["MASTER_PORT"] = args.master_port
    os.environ["RANK"] = "0"
    os.environ["WORLD_SIZE"] = "2"

    dist.init_process_group(backend=BACKEND, rank=0, world_size=2)

    DST = 1

    def make_tensor(fill=1.0):
        elem = torch.tensor([], dtype=torch.float16).element_size()
        numel = args.size_bytes // elem
        return torch.full((numel,), fill, dtype=torch.float16, device=DEVICE)

    def make_empty_buf():
        """接收用的 buffer, 跟 make_tensor 同样 shape / dtype / device。"""
        elem = torch.tensor([], dtype=torch.float16).element_size()
        numel = args.size_bytes // elem
        return torch.empty(numel, dtype=torch.float16, device=DEVICE)

    # ----------------------- warmup -----------------------
    for w in range(args.warmup):
        # send N
        send_handles = []
        for i in range(args.count):
            t = make_tensor(fill=float(w * 1000 + i))
            send_handles.append(dist.isend(t, dst=DST))
        # recv N
        recv_bufs = [make_empty_buf() for _ in range(args.count)]
        recv_handles = []
        for buf in recv_bufs:
            recv_handles.append(dist.irecv(buf, src=DST))
        for h in send_handles + recv_handles:
            h.wait()
    device_synchronize()
    dist.barrier()

    # ----------------------- measure -----------------------
    issue_times, wait_times, rtt_times = [], [], []
    for it in range(args.iters):
        device_synchronize()
        dist.barrier()

        t0 = time.perf_counter()

        # (1) 下发 N 个 isend —— 无 metadata 握手
        send_handles = []
        for i in range(args.count):
            t = make_tensor(fill=float(it * 1000 + i))
            send_handles.append(dist.isend(t, dst=DST))

        # (2) 下发 N 个 irecv
        recv_bufs = [make_empty_buf() for _ in range(args.count)]
        recv_handles = []
        for buf in recv_bufs:
            recv_handles.append(dist.irecv(buf, src=DST))
        t_issue = time.perf_counter()

        # (3) 等所有 handle 完成
        for h in send_handles + recv_handles:
            h.wait()
        device_synchronize()
        t1 = time.perf_counter()

        issue_times.append((t_issue - t0) * 1000)
        wait_times.append((t1 - t_issue) * 1000)
        rtt_times.append((t1 - t0) * 1000)

    def stats(xs):
        xs_sorted = sorted(xs)
        avg = sum(xs) / len(xs)
        p50 = xs_sorted[len(xs) // 2]
        p90 = xs_sorted[int(len(xs) * 0.9)]
        return avg, p50, p90, min(xs), max(xs)

    rtt_a, rtt_p50, rtt_p90, rtt_lo, rtt_hi = stats(rtt_times)
    iss_a, iss_p50, iss_p90, iss_lo, iss_hi = stats(issue_times)
    wt_a,  wt_p50,  wt_p90,  wt_lo,  wt_hi  = stats(wait_times)
    payload = args.size_bytes * args.count
    print("=" * 72)
    print(f"[raw_sender] size/tensor = {args.size_bytes} bytes "
          f"({args.size_bytes/1024/1024:.3f} MiB), count = {args.count}, "
          f"backend = {BACKEND}   (raw isend/irecv, no vllm wrapper)")
    print(f"[raw_sender] payload per direction = {payload} bytes "
          f"({payload/1024/1024:.3f} MiB)  "
          f"(round-trip = {2*payload} bytes / {2*payload/1024/1024:.3f} MiB)")
    print("-" * 72)
    print(f"[raw_sender] CPU issue N (no metadata handshake):")
    print(f"           avg={iss_a:.3f} ms  p50={iss_p50:.3f}  p90={iss_p90:.3f}  "
          f"min={iss_lo:.3f}  max={iss_hi:.3f}")
    print(f"[raw_sender] HCCL wait (handles + device_synchronize, NPU-side):")
    print(f"           avg={wt_a:.3f} ms   p50={wt_p50:.3f}   p90={wt_p90:.3f}   "
          f"min={wt_lo:.3f}   max={wt_hi:.3f}")
    print(f"[raw_sender] full round-trip:")
    print(f"           avg={rtt_a:.3f} ms  p50={rtt_p50:.3f}  p90={rtt_p90:.3f}  "
          f"min={rtt_lo:.3f}  max={rtt_hi:.3f}")
    print(f"[raw_sender] per-tensor RTT (avg/count) = {rtt_a / args.count:.3f} ms")
    print("=" * 72)

    dist.destroy_process_group()


if __name__ == "__main__":
    main()