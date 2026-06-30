# PP_TIMING 相邻间隔含义表

每段间隔 = `<stage_i> → <stage_{i+1}>` 的时间差，对应这两个打点之间**实际执行的代码**。
"大说明什么"给判断方向，不绝对。所有 stage 含 `*` 期望显式同步（PP_TIMING_SYNC 开时
为准）；未开同步时段含义不变但数值偏小、含异步水分。

## 各角色单步序列（步边界 = worker_entry）

```
standard: worker_entry → forward_entry → forward_done
edge:     worker_entry → send_to_cloud done → recv_from_cloud
          → segment_a_entry → segment_a_done → segment_e_entry → segment_e_done
cloud:    worker_entry → pp_recv_done → segment_c_entry → segment_c_done
```

非标准顺序的相邻对（跨步、回环）见末尾"非步内间隔"。

## edge 角色

| 间隔 (from → to) | 这段在跑什么 | 大说明什么 |
|---|---|---|
| `worker_entry → send_to_cloud done` | 入口处理 + SP 聚合(`_all_gather_tensor_dict`) + `edge_cloud_isend_tensor_dict`(isend) + `handle.wait()` 等发送完成 | SP 聚合开销大（TP 卡多）；或 isend/网络发送慢；wait 等待说明 HCCL 排队 |
| `send_to_cloud done → recv_from_cloud` | edge 已发完，等 cloud 跑完 segment_c 并发回 → **这段≈cloud 中段计算 + 一次网络往返** | cloud segment_c 计算慢（中段层最多），或网络 RTT 大。这是边云最该关注的"等待 cloud"段 |
| `recv_from_cloud → segment_a_entry` | 收回张量后、segment_a 前的准备（构建 attn metadata、buffer 等） | 通常很小；变大说明 prepare 路径有问题 |
| `segment_a_entry → segment_a_done` | edge **head 段**前向（前 head_k 层 + 可能的 embedding） | head 段计算；prefill 步 token 多时此段大属正常 |
| `segment_a_done → segment_e_entry` | head 段结束到 tail 段开始的衔接（context 切换、layer_idx 重置等） | 应极小；变大说明衔接异常 |
| `segment_e_entry → segment_e_done` | edge **tail 段**前向（后 tail_k 层 + norm + 可能的 all_gather hidden） | tail 段计算 + logits/norm；prefill 步大属正常。这是 edge 本地计算主体 |
| `segment_e_done → (步结束)` | 本步收尾（采样、输出封装等，在 runner 外） | 通常不单独看 |

## cloud 角色

| 间隔 (from → to) | 这段在跑什么 | 大说明什么 |
|---|---|---|
| `worker_entry → pp_recv_done` | cloud 入口 + `edge_cloud_broadcast_recv`(irecv) + `wait_for_comm()` 等接收完成 + `cloud_prepare_early`(输入预准备，与 edge segment_a 重叠) | 接收慢（等 edge 发）；若很大说明 edge 发得晚（edge 的 send_to_cloud 段长）→ 看 edge 侧 |
| `pp_recv_done → segment_c_entry` | 收完到中段前向前的准备（attn metadata、图参数更新 `_update_full_graph_params_if_needed`） | 通常小；变大说明图参数更新或 prepare 慢 |
| `segment_c_entry → segment_c_done` | cloud **中段**前向（head_k .. num_layers-tail_k，层最多） | 中段计算主体，prefill 步必然最大。是 cloud 算力的核心指标 |
| `segment_c_done → (步结束)` | 收尾（打包 hidden 回传 edge） | 通常不单独看；含回传时关注 |

## standard 角色（非边云）

| 间隔 (from → to) | 这段在跑什么 | 大说明什么 |
|---|---|---|
| `worker_entry → forward_entry` | 入口 + 可能的 PP 接收(非首 rank 的 `irecv_tensor_dict`) + 输入准备 | PP 非首 rank 时这段含跨 stage 接收；变大说明上一 stage 慢或通信慢 |
| `forward_entry → forward_done` | 完整模型前向（全层） | 主体计算。prefill/decode 差异主要在这段 |
| `forward_done → (步结束)` | 后处理（logits、采样等） | decode 步采样段 |

## 非步内间隔（跨步 / 边界，单独标注，不要混进步内分析）

| 间隔 | 含义 | 用途 |
|---|---|---|
| `segment_e_done → worker_entry(下一步)` | edge 上一步收尾到下一步入口 | 步间 idle / 调度空隙；若稳定偏大说明步间有空转，可排查 scheduler 间隔 |
| `forward_done → worker_entry(下一步)` | standard 同上 | 同上 |
| `segment_c_done → worker_entry(下一步)` | cloud 同上 | 同上 |

> 这些跨步间隔含"非打点代码 + scheduler 空隙"，解读时务必标注"步间/idle"，避免与步内
> 计算段混淆。

## 边云重叠关系（解释为什么某段"看起来大"）

edge 与 cloud 是**并发**的：edge 跑 segment_a 时，cloud 在 `cloud_prepare_early` 预
准备（重叠设计，worker.py 注释明示）。因此：

- edge 的 `worker_entry → send_to_cloud done` 期间，cloud 在做入口+预准备，正常。
- edge 的 `send_to_cloud done → recv_from_cloud`（等 cloud）≈ cloud 的
  `pp_recv_done → segment_c_done`（cloud 接收+中段计算）扣除重叠部分。
  - 若 edge 这段 ≫ cloud 的 segment_c，差值是**网络往返**；若两者接近，瓶颈在 cloud 计算。

## 同步状态对数值的影响

| PP_TIMING_SYNC | 影响 |
|---|---|
| 关（默认） | 时间戳含异步水分；`segment_*` 段可能只反映 kernel 提交；通信段偏小不可信；`send_to_cloud done`/`recv_from_cloud` 因自带 wait 仍较可信 |
| 开 | 每个打点前 `npu.synchronize()`，数值反映真实完成；但会拖慢推理、扭曲被测时序（测量本身改变系统）。通信段与计算段都更准 |

解读前先确认同步状态：`echo $PP_TIMING_SYNC` 或看是否有 `/tmp/vllm_pp_timing_sync=1`。

## 阶段缺失诊断（迁移完整性自查）

若某角色的步序列缺阶段，对应迁移遗漏，指向 migrate-dadian：

| 缺失 | 推断 | 处理 |
|---|---|---|
| edge 缺 `send_to_cloud done` | worker.py R4 打点没迁 | 重迁 send 打点 |
| edge 缺 `recv_from_cloud` | worker.py R5 打点没迁 | 重迁 recv 打点 |
| cloud 缺 `pp_recv_done` | worker.py cloud 接收打点没迁 | 重迁 |
| 缺 `segment_*` | model_runner_v1 打点没迁 | 重迁 _pp_timing 调用 |
| 全角色都没输出 | 开关没开 / rank0 门控把所有进程都挡了 | 查 `pp_timing_enabled` 与 rank0 判定 |
