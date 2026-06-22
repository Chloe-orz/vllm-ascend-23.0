"""
isend_tensor_dict 单程阻塞测试 —— 发送端 (rank 0)

直接调用 vllm 仓中的 ``GroupCoordinator.isend_tensor_dict``，与生产代码一致。
脚本假设 ``import vllm`` 可用 (vllm 已 pip install 到 venv, 或 CWD 在 vllm
仓根目录上 PYTHONPATH 已加好)。

用法 (sender 机器):
    python oneway_send.py \
        --master-addr 1.1.1.1 --master-port 3004 \
        --size-mb 4 --count 2 --iters 20 --warmup 5

与 ping-pong 版的区别:
    * receiver 只收不回发, 所以本脚本测的是 *单程* 的 send 时间。
    * receiver 收齐 N 个后会做一次 ``dist.barrier()`` 作为 ACK,
      sender 用这次 barrier 判定 "对端 NPU 上也收齐了"。

输出三段时间:
    * ``CPU issue``       : 把 N 个 isend_tensor_dict 全部下发完的时间
                             (含 N 次同步的 send_object metadata 握手)。
    * ``NPU send wait``   : isend handle.wait() + device_synchronize 的时间,
                             代表 **本端 NPU 上 send 操作的完成时间**。
                             这一项最适合回答 "NPU 是否串行" 的问题。
    * ``end-to-end 1-way``: send wait 结束之后再做一次 barrier (ACK),
                             代表数据真正到达对端 NPU 所花的端到端单程时间。
"""

import argparse
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

from vllm.distributed.parallel_state import (  # noqa: E402
    init_distributed_environment,
    init_model_parallel_group,
)


def build_tensor_dict(size_mb, dtype=torch.float16, fill=1.0):
    elem = torch.tensor([], dtype=dtype).element_size()
    numel = int(size_mb * 1024 * 1024 / elem)
    return {"data": torch.full((numel,), fill, dtype=dtype, device=DEVICE)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--master-addr", required=True)
    parser.add_argument("--master-port", default="29500")
    parser.add_argument("--size-mb", type=float, default=4.0,
                        help="每个 tensor_dict 中 tensor 的大小 (MB)")
    parser.add_argument("--count", type=int, default=1,
                        help="一轮里发送的 tensor_dict 个数")
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--local-device", type=int, default=0)
    args = parser.parse_args()

    set_device(args.local_device)

    init_method = f"tcp://{args.master_addr}:{args.master_port}"
    init_distributed_environment(
        world_size=2,
        rank=0,
        distributed_init_method=init_method,
        local_rank=args.local_device,
        backend=BACKEND,
    )
    group = init_model_parallel_group(
        group_ranks=[[0, 1]],
        local_rank=args.local_device,
        backend=BACKEND,
        group_name="oneway",
    )

    DST = 1

    # ----------------------- warmup -----------------------
    for w in range(args.warmup):
        send_dicts = [
            build_tensor_dict(args.size_mb, fill=float(w * 1000 + i))
            for i in range(args.count)
        ]
        send_handles = []
        for td in send_dicts:
            send_handles.extend(group.isend_tensor_dict(td, dst=DST))
        for h in send_handles:
            h.wait()
        device_synchronize()
        dist.barrier()  # ACK from receiver
    dist.barrier()

    # ----------------------- measure -----------------------
    issue_ms, send_wait_ms, e2e_ms = [], [], []
    for it in range(args.iters):
        send_dicts = [
            build_tensor_dict(args.size_mb, fill=float(it * 1000 + i))
            for i in range(args.count)
        ]
        device_synchronize()
        dist.barrier()  # 双端对齐起跑线

        t0 = time.perf_counter()

        # (1) 下发 N 个 isend_tensor_dict
        send_handles = []
        for td in send_dicts:
            send_handles.extend(group.isend_tensor_dict(td, dst=DST))
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
    payload = args.size_mb * args.count
    print("=" * 72)
    print(f"[sender] size/tensor = {args.size_mb} MB, count = {args.count}, "
          f"backend = {BACKEND}  (one-way, send only)")
    print(f"[sender] payload one-way = {payload:.2f} MB")
    print("-" * 72)
    print(f"[sender] CPU issue N (incl. {args.count} sync send_object):")
    print(f"           avg={ia:.3f} ms  p50={ip50:.3f}  p90={ip90:.3f}  "
          f"min={ilo:.3f}  max={ihi:.3f}")
    print(f"[sender] NPU send wait (handles + device_synchronize, NPU send-side):")
    print(f"           avg={sa:.3f} ms  p50={sp50:.3f}  p90={sp90:.3f}  "
          f"min={slo:.3f}  max={shi:.3f}")
    print(f"[sender] end-to-end one-way (incl. ACK barrier):")
    print(f"           avg={ea:.3f} ms  p50={ep50:.3f}  p90={ep90:.3f}  "
          f"min={elo:.3f}  max={ehi:.3f}")
    print(f"[sender] per-tensor send wait (avg/count) = {sa / args.count:.3f} ms")
    print("=" * 72)

    dist.destroy_process_group()


if __name__ == "__main__":
    main()
