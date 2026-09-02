# Qwen3.5-27B：P 边云拆分 + PD 分离部署

该目录实现并固化如下唯一目标拓扑：P-edge 2 卡、P-cloud 2 卡、D 2 卡；P 采用 Embedding-Only 边云拆分，P/D 均开启 Qwen3.5 MTP，KV 数据面固定为 `MooncakeLayerwiseConnector`，入口固定为 `load_balance_proxy_layerwise_server_example.py`。D 使用 ACLGraph，不允许 eager 或静默降级。

## 运行结构

```text
Client
  |
  v
Layerwise Proxy
  | first request (remote prefill)             metadata callback
  +---------------------------> D / TP=2 -------------------+
                                                             |
                                                             v
                              P-edge / TP=2 <---------- Proxy
                              Embedding + Scheduler + API
                                      |
                              hidden states / ZMQ decisions
                                      |
                              P-cloud / TP=2
                              all transformer layers + KV
                                      |
                              layerwise Mooncake KV write
                                      |
                                      +---------------------> D / TP=2
```

P-edge 不分配模型 KV cache；调度器使用 P-cloud 汇报的完整 hybrid cache 规格。P-cloud 执行 Qwen3.5 的全部 Transformer/GDN 层并持有 P 侧 KV，在每层完成后通过 Mooncake 写入 D 已分配的 block。D 是普通的非边云 vLLM 实例，只作为 `kv_consumer`，因此不需要边云执行器，但必须使用 `FULL_DECODE_ONLY` ACLGraph。

## 前提

- 三个计算节点分别安装同一组 vLLM 与 vLLM Ascend 提交；模型权重内容及路径一致。
- Mooncake Transfer Engine/CANN/驱动版本在 P-cloud 和 D 间兼容，并已验证 HCCL 与 Mooncake 直连。
- 每个计算节点提供两张可见 NPU。示例可使用 BF16 或 Ascend W8A8 权重；两者通过 `weight_format` 明确区分。
- P-edge、P-cloud、D 使用三个可互达 IP。Proxy 的 `host` 也必须是 D 可回调的具体 IP，不能是 `0.0.0.0`。
- 不设置 `ASCEND_LAUNCH_BLOCKING=1`。该变量与 ACLGraph 不兼容。

## 配置

复制 `deployment.example.json` 为 `deployment.json`，在三台计算节点及 Proxy 节点放置相同内容并修改：

- `model`：仅允许 Qwen3.5-27B。W8A8 使用 `weight_format: "ascend-w8a8"`；BF16 使用 `"bf16"`。
- 四个 IP 必须为跨节点可达的具体地址。
- `devices` 中每个计算角色必须恰好两张卡。
- `network_interfaces` 填各节点承载 HCCL/Gloo 的网卡名。
- `mtp_num_speculative_tokens` 是 P 与 D 共用的唯一值，避免 hybrid Mamba 场景下两端 MTP 深度不一致。
- `p_engine_id` 是本次 P 服务会话的唯一 ID，P-edge/P-cloud 必须相同；P 整体重启时应生成新值，避免仍在运行的 D 复用旧 Transfer Engine 元数据。

本启动器会拒绝卡数、模型标识、端口、IP、MTP 范围等错误配置；正式启动前还会检查本机网卡、角色 IP 和全部监听端口是否可用。对于被重命名、无法从路径确认 `27B` 的本地目录，人工核对权重后才可设置 `allow_unverified_27b: true`；模型 `config.json` 仍必须属于 dense Qwen3.5。

启动器会按角色设置 `VLLM_HOST_IP` 为对应节点 IP；该值同时用于 P-cloud 地址发现和 Mooncake side-channel 广播。在多网卡环境中不能省略或指向管理网地址。

先在任意节点执行四个 dry-run，检查最终命令：

```bash
python examples/edge_cloud_pd_disaggregated_qwen3_5/launch.py decode \
  --config deployment.json --dry-run
python examples/edge_cloud_pd_disaggregated_qwen3_5/launch.py p-edge \
  --config deployment.json --dry-run
python examples/edge_cloud_pd_disaggregated_qwen3_5/launch.py p-cloud \
  --config deployment.json --dry-run
python examples/edge_cloud_pd_disaggregated_qwen3_5/launch.py proxy \
  --config deployment.json --dry-run
```

Decode dry-run 必须同时满足：包含 `FULL_DECODE_ONLY`、`require_aclgraph:true`、`tensor-parallel-size 2` 和 `kv_consumer`；不包含 `--enforce-eager` 或 `--enable-edge-cloud`。

## 启动顺序

1. 在 D 节点启动 Decode：

   ```bash
   python examples/edge_cloud_pd_disaggregated_qwen3_5/launch.py decode \
     --config deployment.json
   ```

2. 在 P-edge 节点启动 rank 0。它会建立 rendezvous 并等待 P-cloud：

   ```bash
   python examples/edge_cloud_pd_disaggregated_qwen3_5/launch.py p-edge \
     --config deployment.json
   ```

3. 随即在 P-cloud 节点启动 headless rank 1：

   ```bash
   python examples/edge_cloud_pd_disaggregated_qwen3_5/launch.py p-cloud \
     --config deployment.json
   ```

4. P 的 API 健康检查通过后，在 Proxy 节点启动指定的 Layerwise Proxy：

   ```bash
   python examples/edge_cloud_pd_disaggregated_qwen3_5/launch.py proxy \
     --config deployment.json
   ```

不要把 P-cloud 当成第二个 prefiller 加入 Proxy；P-edge 与 P-cloud 合起来才是一个逻辑 P 实例。

## 网络端口

| TCP 建连端 | 监听端 | 默认端口 | 用途 |
| --- | --- | ---: | --- |
| Client | Proxy | 8000 | OpenAI API |
| Proxy | P-edge | 8100 | remote prefill API |
| Proxy | D | 8200 | decode API |
| P-cloud | P-edge | 29500 | 两节点分布式 rendezvous |
| P-cloud | P-edge | 29501 | cloud IP 发现 |
| P-cloud | P-edge | 5558 | PRE_OUT SchedulerOutput |
| P-edge | P-cloud | 5559 | POST_OUT SchedulerOutput |
| P-cloud | D | 50001、50002 | Mooncake TP rank 握手；Transfer Engine 另使用其 RPC 端口 |
| D | Proxy | 8000 | `/v1/metaserver` 回调 |

Transfer Engine 的动态 RPC 端口也必须在 P-cloud 与 D 之间互通；从两端 `side_channel` / `te_rpc_port` 初始化日志确认具体值。

## 验收

服务全部 ready 后，从能访问 Proxy 的节点执行：

```bash
python examples/edge_cloud_pd_disaggregated_qwen3_5/smoke_test.py \
  --config deployment.json --requests 4
```

除 API 成功外，还应检查日志中的完整生命周期：

- D：ACLGraph capture/replay 成功，无 eager fallback；`d_scheduler metadata_callback_scheduled` 与 `d_worker waiting_for_kv` 出现。
- Proxy：每个 callback request-id 仅有一次 `prefiller_selected`；重试只产生 `metadata_duplicate_accepted`。
- P-edge：PD scheduler 发出 `PREFILL_FIRST` / draft batches；无 KV cache 分配错误。
- P-cloud：`p_worker kv_cache_registered` 显示 Qwen3.5 hybrid 的多个 cache group，并出现 `layerwise_write_started`。
- D：收到对应 `kv_ready`，请求恢复 decode，最终 API 返回。

建议在正式压测前完成三组硬件用例：单请求（覆盖首轮 graph capture）、4 个并发请求（覆盖 P/D 交错和 Proxy 幂等）、长 prompt + MTP（覆盖 GDN/attention 多 cache group 与 draft 通道）。再与同权重、同采样参数的非 PD TP=2 基线比较输出 token；性能测试需排除首次 ACLGraph capture 的预热请求。

## 失败即停的约束

- `pd_separation` 打开但 connector 不是 `MooncakeLayerwiseConnector/kv_producer` 时，P 启动失败。
- P-edge 与 P-cloud 从共享配置读取同一个 `p_engine_id`，确保调度器与实际持有 KV 的 cloud worker 属于同一逻辑 P engine；缺失该值会启动失败。
- D 设置 `require_aclgraph:true`；若携带 `--enforce-eager`、图模式不是 full graph，或平台把图降级为 `NONE`，启动直接失败。
- P/D 均禁用 prefix caching，避免当前适配范围外的跨实例 prefix 状态组合。
