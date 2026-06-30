"""
isend 原生接口单程阻塞测试 —— 发送端 (rank 0)

使用 ``torch.distributed.isend`` 原生接口, 不经 vllm 任何 wrapper。
receiver 只收不回发, 收齐 N 个后做一次 ``dist.barrier()`` 作为 ACK。

用法:
    python raw_oneway_send.py \
        --master-addr 1.1.1.1 --master-port 3004 \
        --size-bytes 4194304 --count 2 --iters 20 --warmup 5

与 raw_pingpong_send.py 的区别:
    * receiver 只收不回发, 测的是 *单程* send 时间。
    * receiver 收齐后做一次 dist.barrier() 作为 ACK,
      sender 用这次 barrier 判定 "对端 NPU 上数据收齐了"。

输出三段时间 (与 oneway_send.py 格式一致):
    * ``CPU issue``       : N 个 isend 的下发时间 (无 metadata 握手)
    * ``NPU send wait``   : isend handle.wait() + device_synchronize,
                             代表本端 NPU 上 send 操作的完成时间。
                             这一项最适合回答 "NPU 是否串行" 的问题。
    * ``end-to-end 1-way``: send wait 结束之后再做一次 barrier (ACK),
                             代表数据真正到达对端 NPU 的端到端单程时间。
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
                        help="一轮里发送的 tensor 个数")
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

    # ----------------------- warmup -----------------------
    for w in range(args.warmup):
        send_handles = []
        for i in range(args.count):
            t = make_tensor(fill=float(w * 1000 + i))
            send_handles.append(dist.isend(t, dst=DST))
        for h in send_handles:
            h.wait()
        device_synchronize()
        dist.barrier()  # ACK from receiver
    dist.barrier()

    # ----------------------- measure -----------------------
    issue_ms, send_wait_ms, e2e_ms = [], [], []
    for it in range(args.iters):
        device_synchronize()
        dist.barrier()  # 双端对齐起跑线

        t0 = time.perf_counter()

        # (1) 下发 N 个 isend
        send_handles = []
        for i in range(args.count):
            t = make_tensor(fill=float(it * 1000 + i))
            send_handles.append(dist.isend(t, dst=DST))
        t_issue = time.perf_counter()

        # (2) 等所有 send 在本端 NPU 上完成
        for h in send_handles:
            h.wait()
        device_synchronize()
        t_send_done = time.perf_counter()

        # (3) 等对端确认收齐 (ACK barrier)
        dist.barrier()
        t1 = time.perf_counter()

        issue_ms.append((t_issue - t0) * 1000)
        send_wait_ms.append((t_send_done - t_issue) * 1000)
        e2e_ms.append((t1 - t0) * 1000)

    def stats(xs):
        xs_sorted = sorted(xs)
        avg = sum(xs) / len(xs)
        p50 = xs_sorted[len(xs) // 2]
        p90 = xs_sorted[int(len(xs) * 0.9)]
        return avg, p50, p90, min(xs), max(xs)

    ia, ip50, ip90, ilo, ihi = stats(issue_ms)
    sa, sp50, sp90, slo, shi = stats(send_wait_ms)
    ea, ep50, ep90, elo, ehi = stats(e2e_ms)
    payload = args.size_bytes * args.count
    print("=" * 72)
    print(f"[raw_sender] size/tensor = {args.size_bytes} bytes "
          f"({args.size_bytes/1024/1024:.3f} MiB), count = {args.count}, "
          f"backend = {BACKEND}  (raw isend, one-way, send only)")
    print(f"[raw_sender] payload one-way = {payload} bytes "
          f"({payload/1024/1024:.3f} MiB)")
    print("-" * 72)
    print(f"[raw_sender] CPU issue N (no metadata handshake):")
    print(f"           avg={ia:.3f} ms  p50={ip50:.3f}  p90={ip90:.3f}  "
          f"min={ilo:.3f}  max={ihi:.3f}")
    print(f"[raw_sender] NPU send wait (handles + device_synchronize, NPU send-side):")
    print(f"           avg={sa:.3f} ms  p50={sp50:.3f}  p90={sp90:.3f}  "
          f"min={slo:.3f}  max={shi:.3f}")
    print(f"[raw_sender] end-to-end one-way (incl. ACK barrier):")
    print(f"           avg={ea:.3f} ms  p50={ep50:.3f}  p90={ep90:.3f}  "
          f"min={elo:.3f}  max={ehi:.3f}")
    print(f"[raw_sender] per-tensor send wait (avg/count) = {sa / args.count:.3f} ms")
    print("=" * 72)

    dist.destroy_process_group()


if __name__ == "__main__":
    main()