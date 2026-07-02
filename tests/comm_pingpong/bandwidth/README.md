# bandwidth/ —— 双机通信带宽测试 (数据面 + 网络面)

测两台机器之间的通信带宽,分两个面:

| 工具 | 面 | 走的栈 | 测的是什么 |
|---|---|---|---|
| `data_face_send.py` + `data_face_recv.py` | **数据面** | HCCL (torch.distributed) | vllm 边云 P2P 实战能跑到的带宽,含 HCCL 协议/拷贝/ACK 开销 |
| `net_face.py` | **网络面** | 裸 TCP socket (标准库) | 物理网络带宽上限,不经 HCCL/torch |

## 为什么单独新增(原有脚本的不足)

`tests/comm_pingpong/` 下原有脚本(`raw_oneway_send`、`raw_pingpong_send`、
`merged_oneway_send` 等)测的是 **时延** 维度——CPU issue 耗时、NPU wait 耗时、
含 ACK 的端到端 RTT。它们用于**诊断 isend/irecv 是否阻塞 NPU**,不是带宽工具:

- **不输出带宽**(没有任何 GiB/s / GB/s 计算)。
- `raw_oneway_send` 的 end-to-end 含 ACK barrier,把一次额外往返算进了"耗时",
  若用它反推带宽会系统性偏低。
- 没有"网络面 vs 数据面"对照,无法定位瓶颈在网络还是 HCCL 栈。

所以新增本目录,专做带宽。

## 数据面测试 (data_face)

测 HCCL `isend/irecv` 单向发送带宽——vllm 边云 P2P 实际走的路径。

**双机,两端各一进程**(`--master-addr` 两端都填 sender IP,PyTorch 约定 master=rank0):

```bash
# 机器A (sender, 同时是 master)
python data_face_send.py \
    --master-addr <A_ip> --master-port 3004 \
    --size-bytes 1048576,4194304,16777216,67108864,268435456 \
    --count 1 --iters 20 --warmup 5

# 机器B (receiver)
python data_face_recv.py \
    --master-addr <A_ip> --master-port 3004 \
    --size-bytes 1048576,4194304,16777216,67108864,268435456 \
    --count 1 --iters 20 --warmup 5
```

两端 `--size-bytes / --count / --iters / --warmup` **必须完全一致**。

带宽口径:
- `payload = size_bytes * count`
- 时间窗 = `isend` 发起 → 全部 `handle.wait()` → `device_synchronize()` 完成
- `bw = payload / 时间窗`,只由 **sender 端**算并打印(receiver 不算,避免两端时钟打架)
- `bw_peak = payload / min(各轮时间)`(最佳,排除抖动)
- `bw_avg  = payload / mean(各轮时间)`

关键设计:用 `dist.barrier()` 对齐每轮起跑线但**不计入时间窗**;**不加** ACK barrier
收尾(否则把一次往返算进带宽会偏低)。大消息走 HCCL rendezvous,sender `wait()` 完成
即数据已到对端,故 sender 单端 wait 时间 ≈ 单向传输时间。

## 网络面测试 (net_face)

纯 TCP socket(只依赖 Python 标准库,不需要 torch/npu/cuda),隔离物理网络带宽。

```bash
# 机器B (receiver, 先起)
python net_face.py --role receiver --port 5001

# 机器A (sender, 后起)
python net_face.py --role sender --host <B_ip> --port 5001 \
    --size-bytes 1048576,4194304,16777216,67108864,268435456 \
    --iters 20 --warmup 5
```

`net_face` 的 `count` 固定为 1(网络面不摊薄 per-tensor 开销,看裸吞吐)。带宽由
sender 端 `socket.sendall` 完成时间反推。

## 怎么看结果(对比两个面)

跑完两个面,对照同 size 的大消息(>=16 MiB)带宽:

| 现象 | 结论 |
|---|---|
| `net_face` 明显 > `data_face` | **正常**。HCCL 栈有协议/拷贝/同步开销,数据面低于网络面 |
| `net_face` 本身就低 | **网络面有病**。查网卡速率、线缆、MTU、RDMA/ROCE 配置、交换机拓扑、拥塞 |
| `net_face` 高但 `data_face` 异常低 | **HCCL 问题**。网络没病,查 HCCL 版本/配置/环境变量(`HCCL_*`)、是否走了预期网卡 |
| 两者都低且接近 | 链路本身就是瓶颈,带宽已达物理上限 |

## 参数说明

- `--size-bytes`:逗号分隔的字节列表,自动去重排序。建议覆盖 1 MiB → 256 MiB,
  小消息看时延/协议开销,大消息看带宽极限。
- `--count`(仅 data_face):一轮发几个 tensor。`count>1` 摊薄 per-tensor 开销,
  带宽偏高;**对比时 count 必须一致**,勿把 `count=1` 和 `count=8` 直接比。
- `--iters` / `--warmup`:测量轮数 / 预热轮数。预热不计入。
- `--local-device`(仅 data_face):本机用第几张卡。

## 示例输出(data_face_send)

```
==============================================================================
[data_face_send] backend=hccl device=npu count=1 iters=20 warmup=5
[data_face_send] sizes (MiB) = [1.0, 4.0, 16.0, 64.0, 256.0]
==============================================================================
 size(MiB)  payload(MiB)  lat_min(ms)  lat_avg(ms)  bw_peak(GiB/s)  bw_avg(GiB/s)  bw_avg(GB/s)
--------------------------------------------------------------------------
     1.000         1.000       0.10        0.12           9.31           7.86         8.43
   256.000       256.000       8.45        8.72          30.08          29.17        31.30
==============================================================================
```

大消息(256 MiB)的 `bw_avg` 就是该链路数据面的实际带宽。
