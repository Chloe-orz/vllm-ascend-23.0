# NewAPI 边云控制面 SSE 验证记录

验证日期：2026-09-08。结论：此版本 NewAPI 无需源码修改，普通 OpenAI 渠道可以
承载当前边云控制协议，包括流式 Probe 握手和最终 usage 计费。

## 验证环境与边界

- 使用与本地运行实例完全相同的 Docker 镜像，版本 `v1.0.0-rc.34`，镜像 ID：
  `sha256:721c5944aae2970a6457061ff3d346bd06b6b73cbdcf70044f40e098009aeffe`。
- NewAPI 启动在独立容器、独立内存 SQLite 数据库、独立端口 `13000`；没有修改
  用户原有 `3000` 实例的渠道、令牌、余额或源码，也没有调用外部模型服务。
- 运行工作区实际 `EdgePrefixClient`、`create_cloud_control_app`、
  `CloudControlBridge` 和 `CloudControlProcessor`，通过真实 HTTP 和 Docker 网络通信。
- CPU 环境绕过 vLLM/NPU 顶层依赖，仅 KV Probe 和推理完成通知使用模拟值。
  该验证不等同于完整 NPU 推理、多进程调度或用户侧生成流验收。

## 渠道配置

使用普通 OpenAI 渠道，测试模型名 `gpt-4o-mini` 仅用于网关路由及定价，实际上游是
本地 Cloud 控制服务。关闭请求体透传，不注入系统提示词、不改写摘要消息。

请求头覆盖配置：

```json
{"regex:(?i)^x-edge-cloud-": ""}
```

Edge 通过 `VLLM_ASCEND_EDGE_CLOUD_API_KEY` 提供 NewAPI 令牌。无需配置
`X-Mse-Consumer` 或任何响应头透传。

## 时序及结果

每组 E0/E1 同时发起相同原始 request ID 的请求，Cloud 内部必须分开保存
`e0-<id>`、`e1-<id>`；返回 Probe 时恢复原始 ID。只有两个 Edge 都完成
`negotiate()` 后，测试才允许发布 FINISH/usage，避免“先结束再看是否收到 Probe”
掩盖网关缓冲导致的相互等待。

| 协议 | 用户 stream | 并发 Edge 数 | 两边 Probe 均返回耗时 | 最终 usage |
| --- | --- | --- | --- | --- |
| v1 文本 | false | 2 | 26 ms | 2/2 |
| v1 文本 | true | 2 | 23 ms | 2/2 |
| v2 图片 | false | 2 | 20 ms | 2/2 |
| v2 图片 | true | 2 | 27 ms | 2/2 |

这些是单次本地功能测试耗时，不是性能基准。上述外部 `stream` 参数均由实际
Edge 客户端转换为内部 `stream=true, stream_options.include_usage=true`。

全部 8 个请求还通过以下断言：

- 请求体仅包含 `model/messages/stream/stream_options`，不含原始 Prompt、图片或
  自定义 `edge_cloud_prompt_tokens` 字段；长度由请求头传递，v2 ABI 校验成功。
- Probe 的实例、命中、请求 ID 正确，且在 FINISH 前返回；未依赖返回的自定义 Header。
- Edge 最终日志与网关消费日志一致，所有账单 `quota > 0`，
  `admin_info.usage_billing_path` 为 `upstream`，不是对 Probe 文本估算。
- 所有完成请求的 Edge 流任务、请求 ID 占用、Cloud Probe/usage future 已释放。

| Edge | prompt_tokens | completion_tokens | cached_tokens | 验证账单数 |
| --- | --- | --- | --- | --- |
| E0 | 1024 | 128 | 768 | 4 |
| E1 | 1280 | 64 | 512 | 4 |

## 保活和回归覆盖

为缩短验证时间，将隔离 NewAPI 的 `STREAMING_TIMEOUT` 设为 1 秒，测试进程的
Cloud comment 心跳间隔缩短为 0.1 秒。每组 Probe 返回后等待 1.3 秒再发布 usage：
8 条流均未超时且最终正确计费。正式代码的心跳周期为 10 秒，应配置足够长的
网关上游空闲超时及总请求时限。NewAPI 不转发 comment；存在下游代理时还需
配置 NewAPI SSE ping 或调整下游空闲超时。

仓库回归测试覆盖无响应头的 v1/v2 握手、分片 content、多行 SSE、comment、
异常 Probe、缺失 Probe、Probe 超时、Probe 与 usage 共用迭代器、先 Probe/空 delta
后 usage 的顺序、心跳和关闭流后等待任务退出。配置测试覆盖非法 Probe 时限。
本次 CPU 隔离运行的协议、客户端和云端三个测试文件共 132 项通过，选取的配置
测试另有 6 项通过；这不是全仓库或 NPU 测试结果。相关代码和测试通过 Ruff 检查。

此记录只证明正常完成链路的协议和计费兼容。断连后的 KV reservation 超时回收、
异常链路账单补偿及完整 NPU 推理仍需独立验收；不能把网关估算的 fallback usage
当作真实边云 Token 用量。
