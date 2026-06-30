---
name: parse-pp-timing
description: >-
  解析 vllm-ascend PP 打点日志（[PP_TIMING][role][stage] timestamp 行），按角色与步
  分组、计算相邻打点之间的时间间隔，并给出每段间隔的含义（哪段代码在跑、瓶颈在哪）。
  Use whenever the user mentions parse-pp-timing, "解析打点", "打点日志分析",
  "看 PP_TIMING 间隔", "边云时序分析", or pastes PP_TIMING log lines / asks what the
  timing gaps mean. Also triggers on: "为什么 prefill 慢", "卡在哪段", "边云通信耗时".
---

# parse-pp-timing

PP 打点（migrate-dadian 迁移的那套机制）会在推理时按角色输出形如
`[PP_TIMING][edge][send_to_cloud done] 1234567.890123` 的时间戳行。原始数据只是一串
带角色和阶段名的时间戳，看不出哪段慢。本 skill 把它们**按角色 + 步分组**，算出**相邻
打点之间的间隔**，并标注每段间隔对应的代码段含义，定位耗时瓶颈。

## 输入与格式

每行一条打点，格式严格为：

```
[PP_TIMING][<role>][<stage>] <timestamp>
```

- `<role>` ∈ {`standard`, `edge`, `cloud`}
- `<stage>` 是阶段名（见下方"阶段库"）；`send_to_cloud done` 这种含空格的也算一个整体
  stage 名（中括号内到 `]` 为止）
- `<timestamp>` 是 `time.perf_counter()` 输出（秒，浮点，单调递增）

日志可能还混着 `[PP_BATCH]` 行（组 batch 明细）——解析时**忽略非 PP_TIMING 行**，但可
用 `[PP_BATCH][step=N]` 行作为步边界辅助标注（可选）。

## 分组的关键：步边界（极易出错，先看这里）

**不同角色的打点来自不同进程/节点，时间戳基线不同（time.perf_counter 是进程本地单调
钟），绝不能跨角色相减。** 只能在**同一角色内**算相邻间隔。

即使在同一角色内，多次 execute_model 调用会**重复输出同一阶段序列**。比如 edge 角色
每步都打印 `worker_entry → send_to_cloud done → recv_from_cloud → segment_a_entry
→ segment_a_done → segment_e_entry → segment_e_done`，连续几十步。若把"第 N 步的
segment_e_done"和"第 N+1 步的 worker_entry"相减，得到的是跨步间隔（含上一步收尾到
下一步入口的空隙），这通常**不是你想看的**，但偶尔有用（看步间 idle）。

**步边界检测规则**：每个角色的序列以 `worker_entry` 开头（standard/cloud/edge 都是）。
遇到一个新的 `worker_entry` 即开始新一步。因此：

- 步内相邻间隔 = 同一步内相邻两行的时间差。
- 步间间隔 = 上一步最后一个阶段 → 下一步 `worker_entry`（可选输出，单独标注"步间/idle"）。

标准序列顺序见 [reference/interval-meaning.md](reference/interval-meaning.md) 的"各角色
单步序列"——若实际日志里阶段乱序或缺失，说明打点迁移有遗漏（指向 migrate-dadian），
应提示用户而非强行计算。

## 分析流程

1. **解析**：用 `scripts/parse_pp_timing.py <logfile>`，或直接读入按正则提取
   `(role, stage, ts)` 三元组。
2. **分组**：按 role 分流；每个 role 内按 `worker_entry` 切步。
3. **算间隔**：步内相邻行 `ts[i+1] - ts[i]`，标签为 `"<stage_i> → <stage_{i+1}>"`。
4. **标含义**：查 [reference/interval-meaning.md](reference/interval-meaning.md) 的
   "间隔含义表"，给每段一段人类可读的说明（这段在跑什么、大说明什么问题）。
5. **汇总**：对每段间隔类型跨多步取 min/avg/max，输出一张总表；标出每步里最大的那段
   （瓶颈步内段）。

## 阶段库（role × stage 全集）

来自 migrate-dadian 的 marker-inventory §4。`*` 标记的含显式等待（sync 或 wait），
时间戳反映"完成"。

- **standard**：`worker_entry`、`forward_entry*`、`forward_done*`
- **edge**：`worker_entry`、`send_to_cloud done*`（前有 `handle.wait()`）、
  `recv_from_cloud*`（前有 `wait_for_comm()`）、`segment_a_entry*`、`segment_a_done*`、
  `segment_e_entry*`、`segment_e_done*`
- **cloud**：`worker_entry`、`pp_recv_done*`（前有 `wait_for_comm()`）、
  `segment_c_entry*`、`segment_c_done*`

## 怎么看结果（给用户的解读框架）

1. **先看单步总时长**：edge 一步 = `worker_entry` → `segment_e_done`。对比 prefill 步
   与 decode 步（用 `[PP_BATCH]` 行区分：prefill 步 token 数大）。
2. **再看瓶颈段**：步内最长的那段间隔。查 interval-meaning 表看它对应什么。
3. **关注通信段 vs 计算段**：
   - `send_to_cloud done → recv_from_cloud`（edge）：这段是 edge 发完→等 cloud 算完→收
     回，跨度大说明 **cloud 中段 segment_c 慢**或**网络往返大**。
   - `segment_a_done → send_to_cloud done`（edge）：这段是 SP 聚合 + isend + wait，偏大
     说明**发送/聚合**慢。
4. **对比同步开关**：若用户开过 `PP_TIMING_SYNC`，每段是"真完成"时间（含同步开销，更准
   但更慢）；若没开，时间戳含异步水分，通信段会偏小。解读时要问清这点。
5. **跨步趋势**：prefill 前 N 步 token 满载，各段稳定；若某步突然变大，结合 PP_BATCH 看
   是否混入了 decode 或组 batch 异常。

## 输出建议格式

```
== role=edge  (12 steps) ==
step  worker_entry→send_to_cloud  send_to_cloud→recv_from_cloud  recv_from_cloud→seg_a_entry  seg_a→seg_e  step_total
1     0.8ms                     15.2ms (cloud seg_c + 网络)      0.3ms                      22.1ms      38.4ms
...
per-interval summary (min/avg/max ms):
  send_to_cloud done→recv_from_cloud:  14.1 / 15.0 / 16.3   ← 瓶颈：cloud 中段/网络
  segment_a_done→segment_e_done:        21.0 / 22.0 / 23.5   ← edge 计算（head+tail）
```

（实际阶段对以 interval-meaning 表为准；上面是示意。）

## 常见误读

- **跨角色相减**：`cloud.pp_recv_done` 和 `edge.send_to_cloud done` 不能相减——不同进程钟。
  只能各自组内比较，或用 PP_BATCH 的 step 号做粗略对齐看重叠。
- **把 `PP_TIMING_SYNC` 关时的通信间隔当真**：异步未同步时，`send_to_cloud done`（含
  wait）之后的间隔相对可信；但 `segment_*_entry→done` 若没开 sync，可能只反映提交时刻。
  解读时标注同步状态。
- **步边界误判**：若某角色某步缺了 `worker_entry`（迁移漏迁），切步会错位。先做"序列
  完整性检查"：每步必须以 worker_entry 起始、以该角色末段（segment_e_done / segment_c_done
  / forward_done）结束。不完整则告警。
