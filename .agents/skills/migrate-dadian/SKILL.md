---
name: migrate-dadian
description: >-
  将 vllm-ascend 的 PP 打点机制（PP_TIMING 时间戳 + PP_BATCH 组batch打印，基于
  当前本地代码）迁移到一条新代码分支，自动解决迁移冲突，保证基线原功能与打点
  功能都正确。Use whenever the user mentions migrate-dadian, "迁移打点", "把打点
  迁到新分支", "打点 cherry-pick 冲突", or asks to port the PP timing/instrumentation
  to another branch. Also triggers on: "打点迁不过去", "cherry-pick 打点报冲突",
  "新分支上打点不生效".
---

# migrate-dadian

vllm-ascend 有一套 PP 打点机制（PP_TIMING 关键点时间戳 + PP_BATCH 单步组 batch
打印），用于排查流水线/边云通信与 prefill 组 batch 时序。当这套机制需要落到一条
新的代码分支时，新分支的代码已演进（函数合并、变量改名、流程重构），直接
cherry-pick 会产生冲突。本 skill 的职责：**以当前本地代码中的打点机制为唯一基准**，
把等价机制迁到目标分支，自动解决所有冲突，且 **既不改变基线原流程，也保证打点功能
正确**。

## 基准来源（source of truth）

**只以当前本地工作树的打点实现为准**，不要去回溯引入打点的原始 commit——原始 commit
是旧形态，当前本地代码可能已改造（例如打点已被并入了 rank0-per-machine 门控、
新增了 PP_BATCH、send 打点前加了 `handle.wait()`）。以本地为准能避免把旧形态迁过去
再重复改一遍。

打点机制的全部构成见 [reference/marker-inventory.md](reference/marker-inventory.md)，
迁移前必读——它逐条列出了 utils / worker / model_runner_v1 里每一处打点代码、
辅助函数、开关与缓存，是冲突解决时"迁哪些、迁到哪、长什么样"的对照表。

## 核心约束（不可违反）

- **打点是纯加法。** 任何打点 `print` / `_pp_timing(...)` 调用都包裹在自己的
  `if pp_timing_enabled():` 或方法内 `if not pp_timing_enabled(): return` 守卫里。
  解决冲突时永远保留基线逻辑，把打点作为独立守卫块加回去——绝不能把打点合并进
  基线的条件分支里，也不能让打点改变基线执行路径。
- **打点默认关闭。** 开关默认 `0`，未开启时所有打点代码零执行、零开销。迁移后必须
  保持这一点：打点代码不得被提升到守卫之外。
- **不迁基线功能。** 目标分支已有的基线逻辑（如 `edge_sp`/`edge_merge`、SP 分片、
  通信收发）属于该分支，**保留不动**；冲突只意味着"打点要插进基线已占用的位置"，
  而不是二选一。
- **rank0 门控必须随打点一起迁。** `pp_timing_enabled()` / `pp_batch_enabled()` 内含
  `_pp_is_local_rank0()` 门控，单机多卡下非 rank0 进程直接跳过，避免日志刷屏。若
  只迁了打点调用而漏迁门控，会导致每张卡都打印。见 marker-inventory 的 utils 部分。
- **`git add <已解决文件>`，绝不 `git add .`。** 中间分析文件、patch、日志若留在工作树
  会被误提交。
- **`handle.wait()` / `wait_for_comm()` 必须保留在对应打点之前。** 这些显式等待让
  时间戳反映"完成"而非"提交"，是打点正确性的关键，详见冲突规则 R4/R5。

## 迁移流程

### 步骤 0：确认基准与目标

1. 在**当前（含打点的）本地代码**所在仓库，定位打点来源：
   - 优先用 `git log --oneline -- <utils.py> <worker.py> <model_runner_v1.py>` 找到
     "迁移打点"相关 commit；记录其 hash 作为 cherry-pick 源。
   - 若打点尚未提交（在工作树里），用 `git diff` 生成 patch 作为源。
2. 切到**目标分支**（`git checkout <target>`），确认干净。
3. `git cherry-pick <源hash>`（推荐）或 `git apply <patch>`。预期在 worker.py /
   model_runner_v1.py 出现冲突。

### 步骤 1：逐文件解决冲突

对每个 `<<<<<<< ... >>>>>>>` 冲突块，按下文【冲突解决规则】处理。通用原则：
**两边都保留**，按正确缩进和正确相对顺序拼接。处理完每个文件立即
`git add <file>`。

- **utils.py**：纯新增（新开关、新函数），通常无冲突。若有，多半是文件末尾/插入点
  重复，直接保留新增内容。
- **worker.py**：冲突高发区——基线的边云通信变量与打点的 `print` 抢同一位置。这是
  本 skill 最需要判断力的地方，严格按 R1–R6 处理。
- **model_runner_v1.py**：基线若把多个 prepare 函数合并成了
  `_run_input_preparation()`，原始打点对应阶段无处可插——按 R6 注释保留，不强行安插。

### 步骤 2：验证（必须全过）

见下方【验证清单】。任一不过，回到步骤 1 修。

### 步骤 3：完成

全部通过后 `git cherry-pick --continue`（cherry-pick 模式）或正常提交。提交信息注明
打点机制已迁、默认关闭、不影响原流程。

## 冲突解决规则

冲突本质是"打点要插的位置，基线已放了别的东西"。规则按场景给出，处理时先识别属于
哪类，再套用。

**R1 — 打点 print 与基线变量抢同一位置（最常见，worker.py 边云 send 段）**

基线（HEAD）在此处定义了变量（如 `edge_sp = enable_sp()`、`edge_merge = ...`），
打点（incoming）在此处插了一个 `print`。两者缩进不同（变量在 if 块外、print 在 if
块内），语义互不冲突。**两者都保留**：print 留在它的 `if pp_group.world_size == 2:`
块内（紧跟对应 send 调用之后），变量定义放在该块外、其消费者（recv 调用）之前。

```python
self._pp_send_work = edge_cloud_isend_tensor_dict(...)
if pp_timing_enabled():                      # 打点守卫（incoming），保留
    for handle in self._pp_send_work:        #   显式等待 send 完成
        handle.wait()
    pp_timing_sync()
    print(f"[PP_TIMING][edge][send_to_cloud done] {time.perf_counter()}")
edge_sp = enable_sp()                        # 基线变量（HEAD），保留
edge_merge = get_edge_cloud_tensor_meta().merge_payload
tensor_dict, ... = edge_cloud_broadcast_recv(
    num_tokens=...,
    sp_chunk=edge_sp and edge_merge,         # 基线 SP 逻辑原样保留
)
```

> 判据：incoming 段里若出现 `print(f"[PP_TIMING]...")`，HEAD 段里若出现变量赋值且
> 被下方某调用消费 → 就是 R1，两边都留，注意缩进与顺序。

**R2 — 基线重构/合并了函数（model_runner_v1.py prepare 系列迁移到 _run_input_preparation）**

原始打点给 `prepare_inputs_done` / `determine_batch_done` / `build_attn_metadata_done`
等阶段打了点；目标分支已无这些独立函数。**不要把打点塞进合并后的函数内部**（会破坏
其内部结构、且点失去原语义）。改为在合并函数调用**之后**保留一个统一的完成点，其余
被吞并的阶段**注释保留**：

```python
self._run_input_preparation(...)
# self._pp_timing("build_attn_metadata_done", sync_npu=True)  # 合并后阶段，注释保留待后续重定位
```

留注释是为了将来若重新拆分能快速恢复，也便于 code review 追溯。

**R3 — role 计算被卷入冲突**

`worker.execute_model` 顶部，基线可能也有 `role`/`is_edge_device()` 判定。打点用 `role`
做打印标签。处理：role 计算**无条件执行**（放守卫外），因为打点与 PP_BATCH 都要用；
不要让 role 只在 `if pp_timing_enabled():` 内计算。若基线已有等价 role 变量，复用之，
不要重复定义。

**R4 — send 侧打点必须含显式等待**

凡是 `print(... send ... done)` 这类"发送完成"语义的打点，其前面**必须**保留
`for handle in self._pp_send_work: handle.wait()`。否则时间戳只反映 isend 提交、不反映
发送完成——这是已知的正确性缺陷。迁移时若 incoming 没有 wait 而 HEAD 的 isend 是
异步的（`edge_cloud_isend_tensor_dict` 返回 handles），**必须补上 wait**。

**R5 — recv 侧打点必须含 wait_for_comm**

`print(... recv ...)` 类打点前必须保留 `intermediate_tensors.wait_for_comm()`。否则
时间戳在数据未到时就打印。

**R6 — 同名 import 重复**

`from vllm_ascend.utils import (...)` 在 worker.py，迁移后可能与基线 import 块冲突或
重复。合并为一个 import 块，按字母序，去重。新增项：`pp_batch_enabled`、`pp_log_batch`、
`pp_timing_enabled`、`pp_timing_sync`。

## 验证清单（迁移后逐项执行）

```bash
cd <vllm-ascend>

# 1. 三文件字节编译通过
python -m py_compile vllm_ascend/utils.py
python -m py_compile vllm_ascend/worker/worker.py
python -m py_compile vllm_ascend/worker/model_runner_v1.py

# 2. 无残留冲突标记
grep -rn '<<<<<<<\|=======\|>>>>>>>' vllm_ascend/utils.py vllm_ascend/worker/worker.py vllm_ascend/worker/model_runner_v1.py
# 预期：无输出

# 3. 打点开关与门控齐全（utils.py）
grep -nE 'def pp_timing_enabled|def pp_batch_enabled|def pp_log_batch|def pp_timing_sync|def _pp_is_local_rank0' vllm_ascend/utils.py

# 4. worker.py 打点调用点齐全（4 处 print，role 无条件计算）
grep -n 'print(f"\[PP_TIMING' vllm_ascend/worker/worker.py

# 5. model_runner_v1.py 打点阶段齐全（_pp_timing 方法 + 8 个活跃调用点）
grep -n 'def _pp_timing' vllm_ascend/worker/model_runner_v1.py
grep -n 'self\._pp_timing(' vllm_ascend/worker/model_runner_v1.py | grep -v '#'

# 6. send 打点前的 wait 没丢
grep -n -A3 'send_to_cloud done' vllm_ascend/worker/worker.py
# 应见 for handle in self._pp_send_work: handle.wait()

# 7. 暂存已解决文件（不要 git add .）
git add vllm_ascend/utils.py vllm_ascend/worker/worker.py vllm_ascend/worker/model_runner_v1.py
git diff --name-only --diff-filter=U   # 预期：无输出
```

若编译出现 `'return' in a 'finally' block` 的 SyntaxWarning，是文件既有的、与打点无关，
忽略即可。

## 判错防呆

- **打点在新分支"不生效"** → 99% 是开关没开。打点默认关。提醒用户
  `echo 1 > /tmp/vllm_pp_timing_enable`（或 `PP_TIMING_ENABLE=1` 启动）。
- **日志刷屏（每张卡都打印）** → rank0 门控没迁全。检查 `pp_timing_enabled()` 内是否
  调 `_pp_is_local_rank0()`、`_pp_is_local_rank0()` 是否在 utils.py 里。
- **原流程行为变了** → 违反了"纯加法"。检查是否有打点代码被提到了守卫外，或 send/recv
  的 wait 被加到了非打点路径（wait 应只在 `if pp_timing_enabled():` 内）。
- **prefill 次数对不上** → 不是打点迁移问题，是 PP_BATCH 打印的内容，用
  parse-pp-timing skill 或直接看 `[PP_BATCH]` 行分析；参考 [[pp-timing-batch-mechanism]]。
