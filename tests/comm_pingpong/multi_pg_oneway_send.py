"""
多 ProcessGroup 单程阻塞测试 —— 发送端 (rank 0)

为每个 isend 创建独立的 ProcessGroupHCCL (每个 PG 内部有独立的
hcclComm_t + 独立的 internal P2P stream), N 个 isend 提交到 N 个不同的 PG,
让 HCCL P2P 在 NPU 上真正并行。

这是 README 中 "方案 B (多 PG 轮询)" 的实测。

预期: NPU send wait 从 N × per_op_RTT 下降到接近 per_op_RTT
(N 个 isend 完全并行), 受限于物理链路带宽。

代价: 每个 PG 会建链 + 预分配 HCCL buffer, 启动慢一些, 显存占用增大。

用法:
    python multi_pg_oneway_send.py --master-addr 1.1.1.1 --master-port 3004 \
        --size-bytes 4194304 --count 8 --iters 20 --warmup 5

    --num-pgs 默认 = --count, 即每个 isend 独享一个 PG。
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
    parser.add_argument("--size-bytes", type=int, default=4 * 1024 * 1024)
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--num-pgs", type=int, default=None,
                        help="ProcessGroup 数量, 默认与 --count 一致。"
                             "isend 按 i %% num_pgs 分配")
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--local-device", type=int, default=0)
    args = parser.parse_args()

    num_pgs = args.num_pgs or args.count

    set_device(args.local_device)

    os.environ["MASTER_ADDR"] = args.master_addr
    os.environ["MASTER_PORT"] = args.master_port
    os.environ["RANK"] = "0"
    os.environ["WORLD_SIZE"] = "2"

    # 先 init 默认 world group, 之后 new_group 才能工作
    dist.init_process_group(backend=BACKEND, rank=0, world_size=2)

    # 创建 N 个独立的子 PG, 每个都包含 rank 0 和 rank 1
    # 注意: torch.distributed.new_group 必须在所有 rank 上以相同顺序调用,
    # 否则会死锁。双端都创建 num_pgs 个 [0, 1] group。
    pgs = []
    for i in range(num_pgs):
        pg = dist.new_group(ranks=[0, 1], backend=BACKEND)
        pgs.append(pg)

    DST = 1

    DTYPE = torch.float16
    elem = torch.tensor([], dtype=DTYPE).element_size()
    numel = args.size_bytes // elem

    def make_tensor(fill=1.0):
        return torch.full((numel,), fill, dtype=DTYPE, device=DEVICE)

    # ----------------------- warmup -----------------------
    for w in range(args.warmup):
        send_handles = []
        for i in range(args.count):
            pg = pgs[i % num_pgs]
            t = make_tensor(fill=float(w * 1000 + i))
            send_handles.append(dist.isend(t, dst=DST, group=pg))
        for h in send_handles:
            h.wait()
        device_synchronize()
        dist.barrier()  # global barrier as ACK
    dist.barrier()

    # ----------------------- measure -----------------------
    issue_ms, send_wait_ms, e2e_ms = [], [], []
    for it in range(args.iters):
        device_synchronize()
        dist.barrier()

        t0 = time.perf_counter()

        send_handles = []
        for i in range(args.count):
            pg = pgs[i % num_pgs]
            t = make_tensor(fill=float(it * 1000 + i))
            send_handles.append(dist.isend(t, dst=DST, group=pg))
        t_issue = time.perf_counter()

        for h in send_handles:
            h.wait()
        device_synchronize()
        t_send_done = time.perf_counter()

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
    print(f"[multi_pg_sender] size={args.size_bytes} bytes, count={args.count}, "
          f"PGs={num_pgs}, backend={BACKEND}")
    print(f"[multi_pg_sender] total payload one-way = {payload} bytes "
          f"({payload/1024/1024:.3f} MiB)")
    print("-" * 72)
    print(f"[multi_pg_sender] CPU issue ({args.count} isends across "
          f"{num_pgs} PGs):")
    print(f"           avg={ia:.3f} ms  p50={ip50:.3f}  p90={ip90:.3f}  "
          f"min={ilo:.3f}  max={ihi:.3f}")
    print(f"[multi_pg_sender] NPU send wait (handles + device_synchronize):")
    print(f"           avg={sa:.3f} ms  p50={sp50:.3f}  p90={sp90:.3f}  "
          f"min={slo:.3f}  max={shi:.3f}")
    print(f"[multi_pg_sender] end-to-end one-way (incl. ACK barrier):")
    print(f"           avg={ea:.3f} ms  p50={ep50:.3f}  p90={ep90:.3f}  "
          f"min={elo:.3f}  max={ehi:.3f}")
    print(f"[multi_pg_sender] per-tensor send wait (avg/count) = "
          f"{sa / args.count:.3f} ms")
    print("=" * 72)

    dist.destroy_process_group()


if __name__ == "__main__":
    main()