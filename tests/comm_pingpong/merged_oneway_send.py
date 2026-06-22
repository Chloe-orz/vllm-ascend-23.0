"""
isend 合并发送单程阻塞测试 —— 发送端 (rank 0)

在 raw_oneway_send.py 基础上加入 ``--merge`` 参数: 把 ``--merge`` 个 size_bytes
的逻辑 tensor 拼成一个大 tensor, 一次性 isend 发出去, 共发 count/merge 次。
对端按相同布局收完后再 split 回 merge 个逻辑 tensor。

用法 (sender 机器):
    # 发 8 个 4 MiB tensor, 一个个发 (8 次 isend) —— 等价于 raw_oneway
    python merged_oneway_send.py --master-addr 1.1.1.1 --master-port 3004 \
        --size-bytes 4194304 --count 8 --merge 1 --iters 20

    # 发 8 个 4 MiB tensor, 每 4 个合并成 1 个发 (2 次 isend)
    python merged_oneway_send.py --master-addr 1.1.1.1 --master-port 3004 \
        --size-bytes 4194304 --count 8 --merge 4 --iters 20

    # 发 8 个 4 MiB tensor, 一次性全部合并 (1 次 isend)
    python merged_oneway_send.py --master-addr 1.1.1.1 --master-port 3004 \
        --size-bytes 4194304 --count 8 --merge 8 --iters 20

观察思路:
    固定 ``--size-bytes`` 和 ``--count``, 调整 ``--merge``, 比较 NPU send wait:
        merge=1 → count 次 isend (基线, 串行成本 = count × per-op RTT)
        merge=k → count/k 次 isend (NPU 上付 count/k × per-op RTT + 同样的数据传输时间)
    数据传输总量没变, 但减少的是 协议 RTT 次数。

约束:
    --count 必须能被 --merge 整除 (脚本会校验)。

输出三段时间 (与 raw_oneway_send.py 格式一致):
    * ``CPU issue``       : count/merge 次 isend 的下发时间
    * ``NPU send wait``   : isend handle.wait() + device_synchronize,
                             代表本端 NPU 上 send 操作的完成时间。
                             合并后这一项应该明显下降。
    * ``end-to-end 1-way``: send wait + ACK barrier, 单程端到端时间。
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
                        help="每个逻辑 tensor 的大小 (字节, 默认 4 MiB = 4194304)")
    parser.add_argument("--count", type=int, default=8,
                        help="总共发送的逻辑 tensor 个数")
    parser.add_argument("--merge", type=int, default=1,
                        help="每多少个逻辑 tensor 合并成 1 次 isend "
                             "(--count 必须能被 --merge 整除)")
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--local-device", type=int, default=0)
    args = parser.parse_args()

    if args.count % args.merge != 0:
        raise SystemExit(
            f"--count ({args.count}) 必须能被 --merge ({args.merge}) 整除"
        )

    num_sends = args.count // args.merge
    merged_bytes = args.size_bytes * args.merge

    set_device(args.local_device)

    os.environ["MASTER_ADDR"] = args.master_addr
    os.environ["MASTER_PORT"] = args.master_port
    os.environ["RANK"] = "0"
    os.environ["WORLD_SIZE"] = "2"

    dist.init_process_group(backend=BACKEND, rank=0, world_size=2)

    DST = 1

    DTYPE = torch.float16
    elem = torch.tensor([], dtype=DTYPE).element_size()
    # 每个 "逻辑 tensor" 的 numel
    sub_numel = args.size_bytes // elem
    # 合并后每次发送的 numel
    merged_numel = merged_bytes // elem

    def make_merged_tensor(round_idx: int, send_idx: int) -> torch.Tensor:
        """造一个合并后的大 tensor, 内部包含 merge 个逻辑 sub-tensor 拼接。

        sub-tensor 之间用不同 fill 值, 方便对端 split 后校验顺序 / 内容是否对齐。
        """
        parts = []
        for k in range(args.merge):
            # 全局逻辑 idx = send_idx * merge + k
            global_idx = send_idx * args.merge + k
            fill = float(round_idx * 1_000_000 + global_idx)
            parts.append(torch.full((sub_numel,), fill, dtype=DTYPE, device=DEVICE))
        return torch.cat(parts, dim=0)  # shape: (merged_numel,)

    # ----------------------- warmup -----------------------
    for w in range(args.warmup):
        send_handles = []
        for s in range(num_sends):
            t = make_merged_tensor(round_idx=w, send_idx=s)
            send_handles.append(dist.isend(t, dst=DST))
        for h in send_handles:
            h.wait()
        device_synchronize()
        dist.barrier()  # ACK
    dist.barrier()

    # ----------------------- measure -----------------------
    issue_ms, send_wait_ms, e2e_ms = [], [], []
    for it in range(args.iters):
        device_synchronize()
        dist.barrier()  # 双端对齐起跑线

        t0 = time.perf_counter()

        # (1) 下发 num_sends 次 isend, 每次发 merged_bytes
        send_handles = []
        for s in range(num_sends):
            t = make_merged_tensor(round_idx=it, send_idx=s)
            send_handles.append(dist.isend(t, dst=DST))
        t_issue = time.perf_counter()

        # (2) 等所有 send 在本端 NPU 上完成
        for h in send_handles:
            h.wait()
        device_synchronize()
        t_send_done = time.perf_counter()

        # (3) 等对端确认收齐
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
    total_payload = args.size_bytes * args.count
    print("=" * 72)
    print(f"[merged_sender] logical size = {args.size_bytes} bytes "
          f"({args.size_bytes/1024/1024:.3f} MiB), count = {args.count}, "
          f"merge = {args.merge}")
    print(f"[merged_sender] effective: {num_sends} isend(s) of "
          f"{merged_bytes} bytes ({merged_bytes/1024/1024:.3f} MiB) each, "
          f"backend = {BACKEND}")
    print(f"[merged_sender] total payload one-way = {total_payload} bytes "
          f"({total_payload/1024/1024:.3f} MiB)")
    print("-" * 72)
    print(f"[merged_sender] CPU issue ({num_sends} isends, no metadata):")
    print(f"           avg={ia:.3f} ms  p50={ip50:.3f}  p90={ip90:.3f}  "
          f"min={ilo:.3f}  max={ihi:.3f}")
    print(f"[merged_sender] NPU send wait (handles + device_synchronize):")
    print(f"           avg={sa:.3f} ms  p50={sp50:.3f}  p90={sp90:.3f}  "
          f"min={slo:.3f}  max={shi:.3f}")
    print(f"[merged_sender] end-to-end one-way (incl. ACK barrier):")
    print(f"           avg={ea:.3f} ms  p50={ep50:.3f}  p90={ep90:.3f}  "
          f"min={elo:.3f}  max={ehi:.3f}")
    print(f"[merged_sender] per-logical-tensor send wait "
          f"(avg/count) = {sa / args.count:.3f} ms")
    print(f"[merged_sender] per-isend send wait "
          f"(avg/num_sends) = {sa / num_sends:.3f} ms")
    print("=" * 72)

    dist.destroy_process_group()


if __name__ == "__main__":
    main()