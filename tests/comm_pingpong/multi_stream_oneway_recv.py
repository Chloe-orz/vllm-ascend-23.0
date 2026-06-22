"""
多 NPU stream 单程阻塞测试 —— 接收端 (rank 1)

与 multi_stream_oneway_send.py 配对。
对端在多 stream 上下文里 isend, receiver 同样把 irecv 提交到对应 stream,
收齐后做一次 ``dist.barrier()`` 作为 ACK。

用法 (--size-bytes / --count / --num-streams 必须与 sender 一致):
    python multi_stream_oneway_recv.py --master-addr 1.1.1.1 --master-port 3004 \
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
    parser.add_argument("--num-streams", type=int, default=None,
                        help="NPU stream 数量 (须与 sender 一致, 默认 = count)")
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--local-device", type=int, default=0)
    args = parser.parse_args()

    num_streams = args.num_streams or args.count

    set_device(args.local_device)

    os.environ["MASTER_ADDR"] = args.master_addr
    os.environ["MASTER_PORT"] = args.master_port
    os.environ["RANK"] = "1"
    os.environ["WORLD_SIZE"] = "2"

    dist.init_process_group(backend=BACKEND, rank=1, world_size=2)

    SRC = 0

    DTYPE = torch.float16
    elem = torch.tensor([], dtype=DTYPE).element_size()
    numel = args.size_bytes // elem

    streams = [torch.npu.Stream() for _ in range(num_streams)]

    def make_buf():
        return torch.empty(numel, dtype=DTYPE, device=DEVICE)

    def run_one_round():
        recv_handles = []
        bufs = []
        for i in range(args.count):
            s = i % num_streams
            with torch.npu.stream(streams[s]):
                buf = make_buf()
                bufs.append(buf)
                recv_handles.append(dist.irecv(buf, src=SRC))
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

    print(f"[multi_stream_receiver] done. size={args.size_bytes} bytes, "
          f"count={args.count}, streams={num_streams}, iters={args.iters}, "
          f"backend={BACKEND}")
    dist.destroy_process_group()


if __name__ == "__main__":
    main()