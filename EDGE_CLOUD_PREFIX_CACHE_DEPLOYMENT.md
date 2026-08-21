# Qwen3.5-Dense 边云 Prefix Cache 协商部署指南

本文档说明如何在现有 Edge:Cloud = 1:1 的 vLLM/vLLM-Ascend 边云系统中，
启用 Prefix Cache 协商和 Cloud 独立 KV Cache 管理。第一阶段使用 Edge 直连
Cloud HTTP 控制服务；第二阶段只将该连接切换到 Higress。

## 1. 当前范围

当前实现支持以下组合：

- Qwen3.5-Dense 文本模型，Hugging Face `model_type` 必须为 `qwen3_5`
  或 `qwen3_5_text`。
- OpenAI Chat Completions API：`/v1/chat/completions`。
- `embedding_only` 和 `head_tail` 边云切分配置。其中本文以
  `embedding_only` 为例。
- PD Separation、Chunked Prefill 和 Prefix Caching。
- Edge 使用 HMAC block Hash 隐藏真实 Prompt；Cloud-facing SchedulerOutput
  中的真实 token ID 也会被替换。
- Cloud 使用独立物理 KV block table，不复用 Edge block ID。

当前不支持：

- Qwen3.5 MoE、其他模型系列或未经校验的 `model_type`。
- Multimodal、LoRA、prompt embeds。
- speculative decoding，包括 MTP、EAGLE/EAGLE3 和独立 Draft Model。
- `n > 1`、beam search 和 prompt logprobs。
- PCP/DCP 上下文并行。
- `/v1/completions` 和离线 LLM API 的 Prefix 协商。

当前以串行或低并发流量为验收范围，尚未实现完整的高并发 admission
reservation、超时回收和故障恢复。

## 2. 网络与端口

示例部署使用以下端口：

| 端口 | 所在节点 | 用途 |
| --- | --- | --- |
| `8500` | Edge | 对用户提供 OpenAI Chat Completions API |
| `29871` | Edge/master | 原有边云分布式启动与通信发现 |
| `8100` | Cloud | Prefix Cache 协商 HTTP/SSE 控制服务 |

`--master-addr` 通常指向分布式 rank 0 所在的 Edge 地址。Edge 配置中的
`control_url` 必须指向 Edge 实际可访问的 Cloud 地址，两者不一定相同。

第一阶段需要允许 Edge 访问 `CLOUD_IP:8100`。该端口只应暴露在内部网络，
不应直接向用户开放。

## 3. 启动前检查

### 3.1 代码版本

Edge 和 Cloud 必须使用相同版本的两个仓库：

```text
vLLM branch:        feat/edge-cloud-prefix-negotiation
vLLM-Ascend branch: feat/edge-cloud-prefix-negotiation
```

### 3.2 模型类型

目录名和 `--served-model-name` 不参与适配判断。分别在 Edge 和 Cloud 检查
模型配置：

```bash
jq -r '.model_type, (.text_config.model_type // empty)' MODEL_PATH/config.json
```

输出必须包含以下值之一：

```text
qwen3_5
qwen3_5_text
```

如果模型目录名是 `Qwen3.6-27B`，但配置仍为上述 Qwen3.5 model type，可以
继续使用；如果实际 model type 是 `qwen3_6`，当前实现会拒绝启动，不能仅通过
修改校验列表绕过。

### 3.3 模型与 Tokenizer 一致性

Edge 和 Cloud 必须使用完全相同的：

- 模型版本和配置；
- Tokenizer 文件；
- Chat Template；
- KV block size；
- 边云层切分和并行配置。

协议不会把模型版本或 Tokenizer 内容发送给 Cloud。两侧配置不一致可能造成
错误推理，因此部署系统必须保证这些文件来自同一个模型制品。

### 3.4 创建 Edge 租户密钥

只在 Edge 创建 HMAC 密钥，Cloud 不需要该密钥：

```bash
install -d -m 700 /run/secrets
umask 077
openssl rand -hex 32 > /run/secrets/edge-cloud-tenant-key
```

允许共享 Prefix Cache 路由历史的 Edge 必须使用相同密钥；不同企业应使用
不同密钥。密钥文件去除首尾空白后必须至少包含 16 bytes。

## 4. 第一阶段：Edge 直连 Cloud

以下示例沿用 1 个 Edge NPU 和 4 个 Cloud NPU，并采用
`embedding_only + async scheduling + chunk prefill prior`。

首次验证建议将外部请求并发限制为 1。可以保留 `--max-num-seqs 128`，但在
完成串行正确性验证前不要直接施加 128 并发；也可以临时将其改为 1。

### 4.1 Edge 启动命令

将 `CLOUD_IP` 替换为 Edge 能够访问的 Cloud 内网地址。

```bash
vllm serve /home/extra/Qwen3.5-27B \
    --served-model-name "qwen3.5" \
    --host 0.0.0.0 \
    --port 8500 \
    --master-addr 76.76.26.17 \
    --master-port 29871 \
    --max-model-len 262144 \
    --max-num-batched-tokens 8192 \
    --max-num-seqs 128 \
    --gpu-memory-utilization 0.95 \
    --async-scheduling \
    --enable-prefix-caching \
    --trust-remote-code \
    --nnodes 2 \
    --node-rank 0 \
    --enable-edge-cloud \
    --edge-npu-count 1 \
    --cloud-npu-count 4 \
    --additional-config '{
      "enable_cpu_binding": true,
      "enable_weight_nz_layout": true,
      "edge_cloud_config": {
        "enabled": true,
        "role": "edge",
        "mode": "embedding_only",
        "enable_decode_graph": true,
        "edge_head_tail_layers": 0,
        "pd_separation": {
          "enabled": true,
          "next_prefill_prior_enable": true,
          "limit_prefill_batch_size": false,
          "chunk_prefill_prior_enable": true,
          "max_chunk_prefill_ahead": 1
        },
        "prefix_cache_coordination": {
          "enabled": true,
          "control_url": "http://CLOUD_IP:8100/v1/chat/completions",
          "tenant_key_file": "/run/secrets/edge-cloud-tenant-key",
          "connect_timeout": 5.0
        }
      }
    }' \
    --compilation-config '{
      "cudagraph_mode": "FULL_DECODE_ONLY",
      "cudagraph_capture_sizes": [1, 2, 4, 8, 16, 32]
    }'
```

### 4.2 Cloud 启动命令

Cloud 的 `instance_id` 必须在所有 Cloud 实例中唯一。Cloud 不配置
`tenant_key_file`。

```bash
vllm serve /weight/Qwen3.5-27B \
    --served-model-name "qwen3.5" \
    --headless \
    --master-addr 76.76.26.17 \
    --master-port 29871 \
    --max-model-len 262144 \
    --max-num-batched-tokens 8192 \
    --max-num-seqs 128 \
    --gpu-memory-utilization 0.95 \
    --async-scheduling \
    --enable-prefix-caching \
    --trust-remote-code \
    --nnodes 2 \
    --node-rank 1 \
    --enable-edge-cloud \
    --edge-npu-count 1 \
    --cloud-npu-count 4 \
    --additional-config '{
      "enable_cpu_binding": true,
      "enable_weight_nz_layout": true,
      "edge_cloud_config": {
        "enabled": true,
        "role": "cloud",
        "mode": "embedding_only",
        "enable_decode_graph": true,
        "edge_head_tail_layers": 0,
        "pd_separation": {
          "enabled": true,
          "next_prefill_prior_enable": true,
          "limit_prefill_batch_size": false,
          "chunk_prefill_prior_enable": true,
          "max_chunk_prefill_ahead": 1
        },
        "prefix_cache_coordination": {
          "enabled": true,
          "listen_host": "0.0.0.0",
          "listen_port": 8100,
          "instance_id": "cloud-0"
        }
      }
    }' \
    --compilation-config '{
      "cudagraph_mode": "FULL_DECODE_ONLY",
      "cudagraph_capture_sizes": [1, 2, 4, 8, 16, 32]
    }'
```

## 5. 第一阶段验证

### 5.1 HTTP 检查

等待两侧完成模型初始化，然后从 Edge 所在网络检查 Cloud 控制服务：

```bash
curl --fail --show-error http://CLOUD_IP:8100/health
```

预期响应：

```json
{"status":"ok"}
```

该接口只证明 HTTP 进程可访问，不保证底层 KV Manager 已完成初始化。正式
请求应在 Edge 和 Cloud 都进入服务状态后发起。

### 5.2 冷请求

只使用 Chat Completions：

```bash
curl --fail --show-error http://EDGE_IP:8500/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "qwen3.5",
      "messages": [
        {"role": "user", "content": "请总结这段足够长且可重复的测试上下文。"}
      ],
      "max_tokens": 32,
      "stream": false
    }'
```

冷请求预期 Cloud Prefix 命中为 0。Edge 会在内部为该请求建立一个长 SSE
连接，Cloud 在推理完成后通过该连接返回标准 OpenAI usage。

### 5.3 重复 Prefix

等待冷请求完整结束后，再发送具有相同长 Prefix 的请求。检查日志和 usage：

- Cloud 返回的 Prefix hit tokens 大于 0；
- Edge 实际复用量不超过 Cloud hit；
- `prompt_tokens`、`completion_tokens` 和 `total_tokens` 正确；
- `prompt_tokens_details.cached_tokens` 等于实际 Edge/Cloud 公共命中量；
- 相同输入的输出与关闭协商机制时逐 token 一致。

Prefix Cache 只能复用完整 KV block。短于一个 block 或只在尾部不完整 block
内重复的 Prompt，可以被路由但不会形成可复用 KV block。

### 5.4 Qwen3.5 Mamba 回归

至少覆盖以下用例：

1. Prefix 完全未命中；
2. Prefix 命中多个完整 block；
3. 命中 Prefix 后，剩余 suffix 在一个 prefill chunk 内处理完；
4. Prompt 跨越 Mamba state-block 边界；
5. 长 Prompt 被切成多个 Chunked Prefill；
6. 同一请求启用 `next_prefill_prior_enable` 和
   `chunk_prefill_prior_enable`；
7. 连续重复请求不会出现 Mamba metadata 复用、KeyError 或请求悬挂。

完成串行验证后，再按 2、4、8、16 等梯度提高并发，观察 KV block 使用量、
请求完成率和输出一致性。

## 6. 第二阶段：接入 Higress

Higress MVP 不需要修改源码。Cloud 配置保持不变，只修改 Edge 的
`control_url`：

```json
{
  "prefix_cache_coordination": {
    "enabled": true,
    "control_url": "http://HIGRESS_HOST/INTERNAL_ROUTE/v1/chat/completions",
    "tenant_key_file": "/run/secrets/edge-cloud-tenant-key",
    "connect_timeout": 5.0
  }
}
```

Higress 需要：

- 配置到 Cloud 控制服务的内部路由和健康检查；
- 开启 `ai-load-balancer` 的 `prefix_cache` 策略并配置 Redis；
- 开启 `ai-statistics`；
- 禁止该内部 POST 的自动重试；
- 调高或关闭长 SSE 的 stream idle timeout；
- 允许 `X-Edge-Cloud-*` 响应头透传；
- 保持 HTTP stream 到最终 usage 和 `[DONE]` 后再结束。

当前内部 HTTP 场景不使用鉴权或 TLS。如果后续启用 Higress 鉴权、HTTPS 或
mTLS，需要另外扩展 Edge HTTP Client 的认证配置。

## 7. 协商链路日志与排障

所有 Prefix 协商、Cloud KV 预约和 usage 回传日志都带统一标记：

```text
[EDGE_CLOUD_PREFIX]
```

每条日志还包含稳定的 `event=<事件名>`，并尽量携带 `request_id`、
`control_request_id`、`engine_request_id`、`head_token`、命中 token 数或请求数。
日志不会记录原始 Prompt、token ID 列表、Hash 值、tenant key 或完整 HTTP body。

默认 INFO 日志可以观察一次请求的关键状态转换：

| 阶段 | Edge 事件 | Cloud 事件 |
| --- | --- | --- |
| HTTP 协商 | `edge_negotiate_start`、`edge_probe_response` | `cloud_http_probe_reserved`、`cloud_kv_probe_reserved` |
| 数据面接入 | `edge_scheduler_request_published` | `cloud_kv_admission_start`、`cloud_kv_admission_complete` |
| Prefill 完成 | `edge_prefill_ack_received` | `cloud_prefill_ack_published` |
| 请求结束 | `edge_finish_manifest_created`、`edge_usage_received` | `cloud_kv_request_finished`、`cloud_sse_usage_ready` |

查看两侧全部关键日志：

```bash
grep -F '[EDGE_CLOUD_PREFIX]' edge.log
grep -F '[EDGE_CLOUD_PREFIX]' cloud.log
```

使用控制请求 ID 串联 Edge 和 Cloud 日志（日志中的字符串值带单引号）：

```bash
grep -F "request_id='REQUEST_ID'" edge.log cloud.log
grep -F "control_request_id='REQUEST_ID'" edge.log cloud.log
```

`edge_scheduler_request_published` 会同时打印控制请求 ID 和 Engine 内部请求 ID；
得到 Engine ID 后，可以继续检查 KV 分配和 finish 路径：

```bash
grep -F "engine_request_id='ENGINE_REQUEST_ID'" edge.log cloud.log
```

快速检查异常处理分支：

```bash
grep -E '\[EDGE_CLOUD_PREFIX\].*event=[^ ]*(failed|missing|without|orphaned|rejected|cancelled|duplicate|malformed|unknown)' edge.log cloud.log
```

需要观察每批 SchedulerOutput、KV slots 分配和 worker ACK 时，在 Edge 和 Cloud
启动前设置：

```bash
export VLLM_LOGGING_LEVEL=DEBUG
```

DEBUG 模式会增加每个调度批次的日志量，只建议在复现窗口内开启。排障时应先确认
同一请求依次出现预约、接入、ACK、finish 和 usage；缺少哪一个事件，故障通常就位于
该事件与前一个事件之间。

## 8. 常见问题

### 8.1 启动时报模型不受支持

典型错误包含：

```text
prefix cache coordination currently supports only Qwen3.5-Dense
```

检查实际 `hf_text_config.model_type`。不要通过删除校验强行运行未适配模型。

### 8.2 Edge 无法连接 Cloud 8100

检查：

- `control_url` 使用的是 Cloud 可达地址，而不是错误地复用 Edge
  `--master-addr`；
- Cloud 防火墙和容器端口映射允许 `8100`；
- Cloud 配置启用了 `prefix_cache_coordination`；
- Cloud 进程没有因模型或 KV 初始化失败而退出。

### 8.3 tenant key 错误

检查密钥文件存在、运行用户可读，且去除首尾空白后至少为 16 bytes。Cloud
不应持有或配置该密钥。

### 8.4 Edge/Cloud block size 不一致

协议会 fail closed。确保两侧 vLLM/vLLM-Ascend 版本、模型配置、KV cache
配置和 block size 一致。

### 8.5 重复请求仍然不命中

检查：

- 前一个请求已经完成，Cloud worker ACK 已使 blocks 可见；
- Prompt 至少包含一个完整 KV block；
- 请求使用相同 Tokenizer、Chat Template 和租户密钥；
- Cloud KV Cache 没有因容量压力淘汰对应 blocks；
- 日志中的 request ID、Cloud instance ID 和 hit tokens 对应同一次请求。

### 8.6 Mamba KeyError、未绑定变量或 Prefix suffix 请求悬挂

确认当前 vLLM-Ascend 分支包含以下修复：

```text
fix(model_runner): preserve Mamba copy metadata in cloud fast path
fix(model_runner): skip remote Mamba cache preprocessing
fix(scheduler): classify cached suffix as final prefill chunk
```

这些修复分别处理 Cloud Mamba fast path metadata、`embedding_only` Edge 的
remote-only Mamba cache，以及 Prefix 命中后最终 suffix chunk 的状态转换。

## 9. 生产化前置条件

当前版本用于功能验证。在生产化之前至少需要完成：

- 真实 Qwen3.5-27B Ascend 双机 E2E；
- 长时间并发和 KV 容量压力测试；
- 用户 abort、Edge/Cloud 进程退出和网络中断故障注入；
- reservation 超时回收和幂等释放；
- Higress 路由、Header、active request 生命周期和 usage 统计验证；
- 每租户 usage 的持久化、去重、对账和计费规则实现。
