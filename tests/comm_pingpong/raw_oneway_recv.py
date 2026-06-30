"""
irecv 原生接口单程阻塞测试 —— 接收端 (rank 1)

使用 ``torch.distributed.irecv`` 原生接口, 不经 vllm 任何 wrapper。
只收不回发, 收齐 N 个后做一次 ``dist.barrier()`` 作为 ACK,
通知 sender "对端 NPU 上数据收齐了"。

用法 (--size-bytes / --count / --iters / --warmup 必须与 sender 一致):
    python raw_oneway_recv.py \
        --master-addr 1.1.1.1 --master-port 3004 \
        --size-bytes 4194304 --count 2 --iters 20 --warmup 5
"""

import argparse
import os

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
                        help="每个 tensor 的大小 (字节, 必须与 sender 一致)")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--local-device", type=int, default=0)
    args = parser.parse_args()

    set_device(args.local_device)

    os.environ["MASTER_ADDR"] = args.master_addr
    os.environ["MASTER_PORT"] = args.master_port
    os.environ["RANK"] = "1"
    os.environ["WORLD_SIZE"] = "2"

    dist.init_process_group(backend=BACKEND, rank=1, world_size=2)

    SRC = 0

    def make_empty_buf():
        elem = torch.tensor([], dtype=torch.float16).element_size()
        numel = args.size_bytes // elem
        return torch.empty(numel, dtype=torch.float16, device=DEVICE)

    def run_one_round():
        recv_bufs = [make_empty_buf() for _ in range(args.count)]
        recv_handles = []
        for buf in recv_bufs:
            recv_handles.append(dist.irecv(buf, src=SRC))
        for h in recv_handles:
            h.wait()
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

    print(f"[raw_receiver] done. size={args.size_bytes} bytes "
          f"({args.size_bytes/1024/1024:.3f} MiB) count={args.count} "
          f"iters={args.iters} backend={BACKEND}  (raw irecv, one-way, recv only)")
    dist.destroy_process_group()


if __name__ == "__main__":
    main()