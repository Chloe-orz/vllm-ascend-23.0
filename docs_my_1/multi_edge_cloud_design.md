# 多边多云边云架构设计

> 版本：v1.5（2026-08-14；…；v1.4 = §2.3.1 静态通信域多边初始化清单与限制；v1.5 = 新增 §2.3.2 全局域 vs 全相联 P2P 对比设计）
> 范围：基于现有 vllm / vllm-ascend 边云 PD 分离代码，从「一边一云强绑定」演进为「多边多云 + 中央调度器」。
> **本文档场景：head_tail（首一尾一）**——边侧跑头尾各 k 层并持有对应 KV，云侧跑中间层并持有中间层 KV。
> embedding_only 模式见独立分册 `multi_edge_cloud_design_embedding_only.md`
> （同一代码路径的 k=0 退化形态，差异对照见该分册 §7）。

**术语**：PF/PL = prefill 头段/尾段；DF/DL = decode 头段/尾段；DRF/DRL = draft 头段/尾段；
e2c/c2e = 边→云 / 云→边数据面方向；GPI = 中央的全局 Prefix 索引；SO = SchedulerOutput。

---

## 1. 现状架构与耦合点（一边一云）

### 1.1 数据流与角色

```
用户请求 → Edge（tokenize + embed + 头 k 层）── e2c: hidden_states+residual ──→ Cloud（中间层，全部中间层 KV）
         ←──────────── c2e: hidden_states+residual ──────────── Edge（尾 k 层 + norm/lm_head + 采样）
```

- 角色由 `--headless` 间接决定（非 headless = 边），`_IS_EDGE_DEVICE` 全局布尔
  （`vllm/vllm/engine/arg_utils.py:2005-2008`、`vllm/vllm/distributed/parallel_state.py:1357-1372`）。
- 跨节点只传 hidden states（HCCL P2P），对端写死（`dst=local_rank+1` / `src=0`，
  `worker.py:1279,1328`、`shared_model_edge_worker.py:587-638`）；KV cache 各自留在本地。
- ZMQ 控制面一对一（`patch_engine_core.py:130-170`、`v1/engine/passive_core.py:84-349`）。

### 1.2 关键事实（多边改造的出发点）

| # | 事实 | 位置 |
|---|---|---|
| F1 | **prefix 命中判断在边侧**：全局唯一 `KVCacheManager` 挂在边 `PDSeparatedScheduler`（继承 vllm Scheduler），`schedule()`→`allocate_slots()`→`cached_block_hash_to_block` 最长前缀匹配，发生在 PF 调度时；云 `PassiveScheduler` 无任何 KVCacheManager | `pd_separated_scheduler.py`、`passive_scheduler.py`（无 KV 代码） |
| F2 | **块 id 空间全局统一**：所有 worker 共享一套 `KVCacheConfig`，num_blocks clamp 到最小；边云 TP 不同时 canonical page 对齐 + worker 本地 rebase | `kv_cache_utils.py:1340-1367, 2061-2207` |
| F3 | head_tail 下边多虚拟 DP worker 共享 global KV buffer（各 dp_rank 的 num_blocks 合并为全局池） | `shared_model_edge_worker.py:655-681` |
| F4 | 释放靠 `finished_req_ids` **搭车**在下一个非 EMPTY SO 上；无独立 FIN/abort 通道、无心跳、云无请求注册表 | `patch_engine_core.py:351-368` |
| F5 | active flight 中的请求不可 preempt（`_is_request_preemptible` 收窄） | `pd_separated_scheduler.py:716-721` |
| F6 | 隐藏通道每 DP 固定 2 prefill + 1 decode；`decode_or_draft_inflight_limit=1`（DECODE 通道 FIFO 保护） | `pd_separated_scheduler.py:235-248` |
| F7 | 云 worker `_cloud_prepare_cache` 单槽 + `req_ids_key` 校验（0731 修复：冻结+校验防串批） | `model_runner_v1.py:941, 6997-7194` |
| F8 | 边云 input_batch 顺序必须对齐（`_reorder_input_batch_to_so_order`）；head_tail+非投机的尾段必须重新同步 GPU 状态（`_skip_tail_sync` 不生效），否则 KV 写错槽 | `model_runner_v1.py:743-767, 2606-2625, 10380-10428` |

### 1.3 强绑定耦合点清单（改造对象）

1. **角色/拓扑**：`is_edge_node` 二值、rank 布局按"唯一边+唯一云"排布。
2. **控制面**：ZMQ 一对一；无 FIN/心跳/注册表（F4）。
3. **数据面**：HCCL comm group 静态、对端常量。
4. **调度**：边侧单套尾段队列/head_token/隐藏通道；云侧单来源队列、`_cloud_prepare_cache` 单槽。
5. **KV**：命中判断与块池管理全在边（F1/F2），多边后"统一 id 空间 + 边独管"两个前提都破。

---

## 2. 目标架构总览

### 2.1 拓扑与角色

```
                    ┌──────────────────────────┐
                    │     Central Scheduler     │
                    │  · GPI（block_hash→cloud） │   ← 仅作路由参考，不参与分配（§4.5 铁律）
                    │  · 云负载视图 / 路由打分    │
                    │  · 租约 lease / Route RPC  │
                    └─────▲──────────────▲─────┘
              Route RPC   │              │  心跳 + GPI 增量上报（每云一条）
        ┌─────────────────┘              └──────────────────┐
  ┌─────┴─────┐   ┌──────────┐                       ┌──────┴──────┐
  │  Edge 0   │   │  Edge 1  │  ...                  │  Edge E-1   │   头尾 k 层 + 本地 KV 池
  └─────┬─────┘   └────┬─────┘                       └──────┬──────┘
        │   e2c/c2e hidden states（HCCL P2P，按 pair 全互联） │
  ┌─────┴──────────────┴────────────────────────────────────┴──────┐
  │  Cloud 0          Cloud 1        ...          Cloud C-1        │   中间层 + 云 KV 池（云自管）
  └─────────────────────────────────────────────────────────────────┘
```

- **身份三元组**：`(edge_id / cloud_id, epoch)`——进程每次启动 epoch+1，对端凭此作废旧状态
  （防重启后新旧身份混淆；§5）。`cloud_id` 粒度 = （云实例， dp_rank)，多 DP 云对外是多个 cloud_id。
- **职责切分**：中央只做路由决策与全局索引，不进数据面、不做逐 token 调度；逐 token 调度仍由
  各边/云本地 scheduler 完成（最大程度复用现有 PF/PL/DF/DL 状态机）。

### 2.2 请求生命周期

```
Edge 收到请求
  1. tokenize + 计算 block_hashes（复用 vllm hash_block_tokens，纯 CPU）
  2. 边本地 allocate（头尾层池）→ 得 edge_hit；边池不足 → 本地排队/preempt，不发 Route（§4.2）
  3. Route RPC → 中央: {edge_id, block_hashes, prompt_len, priority}
        中央返回: {cloud_id, est_hit_len, lease_id}（打分见 §4.9；est_hit 仅参考）
  4. 边记录路由: req_id → (cloud_id, lease_id)     ← prefill 决定，decode 复用
  5. PF 段（全量 token ids + 边侧头尾层 block table + lease_id + channel）发目标云，
     hidden states 按 §4.5 发送区间规则全量发出（注 2）
  6. decode 每步直接查本地路由表直发同一云，不再询问中央
  7. 请求结束/abort → 显式 FIN 控制消息（注 3）→ 双边释放；云块转空闲 prefix 缓存（§4.6）
```

> **注 1（req_id 全局唯一：云侧包装，边不感知）**：vllm 默认 `random_uuid()`，但 OpenAI 协议
> 允许客户端显式指定 request_id（`chat_completion/protocol.py:352`、
> `completion/protocol.py:129-132`），两边用户传相同 id 会撞。**前缀化不做在边侧，而做在云侧
> 入口适配层**：云对每个边有独立 channel，收包时 channel 即标识 edge_id，云在入口统一包装
> `cloud_req_id = f"e{edge_id}-{orig_req_id}"`（head_token 同理包成 `f"{edge_id}:{orig_token}"`），
> 云内所有结构（registry、pending_heads、prepare cache 键、调度队列）一律使用包装后的 id；
> **云→边的所有回传（c2e 数据面、NACK、Pause/Resume、PreemptNotice 等）在出口适配层统一剥离
> 前缀**，边看到的永远是自己的原始 id。效果：边侧零改动、完全不感知多边命名空间；云内键协议
> 保证全局唯一；消息线上不传 edge_id。纪律：所有云→边消息必须经出口适配器剥离前缀，
> 漏一处 = 边不认识自己的请求（纳入 code review 检查点与单测）。

> **注 2（全量发送，设计决策）**：边→云不按命中截断。理由：① 云自管 KV 需全量 token ids
> 本地计算链式 block hash（父哈希依赖）；② 云实命中低于预期时直接用已有输入多算一段，
> **不存在"缺输入"的正确性问题**；③ wire 布局恒 = 全量 prompt 行数，批序对齐不变。
> head_tail 下"全量"= 边头层前向覆盖 `[min(edge_hit, pinned), end)`（§4.5）。
> 代价：e2c 带宽与 prompt 长度成正比；带宽敏感时的截断优化备案见 §6.2。

> **注 3（路由表成本）**：边侧 req_id→(cloud_id, lease_id) 是每在途请求两个字段，dict 查询
> ~100ns vs 毫秒级 NPU step，表大小=在途请求数、结束即删——成本可忽略。**中央不维护逐请求
> 路由表**（路由结果边自持；云宕机时中央广播、各边扫本地表重路由）；中央长期状态只有
> GPI（按 block 数增长，与请求数解耦）+ 云负载视图（C 条）。

### 2.3 通信面改造

| 层 | 现状 | 改造 |
|---|---|---|
| 边↔中央 | 无 | Route RPC（REQ/REP 或 gRPC） |
| 云→中央 | 无 | 上报通道（PUSH）：GPI 增量 + 负载心跳（§4.8） |
| 边↔云控制面 | 单 `_pp_pd_channel` | 边：`dict[cloud_id → Channel]`；云：每边一个 subscriber channel，**收包 socket 即来源**；新增独立可靠控制消息（FIN/NACK/Pause/Resume/PreemptNotice/EdgeFreeNotice/心跳，带重传+幂等，不搭 SO 便车） |
| 边↔云数据面 | 静态 PP 对端 | **方案 A（起步）**：每 (edge, cloud) worker pair 建独立 HCCL send/recv comm group（全互联），运行时按段内 req_id 前缀解析 edge_id 选组；**方案 B（远期）**：hidden states 走 Mooncake/RDMA 动态端点，支持云弹性扩缩 |
| 隐藏通道 | 每 DP 固定 3 条 | 按 (edge_id, cloud_id) pair 分池；通道号由**边**分配随段携带，云只消费 |

### 2.3.1 静态通信域（无动态扩缩）：多边多云的初始化清单与限制

方案 A 采用**启动期一次性建立全局通信域**的静态模型。多边多云场景下，启动时必须初始化：

| 层 | 初始化内容 |
|---|---|
| **进程组底座** | 所有边、所有云的全部 NPU 加入**同一个** torch.distributed world group（TCPStore/env 做 rendezvous）；任一成员缺席，全员 init 卡死 |
| **角色注册表** | 静态映射表 `edge_id / cloud_id ↔ rank 集合`，全员一致（替代原来的 `local_rank < edge_npu_count` 二值判定）；`(id, epoch)` 中 epoch 全部从 0 开始 |
| **并行分组** | 各云/各边内部的 TP/DP/EP 组按 pair 拓扑切分（原 PP=2 改写逻辑扩展为 pair 布局） |
| **数据面 HCCL 组** | **每 (edge_i, cloud_j, dp_rank) pair × 3 条隐藏通道**（PREFILL_1/PREFILL_2/DECODE）建独立 comm group，共 E×C×DP×3 个；运行时按段内包装 id 解析 edge_id 选组 |
| **tensor meta** | 每个 pair 双方各自从 config 独立预计算 e2c/c2e 元数据（线上不传元数据，故配置必须严格一致） |
| **CHER 缓冲** | 每 pair 每通道的 recv buffer 预分配（按在飞上限封死：2 PF + 1 D + 2 draft） |
| **控制面 ZMQ** | 边：`dict[cloud_id → channel]`；云：每边一个 subscriber channel；端口按 `(edge_id, cloud_id, dp_rank)` 静态规划偏移 |
| **中央调度器** | 地址启动期静态配置给所有边云；Route/上报通道建连 |
| **KV 配置** | **每云独立**决定自己中间层池的 `num_blocks`/spec；边独立决定头尾层池（不再全集群统一 clamp） |

**限制（静态模型的代价）**：

1. **成员集合启动即冻结**：任何加云/加边/减云都要重建 world group = **全集群进程重启**，
   无"热加入"概念。
2. **组数量平方级增长**：E×C×DP×3 个 HCCL comm group，每个占 device 侧资源（通信 buffer、
   stream），且 HCCL 对单进程 comm 数有实际上限——**Phase 3 前必须小集群实测建组耗时、
   显存占用与上限**（§8.2）。
3. **初始化时间随规模增长**：world rendezvous + 全互联建组都是全员同步操作，
   任何一台机器故障 = 全集群起不来。
4. **故障恢复弱**：成员重启后必须以**相同 rank、相同端口**归位（静态表里没有"新成员"概念）；
   epoch 机制只能作废旧状态，通信组本身不能动态重建——死掉的 pair 通道要么等原进程归位，
   要么重启全集群。
5. **端口/地址规划静态化**：base+offset 推导方案在规模变化时要重新规划，多实例共部署易撞端口。
6. **不支持滚动升级**；**容量僵化**：云池大小启动固定，闲不能缩、忙不能扩。

**出路（方案 B，远期）**：hidden states 改走 Mooncake/RDMA 等支持动态端点的传输层——成员
注册/发现由传输层负责，云的加入退出变成"注册一个新端点"而非"重建通信域"；届时中央调度器
顺势承担成员注册中心角色（它已有心跳与广播通道）。

### 2.3.2 两种通信域方案对比设计（全局域 vs 全相联 P2P）

> 控制面（ZMQ/TCP）与数据面（HCCL）分开设计。结论先行：**两方案的控制面几乎相同
> （ZMQ 本就独立建连），差异集中在数据面的建域方式**；全相联 P2P 可行的根本原因——
> 本系统运行时**不需要任何跨实例集合通信**（hidden 只走 P2P，EP/TP/DP 组都在实例内）。

#### 方案 A：全局域（Global World）

```
┌──────────── 全局 world group（全部边+全部云的所有 NPU）────────────┐
│  Edge0:[n0 n1]   Edge1:[n2 n3]   Cloud0:[n4..n7]   Cloud1:[n8..]   │
│  子组 = 实例内 TP/DP/EP 组 + pair 通道组 {n_i, n_j} × E×C×DP×3      │
└─────────────────────────────────────────────────────────────────────┘
```

- **数据面**：一个 torch.distributed world（HCCL backend）罩住所有 NPU；实例内 TP/DP/EP 组
  与 pair 通道组（2-rank comm）全部用 `new_group` 从 world 切出。建组一致性由 world 语义
  保证（全员调用、顺序一致）。
- **控制面**：ZMQ per-pair channel（与方案 B 相同）；地址发现复用 world 的 TCPStore
  （当前 `master_port+1+dp_rank` 约定的直接扩展）。
- **初始化**：全员一次 rendezvous + barrier；任何成员缺席 = 全员卡死。
- **配置分发**：world broadcast / TCPStore，现成。

#### 方案 B：全相联 P2P（独立域 + pair 互联）

```
┌─ Edge0 独立域 ──┐                          ┌─ Cloud0 独立域 ──┐
│  n0 ══ n1       │                          │ n4══n5══n6══n7   │
│  (自己的 world,  │                          │ (自己的 world,    │
│   内部 TP/DP)   │                          │  内部 TP/DP/EP)  │
└──┬──────────────┘                          └──┬───────┬────────┘
   │   pair comm {n0,n4} ×3通道（2-rank，带外建组）│       │
   └───────────────────────────────────────────┘       │
   │   pair comm {n0,n8} ×3通道 ──▶ Cloud1 独立域 ……    │
└─────────────────────────────────────────────────────┘
```

- **数据面**：每实例一个独立 torch 域（自己的 master port/store），内部 TP/DP/EP 组建法与今天
  完全相同；跨实例只建 **2-rank pair comm**（每 pair ×3 通道），用 HCCL 带外建组
  （`hcclCommInitRootInfo` 类接口：root info/rank table 经控制面交换，无需共享 world）。
  **运行时纪律：禁止任何跨实例集合通信，pair P2P 除外**——这条纪律保证方案 B 永远可行。
- **控制面**：ZMQ per-pair channel（与方案 A 相同）；**发现机制换为中央调度器兼任注册中心**——
  各实例启动时向中央注册 `(id, epoch, rank→IP:port 表)`，从中央拉取对端表，再经 ZMQ 控制通道
  交换 HCCL root info 完成 pair 建组。
- **初始化**：各实例独立 init（互不等待）；pair 建组按需双边握手，可分批/懒加载。
- **配置分发**：中央统一分发（它本就有心跳/广播通道）。

#### 对比表

| 维度 | A：全局域 | B：全相联 P2P |
|---|---|---|
| 初始化耦合 | 全员 rendezvous，一台故障全集群起不来 | 各实例独立 init；pair 握手只涉及两端 |
| 干活组数量 | 1 world + E×C×DP×3 子组 | 每实例 1 域 + E×C×DP×3 pair 组（**数量相同**，差别只在 world 这把"伞"） |
| 控制面 | ZMQ + TCPStore 发现 | ZMQ + 中央注册发现（差异仅此一处） |
| 跨实例集合通信 | 可用（world barrier/bcast），但业务不需要 | 不可用，也不需要（纪律保证） |
| 故障域 | world 级操作可能因任一成员死亡受阻；部分 HCCL 实现 world 会"中毒" | 死亡只影响其 pair 通道；他实例集合通信无感 |
| 单点重启 | 原则上全集群重 init | 实例独立重启 + 只重建自己的 pair（配合 epoch 语义） |
| 扩缩容/滚动升级 | 不支持（成员冻结） | 天然支持：新实例 = 注册 + 建 pair，不碰存量 |
| 实现成本 | 最小（贴合现状，torch 切子组/TCPStore 现成） | 需新增：注册协议、root info 交换、pair 建组管理 |
| HCCL 风险 | 无（现网验证过） | 需验证：2-rank 带外建组的性能与现网 world 子组一致；单进程 comm 数上限相同 |

#### 可行性结论与迁移路径

**方案 B 可行**，依据：① 运行时无跨实例集合通信需求（设计纪律）；② HCCL 支持无共享
world 的 2-rank 带外建组（PD 分离 KV 直传/llm-datadist 等同款用法）；③ pair 组数量与
方案 A 相同，资源开销不增加；④ 控制面复用同一套 ZMQ channel，仅发现机制替换。

**迁移路径**：Phase 2-3 用方案 A（改动最小）；但**从第一天起执行"无跨实例集合通信"纪律**，
则 A→B 只是初始化方式的替换，数据面零改动。方案 B 落地后，扩缩容、滚动升级、单实例
重启全部解锁，且不再需要"方案 B：Mooncake/RDMA"作为独立演进项（P2P 动态建组已覆盖其
核心价值；更大规模的弹性可再评估 RDMA）。

### 2.4 分阶段落地

- **Phase 1**：1 边 1 云 + 中央调度器（路由固定返回 cloud 0），打通 Route RPC 与 GPI 上报，不改行为。
- **Phase 2**：N 边 1 云。**前置：KV 云自管/双池拆分（§4.2）**——两边各自管池即撞块。攻云侧多源调度（§3）。
- **Phase 3**：N 边 M 云。pair 全互联 HCCL + 真路由打分；先小集群实测 E×C 个 comm group 的显存/初始化开销。
- **Phase 4**：KV 卸载/协同重算/反熵对账（§4.7-4.8）。

---

## 3. 云侧多边调度

### 3.1 设计约束

1. **调度不识别来源边**：一张**全局调度队列**，出队只看 （优先级， 到达序号）。edge_id 只在三个
   时刻**惰性解析**：执行时选 HCCL pair group、算完回传 c2e、失联清理——全部经 req_id 前缀或
   收包 channel。
2. **同边不可超越（唯一顺序硬约束）**：同一边的段必须按到达序执行。依据：0812 死锁修复
   （两态一律按到达序）+ `_cloud_prepare_cache` req_ids 校验假设云按发送序消费。全局 FIFO
   天然满足；优先级插队时"优先级只跨边生效，同边后段不得超越前段"。
3. **默认不二次组 batch，但设计不排除**：段原样执行；数据结构保留合并演进能力（§3.7）。
4. **键天然全局唯一**：req_id/head_token 由云在收包入口包装前缀（§2.2 注 1，边不感知），云内一律用包装后的裸键。
5. **故障域隔离**：一边异常/失联不得卡住他边队列。

### 3.2 数据结构与主循环

```python
class SchedSeg:                      # 全局队列元素 = 某边组好批的原始段
    head_token: HeadToken            # f"{edge_id}:{uuid}"，裸键即唯一
    req_ids: tuple[str, ...]         # 各 req_id 带 e{edge_id}- 前缀
    kind: SegKind                    # PF / DF / DRF（决定优先级档）
    num_tokens: int
    kv_footprint_blocks: int         # 准入估算的 KV 需求
    arrival_seq: int                 # 全局单调到达序号
    priority: int
    lease_id: str | None
    payload: SchedulerOutput         # 原样下发

class CloudScheduler:
    queue: deque[SchedSeg]
    pending_heads: dict[HeadToken, SchedSeg]      # 已出队待回传
    edge_stats: dict[int, EdgeStats]              # 只记账（inflight/心跳/状态），不参与排序
    global_prefill_inflight_limit: int
    kv_watermark_high/low: float = 0.95 / 0.80    # 滞后防抖动
    prepare_cache: LruSlots                       # 单槽 → 2~4 槽 LRU，键=req_ids 全序元组
```

```python
def step(self):
    # ① 收包：每边一个 channel，socket 即来源；准入口记账 + 段入全局队尾
    for channel, msg in self.poll_all_channels():
        self.admit(channel, self.classify(msg))          # ③

    # ② 出队：最高优先级档中取"是同边队首"的最早段（同边不可超越）
    seg = self.pop_next_schedulable()
    if seg is None: return EMPTY

    # ④ 原样下发；此刻才解析来源边，选 pair HCCL group（通道号段内携带）
    edge_id = parse_edge_id(seg.req_ids[0])
    self.worker_select_hccl_pair(edge_id, seg.hidden_channel)

    # ⑤ 执行后回调：pending_heads 标记可回传；c2e 按 req_id 前缀选组发回；
    #    更新 inflight / GPI 增量（§4.8）；KV 水位检查（§4.7）
    return seg.payload

def admit(self, channel, seg):
    stats = self.edge_stats[channel.edge_id]
    need  = estimate_kv_blocks(seg)                       # 扣 pinned + 在队持有（§6.4 G6）
    if (stats.inflight_prefill >= self.per_edge_quota(channel.edge_id)
            or self.global_prefill_inflight >= self.global_prefill_inflight_limit
            or self.kv_free_blocks < need + DECODE_RESERVE):
        if seg.retryable:                                # 新 prefill
            self.send_nack(channel, seg.head_token, ...) # 沿收包 channel 直回；边重新 Route
            return
        self.defer_or_preempt(seg)                       # decode 不可拒绝：排队或触发 §4.7
        return
    stats.inflight_prefill += 1
    self.confirm_lease(seg.lease_id)                     # §4.6；缺失/过期只损失优化
    self.queue.append(seg)
```

### 3.3 公平性与防打爆（准入层解决，不动调度序）

调度序保持极简（优先级， 到达序）。公平性收敛在 `admit()` 一处：
① 逐边 inflight 配额（可配权重），超限 NACK/排队，不挤占他边在途名额；
② 全局上限 + KV 余量硬校验。后续要加权重公平/租户隔离只改这里。

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
t≈3  prefill 档 → A(seq 早于 B，E0 队首✓）→ step#2=A → pair(0,0) 收全量 hidden
t≈5  step#3=B；B 的前 6000 tok 命中 pin 块，云只算 2000 tok（全量输入在手，无需补发）
t≈10 A 完成: pending_heads["0:tokA"] 可回传 → c2e 按前缀回 E0 → A 进入 decode
     A 的块 cache_blocks → GPI insert 上报；E0.inflight 释放
t=12 新波: E2→PF(C) ADMIT；E0→DF(A) ADMIT → queue=[C#4, DF_A#5]
     出队: decode 档 → step#4=DF_A；step#5=C
t=15 NACK 演示: E1→PF(D, 需 1000 blk > kv_free≈600−100)
     → NACK 沿 E1 channel 直回 → E1 重新 Route（中央临时调低 C0 权重，可能去 C1）
```

**"同边不可超越"演示**：E0 连发 PF(X)#8、DF(Y)#9，decode 优先也不能先出 Y（Y 不是 E0 队首，
X 未调度）→ 先出其他边的 decode 队首段，否则出 X。纯 FIFO 下此情形不出现。

**关键不变量**（可直接作单测断言）：
1. 下发的每个段都是某边原始组好批的 SO，不拆不合。
2. 任意时刻同一边的段执行顺序 = arrival_seq 顺序。
3. `Σ edge_stats[*].inflight_prefill ≤ global_prefill_inflight_limit`。
4. decode 头段永不被 NACK（只 defer 或触发卸载/抢占）。
5. 任一边 DEAD 后其段从队列剔除、inflight 归零，其他段相对顺序不变。

### 3.5 PD 框架优化机制的多边适配

| 机制 | 当前实现逻辑 | 多边适配结论 |
|---|---|---|
| **PD 穿插（边侧）** | `PrefillState` 三态（IDLE/LOW/HIGH）门控 PF vs DF/DL 派发（`pd_separated_scheduler.py:893-902`）；`_force_*_last` 严格交替（`:328-334`）；`_pending_tail_count` 门控进 running（`:2359-2369`） | 纯边内机制，**零改动** |
| **PD 穿插（云侧）** | `CloudSchedulingState` 两态交替防同向通道 FIFO 死锁；派发 prefill slice 后 10ms throttle 等 decode（`passive_scheduler.py:537-582`） | 状态机保留，"等 decode"变为等任一边；通道 per-pair 化后死锁域缩小到单 pair（由约束 2 保证）；多边下 decode 更充足，throttle 命中率上升 |
| **层切分** | PF 按 YAML token 阈值切片；slice 0 续算状态存 model_runner **单例** `_layerwise_*` 12 项（`model_runner_v1.py:839-852`）→ 全云同时只允许一个 sliced prefill；slice 间可插 decode；非末 slice 经 `_freeze_intermediate_tensors` clone | 单例锁与来源边无关，保留为全云全局约束；slice 间可插**任一边** decode；演进项：多槽化（按 head_token 键控）默认不做 |
| **切 chunk** | vllm 原生 budget 切 chunk（序列维），边把每个 chunk 包装成 PF/PL 对；`chunk_prefill_prior` 允许同请求下一 chunk 提前发；与层切分（层维）正交 | 零改动，只依赖约束 2 保证 chunk 序 |
| **提前收** | CHER guard thread 提前 irecv + `cloud_prepare_early` 提前做 input prep/attn metadata，与边 segment 计算重叠；`_cloud_prepare_cache` 单槽 + `req_ids_key` 校验 | 前缀化后键天然不串边；单槽→LRU 多槽（§3.2）；irecv 的 pair group 按段内前缀解析；另见 §3.6 H1 |

**decode 与其连续 MTP draft 步之间穿插 P/P-draft 的分析**：

- 当前约束：DF→DL、DRF→DRL 严格交替（`_force_*`）；DECODE 通道 `decode_or_draft_inflight_limit=1`；
  draft 可 pipeline（`draft_remote_pending_limit=2`）；decode 与 draft 步之间边侧允许插 PF，
  正确性靠严格交替 + 快照/恢复（0801 的 `topk_indices_buffer` 快照/恢复、
  `_snapshot_verified_draft_tokens`/`_patch_deferred_draft_token_ids`，`model_runner_v1.py:3522-3654`）。
- 多边影响三层分析：

| 层 | 影响 | 结论 |
|---|---|---|
| 通道层 | draft/decode 走本 pair DECODE 通道；他边 PF 走他 pair PREFILL 通道 | ✓ FIFO 互不干扰 |
| 时序层 | 他边段插入只延迟本边 DRL 回传，本边通道消息序不变 | ✓ 仅延迟不错序 |
| 云侧共享 buffer 层 | `topk_indices_buffer`、`_layerwise_*` 会被**任何来源**的插入覆盖 | ⚠ 唯一真风险 |

- 风险不是新类别：快照/恢复按**执行序列**触发（"下一段不是本 draft 链延续就快照"），与 SO
  来源无关，多边下自动成立。待办：① 走查确认所有快照/恢复判定点无"同一边"隐含假设；
  ② 回归矩阵 {同边 PF, 他边 PF, 他边 DF, 他边 draft} × {decode 后, draft step 间} 精度对齐测试。

### 3.6 NPU-CPU 异步重叠机制的多边隐患分析

**前提变化**：1-1 时边云是强同步确定性交替（EXPECT_ALTERNATION、`_force_*_last`），所有异步
重叠优化（CHER、prepare-early、层切分穿插、异步采样修正）都建立在"对端下一步可预测"上。
多边后云对任一边非确定调度。审判标准：**正确性依赖"邻接性/可预测性"还是"时序无关结构"**。

| # | 机制 | 结论 |
|---|---|---|
| H1 | **提前 prepare 的邻接假设** | attn_metadata/logits_indices 内嵌 prepare 时刻行索引；多边下 prepare 与消费之间可能插入他边执行、行序漂移。**0731 的 `req_ids_key` 校验恰好兜住正确性**（成员/顺序变→失配→慢路径重 prepare）。纪律：任何 fast path 不得跳过键校验；失配率上升属性能问题，靠槽数+打点收敛 |
| H2 | per-pair 有界在飞 | **结构性安全**：跨节点耦合全部 = per-pair FIFO + 在飞上限（2 PF + 1 D + 2 draft），他边调度不确定性伸不进 FIFO；推论：全局队列长度有上界 = Σ 各边在飞上限 |
| H3 | `_layerwise_*` 单例 + 他边 decode 穿插 | 机制同今日（slice 间插 decode 本是设计内场景），频率上升；回归矩阵扩"他边"用例；走查点：`_layerwise_positions` 等若存持久缓冲区**引用**而非 clone，是现网已有隐患，多边放大 |
| H4 | ZOMBIE/死 peer 的异步收发配对 | 由异常原则覆盖（§5）；isend/irecv 句柄等待与通道清理必须成对 |
| H5 | **死锁自由性** | 无环形等待，三论据：① 数据 eager 推送（边发段即 isend，云执行不依赖边后续动作）；② 云 work-conserving（同边约束只跳过不卡死，队首段永可执行）；③ 在飞有界 + 清道消息走独立通道不被队列阻塞 |
| H6 | 性能新现象 | convoy 抖动（打点定位）；CHER 提前 irecv 缓冲持有变长（per-pair 缓冲池按在飞上限配置封死上界）；10ms throttle 参数多边下需重校 |

**结论**：异步体系基本成立——跨节点耦合全部是时序无关结构（per-pair FIFO + 有界在飞 +
键校验）；唯一邻接依赖（H1）被现有校验兜住。多边工作量集中在性能域（H6）与回归覆盖（H3），
不是新的正确性缺陷类别。

### 3.7 演进预留：跨边组 batch（默认不开启）

合并批 = 各边段按 req_id 前缀分组的连续拼接；算完按段边界切片、按前缀各回各边。
**边侧几乎零改动**（每边收发行序 = 自己 e2c 发送序）。实施时必须处理 6 点：

1. **merge window + 超时发车**：合并 step 须等所有贡献边 payload 到齐，慢边拖累快边（convoy）；
   等齐或超时（如 2ms）即发车。
2. **部分失败降级**：一边中途 DEAD，云须能剔除其行、降级为剩余边子批重建元数据执行。
3. **置换收在云内**：现有"边镜像云 reorder"机制在合并模式下失效（边不知合并序），c2e 切片
   须按"合并计算序→各边发送序"逆置换切。
4. **同边不可超越**：每边每个合并批最多贡献一个段。
5. **校验与回调按段粒度**：prepare cache 键 = 合并 req_ids 元组；一个合并 step 触发多段回调。
6. **记账不变**：配额准入时已按段记过。

### 3.8 边失联处理

```
last_heartbeat 超 T1(5s)  → SUSPECT：该边的段标记不可调度（保留队列位置，等恢复）
超 T2(30s)                → DEAD：
  - 按 req_id 前缀扫描全局队列与 pending_heads，剔除该边的段
  - 在途请求标记 orphan，释放其云侧 KV（块转空闲 prefix，hash 保留供他请求命中）
  - 该边 lease 全部过期；上报中央注销 PENDING
  - 隐藏通道池/prepare 槽清理；c2e 向死 peer 的发送超时 + 通道 teardown/重建（§5 原则 1 例外）
  - 边以 (edge_id, epoch+1) 重启后全量重握手，旧 epoch 状态已全部作废
```

---

## 4. KV cache 管理（核心章）

### 4.1 复用的 vllm 原生机制（先讲清原生逻辑）

**① Block 分配与引用计数**（`kv_cache_manager.py:340-447`、`block_pool.py`）
- `allocate_slots()` 从 `free_block_queue` 头部取块；`free(request)` 把块 ref_cnt 减到 0 后**追加到
  队列尾部**。**ref_cnt=0 ≠ 失效**：hash 映射（`cached_block_hash_to_block`）仍保留，仍可被命中。
  真驱逐发生在分配侧——弹出带 hash 旧块复用时才删映射。
- free 队列尾进头出 = **天然 LRU**；命中即 touch（命中块重新 ref>0 离队，释放后回尾部）——
  热前缀长寿、冷前缀自然淘汰，无需额外代码。

**② Prefix 命中**（`kv_cache_utils.py:560-706`、`kv_cache_manager.py:210-230`）
- 链式哈希（父块 hash + 本块 token ids + extra keys）保证前缀链唯一；分配前找最长连续前缀命中，
  命中块 ref+1，只对 miss 段分配新块；算完的块由 `cache_blocks` 插入映射。

**③ 抢占与重算**（vllm v1 原生）
- allocate 失败 → preempt 优先级最低/最晚到达的 running 请求（free 全部块、退回 waiting）；
  重调度时重走 prefill，刚释放的块若未被复用可部分命中（"recompute preemption"）。
- 边云现状收窄：active flight 中不可 preempt（F5）；多边下沿用此规则，抢占点选在段间隙。

### 4.2 所有权：双池分离（head_tail 主线）

多边多云后"统一 id 空间 + 边独管"两个前提都破（各云容量不同；多边各自分配撞块）。
且边云存储内容不同（边头尾层、云中间层），块数与索引本就应是两个独立名字空间——**不统一，明确拆开**：

```
Edge i 本地池：头 k + 尾 k 层 KV   ← 边 scheduler 自管（只服务本边，无竞争，原生逻辑几乎不动）
Cloud j 本地池：中间层 KV          ← 云自管（KVCacheManager 下沉，PassiveScheduler 升半主动）
```

- **每请求两张 block table**：边表（边分配，随 SO 携带）+ 云表（云 PF 准入时自分配）。
- **跨边 prefix 共享免费获得**：同云一个池一个 hash 索引，E0 缓存的前缀 E1 直接命中。
- SO 协议：不再携带云的块分配；携带全量 token ids + 边侧块表 + lease_id。
- 边 scheduler 的 KV 职责缩减为只管头尾层池。
- 过渡备选：静态分区（每云块池按边切分）——改动最小但跨边不共享、利用不均，仅作回退。

#### 4.2.1 边云 KV 联动边界（独立 vs 必须联系）

**原则："块"的所有权决定完全各自独立；"请求"的存在性决定必须双边一致。**

| 完全独立（本地决定，不通知对侧） | 理由 |
|---|---|
| block id 空间 / 分配算法 / 块表结构 | 两个名字空间，无交集 |
| **空闲 prefix 块的驱逐与命中**（LRU/TTL） | 一侧逐了另一侧没逐，仅使 `edge_hit ≠ cloud_hit`——分歧只改变各自重算量，发送区间规则（§4.5）兜底，无正确性问题 |
| host 卸载内部机制（D2H/H2D、host 池逐出） | 单边资源决策；对侧只感知 Pause/Resume |
| GPI 上报节奏 | 软状态，仅影响路由参考质量（§4.5 铁律） |

**必须联动（协议保证，缺了就是泄漏/垃圾块/乱序）**：
1. **请求生命周期双侧同步**：创建 = 双侧 admit 都成功（任一侧 NACK 整体不开始）；
   释放 = FIN 双边到达 + 双侧 TTL GC 兜底。一侧残留块 = 唯一泄漏源。
2. **活跃请求的单侧抢占/卸载必须通知对侧**：云→边 `PreemptNotice`/`PauseReq`（边收到云 L3 后
   同步释放边块）；边→云 **新增对称 `EdgeFreeNotice`**（边本地 preempt/abort 后云的中间层块
   即成垃圾，立即释放不等 TTL）。判定：任何一侧对仍被对侧引用的请求做 free 决定时，
   通知是该决定的一部分（先停调度→双清→确认）。
3. **num_computed 推进一致性**：两池各记账但同值，靠段协议推进（PF/DF 携带、PL/DL 回报）；
   不一致走丢段异常路径（§5 #6），不做自动对账。

**软联动（可延迟/失败/拒绝）**：Route 期 est_hit 与 pin、GPI 上报——"失败只损失优化收益"。

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
pin 创建 → confirm 时引用转请求 → sweeper 超时解 pin。不变量：PINNED 块 ref_cnt ≥ 1 不会被弹出复用；
lease 是优化，任何失败路径不得阻塞段处理。

**(d) OffloadStore（新增）**：`req_id → {host_slots, block_map(原NPU block→host slot), valid}` +
`host_arena`（pinned DDR 池，自身 LRU；满则最旧 handle 失效 → 该 req 退化 L3 重算）。
D2H 完成后 NPU 块 free（hash 映射随块复用失效，可恢复性由 handle 承载）；恢复时按 block_map
H2D 到新块，重建 req_to_blocks。

**(e) WatermarkGovernor（新增）**：`NORMAL/OFFLOADING` 两态 + 高低水位（0.95/0.80 滞后）+
每分钟抢占次数窗口（防雪崩）；受害者选择输入来自 ReqRegistry（decode 间隔、剩余长度估计）。

**(f) GpiReporter（新增）**：insert/evict/pending/solid 攒批（200ms 或 Δ≥64 块）+ bloom 摘要；
钩子挂接：`cache_blocks` 后、free 队列弹出带 hash 块时、PF 准入确认后（pending）、PF 完成后（solid）。

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

### 4.4 云自管执行逻辑（head_tail 逐步）

**PF 段**：

```
边侧先行：
 1. 边本地 allocate_slots（头尾层块）→ edge_hit（本地权威）；边池不足 → 本地排队/preempt，不发 Route
 2. Route RPC → {cloud_id, est_hit, lease}；边记录路由
 3. 边头层前向 [min(edge_hit, pinned), end)，全量发出（§4.5 发送区间规则）
 4. PF 段 = {head_token, 全量 token ids, 边侧头尾层 block table, lease_id, channel} → 发云
云侧：
 5. 收包校验（channel → (edge_id, epoch)；未知/旧 epoch → 丢弃+告警）
 6. 准入（配额/全局上限/kv_free 扣 pinned+在队持有）→ 可拒绝则 NACK 沿 channel 直回
 7. confirm_lease（缺失/过期 → 跳过，纯少优化）
 8. block_hashes：全量 token ids 本地链式哈希（与边/中央同算法同 block_size）
 9. allocate_slots（仅中间层）→ 权威命中 cloud_hit
    pin 失败致实命中 < min(edge_hit, pinned) → 保留的补发通道请边补算补发该区间 hidden states（§4.5）
10. registry 登记 → 段入全局队尾
11. 出队 → 解析前缀选 pair group → CHER 提前收 + cloud_prepare_early
12. 执行中间层 [min(edge_hit, cloud_hit), end)——两侧起点必须按 §4.5 min 规则对齐，
    命中长的一侧对多出段做"只前向"（产出相同 K/V，复写同值无害）；
    非末 slice 冻结 IntermediateTensors（层切分）
13. 段/slice 完成：cache_blocks → GPI insert（或 PENDING→SOLID）
14. c2e 回 hidden+residual（末 slice）→ 边尾层前向（写尾层 KV 到边池块）→ norm+lm_head+采样
```

**decode 段**：

```
边：本地 allocate_slots 增长（头尾层）→ DF 段携边侧新块信息发云
云：registry 查 req（不存在 → FIN 丢失/epoch 过期异常分支，丢弃并通知源边）
   → allocate_slots 增长（中间层）；失败 → §4.7 L2/L3
   → 执行 → c2e → 边尾层前向 + 采样；last_seen 刷新
   MTP draft 步同通道序执行，快照/恢复纪律同 §3.5
```

**失败语义不对称**（重要）：边 preempt 只丢边块——云的中间层块仍在，恢复后可直接续；
云 L3 则边块也失去意义（无中间层无法 decode）→ 边收到 PreemptNotice 后同步释放边块。

**终结与异常路径**：见 §5 矩阵。

### 4.5 双侧 prefix 命中协议与"GPI 仅参考"铁律

- **有效命中规则（关键，v1.1 修正）**：`edge_hit`（边查本地池，纯本地）与 `cloud_hit`
  （中央 GPI 估算 → 云准入权威复核）**不能独立生效**。根因：KV cache 存的是各层 K/V，
  **不是该层的输出 hidden states**——
  - 例：prompt 8000，`edge_hit=0`、`cloud_hit=6000`。边尾层要把尾层 KV 建到 8000，
    就需要云在 `[0, 8000)` 每个位置的输出 hidden；云命中的 6000 段从未前向过、拿不出输出，
    只能重算 → 云命中部分的计算收益为零（缓存 K/V 只是注意力上下文，仍须前向这些位置
    才能产输出）。
  - 对称例：`edge_hit=6000`、`cloud_hit=2000`。云要从 2000 算就需要边产 h[2000,8000)，
    边头层必须重新前向 [2000,6000) → 边命中部分的收益为零。
  - **结论：有效命中 = min(edge_hit, cloud_hit)，两侧计算起点必须对齐到 min。**
- **可选优化（打破 min 规则的唯一途径）**：额外缓存**段边界 hidden states**——命中长的一侧
  直接返回缓存输出而不重算（云缓存 c2e 输出 / 边缓存 e2c 输出）。显存换重算
  （每请求 ≈ prompt_len × hidden_size × 2B），默认不开启，长前缀高复用场景再评估。
- **发送区间规则**：边头层前向覆盖 `[min(edge_hit, pinned), end)` 并全量发出；
  云执行中间层 `[min(edge_hit, cloud_hit_actual), end)`，多余输入丢弃。
  **pin 失败（实命中 < pinned 且 < edge_hit）时云缺输入 → head_tail 下补发通道保留**
  （边重跑该区间头层前向，真开销）。
- **铁律：GPI/负载视图仅作路由参考，绝不参与任何实际资源分配决定**（中央与云之间有上报延迟）。
  分配/命中/驱逐/pin 执行的唯一权威是各池本地所有者；中央发的 pin 只是"请求"，云可拒绝或
  部分接受（ack 实际 pinned_len）；任何流程不得因 pin 缺失而阻塞。
- **路由打分（中央）**：Route RPC 须携带 `edge_hit`，中央按 min 规则打分；pin 也只需保
  `min(edge_hit, cloud_hit_est)` 段（超出部分对本请求无收益）。

```
score(c) = w1·(min(edge_hit, cloud_hit_est(c))/prompt_len)   # 有效命中（参考值）
         + w2·(kv_free(c)/kv_total(c))          # 心跳余量
         − w3·queue_delay(c)                    # 心跳背压
         − w4·recent_preempt(c)                 # 近期抢占降权
平局 → 按 block_hashes[0] 一致性哈希             # 同前缀天然聚集同云，命中率随时间上升
```

- **Route-time PENDING**：中央决策时即把所选云的前缀 hashes 标 PENDING，后到同前缀请求命中
  PENDING 蹭在途 prefill；云 PF 准入后转 SOLID；路由后 PF 超时未到达则中央 TTL 清除。

### 4.6 过期与保留策略（三级语义）

| 类别 | 语义 | 实现 |
|---|---|---|
| **活跃请求块**（ref>0） | 不可驱逐，只走卸载/抢占（§4.7） | vllm 原生 ref_cnt，无改动 |
| **租约 pin 块** | Route 后、PF 到达前尽量保活 | `pin{lease_id, hashes, ttl=5s}`：云本地 ref+1；PF 准入 confirm 转请求；sweeper 超时解 pin。**全量发送决策后 pin 是纯优化**，失败只意味着多算一段 |
| **空闲 prefix 块**（ref=0，hash 在） | 默认纯 LRU（复用 §4.1① free 队列序）；可选 TTL | TTL 扫描器：每 60s 扫 cached 映射，`now − last_hit_ts > TTL` 且 ref=0 的块删映射并移队首优先复用。默认关闭（LRU 已够），会话周期明显时开启，TTL ≈ 2×会话间隙 |

**设计要点**：驱逐决策全部在各池本地；中央只被动收 evict 上报，不做逐块遥控。

### 4.7 满载四级处理（重计算设计）

前提：云重算中间层需要边重跑头层产 hidden states（head_tail 下是真算力）。四级按代价从低到高：

- **L0 准入控制（不让它满）**：中央路由前估算足迹只路由到余量足够的云；云准入二次核对+NACK；
  边池自准入（§4.4 步 1）。绝大多数"满"在此消化。记账口径：`kv_free` 须扣 pinned + 已准入
  未执行段持有块；`DECODE_RESERVE` 按在跑请求数 × 增长窗口动态估算。
- **L1 空闲 prefix 驱逐（零代价）**：vllm 原生行为（弹出复用即逐），无需新代码；新增的只是
  evict 上报中央。代价只是未来某请求 miss 一段。
- **L2 活跃 KV 异步卸载到 host DDR（head_tail 下必须做好）**：水位 0.95 触发/0.80 解除（滞后）。
  受害者：decode 间隔长、剩余输出长的请求（MTP topk 等附属状态随主 KV 一起处理）。
  **必须与边配合（Pause/Resume 流控）**：云先发 `PauseReq{req_id}` → 边停发该 req 的段 →
  云异步 D2H（可对接已有 SimpleCPUOffloadConnector / RecomputeCPUOffloadConnector）→ 释放 NPU 块；
  恢复：H2D 预取完成 → `ResumeReq` → 边恢复调度。边等待超时可主动升级 L3。
  不做 pause 直接卸载 → 边持续发段在云堆积、块没卸完就被调度（§6.3 G2）。
  D2H/H2D 走 DMA 与计算 overlap；H2D 预取与当前批 overlap。
- **L3 协同重算（兜底，应罕见）**：云 free 受害者全部块（原生路径）→ `PreemptNotice` →
  边释放边块、标记 re-prefill-pending → 下轮重走 PF：全量 token 重新前向头层发出
  （与普通 PF 同构）；云当新 prefill 准入但**优先级提升**；刚释放的块大概率部分命中
  （§4.1③ 原生效应），实际重算量常小于全量。防雪崩：抢占云 `recent_preempt+1` 降权；
  单云每分钟抢占上限；水位滞后。

**L3 时序**：

```
Cloud C0                          Edge E1                     Central
   │  kv_used=96% > 95%              │                          │
   │  选受害者 R(E1 的 req, 已算 3000 tok)                        │
   │  free(R) 块入空闲队列            │                          │
   ├──── PreemptNotice(req) ────────→│  释放 R 的边块             │
   ├──── evict{真驱逐的块} ───────────┼─────────────────────────→│
   │                                 │  下轮: 头层前向 R 的全部 3000 tok
   │  ←── PF'(R, 新 head_token, ─────┤                          │
   │      优先级提升)                 │                          │
   │  准入(优先席) → 命中自查：       │                          │
   │  刚释放的块未被复用 → 命中大部   │                          │
   │  只对 miss 段重算                │                          │
```

### 4.8 GPI 同步协议（云 → 中央）

数据源 = 块池所有者（云自管 → 钩子在云侧 KVCacheManager/BlockPool；静态分区过渡期临时在边）。

| 时机（云侧） | 消息 | 说明 |
|---|---|---|
| `cache_blocks` 插入映射后 | `insert{hashes}`（攒批 200ms 或 Δ≥64） | |
| 分配侧弹出带 hash 旧块复用时 | `evict{hashes}`（攒批） | **请求 free() 时不上报**——块回空闲队列仍可命中 |
| PF 准入完成 | `pending{hashes}` | 与中央 Route-time PENDING 互为确认 |
| PF 计算完成 | `solid{hashes}` | PENDING→SOLID |
| 每 30s 心跳 | `{kv_free, queue_delay, inflight, recent_preempt}` + bloom 摘要 | 负载视图 + 反熵：中央 bloom 粗对账，大面积不一致要求全量重报（重启/丢消息兜底） |

### 4.9 中央调度器职责小结

- GPI（`block_hash → {cloud_id: (state, version, last_seen)}`，SOLID/PENDING）+ 云负载视图。
- Route RPC：输入 `{edge_id, block_hashes, prompt_len, priority}`，输出 `{cloud_id, est_hit, lease_id}`。
- 打分公式见 §4.5；一致性哈希 tie-break。
- **无逐请求路由表、无持久化状态**；宕机可降级（边 Route 超时退化本地一致性哈希默认路由，
  恢复后靠全量上报+反熵重建），可热备。

---

## 5. 异常与容错矩阵

> 现状短板（F4/F5）：无独立 FIN/abort 通道、无心跳、云无请求注册表、active flight 不可抢占。
> 多边后"某边长期无 SO 到某云"是常态，搭车通知不再可靠——下表为完整处置。

| # | 场景 | 边侧处理 | 云侧处理 |
|---|---|---|---|
| 1 | 边过载（embedding/头层积压） | 入口限流/排队背压；新请求 Route 时倾向空闲云 | 无感（只看到流量下降） |
| 2 | 云过载（KV 水位高） | NACK 的新 PF 重新 Route（中央降权该云） | §4.7 四级：NACK → 空闲驱逐 → 卸载 → 协同重算 |
| 3 | 请求 abort | `finish_requests` 本地清理 + **显式 FIN** 发往路由的云（双边释放：边清头尾层块） | 收 FIN：段从队列/pending_heads 剔除、释放中间层块转空闲 prefix、清 prepare 槽 |
| 4 | 边死亡 | — | §3.8 SUSPECT/DEAD + **请求注册表 TTL GC**（必需：边死亡后中间层块成孤儿）；c2e 死 peer 超时+通道 teardown |
| 5 | 云死亡 | 中央广播 → 扫本地路由表，指向死云的请求重路由 + **同步释放边块**（单独存在无意义）；新云全量重算（边重跑头层，无需客户端重发 prompt） | — |
| 6 | 控制面丢包/乱序 | 段超时无回传 → 按 head_token 幂等重发或标记失败 | 按 head_token 去重（重复段丢弃并回 ACK） |
| 7 | 在飞请求遇云过载 | 无操作（等段完成） | 保留 F5 规则：active flight 不可 preempt；抢占点只选段间隙 |
| 8 | FIN 与在飞段竞态 | 发 FIN 后不再为该 req 发段 | 在飞段执行完但**结果丢弃不回传**（通道 FIFO 要求收发配对完成），随后按 #3 清理 |
| 9 | 边云池压力不对称 | 边池不足时本地排队/preempt，不发 Route | 云池不足走 NACK 重路由 |
| 10 | 边本地 preempt（边池满） | 释放边块 + 发 `EdgeFreeNotice{req_id}` | 收通知立即释放中间层块（不等 TTL GC）；请求重排队后按新请求重新 Route |
| 11 | 边/云重启 | (id, epoch+1) 注册，全量重握手 | 发现新 epoch → 旧 epoch 全部状态作废（队列/pending/租约/注册表按前缀清扫） |
| 12 | 中央宕机 | Route 超时退化本地一致性哈希默认路由 | 继续服务在途；恢复后全量上报重建 GPI |

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
 → 边本地 allocate（头尾层）→ edge_hit
 → Route RPC → 中央 GPI 匹配 C1 命中 6000/8000 → pin → 返回 {C1, est_hit=6000, lease L}
 → E0 记路由表 → 头层前向 [min(edge_hit, 6000), 8000) 全量发 → PF 段发 C1
 → C1 收包(channel=E0) → 准入 OK → confirm_lease → allocate_slots 权威命中 6000 ✓
 → 入队 → 出队 → 前缀选 pair(0,1) → CHER + prepare → 执行 [6000,8000)（可切层）
 → c2e 回传 → E0 尾层+采样 → decode 逐步直发 C1
 → 结束: FIN → 双边释放 → 云块转空闲 prefix（GPI insert 已上报）✓
```

**结论：✓ 完备**，每环都有机制承载。

### 6.2 模拟二：跨边同前缀命中与 pin 竞态 → 全量发送后消解为纯性能问题

```
E0 的请求在 C1 缓存前缀 P（块转空闲 prefix）
E1 发同前缀请求 → Route → GPI 命中 → 中央选 C1 → pin 飞行期间块被逐 / PF 排队超 lease TTL
 → PF 准入时实命中 4000 < 预估 6000
```

**全量发送决策 + min 规则下的结论**：云实命中 4000 时，两侧起点按 §4.5 min 规则对齐到 4000，
云需要边产 [4000, end) 的 hidden；边发送区间是 [min(edge_hit, pinned=6000), end)，
缺口 [4000, 6000) → 走保留的补发通道（边重跑该区间头层）。pin 同步化（中央等云 ack 实际
pinned_len 再回边，Route +1 RTT）可把窗口压到最小——head_tail 下价值最高（省边算力+带宽+
避免补发），默认不启用，带宽敏感时再做。

### 6.3 模拟三：云过载 L2 卸载 → G2 已闭环

不通知边直接卸载 → 边持续发 DF 堆积 + 块没卸完被调度。**处置**：Pause/Resume 流控
（已并入 §4.7 L2）；边超时自动升级 L3。

### 6.4 模拟四：边执行中途死亡 → G3 已闭环

c2e 向死 peer 发送可能无限阻塞；同 id 重启身份混淆。**处置**：(id, epoch) 身份 +
通道超时 teardown/重建（§5 #4/#11）。

### 6.5 模拟五：双边并发同前缀（未缓存）路由 → G4 已闭环

各自 miss → 可能分别打到两朵云重复 prefill。**处置**：Route-time PENDING（§4.5）+
一致性哈希收敛残余窗口。

### 6.6 模拟六：chunk ahead / MTP 链 / 层切分穿插

同边不可超越保证 chunk 序；MTP 链三层分析（§3.5）；`_layerwise_*` 单例纪律（§3.6 H3）。
**结论：✓ 无新机制需求。**

### 6.7 缺口登记表

| # | 缺口 | 处置 | 落点 |
|---|---|---|---|
| G1 | pinned_hit 非硬保证 | 全量发送 + 边前向下探到 pinned + 保留补发通道兜底（pin 同步化为可选优化） | §2.2 注 2、§4.5、§6.2 |
| G2 | L2 卸载不与边协调会堆 DF/数据竞争 | Pause/Resume 流控 | §4.7 L2、§6.3 |
| G3 | 重启身份混淆；c2e 死 peer 阻塞 | (id, epoch) + 通道超时 teardown | §5 #4/#11、§6.4 |
| G4 | 双边并发同前缀重复 prefill 窗口 | Route-time PENDING | §4.5、§6.5 |
| G5 | cloud_id 粒度未定义 | cloud_id = （云实例， dp_rank) | §2.1 |
| G6 | 准入记账口径 | kv_free 扣 pinned+在队持有；DECODE_RESERVE 动态估算 | §4.7 L0 |
| G7 | 多边观测性 | (edge_id, cloud_id) 维度打点：出队时延/队列深/补发/pause 次数 | 实施项 |

### 6.8 已验证完备的机制清单

happy path 全链路（§6.1）；跨边 prefix 共享；NACK 重路由闭环；同边因果序；
chunk/MTP/层切分/提前收适配；L3 协同重算时序；中央/云宕机降级。

---

## 7. embedding_only 模式

embedding_only（边无 transformer 层、零 KV，k=0 退化形态）已从本文档剥离，见独立分册
**`multi_edge_cloud_design_embedding_only.md`**——同一代码路径（层集合配置驱动），
该分册 §7 含两模式的差异对照表。

---

## 8. 实施

### 8.1 改动量排序

| 序 | 项 | 主要落点 |
|---|---|---|
| 1（最大） | **KV 双池拆分 / 云自管**（§4.2）：CloudKVStore（KVCacheManager+BlockPool+ReqRegistry+LeaseTable）入云 PassiveScheduler；边 scheduler 缩减为头尾层池；SO 协议改造 | `core/passive_scheduler.py`、`core/pd_separated_scheduler.py`、`vllm/v1/core/*` |
| 2 | 数据面 HCCL pair 全互联 + 运行时选组 | `vllm_ascend/distributed/parallel_state.py`、`worker.py`、`shared_model_edge_worker.py` |
| 3 | 云侧多源调度（§3：全局单队列+同边不可超越、前缀化、准入配额/NACK、prepare 多槽） | `core/passive_scheduler.py`、`worker/model_runner_v1.py` |
| 4 | 中央调度器新进程（GPI/打分/租约/反熵）+ 边 Route 客户端 + 路由表 | 新增模块 + `core/pd_separated_scheduler.py` |
| 5 | 可靠控制消息（FIN/NACK/Pause/Resume/PreemptNotice/EdgeFreeNotice/心跳）+ 请求注册表 TTL GC | `v1/engine/passive_core.py`、`patch_engine_core.py` |
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
5. §5 异常矩阵 #3/#4/#8/#10/#11 的端到端注入测试。

---

## 9. 问题总结表

| # | 问题 | 结论 | 落点 |
|---|---|---|---|
| Q1 | 边云如何解绑？ | (id, epoch) 三元组注册替代 headless 二值；控制面 per-pair channel；数据面 pair 全互联；KV 双池/云自管 | §2.1、§2.3、§4.2 |
| Q2 | 中央调度器怎么路由？ | GPI 前缀匹配 + 负载心跳打分 + 一致性哈希 tie-break；Route-time PENDING 防重复 prefill | §4.5、§4.9 |
| Q3 | prefill 决定路由、decode 复用？ | 边本地路由表 req_id→(cloud_id, lease)；一次 Route 逐步复用；成本可忽略 | §2.2 及注 3 |
| Q4 | 云如何同时处理多边调度诉求？ | 全局单队列 +（优先级， 到达序）+ 调度不识别来源边；edge_id 惰性解析 | §3.1-3.2 |
| Q5 | 需要传 edge_id 吗？ | 不需要：**云侧入口适配层包装/出口剥离** req_id/head_token 前缀（边零改动、不感知）+ 收包 channel 标识来源 | §2.2 注 1 |
| Q6 | 每请求查表成本大吗？ | 可忽略（~100ns vs 毫秒 step；表=在途请求数）；中央不持逐请求表 | §2.2 注 3 |
| Q7 | 云要二次组 batch 吗？ | 默认不组（段原样执行）；合并演进预留（拼接+切片回传+merge window 等 6 要点） | §3.1、§3.7 |
| Q8 | 调度顺序要守什么约束？ | 同边不可超越（0812 死锁修复+prepare 校验决定）；优先级只跨边生效 | §3.1 |
| Q9 | 公平性/防打爆？ | 收敛在准入口：逐边 inflight 配额 + 全局上限 + NACK 重路由 | §3.3 |
| Q10 | PD 穿插/层切分/chunk/提前收多边还成立吗？ | 边侧机制零改动；云侧状态机保留（等任一边 decode）；层切分单例锁全局化；提前收键前缀化 | §3.5 |
| Q11 | 不同边请求状态怎么管？ | 请求级状态用全局唯一 req_id 单一名空间；执行上下文单例靠 source-agnostic 调度纪律 | §3.5 |
| Q12 | decode+MTP 链中间插 P/P-draft 有影响吗？ | 通道层✓时序层✓；共享 buffer 层⚠——快照/恢复本就 source-agnostic，补回归矩阵即可 | §3.5 |
| Q13 | NPU-CPU 异步优化多边下有隐患吗？ | 基本成立：耦合全是时序无关结构；唯一邻接依赖（提前 prepare）被 0731 键校验兜住；死锁自由三论据 | §3.6 |
| Q14 | 当前 KV 命中判断在哪？ | 边侧 scheduler（全局唯一 KVCacheManager）；云纯被动 | §1.2 F1 |
| Q15 | 多边多云 KV 归谁管？ | head_tail 双池分离（边管头尾层、云管中间层）；跨边 prefix 共享免费（em 单池形态见分册） | §4.2 |
| Q16 | 边云 KV 还要互相联系吗？ | 资源面完全独立（空闲 prefix 驱逐/命中各自为政）；生命周期面必须联动（FIN 双边、单侧抢占通知、num_computed 一致） | §4.2.1 |
| Q17 | KV 何时保留/过期？ | 活跃块不可逐；空闲 prefix 块原生 LRU（命中即 touch）+ 可选 TTL；lease pin 保活在途路由（纯优化） | §4.6 |
| Q18 | KV 怎么与中央同步做 prefix cache？ | GPI 攒批增量 + bloom 反熵；**铁律：仅路由参考，不参与实际分配**（延迟状态下分配权威在各池本地） | §4.5、§4.8 |
| Q19 | KV 满了怎么重计算？ | 四级：L0 双侧准入 → L1 空闲驱逐（原生）→ L2 host 卸载（Pause/Resume 流控，head_tail 下必须做好）→ L3 协同重算（防雪崩） | §4.7 |
| Q20 | 各种异常场景怎么处理？ | 12 场景矩阵（边云分列）+ 两横向原则（通道 FIFO 不可掐断、清理消息独立可靠） | §5 |
| Q21 | 边发云的信息要截断命中部分吗？ | 不截断，一律全量（云自管需全量 tokens 算哈希；缺输入问题消解；wire 布局不变）；带宽敏感时截断+pin-ack 优化备案 | §2.2 注 2、§6.2 |
| Q22 | 设计机制完备吗？ | 六模拟走查 + G1-G7 缺口登记闭环 + 不变量清单 | §6 |
| Q23 | head_tail 与 em 的关系？ | 同一代码路径（层集合配置驱动），em = k=0 退化，见独立分册 `multi_edge_cloud_design_embedding_only.md`（含差异对照表） | §7 |
| Q24 | 边云 cache 命中不一致怎么办？（致命问题，v1.1 修正） | **有效命中 = min(edge_hit, cloud_hit)**：KV cache 只存 K/V 不存输出 hidden，命中长的一侧产不出另一侧需要的中间量，多命中部分计算收益为零；两侧计算起点对齐 min。唯一打破途径 = 可选的段边界 hidden cache（显存换重算） | §4.5 |

**五个显式取舍（评审备查）**：
1. 全量发送——用带宽换正确性简洁与零等待（截断优化有备案）。
2. GPI 最终一致——用同步成本换路由低延迟；延迟下路由质量退化但永不影响正确性。
3. 调度不识别边——用准入口配额替代调度级公平（DRR 被有意简化）。
4. 单 active sliced prefill——用 prefill 并行度换 `_layerwise_*` 单例的内存与安全。
5. 云自管/双池 KV——最大架构改动，换跨边共享与故障域清晰；静态分区为回退方案。

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
| `vllm-ascend/vllm_ascend/worker/worker.py` | NPUWorker 边/云执行路径、HCCL send/recv、CHER |
| `vllm-ascend/vllm_ascend/worker/model_runner_v1.py` | 模型分段、`_cloud_prepare_cache`、批序对齐、`_layerwise_*`、快照/恢复 |
| `vllm-ascend/vllm_ascend/distributed/parallel_state.py` | e2c/c2e tensor meta、HCCL P2P 原语、draft meta |
| `vllm/vllm/v1/core/kv_cache_manager.py` | KV 分配/释放、prefix 命中入口 |
| `vllm/vllm/v1/core/block_pool.py` | free 队列（LRU 本体）、hash 映射、驱逐 |
| `vllm/vllm/v1/core/kv_cache_utils.py` | `hash_block_tokens` 链式哈希、KVCacheConfig 统一 |
