"""
isend_tensor_dict / irecv_tensor_dict NPU 阻塞测试 —— 发送端 (rank 0)

用法 (在 sender 机器上):
    python pingpong_send.py \
        --master-addr <recv_ip> --master-port 29500 \
        --size-mb 4 --count 4 --iters 20 --warmup 5

观察思路:
    在 size 固定时，分别跑 count=1,2,3,4,...，比较 round-trip 的耗时。
        若 count=N 的耗时 ≈ N × (count=1 的耗时)  -> HCCL 在 NPU 上串行执行 (阻塞 NPU 后续传输)
        若 count=N 的耗时 << N × (count=1 的耗时) -> NPU 上可以并行/流水
    另外脚本会单独打出 "CPU 下发 N 个 isend 的耗时"，用于确认 CPU 端确实没有被阻塞。
"""

import argparse
import os
import time

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


# ----------------------------------------------------------------------------
# 与 vllm 中 isend_tensor_dict / irecv_tensor_dict 等价的最小实现:
# 把 dict 中的每个 tensor 用 dist.isend / dist.irecv 异步下发, 返回 Work 句柄列表
# ----------------------------------------------------------------------------
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


def build_tensor_dict(size_mb, dtype=torch.float16, fill=1.0):
    """每个 dict 内放一个 size_mb 大小的 tensor (键名固定, 便于双端对齐)。"""
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

    os.environ["MASTER_ADDR"] = args.master_addr
    os.environ["MASTER_PORT"] = args.master_port
    os.environ["RANK"] = "0"
    os.environ["WORLD_SIZE"] = "2"

    set_device(args.local_device)
    dist.init_process_group(backend=BACKEND, rank=0, world_size=2)

    DST = 1
    template = build_tensor_dict(args.size_mb)  # 用于对端 recv 的形状模板

    # ----------------------- warmup -----------------------
    for w in range(args.warmup):
        send_dicts = [build_tensor_dict(args.size_mb, fill=float(w * 1000 + i))
                      for i in range(args.count)]
        send_works = []
        for td in send_dicts:
            send_works.extend(isend_tensor_dict(td, dst=DST))
        recv_dicts, recv_works = [], []
        for _ in range(args.count):
            rd, rws = irecv_tensor_dict(template, src=DST)
            recv_dicts.append(rd)
            recv_works.extend(rws)
        for wk in send_works + recv_works:
            wk.wait()
    device_synchronize()
    dist.barrier()

    # ----------------------- measure -----------------------
    issue_times = []   # CPU 下发 N 个 isend 的时间 (验证 CPU 不阻塞)
    rtt_times   = []   # 端到端往返时间 (验证 NPU 是否阻塞)
    for it in range(args.iters):
        send_dicts = [build_tensor_dict(args.size_mb, fill=float(it * 1000 + i))
                      for i in range(args.count)]
        device_synchronize()
        dist.barrier()  # 双端对齐计时起点

        t0 = time.perf_counter()

        # (1) 把 N 个 dict 全部下发出去 —— 这步应当只在 CPU 上排队, 不应被 NPU 阻塞
        send_works = []
        for td in send_dicts:
            send_works.extend(isend_tensor_dict(td, dst=DST))
        t_issue = time.perf_counter()

        # (2) 依次接收回 N 个 dict
        recv_dicts, recv_works = [], []
        for _ in range(args.count):
            rd, rws = irecv_tensor_dict(template, src=DST)
            recv_dicts.append(rd)
            recv_works.extend(rws)

        # (3) 等所有 recv 完成 —— 这里的耗时反映 NPU 上 HCCL 的真实串/并行情况
        for wk in recv_works:
            wk.wait()
        for wk in send_works:
            wk.wait()
        device_synchronize()
        t1 = time.perf_counter()

        issue_times.append((t_issue - t0) * 1000)
        rtt_times.append((t1 - t0) * 1000)

    def stats(xs):
        xs_sorted = sorted(xs)
        avg = sum(xs) / len(xs)
        p50 = xs_sorted[len(xs) // 2]
        p90 = xs_sorted[int(len(xs) * 0.9)]
        return avg, p50, p90, min(xs), max(xs)

    a, p50, p90, lo, hi = stats(rtt_times)
    ia, ip50, ip90, ilo, ihi = stats(issue_times)
    total_bytes = args.size_mb * args.count   # 单程; 来回是 2 倍
    print("=" * 70)
    print(f"[sender] size/tensor = {args.size_mb} MB, count = {args.count}, "
          f"backend = {BACKEND}")
    print(f"[sender] payload per direction = {total_bytes:.2f} MB "
          f"(round-trip = {2*total_bytes:.2f} MB)")
    print("-" * 70)
    print(f"[sender] CPU issue {args.count} isends:   "
          f"avg={ia:.3f} ms  p50={ip50:.3f}  p90={ip90:.3f}  "
          f"min={ilo:.3f}  max={ihi:.3f}")
    print(f"[sender] full round-trip:           "
          f"avg={a:.3f} ms  p50={p50:.3f}  p90={p90:.3f}  "
          f"min={lo:.3f}  max={hi:.3f}")
    print(f"[sender] per-tensor RTT (avg/count) = {a / args.count:.3f} ms")
    print("=" * 70)

    dist.destroy_process_group()


if __name__ == "__main__":
    main()
