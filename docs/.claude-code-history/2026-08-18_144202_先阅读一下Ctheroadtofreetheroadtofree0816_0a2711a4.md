# Claude Code Session

> **Resume in CLI:** `claude --resume 0a2711a4-03e0-46ef-bb99-578e5278b3bc`

| Field | Value |
|---|---|
| **Project** | `c:\v0\23\0-lwd-acc-test-br` |
| **Session ID** | `0a2711a4-03e0-46ef-bb99-578e5278b3bc` |
| **Working Dir** | `c:\v0.23.0_lwd_acc_test_br` |
| **Started** | 2026/8/18 14:41:59 |
| **Last Updated** | 2026/8/18 16:09:57 |
| **Messages** | 149 |

---

## User <sup>2026/8/18 14:41:59</sup>

先阅读一下C:\theroadtofree\theroadtofree\0816\vllm-ascend KV内存分配计算.md


---

## Assistant <sup>2026/8/18 14:42:02</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "C:\\theroadtofree\\theroadtofree\\0816\\vllm-ascend KV内存分配计算.md"
}
```

</details>


---

## User <sup>2026/8/18 14:42:02</sup>

<details>
<summary>Tool Result</summary>

```
1	# vllm-ascend KV内存分配计算
2	
3	> **Workspace:** /Users/tongtongwang/gitcode_github
4	
5	---
6	
7	## User
8	vllm-ascend如何计算分配多大的kv
9	
10	## Assistant
11	我来搜索 vllm-ascend 中 KV cache 分配相关的代码。
12	
13	让我深入查看关键的几个文件，了解 KV cache 大小的计算逻辑。
14	
15	我找到了核心函数 `determine_available_memory`。让我读取完整实现。
16	
17	让我查看 `requested_memory` 和 `init_snapshot` 的来源。
18	
19	让我也看一下用户打开的 gdn.py 文件第 229 行附近的上下文。
20	
21	# vllm-ascend KV cache 大小计算流程
22	
23	核心逻辑在 [worker.py#L352](file:///Users/tongtongwang/gitcode_github/vllm-ascend-github/vllm_ascend/worker/worker.py#L352) 的 `determine_available_memory()` 方法。分两条路径：
24	
25	## 路径 A：用户手动指定（快速路径）
26	
27	如果启动时设置了 `--kv-cache-memory`（对应 `cache_config.kv_cache_memory_bytes`），[worker.py#L365-L378](file:///Users/tongtongwang/gitcode_github/vllm-ascend-github/vllm_ascend/worker/worker.py#L365-L378) 直接返回该值，仅执行 `profile_run()` 编译模型，跳过内存测算。此路径**不**遵循 `gpu_memory_utilization` 配置。
28	
29	## 路径 B：自动测算（默认路径）
30	
31	### 1. 初始化内存快照（[worker.py#L297-L309](file:///Users/tongtongwang/gitcode_
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:42:03</sup>


---

## Assistant <sup>2026/8/18 14:42:12</sup>

已读完。这份文档是 8/16 的一次对话记录，讲 vllm-ascend 的 KV 内存分配，核心内容：

## 1. KV cache 大小计算逻辑（vllm-ascend）

核心在 `worker.py` 的 `determine_available_memory()`，两条路径：

- **路径 A（手动指定）**：设置 `--kv-cache-memory` 直接用该值，不走 `gpu_memory_utilization`
- **路径 B（默认自动测算）**：
  ```
  KV_cache_可用 = HBM总量 × gpu_memory_utilization(0.9)
                  − (权重 + profile run 激活峰值 + CANN/HCCL 等非 torch 显存)
  ```
  关键点：profile run 在 **graph capture 之前**做，避免 ACLGraph 池内存被算进峰值；另有 EdgeCloud edge 场景返回虚拟 1 TiB 的特殊分支（这个和你之前排查的 PD include_mrope edge/cloud 问题相关）。

## 2. Qwen3-27B / 64G NPU 的 TP=2/4/8 估算

假设 bf16、GQA 8 KV heads、64 层（每 token 总 KV 128 KB）：

| | TP=2 | TP=4 | TP=8 |
|---|---|---|---|
| 单卡 KV cache | 21.6 GB | 38.1 GB | 46.35 GB |
| 全卡 KV 总量 | 43.2 GB | 152.4 GB | 370.8 GB |
| 可缓存 token | 168 K | 595 K | 1448 K |

结论：
- 单卡 KV 比例 ≈ **1 : 1.76 : 2.15**（受每卡固定 ~3 GB 开销拖累，增长放缓）
- 全卡 KV 总量 / token 容量 ≈ **1 : 3.53 : 8.58**（**超线性**：权重恒定被摊薄 + 每卡开销线性堆叠）
- 高 TP 的价值主要在于放大 KV 容量、降低 preemption，TP=8 vs TP=2 约 **8.6 倍**容量

注意这是估算（假设是 dense Qwen3 + GQA），实际以启动日志 `GPU KV cache size: XXXXX tokens` 验证为准。

需要我基于这个做什么？比如对照你 `c:\vllm_gitcode_new` 里的实际代码核实公式，或者结合 PD 部署（qwen3.6-27b 2卡/实例）重算容量？


---

## User <sup>2026/8/18 14:46:02</sup>

边云场景，qwen3.6-27b模型，云侧设置2卡、4卡、8卡，打印的kv_cache_config.num_blocks是628、1763、2024，从代码角度分析一下是否和代码实现一致


---

## Assistant <sup>2026/8/18 14:46:09</sup>


---

## Assistant <sup>2026/8/18 14:46:10</sup>

我先在代码库里找相关实现来核对。


---

## Assistant <sup>2026/8/18 14:46:10</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "ls /c/vllm_gitcode_new",
  "description": "List repo root directories"
}
```

</details>


---

## Assistant <sup>2026/8/18 14:46:10</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "head_limit": 30,
  "output_mode": "files_with_matches",
  "path": "c:\\vllm_gitcode_new",
  "pattern": "num_blocks"
}
```

</details>


---

## User <sup>2026/8/18 14:46:11</sup>

<details>
<summary>Tool Result</summary>

```
Found 30 files limit: 30
c:\vllm_gitcode_new\vllm\vllm\v1\core\sched\scheduler.py
c:\vllm_gitcode_new\.claude-code-history\2026-05-23_192559_vllm-ascend-pp并行场景scheduler调度决策的Schedule_3e11ea47.md
c:\vllm_gitcode_new\vllm-ascend\vllm_ascend\worker\model_runner_v1.py
c:\vllm_gitcode_new\vllm\vllm\v1\worker\gpu_worker.py
c:\vllm_gitcode_new\vllm\vllm\v1\worker\mamba_utils.py
c:\vllm_gitcode_new\vllm\vllm\v1\worker\kv_connector_model_runner_mixin.py
c:\vllm_gitcode_new\vllm\vllm\v1\worker\gpu_input_batch.py
c:\vllm_gitcode_new\vllm\vllm\v1\worker\gpu_model_runner.py
c:\vllm_gitcode_new\vllm\vllm\v1\worker\gpu\spec_decode\rejection_sampler.py
c:\vllm_gitcode_new\vllm\vllm\v1\worker\gpu\warmup.py
c:\vllm_gitcode_new\vllm\vllm\v1\worker\gpu\sample\penalties.py
c:\vllm_gitcode_new\vllm\vllm\v1\worker\gpu\sample\gumbel.py
c:\vllm_gitcode_new\vllm\vllm\v1\worker\gpu\model_runner.py
c:\vllm_gitcode_new\vllm\vllm\v1\worker\gpu\block_table.py
c:\vllm_gitcode_new\vllm\vllm\v1\worker\gpu\attn_utils.py

...(truncated)
```

</details>


---

## User <sup>2026/8/18 14:46:19</sup>

<details>
<summary>Tool Result</summary>

```
vllm
vllm-ascend
```

</details>


---

## Assistant <sup>2026/8/18 14:46:22</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-n": true,
  "head_limit": 60,
  "output_mode": "content",
  "path": "c:\\vllm_gitcode_new\\vllm-ascend\\vllm_ascend\\worker\\worker.py",
  "pattern": "determine_available_memory|available_kv_cache_memory|num_blocks|edge|cloud|1\\s*<<\\s*30|TiB"
}
```

</details>


---

## User <sup>2026/8/18 14:46:22</sup>

<details>
<summary>Tool Result</summary>

```
327:    def determine_available_memory(self) -> int:
355:        self.available_kv_cache_memory_bytes = self.requested_memory - profile_result.non_kv_cache_memory
358:            "Available KV cache memory: %.2f GiB", GiB(self.available_kv_cache_memory_bytes), scope="local"
361:        return int(self.available_kv_cache_memory_bytes)
```

</details>


---

## Assistant <sup>2026/8/18 14:46:26</sup>


---

## Assistant <sup>2026/8/18 14:46:26</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\vllm_gitcode_new\\vllm-ascend\\vllm_ascend\\worker\\worker.py",
  "limit": 150,
  "offset": 240
}
```

</details>


---

## User <sup>2026/8/18 14:46:26</sup>

<details>
<summary>Tool Result</summary>

```
240	            for name, buffer in model.named_buffers():
241	                if name in self._sleep_saved_buffers:
242	                    buffer.data.copy_(self._sleep_saved_buffers[name].data)
243	            self._sleep_saved_buffers = {}
244	
245	    def initialize_cache(self, num_gpu_blocks: int, num_cpu_blocks: int) -> None:
246	        self.cache_config.num_gpu_blocks = num_gpu_blocks
247	        self.cache_config.num_cpu_blocks = num_cpu_blocks
248	
249	    def _init_device(self):
250	        device = torch.device(f"npu:{self.local_rank}")
251	        torch.npu.set_device(device)
252	
253	        # Import _inductor for graph mode execution with triton
254	        # This lazy import avoids torch_npu re-initialization in patch
255	        # Note that this should be imported after torch.npu.set_device
256	        # to avoid repeated set_device in extra processes
257	        from vllm.triton_utils import HAS_TRITON
258	
259	        if HAS_TRITON:
260	            import torch_npu.
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:46:30</sup>


---

## Assistant <sup>2026/8/18 14:46:31</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-i": true,
  "head_limit": 40,
  "output_mode": "files_with_matches",
  "path": "c:\\vllm_gitcode_new\\vllm-ascend",
  "pattern": "edge_cloud|edgecloud|embedding_only"
}
```

</details>


---

## User <sup>2026/8/18 14:46:31</sup>

<details>
<summary>Tool Result</summary>

```
No files found
```

</details>


---

## Assistant <sup>2026/8/18 14:46:31</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-n": true,
  "head_limit": 40,
  "output_mode": "content",
  "path": "c:\\vllm_gitcode_new\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "pattern": "num_blocks"
}
```

</details>


---

## User <sup>2026/8/18 14:46:31</sup>

<details>
<summary>Tool Result</summary>

```
2755:                    # as it only support the 0-dim of kv_cache is `num_blocks`.
2904:                    num_blocks = sum_page_size_bytes // current_kv_cache_spec.page_size_bytes
2906:                    # `num_blocks` is the number of blocks the model runner can use.
2907:                    # `kv_cache_config.num_blocks` is the number of blocks that
2910:                    # different memory capacities, `num_blocks` can be different on
2911:                    # different GPUs, and `kv_cache_config.num_blocks` is set to
2912:                    # the min of all `num_blocks`. Verify it here.
2913:                    assert num_blocks >= kv_cache_config.num_blocks
2920:                            num_blocks * block_size_chunk,
2935:                            num_blocks,
2948:                        mla_num_blocks, mla_block_size, num_kv_heads, _ = kv_cache_shape
2951:                            mla_num_blocks,
2957:                            mla_num_blocks,
2972:               
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:46:35</sup>


---

## Assistant <sup>2026/8/18 14:46:36</sup>

主工作目录下可能有边云版本代码，我找一下。


---

## Assistant <sup>2026/8/18 14:46:36</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "ls /c/v0.23.0_lwd_acc_test_br",
  "description": "List primary working directory"
}
```

</details>


---

## User <sup>2026/8/18 14:46:37</sup>

<details>
<summary>Tool Result</summary>

```
__pycache__
ec_rootcause.py
log
vllm
vllm-ascend
```

</details>


---

## Assistant <sup>2026/8/18 14:46:41</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-i": true,
  "head_limit": 30,
  "output_mode": "files_with_matches",
  "path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend",
  "pattern": "embedding_only|edge_cloud|1 TiB|1 << 30"
}
```

</details>


---

## User <sup>2026/8/18 14:46:41</sup>

<details>
<summary>Tool Result</summary>

```
Found 30 files limit: 30
vllm-ascend\docs\PDbatch分离边云协同多实例调度详细设计_NEW.md
vllm-ascend\docs\.claude-code-history\2026-08-17_094615_先阅读Cv0.23.0_lwd_acc_test_brvllm-ascen_8cd0c21c.md
vllm-ascend\docs\.claude-code-history\2026-08-11_210821_ide_opened_fileThe-user-opened-the-fil_f622a2cc.md
vllm-ascend\docs\.claude-code-history\2026-08-11_210122_ide_selectionThe-user-selected-the-lin_f13f2dd8.md
vllm-ascend\docs\.claude-code-history\2026-08-06_231815_边云场景，存在精度问题，分析-Ctheroadtofree_githubv_de702c0d.md
vllm-ascend\vllm_ascend\worker\worker.py
vllm-ascend\vllm_ascend\ascend_config.py
vllm-ascend\vllm_ascend\envs.py
vllm-ascend\vllm_ascend\worker\model_runner_v1.py
vllm-ascend\vllm_ascend\distributed\parallel_state.py
vllm-ascend\vllm_ascend\core\pd_separated_scheduler.py
vllm-ascend\vllm_ascend\v1\engine\passive_core.py
vllm-ascend\vllm_ascend\patch\platform\patch_engine_core.py
vllm-ascend\vllm_ascend\core\passive_scheduler.py
vllm-ascend\vllm_ascend\ascend_forward_context.py
vllm-ascend\tests\u
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:46:47</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-n": true,
  "head_limit": 80,
  "output_mode": "content",
  "path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\worker.py",
  "pattern": "embedding_only|edge|cloud|available_kv|requested_memory|non_kv_cache|determine_available"
}
```

</details>


---

## User <sup>2026/8/18 14:46:48</sup>

<details>
<summary>Tool Result</summary>

```
48:    is_cloud_device,
49:    is_edge_device,
81:    edge_cloud_broadcast_recv,
82:    edge_cloud_broadcast_recv_scheduled_draft,
83:    edge_cloud_send_tensor_dict,
84:    edge_cloud_send_tensor_dict_scheduled_draft,
86:    init_edge_cloud_tensor_meta,
88:from vllm_ascend.edge_cloud_materialized import (
138:    # DeepSeek V4 uses hc_pre/hc_post internally, but in the edge-cloud
230:        # [CHER/EHER] Cloud-side hidden early-receive (and its edge-side
236:        # Shared by CHER (cloud) and EHER (edge) since the recv primitives
244:        # Whether cloud-side hidden early-receive (CHER) is active on this
246:        # PD-separated cloud worker (local_rank==0) this is always True; False
247:        # (edge role, non-rank0, or PD off) => the legacy sync recv path is
249:        self._cloud_hidden_early_recv_enabled: bool = False
568:        self.requested_memory = self.init_snapshot.total_memory * self.cache_config.gpu_memory_utilization
569:        if self.init_snapshot.free_memo
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:46:50</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\worker.py",
  "limit": 100,
  "offset": 700
}
```

</details>


---

## User <sup>2026/8/18 14:46:50</sup>

<details>
<summary>Tool Result</summary>

```
700	                self._early_recv_max_inflight = 0
701	            if self._cloud_hidden_early_recv_enabled:
702	                logger.info(
703	                    "[CHER] cloud hidden early-receive enabled on worker "
704	                    "rank=%s", getattr(self, "rank", "?"),
705	                )
706	
707	    @torch.inference_mode()
708	    def determine_available_memory(self) -> int:
709	        """Profiles the peak memory usage of the model to determine how much
710	        memory can be used for KV cache without OOMs.
711	
712	        The engine will first conduct a profiling of the existing memory usage.
713	        Then, it calculates the free memory that can be used for KV cache in
714	        bytes.
715	        """
716	        GiB = lambda b: b / GiB_bytes
717	
718	        # Fast path: user has explicitly specified KV cache size via
719	        # --kv-cache-memory. Still run profile_run() to compile the model,
720	        # but skip the memory profiling calculation en
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:47:16</sup>


---

## Assistant <sup>2026/8/18 14:47:17</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-n": true,
  "head_limit": 40,
  "output_mode": "content",
  "path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend",
  "pattern": "num_blocks.*=.*available|available.*//.*page|get_kv_cache_configs"
}
```

</details>


---

## User <sup>2026/8/18 14:47:17</sup>

<details>
<summary>Tool Result</summary>

```
vllm-ascend\docs\PDbatch分离边云协同多实例调度详细设计_NEW.md:188:[Omitted long matching line]
vllm-ascend\docs\PDbatch分离边云协同多实例调度详细设计_NEW.md:939:3. `get_kv_cache_configs()`（边 CPU 汇聚，num_blocks 口径见 §6.6）
vllm-ascend\docs\PDbatch分离边云协同多实例调度详细设计_NEW.md:1426:**实现要点（关键：不能直接复用现有全局 min）**：`get_kv_cache_configs` 现有"所有 rank 拉平到全局最小"（kv_cache_utils.py:2146）会把**边也钳进去**。1:1 时边钳到 cloud 无害（边只镜像 1 份）；多实例下边要容纳 **N 份**（4×2024=8096 > 2024），边物理池被钳到 per-instance 值 = 边侧超卖/OOM。正确做法：
vllm-ascend\vllm_ascend\worker\worker.py:775:        # get_kv_cache_configs() does not clamp num_blocks to the edge's
vllm-ascend\vllm_ascend\worker\edge_cloud\shared_model_edge_worker.py:1191:        # get_kv_cache_configs() does not clamp num_blocks to the edge's
vllm-ascend\vllm_ascend\patch\platform\patch_kv_cache_utils.py:235:    num_blocks = available_memory // (layer_tuple_page_bytes * num_layer_tuples)
vllm-ascend\vllm_ascend\distributed\kv_transfer\kv_pool\cpu_offload\metadata.py:152:            num_blocks = available_memory // layer
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:47:19</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\patch\\platform\\patch_kv_cache_utils.py"
}
```

</details>


---

## User <sup>2026/8/18 14:47:19</sup>

<details>
<summary>Tool Result</summary>

```
1	# SPDX-License-Identifier: Apache-2.0
2	# SPDX-FileCopyrightText: Copyright contributors to the vLLM-Ascend project
3	import math
4	from collections import defaultdict
5	from dataclasses import replace
6	
7	import vllm.v1.core.kv_cache_utils
8	from vllm.config import VllmConfig
9	from vllm.utils.math_utils import cdiv, round_up
10	from vllm.v1.core.kv_cache_utils import _approximate_gcd, may_override_num_blocks
11	from vllm.v1.kv_cache_interface import (
12	    KVCacheConfig,
13	    KVCacheGroupSpec,
14	    KVCacheSpec,
15	    KVCacheTensor,
16	    MLAAttentionSpec,
17	    SlidingWindowMLASpec,
18	    UniformTypeKVCacheSpecs,
19	)
20	
21	from vllm_ascend.utils import vllm_version_is
22	
23	_orig_resolve_kv_cache_block_sizes = vllm.v1.core.kv_cache_utils.resolve_kv_cache_block_sizes
24	
25	
26	def _ascend_resolve_kv_cache_block_sizes(
27	    kv_cache_config: KVCacheConfig,
28	    vllm_config: VllmConfig,
29	) -> tuple[int, int]:
30	    """Ascend-compatible resolve_kv_cache_block_sizes
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:47:26</sup>


---

## Assistant <sup>2026/8/18 14:47:28</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-n": true,
  "head_limit": 60,
  "output_mode": "content",
  "path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\patch\\models\\qwen3_5_edge_cloud.py",
  "pattern": "class |num_kv_heads|kv_heads|head_dim|KVCacheSpec|kv_cache_spec|MLA|layers"
}
```

</details>


---

## User <sup>2026/8/18 14:47:28</sup>

<details>
<summary>Tool Result</summary>

```
48:    num_layers = len(self.layers)
49:    assert 0 <= start_layer <= end_layer <= num_layers, (
50:        f"Invalid segment range [{start_layer}, {end_layer}) for {num_layers} layers"
56:        is_last_segment = end_layer == num_layers and get_pp_group().is_last_rank
71:    for layer in islice(self.layers, start_layer, end_layer):
159:    for layer in self.model.layers:
177:    self.moe_layers = []
179:    for layer in self.model.layers:
184:            self.moe_layers.append(layer.mlp.experts)
187:        self.num_moe_layers = 0
195:        logger.warning("No Qwen3Next MoE layer found in the model.layers.")
198:    self.num_moe_layers = len(self.moe_layers)
218:    for layer in self.language_model.model.layers:
234:    self.moe_layers = []
236:    for layer in self.language_model.model.layers:
241:            self.moe_layers.append(layer.mlp.experts)
244:        self.num_moe_layers = 0
253:            "No Qwen3_5 MoE layer found in the language_model.model.layers."
257:    self.nu
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:47:40</sup>


---

## Assistant <sup>2026/8/18 14:47:41</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-i": true,
  "-n": true,
  "head_limit": 30,
  "output_mode": "content",
  "path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend",
  "pattern": "qwen3.?6|qwen3_6"
}
```

</details>


---

## User <sup>2026/8/18 14:47:41</sup>

<details>
<summary>Tool Result</summary>

```
vllm-ascend\docs\.claude-code-history\2026-08-17_173051_边云场景dp并行场景，云双机场景云双机是通过cloud_addr-自动发现的，有_1e778b19.md:302:153	| 侧 | 拉起配置（N=4，qwen3.6 2 卡/实例） |
vllm-ascend\docs\.claude-code-history\2026-08-17_094615_先阅读Cv0.23.0_lwd_acc_test_brvllm-ascen_8cd0c21c.md:817:          "description": "qwen3.5 与文档中 qwen3.6-27b 是同一模型(命名笔误),直接沿用 §6.3 现有实测数字做 N=8/16 临界分析",
vllm-ascend\docs\.claude-code-history\2026-08-17_094615_先阅读Cv0.23.0_lwd_acc_test_brvllm-ascen_8cd0c21c.md:821:          "description": "qwen3.5 是新模型,§6.3 表标注「待按 2 卡实例口径重新实测」,临界分析以现有 qwen3.6 数字作参考推演",
vllm-ascend\docs\.claude-code-history\2026-08-17_094615_先阅读Cv0.23.0_lwd_acc_test_brvllm-ascen_8cd0c21c.md:825:      "question": "qwen3.5 与文档中 qwen3.6-27b 的关系?(影响 §1.4 场景与 §6.3 容量表口径)"
vllm-ascend\docs\.claude-code-history\2026-08-17_094615_先阅读Cv0.23.0_lwd_acc_test_brvllm-ascen_8cd0c21c.md:842:Your questions have been answered: "每服务器多实例的实例编码方式,采用哪种?(决定 §2.1 配置推导的改法)"="复用 node_rank = 逻辑实例 (Recommended)", "qwen3.5 与文档中 qwen3.6-27b 的关系?(影响 §1.4 
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:48:01</sup>


---

## Assistant <sup>2026/8/18 14:48:01</sup>

设计文档里出现过 2024 这个数字，而且 `log` 目录可能存有实际启动日志。我先看日志再对照代码。


---

## Assistant <sup>2026/8/18 14:48:02</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "ls -la /c/v0.23.0_lwd_acc_test_br/log | head -50",
  "description": "List log directory"
}
```

</details>


---

## User <sup>2026/8/18 14:48:03</sup>

<details>
<summary>Tool Result</summary>

```
total 380
drwxr-xr-x 1 root 197121      0 Aug 12 19:48 .
drwxr-xr-x 1 root 197121      0 Aug 10 20:08 ..
-rw-r--r-- 1 root 197121  16061 Aug  6 17:58 0806_1.txt
-rw-r--r-- 1 root 197121  11533 Aug 10 20:09 0810-1.txt
-rw-r--r-- 1 root 197121 112784 Aug 11 17:37 0810-2.txt
-rw-r--r-- 1 root 197121  15754 Aug 11 20:24 0811-1.txt
-rw-r--r-- 1 root 197121  15581 Aug 11 20:44 0811-2.txt
-rw-r--r-- 1 root 197121  30263 Aug 12 15:16 0811-3.txt
-rw-r--r-- 1 root 197121   1020 Aug 12 15:45 0811-4.txt
-rw-r--r-- 1 root 197121  29632 Aug 12 16:24 0811-5.txt
-rw-r--r-- 1 root 197121  26237 Aug 12 16:57 0811-6.txt
-rw-r--r-- 1 root 197121  18314 Aug 12 17:36 0811-7.txt
-rw-r--r-- 1 root 197121  28217 Aug 12 18:03 0811-8.txt
-rw-r--r-- 1 root 197121  28023 Aug 12 19:19 0811-9.txt
-rw-r--r-- 1 root 197121  28529 Aug 12 19:49 0811-a.txt
```

</details>


---

## Assistant <sup>2026/8/18 14:48:05</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-n": true,
  "head_limit": 60,
  "output_mode": "content",
  "path": "c:\\v0.23.0_lwd_acc_test_br\\log",
  "pattern": "num_blocks|Available KV cache|KV cache size|available_memory|GiB"
}
```

</details>


---

## User <sup>2026/8/18 14:48:05</sup>

<details>
<summary>Tool Result</summary>

```
No matches found
```

</details>


---

## Assistant <sup>2026/8/18 14:48:19</sup>


---

## Assistant <sup>2026/8/18 14:48:20</sup>

日志里没有相关信息，回到代码。我需要看 num_blocks 的最终计算与聚合路径（vllm 核心的 `get_kv_cache_configs`）。


---

## Assistant <sup>2026/8/18 14:48:20</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-n": true,
  "head_limit": 50,
  "output_mode": "content",
  "path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_model_runner.py",
  "pattern": "get_kv_cache_configs|available_memory|num_blocks"
}
```

</details>


---

## User <sup>2026/8/18 14:48:21</sup>

<details>
<summary>Tool Result</summary>

```
6319:            self.vllm_config, kv_cache_groups, available_memory=0
6324:        self.cache_config.num_gpu_blocks = minimal_config.num_blocks
7010:        max_num_blocks = []
7017:            max_num_blocks_per_req = cdiv(
7021:                max_num_blocks_per_req = (
7022:                    max_num_blocks_per_req
7026:            max_num_blocks.append(max_num_blocks_per_req)
7043:                max_num_blocks_per_req=max_num_blocks,
7131:                num_blocks = raw_tensor.numel() // kv_cache_spec.page_size_bytes
7134:                    num_blocks_per_kv_block = (
7137:                    kernel_num_blocks = num_blocks * num_blocks_per_kv_block
7146:                        kernel_num_blocks,
7177:                        # NOTE: This assumes kv_cache_shape[0] == num_blocks
7206:                        target_shape = (num_blocks, *shape)
7232:        Update the layout of attention layers from (2, num_blocks, ...) to
7233:        (num_blocks, 2, ...).
7250:            # block
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:48:23</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-n": true,
  "head_limit": 60,
  "output_mode": "content",
  "path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\engine\\core.py",
  "pattern": "available_memory|num_blocks|get_kv_cache_config"
}
```

</details>


---

## User <sup>2026/8/18 14:48:23</sup>

<details>
<summary>Tool Result</summary>

```
48:    get_kv_cache_configs,
275:                available_gpu_memory = self.model_executor.determine_available_memory()
286:        kv_cache_configs = get_kv_cache_configs(
307:        vllm_config.cache_config.num_gpu_blocks = scheduler_kv_cache_config.num_blocks
```

</details>


---

## Assistant <sup>2026/8/18 14:48:27</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\engine\\core.py",
  "limit": 70,
  "offset": 255
}
```

</details>


---

## User <sup>2026/8/18 14:48:27</sup>

<details>
<summary>Tool Result</summary>

```
255	        start = time.time()
256	
257	        # register all kvcache specs in enginecore process.
258	        register_all_kvcache_specs(vllm_config)
259	
260	        # Get all kv cache needed by the model
261	        kv_cache_specs = self.model_executor.get_kv_cache_specs()
262	
263	        has_kv_cache = any(kv_cache_spec for kv_cache_spec in kv_cache_specs)
264	        if has_kv_cache:
265	            if envs.VLLM_ELASTIC_EP_SCALE_UP_LAUNCH:
266	                # NOTE(yongji): should already be set
267	                # during _eep_scale_up_before_kv_init
268	                assert self.available_gpu_memory_for_kv_cache > 0
269	                available_gpu_memory = [self.available_gpu_memory_for_kv_cache] * len(
270	                    kv_cache_specs
271	                )
272	            else:
273	                # Profiles the peak memory usage of the model to determine how
274	                # much memory can be allocated for kv cache.
275	                available_gpu_memory
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:48:31</sup>


---

## Assistant <sup>2026/8/18 14:48:31</sup>

关键发现：edge-cloud 下取的是 `max_group_idx`（按 group 数最多的一份 config），不是全局 min。继续看 `get_kv_cache_configs` 内部 num_blocks 怎么算。


---

## Assistant <sup>2026/8/18 14:48:34</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-n": true,
  "head_limit": 80,
  "output_mode": "content",
  "path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\core\\kv_cache_utils.py",
  "pattern": "def get_kv_cache_configs|def _get_kv_cache_config_from_group|min\\(|min_available|may_override_num_blocks"
}
```

</details>


---

## User <sup>2026/8/18 14:48:34</sup>

<details>
<summary>Tool Result</summary>

```
920:def may_override_num_blocks(vllm_config: VllmConfig, num_blocks: int) -> int:
969:    return may_override_num_blocks(vllm_config, num_blocks)
1156:    min_num_layers = min(per_type_counts.values())
1238:    num_blocks = may_override_num_blocks(vllm_config, num_blocks)
1299:            conv_page = min(
1379:        num_blocks = may_override_num_blocks(vllm_config, num_blocks)
1663:            size_to_candidate[ps] = min(x for x in all_page_sizes if x >= ps)
2061:def get_kv_cache_configs(
2135:    # `may_override_num_blocks` in `get_kv_cache_config_from_groups` clamps
2192:    min_num_blocks = min(
```

</details>


---

## Assistant <sup>2026/8/18 14:48:38</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\core\\kv_cache_utils.py",
  "limit": 180,
  "offset": 2061
}
```

</details>


---

## User <sup>2026/8/18 14:48:38</sup>

<details>
<summary>Tool Result</summary>

```
2061	def get_kv_cache_configs(
2062	    vllm_config: VllmConfig,
2063	    kv_cache_specs: list[dict[str, KVCacheSpec]],
2064	    available_memory: list[int],
2065	) -> list[KVCacheConfig]:
2066	    """
2067	    Generates the KV cache configurations for a model.
2068	    Since we use a shared centralized controller for all workers, we need the
2069	    `kv_cache_config` to be consistent across all workers to make sure
2070	    the KV cache allocation can be applied to all workers. However, different
2071	    workers may have different memory available, and different type of layers
2072	    (when pipeline parallel is enabled). To handle the difference between
2073	    workers, the current implementation is:
2074	    1. Merge the KV cache specs of all workers to get the KVCacheSpecs for
2075	       the whole model.
2076	    2. Generate the KV cache groups based on the layer ratio of the whole model.
2077	       This also handles spec unification for hybrid models.
2078	    3. Handle auto-
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:48:58</sup>


---

## Assistant <sup>2026/8/18 14:48:59</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-n": true,
  "head_limit": 60,
  "output_mode": "content",
  "path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\docs\\PDbatch分离边云协同多实例调度详细设计_NEW.md",
  "pattern": "num_blocks"
}
```

</details>


---

## User <sup>2026/8/18 14:48:59</sup>

<details>
<summary>Tool Result</summary>

```
80:- 边侧 KV 约束：per-instance 分区下每 (instance,dp) 分到 per_dp_num_blocks/N，须覆盖 2 inflight prefill 的 KV
939:3. `get_kv_cache_configs()`（边 CPU 汇聚，num_blocks 口径见 §6.6）
955:**结论**：collective_rpc 广播 + response 回收机制天然支持更多 rank，启动期改动集中在四处：§2.2 端口/store 偏移 + 校验（硬前提）、启动编排逐实例串行握手（缓解 #2/#3）、同机实例错峰拉起（#6，编排层，不进 vllm 配置面）、§6.6 num_blocks 汇聚口径（边不进全局 min）。
1362:**v1 = per-instance 分区**（`per_dp_num_blocks / N` 给每 (instance,dp)，各 scheduler 独立准入、无共享、无协调器）。
1378:分区下边侧向每实例 PP group（G2）报 `per_dp_num_blocks / N`，per-instance min = min(edge/N, cloud_i)；min 机制是 per-PP-group（多实例 G2 天然支持 per-instance，机制不破坏）。
1380:实测 R = 边/云 num_blocks 比（**每模型 N 上限不同，§1.4 部署矩阵**；翻转分析只对能达到 N* 的模型实际生效）：
1382:| 模型 | 首/尾层 | 边 num_blocks | 云 num_blocks | R（=N*） | 该模型 N 上限 | 实际可达翻转区？ |
1391:[Omitted long matching line]
1407:后果：边侧首层 4N 个 prefill 在飞（边侧算力天花板对 N 的约束）；边侧 KV 分区 `per_dp_num_blocks/N` 须覆盖**每 (instance,dp) 2 inflight prefill** KV（非整个实例 4）。分区 sizing 与 inflight 作用域耦合。
1417:### 6.6 启动期 num_blocks 汇聚：min(边/N, 所有云实例)（同构部署，已确认可行）
1423:- 每 
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:49:02</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\docs\\PDbatch分离边云协同多实例调度详细设计_NEW.md",
  "limit": 100,
  "offset": 1360
}
```

</details>


---

## User <sup>2026/8/18 14:49:02</sup>

<details>
<summary>Tool Result</summary>

```
1360	### 6.1 边侧 KV 准入：per-instance 分区（v1）
1361	
1362	**v1 = per-instance 分区**（`per_dp_num_blocks / N` 给每 (instance,dp)，各 scheduler 独立准入、无共享、无协调器）。
1363	
1364	理由：实例间请求理论均衡（`InstanceDispatcher` 均衡路由）-> 无实例需借 KV，共享的利用率收益不兑现而风险是硬的。embedding_only 无 edge KV 免。
1365	
1366	### 6.2 共享池 + 协调器（后续实测后调优）
1367	
1368	若实测分区不够（长序列打满 / inflight 上不去影响 pipeline 重叠），需：
1369	
1370	- per-dp 共享 `KVCacheManager`（单 free list，跨实例物理共享）
1371	- per-instance 软配额（min guarantee + 溢出借闲）+ 上限 cap（爆炸半径）
1372	- 先确认 scheduler 并发模型（EngineCore 层 per-step 一个 (instance,bt) sequential 时分复用 N scheduler = 单线程免锁；lockstep 原指 worker 层 1 进程，KVCacheManager 准入在 EngineCore 层）
1373	
1374	**共享下 headroom 口径**：edge_kv_headroom 是 per-dp 全局量（非 per-instance）、cloud_kv_headroom 才 per-instance（实例选择看云侧 room、dp 选择 + 边侧准入看 per-dp edge room）。**分区下两者都 per-instance**（InstanceLoadStats 原 per-instance 结构即正确）。
1375	
1376	### 6.3 容量 sizing（已核实；N 范围更新 2026-08：按模型口径，qwen3.6-27b 上限 16）
1377	
1378	分区下边侧向每实例 PP group（G2）报 `per_dp_num_blocks / N`，per-instance min
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:49:30</sup>


---

## Assistant <sup>2026/8/18 14:49:30</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\core\\kv_cache_utils.py",
  "limit": 70,
  "offset": 905
}
```

</details>


---

## User <sup>2026/8/18 14:49:30</sup>

<details>
<summary>Tool Result</summary>

```
905	    num_layer_per_group = max(
906	        len(group.layer_names) for group in kv_cache_config.kv_cache_groups
907	    )
908	    max_memory_usage_per_request = num_layer_per_group * max_memory_usage_bytes(
909	        vllm_config, (group.kv_cache_spec for group in kv_cache_config.kv_cache_groups)
910	    )
911	    memory_per_block = (
912	        kv_cache_config.kv_cache_groups[0].kv_cache_spec.page_size_bytes
913	        * num_layer_per_group
914	    )
915	    num_block_per_request = cdiv(max_memory_usage_per_request, memory_per_block)
916	    max_concurrency = kv_cache_config.num_blocks / num_block_per_request
917	    return max_concurrency
918	
919	
920	def may_override_num_blocks(vllm_config: VllmConfig, num_blocks: int) -> int:
921	    """
922	    Override the number of kv cache blocks if `num_gpu_blocks_override` is set.
923	    The override is logged once, at the call site in `get_kv_cache_configs`.
924	    """
925	    if vllm_config.cache_config.num_gpu_blocks_override is n
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:49:35</sup>


---

## Assistant <sup>2026/8/18 14:49:36</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-n": true,
  "head_limit": 40,
  "output_mode": "content",
  "path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend",
  "pattern": "class .*Spec|MambaParams|recurrent_state|temporal_pool"
}
```

</details>


---

## User <sup>2026/8/18 14:49:36</sup>

<details>
<summary>Tool Result</summary>

```
vllm-ascend\vllm_ascend\kv_offload\npu.py:16:class NPUOffloadingSpec(OffloadingSpec):
vllm-ascend\vllm_ascend\ops\gdn_attn_builder.py:78:class GDNSpecCausalConv1dMetadata:
vllm-ascend\vllm_ascend\ops\gdn_attn_builder.py:97:class GDNSpecDecodeMetadata:
vllm-ascend\vllm_ascend\ops\gdn.py:688:            core_attn_out_spec, last_recurrent_state = None, None
vllm-ascend\vllm_ascend\ops\gdn.py:732:            (core_attn_out_non_spec, last_recurrent_state) = chunk_gated_delta_rule(
vllm-ascend\vllm_ascend\ops\gdn.py:745:            ssm_state[prefill_state_indices] = last_recurrent_state.transpose(-1, -2).contiguous().to(ssm_state.dtype)
vllm-ascend\vllm_ascend\ops\gdn.py:769:            core_attn_out_non_spec, last_recurrent_state = None, None
vllm-ascend\vllm_ascend\_310p\spec_decode\llm_base_proposer_310.py:29:class AscendSpecDecodeBaseProposer310(AscendSpecDecodeBaseProposer):
vllm-ascend\vllm_ascend\patch\worker\patch_gdn_attn.py:65:class GDNSpecCausalConv1dHostMetadata:
vllm-ascend\vllm
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:50:03</sup>


---

## Assistant <sup>2026/8/18 14:50:04</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "ls /c/v0.23.0_lwd_acc_test_br/vllm/vllm/model_executor/models/ | grep -i qwen",
  "description": "Find qwen model files in vllm"
}
```

</details>


---

## User <sup>2026/8/18 14:50:05</sup>

<details>
<summary>Tool Result</summary>

```
colqwen3.py
colqwen3_5.py
qwen.py
qwen2.py
qwen2_5_omni_thinker.py
qwen2_5_vl.py
qwen2_audio.py
qwen2_moe.py
qwen2_rm.py
qwen2_vl.py
qwen3.py
qwen3_5.py
qwen3_5_mtp.py
qwen3_asr.py
qwen3_asr_forced_aligner.py
qwen3_asr_realtime.py
qwen3_dflash.py
qwen3_moe.py
qwen3_next.py
qwen3_next_mtp.py
qwen3_omni_moe_thinker.py
qwen3_vl.py
qwen3_vl_moe.py
qwen_vl.py
```

</details>


---

## Assistant <sup>2026/8/18 14:50:08</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-n": true,
  "head_limit": 60,
  "output_mode": "content",
  "path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\model_executor\\models\\qwen3_5.py",
  "pattern": "num_key_value_heads|linear_num|head_dim|num_hidden_layers|linear_key|linear_value|class Qwen3_5|GatedDeltaNet|full_attention|linear_attn"
}
```

</details>


---

## User <sup>2026/8/18 14:50:09</sup>

<details>
<summary>Tool Result</summary>

```
43:from vllm.model_executor.layers.mamba.gdn.qwen_gdn_linear_attn import (
44:    QwenGatedDeltaNetAttention,
110:class Qwen3_5ProcessingInfo(Qwen3VLProcessingInfo):
115:class Qwen3_5MoeProcessingInfo(Qwen3VLProcessingInfo):
120:class Qwen3_5DecoderLayer(Qwen3NextDecoderLayer):
138:            self.linear_attn = QwenGatedDeltaNetAttention(
141:                prefix=f"{prefix}.linear_attn",
144:        elif self.layer_type == "full_attention":
208:class Qwen3_5Model(Qwen3NextModel):
237:            config.num_hidden_layers, get_layer, prefix=f"{prefix}.layers"
433:class Qwen3_5ForCausalLMBase(
529:class Qwen3_5ForCausalLM(Qwen3_5ForCausalLMBase):
533:class Qwen3_5MoeForCausalLM(Qwen3_5ForCausalLMBase, QwenNextMixtureOfExperts):
554:class Qwen3_5ForConditionalGeneration(Qwen3VLForConditionalGeneration, IsHybrid):
702:            hf_config.linear_num_key_heads,
703:            hf_config.linear_num_value_heads,
704:            hf_config.linear_key_head_dim,
705:            hf_config.linea
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:50:11</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\model_executor\\models\\qwen3_5.py",
  "limit": 120,
  "offset": 115
}
```

</details>


---

## User <sup>2026/8/18 14:50:11</sup>

<details>
<summary>Tool Result</summary>

```
115	class Qwen3_5MoeProcessingInfo(Qwen3VLProcessingInfo):
116	    def get_hf_config(self):
117	        return self.ctx.get_hf_config(Qwen3_5MoeConfig)
118	
119	
120	class Qwen3_5DecoderLayer(Qwen3NextDecoderLayer):
121	    def __init__(
122	        self,
123	        vllm_config: VllmConfig,
124	        layer_type: str,
125	        prefix: str = "",
126	    ) -> None:
127	        super(Qwen3NextDecoderLayer, self).__init__()
128	
129	        config = vllm_config.model_config.hf_text_config
130	        model_config = vllm_config.model_config
131	        cache_config = vllm_config.cache_config
132	        quant_config = vllm_config.quant_config
133	
134	        self.layer_type = layer_type
135	        self.layer_idx = extract_layer_index(prefix)
136	
137	        if self.layer_type == "linear_attention":
138	            self.linear_attn = QwenGatedDeltaNetAttention(
139	                config=config,
140	                vllm_config=vllm_config,
141	                prefix=f"{prefix}.linear
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:50:17</sup>


---

## Assistant <sup>2026/8/18 14:50:17</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-n": true,
  "head_limit": 40,
  "output_mode": "content",
  "path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\model_executor\\layers\\mamba\\mamba_mixer2.py",
  "pattern": "page_size_bytes|MambaSpec|def get_cache_spec|conv_state_shape|ssm_state_shape|tp_size|num_heads|block_size"
}
```

</details>


---

## User <sup>2026/8/18 14:50:18</sup>

<details>
<summary>Tool Result</summary>

```
77:        self.tp_size = get_tensor_model_parallel_world_size()
81:        self.per_rank_hidden_size = full_hidden_size // self.tp_size
93:        assert self.full_hidden_size % self.tp_size == 0, (
106:        #   2. tp_size divides n_groups
117:            if self.tp_size > 1:
122:                count = self.tp_size * x.shape[-1]
129:            redundant_tp: bool = self.n_groups % self.tp_size != 0
158:        if ((self.n_groups % self.tp_size) != 0) or self.n_groups != 1:
173:    tp_size: int,
196:            shard_size = full_dim // tp_size
256:        num_heads: int = 128,
282:        self.tp_size = get_tensor_model_parallel_world_size()
285:        assert num_heads % self.tp_size == 0, (
289:        assert (n_groups % self.tp_size) == 0 or n_groups == 1, (
300:        self.num_heads = num_heads
303:        if n_groups % self.tp_size != 0:
305:            # - but if n_groups cannot divide tp_size, we need to
308:                n_groups, self.tp_size
315:        if n_groups % s
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:50:21</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-n": true,
  "head_limit": 60,
  "output_mode": "content",
  "path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\model_executor\\layers\\mamba\\mamba_mixer2.py",
  "pattern": "def get_cache_spec|def _get_cache_spec|page_size|MambaSpec\\("
}
```

</details>


---

## User <sup>2026/8/18 14:50:21</sup>

<details>
<summary>Tool Result</summary>

```
No matches found
```

</details>


---

## Assistant <sup>2026/8/18 14:50:24</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rn \"MambaSpec(\" /c/v0.23.0_lwd_acc_test_br/vllm/vllm --include=\"*.py\" | head; grep -rn \"def get_mamba_state_spec\\|def get_cache_spec\" /c/v0.23.0_lwd_acc_test_br/vllm/vllm/model_executor/layers/mamba/*.py | head",
  "description": "Find MambaSpec creation and cache spec functions"
}
```

</details>


---

## User <sup>2026/8/18 14:50:26</sup>

<details>
<summary>Tool Result</summary>

```
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/model_executor/layers/mamba/abstract.py:48:        return MambaSpec(
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/platforms/interface.py:623:        mamba_page_size = MambaSpec(
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/v1/kv_cache_interface.py:608:class MambaSpec(KVCacheSpec):
```

</details>


---

## Assistant <sup>2026/8/18 14:50:37</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\model_executor\\layers\\mamba\\abstract.py"
}
```

</details>


---

## User <sup>2026/8/18 14:50:37</sup>

<details>
<summary>Tool Result</summary>

```
1	# SPDX-License-Identifier: Apache-2.0
2	# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
3	from abc import abstractmethod
4	from collections.abc import Iterable
5	
6	import torch
7	
8	from vllm.config import VllmConfig
9	from vllm.model_executor.layers.attention_layer_base import AttentionLayerBase
10	from vllm.v1.attention.backend import AttentionBackend
11	from vllm.v1.attention.backends.registry import MambaAttentionBackendEnum
12	from vllm.v1.attention.selector import get_mamba_attn_backend
13	from vllm.v1.kv_cache_interface import KVCacheSpec, MambaSpec
14	
15	
16	class MambaBase(AttentionLayerBase):
17	    """
18	    Base class for Mamba-like layers which support the v1 engine.
19	    Inherit from this class if you implement a custom layer.
20	    """
21	
22	    # Contains the KV cache (mamba state) for the layer
23	    # in the shape specified by `self.get_state_shape`.
24	    kv_cache: tuple[torch.Tensor, ...]
25	
26	    @abstractmethod
27	    def get_stat
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:50:40</sup>


---

## Assistant <sup>2026/8/18 14:50:40</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rn \"def get_state_shape\\|def get_state_dtype\" -A 25 /c/v0.23.0_lwd_acc_test_br/vllm/vllm/model_executor/layers/mamba/gdn/qwen_gdn_linear_attn.py | head -60",
  "description": "Find GDN state shape definition"
}
```

</details>


---

## User <sup>2026/8/18 14:50:41</sup>

<details>
<summary>Tool Result</summary>

```
421:    def get_state_shape(
422-        self,
423-    ) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
424-        return MambaStateShapeCalculator.gated_delta_net_state_shape(
425-            self.tp_size,
426-            self.num_k_heads,
427-            self.num_v_heads,
428-            self.head_k_dim,
429-            self.head_v_dim,
430-            self.conv_kernel_size,
431-            self.num_spec,
432-        )
433-
434-    def __init__(
435-        self,
436-        config: Qwen3NextConfig,
437-        vllm_config: VllmConfig,
438-        prefix: str = "",
439-        gqa_interleaved_layout=False,
440-    ) -> None:
441-        super().__init__(config, vllm_config, prefix)
442-
443-        self.num_k_heads = config.linear_num_key_heads
444-        self.num_v_heads = config.linear_num_value_heads
445-        self.head_k_dim = config.linear_key_head_dim
446-        self.head_v_dim = config.linear_value_head_dim
```

</details>


---

## Assistant <sup>2026/8/18 14:50:46</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rn \"def gated_delta_net_state_shape\" -A 40 /c/v0.23.0_lwd_acc_test_br/vllm/vllm/model_executor/layers/mamba/ --include=\"*.py\" | head -60",
  "description": "Find gated delta net state shape calculator"
}
```

</details>


---

## User <sup>2026/8/18 14:50:47</sup>

<details>
<summary>Tool Result</summary>

```
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/model_executor/layers/mamba/mamba_utils.py:213:    def gated_delta_net_state_shape(
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/model_executor/layers/mamba/mamba_utils.py-214-        cls,
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/model_executor/layers/mamba/mamba_utils.py-215-        tp_world_size: int,
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/model_executor/layers/mamba/mamba_utils.py-216-        num_k_heads: int,
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/model_executor/layers/mamba/mamba_utils.py-217-        num_v_heads: int,
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/model_executor/layers/mamba/mamba_utils.py-218-        head_k_dim: int,
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/model_executor/layers/mamba/mamba_utils.py-219-        head_v_dim: int,
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/model_executor/layers/mamba/mamba_utils.py-220-        conv_kernel_size: int,
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/model_executor/layers/mamba/mamba_utils.py-221-        num_spec: int = 0,
/c/v0.
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:51:01</sup>


---

## Assistant <sup>2026/8/18 14:51:01</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\edge_cloud\\shared_model_edge_worker.py",
  "limit": 80,
  "offset": 1140
}
```

</details>


---

## User <sup>2026/8/18 14:51:01</sup>

<details>
<summary>Tool Result</summary>

```
1140	        """Per-virtual-worker share of the available KV-cache memory.
1141	
1142	        Whichever virtual worker is called first performs the
1143	        actual memory profiling (via ``profile_run``); all
1144	        subsequent callers (regardless of ``local_rank``) return
1145	        the per-worker share already cached on the registry.
1146	        This avoids requiring any specific ``local_rank`` to be
1147	        called first while still ensuring the expensive profile
1148	        run executes exactly once.
1149	        """
1150	        # Fast path: already computed by some virtual worker in
1151	        # this process. Each virtual worker still needs to run
1152	        # ``profile_run`` on its own model_runner to initialise
1153	        # its compiled artifacts.
1154	        for w in _SHARED_MODEL_REGISTRY:
1155	            if w._per_worker_kv_cache_memory is not None:
1156	                self.model_runner.profile_run()
1157	                return w._per_worker_kv_cache
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:52:28</sup>


---

## Assistant <sup>2026/8/18 14:52:29</sup>

再核对一个关键点：`get_kv_cache_config_from_groups` 的除数口径，以及 GDN 层 page 是否真的按 TP 切分。


---

## Assistant <sup>2026/8/18 14:52:29</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\core\\kv_cache_utils.py",
  "limit": 120,
  "offset": 1210
}
```

</details>


---

## User <sup>2026/8/18 14:52:29</sup>

<details>
<summary>Tool Result</summary>

```
1210	                ps = spec.kv_cache_specs[layer_name].page_size_bytes
1211	            else:
1212	                ps = spec.page_size_bytes
1213	            slot_idx = slot_count[ps]
1214	            slot_count[ps] += 1
1215	            if slot_idx == len(buckets[ps]):
1216	                buckets[ps].append([])
1217	            buckets[ps][slot_idx].append(layer_name)
1218	    return buckets
1219	
1220	
1221	def _get_kv_cache_config_deepseek_v4(
1222	    vllm_config: VllmConfig,
1223	    kv_cache_groups: list[KVCacheGroupSpec],
1224	    available_memory: int,
1225	) -> tuple[int, list[KVCacheTensor]]:
1226	    """DeepseekV4 KV cache tensor layout planning.
1227	
1228	    Emit one KVCacheTensor per (slot_idx, page_size). Layers from different
1229	    groups at the same slot share a tensor (they have independent block
1230	    tables so block-id namespaces never collide).
1231	    """
1232	    # buckets = {page_size: [[layer_names], [layer_names], ...]}
1233	    buckets = _bucket_l
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:52:32</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\core\\kv_cache_utils.py",
  "limit": 130,
  "offset": 1329
}
```

</details>


---

## User <sup>2026/8/18 14:52:32</sup>

<details>
<summary>Tool Result</summary>

```
1329	        The generated KVCacheConfig
1330	    """
1331	    if len(kv_cache_groups) == 0:
1332	        # Attention free models do not have KV cache.
1333	        # Return num_blocks=1 as BlockPool always needs a null_block.
1334	        return KVCacheConfig(
1335	            num_blocks=1,
1336	            kv_cache_tensors=[],
1337	            kv_cache_groups=kv_cache_groups,
1338	        )
1339	
1340	    if vllm_config.parallel_config.enable_edge_cloud:
1341	        # Edge-cloud: page_size_padded on the specs is the CANONICAL page
1342	        # (derived with canonical_tp=1) whose only purpose is to keep page
1343	        # sizes aligned across edge/cloud workers with different TP sizes,
1344	        # so that spec merging never scales block_size. Charging that
1345	        # canonical page to every worker over-provisions KV memory by
1346	        # cloud_tp-fold (e.g. 4x fewer blocks with cloud_tp=4). Rebase the
1347	        # per-worker config to the worker's LOCAL (TP-sharded) pa
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:55:06</sup>


---

## Assistant <sup>2026/8/18 14:55:06</sup>

再确认一个细节：full-attn 的 page 是否记录了按 TP 切分后的“本地真实 page”。


---

## Assistant <sup>2026/8/18 14:55:07</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-n": true,
  "head_limit": 30,
  "output_mode": "content",
  "path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "pattern": "real_page_size|canonical_tp|page_size_padded"
}
```

</details>


---

## User <sup>2026/8/18 14:55:07</sup>

<details>
<summary>Tool Result</summary>

```
9845:                        page_size_padded = getattr(
9846:                            current_kv_cache_spec, "page_size_padded", None
9848:                        if page_size_padded is not None:
9852:                            # (cf. upstream GPUModelRunner page_size_padded view).
9854:                            page_stride = page_size_padded // dtype_size
10509:            mamba_page_size_padded = 0
10513:                    mamba_page_size_padded = spec.page_size_bytes
10514:            # align attn_page_size to mamba_page_size_padded
10516:                if kv_cache_spec[layer_name].page_size_bytes < mamba_page_size_padded:  # type: ignore[attr-defined]
10517:                    object.__setattr__(kv_cache_spec[layer_name], "page_size_padded", mamba_page_size_padded)
```

</details>


---

## Assistant <sup>2026/8/18 14:55:34</sup>

<details>
<summary>Tool: <code>Grep</code></summary>

```json
{
  "-n": true,
  "head_limit": 40,
  "output_mode": "content",
  "path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "pattern": "def get_kv_cache_spec|FullAttentionSpec\\(|num_kv_heads"
}
```

</details>


---

## User <sup>2026/8/18 14:55:34</sup>

<details>
<summary>Tool Result</summary>

```
9533:                            num_heads = kv_cache_spec.block_size * kv_cache_spec.num_kv_heads
9738:                        current_kv_cache_spec.num_kv_heads,
9748:                                                current_kv_cache_spec.num_kv_heads,
9754:                                current_kv_cache_spec.num_kv_heads,
9841:                            current_kv_cache_spec.num_kv_heads,
9891:                            current_kv_cache_spec.num_kv_heads,
9919:                            current_kv_cache_spec.num_kv_heads,
9930:                        mla_num_blocks, mla_block_size, num_kv_heads, _ = kv_cache_shape
9935:                            num_kv_heads,
9943:                                num_kv_heads,
9950:                            num_kv_heads,
9973:                            current_kv_cache_spec.num_kv_heads,
9983:                                current_kv_cache_spec.num_kv_heads,
10063:                                                     * _spec.num_kv_heads
10372:
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:55:37</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 140,
  "offset": 10372
}
```

</details>


---

## User <sup>2026/8/18 14:55:37</sup>

<details>
<summary>Tool Result</summary>

```
10372	    def get_kv_cache_spec(self) -> dict[str, KVCacheSpec]:
10373	        """
10374	        Generates the KVCacheSpec by parsing the kv cache format from each
10375	        Attention module in the static forward context.
10376	        Returns:
10377	            KVCacheSpec: A dictionary mapping layer names to their KV cache
10378	            format. Layers that do not need KV cache are not included.
10379	        """
10380	        # embedding_only: edge has no local attention layers, so its
10381	        # static_forward_context is empty and the normal path returns {}.
10382	        # Returning {} here lets the cloud's fresh spec (after weights
10383	        # processing) drive the merged spec, avoiding stale dimensions
10384	        # (e.g. head_size changed by quantization).
10385	        if (
10386	            self._edge_cloud_enabled
10387	            and self.edge_cloud_cfg.mode == "embedding_only"
10388	            and self.edge_cloud_cfg.role == "edge"
10389	        ):
1039
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:55:41</sup>


---

## Assistant <sup>2026/8/18 14:55:42</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rn \"real_page_size_bytes\" /c/v0.23.0_lwd_acc_test_br/vllm/vllm --include=\"*.py\" | head -20; echo ---; grep -rn \"real_page_size_bytes\" /c/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend --include=\"*.py\" | head -20",
  "description": "Find where real_page_size_bytes is defined"
}
```

</details>


---

## User <sup>2026/8/18 14:55:43</sup>

<details>
<summary>Tool Result</summary>

```
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/distributed/kv_transfer/kv_connector/v1/offloading/worker.py:97:                        layer_kv_cache_spec.real_page_size_bytes
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/v1/core/kv_cache_utils.py:1253:    real_page_size = getattr(spec, "real_page_size_bytes", None)
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/v1/kv_cache_interface.py:169:        real_page_size = self.real_page_size_bytes
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/v1/kv_cache_interface.py:183:    def real_page_size_bytes(self) -> int:
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/v1/kv_cache_interface.py:295:    def real_page_size_bytes(self) -> int:
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/v1/kv_cache_interface.py:320:    actual_page_size = spec.real_page_size_bytes
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/v1/kv_cache_interface.py:331:    real_page_size_bytes to use TQ slot bytes instead of the raw
/c/v0.23.0_lwd_acc_test_br/vllm/vllm/v1/kv_cache_interface.py:338:    def real_page_size_bytes(self) -> int:
/c/v0.23.0_
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:55:47</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\kv_cache_interface.py",
  "limit": 60,
  "offset": 160
}
```

</details>


---

## User <sup>2026/8/18 14:55:47</sup>

<details>
<summary>Tool Result</summary>

```
160	class AttentionSpec(KVCacheSpec):
161	    num_kv_heads: int
162	    head_size: int
163	    dtype: torch.dtype
164	    kv_quant_mode: KVQuantMode = KVQuantMode.NONE
165	    page_size_padded: int | None = None
166	
167	    @property
168	    def page_size_bytes(self) -> int:
169	        real_page_size = self.real_page_size_bytes
170	        # Per-token-head scales are stored in separate tensors managed
171	        # by the attention backend, but the memory is carved from the
172	        # raw KV cache allocation so it must be budgeted here.
173	        if self.kv_quant_mode.is_per_token_head:
174	            real_page_size += (
175	                2 * self.block_size * self.num_kv_heads * get_dtype_size(torch.float32)
176	            )
177	        if self.page_size_padded is not None:
178	            assert self.page_size_padded >= real_page_size
179	            return self.page_size_padded
180	        return real_page_size
181	
182	    @property
183	    def real_page_size_bytes(self)
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:56:10</sup>


---

## Assistant <sup>2026/8/18 14:56:37</sup>

核对完代码链路，给出分析结论。

## 代码链路（num_blocks 是怎么算出来的）

1. **每 rank 可用 KV 显存**：[worker.py:771](vllm-ascend/vllm_ascend/worker/worker.py#L771) — `available = HBM×0.9 − (权重/TP + 激活峰值 + non_torch)`；embedding_only 边侧走 [worker.py:777-790](vllm-ascend/vllm_ascend/worker/worker.py#L777-L790) 返回虚拟 1TiB。
2. **每 rank 的 block 字节数**（hybrid 模型，qwen3.5/3.6 = full-attn + GDN）：
   - full-attn 真实 page = `2 × block_size × num_kv_heads/TP × head_size × dtype`（[kv_cache_interface.py:194-200](vllm/vllm/v1/kv_cache_interface.py#L194-L200)），**随 TP 切分**；
   - GDN state（conv/temporal）也 `divide(..., tp_world_size)` 切分（[mamba_utils.py:223-233](vllm/vllm/model_executor/layers/mamba/mamba_utils.py#L223-L233)）；
   - 边云下 spec 用 canonical(TP=1) page 对齐，再按本 worker 的本地 page 重定位（[kv_cache_utils.py:1340-1367](vllm/vllm/v1/core/kv_cache_utils.py#L1340-L1367)），本地 page 同样 ∝ 1/TP。
   - `num_blocks = available // (group_size × page)`（[kv_cache_utils.py:1406-1414](vllm/vllm/v1/core/kv_cache_utils.py#L1406-L1414)）。
3. **全局 min 拉平**（[kv_cache_utils.py:2192-2202](vllm/vllm/v1/core/kv_cache_utils.py#L2192-L2202)），随后边云分支单选 cloud 侧 config 给 scheduler（[core.py:297-304](vllm/vllm/v1/engine/core.py#L297-L304)）。

## 理论关系与实测对照

由于分子里只有权重项 ∝1/TP、分母 page 也 ∝1/TP，代码上应满足**仿射线性增长**：

```
blocks(TP) ≈ (a·TP − W) / P     （a=固定预算, W=云侧权重, P=TP=1 时 block 字节）
```

用 TP=2/4 两个点拟合：`blocks(TP) ≈ 567.5·TP − 507`

| TP | 实测 | 代码预期 | 结论 |
|---|---|---|---|
| 2 | 628 | — | 基准 |
| 4 | 1763 | —（×2.81，超线性，与“page 减半+权重释放”完全吻合） | ✅ 一致 |
| 8 | 2024 | **≈4033** | ❌ 只有预期的 50% |

反推 TP=8 的每卡可用 KV：约 253 单位（P），而 TP=2/4 分别是 314P、441P——**TP=8 每卡可用 KV 比 TP=2 还低**，这在“权重/TP + page/TP”的单 rank 公式下不可能成立。换算成绝对值（若云侧权重≈50GB，P≈100MB）：TP8 每卡 non-KV 比趋势预期多了约 **25GB**。所以 **TP2→TP4 与代码一致，TP4→TP8 不一致，TP=8 被某个东西钳住了**。

## TP=8 被钳的三个候选（按嫌疑排序）

1. **`num_gpu_blocks_override`**（[kv_cache_utils.py:920-927](vllm/vllm/v1/core/kv_cache_utils.py#L920-L927)）：2024 恰好等于设计文档 §6.3 里的历史“云侧 num_blocks”值。如果 TP=8 那次启动带了 `--num-gpu-blocks 2024`（或沿用旧脚本），`may_override_num_blocks` 会无视 profile 直接钉死 2024。**先查 TP=8 的启动命令。**
2. **全局 min 被别的 worker 钳住**：min 是在**所有** worker（含边）上取的（kv_cache_utils.py:2192）。若边侧 spec 为空、投影回落到全模型 spec 但 available 是真实小显存（[kv_cache_utils.py:2121-2131](vllm/vllm/v1/core/kv_cache_utils.py#L2121-L2131) 的 fallback），或 TP=8 云双机下某个 rank 被同机进程占了显存，都会把全体拉平。
3. **TP=8 当次运行条件不同**：gpu_memory_utilization / max_num_batched_tokens 不同，或双机 TP 的 HCCL buffer 使 `non_torch_increase` 暴涨（但 25GB/卡 的量级对 HCCL 不太合理，嫌疑最低）。

## 验证方法（一条日志即可分辨）

看 TP=8 那次各 rank 的 `Available KV cache memory: X GiB`（[worker.py:793-795](vllm-ascend/vllm_ascend/worker/worker.py#L793-L795)）：
- 若 ≈50GB（≈TP4 每卡 KV 的 2 倍）而 num_blocks 仍 2024 → 被钳（候选 1/2）；
- 若只有 ≈25GB → 显存侧异常（候选 3），再看 profile_result 里 non_torch/torch_peak 哪项暴涨。

## 附带影响（对多实例设计文档）

如果 628（TP=2 云侧）这个数坐实，§6.3 的临界分析要重算：R = 16524/628 ≈ **26.3**，N=16 时 edge/16 = 1033 > 628，仍是 cloud-bound——**“N=16 容量翻转”的结论不再成立**，qwen3.6 多实例的容量上限直接解除。这也正是文档 open item“2 卡 tp2 实例云侧 num_blocks 需重测”指向的问题（旧表 2024 标成 C=2，现在看 2024 更像 TP=8 的值）。

我把这个新实测数字更新到记忆里：


---

## Assistant <sup>2026/8/18 14:56:37</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "C:\\Users\\root\\.claude\\projects\\c--v0-23-0-lwd-acc-test-br\\memory\\pd-multi-instance-scale.md"
}
```

</details>


---

## User <sup>2026/8/18 14:56:37</sup>

<details>
<summary>Tool Result</summary>

```
1	---
2	name: pd-multi-instance-scale
3	description: PD 边云多实例设计的规模/模型结论:N 上限按模型不同(qwen3.6-27b 16、DS 4、kimi 2);目标边云算力比 1:32 / 2:32
4	metadata: 
5	  node_type: memory
6	  type: project
7	  originSessionId: 8cd0c21c-50cb-452f-8e15-3f13bb365bd5
8	  modified: 2026-08-18T01:18:58.170Z
9	---
10	
11	PD batch 分离边云协同多实例调度设计(文档:vllm-ascend/docs/PDbatch分离边云协同多实例调度详细设计_NEW.md,"方案设计"阶段)的规模/模型结论(2026-08 明确):
12	
13	- **目标边云算力比**:embedding_only(边 1 卡)= 1:32、head_tail 首 x 尾 x(边 2 卡)= 2:32;云侧总量固定 32 卡 = **4 台 8 卡 A2 服务器满配**
14	- **每模型云部署卡数与 N 上限**(4×8 卡服务器满配下):
15	  - qwen3.6-27b:**2 卡/实例**,每服务器 4 实例(同机共置),**N 最大 16**--唯一触发容量临界(N=8 时 1.02×)/翻转(N=16 时 0.51×,云利用率 ~51%)的模型,R=8.16(edge 16524/cloud 2024)
16	  - deepseek-v4-flash-w8a8:**8 卡/实例**,每服务器 1 实例(无共置),N 上限 4,R=17.56(翻转点在 N 范围外)
17	  - kimi25_w4a8_static_m6:**16 卡/实例**,实例跨 2 台服务器,N 上限 2(容量安全,关注跨机 tp 带宽)
18	- 已定设计决策:
19	  - 实例编码 = **node_rank 复用为逻辑实例**(一物理机可承载多个 node-rank,各自 ASCEND_RT_VISIBLE_DEVICES 卡切片静态划分、不共卡),`instance_id = node_rank-1`、`N = nnodes
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 14:56:48</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "C:\\Users\\root\\.claude\\projects\\c--v0-23-0-lwd-acc-test-br\\memory\\pd-multi-instance-scale.md",
  "old_string": "  - qwen3.6-27b:**2 卡/实例**,每服务器 4 实例(同机共置),**N 最大 16**--唯一触发容量临界(N=8 时 1.02×)/翻转(N=16 时 0.51×,云利用率 ~51%)的模型,R=8.16(edge 16524/cloud 2024)",
  "new_string": "  - qwen3.6-27b:**2 卡/实例**,每服务器 4 实例(同机共置),**N 最大 16**--原判容量临界(N=8 1.02×)/翻转(N=16 0.51×)基于 R=8.16(edge 16524/cloud 2024)。**2026-08-18 重实测推翻该口径**:边云 head_tail 云侧 num_blocks TP=2/4/8 = **628/1763/2024**(2024 实为 TP=8 的值,旧表误标 C=2)。TP2->TP4 ×2.81 与代码仿射模型一致;**TP4->TP8 ×1.15 与代码不一致**(按 blocks(TP)≈567.5·TP−507 外推 TP8 应 ≈4033,实际 2024 只有一半,反推每卡可用 KV 比 TP2 还低,必有钳制;三大嫌疑:num_gpu_blocks_override=2024 / 全局 min 被边或弱势 rank 钳(kv_cache_utils.py:2192)/双机 TP8 non_torch 暴涨;验证=看 TP8 日志各 rank \"Available KV cache memory\")。若 628 坐实,R=16524/628≈26.3,**N=16 仍是 cloud-bound(1033>628),容量翻转结论不再成立**(§6.3 及本文档原结论待修订)"
}
```

</details>


---

## User <sup>2026/8/18 14:56:49</sup>

<details>
<summary>Tool Result</summary>

```
The file C:\Users\root\.claude\projects\c--v0-23-0-lwd-acc-test-br\memory\pd-multi-instance-scale.md has been updated successfully.
```

</details>


---

## Assistant <sup>2026/8/18 14:57:07</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "C:\\Users\\root\\.claude\\projects\\c--v0-23-0-lwd-acc-test-br\\memory\\pd-multi-instance-scale.md",
  "old_string": "description: PD 边云多实例设计的规模/模型结论:N 上限按模型不同(qwen3.6-27b 16、DS 4、kimi 2);目标边云算力比 1:32 / 2:32",
  "new_string": "description: PD 边云多实例设计的规模/模型结论:N 上限按模型不同(qwen3.6-27b 16、DS 4、kimi 2);qwen3.6 num_blocks 重实测 628/1763/2024@TP2/4/8,TP8 异常待查,N=16 翻转结论存疑"
}
```

</details>


---

## User <sup>2026/8/18 14:57:08</sup>

<details>
<summary>Tool Result</summary>

```
The file C:\Users\root\.claude\projects\c--v0-23-0-lwd-acc-test-br\memory\pd-multi-instance-scale.md has been updated successfully.
```

</details>


---

## Assistant <sup>2026/8/18 14:57:11</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cat \"/c/Users/root/.claude/projects/c--v0-23-0-lwd-acc-test-br/memory/MEMORY.md\"",
  "description": "Check memory index"
}
```

</details>


---

## User <sup>2026/8/18 14:57:12</sup>

<details>
<summary>Tool Result</summary>

```
- [PD deadlock localization](pd-deadlock-localization.md) - root cause found (include_mrope edge/cloud mismatch), fix applied, awaiting confirmation run
- [PD multi-instance scale](pd-multi-instance-scale.md) - N 上限按模型:qwen3.6-27b 16(2卡/实例,同机共置)/DS 4(8卡)/kimi 2(16卡跨机);算力比 1:32、2:32;N=16 容量翻转仅 qwen3.6
```

</details>


---

## Assistant <sup>2026/8/18 14:57:18</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "C:\\Users\\root\\.claude\\projects\\c--v0-23-0-lwd-acc-test-br\\memory\\MEMORY.md",
  "old_string": "- [PD multi-instance scale](pd-multi-instance-scale.md) - N 上限按模型:qwen3.6-27b 16(2卡/实例,同机共置)/DS 4(8卡)/kimi 2(16卡跨机);算力比 1:32、2:32;N=16 容量翻转仅 qwen3.6",
  "new_string": "- [PD multi-instance scale](pd-multi-instance-scale.md) - N 上限按模型:qwen3.6-27b 16/DS 4/kimi 2;qwen3.6 云侧 num_blocks 重实测 628/1763/2024@TP2/4/8,TP8 与代码预期(≈4033)不符待查,N=16 翻转结论存疑"
}
```

</details>


---

## User <sup>2026/8/18 14:57:19</sup>

<details>
<summary>Tool Result</summary>

```
The file C:\Users\root\.claude\projects\c--v0-23-0-lwd-acc-test-br\memory\MEMORY.md has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/18 14:57:29</sup>

## 结论汇总

**TP=2→4 与代码一致，TP=8 与代码不一致（被钳制）**：

- **代码应有的关系**：分子（每卡可用 KV = 0.9×HBM − 权重/TP − 激活 − non_torch）和分母（block 字节，full-attn KV heads 和 GDN state 均按 TP 切分）共同决定 `num_blocks(TP) ≈ 567.5·TP − 507`（由 TP2/4 两点拟合），即应近似线性增长。
- **TP2→TP4（×2.81）**：超线性，与“page 减半 + 权重释放翻倍 KV 预算”完全吻合 ✅
- **TP4→TP8（×1.15）**：代码预期 ≈4033，实际 2024 只有 50% ❌。反推 TP=8 每卡可用 KV 比 TP=2 还低，单 rank 公式解释不通。

**下一步最省事的判别**：查 TP=8 那次的启动参数有没有 `--num-gpu-blocks 2024`（2024 恰好是文档 §6.3 的历史值，嫌疑最大），再看各 rank 日志 `Available KV cache memory: X GiB`——若每卡 ≈50GB 而 num_blocks 仍 2024，就是 override 或全局 min 被别的 worker 钳住；若 ≈25GB，则是显存侧异常（双机 HCCL/激活峰值）。

**连带影响**：若 628（TP=2）坐实，R = 16524/628 ≈ 26.3，qwen3.6 N=16 时边侧 1033 > 云侧 628 仍为 cloud-bound，**§6.3 的“N=16 容量翻转”结论不再成立**——这正是文档 open item“2 卡 tp2 实例云侧 num_blocks 需重测”要防的事。已把新数字和 TP8 异常记入记忆，待你确认 TP=8 的启动配置后可再更新文档 §6.3。


---

## User <sup>2026/8/18 16:07:00</sup>

<ide_selection>The user selected the lines 2196 to 2196 from c:\v0.23.0_lwd_acc_test_br\vllm\vllm\v1\core\kv_cache_utils.py:
kv_cache_config.num_blocks

This may or may not be related to the current task.</ide_selection>

没有配置--num-gpu-blocks；C:\v0.23.0_lwd_acc_test_br\vllm\vllm\v1\core\kv_cache_utils.py的2196行增加kv_cache_config.num_blocks打印的；重新测试了一下，参数和之前有差异，但三组数据是相同条件下的：tp=8 num_blocks=1975  Available KV cache memory 49.6G; tp=4 num_blocks=1715  Available KV cache memory 43.5G; tp=2 num_blocks=611  Available KV cache memory 30.9G;


---

## Assistant <sup>2026/8/18 16:07:57</sup>


---

## Assistant <sup>2026/8/18 16:08:02</sup>

三组同条件的新数据非常关键——直接把钳制点定位出来了。先算隐含的每 block 池字节数：

| TP | avail | num_blocks | 隐含每 block 池字节 (avail÷blocks) |
|---|---|---|---|
| 2 | 30.9G | 611 | **50.6 MB** |
| 4 | 43.5G | 1715 | **25.4 MB** |
| 8 | 49.6G | 1975 | **25.1 MB** |

TP2→TP4 池字节正好减半（page 按 TP 切分 ✓），但 **TP4→TP8 几乎不变（25.4→25.1，仅差 conv 类小分量的继续切分）**——即每 rank 的 page 在 TP=8 处触底不再减半。这是“KV 头数 < TP 时复制而非切分”的典型特征。我验证一下模型的头数配置：


---

## Assistant <sup>2026/8/18 16:08:03</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rln \"qwen3\" /c/v0.23.0_lwd_acc_test_br/log/*.txt | head -5; grep -rh \"num_key_value_heads\\|linear_num\\|head_dim\\|num_hidden_layers\" /c/v0.23.0_lwd_acc_test_br/log/*.txt 2>/dev/null | head -20",
  "description": "Search logs for model config details"
}
```

</details>


---

## User <sup>2026/8/18 16:08:04</sup>

<details>
<summary>Tool Result</summary>

```
(Bash completed with no output)
```

</details>


---

## Assistant <sup>2026/8/18 16:08:09</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rh \"model\" /c/v0.23.0_lwd_acc_test_br/log/0810-2.txt | head -10; echo ===; grep -rn \"num_key_value_heads\\|num_kv_heads\" /c/v0.23.0_lwd_acc_test_br/vllm/vllm/model_executor/models/qwen3_5.py /c/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/patch/models/qwen3_5_edge_cloud.py | head",
  "description": "Look for model path and kv head references"
}
```

</details>


---

## User <sup>2026/8/18 16:08:10</sup>

<details>
<summary>Tool Result</summary>

```
(Worker_DP0_TP2_EP2 pid=155663) INFO 08-11 09:26:03 [model_runner_v1.py:8377] [SLICE-DIAG] _dummy_run: layer_slice_info=None is_first=None is_last=None start=None end=None total=None num_tokens=1 uniform_decode=False
(Worker_DP0_PP1_TP0_EP0 pid=155661) INFO 08-11 09:26:03 [model_runner_v1.py:8377] [SLICE-DIAG] _dummy_run: layer_slice_info=None is_first=None is_last=None start=None end=None total=None num_tokens=1 uniform_decode=False
(Worker_DP0_PP1_TP0_EP0 pid=155661) INFO 08-11 09:26:03 [model_runner_v1.py:2015] [PP-EVT] sync_meta: rank=1 dp_rank=0 call=12 my_bt=0 peer_bt=1 num_tokens=1
(Worker_DP0_PP1_TP0_EP0 pid=155661) INFO 08-11 09:26:03 [model_runner_v1.py:7953] [PAD-DIAG] dp_rank=0 allow_dp_padding=False local_num_tokens=1 padded=1 across_dp=[1, 15]
(Worker_DP0_PP1_TP0_EP0 pid=155661) INFO 08-11 09:26:03 [model_runner_v1.py:8653] [PD-DIAG] D. cloud _dummy_run INPUT (intermediate_tensors): shape=[1, 2048] norm=0.000000 mean=0.000000
(Worker_DP0_PP1_TP0_EP0 pid=155661) INFO 08-11
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/18 16:08:16</sup>


---

## Assistant <sup>2026/8/18 16:08:17</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -n \"model\\|qwen\\|served-model\\|/data\\|/home\\|/mnt\" /c/v0.23.0_lwd_acc_test_br/ec_rootcause.py | head -10",
  "description": "Check test script for model path"
}
```

</details>


---

## User <sup>2026/8/18 16:08:18</sup>

<details>
<summary>Tool Result</summary>

```
(Bash completed with no output)
```

</details>


---

## Assistant <sup>2026/8/18 16:09:08</sup>


---

## Assistant <sup>2026/8/18 16:09:27</sup>

三组新数据把上一轮的“TP=8 被钳”之谜解开了——**这组数据与代码实现是自洽的**，钳制机制是 **GQA KV 头数在 TP=8 触底复制**。推导如下。

## 1. 数据自洽性验证

按代码公式 `num_blocks = avail // (group_size × local_page)`（[kv_cache_utils.py:967](vllm/vllm/v1/core/kv_cache_utils.py#L967)），反解每 rank 每 block 池字节：

| TP | avail (GiB) | num_blocks | 隐含池字节/block |
|---|---|---|---|
| 2 | 30.9 | 611 | 54.3 MB |
| 4 | 43.5 | 1715 | 27.2 MB |
| 8 | 49.6 | 1975 | 27.0 MB |

交叉验证 TP4->TP8：`blocks(8)/blocks(4) = avail(8)/avail(4) × B(4)/B(8) = 1.140 × 1.010 = 1.152`，实测 1975/1715 = **1.152** ✅ 完全闭合。

## 2. 代码解释：page 为什么在 TP=8 不再减半

- **TP2->TP4：池字节 ×1.99**，page 精确减半——full-attn KV heads（[kv_cache_interface.py:194-200](vllm/vllm/v1/kv_cache_interface.py#L194-L200)）和 GDN state（[mamba_utils.py:223-233](vllm/vllm/model_executor/layers/mamba/mamba_utils.py#L223-L233)）都按 TP 切分 ✅
- **TP4->TP8：池字节 ×1.01**，主分量不再切分。代码里两类的行为不同：
  - **GDN 要求整除**（`assert num_heads % tp_size == 0`，[mamba_mixer2.py:285](vllm/vllm/model_executor/layers/mamba/mamba_mixer2.py#L285)）——不整除会直接断言失败，不会“触底”；
  - **full-attn KV heads 不整除时走复制**（vLLM GQA 标准逻辑：heads < TP 时每 rank 复制 1 个头）。

所以唯一能产生“TP4 后 page 恒定”的路径是：**`num_key_value_heads = 4`** → TP2 每 rank 2 头、TP4 每 rank 1 头、**TP8 复制成 8 份、每 rank 仍 1 头**（物理存储 2× 冗余）。TP4/TP8 的 page 主分量都是 `2×bs×1×hd×2B`，恒定；仅剩 conv state 等小分量继续切分（差的那 1%）。这同时要求 full-attn page 在 `local_page = max(各分量) + conv`（[kv_cache_utils.py:1303](vllm/vllm/v1/core/kv_cache_utils.py#L1303)）中占主导——与 27 MB/block 的量级吻合。

**一条验证**：看模型 config.json 的 `num_key_value_heads` 是否 = 4（或在 TP=8 日志/断点打印 spec 的 `num_kv_heads`，应看到每 rank 1 头、total 复制为 8）。

## 3. 结论

1. **611/1715/1975 与代码实现一致**，无需 override 或 min 钳制假设；上一轮“预期 TP8≈4033 落空”的原因是当时假设了 page 严格 ∝1/TP，实际在 TP>num_kv_heads 后 full-attn KV 复制、page 触底。
2. **TP=8 对 qwen3.6-27b 是负收益配置**：每卡释放的权重显存（avail 43.5→49.6G）大部分被 KV 复制浪费——full-attn KV 物理总量在 TP4->TP8 翻倍冗余，num_blocks 仅 +15%。token 容量角度 TP=4 是性价比拐点。
3. **多实例设计影响**（比上轮结论更确定）：云侧 2 卡实例 num_blocks ≈ 611（本轮参数口径），R = 16524/611 ≈ **27**，N=16 时边侧 1033 仍 > 云侧 611，**cloud-bound 不翻转**——§6.3 基于 2024@C=2 的“N=16 翻转、云利用率 51%”结论应作废，qwen3.6 多实例容量上限实际由边侧算力而非 KV 决定。

更新记忆：


---

## Assistant <sup>2026/8/18 16:09:37</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "C:\\Users\\root\\.claude\\projects\\c--v0-23-0-lwd-acc-test-br\\memory\\pd-multi-instance-scale.md",
  "old_string": "  - qwen3.6-27b:**2 卡/实例**,每服务器 4 实例(同机共置),**N 最大 16**--原判容量临界(N=8 1.02×)/翻转(N=16 0.51×)基于 R=8.16(edge 16524/cloud 2024)。**2026-08-18 重实测推翻该口径**:边云 head_tail 云侧 num_blocks TP=2/4/8 = **628/1763/2024**(2024 实为 TP=8 的值,旧表误标 C=2)。TP2->TP4 ×2.81 与代码仿射模型一致;**TP4->TP8 ×1.15 与代码不一致**(按 blocks(TP)≈567.5·TP−507 外推 TP8 应 ≈4033,实际 2024 只有一半,反推每卡可用 KV 比 TP2 还低,必有钳制;三大嫌疑:num_gpu_blocks_override=2024 / 全局 min 被边或弱势 rank 钳(kv_cache_utils.py:2192)/双机 TP8 non_torch 暴涨;验证=看 TP8 日志各 rank \"Available KV cache memory\")。若 628 坐实,R=16524/628≈26.3,**N=16 仍是 cloud-bound(1033>628),容量翻转结论不再成立**(§6.3 及本文档原结论待修订)",
  "new_string": "  - qwen3.6-27b:**2 卡/实例**,每服务器 4 实例(同机共置),**N 最大 16**--原判容量翻转(N=16 0.51×)基于 R=8.16(edge 16524/cloud 2024),**已作废**。2026-08-18 重实测(同条件三组,无 override):云侧 head_tail TP=2/4/8 num_blocks = **611/1715/1975**,avail = 30.9/43.5/49.6G。**TP8 增长停滞根因已定位(代码自洽,数字交叉验证闭合)**:隐含每 block 池字节 54.3/27.2/27.0MB,TP4->TP8 不再减半 = GQA full-attn KV 头触底复制(推断 num_key_value_heads=4:TP8 复制成 8 份每 rank 1 头,page 恒定;GDN 走整除断言不会触底,mamba_mixer2.py:285)。推论:TP=8 对该模型 KV 容量负收益(复制冗余 2×,num_blocks 仅 +15%),**TP=4 是容量性价比拐点**;待验证 config.json num_key_value_heads=4。R=16524/611≈27,**N=16 仍 cloud-bound 不翻转**,§6.3 翻转分析待按新口径修订,多实例上限实际由边侧算力而非 KV 决定"
}
```

</details>


---

## User <sup>2026/8/18 16:09:38</sup>

<details>
<summary>Tool Result</summary>

```
The file C:\Users\root\.claude\projects\c--v0-23-0-lwd-acc-test-br\memory\pd-multi-instance-scale.md has been updated successfully.
```

</details>


---

## Assistant <sup>2026/8/18 16:09:43</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "C:\\Users\\root\\.claude\\projects\\c--v0-23-0-lwd-acc-test-br\\memory\\pd-multi-instance-scale.md",
  "old_string": "description: PD 边云多实例设计的规模/模型结论:N 上限按模型不同(qwen3.6-27b 16、DS 4、kimi 2);qwen3.6 num_blocks 重实测 628/1763/2024@TP2/4/8,TP8 异常待查,N=16 翻转结论存疑",
  "new_string": "description: PD 边云多实例设计的规模/模型结论:N 上限按模型不同(qwen3.6-27b 16、DS 4、kimi 2);qwen3.6 num_blocks 611/1715/1975@TP2/4/8 已代码自洽(kv heads=4 触底复制),N=16 翻转结论已作废"
}
```

</details>


---

## User <sup>2026/8/18 16:09:44</sup>

<details>
<summary>Tool Result</summary>

```
The file C:\Users\root\.claude\projects\c--v0-23-0-lwd-acc-test-br\memory\pd-multi-instance-scale.md has been updated successfully.
```

</details>


---

## Assistant <sup>2026/8/18 16:09:49</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "C:\\Users\\root\\.claude\\projects\\c--v0-23-0-lwd-acc-test-br\\memory\\MEMORY.md",
  "old_string": "- [PD multi-instance scale](pd-multi-instance-scale.md) - N 上限按模型:qwen3.6-27b 16/DS 4/kimi 2;qwen3.6 云侧 num_blocks 重实测 628/1763/2024@TP2/4/8,TP8 与代码预期(≈4033)不符待查,N=16 翻转结论存疑",
  "new_string": "- [PD multi-instance scale](pd-multi-instance-scale.md) - N 上限按模型:qwen3.6-27b 16/DS 4/kimi 2;qwen3.6 云侧 num_blocks 611/1715/1975@TP2/4/8 已代码自洽(kv heads=4 TP8 触底复制),N=16 翻转结论作废"
}
```

</details>


---

## User <sup>2026/8/18 16:09:50</sup>

<details>
<summary>Tool Result</summary>

```
The file C:\Users\root\.claude\projects\c--v0-23-0-lwd-acc-test-br\memory\MEMORY.md has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/18 16:09:57</sup>

**总结**：这组同条件数据与代码实现**一致**，且比上一轮更能说明问题：

1. **TP4->TP8 的 blocks 比 1.152 = avail 比 1.140 × 池字节比 1.010**，与 `num_blocks = avail // (group_size × page)` 完全闭合；
2. 池字节 54.3 -> 27.2 -> 27.0 MB 的“减半后触底”指向 **full-attn KV 头数 = 4**：TP=8 时头数 < TP，vLLM 走复制路径（每 rank 1 头、8 份含 2× 冗余），page 不再下降；GDN 因有整除断言不可能触底，排除。
3. 工程结论：该模型 TP=8 是 KV 容量负收益配置（+15% blocks 换 2× KV 复制冗余），TP=4 是拐点；多实例 N=16 的“容量翻转”结论作废（R≈27，恒 cloud-bound）。

剩一个待确认项：模型 config.json 的 `num_key_value_heads` 是否 = 4（顺手看一眼即可闭环）。


---
