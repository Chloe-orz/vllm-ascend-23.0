"""
isend_tensor_dict / irecv_tensor_dict NPU 阻塞测试 —— 接收端 (rank 1)

用法 (在 receiver 机器上, 注意 --size-mb / --count 必须与 sender 完全一致):
    python pingpong_recv.py \
        --master-addr <recv_ip> --master-port 29500 \
        --size-mb 4 --count 4 --iters 20 --warmup 5

逻辑:
    1) 用 irecv_tensor_dict 收 N 个 dict
    2) 全部收齐后, 再用 isend_tensor_dict 把同样 N 个 dict 原样发回
       这样 sender 端测出来的就是完整的往返时间。
"""

import argparse
import os

import torch
import torch.distributed as dist

try:
    import torch_npu  # noqa: F401
    DEVICE = "npu"
    def device_synchronize():
        torch.npu.synchronize()
    def set_device(i):
        torch.npu.set_device(i)
    BACKEND = "hccl"
except ImportError:
    DEVICE = "cuda"
    def device_synchronize():
        torch.cuda.synchronize()
    def set_device(i):
        torch.cuda.set_device(i)
    BACKEND = "nccl"


def isend_tensor_dict(tensor_dict, dst, group=None):
    works = []
    for key in sorted(tensor_dict.keys()):
        t = tensor_dict[key].contiguous()
        works.append(dist.isend(t, dst=dst, group=group))
    return works


def irecv_tensor_dict(template_dict, src, group=None):
    out, works = {}, []
    for key in sorted(template_dict.keys()):
        buf = torch.empty_like(template_dict[key])
        works.append(dist.irecv(buf, src=src, group=group))
        out[key] = buf
    return out, works


def build_tensor_dict(size_mb, dtype=torch.float16, fill=0.0):
    elem = torch.tensor([], dtype=dtype).element_size()
    numel = int(size_mb * 1024 * 1024 / elem)
    return {"data": torch.full((numel,), fill, dtype=dtype, device=DEVICE)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--master-addr", required=True)
    parser.add_argument("--master-port", default="29500")
    parser.add_argument("--size-mb", type=float, default=4.0)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--local-device", type=int, default=0)
    args = parser.parse_args()

    os.environ["MASTER_ADDR"] = args.master_addr
    os.environ["MASTER_PORT"] = args.master_port
    os.environ["RANK"] = "1"
    os.environ["WORLD_SIZE"] = "2"

    set_device(args.local_device)
    dist.init_process_group(backend=BACKEND, rank=1, world_size=2)

    SRC = 0
    template = build_tensor_dict(args.size_mb)

    # warmup
    for _ in range(args.warmup):
        recv_dicts, recv_works = [], []
        for _ in range(args.count):
            rd, rws = irecv_tensor_dict(template, src=SRC)
            recv_dicts.append(rd)
            recv_works.extend(rws)
        for wk in recv_works:
            wk.wait()
        send_works = []
        for rd in recv_dicts:
            send_works.extend(isend_tensor_dict(rd, dst=SRC))
        for wk in send_works:
            wk.wait()
    device_synchronize()
    dist.barrier()

    # measure
    for _ in range(args.iters):
        device_synchronize()
        dist.barrier()  # 与 sender 对齐

        recv_dicts, recv_works = [], []
        for _ in range(args.count):
            rd, rws = irecv_tensor_dict(template, src=SRC)
            recv_dicts.append(rd)
            recv_works.extend(rws)
        for wk in recv_works:
            wk.wait()

        send_works = []
        for rd in recv_dicts:
            send_works.extend(isend_tensor_dict(rd, dst=SRC))
        for wk in send_works:
            wk.wait()
        device_synchronize()

    print(f"[receiver] done. size={args.size_mb}MB count={args.count} "
          f"iters={args.iters} backend={BACKEND}")
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
