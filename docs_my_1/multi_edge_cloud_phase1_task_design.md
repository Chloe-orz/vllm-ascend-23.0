# 第一阶段任务级详细设计（模块 A–F）

> 版本：v1.2（2026-08-17；v1.1 = B4/C8/D1/E5/波次图；v1.2 = Route 流程强化：中央↔云同步 pin 确认为必选流程，结果以云 ack 为准（confirmed_hit））
> 上位文档：《multi_edge_cloud_dev_plan.md》（模块/任务划分与里程碑）。
> 本文档回答每个任务"**预期实现逻辑是什么**"：步骤、数据结构、接口、改动点、验证。
> 缩略：SO = SchedulerOutput；seg = 调度段；KVCM = KVCacheManager。

---

## 模块 A：通信与角色

### A1 角色与配置

**实现逻辑**：
1. `ParallelConfig` 新增 `edge_id / cloud_id / epoch / central_addr`；`--enable-edge-cloud` 下角色不再由
   `--headless` 推导，改为显式声明 + 注册表校验。
2. 新增 `role_registry.py`：
   ```python
   class RoleRegistry:
       def __init__(self, path_or_central): ...   # 启动期从静态配置文件（首选）或中央拉取
       def self_role(self) -> tuple[Role, int, int]      # (edge|cloud, id, epoch)
       def peers(self, role: Role) -> list[PeerInfo]      # [(id, [rank..], ip, port_base, dp_ranks)]
       def endpoint(self, edge_id, cloud_id, dp) -> Addr  # 端口规划的单一出处（供 A4 用）
   ```
3. 静态注册表以 YAML 下发到所有实例（一期）；启动时校验：本进程 id 在表内、模式（em/ht）与
   `edge_head_tail_layers` 全表一致、epoch ≥ 表中记录值。
4. `vllm/distributed/parallel_state.py` 的 `_IS_EDGE_DEVICE` 改为查询注册表角色，
   废弃 `local_rank < edge_npu_count` 推导（保留断言：两者一致才继续，便于过渡期发现问题）。
5. epoch 语义：进程每次启动向注册方（一期=配置文件+启动时间戳，二期=中央 B3）申报，
   对端凭 `(id, epoch)` 作废旧状态；一期 epoch 可固定 0，但**消息信封必须带 epoch 字段**（协议预留）。

**改动**：`config/parallel.py`、`engine/arg_utils.py`、`ascend_config.py`、新增 `role_registry.py`。
**验证**：配置解析/注册表加载/epoch 校验/模式不一致拒绝的单测。

### A2 线序适配层（最先合入）

**实现逻辑**（核心原则：线序显式 = SO 键序，行序为内部细节）：
1. 发送侧（`edge_cloud_isend_tensor_dict`，`distributed/parallel_state.py`）：
   ```python
   perm = [req_id_to_index[rid] for rid in so.num_scheduled_tokens.keys()]
   # perm 由同一份 SO 在收发两侧各自独立计算，结果必然一致
   flat = gather_by_perm(tensors, perm)     # 融合进现有 merge_payload 的 cat 拷贝
   isend(pair_group, flat)
   ```
2. 接收侧（`edge_cloud_broadcast_recv` / CHER 路径）：
   - recv 到 **staging 缓冲**（SO 序），不再要求 input_batch 行序匹配；
   - input prep 按 req_id 查表取每请求状态（块表/位置），在 staging 布局上直接构建 attn metadata；
   - 输出张量按 req_id scatter 回各请求持久槽位。
3. `req_id_to_index` 的维护不变（`swap_states` 等已同步）；req_id 查不到 = 协议错误，显式报错。
4. `_reorder_input_batch_to_so_order` 删除调用，保留函数改作**调试断言**（断言 staging 序 ≡ SO 序）。
5. c2e 方向同构复用同一适配器（`WireAdapter.gather(so, tensors)` / `scatter(so, staged)`）。

**改动**：`distributed/parallel_state.py`（isend/irecv 原语）、`model_runner_v1.py`（prepare/输出路径）。
**验证**：现网 1边1云 属性测试——头尾段之间随机 shuffle input_batch，输出逐位一致；
0804/0731 原故障用例回归。

### A3 静态域 + pair HCCL 建组

**实现逻辑**：
1. `init_ascend_model_parallel` 在实例内 TP/DP 组之后，遍历注册表 peer：
   ```python
   for cloud in registry.peers(CLOUD):      # 边侧执行
       for ch in (PREFILL_1, PREFILL_2, DECODE):
           g = new_group(ranks=[self_ranks + cloud.ranks])
           pair_table[(self.edge_id, cloud.id, ch)] = g
   # 云侧对称执行，保证两端建组序列一致（按 (edge_id, cloud_id, ch) 字典序）
   ```
2. `PairGroupTable.get(edge_id, channel) -> GroupCoordinator`；2-rank 组内 dst/src = 对端 rank。
3. 改造调用点（对端从常量改为查表）：
   - `worker.py:1130`（边 send）、`:1279`（云 recv）、`:1328`（云 send）；
   - `shared_model_edge_worker.py:587-638`（共享模型边 isend/recv）；
   - CHER guard thread：按段的 edge_id 解析 pair 后 post irecv。
4. 建组一致性：两端按同一顺序遍历 (edge, cloud, ch) 调用 `new_group`（torch 要求全员按序参与）。

**改动**：`distributed/parallel_state.py`、`worker.py`、`shared_model_edge_worker.py`。
**验证**：1边1云 回环收发 + FIFO 保序；1边2云 选组正确性（A→C0、B→C1 不串）。

### A4 ZMQ per-pair 控制面

**实现逻辑**：
1. 云侧（`passive_core.py`）：subscriber 从单 endpoint 改为**每边一个**（bind 本云端口，
   按注册表 connect 各边 PRE_OUT）；`poll_all_channels() -> Iterator[(Channel, bytes)]`，
   channel 对象携带 `edge_id`（由 endpoint 地址反查注册表）。
2. 边侧（`patch_engine_core.py`）：`_pp_pd_channel` → `dict[cloud_id, Publisher]`；
   `_maybe_publish_pre_out` 按路由表（C6）选目标 channel 发布；POST_OUT 收包同理按 cloud_id 归类。
3. 端口规划集中在 `RoleRegistry.endpoint()`（A1）：`base + (edge_id × MAX_C + cloud_id) × 4 + dp_rank`，
   单出处防漂移。

**验证**：1边2云 双通道收发；端口冲突检测单测。

### A5 可靠控制消息

**实现逻辑**：
1. `ctrl_channel.py`（复用 A4 的 per-pair ZMQ 通道，独立逻辑流）：
   ```python
   CtrlMsg = {msg_id: uuid, type: FIN|NACK|HEARTBEAT|..., epoch: int, payload: dict}
   # at-least-once：发送方重传（指数退避，上限 3 次）直到收到 ACK；
   # 接收方 seen_ids LRU(10k) 去重 → 幂等执行
   ```
2. 心跳：每 pair 每 2s 一条 HEARTBEAT；`last_seen` 驱动 D3 的 SUSPECT/DEAD。
3. 死 peer teardown：心跳超时 → 标记 → 关闭该 pair 通道 + **中止/等待在飞 HCCL 句柄**
   （超时的 wait(handle, timeout) → 失败则销毁该 pair comm group 并标记需重建）+ 通知调度器（D3）。
4. FIN/NACK 的处理函数注册到各消费模块（C3/D1/D2），A5 只做传输可靠性。

**验证**：kill 对端 → 超时 teardown 完成且不残留半事务；丢包/重复注入 → 幂等执行一次。

---

## 模块 B：中央调度器与边云交互

### B1 ⚡ 协议 schema 冻结

**实现逻辑**：`central/protocol.py`，四组消息 dataclass + `version` 字段（msgpack 或 JSON）：
```python
RouteRequest {version, edge_id, block_hashes: list[int], prompt_len, priority, edge_hit: int|None}
RouteResponse {version, cloud_id, confirmed_hit, lease_id, reject: bool}   # confirmed_hit 以云 ack 为准（B2）
PinReq/PinAck {version, lease_id, hashes, ttl / confirmed_pinned_len, accepted: bool}
Heartbeat {version, cloud_id, kv_free, queue_delay, inflight, recent_preempt, ts}
GpiDelta {version, cloud_id, kind: insert|evict|pending|solid, hashes: list[int]}
Register/PeerTable/DeadBroadcast {...}
```
**验证**：序列化/反序列化单测 + 版本不匹配拒绝。

### B2 Route 服务端（轮询内核 + **同步 pin 确认**）

**实现逻辑**：

1. `RouterCore.route(req)`：从 `LoadView.alive_clouds()` 轮询选一朵候选云。
2. **同步确认（必选流程，不是可选优化）**：向候选云发 `PinReq{lease_id, hashes, ttl}`
   （REQ/REP 同步等待），云以**本地块池为准**实际 pin 块并回
   `PinAck{lease_id, confirmed_pinned_len}`。
3. **以云为准**（铁律的落地形态）：中央**不得**直接拿 GPI 的估算值回复边——
   - `confirmed ≈ est`（GPI 基本准）→ 正常返回；
   - `confirmed ≪ est`（GPI 过期严重）→ 该云临时移出轮询集（30s 降权），
     **换次优云再确认一次**；两轮都不行才返回低命中结果；
   - 顺手用 ack 值回写修正 GPI 该条目（滞后自愈）。
4. 返回 `RouteResponse{cloud_id, confirmed_hit, lease_id}`——**confirmed_hit 是云确认的
   下界，边可据此做发送区间决策**（ht：`[min(edge_hit, confirmed), end)`；em 全量发送不受影响）。
5. NACK 重询价：同一入口，将该云临时移出轮询集。无可用云：`reject=true`，边按 C6 降级。
6. **内核占位纪律**：候选选择用轮询占位，但**确认流程与内核无关、本期就必须做**；
   二期换打分内核时确认链路不动。
7. 时延预算：Route = 边↔中央 RTT + 中央↔云 RTT（各毫秒级，每请求仅一次）。

**一致性窗口与兜底**：PinAck 后块被 ref+1 pin 住，PF 到达 `confirm_lease` 转引用（C4）——
常规路径一致性闭环。残余窗口（PF 排队超 lease TTL 被 sweeper 解 pin 后块被逐）由云准入时
本地复核兜底：em 用全量输入多算一段；ht 走补发通道（罕用）。lease TTL 必须 > 预期排队时长。

**验证**：mock 云对打：① ack 与 GPI 一致 → 正常；② ack < est → 换云再确认 + GPI 回写修正；
③ 云拒绝 pin → 降权重试；④ 两云都失败 → reject。

### B3 心跳摄入 + 注册/广播 + GPI 空转

**实现逻辑**：
1. `LoadView.ingest(Heartbeat)` → `dict[cloud_id, (metrics, last_seen)]`；超时（10s）标 DEAD →
   `DeadBroadcast` 发全体边（经注册表通道）。
2. `RegistryService`：实例启动 hello → 校验/登记 `(id, epoch)` → 下发对端表（A1 注册表的运行时版）。
3. `GpiStore.ingest(GpiDelta)`：仅入 `dict[hash, set[cloud_id]]`（只存不算）+ 条目数统计打点；
   云 DEAD 时批量清除该云条目（逻辑先建好，一期无消费者）。

**验证**：mock 云上报断言视图；kill 云 → 全体边收到 DEAD；GPI 写入/清除闭环。

### B4 边↔中央↔云 交互建模（整体视图）

**全部通道一览**（中央为轴心，无 边↔云 直连控制面之外的通道）：

| # | 通道 | 模式 | 消息 | 频率 | 超时与降级 |
|---|---|---|---|---|---|
| 1 | 边 → 中央 | REQ/REP 同步 | `RouteRequest` | 每请求仅 1 次 | ~ms 级超时 → 边本地一致性哈希默认路由（C6） |
| 2 | 中央 → 边 | REP + PUB | `RouteResponse`、`DeadBroadcast`、`PeerTable`（注册时） | 应答 + 事件触发 | 边收不到广播不影响服务，下次心跳对齐 |
| 3 | 云 → 中央 | PUSH | `Heartbeat{kv_free, queue_delay, inflight, recent_preempt}` | 周期 2s | 中央 10s 未见 → 标 DEAD → 通道 5 |
| 4 | 云 → 中央 | PUSH | `GpiDelta{insert/evict/pending/solid, hashes}` | 攒批（200ms 或 Δ≥64） | 只存不算（一期）；丢失无正确性影响 |
| 5 | 中央 → 全员 | PUB | `DeadBroadcast{cloud_id}` | 事件触发 | 边收到后扫路由表重路由（C6）；GPI 清除该云条目（B3） |
| 6 | 实例 → 中央 | REQ/REP | `Register{id, epoch}` → `PeerTable` | 启动时 1 次 | epoch 冲突拒绝启动 |
| 7 | 中央 ↔ 云 | **REQ/REP 同步** | `PinReq{lease_id, hashes, ttl}` → `PinAck{lease_id, confirmed_pinned_len}` | 随 Route 决策，每请求 1 次 | **以云 ack 为准**（B2）；云可拒绝/部分接受 |

**稳态时序**：

```
启动:  各实例 Register → 拿 PeerTable → 建 A3/A4 通道 → 进入稳态
稳态:  云每 2s Heartbeat + 攒批 GpiDelta －→ 中央维护 LoadView/GpiStore
       请求到达边 → Route(1次) ─┬─ 中央选候选云
                                 ├─ 中央↔云同步 PinReq/PinAck（以云为准）
                                 └─ 返回 confirmed_hit + lease_id 给边
       边按路由发段（A4，不再经中央）→ 云 confirm_lease 转引用（一致性闭环）
       ……decode 全程不触碰中央……
       请求结束 → FIN（A5，边→云直连，不经中央）
故障:  云静默 10s → 中央 DeadBroadcast → 边重路由 + 云孤儿由 C3/D3 清理
       中央宕机 → 边 Route 超时 → 本地默认路由降级；云/边继续服务在途
```

**建模要点**：中央只承载"每请求一次的路由 + 周期心跳 + 事件广播"三类轻量交互，
**稳态数据面（段/hidden）与控制面（段/FIN/NACK）都不经过中央**——这是它能做薄、
能降级、无状态可热备的根本原因。

---

## 模块 C：KV 管理与边云协议

### C1 ⚡ SO 协议改造

**实现逻辑**：
1. 段 schema v2（`v1/core/sched/output.py` 或 ascend 侧封装层，推荐封装避免侵入上游）：
   - 云侧语义删除：`new_block_ids`、`num_computed_tokens`（由云本地管理，C2/C5）；
   - 新增：`lease_id: str|None`、`edge_block_table: list[int]|None`（ht 预留，em 恒空）、`epoch`。
2. 序列化/反序列化两侧同步修改 + 版本号协商（与 B1 同批次冻结）。
3. 边 scheduler 不再把 KV 分配结果写进段（C7 配合）。

**验证**：schema 单测 + 新旧版本共存期拒绝策略。

### C2 CloudKVStore

**实现逻辑**：
1. `cloud_kv_store.py` 封装 KVCM + BlockPool（em：本云全模型层 spec；云用自己的
   `kv_cache_config` 实例化，不再参与全集群 clamp）：
   ```python
   class CloudKVStore:
       def admit_kv(self, seg) -> AdmitResult:
           hashes = chain_hash(seg.token_ids, extra_keys(seg))   # 与边/中央同算法
           hit, _ = self.kvcm.get_computed_blocks(hashes)
           ok = self.kvcm.allocate_slots(seg.req_ids, hashes)     # 权威命中+分配
           return AdmitResult(ok, hit_len=hit)
       def grow(self, req_id, n=1): ...     # decode 增长
       def free(self, req_id): ...          # 转空闲 prefix（hash 保留）
       def pin/confirm_lease(...)            # → C4
   ```
2. `PassiveScheduler.admit` 在准入时调用 `admit_kv`；`num_computed` 记入 ReqRegistry（C3）。
3. extra_keys（cache_salt/lora/mm）随段携带，保证与边侧哈希同源。

**验证**：单云驱动段流，命中长度/块分配与原生 vllm 参照实例逐请求一致。

### C3 ReqRegistry + TTL GC + FIN

**实现逻辑**：
1. `req_registry.py`：
   ```python
   CloudReqEntry {req_id, edge:(id,epoch), state: ADMITTED|RUNNING|ZOMBIE,
                  num_computed, lease_id, last_seen}
   ```
   准入时登记；每次收到该 req 的段刷新 `last_seen`。
2. TTL sweeper（引擎主循环周期调用，T=60s 可配）：过期 entry → 按 FIN 路径回收。
3. FIN 处理（A5 注册回调）：无在飞段 → `kv_store.free(req)` + 队列/pending 剔除 + 删 entry；
   有在飞段 → 置 ZOMBIE，段收尾（配对接完）结果丢弃不回传后再回收。

**验证**：假死注入（只停发）→ TTL 回收；FIN 丢失注入 → 兜底生效；ref_cnt 守恒断言。

### C4 LeaseTable（pin 预约）

**实现逻辑**：
1. `LeaseEntry {lease_id, hashes, pinned_blocks, expire_ts, state}`。
2. `pin(lease_id, hashes, ttl=5s)`：对命中块 ref+1（块已不在 → 跳过并在 ack 中返回实际
   pinned_len；一期 ack 可只记日志）；sweeper 超时 → ref−1 释放。
3. `confirm_lease(lease_id, req_id)`：C2 准入时调用，把 pin 引用并入请求块表；
   lease 不存在/过期 → 跳过（仅损失优化）。**注意：经 B2 同步确认后，pin 在常规路径
   是必然命中的（confirmed_hit 即本表 pin 成功的结果），confirm 只是引用过户**；
   跳过仅发生在"PF 排队超 TTL 被 sweeper 解 pin"的极小窗口，由云准入本地复核兜底。
4. 不变量：PINNED 块 ref_cnt ≥ 1（sweeper 之外不得解除）。

**验证**：pin 后制造驱逐压力 → 命中保住；超时 → 解 pin；块缺失 → 不死。

### C5 slot_mapping 数据源切换

**实现逻辑**：
1. `model_runner_v1.py`：slot_mapping/positions 的原料从 SO 字段改为
   `kv_store.req_to_blocks(req_id)` + `registry.num_computed(req_id)`；派生函数签名不变。
2. `cloud_prepare_early` 调用点移到**准入分配之后**（prepare 需要块表）。
3. 删除 1TiB 虚拟显存 hack（`worker.py:755-772`）；`get_kv_cache_configs` 中云池按本云
   spec/显存独立计算（em 边 spec 为空，天然不参与）。

**验证**：与 C2 联合对标原生（同段流下 slot_mapping 序列一致）。

### C6 边侧 Route 客户端 + 路由表

**实现逻辑**：
1. `route_client.py`：
   ```python
   class RouteClient:
       def route(self, req) -> RouteDecision:      # 同步 RPC（B2），结果写路由表
       def on_nack(self, cloud_id, req): ...        # 退避 50ms 重新 route（该云临时降权）
       def on_timeout(self, req): ...               # 中央不可用 → 本地一致性哈希默认云（降级）
   route_table: dict[req_id, (cloud_id, lease_id)]  # 请求结束即删
   ```
2. 与 B1 协议对齐；mock 中央可注入固定响应/超时/NACK 序列。

**验证**：mock 中央单测：正常、NACK 换云、超时降级。

### C7 边侧全量发送 + FIN

**实现逻辑**：
1. `pd_separated_scheduler.py` PF 路径：调 `route_client.route()` → 段携带 `lease_id` + 目标
   channel（A4）；em 全量 embed 发出（不截断）；ht 留 `min(edge_hit, pinned)` 接口注释（二期）。
2. decode：每步查路由表直发（不再问中央）；路由表 miss = 协议错误（应不存在）。
3. `finish_requests`：通过 A5 发 FIN 到路由的云；`finished_req_ids` 搭车降级为冗余路径。

**验证**：1边1云 prefill→decode→FIN 端到端行为对齐现网。

### C8 CloudKVStore：复用 vllm 原生机制 vs 自研清单

**直接复用（不改代码，只调用）**：

| 机制 | 位置 | 用途 |
|---|---|---|
| `KVCacheManager`（allocate_slots / get_computed_blocks / free / cache_blocks） | `vllm/v1/core/kv_cache_manager.py` | C2 的分配、权威命中、释放主逻辑——**整体搬入云侧使用** |
| `BlockPool`（free 队列 LRU、`cached_block_hash_to_block`、ref_cnt） | `vllm/v1/core/block_pool.py` | 块生命周期与空闲 prefix 缓存（L1 驱逐就是它的原生行为） |
| 链式哈希 `hash_block_tokens` / `request_block_hasher` | `vllm/v1/core/kv_cache_utils.py` | 云本地从全量 token ids 重建哈希链（与边/中央同链） |
| KVCacheConfig/spec 分组 | `vllm/v1/core/kv_cache_utils.py` | 云侧独立 spec 生成（em=全模型层） |
| KVConnector 注册框架 | `vllm_ascend/distributed/kv_transfer/__init__.py` | 后续多级存储/卸载的挂钩点（E 模块同款） |

**需改造（小改，机制不变）**：

| 项 | 位置 | 改什么 |
|---|---|---|
| `PassiveScheduler` | `core/passive_scheduler.py` | 纯被动 → 半主动：准入时调 `admit_kv`；KV 记账（kv_free）暴露给 D2 准入 |
| `model_runner_v1.py` | worker | slot_mapping/positions 数据源从 SO 字段切到云本地 `req_to_blocks`（C5）；`cloud_prepare_early` 移到准入分配后 |
| KVCacheConfig 统一逻辑 | `kv_cache_utils.py`、`worker.py:755-772` | 去掉跨边云 clamp，每云独立；删 1TiB 虚拟显存 hack |
| `pd_separated_scheduler.py` | 边 | 瘦身：不再把分配结果写进段（em 删 KV 职责） |

**全新实现（vllm 没有等价物）**：

| 项 | 为什么现有没有 |
|---|---|
| ReqRegistry（注册表 + TTL GC） | 原生"请求集合"由 scheduler 的 waiting/running 充当，被动云没有等价物 |
| LeaseTable（pin/confirm/sweeper） | 租约是中央路由引入的新概念，原生无 |
| GpiReporter（攒批上报 + bloom 摘要） | 中央 GPI 是新组件，原生无上报通道 |
| NACK 准入估算（`estimate_kv_blocks`：扣 pinned + 在队持有） | 原生准入只看本地 allocate 成败，无"预占估算" |
| SO 协议封装层（C1：去块表化 + lease_id） | 协议变化本身是本项目定义的 |
| num_computed 回报边通道（随 c2e/段完成） | 原生边云一体记账，无回报需求 |

---

## 模块 D：云侧内部调度

### D1 全局单队列 + FIFO + 同边不可超越

**队列放在哪、怎么被驱动（先明确执行模型）**：

队列放在 `PassiveScheduler` 实例内，由 **`PassiveEngineCore` 的 busy loop 线程**驱动
（`passive_core.py:461 run_busy_loop → :598 step()`，现成生命周期，不新增线程模型）：

```
ZMQ subscriber（可选独立线程，现成）
   │  consume_new_outputs()
   ▼
_inbox: queue.Queue          ← 唯一的跨线程点（线程安全，现成）
   │  每个 tick: poll_and_classify() drain
   ▼
全局 deque[SchedSeg]         ← 只被 busy loop 线程触碰，无锁
   │  同 tick: schedule() → pop_next_schedulable()
   ▼
slice 计划 → executor.rpc_broadcast_mq → worker 进程执行
```

**使用纪律**：① 全局 deque 只被 busy loop 一个线程读写（subscriber 线程只写 `_inbox`）；
② A5 控制消息（FIN/NACK 回调）若来自非 busy loop 线程，**必须经 `_inbox` 注入**，
不得直接操作队列/registry；③ admit/包装（D2）在 `poll_and_classify` 内完成，
出队（pop）在 `schedule()` 内完成——入队与出队同一 tick 同一线程，天然无竞态。

**实现逻辑**：
1. `PassiveScheduler` 的 4 类队列（ready_prefills/decodes/drafts/pdmixes）替换为：
   ```python
   queue: deque[SchedSeg]          # 全局到达序
   edge_head: dict[int, int]       # edge_id → 该边当前队首的 arrival_seq（队首判定用）
   seq: int = 0                    # 全局单调计数
   ```
2. `pop_next_schedulable()`：从头扫描，取"是本边队首"的第一个段（FIFO 下即队首元素；
   扫描逻辑按最终形态写，二期加优先级档时不变）。
3. 段的执行回调维护 `edge_head`（出队即推进）。
4. 云侧交替状态机（EXPECT_ALTERNATION）保留，"等 decode"语义不变（一期单源下自然满足）。

**验证**：1边1云 走通；乱序注入（人为颠倒到达序）→ 同边不被超越；N边1云 mock 段流多源不串。

### D2 包装剥离 + 最简准入 + NACK

**实现逻辑**：
1. `id_adapter.py`：
   ```python
   def wrap_inbound(channel, seg):  # 收包入口
       seg.req_ids = [f"e{channel.edge_id}-{r}" for r in seg.req_ids]
       seg.head_token = f"{channel.edge_id}:{seg.head_token}"
   def strip_outbound(msg):          # 出口统一调用点（c2e 数据面引用 + 全部控制消息）
       ...反向剥离...
   ```
   **出口调用点清单**列入 code review 检查项 + 单测（漏剥离 = 边不认识自己的请求）。
2. 最简准入（`admit`，挂在 D1 入队前）：`global_inflight < limit && kv_free(由 C2 记账) > need`
   → 否则发 NACK（A5，沿收包 channel 直回）。逐边配额/优先级档二期。
3. `pending_heads`、prepare cache 键等全部使用包装后 id。

**验证**：包装/剥离一致性单测；限额打满 → NACK → 边重发走通。

### D3 边失联处理

**实现逻辑**：
1. `EdgeStats{last_heartbeat, state: ACTIVE|SUSPECT|DEAD}`（心跳来自 A5）。
2. 超 T1(5s) → SUSPECT：该边的段标记不可调度（保留队列位置）；
   超 T2(30s) → DEAD：
   - 按包装前缀扫描全局队列/pending_heads 剔除该边的段；
   - 在途请求按 C3 的 TTL GC 等价路径回收 KV；
   - 通道 teardown（A5）；上报中央（B3）。
3. 边以新 epoch 回归：旧 epoch 残留已在 DEAD 时清空，直接按新边接入。

**验证**：边假死注入 → SUSPECT/DEAD 迁移与清理断言。

---

## 模块 E：边侧多级 KV 存储（Mooncake 简化版）

### E1 接口定稿

**实现逻辑**：`tiered_kv_store.py` 抽象接口（语义对齐 Mooncake，便于未来替换）：
```python
class TieredKVStore(Protocol):
    def exists(self, h: BlockHash) -> Tier|None            # NPU / HOST / None
    def prefetch(self, hashes: list[BlockHash]) -> Handle  # 触发 H2D（异步）
    def get(self, handle) -> list[Block]                   # 取回（等待恢复完成）
    def put(self, blocks: list[Block], hashes) -> None     # 写入（先入 NPU 层）
    def evict(self, policy=LRU) -> None                    # 分层驱逐（NPU→host→drop）
    def pin(self, hashes) / unpin(self, hashes)
```
**验证**：接口契约评审 + 桩实现（内存版）跑通调用方。

### E2 本地两级存取

**实现逻辑**：
1. L0（NPU）：复用边池 BlockPool 语义；L1（host）：pinned DDR 池（定长块，LRU）。
2. `put`：先写 NPU 层；NPU 满 → 选最冷块 **D2H 降级到 host**（hash 迁移，不丢弃）；
   host 满 → 真驱逐。
3. `exists/get`：命中在 host → 记录并走 prefetch 恢复；命中语义 = NPU命中 + host命中。

**验证**：单边实例：写满 NPU → 驱逐到 host → 按 hash 找回 → 数据逐位一致。

### E3 异步传输引擎 + connector 注册

**实现逻辑**：
1. 本地 DMA 队列（独立线程/stream）：D2H/H2D 任务异步执行，完成回调驱动 Handle 状态
   （PENDING→READY）；H2D 预取与当前批计算重叠（回调里只改状态，读取在下一步）。
2. 注册为 vllm KVConnector（复用树内注册位，`vllm_ascend/distributed/kv_transfer/__init__.py`），
   save/load 钩子对接到边池的 cache_blocks/free 路径。

**验证**：并发注入（恢复中发起新 put/get）→ 无数据竞争；恢复与计算重叠的时序断言。

### E4 边池集成原型 + 定标

**实现逻辑**：
1. 把 E2/E3 接到边头尾层池（ht 原型，k=1）：命中路径改为先查 TieredKVStore。
2. **判决性实测**：同机测量 "host 命中恢复一个块（H2D + 接入）" vs "头层重算等价区间"的时延比；
   输出定标报告（恢复成本必须 ≪ 重算，否则 tiering 不成立，回退到纯 NPU 池 + 调 k）。
3. 打点：tier 命中分布、恢复时延、host 池水位。

**验证**：实测报告（这是 go/no-go 判据，ht 是否依赖多级存储由它决定）。

### E5 云侧多级存储：现状与实现路径

**现状**：云侧当前**没有启用**多级存储——但框架与现成实现都在树里：KVConnector 注册表
（`vllm_ascend/distributed/kv_transfer/__init__.py`）已有 `UCMConnector`（kv_pool 分层池）、
`LMCacheAscendConnector`、`AscendStoreConnector`（Mooncake store）、`SimpleCPUOffloadConnector`
等多个实现。即"能力在库、链路未接"。

**能否实现**：可以，且与模块 E 同构，两条候选路径：

1. **复用 E 组件（推荐）**：CloudKVStore 的 free/evict 路径挂 `TieredKVStore`（同一组件两侧
   复用），过载包二期（L2 host 卸载）的 OffloadStore 就是它——边云语义一致、一份维护。
2. **直接评估接入 UCM/LMCache**：若 E4 定标前想快速获得云侧分层能力，可先评估
   UCMConnector 的适配度（它本就是分层 KV pool），代价是语义与边侧组件分叉。

**与边侧（E 模块）的语义差异**（实现时注意）：

| 维度 | 边侧多级（E） | 云侧多级 |
|---|---|---|
| 服务对象 | 只服务本边请求 | 多边共享（host 层命中也有**跨边 prefix 共享价值**——恢复后仍可被他边命中） |
| 内容 | 头尾 k 层 KV（ht） | 中间层/全模型层 KV |
| 触发 | 边池满驱逐降级 | 水位主动卸载（Pause/Resume 流控，过载包二期） |
| 语义近亲 | 简化版 store | **更接近 Mooncake store**（共享 prefix 池） |

**阶段结论**：一期不做；二期与 E4 定标结论联动决策（E 组件复用 vs 接 UCM）。

---

## 总开发顺序与依赖图

**Week 0-1（对齐前置，全员参与）**：
- 「模块 B·中央调度器 — 协议 schema 冻结」（Route/心跳/GPI/注册广播）
- 「模块 C·KV 管理与边云协议 — SO 协议改造」（去块表化 + lease_id + 可空边侧块表）
- 「模块 A·通信与角色 — 角色与配置」（id/epoch/注册表/端口单一出处）
- 「模块 F·验证基座 — 段流驱动器 + 不变量断言库」

——此后进入并行波次（同一波次内任意并行）：

| 波次 | 任务（模块·功能点） | 依赖 |
|---|---|---|
| **Wave 1** | 通信与角色 · **线序适配层**（**无依赖，最先合入现网**） | 无 |
| | 通信与角色 · 静态域 + pair HCCL 建组 | 角色与配置 |
| | 中央调度器 · Route 服务端（轮询内核）+ 心跳摄入 + 注册/广播 + GPI 空转 | 协议 schema 冻结 |
| | KV 管理与边云协议 · **CloudKVStore**（KVCacheManager 下沉 + 权威命中） | SO 协议改造（桩段即可起步） |
| | 边侧多级 KV 存储 · 接口定稿 → 本地两级存取 | 无（完全独立） |
| **Wave 2** | 通信与角色 · ZMQ per-pair 控制面 | 角色与配置、pair 建组 |
| | KV 管理与边云协议 · ReqRegistry + TTL GC + FIN | CloudKVStore |
| | KV 管理与边云协议 · LeaseTable（pin 预约） | CloudKVStore |
| | KV 管理与边云协议 · 边侧 Route 客户端 + 路由表 | 协议 schema（mock 中央即可） |
| | 云侧内部调度 · 全局单队列 + FIFO + 同边不可超越 | SO 协议改造、段流驱动器 |
| | 边侧多级 KV 存储 · 异步传输引擎 + connector 注册 | 本地两级存取 |
| **Wave 3** | 通信与角色 · 可靠控制消息（FIN/NACK/心跳/teardown） | ZMQ 控制面 |
| | KV 管理与边云协议 · slot_mapping 数据源切换 | CloudKVStore、ReqRegistry |
| | KV 管理与边云协议 · 边侧全量发送 + FIN | Route 客户端、ZMQ 控制面、SO 协议改造 |
| | 云侧内部调度 · 包装剥离 + 最简准入 + NACK | 全局队列、CloudKVStore（记账）、可靠控制消息 |
| | 边侧多级 KV 存储 · 边池集成原型 + 恢复时延定标 | 异步传输引擎 |
| **Wave 4** | 云侧内部调度 · 边失联处理（SUSPECT/DEAD） | 包装剥离+准入、可靠控制消息、注册/广播 |
| | 验证基座 · 打点最小集汇总 | 各包打点内嵌完成 |

**关键路径**（决定总工期的两条最长链）：
- **通信链**：角色与配置 → pair 建组 → ZMQ 控制面 → 可靠控制消息 → 包装剥离+准入 → 边失联处理
- **KV 链**：SO 协议改造 → CloudKVStore → ReqRegistry / LeaseTable → 数据源切换 → 边侧全量发送

中央调度器（模块 B）与边侧多级存储（模块 E）全线在关键路径之外，是天然的人力缓冲带。

**联调**：M1（通信与角色 + 中央 + KV 管理与边云协议 + 云侧内部调度 集成 → 1边1云 对齐现网）
→ M2（1边2云 轮询/心跳/NACK/广播）→ M3（N边1云 mock 多源段流）→ M4（二期：换芯/配额/过载/定 ht 启动）。

---

## 模块 F：验证基座

### F1 段流驱动器 + 不变量断言库（第 1 周交付）

**实现逻辑**：
1. 段流驱动器（`testkit/seg_stream.py`）：脚本化生成段流（单源/多源/乱序注入/故障注入：
   kill、丢包、FIN 丢失、pin 失败），可直接灌入 PassiveScheduler/CloudKVStore（不走 HCCL）。
2. 断言库（`testkit/invariants.py`）：
   - INV1 同边执行序 = arrival_seq 序；
   - INV2 Σ inflight ≤ 全局限额；
   - INV3 ref_cnt 守恒（Σref == 活跃块数 + pin 块数）；
   - INV4 registry 键集 ⊇ req_to_blocks 键集；
   - INV5 ZOMBIE/PAUSED 段不下发但在飞事务配对接完。

### F2 打点最小集

**实现逻辑**：(edge_id, cloud_id) 维度计数器/直方图：出队时延、NACK 数、命中数（hit_len）、
pin 成功率；输出到日志/Prometheus（一期日志即可）。作为 C/D 模块交付检查项内嵌。

---

## 附：任务间接口速查

| 接口 | 产出方 → 消费方 | 冻结批次 |
|---|---|---|
| 协议 schema（Route/心跳/GPI/注册） | B1 → B2/B3/C6/D/云 | 第 1 周 |
| SO 段 schema v2 | C1 → C2/C5/C7/D1/A2 | 第 1 周 |
| RoleRegistry/endpoint | A1 → A3/A4/B3/D3 | 第 1 周 |
| PairGroupTable | A3 → worker/CHER | A3 内 |
| ctrl_channel（FIN/NACK/HEARTBEAT） | A5 → C3/D1/D2/D3/B3 | A5 内 |
| CloudKVStore.admit_kv/grow/free | C2 → C3/C5/D2 | C 模块内 |
| WireAdapter.gather/scatter | A2 → A3/worker/prepare | A2 内 |
| TieredKVStore | E1 → E2/E3/E4 | E 模块内 |
