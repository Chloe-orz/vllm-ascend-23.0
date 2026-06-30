"""
isend / irecv 原生接口 NPU 阻塞测试 —— 接收端 (rank 1)

使用 ``torch.distributed.isend / irecv`` 原生接口, 不经 vllm 任何 wrapper。

用法 (注意 --size-bytes / --count 必须与 sender 完全一致):
    python raw_pingpong_recv.py \
        --master-addr <sender_ip> --master-port 3004 \
        --size-bytes 4194304 --count 2 --iters 20 --warmup 5

逻辑:
    1) 用 irecv 收 N 个 tensor (handle.wait)
    2) 全部收齐后, 用 isend 把同样 N 个 tensor 原样发回
       这样 sender 端测出来的就是完整的往返时间。
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
        # 1) 收 N 个
        recv_bufs = [make_empty_buf() for _ in range(args.count)]
        recv_handles = []
        for buf in recv_bufs:
            recv_handles.append(dist.irecv(buf, src=SRC))
        for h in recv_handles:
            h.wait()
        # 2) 原样发回 N 个 (复用收到的 buffer)
        send_handles = []
        for buf in recv_bufs:
            send_handles.append(dist.isend(buf, dst=SRC))
        for h in send_handles:
            h.wait()

    # warmup
    for _ in range(args.warmup):
        run_one_round()
    device_synchronize()
    dist.barrier()

    # measure
    for _ in range(args.iters):
        device_synchronize()
        dist.barrier()
        run_one_round()
        device_synchronize()

    print(f"[raw_receiver] done. size={args.size_bytes} bytes "
          f"({args.size_bytes/1024/1024:.3f} MiB) count={args.count} "
          f"iters={args.iters} backend={BACKEND}  (raw isend/irecv)")
    dist.destroy_process_group()


if __name__ == "__main__":
    main()