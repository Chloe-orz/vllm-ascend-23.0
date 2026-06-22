"""
isend_tensor_dict 单程阻塞测试 —— 接收端 (rank 1)

只 irecv, 不回发, 收齐 N 个后做一次 ``dist.barrier()`` 作为 ACK,
通知 sender "对端 NPU 上数据收齐了"。

用法 (receiver 机器, --size-bytes / --count / --iters / --warmup 必须与 sender 一致):
    python oneway_recv.py \
        --master-addr 1.1.1.1 --master-port 3004 \
        --size-bytes 4194304 --count 2 --iters 20 --warmup 5
"""

import argparse

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--master-addr", required=True)
    parser.add_argument("--master-port", default="29500")
    parser.add_argument("--size-bytes", type=int, default=4 * 1024 * 1024,
                        help="每个 tensor_dict 中 tensor 的大小 (字节, 必须与 sender 一致)")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--local-device", type=int, default=0)
    args = parser.parse_args()

    set_device(args.local_device)

    init_method = f"tcp://{args.master_addr}:{args.master_port}"
    init_distributed_environment(
        world_size=2,
        rank=1,
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

    SRC = 0

    def run_one_round():
        recv_results = [group.irecv_tensor_dict(src=SRC)
                        for _ in range(args.count)]
        for _, handles, _ in recv_results:
            for h in handles:
                h.wait()
        for _, _, postprocess in recv_results:
            for fn in postprocess:
                fn()
        device_synchronize()
        dist.barrier()  # ACK to sender

    # warmup
    for _ in range(args.warmup):
        run_one_round()
    dist.barrier()

    # measure
    for _ in range(args.iters):
        device_synchronize()
        dist.barrier()  # 与 sender 对齐起跑线
        run_one_round()

    print(f"[receiver] done. size={args.size_bytes} bytes "
          f"({args.size_bytes/1024/1024:.3f} MiB) count={args.count} "
          f"iters={args.iters} backend={BACKEND}  (one-way, recv only)")
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
