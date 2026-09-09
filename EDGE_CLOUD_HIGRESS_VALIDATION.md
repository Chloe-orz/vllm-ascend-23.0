# 边云 Prefix Cache 协商接入 Higress 验证指南

> 历史验证说明：本文保留旧版 Higress 验证步骤与结果。当前 Edge 已移除
> `consumer_id` 配置及 `X-Mse-Consumer` 请求头，改为可选的环境变量
> `VLLM_ASCEND_EDGE_CLOUD_API_KEY` 和标准 Bearer 鉴权。Probe 回程也已改为标准 SSE
> `delta.content` 控制消息加空 delta，不再依赖响应头；请求输入长度已改用
> `X-Edge-Cloud-Prompt-Tokens`。下文的旧 Consumer Header、响应头握手及请求体字段
> 步骤和日志不再代表当前源码；当前接入方式见
> [部署指南](EDGE_CLOUD_PREFIX_CACHE_DEPLOYMENT.md#6-第二阶段接入-ai-网关)。

本文档说明如何把已经通过 Edge 直连 Cloud 验证的 Prefix Cache 协商链路切换到
Higress，并验证透明路由、响应头、长 SSE 生命周期、Consumer 维度 Token 统计和
Prefix Cache 命中信息。

本文以当前实现的 `Edge:Cloud = 1:1` 为范围。Higress 只代理 Edge 到 Cloud 的
内部控制请求，不代理用户到 Edge 的推理请求，也不参与 HCCL、Pipeline Parallel
或 KV Cache 的实际分配。

本文档核对和验证过的基线为：

- Higress 源码 `v2.2.4`，commit `58666ac9`；
- Higress `ai-statistics` 插件 `2.0.1`；
- vLLM 和 vLLM-Ascend 分支 `feat/edge-cloud-prefix-negotiation`；
- Qwen3.5-Dense 纯文本 Chat Completions；
- 普通解码或两侧配置完全一致的 Qwen3.5 MTP；
- 内部 HTTP、无鉴权。

本文以 Higress `all-in-one:latest-o11y` **单容器部署**为主。该镜像在一个容器里
同时运行 Gateway、Console、file-backed apiserver、Prometheus、Loki、Grafana
和插件服务，不需要 Kubernetes。文中出现的 `McpBridge`、`Ingress`、
`WasmPlugin` 是 all-in-one 内部沿用的配置对象格式，不代表需要搭建 K8S 集群。

## 1. 目标拓扑

```text
用户
  |
  | OpenAI Chat Completions，原始 Prompt
  v
Edge :8500
  |
  | 内部 OpenAI-compatible POST
  | Prompt 已替换为 block Hash 链
  | X-Mse-Consumer: enterprise-a
  v
Higress Gateway 宿主机 :18080 -> 容器 :8080
  |
  | 透明转发 /v1/chat/completions
  v
Cloud Prefix Control :8100
  |
  | 响应头立即返回预约结果
  | SSE 在推理结束后返回 usage 和 [DONE]
  v
Edge 丢弃内部 usage；Higress 完成统计
```

用户仍然请求 `http://EDGE_IP:8500/v1/chat/completions`。只有 Edge 配置中的
`prefix_cache_coordination.control_url` 改为 Higress Gateway 地址。

本阶段不需要启用以下插件：

- `ai-proxy`：内部请求已经是 Cloud 能直接处理的 OpenAI 兼容协议，不需要供应商
  协议转换、模型映射或鉴权注入；
- `ai-load-balancer`：当前只有一个 Cloud endpoint，不存在选择空间；
- Redis：1:1 静态路由和 `ai-statistics` 都不依赖 Redis。

在这个范围内，Higress 不需要修改源码，只有配置和联合验证工作。

## 2. 变量和网络前提

后续示例使用以下名称，请按实际环境替换：

| 名称 | 示例值 | 含义 |
| --- | --- | --- |
| `HIGRESS_CONTAINER` | `edge-cloud-higress` | all-in-one 容器名 |
| `HIGRESS_GATEWAY_IP` | `76.76.26.100` | Edge 可访问的 Gateway 内网地址 |
| `HIGRESS_GATEWAY_PORT` | `18080` | 宿主机映射的 Gateway HTTP 端口 |
| `HIGRESS_CONSOLE_PORT` | `18001` | 宿主机映射的 Console 端口 |
| `CLOUD_CONTROL_IP` | `76.76.26.231` | Higress 可访问的 Cloud 内网地址 |
| `CLOUD_CONTROL_PORT` | `8100` | Cloud Prefix 控制服务端口 |
| `CONSUMER_ID` | `enterprise-a` | 企业计费标识 |
| `MODEL_NAME` | `qwen3.6` | Edge 的 `--served-model-name` |
| `ROUTE_NAME` | `edge-cloud-prefix-control` | Higress 路由名 |
| `SERVICE_NAME` | `edge-cloud-control` | Higress 静态服务名 |

网络至少需要满足：

- Edge 可以访问 `HIGRESS_GATEWAY_IP:HIGRESS_GATEWAY_PORT`；
- Higress 容器可以访问 `CLOUD_CONTROL_IP:8100`；
- Cloud 与 Edge 原有的 `29872`、`5558`、`5559` 等边云数据面端口保持可达；
- Higress 不需要访问 Edge 的用户 API；
- 接入完成后，Edge 不再需要直接访问 Cloud `8100`，但建议在验收结束前保留直连
  回退能力。

无鉴权时，`X-Mse-Consumer` 是 Edge 自声明的可信内部身份，不能防止伪造。因此
该 Gateway 路由只能暴露在可信内网，不能直接开放给普通用户。

如果服务器上还没有启动容器，可以使用与本地验证相同的镜像：

```bash
HIGRESS_CONTAINER=edge-cloud-higress
HIGRESS_GATEWAY_PORT=18080
HIGRESS_CONSOLE_PORT=18001
HIGRESS_IMAGE=higress-registry.cn-hangzhou.cr.aliyuncs.com/higress/all-in-one:latest-o11y

docker run -d \
  --name "${HIGRESS_CONTAINER}" \
  --restart unless-stopped \
  -v edge-cloud-higress-data:/data \
  -p "${HIGRESS_GATEWAY_PORT}:8080" \
  -p "${HIGRESS_CONSOLE_PORT}:8001" \
  "${HIGRESS_IMAGE}"
```

本地已经验证过的 arm64 镜像 digest 为：

```text
higress-registry.cn-hangzhou.cr.aliyuncs.com/higress/all-in-one@sha256:8e1ee5bc7a20583d93879954587e7d3c2f08302c3fc22f17bd893dd242986d0e
```

`latest-o11y` 是浮动标签。服务器验证前建议比较实际 digest：

```bash
docker image inspect "${HIGRESS_IMAGE}" \
  --format '{{json .RepoDigests}}'
```

如果本地和服务器 digest 一致，可以认为二者是同一镜像内容；正式固化部署时建议
直接使用 digest，避免未来重新拉取 `latest-o11y` 得到不同版本。

等待 Console 和 Gateway 就绪：

```bash
until curl --fail --silent \
  "http://127.0.0.1:${HIGRESS_CONSOLE_PORT}/" >/dev/null; do
  sleep 2
done

until curl --silent --output /dev/null \
  "http://127.0.0.1:${HIGRESS_GATEWAY_PORT}/"; do
  sleep 2
done
```

浏览器打开：

```text
http://HIGRESS_HOST:18001
```

首次进入时按页面提示初始化管理员账号。本文不要求额外启动 Prometheus、Loki 或
Grafana；`o11y` 镜像已经包含这些进程。

命名 volume `edge-cloud-higress-data` 用于在删除并重建容器后保留 Console、路由
和插件配置。如果服务器上已经有配置好的容器，不要为了增加 volume 直接删除它；
先备份 `/data`，再安排迁移。

## 3. 切换前检查

### 3.1 确认直连链路仍然正常

先保留 Edge 的直连配置，至少完成一次冷请求和一次重复 Prefix 请求。Edge 和
Cloud 日志中不应出现 ERROR，重复请求应能观察到非零 Prefix hit。

Cloud 健康检查：

```bash
curl --fail --show-error \
  http://CLOUD_CONTROL_IP:8100/health
```

预期：

```json
{"status":"ok"}
```

### 3.2 从 Higress 运行环境检查 Cloud

```bash
docker exec "${HIGRESS_CONTAINER}" \
  curl --fail --show-error \
  http://CLOUD_CONTROL_IP:8100/health
```

如果这里失败，应先处理路由、防火墙、容器网络或 Cloud 监听地址，暂时不要修改
Edge 的 `control_url`。

## 4. 先处理 Higress 超时和重试

这一步必须在接入真实请求前完成。

### 4.1 为什么需要关闭 stream idle timeout

Edge 发往 Cloud 的内部请求固定为流式请求：

```json
{
  "stream": true,
  "stream_options": {
    "include_usage": true
  }
}
```

Cloud 会先返回 HTTP 响应头和一条 SSE comment，表示 KV 预约完成。之后直到推理
结束，连接上可能没有新的字节；最后 Cloud 才返回标准 OpenAI usage 和 `[DONE]`。

Higress v2.2.4 的默认 downstream idle timeout 是 180 秒，它同时会成为 Envoy
`stream_idle_timeout`。超过 180 秒没有新数据的长请求可能被网关中断。当前 Cloud
还没有定时发送 heartbeat，因此验证环境建议将它设为 `0`，即关闭全局 stream
idle timeout。

当前默认 route timeout 已经是 `0`。如果既有 Higress 实例修改过它，也必须恢复
为 `0`。注意：`higress.io/timeout: "0"` 在 v2.2.4 中不会生成路由级覆盖，不能
用它抵消一个非零的全局 `downstream.routeTimeout`。

all-in-one 中的生效文件是：

```text
/data/configmaps/higress-config.yaml
```

先备份到宿主机：

```bash
docker cp \
  "${HIGRESS_CONTAINER}:/data/configmaps/higress-config.yaml" \
  /tmp/higress-config.before-edge-cloud.yaml
```

然后使用镜像自带的 `yq` 修改 `data.higress` 这个内嵌 YAML，同时保留其他配置：

```bash
docker exec "${HIGRESS_CONTAINER}" yq -i \
  '.data.higress |= (
    from_yaml |
    .downstream.idleTimeout = 0 |
    .downstream.routeTimeout = 0 |
    to_yaml
  )' \
  /data/configmaps/higress-config.yaml
```

修改后的关键内容应为：

```yaml
data:
  higress: |-
    downstream:
      idleTimeout: 0
      routeTimeout: 0
```

all-in-one 的 file-backed apiserver 会观察 `/data` 变化并触发配置下发。等待约
5 秒后检查 Envoy：

```bash
sleep 5

docker exec "${HIGRESS_CONTAINER}" \
  curl --silent http://127.0.0.1:15000/config_dump \
  > /tmp/higress-config-dump.json

jq -r '
  .. | objects |
  select(has("stream_idle_timeout")) |
  .stream_idle_timeout
' /tmp/higress-config-dump.json | sort -u
```

预期包含：

```text
0s
```

如果文件已经是 `0`，但 config dump 仍然是 `180s`，当前还没有业务流量时可以
重启单容器并再次检查：

```bash
docker restart "${HIGRESS_CONTAINER}"

until curl --fail --silent \
  "http://127.0.0.1:${HIGRESS_CONSOLE_PORT}/" >/dev/null; do
  sleep 2
done
```

容器重新就绪后，重新执行上面的 `config_dump` 检查，确认值已经变为 `0s`。

生产环境不一定要永久使用 `0`。完成验证并具备 Cloud SSE heartbeat 后，可以改成
“最大允许推理时间 + 安全余量”。由于这个配置是网关全局配置，修改前需要评估其他
路由。

### 4.2 禁止内部 POST 自动重试

一次 POST 对应一次 KV 预约。网关在超时、连接失败或 5xx 后重试，可能在多个
Cloud 上产生重复预约，或让一个 Edge 请求对应多个 Cloud 生命周期。因此该路由
必须关闭重试。

后续创建的路由内部配置应包含：

```yaml
metadata:
  annotations:
    higress.io/proxy-next-upstream: "off"
```

不要为这个路由配置重试次数、hedging、镜像流量或故障转移。

## 5. 在 Higress 创建 Cloud 服务来源

### 5.1 Console 操作

进入 Higress Console：

1. 打开“服务来源”。
2. 选择“创建服务来源”。
3. 类型选择“固定地址”或“静态地址”。
4. 名称填写 `edge-cloud-control`。
5. 地址填写 `CLOUD_CONTROL_IP:8100`。静态类型必须填写数值 IP 和端口的组合；
   Higress v2.2.4 不接受把域名写入 static endpoint。
6. 协议选择 `HTTP`。
7. 逻辑服务端口填写 `80`。实际连接端口仍来自地址中的 `8100`。
8. 保存，等待约 5 秒。

创建后，路由中看到的服务名应为：

```text
edge-cloud-control.static
```

如果 Cloud 只能通过域名访问，应改用 DNS 类型服务来源，不要把域名硬塞进 static
类型。

### 5.2 检查容器内生成的 McpBridge 配置

Console 保存后会把服务来源写入容器内：

```text
/data/mcpbridges/default.yaml
```

Higress v2.2.4 只处理名为 `default` 的 McpBridge。不要用单独文件覆盖它，因为
其中还包含 Console 等已有服务来源。检查内容：

```bash
docker exec "${HIGRESS_CONTAINER}" \
  sed -n '1,240p' /data/mcpbridges/default.yaml
```

应能在现有 `spec.registries` 列表中找到：

```yaml
apiVersion: networking.higress.io/v1
kind: McpBridge
metadata:
  name: default
  namespace: higress-system
spec:
  registries:
    - type: static
      name: edge-cloud-control
      domain: CLOUD_CONTROL_IP:8100
      port: 80
      protocol: http
```

确认 `edge-cloud-control` 条目存在，并且 controller 日志没有
`invalid endpoint`。

```bash
docker logs --since 10m "${HIGRESS_CONTAINER}" 2>&1 \
  | grep -E 'edge-cloud-control|invalid endpoint' || true
```

## 6. 创建透明路由

### 6.1 Console 操作

进入“路由配置”并创建普通 HTTP 路由：

1. 路由名称：`edge-cloud-prefix-control`。
2. Domain：使用默认域名或留空，最终生成的 Ingress rule 不能带 Host 限制。
3. Path 匹配：前缀匹配。
4. Path：`/v1/chat/completions`。
5. 后端服务：`edge-cloud-control.static`。
6. 服务端口：`80`。
7. 权重：`100`。
8. 不配置 path rewrite、header rewrite、超时重试、流量镜像或 fallback。
9. 保存并等待配置下发。

本文使用 IP 形式的 `control_url`，因此路由必须没有 Host 限制。当前 Edge HTTP
Client 没有单独覆盖 `Host` Header 的选项；如果路由绑定了域名，就必须把同一个
可解析域名直接写入 `control_url`，不能仍然使用 Gateway IP。

### 6.2 检查容器内生成的路由

Console 保存后会生成：

```text
/data/ingresses/edge-cloud-prefix-control.yaml
```

检查：

```bash
docker exec "${HIGRESS_CONTAINER}" \
  sed -n '1,240p' \
  /data/ingresses/edge-cloud-prefix-control.yaml
```

它的关键结构应等价于：

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: edge-cloud-prefix-control
  namespace: higress-system
  labels:
    higress.io/resource-definer: higress
  annotations:
    higress.io/destination: edge-cloud-control.static:80
    higress.io/ignore-path-case: "false"
    higress.io/proxy-next-upstream: "off"
spec:
  ingressClassName: higress
  rules:
    - http:
        paths:
          - path: /v1/chat/completions
            pathType: Prefix
            backend:
              resource:
                apiGroup: networking.higress.io
                kind: McpBridge
                name: default
```

重点确认：

- 没有 `host:`；
- destination 是 `edge-cloud-control.static:80`；
- `higress.io/proxy-next-upstream` 是 `off`；
- 没有 rewrite；
- 没有其他插件覆盖 `X-Mse-Consumer` 或 `X-Edge-Cloud-*` Header。

如果 Console 生成的路由缺少关闭重试的注解，使用容器自带的 `yq` 补充：

```bash
docker exec "${HIGRESS_CONTAINER}" yq -i \
  '.metadata.annotations."higress.io/proxy-next-upstream" = "off"' \
  /data/ingresses/edge-cloud-prefix-control.yaml

sleep 5

docker exec "${HIGRESS_CONTAINER}" yq \
  '.metadata.annotations, .spec.rules' \
  /data/ingresses/edge-cloud-prefix-control.yaml
```

## 7. 启用 ai-statistics

### 7.1 推荐的轻量配置

在 Console 中进入路由 `edge-cloud-prefix-control` 的插件配置：

1. 找到 `ai-statistics`。
2. 选择版本 `2.0.1`。
3. 作用域选择当前路由。
4. 启用插件。
5. 切换到 YAML 编辑模式。
6. 填写：

```yaml
use_default_response_attributes: true
```

轻量模式会解析流式 usage，但不缓冲完整流式响应，也不会把 Hash 消息记录为
`question` 或 `messages`。它适合先验证计费 Counter。

不要同时填写 `use_default_attributes: true`。完整模式会记录问题、回答等字段并
增加内存开销，这条内部路由没有这个需求。

### 7.2 需要在 ai_log 中记录实例和路由结果时

`ai-statistics 2.0.1` 在 `use_default_response_attributes: true` 时会忽略显式
`attributes`。因此不能把轻量开关和自定义属性混在同一个配置里。

若需要让逐请求 `ai_log` 同时包含 Consumer、Cloud 实例和 Prefix 信息，改用下面
的完整显式属性列表，并删除 `use_default_response_attributes`：

```yaml
attributes:
  - key: model
    apply_to_log: true
  - key: reasoning_tokens
    apply_to_log: true
  - key: cached_tokens
    apply_to_log: true
  - key: input_token_details
    apply_to_log: true
  - key: output_token_details
    apply_to_log: true
  - key: consumer
    value_source: request_header
    value: x-mse-consumer
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

其中：

- `edge_cloud_hit_tokens` 是 Cloud 在预约响应头中给出的候选命中；
- `cached_tokens` 来自最终 usage，是 Edge 和 Cloud 的实际公共命中；
- 对账和计费应使用 `cached_tokens`，不能使用候选命中 Header；
- `X-Mse-Consumer` 即使不配置为自定义属性，也会被插件用于 Prometheus 的
  `ai_consumer` 标签；这里增加它只是为了逐请求日志关联。

如果使用 Console 管理插件，不要直接向 all-in-one 的 `/data/wasmplugins` 手写
文件。应由 Console API 生成资源，否则可能触发 YAML/base64 解析问题。

### 7.3 为什么不需要创建 Higress Consumer 凭据

当前系统允许内部 HTTP、无鉴权。Edge 会根据
`prefix_cache_coordination.consumer_id` 自动发送：

```text
X-Mse-Consumer: enterprise-a
```

`ai-statistics` 会直接把它写入 `ai_consumer` 指标标签。当前验证不需要再启用
key-auth、basic-auth 或创建 Consumer credential。

后续如果增加鉴权，网关必须根据已验证的凭据生成或覆盖这个 Header，不能继续
信任调用方自声明值。

## 8. 修改 Edge，Cloud 保持不变

Cloud 启动命令不需要修改，仍然监听：

```json
{
  "prefix_cache_coordination": {
    "enabled": true,
    "listen_host": "0.0.0.0",
    "listen_port": 8100,
    "instance_id": "cloud-0"
  }
}
```

只修改 Edge 的 `control_url`：

```json
{
  "prefix_cache_coordination": {
    "enabled": true,
    "control_url": "http://HIGRESS_GATEWAY_IP:HIGRESS_GATEWAY_PORT/v1/chat/completions",
    "tenant_key_file": "/run/secrets/edge-cloud-tenant-key",
    "consumer_id": "enterprise-a",
    "connect_timeout": 5.0
  }
}
```

`connect_timeout` 只限制建立连接的时间。Edge Client 对整个 SSE 使用
`total=None`，因此不会在模型推理期间主动触发总超时。

修改配置后重启 Edge。Cloud 已正常运行时不需要重启 Cloud。

如果启用 MTP，Edge 和 Cloud 仍必须使用完全相同的配置，例如：

```bash
--speculative-config \
  '{"num_speculative_tokens":3,"method":"mtp","enforce_eager":true}'
```

Higress 不感知 MTP draft token，也不需要新增配置。它统计的是 Cloud 最终返回的
OpenAI usage，即接受后的 completion token，而不是内部产生但被拒绝的 draft
token。如果未来按实际投机计算量计费，需要扩展 Cloud usage 口径；当前
`ai-statistics` 数据不足以计算被拒绝 draft token 的算力成本。

## 9. 联合验证

### 9.1 不要直接向真实 Cloud 伪造控制 POST

`POST /v1/chat/completions` 不是普通探活接口。Cloud 收到合法 Hash manifest 后会
建立 KV 预约，并等待同一个 Edge 请求进入 Scheduler。手工向真实 Cloud 或
Higress 发送伪造 manifest 可能留下无法完成的预约。

网络探活只调用 `/health`；功能验证必须从 Edge 的用户 API 发起正常请求。

### 9.2 准备日志观察窗口

Edge 和 Cloud：

```bash
grep --line-buffered '\[EDGE_CLOUD_PREFIX\]' EDGE_LOG_FILE
grep --line-buffered '\[EDGE_CLOUD_PREFIX\]' CLOUD_LOG_FILE
```

all-in-one o11y：

```bash
docker exec "${HIGRESS_CONTAINER}" \
  tail -F /var/log/proxy/access.log \
  | grep --line-buffered 'edge-cloud-prefix-control'
```

### 9.3 冷请求

向 Edge 发起一个此前没有使用过、长度超过至少一个 KV block 的纯文本请求：

```bash
curl --fail --show-error \
  http://EDGE_IP:8500/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen3.6",
    "messages": [
      {
        "role": "user",
        "content": "这里替换为足够长、之后能够原样重复的纯文本测试上下文"
      }
    ],
    "max_tokens": 32,
    "stream": false
  }'
```

用户请求可以是 `stream=false`，Edge 到 Higress 的内部请求仍然是长 SSE。

冷请求应观察到：

| 位置 | 关键证据 |
| --- | --- |
| Edge | `edge_negotiate_start`，并记录正确 `consumer_id` |
| Edge | `edge_probe_response instance_id='cloud-0' hit_tokens=0` |
| Cloud | `cloud_http_probe_reserved` 和 `cloud_kv_probe_reserved` |
| Cloud | 请求结束后出现 `cloud_kv_request_finished`、usage ready 事件 |
| Edge | `edge_usage_received`，Token 数与用户结果一致 |
| Higress | 访问日志 `route_name=edge-cloud-prefix-control`、HTTP 200 |
| Higress | upstream 指向 `edge-cloud-control.static` 和 Cloud `IP:8100` |

Higress Token Counter 只会在最终 usage 到达后更新。请求仍在生成时查询不到增量是
正常现象。

### 9.4 重复 Prefix

等待冷请求完全结束，再发送完全相同的长 Prompt。预期：

- Edge `edge_probe_response` 的 `hit_tokens` 大于 0；
- Cloud `cloud_kv_probe_reserved` 的 `hit_blocks` 大于 0；
- 最终 usage 的 `prompt_tokens_details.cached_tokens` 大于 0；
- Higress `ai_log.cached_tokens` 与 Edge `edge_usage_received.cached_tokens` 一致；
- 每个 Edge request ID 在 Cloud 只出现一次 `cloud_http_probe_reserved`，证明没有
  自动重试导致重复预约；
- 用户输出与直连 Higress 之前的结果一致。

### 9.5 MTP 验证

启用 MTP 时，在上述冷请求和重复请求之外检查 Cloud 日志：

```text
[EDGE_CLOUD_PREFIX] event=cloud_kv_mtp_draft_rewritten
[EDGE_CLOUD_PREFIX] event=cloud_kv_mtp_acceptance_recorded
[EDGE_CLOUD_PREFIX] event=cloud_kv_mtp_draft_chain_completed
```

必要时还会看到：

```text
[EDGE_CLOUD_PREFIX] event=cloud_kv_computed_tokens_reconciled
```

Higress 接入前后这些事件的顺序和 Token 语义不应变化。

## 10. 检查 Token Counter 和逐请求日志

### 10.1 Gateway 原始 Prometheus Counter

```bash
docker exec "${HIGRESS_CONTAINER}" \
  curl --silent http://127.0.0.1:15020/stats/prometheus \
  | grep 'route_upstream_model_consumer_metric_' \
  | grep 'ai_route="edge-cloud-prefix-control"' \
  | grep 'ai_consumer="enterprise-a"'
```

至少应看到：

```text
route_upstream_model_consumer_metric_input_token
route_upstream_model_consumer_metric_output_token
route_upstream_model_consumer_metric_total_token
route_upstream_model_consumer_metric_llm_duration_count
```

标签中应包含：

```text
ai_route="edge-cloud-prefix-control"
ai_cluster="outbound|80||edge-cloud-control.static"
ai_model="qwen3.6"
ai_consumer="enterprise-a"
```

`ai_model` 来自内部请求体中的 `model`，应等于 Edge 的
`--served-model-name`。模型目录使用 Qwen3.5-Dense 适配并不要求服务名必须叫
`qwen3.5`；如果实际服务名是 `qwen3.6`，这里就应看到 `qwen3.6`。

all-in-one 只有一个 Gateway/Envoy 进程，因此这里看到的就是该验证容器的原始
累计 Counter。

Prometheus 示例：

```promql
sum by (ai_consumer) (
  increase(
    route_upstream_model_consumer_metric_total_token{
      ai_route="edge-cloud-prefix-control"
    }[10m]
  )
)
```

直接查询 all-in-one 内置 Prometheus：

```bash
docker exec "${HIGRESS_CONTAINER}" \
  curl --silent --get \
  http://127.0.0.1:9090/prometheus/api/v1/query \
  --data-urlencode \
  'query=route_upstream_model_consumer_metric_total_token{ai_route="edge-cloud-prefix-control",ai_consumer="enterprise-a"}' \
  | jq .
```

Higress Dashboard 的 Consumer Usage 使用 `increase()`。新 Consumer 的第一条
Counter 样本可能位于窗口边界，短时间内可能看不到，或显示外推后的非整数。联合
验收时，应以 Gateway 原始 Counter 和逐请求 `ai_log` 为准；查看 Dashboard 时，
为同一个 Consumer 连续发送至少两次请求并等待 Prometheus 完成抓取。

### 10.2 格式化 ai_log

对于 all-in-one o11y：

```bash
docker exec "${HIGRESS_CONTAINER}" \
  tail -n 20 /var/log/proxy/access.log \
  | jq -Rr '
      fromjson? |
      select(.route_name == "edge-cloud-prefix-control") |
      .ai_log | fromjson? |
      {
        model,
        consumer,
        input_token,
        output_token,
        total_token,
        cached_tokens,
        edge_cloud_instance,
        edge_cloud_hit_tokens,
        response_type
      }
    '
```

如果使用第 7.1 节的轻量配置，`consumer`、`edge_cloud_instance` 和
`edge_cloud_hit_tokens` 不会出现在 `ai_log`，但 Token 字段和 Prometheus
`ai_consumer` 标签仍然存在。

访问日志外层还应检查：

- `route_name`：是否命中 `edge-cloud-prefix-control`；
- `upstream_cluster`：是否为 `edge-cloud-control.static`；
- `upstream_host`：是否为预期 Cloud `IP:8100`；
- `response_code`：是否为 `200`；
- `response_flags`：成功请求应为 `-`；
- `duration`：是否覆盖整个推理时间，而不是只覆盖 Prefix probe。

等待 Promtail 采集后，也可以直接查询 all-in-one 内置 Loki：

```bash
docker exec "${HIGRESS_CONTAINER}" \
  curl --silent --get \
  http://127.0.0.1:3100/loki/api/v1/query_range \
  --data-urlencode \
  'query={route_name="edge-cloud-prefix-control"} |= "cached_tokens"' \
  --data-urlencode 'limit=20' \
  --data-urlencode 'direction=backward' \
  | jq .
```

如果 Loki 暂时没有结果，先以 `/var/log/proxy/access.log` 为准，并检查 Promtail
日志；Loki 是否完成采集不影响 Gateway 原始 Counter 的正确性。

### 10.3 当前计费口径

标准 usage 提供：

```text
prompt_tokens
completion_tokens
total_tokens
prompt_tokens_details.cached_tokens
```

`cached_tokens` 当前没有独立 Prometheus Counter，只存在于 `ai_log` 的 usage
明细。若希望按 Cloud 实际处理的 Token 计费，可由日志消费或账单系统计算：

```text
uncached_prompt_tokens = prompt_tokens - cached_tokens
cloud_compute_tokens = uncached_prompt_tokens + completion_tokens
```

这个公式不包含 MTP 被拒绝 draft token，也不覆盖请求在 usage 返回前失败的实际
消耗。当前阶段适合验证统计链路，不应直接作为完整生产账单规则。

## 11. 路由验证边界

当前 1:1 阶段能够确认：

- 请求命中了正确 Higress route；
- `X-Mse-Consumer` 被保留并进入统计标签；
- Gateway 选择了配置的 Cloud upstream；
- Cloud 返回的 `X-Edge-Cloud-Instance-ID` 到达 Edge；
- Prefix 预约流保持到 usage 和 `[DONE]`；
- 每个成功请求只统计一次。

它不能证明多个 Cloud 之间的 Prefix-aware 选择，因为当前边云数据面仍按 1:1
建立。不要为了本阶段验收，在一个静态服务中放入多个真实 Cloud endpoint；Envoy
随机选择到另一个没有与该 Edge 建立数据面的实例会造成控制面和数据面错配。

Higress 自带 `ai-load-balancer` 的 `prefix_cache` 策略会读取 `messages`。当前 Edge
发送的每个完整 KV block Hash 都是一个 `role=user` message，因此从请求形态上可以
被它继续构造 Prefix 历史键。但多 Cloud 验证必须等多边对一云的数据面调度、实例
绑定和失败处理具备之后单独进行，不能把“插件能解析 Hash messages”等同于整个
多 Cloud 系统已经正确。

## 12. 常见故障

### 12.1 Edge 收到 404

优先检查：

- `control_url` path 是否精确为 `/v1/chat/completions`；
- 路由内部配置是否意外生成了 `host`；
- 是否配置了 path rewrite；
- Edge 请求的 Gateway 端口是否对应 HTTP listener。

### 12.2 Edge 收到 503，Gateway 日志 `response_flags=UF`

检查：

```bash
docker exec "${HIGRESS_CONTAINER}" \
  curl --fail --show-error \
  http://CLOUD_CONTROL_IP:8100/health
```

以及：

- McpBridge static `domain` 是否为 `IP:8100`；
- route destination 是否使用逻辑端口 `80`；
- Cloud 是否监听 `0.0.0.0:8100`；
- 服务来源创建后是否已经等待配置下发；
- Gateway 所在网络的防火墙和安全组。

503 不会增加 Token Counter，但会保留访问日志，可通过 `response_flags` 和
`upstream_transport_failure_reason` 定位。

### 12.3 约 180 秒后连接断开

这是典型的 `stream_idle_timeout`。检查容器内实际 Envoy config dump，不要只看
`/data/configmaps/higress-config.yaml`。还要确认服务器外层的 LoadBalancer、
L4/L7 代理、防火墙连接跟踪没有更短的 idle timeout。

### 12.4 指标中的 Consumer 是 `none`

检查 Edge 启动日志：

```text
[EDGE_CLOUD_PREFIX] event=edge_client_initialized consumer_id='enterprise-a'
[EDGE_CLOUD_PREFIX] event=edge_negotiate_start consumer_id='enterprise-a'
```

如果 Edge 正确，再检查是否有 Higress 插件删除或覆盖 `X-Mse-Consumer`。当前无
鉴权路径不需要创建 Consumer credential。

### 12.5 请求成功，但 Token Counter 不增长

检查：

- `ai-statistics` 是否启用在路由级而不是错误的其他路由；
- 插件版本是否为已验证的 `2.0.1`；
- Cloud 最终 SSE 是否包含 usage；
- Edge 是否出现 `edge_usage_received`；
- SSE 是否正常到达 `[DONE]`；
- 是否在请求完成前过早查询；
- 是否查询了错误的 Higress 容器或错误端口。

### 12.6 Prefix Header 命中与 cached_tokens 不同

这是允许的。响应头代表 Cloud 候选命中，最终 `cached_tokens` 代表 Edge 和 Cloud
共同确认的真实复用量。对账应以后者为准。

### 12.7 同一个 request ID 在 Cloud 出现两次预约

首先检查容器内该路由配置的：

```yaml
higress.io/proxy-next-upstream: "off"
```

同时检查网关上游是否还有其他负载均衡器、Service Mesh 或客户端代理执行重试。
在重复预约原因查清前不要继续并发测试。

## 13. 验收清单

全部满足后，才认为第二阶段通过：

- [ ] Higress 到 Cloud `/health` 可达；
- [ ] `downstream.routeTimeout=0`；
- [ ] 长请求不会被 `stream_idle_timeout` 中断；
- [ ] 路由无 Host 限制、无 rewrite、无 retry；
- [ ] Edge 只修改 `control_url`，Cloud 配置不变；
- [ ] 冷请求 Prefix hit 为 0，完成后有 usage；
- [ ] 重复请求 Prefix hit 和 `cached_tokens` 大于 0；
- [ ] Edge 看到的 `instance_id` 是预期 Cloud；
- [ ] Gateway `route_name`、`upstream_cluster`、`upstream_host` 正确；
- [ ] `ai_consumer="enterprise-a"`，不是 `none`；
- [ ] input/output/total Counter 增量与 usage 一致；
- [ ] 每个请求只产生一次 Cloud 预约和一次 Token 统计；
- [ ] MTP 模式下 draft/acceptance/chain 日志正常，输出与直连一致；
- [ ] 未在 Higress 日志中记录原始 Prompt 或 tenant key。

## 14. 回退

Higress 接入失败时，将 Edge 的 `control_url` 恢复为直连地址并重启 Edge：

```json
{
  "control_url": "http://CLOUD_CONTROL_IP:8100/v1/chat/completions"
}
```

Cloud 不需要重启。确认直连恢复后，再停用 Higress 的
`edge-cloud-prefix-control` 路由或 `ai-statistics` 插件。

如果本次为隔离验证而将全局 `downstream.idleTimeout` 改成了 `0`，回退时应根据
集群原配置和其他业务需求决定是否恢复，不能不加检查地统一改回默认值。
