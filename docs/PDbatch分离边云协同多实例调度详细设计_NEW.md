# PD batch 分离边云协同推理 - 多实例调度详细设计

> 本文档将边云 PD 分离架构从 **"1 边 : 1 云"** 扩展为 **"1 边 : N 云"**（N 个云实例）。
> 目标是提升边侧算力利用率：边侧 1–2 卡只做 embedding + 首 x 层 + 尾 x 层，
> 在 1:1 时长期空闲等待云侧中间层；引入 N 个云实例后，边侧作为 N 流共享的单一首/尾处理器，
> 在一个实例的尾层等待云回包期间，可首层喂给另一个实例，从而把边侧空闲窗口填满。
>
> **多实例 N 是与现有 data_parallel_size(D) 正交的新维度**：实例间松耦合、请求级分发、
> **无集合通信**；实例内部保留现有 dp+tp / tp 配置与跨 DP batch_type 协调不变。
> N 间无集合通信可乱序；D 内（2DP）紧耦合 EP all-toall 配对。
>
> 适用前提：本文档为**方案设计阶段**（不修改代码）。所有结论均经代码核实，引用处标注文件:行号。

---

## 0 术语与上下文

| 术语 | 含义 |
|------|------|
| **N** | 云实例数（新维度）。边侧 1 个、云侧 N 个实例 |
| **D** | data_parallel_size，实例内 DP 并行度（现有，如 dp=2） |
| **C** | cloud_npu_count，每实例云侧 TP 卡数 |
| **E** | 边侧 rank 数：shared-model 1 卡 E=1（1 进程 host D virtual）；per-rank 2 卡 E=D |
| **实例** | 一个完整的云侧 deployment（含 D×C 个云 rank），端到端承载一组请求的中间层 |
| **PF/PL/DF/DL** | PREFILL_FIRST / PREFILL_LAST / DECODE_FIRST / DECODE_LAST 四段独立调度 |
| **HEAD batch** | FIRST 段（PF/DF）：边侧首层 forward + isend 到云 |
| **TAIL batch** | LAST 段（PL/DL）：边侧 recv 云回包 + 尾层 forward + sampler |
| **2P1D** | 边侧每 (instance,dp) 2 个 prefill channel + 1 个 decode channel（prefill_inflight_limit=2） |
| **COMPUTE** | 纯前向任务：head（首层+isend）/ mid / tail（尾层+sampler），通信之外的纯计算单元 |
| **COMM_RECV** | 接收通信任务 = irecv post + 设备侧 fence + channel 释放（本设计新增的任务类型） |
| **设备侧 fence** | `handle.wait()`：不阻塞 CPU，只做 `current_stream.wait_event(nccl_end_event)` + record_stream |
| **CPU 可见完成** | `event.query()` / `Event.synchronize()`：让调度器/worker 在 CPU 上得知 recv 完成 |
| **coord** | 跨 DP batch_type 协调（`_coordinate_bt` all_reduce），锁 bt 不锁 instance |
| **leader** | shared-model 下 `_is_leader` 的 worker（tail 1× 代算）；实例调度上指 dp0 EngineCore |
| **POST_OUT** | 控制面信号：云 worker 推理完成 + isend 已发起。**2026-08 定**：§3.4 TAIL 自投递 + recv fence **采纳**；POST_OUT 通道**保留**（剩余载荷 = 完成 ack 类控制信号），**形态已定 b** = 共用 PRE_OUT 的 ROUTER/DEALER 双向 socket（§3.7.1，线程模型 §3.7.2） |

### 当前基线（1:1 已落地）

- `PDSeparatedScheduler` 产出 PF/PL/DF/DL 四类独立 `SchedulerOutput`
- `EngineCore.step_with_batch_queue` 按 batch_type 经 PRE_OUT 发首段、POST_OUT 收尾段
- 云侧 `PassiveEngineCoreProc` 改写 PF->PL / DF->DL
- 边侧 `_drain_pd_channel_inbox` 把回传段入 `prefills_last_ready` / `decodes_last_ready`
- 跨 DP batch_type 协调（`_coordinate_bt`）保证 2DP 同 bt -> 云 EP all-toall 配对
- shared-model 尾层为 **leader 1× batched tail**（2DP token 合并，leader 代算）

### 设计原则

1. **实例间松耦合**：无集合通信、无协调 barrier，请求端到端钉在一个云实例（中间层 KV 驻留该实例，不跨实例迁移）
2. **实例内紧耦合**：保留现有跨 DP batch_type 协调 + barrier-drain 尾层
3. **正交扩展**：多实例是"实例间"新增层，不破坏实例内 dp+tp 语义
4. **边侧是吞吐天花板**：N 流共享单一首/尾处理器，利用率提升落点在填满边侧空闲窗口

---

## 1 需求背景

### 1.1 1:1 瓶颈

边云 PD 分离下，decode 每 token 走 **边(首层) -> 云(中间层) -> 边(尾层)** 往返。边侧 1–2 卡只做 embedding + 首/尾少量层，算力远小于云侧。1:1 时：

- 边侧发完首层 isend 后，**阻塞等待**云侧中间层算完 + hidden 回传，期间边侧算力空闲
- 云侧中间层算完发回 hidden 后，等边侧尾层，期间云侧算力也闲置
- 边侧空闲窗口 = 云侧中间层计算时间 + 双向传输时间，这是 1:1 下无法消除的串行依赖

### 1.2 N 实例重叠收益

引入 N 个云实例后，边侧时分复用：在实例 i 的尾层等云回包期间，给实例 j 喂首层。两个方向重叠：

- **云 -> 边**：尾层 gate 在"收到对应云实例 isend（云算完）"之后，用 tag 把 isend 匹配回正确流
- **边 -> 云**：持续把首层产出喂给空闲云实例，保证云侧不空转

边↔云用 isend/irecv 点对点异步传输，**跨实例不走集合通信**，与实例内 DP 集合通信路径分开。

### 1.3 收益约束

- 边侧算力是天花板：N 越大，边侧首/尾处理越成瓶颈，N 上限受边侧算力约束
- **目标边云算力比（2026-08 明确）**：embedding_only（边 1 卡）= 1:32、head_tail 首 x 尾 x（边 2 卡）= 2:32--云侧总量固定 32 卡（4 台 8 卡服务器满配），边侧以 1~2 卡服务全部 N 流，是"边侧是吞吐天花板"的量化口径；多实例重叠收益兑现的前提 = 边侧首/尾吞吐 ≥ N 流喂入速率（§6.4）
- **N 范围（更新，2026-08）**：qwen3.6 典型配置 2 卡/实例，8 卡 A2 服务器可部署 4 实例（§2.6 形态二），N 典型 4~8、上限 16（§1.4）。**N ≥ 8 进入容量临界区**（edge/N ≈ cloud，翻转点 N* = R ≈ 8.16，见 §6.3），边侧 KV/算力资源需随 N 扩展（§1.4 遗留问题）或启用 §6.2 共享池
- inflight 约束：2P1D 下每 (instance,dp) 2 个 prefill 在飞，边侧共 4N 个 prefill 在飞（N=8 时 32 个在飞，边侧压力评估见 §6.4）
- 边侧 KV 约束：per-instance 分区下每 (instance,dp) 分到 per_dp_num_blocks/N，须覆盖 2 inflight prefill 的 KV


### 1.4 场景范围
1、多实例支持mtp 等特性；多实例叠加多dp（云双机）设计要考虑
2、模型（云侧部署卡数，2026-08 明确）：qwen3.6-27b = **2 卡**/实例、deepseek-v4-flash-w8a8 = **8 卡**/实例、kimi25_w4a8_static_m6 = **16 卡**/实例（跨 2 台 8 卡服务器）；优先 qwen3.6-27b（沿用 §6.3 实测数字）
3、基于HCCL通信域，不支持在线动态加入退出，某个云实例故障，多实例故障
4、不支持云异构，云实例同构（卡型 / gpu_memory_utilization / 模型与 dp·tp 配置一致）
5、**云侧一台服务器部署多个实例（2026-08 新增，必选场景）**：qwen3.6 计算基线是 2 卡，云侧实例 2 卡，8 卡 A2 推理服务器部署 4 实例（§2.6 形态二，由"v1 不支持"改为 v1 支持）；实例数最大 16（= 4 服务器 × 4 实例），边侧资源要基于实例数扩展（N ≥ 8 容量临界分析见 §6.3）
6、**目标边云算力比（2026-08 明确）**：embedding_only（边 1 卡）= 1:32、head_tail 首 x 尾 x（边 2 卡）= 2:32（云侧 32 卡 = 4 台 8 卡服务器满配）

**每模型部署矩阵（4 台 8 卡服务器 = 32 卡满配下）**：

| 模型 | 实例卡数 C | 每服务器实例数 K | N（满配） | 形态 | 备注 |
|------|-----------|----------------|-----------|------|------|
| qwen3.6-27b | 2 | 4 | **16** | §2.6 形态三c | 同机多实例主力场景；N=16 容量翻转（§6.3） |
| deepseek-v4-flash-w8a8 | 8 | 1 | 4 | 每服务器 1 实例（无共置） | 单机 tp8 实例；R≈17.56，N=4 远低于翻转点 |
| kimi25_w4a8_static_m6 | 16 | -（实例跨机） | 2 | 实例跨 2 台服务器（云双机，§2.1 不占额外 node-rank） | 实例内多机；跨机带宽承载实例内 tp 通信 |

-> 同机多实例（K>1）仅发生在小实例模型（qwen3.6 2 卡）；DS/kimi 实例卡数 ≥ 服务器卡数，天然每机 1 实例或跨机实例，§2.6 共置分析只对 qwen3.6 形态生效。**N=16 上限结论是 qwen3.6 特有口径**。

问题：
1、一个实例挂死，多实例挂死，-- 逃生手段；**同机共置下一台服务器挂 = 该机 K 个实例同时挂（相关性故障，故障域=服务器，见 §2.6）**
2、后续可靠性方案 考虑

问题
1、api选择实例，api在边云场景基于kv选择
2、边侧暴露多个端点，服务命令行
3、

---

## 2 配置方案

### 2.1 新增配置项

问题：
1、显示增加实例配置
2、边侧按照多实例，拉一次服务，

**不新增显式实例配置**：`nnodes` / `node_rank` 已完全编码实例数与实例id，**内部推导**，去掉 `--cloud-instance-num` 与 `instance_id`：

- 边侧：`N = nnodes - 1`（边固定 node_rank 0、单节点）
- 云侧：`instance_id = node_rank - 1`（**从 0 开始**，node_rank 1..N → 实例 0..N-1）
- 每实例 npu 数 = `cloud-npu-count / N`（云总 npu 不变）
- 校验：`cloud-npu-count % N == 0`（整除断言）；边必须 node_rank 0；云 node_rank ∈ [1, N]
- **节点维度 = 实例维度，不数物理机**：nnodes 数的是「边 + 每实例一个 node-rank」。实例内云多机（dp 云双机）**不占额外 node-rank**，用现有 dp 配置表达：`--data-parallel-size 2 --data-parallel-size-local 1` + 每机 `--data-parallel-start-rank 0/1`（1:1 dp=2 云双机现状即如此：nnodes 仍为 2，边 node-rank 0、云双机都是 node-rank 1，靠 start-rank 区分）。推导规则对单机/双机实例**全部成立**，无需显式实例配置
- **一物理机多逻辑 node-rank（同机多实例，2026-08 新增）**：反向同理--一台物理服务器可承载 **K 个逻辑 node-rank**（= K 个实例）。8 卡服务器部署 4 个 2 卡实例 = 4 次独立拉起，node_rank 1..4，各自 `ASCEND_RT_VISIBLE_DEVICES` 静态卡切片（0,1 / 2,3 / 4,5 / 6,7），**卡按实例静态划分、不共卡**（共卡分时复用不在考虑范围）。`instance_id = node_rank-1` 推导规则零改动成立，§2.6 形态二的「配置推导破坏」缺口由此消解
- 校验补充（同机多实例）：同一物理服务器上各实例卡切片**不重叠**（拉起脚本/部署侧保证，切片信息不进 vllm 配置面）；同机实例端口/store 偏移校验见 §2.2

| 侧 | 拉起配置（N=4 示例） |
|----|----------------------|
| 边 | `--nnodes 5 --node-rank 0` + `--edge-npu-count 2 --cloud-npu-count 32` |
| 云实例 i | `--nnodes 5 --node-rank 1+i` + `--edge-npu-count 2 --cloud-npu-count 32` |

| 侧 | 拉起配置（N=4 示例） |
|----|----------------------|
| 边 | `--nnodes 5 --node-rank 0` + `--edge-npu-count 2 --cloud-npu-count 8` |
| 云实例 i | `--nnodes 5 --node-rank 1+i` + `--edge-npu-count 2 --cloud-npu-count 8` |

- 边云共用同一 `--edge-npu-count / --cloud-npu-count`（云总 npu，非单实例），实例差异只在 node-rank
- dp 配置（D）由人为保证边云一致
- 实例注册/发现 = **静态推导**（node-rank），无动态注册
- 故障模型（v1）：任一实例挂即整个服务挂，不做 failover / 优雅 drain

**全局编排（torchrun rendezvous，G0 单世界组）**：

- 全局 world_size = E + N·D·C（E=edge-npu-count），rank 派生见 §4.1（边 rank 在前、实例按 node_rank 序续编，instance_id = node_rank-1 与 §4.1 的实例序一致）
- 边 = rank0 master，一次 rendezvous + 启动 barrier（全部实例就位才放行，任一实例未起整体阻塞，见 §3.10）
- pp 语义不变：每实例仍"边 pp0 + 云 pp1"两段借用，G2 per-instance（§4.2）
- 现状 1:1 即 `--nnodes 2 --node-rank 0/1`（N = 2-1 = 1，instance_id = 0，退化为现有行为），多实例是该编排的自然扩展（node 数变化，无新配置面）
- **同机多实例拉起示例（边 2 卡 + 1 台 8 卡服务器 × 4 实例，N=4，典型形态见 §2.6 形态三）**：

| 侧 | 拉起配置（N=4，qwen3.6 2 卡/实例） |
|----|----------------------|
| 边 | `--nnodes 5 --node-rank 0 --edge-npu-count 2 --cloud-npu-count 8` |
| 云服务器A 实例0 | `--nnodes 5 --node-rank 1 --cloud-npu-count 8` + `ASCEND_RT_VISIBLE_DEVICES=0,1` |
| 云服务器A 实例1 | `--nnodes 5 --node-rank 2 --cloud-npu-count 8` + `ASCEND_RT_VISIBLE_DEVICES=2,3` |
| 云服务器A 实例2 | `--nnodes 5 --node-rank 3 --cloud-npu-count 8` + `ASCEND_RT_VISIBLE_DEVICES=4,5` |
| 云服务器A 实例3 | `--nnodes 5 --node-rank 4 --cloud-npu-count 8` + `ASCEND_RT_VISIBLE_DEVICES=6,7` |

  同一物理机上 4 个实例各自独立拉起（4 个进程组/4 套 deployment），node_rank 即实例 id；world = 2+8 = 10。**rendezvous 语义注意**：torchrun/编排器的"node"须按逻辑节点理解--同一物理机上的多个实例以不同 node-rank 加入同一 rendezvous（边 master_addr），编排器需支持一机多 agent（或用每实例独立拉起脚本实现），实现期核实拉起工具对该模式的支持。


### 2.2 端口 / 通信 store 编码扩展

#### 2.2.1 各通道功能说明（2026-08 补充，均经代码核实）

边云之间共 6 类通道，按「启动期一次性握手 / 启动期 method 链 / 运行期持续通信」分三类：

**A. 运行期持续通信（2 类）**

| 通道 | 参与者 / 方向 | 功能 | 代码锚点 |
|------|--------------|------|---------|
| **ZMQ port（PRE_OUT / POST_OUT 对）** | 边 EngineCore ↔ 云 PassiveEC，每 dp_rank 一对 | PD 段级 `SchedulerOutput` 传输通道（`PPSchedulerZmqChannel`）：边经 **PRE_OUT** 发首段（PF/DF：首层调度指令 + head_token，云据此改写为 PL/DL 前执行中间层）；云经 **POST_OUT** 回尾段（PL/DL；§3.4 提案删除、**未定**，定删则收敛为单向 PRE_OUT，见 §2.2.2）。PUSH/PULL + 后台 pub/sub 线程 + `queue.Queue(1000)` 桥接，scheduler 线程不阻塞在 ZMQ 上；`IMMEDIATE=1` + warmup 消息防 2P1D 首消息丢失死锁 | passive_core.py:302-324（双端镜像构造）、:1037-1045（云侧端口 `pd_config.post/pre_out_port + dp_rank*2`）；patch_engine_core.py:181-194（边侧同偏移 + cloud_addr 自动发现） |
| **gloo coord group（master_port+201）** | 云实例内 DP0 ↔ DP1（云到云直连，边不在组） | 实例内跨 DP 协调通信域：云侧 EP all-toall 配对所需的跨 DP batch_type 协调 / 中间层段同步走此 gloo 组；双机部署时云 DP0 host、DP1 connect（单机 dp 同进程组内走本机） | passive_core.py:1096-1112（DP1 侧 connect）；IP 发现见下行 IP-exchange store |

**B. 启动期一次性握手（2 类，one-shot，用完即删）**

| 通道 | 参与者 / 方向 | 功能 | 代码锚点 |
|------|--------------|------|---------|
| **cloud_ip store（master_port+1+dp_rank，key=`cloud_ip`）** | 边 host（world_size=2），云写 / 边读 | 云节点可达 IP 上报：每 dp_rank 独立端口（防 EADDRINUSE），云连接仅与其配对的边 DP rank 的 store，写 `get_ip()`；边读到后构造 POST_OUT 的 connect endpoint（`tcp://{cloud_addr}:{post_out_port}`），**免去 CLI 显式传云 IP**。多实例下 key/port 双撞（§2.2 末） | passive_core.py:1006-1029（云侧写）；patch_engine_core.py:165-179（边侧 host + get 后 del） |
| **IP-exchange store（master_port+200，key=`coord_master_ip`）** | 边 DP0 host（wait_for_workers=False），云 DP0 写 / 云 DP1 读 | 云双机 coord 组 IP 发现（**边只做 IP broker，不进组**）：云 DP1 从边 DP0 的 store 取到云 DP0 的可达 IP，才能 connect master_port+201 的 gloo coord 组。仅 dp>1 且 MoE 时创建；非集合通信（set/get），不阻塞云启动 | patch_engine_core.py:137-163（边 host）；passive_core.py:1100-1112（云 set/get） |

**C. 启动期 + 运行期控制面（2 类）**

| 通道 | 参与者 / 方向 | 功能 | 代码锚点 |
|------|--------------|------|---------|
| **rpc_broadcast_mq / peer_worker_response_mq** | 边 executor（leader，connect_ip=master_addr）↔ 云 worker | 跨节点 `collective_rpc` 的 ZMQ 广播/回收对：**启动期 method 链全走此通道**（get_kv_cache_specs -> determine_available_memory（profile_run）-> get_kv_cache_configs -> initialize_from_config -> warmup，§3.10），运行期条件 rpc（update_max_model_len 等）同样 fan-out；边广播请求，云 worker 执行，结果按 rank 经 peer_worker_response_mqs 回收到边 | patch_multiproc_executor.py:87-101（边 leader 创建，connect master_addr）、:202-217（response_mqs 按全局 rank 组装）、:226-247（wait_until_ready 顺序死锁先例注释） |
| **边侧 PD TCPStore（master_port，HCCL rendezvous store）** | 边 rank0 host，全部云 worker connect | torch.distributed 世界组初始化 store（`master_addr:master_port`）：G0 世界组及所有子组（G2-G5 `new_group`）的 HCCL/gloo rendezvous 均经此 store 的 prefix key 完成；**单 store 服务单实例**，多实例需 per-instance store/key（N 个实例各自 rendezvous，§4.2 G2）。启动顺序链：cloud_ip 握手 -> 边此 store 就绪 -> 云 distributed init（顺序敏感，有死锁先例注释） | patch_multiproc_executor.py:236-240（顺序链注释）；cloud_ip -> 本 store 的先后依赖见 passive_core.py:1009-1011（"avoid colliding with the NCCL rendezvous store on master_port"） |

**启动顺序依赖链（1:1 现状，多实例逐实例复制，§3.10）**：

```
云 PassiveEC 起 -> DEALER connect 边 {pre_out_ports[dp_rank]} + 发 HELLO（IDENTITY = instance_id）
    -> 边 host PD TCPStore（master_port），各 dp 的 ROUTER actor 收本 dp 的 HELLO 建 readiness 表
    -> 云 worker distributed init（连 store，HCCL rendezvous）+ _init_message_queues
    -> rpc_broadcast_mq / response_mq wait_until_ready
    -> 启动 method 链（profile/KV/warmup）-> 运行期（单 socket 双向：PRE_OUT 下发 + POST_OUT 完成 ack；coord group + 数据面 isend/irecv；IP-exchange 显式配置、cloud_ip store 已删）
```

（另有一类同机通道 cloud_recv_hint_mq / §5.2.3 新增 recv_done_mq：进程内/同机 MessageQueue，不占跨机端口，不在本表范围。）

#### 2.2.2 通道收敛（2026-08 定型：IP-exchange 改显式配置已定；POST_OUT 保留 + 形态 b（共用 PRE_OUT 的 ROUTER/DEALER）已定，cloud_ip store 连带删除 -> **收敛 4 类**）

| 决策 | 状态 | 连带删除 | 依据 |
|------|------|---------|------|
| 云双机 coord IP 改**显式配置**（对端机 IP 经 CLI/env/拉起脚本传入，不进 vllm 配置面） | **已定** | IP-exchange store（+200） | 功能被显式配置取代；与 §2.1「静态推导、无动态注册」一致 |
| **POST_OUT 删除**（§3.4 提案：TAIL 自投递 + recv fence） | **已关闭（2026-08 定：不删）**--TAIL 自投递本身**采纳**，通道**保留**；**形态 b 已定**（共用 PRE_OUT 的 ROUTER/DEALER） | **cloud_ip store（+1+dp_rank）连带删除（已定）** | TAIL SO 自投递后 POST_OUT 剩余载荷 = 完成 ack；形态 b 下云不 bind 任何端口、边不需知云 IP，store 的唯一消费者（边构造 POST_OUT connect endpoint，passive_core.py:1006-1029）消失 |

**定型 4 类跨机通道**（IP-exchange 已删；POST_OUT 保留但形态 b 已定 = 与 PRE_OUT 共用同一 ROUTER/DEALER，cloud_ip store 连带删除）：

```
启动期：PD TCPStore（master_port，HCCL rendezvous，边 host / 云 connect master_addr）
        + rpc_broadcast_mq / peer_worker_response_mq（method 链）
运行期：ZMQ ROUTER/DEALER（边每 dp bind 显式配置的 `pre_out_ports[dp]`，云 (i,dp) DEALER connect 对应端口：PRE_OUT 下发 + POST_OUT 完成 ack 回传双向，§3.7.1/§3.7.2）
        + gloo coord group（+201，云到云直连，IP 显式配置）
数据面：HCCL isend/irecv（不占 TCP 端口）
```

**最终形态 4 类**（2026-08 定：TAIL 自投递采纳 + POST_OUT 保留 + 形态 b 共用 socket）：cloud_ip store 连带删除，启动链少 2N 条 one-shot 握手（§3.10 风险 #3 顺序死锁面部分消解）；ZMQ 满配端口 62 -> 1（§3.7.1）。

**收益（已定部分）**：IP-exchange 删除即少 N 条启动链与对应端口；失去自动发现（换机换 IP 改配置重拉），静态部署模型下可接受。

**代价**：云双机每实例需传对端机 IP（N 对地址，拉起脚本生成）；**实现期核实项：peer_worker_response_mq 的 handle 交换是否依赖云侧 bind 地址**（若依赖，云侧地址仍需传到边的途径，不能只靠 master_addr 反连）。

现有所有按 dp_rank 编码的端口/store，N 实例下会撞端口，需加 **instance 偏移**（与 ZMQ `instance*D+dp` 同类改动）：

| 通道 | 现有编码 | 多实例编码 |
|------|----------|------------|
| ZMQ port | `base + dp_rank*2` | **PRE_OUT（部署要求已定，2026-08）：边侧单端口**、不随 N/D 增长，显示配置无默认值；方案 = 边 ROUTER bind 单端口 / 云 DEALER connect（显式 identity = `instance*D+dp_rank`，`ZMQ_ROUTER_MANDATORY` 报 EAGAIN 不静默丢，per-instance 背压，分析见 §3.7.1）。POST_OUT **已定保留、形态已定 b**（2026-08，§3.4/§3.7.1）：与 PRE_OUT 按 dp 共用同一 ROUTER/DEALER socket（全双工，剩余载荷 = 完成 ack 类轻信号），**端口 = D 个显示值（`pre_out_ports[dp_rank]` 显式列表、不推导；随 D 增长、不随 N）、post_out_port 配置项取消、cloud_ip store 连带删**。N=16/D=2 满配端口数 62 -> 2（D=4 则 4） |
| IP-exchange store | `master_port+200` (按 dp_rank) | **删除**（云双机 coord IP 改显式配置，已定，§2.2.2） |
| gloo coord group | `master_port+201` (云到云) | 每实例独立 gloo 组，保留；对端 IP 改显式配置（已定，§2.2.2），端口仍加 instance 偏移 |
| cloud_ip store | `master_port+1+dp_rank` | **删除（已定，§3.7.1 形态 b）**：POST_OUT 共用 PRE_OUT 的 ROUTER/DEALER，云不 bind 任何端口、边不需知云 IP，key/port 双偏移问题随之消失 |
| rpc_broadcast_mq / peer_worker_response_mq（跨节点 collective_rpc ZMQ） | 按 dp_rank/world 编码 | 加 instance 偏移；**启动期 method 链全走此通道**（get_kv_cache_specs / determine_available_memory / initialize_from_config / warmup，见 §3.10），撞端口 = 控制面串台 |
| 边侧 PD TCPStore（HCCL rendezvous store） | 单 store 服务单实例 | **无需扩展端口、也无需 per-instance store**（2026-08 代码核实）：`nnodes>1` 时边云全体 dp rank 并入**同一个 world group**（`init_distributed_environment` 里 rank 重排 + `world_size_across_dp`，vllm/parallel_state.py:1602-1645），gloo cpu_group 与 HCCL device_group 均为该 world 上的 `new_group` 子组（parallel_state.py:416-425），靠 torch 内部 PrefixStore key 前缀（由全局唯一 rank 集派生）隔离，**不新增端口**。多实例沿用 G0 单世界组（§2.1，world = E+N·D·C）：各实例子组 rank 集全局唯一 ⇒ key 天然不撞。`get_next_dp_init_port()`（29500 递增）仅在 `nnodes==1` 单机多 DP 路径生效（:1646-1649），边云不经过。代价：`new_group` 是全 world 集合通信，N 实例启动偏差互相 gate（见 §3.10） |

云侧镜像不变（各实例独立 deployment，按 §2.1 推导的 instance_id 入自己子组，本就隔离）。

**同机多实例 = 偏移硬前提（2026-08 升级；形态 b 后偏移面收窄）**：跨服务器时同端口可靠 IP 区分，**同一服务器上多实例同 IP**。2026-08 通道收敛后仍在偏移面上的只剩 **gloo coord（+201）与 rpc_broadcast_mq / peer_worker_response_mq**（ZMQ 端口 per-dp 显式配置不随 N、IP-exchange/cloud_ip store 已删、PD TCPStore 单 store 零偏移）；这两类**不偏移必然撞、且无法靠 IP 兜底**。原 §2.6 形态二风险 #2 从"多实例风险"升级为同机部署的硬性前提，实现上必须：

- 偏移对同机场景**强制校验**：拉起期按 `instance*D + dp_rank` 规则推导端口并检查可用性（被占且非本实例规则端口 = 拒绝拉起），防止端口翻转串台
- 所有 store key 强制带 instance（`cloud_ip_{i}` / `coord_master_ip_{i}` 等），同机同 IP 下 key 不带 instance 无法区分

200，201内部编码，增加配置校验防止翻转，边云master_port增加约束，端口要能规则可推导（同机多实例下该约束从"建议"升级为"必须"：N=16、D=2 时偏移量达 instance*D+dp = 31，master_port 基值须预留足够偏移空间且不与机器上其他服务重叠）

**cloud_ip store 补充（启动期核实新增；该通道已按 §2.2.2 决策删除，以下分析作为缺口识别记录保留）**：不只是端口撞--N 个云 passive core 会写**同一个 key**，last-writer-wins，边侧 HCCL rendezvous 连到错误实例。key 必须带 instance（如 `cloud_ip_{i}`），边侧按实例分别取 IP/建 rendezvous。代码事实：云侧现写死 key `cloud_ip`、port = `master_port+1+dp_rank`（passive_core.py:1017-1028）；边侧按 dp_rank host 对应 store（patch_engine_core.py:171-178）。**同机多实例下该缺口双重命中**：4 个同机实例同 IP 写同 key + 同 port，两维度都必须加 instance 偏移（port = `master_port+1+ (instance*D+dp_rank)`，key = `cloud_ip_{instance}`）--删除通道后该问题整体不存在。

#### 2.2.3 ROUTER/DEALER 通信框图（形态 b 定案；IP/端口来源与连接信息）

**连接信息来源一览**：

| 信息 | 取值 / 来源 | 单实例（N=1,D=1） | 多实例 |
|------|------------|------------------|--------|
| pre_out_ports（ZMQ 端口列表） | **显式配置，必填、无默认、不做推导**（部署要求，§3.7.1）：`[p0..p_{D-1}]` 按 dp_rank 序、边云共享同一列表、长度=D、值唯一：边 dpX **bind** `tcp://*:p_X`（`*`=本机所有网卡），云 (i,dpX) **connect** `tcp://master_addr:p_X`（整体为边 dpX 的 IP:端口，非云本地） | 1 个（dp0） | D 个显示值（**随 D 增长、不随 N**；dp=4 即 4 个；post_out_port 配置项已取消） |
| 边 IP（仅出现在云的 connect 目标里） | `master_addr`（现有配置，= PD TCPStore host、边 rank0 所在机；**边云共享同一配置值**，现状 1:1 云侧即用它 connect PRE_OUT，passive_core.py:1040） | 同左 | 同左 |
| 云 IP / 云端口 | **无**：云不 bind 任何端口，边不需知云 IP（cloud_ip store 已删，§2.2.2） | 同左 | 同左（同机共置/跨机无差别） |
| DEALER IDENTITY | **静态推导** `instance_id`（= node_rank-1，§2.1，无新增配置）；dp 已由端口区分，identity 无需编码 dp，跨 socket 的 (dp, instance) 二元组全局唯一 | `"0"` | 每个 dp 的 ROUTER 内 `"0"`..`"{N-1}"`；**同机多实例同 IP 连同组端口，仅靠 IDENTITY 区分**（无 instance 端口偏移、无 IP 兜底需求） |
| readiness | HELLO 首帧（connect 后云发，ROUTER 收向自动带 [id\|"HELLO"]）；全部到齐才放行调度（G0 barrier，§3.10） | 1 个 HELLO | 每个 dp ROUTER 各收 N 个（全局 N×D） |
| 边内结构（仅边侧） | 每 dp 进程独立 ROUTER，**无 fan-in、无 IPC 转发**（§3.7.2 修订）；跨 dp 的 ack/负载统计经既有 inner-DP gloo 组汇入 leader | 单进程单 ROUTER | D 个 ROUTER（每 dp 进程一个） |

**图 1：单实例（N=1, D=1；identity 集合 = {"0"}）**

```
     边（master_addr 所在机）                          云（单实例 × D=1）
┌─────────────────────────────────┐              ┌─────────────────────────────────┐
│ EngineCore(dp0) = leader        │              │ PassiveEC(dp0)                  │
│                                 │              │                                 │
│  publish(SO): put_nowait        │              │  ack 生产: put_nowait           │
│         │                       │              │         │                       │
│         ▼                       │              │         ▼                       │
│  ┌───────────────────────────┐  │              │  ┌───────────────────────────┐  │
│  │ ROUTER actor（1 线程）     │  │              │  │ DEALER actor（1 线程）     │  │
│  │ bind tcp://*:PORTS[0]    │◄─┼──────────────┼──┤ connect                   │  │
│  │ · readiness 表            │─►│──────────────┼──►│ tcp://master_addr:PORTS[0]│  │
│  │ · ack inbox（按 id 记源）  │  │              │  │ IDENTITY = "0"           │  │
│  │ · per-id out 队列（有界）  │  │              │  │ · inbox→consume_new_out.. │  │
│  └───────────────────────────┘  │              │  │ · out 队列（HELLO/ACK）   │  │
│   send: NOBLOCK + MANDATORY     │              │  └───────────────────────────┘  │
└─────────────────────────────────┘              └─────────────────────────────────┘

  TCP 连接：唯一 1 条，云发起 connect，全双工（两个方向共用）
  注：云侧 connect 目标 master_addr:PORTS[0] 整体是【边的地址】（IP=边机，端口=边 bind 的端口），云本地不 bind
  ① HELLO          云→边  [id="0"|"HELLO"]     （readiness 注册）
  ② scheduler_out  边→云  ["0"|SO]             （identity envelope，DEALER 侧帧被剥掉，payload 同现状）
  ③ 完成 ACK       云→边  ["0"|ACK]            （TAIL 自投递后 POST_OUT 剩余载荷，§3.4）
  顺序：per-id pipe FIFO；per-id 队列满 = EAGAIN 留队重试（不丢、不阻塞 actor）
```

**图 2：多实例（示例：边 D=2，每 dp 一个 ROUTER；云服务器 A 同机共置 2 实例 × D=2 + 云服务器 B 1 实例 × D=2，N=3）**

```
     边（master_addr 机，D=2；每 dp 进程各一个 ROUTER，端口按 dp 推导）
┌──────────────────────────────────────┐
│ EngineCore(dp0)：ROUTER actor（1 线程）│        云服务器 A（IP_A，同机共置实例0/实例1）
│   bind tcp://*:PORTS[0]               │   ┌──────────────────────────────────────────────┐
│   · readiness 表（本 dp 的 N 个 id）   │◄──┼─ IP_A 实例0.dp0   DEALER id="0" ────────────┤
│   · ack inbox（按 id 记来源）          │◄──┼─ IP_A 实例1.dp0   DEALER id="1" ────────────┤
│   · out 队列 × N（id = instance）      │─►─┼─ 两者 connect tcp://master_addr:PORTS[0] ────┤
│   · ack -> dp0 负载统计                │   └──────────────────────────────────────────────┘
└──────────────────────────────────────┘            ^ 目标 = 边 dp0 的地址（非云本地；云不 bind）
┌──────────────────────────────────────┐        云服务器 B（IP_B，实例2）
│ EngineCore(dp1)：ROUTER actor（1 线程）│   ┌──────────────────────────────────────────────┐
│   bind tcp://*:PORTS[1]               │◄──┼─ IP_B 实例2.dp0   DEALER id="2" ────────────┤
│   （结构同 dp0，只服务各实例的 dp1）     │   │   connect tcp://master_addr:PORTS[0]          │
│   · ack -> dp1 负载统计                │   └──────────────────────────────────────────────┘
└──────────────────────────────────────┘   （IP_A 实例0.dp1/实例1.dp1 与 IP_B 实例2.dp1 同理
                                              connect PORTS[1]，id 分别 "0"/"1"/"2"）

  端口：边共 D 个显示值（PORTS = pre_out_ports 显式列表、不推导；随 D 增长、不随 N）；云不 bind 任何端口
  连接：N×D 条全双工 TCP，云 (i,dpX) connect 到 PORTS[dpX] 的边 dpX ROUTER，与配对边 dp 直连、无中继；
        DEALER 显式 IDENTITY 断线重连保持身份
  IDENTITY：每个 ROUTER 内 = instance_id（dp 已由端口区分）；同机共置（IP_A 上 4 个 DEALER）分属两组端口、
        每组 2 个 id，仍无需 instance 端口偏移与 IP 兜底（§2.2.2 / §3.7.1）
  跨 dp 汇聚：各 dp ROUTER 收到的 ack/负载统计经既有 inner-DP gloo 组（§3.4 all_reduce 同路）汇入 leader
        的 InstanceDispatcher，不新增通道
  消息：HELLO(id)/ACK(id) 云->边（ROUTER 收向自动带 id 帧，来源解复免费）；
        [id|SO] 边->云按 id 定向路由（MANDATORY：EAGAIN=慢实例留队重试不串台，EHOSTUNREACH=未就绪/失联）
  背压：per-id 队列深度进 InstanceLoadStats（§3.5），调度层绕开慢实例；transport 不丢、不全局阻塞
```


（线程/actor 内部结构、背压与 readiness 细节见 §3.7.2；socket 选型依据见 §3.7.1。）

### 2.3 边侧模式

| 模式 | edge KV | 边卡 | 说明 |
|------|---------|------|------|
| `embedding_only` | 无 | 1 卡 shared-model | 1 rank host D virtual，无 edge KV 免准入协调 |
| `head_tail` | per-dp_rank | 2 卡 | 有 KV 需准入（与控制面决策一致） |

多实例经 per-instance 通道扩展（两种模式同构，只是 virtual workers vs real ranks + 有无 edge KV），非退化情形、无需单独设计。

### 2.4 部署形态（边 2 卡，云 4 服务器 × 8 卡）

统一符号：N=实例数、D=每实例 dp、C=每 dp 云 tp、E=边 rank 数；云 rank 公式 `E+i·D·C+j·C`（实例 i、dp j）。

#### 形态一：四实例，dp=1（每实例单机 tp8，边 2 卡 tp2）

```
边侧服务器 (node_rank 0, 2卡)
┌──────────────────────────────┐
│ 边卡0 [rank0] ┐              │  E=2：D=1 -> 边侧 1 个 DP rank，
│ 边卡1 [rank1] ┘ 边内 TP=2    │  两卡做首/尾层张量并行
└──────────────────────────────┘
   │G2_0      │G2_1      │G2_2      │G2_3      <- 4 个 PP 子组（各 2+8 rank）
   ▼          ▼          ▼          ▼
┌─────────┐┌─────────┐┌─────────┐┌─────────┐
│云服务器1 ││云服务器2 ││云服务器3 ││云服务器4 │
│node_rank1││node_rank2││node_rank3││node_rank4│
│实例0     ││实例1     ││实例2     ││实例3     │
│rank 2-9  ││rank10-17 ││rank18-25 ││rank26-33 │
│dp1×tp8   ││dp1×tp8   ││dp1×tp8   ││dp1×tp8   │
└─────────┘└─────────┘└─────────┘└─────────┘
```

- 边侧 2 卡全部进每个 G2（tp2 整体是一个 PP stage，两 rank 都在全部 4 个 G2 内，跨实例时分复用）
- 配置：`--nnodes 5 --node-rank 0 --edge-npu-count 2 --cloud-npu-count 32`；云各服务器 `--node-rank 1..4`
- world = 2+32 = 34；每实例 2P1D 通道独立；**§2.1 推导规则适用**（N=4，instance_id=node_rank-1）
- 边内 TP=2 与云侧实例内 TP 无耦合（各切各的，hidden 按 G2 内边侧 TP 切分对齐）

#### 形态二：2 实例，dp=2，dp 云双机

```
边侧服务器 (node_rank 0, 2卡, per-rank 模式)
┌──────────────────────────────┐
│ 边卡0 [rank0, DP0]            │──服务所有实例的 dp0（时分复用）
│ 边卡1 [rank1, DP1]            │──服务所有实例的 dp1（时分复用）
└──────────────────────────────┘
   │ G2(0,dp0) G2(0,dp1)          │ G2(1,dp0) G2(1,dp1)
   ▼                              ▼
┌────────────────────────┐  ┌────────────────────────┐
│ 实例0 = 服务器1 + 服务器2 │  │ 实例1 = 服务器3 + 服务器4 │
│ 两机都是 node_rank 1    │  │ 两机都是 node_rank 2    │
│ 服务器1: dp0×tp4 (rank2-5)│  │ 服务器3: dp0×tp4(rank10-13)│
│   --data-parallel-start-  │  │   --data-parallel-start-  │
│    rank 0, local 1        │  │    rank 0, local 1        │
│ 服务器2: dp1×tp4 (rank6-9)│  │ 服务器4: dp1×tp4(rank14-17)│
│   --data-parallel-start-  │  │   --data-parallel-start-  │
│    rank 1, local 1        │  │    rank 1, local 1        │
│                        │  │                        │
│ 云双机 coord：dp0<->dp1 │  │ 同左（独立 gloo 组）     │
│ gloo 直连 master+201+i  │  │                        │
│ 边只做 IP broker        │  │                        │
└────────────────────────┘  └────────────────────────┘
```

- 配置：边 `--nnodes 3 --node-rank 0 --edge-npu-count 2 --cloud-npu-count 32`；云每机 `--nnodes 3 --node-rank 1或2 --data-parallel-size 2 --data-parallel-size-local 1 --data-parallel-start-rank 0/1`（同 1:1 云双机现状：双机不占额外 node-rank，靠 start-rank 区分）
- world = 18；G2 共 N×D=4 个（各 1+4 rank）；coord/IP-broker/gloo 端口全部 +instance 偏移（§2.2）
- **§2.1 推导规则适用**（N = 3-1 = 2，instance_id = node_rank-1；节点维度只数实例，物理机数 4 > nnodes 3）

#### 形态三：四实例，dp=2，dp 云单机

```
边侧服务器 (node_rank 0, 2卡, per-rank 模式)
┌──────────────────────────────┐
│ 边卡0 [rank0, DP0]            │──4 实例 × dp0 共 4 条流
│ 边卡1 [rank1, DP1]            │──4 实例 × dp1 共 4 条流
└──────────────────────────────┘
   │ 8 个 G2 子组：(实例i=0..3) × (dp0/dp1)，各 1+4 rank
   ▼          ▼          ▼          ▼
┌─────────┐┌─────────┐┌─────────┐┌─────────┐
│云服务器1 ││云服务器2 ││云服务器3 ││云服务器4 │
│node_rank1││node_rank2││node_rank3││node_rank4│
│实例0     ││实例1     ││实例2     ││实例3     │
│dp0: rank ││dp0: rank ││…         ││…         │
│  2-5(tp4)││ 10-13    ││          ││          │
│dp1: rank ││dp1: rank ││          ││          │
│  6-9(tp4)││ 14-17    ││          ││          │
│同机 coord││          ││          ││          │
└─────────┘└─────────┘└─────────┘└─────────┘
```

- 配置：`--nnodes 5 --node-rank 0 --edge-npu-count 2 --cloud-npu-count 32`；world = 34
- 每服务器内 dp0/dp1 同机（coord 走本机，无双机 IP broker 依赖）
- **§2.1 推导规则适用**（N=4，instance_id=node_rank-1），边 2 卡全部利用--三形态中边侧利用率与设计目标最贴合

#### 汇总对比

| 形态 | N | D | C | world | G2 数 | 边卡利用 | §2.1 推导 | 备注 |
|------|---|---|---|-------|-------|----------|-----------|------|
| 一：四实例 dp1 边 tp2 | 4 | 1 | 8 | 34 | 4（各 2+8） | 2/2 卡（边内 TP=2） | ✓ | 边两卡整体进全部 G2，跨实例时分复用 |
| 二：2实例 dp2 云双机 | 2 | 2 | 4 | 18 | 4 | 2/2 卡 | ✓（nnodes=3） | 双机不占 node-rank（dp start-rank 区分）；云双机 coord + IP broker per-instance |
| 三：四实例 dp2 云单机 | 4 | 2 | 4 | 34 | 8 | 2/2 卡 | ✓ | 同机 coord（dp local=2 同进程组）；边 2 卡 × 4 实例全时分复用 |

### 2.5 部署形态（边 1 卡，云 4 服务器 × 8 卡）

边 1 卡 = **shared-model 模式**（1 个 HCCL rank host D 个 virtual worker 共享 nn.Module；D=2 时 EP=1、tail = leader 1× 代算 2DP token，§5.3 结论适用）。云 rank 公式 `E+i·D·C+j·C`，E=1。

#### 形态一：四实例，dp=1（每实例单机 tp8，边单 rank）

```
边侧服务器 (node_rank 0, 1卡)
┌──────────────────────────────┐
│ 边卡0 [rank0] ── 唯一 DP rank │  E=1（D=1 无 virtual worker）
└──────────────────────────────┘
   │G2_0      │G2_1      │G2_2      │G2_3      <- 4 个 PP 子组（各 1+8 rank）
   ▼          ▼          ▼          ▼
┌─────────┐┌─────────┐┌─────────┐┌─────────┐
│云服务器1 ││云服务器2 ││云服务器3 ││云服务器4 │
│node_rank1││node_rank2││node_rank3││node_rank4│
│实例0     ││实例1     ││实例2     ││实例3     │
│rank 1-8  ││rank 9-16 ││rank17-24 ││rank25-32 │
│dp1×tp8   ││dp1×tp8   ││dp1×tp8   ││dp1×tp8   │
└─────────┘└─────────┘└─────────┘└─────────┘
```

- 配置：`--nnodes 5 --node-rank 0 --edge-npu-count 1 --cloud-npu-count 32`；云各服务器 `--node-rank 1..4`
- world = 1+32 = 33；**§2.1 推导规则适用**（N=4，instance_id=node_rank-1）
- D=1 时与 §2.4 形态一同构（边 1 rank，无 TP/无 virtual worker 差异）

#### 形态二：2 实例，dp=2，dp 云双机（边 1 卡 host 2 virtual worker）

```
边侧服务器 (node_rank 0, 1卡, shared-model)
┌──────────────────────────────┐
│ 边卡0 [rank0]                 │ host 2 个 virtual worker：
│   ├─ vworker0 (DP0)           │──服务所有实例的 dp0（时分复用）
│   └─ vworker1 (DP1)           │──服务所有实例的 dp1（时分复用）
│  EP=1；tail = leader 1× 代算   │
└──────────────────────────────┘
   │ G2_0 (按 dp 切 channel)       │ G2_1
   ▼                              ▼
┌────────────────────────┐  ┌────────────────────────┐
│ 实例0 = 服务器1 + 服务器2 │  │ 实例1 = 服务器3 + 服务器4 │
│ 两机都是 node_rank 1    │  │ 两机都是 node_rank 2    │
│ 服务器1: dp0×tp4 (rank1-4) │  │ 服务器3: dp0×tp4(rank9-12) │
│   --data-parallel-start-  │  │   --data-parallel-start-  │
│    rank 0, local 1        │  │    rank 0, local 1        │
│ 服务器2: dp1×tp4 (rank5-8) │  │ 服务器4: dp1×tp4(rank13-16)│
│   --data-parallel-start-  │  │   --data-parallel-start-  │
│    rank 1, local 1        │  │    rank 1, local 1        │
│                        │  │                        │
│ 云双机 coord：dp0<->dp1 │  │ 同左（独立 gloo 组）     │
│ gloo 直连 master+201+i  │  │                        │
│ 边只做 IP broker        │  │                        │
└────────────────────────┘  └────────────────────────┘
```

- 配置：边 `--nnodes 3 --node-rank 0 --edge-npu-count 1 --cloud-npu-count 32`；云每机 `--nnodes 3 --node-rank 1或2 --data-parallel-size 2 --data-parallel-size-local 1 --data-parallel-start-rank 0/1`（同 1:1 云双机现状）
- world = 1+16 = 17；G2 共 N=2 个（shared-model 每实例一个 `{0}∪实例i云rank`，size 1+8，按 dp 切 channel）
- 边内 2 DP 在 1 进程内，**2DP 协调在 EngineCore gloo 层**（G1：D 个 EngineCore，边 HCCL rank 仅 1 个）
- **§2.1 推导规则适用**（N = 3-1 = 2，instance_id = node_rank-1；节点维度只数实例，物理机数 4 > nnodes 3）

#### 形态三：四实例，dp=2，dp 云单机（边 1 卡 host 2 virtual worker）

```
边侧服务器 (node_rank 0, 1卡, shared-model)
┌──────────────────────────────┐
│ 边卡0 [rank0]                 │ host 2 个 virtual worker：
│   ├─ vworker0 (DP0)           │──4 实例 × dp0 共 4 条流
│   └─ vworker1 (DP1)           │──4 实例 × dp1 共 4 条流
│  EP=1；tail = leader 1× 代算   │
└──────────────────────────────┘
   │ 4 个 G2 子组（每实例一个，按 dp 切 channel，各 1+8 rank）
   ▼          ▼          ▼          ▼
┌─────────┐┌─────────┐┌─────────┐┌─────────┐
│云服务器1 ││云服务器2 ││云服务器3 ││云服务器4 │
│node_rank1││node_rank2││node_rank3││node_rank4│
│实例0     ││实例1     ││实例2     ││实例3     │
│dp0: rank ││dp0: rank ││…         ││…         │
│  1-4(tp4)││  9-12    ││          ││          │
│dp1: rank ││dp1: rank ││          ││          │
│  5-8(tp4)││ 13-16    ││          ││          │
│同机 coord││          ││          ││          │
└─────────┘└─────────┘└─────────┘└─────────┘
```

- 配置：`--nnodes 5 --node-rank 0 --edge-npu-count 1 --cloud-npu-count 32`；world = 1+32 = 33
- 每服务器内 dp0/dp1 同机（coord 走本机，无双机 IP broker 依赖）
- **§2.1 推导规则适用**；边 1 卡 × 4 实例全时分复用，是边侧算力最紧张、多实例重叠收益最大的形态

#### 汇总对比

| 形态 | N | D | C | world | G2 数 | 边模式 | §2.1 推导 | 备注 |
|------|---|---|---|-------|-------|--------|-----------|------|
| 一：四实例 dp1 | 4 | 1 | 8 | 33 | 4（各 1+8） | 单 rank（无 virtual） | ✓ | 与 §2.4 形态一同构 |
| 二：2实例 dp2 云双机 | 2 | 2 | 4 | 17 | 2 | shared-model（2 vworker，EP=1） | ✓（nnodes=3） | 双机不占 node-rank（dp start-rank 区分）；云双机 coord + IP broker per-instance |
| 三：四实例 dp2 云单机 | 4 | 2 | 4 | 33 | 4 | shared-model（2 vworker，EP=1） | ✓ | 同机 coord；边 1 卡 × 4 实例全时分复用 |

与 §2.4（边 2 卡）的核心差异：E=2/TP2 或 per-rank 双 rank -> E=1 单 rank；G2 从「边全部 rank 进每实例」变为「边 1 rank 进每实例」（形态二/三 G2 数从 N×D 降为 N，dp 维度在 channel 切分层消化）；形态二/三的边侧 tail 无跨 2DP EP all-toall（EP=1，leader 代算），worker 层异步重叠约束更宽松（§5.3）。

### 2.6 部署形态（边 2 卡，云 2 服务器 × 16 卡，dp=1）--含每服务器多实例（2026-08 起为必选场景）

dp=1、边 2 卡做边内 TP=2（同 §2.4 形态一模式），E=2，world 均为 2+32 = 34。

#### 形态一：2 实例（每服务器 1 实例，tp16）--标准形态，完全支持

```
边侧服务器 (node_rank 0, 2卡)
┌──────────────────────────────┐
│ 边卡0 [rank0] ┐              │
│ 边卡1 [rank1] ┘ 边内 TP=2    │
└──────────────────────────────┘
   │G2_0                 │G2_1            <- 2 个 PP 子组（各 2+16 rank）
   ▼                     ▼
┌───────────────────┐  ┌───────────────────┐
│云服务器1 (16卡)     │  │云服务器2 (16卡)     │
│node_rank 1         │  │node_rank 2         │
│实例0               │  │实例1               │
│rank 2-17           │  │rank 18-33          │
│dp1×tp16            │  │dp1×tp16            │
└───────────────────┘  └───────────────────┘
```

- 配置：`--nnodes 3 --node-rank 0 --edge-npu-count 2 --cloud-npu-count 32`；云各服务器 `--node-rank 1/2`
- **§2.1 推导规则适用**（N=3-1=2）；与 §2.4 形态一完全同构（只是 C=8->16），无新增项，**v1 支持**

#### 形态二：4 实例（每服务器 2 实例，tp8）--每服务器多实例，v1 支持（2026-08 升级）

```
边侧服务器 (node_rank 0, 2卡)
┌──────────────────────────────┐
│ 边卡0 [rank0] ┐ 边内 TP=2     │
│ 边卡1 [rank1] ┘               │
└──────────────────────────────┘
   │G2_0   │G2_1     │G2_2   │G2_3        <- 4 个 PP 子组（各 2+8 rank）
   ▼       ▼         ▼       ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│云服务器1 (16卡)           │  │云服务器2 (16卡)           │
│ 实例0: 卡0-7,  tp8        │  │ 实例2: 卡0-7,  tp8        │
│   node_rank 1, rank 2-9   │  │   node_rank 3, rank18-25  │
│   VISIBLE_DEVICES=0-7     │  │   VISIBLE_DEVICES=0-7     │
│ 实例1: 卡8-15, tp8        │  │ 实例3: 卡8-15, tp8        │
│   node_rank 2, rank10-17  │  │   node_rank 4, rank26-33  │
│   VISIBLE_DEVICES=8-15    │  │   VISIBLE_DEVICES=8-15    │
│ （同机 2 实例，卡静态划分，  │  │                          │
│   各自独立拉起）           │  │                          │
└──────────────────────────┘  └──────────────────────────┘
```

- **实例编码 = node_rank 即逻辑实例**（§2.1 新增规则）：同一物理服务器上 2 个实例各自独立拉起，node_rank 1/2（服务器1）与 3/4（服务器2）；`instance_id = node_rank-1`、`N = nnodes-1 = 4` 推导规则**零改动成立**
- 卡静态划分：实例0 用卡 0-7、实例1 用卡 8-15（`ASCEND_RT_VISIBLE_DEVICES` 切片），不共卡
- world = 34；nnodes=5 数「边 + 4 个逻辑节点」（物理机 3 台 < nnodes 5，节点维度=实例维度在两个方向上成立：一实例跨多机不占额外交 rank、一机多实例各占一个 node_rank）

#### 形态二支持项 / 新增处理项分析（2026-08 更新：v1 支持）

**支持项（逻辑设计天然兼容，共置不引入正确性问题）**：

| # | 项 | 依据 |
|---|----|------|
| 1 | group 派生（G0-G5）按 rank 区间切分，共置无影响 | §4.2 是逻辑 rank 划分，与物理位置无关 |
| 2 | 实例间松耦合：无集合通信跨实例，同机共置无正确性影响 | §3.2/§8 实例间无协调/无 barrier |
| 3 | 数据面 G2 / hidden channel / 2P1D per-instance 隔离 | §4.3/§4.4 per-instance 子组+池，逻辑隔离 |
| 4 | 调度 / KV 分区 / prefill_inflight per-(instance,dp) 独立 | §3.1/§6.1/§6.4 与物理位置无关 |
| 5 | NPU 算力/显存无竞争（**前提：卡按实例静态划分**，实例0 卡0-7、实例1 卡8-15，不共卡） | profile/KV 分配各自 8 卡 |
| 6 | ZMQ 控制面 per-instance channel 可同机共存（端口偏移后） | §2.2/§3.7 |
| 7 | **实例配置推导成立（原硬缺口 #1 已消解）** | §2.1 新增「一物理机多逻辑 node-rank」：同机实例各自独立拉起、node_rank 即 instance_id，推导规则零改 |

**新增处理项（v1 必做，原「不支持项」）**：

| # | 项 | 性质 | 说明 |
|---|----|------|------|
| ~~1~~ | ~~配置推导破坏~~ | 已消解 | 原「node_rank 数服务器不数实例」缺口由 §2.1 逻辑 node-rank 规则消解：无需恢复 `--cloud-instance-num` / 显式 instance-id，同机实例 = 不同 node-rank 独立拉起 + 卡切片。遗留：拉起脚本/编排器须支持一机多实例拉起（node_rank->物理机映射由部署侧维护，不进 vllm 配置面） |
| 2 | **同机端口/store 偏移（硬前提，必做）** | 拉起失败 | 跨服务器同端口可靠 IP 区分，**同服务器同 IP 必撞**：§2.2 全通道 instance 偏移 + 拉起期端口规则校验（强制）；cloud_ip key/port 双维度带 instance（passive_core.py:1017-1028） |
| 3 | **host 资源竞争（K=4 时量化）** | 性能 | 同机 K 个实例：模型权重加载 ×K（qwen3.6-27b 2 卡实例权重 host RAM ×4）、worker 进程/线程 ×4、CPU 竞争；**边↔云网络出口共享**（4 实例 hidden isend/irecv + ZMQ 控制面挤同一网口）-> 数据面带宽评估口径从 per-instance 改 **per-server 聚合**：每服务器聚合带宽须 ≥ 4×单实例 hidden 流量，否则多实例重叠收益被带宽竞争吃掉（千兆/万兆口下 qwen3.6-27b 4 实例聚合是带宽评估重点，实现期实测） |
| 4 | **相关性故障（故障域=服务器）** | 可用性 | 一服务器挂 = 该机 K 实例**同时**挂：N=8（2 服务器 × 4 实例）实际只有 2 个故障域，一机挂即半数实例挂 -> v1「任一实例挂=整体挂」下整体挂；可用性 = 服务器级可用性，多实例不增加故障点也不分散。逃生手段（§1.4 遗留）：v1 无 failover，实例级故障定位需先区分「单实例挂（进程级）」vs「整机挂（K 实例齐挂）」--后者恢复=整服务器重拉 |
| 5 | **启动竞争** | 启动时长 | 同机 K 实例同时权重加载/profile_run/warmup（CPU/内存带宽/网口竞争），启动变慢甚至超时。处理：**同机实例错峰拉起**（编排层：实例 i 延后 i×错峰间隔，或权重加载完成后再放行下一实例）+ §3.10 逐实例串行握手；代价 = 启动时长 ∝ 同机实例数（K=4 时约 4× 单实例关键路径，可部分并行：权重加载与上一实例 profile 重叠） |
| 6 | **运维/观测混淆** | 可用性 | 同机日志、进程命名、metrics **强制带 instance 标签**（instance_id 进日志前缀/进程 title/metrics label），否则同机 K 实例输出无法区分；拉起脚本进程命名建议 `vllm-cloud-inst{i}` |

**结论（2026-08 更新）**：形态一（每服务器 1 实例）与形态二（每服务器多实例）**均 v1 支持**。原硬缺口 #1（配置推导）由 §2.1「node_rank = 逻辑实例」消解，零新增配置项；剩余必做项 = #2 同机端口偏移强制校验（§2.2）、#5 启动错峰（§3.10）、#6 instance 标签强制；#3 带宽（per-server 聚合口径）与 #4 故障域（=服务器）为评估/运维口径变更，非功能缺口。卡静态划分（不共卡）仍是前提，共卡（实例间分时复用同卡）不在考虑范围。

#### 形态三：qwen3.6-27b 典型形态（边 2 卡 + 8 卡服务器 × 4 实例 tp2，2026-08 新增）

qwen3.6-27b 计算基线 2 卡 -> 云实例 = 2 卡 tp2，8 卡 A2 推理服务器部署 4 实例。

```
边侧服务器 (node_rank 0, 2卡)
┌──────────────────────────────┐
│ 边卡0 [rank0] ┐ 边内 TP=2     │
│ 边卡1 [rank1] ┘               │
└──────────────────────────────┘
   │G2_0  │G2_1  │G2_2  │G2_3      <- 4 个 PP 子组（各 2+2 rank）
   ▼      ▼      ▼      ▼
┌──────────────────────────────┐
│云服务器A (8卡, 4 实例)         │
│ 实例0: 卡0-1,  node_rank 1    │
│   rank 2-3,  VISIBLE=0,1     │
│ 实例1: 卡2-3,  node_rank 2    │
│   rank 4-5,  VISIBLE=2,3     │
│ 实例2: 卡4-5,  node_rank 3    │
│   rank 6-7,  VISIBLE=4,5     │
│ 实例3: 卡6-7,  node_rank 4    │
│   rank 8-9,  VISIBLE=6,7     │
│ （同机 4 实例，卡静态划分，     │
│   各自独立拉起+错峰启动）      │
└──────────────────────────────┘
```

- 配置：边 `--nnodes 5 --node-rank 0 --edge-npu-count 2 --cloud-npu-count 8`；云服务器A 上 4 实例分别 `--node-rank 1..4` + 各自 `ASCEND_RT_VISIBLE_DEVICES` 切片（§2.1 同机多实例拉起示例）
- world = 2+8 = 10；G2 共 4 个（各 2+2 rank，边 2 卡整体进全部 G2）
- 扩展到 2 台 8 卡服务器：N=8、world=18、nnodes=9（物理机 3 台）；**N=8 进入容量临界区**（edge/N ÷ cloud ≈ 1.02×，§6.3），边侧资源扩展为前置条件
- 该形态是 qwen3.6-27b 的**默认部署形态**：形态二（16 卡 × 2×tp8）退居非典型；§2.6 全部同机多实例结论（支持项 7 条 / 处理项 5 条）对本形态同等适用，K=4 使 #3 host 竞争、#5 启动错峰的影响翻倍（4 实例权重加载 ×4、启动关键路径 ∝4）

#### 汇总对比（§2.6）

| 形态 | N | 每服务器实例 | C | world | 物理机数 | 边卡利用 | §2.1 推导 | 备注 |
|------|---|------------|---|-------|---------|----------|-----------|------|
| 一：2实例 tp16 | 2 | 1 | 16 | 34 | 3 | 2/2 卡 | ✓ | 标准形态，零新增 |
| 二：4实例 tp8 | 4 | 2 | 8 | 34 | 3 | 2/2 卡 | ✓（一机多 node-rank） | 同机多实例，v1 支持 |
| 三a：4实例(1服务器) tp2 | 4 | 4 | 2 | 10 | 2 | 2/2 卡 | ✓（一机多 node-rank） | qwen3.6-27b 单服务器形态；同机压力最大（K=4） |
| 三b：8实例(2服务器) tp2 | 8 | 4 | 2 | 18 | 3 | 2/2 卡 | ✓（一机多 node-rank） | qwen3.6-27b 中间形态；N=8 容量临界（§6.3） |
| 三c：16实例(4服务器) tp2 | 16 | 4 | 2 | 34 | 5 | 2/2 卡 | ✓（一机多 node-rank） | **N 上限满配形态**；翻转 edge-bound（云利用率 ~51%，§6.3），边侧资源扩展为硬前置 |

---

## 3 控制面方案

### 3.1 队列结构：per-instance 队列（方案 A）

N 实例 × D DP-rank = **N×D 个 per-DP-rank 调度器**（`PDSeparatedScheduler`），按实例分组。每个 (instance,dp) scheduler 各持一个 `HiddenChannelManager`（天然 per-(instance,dp) 隔离）。

```
边侧 EngineCore 进程 (D 个，每 DP rank 一个)
├─ instance 0 scheduler × D  (PDSeparatedScheduler)
├─ instance 1 scheduler × D
└─ ...
    instance N-1 scheduler × D
```

### 3.2 两级结构

| 层 | 耦合 | 协调 | 集合通信 |
|----|------|------|----------|
| 实例间（N） | 松耦合 | 无协调 / 无 barrier | 无 |
| 实例内（D） | 紧耦合 | 现有跨 DP batch_type 协调 + barrier-drain 尾层 | 有（EP all-toall 配对） |

- 实例间尾层按 isend 到达逐实例处理（不 barrier）
- **内 barrier + 外 as-arrived 叠加**

### 3.3 请求路由：两级层级分发

两级层级分发（实例 -> DP）：
- **内层**：复用现有 DP 前端分发 + `balance_gather`
- **外层**：实例间负载走 publish-to-front-end（不引入集合通信）

可插拔 `InstanceDispatcher` 策略接口，默认 least-loaded，prefix-aware v1 不做。请求 pinning 后，draft/prefill/MTP/decode 全跟随（不只 decode）。

### 3.4 实例调度分层（方案 c，已选）

实例决策由 **leader（dp0 EngineCore 进程，调度层）的独立状态感知策略接口**（`InstanceDispatcher`，可插拔）做：

- **仅 leader 提议 instance_id**，all_reduce 作分发通道
- payload = `instance_id[leader 提议] + batch_type[2 DP 各提议]`（方案 c 带 instance_id，但仅 leader 提议）
- follower（dp1）收 leader 的 instance_id 并跟随
- batch_type 仍 2 DP 协调（现有 winner 规则不变），winner bt 应用到 leader 选的 instance
- **不另建 per-step 下发通道**（避免新通道代价），all_reduce 借作分发
- 一致性 = 单点决策（leader）无分歧 + all_reduce 分发保一致
- leader(dp0) 挂 = 整体挂（v1 故障模型，无 failover）

**作用域**：
- `InstanceDispatcher` 决策 **HEAD（FIRST）batch 喂哪个实例**
- **TAIL（LAST）batch 的实例 = HEAD 下发时已 pin 的 instance**（edge 自投递 TAIL 的 SO，不依赖云返回；`depends_on={COMM_RECV(c2e)}`）。「as-arrived」性质保留：TAIL 处理顺序由「recv fence 完成」驱动，仍是云返回到达序，只是从控制面（POST_OUT）换成数据面（recv 完成）；2DP lockstep = edge 2DP 各自 `COMM_RECV` 的 fence 都 ready

> **2026-08 定案**：TAIL 自投递 + recv fence **采纳**（上文 as-arrived 换驱动源的描述即为落地目标）；**POST_OUT 通道保留**（原"通道删除"提案关闭）--`_maybe_publish_post_out` 的 PL/DL SO 回传取消，剩余载荷 = `_drain_worker_completion_acks` 一族完成 ack 控制信号（云 worker 推理完成 + isend 已发起；明细落地时定）。通道形态（b 共用 PRE_OUT 的 ROUTER/DEALER / c 独立）见 §3.7.1。

子点（v1）：bt 提议 scope 用 dummy 兜底（leader 策略挑两 DP 都有工作的实例最小化 dummy）；精化（两阶段 all_reduce / leader 连 bt 一起决策）留作后续。

### 3.5 负载统计：InstanceLoadStats

`InstanceLoadStats` 富结构：running / waiting / cloud_kv_headroom / edge_kv_headroom / prefill·decode·mtp 队列深度。

**关键纠正**：边侧是 **D 个 EngineCore/executor 进程**（每 DP rank 一个，`shared_model_multiproc_executor.py` "one edge executor process per DP rank"），不是 1 进程。"shared-model 1 进程"指 `SharedModelWorkerProc`（worker，1 进程 host D virtual 共享 nn.Module），EngineCore 是 D 个。

- `InstanceDispatcher`(leader dp0) **不是本地读所有 scheduler**——只有自己的 N 个，需实例内 D 聚合
- **跨 D EngineCore all_gather** 聚合成一份（count 求和、headroom 取 min）
- 前端发布 = 复用 `DPEngineCoreProc._maybe_publish_request_counts`（core.py，每 DP EngineCore per-step 发 SchedulerStats 到 output_queue(-1=前端)，if has_coordinator and not external_lb），扩 instance_id，前端聚合 N×D -> N 选实例 pin
- v1：leader 用自己 N scheduler + balance_gather per-instance running 轮转/least-loaded；前端每 DP 发 running/waiting 选实例 pin
- 后续：富结构 InstanceLoadStats + 云 passive 上报 cloud_kv 到边侧 leader（云 passive 现只 publish hidden tensor 无负载上报，最大改动）

<!-- 
### 3.6 balance_gather 前提（致命约束已核实）

`enable_balance_scheduling` 是现有 additional_config 项。**边云不能直接开**：

- 开它 -> `BalanceDPEngineCoreProc`，其 `run_busy_loop` not-executed 分支**缺 `_is_coordinated_dp` 适配**——直接 `execute_dummy_batch` -> **coord 模式 self-drive dummy -> count-drift 死锁（致命）**

**替代方案（推荐 b）**：不引入 `BalanceDPEngineCoreProc`，在边云已 coord 适配的 `DPEngineCoreProc.run_busy_loop` **直接加一行 balance_gather**（复用已适配 run_busy_loop 避开 dummy 死锁，每步多 1 all_gather 与 coord all_reduce 不同信息 1:1 对齐可共存）。

部署配置：
- `has_coordinator`（internal LB，派生非配置项：dp>1 + MoE/非external_lb，边云 MoE dp2 默认自动 True）使 `_maybe_publish_request_counts` 发前端
- balance_gather 经方案 (b) 在边云 run_busy_loop 直接加（**非开 enable_balance_scheduling**）
-->

### 3.7 ZMQ 收发线程：方案 1（沿用 per-channel）

现有每个 `PPSchedulerZmqChannel` 自带 2 个后台线程（`_publisher_thread` pickle+send，`_subscriber_thread` poll+recv+unpickle）；`publish()` 是 `put_nowait` 非阻塞、`consume_new_outputs()` 非阻塞 list-swap，scheduler 线程从不阻塞在 ZMQ 上。

多实例直接实例化 N×D 个 channel = 2×N×D 个 I/O-wait 后台线程，小 N×D 下可接受、per-channel 隔离、零重构。端口编码扩为 `+ (instance*D + dp_rank)*2`。

**ZMQ 端口数结论（2026-08 核实）**：现状每 dp_rank 占 2 端口（PRE_OUT + POST_OUT 一对，PUSH/PULL 单向 socket 一方向一端口，`{pre/post}_out_port + dp_rank*2` 成对分配，patch_engine_core.py:181-194 / passive_core.py:1037-1045 云侧镜像）。**不做 socket 层合并**（ZMQ PAIR 单端口双向需重构线程模型--socket 非线程安全，pub/sub 双线程须并成单 poller；CLIENT/SERVER 有每 peer 在飞限制，不适配流式下发），而是**若 §3.4 的 POST_OUT 删除提案定案**：TAIL 自投递后云->边控制面回传整条删除，每 (instance,dp) 收敛为 **PRE_OUT 单端口**，编码从 `+ (instance*D+dp)*2`（步长 2）变 `+ (instance*D+dp)`（步长 1）--N=16、D=2 满配下 62 -> 31 端口，master_port 偏移空间压力减半。**POST_OUT 删除当前待定（未定案前维持 2 端口/对）**，删除的连带收益与代价见 §2.2.2。

**N 扩到 8/16 的线程/host 评估（2026-08 补）**：边侧 2×N×D 线程（N=8、D=2 -> 32 个，I/O-wait 型，CPU 占用低，仍可接受）；同机共置下云侧一台服务器 K 个 executor 各自带线程/进程（K=4 时 4 套 PassiveEC+executor+worker 进程树），host 进程数与 CPU 竞争见 §2.6 处理项 #3/#5。

**（已被 §3.7.1/§3.7.2 形态 b 取代，2026-08）**旧结论（send 不宜压成一路：PUSH 满阻塞、慢云堵全部）不再成立：ROUTER send NOBLOCK + per-identity 队列使 EAGAIN 只滞留该实例队列、不阻塞 actor、不串台；每 dp 一 actor + per-identity 有界队列即终态，线程模型见 §3.7.2。

### 3.7.1 PRE_OUT 单端口多云（2026-08 部署要求，已定）

**部署要求（两条，均已定）**：(1) pre_out_port / post_out_port **显示配置、无默认值**（缺失 fail-fast，拉起期校验 bind 可用性）；(2) 边侧端口配置**不随实例数 N 增长**（2026-08 修订：初版"只配一个"作废），**按 dp 显式配置、不做规则推导**：`pre_out_ports = [p0..p_{D-1}]`（按 dp_rank 序的显示列表，边云共享、必填无默认、长度=D、值唯一，dp=4 即 4 个显示值）；边 dpX bind `p_X`，云 (instance,dpX) connect `master_addr:p_X`，边仍**定向**给各实例发 scheduler_output。

**现状**：边 PUSH bind `tcp://*:{pre_out_port + dp_rank*2}`（N×D 个 bind 端口）、云 PULL connect（passive_core.py:1037-1050 云侧、patch_engine_core.py:181-194 边侧镜像）；TCP 连接方向本就是云 -> 边，本变更只是把 N×D 个 bind 收敛为 1 个，**关键在单 bind 多 peer 后 ZMQ 分发语义必须重选**。

**socket 选型（三选一，结论 = C）**：

| 方案 | 单 bind 多 peer 语义 | 定向性 | 背压/可靠性 | 结论 |
|------|--------------------|--------|------------|------|
| A. PUSH/PULL 维持现状类型 | 逐消息**轮询负载均衡**（fair-queue，跳过 HWM 满的 pipe），每条消息发恰好一个 peer、由 ZMQ 选中 | **无**：调度器对实例的指派失效（给实例 0 的 batch 可能落到实例 3），与 per-instance batch/recv fence/KV 亲和正面冲突 | HWM 满跳过不阻塞；但定向性丢失 | **否决**（除非调度模型改"实例池化、消息自包含、任意实例可执行"，属调度架构重写） |
| B. PUB/SUB（云 SUB 按 instance 订阅前缀） | publisher 侧 per-pipe 订阅过滤，不匹配不写入该 pipe，**带宽不放大** | 有（topic 定向） | **PUB mute 静默丢弃**（慢实例 HWM 满即丢 scheduler_output -> 请求黑洞），须 app 层确认+重传 | **否决**（违反 §3.7 "scheduler_output 不能丢"） |
| C. **ROUTER/DEALER** | 边 ROUTER bind 单端口，云 DEALER connect（TCP 方向不变） | **精确**：`send_multipart([identity, payload])`，identity = `instance*D+dp_rank`（DEALER 显式 identity 或连接后注册帧建路由表） | `ZMQ_ROUTER_MANDATORY`：对端不可达/HWM 满 send 报 **EAGAIN 不静默丢**，边侧对该实例队列阻塞/重试 = **per-instance 独立背压**，慢实例只堵自己不串台 | **推荐/采纳** |

**C 方案落地点**：

- 云侧：PULL -> DEALER + connect 地址变单端口；DEALER 收到的消息 identity 帧被剥掉，payload 格式与现状一致（消息面无感）；**线程面须改单 actor**（§3.7.2）
- 边侧：PUSH -> ROUTER（**每 dp 一个**，bind 各自显式配置的 `pre_out_ports[dp_rank]`，§3.7.2）；注册/心跳 recv + scheduler_output send 共用一个 socket，**非线程安全 -> 每 dp 一个 actor 线程**；per-instance pickle 可保留并行，actor 内 send NOBLOCK + EAGAIN 重试
- readiness：现状 `IMMEDIATE=1 + wait_until_ready` 换成"注册帧确认"（实例就位 = 边路由表收到该 identity），与 G0 启动 barrier（§2.1/§3.10）衔接
- 重连：DEALER 显式 identity 断线重连保持同一路由（ROUTER 重关联 pipe）；**边重启则路由表清空**，靠注册帧重建；mandatory 下 unroutable 报错细节（EAGAIN vs EHOSTUNREACH）实现期核实
- 连带收益：边侧 PRE_OUT 从 2×N×D 端口/线程收敛为 1 端口 + 1 actor（§3.7 线程结论同步改写）；同机共置下 PRE_OUT 云侧只 connect 不 bind，**该通道的端口偏移前提整条消解**（§2.2）

**POST_OUT 对等约束（2026-08 定案）**：§3.4 **TAIL 自投递 + recv fence 采纳、POST_OUT 通道保留**（原删除提案关闭），**通道形态已定 b（共用 PRE_OUT 的 ROUTER/DEALER 双向 socket，下表保留作选型依据记录）**。TAIL SO 回传改边自投递后，POST_OUT 剩余载荷 = 完成 ack 类控制信号（云 worker 推理完成 + isend 已发起，`_drain_worker_completion_acks` 一族；轻流量，明细 §3.4 落地时定）。方向 = N 云 -> 1 边多对一汇聚。

| 候选 | 形态 | 端口 | 要点 |
|------|------|------|------|
| b. **共用 PRE_OUT 的 ROUTER/DEALER（双向，推荐）** | ROUTER/DEALER 全双工异步对：DEALER 同一连接上收（PRE_OUT）+ 发（POST_OUT ack），ROUTER 收到的消息自动带 [identity/payload] 帧，边的来源解复免费解决（汇聚方向无需任何解复头） | **1（两方向合计）** | 剩余载荷轻（ack 类）恰好适配搭便车；TCP 全双工 + ZMQ 每 pipe 收发独立 = 方向级流控独立（云慢收不堵云发、边慢收只反压云发送方向）；**代价：云侧线程模型也要改**（现状 PUSH/PULL 两 socket 两线程 -> 单 DEALER 非线程安全，云侧也须单 actor/加锁，上文"云侧近乎无感"在此形态下不成立）；两侧 actor 循环 recv 先排干、send NOBLOCK+EAGAIN 重试；断线/重连/drain 双流耦合；**cloud_ip store 连带删除 + post_out_port 配置项整个取消**（云不 bind 任何端口、边不需知云 IP） |
| c. 独立通道 | 第二对 socket：PUSH(云 connect)/PULL(边 bind) 单端口多对一汇聚（无路由问题，消息带 (instance,dp) 头解复），或维持 per-(instance,dp) | 1+1 或 1+N×D | 现状 bind/connect 方向反转（现状 = 云 bind POST_OUT、边 connect，靠 cloud_ip store 发现端点，passive_core.py:1006-1029）；反转后边不需知云 IP，cloud_ip store 同样可删；云侧线程模型维持现状（收发仍两 socket） |

**已选 b（2026-08 定案）**：POST_OUT 收敛为轻量 ack 后，独立通道的隔离收益（独立 HWM / 独立 teardown）小于 b 的端口+配置+发现三重收益；b 的主要代价（云侧 actor 改造）与边侧改造同构，边际成本低。收发线程模型（单实例/多实例）见 §3.7.2。

### 3.7.2 形态 b 收发线程模型（2026-08 定案；修订：边侧 per-dp ROUTER，取消 leader fan-in）

**修订记录**：初版为"边侧单 bind 端口归 leader + follower localhost/IPC 转发"；定稿改为**每 dp_rank EngineCore 进程各 bind 各的 ROUTER（端口按 dp 规则推导）**--部署要求同步修订为"端口配置不随实例数 N 增长，允许按 dp 推导不同端口"。收益：消除 fan-in 与 leader 收发单点，边云两侧结构完全对称，dp=4 直接扩展（4 actor / 4 端口），无内层 hop。

现状基线：每 `PPSchedulerZmqChannel` = 1 pub 线程（pickle + PUSH send，`queue.Queue(1000)` + `put_nowait`）+ 1 sub 线程（poll + recv + unpickle），`publish()`/`consume_new_outputs()` 均非阻塞，调度线程从不阻塞在 ZMQ 上（passive_core.py:124-228）；边侧每个 dp_rank EngineCore 进程各 bind 各的端口（`pre_out_port+dp*2`，patch_engine_core.py:186-192）。

**云侧（单实例与多实例同构，每 (instance,dp) 一个 PassiveEC 进程）**：

- 现状 2 线程（pub: POST_OUT PUSH bind / sub: PRE_OUT PULL connect）-> **1 actor 线程 + 单 DEALER**（`IDENTITY = instance_id`，connect 目标 = `master_addr:{pre_out_ports[dp_rank]}`，端口取自显式配置列表的本 dp 项）
- actor 循环：poll -> **recv 先排干**（scheduler_output 入 inbox，`consume_new_outputs` 语义不变）-> out 队列排干 send **NOBLOCK**（首帧 HELLO，运行期完成 ack；EAGAIN 留队重试）
- ack 生产（`_drain_worker_completion_acks` 一族，TAIL 自投递后 POST_OUT 剩余载荷）在 PassiveEC 主循环 put_nowait，与现状 publish() 调用点同构
- 多实例 = 每实例重复，进程间无共享无协调；线程总量 **2×N×D -> N×D**（N=16/D=2：64 -> 32，摊在 4 台服务器）

**边侧（per-dp ROUTER，与云侧结构对称）**：

- **每 dp_rank EngineCore 进程各 1 个 ROUTER actor（1 线程）**：bind `tcp://*:{pre_out_ports[dp_rank]}`，**只服务本 dp 的 N 个实例**；端口为**显式配置**（`pre_out_ports` 列表按 dp_rank 序，不做 base+dp 推导；显示、必填、无默认、长度=D、值唯一），D=4 即 4 个显示值
- **IDENTITY = instance_id**（dp 已由端口区分，identity 无需再编码 dp；跨 socket 的 (dp, instance) 二元组全局唯一，日志/监控用二元组）
- 每 dp 的 actor：recv 排干（HELLO -> 本 dp readiness 表（N 个 id）/ ack -> 本 dp 负载统计）+ **per-identity out 队列**发送（NOBLOCK/MANDATORY：EAGAIN = 慢实例留队重试；EHOSTUNREACH = 未就绪入队等待 / 已就绪后失联 = v1 故障模型整体挂，fail-fast）
- **跨 dp 汇聚走既有通道**：dp>1 时各 dp 的 ack/负载统计经现有 inner-DP gloo 组（与 §3.4 实例分发的 all_reduce 同路）汇入 leader 的 `InstanceDispatcher`，**不新增通道、无 IPC 转发 hop**
- 线程数：现状 2×N×D -> **D（每 dp 1 actor）**；N=16/D=2：64 -> 2；D=4：64 -> 4
- **配置校验（拉起期 fail-fast）**：列表长度 = D、值唯一、端口可用（被占且非本 dp 显式端口 = 拒绝拉起，防同机串台）；边云列表一致性由人为保证（§2.1 既定口径）；master_port 偏移空间预留等推导类约束对本通道不再适用
- pickle 按 dp 分散（每 actor 各自序列化，无单点）；leader 无收发依赖（只消费汇聚后的负载统计）

**运行时路径（dp=2 示例，全部直连、无中继）**：

```
边->云（SO）：          边 dpX --TCP:{pre_out_ports[X]}--> 云 (i, dpX)   每 dp 与配对实例直连
云->边（HELLO/ack）：   云 (i, dpX) --TCP:{pre_out_ports[X]}--> 边 dpX 的 ROUTER
数据面（hidden/KV）：   边 dpX worker <--HCCL isend/irecv--> 云 (i, dpX) workers   不经 ZMQ、不经 dp0
```

**背压（修订 §3.7 旧结论）**：

- 旧（send 不宜压成一路：PUSH 满阻塞、慢云堵全部）**不成立**：ROUTER send NOBLOCK，EAGAIN 只滞留该 identity 队列，actor 不阻塞、其他实例不受影响
- per-identity 有界队列（沿用 1000 量级）深度进 `InstanceLoadStats`（§3.5，经 inner-DP 汇聚），过载防线 = 调度层绕开慢实例（transport 不丢、不全局阻塞）；队列满 = 高水位告警而非丢
- 旧 per-channel `queue.Queue(1000)` 的隔离性由 per-identity 队列等价继承

**readiness / 重连 / 顺序**：

- HELLO 帧替代 `IMMEDIATE=1 + wait_until_ready`；每个 dp 的 ROUTER 各自等 N 个 HELLO，全局仍由 G0 barrier 保证（N×D 全就位才放行调度，§3.10）
- DEALER 显式 IDENTITY 断线重连保持身份，actor 侧 pipe 自动重关联；边某 dp 进程重启后该 dp 的云 DEALER 自动重连 + 重发 HELLO（v1 故障模型下整体挂，重启语义即可）
- per-identity pipe FIFO：per-(instance,dp) 消息顺序与现状 per-channel 等价

**1:1 退化**：N=1/D=1 即单端口（PORTS[0]）、单 actor、identity 集合 = {0}，与 1:N 同一代码路径（部署差异只在端口数随 D、identity 数随 N）。
### 3.8 控制通道可靠性

per-channel ZMQ（每 channel 独立 `queue.Queue(1000)` + 独立 pub/sub 线程），实例间互不影响；丢消息恢复是 1:1 既有的 HWM=1000 + 不丢假设，非多实例新增 gap。

### 3.9 云侧双机相互感知（coord group）

现有 dp=2 双机方案 A：边侧只做 IP broker（`master_port+200` store，`wait_for_workers=False`，set/get 非集合通信），云 coord group 云到云直连（云 DP0 host gloo `master_port+201`，云 DP1 connect，**边不在组里**）。

多实例下边侧 host N 个 IP 交换 store 即可，每实例 gloo 组天然隔离；边侧自身 `dp_group`（edge 内 batch_type 协调）与云多实例无关。

### 3.10 启动期控制面：边 EngineCore ↔ 云实例 worker 的 method 链

**现状（1:1）**：借用 PP 下边是唯一 active EngineCore，云是 passive EngineCore；启动期边经 rpc_broadcast_mq 广播 -> 云 passive executor 落到云 worker -> 结果经 peer_worker_response_mqs 回收（patch_multiproc_executor.py:202-247）。启动链（core.py:231-291）：

1. `get_kv_cache_specs()`（collective_rpc，收每 worker 层->spec）
2. `determine_available_memory()`（每 worker profile_run，回 available_memory 列表）
3. `get_kv_cache_configs()`（边 CPU 汇聚，num_blocks 口径见 §6.6）
4. `initialize_from_config()`（所有 worker 分配 KV tensor）
5. `compile_or_warm_up_model()` / warmup
6. 握手：`wait_for_ready` + `response_mq.wait_until_ready()`（cloud_ip TCPStore 顺序敏感，1:1 已有顺序死锁先例注释 patch_multiproc_executor.py:232-244）

**多实例（N 典型 4~8、上限 16，含同机共置）风险与要求**：

| # | 风险 | 性质 | 处理 |
|---|------|------|------|
| 1 | 端口/store key 撞车 + cloud_ip key last-writer-wins（N 个 passive core 写同一 key，边 HCCL rendezvous 连错实例）；**同机共置下同 IP 双重命中** | 拉起失败/串台 | §2.2 instance 偏移 + 拉起期端口规则校验（**硬前提**，不改拉不起） |
| 2 | collect 全量等待：determine_available_memory / initialize_from_config / warmup 需收齐 N·D·C 个 ack，任一实例未起/挂 -> 边卡死，无 per-instance 超时 | 可用性（v1 接受） | v1 故障模型"任一实例挂=整体挂"在启动期同样成立；启动时间 = 最慢实例 + N 倍 collect 串行回收（profile_run 实例间并行） |
| 3 | 顺序依赖链 ×N：cloud_ip -> 边 TCPStore -> HCCL rendezvous -> 云 `_init_message_queues` 每实例一条，任一 wait 提前 = 全组死锁 | 死锁面变宽 | 启动编排改「逐实例串行握手、全部就绪后再全局 barrier」，解耦 N 条链 |
| 4 | response ack 现按 rank 顺序匹配；多实例需按 **(instance, rank) 分组回收**，否则乱序错配 | 正确性（实现要求） | collect 按 instance 分组 |
| 5 | profile/warmup 控制面通信量 ×N（实例间执行并行，瓶颈在边回收）；条件 rpc（update_max_model_len）全实例 fan-out 语义无碍 | 轻微 | 接受 |
| 6 | **同机实例启动竞争（2026-08 新增）**：同一服务器 K 个实例同时权重加载/profile_run/warmup，host RAM（权重 ×K）、CPU、内存带宽、网口同时竞争，启动变慢甚至 OOM/超时 | 启动时长/拉起失败 | **同机实例错峰拉起**：编排层按 instance 序错峰（实例 i 延后 i×间隔，或「权重加载完成 -> 放行下一实例」流水）；profile/warmup 阶段同机实例**串行**、跨服务器实例仍并行；代价 = 启动关键路径 ∝ 同机实例数 K（§2.6 处理项 #5） |

**结论**：collective_rpc 广播 + response 回收机制天然支持更多 rank，启动期改动集中在四处：§2.2 端口/store 偏移 + 校验（硬前提）、启动编排逐实例串行握手（缓解 #2/#3）、同机实例错峰拉起（#6，编排层，不进 vllm 配置面）、§6.6 num_blocks 汇聚口径（边不进全局 min）。

### 3.11 请求调度到实例：架构实现框图（可插拔策略）

```
              ┌────────────────────────────────────────────┐
              │           状态源（可扩展输入）               │
              │  InstanceLoadStats（N×D 聚合发布，§3.5）     │
              │  ├ 边侧：waiting / running /                │
              │  │        prefill·decode·mtp 队列深度        │
              │  │        edge_kv_headroom（分区口径）       │
              │  ├ 云侧：cloud_kv_headroom per-instance     │
              │  │        （云 passive 上报，后续 #3）        │
              │  └ 预留：prefix 亲和信号（§3.5，v1 不采集）   │
              └──────────────────┬─────────────────────────┘
                                 │ 聚合 / 订阅
                                 ▼
 请求 r ──► ┌──────────────────────────────────────────────┐
            │   InstanceDispatcher（可插拔策略接口）         │
            │  ┌────────────────────────────────────────┐  │
            │  │ v1 默认：RoundRobin（逐实例轮转 0->1->…） │  │
            │  │ 扩展：LeastLoaded（队列深度最小实例）     │  │
            │  │ 扩展：QueueAndKVAware（边云队列 + KV    │  │
            │  │         headroom 联合决策）              │  │
            │  │ 扩展：PrefixAware（命中优先，亲和信号）   │  │
            │  └────────────────────────────────────────┘  │
            └──────────────────┬───────────────────────────┘
                               │ 决策输出：r.instance_id = i
                               │ （请求 pinning：draft/prefill/
                               │   MTP/decode 全跟随，§3.4）
                               ▼
            ┌──────────────────────────────────────────────┐
            │ 内层 DP 分发（复用现有机制，零改）              │
            │ 前端按 DP 负载分发 + balance_gather 准入       │
            └──────────────────┬───────────────────────────┘
                               ▼
            per-(instance,dp) 请求队列
            （N×D 个 PDSeparatedScheduler，各持独立
             HiddenChannelManager；实例间无集合通信）
```

要点：**决策点单一**（leader/前端，无分歧）、pinning 落请求级元数据全链路透传（verify 继承，§3.4）、内层 DP 分发零改。

---

## 4 数据面方案

### 4.1 全局 rank 编排

边 rank 稳定在前：0（1 卡）或 0,1（2 卡 dp=2，每卡跑首+尾、各自一个 DP rank）。云按 instance_id 在边 rank 基础上续编，每实例占连续 range：

```
inst_i = [edge_cnt + Σ(prev_sizes), + size_i)
实例i dpj first-worker rank = E + i*D*C + j*C
```

- **G0 世界组** `[0, E+N*D*C)`：rank0 master，仅 rendezvous + 启动 barrier
- 边只进世界组 + PP group，**不进**实例 DP/EP/coord 组（运行时集合通信必须走实例子组，否则跨实例耦合）
- 启动 barrier 全实例就位 == "任一实例挂 = 整个服务挂"

后果：①rank 公式/group 派生重写（交错 `i*(1+C)` -> 前边+按实例）；②PP 路由按 instance 选 G2 子组；③边 rank 进 per-instance PP 子组，跨实例时分复用。

**代码缺口（启动期核实，2026-08 补）**：

- 云侧 executor 的全局 rank 起点现**硬编码**单实例：`global_start_rank = edge_npu_count`（patch_multiproc_executor.py:161-165），`_is_driver_worker` 同样只认 `rank == edge_npu_count`（:281-288）。多实例必须改为 `E + i·D·C + j·C`（i = instance_id = node_rank-1、j = dp start-rank），这是 §4.1 rank 公式落地的**第一改动点**
- 现有 group 派生按 dp 实例交错 `instance0_edge, instance0_cloud, instance1_edge, ...`（vllm/distributed/parallel_state.py:1988-2109、vllm_ascend MC2 同构 parallel_state.py:572-605），即上文①的重写对象
- `edge_npu_count/cloud_npu_count` 现为 DP 实例总量口径、`__post_init__` 除以 dp_size 成 per-DP 值（config/parallel.py:200-233）；多实例下 cloud-npu-count 语义扩为 N·D·C 总量，post_init 除法口径需连带调整
- **同机共置不影响本节任何派生**：G0-G5 全部是逻辑 rank 区间划分，与 rank 落在哪台物理服务器无关（§2.6 支持项 #1）；instance -> 物理服务器映射由拉起脚本维护，不进 group 派生

### 4.2 group 派生（G0–G5）

| group | 组成 | size | 说明 |
|-------|------|------|------|
| **G0** 世界组 | 全部 rank | E+N·D·C | rank0 master，rendezvous+barrier |
| **G1** edge dp_group | D 个 EngineCore（gloo） | D | 跨 dp_group all_reduce 协调 batch_type；**非 HCCL edge ranks**（shared-model 1 卡时 edge HCCL rank 仅 1 个但 dp_group 仍 D 个 EngineCore，2 DP 协调在 EngineCore gloo 层），不变于 N |
| **G2** per-instance PP/数据通道 | shared-model: `{0}∪实例i云rank` / per-rank: `{j}∪实例i dpj rank` | 1+D·C / 1+C | 边进此组；shared-model 每实例一个按 dp 切 channel / per-rank N×D 个 channel 复用（Option A） |
| **G3** per-instance 云 DP/coord | 各 dp first-worker | D | 边不在 |
| **G4** per-instance EP | 实例i全部云rank | D·C | MoE all-toall；**EP 跨 D 不跨 N** |
| **G5** per-instance TP | 实例i dpj rank | C | |

**边只进 G0 + G2 -> 运行时无集合通信经边跨实例耦合。**

**EP 拓扑关键结论**：EP all-toall 跨 data_parallel_size（D，实例内），**不跨多实例 N**（per-instance G4）。N 间无集合通信可乱序；D 内（2DP）紧耦合 EP all-toall 配对。

### 4.3 PP 路由（step 2）

核心 = 按 instance_id 选 G2 子组，**子组内 dst=local_rank+1 沿用 1:1 不改**（global rank+1 才落兄弟边卡，路由用 in-group local rank 不受影响）。

- shared-model：virtual worker k（data_parallel_rank=k）在实例 i 子组内 dst=k+1 -> inst_i dp k first-worker（子组布局 `[edge(0), inst_i dp0_first(1), …, dp_{D-1}_first(D)]`）
- per-rank：edge card j 在 (i,j) 子组内边 in-group0、inst_i dp j first-worker in-group1，dst=同 1:1 per-rank 逻辑
- 返程 cloud->edge：子组内云发到 edge（in-group0），沿用 1:1；边按 (instance,dp,channel,head_token) 匹配回程 isend 路由到正确 virtual worker/tail
- instance_id 传递 = 经 scheduler_output 下发到 worker（请求 InstanceDispatcher pinning 时定），worker 读 instance_id 选 PP 子组 + channel 池
- 改动主要在边侧（1 个 PP group + 1 池 -> N/N×D 个，按 instance_id 选）；云侧基本不变

### 4.4 HiddenChannelManager instance 维度（step 3）

**核心 = instance 维度落 pp_group/通信器层，不在 channel-type 切分层；HiddenChannelManager 切片逻辑零改。**

核对代码：channel = pp_group 内子通信器（`create_hidden_channel_groups` 建 num_prefill+num_decode 个 2-rank HCCL 子组）；`HiddenChannelType` 是全局 tag 单例（init 一次建池覆盖 dp_size），**不编码 instance**，靠 pp_group 隔离；isend/irecv 由 worker 发（scheduler 只盖 channel tag 到 SchedulerOutput.hidden_channel，worker 读 tag 在 pp_group 上 isend）。

- pp_group 变 per-instance（=G2）：shared-model N 个各 `[edge(0), inst_i dp0_first(1)..dp_{D-1}_first(D)]`，edge 同时在 N 个 pp_group；per-rank N×D 个各 `[edge card j(0), inst_i dp j first(1)]`
- `create_hidden_channel_groups` 每 pp_group 各调一次（shared-model 共 N×(D×2+D) 子组；per-rank 共 N×D×3 子组），**tag 集 per-instance 复用**
- `HiddenChannelManager` 改动极小：N×D scheduler 各持一 manager = 天然 per-(instance,dp)；allocate/release/切片零改（prefill_start=dp_rank*per_dp+1、decode(dp_rank+1)）；manager **不需 instance_id**（head_token 全局唯一 + 各 manager 只调度本 instance 请求 = 池天然隔离）
- **channel 释放点绑定 recv 完成**（计算/通信分离）：`release_prefill` 从「PL 从 POST_OUT 弹出时」改为「`COMM_RECV` 阶段2 的 CPU 可见完成」。instance i 的 recv 完成即释放 instance i 的 channel，instance i 下一批 PF 可立即下发，不因其它 instance 的 POST_OUT 延迟而滞留；`prefill_inflight_limit` per-(instance,dp)=2 不变，信用回路短一个 RTT。
- instance 维度由 worker 侧实现：读 SchedulerOutput.instance_id 选 pp_group，在该 pp_group 上 isend(channel=hidden_channel, dst=peer)，tag 在 pp_group 内解析
- `HiddenChannelType.init` 池大小**无 N 因子**（tag per-instance 复用，池只需覆盖 per-instance dp_size D）
- 待实现期核实：若有全局 dict 以 HiddenChannelType 为 key 存 handle（跨 instance 撞 key）需改 key 为 (instance_id, channel_type)，目前看 tag 只是 isend 参数无全局注册表大概率零改

### 4.5 边↔云 HCCL isend/irecv

- 边↔云用 isend/irecv 点对点异步传输，跨实例不走集合通信
- 数据通道 = HiddenChannelManager 的 HCCL channel 池（2P1D = 2 prefill + 1 decode channel/dp），按实例复制
- per-instance 1:1 dp 配对：边执行 dp 并行（edge_dp==D）-> 经实例 i 数据通道 -> 云实例 i 执行 dp 并行（D），边跨实例时分复用
- edge_dp 与实例 dp 耦合（==D），新维度是 N（实例数），**不是 edge_dp 解耦**

---

## 5 调度层面方案

### 5.1 两级调度总览

| 层 | 机制 | 同步 |
|----|------|------|
| 实例间（N） | as-arrived（云返回驱动），无 barrier | 乱序 |
| 实例内（D） | coord batch_type 协调 + barrier-drain（现有多实例下改为 recv done 通知驱动） | lockstep |

实例调度决策（HEAD 喂哪个实例）见 §3.4；TAIL 实例 = HEAD 下发时已 pin 的 instance（edge 自投递），处理顺序由「recv fence 完成」驱动（as-arrived 性质保留，见 §3.4）。

实例间调度（step 级）架构实现框图（可插拔策略，HEAD 与 TAIL 解耦）：

```
              ┌─────────────────────────────────────────────┐
              │            状态源（可扩展输入）               │
              │ ├ per-instance scheduler 有无可发 batch      │
              │ ├ COMM_RECV(c2e) fence 状态（recv 是否 ready：│
              │ │   NPU event / recv_done，实例 i hidden 是否 │
              │ │   已到边，§5.2）                            │
              │ ├ pending_tails 深度 / channel 占用           │
              │ └ InstanceLoadStats（复用 §3.11 状态源）      │
              └──────────────────┬──────────────────────────┘
                                 │
         ┌───────────────────────┴────────────────────────┐
         ▼ HEAD 路径（每 step）            ▼ TAIL 路径（事件驱动）
┌──────────────────────────────┐  ┌──────────────────────────────┐
│ coord all_reduce（方案 c）     │  │ worker / 调度层 poll         │
│ leader(dp0) 提议 instance_id  │  │ TailDispatchPolicy（可插拔）  │
│ ┌──────────────────────────┐ │  │ ┌──────────────────────────┐ │
│ │ v1：InOrder 逐实例轮转     │ │  │ │ v1：FIFO 队首序逐实例     │ │
│ │ 扩展：RecvReadyAware      │ │  │ │ 扩展：RecvReadyFirst      │ │
│ │  （recv ready 的实例优先   │ │  │ │  （ready 实例 TAIL 先行， │ │
│ │   喂 HEAD，减少等待）      │ │  │ │   就绪序 = as-arrived）   │ │
│ │ 扩展：QueueAware          │ │  │ │ 扩展：TailBatchMerge      │ │
│ │  （队列深实例优先）        │ │  │ │  （open item #1，后续）   │ │
│ └──────────────────────────┘ │  │ └──────────────────────────┘ │
│ 输出：(instance_i, winner_bt) │  │ 硬约束（策略不可违反）：      │
│ follower dp1 跟随；           │  │ · 实例内不乱序（token 序 +   │
│ 对 (i,bt) 无工作的 DP dummy   │  │   云 bt 配对），队首不跳队   │
└──────────────┬───────────────┘  │ · 2DP lockstep（2DP fence   │
               │ HEAD batch       │   都 ready 才 forward）      │
               ▼ SO.instance_id   └──────────────┬───────────────┘
        worker 按 i 选 G2 pp_group +              │ TAIL forward
        channel 池 isend ──► 云实例 i             ▼
                                        tail forward（读 recv 结果，
                                        fence 已 ready 不阻塞）
```

要点：

- **HEAD 与 TAIL 策略解耦**：HEAD 是 per-step 决策（coord 分发，2DP 一致），TAIL 是事件驱动（recv fence 就绪序），两个策略接口独立可插拔
- TAIL 侧任何策略必须遵守三条硬约束：实例内保序、2DP lockstep、队首不跳队--策略只能在「实例间先后」上做选择
- 与 §3.11 状态源打通（InstanceLoadStats 复用），扩展时只加策略实现、不动分发通道

### 5.2 调度层计算/通信分离（核心改造）

> 目标：TAIL 等 hidden 期间 worker 继续 dispatch 其它 round/实例，填满边侧空闲窗口。落地方式是把「recv」从 tail 计算里拆成**调度器可见的独立任务**，由调度器调度，依赖关系由「数据面完成信号」门控——即「通信任务完成后，才允许下发依赖该通信任务的计算任务」。

#### 5.2.1 现状与阻塞点（fence 语义修正）

当前 TAIL 在 round barrier 后同步 drain，worker 在等云 hidden 期间无法处理其它实例。代码路径：

```
drain_batched_round (shared_model_edge_worker.py:367)
  ① deferred():373 -> AsyncIntermediateTensors(irecv 已发起未 wait)   [异步 ✅]
  ② execute_model_batched_tail:417 -> it["hidden_states"](:1058)
       -> wait_for_comm -> handle.wait() (gpu_worker.py:97)
```

**fence 语义修正**：`handle.wait()` 对 NCCL/HCCL 设备通信**不阻塞 CPU**——它只做 `current_stream.wait_event(nccl_end_event)` + tensor `record_stream`，立即返回；真正阻塞 CPU 的是 `synchronize()`。所以 ② 不是「CPU 阻塞等 hidden」。

**真正的串行点**（多实例无法重叠的根因，需实现期核实其一或若干）：
1. `round barrier`（:485）的 2DP lockstep——两 DP 都 drain 完 tail 才进下一 round；
2. tail 路径 sampler 的 D2H（`.item()` / `.cpu()`）——取采样结果回 CPU 的同步；
3. EngineCore 的 `future.result()` collect。

**irecv 已异步**（`edge_cloud_irecv_tensor_dict` :1416 `torch.distributed.irecv` 返回 handle 不 wait）。设备侧 fence 由 `handle.wait()` 承担；「CPU 可见完成」改用 NPU event（`event.query()`，因 `Work.is_completed` 支持不确定）。

#### 5.2.2 任务模型：COMPUTE + COMM_RECV

两类任务（术语见 §0）：

| 任务 | 职责 | 是否阻塞 |
|------|------|---------|
| `COMPUTE` | 纯前向：head（首层+isend）/ mid / tail（尾层+sampler） | head/mid 同步；tail 依赖 COMM_RECV |
| `COMM_RECV` | irecv post + 设备侧 fence + channel 释放 | 阶段1 非阻塞；阶段2 完成线程通知 |

依赖关系由 `depends_on` 表达，主链：

```
COMPUTE(head) ──> COMM_RECV(e2c / c2e) ──(recv done)──> COMPUTE(tail)
```

**send 不独立成任务**（fire-and-forget，留在 COMPUTE 尾部）；decode 单通道的 send fence 见 §5.6。

#### 5.2.3 改造点（按层）

> 改造分三层：调度层引入任务模型与依赖、worker 层拆细 RPC 与完成通知、数据面补齐 event。核心是把「recv 完成」从 worker 内部 poll 上移为「完成线程通知 → scheduler 下发」。

| 层 | 位置 | 改造 |
|---|------|------|
| 调度层 | `vllm/vllm/v1/core/sched/output.py` | 新增 `TaskKind`（`COMPUTE`/`COMM_RECV`）+ `WorkerTask`（`task_id`/`kind`/`batch_type`/`channel`/`num_tokens`/`direction`/`depends_on`） |
| 调度层 | `PDSeparatedScheduler` | HEAD 下发时产出 `COMPUTE(head)`，并自投递 `COMM_RECV(c2e)` + 预生成 `COMPUTE(tail)`（`depends_on={COMM_RECV}`）；`release_prefill` 释放点改绑 recv 完成 |
| 调度层 | EngineCore | 从新增 sideband 队列 `recv_done_mq` drain「recv done」→ `COMPUTE(tail)` 标记 ready → 下发（2DP lockstep 经现有 coord all_reduce 保证） |
| worker | `worker.py` / `shared_model_edge_worker.py` | 拆细 RPC：新增 `execute_comm_recv`（post irecv + `handle.wait()` 设备侧 fence + record event，立即返回「已 post」） |
| worker | 新增 sideband 队列 `recv_done_mq` | 独立于 `response_mq`（仿 `cloud_recv_hint_mq` 先例）；完成线程写「recv done」，EngineCore 从此 drain，**不复用 response_mq**（避免与 batch_queue 的 model output future 冲突） |
| worker | 新增 per-(instance,dp) 完成线程 | `event.synchronize()`（或 `query()` 轮询）等到 recv 完成 → 写 `recv_done_mq`。**worker 不 poll-and-run tail**（tail 下发决策在 scheduler） |
| worker | `drain_batched_round` 步骤② / round barrier (:485) | `execute_model_batched_tail` **删除立即调用**，改存 `pending_tails[instance]`；round barrier 放宽不等 tail drain（2DP 都 dispatch 完即新 round） |
| 数据面 | `edge_cloud_irecv_tensor_dict` (:1416) | irecv 后在 `_HC_STREAM_RECV` stream ctx (:1406) 内 record NPU event 并随结果返回（CPU 可见完成用） |
| 数据面 | `AsyncIntermediateTensors` (gpu_worker.py:73) | 加 `_comm_event` + `is_ready()`（`event.query()`，非阻塞）；`wait_for_comm` 不变（`handle.wait()` 设备侧 fence） |

#### 5.2.4 改造后流程

**调度层**（scheduler，每 (instance,dp)，依赖由 `depends_on` 表达）：

```
schedule():
  ① 下发 COMPUTE(head)：head forward + isend（同步，返回占位输出）
  ② 下发 COMM_RECV(c2e)：post irecv + handle.wait()（设备侧 fence，不阻塞 CPU）+ record event，立即返回「已 post」
  ③ COMPUTE(tail).depends_on = {COMM_RECV}：待「recv done」回执后下发
```

**worker 层**（worker_busy_loop 每循环）：

```
  ① MQ poll + dispatch COMM_RECV（post irecv + record event，立即回执「已 post」）
  ② 完成线程 event.synchronize()/query() 等到 recv 完成 → 写 `recv_done_mq`（不复用 response_mq）
  ③ round barrier（放宽：drain 只 post recv，不等 tail）
```

**「recv done」回传后**（经 `recv_done_mq`，scheduler 侧）：

```
scheduler 从 recv_done_mq drain (instance,dp) 的「recv done」→ COMPUTE(tail) 标记 ready → 下发（2DP lockstep 由现有 coord all_reduce 保证）
```

**跨 round 重叠（收益落点）**：

```
round k   实例i TAIL (COMM_RECV post + event → 完成线程等)
   ↓      worker 不阻塞, 继续
round k+1 实例j HEAD (head+isend 同步)
   ↓      实例i recv done → scheduler 下发 COMPUTE(tail) batched_tail (2DP lockstep)
round k+2 ...
```

TAIL 等 hidden 期间 worker 继续 dispatch 其他 round/实例；tail 下发由 **scheduler 在 recv done 后驱动**，而非 worker poll。

#### 5.2.5 2DP lockstep / 乱序 / 保序

| 约束 | 机制 |
|------|------|
| **实例内不乱序** | scheduler 的 per-(instance,dp) 就绪队列队首未就绪不跳队（保 token 序 + 云 bt 配对） |
| **实例间乱序** | 不同 instance 的「recv done」独立回传，先 done 先下发 tail（EP all-toall per-instance 不跨 N） |
| **2DP lockstep** | 2DP 都「recv done」才下发 `COMPUTE(tail)` batched（coord all_reduce 保证；batched 2DP 一起 forward + EP all-toall 配对，tail 逻辑零改） |

### 5.3 调度层计算/通信分离对 2DP 的协调分析（关键）

> 这是多实例下计算/通信分离的核心可行性论证：tail 下发从 round barrier 改为「recv done 通知」后，2DP 的 tail 计算是否还能保证同步。

#### 5.3.1 tail 计算是 leader 1× 代算，不是 2DP 各自 forward

drain_batched_round 注释明说 **"1× batched tail on the leader runner"**（[:392](../vllm-ascend/vllm_ascend/worker/edge_cloud/shared_model_edge_worker.py#L392)）：

- leader = `_SHARED_MODEL_REGISTRY` 中 `_is_leader` 的 worker（[:396](../vllm-ascend/vllm_ascend/worker/edge_cloud/shared_model_edge_worker.py#L396)）
- `leader_runner.execute_model_batched_tail(bundles, intermediates)`（[:417](../vllm-ascend/vllm_ascend/worker/edge_cloud/shared_model_edge_worker.py#L417)）——leader 单独 forward
- 内部 `merged_hidden = torch.cat([it["hidden_states"][:n] ...])`（[:1058](../vllm-ascend/vllm_ascend/worker/edge_cloud/batched_model_runner.py#L1058)）——**2DP hidden 合并成 1 batch**
- `_model_forward(merged)`（[:1222](../vllm-ascend/vllm_ascend/worker/edge_cloud/batched_model_runner.py#L1222)）——leader 1× forward 合并 token
- 结果 slice 分发：`peer_worker.model_runner.execute_model_post_batched(...)` per dp_rank（[:456](../vllm-ascend/vllm_ascend/worker/edge_cloud/shared_model_edge_worker.py#L456)）

**dp1 不独立 forward**，其 token 由 leader 代算（2DP hidden cat -> leader forward -> slice 回 dp1）。所以 tail 计算根本**不存在"2DP 各自 forward 需同步"**这回事。

#### 5.3.2 2DP 的同步点只在 recv 就绪，不在 tail forward

| 阶段 | 2DP 各自? | 是否需 2DP 同步 |
|------|-----------|-----------------|
| recv (irecv) | 各自（per dp_rank `do_direct_recv`） | **是，这里需 lockstep** |
| tail forward | **否，leader 1× 代算** | 否（leader 单独） |
| post_batched | 各自（per dp_rank） | 否（各 DP 独立采样） |

- 当前 drain：`round barrier all(paused)`（2DP recv done 同步）-> leader 1× tail forward
- 新调度：scheduler 收到 2DP 都「recv done」-> 下发 `COMPUTE(tail)` leader 1× tail forward

**同步语义完全等价，只是把 round barrier 换成「recv done 通知 + scheduler 下发」。** leader 1× 代算不变。2DP lockstep 锚定在 **recv 就绪**，不是 forward。

#### 5.3.3 为什么脱离 round barrier 无害

1. **EP=1**：shared-model `ep_edge_ranks=[0]`（[parallel_state.py:1775](../vllm/vllm/distributed/parallel_state.py#L1775)），edge tail 的 EP all-toall 在 edge 单 rank，**无跨 2DP 集合通信**。leader 1× forward 不需 dp1 参与 EP 配对。
2. **tail forward leader 1×**：dp1 不 forward，不存在 dp1 forward 落后/超前 dp0。
3. **cloud EP all-toall 配对**：在 cloud middle（cloud worker），被 edge head **PRE_OUT** 驱动。head 段是 `execute_model`（SYNC_METHODS，[shared_model_multiproc_executor.py:173](../vllm/vllm/v1/executor/shared_model_multiproc_executor.py#L173)），**仍在 round barrier 2DP lockstep**，不受 tail 调度影响。

#### 5.3.4 EngineCore 层重叠深度限制（batch_queue_size）

> `batch_queue_size` 是 EngineCore 层的 **PP 在飞信用上限**（限制「同一时刻几个 execute_model future 未 collect」），与「DL/PL 何时被 pick」正交——它不决定 tail 的下发时机，只限制在飞深度。

- 每 step：`_coordinate_bt`（all_reduce 2DP 同步）-> fill（execute_model）-> fill 条件 / collect
- fill 条件 = `model_executed AND len(batch_queue) < batch_queue_size AND not batch_queue[-1].done()`（队尾未完成 -> 继续 fill）
- batch_queue 满 或 队尾 done -> collect（队尾 `future.result()` 阻塞）
- 实例 i 的 tail future 未 collect 会占用一个在飞位 -> 填至 batch_queue 满 -> collect 队尾阻塞
- scheduler 收到实例 i「recv done」-> 下发 tail -> 队尾 collect 解除 -> 2DP all_reduce 推进

**异步重叠深度 = batch_queue_size − 1 = pp_size − 1 = 1**（边云 PP=2）。实例 i tail 延迟期间，EngineCore 最多再填 1 个（实例 j）。compute/comm 分离改变「recv 何时 post、tail 何时下发」，不改变「tail 输出仍占 batch_queue 一个在飞位」，故该深度约束不变，需配合调大 batch_queue_size 才能放大重叠收益。

> 结论：计算/通信分离对 2DP **无致命冲突**（EP=1 / dummy 不影响 / tail leader 1× 代算）。收益是**缩短** collect 阻塞时长；但**重叠深度受 EngineCore 的 batch_queue_size 限制**，需配合调大 batch_queue_size 才能放大重叠收益。

### 5.4 coord / balance_gather 多实例扩展（open item #4）

#### 5.4.1 `_coordinate_bt` all_reduce 扩展

`_coordinate_bt`（patch_engine_core.py:708）= 1 次 SUM-gather on dp_group，payload `2*dp_size+1` int32 `[bt_id_0..bt_id_{n-1}, wait_0..wait_{n-1}, unfinished]`，winner = 默认 dp0 priority + Rule2（DL ready -> winner=DL）+ Rule1（一 DP DF-ready 另一 EMPTY 且有 waiting decode -> winner=EMPTY 推迟 DF）。

**多实例 v1 扩展 = payload +1 instance_id slot**（leader dp_rank==0 填、其他 0、SUM=leader's instance_id，所有 DP 收到同一 instance），**1 次 all_reduce 不变、payload 仅 +1 int32**。

#### 5.4.2 `balance_gather` 扩展

`balance_gather` = `all_gather(running_tensor, balance_queue, dp_group)`，判定 `max(running across DP) == max_num_running_reqs` 停接。

**多实例扩展 = running_tensor `[1]->[N]`、balance_queue `tensor[1]->tensor[N]`、判定改 per-instance**（实例 i max running == max -> 停接实例 i，不影响其他），group 不变、1 次 all_gather 不变、payload 扩 N 倍。

#### 5.4.3 连带改动

- `_intended_batch_type()`（调用点 line 1049）从"1 scheduler ready"改"汇总 N 个 per-instance scheduler ready 返回整体 intended"
- `_schedule_target(winner)`（调用点 line 1112）加 instance 参数（从 instance i scheduler 取 winner bt batch，无则 dummy 带 i 路由）
- leader `InstanceDispatcher` 在 `_coordinate_bt` 前/内决策 instance 填 slot

#### 5.4.4 深层风险（效率/延迟，非死锁）

v1 用**整体 intended**（跨实例汇总）做 bt 协调，丢 per-instance 信息：

- (a) dummy 频繁：winner bt 是 2DP 整体 intended 妥协，应用到 instance i 时某 DP 对 i 无该 bt 工作 -> dummy
- (b) **Rule1/Rule2 decode 对齐跨实例误判**：bt_ids 是 N 实例汇总，实例 j 的 DL ready 让 winner=DL 应用到 instance i，可能让 i 的 DF 被错误推迟（i 根本没在 decode 阶段）——跨实例误伤延迟

**根治 = 精化两阶段 all_reduce**（阶段 1 分发 instance i、阶段 2 2DP 各报对 i 的 intended bt 协调，bt 绑 instance、Rule1/Rule2 在 per-instance bt 上判定不串扰），代价 2 次 all_reduce。v1 dummy 兜底，精化留后续。

**风险性质 = 效率/延迟（非死锁）**：winner 机制仍保证 2DP 同 bt 配对云 EP（配对正确性不变、不死锁），整体-intended 串扰仅致 dummy 多 + Rule1/2 跨实例误伤延迟。

### 5.5 dummy 不串实例

dummy 走 instance i 的 channel 池（§4.4 per-(instance,dp) 池隔离）。coord 保证 2DP 同 bt，某 DP dummy（tokens=0，无 marker）不进 `pending_tails`/batched tail（leader cat 时按 `n_actuals_tail` 自然跳过，0 token 不合并），与当前 1:1 drain 一致。

### 5.6 decode 单通道 send fence 与 DL 下发时机（计算/通信分离补充）

**decode 单通道 send fence**：decode 每 (instance,dp) **单通道 + 单发送缓冲**，DF2 的 head compute 会覆盖 DF1 还在读的发送缓冲，必须在 DF2 head compute 前放一条设备侧 fence（非阻塞 `handle.wait()`）。per-instance 隔离：instance i 的 DF 与 instance j 的 DF 走不同 channel，互不干扰。

**DL 30ms → recv fence**：现状 DL 被 `_can_schedule_decode_last` 的 30ms 延迟（`pd_separated_scheduler.py:1095`）同时推迟「irecv post」与「tail forward」。分离后：
- irecv（`COMM_RECV` 阶段1）在 DF isend 后**立即 post**，无需 30ms；
- tail forward（`COMPUTE`）由 **recv fence** 门控，无需 30ms。

即 DL 的下发时机从「定时器」换成「数据面就绪」，与 §5.2.3 的 `COMM_RECV`/`COMPUTE` 依赖一致。严格交替 `DF isend → DL irecv → DF isend → DL irecv` 仍须保留（单 channel stream，否则跨侧死锁，见 `worker.py:1185-1190` 注释）。

---

## 6 KV 方案

### 6.1 边侧 KV 准入：per-instance 分区（v1）

**v1 = per-instance 分区**（`per_dp_num_blocks / N` 给每 (instance,dp)，各 scheduler 独立准入、无共享、无协调器）。

理由：实例间请求理论均衡（`InstanceDispatcher` 均衡路由）-> 无实例需借 KV，共享的利用率收益不兑现而风险是硬的。embedding_only 无 edge KV 免。

### 6.2 共享池 + 协调器（后续实测后调优）

若实测分区不够（长序列打满 / inflight 上不去影响 pipeline 重叠），需：

- per-dp 共享 `KVCacheManager`（单 free list，跨实例物理共享）
- per-instance 软配额（min guarantee + 溢出借闲）+ 上限 cap（爆炸半径）
- 先确认 scheduler 并发模型（EngineCore 层 per-step 一个 (instance,bt) sequential 时分复用 N scheduler = 单线程免锁；lockstep 原指 worker 层 1 进程，KVCacheManager 准入在 EngineCore 层）

**共享下 headroom 口径**：edge_kv_headroom 是 per-dp 全局量（非 per-instance）、cloud_kv_headroom 才 per-instance（实例选择看云侧 room、dp 选择 + 边侧准入看 per-dp edge room）。**分区下两者都 per-instance**（InstanceLoadStats 原 per-instance 结构即正确）。

### 6.3 容量 sizing（已核实；N 范围更新 2026-08：按模型口径，qwen3.6-27b 上限 16）

分区下边侧向每实例 PP group（G2）报 `per_dp_num_blocks / N`，per-instance min = min(edge/N, cloud_i)；min 机制是 per-PP-group（多实例 G2 天然支持 per-instance，机制不破坏）。

实测 R = 边/云 num_blocks 比（**每模型 N 上限不同，§1.4 部署矩阵**；翻转分析只对能达到 N* 的模型实际生效）：

| 模型 | 首/尾层 | 边 num_blocks | 云 num_blocks | R（=N*） | 该模型 N 上限 | 实际可达翻转区？ |
|------|---------|---------------|---------------|----------|---------------|------------------|
| qwen3.6-27b（C=2） | 首1尾1 | 16524 | 2024 | 8.16 | **16** | **是：N=8 临界（1.02×）、N=16 翻转（0.51×）** |
| deepseek-v4-flash-w8a8（C=8） | 首3尾1 | 142728 | 8127 | 17.56 | 4（8卡/实例，每服务器 1 实例） | 否：N=4 时 4.39×，远低于翻转点 |
| kimi25_w4a8_static_m6（C=16） | 待实测 | 待实测 | 待实测 | 待实测 | 2（实例跨 2 服务器） | 否：N=2 任意 R 下均安全 |

翻转点 N* = R。**2026-08 更新结论（容量临界/翻转是 qwen3.6-27b 特有问题）**：

- **qwen3.6-27b、N ≤ 4**：edge/N > 云，cloud-bound 不翻转、无容量损失（原结论不变）
- **qwen3.6-27b、N = 8（形态三b，2 服务器 × 4 实例，§2.6 形态三）**：edge/N ÷ cloud = 16524/8/2024 ≈ **1.02×，进入临界区**--余量为 2%，任何口径偏差（gpu_memory_utilization 微调、buffer 漂移、§6.3 表口径不一致）都会翻转为 edge-bound，min 被 edge/N 钳制。**N=8 落地前置条件：按 2 卡实例口径重实测 R 并确认 > 8.16（现表为既有口径实测，2 卡 tp2 实例的云侧 num_blocks 需重测），否则须扩边侧资源或降 N**
- **qwen3.6-27b、N = 16（满配，形态三c）**：翻转 edge-bound（edge/16 = 1032 < 2024），每实例值被钳到 edge/N，**云侧容量利用率仅 ~51%**（云空闲 KV 不可借给其他实例，§6.1 分区不可借）。N=16 只在边侧资源同步扩展（§1.4，目标算力比 2:32 不变下边侧 KV 扩容）使 R 同比提升时可用
- **DS（8 卡实例）**：N 上限 4（每服务器 1 实例、无共置），4.39× 余量厚，**翻转点 17.56 在其 N 范围外，容量问题不存在**；DS 的多实例代价在 per-server host 资源（每机单实例，无共置竞争）与 4 台服务器 4 故障域
- **kimi（16 卡实例，跨 2 服务器）**：N ≤ 2，容量安全；设计关注点在实例内跨机 tp 通信带宽（§2.1 云双机不占额外 node-rank）而非 KV 翻转

dp=2 不影响 R（边云 per-dp 同除）。

分区下每实例 (edge/N − cloud) 私有闲置不可借，但 cloud-bound 下云是瓶颈本用不上、均衡请求无影响；**翻转后（N > R）闲置方向反转（云侧闲置），此时 §6.2 共享池对边侧虽无增益，但应重新评估 per-instance 准入配额与实际负载均衡的匹配，避免长尾实例打满 edge/N 而其他实例闲置**。qwen3.6-27b 余量最薄（若 16524/2024 口径不一致最坏 1.02× 临界，建议确认同口径--N=8 下该确认从"建议"升级为"必做"）。

### 6.4 prefill_inflight_limit 作用域（per-(instance,dp)）

`prefill_inflight_limit` 是 `PDSeparatedScheduler` 实例属性（默认 = `_PREFILL_CHANNELS_PER_DP` = 2），而 scheduler 是 per-(instance,dp)（方案 A N×D 个）。

- 1:1 dp=2：每 dp scheduler 各 2 = 共 4
- 多实例 N：每 (instance,dp) 各 2 = 共 2×N×D = **4N**（dp=2，每实例 4），与 channel 2/dp（prefill_per_dp=2）匹配、自洽

后果：边侧首层 4N 个 prefill 在飞（边侧算力天花板对 N 的约束）；边侧 KV 分区 `per_dp_num_blocks/N` 须覆盖**每 (instance,dp) 2 inflight prefill** KV（非整个实例 4）。分区 sizing 与 inflight 作用域耦合。

**N 扩到 8/16 的边侧压力（2026-08 补）**：N=8 时边侧 32 个 prefill 在飞、N=16 时 64 个--边侧首层算力与 KV 准入压力线性放大，多实例重叠收益的兑现前提是边侧首/尾处理吞吐 ≥ N 流喂入速率（§1.2/§1.3 边侧天花板）；实测时以边侧 head/tail 利用率为准评估 N 的实际收益上限，超出后继续加实例只增加在飞与内存压力而无吞吐增益。

> 计算/通信分离下，`prefill_inflight_limit` 的信用释放点从「PL 返回」提前到「recv 完成」（§4.4），信用回路短一个 RTT，但 inflight 上限值本身不变（per-(instance,dp)=2）。

### 6.5 云侧 KV

请求端到端钉在一个云实例，中间层 KV 驻留该实例，**不做跨实例迁移**。cloud_kv_headroom per-instance 上报边侧 leader（v1 不做，后续 open item #3）。

### 6.6 启动期 num_blocks 汇聚：min(边/N, 所有云实例)（同构部署，已确认可行）

**部署前提**：所有云实例**同构**（卡型 / gpu_memory_utilization / 模型与 dp·tp 配置一致），启动期校验各实例 profile 出的 available_memory 差异超阈值即拒绝拉起（否则最小实例静默把全体拉平，容量损失无告警）。embedding_only 边无 edge KV 天然免（1TiB 虚拟值先例，worker.py:549）。

**汇聚公式（head_tail）**：per-instance 值 = `min(edge/N, min_i cloud_i)`。同构 + N ≤ 4 < R（§6.3 翻转点，两模型 R ≥ 8）下恒等于 cloud_i（cloud-bound 不翻转）：

- 每 (instance,dp) scheduler 准入 num_blocks = 该值（N×D 个 scheduler 同值）
- 云实例 i 物理分配 = 该值（低于自身容量与 1:1 现状同性质，cloud-bound 下无损失）

**实现要点（关键：不能直接复用现有全局 min）**：`get_kv_cache_configs` 现有"所有 rank 拉平到全局最小"（kv_cache_utils.py:2146）会把**边也钳进去**。1:1 时边钳到 cloud 无害（边只镜像 1 份）；多实例下边要容纳 **N 份**（4×2024=8096 > 2024），边物理池被钳到 per-instance 值 = 边侧超卖/OOM。正确做法：

- **边不进全局 min**：边物理池按自身 profiled 容量分配（或报虚拟大值，同 embedding_only 思路）；边侧分区 edge/N 只是**准入簿记**（§6.1），不是物理钳制
- 全局 min 只在「每实例的云 workers」上取；边以 edge/N 份额参与该实例的 min
- 该规则在假想 edge-bound（N > R）下也自洽：每实例值 = edge/N，边物理 = 全池 = N×edge/N，不超卖

**scheduler config 分发**：core.py edge_cloud 分支现单选 `max_group_idx` 一份 config 给 scheduler（:271-278）；同构下各实例 config 相同，**单选可用**，N×D scheduler 共用同一 num_blocks（异构已被部署前提排除）。

---

## 7 open items / 风险

### 7.1 已决（v1）

| # | 项 | 决定 |
|---|----|------|
| #1 | 同 batch_type 跨实例尾层组批 | **不做**，各实例尾层独立处理；后续需要再考虑 |
| #6 | 实例调度决策机制 | **方案 c**：leader 决策 + all_reduce 分发 |
| #5 | prefill_inflight_limit 作用域 | **per-(instance,dp)**，共 4N |

### 7.2 待后续

| # | 项 | 说明 |
|---|----|------|
| #2 | worker 层异步重叠实现 | 6 改造点已细化（§5.2.3），待实现期核实 NPU event 在 `_HC_STREAM_RECV` record、2DP event 就绪同步、backpressure/内存（pending 上限，沿用 prefill_inflight_limit per-(instance,dp)） |
| #3 | 负载统计发布节奏/聚合 | N×D 发送方发布频率/新鲜度/前端聚合时机待定；富结构 InstanceLoadStats + 云 passive 上报 cloud_kv 是后续最大改动 |
| #4 | coord/balance_gather 精化 | v1 整体 intended dummy 兜底；精化两阶段 all_reduce 根治跨实例 Rule1/2 误伤（优化效率非纠正确性） |
| - | batch_queue_size 调优 | 当前 = pp_size = 2，重叠深度 = 1；放大重叠需调大，代价 inflight/内存/KV 压力 |
| - | 边侧 KV 共享池 | 实测分区不够时启用（§6.2），最大风险 = vllm KVCacheManager per-EngineCore 设计 -> 跨实例共享是深度改动 |
| - | 2 卡实例口径 R 重实测（2026-08） | §6.3 现表为既有口径实测；qwen3.6-27b 2 卡 tp2 实例云侧 num_blocks 需重测，N=8 临界判定依赖该值 |
| - | per-server 聚合带宽实测（2026-08） | 同机 K 实例 hidden isend/irecv + ZMQ 挤同一网口，K=4 聚合带宽 vs 单实例流量的实测决定多实例重叠收益上限（§2.6 处理项 #3） |
| - | 同机错峰拉起编排（2026-08） | 编排层按 instance 序错峰 / 权重加载流水放行，profile/warmup 同机串行、跨机并行（§3.10 #6），错峰参数待实测定 |

### 7.3 风险性质汇总

| 风险 | 性质 | 说明 |
|------|------|------|
| coord all_reduce 2DP 同步 + batch_queue collect 阻塞 | **效率约束（非死锁）** | 重叠深度受 batch_queue_size 限制，worker 层无法单独突破 |
| 整体 intended 跨实例 Rule1/2 误伤 | **效率/延迟（非死锁）** | winner 机制仍保证 2DP 同 bt 配对云 EP，配对正确性不变 |
| NPU event record stream | **正确性** | 必须在 `_HC_STREAM_RECV`（irecv stream）record，否则不反映 irecv 完成 |
| 2DP event 就绪同步 | **正确性** | 实例 i dp0/dp1 hidden 云 2DP isend 可能不同时到，等 2DP 都「recv done」齐 |
| 边侧 KV 跨实例共享 | **深度改动（最大风险）** | per-EngineCore 设计、并发安全、block_table 跨实例簿记、公平/饥饿、爆炸半径、驱逐跨实例、prefix caching 跨实例 |
| **同机端口/store 撞车（2026-08 新增）** | **拉起失败/串台（硬前提）** | 同机多实例同 IP，§2.2 全通道 instance 偏移 + 拉起期校验必须，不改拉不起（§2.6 处理项 #2） |
| **云侧 global_start_rank 硬编码（2026-08 新增）** | **正确性（代码缺口）** | 现硬编码 `edge_npu_count` 单实例（patch_multiproc_executor.py:161-165），多实例须改 `E+i·D·C+j·C`，不改则同机实例 rank 全部重叠（§4.1 代码缺口） |
| **同机 host 资源/带宽竞争（2026-08 新增）** | **性能（评估口径变更）** | 权重 ×K、网口出口共享：数据面带宽评估口径改 per-server 聚合，多实例重叠收益可能被带宽竞争吃掉（§2.6 处理项 #3） |
| **相关性故障域=服务器（2026-08 新增）** | **可用性（故障模型）** | 一机挂 = 该机 K 实例齐挂，N=8 实际仅 2 个故障域；v1 无 failover 整体挂（§2.6 处理项 #4） |
| **同机启动竞争（2026-08 新增）** | **启动时长** | 同机 K 实例错峰拉起，启动关键路径 ∝ K（§3.10 #6） |
| **N ≥ 8 容量临界/翻转（2026-08 新增）** | **容量（前置条件）** | qwen3.6-27b R≈8.16：N=8 临界（1.02×）、N=16 翻转 edge-bound（云利用率 ~51%）；N≥8 须 2 卡实例口径重实测 R + 边侧资源扩展（§6.3） |

---

## 8 与现有边云 DP 工作的正交性

多实例调度与现有边云 DP 工作**正交**：

- **DP 是实例内/紧耦合集合通信**（跨 data_parallel_size D，EP all-toall 配对、coord batch_type 协调）
- **多实例调度是实例间松耦合分发**（跨 N，无集合通信、请求级分发）

现有 DP 工作（段级协调、dummy skip 修复、MC2/ALLGATHER 选择）均在实例内 D 维度，多实例 N 维度不触及。

---

> 本文档为方案设计阶段产出，所有结论经代码核实。实现期需对 open items 逐项验证，
> 特别是 NPU event 轮询机制（§5.2.3 改造点 1）与 batch_queue_size 调优（§5.3.4）。
