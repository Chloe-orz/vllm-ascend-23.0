# comm_pingpong —— `isend_tensor_dict` 是否阻塞 NPU 的双机诊断脚本

这两个脚本用于回答一个具体问题：

> `isend_tensor_dict` / `irecv_tensor_dict` 虽然是异步接口、不阻塞 CPU，那它**是否会阻塞 NPU** 上的后续 HCCL 传输？也就是说，HCCL 在 NPU 上是串行执行还是可以并行/流水？

脚本**直接 `import` vllm 仓中的 `GroupCoordinator.isend_tensor_dict / irecv_tensor_dict`**，而不是自己重写，避免重新实现造成测量偏差。运行时 CWD 落在 vllm 仓根目录（或者 vllm 已经装进 venv）即可，脚本自身放在 vllm-ascend 仓的 `tests/comm_pingpong/` 下做版本管理。

不是 pytest 用例，所以单独建子目录，没放进 `tests/ut/` 或 `tests/e2e/`。

## 文件

两套脚本，二选一或都跑：

- `pingpong_send.py` / `pingpong_recv.py` —— 双向 ping-pong 版。sender 下发 N 个 tensor_dict、收回 N 个，打印 RTT 分项耗时。
- `oneway_send.py`   / `oneway_recv.py`   —— 单程版。sender 只发不收，receiver 只收不回。收齐后用一次 `dist.barrier()` 作为 ACK。**用来区分"同方向串行 / 双向流水"**——如果 ping-pong 版的 HCCL wait 增长跟单程版基本一致，说明 send 和 recv 在 NPU 上确实共用一条 stream、彼此串行；如果 ping-pong 版增长慢于单程版的两倍，说明双向能重叠。

两个脚本都自动探测 `torch_npu`，有就走 HCCL，否则回落到 NCCL/CUDA，便于在 GPU 机器上自测脚本逻辑。

## 用法

两台机器都装好 `torch + torch_npu + vllm`（vllm 必须可 `import`），IP 互通。下面假设 sender IP = `1.1.1.1`、receiver IP = `2.2.2.2`，端口 `3004`。

> ⚠️ PyTorch 分布式约定里 `MASTER_ADDR` 是 rank 0（sender）的地址，**两端 `--master-addr` 都填 sender IP `1.1.1.1`**，不是 receiver。

### ping-pong 版 (双向 RTT)

**Receiver (2.2.2.2):**

```bash
python <vllm-ascend>/tests/comm_pingpong/pingpong_recv.py \
    --master-addr 1.1.1.1 --master-port 3004 \
    --size-mb 4 --count 1 --iters 20 --warmup 5
```

**Sender (1.1.1.1):**

```bash
python <vllm-ascend>/tests/comm_pingpong/pingpong_send.py \
    --master-addr 1.1.1.1 --master-port 3004 \
    --size-mb 4 --count 1 --iters 20 --warmup 5
```

### one-way 版 (单程 send)

**Receiver (2.2.2.2):**

```bash
python <vllm-ascend>/tests/comm_pingpong/oneway_recv.py \
    --master-addr 1.1.1.1 --master-port 3004 \
    --size-mb 4 --count 1 --iters 20 --warmup 5
```

**Sender (1.1.1.1):**

```bash
python <vllm-ascend>/tests/comm_pingpong/oneway_send.py \
    --master-addr 1.1.1.1 --master-port 3004 \
    --size-mb 4 --count 1 --iters 20 --warmup 5
```

参数：

| 参数 | 含义 |
| --- | --- |
| `--size-mb`     | 每个 tensor_dict 中 tensor 的大小 (MB) |
| `--count`       | 一轮里下发/接收的 tensor_dict 个数 |
| `--iters`       | 正式测量轮数 |
| `--warmup`      | 预热轮数 (不计入统计) |
| `--local-device`| 本机使用的卡号 (默认 0) |

> 两端 `--size-mb` 和 `--count` 必须严格一致，否则 recv buffer 形状对不上会挂。

## 输出读法（sender 端）

### ping-pong 版

每轮 sender 会拆出三段耗时，挑要紧的看：

| 指标 | 含义 |
| --- | --- |
| `CPU issue N` | 把 N 个 `isend_tensor_dict` + N 个 `irecv_tensor_dict` 全部下发完的时间。**注意**：vllm 实现里每个 `isend_tensor_dict` 都会先做一次 `send_object(metadata)`，走的是 gloo/CPU 组，**同步阻塞**；同理 irecv 端 `recv_object`。所以这一项里已经隐含了 2N 次跟对端的握手开销，**它不是"CPU 完全不阻塞"的证据**。 |
| `HCCL wait`   | 等所有 isend/irecv handle + `device_synchronize` 完成的时间，反映 NPU 上 HCCL 的串/并行行为。**这是回答本问题的关键指标**。 |
| `full round-trip` | 端到端 RTT，等于 `CPU issue + HCCL wait`。 |

### one-way 版

| 指标 | 含义 |
| --- | --- |
| `CPU issue N`      | N 个 `isend_tensor_dict` 的下发时间 (含 N 次同步 `send_object`)。 |
| `NPU send wait`    | `isend handle.wait() + device_synchronize` 的时间，代表 **本端 NPU 上 send 操作的完成时间**。这一项最适合回答 "NPU 上 send 是否串行"。 |
| `end-to-end 1-way` | 加上一次 ACK barrier 之后的时间，代表数据真正抵达对端 NPU 的端到端单程时间。 |

## 如何判读结果

固定 `--size-mb`，分别跑 `--count 1 / 2 / 3 / 4`，把 sender 打印的 `HCCL wait` (ping-pong 版) 或 `NPU send wait` (one-way 版) 列成表：

| count | wait 实测 | N × wait(count=1) | 结论 |
| --- | --- | --- | --- |
| 1 | 5 ms  | 5 ms  | 基准 |
| 2 | ~10 ms | 10 ms | **NPU 上串行执行 → 后续 HCCL 传输被阻塞** |
| 2 | ~5–6 ms | 10 ms | NPU 上可并行/流水 → 不阻塞 |

不建议看 `full round-trip` / `end-to-end 1-way` 直接做线性外推，因为里面包含了 metadata 握手 / ACK barrier，它们本身就近似线性增长，会把"NPU 是否串行"的信号污染。

**进一步区分发送方向 vs 接收方向：** 用 one-way 版的 `NPU send wait` 和 ping-pong 版的 `HCCL wait` 对照——

- 若 ping-pong `HCCL wait` ≈ 2 × one-way `NPU send wait` → send 和 recv 在 NPU 上串行（共用一条 stream）。
- 若 ping-pong `HCCL wait` ≈ one-way `NPU send wait` → send/recv 双向能完全重叠。
- 介于两者之间 → 部分重叠。

## 几个容易踩的坑

1. **必须 `device_synchronize()` 再计时**：`time.perf_counter()` 只测 CPU 时间，不同步会得到"假快"的下发时间。脚本里在 `wait()` 之后又补了一次 `synchronize`，确保 RTT 是真实的端到端时间。
2. **vllm 的 isend_tensor_dict 不是纯异步**：见上文 `CPU issue` 指标说明。如果你要问的不是"NPU 是否阻塞"而是"CPU 是否真的不阻塞"，注意区分。
3. **`HCCL_BUFFSIZE`** 等环境变量会影响 HCCL 内部缓冲，从而影响是否能流水的结果。可以两端都 `export HCCL_BUFFSIZE=200` 之类再对比一次。
4. **`use_cpu_custom_send_recv` 路径**：CPU 平台上 `isend_tensor_dict` 走的是同步的 device_communicator，本脚本默认在 NPU/CUDA 上跑不会触发；如果硬要在 CPU 上跑，结果不代表 NPU 行为。
5. 如果要进一步区分**发送方向**和**接收方向**各自的阻塞情况，可以把 receiver 改成只 recv 不回发，再由 sender 用 NPU event 测单程；但用 `HCCL wait` 已经足够回答"是否串行"这个问题。
