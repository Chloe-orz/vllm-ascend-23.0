# 边云协同场景 vLLM-Ascend 适配设计文档

| 版本 | 日期 | 作者 | 描述 |
|------|------|------|------|
| 0.1 | 2026-04-28 | - | 初始版本 |

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
│  - Transformer Layer 0 │   - Transformer Layer 1 ~ N-2         │
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
- 加载 embedding 层和首尾 transformer 层
- 接收用户请求，进行 token embedding
- 执行 layer_0 前向传播
- 发送 hidden_states 到云侧
- 接收云侧回来的 hidden_states
- 执行 layer_N 前向传播
- 执行 sampling 输出

**云侧职责**：
- 加载中间所有 transformer 层
- 接收边侧 hidden_states
- 执行中间层前向传播
- 发送 hidden_states 回边侧

### 1.2 设计目标

1. **图编译适配**：确保边侧和云侧的 PIECEWISE ACL Graph 编译正确处理跨节点通信边界
2. **通信高效**：最小化边云之间的通信开销
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
| 通信时机 | 每层之后 | 仅首尾边界 |

### 2.2 关键挑战

1. **非连续层分片**：边侧需要首层(0)和尾层(N-1)，而非连续的 pipeline stage
2. **跨节点通信边界**：HiddenStates 传递发生在边云边界，需要与 ACL Graph 捕获边界对齐
3. **图编译分割点**：PIECEWISE 编译需要正确识别跨节点通信算子作为分割点
4. **形状/类型同步**：边云之间需要协商 hidden_states 的 shape 和 dtype

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
│    │           └── 使用 NPUGraph 进行图捕获和回放              │
│    │                                                         │
│    └── enable_npugraph_ex=False                              │
│          └── fusion_pass_compile()                           │
│                ├── AddRMSNormQuantFusionPass                 │
│                ├── QKNormRopeFusionPass                      │
│                ├── MatmulAllReduceAddRMSNormPass              │
│                ├── MulsAddFusionPass                          │
│                └── SequenceParallelismPass / MoePass           │
└──────────────────────────────────────────────────────────────┘
```

**关键文件**：
- `compilation/compiler_interface.py:118` - `AscendCompiler` 主类
- `compilation/acl_graph.py:38` - `ACLGraphWrapper` 图捕获封装
- `compilation/graph_fusion_pass_manager.py:25` - `GraphFusionPassManager` 融合pass管理器

### 3.2 PIECEWISE 编译模式

当前代码中 PIECEWISE 模式的关键逻辑（`platform.py:391-409`）：

```python
elif compilation_config.cudagraph_mode == CUDAGraphMode.PIECEWISE:
    compilation_config.set_splitting_ops_for_v1(...)
    compilation_config.use_inductor = False
    compilation_config.splitting_ops.extend(["vllm::mla_forward"])
    update_aclgraph_sizes(vllm_config)
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
        if aclgraph_runtime_mode != self.runtime_mode:
            return self.runnable(*args, **kwargs)  # 跳过图捕获

        # 3. 首次运行：捕获 ACL Graph
        if entry.aclgraph is None:
            with torch.npu.graph(aclgraph, pool=self.graph_pool):
                output = self.runnable(*args, **kwargs)
            entry.aclgraph = aclgraph
            return output

        # 4. 后续运行：回放 ACL Graph
        logger.info_once("Replaying aclgraph")
        torch.npu.current_stream().synchronize()
        entry.aclgraph.replay()
        return entry.output
```

### 3.4 现有 PD-disaggregation 支持

**KV 传递连接器**：
- `distributed/kv_transfer/kv_p2p/mooncake_connector.py` - Mooncake P2P 连接器
- `distributed/kv_transfer/kv_pool/ascend_store/pool_worker.py` - KV Pool Worker

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
│  ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
│  │   Edge      │          │   Cloud     │          │  Transfer   │
│  │   Node      │◄────────►│   Node      │          │  Layer      │
│  │  (2 cards)  │  Hidden  │  (8 cards)  │          │             │
│  └─────────────┘ States   └─────────────┘          └─────────────┘
│        │                                                         │
│        │                    ┌─────────────────┐                   │
│        │                    │ ACL Graph Mgr   │                   │
│        │                    │ (EdgeSegment)   │                   │
│        │                    │ [Layer 0]       │                   │
│        │                    │ [Layer N]       │                   │
│        │                    └─────────────────┘                   │
│        │                                                         │
│        │                    ┌─────────────────┐                   │
│        │                    │ ACL Graph Mgr   │                   │
│        │                    │ (CloudSegment)  │                   │
│        │                    │ [Layer 1..N-2] │                   │
│        │                    └─────────────────┘                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 核心组件

| 组件 | 职责 | 关键文件 |
|------|------|---------|
| `EdgeCloudManager` | 边云协同管理 | `edge_cloud/manager.py` (NEW) |
| `HiddenStatesTransfer` | HiddenStates 跨节点传递 | `edge_cloud/hidden_states_transfer.py` (NEW) |
| `EdgeACLGraphSegment` | 边侧图编译段 | `compilation/edge_segment.py` (NEW) |
| `CloudACLGraphSegment` | 云侧图编译段 | `compilation/cloud_segment.py` (NEW) |
| `CrossNodeSend/Recv` | 跨节点通信算子 | `ops/cross_node_comm.py` (NEW) |
| `LayerShardLoader` | 模型层分片加载 | `model_loader/layer_shard.py` (NEW) |

### 4.3 配置设计

```python
# ascend_config.py 新增配置
class EdgeCloudConfig:
    def __init__(self, additional_config):
        # 边云协同总开关
        self.enabled = additional_config.get("edge_cloud_enabled", False)

        # 节点角色
        self.node_role = additional_config.get("edge_cloud_role", "edge")
        # 可选值: "edge", "cloud"

        # 边侧配置
        self.edge_config = EdgeConfig(
            first_layer=0,
            last_layer=-1,  # -1 表示最后一层
            num_layers=get_total_num_hidden_layers(),
        )

        # 云侧配置
        self.cloud_config = CloudConfig(
            start_layer=1,
            end_layer=-2,  # 倒数第二层
        )

        # HiddenStates 传输配置
        self.transfer_config = TransferConfig(
            backend="mooncake",  # or "nccl", "rccl"
            buffer_size=1e9,
            async_op=True,
        )
```

### 4.4 分层加载策略

```python
def get_layer_loading_plan(node_role: str, total_layers: int) -> list[int]:
    """
    边云场景的层加载策略

    边侧: 加载 layer 0, 1, N-2, N-1 (embedding相关的首尾层)
    云侧: 加载 layer 2, 3, ..., N-3 (中间层)
    """
    if node_role == "edge":
        # 边侧: embedding相关层
        return [0, 1, total_layers - 2, total_layers - 1]
    else:  # cloud
        # 云侧: 中间所有层
        return list(range(2, total_layers - 2))
```

---

## 5. 图编译详细设计

### 5.1 边云场景的图编译挑战

现有 PIECEWISE 编译按连续算子分割图，但边云场景需要：

1. **跨节点通信作为分割点**：`hidden_states_send` 和 `hidden_states_recv` 算子
2. **非连续层组合**：边侧 layer_0 + layer_N 需要在同一个 ACLGraph 中
3. **异步通信**：通信和计算需要 overlap

### 5.2 分割算子设计

新增以下 splitting_ops 用于边云场景：

```python
# 边云通信相关的 splitting_ops
EDGE_CLOUD_SPLITTING_OPS = [
    "vllm_ascend::hidden_states_send",      # 发送 hidden_states 到对端
    "vllm_ascend::hidden_states_recv",      # 接收 hidden_states 从对端
    "vllm_ascend::sync_barrier",            # 同步屏障
]
```

### 5.3 ACLGraph 分段捕获

#### 5.3.1 边侧 ACLGraph

```python
class EdgeACLGraphSegment:
    """
    边侧 ACLGraph 段，包含:
    - embedding + layer_0 (forward)
    - 接收 hidden_states (recv)
    - layer_N (backward-aware forward)
    - 发送 hidden_states (send)
    """

    def __init__(self, vllm_config, layer_plan):
        self.layer_plan = layer_plan  # e.g., [0, 1, N-2, N-1]
        self.aclgraph_segments = {}  # batch_descriptor -> ACLGraphEntry

    def capture_segment_0(self, input_ids, positions, ...):
        """
        Segment 0: embedding + layer_0
        输入: input_ids
        输出: hidden_states_after_layer_0
        """
        hidden_states = self.embedding(input_ids)
        for layer_idx in [0]:
            hidden_states = self.layers[layer_idx](hidden_states, positions)
        return hidden_states

    def capture_recv_and_layer_n(self, hidden_states_from_cloud):
        """
        Segment N: recv + layer_N
        输入: hidden_states_from_cloud
        输出: hidden_states_after_layer_n
        """
        # 接收云侧 hidden_states
        recv_hidden = self.hidden_states_recv(hidden_states_from_cloud)
        # 执行 layer_N
        for layer_idx in [self.layer_plan[-1]]:
            recv_hidden = self.layers[layer_idx](recv_hidden, positions)
        return recv_hidden

    def capture_send(self, hidden_states):
        """
        Segment Send: 发送 hidden_states 到云侧
        """
        self.hidden_states_send(hidden_states)
```

#### 5.3.2 云侧 ACLGraph

```python
class CloudACLGraphSegment:
    """
    云侧 ACLGraph 段，包含:
    - 接收 hidden_states (recv)
    - 中间层 layer_1 ~ layer_{N-2}
    - 发送 hidden_states (send)
    """

    def __init__(self, vllm_config, layer_plan):
        self.layer_plan = layer_plan  # e.g., [2, 3, ..., N-3]
        self.aclgraph_segments = {}

    def capture_recv_and_middle_layers(self, hidden_states_from_edge):
        """
        Segment 1: recv + middle layers
        输入: hidden_states_from_edge
        输出: hidden_states_after_middle
        """
        recv_hidden = self.hidden_states_recv(hidden_states_from_edge)
        for layer_idx in self.layer_plan:
            recv_hidden = self.layers[layer_idx](recv_hidden, positions)
        return recv_hidden

    def capture_send(self, hidden_states):
        """
        Segment Send: 发送 hidden_states 回边侧
        """
        self.hidden_states_send(hidden_states)
```

### 5.4 跨节点通信算子注册

```python
# ops/cross_node_comm.py

class HiddenStatesSend(torch.autograd.Function):
    """发送 HiddenStates 到对端节点"""

    @staticmethod
    def forward(ctx, hidden_states, peer_rank, tag):
        # 使用 NPU 集合通信或 RoCE 发送
        dist.send(hidden_states, peer_rank, tag)
        return None

    @staticmethod
    def backward(ctx, grad_output):
        # 接收梯度
        peer_rank = ctx.peer_rank
        tag = ctx.tag
        grad = torch.empty_like(grad_output)
        dist.recv(grad, peer_rank, tag)
        return grad, None, None


class HiddenStatesRecv(torch.autograd.Function):
    """接收 HiddenStates 从对端节点"""

    @staticmethod
    def forward(ctx, shape, dtype, peer_rank, tag):
        # 接收 hidden_states
        tensor = torch.empty(shape, dtype=dtype, device="npu")
        dist.recv(tensor, peer_rank, tag)
        return tensor

    @staticmethod
    def backward(ctx, grad_output):
        # 发送梯度回对端
        peer_rank = ctx.peer_rank
        tag = ctx.tag
        dist.send(grad_output, peer_rank, tag)
        return None, None, None, None


# 注册为 custom op
def register_cross_node_ops():
    from vllm_ascend.ops import register_custom_ops
    register_custom_ops()

    torch.library.register_fake("vllm_ascend::hidden_states_send")(
        lambda hidden_states, peer_rank, tag: None
    )
    torch.library.register_fake("vllm_ascend::hidden_states_recv")(
        lambda shape, dtype, peer_rank, tag: torch.empty(shape, dtype=dtype, device="npu")
    )
```

### 5.5 Fusion Pass 扩展

#### 5.5.1 新增 HiddenStates Send/Recv 融合 Pass

```python
# compilation/passes/hidden_states_comm_fusion_pass.py

class HiddenStatesSendRecvFusionPass(VllmInductorPass):
    """
    融合 HiddenStates 通信与计算的边界算子

    融合策略:
    1. send + 计算 -> 异步发送
    2. recv + 计算 -> 预取 recv
    """

    def __init__(self, vllm_config):
        super().__init__(vllm_config)
        self.pattern_match_passes = PatternMatcherPass(
            pass_name="hidden_states_comm_fusion_pass"
        )

        # 注册融合模式
        self._register_async_send_pattern()
        self._register_prefetch_recv_pattern()

    def _register_async_send_pattern(self):
        """融合 send 与后续计算，实现异步发送"""
        def pattern(hidden_states, peer_rank, tag, next_input):
            # 发送
            torch.ops.vllm_ascend.hidden_states_send(hidden_states, peer_rank, tag)
            return next_input

        def replacement(hidden_states, peer_rank, tag, next_input):
            # 使用异步发送，与计算 overlap
            handle = torch.ops.vllm_ascend.hidden_states_send_async(
                hidden_states, peer_rank, tag
            )
            return next_input, handle

        self.pattern_match_passes.register_replacement(
            pattern, replacement, [...], pm.fwd_only
        )

    def is_applicable_for_range(self, compile_range: Range) -> bool:
        return True

    def __call__(self, graph: torch.fx.Graph):
        self.begin()
        self.matched_count = self.pattern_match_passes.apply(graph)
        self.end_and_log()
```

#### 5.5.2 修改 GraphFusionPassManager

```python
# compilation/graph_fusion_pass_manager.py

class GraphFusionPassManager:
    def configure(self, config: VllmConfig):
        # ... 现有配置 ...

        # 边云协同场景额外 pass
        if get_ascend_config().edge_cloud_config.enabled:
            from .passes.hidden_states_comm_fusion_pass import (
                HiddenStatesSendRecvFusionPass,
            )
            self.passes.append(HiddenStatesSendRecvFusionPass(config))

            # 边云协同场景的 sequence parallelism 需要特殊处理
            if config.compilation_config.pass_config.enable_sp:
                from .passes.edge_cloud_sp_pass import EdgeCloudSequenceParallelismPass
                self.passes.append(EdgeCloudSequenceParallelismPass(config))
```

### 5.6 PIECEWISE 编译配置

```python
# platform.py 边云场景编译配置

def _configure_edge_cloud_compilation(vllm_config: VllmConfig):
    """边云场景的编译配置"""
    compilation_config = vllm_config.compilation_config
    ascend_config = get_ascend_config()

    if not ascend_config.edge_cloud_config.enabled:
        return

    # 边云场景只支持 PIECEWISE 模式
    compilation_config.cudagraph_mode = CUDAGraphMode.PIECEWISE

    # 设置边云通信相关的 splitting_ops
    edge_cloud_ops = [
        "vllm_ascend::hidden_states_send",
        "vllm_ascend::hidden_states_recv",
        "vllm_ascend::sync_barrier",
    ]

    if compilation_config.splitting_ops is None:
        compilation_config.splitting_ops = []

    compilation_config.splitting_ops.extend(edge_cloud_ops)

    # 边云场景禁用 inductor，使用纯 ACL Graph
    compilation_config.use_inductor = False

    # 更新 ACL Graph sizes
    update_aclgraph_sizes(vllm_config)
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
│  Segment 0: embedding + layer_0                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ with torch.npu.graph(aclgraph_segment_0):             │  │
│  │     hidden_states = embedding(input_ids)               │  │
│  │     hidden_states = layer_0(hidden_states)              │  │
│  │     # 发送 hidden_states                               │  │
│  │     torch.ops.vllm_ascend.hidden_states_send(         │  │
│  │         hidden_states, peer_rank=cloud_rank, tag=0      │  │
│  │     )                                                   │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  Segment N: recv + layer_N                                    │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ with torch.npu.graph(aclgraph_segment_n):             │  │
│  │     # 接收 hidden_states                               │  │
│  │     recv_hidden = torch.ops.vllm_ascend.hidden_states_recv(│  │
│  │         shape, dtype, peer_rank=cloud_rank, tag=0       │  │
│  │     )                                                   │  │
│  │     hidden_states = layer_N(recv_hidden)               │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘

云侧 (Cloud):
┌──────────────────────────────────────────────────────────────┐
│  Forward Context                                              │
│  ├── batch_descriptor                                         │
│  ├── cudagraph_runtime_mode = PIECEWISE                     │
│  └── compile_range = (start_layer, end_layer)                │
├──────────────────────────────────────────────────────────────┤
│  Segment 1: recv + middle layers                             │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ with torch.npu.graph(aclgraph_segment_1):             │  │
│  │     # 接收 hidden_states                               │  │
│  │     recv_hidden = torch.ops.vllm_ascend.hidden_states_recv(│  │
│  │         shape, dtype, peer_rank=edge_rank, tag=0       │  │
│  │     )                                                   │  │
│  │     for layer in middle_layers:                        │  │
│  │         recv_hidden = layer(recv_hidden)                │  │
│  │     # 发送 hidden_states 回边侧                         │  │
│  │     torch.ops.vllm_ascend.hidden_states_send(         │  │
│  │         recv_hidden, peer_rank=edge_rank, tag=1        │  │
│  │     )                                                   │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. 通信机制设计

### 6.1 HiddenStatesTransfer 抽象

```python
# edge_cloud/hidden_states_transfer.py

class HiddenStatesTransfer(ABC):
    """HiddenStates 传输抽象接口"""

    @abstractmethod
    def send(
        self,
        hidden_states: torch.Tensor,
        peer_rank: int,
        tag: int,
        async_op: bool = False
    ) -> Optional[torch.distributed.Work]:
        """发送 hidden_states 到对端"""
        pass

    @abstractmethod
    def recv(
        self,
        shape: torch.Size,
        dtype: torch.dtype,
        peer_rank: int,
        tag: int,
    ) -> torch.Tensor:
        """从对端接收 hidden_states"""
        pass

    @abstractmethod
    def recv_async(
        self,
        buffer: torch.Tensor,
        peer_rank: int,
        tag: int,
    ) -> torch.distributed.Work:
        """异步接收 hidden_states 到指定 buffer"""
        pass
```

### 6.2 Mooncake 实现

```python
# edge_cloud/hidden_states_transfer_mooncake.py

class HiddenStatesTransferMooncake(HiddenStatesTransfer):
    """基于 Mooncake 的 HiddenStates 传输实现"""

    def __init__(self, config: TransferConfig):
        self.config = config
        self.transfer_engine = self._init_transfer_engine()
        self.send_queue = queue.Queue(maxsize=config.buffer_size)
        self.recv_buffers = {}

    def send(self, hidden_states, peer_rank, tag, async_op=False):
        if async_op:
            return self.transfer_engine.isend(
                hidden_states, peer_rank, tag=tag
            )
        else:
            self.transfer_engine.send(hidden_states, peer_rank, tag=tag)
            return None

    def recv(self, shape, dtype, peer_rank, tag):
        # 分配 buffer
        if (peer_rank, tag) not in self.recv_buffers:
            self.recv_buffers[(peer_rank, tag)] = torch.empty(
                shape, dtype=dtype, device="npu"
            )
        buffer = self.recv_buffers[(peer_rank, tag)]

        self.transfer_engine.recv(buffer, peer_rank, tag=tag)
        return buffer
```

### 6.3 HCCL 实现（同节点内）

```python
# edge_cloud/hidden_states_transfer_hccl.py

class HiddenStatesTransferHCCL(HiddenStatesTransfer):
    """基于 HCCL 的 HiddenStates 传输实现（用于同节点内通信）"""

    def __init__(self, config: TransferConfig):
        self.config = config
        self.world_size = dist.get_world_size()
        self.rank = dist.get_rank()

        # 创建 HCCL 组
        self.hccl_group = dist.new_group(
            ranks=list(range(self.world_size)),
            backend="hccl"
        )

    def send(self, hidden_states, peer_rank, tag, async_op=False):
        if async_op:
            return dist.broadcast(
                hidden_states,
                src=self.rank,
                group=self.hccl_group,
                async_op=True
            )
        else:
            dist.broadcast(
                hidden_states,
                src=self.rank,
                group=self.hccl_group
            )
            return None
```

---

## 7. 其他模块简要设计

### 7.1 模型加载

```python
# model_loader/layer_shard_loader.py

class LayerShardLoader:
    """按层分片加载模型权重"""

    def __init__(self, node_role, layer_plan):
        self.node_role = node_role
        self.layer_plan = layer_plan

    def load_model(self, model_path):
        """只加载需要的层"""
        # 1. 加载 embedding
        if self.node_role == "edge":
            self.embedding = load_embedding(model_path)

        # 2. 按 layer_plan 加载 transformer 层
        self.layers = {}
        for layer_idx in self.layer_plan:
            if layer_idx == 0 or layer_idx == self.total_layers - 1:
                if self.node_role == "edge":
                    self.layers[layer_idx] = load_transformer_layer(
                        model_path, layer_idx
                    )
            else:
                if self.node_role == "cloud":
                    self.layers[layer_idx] = load_transformer_layer(
                        model_path, layer_idx
                    )
```

### 7.2 调度协同

```python
# scheduler/edge_cloud_scheduler.py

class EdgeCloudScheduler:
    """
    边云协同调度器

    协调边侧和云侧的执行顺序，确保：
    1. 边侧完成 layer_0 后才能发送
    2. 云侧接收到 hidden_states 后才能开始计算
    3. 边侧接收到云侧 hidden_states 后才能执行 layer_N
    """

    def __init__(self, vllm_config):
        self.edge_rank = vllm_config.parallel_config.rank
        self.cloud_ranks = [...]  # 云侧 rank 列表

    def sync_and_execute(self, execute_func, segment):
        """带同步的段执行"""
        if segment == "edge_layer0":
            # 边侧：直接执行
            return execute_func()

        elif segment == "send_to_cloud":
            # 发送后需要等待云侧确认
            send_fut = self.async_send()
            return send_fut

        elif segment == "cloud_middle":
            # 云侧：等待边侧发送完成
            self.wait_peer_send_complete()
            return execute_func()

        elif segment == "send_to_edge":
            # 云侧发送回边侧
            send_fut = self.async_send()
            return send_fut

        elif segment == "edge_layerN":
            # 边侧：等待云侧发送完成
            self.wait_peer_send_complete()
            return execute_func()
```

### 7.3 配置参数

```python
# 使用示例

# 边侧启动
vllm serve --quantization fp8 \
    --additional-config '{
        "edge_cloud_enabled": true,
        "edge_cloud_role": "edge",
        "edge_config": {
            "first_layer": 0,
            "last_layer": -1
        },
        "transfer_config": {
            "backend": "mooncake",
            "buffer_size": 1073741824,
            "peer_rank": 0
        }
    }'

# 云侧启动
vllm serve --quantization fp8 \
    --additional-config '{
        "edge_cloud_enabled": true,
        "edge_cloud_role": "cloud",
        "cloud_config": {
            "start_layer": 1,
            "end_layer": -2
        },
        "transfer_config": {
            "backend": "mooncake",
            "buffer_size": 1073741824,
            "peer_rank": 0
        }
    }'
```

---

## 8. 实现计划

### Phase 1: 基础框架（2周）

| 任务 | 负责人 | 描述 |
|------|--------|------|
| T1.1 | - | 创建 `edge_cloud/` 目录结构 |
| T1.2 | - | 实现 `HiddenStatesTransfer` 抽象接口 |
| T1.3 | - | 实现 Mooncake `HiddenStatesTransfer` |
| T1.4 | - | 实现 `LayerShardLoader` |
| T1.5 | - | 添加 `edge_cloud_config` 到 `AscendConfig` |

### Phase 2: 图编译（3周）

| 任务 | 负责人 | 描述 |
|------|--------|------|
| T2.1 | - | 实现 `hidden_states_send/recv` custom ops |
| T2.2 | - | 实现 `EdgeACLGraphSegment` |
| T2.3 | - | 实现 `CloudACLGraphSegment` |
| T2.4 | - | 实现 `HiddenStatesSendRecvFusionPass` |
| T2.5 | - | 修改 `GraphFusionPassManager` 支持边云场景 |
| T2.6 | - | 修改 `ACLGraphWrapper` 支持跨节点分割 |
| T2.7 | - | 实现 `EdgeCloudSequenceParallelismPass` |

### Phase 3: 集成与测试（2周）

| 任务 | 负责人 | 描述 |
|------|--------|------|
| T3.1 | - | 集成边云协同到 `NPUWorker` |
| T3.2 | - | 实现 `EdgeCloudScheduler` |
| T3.3 | - | 添加端到端测试 |
| T3.4 | - | 性能基准测试 |
| T3.5 | - | 文档编写 |

### Phase 4: 优化（1周）

| 任务 | 负责人 | 描述 |
|------|--------|------|
| T4.1 | - | 通信与计算 overlap 优化 |
| T4.2 | - | 图捕获大小优化 |
| T4.3 | - | 内存优化 |

---

## 附录 A: 关键文件清单

### 新增文件

```
vllm_ascend/
├── edge_cloud/
│   ├── __init__.py
│   ├── manager.py              # EdgeCloudManager
│   ├── hidden_states_transfer.py   # HiddenStatesTransfer 抽象
│   ├── hidden_states_transfer_mooncake.py
│   ├── hidden_states_transfer_hccl.py
│   └── scheduler.py           # EdgeCloudScheduler
├── compilation/
│   └── passes/
│       ├── hidden_states_comm_fusion_pass.py
│       ├── edge_cloud_sp_pass.py
│       └── __init__.py
└── ops/
    └── cross_node_comm.py     # 跨节点通信算子
```

### 修改文件

```
vllm_ascend/
├── ascend_config.py          # 添加 EdgeCloudConfig
├── platform.py                # 边云编译配置
├── compilation/
│   ├── acl_graph.py          # ACLGraphWrapper 扩展
│   └── graph_fusion_pass_manager.py  # 添加新 pass
├── worker/
│   ├── model_runner_v1.py     # 边云协同执行
│   └── worker.py              # NPUWorker 扩展
├── model_loader/
│   └── layer_shard_loader.py  # 按层分片加载
└── attention/
    └── attention_v1.py        # 边云协同 attention
```

---

## 附录 B: 参考资料

1. vLLM-Ascend 现有代码库
2. [ACL Graph 设计文档](./acl_graph_design.md) (待补充)
3. [Mooncake Transfer Engine 文档](https://github.com/AlibabaPAI/mooncake)
4. [Ascend CANN 文档](https://www.hiascend.com/document/content/HAT/CANN)

---

## 附录 C: 术语表

| 术语 | 英文 | 描述 |
|------|------|------|
| 边云协同 | Edge-Cloud Collaboration | 边侧和云侧协同完成推理任务 |
| ACL Graph | ACL Graph | Ascend 加速库的图编译机制 |
| PIECEWISE | PIECEWISE | 分段图编译模式 |
| HiddenStates | Hidden States | Transformer 层的隐藏状态 |
| Splitting Ops | Splitting Operations | 图分割点算子 |
| Layer Shard | Layer Sharding | 按层分片加载/存储模型 |
