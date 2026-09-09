# 2E1C + Prefix Cache 协商部署指南（lwd_cloud_reuse_merge_br_0828）

两边一云（E0/E1/C0）融合版启动示例：静态注册表通信域 + 中央控制面
prefix 协商 + 云侧 KV 自管理（CloudKVRequestManager 统一池）。

- 示例拓扑：E0=10.0.0.11、E1=10.0.0.12、C0=10.0.0.13（TP=4）
- 示例模型：Qwen3.5-27B（当前仅支持 Qwen3.5-Dense 文本、`/v1/chat/completions`）
- IP/路径/卡号按实际环境替换

## 1. 各节点需要放置的文件

| 节点 | 必需文件 | 说明 |
|---|---|---|
| E0、E1、C0 | `registry_2e1c.yaml`（三机同一份） | 静态注册表：全局 rank、地址、ZMQ 端口；改动需全员重启 |
| E0、E1 | 租户密钥文件 `/run/secrets/edge-cloud-tenant-key`（两边同一把） | HMAC hash 链密钥，仅边侧持有 |
| C0 | 无需密钥 | 云不配置 `tenant_key_file` |

经 NewAPI 时，E0、E1 各自设置环境变量 `VLLM_ASCEND_EDGE_CLOUD_API_KEY`，
用于 Bearer 鉴权和计费归属；与租户摘要密钥独立，无需令牌文件。

`registry_2e1c.yaml`（本目录有模板）：

```yaml
world:
  master_addr: 10.0.0.13      # 取云实例地址
  master_port: 29600
edges:
  - id: 0
    addr: 10.0.0.11
    ranks: [0]
    zmq_base_port: 5560
  - id: 1
    addr: 10.0.0.12
    ranks: [1]
    zmq_base_port: 5660
clouds:
  - id: 0
    addr: 10.0.0.13
    ranks: [2, 3, 4, 5]       # C0 为 TP=4
    zmq_base_port: 5760
```

注意：`ranks` 是【全局 rank】（HCCL 建组用），不是物理 NPU 号；物理选卡在各
实例启动命令里用 `ASCEND_RT_VISIBLE_DEVICES` 指定，且全局 RANK 必须与注册表
一致，否则建组错位。

## 2. 租户密钥生成（任一台机器执行一次，再同步到另一台边）

```bash
# 生成 32 字节随机密钥（十六进制文本，64 字符）
openssl rand -hex 32 | sudo tee /run/secrets/edge-cloud-tenant-key
sudo chmod 600 /run/secrets/edge-cloud-tenant-key

# 同步到另一台边（内容必须完全一致）
scp /run/secrets/edge-cloud-tenant-key user@10.0.0.12:/tmp/tenant-key
# 在 E1 上：
sudo mv /tmp/tenant-key /run/secrets/edge-cloud-tenant-key
sudo chmod 600 /run/secrets/edge-cloud-tenant-key
```

要点：

1. 长度：去首尾空白后 ≥16 字节；`openssl rand -base64 32` 或
   `head -c 32 /dev/urandom > file`（二进制）亦可。
2. 无 openssl 时：`python3 -c "import secrets; print(secrets.token_hex(32))" | sudo tee /run/secrets/edge-cloud-tenant-key`
3. E0/E1 必须同一把：key 不一致时两边命中池互不可见（不报错，只是互不命中）。
4. 轮换 key 后旧 hash 立即全部失效（随云重启/淘汰自然清理），相当于 prefix
   cache 整体冷启动。
5. `/run/secrets` 是 tmpfs，机器重启后丢失；生产建议放持久路径（如
   `/etc/edge-cloud/tenant-key`）并同步修改 `tenant_key_file`。

## 3. E0 启动命令（10.0.0.11）

```bash
export ASCEND_RT_VISIBLE_DEVICES=0   # 本机物理卡号

vllm serve /home/extra/Qwen3.5-27B \
    --served-model-name "qwen3.5" \
    --host 0.0.0.0 --port 8500 \
    --max-model-len 262144 \
    --max-num-batched-tokens 8192 --max-num-seqs 128 \
    --gpu-memory-utilization 0.95 \
    --async-scheduling --enable-prefix-caching --trust-remote-code \
    --enable-edge-cloud --edge-id 0 \
    --role-registry /etc/edge-cloud/registry_2e1c.yaml \
    --edge-npu-count 1 --cloud-npu-count 4 \
    --master-addr 10.0.0.13 --master-port 29600 \
    --additional-config '{
      "edge_cloud_config": {
        "enabled": true, "role": "edge", "mode": "embedding_only",
        "pd_separation": {"enabled": true, "chunk_prefill_prior_enable": true, "max_chunk_prefill_ahead": 1},
        "prefix_cache_coordination": {
          "enabled": true,
          "control_url": "http://10.0.0.13:8100/v1/chat/completions",
          "tenant_key_file": "/run/secrets/edge-cloud-tenant-key",
          "connect_timeout": 5.0
        }
      }
    }'
```

## 4. E1 启动命令（10.0.0.12）

E1 使用 `--edge-id 1`，`tenant_key_file` 内容与 E0 相同。经 NewAPI 时，
可为两个边配置不同的 API 令牌，以区分消耗。

```bash
export ASCEND_RT_VISIBLE_DEVICES=0

vllm serve /home/extra/Qwen3.5-27B \
    --served-model-name "qwen3.5" \
    --host 0.0.0.0 --port 8500 \
    --max-model-len 262144 \
    --max-num-batched-tokens 8192 --max-num-seqs 128 \
    --gpu-memory-utilization 0.95 \
    --async-scheduling --enable-prefix-caching --trust-remote-code \
    --enable-edge-cloud --edge-id 1 \
    --role-registry /etc/edge-cloud/registry_2e1c.yaml \
    --edge-npu-count 1 --cloud-npu-count 4 \
    --master-addr 10.0.0.13 --master-port 29600 \
    --additional-config '{
      "edge_cloud_config": {
        "enabled": true, "role": "edge", "mode": "embedding_only",
        "pd_separation": {"enabled": true, "chunk_prefill_prior_enable": true, "max_chunk_prefill_ahead": 1},
        "prefix_cache_coordination": {
          "enabled": true,
          "control_url": "http://10.0.0.13:8100/v1/chat/completions",
          "tenant_key_file": "/run/secrets/edge-cloud-tenant-key",
          "connect_timeout": 5.0
        }
      }
    }'
```

## 5. C0 启动命令（10.0.0.13，TP=4）

```bash
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3
export RANK_START=2   # 本实例首个全局 rank = 注册表 clouds[0].ranks[0]

vllm serve /weight/Qwen3.5-27B \
    --served-model-name "qwen3.5" \
    --headless \
    --max-model-len 262144 \
    --max-num-batched-tokens 8192 --max-num-seqs 128 \
    --gpu-memory-utilization 0.95 \
    --async-scheduling --enable-prefix-caching --trust-remote-code \
    --enable-edge-cloud --cloud-id 0 \
    --role-registry /etc/edge-cloud/registry_2e1c.yaml \
    --cloud-npu-count 4 --tensor-parallel-size 4 \
    --master-addr 10.0.0.13 --master-port 29600 \
    --additional-config '{
      "edge_cloud_config": {
        "enabled": true, "role": "cloud", "mode": "embedding_only",
        "pd_separation": {"enabled": true, "chunk_prefill_prior_enable": true, "max_chunk_prefill_ahead": 1},
        "prefix_cache_coordination": {
          "enabled": true,
          "listen_host": "0.0.0.0",
          "listen_port": 8100,
          "instance_id": "cloud-0"
        }
      }
    }'
```

## 6. 说明与约束

1. MTP（可选）：三机同时追加完全相同的
   `--speculative-config '{"num_speculative_tokens":3,"method":"mtp","enforce_eager":true}'`；
   仅支持 mtp，边云 `num_speculative_tokens` 必须一致。
2. 硬性约束（校验会拒）：必须 `--async-scheduling` + `--enable-prefix-caching`；
   仅 Qwen3.5-Dense 文本、`/v1/chat/completions`；不支持 LoRA/多模态/n>1/
   beam search/PCP/DCP。
3. 多 edge 命名空间隔离对配置透明：边侧协商请求自动携带
   `X-Edge-Cloud-Edge-Id`（取自 `--edge-id`），云侧自动加/拆前缀，E0/E1 的
   request id 空间互不干扰，无需新增配置项。
4. 启动顺序：建议 C0 先起（HTTP 控制面 :8100 + ZMQ 通道 + pair 组建好），再起
   E0、E1；E1 会等 E0 经 TCPStore 发布 scheduler KV 配置（隐含依赖 E0 先完成
   KV sizing）。
5. 走 NewAPI（可选）：两边 `control_url` 改为网关的 `/v1/chat/completions`，
   启动服务前设置 `export VLLM_ASCEND_EDGE_CLOUD_API_KEY='sk-你的NewAPI令牌'`。
   变量值不要带 `Bearer` 前缀，边侧读取后发送 `Authorization: Bearer ...`，
   不再发送 `X-Mse-Consumer`。直连无鉴权云端时不设置该变量。
   输入长度放在 `X-Edge-Cloud-Prompt-Tokens` 请求头，旧请求体字段已移除。
   NewAPI 普通 OpenAI 渠道配置 `X-Edge-Cloud-*` 请求头透传即可保留控制元数据，
   无需开启请求体透传；关闭消息改写及系统提示词注入。回程 Probe 已放入标准
   SSE `delta.content`，紧跟空 delta 推动网关刷新；无需修改 NewAPI 或透传响应头。
   Edge/Cloud 必须同步升级。`probe_timeout` 默认 30 秒；网关上游空闲超时应大于
   Cloud 的 10 秒心跳周期并留余量，完整请求时限需覆盖推理。若还有下游代理，
   需考虑开启 NewAPI SSE ping。外部 `stream=true/false` 均使用这条内部 SSE 通道。
6. 静态 `kv_partition` 已移除：多边部署必须开启 `prefix_cache_coordination`
   （云侧 CloudKVRequestManager 统一管理整个 KV 池，边发来的 block id 一律
   丢弃并在云侧重新分配），启动校验会拒绝"注册表多边 + coordination 关闭"
   的组合。
7. head_tail（首 x 尾 x）模式：三机 `mode` 改为 `"head_tail"` 并设
   `edge_head_tail_layers: x`，其余相同。
8. em（embedding_only）模式下边侧无 KV：云确认的 prefix 命中按外部命中记账，
   边只 embedding/发送后缀 token，云侧从预约命中位置起算（需要
   lwd_cloud_reuse_merge_br_0828 及以上版本）。
