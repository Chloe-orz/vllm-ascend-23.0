"""
数据面带宽测试 —— 接收端 (rank 1, HCCL)

与 data_face_send.py 配对。receiver 端对称地 irecv N 个 -> wait 全部 ->
device_synchronize()。两端通过 dist.barrier() 对齐起跑线 (不计入带宽分母),
但 **不** 用 ACK barrier 污染测量 —— 带宽由 sender 端算出并打印, receiver
端只需保证收齐即可, 不单独算带宽 (否则两端时钟/口径不同会打架)。

用法 (双机, 两端各一进程):
    python data_face_recv.py \
        --master-addr <sender_ip> --master-port 3004 \
        --size-bytes 1048576,4194304,16777216,67108864,268435456 \
        --count 1 --iters 20 --warmup 5

注意: --master-addr 两端都填 *sender* IP (PyTorch 约定 master 是 rank0)。
--size-bytes / --count / --iters / --warmup 必须与 sender 完全一致。
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


def parse_sizes(raw: str) -> list[int]:
    out = []
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            continue
        out.append(int(tok))
    seen = set()
    uniq = []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--master-addr", required=True)
    parser.add_argument("--master-port", default="29500")
    parser.add_argument(
        "--size-bytes",
        default="1048576,4194304,16777216,67108864,268435456",
        help="每个 tensor 的字节大小, 逗号分隔, 必须与 sender 一致",
    )
    parser.add_argument("--count", type=int, default=1,
                        help="一轮里接收的 tensor 个数, 与 sender 一致")
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--local-device", type=int, default=0)
    args = parser.parse_args()

    sizes = parse_sizes(args.size_bytes)

    set_device(args.local_device)

    os.environ["MASTER_ADDR"] = args.master_addr
    os.environ["MASTER_PORT"] = args.master_port
    os.environ["RANK"] = "1"
    os.environ["WORLD_SIZE"] = "2"

    dist.init_process_group(backend=BACKEND, rank=1, world_size=2)

    SRC = 0

    print("=" * 78)
    print(f"[data_face_recv] backend={BACKEND} device={DEVICE} "
          f"count={args.count} iters={args.iters} warmup={args.warmup}")
    print(f"[data_face_recv] sizes (MiB) = "
          f"{[s / 1024 / 1024 for s in sizes]}")
    print("=" * 78)

    for size_bytes in sizes:
        elem = torch.tensor([], dtype=torch.float16).element_size()
        numel = size_bytes // elem

        def make_empty_buf():
            return torch.empty(numel, dtype=torch.float16, device=DEVICE)

        # ----------------------- warmup -----------------------
        for w in range(args.warmup):
            recv_handles = []
            bufs = [make_empty_buf() for _ in range(args.count)]
            for buf in bufs:
                recv_handles.append(dist.irecv(buf, src=SRC))
            for h in recv_handles:
                h.wait()
            device_synchronize()
            dist.barrier()
        dist.barrier()

        # ----------------------- measure -----------------------
        # receiver 只需对称地收齐; 带宽由 sender 端计算打印。
        # 同样不用 ACK barrier 污染, 只用 barrier 对齐起跑线。
        for it in range(args.iters):
            recv_handles = []
            bufs = [make_empty_buf() for _ in range(args.count)]
            for buf in bufs:
                recv_handles.append(dist.irecv(buf, src=SRC))
            for h in recv_handles:
                h.wait()
            device_synchronize()
            dist.barrier()  # 与 sender 的对齐 barrier 配对

        dist.barrier()  # 本 size 结束同步
        print(f"[data_face_recv] size={size_bytes/1024/1024:>7.3f} MiB  done")

    print("=" * 78)
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
