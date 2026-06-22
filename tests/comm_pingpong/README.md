# comm_pingpong —— `isend_tensor_dict` 是否阻塞 NPU 的双机诊断脚本

这两个脚本用于回答一个具体问题：

> `isend_tensor_dict` / `irecv_tensor_dict` 虽然是异步接口、不阻塞 CPU，那它**是否会阻塞 NPU** 上的后续 HCCL 传输？也就是说，HCCL 在 NPU 上是串行执行还是可以并行/流水？

这不是 pytest 用例，因此放在 `tests/` 下独立子目录而不是 `tests/ut/` 或 `tests/e2e/`。

## 文件

- `pingpong_send.py` —— 发送端 (rank 0)，下发 N 个 tensor_dict、收回 N 个、打印 RTT 统计。
- `pingpong_recv.py` —— 接收端 (rank 1)，收到 N 个后原样回发。

两个脚本都自动探测 `torch_npu`，有就走 HCCL，否则回落到 NCCL/CUDA，便于在 GPU 机器上自测脚本逻辑。

## 用法

两台机器都装好 `torch + torch_npu`，IP 互通。下面假设 receiver IP 为 `192.168.1.10`。

**Receiver 机器：**

```bash
python pingpong_recv.py \
    --master-addr 192.168.1.10 --master-port 29500 \
    --size-mb 4 --count 1 --iters 20
```

**Sender 机器：**

```bash
python pingpong_send.py \
    --master-addr 192.168.1.10 --master-port 29500 \
    --size-mb 4 --count 1 --iters 20
```

参数：

| 参数 | 含义 |
| --- | --- |
| `--size-mb`     | 每个 tensor_dict 中 tensor 的大小 (MB) |
| `--count`       | 一轮里下发/接收的 tensor_dict 个数 |
| `--iters`       | 正式测量轮数 |
| `--warmup`      | 预热轮数 (不计入统计) |
| `--local-device`| 本机使用的卡号 (默认 0) |

> 两端的 `--size-mb` 和 `--count` 必须严格一致，否则 recv buffer 形状对不上会挂。

## 如何判读结果

固定 `--size-mb`，分别跑 `--count 1 / 2 / 3 / 4`，比较 sender 打印的 `full round-trip`：

| count | RTT 实测 | N × RTT(count=1) | 结论 |
| --- | --- | --- | --- |
| 1 | 5 ms  | 5 ms  | 基准 |
| 2 | ~10 ms | 10 ms | **NPU 上串行执行 → 后续传输被阻塞** |
| 2 | ~5–6 ms | 10 ms | NPU 上可并行/流水 → 不阻塞 |

同时关注 `CPU issue N isends` 一行：哪怕 NPU 串行，这一项也应保持在亚毫秒级，这恰恰印证了"接口异步、CPU 不阻塞"的说法；真正可能被阻塞的是 **NPU 侧的传输 stream**。

## 几个容易踩的坑

1. **必须 `device_synchronize()` 再计时**：`time.perf_counter()` 只测 CPU 时间，不同步会得到"假快"的下发时间，看不到 NPU 上真正的等待。脚本里在 `wait()` 之后又补了一次 `synchronize`，确保 RTT 是真实的端到端时间。
2. **`HCCL_BUFFSIZE`** 等环境变量会影响内部缓冲行为，从而影响是否能流水的结果。可以两端都 `export HCCL_BUFFSIZE=200` 之类再对比一次。
3. 如果要进一步区分**发送方向**和**接收方向**各自的阻塞情况，可以把 receiver 改成只 recv 不回发，再由 sender 用 NPU event 测单程；但用 RTT 已经足够回答"是否串行"这个问题。
