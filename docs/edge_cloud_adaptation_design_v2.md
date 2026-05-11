# 边云协同场景 vLLM-Ascend 适配设计文档（第二版）

| 版本 | 日期 | 作者 | 描述 |
|------|------|------|------|
| 0.1 | 2026-04-28 | - | 初始版本 |
| 0.2 | 2026-04-28 | - | 第二版：修正图编译与通信架构设计，补充工程实现细节 |

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [边云场景分析](#2-边云场景分析)
3. [现有代码能力分析](#3-现有代码能力分析)
4. [架构设计](#4-架构设计)
5. [图编译详细设计](#5-图编译详细设计)
6. [通信机制设计](#6-通信机制设计)
7. [其他模块简要设计](#7-其他模块简要设计)
8. [实现计划](#8-实现计划)

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
│  - Embedding          │                                       │
│  - Transformer Layer 0 │   - Transformer Layer 1 ~ N-1         │
│  - Transformer Layer N │                                       │
│  - HiddenStates Send/  │   - HiddenStates Recv/Send             │
│    Recv                │                                       │
│  - Sampling            │                                       │
└───────────────────────┴─────────────────────────────────────────┘
         │                              │
         │    HiddenStates Transfer      │
         │    (Via RoCE/NIC)            │
         └──────────────────────────────┘
```

**边侧职责**：
- 加载 embedding 层和首尾 transformer 层（Layer 0 和 Layer N）
- 接收用户请求，进行 token embedding
- 执行 Layer 0 前向传播
- 发送 hidden_states 到云侧
- 接收云侧回来的 hidden_states
- 执行 Layer N 前向传播
- 执行 sampling 输出

**云侧职责**：
- 加载中间所有 transformer 层（Layer 1 ~ N-1）
- 接收边侧 hidden_states
- 执行中间层前向传播
- 发送 hidden_states 回边侧

### 1.2 设计目标

1. **图编译适配**：确保边侧和云侧的 PIECEWISE ACL Graph 编译正确处理层间边界，通信发生在图外
2. **通信高效**：最小化边云之间的通信开销，支持通信与计算 overlap
3. **功能完整**：支持完整的推理流程，包括 prefill 和 decode
4. **性能优化**：通过图编译融合和通信隐藏提升整体性能

---

## 2. 边云场景分析

### 2.1 与现有 PD-disaggregation 的区别

| 特性 | 现有 PD-disaggregation | 边云协同 |
|------|----------------------|---------|
| 分割方式 | KV Cache 传递 | HiddenStates 传递 |
| P节点职责 | Prefill + KV生成 | Embedding + 首尾层 |
| D节点职责 | Decode + KV消费 | 中间层计算 |
| 通信内容 | Key/Value Tensors | Hidden State Tensors |
| 通信时机 | 每层之后（layerwise） | 仅首尾边界 |
| 层分布 | 连续（按PP切分） | 非连续（边侧首尾，云侧中间） |

### 2.2 关键挑战

1. **非连续层分片**：边侧需要首层(0)和尾层(N)，而非连续的 pipeline stage，与现有模型并行假设冲突
2. **跨节点通信边界**：HiddenStates 传递发生在边云边界，必须在 ACL Graph 回放完成后执行，不能在图内捕获
3. **图编译分割点**：PIECEWISE 编译需要在 Layer 0 输出边界和 Layer N 输入边界正确分割图段
4. **形状/类型同步**：边云之间需要协商 hidden_states 的 shape 和 dtype，且需支持动态 batch/token 数
5. **多 TP 组协同**：边侧 TP=2 和云侧 TP=8 的 tensor parallel 结果需要正确聚合/分发给对端

---

## 3. 现有代码能力分析

### 3.1 图编译架构

vLLM-Ascend 的 ACL Graph 编译架构如下：

```
┌──────────────────────────────────────────────────────────────┐
│                     AscendCompiler                            │
│                  (CompilerInterface)                         │
├──────────────────────────────────────────────────────────────┤
│  compile()                                                    │
│    ├── enable_npugraph_ex=True                               │
│    │     └── npugraph_ex_compile()  [torchair backend]     │
│    │           └── 使用 torchair NPU backend 进行图编译    │
│    │                                                         │
│    └── enable_npugraph_ex=False                              │
│          └── fusion_pass_compile()                           │
│                ├── AddRMSNormQuantFusionPass                 │
│                ├── QKNormRopeFusionPass                      │
│                ├── MatmulAllReduceAddRMSNormPass             │
│                ├── MulsAddFusionPass                         │
│                ├── SequenceParallelismPass                   │
│                └── SequenceParallelismMoePass                │
└──────────────────────────────────────────────────────────────┘
```

**关键文件**：
- `vllm_ascend/compilation/compiler_interface.py:118` - `AscendCompiler` 主类
- `vllm_ascend/compilation/acl_graph.py:38` - `ACLGraphWrapper` 图捕获封装
- `vllm_ascend/compilation/graph_fusion_pass_manager.py:25` - `GraphFusionPassManager` 融合 pass 管理器

### 3.2 PIECEWISE 编译模式

当前代码中 PIECEWISE 模式的关键逻辑（`platform.py:391-410`）：

```python
elif compilation_config.cudagraph_mode == CUDAGraphMode.PIECEWISE:
    logger.info("PIECEWISE compilation enabled on NPU. use_inductor not supported - using only ACL Graph mode")
    assert compilation_config.mode == CompilationMode.VLLM_COMPILE, (
        "When enabling VLLM_COMPILE aclgraph, please make sure compilation_config.mode == "
        "CompilationMode.VLLM_COMPILE and compilation_config.cudagraph_mode == CUDAGraphMode.VLLM_COMPILE"
    )
    compilation_config.set_splitting_ops_for_v1(
        all2all_backend=vllm_config.parallel_config.all2all_backend,
        data_parallel_size=vllm_config.parallel_config.data_parallel_size,
    )
    compilation_config.use_inductor = False
    # NOTE: Theoretically, we should also add vllm::mla_forward in the attention ops.
    # Since the process is created in the spawn mode, the value of the class attribute
    # attention ops transmitted is still the one before modification, so it has not been modified.
    compilation_config.splitting_ops.extend(["vllm::mla_forward"])
    update_aclgraph_sizes(vllm_config)
    ascend_config.ascend_compilation_config.enable_npugraph_ex = False
```

**分割算子（splitting_ops）**：
- `vllm::mla_forward` - Multi-Level Attention forward
- `vllm::all_to_all` - All-to-All 通信（用于 TP/DP 场景）

### 3.3 ACLGraphWrapper 工作流程

```python
# acl_graph.py:110-213
class ACLGraphWrapper:
    def __call__(self, *args, **kwargs):
        # 1. 获取 forward context 中的 batch_descriptor 和 runtime_mode
        forward_context = get_forward_context()
        batch_descriptor = forward_context.batch_descriptor
        aclgraph_runtime_mode = forward_context.cudagraph_runtime_mode

        # 2. 检查是否匹配当前 runtime_mode
        if aclgraph_runtime_mode == CUDAGraphMode.NONE or \
           aclgraph_runtime_mode != self.runtime_mode:
            return self.runnable(*args, **kwargs)  # 跳过图捕获/回放

        # 3. 首次运行：捕获 ACL Graph
        if entry.aclgraph is None:
            forward_context.capturing = True
            with torch.npu.graph(aclgraph, pool=self.graph_pool):
                output = self.runnable(*args, **kwargs)
            entry.aclgraph = aclgraph
            entry.output = weak_ref_tensors(output)
            return output

        # 4. 后续运行：回放 ACL Graph
        logger.info_once("Replaying aclgraph")
        torch.npu.current_stream().synchronize()
        entry.aclgraph.replay()
        return entry.output
```

**重要限制**：`torch.npu.graph` 只能捕获在 NPU 上执行的算子。`dist.send`/`dist.recv` 等集合通信操作由 CPU 端发起，**不能直接在 ACL Graph 捕获上下文中执行**。因此跨节点通信必须在图外进行。

### 3.4 现有 PD-disaggregation 支持

**KV 传递连接器**：
- `vllm_ascend/distributed/kv_transfer/kv_p2p/mooncake_layerwise_connector.py` - Mooncake P2P layerwise 连接器（v1 接口主要实现）
- `vllm_ascend/distributed/kv_transfer/kv_p2p/mooncake_connector.py` - Mooncake P2P 连接器
- `vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/pool_worker.py` - KV Pool Worker（`KVPoolWorker` 类）

**关键标识**（`attention/attention_v1.py:381-383`）：
```python
self.is_kv_producer = (
    self.vllm_config.kv_transfer_config is not None and
    self.vllm_config.kv_transfer_config.is_kv_producer
)
```

---

## 4. 架构设计

### 4.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      边云协同推理架构                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐          ┌─────────────┐                       │
│  │   Edge      │          │   Cloud     │                       │
│  │   Node      │◄────────►│   Node      │                       │
│  │  (TP=2)     │  Hidden  │  (TP=8)     │                       │
│  └─────────────┘ States   └─────────────┘                       │
│        │                                                         │
│        │  ┌─────────────────────────────────────────────┐       │
│        │  │ Edge 侧 ACL Graph 段                        │       │
│        │  │ ┌─────────────┐    ┌─────────────┐         │       │
│        │  │ │ Segment A   │    │ Segment B   │         │       │
│        │  │ │ Embedding   │───►│ Layer 0     │──┐      │       │
│        │  │ └─────────────┘    └─────────────┘  │      │       │
│        │  └─────────────────────────────────────┘      │       │
│        │                                               │       │
│        │                    [图外通信: send hidden]     │       │
│        │                                               ▼       │
│        │  ┌─────────────────────────────────────────────┐       │
│        │  │ Cloud 侧 ACL Graph 段                       │       │
│        │  │ ┌─────────────┐    ┌─────────────────────┐ │       │
│        │  │ │ Segment C   │    │ Segment D           │ │       │
│        │  │ │ Recv Buffer │───►│ Layers 1 .. N-1     │─┘       │
│        │  │ └─────────────┘    └─────────────────────┘         │
│        │  └─────────────────────────────────────────────┘       │
│        │                                               │       │
│        │                    [图外通信: send hidden]     │       │
│        │                                               ▼       │
│        │  ┌─────────────────────────────────────────────┐       │
│        │  │ Edge 侧 ACL Graph 段 (续)                   │       │
│        │  │ ┌─────────────┐    ┌─────────────────────┐ │       │
│        │  │ │ Segment E   │    │ Segment F           │ │       │
│        │  │ │ Recv Buffer │───►│ Layer N + Sampling  │─┘       │
│        │  │ └─────────────┘    └─────────────────────┘         │
│        │  └─────────────────────────────────────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 核心组件

| 组件 | 职责 | 关键文件 |
|------|------|---------|
| `EdgeCloudManager` | 边云协同生命周期管理、配置解析、角色判定 | `edge_cloud/manager.py` (NEW) |
| `HiddenStatesTransfer` | HiddenStates 跨节点传递抽象 | `edge_cloud/hidden_states_transfer.py` (NEW) |
| `HiddenStatesTransferMooncake` | 基于 Mooncake 的传输实现 | `edge_cloud/hidden_states_transfer_mooncake.py` (NEW) |
| `HiddenStatesTransferNCCL` | 基于 NCCL/HCCL 的传输实现（同节点或 RDMA 场景） | `edge_cloud/hidden_states_transfer_nccl.py` (NEW) |
| `EdgeModelRunner` | 边侧模型执行器（扩展 NPUModelRunner） | `worker/edge_cloud_model_runner.py` (NEW) |
| `CloudModelRunner` | 云侧模型执行器（扩展 NPUModelRunner） | `worker/edge_cloud_model_runner.py` (NEW) |
| `LayerShardLoader` | 按层分片加载模型权重 | `model_loader/layer_shard_loader.py` (NEW) |

### 4.3 配置设计

新增配置应符合 `AscendConfig` 现有解析模式（从 `additional_config` 取子字典后初始化对应 Config 类）：

```python
# ascend_config.py 新增

class EdgeCloudConfig:
    def __init__(self, config_dict: dict):
        # 边云协同总开关
        self.enabled = config_dict.get("enabled", False)

        # 节点角色
        self.node_role = config_dict.get("role", None)
        # 可选值: "edge", "cloud"

        # 总层数（从模型配置读取）
        self.total_layers = config_dict.get("total_layers", 0)

        # 边侧层配置: 加载首层和尾层的索引列表
        self.edge_layers = config_dict.get("edge_layers", [0, -1])

        # 云侧层配置: 中间层的起始和结束索引
        self.cloud_start_layer = config_dict.get("cloud_start_layer", 1)
        self.cloud_end_layer = config_dict.get("cloud_end_layer", -2)

        # HiddenStates 传输配置
        transfer_cfg = config_dict.get("transfer_config", {})
        self.transfer_backend = transfer_cfg.get("backend", "mooncake")
        self.transfer_buffer_size = transfer_cfg.get("buffer_size", 1 << 30)  # 1GB
        self.transfer_async = transfer_cfg.get("async", True)
        self.peer_addrs = transfer_cfg.get("peer_addrs", [])  # 对端地址列表

        # 校验
        if self.enabled:
            assert self.node_role in ("edge", "cloud"), \
                "edge_cloud role must be 'edge' or 'cloud'"


# 在 AscendConfig.__init__ 中新增:
edge_cloud_config = additional_config.get("edge_cloud_config", {})
self.edge_cloud_config = EdgeCloudConfig(edge_cloud_config)
```

### 4.4 分层加载策略

```python
def get_layer_loading_plan(node_role: str, total_layers: int) -> list[int]:
    """
    边云场景的层加载策略

    边侧: 加载 layer 0 和 layer N-1 (即首层和尾层)
    云侧: 加载 layer 1, 2, ..., N-2 (中间层)
    """
    if node_role == "edge":
        return [0, total_layers - 1]
    else:  # cloud
        return list(range(1, total_layers - 1))
```

**注**：若模型存在独立的 embedding / lm_head（如多数 LLM），边侧还需加载 embedding 和 lm_head。

---

## 5. 图编译详细设计

### 5.1 边云场景的图编译挑战

现有 PIECEWISE 编译按连续算子分割图，但边云场景需要：

1. **通信在图外执行**：`dist.send` / `dist.recv` 不能嵌入 ACL Graph，必须在图回放完成后执行
2. **非连续层组合**：边侧 Layer 0 和 Layer N 分别位于两次通信之间，各自独立成段
3. **异步通信 overlap**：边侧 Segment A/B 执行后可与通信 overlap；云侧计算与边侧等待可部分 overlap
4. **动态 shape 支持**：prefill/decode 阶段 token 数变化，需分别捕获不同 batch_descriptor 的图

### 5.2 分割算子设计

边云场景**不引入新的 splitting_ops**，而是复用现有的层边界分割机制。关键修改在于模型执行器（ModelRunner）在边云边界主动插入图中断和通信逻辑。

若必须显式标记分割点，可在模型 forward 中插入 no-op 自定义算子作为标记：

```python
# 可选：仅用于调试或显式边界标记
torch.ops.vllm_ascend.edge_cloud_boundary(tag="after_layer_0")
```

### 5.3 ACLGraph 分段捕获

#### 5.3.1 边侧 ACLGraph

边侧包含三个独立的 ACLGraph 捕获段（因为中间被云侧计算和通信打断）：

```python
class EdgeModelRunner(NPUModelRunner):
    """
    边侧模型执行器
    """

    def __init__(self, vllm_config, ...):
        super().__init__(vllm_config, ...)
        self.edge_cloud_mgr = EdgeCloudManager(vllm_config)
        self.transfer = self.edge_cloud_mgr.create_transfer()

    def execute_model(self, scheduler_output, ...):
        # Segment 1: Embedding + Layer 0 (ACL Graph 捕获/回放)
        hidden_states = self._execute_segment_embedding_layer0(scheduler_output)

        # 图外通信: 发送 hidden_states 到云侧
        # 使用异步发送，与云侧计算形成流水线
        send_work = self.transfer.send_async(hidden_states, peer=self.cloud_peer)

        # 边侧可在此执行其他任务（如准备下一次请求的 input batch）
        # ...

        # 等待云侧计算完成并接收回传 hidden_states
        recv_hidden = self.transfer.recv(
            shape=self._infer_hidden_shape(scheduler_output),
            dtype=hidden_states.dtype,
            peer=self.cloud_peer,
        )

        # Segment 2: Layer N + Sampling (ACL Graph 捕获/回放)
        output = self._execute_segment_layer_n_sampling(recv_hidden, scheduler_output)
        return output
```

#### 5.3.2 云侧 ACLGraph

```python
class CloudModelRunner(NPUModelRunner):
    """
    云侧模型执行器
    """

    def __init__(self, vllm_config, ...):
        super().__init__(vllm_config, ...)
        self.edge_cloud_mgr = EdgeCloudManager(vllm_config)
        self.transfer = self.edge_cloud_mgr.create_transfer()

    def execute_model(self, scheduler_output, ...):
        # 接收边侧 hidden_states（阻塞等待）
        recv_hidden = self.transfer.recv(
            shape=self._infer_hidden_shape(scheduler_output),
            dtype=self.hidden_dtype,
            peer=self.edge_peer,
        )

        # Segment: Layers 1 ~ N-1 (ACL Graph 捕获/回放)
        # 注意：云侧 TP=8，内部包含 all-reduce / all-to-all，这些算子可以被 PIECEWISE 图捕获
        hidden_states = self._execute_segment_middle_layers(recv_hidden, scheduler_output)

        # 图外通信: 发送结果回边侧
        self.transfer.send(hidden_states, peer=self.edge_peer)

        # 云侧无输出（或输出空占位）
        return None
```

### 5.4 跨节点通信实现

**重要修正**：跨节点通信不使用 `torch.autograd.Function` 包装为 fake custom op，因为：
1. `dist.send/recv` 是 CPU 发起的集合通信，无法在 `torch.npu.graph` 中正确捕获
2. vLLM 推理阶段无 backward，不需要 `autograd.Function`
3. 通信必须在图外显式执行

```python
# edge_cloud/hidden_states_transfer.py

import torch.distributed as dist
from abc import ABC, abstractmethod


class HiddenStatesTransfer(ABC):
    """HiddenStates 传输抽象接口"""

    @abstractmethod
    def send(self, hidden_states: torch.Tensor, peer: int | str, tag: int = 0) -> None:
        """同步发送 hidden_states 到对端"""
        pass

    @abstractmethod
    def send_async(
        self, hidden_states: torch.Tensor, peer: int | str, tag: int = 0
    ) -> "HiddenStatesTransferWork":
        """异步发送 hidden_states 到对端，返回句柄用于后续等待"""
        pass

    @abstractmethod
    def recv(
        self, shape: torch.Size, dtype: torch.dtype, peer: int | str, tag: int = 0
    ) -> torch.Tensor:
        """同步从对端接收 hidden_states"""
        pass

    @abstractmethod
    def recv_async(
        self, buffer: torch.Tensor, peer: int | str, tag: int = 0
    ) -> "HiddenStatesTransferWork":
        """异步接收 hidden_states 到指定 buffer"""
        pass


class HiddenStatesTransferWork(ABC):
    """异步传输句柄"""

    @abstractmethod
    def wait(self) -> None:
        pass
```

### 5.5 Fusion Pass 扩展

边云场景下，通信算子不在 FX Graph 内，因此**不需要也不应**新增针对通信的 Fusion Pass。

若需要优化，应考虑以下方向：
1. **计算与通信 overlap**：通过调度器实现，而非图融合 pass
2. **云侧 Sequence Parallelism**：若启用 SP，复用现有 `SequenceParallelismPass` 和 `SequenceParallelismMoePass`
3. **边侧首尾层融合**：若 Layer 0 / Layer N 存在可融合的算子（如 RMSNorm + Quant），复用现有 `AddRMSNormQuantFusionPass` 等

```python
# GraphFusionPassManager 无需修改，复用现有 pass 即可
# 边云场景若启用 SP，现有 configure 逻辑已自动注入 SequenceParallelismPass
```

### 5.6 PIECEWISE 编译配置

```python
# platform.py 边云场景编译配置（新增逻辑）

def _configure_edge_cloud_compilation(vllm_config: VllmConfig):
    """边云场景的编译配置"""
    compilation_config = vllm_config.compilation_config
    ascend_config = get_ascend_config()

    if not ascend_config.edge_cloud_config.enabled:
        return

    # 边云场景只支持 PIECEWISE 模式
    if compilation_config.cudagraph_mode not in (
        CUDAGraphMode.PIECEWISE,
        CUDAGraphMode.FULL_AND_PIECEWISE,
    ):
        logger.warning(
            "Edge-cloud collaboration requires PIECEWISE cudagraph mode. "
            "Falling back to PIECEWISE."
        )
        compilation_config.cudagraph_mode = CUDAGraphMode.PIECEWISE

    # 保持现有 splitting_ops 不变（vllm::mla_forward, vllm::all_to_all）
    # 边云通信发生在图外，不需要新增 splitting_ops

    # 禁用 inductor，使用纯 ACL Graph
    compilation_config.use_inductor = False

    # 更新 ACL Graph sizes（支持动态 batch）
    update_aclgraph_sizes(vllm_config)
    ascend_config.ascend_compilation_config.enable_npugraph_ex = False
```

### 5.7 图捕获流程

```
边侧 (Edge):
┌──────────────────────────────────────────────────────────────┐
│  Forward Context                                              │
│  ├── batch_descriptor                                         │
│  ├── cudagraph_runtime_mode = PIECEWISE                     │
│  └── compile_range = (start_layer, end_layer)                │
├──────────────────────────────────────────────────────────────┤
│  Segment A+B: embedding + layer_0                            │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ with torch.npu.graph(aclgraph_segment_ab):           │  │
│  │     hidden_states = embedding(input_ids)               │  │
│  │     hidden_states = layer_0(hidden_states)             │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  [图外] 发送 hidden_states 到云侧                              │
│  transfer.send_async(hidden_states, peer=cloud_rank, tag=0)  │
│                                                               │
│  [图外] 接收云侧返回的 hidden_states                           │
│  recv_hidden = transfer.recv(shape, dtype, peer=cloud_rank)  │
│                                                               │
│  Segment E+F: layer_N + sampling                             │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ with torch.npu.graph(aclgraph_segment_ef):           │  │
│  │     hidden_states = layer_N(recv_hidden)               │  │
│  │     logits = lm_head(hidden_states)                    │  │
│  │     output = sample(logits)                            │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘

云侧 (Cloud):
┌──────────────────────────────────────────────────────────────┐
│  Forward Context                                              │
│  ├── batch_descriptor                                         │
│  ├── cudagraph_runtime_mode = PIECEWISE                     │
│  └── compile_range = (start_layer, end_layer)                │
├──────────────────────────────────────────────────────────────┤
│  [图外] 接收边侧 hidden_states                                 │
│  recv_hidden = transfer.recv(shape, dtype, peer=edge_rank)   │
│                                                               │
│  Segment C+D: layers 1 ~ N-1                                 │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ with torch.npu.graph(aclgraph_segment_cd):           │  │
│  │     for layer in middle_layers:                        │  │
│  │         recv_hidden = layer(recv_hidden)               │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  [图外] 发送 hidden_states 回边侧                              │
│  transfer.send(recv_hidden, peer=edge_rank, tag=1)           │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. 通信机制设计

### 6.1 HiddenStatesTransfer 抽象

见 5.4 节。通信完全在图外执行，不尝试包装为 custom op。

### 6.2 Mooncake 实现

```python
# edge_cloud/hidden_states_transfer_mooncake.py

from mooncake.engine import TransferEngine

class HiddenStatesTransferMooncake(HiddenStatesTransfer):
    """基于 Mooncake TransferEngine 的 HiddenStates 传输实现"""

    def __init__(self, config: EdgeCloudConfig):
        self.config = config
        self.engine = TransferEngine()  # 或复用 global_te
        self._init_endpoints(config.peer_addrs)

    def _init_endpoints(self, peer_addrs):
        for addr in peer_addrs:
            self.engine.connect_peer(addr)

    def send(self, hidden_states, peer, tag=0):
        # Mooncake 同步发送
        self.engine.send(hidden_states.data_ptr(), hidden_states.numel() * hidden_states.element_size(), peer, tag)

    def send_async(self, hidden_states, peer, tag=0):
        # Mooncake 异步发送
        handle = self.engine.isend(
            hidden_states.data_ptr(), hidden_states.numel() * hidden_states.element_size(), peer, tag
        )
        return MooncakeWork(handle)

    def recv(self, shape, dtype, peer, tag=0):
        buffer = torch.empty(shape, dtype=dtype, device="npu")
        self.engine.recv(
            buffer.data_ptr(), buffer.numel() * buffer.element_size(), peer, tag
        )
        return buffer

    def recv_async(self, buffer, peer, tag=0):
        handle = self.engine.irecv(
            buffer.data_ptr(), buffer.numel() * buffer.element_size(), peer, tag
        )
        return MooncakeWork(handle)


class MooncakeWork(HiddenStatesTransferWork):
    def __init__(self, handle):
        self.handle = handle

    def wait(self):
        self.handle.wait()
```

### 6.3 NCCL/HCCL 实现（同节点或 RDMA 直连场景）

```python
# edge_cloud/hidden_states_transfer_nccl.py

import torch.distributed as dist

class HiddenStatesTransferNCCL(HiddenStatesTransfer):
    """基于 torch.distributed (NCCL/HCCL) 的 HiddenStates 传输实现"""

    def __init__(self, config: EdgeCloudConfig):
        self.config = config
        # 假设边云节点已加入同一个 process group
        # 或使用独立建立的 edge_cloud_pg
        self.pg = self._get_or_create_edge_cloud_pg()

    def _get_or_create_edge_cloud_pg(self):
        # 通过 additional_config 中指定的 ranks 创建通信组
        # 或使用默认的 world group（若边云在同一集群）
        return dist.group.WORLD  # placeholder

    def send(self, hidden_states, peer, tag=0):
        dist.send(hidden_states, dst=peer, tag=tag, group=self.pg)

    def send_async(self, hidden_states, peer, tag=0):
        work = dist.isend(hidden_states, dst=peer, tag=tag, group=self.pg)
        return NCCLWork(work)

    def recv(self, shape, dtype, peer, tag=0):
        buffer = torch.empty(shape, dtype=dtype, device="npu")
        dist.recv(buffer, src=peer, tag=tag, group=self.pg)
        return buffer

    def recv_async(self, buffer, peer, tag=0):
        work = dist.irecv(buffer, src=peer, tag=tag, group=self.pg)
        return NCCLWork(work)


class NCCLWork(HiddenStatesTransferWork):
    def __init__(self, work):
        self.work = work

    def wait(self):
        self.work.wait()
```

---

## 7. 其他模块简要设计

### 7.1 模型加载

```python
# model_loader/layer_shard_loader.py

class LayerShardLoader:
    """按层分片加载模型权重"""

    def __init__(self, vllm_config):
        self.vllm_config = vllm_config
        self.edge_cloud_cfg = get_ascend_config().edge_cloud_config
        self.node_role = self.edge_cloud_cfg.node_role
        self.layer_plan = get_layer_loading_plan(
            self.node_role, self.edge_cloud_cfg.total_layers
        )

    def load_model(self, model_path):
        """只加载当前节点需要的层"""
        state_dict = {}

        # 边侧加载 embedding 和 lm_head
        if self.node_role == "edge":
            state_dict.update(load_embedding_weights(model_path))
            state_dict.update(load_lm_head_weights(model_path))

        # 按 layer_plan 加载 transformer 层
        for layer_idx in self.layer_plan:
            state_dict.update(load_layer_weights(model_path, layer_idx))

        return state_dict

    def patch_model_runner(self, model_runner):
        """
        修改 model_runner 中的模型，移除未加载的层以避免 forward 报错。
        若层未加载，替换为 Identity 或 None，并在 execute_model 中跳过。
        """
        model = model_runner.model
        total_layers = len(model.model.layers)

        for i in range(total_layers):
            if i not in self.layer_plan:
                model.model.layers[i] = None  # 或未加载的占位符
```

### 7.2 调度协同

```python
# edge_cloud/scheduler.py

class EdgeCloudScheduler:
    """
    边云协同调度器

    协调边侧和云侧的执行顺序：
    1. 边侧完成 Layer 0 后异步发送 hidden_states
    2. 云侧阻塞接收 hidden_states 后执行中间层
    3. 云侧完成后发送 hidden_states 回边侧
    4. 边侧接收后执行 Layer N 和 sampling

    为提高吞吐，可引入微批流水线（micro-batching）：
    - 边侧处理请求批次 A 的 Layer 0 时，可同时接收批次 B 的云侧结果
    """

    def __init__(self, vllm_config):
        self.vllm_config = vllm_config
        self.cfg = get_ascend_config().edge_cloud_config

    def execute_edge_pipeline(self, model_runner, scheduler_output):
        """边侧执行流水线"""
        # Step 1: 执行本地 Layer 0
        hidden_after_l0 = model_runner.run_layer_0(scheduler_output)

        # Step 2: 异步发送（与云侧计算 overlap）
        send_handle = model_runner.transfer.send_async(hidden_after_l0)

        # Step 3: 若存在上一批次的云侧返回结果，执行 Layer N
        # （微批流水线场景）
        if self.prev_recv_buffer is not None:
            output = model_runner.run_layer_n_and_sampling(self.prev_recv_buffer)
            self.prev_recv_buffer = None
            # 返回上一批次结果，当前批次继续等待
            return output

        # Step 4: 等待接收当前批次结果
        recv_hidden = model_runner.transfer.recv(
            shape=self._expected_shape(scheduler_output),
            dtype=hidden_after_l0.dtype,
        )
        send_handle.wait()  # 确保发送已完成（可选，依 Mooncake/NCCL 语义）

        # Step 5: 执行 Layer N + Sampling
        output = model_runner.run_layer_n_and_sampling(recv_hidden)
        return output

    def execute_cloud_pipeline(self, model_runner, scheduler_output):
        """云侧执行流水线"""
        # Step 1: 接收边侧 hidden_states
        recv_hidden = model_runner.transfer.recv(
            shape=self._expected_shape(scheduler_output),
            dtype=model_runner.hidden_dtype,
        )

        # Step 2: 执行中间层
        hidden_after_mid = model_runner.run_middle_layers(recv_hidden)

        # Step 3: 发送回边侧
        model_runner.transfer.send(hidden_after_mid)
        return None
```

### 7.3 配置参数

```python
# 使用示例

# 边侧启动
vllm serve /path/to/model \
    --tensor-parallel-size 2 \
    --additional-config '{
        "edge_cloud_config": {
            "enabled": true,
            "role": "edge",
            "total_layers": 61,
            "edge_layers": [0, 60],
            "transfer_config": {
                "backend": "mooncake",
                "buffer_size": 1073741824,
                "peer_addrs": ["cloud-node-0:9010"]
            }
        }
    }'

# 云侧启动
vllm serve /path/to/model \
    --tensor-parallel-size 8 \
    --additional-config '{
        "edge_cloud_config": {
            "enabled": true,
            "role": "cloud",
            "total_layers": 61,
            "cloud_start_layer": 1,
            "cloud_end_layer": 59,
            "transfer_config": {
                "backend": "mooncake",
                "buffer_size": 1073741824,
                "peer_addrs": ["edge-node-0:9010"]
            }
        }
    }'
```

---

## 8. 实现计划

### Phase 1: 基础框架（2周）

| 任务 | 负责人 | 描述 |
|------|--------|------|
| T1.1 | - | 创建 `edge_cloud/` 目录结构 |
| T1.2 | - | 实现 `HiddenStatesTransfer` 抽象接口与 `HiddenStatesTransferWork` |
| T1.3 | - | 实现 Mooncake `HiddenStatesTransferMooncake` |
| T1.4 | - | 实现 `LayerShardLoader`，支持按层分片加载权重 |
| T1.5 | - | 添加 `EdgeCloudConfig` 到 `AscendConfig` |
| T1.6 | - | 实现 `EdgeCloudManager` 生命周期管理 |

### Phase 2: 模型执行器（3周）

| 任务 | 负责人 | 描述 |
|------|--------|------|
| T2.1 | - | 实现 `EdgeModelRunner`（继承 NPUModelRunner） |
| T2.2 | - | 实现 `CloudModelRunner`（继承 NPUModelRunner） |
| T2.3 | - | 修改 `NPUWorker` 根据 role 创建对应 ModelRunner |
| T2.4 | - | 在 `platform.py` 中集成边云编译配置 `_configure_edge_cloud_compilation` |
| T2.5 | - | 确保 PIECEWISE 模式下边侧/云侧图捕获正确（分别在 Layer 0 后和 Layer N 前断开） |
| T2.6 | - | 处理动态 shape：prefill/decode 不同 batch_descriptor 的图缓存 |

### Phase 3: 集成与测试（2周）

| 任务 | 负责人 | 描述 |
|------|--------|------|
| T3.1 | - | 集成边云协同到 `NPUWorker` 启动流程 |
| T3.2 | - | 实现端到端单卡/多卡测试（模拟边云场景） |
| T3.3 | - | 添加异常处理：通信超时、对端断开、shape 不匹配 |
| T3.4 | - | 性能基准测试：测量通信耗时与计算 overlap 效果 |
| T3.5 | - | 文档编写与代码评审 |

### Phase 4: 优化（1周）

| 任务 | 负责人 | 描述 |
|------|--------|------|
| T4.1 | - | 微批流水线优化：边侧 Layer 0 与上一批次 Layer N overlap |
| T4.2 | - | 通信压缩：对 hidden_states 进行量化/稀疏化后再传输 |
| T4.3 | - | 内存优化：复用 recv/send buffer，避免重复分配 |

---

## 附录 A: 关键文件清单

### 新增文件

```
vllm_ascend/
├── edge_cloud/
│   ├── __init__.py
│   ├── manager.py                        # EdgeCloudManager
│   ├── hidden_states_transfer.py         # HiddenStatesTransfer 抽象
│   ├── hidden_states_transfer_mooncake.py
│   ├── hidden_states_transfer_nccl.py
│   └── scheduler.py                      # EdgeCloudScheduler
├── worker/
│   └── edge_cloud_model_runner.py        # EdgeModelRunner / CloudModelRunner
└── model_loader/
    └── layer_shard_loader.py             # LayerShardLoader
```

### 修改文件

```
vllm_ascend/
├── ascend_config.py                      # 添加 EdgeCloudConfig
├── platform.py                            # 边云编译配置
├── worker/
│   ├── model_runner_v1.py                 # 可能需要暴露层执行接口
│   └── worker.py                          # NPUWorker 扩展
└── compilation/
    └── acl_graph.py                       # 确认图外通信不影响 ACLGraphWrapper
```

---

## 附录 B: 参考资料

1. vLLM-Ascend 现有代码库
2. [Mooncake Transfer Engine 文档](https://github.com/AlibabaPAI/mooncake)
3. [Ascend CANN 文档](https://www.hiascend.com/document/content/HAT/CANN)
4. PyTorch Distributed Communications (`torch.distributed`)

---

## 附录 C: 术语表

| 术语 | 英文 | 描述 |
|------|------|------|
| 边云协同 | Edge-Cloud Collaboration | 边侧和云侧协同完成推理任务 |
| ACL Graph | ACL Graph | Ascend 加速库的图编译机制，基于 `torch.npu.graph` |
| PIECEWISE | PIECEWISE | 分段图编译模式，按 splitting_ops 将模型拆分为多段捕获 |
| HiddenStates | Hidden States | Transformer 层的隐藏状态张量 |
| Splitting Ops | Splitting Operations | 图分割点算子，如 `vllm::mla_forward` |
| Layer Shard | Layer Sharding | 按层分片加载/存储模型权重 |
| 图外通信 | Out-of-Graph Communication | 在 ACL Graph 捕获/回放之外执行的通信操作 |
