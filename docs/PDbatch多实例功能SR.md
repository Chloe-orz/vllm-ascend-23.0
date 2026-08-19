# PD batch 分离边云协同推理·多实例扩展 功能 SR

> 依据《PDbatch分离边云协同多实例调度详细设计_NEW.md》（含 2026-08 全部定案）整理的功能需求规格。
> 范围：将边云 PD 分离架构从 **1 边 : 1 云** 扩展为 **1 边 : N 云实例**（N ≤ 16，按模型口径）。
> 条目格式：编号 | 需求描述 | 优先级（v1 / v1.x）| 验收标准 | 溯源（设计文档章节）。

---

## 0. 前提假设与非目标

**前提假设**：

- A1 所有云实例**同构**（卡型、显存配置、模型与 dp·tp 配置一致），启动期 profile 校验差异超阈值即拒绝拉起（§6.6）；
- A2 多实例维度 N 与现有 data_parallel_size(D) **正交**：实例间松耦合无集合通信，实例内 dp+tp 协调不变（§9）；
- A3 边侧为单点算力（1-2 卡），一个 EngineCore 进程组内 N 个 per-instance scheduler 时分复用（§3.1）；
- A4 边云为**一个 G0 世界组**，rank 编队 / 通道 / 启动 barrier 单次完成（§2.2/§4.1）。

**非目标（明确不做）**：

- NG1 边侧 KV 准入共享（共享池 + 准入协调器）--v1 不做，动态配额为 v1.x 候选（§6.2/§6.2.1）；
- NG2 KV 跨实例迁移 / 跨实例 prefix cache 亲和（§6.5）；
- NG3 死实例原地修复 / 热重入（communicator 重组，§10.4 不做项）；
- NG4 实例间引入任何集合通信或 barrier（§9）；
- NG5 端点↔dp 静态绑定（dp 维度留给前端 internal LB，§3.12）。

---

## 1. FR-CFG 实例配置与编队

| 编号 | 需求 | 优先级 | 验收标准 | 溯源 |
|---|---|---|---|---|
| FR-CFG-01 | 提供 `--instance-parallel-size` 配置实例总数 N，边云三侧同值 | v1 | 三侧不一致时拉起失败并报错 | §2.1 |
| FR-CFG-02 | 提供 `--instance-parallel-start-rank` 配置实例号 i（云侧 0..N-1；边侧形态 B 前端命令同款语义） | v1 | 越界（i ≥ N）拉起失败 | §2.1 |
| FR-CFG-03 | `--nnodes` 恒为 2，`--node-rank` 仅表达边(0)/云(1)角色；node_rank × instance-start-rank × dp-start-rank 三轴正交 | v1 | 同机 K 实例 = 同 node_rank + 不同 start-rank + 独立 ASCEND_RT_VISIBLE_DEVICES 切片 | §2.1 |
| FR-CFG-04 | 云侧全局 rank 起点 = `E + i·D·C + j·C`（E=边卡数，i=实例号，j=dp start-rank，C=每实例卡数），替换现硬编码 `edge_npu_count` | v1 | N 实例 rank 区间互不重叠；同机实例无 rank 冲突 | §4.1 |
| FR-CFG-05 | G0 世界组 `[0, E+N·D·C)` 编队：rank0 master，仅 rendezvous + 启动 barrier；启动 barrier 全实例就位才放行 | v1 | 任一实例缺席时编队超时 fail-fast，不留半拉起状态 | §2.2/§4.1 |
| FR-CFG-06 | 边 rank 稳定在前（0..E-1），只进世界组与各实例 PP 子组，不进实例 DP/EP/coord 组 | v1 | 边 rank 出现在任何实例内组即违规 | §4.1 |
| FR-CFG-07 | 边侧模式 `embedding_only` / `head_tail`（首 x 尾 y）配置生效，决定边 KV 形态与通道集 | v1 | 两模式下行为符合 §2.3 表 | §2.3 |

## 2. FR-CHN 通道与端口

| 编号 | 需求 | 优先级 | 验收标准 | 溯源 |
|---|---|---|---|---|
| FR-CHN-01 | PRE_OUT 采用 ZMQ ROUTER/DEALER：边每 dp 绑定 D 个端口，N×D 个云 DEALER 连接，IDENTITY = instance start-rank，(dp, instance) 全 socket 唯一 | v1 | 任一云实例收发定向正确，无串台 | §2.2/§3.7.2 |
| FR-CHN-02 | PRE_OUT 云侧 readiness：每实例 HELLO/ACK 就绪表覆盖 {0..N-1}，齐后才参与数据面 | v1 | 实例未就绪时其数据不被投递 | §3.7.2 |
| FR-CHN-03 | hidden 通道 HCCL 按实例复制：每 (instance, dp) 独立 2P1D（2 prefill + 1 decode）通道 | v1 | 跨实例无通道共享；实例 i 的 isend/irecv 只走自己通道 | §4.4/§4.5 |
| FR-CHN-04 | coord gloo（dp>1）per-instance 独立端口组（master_port+201+i 等），不跨实例混用 | v1 | 同机多实例端口互不冲突 | §2.2 |
| FR-CHN-05 | 同机多实例（K>1）全通道端口/store 加 instance 偏移，拉起期占用检测 fail-fast（防同机串台） | v1 | 两实例同机拉起，端口冲突即拒拉 | §2.2/§2.6 处理项 #2 |
| FR-CHN-06 | 云侧不 bind 任何端口（全部主动连接边侧） | v1 | 云侧 netstat 无新增监听端口 | §2.2 |
| FR-CHN-07 | 控制通道（rpc_broadcast_mq / response_mq method 链）覆盖 N 实例启动编排 | v1 | 启动 method 链全部实例应答 | §3.10 |

## 3. FR-DEP 部署形态

| 编号 | 需求 | 优先级 | 验收标准 | 溯源 |
|---|---|---|---|---|
| FR-DEP-01 | 支持跨机部署：云实例分布任意台服务器（每台 C 卡一实例），G2 prefix 子组按实例派生 | v1 | §2.4 形态 N=4 拉起并通过功能验证 | §2.4 |
| FR-DEP-02 | 支持同机多实例：一机 K 实例（K=2/4）经 ASCEND_RT_VISIBLE_DEVICES 卡切片 + 端口偏移共存 | v1 | §2.5/§2.6 形态拉起；实例间无相互干扰 | §2.5/§2.6 |
| FR-DEP-03 | 支持四类典型场景（§2.7）：①qwen3.6-27B embedding_only N=8；②DS-v4-flash head_tail 首3尾1 N=4；③kimi embedding_only N=2 dp=2；④kimi head_tail 首1尾1 N=2 dp=4（边 2 卡 D=4） | v1 | 各场景按 §2.7 配置表/编队清单逐项可拉起 | §2.7 |
| FR-DEP-04 | 同机 K 实例错峰拉起（启动关键路径 ∝ K），同机资源竞争有观测 | v1 | K=4 同机拉起成功率 100%，竞争指标可见 | §2.6 处理项 #3 |
| FR-DEP-05 | N 上限按模型口径约束（qwen3.6-27b ≤16、DS ≤4、kimi ≤2），超限告警 | v1 | 超上限配置拉起告警 | §6.3 |

## 4. FR-FE 前端与请求路由

| 编号 | 需求 | 优先级 | 验收标准 | 溯源 |
|---|---|---|---|---|
| FR-FE-01 | 一实例一端点：N 个 ApiServer 各自独立 ip:port 监听，端点 i ↔ 实例 i（instance_id = client_index = i） | v1 | N 端点请求各自路由到对应实例 scheduler 组 | §3.12 |
| FR-FE-02 | 网关请求级分发：选端点 = 选实例；请求携带 instance_id pin 透传至 EngineCore | v1 | pin 合法性校验（0 ≤ id < N），非法 pin 拒绝 | §3.12 |
| FR-FE-03 | InstanceDispatcher 默认策略 RequestPinned；无 pin 请求（直连调试）least-loaded fallback | v1 | 无 pin 请求可被 fallback 调度且不破坏有 pin 请求 | §3.12 |
| FR-FE-04 | dp>1 采用「端点定实例、负载定 dp」：ApiServer = N（非 N×D），dp 维度由前端 internal LB（waiting×4+running 打分）选择 | v1 | 无端点↔dp 静态绑定；回投只看 client_index | §3.12.1 场景四 |
| FR-FE-05 | 输出按 client_index 定向回投发起端点，流式输出逐端点正确 | v1 | 网关无需响应关联即可正确回流 | §3.12 |
| FR-FE-06 | 形态 A（单命令）：`--api-server-count N` + `--api-server-endpoints instance<i>=ip:port` 键值列表（N 个端点唯一来源、顺序无关）；键集合恰为 0..N-1、ip:port 唯一、`--host/--port` 互斥 | v1 | 缺号/重号/越界/冲突均拉起失败 | §3.12.2 |
| FR-FE-07 | 形态 B（多命令，1 主 + N-1 attach）：主命令带 `--api-server-rpc-port`（显式必填）起 EngineCore + 实例 0 前端；attach 命令带 `--api-server-attach ip:port`（独立于 -dpa/-dpp 语义）只起 ApiServer 注册 | v1 | attach 命令不 spawn EngineCore、不进 rendezvous | §3.12.2 |
| FR-FE-08 | 形态 B 前端注册 barrier：EngineCore 等 client_count = N 注册齐才放行（与 G0 barrier 串联）；client_count 从构造定值改注册制 | v1 | 缺任一 attach 命令时整体阻塞并超时 fail-fast | §3.12.2 |
| FR-FE-09 | 形态 B 公共配置一致性校验：除 host/port/start-rank/attach/rpc-port 外逐字一致，不一致 fail-fast | v1 | 改模型路径的 attach 命令被拒 | §3.12.2 |
| FR-FE-10 | 网关部署约束（请求级分发，短连接或 request/stream 级路由）写入部署文档；SSE 长连接粘端点告警 | v1 | 文档交付 + 告警项 | §3.12 风险 #1 |

## 5. FR-SCHED 实例间调度（§7 定案规格）

| 编号 | 需求 | 优先级 | 验收标准 | 溯源 |
|---|---|---|---|---|
| FR-SCHED-01 | 全局调度：leader(dp0) 维护 N 实例全局视图（尾 ready ×3 序合并 / waiting 序合并 / running 过滤器 / 在途计数聚合），每 step 单点决策 (instance_id, batch_type)，经 all_reduce 分发 | v1 | follower force 对齐出 SO / 无工作出 dummy；决策单点唯一 | §7.1/§7.2 |
| FR-SCHED-02 | 两阶段决策：Stage A 层间定「调度什么」（单实例策略全局化），Stage B 层内定「调度哪个实例」 | v1 | 层序与选择键符合 §7.3 表 | §7.3 |
| FR-SCHED-03 | 层间优先级：插队例外（链不变量）> [全局 IDLE 时首段 PF] > DRL > DRF > DL > DF > PL；全局 HIGH（任一实例 chunk 在飞）跳过 PF 层；**DRL（MTP 尾）任何水位下先于一切其他首段与尾** | v1 | 构造竞争场景验证层序 | §7.3 |
| FR-SCHED-04 | 实例选择键：尾类 = ready 时间最早（per-instance D-dp AND，取较晚 dp），并列按层序再按 instance_id；首段 = original_seq 全局 FIFO 落 pin 实例 | v1 | 跨实例到达序/就绪序单调 | §7.3 |
| FR-SCHED-05 | 尾 ready 判定数据驱动：recv fence（COMM_RECV，NPU event）完成才 ready；dp1 ready 位经 all_reduce 捎带 N-bit bitmap | v1 | 未就绪尾不被调度 | §7.2/§5.2 |
| FR-SCHED-06 | 五条硬约束：实例内保序（队首不跳队）、2DP lockstep、尾批不可丢弃/取消、请求不迁移（chunk/MTP/decode 全程 pin 原实例）、MTP 链不变量（DRF->DRL 交替、占位 D首紧跟、pregenerated FIFO） | v1 | 任一约束破坏即测试失败 | §7.5 |
| FR-SCHED-07 | 全局化规则：running 准入门 per-instance 过滤器；DL/DRL delay 窗 per-instance 计时（DL 30ms/DRL 10ms，§5.2 落地后随 fence 门控归零）；decode/draft 单飞门 per-instance；chunked 状态机 per-instance | v1 | §7.4 表逐行符合 | §7.4 |
| FR-SCHED-08 | 兜底：首段年龄阈值 T（超时强制 PF）、尾链龄监控进 InstanceLoadStats、队头阻塞有界跳过（≤K 个）、无候选 coord EMPTY + sleep 等云 | v1 | 长尾场景不饿死、不全局卡死 | §7.6 |
| FR-SCHED-09 | 部分实例 wait-for-tail 不阻塞其他实例调度（多实例收益点） | v1 | 实例 i 等云期间实例 j 正常调度 | §5.1.3 机制 10 |
| FR-SCHED-10 | dummy 不串实例：某 (i,bt) 无工作的 DP 只出本实例 dummy | v1 | 跨实例 dummy 出现即违规 | §5.5 |
| FR-SCHED-11 | 调度层计算/通信分离（§5.2 核心）：TAIL 等 hidden 期间 worker 继续 dispatch 其它 round/实例 | v1 | 重叠执行生效，边空闲窗口被填充（收益验证 §1.2） | §5.2 |

## 6. FR-DAT 数据面

| 编号 | 需求 | 优先级 | 验收标准 | 溯源 |
|---|---|---|---|---|
| FR-DAT-01 | G2 prefix 通信子组按实例派生（实例 i 云 workers + 边 rank），PP 路由按 instance 选子组 | v1 | 边 rank 进且仅进自己服务实例的 PP 子组 | §4.2/§4.3 |
| FR-DAT-02 | PRE_OUT 按实例定向：边→云 (实例 i, dp j) 的 hidden/KV 只投递到对应实例 | v1 | 无跨实例错投 | §3.7 |
| FR-DAT-03 | 边侧算力跨实例时分复用：实例 i 等云回包期间，边可首层喂实例 j（核心收益目标） | v1 | 边利用率相对 1:1 提升（§1.2 量化口径） | §1.2/§3.1 |
| FR-DAT-04 | rpc_broadcast_mq / sample_tokens 等控制方法链多实例正确（sample_tokens local_only 化为待核实项） | v1 | 启动链 + 运行链全实例通过 | §3.10/§8.2 |

## 7. FR-KV KV 与准入

| 编号 | 需求 | 优先级 | 验收标准 | 溯源 |
|---|---|---|---|---|
| FR-KV-01 | head_tail：边 KV 池按 N 均分作 per-instance 准入簿记（per_dp_num_blocks/N），物理池共享不钳制 | v1 | 边物理分配 = 自身容量，无超卖（§6.6 实现要点） | §6.1 |
| FR-KV-02 | embedding_only：边无 edge KV，准入免（上报虚拟大值，num_blocks 恒云侧） | v1 | 边侧零 KV 开销 | §6.1/§6.6 |
| FR-KV-03 | 启动期 num_blocks 汇聚：per-instance 值 = min(edge/N, min_i cloud_i)；**边不进全局 min**（防边物理池被钳到 per-instance 值超卖） | v1 | head_tail 下边物理池 = 全容量 | §6.6 |
| FR-KV-04 | 云侧 KV：实例 i 物理分配 = per-instance 汇聚值（cloud-bound 下无损失）；N×D scheduler 同值 | v1 | 同构校验 + 单选 config 分发正确 | §6.5/§6.6 |
| FR-KV-05 | prefill_inflight_limit per-(instance,dp) 作用域（2P1D 通道池按实例复制） | v1 | 跨实例在途互不挤占 | §6.4 |
| FR-KV-06 | KV 动态配额（软分区 + 只读占用计数借贷）：v1.x 候选，不做准入协调的共享 | v1.x | 方案评审通过后另立 SR | §6.2.1 |

## 8. FR-REL 可靠性

| 编号 | 需求 | 优先级 | 验收标准 | 溯源 |
|---|---|---|---|---|
| FR-REL-01 | 多源故障检测：进程级（launcher 监视子进程退出）+ 通道级 heartbeat（云 PassiveEC 周期 echo，边 X×3 未收判死）+ 集合通信 watchdog 兜底（hang 转 fail） | v1 | kill -9 云实例 / NPU 假死注入，均在阈值内检出 | §10.2 |
| FR-REL-02 | 云实例故障触发整体重启：决策单点 = 边主命令，teardown 全部边云进程后全量重拉（G0 重新编队） | v1 | 注入故障后有界 RTO 内服务恢复（readiness = N 端点全活） | §10.2 |
| FR-REL-03 | teardown 杀干净保证：systemd control-group 级杀死 + 重启前 npu-smi 显存残留检查（残留拒拉告警） | v1 | 重启后无孤儿进程/显存残留 | §10.2 |
| FR-REL-04 | 形态 B 重启编排：先杀全部 N 条边命令，再按主->attach 顺序重拉 | v1 | 编排脚本覆盖两形态 | §10.2 |
| FR-REL-05 | 在飞请求 fail-fast：故障/重启期间请求快速失败，网关/客户端重试语义明确 | v1 | 无请求无限挂起 | §10.2 |
| FR-REL-06 | 降级运行 N->N-1：heartbeat 判死后摘除实例（调度 alive 位跳过、网关摘端点、edge KV/通道记账回收），其余实例继续服务；恢复仍走整体重启 | v1.x | 摘除后 N-1 实例服务正常，无残留记账 | §10.4 |

## 9. FR-OBS 观测与运维

| 编号 | 需求 | 优先级 | 验收标准 | 溯源 |
|---|---|---|---|---|
| FR-OBS-01 | client_index（= instance_id）强制进 metrics label 与日志前缀，N 端点输出可区分 | v1 | 多实例并发下按实例过滤查询可用 | §3.12 改动 4 |
| FR-OBS-02 | InstanceLoadStats 覆盖 per-instance：队列深度、尾等待年龄（tail-wait age）、在途计数 | v1 | 负载倾斜可观测（调度兜底依据） | §3.5/§7.6 |
| FR-OBS-03 | 边利用率/空闲窗口填充率、per-instance 吞吐与 TTFT/TPOT 分实例上报（收益验证口径） | v1 | 相对 1:1 基线的提升可量化 | §1.2/§1.3 |
| FR-OBS-04 | 同机多实例资源竞争观测（权重 ×K、网口 per-server 聚合带宽口径） | v1 | K>1 场景带宽竞争可见 | §2.6 处理项 #3 |

## 10. FR-CMP 兼容与退化

| 编号 | 需求 | 优先级 | 验收标准 | 溯源 |
|---|---|---|---|---|
| FR-CMP-01 | N=1 退化为现网 1:1：单端点单实例，行为与现网一致（同一代码路径，部署差异仅端点数与 scheduler 分组数） | v1 | N=1 全量现网回归通过 | §3.12.1 场景一/二 |
| FR-CMP-02 | 现有实例内机制（2DP 协调、段级协调、EP all-toall、MC2/ALLGATHER）零改动（N 维不触及 D 维） | v1 | 相关现网测试全通过 | §9 |
| FR-CMP-03 | dp=1 与 dp>1 双口径支持：全局调度两阶段对 D 无假设（决策单点 leader dp0，follower force） | v1 | §2.7 场景三（D=2）/场景四（D=4）通过 | §7.1/§2.7 |

---

## 附：v1 交付边界汇总

- **v1 交付**：FR-CFG/CHN/DEP/FE/SCHED/DAT/KV/REL/OBS/CMP 全部 v1 条目（约 50 条）；
- **v1.x 候选**：FR-KV-06（动态配额）、FR-REL-06（降级运行）、§3.5 前端发布 + 网关 prefix 亲和（NG2 解禁路径）；
- **实现前置缺口**（代码层，FR 之外）：云侧 global_start_rank 硬编码改 `E+i·D·C+j·C`（FR-CFG-04 落地点）；LOW 预测器/挑选器不一致核实；dp=1 + api_server_count=N 的 DPCoordinator 行为核实；kimi 2 卡实例口径 R 重实测。
