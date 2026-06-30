# 打点机制完整清单（迁移基准 = 当前本地代码）

这是 migrate-dadian 的 source of truth。迁移时逐条对照：目标分支必须有等价物。
按"在哪个文件 / 是什么 / 长什么样"组织。代码片段为**当前本地实际形态**，非旧 commit。

## 1. vllm_ascend/utils.py —— 开关、门控、辅助函数（全部新增，通常无冲突）

### 1.1 模块级常量与缓存

```python
# 三个运行时开关：文件 > 环境变量，1s 缓存，默认 0
_PP_ENABLE_FILE = "/tmp/vllm_pp_timing_enable"     # PP_TIMING 打点
_PP_SYNC_FILE   = "/tmp/vllm_pp_timing_sync"       # 打点前后 NPU 同步
_PP_BATCH_FILE  = "/tmp/vllm_pp_batch_enable"      # 单步组 batch 打印
_pp_enable_cached: bool | None = None
_pp_sync_cached:   bool | None = None
_pp_batch_cached:   bool | None = None
_pp_cache_ts: float = 0.0
# 进程稳定的本机 local rank 0 判定，首次后缓存
_pp_local_rank0: bool | None = None
```

### 1.2 函数（顺序与签名）

```python
def _pp_is_local_rank0() -> bool:
    # get_world_group().local_rank == 0；分布式未初始化回退 LOCAL_RANK env；缓存
    ...

def _pp_read_cache() -> None:
    # 每 ≤1s 刷新 _pp_enable_cached / _pp_sync_cached / _pp_batch_cached
    # 文件存在则读文件，否则读环境变量 PP_TIMING_ENABLE / PP_TIMING_SYNC / PP_BATCH_ENABLE
    ...

def pp_timing_enabled() -> bool:
    # if not _pp_is_local_rank0(): return False   ← rank0 门控
    # _pp_read_cache(); return _pp_enable_cached or False
    ...

def should_pp_timing_sync() -> bool:
    # _pp_read_cache(); return _pp_sync_cached or False   （无 rank0 门控，仅被 pp_timing_sync 用）
    ...

def pp_timing_sync() -> None:
    # if should_pp_timing_sync(): torch.npu.synchronize()
    ...

def pp_batch_enabled() -> bool:
    # if not _pp_is_local_rank0(): return False   ← rank0 门控
    # _pp_read_cache(); return _pp_batch_cached or False
    ...

def pp_log_batch(role: str, scheduler_output, step: int) -> int:
    # 遍历 scheduler_output.num_scheduled_tokens (req_id -> int)
    # 分类：scheduled_new_reqs 里的 → prefill(new)（带 prompt_len/computed）
    #       否则 tok>1 → prefill(chunk)；tok==1 → decode
    # 打印 header: [PP_BATCH][step=..][role=..][prefill=Y/N][mixed=Y/N] total_tokens=.. num_reqs=.. prefill=.. decode=..
    # 逐请求打印一行明细
    # 返回本步 prefill 请求数
    ...
```

> 关键不变量：`pp_timing_enabled` 与 `pp_batch_enabled` 都含 rank0 门控；
> `should_pp_timing_sync` 不含门控（它只决定要不要同步，由打点调用方已先过 enabled 关）。

## 2. vllm_ascend/worker/worker.py —— worker 层打点（冲突高发区）

### 2.1 import（合并进 `from vllm_ascend.utils import (...)`）

```
pp_batch_enabled,
pp_log_batch,
pp_timing_enabled,
pp_timing_sync,
```

还需文件顶部有 `import time`（若无则加）。

### 2.2 __init__ 中的计数器

```python
self._pp_send_work: list[Handle] = []
# PP_BATCH 用：步序号与 prefill 步累计（仅 rank0 递增）
self._pp_batch_step: int = 0
self._pp_prefill_count: int = 0
```

### 2.3 execute_model 顶部（role 无条件 + 入口打点 + batch 打印）

```python
# role 在打点与 batch 打印间共用 → 无条件计算（放守卫外）
role = "standard"
if is_edge_device():
    role = "edge"
elif is_cloud_device():
    role = "cloud"

if pp_timing_enabled():
    pp_timing_sync()
    print(f"[PP_TIMING][{role}][worker_entry] {time.perf_counter()}")

if pp_batch_enabled() and scheduler_output.total_num_scheduled_tokens > 0:
    self._pp_batch_step += 1
    n_prefill = pp_log_batch(role, scheduler_output, self._pp_batch_step)
    if n_prefill > 0:
        self._pp_prefill_count += 1
        print(
            f"[PP_BATCH][step={self._pp_batch_step}] "
            f"cumulative_prefill_batches={self._pp_prefill_count}"
        )
```

### 2.4 cloud 侧接收完成打点（pp_recv_done）

```python
# cloud 接收 edge 发来的张量后
if pp_timing_enabled():
    intermediate_tensors.wait_for_comm()   # ← R5 显式等待
    pp_timing_sync()
    print(f"[PP_TIMING][cloud][pp_recv_done] {time.perf_counter()}")
```

### 2.5 edge 侧发送完成打点（send_to_cloud done，含 R4 显式 wait）

```python
self._pp_send_work = edge_cloud_isend_tensor_dict(
    _gathered,
    num_tokens=scheduler_output.total_num_scheduled_tokens,
)
if pp_timing_enabled():
    # 等待 isend handle 完成，使标记反映"发送完成"而非"提交"
    for handle in self._pp_send_work:
        handle.wait()
    pp_timing_sync()
    print(f"[PP_TIMING][edge][send_to_cloud done] {time.perf_counter()}")
```

### 2.6 edge 侧接收完成打点（recv_from_cloud）

```python
if pp_timing_enabled():
    intermediate_tensors.wait_for_comm()   # ← R5 显式等待
    pp_timing_sync()
    print(f"[PP_TIMING][edge][recv_from_cloud] {time.perf_counter()}")
```

### 2.7 worker.py 打点阶段一览表

| 标签 | 阶段名 | 触发位置 | 前置等待 |
|---|---|---|---|
| `[role]` | `worker_entry` | execute_model 顶部 | pp_timing_sync |
| `cloud` | `pp_recv_done` | 接收 edge 张量后 | wait_for_comm |
| `edge` | `send_to_cloud done` | isend 之后 | handle.wait 循环 |
| `edge` | `recv_from_cloud` | 接收 cloud 张量后 | wait_for_comm |

> 注：`runner_entry` / `runner_done` / `runner_entry_e` / `runner_done_e` 在当前本地代码
> 中是**注释状态**（`# if pp_timing_enabled(): ...`）。迁移时保持注释——它们已被
> model_runner_v1.py 内部更细的 segment 打点替代，避免重复。

## 3. vllm_ascend/worker/model_runner_v1.py —— runner 层打点

### 3.1 _pp_timing 方法（新增）

```python
def _pp_timing(self, stage: str, sync_npu: bool = False) -> None:
    from vllm_ascend.utils import pp_timing_enabled, should_pp_timing_sync

    if not pp_timing_enabled():
        return
    if sync_npu and should_pp_timing_sync():
        torch.npu.synchronize()
    if self._edge_cloud_enabled:
        role = self.edge_cloud_cfg.role
    else:
        role = "standard"
    print(f"[PP_TIMING][{role}][{stage}] {time.perf_counter()}")
```

> 注意：这里 role 来自 `self.edge_cloud_cfg.role`（edge/cloud/standard），与 worker.py
> 顶部 `is_edge_device()/is_cloud_device()` 判定一致。`pp_timing_enabled()` 内的 rank0
> 门控同样作用于这里（因为本方法第一行就 `if not pp_timing_enabled(): return`）。

### 3.2 调用点（8 处活跃，均在各 segment / forward 的 entry 与 done）

| 调用 | 位置 | 守卫/等待 |
|---|---|---|
| `_pp_timing("forward_entry", sync_npu=True)` | 标准路径 forward 前 | 内部 sync |
| `_pp_timing("forward_done", sync_npu=True)` | 标准路径 forward 后 | 内部 sync |
| `_pp_timing("segment_a_entry", sync_npu=True)` | edge segment_a（head 层）前 | 内部 sync |
| `_pp_timing("segment_a_done", sync_npu=True)` | edge segment_a 后 | 内部 sync |
| `_pp_timing("segment_e_entry", sync_npu=True)` | edge segment_e（tail 层+norm）前 | 内部 sync |
| `_pp_timing("segment_e_done", sync_npu=True)` | edge segment_e 后 | 内部 sync |
| `_pp_timing("segment_c_entry", sync_npu=True)` | cloud segment_c（中段）前 | 内部 sync |
| `_pp_timing("segment_c_done", sync_npu=True)` | cloud segment_c 后 | 内部 sync |

> 注释状态（`# self._pp_timing("state_setup_done", ...)` 等）是 prepare 系列合并后
> 按 R6 注释保留的，迁过去保持注释。

## 4. 各角色的一次 execute_model 打点序列（用于判断"迁移后点齐不齐"）

- **standard（非边云）**：worker_entry → forward_entry → forward_done
- **cloud**：worker_entry → pp_recv_done → segment_c_entry → segment_c_done
- **edge**：worker_entry → send_to_cloud done → recv_from_cloud → segment_a_entry → segment_a_done → segment_e_entry → segment_e_done

迁移后若某角色序列缺中间环节（比如 edge 缺 `recv_from_cloud`），说明对应打点在
冲突解决时被误删，回查 R5。

## 5. 开关与门控速查

| 开关 | 文件 | 环境变量 | 运行时文件 | 作用 | rank0 门控 |
|---|---|---|---|---|---|
| 打点 | PP_TIMING_ENABLE | `/tmp/vllm_pp_timing_enable` | 输出 PP_TIMING 时间戳 | 是 |
| 同步 | PP_TIMING_SYNC | `/tmp/vllm_pp_timing_sync` | 打点前后 `npu.synchronize()` | 否（仅 sync 内部） |
| batch | PP_BATCH_ENABLE | `/tmp/vllm_pp_batch_enable` | 输出单步组 batch 明细 | 是 |
