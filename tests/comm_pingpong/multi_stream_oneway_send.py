"""
多 NPU stream 单程阻塞测试 —— 发送端 (rank 0)

使用同一个 ProcessGroup, 但为每个 isend 切换到不同的 NPU stream 后再提交。
检验能否通过多 stream 使 HCCL P2P 在 NPU 上并行。

机制: ``torch.npu.Stream()`` 创建的 stream 与 ProcessGroupHCCL 内部的
comm stream 是两个不同的概念。``dist.isend`` 内部会将 input tensor 的
就绪依赖记录在当前 NPU stream 上, 但最终的 ``hcclSend`` 仍然入列到
ProcessGroupHCCL 内部的 唯一一条 comm stream。

因此猜测: 切换 stream 不影响 HCCL op 的排队位置, NPU send wait 仍串行。
此脚本用于验证这一猜测。

用法:
    python multi_stream_oneway_send.py --master-addr 1.1.1.1 --master-port 3004 \
        --size-bytes 4194304 --count 8 --iters 20 --warmup 5

    --num-streams 默认为 --count, 即各 isend 独享一条 stream。
    也可指定更少的 stream 数量, isend 以 i % num_streams 轮询分配。
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
                        help="每个 tensor 的大小 (字节)")
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--num-streams", type=int, default=None,
                        help="使用的 NPU stream 数量, 默认与 --count 一致。"
                             "isend 按 i %% num_streams 分配")
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--local-device", type=int, default=0)
    args = parser.parse_args()

    num_streams = args.num_streams or args.count

    set_device(args.local_device)

    os.environ["MASTER_ADDR"] = args.master_addr
    os.environ["MASTER_PORT"] = args.master_port
    os.environ["RANK"] = "0"
    os.environ["WORLD_SIZE"] = "2"

    dist.init_process_group(backend=BACKEND, rank=0, world_size=2)

    DST = 1

    DTYPE = torch.float16
    elem = torch.tensor([], dtype=DTYPE).element_size()
    numel = args.size_bytes // elem

    # 创建多个 NPU stream
    streams = [torch.npu.Stream() for _ in range(num_streams)]

    def make_tensor(fill=1.0):
        return torch.full((numel,), fill, dtype=DTYPE, device=DEVICE)

    # ----------------------- warmup -----------------------
    for w in range(args.warmup):
        send_handles = []
        for i in range(args.count):
            s = i % num_streams
            with torch.npu.stream(streams[s]):
                t = make_tensor(fill=float(w * 1000 + i))
                send_handles.append(dist.isend(t, dst=DST))
        for h in send_handles:
            h.wait()
        device_synchronize()
        dist.barrier()
    dist.barrier()

    # ----------------------- measure -----------------------
    issue_ms, send_wait_ms, e2e_ms = [], [], []
    for it in range(args.iters):
        device_synchronize()
        dist.barrier()

        t0 = time.perf_counter()

        send_handles = []
        for i in range(args.count):
            s = i % num_streams
            with torch.npu.stream(streams[s]):
                t = make_tensor(fill=float(it * 1000 + i))
                send_handles.append(dist.isend(t, dst=DST))
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
    print(f"[multi_stream_sender] size={args.size_bytes} bytes, count={args.count}, "
          f"streams={num_streams}, backend={BACKEND}")
    print(f"[multi_stream_sender] total payload one-way = {payload} bytes "
          f"({payload/1024/1024:.3f} MiB)")
    print("-" * 72)
    print(f"[multi_stream_sender] CPU issue ({args.count} isends across "
          f"{num_streams} streams):")
    print(f"           avg={ia:.3f} ms  p50={ip50:.3f}  p90={ip90:.3f}  "
          f"min={ilo:.3f}  max={ihi:.3f}")
    print(f"[multi_stream_sender] NPU send wait:")
    print(f"           avg={sa:.3f} ms  p50={sp50:.3f}  p90={sp90:.3f}  "
          f"min={slo:.3f}  max={shi:.3f}")
    print(f"[multi_stream_sender] end-to-end one-way (incl. ACK barrier):")
    print(f"           avg={ea:.3f} ms  p50={ep50:.3f}  p90={ep90:.3f}  "
          f"min={elo:.3f}  max={ehi:.3f}")
    print(f"[multi_stream_sender] per-tensor send wait (avg/count) = "
          f"{sa / args.count:.3f} ms")
    print("=" * 72)

    dist.destroy_process_group()


if __name__ == "__main__":
    main()