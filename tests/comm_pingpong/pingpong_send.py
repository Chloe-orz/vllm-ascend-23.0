"""
isend_tensor_dict / irecv_tensor_dict NPU 阻塞测试 —— 发送端 (rank 0)

直接调用 vllm 仓中的 ``GroupCoordinator.isend_tensor_dict /
GroupCoordinator.irecv_tensor_dict``，避免重写实现造成测量偏差。
脚本假设运行环境下 ``import vllm`` 可用 (vllm 已安装到 venv, 或 CWD 在
vllm 根目录上 PYTHONPATH 已加好)。

用法 (在 sender 机器上):
    python pingpong_send.py \
        --master-addr <recv_ip> --master-port 29500 \
        --size-mb 4 --count 4 --iters 20 --warmup 5

观察思路:
    固定 ``--size-mb``，分别跑 ``--count 1,2,3,4,...``，比较 round-trip 耗时。
        若 count=N 的耗时 ≈ N × (count=1 的耗时)  -> HCCL 在 NPU 上串行 (阻塞)
        若 count=N 的耗时 << N × (count=1 的耗时) -> NPU 上可并行/流水

    脚本另外单独打印两项细分时间:
      * ``CPU issue``  : 把 N 个 isend_tensor_dict 全部下发掉的时间。注意:
                          真实实现里每个 isend_tensor_dict 都会先做一次
                          ``send_object`` —— 走 gloo/CPU 组、**同步阻塞**，所以
                          这一项并不是"纯 CPU 排队"时间，里面已经含了 N 次跟
                          对端的握手开销。
      * ``HCCL wait``  : 在 issue 完成之后, 等所有 isend/irecv handle 完成的
                          时间。这一项才反映 NPU 上的 HCCL 串/并行情况。
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

# 必须在 set_device 之后再 import vllm 的并行接口, 因为 GroupCoordinator
# 构造时会依据 current_platform 选择 device 字符串 (npu:i / cuda:i)。
from vllm.distributed.parallel_state import (  # noqa: E402
    init_distributed_environment,
    init_model_parallel_group,
)


def build_tensor_dict(size_mb, dtype=torch.float16, fill=1.0):
    """每个 dict 内放一个 size_mb 大小的 tensor (键名固定, 便于双端 metadata 对齐)。"""
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
    parser.add_argument("--iters", type=int, default=20, help="正式测量轮数")
    parser.add_argument("--warmup", type=int, default=5, help="预热轮数")
    parser.add_argument("--local-device", type=int, default=0)
    args = parser.parse_args()

    set_device(args.local_device)

    # 用 vllm 自己的 init_distributed_environment + init_model_parallel_group,
    # 这样后续 isend_tensor_dict / irecv_tensor_dict 的行为跟生产代码完全一致。
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
        group_name="pingpong",
    )

    DST = 1  # rank_in_group of receiver

    # ----------------------- warmup -----------------------
    for w in range(args.warmup):
        send_dicts = [
            build_tensor_dict(args.size_mb, fill=float(w * 1000 + i))
            for i in range(args.count)
        ]
        send_handles = []
        for td in send_dicts:
            send_handles.extend(group.isend_tensor_dict(td, dst=DST))
        recv_results = [group.irecv_tensor_dict(src=DST)
                        for _ in range(args.count)]
        for _, handles, _ in recv_results:
            for h in handles:
                h.wait()
        for _, _, postprocess in recv_results:
            for fn in postprocess:
                fn()
        for h in send_handles:
            h.wait()
    device_synchronize()
    dist.barrier()

    # ----------------------- measure -----------------------
    issue_times, wait_times, rtt_times = [], [], []
    for it in range(args.iters):
        send_dicts = [
            build_tensor_dict(args.size_mb, fill=float(it * 1000 + i))
            for i in range(args.count)
        ]
        device_synchronize()
        dist.barrier()  # 双端对齐计时起点

        t0 = time.perf_counter()

        # (1) 下发 N 个 isend_tensor_dict。注意每个 call 都会先做一次同步的
        #     send_object(metadata), 所以这段时间并不是纯 CPU 排队时间。
        send_handles = []
        for td in send_dicts:
            send_handles.extend(group.isend_tensor_dict(td, dst=DST))

        # (2) 下发 N 个 irecv_tensor_dict。同样每个 call 会先做一次同步的
        #     recv_object 拿对端的 metadata。
        recv_results = [group.irecv_tensor_dict(src=DST)
                        for _ in range(args.count)]
        t_issue = time.perf_counter()

        # (3) 等所有 handle 完成 —— 这段时间反映的是 NPU 上 HCCL 的串/并行情况。
        for _, handles, _ in recv_results:
            for h in handles:
                h.wait()
        for _, _, postprocess in recv_results:
            for fn in postprocess:
                fn()
        for h in send_handles:
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
    payload = args.size_mb * args.count
    print("=" * 72)
    print(f"[sender] size/tensor = {args.size_mb} MB, count = {args.count}, "
          f"backend = {BACKEND}")
    print(f"[sender] payload per direction = {payload:.2f} MB "
          f"(round-trip = {2*payload:.2f} MB)")
    print("-" * 72)
    print(f"[sender] CPU issue N (incl. {args.count} sync send_object/recv_object):")
    print(f"           avg={iss_a:.3f} ms  p50={iss_p50:.3f}  p90={iss_p90:.3f}  "
          f"min={iss_lo:.3f}  max={iss_hi:.3f}")
    print(f"[sender] HCCL wait (handles + device_synchronize, NPU-side):")
    print(f"           avg={wt_a:.3f} ms   p50={wt_p50:.3f}   p90={wt_p90:.3f}   "
          f"min={wt_lo:.3f}   max={wt_hi:.3f}")
    print(f"[sender] full round-trip:")
    print(f"           avg={rtt_a:.3f} ms  p50={rtt_p50:.3f}  p90={rtt_p90:.3f}  "
          f"min={rtt_lo:.3f}  max={rtt_hi:.3f}")
    print(f"[sender] per-tensor RTT (avg/count) = {rtt_a / args.count:.3f} ms")
    print("=" * 72)

    dist.destroy_process_group()


if __name__ == "__main__":
    main()
