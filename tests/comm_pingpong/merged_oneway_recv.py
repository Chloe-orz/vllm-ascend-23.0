"""
irecv 合并接收单程阻塞测试 —— 接收端 (rank 1)

与 merged_oneway_send.py 配对: 一次 irecv 收一个 merged_bytes 大小的大 tensor,
再用 ``torch.split`` (或等价的 slicing) 拆回 merge 个逻辑 tensor。
拆分后可选做一次 contiguous 拷贝以匹配真实业务使用模式 (默认 view-only, 零拷贝)。

收齐 (count/merge) 次大 tensor 后做一次 ``dist.barrier()`` 作为 ACK,
通知 sender "对端 NPU 上数据收齐了"。

用法 (--size-bytes / --count / --merge / --iters / --warmup 必须与 sender 一致):
    python merged_oneway_recv.py --master-addr 1.1.1.1 --master-port 3004 \
        --size-bytes 4194304 --count 8 --merge 4 --iters 20

参数:
    --copy-after-split   拆分后对每个逻辑 tensor 做 .contiguous() 拷贝,
                          模拟下游需要独立 buffer 的场景 (额外开销, 但和真实业务更接近)。
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
                        help="每个逻辑 tensor 的大小 (字节, 必须与 sender 一致)")
    parser.add_argument("--count", type=int, default=8,
                        help="总共接收的逻辑 tensor 个数 (必须与 sender 一致)")
    parser.add_argument("--merge", type=int, default=1,
                        help="每多少个逻辑 tensor 合并成 1 次 irecv "
                             "(必须与 sender 一致, --count 须能被整除)")
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--local-device", type=int, default=0)
    parser.add_argument("--copy-after-split", action="store_true",
                        help="split 后对每个逻辑 tensor 做 contiguous 拷贝 "
                             "(默认只 view, 无额外开销)")
    args = parser.parse_args()

    if args.count % args.merge != 0:
        raise SystemExit(
            f"--count ({args.count}) 必须能被 --merge ({args.merge}) 整除"
        )

    num_recvs = args.count // args.merge

    set_device(args.local_device)

    os.environ["MASTER_ADDR"] = args.master_addr
    os.environ["MASTER_PORT"] = args.master_port
    os.environ["RANK"] = "1"
    os.environ["WORLD_SIZE"] = "2"

    dist.init_process_group(backend=BACKEND, rank=1, world_size=2)

    SRC = 0

    DTYPE = torch.float16
    elem = torch.tensor([], dtype=DTYPE).element_size()
    sub_numel = args.size_bytes // elem
    merged_bytes = args.size_bytes * args.merge
    merged_numel = merged_bytes // elem

    def make_merged_buf() -> torch.Tensor:
        """接收用 buffer, 形状与 sender 端 cat 后一致 (merged_numel,)。"""
        return torch.empty(merged_numel, dtype=DTYPE, device=DEVICE)

    def split_logical(merged_t: torch.Tensor) -> list[torch.Tensor]:
        """把一个 merged tensor 拆回 merge 个逻辑 sub-tensor。

        默认走 ``torch.split`` 是 view (零拷贝), 不会触发 NPU 同步。
        若指定 --copy-after-split, 每片再 .contiguous() 拷一份, 模拟下游
        需要独立 buffer 的真实业务场景。
        """
        parts = list(torch.split(merged_t, sub_numel, dim=0))
        assert len(parts) == args.merge, (
            f"split 后得到 {len(parts)} 个 sub-tensor, 期望 {args.merge}"
        )
        if args.copy_after_split:
            parts = [p.contiguous().clone() for p in parts]
        return parts

    def run_one_round():
        # 1) 收 num_recvs 次, 每次收 merged_bytes
        recv_bufs = [make_merged_buf() for _ in range(num_recvs)]
        recv_handles = []
        for buf in recv_bufs:
            recv_handles.append(dist.irecv(buf, src=SRC))
        for h in recv_handles:
            h.wait()
        # 2) 拆回逻辑 tensor (模拟生产侧用法)
        logical_tensors: list[torch.Tensor] = []
        for merged_t in recv_bufs:
            logical_tensors.extend(split_logical(merged_t))
        assert len(logical_tensors) == args.count, (
            f"split 后得到 {len(logical_tensors)} 个逻辑 tensor, "
            f"期望 {args.count}"
        )
        device_synchronize()
        dist.barrier()  # ACK
        return logical_tensors

    # warmup
    for _ in range(args.warmup):
        run_one_round()
    dist.barrier()

    # measure
    for _ in range(args.iters):
        device_synchronize()
        dist.barrier()  # 与 sender 对齐起跑线
        run_one_round()

    print(f"[merged_receiver] done. logical size={args.size_bytes} bytes "
          f"({args.size_bytes/1024/1024:.3f} MiB), count={args.count}, "
          f"merge={args.merge}, num_recvs={num_recvs}, "
          f"copy_after_split={args.copy_after_split}, "
          f"iters={args.iters} backend={BACKEND}")
    dist.destroy_process_group()


if __name__ == "__main__":
    main()