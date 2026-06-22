"""
多 ProcessGroup 单程阻塞测试 —— 接收端 (rank 1)

与 multi_pg_oneway_send.py 配对。
对端创建 num_pgs 个独立的 PG, receiver 也以**相同顺序**创建相同数量的 PG,
然后用 i % num_pgs 选择 PG 来发起 irecv。

⚠️ 重要: dist.new_group 必须在所有 rank 上以严格相同的顺序调用, 否则会死锁。
所以 sender 和 receiver 的 --num-pgs 必须严格一致。

用法 (--size-bytes / --count / --num-pgs 必须与 sender 一致):
    python multi_pg_oneway_recv.py --master-addr 1.1.1.1 --master-port 3004 \
        --size-bytes 4194304 --count 8 --iters 20 --warmup 5
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
    parser.add_argument("--size-bytes", type=int, default=4 * 1024 * 1024)
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--num-pgs", type=int, default=None,
                        help="ProcessGroup 数量, 必须与 sender 一致 (默认 = count)")
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--local-device", type=int, default=0)
    args = parser.parse_args()

    num_pgs = args.num_pgs or args.count

    set_device(args.local_device)

    os.environ["MASTER_ADDR"] = args.master_addr
    os.environ["MASTER_PORT"] = args.master_port
    os.environ["RANK"] = "1"
    os.environ["WORLD_SIZE"] = "2"

    dist.init_process_group(backend=BACKEND, rank=1, world_size=2)

    # 严格按和 sender 相同的顺序创建 PG, 避免死锁
    pgs = []
    for i in range(num_pgs):
        pg = dist.new_group(ranks=[0, 1], backend=BACKEND)
        pgs.append(pg)

    SRC = 0

    DTYPE = torch.float16
    elem = torch.tensor([], dtype=DTYPE).element_size()
    numel = args.size_bytes // elem

    def make_buf():
        return torch.empty(numel, dtype=DTYPE, device=DEVICE)

    def run_one_round():
        bufs = [make_buf() for _ in range(args.count)]
        recv_handles = []
        for i in range(args.count):
            pg = pgs[i % num_pgs]
            recv_handles.append(dist.irecv(bufs[i], src=SRC, group=pg))
        for h in recv_handles:
            h.wait()
        device_synchronize()
        dist.barrier()

    for _ in range(args.warmup):
        run_one_round()
    dist.barrier()

    for _ in range(args.iters):
        device_synchronize()
        dist.barrier()
        run_one_round()

    print(f"[multi_pg_receiver] done. size={args.size_bytes} bytes, "
          f"count={args.count}, PGs={num_pgs}, iters={args.iters}, "
          f"backend={BACKEND}")
    dist.destroy_process_group()


if __name__ == "__main__":
    main()