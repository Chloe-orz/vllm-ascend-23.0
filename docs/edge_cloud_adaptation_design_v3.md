# 边云协同场景 vLLM-Ascend 适配设计文档（第三版）

| 版本 | 日期 | 作者 | 描述 |
|------|------|------|------|
| 0.1 | 2026-04-28 | - | 初始版本（v1） |
| 0.2 | 2026-04-28 | - | 第二版：修正图编译与通信架构设计 |
| 0.3 | 2026-04-28 | - | 第三版：基于 MindIE-LLM 实际存在的 ATB 通信组件与 C++ 调度层，结合 vllm-ascend ACLGraphWrapper 能力重新设计；**注：MindIE-LLM 核心运行时中未验证的 ACL Graph 边云实现已被清理** |

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [MindIE-LLM 边云现状重新审视](#2-mindie-llm-边云现状重新审视)
3. [v2 到 v3 的关键演进](#3-v2-到-v3-的关键演进)
4. [架构设计](#4-架构设计)
5. [图编译详细设计（重点）](#5-图编译详细设计重点)
   - 5.7 [图执行时序保证](#57-图执行时序保证)
   - 5.8 [基于 Monkey Patch 的分段 forward 设计](#58-基于-monkey-patch-的分段-forward-设计)
   - 5.9 [多模型适配方案（DeepSeek-V4 / Qwen3.5）](#59-多模型适配方案deepseek-v4--qwen35)
   - 5.10 [dummy_run / profile_run 阶段独立图捕获](#510-dummy_run--profile_run-阶段独立图捕获)
   - 5.11 [非对称分片策略：首3尾1 方案设计](#511-非对称分片策略首3尾1-方案设计)
6. [边云 ACL 场景数据流（重点）](#6-边云-acl-场景数据流重点)
7. [通信机制设计](#7-通信机制设计)
8. [模型执行器设计](#8-模型执行器设计)
9. [其他模块简要设计](#9-其他模块简要设计)
10. [实现计划](#10-实现计划)

---

## 1. 背景与目标

### 1.1 边云协同场景描述

```
┌─────────────────────────────────────────────────────────────────┐
│                         边云协同推理架构                          │
├───────────────────────┬─────────────────────────────────────────┤
│     边侧 (Edge)        │              云侧 (Cloud)               │
│    2卡 (TP=2)         │             8卡 (TP=8)                  │
├───────────────────────┼─────────────────────────────────────────┤
│  - Embedding          │  - Transformer Layers K~N-K-1           │
│  - Layers 0~K-1       │                                         │
│  - Layers N-K~N-1     │                                         │
│  - HiddenStates Send/ │  - HiddenStates Recv/Send               │
│    Recv               │                                         │
│  - Sampling           │                                         │
└───────────────────────┴─────────────────────────────────────────┘
         │                              │
         │    HiddenStates Transfer      │
         │    (Via RoCE/NIC)            │
         └──────────────────────────────┘
```

### 1.2 设计目标

1. **图编译适配**：基于 vllm-ascend 现有 `ACLGraphWrapper` 能力，引入 Decode 阶段部分 Graph 优化；通信（`dist.send`/`dist.recv`）始终在图外 Eager 执行，避免 HCCL 与 `torch.npu.NPUGraph` 死锁
2. **通信组件参照 MindIE-LLM ATB 示例层**：直接参照其成熟的 `EdgeCloudDataComm`（HCCL 数据面）与 `EdgeCloudCtrlComm`（TCP 控制面）实现
3. **调度策略参照 MindIE-LLM C++ 层**：`EdgeCloudPolicy` 的 P/D 调度策略与 `LayerwiseMixin` 的批次状态机管理
4. **性能优化**：Prefill 全程 Eager，Decode 计算段启用 ACL Graph 捕获/重放，支持动态 batch size 的图缓存

---

## 2. MindIE-LLM 边云现状重新审视

### 2.1 代码仓清理情况

经重新核查，MindIE-LLM 核心运行时（`mindie_llm/`）中**未验证的 ACL Graph 边云实现已被大规模清理**：

| 类别 | 之前状态（v3 初版参照） | 当前实际状态 |
|------|----------------------|------------|
| 边云设计文档（4 份） | 存在 | **已全部删除** |
| `model_runner_exp.py` 边云代码 | 1038 行，含 `forward_decode_with_graph` | **已清理为 524 行通用代码**，无边云逻辑 |
| `aclgraph_model_wrapper_exp.py` 边云代码 | 含边云参数透传 | **已清理为 298 行通用代码**，无边云逻辑 |
| `aclgraph_backend.py` 边云代码 | 含边云适配 | **通用 ACL Graph backend**，无边云逻辑 |
| `mindie_llm/utils/layerwise/` 下 `edge_cloud_*_comm.py` | 存在 | **源文件已删除**（仅残留 pyc） |

### 2.2 当前实际可用的参照

MindIE-LLM 中**仍然保留**、可作为 vllm-ascend 设计参照的组件：

| 组件 | 文件路径 | 状态 | 可参照内容 |
|------|---------|------|-----------|
| `EdgeCloudDataComm` | `examples/atb_models/.../edge_cloud_data_comm.py` | ✅ 完整保留（528 行） | HCCL 数据通信：send_hidden/recv_hidden、stream/cards 管理、rank table 处理 |
| `EdgeCloudCtrlComm` | `examples/atb_models/.../edge_cloud_ctrl_comm.py` | ✅ 完整保留（465 行） | TCP 控制通信：TLS、TCPClient/TCPServer、send_prefill/recv_decode 等 |
| `LwdCommunicationManager` | `mindie_llm/utils/layerwise/communication.py` | ✅ 保留（344 行） | 配置解析：role_type、IP/port 校验、通信初始化流程 |
| `EdgeCloudPolicy` | `src/scheduler/policy/stage_policy/edge_cloud_policy.cpp` | ✅ 保留 | C++ 调度策略：P/D Batch 计数、优先级决策 |
| `LayerwiseMixin` | `src/engine/layerwise_mixin.cpp` | ✅ 保留 | Engine 扩展：批次准备、响应处理、状态机 |
| ATB Decode Graph Wrapper | `examples/.../layerwise_decode_graph_wrapper.py` | ✅ 保留（102 行） | **思想参照**：计算分段（head/tail graph）、通信与计算解耦；**注意**：此为 ATB 专用实现（`torch.classes.ModelTorch`），不能直接映射到 ACL Graph |

### 2.3 对 v3 设计的修正结论

- **通信层设计**：可直接参照 ATB 示例层的 `EdgeCloudDataComm` 和 `EdgeCloudCtrlComm`，成熟可靠
- **调度层设计**：可参照 C++ 层的 `EdgeCloudPolicy` 与 `LayerwiseMixin`
- **图编译设计**：MindIE-LLM 核心运行时**无已验证的 ACL Graph 边云实现**。v3 的 Decode Graph 方案需基于 vllm-ascend 现有 `ACLGraphWrapper` 能力**自行设计**，可借鉴 ATB 示例中"计算分段 + 通信解耦"的思想，但不可声称"直接复用 MindIE-LLM 的 ACL Graph 边云代码"

---

## 3. v2 到 v3 的关键演进

### 3.1 v2 设计的问题

v2 文档中边云场景对 ACL Graph 的处理过于保守：
- 边云模式下强制使用 **PIECEWISE Eager**，Decode 阶段也无法享受 Graph 重放收益
- 未充分利用 vllm-ascend 已有的 `ACLGraphWrapper` 基础设施

### 3.2 v3 核心改进

```
v2: 边云模式 → PIECEWISE Eager → 全程无 Graph → Decode 性能损失
v3: 边云模式 → Prefill Eager + Decode 计算段 Graph → 性能恢复
```

| 改进项 | v2 | v3 |
|--------|-----|-----|
| Prefill 阶段 | Eager | Eager（不变） |
| Decode 计算段 | Eager | **Graph（基于 ACLGraphWrapper 自行设计）** |
| Decode 通信段 | Eager | Eager（不变，始终在图外） |
| 图编译基础 | 无 | `ACLGraphWrapper` + `batch_descriptor` 缓存 |
| 通信组件 | Mooncake/NCCL 抽象 | **参照 MindIE-LLM ATB 示例的 HCCL + TCP 实现** |
| 调度策略 | 无 | **参照 MindIE-LLM C++ EdgeCloudPolicy** |

---

## 4. 架构设计

### 4.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      边云协同推理架构 (v3)                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐          ┌─────────────┐                       │
│  │   Edge      │          │   Cloud     │                       │
│  │   Node      │◄────────►│   Node      │                       │
│  │  (TP=2)     │  Hidden  │  (TP=8)     │                       │
│  └─────────────┘ States   └─────────────┘                       │
│        │                                                         │
│        │  ┌─────────────────────────────────────────────┐       │
│        │  │ Edge 侧 ACL Graph 段 (Decode)               │       │
│        │  │ ┌─────────────────┐    ┌─────────────────┐ │       │
│        │  │ │ Graph Segment A │    │ Graph Segment E │ │       │
│        │  │ │ Embed+Layers0~K-1│───►│ LayersN-K~N-1+Norm│ │       │
│        │  │ │ (ACLGraphWrapper)│   │ (ACLGraphWrapper)│ │       │
│        │  │ └─────────────────┘    └─────────────────┘ │       │
│        │  └─────────────────────────────────────────────┘       │
│        │                                               │       │
│        │                    [图外通信: send/recv]      │       │
│        │                                               ▼       │
│        │  ┌─────────────────────────────────────────────┐       │
│        │  │ Cloud 侧 ACL Graph 段 (Decode)              │       │
│        │  │ ┌─────────────────────────────────────┐    │       │
│        │  │ │ Graph Segment C                     │    │       │
│        │  │ │ Layers K .. N-K-1                   │    │       │
│        │  │ │ (ACLGraphWrapper)                   │    │       │
│        │  │ └─────────────────────────────────────┘    │       │
│        │  └─────────────────────────────────────────────┘       │
│        │                                               │       │
│        │  ┌─────────────────────────────────────────────┐       │
│        │  │ Edge/Cloud Prefill 阶段                     │       │
│        │  │ 分段 Eager (Segment A→通信→C→通信→E)        │       │
│        │  └─────────────────────────────────────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 核心组件

| 组件 | 职责 | 设计来源 |
|------|------|---------|
| `EdgeCloudConfig` | 边云协同配置 | v2 基础上新增 `enable_decode_graph` 等 |
| `HiddenStatesTransferHCCL` | HCCL 数据通信 | **参照 MindIE-LLM ATB 示例 `EdgeCloudDataComm`** |
| `EdgeCloudCtrlComm` | TCP 控制通信 | **参照 MindIE-LLM ATB 示例 `EdgeCloudCtrlComm`** |
| `EdgeCloudManager` | 生命周期管理、配置解析 | **参照 MindIE-LLM `LwdCommunicationManager`** |
| `EdgeModelRunner` | 边侧执行器，含 Decode Graph | 基于 vllm-ascend `NPUModelRunner` + `ACLGraphWrapper` 自行设计 |
| `CloudModelRunner` | 云侧执行器，含 Decode Graph | 同上 |
| `LayerShardLoader` | 按层分片加载 | v2 继承 |

---

## 5. 图编译详细设计（重点）

### 5.1 核心原则

1. **计算和通信在执行时序上解耦**（借鉴 MindIE-LLM ATB 示例思想）
2. **Graph 只负责计算，通信始终在 Graph 外部执行**
3. **Prefill 全程 Eager**，形状多变，图捕获收益低
4. **Decode 阶段计算段使用 ACL Graph**，batch 相对固定，调度收益高

### 5.2 图捕获与重放的精确位置

vllm-ascend 中 `ACLGraphWrapper` 的图捕获与重放发生在以下精确位置：

#### 5.2.1 图捕获（Capture）

**运行时懒捕获（Lazy Capture）**：
- **文件**：`vllm-ascend/vllm_ascend/compilation/acl_graph.py`
- **函数**：`ACLGraphWrapper.__call__()`
- **捕获分支入口**：行 130
- **创建 NPUGraph**：行 142 `aclgraph = torch.npu.NPUGraph()`
- **图捕获上下文开始**：行 157 `with torch.npu.graph(aclgraph, pool=self.graph_pool):`
- **实际模型前向被捕获**：行 159 `output = self.runnable(*args, **kwargs)`

```python
# acl_graph.py:130-188
if entry.aclgraph is None:                                    # 行 130 ← 捕获分支入口
    validate_cudagraph_capturing_enabled()                     # 行 138
    aclgraph = torch.npu.NPUGraph()                           # 行 142 ← 创建 NPUGraph
    with ExitStack() as stack:
        forward_context.capturing = True                      # 行 156
        with torch.npu.graph(aclgraph, pool=self.graph_pool): # 行 157 ← 图捕获上下文开始
            output = self.runnable(*args, **kwargs)           # 行 159 ← 实际模型前向（被捕获）
    entry.aclgraph = aclgraph                                 # 行 181
    entry.output = weak_ref_tensors(output)                   # 行 180
    return output                                             # 行 188
```

**初始化预热捕获（Warmup Capture）**：
- **文件**：`vllm-ascend/vllm_ascend/worker/worker.py`
- **函数**：`NPUWorker.compile_or_warm_up_model()`
- **触发图捕获**：行 498 `self.model_runner.capture_model()`

- **文件**：`vllm-ascend/vllm_ascend/worker/model_runner_v1.py`
- **函数**：`NPUModelRunner.capture_model()`
- **委托捕获**：行 3708-3712

- **文件**：`vllm/vllm/v1/worker/gpu_model_runner.py`
- **函数**：`GPUModelRunner._warmup_and_capture()`
- **预热后捕获**：行 6124

#### 5.2.2 图重放（Replay）

**运行时重放**：
- **文件**：`vllm-ascend/vllm_ascend/compilation/acl_graph.py`
- **函数**：`ACLGraphWrapper.__call__()`
- **重放分支入口**：行 190
- **流同步**：行 211 `torch.npu.current_stream().synchronize()`
- **图重放**：行 212 `entry.aclgraph.replay()` ← **核心重放操作**
- **返回缓存输出**：行 213 `return entry.output`

```python
# acl_graph.py:190-213
logger.info_once("Replaying aclgraph")                       # 行 199
if not self.enable_enpu and not is_draft_eagle:
    torch.npu.current_stream().synchronize()                 # 行 211
entry.aclgraph.replay()                                      # 行 212 ← 图重放
return entry.output                                          # 行 213
```

#### 5.2.3 Forward Context 设置位置

**forward_context 的 `cudagraph_runtime_mode` 和 `batch_descriptor` 在以下位置被传入**：

- **文件**：`vllm-ascend/vllm_ascend/ascend_forward_context.py`
- **函数**：`set_ascend_forward_context()`
- **Context 设置入口**：行 57-85

- **文件**：`vllm-ascend/vllm_ascend/worker/model_runner_v1.py`
- **函数**：`NPUModelRunner.execute_model()`
- **实际传入 mode 和 descriptor**：行 1678-1679

```python
# model_runner_v1.py:1671-1694
with set_ascend_forward_context(
    attn_metadata,
    self.vllm_config,
    num_tokens=num_tokens_padded,                              # 行 1676
    num_tokens_across_dp=num_tokens_across_dp,                 # 行 1677
    aclgraph_runtime_mode=cudagraph_mode,                      # 行 1678 ← 传递 cudagraph_mode
    batch_descriptor=batch_desc,                               # 行 1679 ← 传递 batch_descriptor
    # ...
):
    hidden_states = self._model_forward(...)                   # 行 1692
```

#### 5.2.4 模型被包装为 ACLGraphWrapper 的位置

- **文件**：`vllm-ascend/vllm_ascend/worker/model_runner_v1.py`
- **函数**：`NPUModelRunner.load_model()`
- **FULL 模式包装**：行 2951

```python
# model_runner_v1.py:2948-2957
if self.compilation_config.cudagraph_mode.has_full_cudagraphs():
    self.model = ACLGraphWrapper(                              # 行 2951
        self.model,
        self.vllm_config,
        runtime_mode=CUDAGraphMode.FULL,
        use_eagle=self.use_eagle,
        enable_enpu=self.enable_enpu,
    )
```

### 5.3 边云场景下图编译的关键差异

**边云场景与常规 FULL 模式的核心差异**：

| 维度 | 常规 FULL 模式 | 边云 Decode 模式 |
|------|---------------|-----------------|
| 模型包装 | `load_model()` 中用单个 `ACLGraphWrapper` 包装**整个模型** | **不按 FULL 模式包装整个模型**；在 `EdgeModelRunner`/`CloudModelRunner` 中对**计算段**分别创建 `ACLGraphWrapper` |
| 调用次数 | 一次 `self.model(...)` 完成整网前向 | 多次分段调用（Segment A → 通信 → Segment E） |
| 通信位置 | 无跨节点通信 | 计算段之间插入 `send_hidden`/`recv_hidden`（图外 Eager） |
| Graph 中断 | 无中断 | 通信自然成为图中断点 |

### 5.4 基于分段 ACLGraphWrapper 的 Decode 设计

边云场景下，不在 `load_model()` 阶段用单个 `ACLGraphWrapper` 包装整个模型，而是将模型拆分为多个计算段，每段独立使用 `ACLGraphWrapper`：

```python
# vllm_ascend/worker/edge_cloud_model_runner.py

class EdgeModelRunner(NPUModelRunner):
    """Edge 侧执行流程"""

    def execute_model(self, scheduler_output, ...):
        """统一入口：Prefill 和 Decode 均通过重写 _model_forward 实现分段执行。"""
        return super().execute_model(scheduler_output, ...)

    def _model_forward(self, num_tokens_padded, input_ids, positions, ...):
        """重写 _model_forward，Prefill 和 Decode 均执行分段计算。"""
        forward_context = get_forward_context()
        assert forward_context is not None

        if forward_context.cudagraph_runtime_mode == CUDAGraphMode.NONE:
            # ==================== Prefill 分段执行（Eager）===================
            return self._prefill_forward(input_ids, positions)

        # ==================== Decode 分段执行（Graph）===================
        # --- Segment A: Embedding + Layers 0~K-1 (Graph) ---
        hidden_states, residual = self.segment_a_wrapper(
            input_ids, positions)
        # 首次: acl_graph.py:130-188 捕获
        # 后续: acl_graph.py:211-212 重放

        hidden_states = self._postprocess_hidden(hidden_states)

        # --- 图外通信：发送 (hidden_states, residual) 到 Cloud ---
        self.transfer.send_hidden('d', hidden_states, residual=residual)
        self.ctrl_comm.send_decode()

        # --- 图外通信：接收 Cloud 回传的中间状态 ---
        recv_hidden, recv_residual = self.transfer.recv_hidden('d', expected_shape)

        # 关键：重置 layer_idx，使 weight_prefetch 定位到尾段起始层
        ascend_ctx = get_ascend_forward_context()
        if ascend_ctx is not None:
            ascend_ctx.layer_idx = self.num_layers - self.k

        # --- Segment E: Layers N-K~N-1 + Norm (Graph) ---
        hidden_states = self.segment_e_wrapper(
            recv_hidden, recv_residual, positions)
        # 首次: acl_graph.py:130-188 捕获
        # 后续: acl_graph.py:211-212 重放

        # 返回 hidden_states（父类 compute_logits 计算 logits）
        return hidden_states
```

```python
class CloudModelRunner(NPUModelRunner):
    """Cloud 侧执行流程"""

    def execute_model(self, scheduler_output, ...):
        """根据 is_prefill 分发到 Prefill 或 Decode 处理。"""
        if scheduler_output.is_prefill:
            return self._execute_cloud_prefill(scheduler_output, ...)
        return self._execute_cloud_decode(scheduler_output, ...)

    def _execute_cloud_decode(self, scheduler_output, ...):
        """Cloud Decode：接收 → Graph 计算 → 发送"""

        # --- 图外通信：接收 Edge 发来的 (hidden_states, residual) ---
        recv_hidden, recv_residual = self.transfer.recv_hidden('d', None)

        # --- Segment C: Layers K ~ N-K-1 (Graph) ---
        with set_ascend_forward_context(
            attn_metadata,
            self.vllm_config,
            aclgraph_runtime_mode=CUDAGraphMode.FULL,
            batch_descriptor=self._get_decode_batch_descriptor(
                scheduler_output.num_tokens),
        ):
            hidden_states, residual = self.segment_c_wrapper(
                recv_hidden, recv_residual, position_ids)
            # 首次: acl_graph.py:130-188 捕获
            # 后续: acl_graph.py:211-212 重放

        hidden_states = self._postprocess_hidden(hidden_states)

        # --- 图外通信：发送 (hidden_states, residual) 回 Edge ---
        self.transfer.send_hidden('d', hidden_states, residual=residual)
        self.ctrl_comm.send_decode()
```


### 5.6 PIECEWISE 模式兼容

```python
# platform.py 边云场景编译配置

def _configure_edge_cloud_compilation(vllm_config: VllmConfig):
    """边云场景的编译配置（v3）"""
    compilation_config = vllm_config.compilation_config
    ascend_config = get_ascend_config()

    if not ascend_config.edge_cloud_config.enabled:
        return

    # 边云场景支持 PIECEWISE 或 FULL_AND_PIECEWISE
    if compilation_config.cudagraph_mode not in (
        CUDAGraphMode.PIECEWISE,
        CUDAGraphMode.FULL_AND_PIECEWISE,
    ):
        compilation_config.cudagraph_mode = CUDAGraphMode.PIECEWISE

    # 保持现有 splitting_ops 不变
    compilation_config.splitting_ops.extend(["vllm::mla_forward"])

    # 禁用 inductor
    compilation_config.use_inductor = False
    update_aclgraph_sizes(vllm_config)
    ascend_config.ascend_compilation_config.enable_npugraph_ex = False

    # v3 说明：边云模式下不全局禁用 ACL Graph。
    # Prefill 阶段通过 forward_context.cudagraph_runtime_mode = NONE 跳过 Graph。
    # Decode 计算段通过分段 ACLGraphWrapper 手动控制 Graph 启用/禁用。
```

### 5.7 图执行时序保证

```
Edge 侧 Decode 时序:
时间轴:  T0          T1          T2          T3          T4
         │           │           │           │           │
         ▼           ▼           ▼           ▼           ▼
    ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
    │ Segment │ │ Send    │ │ Recv    │ │ Segment │ │ Logits  │
    │ A       │ │ (Eager) │ │ (Eager) │ │ E       │ │         │
    │ (Graph) │ │         │ │         │ │ (Graph) │ │         │
    └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘
         ↑ acl_graph.py:212      ↑ acl_graph.py:212
         | 或 130-188            | 或 130-188

Cloud 侧 Decode 时序:
时间轴:  T0          T1          T2          T3
         │           │           │           │
         ▼           ▼           ▼           ▼
    ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
    │ Recv    │ │ Segment │ │ Send    │ │ Logits  │
    │ (Eager) │ │ C       │ │ (Eager) │ │         │
    │         │ │ (Graph) │ │         │ │         │
    └─────────┘ └─────────┘ └─────────┘ └─────────┘
                        ↑ acl_graph.py:212
                        | 或 130-188

Edge 侧 Prefill 时序:
时间轴:  T0          T1          T2          T3          T4
         │           │           │           │           │
         ▼           ▼           ▼           ▼           ▼
    ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
    │ Segment │ │ Send    │ │ Recv    │ │ Segment │ │ Logits  │
    │ A       │ │ (Eager) │ │ (Eager) │ │ E       │ │         │
    │ (Eager) │ │         │ │         │ │ (Eager) │ │         │
    └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘
         ↑ segment_a lambda      ↑ segment_e lambda

Cloud 侧 Prefill 时序:
时间轴:  T0          T1          T2          T3
         │           │           │           │
         ▼           ▼           ▼           ▼
    ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
    │ Recv    │ │ Segment │ │ Send    │ │ Logits  │
    │ (Eager) │ │ C       │ │ (Eager) │ │         │
    │         │ │ (Eager) │ │         │ │         │
    └─────────┘ └─────────┘ └─────────┘ └─────────┘
                        ↑ segment_c lambda
```

**关键保证**：
- `send_hidden` / `recv_hidden` 始终在 Eager 模式执行
- `ACLGraphWrapper.__call__` 仅在 `cudagraph_runtime_mode != NONE` 时触发 capture/replay
- 每个 Graph replay 完成后，通过 `torch.npu.current_stream().synchronize()`（acl_graph.py:211）确保时序，再执行通信

### 5.8 基于 Monkey Patch 的分段 forward 设计

> **核心思路**：通过 **Monkey Patch**（运行时动态绑定新方法）为 `LlamaModel` / `LlamaForCausalLM` 添加 `forward_edge_cloud_segment(start_layer, end_layer)` 方法，**不修改 vllm 源码**，也不创建独立的分段模块。
>
> vllm-ascend 本身已大量使用 Monkey Patch（如 `patch_qwen3_5.py` 中 `Qwen3_5DecoderLayer.forward = AscendQwen3_5DecoderLayer.forward`），因此这是与 vllm-ascend 工程实践一致的最佳方案。

#### 5.8.1 方案概述

核心思路：**在原模型中新增一个 `forward_edge_cloud_segment(start_layer, end_layer)` 方法，三段（A/C/E）都通过 `islice(self.layers, start, end)` 遍历指定层范围，层范围信息由调用方传入，支持灵活配置（如 Edge 侧加载首 2 层 + 尾 2 层）。**

#### 5.8.2 通过 Monkey Patch 添加分段方法

```python
# vllm_ascend/patch/models/llama_edge_cloud.py

from itertools import islice
from vllm.model_executor.models.llama import LlamaModel, LlamaForCausalLM


def _forward_edge_cloud_segment(
        self,
        start_layer: int,   # islice 起始索引（含）
        end_layer: int,     # islice 结束索引（不含）
        input_ids: torch.Tensor | None,
        positions: torch.Tensor,
        intermediate_tensors: IntermediateTensors | None = None,
        inputs_embeds: torch.Tensor | None = None,
        **extra_layer_kwargs,
    ) -> torch.Tensor | IntermediateTensors | tuple[torch.Tensor, list[torch.Tensor]]:
        """
        边云协同专用：通用分段 forward。
        三段（A/C/E）统一通过 islice(self.layers, start_layer, end_layer) 遍历。

        典型配置（K=1，首尾各 1 层）：
          Segment A: start=0,   end=1      → islice(layers, 0, 1)    → Layer 0
          Segment C: start=1,   end=N-1    → islice(layers, 1, N-1)  → Layers 1~N-2
          Segment E: start=N-1, end=N      → islice(layers, N-1, N)  → Layer N-1

        典型配置（K=2，首尾各 2 层）：
          Segment A: start=0, end=2        → islice(layers, 0, 2)    → Layers 0,1
          Segment C: start=2, end=N-2      → islice(layers, 2, N-2)  → Layers 2~N-3
          Segment E: start=N-2, end=N      → islice(layers, N-2, N)  → Layers N-2,N-1
        """
        num_layers = len(self.layers)
        assert 0 <= start_layer < end_layer <= num_layers

        # 判断当前分段是否是首段（需要 embed）
        is_first_segment = (start_layer == 0 and get_pp_group().is_first_rank)
        # 判断当前分段是否是尾段（需要 norm）
        is_last_segment = (end_layer == num_layers and get_pp_group().is_last_rank)

        # Embedding 或恢复中间状态
        if is_first_segment:
            if inputs_embeds is not None:
                hidden_states = inputs_embeds
            else:
                hidden_states = self.embed_input_ids(input_ids)
            residual = None
        else:
            assert intermediate_tensors is not None
            hidden_states = intermediate_tensors["hidden_states"]
            residual = intermediate_tensors["residual"]

        # 【核心】islice 遍历指定范围的层
        # Segment A: islice(0, K)       → Layers 0 ~ K-1
        # Segment C: islice(K, N-K)     → Layers K ~ N-K-1
        # Segment E: islice(N-K, N)     → Layers N-K ~ N-1
        for idx, layer in enumerate(
            islice(self.layers, start_layer, end_layer)
        ):
            hidden_states, residual = layer(
                positions, hidden_states, residual, **extra_layer_kwargs)

        # 如果不是尾段，返回中间状态给下一段/对端节点
        if not is_last_segment:
            return IntermediateTensors(
                {"hidden_states": hidden_states, "residual": residual})

        # 尾段做 norm，输出最终 hidden_states
        hidden_states, _ = self.norm(hidden_states, residual)
        return hidden_states
```

**设计要点**：
1. **零覆盖**：原有 `forward()` 完全保留，PP 逻辑不受影响
2. **三段统一 islice**：Segment A/C/E 都通过 `islice(self.layers, start, end)` 实现，结构完全对称
3. **层范围参数化**：`start_layer` / `end_layer` 由调用方传入，支持灵活配置（K=1, K=2 或任意）
4. **首/尾段自动判断**：`is_first_segment = (start_layer == 0 and is_first_rank)`，`is_last_segment = (end_layer == num_layers and is_last_rank)`，同时兼容 PP 状态
5. **返回类型**：非尾段返回 `IntermediateTensors`，尾段返回最终 `hidden_states`

#### 5.8.3 Monkey Patch 绑定 LlamaForCausalLM

```python
# vllm_ascend/patch/models/llama_edge_cloud.py
# （与 5.8.2 节同文件，追加以下代码）

def _llama_forward_edge_cloud_segment_wrapper(
    self,
    start_layer: int,
    end_layer: int,
    input_ids: torch.Tensor | None,
    positions: torch.Tensor,
    intermediate_tensors: IntermediateTensors | None = None,
    inputs_embeds: torch.Tensor | None = None,
) -> torch.Tensor | IntermediateTensors:
    """LlamaForCausalLM 透传至 LlamaModel"""
    return self.model.forward_edge_cloud_segment(
        start_layer, end_layer,
        input_ids, positions, intermediate_tensors, inputs_embeds
    )


# ── Monkey Patch：运行时动态绑定 ──
LlamaForCausalLM.forward_edge_cloud_segment = _llama_forward_edge_cloud_segment_wrapper
```

**Patch 加载入口**（在 vllm-ascend patch 初始化时自动加载）：

```python
# vllm_ascend/patch/worker/__init__.py
# 或 patch 统一加载逻辑中增加：

if get_ascend_config().edge_cloud_config.enabled:
    import vllm_ascend.patch.models.llama_edge_cloud  # noqa
```

> **其他模型适配**：Qwen、DeepSeek 等非 Llama 架构的模型，只需创建对应的 patch 文件（如 `qwen_edge_cloud.py`、`deepseek_edge_cloud.py`），定义 `_forward_edge_cloud_segment` 并 Monkey Patch 到对应模型类即可。所有模型的分段遍历核心都是统一的 `islice(self.layers, start_layer, end_layer)`。

#### 5.8.4 ModelRunner 适配（不复用分段模块，自定义加载流程）

**不再调用 `super().load_model()`**，而是自定义四阶段加载流程，实现加载时裁剪：

```python
# vllm_ascend/worker/edge_cloud_model_runner.py
from vllm.model_executor.model_loader import initialize_model, get_model_loader
from vllm.model_executor.model_loader.utils import process_weights_after_loading
from vllm.model_executor.models.utils import PPMissingLayer

class EdgeModelRunner(NPUModelRunner):
    def load_model(self) -> None:
        # 步骤1: 初始化模型（创建结构，不加载权重）
        model = initialize_model(
            vllm_config=self.vllm_config,
            model_config=self.model_config,
        )
        self.num_layers = len(model.model.layers)

        # 步骤2: 层裁剪 — 将非本侧层替换为 PPMissingLayer()
        # 关键：在 load_weights() 之前完成，使非本侧层权重直接跳过
        k = get_ascend_config().edge_cloud_config.edge_head_tail_layers
        LayerShardLoader.apply_sharding(model, EdgeCloudLayerPlan("edge", self.num_layers, k))

        # 步骤3: 加载权重 — AutoWeightsLoader 自动跳过 PPMissingLayer
        loader = get_model_loader(self.vllm_config.load_config)
        loader.load_weights(model, self.model_config)

        # 步骤4: 后处理
        process_weights_after_loading(model, self.model_config, self.device)

        # 步骤5: 配置分段参数
        self.k = k
        num_layers = self.num_layers

        # 【关键】不再创建 _SegmentAModule / _SegmentEModule
        # 直接用 lambda 包装原模型的 forward_edge_cloud_segment 方法
        self.segment_a = lambda input_ids, positions: \
            model.forward_edge_cloud_segment(
                0, self.k, input_ids, positions)

        self.segment_e = lambda hidden_states, residual, positions: \
            model.forward_edge_cloud_segment(
                num_layers - self.k, num_layers,
                None, positions,
                intermediate_tensors=IntermediateTensors({
                    "hidden_states": hidden_states,
                    "residual": residual,
                }))

        # 步骤6: ACLGraphWrapper 包装 lambda（callable）
        if self.compilation_config.cudagraph_mode.has_full_cudagraphs():
            from vllm_ascend.compilation.acl_graph import ACLGraphWrapper
            self.segment_a_wrapper = ACLGraphWrapper(
                self.segment_a, self.vllm_config,
                runtime_mode=CUDAGraphMode.FULL,
                use_eagle=self.use_eagle, enable_enpu=self.enable_enpu,
            )
            self.segment_e_wrapper = ACLGraphWrapper(
                self.segment_e, self.vllm_config,
                runtime_mode=CUDAGraphMode.FULL,
                use_eagle=self.use_eagle, enable_enpu=self.enable_enpu,
            )

        self.model = model

    def execute_model(self, scheduler_output):
        """统一入口：Prefill 和 Decode 均通过重写 _model_forward 实现分段执行。"""
        return super().execute_model(scheduler_output)

    def _model_forward(self, num_tokens_padded, input_ids, positions, ...):
        """重写 _model_forward，Prefill 和 Decode 均执行分段计算。"""
        forward_context = get_forward_context()
        assert forward_context is not None

        if forward_context.cudagraph_runtime_mode == CUDAGraphMode.NONE:
            # Prefill 分段执行（Eager）
            return self._prefill_forward(input_ids, positions)

        # Decode 分段执行（Graph）
        hidden_states, residual = self.segment_a_wrapper(
            input_ids, position_ids)
        self.transfer.send_hidden('d', hidden_states, residual=residual)
        self.ctrl_comm.send_decode()
        recv_hidden, recv_residual = self.transfer.recv_hidden('d', expected_shape)

        # 关键：重置 layer_idx
        ascend_ctx = get_ascend_forward_context()
        if ascend_ctx is not None:
            ascend_ctx.layer_idx = self.num_layers - self.k

        hidden_states = self.segment_e_wrapper(
            recv_hidden, recv_residual, position_ids)
        return hidden_states


class CloudModelRunner(NPUModelRunner):
    def load_model(self) -> None:
        # Cloud 侧同样自定义四阶段流程
        model = initialize_model(
            vllm_config=self.vllm_config,
            model_config=self.model_config,
        )
        self.num_layers = len(model.model.layers)

        k = get_ascend_config().edge_cloud_config.edge_head_tail_layers
        LayerShardLoader.apply_sharding(model, EdgeCloudLayerPlan("cloud", self.num_layers, k))

        loader = get_model_loader(self.vllm_config.load_config)
        loader.load_weights(model, self.model_config)
        process_weights_after_loading(model, self.model_config, self.device)

        self.k = k
        num_layers = self.num_layers

        # Segment C: islice(layers, k, N-k) → Layers k ~ N-k-1
        self.segment_c = lambda hidden_states, residual, positions: \
            model.forward_edge_cloud_segment(
                self.k, num_layers - self.k,
                None, positions,
                intermediate_tensors=IntermediateTensors({
                    "hidden_states": hidden_states,
                    "residual": residual,
                }))

        if self.compilation_config.cudagraph_mode.has_full_cudagraphs():
            from vllm_ascend.compilation.acl_graph import ACLGraphWrapper
            self.segment_c_wrapper = ACLGraphWrapper(
                self.segment_c, self.vllm_config,
                runtime_mode=CUDAGraphMode.FULL,
                use_eagle=self.use_eagle, enable_enpu=self.enable_enpu,
            )

        self.model = model

    def execute_model(self, scheduler_output):
        """根据 is_prefill 分发到 Prefill 或 Decode 处理。"""
        if scheduler_output.is_prefill:
            return self._execute_cloud_prefill(scheduler_output)
        return self._execute_cloud_decode(scheduler_output)

    def _execute_cloud_decode(self, scheduler_output):
        recv_hidden, recv_residual = self.transfer.recv_hidden('d', None)

        with set_ascend_forward_context(...):
            hidden_states, residual = self.segment_c_wrapper(
                recv_hidden, recv_residual, position_ids)

        self.transfer.send_hidden('d', hidden_states, residual=residual)
        self.ctrl_comm.send_decode()
```

#### 5.8.5 layer_idx 同步与 vllm-ascend 扩展特性兼容

**Cloud 侧（连续层 k~N-k-1）**：
- `set_ascend_forward_context` 初始化 `layer_idx = start_layer = k`
- `forward_edge_cloud_segment(k, N-k)` 内部 `islice(layers, k, N-k)` 遍历真实层
- 每层执行后 weight_prefetch 自动 `layer_idx += 1`
- **天然同步，无需额外处理**

**Edge 侧（非连续层 0~k-1 和 N-k~N-1）**：
- Segment A（`islice(0, k)`）执行后，`layer_idx` 被递增到 k
- 但下一跳是 Layer N-k，不是 Layer k
- **必须在 Segment E 执行前手动重置 `layer_idx = N-k`**（见 8.1 节 `_model_forward` / `_prefill_forward` 代码）
- 重置后 Segment E（`islice(N-k, N)`）执行时，weight_prefetch 访问 `model.layers[N-k]` ~ `model.layers[N-1]`，均为真实层

**EPLB / layer_shard_linear**：
- EPLB 增加 `PPMissingLayer` 跳过，layer_shard_linear Cloud 侧连续层正常工作

---

### 5.9 多模型适配方案（DeepSeek-V4 / Qwen3.5）

> 边云协同 Monkey Patch 方案（5.8 节）以标准 Llama 架构为基准设计，但实际接入的模型存在架构差异。本节分析 DeepSeek-V4 与 Qwen3.5 的关键差异，并给出适配方案。

#### 5.9.1 Qwen3.5 适配（另开专用实现）

**差异分析**：

Qwen3.5 的 `Qwen3NextDecoderLayer.forward` 签名为：
```python
def forward(self, hidden_states, residual, positions=None, **kwargs)
```

而标准 LlamaDecoderLayer 的签名为：
```python
def forward(self, positions, hidden_states, residual, **kwargs)
```

参数顺序不同：`hidden_states` 是第一个参数，`residual` 是第二个，`positions` 是第三个关键字参数。

> 虽然通过**关键字参数调用**（`layer(positions=..., hidden_states=..., residual=...)`）可以让同一段代码同时兼容 Llama 和 Qwen3.5，但为便于理解和学习，**另开一套专用实现** `qwen3_5_edge_cloud.py`，逻辑与 Llama 版完全相同，仅 layer 调用使用 Qwen3.5 原生的位置参数顺序。

**专用实现（`qwen3_5_edge_cloud.py`）**：

```python
def _forward_edge_cloud_segment_qwen3_5(...):
    # ... 逻辑与 Llama 版完全相同 ...
    for idx, layer in enumerate(islice(self.layers, start_layer, end_layer)):
        # Qwen3.5 原生位置参数顺序
        hidden_states, residual = layer(
            hidden_states, residual, positions, **extra_layer_kwargs)
    # ...
```

**加载入口**：

在 `patch/worker/__init__.py` 的边云 patch 加载逻辑中，通用 Llama patch 之后追加加载 Qwen3.5 专用 patch：

```python
# 通用 Patch（Llama / Qwen2 / DeepSeek-V2 / V3 等）
import vllm_ascend.patch.models.llama_edge_cloud

# Qwen3.5 专用 Patch（参数顺序不同，另开实现便于理解）
try:
    import vllm_ascend.patch.models.qwen3_5_edge_cloud
except Exception:
    pass
```

**占位层兼容性**：

`EdgeCloudMissingLayer.forward(positions, hidden_states, residual)` 使用位置参数。由于 Qwen3.5 调用时传入位置参数（但顺序不同），在专用实现中我们已经使用 Qwen3.5 原生的 `(hidden_states, residual, positions)` 顺序，占位层 `EdgeCloudMissingLayer` 的签名仍为标准顺序。

> 实际上 Qwen3.5 的占位层调用发生在 `EdgeModelRunner`/`CloudModelRunner` 中，这些 runner 已经通过 `convert_to_execution_layers` 将非本侧层替换为 `EdgeCloudMissingLayer`。`EdgeCloudMissingLayer.forward(positions, hidden_states, residual)` 按名绑定，因此 Qwen3.5 专用实现中 `layer(hidden_states, residual, positions)` 调用占位层时，Python 会按名称正确映射到 `EdgeCloudMissingLayer` 的形参。
>
> 为明确语义，也可以为 Qwen3.5 提供专用占位层 `Qwen3_5MissingLayer(hidden_states, residual, positions)`，但实际运行效果与 `EdgeCloudMissingLayer` 完全相同（仅参数顺序不同，返回值都是 `(hidden_states, residual)`）。

#### 5.9.2 DeepSeek-V4 适配（专用分段 forward + 通信扩展）

**差异分析**：

DeepSeek-V4 与标准 Transformer 存在多处架构差异，不能直接套用 5.8 节的通用分段 forward：

| 差异项 | 标准 Llama / Qwen / DS-V2/V3 | DeepSeek-V4 |
|--------|---------------------------|-------------|
| **DecoderLayer 签名** | `layer(positions, hidden_states, residual)` | `layer(x, positions, input_ids)` |
| **residual 传递** | 外部传递，层返回 `(hidden_states, residual)` | 内部通过 `hc_pre`/`hc_post` 管理，层只返回 `hidden_states` |
| **Embedding 后处理** | 直接送入第一层 | 需 `unsqueeze(-2).repeat(1, hc_mult, 1)` 扩展为 `[num_tokens, hc_mult, hidden_size]` |
| **尾层处理** | `self.norm(hidden_states, residual)` | `hc_head(...)` + `self.norm(hidden_states)` |
| **中间状态需携带** | `hidden_states` + `residual` | `hidden_states` + `input_ids`（Hash MoE routing 需要） |
| **占位层行为** | 返回 `(hidden_states, residual)` | 返回 `x`（单张量） |

**适配方案**：

1. **独立分段 forward**（`deepseek_v4_edge_cloud.py`）：
   - 为 `DeepseekV4Model` / `DeepseekV4ForCausalLM` 单独实现 `_forward_edge_cloud_segment_v4`，内部逻辑完全按照 V4 原 `forward` 实现：
     - 首段做 `embed_input_ids` + `unsqueeze` + `hc_mult` 扩展
     - 遍历层时调用 `layer(hidden_states, positions, input_ids)`
     - 非尾段返回 `IntermediateTensors({"hidden_states": ..., "input_ids": ...})`
     - 尾段执行 `hc_head` + `norm`
   - 同样通过 Monkey Patch 动态绑定到 `DeepseekV4Model` / `DeepseekV4ForCausalLM`

2. **专用占位层**（`DeepSeekV4MissingLayer`）：
   ```python
   class DeepSeekV4MissingLayer(nn.Module):
       def forward(self, x, positions, input_ids, **kwargs):
           return x
   ```
   `PPMissingLayer` 对 V4 恰好安全（`layer(x, positions, input_ids)` → 返回 `args[0] = x`），但为明确语义仍提供专用类。

3. **通信层扩展**（`HiddenStatesTransferHCCL`）：
   - `send_hidden` 增加 `input_ids: torch.Tensor | None = None` 参数
   - `recv_hidden` 增加 `input_ids_shape` / `recv_input_ids` 参数，返回三元组 `(hidden_states, residual, input_ids)`
   - 标准模型调用时 `input_ids=None`，不影响原有逻辑

4. **ModelRunner 模型类型分支**（`edge_cloud_model_runner.py`）：
   - `EdgeCloudModelRunnerBase.__init__` 中检测 `model_type == "deepseek_v4"`，设置 `self._is_deepseek_v4`
   - `load_model` 时根据标志创建不同签名的 segment lambda：
     - V4：`segment_e(hidden_states, input_ids, positions)`
     - 标准：`segment_e(hidden_states, residual, positions)`
   - `_prefill_forward` / `_model_forward` / `_execute_cloud_prefill` / `_execute_cloud_decode` 中按标志分支处理收发逻辑

**通信数据流（V4）**：

```
Edge Prefill/Decode:
  segment_a(input_ids, positions) → hidden_states
  send_hidden(stage, hidden_states, input_ids=input_ids)
  recv_hidden(stage, expected_shape, input_ids_shape=input_ids.shape)
    → recv_hidden, _, recv_input_ids
  segment_e(recv_hidden, recv_input_ids, positions) → hidden_states

Cloud Prefill/Decode:
  recv_hidden(stage, None, recv_input_ids=True)
    → recv_hidden, _, recv_input_ids
  segment_c(recv_hidden, positions, recv_input_ids) → result
  send_hidden(stage, hidden_states, input_ids=input_ids)
```

> **注意**：Cloud 侧 `_execute_cloud_prefill` 中 `recv_hidden` 的 `expected_shape` 为 `None`，`input_ids_shape` 在接收 `hidden_states` 之前未知。因此 `recv_hidden` 增加 `recv_input_ids: bool = False` 参数，当设为 `True` 时，在接收完 `hidden_states` 后自动按 `hidden_states.shape[0]` 推断并接收 `input_ids`。

---

### 5.10 dummy_run / profile_run 阶段独立图捕获

#### 问题背景

vLLM 启动阶段会通过 `worker.capture_model()` → `model_runner._dummy_run()` 遍历 `cudagraph_capture_sizes`，对每个 batch size 执行一次完整的前向，触发 `ACLGraphWrapper` 的 **Capture**。在边云协同架构下，这一流程会遇到以下阻塞风险：

1. **Edge 侧**：`segment_a_wrapper` Capture 后，会执行真实的 `send_hidden("d", ...)` 和 `recv_hidden("d", ...)`，阻塞等待 Cloud 侧响应。
2. **Cloud 侧**：`segment_c_wrapper` Capture 前，会执行真实的 `recv_hidden("d", ...)`，阻塞等待 Edge 侧发送。
3. **时序不一致**：Edge 与 Cloud 是两个独立进程，dummy_run 的触发时机可能不同步（如 Cloud 尚未启动、或已启动但 capture 不同 size）。HCCL/TCP 的同步 `send`/`recv` 会导致任意一方永久阻塞，最终启动失败。

#### 解决思路

利用 vLLM 已有的 `forward_context.in_profile_run` 标志（由 `set_ascend_forward_context(..., in_profile_run=True)` 在 dummy_run / profile_run 阶段设置），在 Edge 和 Cloud 的 ModelRunner 中检测该标志：

- **标志为 `True`**（dummy_run / profile_run）：跳过所有 HCCL/TCP 通信，用 `torch.zeros_like` 或 `torch.zeros` 在本地构造 dummy 中间状态，使各段 wrapper **独立 Capture**，互不影响。
- **标志为 `False`**（真实推理）：正常执行 `send_hidden` / `recv_hidden`，恢复边云协同。

ACL Graph 的 Capture 只记录 kernel 调用序列，不依赖数据内容。因此 dummy 数据的数值无关紧要，只要 **shape、device、dtype** 与真实场景一致即可。

#### 检测方法

在 `EdgeCloudModelRunnerBase` 中新增统一检测接口：

```python
def _is_dummy_or_profile_run(self) -> bool:
    """检测当前是否处于 dummy_run / profile_run / capture 阶段。"""
    forward_context = get_forward_context()
    if forward_context is None:
        return False
    return getattr(forward_context, "in_profile_run", False)
```

`EdgeModelRunner` 与 `CloudModelRunner` 均继承自 `EdgeCloudModelRunnerBase`，可直接复用。

#### Edge 侧修改（`_model_forward` Decode + `_prefill_forward` Prefill）

**标准模型（含 residual）Decode 示例**：

```python
def _model_forward(self, num_tokens_padded, input_ids, positions, ...):
    # ... segment_a_wrapper 执行 ...
    hidden_states = self._postprocess_hidden(hidden_states)

    if self._is_dummy_or_profile_run():
        # 跳过通信，本地 zeros 模拟 Cloud 回传
        recv_hidden = torch.zeros_like(hidden_states)
        recv_residual = torch.zeros_like(residual) if residual is not None else None
    else:
        self.transfer.send_hidden("d", hidden_states, residual=residual)
        self.ctrl_comm.send_decode()
        recv_hidden, recv_residual, _ = self.transfer.recv_hidden("d", hidden_states.shape)

    # layer_idx 重置仍需执行，否则 segment_e_wrapper 的 weight_prefetch 定位错误
    ascend_ctx = get_ascend_forward_context()
    if ascend_ctx is not None:
        ascend_ctx.layer_idx = self.num_layers - self.k

    hidden_states = self.segment_e_wrapper(recv_hidden, recv_residual, positions)
    return hidden_states
```

**DeepSeek-V4（含 input_ids）Prefill 示例**：

```python
def _prefill_forward(self, input_ids, positions):
    result = self.segment_a(input_ids, positions)
    hidden_states = result["hidden_states"]
    seg_input_ids = result["input_ids"]
    hidden_states = self._postprocess_hidden(hidden_states)

    if self._is_dummy_or_profile_run():
        recv_hidden = torch.zeros_like(hidden_states)
        recv_input_ids = torch.zeros_like(seg_input_ids)
    else:
        self.transfer.send_hidden("p", hidden_states, input_ids=seg_input_ids)
        self.ctrl_comm.send_prefill()
        recv_hidden, _, recv_input_ids = self.transfer.recv_hidden(
            "p", hidden_states.shape, input_ids_shape=seg_input_ids.shape
        )
        self.ctrl_comm.recv_prefill()

    # ... 重置 layer_idx ...
    hidden_states = self.segment_e(recv_hidden, recv_input_ids, positions)
    return hidden_states
```

#### Cloud 侧修改（`_execute_cloud_decode` + `_execute_cloud_prefill`）

Cloud 侧在 dummy_run 时同样需要跳过 `recv_hidden`（避免阻塞等待 Edge）和 `send_hidden`（避免阻塞等待 Edge 接收）。

**标准模型 Cloud Decode 示例**：

```python
def _execute_cloud_decode(self, scheduler_output, intermediate_tensors=None):
    num_scheduled_tokens = scheduler_output.total_num_scheduled_tokens
    batch_desc = self._get_decode_batch_descriptor(num_scheduled_tokens)
    is_dummy = self._is_dummy_or_profile_run()

    if not is_dummy:
        recv_hidden, recv_residual, _ = self.transfer.recv_hidden("d", None)
    else:
        device = self.device
        hidden_size = self.model_config.hidden_size
        recv_hidden = torch.zeros(
            num_scheduled_tokens, hidden_size, device=device, dtype=self.model_config.dtype
        )
        recv_residual = torch.zeros(
            num_scheduled_tokens, hidden_size, device=device, dtype=self.model_config.dtype
        )

    with set_ascend_forward_context(...):
        dummy_positions = torch.zeros(
            (recv_hidden.shape[0],), dtype=torch.int64, device=recv_hidden.device
        )
        result = self.segment_c_wrapper(recv_hidden, recv_residual, dummy_positions)
        hidden_states = result["hidden_states"]
        residual = result["residual"]

    hidden_states = self._postprocess_hidden(hidden_states)

    if not is_dummy:
        self.transfer.send_hidden("d", hidden_states, residual=residual)
        self.ctrl_comm.send_decode()

    return None
```

#### 关键保证

1. **layer_idx 重置不受影响**：dummy_run 时虽然跳过了通信，但 `ascend_ctx.layer_idx = self.num_layers - self.k` 仍必须在 `segment_e_wrapper` / `segment_c_wrapper` 执行前设置，否则 weight_prefetch 会定位到错误的层范围，导致 Capture 的 Graph 与真实推理不一致。

2. **Cloud 侧 attn_metadata 仍为 None**：dummy_run 时 Cloud 侧 `set_ascend_forward_context` 的 `attn_metadata` 参数仍为 `None`（与真实推理相同），因为 attention 的 KV cache 布局在 Cloud 侧尚未完全解决（见 5.7 节 TODO）。dummy_run 时数据内容不影响 Capture，因此当前方案安全。

3. **Graph 缓存 key 不变**：`batch_descriptor` 仍以 `num_tokens` 为 key。dummy_run 时 `num_scheduled_tokens` 来自 `cudagraph_capture_sizes`，与真实推理的 batch size 列表一致，因此 Capture 的 Graph 可在真实推理时直接 Replay。

#### 方案收益

- **启动解耦**：Edge 与 Cloud 可独立启动、独立执行 dummy_run，无需严格的启动时序对齐。
- **鲁棒性提升**：即使某一侧 crash 后重启，另一侧无需重新执行 dummy_run，直接恢复通信即可。
- **零额外依赖**：完全复用 vLLM 已有的 `in_profile_run` 标志，无需新增全局状态或环境变量。

---

### 5.11 非对称分片策略：首3尾1 方案设计

#### 问题背景

当前边云协同架构采用**对称分片**策略：`Edge` 侧保留首 `K` 层和尾 `K` 层，`Cloud` 侧保留中间 `N-2K` 层。该策略由单一配置项 `edge_head_tail_layers` 控制：

```yaml
edge_cloud_config:
  edge_head_tail_layers: 1   # Edge 保留 Layer 0 和 Layer N-1
```

对于 DeepSeek-V4，该策略存在以下问题：

1. **Hash MoE 的路由依赖**：V4 的前 3 层（`Layer 0~2`）使用 `DeepseekV4HashGate`，路由公式为 `expert_id = hash(token_id) % num_experts`。若 `K < 3`，`Cloud` 侧会包含 Hash 路由层，必须在边云间传递 `input_ids`。

2. **`input_ids` 的安全隐患**：`input_ids` 是原始文本的 token 化整数序列，`Cloud` 侧拥有 tokenizer 即可通过 `decode(input_ids)` 还原原始输入。在医疗、金融、政企等隐私敏感场景下，这是不可接受的。

3. **尾层的功能冗余**：V4 的尾段需要执行 `hc_head + norm + prediction_head`，这些操作绑定在最后一层（`Layer N-1`）。尾 3 层相比尾 1 层仅多出两层标准 Transformer 计算，对功能完整性没有本质提升。

#### 核心思路

**将对称分片扩展为非对称分片**：
- **首层数 `head_k`**：大于默认的 1，确保覆盖所有 Hash 路由层（`head_k ≥ 3`）
- **尾层数 `tail_k`**：保持为 1，因为尾 1 层已包含全部必需的输出组件

```
对称 K=1:
  Edge: [Layer 0]              [Layer N-1]
  Cloud: [Layer 1] ... [Layer N-2]
            ↑ Hash 路由层在 Cloud，需要 input_ids

非对称 首3尾1:
  Edge: [Layer 0] [Layer 1] [Layer 2]          [Layer N-1]
           ↑ Hash 路由层全部在 Edge
  Cloud: [Layer 3] ... [Layer N-2]
            ↑ 全部是可学习路由，无需 input_ids
```

#### 收益与代价

| 维度 | 对称 K=1 | 非对称 首3尾1 | 差异 |
|------|---------|--------------|------|
| **Edge 加载层数** | 2 | 4 | +2 层 |
| **Edge 权重存储（Pro）** | ~31 GB | ~63 GB | +32 GB |
| **Edge 权重存储（Flash）** | ~8 GB | ~16 GB | +8 GB |
| **是否传递 `input_ids`** | ✅ 需要 | ❌ 不需要 | **安全彻底解决** |
| **理论端到端延迟** | 309 ms | 309 ms | 不变（总层数不变） |
| **实际延迟（2卡 Edge）** | ~280 ms | ~316 ms | +13%（Edge 算力弱） |
| **Graph 规模（segment_a）** | 1 层 | 3 层 | 更大，但可编译 |
| **weight_prefetch 效率** | 低 | 高（3 层可流水线）| Edge 侧更优 |

#### 显存可行性分析

| 模型 | 配置 | 权重（FP4/FP8 混合） | 2×24GB | 2×32GB | 4×24GB |
|------|------|-------------------|--------|--------|--------|
| V4-Flash | 首3尾1 | ~16 GB | ✅ | ✅ | ✅ |
| V4-Pro | 首3尾1 | ~63 GB | ❌ | ❌ | ✅ |
| V4-Pro | 首2尾1 | ~47 GB | ⚠️ 临界 | ✅ | ✅ |

**结论**：
- V4-Flash 的 首3尾1 在 2×24GB 上非常宽松
- V4-Pro 的 首3尾1 需要 **4×24GB** 或 **2×32GB + 量化优化**
- V4-Pro 若只有 2×24GB，可退守 **首2尾1**（覆盖 2/3 Hash 层，部分改善安全）或配合 **Weight Offloading**

#### 详细代码修改设计

**修改 1：配置格式扩展（支持非对称 `[head, tail]`）**

```yaml
# vllm-ascend 配置文件 edge_cloud_config 部分
edge_cloud_config:
  enabled: true
  # 对称写法（向后兼容）
  # edge_head_tail_layers: 1
  # 非对称写法（推荐 V4 场景）
  edge_head_tail_layers: [3, 1]   # [首层数, 尾层数]
```

**修改 2：`EdgeCloudModelRunnerBase.__init__` 解析非对称 K**

```python
# vllm_ascend/worker/edge_cloud_model_runner.py
class EdgeCloudModelRunnerBase(NPUModelRunner):
    def __init__(self, vllm_config, device):
        super().__init__(vllm_config, device)
        # ...
        
        # 解析非对称分片配置
        head_tail_cfg = getattr(self.edge_cloud_cfg, "edge_head_tail_layers", 1)
        if isinstance(head_tail_cfg, (list, tuple)) and len(head_tail_cfg) == 2:
            self.head_k, self.tail_k = int(head_tail_cfg[0]), int(head_tail_cfg[1])
        else:
            self.head_k = self.tail_k = int(head_tail_cfg)
        
        # V4 专用：判断 Cloud 侧是否需要 input_ids
        # 若 head_k < 3，Cloud 包含 Hash 路由层，仍需传递 input_ids
        self._cloud_needs_input_ids = (
            self._is_deepseek_v4 and self.head_k < 3
        )
```

**修改 3：Edge 侧 segment lambda 定义**

```python
# EdgeModelRunner.load_model
# segment_a：首 head_k 层
self.segment_a = lambda input_ids, positions: \
    raw_model.forward_edge_cloud_segment(
        0, self.head_k, input_ids, positions)

# segment_e：尾 tail_k 层
self.segment_e = lambda hidden_states, input_ids, positions: \
    raw_model.forward_edge_cloud_segment(
        self.num_layers - self.tail_k, self.num_layers,
        input_ids, positions,
        intermediate_tensors=IntermediateTensors({
            "hidden_states": hidden_states,
            "input_ids": input_ids,
        }))
```

**修改 4：Cloud 侧 segment lambda 定义**

```python
# CloudModelRunner.load_model
if self._is_deepseek_v4:
    if self._cloud_needs_input_ids:
        # K < 3 时保留原有逻辑（fallback）
        self.segment_c = lambda hidden_states, positions, input_ids: \
            raw_model.forward_edge_cloud_segment(
                self.head_k, self.num_layers - self.tail_k,
                None, positions,
                intermediate_tensors=IntermediateTensors({
                    "hidden_states": hidden_states,
                    "input_ids": input_ids,
                }))
    else:
        # K >= 3 时，Cloud 不需要 input_ids
        self.segment_c = lambda hidden_states, positions: \
            raw_model.forward_edge_cloud_segment(
                self.head_k, self.num_layers - self.tail_k,
                None, positions,
                intermediate_tensors=IntermediateTensors({
                    "hidden_states": hidden_states,
                }))
```

**修改 5：`layer_idx` 重置逻辑（多处）**

原代码中所有 `self.num_layers - self.k` 需要改为 `self.num_layers - self.tail_k`：

```python
# _model_forward / _prefill_forward 中重置 layer_idx
ascend_ctx = get_ascend_forward_context()
if ascend_ctx is not None:
    ascend_ctx.layer_idx = self.num_layers - self.tail_k
```

**修改 6：V4 分段 forward 中 `input_ids` 改为可选**

```python
# vllm_ascend/patch/models/deepseek_v4_edge_cloud.py
# _forward_edge_cloud_segment_v4
if is_first_segment:
    hidden_states = self.embed_input_ids(input_ids)
    hidden_states = hidden_states.unsqueeze(-2).repeat(1, self.hc_mult, 1)
    if self.use_mega_moe:
        input_ids = input_ids.to(torch.int64)
else:
    hidden_states = intermediate_tensors["hidden_states"]
    # input_ids 改为可选：非首段、非 Hash 路由场景可能不需要
    input_ids = intermediate_tensors.get("input_ids")

# 层调用时条件传入
for idx, layer in enumerate(islice(self.layers, start_layer, end_layer)):
    if input_ids is not None:
        hidden_states = layer(hidden_states, positions, input_ids)
    else:
        # Cloud 侧 K>=3 时，学习路由层不需要 input_ids
        hidden_states = layer(hidden_states, positions)
```

**修改 7：通信层 `input_ids` 参数改为可选**

```python
# vllm_ascend/edge_cloud/hidden_states_transfer_hccl.py
class HiddenStatesTransferHCCL:
    def send_hidden(self, stage, hidden_states, residual=None, input_ids=None):
        """发送隐藏状态。input_ids 改为可选参数。"""
        # ...
        if input_ids is not None:
            self._send_tensor(input_ids, tag=f"{stage}_input_ids")

    def recv_hidden(self, stage, expected_shape, input_ids_shape=None, recv_input_ids=False):
        """接收隐藏状态。recv_input_ids 默认为 False。"""
        hidden_states = self._recv_tensor(expected_shape, tag=f"{stage}_hidden")
        residual = self._recv_tensor(expected_shape, tag=f"{stage}_residual") if ... else None
        input_ids = None
        if recv_input_ids and input_ids_shape is not None:
            input_ids = self._recv_tensor(input_ids_shape, tag=f"{stage}_input_ids")
        return hidden_states, residual, input_ids
```

**修改 8：Edge/Cloud 执行逻辑中的条件通信**

```python
# Edge 侧 _model_forward（Decode）
if self._is_deepseek_v4:
    hidden_states = self._postprocess_hidden(hidden_states)
    if self._cloud_needs_input_ids:
        self.transfer.send_hidden("d", hidden_states, input_ids=input_ids)
    else:
        self.transfer.send_hidden("d", hidden_states)
    self.ctrl_comm.send_decode()
    
    if self._cloud_needs_input_ids:
        recv_hidden, _, recv_input_ids = self.transfer.recv_hidden(
            "d", expected_shape, input_ids_shape=input_ids.shape)
    else:
        recv_hidden, _, _ = self.transfer.recv_hidden("d", expected_shape)
        recv_input_ids = None

# Cloud 侧 _execute_cloud_decode
if self._is_deepseek_v4:
    if not is_dummy:
        if self._cloud_needs_input_ids:
            recv_hidden, _, recv_input_ids = self.transfer.recv_hidden("d", None)
        else:
            recv_hidden, _, _ = self.transfer.recv_hidden("d", None)
            recv_input_ids = None
    else:
        # dummy_run zeros 构造...
        recv_input_ids = None
```

**修改 9：`EdgeCloudLayerPlan` 支持非对称裁剪**

```python
# vllm_ascend/model_loader/layer_shard_loader.py
class EdgeCloudLayerPlan:
    @staticmethod
    def plan(role: str, head_k: int, tail_k: int, num_layers: int):
        if role == "edge":
            return list(range(0, head_k)) + list(range(num_layers - tail_k, num_layers))
        else:
            return list(range(head_k, num_layers - tail_k))
```

#### Weight Offloading  Fallback（V4-Pro 2×24GB 场景）

若硬件仅支持 2×24GB 且无法升级，可采用 **CPU/NPU 混合存储 + 逐层换入**：

```
Edge 显存（48GB）:
  - 常驻：当前计算层权重（~16GB）
  - 预留：KV Cache + 激活 + Graph buffer（~8GB）
  - 可用：~40GB < 63GB（首3尾1 权重）

Edge CPU 内存（DDR, 512GB+）:
  - 存储全部 4 层权重（63GB）

执行流程（Prefill 阶段）:
  1. 从 CPU 换入 Layer 0 权重到 NPU
  2. 执行 Layer 0
  3. 换出 Layer 0，换入 Layer 1
  4. 执行 Layer 1
  ...

执行流程（Decode 阶段）:
  - 首次 decode 重复上述换入换出
  - 后续 decode 可将 4 层权重常驻 NPU（如果内存允许部分常驻）
```

**延迟影响**：
- Prefill 阶段：每层换入 ~16GB，H2D 带宽 ~10GB/s，+1.6s/层，4 层共 +6.4s（一次性）
- Decode 阶段：权重可常驻或部分预取，额外开销 < 50ms/步

#### 配置决策矩阵

| 部署场景 | 硬件 | 推荐配置 | 理由 |
|---------|------|---------|------|
| V4-Flash | 2×24GB | `edge_head_tail_layers: [3, 1]` | 显存充裕，安全彻底 |
| V4-Pro | 4×24GB | `edge_head_tail_layers: [3, 1]` | 显存充裕，安全彻底 |
| V4-Pro | 2×32GB | `edge_head_tail_layers: [3, 1]` + FP4 全量化 | 差 9GB，量化补足 |
| V4-Pro | 2×24GB | `edge_head_tail_layers: [3, 1]` + Weight Offloading | 显存不足，换入换出 |
| V4-Pro | 2×24GB（延迟敏感） | `edge_head_tail_layers: [2, 1]` + expert_ids 传递 | 临界显存，部分安全 |
| V4-Pro | 2×24GB（极致延迟） | `edge_head_tail_layers: 1` + Token 混淆 | 不增加延迟，安全缓解 |

#### 方案收益

- **安全性**：`head_k ≥ 3` 时彻底消除 `input_ids` 跨边云传输，Cloud 侧无法还原原始输入
- **通信简化**：省去 `input_ids` 传输通道，通信协议更干净
- **向后兼容**：对称写法 `edge_head_tail_layers: 1` 仍然有效，非对称写法则为列表 `[3, 1]`
- **灵活性**：不同模型、不同硬件可独立配置 `head_k` 和 `tail_k`，无需硬编码

---

## 6. 边云 ACL 场景数据流（重点）

### 6.1 从 vLLM 调度器到 Edge/Cloud ModelRunner 的通用调用链

```
[Engine 层]
vllm/vllm/v1/engine/core.py:401
  EngineCore.step()
    ├── vllm/vllm/v1/core/sched/scheduler.py:348
    │     Scheduler.schedule() → SchedulerOutput
    │
    └── vllm/vllm/v1/executor/abstract.py:221
          Executor.execute_model(scheduler_output, non_block=True)
            └── vllm/vllm/v1/executor/uniproc_executor.py:102
                  UniProcExecutor.execute_model()
                    └── vllm/vllm/v1/executor/uniproc_executor.py:67
                          UniProcExecutor.collective_rpc("execute_model", ...)
                            └── run_method(self.driver_worker, "execute_model", ...)
                                  ↓
[Worker 层]
vllm/vllm/v1/worker/worker_base.py:332
  WorkerWrapperBase.execute_model(scheduler_output)
    └── vllm-ascend/vllm_ascend/worker/worker.py:393
          NPUWorker.execute_model(scheduler_output)
            └── vllm-ascend/vllm_ascend/worker/model_runner_v1.py:1421
                  NPUModelRunner.execute_model(scheduler_output, intermediate_tensors)
                    └── EdgeModelRunner.execute_model()  (若 role=edge)
                    └── CloudModelRunner.execute_model() (若 role=cloud)
```

> **说明**：通用调用链到 `EdgeModelRunner.execute_model()` / `CloudModelRunner.execute_model()` 为止。此后，边侧和云侧各自独立执行，通过 HCCL/TCP 协同。以下 6.2 和 6.3 分别展示两侧各自的完整调用链。

### 6.2 Edge 侧完整调用链（Decode 阶段）

```
EdgeModelRunner.execute_model(scheduler_output)
  └── super().execute_model(scheduler_output)
        │ 复用父类输入准备、logits 计算和采样逻辑
        │ 仅 _model_forward 被重写为边云分段执行
        │ 文件: worker/edge_cloud_model_runner.py
        │
        ├── 1. 准备输入 tensors
        │   ├── input_ids  (从 CPU batch index_select 到 NPU)
        │   ├── position_ids
        │   └── attn_metadata
        │
        ├── 2. 构建 batch_descriptor
        │   └── _get_decode_batch_descriptor(num_tokens)
        │       └── BatchDescriptor(num_tokens_padded, is_flash_comm)
        │
        ├── 3. 设置 forward_context (Graph 模式)
        │   └── set_ascend_forward_context(
        │           aclgraph_runtime_mode=CUDAGraphMode.FULL,     ← 启用 Graph
        │           batch_descriptor=batch_desc                   ← 图缓存 key
        │       )
        │       文件: ascend_forward_context.py:57
        │       文件: forward_context.py:251
        │
        ├── 4. _model_forward 进入 Decode 分支（Graph 模式）
        │   └── Segment A: Embedding + Layers 0~K-1 (Graph)
        │       └── segment_a_wrapper(input_ids, position_ids)
        │           └── acl_graph.py:110  ACLGraphWrapper.__call__()
        │               ├── get_forward_context()
        │               ├── batch_descriptor = forward_context.batch_descriptor
        │               ├── aclgraph_runtime_mode = forward_context.cudagraph_runtime_mode
        │               │
        │               ├── 首次运行 (entry.aclgraph is None):
        │               │   ├── aclgraph = torch.npu.NPUGraph()        ← line 142
        │               │   ├── with torch.npu.graph(aclgraph, ...):   ← line 157
        │               │   │   output = self.runnable(...)            ← line 159
        │               │   │   # 实际执行 Embedding + Layers 0~K-1 前向，被图捕获
        │               │   ├── entry.aclgraph = aclgraph              ← line 181
        │               │   └── entry.output = weak_ref_tensors(output)← line 180
        │               │
        │               └── 后续运行:
        │                   ├── torch.npu.current_stream().synchronize()← line 211
        │                   └── entry.aclgraph.replay()                ← line 212
        │                       # 直接重放已捕获的 Embedding + Layers 0~K-1 图
        │
        ├── 5. 后处理
        │   └── maybe_gather_and_unpad_for_flashcomm(hidden_states)
        │   └── maybe_pad_and_gather_cross_dp_and_unpad(hidden_states)
        │
        ├── 6. [图外 Eager] 通信段 1: 发送 (hidden_states, residual) 到 Cloud
        │   ├── transfer.send_hidden('d', hidden_states, residual=residual)
        │   │   └── 文件: edge_cloud/hidden_states_transfer_hccl.py
        │   │       └── torch.distributed.send(...)  ← HCCL 集合通信
        │   └── ctrl_comm.send_decode()
        │       └── 文件: edge_cloud/edge_cloud_ctrl_comm.py
        │           └── TCPClient.send(...)  ← TCP 控制信号
        │
        ├── 7. [图外 Eager] 通信段 2: 接收 Cloud 回传的 (hidden_states, residual)
        │   └── recv_hidden, recv_residual = transfer.recv_hidden('d', expected_shape)
        │       └── 文件: edge_cloud/hidden_states_transfer_hccl.py
        │           └── torch.distributed.recv(...)  ← HCCL 集合通信
        │
        ├── 8. 重置 layer_idx = num_layers - K（关键）
        │   └── ascend_ctx.layer_idx = self.num_layers - self.k
        │
        ├── 9. Segment E: Layers N-K~N-1 + Norm (Graph)
        │   └── segment_e_wrapper(recv_hidden, recv_residual, position_ids)
        │       └── acl_graph.py:110  ACLGraphWrapper.__call__()
        │           ├── 首次: acl_graph.py:130-188  图捕获
        │           └── 后续: acl_graph.py:211-212  图重放
        │
        └── 10. 输出
            └── model.compute_logits(hidden_states)  →  logits
            └── 返回 logits
```

### 6.3 Cloud 侧完整调用链（Decode 阶段）

```
CloudModelRunner.execute_model(scheduler_output)
  └── _execute_cloud_decode(scheduler_output)
        │ 文件: worker/edge_cloud_model_runner.py
        │
        ├── 1. 准备输入 tensors
        │   ├── input_ids, position_ids, attn_metadata
        │
        ├── 2. 构建 batch_descriptor
        │   └── _get_decode_batch_descriptor(num_tokens)
        │
        ├── 3. [图外 Eager] 通信段 1: 接收 Edge 的 (hidden_states, residual)
        │   └── recv_hidden, recv_residual = transfer.recv_hidden('d', None)
        │       └── 文件: edge_cloud/hidden_states_transfer_hccl.py
        │           └── torch.distributed.recv(...)  ← HCCL 集合通信
        │
        ├── 4. 设置 forward_context (Graph 模式)
        │   └── set_ascend_forward_context(
        │           aclgraph_runtime_mode=CUDAGraphMode.FULL,
        │           batch_descriptor=batch_desc
        │       )
        │       文件: ascend_forward_context.py:57
        │       文件: forward_context.py:251
        │
        ├── 5. Segment C: Layers K ~ N-K-1 (Graph)
        │   └── segment_c_wrapper(recv_hidden, recv_residual, position_ids)
        │       └── acl_graph.py:110  ACLGraphWrapper.__call__()
        │           ├── get_forward_context()
        │           ├── batch_descriptor = forward_context.batch_descriptor
        │           ├── aclgraph_runtime_mode = forward_context.cudagraph_runtime_mode
        │           │
        │           ├── 首次运行 (entry.aclgraph is None):
        │           │   ├── aclgraph = torch.npu.NPUGraph()        ← line 142
        │           │   ├── with torch.npu.graph(aclgraph, ...):   ← line 157
        │           │   │   output = self.runnable(...)            ← line 159
        │           │   │   # 实际执行 Layers K~N-K-1 前向，被图捕获
        │           │   ├── entry.aclgraph = aclgraph              ← line 181
        │           │   └── entry.output = weak_ref_tensors(output)← line 180
        │           │
        │           └── 后续运行:
        │               ├── torch.npu.current_stream().synchronize()← line 211
        │               └── entry.aclgraph.replay()                ← line 212
        │                   # 直接重放已捕获的 Layers K~N-K-1 图
        │
        ├── 6. 后处理
        │   └── maybe_gather_and_unpad_for_flashcomm(hidden_states)
        │
        ├── 7. [图外 Eager] 通信段 2: 发送 (hidden_states, residual) 回 Edge
        │   ├── transfer.send_hidden('d', hidden_states, residual=residual)
        │   │   └── torch.distributed.send(...)  ← HCCL 集合通信
        │   └── ctrl_comm.send_decode()
        │       └── TCPClient.send(...)  ← TCP 控制信号
        │
        └── 8. 输出
            └── 返回 (hidden_states, residual) 给 Edge
```

### 6.4 Edge/Cloud Prefill 调用链（分段 Eager）

```
EdgeModelRunner._prefill_forward(input_ids, positions)
  └── 1. Segment A（Eager）
      └── self.segment_a(input_ids, positions)
          └── forward_edge_cloud_segment(0, K, ...)
              └── islice(self.layers, 0, K)  → Layers 0~K-1
                  └── embed_tokens + 首 K 层 Transformer
          └── return (hidden_states, residual)

  └── 2. [图外 Eager] 通信段 1: 发送 (hidden_states, residual) 到 Cloud
      └── transfer.send_hidden('p', hidden_states, residual=residual)
      └── ctrl_comm.send_prefill()

  └── 3. [图外 Eager] 通信段 2: 接收 Cloud 回传
      └── recv_hidden, recv_residual = transfer.recv_hidden('p', expected_shape)
      └── ctrl_comm.recv_prefill()

  └── 4. 重置 layer_idx（关键）
      └── ascend_ctx.layer_idx = num_layers - K

  └── 5. Segment E（Eager）
      └── self.segment_e(recv_hidden, recv_residual, positions)
          └── forward_edge_cloud_segment(N-K, N, ...)
              └── islice(self.layers, N-K, N)  → Layers N-K~N-1
                  └── 尾 K 层 Transformer + norm
          └── return hidden_states

  └── 6. 返回 hidden_states 给父类 compute_logits


CloudModelRunner._execute_cloud_prefill(scheduler_output)
  └── 1. [图外 Eager] 接收 Edge 的 (hidden_states, residual)
      └── recv_hidden, recv_residual = transfer.recv_hidden('p', None)
      └── ctrl_comm.recv_prefill()

  └── 2. Segment C（Eager）
      └── self.segment_c(recv_hidden, recv_residual, dummy_positions)
          └── forward_edge_cloud_segment(K, N-K, ...)
              └── islice(self.layers, K, N-K)  → Layers K~N-K-1
                  └── 中间层 Transformer
          └── return IntermediateTensors({"hidden_states": hs, "residual": res})

  └── 3. [图外 Eager] 发送结果回 Edge
      └── transfer.send_hidden('p', hidden_states, residual=residual)
      └── ctrl_comm.send_prefill()

  └── 4. 返回 None（Cloud 不计算 logits）
```

### 6.5 Edge 侧详细数据流（Decode 阶段）

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    Edge 侧 Decode 详细数据流                               │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  输入: scheduler_output (SchedulerOutput)                                 │
│     ├── num_scheduled_tokens: dict[str, int]                             │
│     ├── total_num_scheduled_tokens                                       │
│     └── is_prefill = False                                               │
│                                                                          │
│     ▼                                                                    │
│  EdgeModelRunner.execute_model(scheduler_output)                          │
│     │ 文件: worker/edge_cloud_model_runner.py                             │
│     ▼                                                                    │
│  super().execute_model(scheduler_output)                                  │
│     │ 复用父类输入准备、logits 计算和采样逻辑                               │
│     ▼                                                                    │
│  _model_forward(...) 进入 Decode 分支（cudagraph_runtime_mode=FULL）     │
│     │                                                                    │
│     ├── 1. 准备输入 tensors                                               │
│     │   ├── input_ids  (从 CPU batch index_select 到 NPU)                │
│     │   ├── position_ids                                                 │
│     │   └── attn_metadata                                                │
│     │                                                                    │
│     ├── 2. 构建 batch_descriptor                                          │
│     │   └── _get_decode_batch_descriptor(num_tokens)                     │
│     │       └── BatchDescriptor(num_tokens_padded, is_flash_comm)        │
│     │                                                                    │
│     ├── 3. 设置 forward_context (Graph 模式)                              │
│     │   └── set_ascend_forward_context(                                  │
│     │           aclgraph_runtime_mode=CUDAGraphMode.FULL,  ← 启用 Graph   │
│     │           batch_descriptor=batch_desc                 ← 图缓存 key  │
│     │       )                                                            │
│     │       文件: ascend_forward_context.py:57                            │
│     │       文件: forward_context.py:251                                  │
│     ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ Segment A: Embedding + Layers 0~K-1 (ACLGraphWrapper)              │ │
│  │                                                                    │ │
│  │ segment_a_wrapper(input_ids, position_ids)                         │ │
│  │   └── acl_graph.py:110  ACLGraphWrapper.__call__()                 │ │
│  │       ├── get_forward_context()                                    │ │
│  │       ├── batch_descriptor = forward_context.batch_descriptor      │ │
│  │       ├── aclgraph_runtime_mode = forward_context.cudagraph_      │ │
│  │       │   runtime_mode                                             │ │
│  │       │                                                            │ │
│  │       ├── 首次运行 (entry.aclgraph is None):                       │ │
│  │       │   ├── aclgraph = torch.npu.NPUGraph()        ← line 142   │ │
│  │       │   ├── with torch.npu.graph(aclgraph, ...):   ← line 157   │ │
│  │       │   │   output = self.runnable(...)            ← line 159   │ │
│  │       │   │   # 实际执行 Embedding + Layers 0~K-1 前向，被图捕获     │ │
│  │       │   ├── entry.aclgraph = aclgraph              ← line 181   │ │
│  │       │   └── entry.output = weak_ref_tensors(output)← line 180   │ │
│  │       │                                                            │ │
│  │       └── 后续运行:                                                │ │
│  │           ├── torch.npu.current_stream().synchronize()← line 211  │ │
│  │           └── entry.aclgraph.replay()               ← line 212   │ │
│  │               # 直接重放已捕获的 Embedding + Layers 0~K-1 图         │ │
│  │                                                                    │ │
│  │ 输出: (hidden_states_after_A, residual_after_A)                   │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│     ▼                                                                    │
│  maybe_gather_and_unpad_for_flashcomm(hidden_states)                      │
│  maybe_pad_and_gather_cross_dp_and_unpad(hidden_states)                   │
│     ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ [图外 Eager] 通信段 1: 发送 (hidden_states, residual) 到 Cloud      │ │
│  │                                                                    │ │
│  │ transfer.send_hidden('d', hidden_states, residual=residual)       │ │
│  │   └── 文件: edge_cloud/hidden_states_transfer_hccl.py               │ │
│  │       └── torch.distributed.send(...)  ← HCCL 集合通信             │ │
│  │                                                                    │ │
│  │ ctrl_comm.send_decode()                                            │ │
│  │   └── 文件: edge_cloud/edge_cloud_ctrl_comm.py                      │ │
│  │       └── TCPClient.send(...)  ← TCP 控制信号                      │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│     ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ [图外 Eager] 通信段 2: 接收 Cloud 回传结果                           │ │
│  │                                                                    │ │
│  │ recv_hidden, recv_residual = transfer.recv_hidden('d', expected_shape) │ │
│  │   └── 文件: edge_cloud/hidden_states_transfer_hccl.py               │ │
│  │       └── torch.distributed.recv(...)  ← HCCL 集合通信             │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│     ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ 重置 layer_idx = N-K（关键）                                        │ │
│  │ ascend_ctx.layer_idx = num_layers - K                               │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│     ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ Segment E: Layers N-K~N-1 + Norm (ACLGraphWrapper)                  │ │
│  │                                                                    │ │
│  │ segment_e_wrapper(recv_hidden, recv_residual, position_ids)       │ │
│  │   └── acl_graph.py:110  ACLGraphWrapper.__call__()                 │ │
│  │       ├── 首次运行: acl_graph.py:130-188  图捕获                   │ │
│  │       └── 后续运行: acl_graph.py:211-212  图重放                   │ │
│  │                                                                    │ │
│  │ 输出: hidden_states_after_norm (final hidden_states)               │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│     ▼                                                                    │
│  model.compute_logits(hidden_states)  →  logits                          │
│     ▼                                                                    │
│  返回 logits                                                              │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 6.6 Cloud 侧详细数据流（Decode 阶段）

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    Cloud 侧 Decode 详细数据流                              │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  输入: scheduler_output (SchedulerOutput)                                 │
│     └── is_prefill = False                                               │
│                                                                          │
│     ▼                                                                    │
│  CloudModelRunner.execute_model(scheduler_output)                         │
│     │ 文件: worker/edge_cloud_model_runner.py                             │
│     ▼                                                                    │
│  _execute_cloud_decode(scheduler_output)                                  │
│     │                                                                    │
│     ├── 1. 准备输入 tensors                                               │
│     │   ├── input_ids, position_ids, attn_metadata                       │
│     │                                                                    │
│     ├── 2. 构建 batch_descriptor                                          │
│     │   └── _get_decode_batch_descriptor(num_tokens)                     │
│     │                                                                    │
│     ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ [图外 Eager] 通信段 1: 接收 Edge 的 (hidden_states, residual)      │ │
│  │                                                                    │ │
│  │ recv_hidden, recv_residual = transfer.recv_hidden('d', None)       │ │
│  │   └── 文件: edge_cloud/hidden_states_transfer_hccl.py               │ │
│  │       └── torch.distributed.recv(...)                              │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│     ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ Segment C: Layers K ~ N-K-1 (ACLGraphWrapper)                      │ │
│  │                                                                    │ │
│  │ set_ascend_forward_context(aclgraph_runtime_mode=FULL, ...)        │ │
│  │                                                                    │ │
│  │ segment_c_wrapper(recv_hidden, recv_residual, position_ids)       │ │
│  │   └── acl_graph.py:110  ACLGraphWrapper.__call__()                 │ │
│  │       ├── 首次运行: acl_graph.py:130-188  图捕获                   │ │
│  │       │   line 142: torch.npu.NPUGraph()                           │ │
│  │       │   line 157: with torch.npu.graph(...):                     │ │
│  │       │   line 159: output = self.runnable(...)                    │ │
│  │       │   # 实际执行 Layers K~N-K-1 前向，被图捕获                   │ │
│  │       └── 后续运行: acl_graph.py:211-212 图重放                    │ │
│  │           line 211: torch.npu.current_stream().synchronize()       │ │
│  │           line 212: entry.aclgraph.replay()                        │ │
│  │                                                                    │ │
│  │ 输出: (hidden_states_after_C, residual_after_C)                    │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│     ▼                                                                    │
│  maybe_gather_and_unpad_for_flashcomm(hidden_states)                      │
│     ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ [图外 Eager] 通信段 2: 发送 (hidden_states, residual) 回 Edge        │ │
│  │                                                                    │ │
│  │ transfer.send_hidden('d', hidden_states, residual=residual)       │ │
│  │   └── torch.distributed.send(...)                                  │ │
│  │                                                                    │ │
│  │ ctrl_comm.send_decode()                                            │ │
│  │   └── TCPClient.send(...)                                          │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│     ▼                                                                    │
│  返回 (hidden_states, residual) 给 Edge                                   │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 6.7 Prefill 阶段数据流（Edge 与 Cloud）

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    Prefill 阶段数据流（分段 Eager）                         │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Edge 侧:                                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ EdgeModelRunner._prefill_forward(input_ids, positions)             │ │
│  │                                                                    │ │
│  │ 1. Segment A（Eager）                                              │ │
│  │    (hidden_states, residual) = segment_a(input_ids, positions)     │ │
│  │    # 执行 Embedding + Layers 0~K-1                                  │ │
│  │                                                                    │ │
│  │ 2. [图外 Eager] 发送 (hidden_states, residual) 到 Cloud            │ │
│  │    transfer.send_hidden('p', hidden_states, residual=residual)     │ │
│  │    ctrl_comm.send_prefill()                                        │ │
│  │                                                                    │ │
│  │ 3. [图外 Eager] 接收 Cloud 回传                                    │ │
│  │    (recv_hidden, recv_residual) = transfer.recv_hidden('p', ...)   │ │
│  │    ctrl_comm.recv_prefill()                                        │ │
│  │                                                                    │ │
│  │ 4. 重置 layer_idx = N-K                                            │ │
│  │                                                                    │ │
│  │ 5. Segment E（Eager）                                              │ │
│  │    hidden_states = segment_e(recv_hidden, recv_residual, positions)│ │
│  │    # 执行 Layers N-K~N-1 + Norm                                     │ │
│  │                                                                    │ │
│  │ 6. 返回 hidden_states（父类 compute_logits 计算 logits）            │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  Cloud 侧:                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ CloudModelRunner._execute_cloud_prefill(scheduler_output)          │ │
│  │                                                                    │ │
│  │ 1. [图外 Eager] 接收 Edge 的 (hidden_states, residual)             │ │
│  │    (recv_hidden, recv_residual) = transfer.recv_hidden('p', ...)   │ │
│  │    ctrl_comm.recv_prefill()                                        │ │
│  │                                                                    │ │
│  │ 2. Segment C（Eager）                                              │ │
│  │    result = segment_c(recv_hidden, recv_residual, dummy_positions) │ │
│  │    # 执行 Layers K~N-K-1                                            │ │
│  │    hidden_states = result["hidden_states"]                         │ │
│  │    residual = result["residual"]                                   │ │
│  │                                                                    │ │
│  │ 3. [图外 Eager] 发送结果回 Edge                                    │ │
│  │    transfer.send_hidden('p', hidden_states, residual=residual)     │ │
│  │    ctrl_comm.send_prefill()                                        │ │
│  │                                                                    │ │
│  │ 4. 返回 None（Cloud 不计算 logits）                                 │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 6.8 关键数据流转总结

| 阶段 | 数据形态 | 位置/传输方式 | 图/ Eager | 关键文件 |
|------|---------|-------------|-----------|---------|
| **Edge Decode Segment A** | input_ids → (hs_after_A, residual) | Edge NPU 本地计算 | **Graph** (capture/replay) | `acl_graph.py:110-213` |
| **Edge → Cloud 通信** | (hs_after_A, residual) | HCCL send / TCP ctrl signal | **Eager** (图外) | `hidden_states_transfer_hccl.py` |
| **Cloud Decode Segment C** | (hs_after_A, residual) → (hs_after_C, residual) | Cloud NPU 本地计算 | **Graph** (capture/replay) | `acl_graph.py:110-213` |
| **Cloud → Edge 通信** | (hs_after_C, residual) | HCCL send / TCP ctrl signal | **Eager** (图外) | `hidden_states_transfer_hccl.py` |
| **Edge Decode Segment E** | (hs_after_C, residual) → final_hs | Edge NPU 本地计算 | **Graph** (capture/replay) | `acl_graph.py:110-213` |
| **Edge Logits** | final_hs → logits | Edge NPU 本地计算 | **Eager** (lm_head 不参与 Graph) | `model.compute_logits()` |
| **Edge Prefill Segment A** | input_ids → (hs_after_A, residual) | Edge NPU 本地计算 | **Eager** (mode=NONE) | `segment_a lambda` |
| **Edge → Cloud 通信 (Prefill)** | (hs_after_A, residual) | HCCL send / TCP ctrl signal | **Eager** (图外) | `hidden_states_transfer_hccl.py` |
| **Cloud Prefill Segment C** | (hs_after_A, residual) → (hs_after_C, residual) | Cloud NPU 本地计算 | **Eager** (mode=NONE) | `segment_c lambda` |
| **Cloud → Edge 通信 (Prefill)** | (hs_after_C, residual) | HCCL send / TCP ctrl signal | **Eager** (图外) | `hidden_states_transfer_hccl.py` |
| **Edge Prefill Segment E** | (hs_after_C, residual) → final_hs | Edge NPU 本地计算 | **Eager** (mode=NONE) | `segment_e lambda` |
| **Edge Logits** | final_hs → logits | Edge NPU 本地计算 | **Eager** (lm_head 不参与 Graph) | `model.compute_logits()` |

---

### 6.9 边云协同完整流程图

```mermaid
flowchart TB
    subgraph Load["【1】模型分层加载"]
        direction TB
        L1[initialize_model] --> L2[apply_sharding]
        L2 --> L3[load_weights]
        L3 --> L4[process_weights_after_loading]
        L4 --> L5[convert_to_execution_layers]
    end

    subgraph EdgeLoad["Edge 侧"]
        E1[保留 0~K-1<br/>N-K~N-1]
    end

    subgraph CloudLoad["Cloud 侧"]
        C1[保留 K~N-K-1]
    end

    L5 --> EdgeLoad
    L5 --> CloudLoad

    subgraph Wrapper["【2】Wrapper 创建"]
        direction TB
        W1[segment_a<br/>forward_edge_cloud_segment<br/>0, K] --> W2[segment_e<br/>forward_edge_cloud_segment<br/>N-K, N]
        W2 --> W3[segment_c<br/>forward_edge_cloud_segment<br/>K, N-K]
        W3 --> W4[segment_a/e_wrapper<br/>ACLGraphWrapper]
        W4 --> W5[segment_c_wrapper<br/>ACLGraphWrapper]
    end

    EdgeLoad --> Wrapper
    CloudLoad --> Wrapper

    subgraph Runtime["【3】推理执行"]
        direction TB
        R1{Prefill /<br/>Decode?}

        R1 -->|Prefill<br/>Eager| P1[Edge: segment_a<br/>Embedding + Layers 0~K-1]
        P1 --> P2[Edge: send_hidden<br/>+ send_prefill]
        P2 --> P3[Cloud: recv_hidden<br/>+ recv_prefill]
        P3 --> P4[Cloud: segment_c<br/>Layers K~N-K-1]
        P4 --> P5[Cloud: send_hidden<br/>+ send_prefill]
        P5 --> P6[Edge: recv_hidden<br/>+ recv_prefill]
        P6 --> P7[Edge: segment_e<br/>Layers N-K~N-1 + hc_head + norm]

        R1 -->|Decode<br/>ACL Graph| D1[Edge: segment_a_wrapper<br/>Graph 捕获/重放]
        D1 --> D2[Edge: send_hidden<br/>+ send_decode]
        D2 --> D3[Cloud: recv_hidden<br/>+ recv_decode]
        D3 --> D4[Cloud: segment_c_wrapper<br/>Graph 捕获/重放]
        D4 --> D5[Cloud: send_hidden<br/>+ send_decode]
        D5 --> D6[Edge: recv_hidden<br/>+ recv_decode]
        D6 --> D7[Edge: segment_e_wrapper<br/>Graph 捕获/重放]
    end

    Wrapper --> Runtime

    subgraph Comm["【4】通信层"]
        direction LR
        HCCL[HCCL 数据面<br/>send_hidden / recv_hidden] --- TCP[TCP 控制面<br/>send_prefill / recv_decode]
    end

    P2 -.-> Comm
    P3 -.-> Comm
    P5 -.-> Comm
    P6 -.-> Comm
    D2 -.-> Comm
    D3 -.-> Comm
    D5 -.-> Comm
    D6 -.-> Comm

    subgraph Forward["【5】底层 Forward 调用"]
        direction TB
        F1[forward_edge_cloud_segment<br/>islice(self.layers, start, end)] --> F2[for layer in islice]
        F2 --> F3[layer(x, positions, input_ids)]
        F3 --> F4[return IntermediateTensors<br/>{hidden_states, input_ids}]
    end

    P1 -.-> Forward
    P4 -.-> Forward
    P7 -.-> Forward
    D1 -.-> Forward
    D4 -.-> Forward
    D7 -.-> Forward
```

---

## 7. 通信机制设计

### 7.1 设计原则

**直接参照 MindIE-LLM ATB 示例层的成熟实现**：
- 数据面：`EdgeCloudDataComm`（HCCL）→ 映射为 `HiddenStatesTransferHCCL`
- 控制面：`EdgeCloudCtrlComm`（TCP）→ 映射为 `EdgeCloudCtrlComm`
- 配置管理：`LwdCommunicationManager` → 映射为 `EdgeCloudManager`

### 7.2 HCCL 数据通信

```python
# edge_cloud/hidden_states_transfer_hccl.py
# 参照 MindIE-LLM ATB 示例 EdgeCloudDataComm

class HiddenStatesTransferHCCL(HiddenStatesTransfer):
    """HCCL 隐藏状态传输

    关键行为（参照 ATB 示例实现）：
    - send_hidden(stage, hidden_states): stage 为 'p'(prefill) 或 'd'(decode)
    - recv_hidden(stage, shape): 同步接收，按 shape 预分配 buffer
    - broadcast_hidden(tmp, shape, stage): TP 组内广播
    - init_hccl(): 基于 rank table 或环境变量初始化 HCCL 通信域
    - init_stream_cards(): 按 comm_group_size 初始化收发 stream 与卡号映射
    """
    
    def __init__(self, dtype=torch.bfloat16, batch_p_num=1):
        self.role = None          # "master"(edge) or "slave"(cloud)
        self.dtype = dtype
        self.init_finish = False
        self.prefill_seq_len_queue = queue.Queue()
        self.decode_batch_size_queue = queue.Queue()
        # ... 其他字段参照 ATB 示例 EdgeCloudDataComm
```

### 7.3 TCP 控制通信

```python
# edge_cloud/edge_cloud_ctrl_comm.py
# 参照 MindIE-LLM ATB 示例 EdgeCloudCtrlComm

class EdgeCloudCtrlComm:
    """TCP 控制通信

    关键行为（参照 ATB 示例实现）：
    - init_tcp_link(rank, role, server_ip, server_port): 初始化 TCP 连接
    - send_prefill() / recv_prefill(): Prefill 完成信号
    - send_decode() / recv_decode(): Decode 完成信号
    - shape_to_msg(shape) / msg_to_shape(msg): shape 信息序列化
    - 支持 TLS 加密（可选）
    """
    
    def __init__(self, tls_config: dict):
        self.tls_enable = tls_config.get("tls_enable", '0') == '1'
        # ... 其他字段参照 ATB 示例 EdgeCloudCtrlComm
```

### 7.4 配置管理

```python
# edge_cloud/manager.py
# 参照 MindIE-LLM LwdCommunicationManager

class EdgeCloudManager:
    """边云协同生命周期管理

    负责：
    - 解析 edge_cloud_config（role、IP、port、rank table 等）
    - 初始化 TCP 控制链路（ctrl_comm.init_tcp_link）
    - 初始化 HCCL 数据链路（data_comm.init_hccl）
    - warmup HCCL 通信（data_comm.hccl_comm_warmup）
    """
    
    def __init__(self, vllm_config):
        self.cfg = get_ascend_config().edge_cloud_config
        self.ctrl_comm = EdgeCloudCtrlComm(tls_config={})
        self.data_comm = HiddenStatesTransferHCCL(
            dtype=self.cfg.hidden_dtype, batch_p_num=1)
        
    def initialize(self):
        # 参照 LwdCommunicationManager.communication_init 流程
        self.ctrl_comm.init_tcp_link(...)
        self.data_comm.init_hccl()
        self.data_comm.hccl_comm_warmup(hidden_size)
```

---

## 8. 模型执行器设计

### 8.1 EdgeModelRunner

```python
class EdgeModelRunner(NPUModelRunner):
    """边侧模型执行器

    模型加载与分层裁剪的详细设计见 5.8 节。
    本节只展示执行阶段的代码。
    """

    def __init__(self, vllm_config, ...):
        super().__init__(vllm_config, ...)
        self.edge_cloud_cfg = get_ascend_config().edge_cloud_config
        self.edge_cloud_mgr = EdgeCloudManager(vllm_config)
        self.edge_cloud_mgr.initialize()

    def execute_model(self, scheduler_output, ...):
        """统一入口：Prefill 和 Decode 均通过 _model_forward 分段执行。"""
        return super().execute_model(scheduler_output, ...)

    def _prefill_forward(self, input_ids, positions):
        """Prefill：分段 Eager（Segment A → 通信 → Segment E）

        Prefill 阶段形状多变，不适合图编译，因此各段均走 Eager 路径。
        执行流程与 Decode 相同，仅将 Graph wrapper 替换为底层 lambda。
        """
        # --- Segment A: Embedding + Layers 0~K-1 (Eager) ---
        hidden_states, residual = self.segment_a(input_ids, positions)
        hidden_states = self._postprocess_hidden(hidden_states)

        # --- 图外通信：发送 (hidden_states, residual) 到 Cloud ---
        self.transfer.send_hidden('p', hidden_states, residual=residual)
        self.ctrl_comm.send_prefill()

        # --- 图外通信：接收 Cloud 回传的中间状态 ---
        recv_hidden, recv_residual = self.transfer.recv_hidden('p', expected_shape)
        self.ctrl_comm.recv_prefill()

        # 关键：重置 layer_idx，使 weight_prefetch 定位到尾段起始层
        ascend_ctx = get_ascend_forward_context()
        if ascend_ctx is not None:
            ascend_ctx.layer_idx = self.num_layers - self.k

        # --- Segment E: Layers N-K~N-1 + Norm (Eager) ---
        hidden_states = self.segment_e(
            recv_hidden, recv_residual, positions)

        # 返回 hidden_states 给父类 compute_logits
        return hidden_states

    def _model_forward(self, num_tokens_padded, input_ids, positions, ...):
        """重写 _model_forward，Prefill 和 Decode 均执行分段计算。"""
        forward_context = get_forward_context()
        assert forward_context is not None

        if forward_context.cudagraph_runtime_mode == CUDAGraphMode.NONE:
            # ==================== Prefill 分段执行（Eager）===================
            return self._prefill_forward(input_ids, positions)

        # ==================== Decode 分段执行（Graph）===================
        # --- Segment A: Embedding + Layers 0~K-1 (Graph) ---
        hidden_states, residual = self.segment_a_wrapper(
            input_ids, positions)
        # 首次: acl_graph.py:130-188 捕获
        # 后续: acl_graph.py:211-212 重放

        hidden_states = self._postprocess_hidden(hidden_states)

        # --- 图外通信：发送 (hidden_states, residual) 到 Cloud ---
        self.transfer.send_hidden('d', hidden_states, residual=residual)
        self.ctrl_comm.send_decode()

        # --- 图外通信：接收 Cloud 回传的中间状态 ---
        recv_hidden, recv_residual = self.transfer.recv_hidden('d', expected_shape)

        # 关键：重置 layer_idx，使 weight_prefetch 定位到尾段起始层
        ascend_ctx = get_ascend_forward_context()
        if ascend_ctx is not None:
            ascend_ctx.layer_idx = self.num_layers - self.k

        # --- Segment E: Layers N-K~N-1 + Norm (Graph) ---
        hidden_states = self.segment_e_wrapper(
            recv_hidden, recv_residual, positions)
        # 首次: acl_graph.py:130-188 捕获
        # 后续: acl_graph.py:211-212 重放

        # 返回 hidden_states（父类 compute_logits 计算 logits）
        return hidden_states
```

### 8.2 CloudModelRunner

```python
class CloudModelRunner(NPUModelRunner):
    """云侧模型执行器

    模型加载与分层裁剪的详细设计见 5.8 节。
    本节只展示执行阶段的代码。
    """

    def __init__(self, vllm_config, ...):
        super().__init__(vllm_config, ...)
        self.edge_cloud_cfg = get_ascend_config().edge_cloud_config
        self.edge_cloud_mgr = EdgeCloudManager(vllm_config)
        self.edge_cloud_mgr.initialize()

    def execute_model(self, scheduler_output, ...):
        if scheduler_output.is_prefill:
            return self._execute_cloud_prefill(scheduler_output)
        else:
            return self._execute_cloud_decode(scheduler_output)

    def _execute_cloud_prefill(self, scheduler_output):
        """Cloud Prefill：接收 → Eager 计算 → 发送"""
        # --- 图外通信：接收 Edge 发来的 (hidden_states, residual) ---
        recv_hidden, recv_residual = self.transfer.recv_hidden('p', None)
        self.ctrl_comm.recv_prefill()

        # --- Segment C: Layers K ~ N-K-1 (Eager) ---
        dummy_positions = torch.zeros(
            (recv_hidden.shape[0],), dtype=torch.int64, device=recv_hidden.device)
        result = self.segment_c(recv_hidden, recv_residual, dummy_positions)
        hidden_states = result["hidden_states"]
        residual = result["residual"]

        # --- 图外通信：发送 (hidden_states, residual) 回 Edge ---
        self.transfer.send_hidden('p', hidden_states, residual=residual)
        self.ctrl_comm.send_prefill()

    def _execute_cloud_decode(self, scheduler_output):
        """Cloud Decode：接收 → Graph 计算 → 发送"""
        # --- 图外通信：接收 Edge 发来的 (hidden_states, residual) ---
        recv_hidden, recv_residual = self.transfer.recv_hidden('d', ...)

        # --- Segment C: Layers K ~ N-K-1 (Graph) ---
        with set_ascend_forward_context(
            aclgraph_runtime_mode=CUDAGraphMode.FULL,
            batch_descriptor=self._get_decode_batch_descriptor(...),
            ...
        ):
            hidden_states, residual = self.segment_c_wrapper(
                recv_hidden, recv_residual, position_ids)
            # 首次: acl_graph.py:130-188 捕获
            # 后续: acl_graph.py:211-212 重放

        hidden_states = self._postprocess_hidden(hidden_states)

        # --- 图外通信：发送 (hidden_states, residual) 回 Edge ---
        self.transfer.send_hidden('d', hidden_states, residual=residual)
        self.ctrl_comm.send_decode()
```

---

## 9. 其他模块简要设计

### 9.1 模型加载辅助组件

#### 9.1.1 EdgeCloudLayerPlan（层分片策略）

```python
@dataclass
class EdgeCloudLayerPlan:
    """定义边云协同场景下各节点的层加载策略"""
    role: str  # "edge" or "cloud"
    total_layers: int
    k: int = 1  # Edge 侧首尾各保留 K 层

    def get_local_layers(self) -> set[int]:
        """返回本节点需要保留真实权重的层索引集合"""
        if self.role == "edge":
            return set(range(self.k)) | set(range(self.total_layers - self.k, self.total_layers))
        else:
            return set(range(self.k, self.total_layers - self.k))

    def get_released_layers(self) -> set[int]:
        """返回本节点可以释放权重的层索引集合"""
        all_layers = set(range(self.total_layers))
        return all_layers - self.get_local_layers()

    def validate(self):
        """验证层分片策略的合法性"""
        edge_layers = self.get_local_layers() if self.role == "edge" else \
                      set(range(self.k)) | set(range(self.total_layers - self.k, self.total_layers))
        cloud_layers = self.get_local_layers() if self.role == "cloud" else \
                       set(range(self.k, self.total_layers - self.k))
        # Edge 和 Cloud 的层集合应该互斥且覆盖全部
        assert edge_layers | cloud_layers == set(range(self.total_layers))
        assert edge_layers & cloud_layers == set()
```

#### 9.1.2 LayerShardLoader（层分片加载管理器）

```python
class LayerShardLoader:
    """层权重分片加载管理器（V3 加载时裁剪版）。

    核心职责：
    1. apply_sharding()：在 load_weights() 之前，将非本侧层替换为 PPMissingLayer
       使 AutoWeightsLoader 自动跳过这些层的权重加载。
    2. convert_to_execution_layers()：在 load_weights() 之后，将 PPMissingLayer
       替换为 EdgeCloudMissingLayer，确保 prefill 阶段遍历时安全透传。

    注意：V3 不再需要 release_layer_weights()，因为权重根本不会被加载。
    """

    @staticmethod
    def release_layer_weights(layer: nn.Module) -> None:
        """（v2 遗留方法，V3 不再调用）释放单个层的参数和 buffer。"""
        ...

    @classmethod
    def apply_sharding(cls, model, layer_plan):
        """对模型应用层分片策略（在 load_weights 之前调用）。

        执行流程：
        1. 非本地 Transformer 层替换为 PPMissingLayer
           AutoWeightsLoader._load_module() 遇到 PPMissingLayer 直接 return 跳过。
        2. Cloud 侧额外将 embed_tokens / norm / lm_head 替换为 PPMissingLayer
           使这些模块的权重也不会被加载。
        3. Edge 侧保留这些模块（用于 Embedding 和 Norm/LM Head 计算）。
        """
        num_layers = len(model.model.layers)
        local_layers = layer_plan.get_local_layers()

        # 1. 处理 Transformer 层
        for i in range(num_layers):
            if i not in local_layers:
                old_layer = model.model.layers[i]
                if isinstance(old_layer, (PPMissingLayer, EdgeCloudMissingLayer)):
                    continue
                model.model.layers[i] = PPMissingLayer()
                del old_layer

        # 2. Cloud 侧跳过 embed_tokens / norm / lm_head 的权重加载
        if layer_plan.role == "cloud":
            for module_name in ['embed_tokens', 'norm']:
                module = getattr(model.model, module_name, None)
                if module is not None and not isinstance(module, PPMissingLayer):
                    setattr(model.model, module_name, PPMissingLayer())
            if hasattr(model, 'lm_head') and model.lm_head is not None \
                    and not isinstance(model.lm_head, PPMissingLayer):
                model.lm_head = PPMissingLayer()

        logger.info(
            "[LayerShardLoader] Role=%s, kept_layers=%s, skipped_layers=%s",
            layer_plan.role, sorted(local_layers),
            sorted(layer_plan.get_released_layers()),
        )

    @classmethod
    def convert_to_execution_layers(cls, model):
        """将 PPMissingLayer 替换为 EdgeCloudMissingLayer（用于执行阶段）。

        调用时机：load_weights() 和 process_weights_after_loading() 之后。

        原因：
        - PPMissingLayer.forward(*args) 返回 args[0]，在 Transformer 层签名下
          会返回 positions，导致 prefill 遍历所有层时出错。
        - EdgeCloudMissingLayer.forward(positions, hidden_states, residual)
          返回 (hidden_states, residual)，可安全透传。
        """
        num_converted = 0
        for i, layer in enumerate(model.model.layers):
            if isinstance(layer, PPMissingLayer):
                model.model.layers[i] = EdgeCloudMissingLayer()
                num_converted += 1
        if num_converted > 0:
            logger.info(
                "[LayerShardLoader] Converted %d PPMissingLayers to "
                "EdgeCloudMissingLayers for safe prefill execution.",
                num_converted,
            )
```

#### 9.1.3 内存优化效果估算

以 `DeepSeek-R1`（61 层，hidden_size=7168）为例，不同 K 值下的内存占用：

> **关键改进**：V3 采用"加载时裁剪"方案，非本侧层的权重在 `load_weights()` 阶段直接被 `AutoWeightsLoader` 跳过，**不会加载到 NPU 显存中**。相比 v2 "先全量加载再释放"方案，Edge 侧权重加载峰值从 ~37B 降至 ~3.8B（K=1 时降低约 **95%**）。

**K=1（首1层 + 尾1层）：**

| 组件 | 参数量（每层） | Edge 保留 | Cloud 保留 | 是否加载 |
|------|-------------|-----------|------------|----------|
| Embedding | ~1.8B | ✅ | ❌ | 仅 Edge 加载 |
| Layer 0 | ~0.6B | ✅ | ❌ | 仅 Edge 加载 |
| Layers 1~59 | ~35.4B | ❌ | ✅ | 仅 Cloud 加载 |
| Layer 60 | ~0.6B | ✅ | ❌ | 仅 Edge 加载 |
| Norm + LM Head | ~1.8B | ✅ | ❌ | 仅 Edge 加载 |
| **Edge 侧总加载** | **~3.8B** | | | |
| **Cloud 侧总加载** | **~35.4B** | | | |

**K=2（首2层 + 尾2层）：**

| 组件 | 参数量（每层） | Edge 保留 | Cloud 保留 | 是否加载 |
|------|-------------|-----------|------------|----------|
| Embedding | ~1.8B | ✅ | ❌ | 仅 Edge 加载 |
| Layers 0~1 | ~1.2B | ✅ | ❌ | 仅 Edge 加载 |
| Layers 2~58 | ~34.2B | ❌ | ✅ | 仅 Cloud 加载 |
| Layers 59~60 | ~1.2B | ✅ | ❌ | 仅 Edge 加载 |
| Norm + LM Head | ~1.8B | ✅ | ❌ | 仅 Edge 加载 |
| **Edge 侧总加载** | **~6.0B** | | | |
| **Cloud 侧总加载** | **~34.2B** | | | |

**峰值内存对比（K=1，FP16/BF16）：**

| 方案 | Edge 侧峰值权重 | 峰值降低比例 | 说明 |
|------|----------------|-------------|------|
| v2（先全量加载再释放） | ~37B | 基准 | 全量加载后通过 `empty(0)` 释放，峰值仍达全量 |
| **V3（加载时裁剪）** | **~3.8B** | **~90%** | `PPMissingLayer` 使权重加载直接跳过 |

> 注：实际参数量取决于具体模型配置和量化策略。上表为 FP16/BF16 下的估算。
> Edge 侧 2 卡（每卡约 48GB）完全可容纳 K=1 的 ~3.8B 参数 + KV Cache，K=2 的 ~6.0B 也仍在容量范围内。

### 9.2 Worker 集成

```python
class NPUWorker(WorkerBase):
    def load_model(self):
        if self.vllm_config.edge_cloud_config.enabled:
            if self.vllm_config.edge_cloud_config.node_role == "edge":
                self.model_runner = EdgeModelRunner(self.vllm_config)
            else:
                self.model_runner = CloudModelRunner(self.vllm_config)
        else:
            self.model_runner = NPUModelRunner(self.vllm_config)
```

### 9.3 配置示例

```bash
# 边侧启动（K=1：首1层 + 尾1层）
vllm serve /path/to/model \
    --tensor-parallel-size 2 \
    --additional-config '{
        "edge_cloud_config": {
            "enabled": true,
            "role": "edge",
            "total_layers": 61,
            "edge_head_tail_layers": 1,
            "enable_decode_graph": true,
            "decode_graph_min_tokens": 1,
            "transfer_config": {
                "backend": "hccl",
                "peer_addrs": ["cloud-node-0:9010"]
            }
        }
    }'

# 边侧启动（K=2：首2层 + 尾2层）
vllm serve /path/to/model \
    --tensor-parallel-size 2 \
    --additional-config '{
        "edge_cloud_config": {
            "enabled": true,
            "role": "edge",
            "total_layers": 61,
            "edge_head_tail_layers": 2,
            "enable_decode_graph": true,
            "decode_graph_min_tokens": 1,
            "transfer_config": {
                "backend": "hccl",
                "peer_addrs": ["cloud-node-0:9010"]
            }
        }
    }'

# 云侧启动（K 值由 Edge 侧决定，Cloud 自动推导中间层范围）
vllm serve /path/to/model \
    --tensor-parallel-size 8 \
    --additional-config '{
        "edge_cloud_config": {
            "enabled": true,
            "role": "cloud",
            "total_layers": 61,
            "edge_head_tail_layers": 1,
            "enable_decode_graph": true,
            "transfer_config": {
                "backend": "hccl",
                "peer_addrs": ["edge-node-0:9010"]
            }
        }
    }'
```

---

## 10. 实现计划

### Phase 1: 通信框架（2周）

| 任务 | 描述 | 参照来源 |
|------|------|---------|
| T1.1 | 创建 `edge_cloud/` 目录结构 | - |
| T1.2 | 实现 `EdgeCloudCtrlComm` | **MindIE-LLM ATB 示例 `edge_cloud_ctrl_comm.py`** |
| T1.3 | 实现 `HiddenStatesTransferHCCL` | **MindIE-LLM ATB 示例 `edge_cloud_data_comm.py`** |
| T1.4 | 实现 `EdgeCloudManager` | **MindIE-LLM `LwdCommunicationManager`** |
| T1.5 | 添加 `EdgeCloudConfig` | v2 + `enable_decode_graph` |
| T1.6 | 实现 `LayerShardLoader` | v2 |

### Phase 2: 图编译与执行器（3周）

| 任务 | 描述 | 参照来源 |
|------|------|---------|
| T2.1 | 实现 `EdgeModelRunner`，含分段 `ACLGraphWrapper` | vllm-ascend `NPUModelRunner` + `ACLGraphWrapper` |
| T2.2 | 实现 `CloudModelRunner`，含分段 `ACLGraphWrapper` | 同上 |
| T2.3 | 修改 `NPUWorker` 根据 role 创建对应 ModelRunner | v2 |
| T2.4 | 确保 Decode Segment 触发 `acl_graph.py:130-188` 捕获 | `ACLGraphWrapper.__call__` 内置逻辑 |
| T2.5 | 确保通信段设置 `cudagraph_runtime_mode=NONE` 跳过 Graph | 自行设计 |
| T2.6 | 处理动态 shape：不同 `batch_descriptor` 的图缓存 | `ACLGraphWrapper` 内置能力 |

### Phase 3: 集成与测试（2周）

| 任务 | 描述 |
|------|------|
| T3.1 | 集成启动流程，端到端单卡/多卡测试 |
| T3.2 | 验证 Decode Segment 图捕获/重放正确性（确认 `acl_graph.py:130-188` 和 `212` 被触发） |
| T3.3 | 验证 HCCL 通信在图外执行，无死锁 |
| T3.4 | 性能基准：对比 Eager vs 分段 Graph 吞吐 |
| T3.5 | 异常处理：通信超时、shape 不匹配、对端断开 |

### Phase 4: 优化（1周）

| 任务 | 描述 |
|------|------|
| T4.1 | Cloud 侧含 `hidden_states` 输入的 Graph 捕获优化 |
| T4.2 | 微批流水线：边侧 Segment A 与上一批次 Segment E overlap |
| T4.3 | 通信压缩：hidden_states 量化/稀疏化传输 |

---

## 附录 A: 与 MindIE-LLM 的映射对照表

| MindIE-LLM 组件 | vllm-ascend v3 映射 | 状态 | 说明 |
|-----------------|-------------------|------|------|
| ATB 示例 `EdgeCloudDataComm` | `HiddenStatesTransferHCCL` | ✅ 可参照 | HCCL 数据通信成熟实现 |
| ATB 示例 `EdgeCloudCtrlComm` | `EdgeCloudCtrlComm` | ✅ 可参照 | TCP 控制通信成熟实现 |
| `LwdCommunicationManager` | `EdgeCloudManager` | ✅ 可参照 | 配置解析与初始化流程 |
| C++ `EdgeCloudPolicy` | vLLM 调度器扩展（未来） | ✅ 可参照 | P/D 调度策略 |
| C++ `LayerwiseMixin` | vLLM Worker 扩展（未来） | ✅ 可参照 | 批次状态机管理 |
| ATB `LayerwiseDecodeGraphWrapper` | `ACLGraphWrapper` + 分段 Segment Wrapper | ⚠️ 思想借鉴 | ATB 专用实现，不可直接映射；借鉴其"计算分段 + 通信解耦"思想 |
| ~~`ModelRunnerExp.forward_decode_with_graph`~~ | ~~`EdgeModelRunner._execute_decode`~~ | ❌ **已删除** | 该函数属于未验证实现，已从 MindIE-LLM 移除 |
| ~~`ModelRunnerExp._capture_decode_graph`~~ | ~~`ACLGraphWrapper.__call__`~~ | ❌ **已删除** | 同上；v3 使用 `ACLGraphWrapper` 内置捕获机制（`acl_graph.py:130-188`） |
| ~~4 份边云设计文档~~ | ~~v3 初版参照~~ | ❌ **已删除** | 文档与对应核心代码一同清理 |

## 附录 B: 关键文件清单

### 新增文件

```
vllm_ascend/
├── edge_cloud/
│   ├── __init__.py
│   ├── manager.py                        # EdgeCloudManager
│   ├── hidden_states_transfer.py         # HiddenStatesTransfer 抽象
│   ├── hidden_states_transfer_hccl.py    # HCCL 实现（参照 MindIE-LLM ATB 示例）
│   ├── edge_cloud_ctrl_comm.py           # TCP 控制通信（参照 MindIE-LLM ATB 示例）
└── worker/
    └── edge_cloud_model_runner.py        # EdgeModelRunner / CloudModelRunner
└── model_loader/
    └── layer_shard_loader.py             # LayerShardLoader
```

### 修改文件

```
vllm_ascend/
├── ascend_config.py                     # 新增 enable_decode_graph 等配置
├── platform.py                          # 更新编译配置逻辑
└── worker/
    └── worker.py                        # 根据 role 创建对应 ModelRunner
```

### 图编译关键文件（已有，需理解其机制）

```
vllm_ascend/
├── compilation/
│   └── acl_graph.py                     # ACLGraphWrapper: capture(130-188), replay(212)
├── ascend_forward_context.py            # set_ascend_forward_context(57)
└── worker/
    └── model_runner_v1.py               # execute_model(1421,1678-1679), load_model(2908-2957)
```
