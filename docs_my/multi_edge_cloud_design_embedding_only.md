# 多边多云边云架构设计（embedding_only 模式）

> 版本：v1.0（2026-08-13，仿照主线文档 `multi_edge_cloud_design.md` 的 embedding_only 独立分册）
> 范围：基于现有 vllm / vllm-ascend 边云 PD 分离代码，从「一边一云强绑定」演进为「多边多云 + 中央调度器」。
> **本文档场景：embedding_only**——边侧只跑 embedding（无 transformer 层、零 KV cache），云侧跑完整
> transformer 并持有全部 KV cache。head_tail（首一尾一）主线见 `multi_edge_cloud_design.md`；
> 两模式同一代码路径（层集合配置驱动），本文档给出 em 形态下自洽的完整设计。

**术语**：PF/PL = prefill 头段/尾段；DF/DL = decode 头段/尾段；DRF/DRL = draft 头段/尾段；
e2c/c2e = 边→云 / 云→边数据面方向；GPI = 中央的全局 Prefix 索引；SO = SchedulerOutput。

---

## 1. 现状架构与耦合点（一边一云，em 模式）

### 1.1 数据流与角色

```
用户请求 → Edge（tokenize + embed_tokens，无任何 transformer 层）
        ── e2c: embeddings（+mrope_positions；不带 residual，云本地补零）──→ Cloud（全部 transformer 层 + 全部 KV）
        ←──── c2e: hidden_states + residual（仅 logits 位置需要，见 §4.5）──── Edge（final norm + lm_head + 采样）
```

关键事实（代码依据）：

| # | 事实 | 位置 |
|---|---|---|
| F1 | 边侧 head_k=tail_k=0，强制无 transformer 层 | `vllm-ascend/vllm_ascend/worker/model_runner_v1.py:908-912, 1282-1286` |
| F2 | 边侧跳过 KV cache 分配，报 1TiB 虚拟显存避免钳制，真实 num_blocks 由云决定 | `model_runner_v1.py:9217-9260`、`worker.py:755-772` |
| F3 | e2c 只发 embedding（residual 不上线，云本地补零）；c2e 带 hidden+residual 供边 final norm | `vllm_ascend/distributed/parallel_state.py:436-448` |
| F4 | 边云 input_batch 顺序必须对齐（`_reorder_input_batch_to_so_order` + 边镜像云 reorder）；em 下边无 attention，错位只乱码不污染 KV | `model_runner_v1.py:743-767, 10380-10428` |
| F5 | em 边无 attention 层，尾段可跳过 GPU 状态重新同步（`_skip_tail_sync` 生效） | `model_runner_v1.py:2606-2625` |
| F6 | **prefix 命中判断在边侧**：全局唯一 `KVCacheManager` 挂边 `PDSeparatedScheduler`；云 `PassiveScheduler` 无任何 KVCacheManager | `core/pd_separated_scheduler.py`、`core/passive_scheduler.py` |
| F7 | 释放靠 `finished_req_ids` 搭车 SO；无独立 FIN/abort 通道、无心跳、云无请求注册表 | `patch_engine_core.py:351-368` |
| F8 | active flight 中的请求不可 preempt | `pd_separated_scheduler.py:716-721` |
| F9 | 隐藏通道每 DP 2 prefill + 1 decode；`decode_or_draft_inflight_limit=1` | `pd_separated_scheduler.py:235-248` |
| F10 | 云 worker `_cloud_prepare_cache` 单槽 + `req_ids_key` 校验（0731 修复） | `model_runner_v1.py:941, 6997-7194` |

### 1.2 强绑定耦合点清单（改造对象）

1. **角色/拓扑**：`is_edge_node` 二值（`--headless` 间接决定）、`_IS_EDGE_DEVICE` 全局布尔、rank 布局按"唯一边+唯一云"。
2. **控制面**：ZMQ 一对一；无 FIN/心跳/注册表（F7）。
3. **数据面**：HCCL comm group 静态、对端常量（`dst=local_rank+1` / `src=0`）。
4. **调度**：边侧单套尾段队列/head_token/隐藏通道；云侧单来源队列、prepare 单槽。
5. **KV**：命中判断与块池管理全在边（F6），但 KV 物理全在云（F2）——错位正是改造的抓手。

### 1.3 em 模式对多边多云设计的三个关键简化

1. **prefix cache 是纯云侧问题**：边侧无 KV，无 head_tail 的双侧命中对齐（min 规则）问题——
   **云单边命中完整成立**：历史只经 attention 读 K/V cache 进入计算，层间传播 position-wise，
   边不需要任何历史位置的 hidden（例：200 长请求云命中 180 → 双方只算 181-200）。
2. **云侧重算便宜**：embedding 是无状态查表，云任何范围的重算只需边重发该范围 embeddings——
   协同重算 ≈ 一次纯云侧 prefill。
3. **边无状态化**：边只剩 embedding + norm/lm_head + 采样。边宕机重启不丢任何 KV；请求迁移只涉及云。

---

## 2. 目标架构总览

### 2.1 拓扑与角色

```
                    ┌──────────────────────────┐
                    │     Central Scheduler     │
                    │  · GPI（block_hash→cloud） │   ← 仅作路由参考，不参与分配（§4.4 铁律）
                    │  · 云负载视图 / 路由打分    │
                    │  · 租约 lease / Route RPC  │
                    └─────▲──────────────▲─────┘
              Route RPC   │              │  心跳 + GPI 增量上报（每云一条）
        ┌─────────────────┘              └──────────────────┐
  ┌─────┴─────┐   ┌──────────┐                       ┌──────┴──────┐
  │  Edge 0   │   │  Edge 1  │  ...                  │  Edge E-1   │   embed + norm/lm_head + 采样（无 KV）
  └─────┬─────┘   └────┬─────┘                       └──────┬──────┘
        │   e2c/c2e（HCCL P2P，按 pair 全互联）              │
  ┌─────┴──────────────┴────────────────────────────────────┴──────┐
  │  Cloud 0          Cloud 1        ...          Cloud C-1        │   全模型层 + KV 池（云自管）
  └─────────────────────────────────────────────────────────────────┘
```

- **身份三元组**：`(edge_id / cloud_id, epoch)`——进程每次启动 epoch+1，对端凭此作废旧状态（§5）。
  `cloud_id` 粒度 = （云实例， dp_rank)，多 DP 云对外是多个 cloud_id。
- **职责切分**：中央只做路由决策与全局索引，不进数据面、不做逐 token 调度；逐 token 调度仍由
  各边/云本地 scheduler 完成。

### 2.2 请求生命周期

```
Edge 收到请求
  0. req_id 规范化：边引擎入口统一加前缀 f"e{edge_id}-{req_id}"（注 1）
  1. tokenize + 计算 block_hashes（复用 vllm hash_block_tokens，纯 CPU）
  2. Route RPC → 中央: {edge_id, block_hashes, prompt_len, priority}
        中央返回: {cloud_id, est_hit_len, lease_id}（打分见 §4.4；est_hit 仅参考）
  3. 边记录路由: req_id → (cloud_id, lease_id)     ← prefill 决定，decode 复用
  4. PF 段（全量 token ids + lease_id + channel）发目标云，
     embeddings 全量发出（不按命中截断，注 2）
  5. decode 每步直接查本地路由表直发同一云，不再询问中央
  6. 请求结束/abort → 显式 FIN 控制消息 → 云释放；块转空闲 prefix 缓存（§4.5）
```

> **注 1（req_id 全局唯一）**：vllm 默认 `random_uuid()`，但客户端可显式指定 request_id
> （`chat_completion/protocol.py:352`），两边用户传相同 id 会撞。边入口统一加 `e{edge_id}-` 前缀
> （一处改动）使 req_id 协议保证全局唯一。效果：消息线上不传 edge_id——云从 req_id 前缀解析，
> 收包 channel 也标识来源。head_token 同理（`f"{edge_id}:{uuid}"`）。

> **注 2（全量发送，设计决策）**：边→云不按命中截断。em 下 embed 是查表，全量零额外算力；
> 且 ① 云自管 KV 需全量 token ids 本地计算链式 block hash（父哈希依赖）；② 云实命中低于预期
> 时直接用已有输入多算一段，**不存在"缺输入"的正确性问题**（补发通道在 em 下永不触发）；
> ③ wire 布局恒 = 全量 prompt 行数。代价：e2c 带宽与 prompt 长度成正比，高命中场景有冗余流量；
> 带宽敏感时的截断 + pin-ack 优化备案见 §6.2。

> **注 3（路由表成本）**：边侧 req_id→(cloud_id, lease_id) 是每在途请求两个字段，~100ns 查询
> vs 毫秒级 NPU step，结束即删——成本可忽略。**中央不维护逐请求路由表**（路由结果边自持；
> 云宕机时中央广播、各边扫本地表重路由）；中央长期状态只有 GPI + 云负载视图（C 条）。

### 2.3 通信面改造

| 层 | 现状 | 改造 |
|---|---|---|
| 边↔中央 | 无 | Route RPC（REQ/REP 或 gRPC） |
| 云→中央 | 无 | 上报通道（PUSH）：GPI 增量 + 负载心跳（§4.7） |
| 边↔云控制面 | 单 `_pp_pd_channel` | 边：`dict[cloud_id → Channel]`；云：每边一个 subscriber channel，收包 socket 即来源；新增独立可靠控制消息（FIN/NACK/Pause/Resume/PreemptNotice/心跳，重传+幂等，不搭 SO 便车） |
| 边↔云数据面 | 静态 PP 对端 | **方案 A（起步）**：每 (edge, cloud) worker pair 独立 HCCL send/recv group（全互联），运行时按段内 req_id 前缀选组；**方案 B（远期）**：Mooncake/RDMA 动态端点 |
| 隐藏通道 | 每 DP 固定 3 条 | 按 (edge_id, cloud_id) pair 分池；通道号由边分配随段携带，云只消费 |

### 2.4 分阶段落地

- **Phase 1**：1 边 1 云 + 中央调度器（路由固定返回 cloud 0），打通 Route RPC 与 GPI 上报，不改行为。
- **Phase 2**：N 边 1 云。**前置：KV 下沉云自管（§4.2）**——两边各自管池即撞块。攻云侧多源调度（§3）。
- **Phase 3**：N 边 M 云。pair 全互联 HCCL + 真路由打分；先小集群实测 E×C 个 comm group 开销。
- **Phase 4**：KV 卸载/协同重算/反熵对账（§4.6-4.7）。

---

## 3. 云侧多边调度

> 本章与 head_tail 主线完全同构（调度机制与模式无关），为独立性完整保留。

### 3.1 设计约束

1. **调度不识别来源边**：一张**全局调度队列**，出队只看 （优先级， 到达序号）。edge_id 只在执行
   选 HCCL pair、回传 c2e、失联清理时**惰性解析**（req_id 前缀 / 收包 channel）。
2. **同边不可超越（唯一顺序硬约束）**：同一边的段必须按到达序执行（0812 死锁修复 + prepare
   校验的假设）。全局 FIFO 天然满足；优先级插队只跨边生效。
3. **默认不二次组 batch，但设计不排除**：段原样执行；合并演进见 §3.7。
4. **键天然全局唯一**：req_id/head_token 前缀化，云用裸 id 作键。
5. **故障域隔离**：一边异常/失联不得卡住他边队列。

### 3.2 数据结构与主循环

```python
class SchedSeg:                      # 全局队列元素 = 某边组好批的原始段
    head_token: HeadToken            # f"{edge_id}:{uuid}"，裸键即唯一
    req_ids: tuple[str, ...]
    kind: SegKind                    # PF / DF / DRF（优先级档）
    num_tokens: int
    kv_footprint_blocks: int
    arrival_seq: int
    priority: int
    lease_id: str | None
    payload: SchedulerOutput         # 原样下发

class CloudScheduler:
    queue: deque[SchedSeg]
    pending_heads: dict[HeadToken, SchedSeg]
    edge_stats: dict[int, EdgeStats]              # 只记账（inflight/心跳/状态），不参与排序
    global_prefill_inflight_limit: int
    kv_watermark_high/low: float = 0.95 / 0.80
    prepare_cache: LruSlots                       # 单槽 → 2~4 槽 LRU，键=req_ids 全序元组
```

```python
def step(self):
    # ① 收包：每边一个 channel，socket 即来源；准入记账 + 段入全局队尾
    for channel, msg in self.poll_all_channels():
        self.admit(channel, self.classify(msg))
    # ② 出队：最高优先级档中取"是同边队首"的最早段（同边不可超越）
    seg = self.pop_next_schedulable()
    if seg is None: return EMPTY
    # ③ 原样下发；此刻才解析来源边，选 pair HCCL group（通道号段内携带）
    edge_id = parse_edge_id(seg.req_ids[0])
    self.worker_select_hccl_pair(edge_id, seg.hidden_channel)
    # ④ 执行后回调：pending_heads 标记可回传；c2e 按前缀选组发回；
    #    更新 inflight / GPI 增量（§4.7）；KV 水位检查（§4.6）
    return seg.payload

def admit(self, channel, seg):
    stats = self.edge_stats[channel.edge_id]
    need  = estimate_kv_blocks(seg)                       # 扣 pinned + 在队持有
    if (stats.inflight_prefill >= self.per_edge_quota(channel.edge_id)
            or self.global_prefill_inflight >= self.global_prefill_inflight_limit
            or self.kv_free_blocks < need + DECODE_RESERVE):
        if seg.retryable:
            self.send_nack(channel, seg.head_token, ...)  # 沿收包 channel 直回；边重新 Route
            return
        self.defer_or_preempt(seg)                        # decode 不可拒绝：排队或触发 §4.6
        return
    stats.inflight_prefill += 1
    self.confirm_lease(seg.lease_id)                      # 缺失/过期只损失优化
    self.queue.append(seg)
```

### 3.3 公平性与防打爆（准入层解决，不动调度序）

调度序保持极简（优先级， 到达序）。公平性收敛在 `admit()` 一处：逐边 inflight 配额（可配权重）
+ 全局上限 + KV 余量硬校验；超限 NACK/排队，不挤占他边在途名额。

### 3.4 图例：三边并发调度模拟

**设定**：Cloud C0；边 E0/E1/E2；优先级 decode > prefill；全局 prefill inflight 上限 2；
KV 1000 blocks（block=16 tok），DECODE_RESERVE=100。

```
t=0  同时到达:  E0→PF(A, 4000 tok, 命中 0)    需 250 blk
                E1→PF(B, 8000 tok, 命中 6000) 需 125 blk
                E2→DF(Z, 3 req decode)        需 ~1 blk
t=1  收包+准入（到达序 A,B,Z）: 三者 ADMIT → queue=[A#1, B#2, Z#3]
     confirm_lease(L_B) → pin B 的 6000 tok 前缀块
t=2  出队: decode 档 → Z（E2 队首✓）→ step#1=Z，前缀解析 e2- → pair(2,0) 收
t≈3  prefill 档 → A(seq 早于 B，E0 队首✓）→ step#2=A → pair(0,0) 收全量 embeddings
t≈5  step#3=B；B 的前 6000 tok 命中 pin 块，云只算 2000 tok（全量输入在手，无需补发）
t≈10 A 完成: pending_heads["0:tokA"] 可回传 → c2e 按前缀回 E0（仅末位置 hidden）→ A 采样进入 decode
     A 的块 cache_blocks → GPI insert 上报；E0.inflight 释放
t=12 新波: E2→PF(C) ADMIT；E0→DF(A) ADMIT → queue=[C#4, DF_A#5]
     出队: decode 档 → step#4=DF_A；step#5=C
t=15 NACK 演示: E1→PF(D, 需 1000 blk > kv_free≈600−100)
     → NACK 沿 E1 channel 直回 → E1 重新 Route（中央临时调低 C0 权重，可能去 C1）
```

**"同边不可超越"演示**：E0 连发 PF(X)#8、DF(Y)#9，decode 优先也不能先出 Y（Y 不是 E0 队首）
→ 先出其他边的 decode 队首段，否则出 X。

**关键不变量**（单测断言）：
1. 下发的每个段都是某边原始组好批的 SO，不拆不合。
2. 任意时刻同一边的段执行顺序 = arrival_seq 顺序。
3. `Σ edge_stats[*].inflight_prefill ≤ global_prefill_inflight_limit`。
4. decode 头段永不被 NACK（只 defer 或触发卸载/抢占）。
5. 任一边 DEAD 后其段从队列剔除、inflight 归零，其他段相对顺序不变。

### 3.5 PD 框架优化机制的多边适配

| 机制 | 当前实现逻辑 | 多边适配结论 |
|---|---|---|
| **PD 穿插（边侧）** | `PrefillState` 三态门控；`_force_*_last` 严格交替；`_pending_tail_count` 门控进 running | 纯边内机制，**零改动** |
| **PD 穿插（云侧）** | `CloudSchedulingState` 两态交替防同向通道 FIFO 死锁；10ms throttle 等 decode | 状态机保留，"等 decode"变为等任一边；死锁域缩小到单 pair；多边下 throttle 命中率上升 |
| **层切分** | slice 0 续算状态存单例 `_layerwise_*` → 全云同时只允许一个 sliced prefill；slice 间可插 decode；非末 slice 冻结 clone | 单例锁与来源边无关，保留为全云全局约束；slice 间可插任一边 decode |
| **切 chunk** | vllm 原生 budget（序列维），与层切分（层维）正交；chunk_prefill_prior 允许提前发 | 零改动，只依赖同边不可超越保证 chunk 序 |
| **提前收** | CHER guard thread 提前 irecv + `cloud_prepare_early` 提前 input prep；单槽 + `req_ids_key` 校验 | 键前缀化天然不串边；单槽→LRU 多槽；irecv pair 按前缀解析；另见 §3.6 H1 |

**decode 与其连续 MTP draft 步之间穿插 P/P-draft**：

| 层 | 影响 | 结论 |
|---|---|---|
| 通道层 | draft/decode 走本 pair DECODE 通道；他边 PF 走他 pair 通道 | ✓ FIFO 互不干扰 |
| 时序层 | 他边段插入只延迟本边 DRL 回传，本边通道消息序不变 | ✓ 仅延迟不错序 |
| 云侧共享 buffer 层 | `topk_indices_buffer`、`_layerwise_*` 会被任何来源插入覆盖 | ⚠ 唯一真风险 |

风险非新类别：快照/恢复（0801 修复）按执行序列触发、与来源无关，多边下自动成立。
待办：走查确认判定点无"同一边"隐含假设 + 回归矩阵 {同边 PF, 他边 PF, 他边 DF, 他边 draft}
× {decode 后, draft step 间} 精度对齐测试。

### 3.6 NPU-CPU 异步重叠机制的多边隐患分析

**前提变化**：1-1 时边云强同步确定性交替，异步重叠优化（CHER、prepare-early、层切分穿插、
异步采样修正）都建立在"对端下一步可预测"上；多边后云对任一边非确定调度。
审判标准：**正确性依赖"邻接性/可预测性"还是"时序无关结构"**。

| # | 机制 | 结论 |
|---|---|---|
| H1 | **提前 prepare 的邻接假设** | attn_metadata 内嵌 prepare 时刻行索引；多边下 prepare 与消费间可能插入他边执行。**0731 的 `req_ids_key` 校验恰好兜住正确性**（失配→慢路径重 prepare）。纪律：fast path 不得跳过键校验；失配率上升属性能问题，靠槽数+打点收敛 |
| H2 | per-pair 有界在飞 | **结构性安全**：耦合全部 = per-pair FIFO + 在飞上限（2 PF + 1 D + 2 draft）；全局队列长度有上界 = Σ 各边在飞上限 |
| H3 | `_layerwise_*` 单例 + 他边 decode 穿插 | 机制同今日，频率上升；回归矩阵扩"他边"用例；走查点：`_layerwise_positions` 等若存持久缓冲区引用而非 clone，是现网已有隐患 |
| H4 | ZOMBIE/死 peer 的异步收发配对 | 由异常原则覆盖（§5）；isend/irecv 句柄等待与通道清理必须成对 |
| H5 | **死锁自由性** | 无环形等待：① 数据 eager 推送（边发段即 isend，云执行不依赖边后续动作）；② 云 work-conserving（同边约束只跳过不卡死）；③ 在飞有界 + 清道消息走独立通道 |
| H6 | 性能新现象 | convoy 抖动（打点定位）；CHER 提前 irecv 缓冲持有变长（per-pair 缓冲池按在飞上限配置封死上界）；10ms throttle 多边下需重校 |

**结论**：异步体系基本成立——跨节点耦合全部是时序无关结构；唯一邻接依赖（H1）被现有校验
兜住。多边工作量集中在性能域（H6）与回归覆盖（H3），不是新的正确性缺陷类别。

### 3.7 演进预留：跨边组 batch（默认不开启）

合并批 = 各边段按 req_id 前缀分组的连续拼接；算完按段边界切片、按前缀各回各边。边侧几乎零改动。
实施要点 6 条：① merge window + 超时发车（convoy 控制）；② 部分失败降级（剔除死边的行重建
元数据）；③ 置换收在云内（c2e 按逆置换切回各边发送序）；④ 同边不可超越（每边每合并批至多
一个段）；⑤ 校验/回调按段粒度；⑥ 配额记账不变。

### 3.8 边失联处理

```
last_heartbeat 超 T1(5s)  → SUSPECT：该边的段标记不可调度（保留位置，等恢复）
超 T2(30s)                → DEAD：
  - 按 req_id 前缀扫描全局队列与 pending_heads，剔除该边的段
  - 在途请求标记 orphan，释放其云侧 KV（块转空闲 prefix，hash 保留供他请求命中）
  - 该边 lease 全部过期；上报中央注销 PENDING
  - 隐藏通道池/prepare 槽清理；c2e 向死 peer 的发送超时 + 通道 teardown/重建
  - 边以 (edge_id, epoch+1) 重启后全量重握手，旧 epoch 状态已全部作废
  - em 特有：边无任何 KV，重启零状态损失（§7 对照）
```

---

## 4. KV cache 管理（核心章）

### 4.1 复用的 vllm 原生机制

**① Block 分配与引用计数**（`kv_cache_manager.py:340-447`、`block_pool.py`）
- `allocate_slots()` 从 `free_block_queue` 头部取块；`free(request)` 块 ref_cnt 减 0 后追加队尾。
  **ref_cnt=0 ≠ 失效**：hash 映射仍保留，仍可被命中。真驱逐在分配侧弹出复用时才删映射。
- free 队列尾进头出 = **天然 LRU**；命中即 touch——热前缀长寿、冷前缀自然淘汰，无需额外代码。

**② Prefix 命中**（`kv_cache_utils.py:560-706`、`kv_cache_manager.py:210-230`）
- 链式哈希（父块 hash + 本块 token ids + extra keys）；分配前找最长连续前缀命中，命中块 ref+1，
  只对 miss 段分配新块；算完的块由 `cache_blocks` 插入映射。

**③ 抢占与重算**（vllm v1 原生）
- allocate 失败 → preempt 优先级最低/最晚到达的 running 请求，重调度时重走 prefill，刚释放的块
  若未被复用可部分命中。边云现状收窄：active flight 中不可 preempt（F8），多边下沿用，抢占点
  选在段间隙。

### 4.2 所有权：KV 整体下沉云自管（em 单池）

em 下边侧没有任何 KV tensor，KV 的分配/命中/驱逐/卸载/抢占全部与边的本地资源无关——
把 `KVCacheManager` 整体下沉到云是最自然的归属：

- **每云一个 KVCacheManager/BlockPool**（全模型层），块 id 空间 per-cloud 独立。
- **跨边 prefix 共享免费获得**：同云一个池一个 hash 索引，E0 缓存的前缀 E1 直接命中。
- 边 scheduler 的 KVCacheManager 退化删除（em 下它本来管的就是"别人的内存"）。
- 云 PassiveScheduler 升级为**半主动**：PF 段到达时本地 `allocate_slots` 做权威命中与分配。
- 过渡备选：静态分区（每云块池按边切分）——改动最小但跨边不共享，仅作回退。

**配套协议变化**：

| 环节 | 现状（边管） | 云管后 |
|---|---|---|
| SO 内容 | 携带 `new_block_ids`、`num_computed_tokens` | 不再携带块分配；携带**全量 token ids** + `lease_id`（§2.2 注 2） |
| 命中判断 | 边调度时本地匹配 | 云 PF 准入时本地匹配（权威）；边发全量不截断，命中只决定云少算多少 |
| 命中不一致 | 不存在（同一权威） | 不存在正确性问题——实命中 < 预期 → 云用全量输入多算一段；pin 仅为保收益的优化 |
| chunk 大小 | 边按本地池余量定 | 边按 Route 响应的 `kv_free` 估算保守定；云 all-or-NACK |
| num_computed_tokens 进度 | 边本地记账 | 云记账，随 PL/DL 输出回报边 |

**边云 KV 联动边界**：em 下边池为空，退化为极简形态——**资源面单边（云）自决**；
生命周期面只剩两条：① FIN 到达云释放 + 云 TTL GC 兜底（边死亡后 orphan 块回收）；
② 云单侧抢占/卸载通知边（PreemptNotice/Pause/Resume）。无 head_tail 的双侧同步问题。

### 4.3 云侧数据结构与架构

```
┌──────────────── Cloud j (cloud_id = 实例×dp_rank) ────────────────┐
│  控制面 ─▶ PassiveScheduler ──alloc/free──▶ CloudKVStore          │
│            · 全局队列/准入/NACK/出队        ├ KVCacheManager(原生)  │
│                │下发段                      │   req_to_blocks      │
│                ▼                            ├ BlockPool(原生)      │
│            Worker/ModelRunner ──读写KV块──▶ │   free_block_queue   │
│            · CHER/_layerwise_/KV tensor     │   cached_hash→block  │
│                                             ├ ReqRegistry(新增)    │
│            新增：                             ├ LeaseTable(新增)     │
│            ReqRegistry/LeaseTable/           ├ OffloadStore(新增)   │
│            OffloadStore/WatermarkGovernor/   ├ WatermarkGovernor    │
│            GpiReporter                       └ GpiReporter(→中央)   │
└──────────────────────────────────────────────────────────────────┘
```

职责边界：**PassiveScheduler 决定"何时执行谁"，CloudKVStore 决定"块给谁、何时回收"，
Worker 只按 block table 读写 KV tensor**。

**(a) 复用原生（不动结构只加钩子）**：`KVCacheBlock{block_id, ref_cnt, hash, 链表}`、
`BlockPool.free_block_queue`（LRU 本体）、`cached_block_hash_to_block`、`KVCacheManager.req_to_blocks`。

**(b) ReqRegistry（请求注册表，新增）**：

```python
@dataclass
class CloudReqEntry:
    req_id: str                  # 含 e{edge_id}- 前缀
    edge: tuple[int, int]        # (edge_id, epoch)
    state: ReqState              # ADMITTED → RUNNING ⇄ PAUSED → ZOMBIE → 删除
    num_computed_tokens: int
    offload_handle: OffloadHandle | None
    lease_id: str | None
    last_seen: float             # 每收到该 req 的段即刷新；TTL GC 依据
registry: dict[str, CloudReqEntry]
```

为什么需要：原生 vllm 的"请求集合"由 scheduler 的 waiting/running 充当，被动云没有等价物。
注册表是云对"我身上活着哪些请求"的唯一权威，支撑 TTL GC、FIN/ZOMBIE、pause/resume。
不变量：registry 键集 ⊇ req_to_blocks 键集（无"有块无登记"泄漏）。

**(c) LeaseTable（新增）**：`lease_id → {hashes, pinned_blocks(ref+1), expire_ts, PINNED/CONFIRMED/EXPIRED}`。
pin 创建 → confirm 时引用转请求 → sweeper 超时解 pin。不变量：PINNED 块 ref_cnt ≥ 1 不会被弹出
复用；lease 是优化，任何失败路径不得阻塞段处理。

**(d) OffloadStore（新增）**：`req_id → {host_slots, block_map(原NPU block→host slot), valid}` +
`host_arena`（pinned DDR 池，自身 LRU；满则最旧 handle 失效 → 该 req 退化 L3 重算）。
D2H 完成后 NPU 块 free；恢复时按 block_map H2D 到新块，重建 req_to_blocks。

**(e) WatermarkGovernor（新增）**：`NORMAL/OFFLOADING` 两态 + 高低水位（0.95/0.80 滞后）+
每分钟抢占次数窗口（防雪崩）；受害者选择输入来自 ReqRegistry。

**(f) GpiReporter（新增）**：insert/evict/pending/solid 攒批（200ms 或 Δ≥64 块）+ bloom 摘要；
钩子挂接：`cache_blocks` 后、free 队列弹出带 hash 块时、PF 准入确认后、PF 完成后。

**Block 生命周期状态机**：

```
              allocate(新块)
FREE_RAW ───────────────▶ ALLOCATED_ACTIVE ──free(req), ref→0 入队尾──▶ FREE_CACHED(带hash)
  ▲                                                                        │  ▲
  │ 弹出复用（删 hash 映射 = 真驱逐 → GpiReporter.evict）                     │  │ 命中复用(ref+1)
  └────────────────────────────────────────────────────────────────────────┘  │
  FREE_CACHED 三条出路：① 命中 → ALLOCATED_ACTIVE ─────────────────────────────┘
                       ② 弹出复用 → FREE_RAW      ③ TTL 扫描（可选）→ 移队首优先复用
叠加态：PINNED = +lease 引用（sweeper 超时解 pin）；PAUSED req 的块 D2H 后 free（流转同上）
```

**关键不变量**（单测/巡检断言）：
1. `Σ ref_cnt == RUNNING/ADMITTED 请求块数 + PINNED lease 块数`。
2. free 队列中任意块 ref_cnt == 0；带 hash 的块必在 cached 映射中。
3. registry 键集 ⊇ req_to_blocks 键集。
4. 同一时刻 `_layerwise_*` 只属于一个 head_token。
5. PAUSED 请求不出队；ZOMBIE 请求的段不再下发，但在飞 HCCL 事务必须配对接完。

**接口时序（谁调谁）**：

| 时刻 | 调用 |
|---|---|
| Route（中央） | `CloudKVStore.pin(lease)`（可同步 ack，可选优化） |
| 段到达 admit | `registry.add()` + `confirm_lease()` + `allocate_slots()` |
| 段出队执行 | worker 按 `req_to_blocks` 读写 KV tensor |
| 段完成 | `cache_blocks()` → GpiReporter.insert |
| decode 增长 | `allocate_slots(1)`；失败 → WatermarkGovernor 升级 |
| FIN / TTL GC | `free(req)` + `registry.pop()` → 块转 FREE_CACHED（hash 保留） |
| 水位 tick | PauseReq → D2H → free / H2D 预取 → ResumeReq |
| 心跳 | GpiReporter 摘要 + kv_free/queue_delay/inflight/recent_preempt → 中央 |

### 4.4 命中协议与"GPI 仅参考"铁律

- **云单边命中（em 特有，无 min 规则）**：边无 KV、边尾无 attention——历史信息只经 attention
  读 K/V cache 进入计算，层间传播 position-wise。例：200 长请求云命中 180 → 双方只算 181-200，
  **边不需要前 180 的任何值**。因此命中判断只需 `cloud_hit` 一个量，无 head_tail 的双侧对齐问题。
- **c2e 回传只需 logits 位置（末 token）的 hidden**（+residual）：边尾是 position-wise 的
  norm+lm_head+采样，c2e 负载与 prompt 长度解耦。
- **铁律：GPI/负载视图仅作路由参考，绝不参与任何实际资源分配决定**（中央与云之间有上报延迟）。
  分配/命中/驱逐/pin 执行的唯一权威是云本地；中央发的 pin 只是"请求"，云可拒绝或部分接受；
  任何流程不得因 pin 缺失而阻塞。
- **路由打分（中央）**：

```
score(c) = w1·(cloud_hit_est(c)/prompt_len)     # GPI 估算命中（参考；em 下单边成立，无需 min）
         + w2·(kv_free(c)/kv_total(c))          # 心跳余量
         − w3·queue_delay(c)                    # 心跳背压
         − w4·recent_preempt(c)                 # 近期抢占降权
平局 → 按 block_hashes[0] 一致性哈希             # 同前缀天然聚集同云，命中率随时间上升
```

- **Route-time PENDING**：中央决策时即把所选云的前缀 hashes 标 PENDING，后到同前缀请求命中
  PENDING 蹭在途 prefill；云 PF 准入后转 SOLID；路由后 PF 超时未到达则中央 TTL 清除。

### 4.5 过期与保留策略（三级语义）

| 类别 | 语义 | 实现 |
|---|---|---|
| **活跃请求块**（ref>0） | 不可驱逐，只走卸载/抢占（§4.6） | vllm 原生 ref_cnt，无改动 |
| **租约 pin 块** | Route 后、PF 到达前尽量保活 | `pin{lease_id, hashes, ttl=5s}`：云本地 ref+1；PF 准入 confirm 转请求；sweeper 超时解 pin。**全量发送决策后 pin 是纯优化**，失败只意味着云多算一段 |
| **空闲 prefix 块**（ref=0，hash 在） | 默认纯 LRU（复用 §4.1①）；可选 TTL | TTL 扫描器：每 60s 扫 cached 映射，`now − last_hit_ts > TTL` 且 ref=0 的块删映射并移队首优先复用。默认关闭；会话周期明显时开启，TTL ≈ 2×会话间隙 |

**设计要点**：驱逐决策全部在云本地；中央只被动收 evict 上报，不做逐块遥控。

### 4.6 满载四级处理（重计算设计）

前提：em 下云重算任何范围只需边重发该范围 embeddings（查表零成本）——全链路重算代价比
head_tail 低一个量级。四级按代价从低到高：

- **L0 准入控制（不让它满）**：中央路由前估算足迹只路由到余量足够的云；云准入二次核对+NACK。
  记账口径：`kv_free` 须扣 pinned + 已准入未执行段持有块；`DECODE_RESERVE` 按在跑请求数 ×
  增长窗口动态估算。
- **L1 空闲 prefix 驱逐（零代价）**：vllm 原生行为（弹出复用即逐），无需新代码；新增的只是
  evict 上报中央。
- **L2 活跃 KV 异步卸载到 host DDR**：水位 0.95 触发/0.80 解除（滞后）。受害者：decode 间隔长、
  剩余输出长的请求（MTP topk 等附属状态随主 KV 一起处理）。**必须与边配合（Pause/Resume 流控）**：
  云先发 `PauseReq{req_id}` → 边停发该 req 的段 → 云异步 D2H（可对接已有
  SimpleCPUOffloadConnector / RecomputeCPUOffloadConnector）→ 释放 NPU 块；恢复：H2D 预取完成 →
  `ResumeReq` → 边恢复调度。边等待超时可主动升级 L3。D2H/H2D 走 DMA 与计算 overlap。
- **L3 协同重算（兜底）**：云 free 受害者全部块（原生路径）→ `PreemptNotice` → 边标记
  re-prefill-pending → 下轮重走 PF：全量 token 重新 embed 发出（查表零成本，**与普通全量 PF
  完全同构，无特殊协议**）；云当新 prefill 准入但**优先级提升**；刚释放的块大概率部分命中
  （§4.1③ 原生效应）。防雪崩：抢占云 `recent_preempt+1` 降权；单云每分钟抢占上限；水位滞后。

**L3 时序**：

```
Cloud C0                          Edge E1                     Central
   │  kv_used=96% > 95%              │                          │
   │  选受害者 R(E1 的 req, 已算 3000 tok)                        │
   │  free(R) 块入空闲队列            │                          │
   ├──── PreemptNotice(req) ────────→│                          │
   ├──── evict{真驱逐的块} ───────────┼─────────────────────────→│
   │                                 │ 标记 R re-prefill-pending │
   │                                 │ 下轮: embed R 的全部 3000 tok（查表）
   │  ←── PF'(R, 新 head_token, ─────┤                          │
   │      优先级提升)                 │                          │
   │  准入(优先席) → 命中自查：       │                          │
   │  刚释放的块未被复用 → 命中大部   │                          │
   │  只对 miss 段重算                │                          │
```

### 4.7 GPI 同步协议（云 → 中央）

数据源 = 块池所有者（云自管 → 钩子在云侧 KVCacheManager/BlockPool；静态分区过渡期临时在边）。

| 时机（云侧） | 消息 | 说明 |
|---|---|---|
| `cache_blocks` 插入映射后 | `insert{hashes}`（攒批 200ms 或 Δ≥64） | |
| 分配侧弹出带 hash 旧块复用时 | `evict{hashes}`（攒批） | **请求 free() 时不上报**——块回空闲队列仍可命中 |
| PF 准入完成 | `pending{hashes}` | 与中央 Route-time PENDING 互为确认 |
| PF 计算完成 | `solid{hashes}` | PENDING→SOLID |
| 每 30s 心跳 | `{kv_free, queue_delay, inflight, recent_preempt}` + bloom 摘要 | 负载视图 + 反熵：中央 bloom 粗对账，大面积不一致要求全量重报 |

### 4.8 中央调度器职责小结

- GPI（`block_hash → {cloud_id: (state, version, last_seen)}`，SOLID/PENDING）+ 云负载视图。
- Route RPC：输入 `{edge_id, block_hashes, prompt_len, priority}`，输出 `{cloud_id, est_hit, lease_id}`。
- 打分公式见 §4.4；一致性哈希 tie-break。
- **无逐请求路由表、无持久化状态**；宕机可降级（边 Route 超时退化本地一致性哈希默认路由，
  恢复后靠全量上报+反熵重建），可热备。

---

## 5. 异常与容错矩阵

> 现状短板（F7/F8）：无独立 FIN/abort 通道、无心跳、云无请求注册表、active flight 不可抢占。
> 多边后"某边长期无 SO 到某云"是常态，搭车通知不再可靠——下表为完整处置（em 形态）。

| # | 场景 | 边侧处理 | 云侧处理 |
|---|---|---|---|
| 1 | 边过载（embedding 积压） | 入口限流/排队背压（边无 KV 负担）；新请求 Route 时倾向空闲云 | 无感（只看到流量下降） |
| 2 | 云过载（KV 水位高） | NACK 的新 PF 重新 Route（中央降权该云） | §4.6 四级：NACK → 空闲驱逐 → 卸载 → 协同重算 |
| 3 | 请求 abort | `finish_requests` 本地清理 + **显式 FIN** 发往路由的云 | 收 FIN：段从队列/pending_heads 剔除、释放块转空闲 prefix、清 prepare 槽 |
| 4 | 边死亡 | — | §3.8 SUSPECT/DEAD + **请求注册表 TTL GC**（orphan 块回收）；c2e 死 peer 超时+通道 teardown。**em 下边上无 KV，零状态损失** |
| 5 | 云死亡 | 中央广播 → 扫本地路由表，指向死云的请求重路由；新云全量重算——**em 下仅需边重发全量 embeddings（无 KV 可丢、无 transformer 重算），是最便宜的故障切换** | — |
| 6 | 控制面丢包/乱序 | 段超时无回传 → 按 head_token 幂等重发或标记失败 | 按 head_token 去重（重复段丢弃并回 ACK） |
| 7 | 在飞请求遇云过载 | 无操作（等段完成） | 保留 F8 规则：active flight 不可 preempt；抢占点只选段间隙 |
| 8 | FIN 与在飞段竞态 | 发 FIN 后不再为该 req 发段 | 在飞段执行完但**结果丢弃不回传**（通道 FIFO 要求收发配对完成），随后按 #3 清理 |
| 9 | 边/云重启 | (id, epoch+1) 注册，全量重握手 | 发现新 epoch → 旧 epoch 全部状态作废（队列/pending/租约/注册表按前缀清扫） |
| 10 | 中央宕机 | Route 超时退化本地一致性哈希默认路由 | 继续服务在途；恢复后全量上报重建 GPI |

**两条横向原则**：
1. **通道 FIFO 不可掐断**：任何异常清理不留半个 HCCL 事务——要么配对接完再丢弃，要么对
   确认死亡的 peer 拆通道（唯一例外）。
2. **清理消息必须可靠独立**：FIN/PreemptNotice/Pause 等走独立控制消息（重传+幂等），
   SO 搭车只作冗余路径。

---

## 6. 流程模拟与完备性自查

### 6.1 模拟一：新请求 happy path（E0 → C1）

```
E0 收请求 → 加 e0- 前缀 → tokenize + block_hashes
 → Route RPC → 中央 GPI 匹配 C1 命中 6000/8000 → pin → 返回 {C1, est_hit=6000, lease L}
 → E0 记路由表 → embed 全量 [0,8000) → PF 段（lease L、全量 token ids）发 C1
 → C1 收包(channel=E0) → 准入 OK → confirm_lease → allocate_slots 权威命中 6000 ✓
 → 入队 → 出队 → 前缀选 pair(0,1) → CHER + prepare → 执行 [6000,8000)（可切层）
 → c2e 回末位置 hidden+residual → E0 norm+lm_head+采样 → decode 逐步直发 C1
 → 结束: FIN → 云释放 → 块转空闲 prefix（GPI insert 已上报）✓
```

**结论：✓ 完备**，每环都有机制承载。

### 6.2 模拟二：跨边同前缀命中与 pin 竞态 → em 下消解为纯性能问题

```
E0 的请求在 C1 缓存前缀 P（块转空闲 prefix）
E1 发同前缀请求 → Route → GPI 命中 → 中央选 C1 → pin 飞行期间块被逐 / PF 排队超 lease TTL
 → PF 准入时实命中 4000 < 预估 6000
```

**em 下：✓ 正确性天然闭环，无需补发通道**。边发的是全量 token ids + 全量 embeddings，
云实命中 4000 就从 4000 接着算——输入永远齐备，代价只是多算 2000 token。pin/lease 降级为
纯省算力优化，其失败不触发任何异常路径。（对比 head_tail：那里需要保留补发通道，见主线文档。）

**可选优化（带宽敏感时再启用）**：pin 同步化——中央先发 pin、等云 ack 实际 pinned_len 再回边，
边按 ack 截断发送。Route 延迟 +1 次中央↔云 RTT，换 e2c 带宽节省。默认不启用。

### 6.3 模拟三：云过载 L2 卸载 → G2 已闭环

不通知边直接卸载 → 边持续发 DF 堆积 + 块没卸完被调度。**处置**：Pause/Resume 流控
（已并入 §4.6 L2）；边超时自动升级 L3。

### 6.4 模拟四：边执行中途死亡 → G3 已闭环

c2e 向死 peer 发送可能无限阻塞；同 id 重启身份混淆。**处置**：(id, epoch) 身份 +
通道超时 teardown/重建（§5 #4/#9）。

### 6.5 模拟五：双边并发同前缀（未缓存）路由 → G4 已闭环

各自 miss → 可能分别打到两朵云重复 prefill。**处置**：Route-time PENDING（§4.4）+
一致性哈希收敛残余窗口。

### 6.6 模拟六：chunk ahead / MTP 链 / 层切分穿插

同边不可超越保证 chunk 序；MTP 链三层分析（§3.5）；`_layerwise_*` 单例纪律（§3.6 H3）。
**结论：✓ 无新机制需求。**

### 6.7 缺口登记表

| # | 缺口 | 处置 | 落点 |
|---|---|---|---|
| G1 | ~~pinned_hit 非硬保证缺补发通道~~ | **em 下被全量发送决策消解**：云输入永远齐备，pin 降级为纯优化；截断+补发仅作带宽优化备案 | §2.2 注 2、§6.2 |
| G2 | L2 卸载不与边协调会堆 DF/数据竞争 | Pause/Resume 流控 | §4.6 L2、§6.3 |
| G3 | 重启身份混淆；c2e 死 peer 阻塞 | (id, epoch) + 通道超时 teardown | §5 #4/#9、§6.4 |
| G4 | 双边并发同前缀重复 prefill 窗口 | Route-time PENDING | §4.4、§6.5 |
| G5 | cloud_id 粒度未定义 | cloud_id = （云实例， dp_rank) | §2.1 |
| G6 | 准入记账口径 | kv_free 扣 pinned+在队持有；DECODE_RESERVE 动态估算 | §4.6 L0 |
| G7 | 多边观测性 | (edge_id, cloud_id) 维度打点：出队时延/队列深/pause 次数 | 实施项 |

### 6.8 已验证完备的机制清单

happy path 全链路（§6.1）；跨边 prefix 共享；NACK 重路由闭环；同边因果序；
chunk/MTP/层切分/提前收适配；L3 协同重算时序；中央/云宕机降级。

---

## 7. 与 head_tail 主线的关系

head_tail（首一尾一）设计见 `multi_edge_cloud_design.md`。两模式同一代码路径
（层集合配置驱动：`cloud_layers = 全模型层`、`edge_layers = ∅`）。em 相对主线的差异汇总
（即主线文档 §7 的镜像视角）：

| 模块 | head_tail（主线） | embedding_only（本文档） |
|---|---|---|
| KV 池 | 双池分离（边头尾层 + 云中间层） | **单池**：KVCacheManager 全部下沉云（§4.2） |
| 命中协议 | **有效命中 = min(edge_hit, cloud_hit)**（KV cache 只存 K/V 不存输出 hidden，命中长的一侧产不出另一侧需要的中间量） | **云单边命中成立**（边尾无 attention，历史只经 K/V cache 进入计算） |
| c2e 回传 | 尾层有 attention → 需要云 `[min, end)` 全段输出 hidden | **只需 logits 位置（末 token）hidden**，负载与 prompt 长度解耦 |
| pin 失败 | 需补发通道（边重跑头层，真开销） | **补发通道永不触发**（全量 embeddings 输入永远齐备） |
| L3 重算成本 | 边重跑头层 = 真 transformer 算力 → L2 必须做好，L3 罕见 | 边重发 embeddings ≈ 零成本 → L3 代价低一个量级 |
| 边池过载 | 边自准入/本地 preempt/EdgeFreeNotice | 不存在（边无 KV 负担，过载=排队背压） |
| 边死亡 | 头尾层 KV 丢失 + 云孤儿块靠 TTL GC | **零损失**（边无状态） |
| 云死亡 | 边块同步释放；新云全量重算+边重跑头层 | 仅需边重发 embeddings——最便宜的故障切换 |
| 尾段同步（F5） | 尾段必须重新同步 GPU 状态，否则 KV 写错槽 | 可跳过同步 |
| wire 布局错位后果 | **写错 KV**（污染缓存）+ 乱码 | 仅乱码（无 KV 可污染） |

---

## 8. 实施

### 8.1 改动量排序

| 序 | 项 | 主要落点 |
|---|---|---|
| 1（最大） | **KV 下沉云自管**（§4.2）：CloudKVStore（KVCacheManager+BlockPool+ReqRegistry+LeaseTable）入云 PassiveScheduler；边 scheduler 删除 KV 职责；SO 协议改造 | `core/passive_scheduler.py`、`core/pd_separated_scheduler.py`、`vllm/v1/core/*` |
| 2 | 数据面 HCCL pair 全互联 + 运行时选组 | `vllm_ascend/distributed/parallel_state.py`、`worker.py`、`shared_model_edge_worker.py` |
| 3 | 云侧多源调度（§3：全局单队列+同边不可超越、前缀化、准入配额/NACK、prepare 多槽） | `core/passive_scheduler.py`、`worker/model_runner_v1.py` |
| 4 | 中央调度器新进程（GPI/打分/租约/反熵）+ 边 Route 客户端 + 路由表 | 新增模块 + `core/pd_separated_scheduler.py` |
| 5 | 可靠控制消息（FIN/NACK/Pause/Resume/PreemptNotice/心跳）+ 请求注册表 TTL GC | `v1/engine/passive_core.py`、`patch_engine_core.py` |
| 6 | KV 策略钩子（pin/GPI 上报/TTL 扫描/卸载对接） | 云侧 `block_pool.py`/`kv_cache_manager.py` 钩子 |
| 7 | 配置/启动：(edge_id, cloud_id, epoch, central_addr) 替代 headless 二值 | `vllm/config/parallel.py`、`engine/arg_utils.py`、`ascend_config.py` |

### 8.2 落地顺序

按 §2.4 Phase 1→4。**Phase 2 前置 = 第 1 项**（两边各自管池即撞块）；
Phase 2 同时暴露 §3 并发问题与 §3.5/3.6 回归矩阵；
Phase 3 前实测 E×C 个 HCCL comm group 的显存/初始化开销。

### 8.3 回归测试矩阵（多边新增）

1. §3.4 不变量 1-5（调度纪律）。
2. §3.5 MTP 穿插矩阵：{同边 PF, 他边 PF, 他边 DF, 他边 draft} × {decode 后, draft step 间}。
3. §3.6 H3：slice 间插他边 decode/draft 的精度对齐。
4. §4.3 不变量 1-5（KV 一致性）。
5. §5 异常矩阵 #3/#4/#8/#9 的端到端注入测试。

---

## 9. 问题总结表

| # | 问题 | 结论 | 落点 |
|---|---|---|---|
| Q1 | 边云如何解绑？ | (id, epoch) 三元组注册替代 headless 二值；控制面 per-pair channel；数据面 pair 全互联；KV 下沉云自管 | §2.1、§2.3、§4.2 |
| Q2 | 中央调度器怎么路由？ | GPI 前缀匹配 + 负载心跳打分 + 一致性哈希 tie-break；Route-time PENDING 防重复 prefill | §4.4、§4.8 |
| Q3 | prefill 决定路由、decode 复用？ | 边本地路由表 req_id→(cloud_id, lease)；一次 Route 逐步复用；成本可忽略 | §2.2 及注 3 |
| Q4 | 云如何同时处理多边调度诉求？ | 全局单队列 +（优先级， 到达序）+ 调度不识别来源边；edge_id 惰性解析 | §3.1-3.2 |
| Q5 | 需要传 edge_id 吗？ | 不需要：req_id/head_token 前缀化 + 收包 channel 标识 | §2.2 注 1 |
| Q6 | 每请求查表成本大吗？ | 可忽略（~100ns vs 毫秒 step；表=在途请求数）；中央不持逐请求表 | §2.2 注 3 |
| Q7 | 云要二次组 batch 吗？ | 默认不组（段原样执行）；合并演进预留（拼接+切片回传+merge window 等 6 要点） | §3.1、§3.7 |
| Q8 | 调度顺序要守什么约束？ | 同边不可超越（0812 死锁修复+prepare 校验决定）；优先级只跨边生效 | §3.1 |
| Q9 | 公平性/防打爆？ | 收敛在准入口：逐边 inflight 配额 + 全局上限 + NACK 重路由 | §3.3 |
| Q10 | PD 穿插/层切分/chunk/提前收多边还成立吗？ | 边侧机制零改动；云侧状态机保留（等任一边 decode）；层切分单例锁全局化；提前收键前缀化 | §3.5 |
| Q11 | 不同边请求状态怎么管？ | 请求级状态用全局唯一 req_id 单一名空间；执行上下文单例靠 source-agnostic 调度纪律 | §3.5 |
| Q12 | decode+MTP 链中间插 P/P-draft 有影响吗？ | 通道层✓时序层✓；共享 buffer 层⚠——快照/恢复本就 source-agnostic，补回归矩阵即可 | §3.5 |
| Q13 | NPU-CPU 异步优化多边下有隐患吗？ | 基本成立：耦合全是时序无关结构；唯一邻接依赖（提前 prepare）被 0731 键校验兜住；死锁自由三论据 | §3.6 |
| Q14 | 当前 KV 命中判断在哪？ | 边侧 scheduler（全局唯一 KVCacheManager）；云纯被动——但 em 下边上无 KV，是错位的，应下沉 | §1.1 F6、§4.2 |
| Q15 | 多边多云 KV 归谁管？ | **em 单池：KVCacheManager 整体下沉云**；跨边 prefix 共享免费；边 scheduler 删除 KV 职责 | §4.2 |
| Q16 | 边云 KV 还要互相联系吗？ | em 下极简：资源面云单边自决；生命周期面只剩 FIN 到达+TTL GC、云抢占/卸载通知边 | §4.2 |
| Q17 | KV 何时保留/过期？ | 活跃块不可逐；空闲 prefix 块原生 LRU（命中即 touch）+ 可选 TTL；lease pin 保活在途路由（纯优化） | §4.5 |
| Q18 | KV 怎么与中央同步做 prefix cache？ | GPI 攒批增量 + bloom 反熵；**铁律：仅路由参考，不参与实际分配** | §4.4、§4.7 |
| Q19 | KV 满了怎么重计算？ | 四级：L0 准入 → L1 空闲驱逐（原生）→ L2 host 卸载（Pause/Resume 流控）→ L3 协同重算（em 下 ≈ 零成本重发） | §4.6 |
| Q20 | 各种异常场景怎么处理？ | 10 场景矩阵（边云分列）+ 两横向原则（通道 FIFO 不可掐断、清理消息独立可靠） | §5 |
| Q21 | 边发云的信息要截断命中部分吗？ | 不截断，一律全量（云自管需全量 tokens 算哈希；缺输入问题消解；wire 布局不变）；带宽敏感时截断+pin-ack 优化备案 | §2.2 注 2、§6.2 |
| Q22 | 设计机制完备吗？ | 六模拟走查 + G1-G7 缺口登记闭环 + 不变量清单 | §6 |
| Q23 | em 下云命中 180/200，是否只算 20？边怎么拿前 180 的值？ | 是，直接从 181 算；边**不需要**前 180 的任何值——历史只经 attention 读 K/V cache 进入计算，层间传播 position-wise；em 边尾无 attention，c2e 只需末位置 hidden | §4.4 |
| Q24 | em 与 head_tail 的关系？ | 同一代码路径（层集合配置驱动），em = k=0 退化；差异模块见对照表 | §7 |

**五个显式取舍（评审备查）**：
1. 全量发送——用带宽换正确性简洁与零等待（截断优化有备案）。
2. GPI 最终一致——用同步成本换路由低延迟；延迟下路由质量退化但永不影响正确性。
3. 调度不识别边——用准入口配额替代调度级公平（DRR 被有意简化）。
4. 单 active sliced prefill——用 prefill 并行度换 `_layerwise_*` 单例的内存与安全。
5. 云自管 KV——最大架构改动，换跨边共享与故障域清晰；静态分区为回退方案。

---

## 附录 A：关键文件速查

| 文件 | 职责 |
|---|---|
| `vllm/vllm/config/parallel.py` | 边云开关、NPU 数、`is_edge_node`、拓扑改写 |
| `vllm/vllm/distributed/parallel_state.py` | 进程组布局、`_IS_EDGE_DEVICE` |
| `vllm-ascend/vllm_ascend/ascend_config.py` | `EdgeCloudConfig`（role/mode），`PDSeparationConfig` |
| `vllm-ascend/vllm_ascend/pd_separation_config.py` | ZMQ 端口、dispatch policy 环境变量 |
| `vllm-ascend/vllm_ascend/patch/platform/patch_engine_core.py` | 边 EngineCore PRE_OUT 发布/POST_OUT 接收；finished_req_ids 搭车合并 |
| `vllm-ascend/vllm_ascend/v1/engine/passive_core.py` | 云被动 core、ZMQ Publisher/Subscriber/Channel |
| `vllm-ascend/vllm_ascend/core/pd_separated_scheduler.py` | 边调度器：PF/PL/DF/DL 状态机、head_token、隐藏通道、KVCacheManager |
| `vllm-ascend/vllm_ascend/core/passive_scheduler.py` | 云被动调度器：队列分类、层切片调度、交替状态机 |
| `vllm-ascend/vllm_ascend/worker/worker.py` | NPUWorker 边/云执行路径、HCCL send/recv、CHER、虚拟显存 |
| `vllm-ascend/vllm_ascend/worker/model_runner_v1.py` | embedding_only 分支、`_cloud_prepare_cache`、批序对齐、`_layerwise_*`、快照/恢复 |
| `vllm-ascend/vllm_ascend/distributed/parallel_state.py` | e2c/c2e tensor meta（em 下 e2c 无 residual）、HCCL P2P 原语、draft meta |
| `vllm/vllm/v1/core/kv_cache_manager.py` | KV 分配/释放、prefix 命中入口 |
| `vllm/vllm/v1/core/block_pool.py` | free 队列（LRU 本体）、hash 映射、驱逐 |
| `vllm/vllm/v1/core/kv_cache_utils.py` | `hash_block_tokens` 链式哈希、KVCacheConfig 统一 |
