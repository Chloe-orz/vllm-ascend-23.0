# 多边多云开发计划（第一阶段·简化版 + 后续阶段）

> 版本：v2.3（2026-08-17；v2.0 = 第一阶段简化版重构；v2.1 = 细粒度拆分 + P5 Mooncake 简化版；v2.2 = 六模块 A-F 重组；v2.3 = 新增 §6 开发清单总览（一期+后续 20 项，含截断发送优化））
> 配套：《multi_edge_cloud_design.md》（ht 主线）、《multi_edge_cloud_design_embedding_only.md》（em 分册）。
> **第一阶段目标**：em 场景、静态通信、调度内核简化（轮询），**把三方交互与全流程走通**；
> 性能类功能（打分、配额、卸载、组 batch）与动态建链全部后置。

---

## 0. 总原则

1. **接口全量、算法可空**：Route/GPI/lease/包装剥离的协议与代码路径按最终形态建，内部逻辑
   （打分、配额）用轮询/常量占位——二期只换内核不换协议。
2. **多源形态先行**：云侧队列、SO 协议第一天起就是"多边的形"（不识别来源、全局唯一键），
   本期只是恰好一边一云在跑；扩边扩云时上负载而非改代码。
3. **协议第一周冻结**（版本化）：Route RPC / 段（segment）/ 控制消息 / KV 记账接口。
4. **em 先行**：路径最短（无边池、无尾段同步、无补发通道）；ht 的 k>0 差异作为后续增量。
5. **验证场景最小化**：能 1边1云 验证的不上 1边N云，能 mock 的不上真机。

---

## 1. 第一阶段功能点（模块 + 周粒度任务）

> 组织原则：**大模块完整归属**（KV、云侧内部调度、调度器与边云交互等各为一块，不拆散），
> 模块内部按 **1 人周粒度**拆任务——每个任务一个人在 AI 辅助编码下约一周完成、
> 独立可验证；模块内任务可串行（一人做）也可并行（多人分领）。
> 带 ⚡ 标记为协议类任务（产出即冻结协议，其他任务的前置）。

### 模块 A：通信与角色（约 5 人周）

| # | 任务 | 内容 | 最小验证 |
|---|---|---|---|
| A1 | 角色与配置 | `(edge_id, cloud_id, epoch, central_addr)` 替代 headless 二值；静态注册表。改 `config/parallel.py`、`arg_utils.py`、`ascend_config.py`，新增 `role_registry.py` | 配置解析+注册表单测 |
| A2 | **线序适配层（最先合入）** | wire 布局 ≡ SO 键序；收发边界按 req_id gather/scatter（融入 merge_payload 拷贝）；`_reorder_input_batch_to_so_order` 降级为断言 | **现网 1边1云 属性测试**：shuffle input_batch → 输出逐位一致 |
| A3 | 静态域 + pair HCCL 建组 | 全局域 + 每 (edge, cloud, dp) pair × 3 通道组；运行时按包装 id 选组。改 `distributed/parallel_state.py`、两个 worker | 1边1云 回环收发+FIFO → 1边2云 选组 |
| A4 | ZMQ per-pair 控制面 | 边 `dict[cloud_id→channel]`；云每边 subscriber；端口按 (edge, cloud, dp) 规划。改 `passive_core.py`、`patch_engine_core.py` | 1边2云 双通道收发 |
| A5 | 可靠控制消息 | FIN/NACK/心跳（重传+幂等）；死 peer 超时+teardown。新增 `ctrl_channel.py` | kill 对端验证 teardown；丢包/重复注入 |

**模块纪律**：运行期禁止跨实例集合通信（pair P2P 除外）——未来动态建链平滑替换的前提。

### 模块 B：中央调度器与边云交互（约 2.5 人周）

| # | 任务 | 内容 | 最小验证 |
|---|---|---|---|
| B1 ⚡ | 协议 schema 冻结 | Route/心跳/GPI 增量/注册广播 四组消息 schema + 版本号（**第一周冻结**，全员共用） | 序列化/反序列化单测 |
| B2 | Route 服务端（轮询内核） | Route 请求→轮询选云→响应 {cloud_id, est_hit, lease_id}；NACK 重询价；lease 字段透传 | mock 边对打：正常 + NACK 换云 |
| B3 | 心跳摄入 + 注册/广播 + GPI 空转 | 云→中央心跳（kv_free/queue_delay/inflight/recent_preempt）；成员注册/epoch/云 DEAD 广播/对端表下发；GPI 增量通道（只存不算，二期换芯） | mock 云上报断言；kill 云→全员收广播 |

### 模块 C：KV 管理与边云协议（约 6 人周，可 2 人并行：云线 C2-C5 / 边线 C6-C7）

| # | 任务 | 内容 | 最小验证 |
|---|---|---|---|
| C1 ⚡ | SO 协议改造 | 段 schema：去 `new_block_ids/num_computed_tokens`，加 `lease_id` + 可空"边侧块表"字段（ht 预留，em 恒空）；两侧序列化 | schema 单测 |
| C2 | CloudKVStore | KVCacheManager+BlockPool 内嵌 PassiveScheduler（em=全模型层）；准入时 `allocate_slots` 权威命中（全量 token ids 本地算哈希）。新增 `cloud_kv_store.py`，改 `passive_scheduler.py` | 单云：命中正确性对标原生 vllm |
| C3 | ReqRegistry + TTL GC + FIN | 请求注册表；TTL sweeper；FIN 释放（含 ZOMBIE 在飞段配对接完再清理）。新增 `req_registry.py` | 假死/FIN 丢失注入 → orphan 回收 + ref_cnt 守恒 |
| C4 | LeaseTable（pin 预约） | pin/confirm/sweeper（**pin 归本模块**，不属过载包） | pin 命中保住 / 超时解 pin / 失败仅多算 |
| C5 | slot_mapping 数据源切换 | worker 派生原料从 SO 改为云本地 `req_to_blocks`；删 1TiB 虚拟显存 hack（`worker.py:755-772`）；`cloud_prepare_early` 移到准入分配后 | 与 C2 联合对标原生 |
| C6 | 边侧 Route 客户端 + 路由表 | Route 客户端（可 mock 中央）+ 路由表 req→(cloud_id, lease)；NACK 重发（退避）；中央超时降级本地路由。新增 `route_client.py` | mock 中央：路由表/NACK/降级单测 |
| C7 | 边侧全量发送 + FIN | em 全量 embed + 段封装；decode 复用直发；abort/完成发 FIN。改 `pd_separated_scheduler.py`、`patch_engine_core.py` | 1边1云 prefill→decode→FIN 端到端 |

### 模块 D：云侧内部调度（约 2.5 人周）

| # | 任务 | 内容 | 最小验证 |
|---|---|---|---|
| D1 | 全局单队列 + FIFO + 同边不可超越 | 全局 `deque[SchedSeg]`；出队只看 arrival_seq；同边队首判定内置（**不识别来源边**）。改 `passive_scheduler.py` | 1边1云 走通；乱序注入不超越 → N边1云 mock 段流多源不串 |
| D2 | 包装剥离 + 最简准入 + NACK | `e{edge_id}-` 入口包装/出口剥离适配层（全部云→边消息必经出口）；全局限额 + NACK 沿收包 channel 直回。新增 `id_adapter.py` | 包装剥离一致性单测；打满限额→NACK→边重发 |
| D3 | 边失联处理 | SUSPECT(5s)/DEAD(30s)；按前缀清扫队列/pending；通道 teardown | 边假死注入 → 清理断言 |

### 模块 E：边侧多级 KV 存储（Mooncake 简化版，约 3.5 人周）

> 不从零重写，也不引入完整 Mooncake：**语义对齐 Mooncake 的本地简化版**。
> 砍：分布式 master、RDMA/跨机传输、P2P 语义；留：block-hash keyed 接口
> （`exists/prefetch/get/put/evict/pin`）、NPU+host DDR 分层、异步传输引擎单机退化。
> 复用：`hash_block_tokens`（与云池/GPI 同链）、vllm KVConnector 注册位
> （树内已有 Mooncake/SimpleCPUOffload/UCM connector）、host 池与未来云侧 OffloadStore 同构。

| # | 任务 | 内容 | 最小验证 |
|---|---|---|---|
| E1 | 接口定稿 | `TieredKVStore` 语义对齐 Mooncake，便于未来换真 Mooncake | 接口契约评审 + 桩实现 |
| E2 | 本地两级存取 | NPU(L0)+host DDR(L1)：put/get/evict/分层 LRU | 单边实例：驱逐到 host / 命中恢复正确性 |
| E3 | 异步传输引擎 + connector 注册 | 本地 DMA 队列 + 完成回调（D2H/H2D 与计算重叠）；注册为 vllm KVConnector | 恢复与计算重叠的并发正确性 |
| E4 | 边池集成原型 + 定标 | 接入边头尾层池（ht 原型）；**恢复时延 vs 头层重算成本定标**（tiering 成立与否的判决性实测） | 恢复时延 ≪ 重算的实测报告 |

### 模块 F：验证基座（约 1.5 人周，横切）

| # | 任务 | 内容 |
|---|---|---|
| F1 | 段流驱动器 + 不变量断言库（**第 1 周交付**） | 单源/多源/乱序/故障注入脚本；断言 ≤5 条（同边序=arrival_seq、Σinflight≤限额、ref_cnt 守恒、registry⊇块表、ZOMBIE 纪律） |
| F2 | 打点最小集（内嵌各包） | (edge, cloud) 维度：出队时延/NACK 数/命中数 |


## 2. 本期不开发（后续阶段），及衔接说明

| 项 | 归属阶段 | 衔接说明 |
|---|---|---|
| 路由打分/GPI 实质/反熵/lease 实质 | 第二阶段（模块 B 换芯） | 协议字段本期已全，只换内核 |
| 逐边配额/优先级档 | 第二阶段（模块 D 增强） | 队列形态已是最终形态 |
| prepare 缓存多槽 LRU | 第二阶段（模块 D 增强） | 一期单槽沿用 + 0731 键校验；多槽属性能优化 |
| 控制消息全类型 schema（Pause/Resume/PreemptNotice/EdgeFreeNotice） | 第一期信封已预留 type 字段，第二期随过载包落地 | A5 的 CtrlMsg 信封与重传/幂等机制一期已建 |
| **过载与重算（修正版 WP7）** | 第二阶段，分两期：一期 Pause/Resume 流控 + L3 协同重算（PreemptNotice+优先席）；二期 L2 host 卸载（OffloadStore，ht 必须做好，em 可更后） | **pin 不在此包**（已在模块 C4）；L0/L1 复用 vllm 原生；L2 与模块 E 边侧多级存储同构，届时应做成同一组件 |
| E2E 性能基线与容量规划 | 第二阶段末（M4 前后） | 含单边喂养比（1 边可带几云）、路由打分调参、命中四元组观测上线 |
| 入口会话亲和（session sticky） | ht 阶段 | 影响 edge_hit；em 无感 |
| 租户隔离 / cache_salt（可选） | 视业务需求，ht 阶段评估 | extra keys 同源链路（C2）已预留位置 |
| 云侧二次组 batch | 性能预留（§3.7 六要点已留路径） | 纪律：调度单元保留独立 payload、回调按段粒度 |
| 动态建链（方案 B） | 未来替换静态域 | 纪律：P1 的"无跨实例集合通信"是替换平滑性的前提 |
| 多 DP 叠加 | ht 阶段 | 见 §3 分析：DP rank 吸收为独立边/云 + D1-D5 处置 |
| ht（首x尾x）全套 | 模块 E 之后 | 见 §4 统一性框架与 ht 专属增量 |

---

## 3. 多 DP × 多边多云叠加分析

**现状**：边侧共享模型 DP = 单 NPU 多虚拟 worker（`_KV_CACHE_CONFIGS_PER_DP_RANK` 合成 global
KV buffer，`shared_model_edge_worker.py:655-681`）；云侧 DP = 每实例 `cloud_npu_count` 个 NPU，
独立 passive core/端口/通道池（`dp_rank×2` 偏移）；**1-1 下按 dp_rank 一一配对**。

**化解总纲**：`cloud_id=(实例, dp_rank)`、边同理——**DP rank 吸收为独立的边/云**，多边多云模型
天然覆盖，不需要第三维概念。残余困难：

| # | 困难 | 处置 |
|---|---|---|
| D1 | pair 组数上平方：(E×边dp)×(C×云dp)×3 | 一期单 DP 不触发；后续亲和集裁剪 |
| D2 | prefix 命中被 DP 分片（同前缀 1/dp 概率） | 中央把云 dp 当独立云做一致性哈希，GPI 按 (cloud, dp) 键控（设计已兼容） |
| D3 | 共享模型边的设备资源复用（组/buffer/stream 共享单 NPU） | 按"每虚拟 worker 持 C×3 组"核算显存；必要时虚拟 worker 时分复用通道 |
| D4 | 端口规划升维到 (edge_id, edge_dp, cloud_id, cloud_dp) | WP1 端口表重排，机械工作 |
| D5 | 入口 LB 与 prefix 亲和冲突（ht 的 edge_hit、会话亲和） | ht 阶段入口加 session sticky；em 不受影响 |

**结论**：em+单 DP 时叠加困难全部不出现；多 DP 是多边多云的特例而非新问题。

---

## 4. 两模式统一性框架（em / 首x尾x）

**三个配置维度 + 一个统一公式**，em 收进 ht 的统一逻辑（em = k=0 退化）：

```python
cloud_layers = all_layers if k == 0 else middle_layers(k)
edge_layers  = {}         if k == 0 else head_tail_layers(k)
edge_hit     = +∞         if k == 0 else edge_local_hit()   # em：embed 查表免费 ≡ 命中无穷
effective_start = min(edge_hit, cloud_hit)                  # 两模式共用一行
c2e_payload  = LOGITS_POSITIONS if k == 0 else RANGE_FROM(effective_start)
```

**各功能点统一/分叉**：模块 A/B/D/F 完全统一；模块 C 统一（层集合配置 + SO 可空"边侧块表"字段）；
模块 E 为 ht 专属新增（em 无）；后续过载包主干统一、仅 L3 重入代价模型分参数（em 激进/ht 保守）。

**分叉纪律**：模式分支只允许出现在三处——配置层（层集合/k）、`effective_start` 计算、
c2e 负载类型；调度/KV/通信/异常主逻辑禁止 `if mode == ...`；schema 一律统一+可空字段。

**ht 专属增量速查**（em 完全不用做）：边池 EdgeKVStore、EdgeFreeNotice、发送区间下探
`[min(edge_hit, pinned), end)`、pin 失败补发通道、尾段同步回归。

---

## 5. 汇总表

| 模块 | 任务（每项 ≈1 人周） | 工作量（人周） | 最小验证场景 | 独立验证 |
|---|---|---|---|---|
| A 通信与角色 | A1 角色配置 / **A2 线序适配（最先合入）** / A3 pair 建组 / A4 ZMQ 控制面 / A5 控制消息 | ~5 | 1边1云 回环+属性测试 → 1边2云 | ✅ |
| B 中央调度器与边云交互 | B1⚡schema / B2 Route 服务端（轮询） / B3 心跳+注册广播+GPI 空转 | ~2.5 | mock 对打 → 1边2云 | ✅✅ |
| C KV 管理与边云协议（em） | C1⚡SO schema / C2 CloudKVStore / C3 ReqRegistry / C4 LeaseTable / C5 数据源切换 / C6 Route 客户端 / C7 全量发送+FIN | ~6（可 2 人并行：云线 C2-C5 / 边线 C6-C7） | 1边1云 端到端对标原生 | ✅ |
| D 云侧内部调度 | D1 全局 FIFO+同边约束 / D2 包装剥离+最简准入 / D3 失联处理 | ~2.5 | 1边1云 → N边1云 mock 段流 | ✅ |
| E 边侧多级 KV 存储（Mooncake 简化版） | E1 接口定稿 / E2 两级存取 / E3 异步传输+connector / E4 集成原型+定标 | ~3.5 | 单边实例两级恢复+时延定标 | ✅ |
| F 验证基座 | F1 段流驱动器+断言库（第 1 周交付） / F2 打点最小集 | ~1.5（横切） | 内嵌各包 | ✅ |

**第一阶段合计约 21 人周**（任务按 1 人周粒度组织；4~5 人 × 5~6 周并行，含联调缓冲）。

**集成里程碑**：
- **M1**：A+B+C+D 集成，1边1云 em 全流程对齐现网行为（路由恒 C0）；
- **M2**：1边2云走通轮询路由、心跳、NACK 换云、云宕机广播；
- **M3**：N边1云 mock 段流验证多源调度形态；
- **M4（进入第二阶段）**：路由换芯（打分/GPI）、配额、过载两期、E 产品化 → ht 启动。

**并行纪律**：① 协议第一周冻结（B1/C1 两个 ⚡ 任务）；② 每任务交付 = 代码 + 基于 F1 基座的验证；
③ A2（线序适配）最先合入；④ 异常路径与正常路径同优先级验收。

---

## 6. 开发清单总览（一期 + 后续，扫描校对版）

> 本节为全量开发项的唯一权威清单（与 §5 汇总表、任务级设计文档波次图一致）。

### 6.1 第一阶段待开发（em 场景，约 21 人周）

| 模块 | 功能点 |
|---|---|
| **A 通信与角色** | A1 角色与配置（id/epoch/注册表）｜**A2 线序适配层（最先合入）**｜A3 静态域+pair HCCL 建组｜A4 ZMQ per-pair 控制面｜A5 可靠控制消息（FIN/NACK/心跳/teardown） |
| **B 中央调度器与边云交互** | B1⚡协议 schema 冻结（含 PinReq/PinAck）｜B2 Route 服务端（轮询内核 + **同步 pin 确认，以云 ack 为准**）｜B3 心跳摄入+注册/epoch/DEAD 广播+GPI 空转｜B4 交互建模 |
| **C KV 管理与边云协议** | C1⚡SO 协议改造（去块表化+lease_id+可空边侧块表）｜C2 CloudKVStore（KVCM 下沉+权威命中）｜C3 ReqRegistry+TTL GC+FIN/ZOMBIE｜C4 LeaseTable（pin 预约）｜C5 slot_mapping 数据源切换+删虚拟显存 hack｜C6 边侧 Route 客户端+路由表+NACK 重发+降级｜C7 边侧全量发送+decode 直发+FIN｜C8 复用/自研清单 |
| **D 云侧内部调度** | D1 全局单队列+FIFO+同边不可超越（busy loop 单线程驱动）｜D2 入口包装/出口剥离+最简准入+NACK｜D3 边失联处理（SUSPECT/DEAD） |
| **E 边侧多级 KV 存储（Mooncake 简化版）** | E1 接口定稿（TieredKVStore 语义对齐）｜E2 本地两级存取（NPU+host DDR）｜E3 异步传输引擎+KVConnector 注册｜E4 边池集成原型+恢复时延定标（go/no-go 判据）｜E5 云侧多级存储路径分析 |
| **F 验证基座** | F1 段流驱动器+不变量断言库（第 1 周交付）｜F2 打点最小集（内嵌各包） |

### 6.2 第二阶段（em 完整化）

1. 路由换芯：前缀匹配打分 + 一致性哈希 + GPI 实质（攒批/反熵/bloom 对账）
2. 逐边配额 + 优先级档（模块 D 增强）
3. prepare 缓存多槽 LRU
4. 过载与重算一期：Pause/Resume 流控 + L3 协同重算（PreemptNotice+优先席重准入+防雪崩）
5. 过载与重算二期：L2 host 卸载（OffloadStore，与模块 E 同构合并为同一组件）
6. **截断发送优化**：同步确认后 confirmed_hit 可信，ht 默认启用跳过已缓存段；em 配置开关（按 e2c 带宽实测决策）。配套：段协议携带完整哈希链 + 准入时 confirm_lease + 补发通道兜底（em 启用截断则需实现罕用的补发路径）
7. E2E 性能基线与容量规划（单边喂养比、打分调参、命中四元组观测）
8. N边M云 全量回归（多源段流+跨边共享+穿插矩阵+故障注入）

### 6.3 ht（首x尾x）阶段

9. 双池拆分落地（EdgeKVStore 头尾层池 + SO 边侧块表字段启用）
10. 发送区间下探 `[min(edge_hit, confirmed_hit), end)` + pin 失败补发通道
11. EdgeFreeNotice（边本地 preempt 通知）+ 边池自准入
12. 模块 E 产品化（边侧多级存储，依赖 E4 定标结论）
13. 尾段同步与 wire 错位的高频穿插回归（head_tail 正确性命门）
14. 入口会话亲和（session sticky，影响 edge_hit）
15. 租户隔离/cache_salt（可选，视业务）

### 6.4 演进/性能预留

16. 云侧二次组 batch（§3.7 六要点：拼接+切片回传+merge window+部分失败降级+置换收云内+同边约束）
17. 动态建链（方案 B：独立域+2-rank 带外建组+中央注册中心；替换静态域，前提是"无跨实例集合通信"纪律已守）
18. 多 DP 叠加（DP rank 吸收为独立边/云 + D1-D5：亲和集裁剪/DP 分片哈希/共享模型边资源核算/端口升维/会话亲和）
19. 段边界 hidden cache（打破 min 规则的可选优化，显存换重算）
20. RDMA/Mooncake 真身接入（更大规模弹性再评估；TieredKVStore 接口已对齐可平滑替换）
