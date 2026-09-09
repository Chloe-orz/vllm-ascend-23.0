# Qwen3.5-Dense 边云 Prefix Cache 协商部署指南

本文档说明如何在现有 Edge:Cloud = 1:1 的 vLLM/vLLM-Ascend 边云系统中，
启用 Prefix Cache 协商和 Cloud 独立 KV Cache 管理。第一阶段使用 Edge 直连
Cloud HTTP 控制服务；第二阶段将该连接切换到 NewAPI 或 Higress。

## 1. 当前范围

当前实现支持以下组合：

- Qwen3.5-Dense 模型，Hugging Face `model_type` 必须为 `qwen3_5`
  或 `qwen3_5_text`。支持纯文本请求，以及
  `Qwen3_5ForConditionalGeneration` 的图片请求；图片请求使用
  `edge-cloud-prefix-v2` 媒体感知 Hash ABI。
- OpenAI Chat Completions API：`/v1/chat/completions`。
- `embedding_only` 和 `head_tail` 边云切分配置。其中本文以
  `embedding_only` 为例。
- PD Separation、Chunked Prefill 和 Prefix Caching。
- Qwen3.5-Dense MTP speculative decoding。当前只支持 `method=mtp`，Edge 和
  Cloud 必须配置相同的 `num_speculative_tokens`，并同时启用异步调度。
- Edge 使用 HMAC block Hash 隐藏真实 Prompt；Cloud-facing SchedulerOutput
  中的 Prompt、生成 token 和 speculative token ID 也会被替换。
- Cloud 使用独立物理 KV block table，不复用 Edge block ID。

当前不支持：

- Qwen3.5 MoE、其他模型系列或未经校验的 `model_type`。
- 音频、视频、LoRA、prompt embeds、image embeds。图片以外的多模态输入和
  预计算 embedding 仍不支持。
- EAGLE/EAGLE3、独立 Draft Model 及 MTP 之外的 speculative decoding。
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
| `29872` | Edge/master | Cloud 向 Edge 上报地址的 TCPStore（`master_port + 1`） |
| `5558` | Edge | PD PRE_OUT，Cloud 连接 Edge |
| `5559` | Cloud | PD POST_OUT，Edge 连接 Cloud |
| `8100` | Cloud | Prefix Cache 协商 HTTP/SSE 控制服务 |

`--master-addr` 通常指向分布式 rank 0 所在的 Edge 地址。Edge 配置中的
`control_url` 必须指向 Edge 实际可访问的 Cloud 地址，两者不一定相同。

第一阶段需要允许 Edge 访问 Cloud 的 `5559` 和 `8100`，并允许 Cloud 访问
Edge 的 `29872` 和 `5558`。这些端口只应暴露在内部网络，不应直接向用户开放。

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
jq -r '.architectures[], .model_type, (.text_config.model_type // empty), (.language_model_only // empty)' MODEL_PATH/config.json
```

输出必须包含以下值之一：

```text
qwen3_5
qwen3_5_text
```

如果模型目录名是 `Qwen3.6-27B`，但配置仍为上述 Qwen3.5 model type，可以
继续使用；如果实际 model type 是 `qwen3_6`，当前实现会拒绝启动，不能仅通过
修改校验列表绕过。

`Qwen3_5ForConditionalGeneration` 不会因为 `language_model_only` 为 `false` 被
启动校验拒绝。只要请求中的 `messages` 全部是文本，Prefix Cache 协商即可运行。

如果希望从进程层面禁用多模态输入并跳过视觉塔，可选择在 Edge 和 Cloud
启动命令中同时增加：

```bash
--language-model-only
```

该参数是可选的省显存与强约束手段，不是文本请求运行的前提；无需修改模型
目录中的 `config.json`。

### 3.3 模型与 Tokenizer 一致性

Edge 和 Cloud 必须使用完全相同的：

- 模型版本和配置；
- Tokenizer 文件；
- Chat Template；
- KV block size；
- 边云层切分和并行配置。

协议不会把模型版本或 Tokenizer 内容发送给 Cloud。两侧配置不一致可能造成
错误推理，因此部署系统必须保证这些文件来自同一个模型制品。

Edge 与 Cloud 可以把同一制品挂载到不同本地目录（本指南示例分别为
`/home/extra/...` 与 `/weight/...`）；MM-ABI 指纹不会把本地挂载路径当作执行
语义。Edge 与 Cloud 可使用适配 910B/910C 等不同硬件的软件镜像，但两个仓库的
协议实现必须兼容，模型、Tokenizer、层切分和数据面配置仍须一致。希望互相共享
媒体 KV 的多个 Edge 还应保持 processor 配置和预处理软件版本一致；否则其
fingerprint 不同，只会产生安全的假 miss。

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

直连无鉴权的 Cloud 控制服务时无需 API Token。经 NewAPI 等支持 Bearer
鉴权的网关时，设置环境变量 `VLLM_ASCEND_EDGE_CLOUD_API_KEY`，值为 `sk-...`，
不要包含空白或 `Bearer` 前缀。Edge 在首次创建控制客户端时读取该变量，
并发送 `Authorization: Bearer <token>`，轮换令牌后
需重启 Edge API 进程。令牌与 `tenant_key_file` 中的 HMAC 密钥独立。
NewAPI 根据令牌对应的用户及最终 usage 计费，可为每个 Edge 分配独立令牌。
旧的 `consumer_id` 配置已移除，Edge 不再发送 `X-Mse-Consumer`。

### 4.2 Cloud 启动命令

Cloud 的 `instance_id` 必须在所有 Cloud 实例中唯一。Cloud 不配置
`tenant_key_file`，也无需设置 `VLLM_ASCEND_EDGE_CLOUD_API_KEY`。

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
          "instance_id": "cloud-0",
          "enforce_mm_abi_match": false
        }
      }
    }' \
    --compilation-config '{
      "cudagraph_mode": "FULL_DECODE_ONLY",
      "cudagraph_capture_sizes": [1, 2, 4, 8, 16, 32]
    }'
```

`enforce_mm_abi_match` 默认 `false`。默认模式只校验并回显 Edge 发送的 MM-ABI
header，不要求异构 Edge/Cloud 镜像计算出相同指纹。若部署使用同构镜像并希望在
Probe 前强制发现模型、processor 或软件版本漂移，可在 Cloud 设为 `true`；该模式
下不一致请求会以 `mm_abi_mismatch` 返回 400。

### 4.3 可选：启用 MTP

Prefix Cache 协商支持 Qwen3.5-Dense 自带的 MTP drafter。需要在上述 Edge 和
Cloud 两条命令中同时增加完全相同的配置，例如：

```bash
--speculative-config '{"num_speculative_tokens":3,"method":"mtp","enforce_eager":true}'
```

MTP 模式下 Cloud KV 管理器会使用与主 Scheduler 相同的 EAGLE/MTP KV group
语义，并为目标模型批次预留 speculative lookahead blocks。独立调度的
`DRAFT_FIRST` 只复用该目标批次已经分配的 Cloud block table，不会重复分配或
重复推进 `num_computed_tokens`。只有匹配的 MTP draft chain 完成，Prompt block
才会对后续 Prefix probe 可见；若 draft token 被拒绝，Cloud 影子请求会在 chain
结束时回退到 Edge 给出的实际 accepted token 数。

若 draft task 在最终 ACK 前被丢弃，Edge 会先通过 control-only EMPTY 通知 Cloud
禁止该请求在 FINISH 新增发布缓存，再释放被 MTP 扣留的 FINISH 和 usage。即使此时
已经没有后续计算 batch，控制面仍会完整闭环；runner metadata 会在未来 FIRST
batch 中幂等清理。同步与 async scheduling 使用相同的 EMPTY 发布判定；PRE_OUT
携带 FINISH/invalidation 时会等待后台 publisher 完成序列化并把消息交给 ZMQ；
stopped、bridge queue 满、序列化或 socket send 失败不会静默确认，控制状态仅在
本地交付成功后消费。

当前该组合仅适配 `method=mtp`。配置 EAGLE/EAGLE3 或独立 Draft Model 会在启动
阶段被拒绝。

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

## 6. 第二阶段：接入 AI 网关

NewAPI 接入时，在启动边侧服务前设置令牌：

```bash
export VLLM_ASCEND_EDGE_CLOUD_API_KEY='sk-你的NewAPI令牌'
```

边侧配置如下：

```json
{
  "prefix_cache_coordination": {
    "enabled": true,
    "control_url": "http://NEWAPI_HOST/v1/chat/completions",
    "tenant_key_file": "/run/secrets/edge-cloud-tenant-key",
    "connect_timeout": 5.0,
    "probe_timeout": 30.0
  }
}
```

输入 Token 数通过 `X-Edge-Cloud-Prompt-Tokens` 请求头传输，云侧要求该头为
非负十进制整数，并核对摘要块数及尾块是否一致。请求体只保留标准 OpenAI
字段 `model`、`messages`、`stream`、`stream_options`；不再发送或读取旧的
`edge_cloud_prompt_tokens` 请求体字段，边云需同步升级。

NewAPI 使用普通 OpenAI 渠道，在独立请求头覆盖中配置
`{"regex:(?i)^x-edge-cloud-": ""}` 即可保留控制元数据，无需为此开启
`pass_through_body_enabled`。关闭系统提示词注入、消息改写及供应商协议转换，
保持摘要消息的内容和顺序。边侧的 API Token 由 NewAPI 用于鉴权，不需透传给云侧。

回程不再依赖 `X-Edge-Cloud-*` 响应头，不需要修改 NewAPI：

1. Cloud 完成 Prefix 预约后，立即发送标准 OpenAI SSE chunk，在
   `choices[0].delta.content` 中放置 JSON 编码的 `edge_cloud_probe` 控制消息。
   消息包含 `protocol`、`request_id`、`instance_id`、`block_size`、`hit_blocks`、
   `hit_tokens`；v2 额外包含 `mm_abi`。
2. 紧跟一个 `delta: {}`、`finish_reason: null` 的标准 chunk，推动 NewAPI
   转发暂存的前一个 Probe chunk。只发 Probe 或 SSE comment 不足以解除该缓冲。
3. Edge 读取并校验 Probe 后开始数据面推理，后台继续消费同一个 SSE 迭代器。
   这条内部控制流不会作为模型回答转发给用户。
4. 等待推理完成期间，Cloud 每 10 秒发送 SSE comment，维持网关上游读活跃；
   完成后发送 `choices: []` 的标准 usage chunk（含 `cached_tokens`）及 `[DONE]`。
   NewAPI 按最终 usage 计费，不按 Probe JSON 的文本长度计费。

`probe_timeout` 默认 30 秒，限制从发起 HTTP 请求到读到完整 Probe 的等待，
包括 Cloud admission 等待；它不是推理总时限。网关的上游流式空闲超时应大于
10 秒并留余量，总请求时限要覆盖完整推理。NewAPI 不会转发 SSE comment，若边侧
与 NewAPI 之间还有设置空闲超时的代理，应开启 NewAPI 下游 SSE ping 或相应调高超时。
仍应禁用控制请求的自动重试。云侧响应头仅保留作直连调试或网关观测，不参与协商。
此次开发态改动无旧响应头协议回退，Edge 和 Cloud 必须同步升级。

已使用未修改的 NewAPI v1.0.0-rc.34 隔离实例，与实际 EdgePrefixClient、Cloud HTTP/SSE
控制服务联调：关闭请求体透传，仅配置上述请求头规则；两边同 request ID 并发，
覆盖 v1/v2 和用户 `stream=false/true` 共 8 个请求。全部在发布 FINISH 前收到 Probe，
最终 usage、缓存 Token 和网关计费记录一致，并验证了心跳保活。仅 KV Probe 与
推理完成事件使用模拟值，未执行 NPU 推理。详见
[NewAPI 控制面验证记录](EDGE_CLOUD_NEWAPI_VALIDATION.md)。

以下 Higress 插件配置保留作为参考；Edge 不再提供 Higress 专用计费 Header，
若仍使用该网关，应由其认证插件建立 Consumer 身份。

从服务来源、透明路由、超时/重试、`ai-statistics`、联合验证到回退的完整操作，见
[边云 Prefix Cache 协商接入 Higress 验证指南](EDGE_CLOUD_HIGRESS_VALIDATION.md)。

接入支持 Bearer 鉴权的 Higress 路由时，Cloud 配置保持不变，修改 Edge 的
`control_url`，并设置 `VLLM_ASCEND_EDGE_CLOUD_API_KEY` 为该网关的 API Token：

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
- 开启 `ai-statistics`；
- 禁止该内部 POST 的自动重试；
- 调高或关闭长 SSE 的 stream idle timeout；
- 通过认证插件根据 Bearer 凭据建立计费 Consumer 身份；
- 保持 SSE content delta 不变并及时转发；`X-Edge-Cloud-*` 响应头仅在需要观测时透传；
- 保持 HTTP stream 到最终 usage 和 `[DONE]` 后再结束。

在当前 1:1 或只验证统计信息的场景中，不需要 `ai-load-balancer` 和 Redis，
普通静态路由即可。只有增加多个 Mock/真实 Cloud backend、验证 Prefix 历史路由
和 least-request 回退时，才需要开启 `ai-load-balancer` 的 `prefix_cache` 策略并
配置 Redis。

Edge 通过 `VLLM_ASCEND_EDGE_CLOUD_API_KEY` 提供 Bearer 凭据；部署时使用 HTTPS 保护令牌。
如果使用 mTLS，需要另外配置客户端证书支持。`X-Mse-Consumer` 如仍用于
Higress 统计，应由认证插件根据凭据生成或覆盖，不能信任客户端自声明的值。

### 6.1 北向非流式请求与内部长 SSE

用户请求中的 `stream` 只控制 Edge 向用户返回结果的方式。Edge 构造内部 Cloud
control 请求时，会固定覆盖为：

```json
{
  "stream": true,
  "stream_options": {
    "include_usage": true
  }
}
```

因此，即使用户发送 `stream=false`，Edge 对网关/Cloud 的内部统计通道仍是
长 SSE。Cloud 先通过标准 content delta 返回 Prefix 预约结果，推理完成后再在同一连接中发送
`choices: []`、标准 OpenAI usage 和 `[DONE]`。网关看到的是长 SSE，Edge
向用户返回的仍可以是普通非流式 JSON，两者没有冲突。

Higress `ai-statistics` 同时兼容普通 `application/json` 非流式响应。该路径适合
独立验证插件能力或未来的其他 OpenAI 兼容路由，但不是当前边云 control 请求的
实际传输形态。

### 6.2 ai-statistics 配置与字段语义

在内部路由上开启内置 `ai-statistics`，推荐使用轻量配置：

```yaml
use_default_response_attributes: true
```

如果 Console 表单没有展示该字段，切换到 YAML 编辑模式填写。该配置会从
OpenAI Chat Completions 的流式或非流式 usage 中提取：

- `prompt_tokens` -> Prometheus `input_token` Counter；
- `completion_tokens` -> Prometheus `output_token` Counter；
- `total_tokens` -> Prometheus `total_token` Counter；
- `prompt_tokens_details.cached_tokens` -> `ai_log.cached_tokens`；
- 完整的 `prompt_tokens_details` -> `ai_log.input_token_details`。

`cached_tokens` 当前不是独立的 Prometheus Counter。需要按 Cloud 实际计算量计费
时，可以由日志消费或账单系统计算：

```text
uncached_prompt_tokens = prompt_tokens - cached_tokens
cloud_compute_tokens = uncached_prompt_tokens + completion_tokens
```

`ai-statistics` 独立于 `attributes` 配置读取请求头 `X-Mse-Consumer`，并把它写入
Prometheus 标签 `ai_consumer`。Header 缺失时标签回退为 `none`。因此 Consumer
Usage 的来源区分依赖 Higress 认证插件产生的 Consumer 身份，不需要额外添加
`attributes.consumer`。

在 `ai-statistics 2.0.1` 中，`use_default_response_attributes: true` 会优先使用
内置轻量属性列表，同时忽略显式的 `attributes` 列表。如需在保留 token 明细的
同时记录 Cloud 实例和 Prefix 命中响应头，应改为下面的完整显式配置：

```yaml
attributes:
  - key: reasoning_tokens
    apply_to_log: true
  - key: cached_tokens
    apply_to_log: true
  - key: input_token_details
    apply_to_log: true
  - key: output_token_details
    apply_to_log: true
  - key: edge_cloud_instance
    value_source: response_header
    value: x-edge-cloud-instance-id
    apply_to_log: true
  - key: edge_cloud_hit_tokens
    value_source: response_header
    value: x-edge-cloud-prefix-hit-tokens
    apply_to_log: true
```

这些自定义字段默认也不是 Prometheus 标签，避免把高基数字段直接引入指标系统。

### 6.3 本地隔离验证结果

Higress 统计可以在不启动 vLLM、不使用 NPU 的情况下独立验证。已完成以下本地
黑盒验证：

- Higress 源码：`v2.2.4`，commit `58666ac9`；
- 镜像：`higress/all-in-one:latest-o11y`；
- 内置插件：`ai-statistics 2.0.1`；
- upstream：返回 OpenAI usage 的 Mock Cloud HTTP Server；
- 路由：静态 1:1 `/v1/chat/completions` 路由，不启用负载均衡插件。

使用下面的 usage 分别验证长 SSE 和普通 JSON：

```json
{
  "prompt_tokens": 6814,
  "completion_tokens": 32,
  "total_tokens": 6846,
  "prompt_tokens_details": {
    "cached_tokens": 6144
  }
}
```

两种返回方式均满足：

- `X-Edge-Cloud-Instance-ID` 和 Prefix hit 响应头原样透传；
- 每次成功请求只增加一次 token Counter；
- input/output/total 指标分别增加 `6814`、`32`、`6846`；
- SSE 日志为 `response_type=stream`，普通 JSON 为 `response_type=normal`；
- 两种日志均记录 `cached_tokens=6144`；
- 请求携带 `X-Mse-Consumer: enterprise-a` 时，指标生成
  `ai_consumer="enterprise-a"`；不携带时回退为 `ai_consumer="none"`；
- upstream `503` 不增加 token Counter，但保留状态码、response flag 和空 usage
  的访问日志，便于异常排查。

可直接从 Gateway 指标端点检查路由维度计数：

```bash
curl --silent http://127.0.0.1:15020/stats/prometheus \
  | grep -E 'route_upstream_model_consumer_metric_(input_token|output_token|total_token|llm_duration_count)'
```

使用 `latest-o11y` 镜像时，还可以从 Prometheus 查询相同指标，并从 Loki 或
`/var/log/proxy/access.log` 检查 `ai_log`。指标标签至少包含 `ai_route`、
`ai_cluster`、`ai_model` 和 `ai_consumer`。

例如，只检查某个计费租户的精确累计 Counter：

```bash
curl --silent http://127.0.0.1:15020/stats/prometheus \
  | grep 'ai_consumer="enterprise-a"'
```

Higress 内置 Dashboard 的 Consumer Usage 使用 Prometheus `increase()` 计算所选
时间窗口的增量。新 consumer 的第一条请求会在 Counter 已非零后才创建序列，且
`increase()` 会对采样窗口做边界外推，因此短时间测试可能看不到第一条请求，或
显示非整数。隔离验证时应以 Gateway 原始 Counter 和逐请求 `ai_log` 为准；若要
观察 Dashboard，至少为同一个 consumer 连续发送两次请求并等待 Prometheus 抓取。
历史 `ai_consumer="none"` 不会被重命名，会在所选时间窗口过去后消失。

该隔离验证只证明路由透传和统计解析正确，不能替代真实 Edge + Cloud 对长连接
生命周期、idle timeout、active request 和 Prefix 路由选择的联合验收。

## 7. 协商链路日志与排障

所有 Prefix 协商、Cloud KV 预约和 usage 回传日志都带统一标记：

```text
[EDGE_CLOUD_PREFIX]
```

每条日志还包含稳定的 `event=<事件名>`，并尽量携带 `request_id`、
`control_request_id`、`engine_request_id`、`head_token`、命中 token 数或请求数。
日志不会记录原始 Prompt、token ID 列表、Hash 值、tenant key 或完整 HTTP body。
Edge 的 `edge_client_initialized` 记录 `authenticated`，表示是否配置了网关
鉴权；日志不记录 API Token。

默认 INFO 日志可以观察一次请求的关键状态转换：

| 阶段 | Edge 事件 | Cloud 事件 |
| --- | --- | --- |
| HTTP 协商 | `edge_negotiate_start`、`edge_probe_response` | `cloud_http_probe_reserved`、`cloud_kv_probe_reserved` |
| 数据面接入 | `edge_scheduler_request_published` | `cloud_kv_admission_start`、`cloud_kv_admission_complete` |
| Prefill 完成 | `edge_prefill_ack_received` | `cloud_prefill_ack_published` |
| 请求结束 | `edge_finish_manifest_created`、`edge_usage_received` | `cloud_kv_request_finished`、`cloud_sse_usage_ready` |

启用 MTP 后，还可以搜索以下 Cloud 事件：

```text
cloud_kv_mtp_draft_rewritten
cloud_kv_mtp_acceptance_recorded
cloud_kv_mtp_draft_chain_completed
cloud_kv_computed_tokens_reconciled
```

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

统一多模态模型制品可直接启动并处理图片请求。图片请求必须满足媒体感知共享的
部署前提；不支持的音频、视频或预计算 embedding 会在 Edge 发起 Cloud HTTP
预约前被拒绝，并记录：

```text
[EDGE_CLOUD_PREFIX] event=edge_request_rejected ...
edge-cloud prefix coordination does not support audio, video,
prompt embeds, or media embeds
```

图片共享直接复用 vLLM `mm_hash` 语义。当前正确性边界要求调用方避免客户端媒体
`uuid`、请求级 `media_io_kwargs` 和不可信 EXIF ImageID；这些快捷路径可能令
不同执行输入具有相同摘要。如果只需要纯文本，可在 Edge 和 Cloud 命令中同时
加入 `--language-model-only`。可接收图片的 Edge 要求
`VLLM_MM_HASHER_ALGORITHM` 产生 32 字节摘要（如 blake3/sha256）；纯文本模式不使用
媒体摘要，继续兼容 v1 支持的算法配置。

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

### 8.6 多模态请求返回 `mm_abi_mismatch`

该错误只会在 Cloud 显式设置 `enforce_mm_abi_match=true` 时出现，表示 Edge 与
Cloud 的模型/processor 指纹不同。910B Edge + 910C Cloud 等异构镜像建议保持
默认值 `false`；若必须使用严格模式，则检查两侧模型配置、processor 配置、
vLLM/vLLM-Ascend/transformers/Pillow 版本和摘要算法。模型挂载目录不同本身不会
造成指纹不一致。

### 8.7 Mamba KeyError、未绑定变量或 Prefix suffix 请求悬挂

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
