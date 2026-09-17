# prefill-only 云侧复用 两边一云（2E1C）启动说明

目录内容：

| 文件 | 用途 | 部署位置 |
|---|---|---|
| `registry_2e1c.yaml` | 全场共享静态注册表（边云身份/全局 rank/云控制面端口/rendezvous 地址） | 三机挂同一份 |
| `start_edge0.sh` | 边 0 启动脚本（`--edge-id 0`，API :8500） | 边0 机器 |
| `start_edge1.sh` | 边 1 启动脚本（`--edge-id 1`，API :8501） | 边1 机器 |
| `start_cloud.sh` | 云 0 启动脚本（`--cloud-id 0`，TP=4，`--headless`） | 云机器 |

拓扑：2 边（各 1 卡）+ 1 云（4 卡），全局 rank 布局 `边0=0，边1=1，云=2..5`，
world=6。控制面为 ROUTER-ROUTER 单通道：**只有云 bind**（`zmq_port: 5700`），
两边 connect 过去；数据面 HCCL 按全场 rank 组网。

**配置优先级**：rendezvous 地址/端口（master_addr/master_port）为
**registry yaml 的 `world` 段 > CLI（`--master-addr`/`--master-port`）> 默认值**。
yaml 是全场唯一事实源——启动脚本不再传这两个 CLI 参数，只填 yaml 一处；
若同时传了 CLI，yaml 值优先生效。

## 一、填写清单（启动前）

1. `registry_2e1c.yaml`：替换 `<EDGE0_IP>` / `<EDGE1_IP>` / `<CLOUD_IP>`；
   `world.master_addr` 必填（跨机 rendezvous 锚点 = 全局 rank0 所在机 = 边0）。
2. 三个 `.sh` 顶部参数区：`MODEL`（三机同款权重路径）、`REGISTRY`（yaml
   绝对路径）；按机器实际情况调整 `PHYSICAL_NPU(S)`。
3. 端口规划确认（见下表），冲突时改 yaml 的 `zmq_port` / `world.master_port`、
   脚本的 `API_PORT` 即可。

| 端口 | 用途 | 配置位置 | 绑定方 | 谁会连它 |
|---|---|---|---|---|
| 8500 / 8501 | 边0 / 边1 OpenAI API | 脚本 `API_PORT` | 边0 / 边1 | 客户端 |
| 29600 | torch rendezvous | yaml `world.master_addr/port` | 边0（全局 rank0 承载 store） | 边1、云 |
| 5700 | 控制面 ROUTER | yaml `clouds[0].zmq_port` | 云 | 边0、边1 |

防火墙只需放通：`边0:29600`（边1/云 → 边0）、`云:5700`（边 → 云单向）、
`边:8500/8501`（客户端 → 边）。云无需反向访问边任何端口。

## 二、启动顺序

**推荐顺序：边0 → 云 → 边1**（三机依次执行；每台等上一台进程拉起即可，
不必等就绪日志）。

1. **边0 先启动**：它承载全局 rank0 的 rendezvous store（`world.master_addr`
   指向它），并对外提供 API。
2. **云第二启动**：headless 拉起云引擎，bind 控制面端口 5700，加载权重
   （耗时最长的一段）。
3. **边1 最后启动**：API :8501。

顺序说明：

- 分布式层是**全组 barrier**：6 个全局 rank 全部在
  `<world.master_addr>:<master_port>` 集合后世界组才建好，任何一台没起，
  其余实例都停在建组等待——所以严格说三台的**拉起先后不影响正确性**
  （TCPStore 客户端会自动重连等待），推荐顺序只是让 rank0 锚点最先就绪、
  日志更好读。
- 控制面顺序无关：边侧 ROUTER connect + HELLO 由 ZMQ 自动缓冲重试，
  云侧未起时消息滞留 per-identity FIFO，云起来后按序补投，不丢。
- **验证请求只能在三台全部就绪后发出**（边侧引擎不等云 HELLO 即对外
  监听，但世界组未成前请求不会推进）。

## 三、就绪验证（看日志关键字）

| 机器 | 日志 | 关键字 |
|---|---|---|
| 云 | `/tmp/lwd_2e1c_cloud0.log` | `cloud-reuse router channel bind tcp://*:5700`；`peer connected (identity=edge0/edge1, 2/2 ready)` |
| 边0/边1 | `/tmp/lwd_2e1c_edge*.log` | `cloud-reuse router channel ... identity=edge*`；`connected -> tcp://<CLOUD_IP>:5700`；`HELLO sent -> cloud0`；`peer confirmed identity=cloud0 (WELCOME received)` |
| 全部 | — | torch 世界组日志 `world_size=6`、`Lwd edge-cloud mode (registry layout) initialized` |

冒烟：

```bash
curl http://<EDGE0_IP>:8500/v1/completions -H 'Content-Type: application/json' \
  -d '{"model":"qwen","prompt":"你好","max_tokens":16}'
# 边1 同款换 8501
```

## 四、参数联动速查

| 改什么 | 要动哪里 |
|---|---|
| 云卡数（如 TP=8） | yaml `clouds[0].ranks`（如 `[2..9]`）→ 云脚本 `PHYSICAL_NPUS`、`CLOUD_NPU_COUNT` → 边脚本 `CLOUD_NPU_COUNT` |
| 加第 3 条边 | yaml `edges` 加条目（`ranks` 取下一个全局 rank）→ 新边脚本 `--edge-id 2` → 三机 `EDGE_NPU_COUNT` 同步 +1 |
| 换 rendezvous 地址/端口 | 只改 yaml `world` 段（三机同步换 yaml） |
| 换模型/长度 | 三机同步改 `MODEL`、`--max-model-len` 等（三机参数不一致会建组失败） |
| 换控制面端口 | yaml `zmq_port`（云 bind）即可，边自动从 yaml 取 |

## 五、停止与故障

- 停止：任意顺序 `Ctrl-C` / kill 即可；**云侧复用无重启自愈**，任一实例
  挂掉需三台整组重启（配置或 registry 变更同理）。
- 常见失败定位：
  - 卡在建组等待 → 检查 yaml `world.master_addr` 是否为边0 IP 且三机
    yaml 一致、29600 放通、三台是否都已拉起；
  - 边日志出现 `never acked (no WELCOME)` → 重复 identity（两条边误配
    同一 `--edge-id`）或云 5700 不可达；
  - registry 报 `not found in registry` → 脚本 `--edge-id/--cloud-id` 与
    yaml 条目对不上。
