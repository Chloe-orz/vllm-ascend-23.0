"""
isend_tensor_dict / irecv_tensor_dict NPU 阻塞测试 —— 接收端 (rank 1)

直接调用 vllm 仓中的 ``GroupCoordinator.isend_tensor_dict /
GroupCoordinator.irecv_tensor_dict``，保证与生产代码行为一致。

用法 (在 receiver 机器上, 注意 --size-bytes / --count 必须与 sender 完全一致):
    python pingpong_recv.py \
        --master-addr <recv_ip> --master-port 29500 \
        --size-bytes 4194304 --count 4 --iters 20 --warmup 5

逻辑:
    1) 用 irecv_tensor_dict 收 N 个 dict (handle.wait + 跑 postprocess)
    2) 全部收齐后, 再用 isend_tensor_dict 把同样 N 个 dict 原样发回
       这样 sender 端测出来的就是完整的往返时间。
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


def build_tensor_dict(size_bytes, dtype=torch.float16, fill=0.0):
    """构造一个 size_bytes 字节大小的 dict, 用作 fallback 回送 buffer。

    实际跑测试时, receiver 用 irecv_tensor_dict 收来的 dict 作为发回内容,
    这个函数主要在 warmup 阶段以及发回 dict 缺失关键 metadata 时兜底。
    """
    elem = torch.tensor([], dtype=dtype).element_size()
    numel = int(size_bytes // elem)
    return {"data": torch.full((numel,), fill, dtype=dtype, device=DEVICE)}


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
        group_name="pingpong",
    )

    SRC = 0  # rank_in_group of sender

    def run_one_round():
        # 1) 收 N 个
        recv_results = [group.irecv_tensor_dict(src=SRC)
                        for _ in range(args.count)]
        for _, handles, _ in recv_results:
            for h in handles:
                h.wait()
        for _, _, postprocess in recv_results:
            for fn in postprocess:
                fn()
        # 2) 原样发回 N 个
        send_handles = []
        for td, _, _ in recv_results:
            send_handles.extend(group.isend_tensor_dict(td, dst=SRC))
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
        dist.barrier()  # 与 sender 对齐
        run_one_round()
        device_synchronize()

    print(f"[receiver] done. size={args.size_bytes} bytes "
          f"({args.size_bytes/1024/1024:.3f} MiB) count={args.count} "
          f"iters={args.iters} backend={BACKEND}")
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
