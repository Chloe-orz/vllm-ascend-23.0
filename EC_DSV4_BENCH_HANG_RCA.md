# Edge-Cloud DeepSeek V4 打 Bench 概率性卡死 RCA —— 云侧未切层短 prefill 插队先到的 DECODE_FIRST

> 场景：edge-cloud PD 分离 + prefill-decode 穿插，DeepSeek V4，多请求 bench，async_scheduling=ON。
> 故障：打 bench 时概率性整体卡死（双边 worker 均不再推进，无报错）。
> 分析日期：2026-08-10。**当前状态：仅 RCA，未修复。**

---

## 1. 结论（一句话）

云侧 `EXPECT_ALTERNATION` 状态机中，**未切层的短 prefill 在 `EXPECT_EXECUTE_PREFILL` 态无条件插队到先到达的 DECODE_FIRST 前面执行**，造成边云双侧 worker FIFO 的跨通道循环等待：

```
edge 等 decode_1 的 c2e 结果（DL）  ↔  cloud 等 prefill_2 的 e2c hidden（PF 中段）
```

四方互等 → 永久死锁。

## 2. 卡死时刻的双边状态（与现场日志完全吻合）

> 注意：边云两台机器时钟偏差约 102s（edge 13:33:55 ≈ cloud 13:32:13），两边日志尾部是同一时刻。

### 边侧（worker MQ 严格 FIFO，按调度顺序执行）

```
... → PL(B) → DF#k → DL#k → PF(prefill_2, 新请求 2625 tokens) → DF#j(Step4970)
                  ↑ 阻塞在这里：DL#k 的 c2e recv（decode_1, 28 tokens）
```

- 日志尾部：`edge_cloud_isend: channel=decode_1 num_tokens=28`（DF#k 的 e2c hidden 已发）→ `broadcast_recv: channel=decode_1 num_tokens=28`（DL#k 挂 irecv 等云端回传）—— 之后**再无 worker 日志**；
- EngineCore 阻塞在 `batch_queue.pop()` 最老 decode_last 的 `future.result()`（`patch_engine_core.py:815-820`），队列积压 `['decode_first','prefill_first','decode_last']`（queue_len=3）不再消化；
- 调度器账面：`prefill_inflight: 1/1`、`decode_or_draft_inflight: 1/1`、`prefill_last_pending[]: 2`、`prefills_last_ready[]: 0`（等云端 PL 回不来）。

### 云侧（worker MQ 同样 FIFO）

```
... → DF(29) → DF(29) → PF(prefill_2, 2625 tokens)     ← DF#k(28) 还在 ready_decodes 里没被派发
                        ↑ 阻塞在这里：PF 中段的 e2c irecv（prefill_2）
```

- 日志尾部：全体 worker `broadcast_recv: channel=prefill_2 num_tokens=2625`（挂 irecv 等边侧 PF 头段 hidden）—— 之后**再无日志**；
- 云侧最后执行的两个 decode 都是 29 tokens（29-running 时代的旧批），**从未执行 28-token 的 DF#k**（日志无 `broadcast_recv: channel=decode_1 num_tokens=28`）——这直接证明 DF#k 被 PF 插队。

### 循环等待链

1. 云 worker 阻塞在 PF 中段的 e2c recv（`wait_for_comm`，`worker.py:1246-1252`）→ 需要边 worker 执行 PF 头段并 isend（`worker.py:1103-1109`）；
2. 边 worker 的 PF 头段排在 DL#k 之后（MQ FIFO，DL 在 Step4968 调度、PF 在 Step4969 调度）→ 需先完成 DL#k；
3. DL#k 阻塞在 decode_1 的 c2e recv（`worker.py:1127-1132`）→ 需要云执行 DF#k 中段并 isend 回传；
4. DF#k 躺在云侧 `ready_decodes` 里，云 worker 已被 PF 占死 → 永远轮不到。

回到 1，环闭合。通道级独立 NPU stream（`parallel_state.py:40-101`）救不了这种场景——**阻塞的是 worker 的 python 执行线程**，根本走不到后面 batch 的 isend 调用。

## 3. 根因代码：到达顺序保护被"切层"条件旁路

数据面铁律（代码自己的注释，`passive_scheduler.py:666-675` `_pick_decode_or_draft_by_arrival` docstring）：**边侧按它数据面需要的顺序发布控制消息，云侧必须按到达顺序执行，否则同通道 FIFO 配对错位 → 跨侧死锁**。

本事件中控制面顺序没错：DF#k（edge Step~4967 发布）先于 PF（Step4969 发布）经同一条 ZMQ PRE_OUT（FIFO）到达云侧。错在云侧**调度时颠倒了它们**。

`_schedule_expect_alternation`（`passive_scheduler.py:755-768`），`EXPECT_EXECUTE_PREFILL` 态（上一个派发的恰是 decode，交替后必入此态，L778-780）：

```python
if self.ready_prefills:
    if (self.ready_decodes
        and self._ready_prefill_is_sliced_first_block()):   # ← 只有"会被切层的 prefill"才比到达顺序
        return self._schedule_by_arrival()
    ...
    return self._pick_prefill_batch()                       # ← 否则 prefill 无条件插队！
```

而 `_ready_prefill_is_sliced_first_block`（L699-703）→ `_slice_for`（L493-517）→ `_do_slice`（L476-491）→ `_resolve_slice_count`（L441-455）：

```python
# L441-455：token 数 ≥ YAML 阈值（千 tokens）才切层；无 YAML 配置时返回 0 = 永不切层
if self._layer_slice_config is not None:
    for token_k, slice_num in self._layer_slice_config.items():
        if total_tokens >= token_k * 1000:
            return slice_num
return 0
```

注释（L516）明确"短 prefill（<8k）执行太快，decode 来不及穿插，同样不切层"。

于是本批 prefill 只有 **2625 tokens**（切不了层）→ `_ready_prefill_is_sliced_first_block()` 为 False → 到达顺序检查被跳过 → **PF 无条件抢到 DF#k 前面** → §2 的死锁环成形。

> 即：现有的 `_schedule_by_arrival`（L705-744）先到先发保护只覆盖"切层 prefill 的 slice-0 vs decode/draft"；短 prefill（DSv4 bench 的 chunk 普遍 1~4k tokens；若云侧未配 layer_slice_config.yaml 则**所有** prefill）从保护网眼里漏出。

### 设计误区

"短 prefill 跑得快、先跑无妨"的前提是 **e2c hidden 已经在路上**。但穿插场景下边侧 worker 是 FIFO：PF 头段排在 DL 后面，而 DL 在等云回传——云先收 PF 就意味着它挂的 irecv 要等边侧先完成一次 decode 往返，而这个往返恰恰需要云先执行被插队的 DF。**worker FIFO 阻塞问题，与 prefill 本身执行快慢无关。**

## 4. 为什么是"概率性"

需四个条件同时满足：

1. 云侧状态机处于 `EXPECT_EXECUTE_PREFILL`（交替节奏下约一半时间）；
2. DF#k 与 PF 在同一 `poll_and_classify` 窗口（ZMQ subscriber `poll(100ms)` + 主循环 tick，`passive_core.py:211-241`、`passive_scheduler.py:232-328`）内同时就绪——若 DF#k 早一个 tick 被分类，它会先被派发，不死锁；
3. prefill 低于切层阈值（短 prefill/chunk 才触发；长 prefill 被切层时 `_schedule_by_arrival` 会正确放行先到的 decode）；
4. 边侧 worker 队列中 DL 排在 PF 头段之前——穿插设计固有顺序，恒成立。

现场日志中 `DECODE_FIRST arrival interval: 463.99 ms`（正常 ~66ms）正是条件 2 的诱发征兆：边侧 decode 环路已积压（batch_queue 满），DF 与 PF 的控制消息成簇到达云侧，落入同一调度 tick。

## 5. 已排除的其他候选

| 候选 | 排除依据 |
|---|---|
| DRF/DF 控制面乱序（pregenerated draft 延迟发布，`patch_engine_core.py:240-247`） | 日志全程无 draft 活动（`drafts_*_ready[]=0`、`draft_remote_pending=0`），MTP 未开 |
| mrope 双边不一致（`worker.py:1194-1208`） | DSv4 纯文本，无 mrope |
| PRE_OUT publisher 满队列丢消息（`passive_core.py:131-138`） | 云侧 DF arrival 日志连续，无 drop warning |
| 通道分配双边不一致 | 通道号随 SO pickle 传输、云侧原样回声、PL 有 `_validate_prefill_tail_channel` 校验；日志中 prefill_2 双边匹配 |
| 2P 边界同流环形死锁（`parallel_state.py:43-55`） | 已由 per-channel stream 修复；且本案是 decode_1 × prefill_2 跨通道顺序颠倒，机制不同 |
| 边侧 inflight/通道泄漏（`_drop_stale_drafts_for_req_ids` 丢占位 DF 等） | 需 MTP；且卡死点双边 worker 均在等数据面 recv，是活的对称互等而非计数泄漏 |

## 6. 修复方向（**本次不实施**）

### 主修（云侧，最小改动）

去掉"仅切层 prefill 才比到达顺序"的门控——`ready_decodes`/`ready_drafts` 非空时一律走 `_schedule_by_arrival`：

```python
# passive_scheduler.py:756（EXPECT_EXECUTE_PREFILL 分支）
- if (self.ready_decodes and self._ready_prefill_is_sliced_first_block()):
+ if self.ready_decodes or self.ready_drafts:
      return self._schedule_by_arrival()
```

理由：死锁与"切层交错"无关，是 worker FIFO 阻塞问题。`_schedule_by_arrival` 已实现所需的 seq 比较（channel_seq < prefill_seq → 先发 decode），只需让它对所有 prefill 生效。代价：短 prefill 不再能插队，云侧 decode 优先，可能轻微影响原交替策略的吞吐调优（需 bench 验证）。

### 加固（可选）

- 云/边 worker 数据面 `handle.wait()` 加超时 + WARN（现在卡死完全无声，只能靠日志尾部推断）；
- 边侧 batch_queue 停摆 / `is_waiting_for_remote_tail` 持续超阈值时打周期性 WARN；
- 修复后用"短 prefill（<切层阈值）+ 持续 decode 流 + 高请求率"的 bench 场景压测验证。

## 7. 复现取证确认方法

下次复现时对比卡死点双边日志尾部，同时满足以下三点即坐实此路径：

1. 云侧最后一个动作是某 `prefill_X` 的 `broadcast_recv`（等 e2c hidden）；
2. 边侧最后一个动作是 `decode_1` 的 `broadcast_recv`（等 c2e），且其 num_tokens 与云侧 `ready_decodes` 中滞留 DF 的 num_tokens 一致；
3. 云侧该 prefill 的 num_tokens 低于切层阈值（或未配 layer_slice_config.yaml）。

辅助判据：卡死前云侧 `DECODE_FIRST arrival interval` 出现明显拉大的间隔（如 463.99 ms）。
