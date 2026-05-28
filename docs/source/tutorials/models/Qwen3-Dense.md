# Qwen3-Dense (Qwen3-0.6B/1.7B/4B/8B/14B/32B, W8A8, W4A8, W4A4, W8A8SC-310)

## 1 Introduction

Qwen3 is the latest generation of large language models in Qwen series, offering a comprehensive suite of dense and mixture-of-experts (MoE) models. Built upon extensive training, Qwen3 delivers groundbreaking advancements in reasoning, instruction-following, agent capabilities, and multilingual support. The Dense variants covered in this document include Qwen3-0.6B, 1.7B, 4B, 8B, 14B, and 32B, along with their quantized versions (W8A8, W4A8, W4A4, and W8A8SC-310) optimized for Ascend NPU deployment.

This document will demonstrate the main validation steps for Qwen3 Dense models in the vLLM-Ascend environment, including supported features, environment preparation, model quantization, single-node and multi-node deployment, as well as accuracy and performance evaluation. By tailoring service-level configurations to fit different use cases, you can ensure optimal performance across various scenarios.

The Qwen3 Dense models are first supported in v0.8.4rc2. W8A8 quantization was first supported in v0.8.4rc2, W4A8 quantization is supported since v0.9.1rc2, and W4A4 is supported since v0.11.0rc1. Atlas inference products use the W8A8SC-310 quantized weights listed in this tutorial. This document is validated and written based on **vLLM-Ascend v0.21.0**. All **v0.21.0 and later versions** can run stably. To use the latest features, it is recommended to use the latest release candidate or official version.

## 2 Supported Features

Please refer to the [Supported Features List](../../user_guide/support_matrix/supported_models.md) for the model support matrix.

Please refer to the [Feature Guide](../../user_guide/feature_guide/index.md) for feature configuration information.

## 3 Prerequisites

### 3.1 Model Weight

The following model variants are available. It is recommended to download the model weight to a shared directory accessible to all nodes.

**BF16 Versions:**

| Model | Hardware Requirement | Download |
|-------|---------------------|----------|
| Qwen3-0.6B | 1 Atlas A3 inference products (64G × 16), 1 Atlas A2 inference products (64G × 8) | [Download](https://modelers.cn/models/Modelers_Park/Qwen3-0.6B) |
| Qwen3-1.7B | 1 Atlas A3 inference products (64G × 16), 1 Atlas A2 inference products (64G × 8) | [Download](https://modelers.cn/models/Modelers_Park/Qwen3-1.7B) |
| Qwen3-4B | 1 Atlas A3 inference products (64G × 16), 1 Atlas A2 inference products (64G × 8) | [Download](https://modelers.cn/models/Modelers_Park/Qwen3-4B) |
| Qwen3-8B | 1 Atlas A3 inference products (64G × 16), 1 Atlas A2 inference products (64G × 8) | [Download](https://modelers.cn/models/Modelers_Park/Qwen3-8B) |
| Qwen3-14B | 1 Atlas A3 inference products (64G × 16), 1 Atlas A2 inference products (64G × 8) | [Download](https://modelers.cn/models/Modelers_Park/Qwen3-14B) |
| Qwen3-32B | 1 Atlas A3 inference products (64G × 16), 1 Atlas A2 inference products (64G × 8) | [Download](https://modelers.cn/models/Modelers_Park/Qwen3-32B) |

**Quantized Versions for Atlas A2/A3 inference products:**

| Model | Quantization | Hardware Requirement | Download |
|-------|-------------|---------------------|----------|
| Qwen3-8B-W4A8 | W4A8 | 1 Atlas A3 inference products (64G × 16) or 1 Atlas A2 inference products (64G × 8) | [Download](https://www.modelscope.cn/models/vllm-ascend/Qwen3-8B-W4A8) |
| Qwen3-32B-W4A4 | W4A4 | 1 Atlas A3 inference products (64G × 16) or 1 Atlas A2 inference products (64G × 8) | [Download](https://www.modelscope.cn/models/vllm-ascend/Qwen3-32B-W4A4) |
| Qwen3-32B-W8A8 | W8A8 | 1 Atlas A3 inference products (64G × 16) or 1 Atlas A2 inference products (64G × 8) | [Download](https://www.modelscope.cn/models/vllm-ascend/Qwen3-32B-W8A8) |

**Quantized Versions for Atlas inference products:**

| Model | Quantization | Hardware Requirement | Download |
|-------|-------------|---------------------|----------|
| Qwen3-8B-W8A8SC | W8A8SC | Atlas inference products (TP1) | [Download](https://www.modelscope.cn/models/Eco-Tech/Qwen3-8B-w8a8sc-310-vllm) |
| Qwen3-14B-W8A8SC | W8A8SC | Atlas inference products (TP1) | [Download](https://www.modelscope.cn/models/Eco-Tech/Qwen3-14B-w8a8sc-310-vllm) |
| Qwen3-32B-W8A8SC | W8A8SC | Atlas inference products (TP4) | [Download](https://www.modelscope.cn/models/Eco-Tech/Qwen3-32B-w8a8sc-310-vllm) |

These are the recommended numbers of cards, which can be adjusted according to the actual situation.

### 3.2 Verify Multi-node Communication

If you need to deploy a multi-node environment, verify the multi-node communication according to [Verify Multi-node Communication Environment](../../installation.md#verify-multi-node-communication).

## 4 Installation

### 4.1 Docker Image Installation

You can use the official all-in-one Docker image for Qwen3 Dense models.

**Docker Pull:**

```{code-block} bash
   :substitutions:

docker pull quay.io/ascend/vllm-ascend:|vllm_ascend_version|
```

**Docker Run:**

Start the docker image on your each node.

:::::{tab-set}
::::{tab-item} Atlas A3 inference products
:sync: A3

```{code-block} bash
   :substitutions:

export IMAGE=quay.io/ascend/vllm-ascend:|vllm_ascend_version|-a3

docker run --rm \
    --name vllm-ascend-env \
    --shm-size=1g \
    --net=host \
    --device /dev/davinci0 \
    --device /dev/davinci1 \
    --device /dev/davinci2 \
    --device /dev/davinci3 \
    --device /dev/davinci4 \
    --device /dev/davinci5 \
    --device /dev/davinci6 \
    --device /dev/davinci7 \
    --device /dev/davinci8 \
    --device /dev/davinci9 \
    --device /dev/davinci10 \
    --device /dev/davinci11 \
    --device /dev/davinci12 \
    --device /dev/davinci13 \
    --device /dev/davinci14 \
    --device /dev/davinci15 \
    --device /dev/davinci_manager \
    --device /dev/devmm_svm \
    --device /dev/hisi_hdc \
    -v /usr/local/dcmi:/usr/local/dcmi \
    -v /usr/local/Ascend/driver/tools/hccn_tool:/usr/local/Ascend/driver/tools/hccn_tool \
    -v /usr/local/bin/npu-smi:/usr/local/bin/npu-smi \
    -v /usr/local/Ascend/driver/lib64/:/usr/local/Ascend/driver/lib64/ \
    -v /usr/local/Ascend/driver/version.info:/usr/local/Ascend/driver/version.info \
    -v /etc/ascend_install.info:/etc/ascend_install.info \
    -v /root/.cache:/root/.cache \
    -it $IMAGE bash
```

:::{note}
Atlas A3 inference products have 8 NPUs with dual-die design (16 chips total: `/dev/davinci[0-15]`).
If you are on a shared machine, map only the chips you need (e.g., `/dev/davinci[0-7]` for NPU 0-3).
:::

::::
::::{tab-item} Atlas A2 inference products
:sync: A2

```{code-block} bash
   :substitutions:

export IMAGE=quay.io/ascend/vllm-ascend:|vllm_ascend_version|

docker run --rm \
    --name vllm-ascend-env \
    --shm-size=1g \
    --net=host \
    --device /dev/davinci0 \
    --device /dev/davinci1 \
    --device /dev/davinci2 \
    --device /dev/davinci3 \
    --device /dev/davinci4 \
    --device /dev/davinci5 \
    --device /dev/davinci6 \
    --device /dev/davinci7 \
    --device /dev/davinci_manager \
    --device /dev/devmm_svm \
    --device /dev/hisi_hdc \
    -v /usr/local/dcmi:/usr/local/dcmi \
    -v /usr/local/Ascend/driver/tools/hccn_tool:/usr/local/Ascend/driver/tools/hccn_tool \
    -v /usr/local/bin/npu-smi:/usr/local/bin/npu-smi \
    -v /usr/local/Ascend/driver/lib64/:/usr/local/Ascend/driver/lib64/ \
    -v /usr/local/Ascend/driver/version.info:/usr/local/Ascend/driver/version.info \
    -v /etc/ascend_install.info:/etc/ascend_install.info \
    -v /root/.cache:/root/.cache \
    -it $IMAGE bash
```

::::
::::{tab-item} Atlas inference products

```{code-block} bash
   :substitutions:

# Use the vllm-ascend image
export IMAGE=quay.io/ascend/vllm-ascend:|vllm_ascend_version|-310p

docker run --rm \
--name vllm-ascend \
--shm-size=10g \
--device /dev/davinci0 \
--device /dev/davinci1 \
--device /dev/davinci2 \
--device /dev/davinci3 \
--device /dev/davinci4 \
--device /dev/davinci5 \
--device /dev/davinci6 \
--device /dev/davinci7 \
--device /dev/davinci_manager \
--device /dev/devmm_svm \
--device /dev/hisi_hdc \
-v /usr/local/dcmi:/usr/local/dcmi \
-v /usr/local/bin/npu-smi:/usr/local/bin/npu-smi \
-v /usr/local/Ascend/driver/lib64/:/usr/local/Ascend/driver/lib64/ \
-v /usr/local/Ascend/driver/version.info:/usr/local/Ascend/driver/version.info \
-v /etc/ascend_install.info:/etc/ascend_install.info \
-v /root/.cache:/root/.cache \
-p 8080:8080 \
-it $IMAGE bash
```

::::
:::::

The default workdir is `/workspace`. vLLM and vLLM-Ascend are installed as Python packages in site-packages.

Installation Verification:
After starting the container, run the following command to verify the installation:

```bash
docker ps | grep vllm-ascend-env
```

Expected result: The container is listed with status Up. You can also verify the vllm-ascend version inside the container:

```bash
pip show vllm-ascend
```

Expected result: The version information is displayed, matching the pulled image version.

### 4.2 Source Code Installation

If you prefer to build from source instead of using the Docker image, install vLLM-Ascend following the [Installation Guide](../../installation.md).

:::{note}
For Atlas inference products, source installation may pull in `triton` and `triton-ascend`. Uninstall them before running vLLM-Ascend on Atlas inference products:

```bash
pip uninstall -y triton-ascend triton
```

:::

To verify the source installation:

```bash
pip show vllm-ascend
```

Expected result: The version information is displayed, confirming a successful installation.

:::{note}
If deploying a multi-node environment, set up the environment on each node.
:::

## 5 Online Service Deployment

### 5.1 Single-Node Online Deployment

Single-node deployment completes both Prefill and Decode within the same node, suitable for development, testing, and small-to-medium scale inference scenarios.

**Start the server:**
> The following command is an example configuration. Adjust the parameters based on your actual scenario.

:::::{tab-set}
::::{tab-item} Atlas A2 inference products / Atlas A3 inference products

Qwen3-32B-W8A8:

```bash
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export TASK_QUEUE_ENABLE=1
export HCCL_OP_EXPANSION_MODE="AIV"

# Enable FlashComm_v1 optimization when tensor parallel is enabled.
export VLLM_ASCEND_ENABLE_FLASHCOMM1=1

vllm serve vllm-ascend/Qwen3-32B-W8A8 \
  --served-model-name qwen3 \
  --trust-remote-code \
  --quantization ascend \
  --distributed-executor-backend mp \
  --tensor-parallel-size 4 \
  --max-model-len 5500 \
  --max-num-batched-tokens 40960 \
  --compilation-config '{"cudagraph_mode": "FULL_DECODE_ONLY"}' \
  --additional-config '{"pa_shape_list":[48,64,72,80], "weight_prefetch_config":{"enabled":true}}' \
  --port 8113 \
  --block-size 128 \
  --gpu-memory-utilization 0.9
```

Qwen3-32B-W4A4:

```bash
export ASCEND_RT_VISIBLE_DEVICES=0,1
export VLLM_USE_V1=1
export TASK_QUEUE_ENABLE=1
export HCCL_BUFFSIZE=1024
vllm serve your_model_path \
    --port 8004 \
    --data-parallel-size 1 \
    --tensor-parallel-size 2 \
    --served-model-name qwen3 \
    --distributed_executor_backend "mp" \
    --max-model-len 40960 \
    --max-num-batched-tokens 16384 \
    --max-num-seqs 64 \
    --trust-remote-code \
    --gpu-memory-utilization 0.9 \
    --quantization ascend \
    --compilation-config '{"cudagraph_capture_sizes": [64]}' \
    --additional-config '{"enable_flashcomm1": true, "ascend_compilation_config": {"fuse_norm_quant": false}}'
```

Qwen3-8B-W4A8:

```bash
export ASCEND_RT_VISIBLE_DEVICES=0,1
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
vllm serve your_model_path \
    --served-model-name qwen3 \
    --max-model-len 4096 \
    --port 20001 \
    --additional-config '{"ascend_compilation_config": {"enable_npugraph_ex": false}}' \
    --quantization ascend
```

::::
::::{tab-item} Atlas inference products

Atlas inference products use the W8A8SC-310 quantized weights from the Eco-Tech official ModelScope repository. Keep an explicit `--max-model-len` for 310P deployment to avoid OOM caused by oversized attention mask allocation.

Qwen3-8B-W8A8SC:

```bash
export VLLM_USE_MODELSCOPE=True
export ASCEND_RT_VISIBLE_DEVICES=0

vllm serve Eco-Tech/Qwen3-8B-w8a8sc-310-vllm/TP1/Qwen3-8B-w8a8sc-310-vllm-tp1 \
    --host 127.0.0.1 \
    --port 8080 \
    --tensor-parallel-size 1 \
    --gpu-memory-utilization 0.90 \
    --max-num-seqs 32 \
    --served-model-name qwen3 \
    --dtype float16 \
    --additional-config '{"ascend_compilation_config": {"fuse_norm_quant": false}}' \
    --compilation-config '{"cudagraph_mode": "FULL_DECODE_ONLY", "cudagraph_capture_sizes": [1,2,4,8,16,32]}' \
    --quantization ascend \
    --max-model-len 16384 \
    --no-enable-prefix-caching \
    --load-format sharded_state
```

Qwen3-14B-W8A8SC:

```bash
export VLLM_USE_MODELSCOPE=True
export ASCEND_RT_VISIBLE_DEVICES=0

vllm serve Eco-Tech/Qwen3-14B-w8a8sc-310-vllm/TP1/Qwen3-14B-w8a8sc-310-vllm-tp1 \
    --host 127.0.0.1 \
    --port 8080 \
    --tensor-parallel-size 1 \
    --gpu-memory-utilization 0.90 \
    --max-num-seqs 16 \
    --served-model-name qwen3 \
    --dtype float16 \
    --additional-config '{"ascend_compilation_config": {"fuse_norm_quant": false}}' \
    --compilation-config '{"cudagraph_mode": "FULL_DECODE_ONLY", "cudagraph_capture_sizes": [1,2,4,8,16]}' \
    --quantization ascend \
    --max-model-len 16384 \
    --no-enable-prefix-caching \
    --load-format sharded_state
```

Qwen3-32B-W8A8SC:

```bash
export VLLM_USE_MODELSCOPE=True
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3

vllm serve Eco-Tech/Qwen3-32B-w8a8sc-310-vllm/TP4/Qwen3-32B-w8a8sc-310-vllm-tp4 \
    --host 127.0.0.1 \
    --port 8080 \
    --tensor-parallel-size 4 \
    --gpu-memory-utilization 0.90 \
    --max-num-seqs 32 \
    --served-model-name qwen3 \
    --dtype float16 \
    --additional-config '{"ascend_compilation_config": {"fuse_norm_quant": false}}' \
    --compilation-config '{"cudagraph_mode": "FULL_DECODE_ONLY", "cudagraph_capture_sizes": [16,32]}' \
    --quantization ascend \
    --max-model-len 20480 \
    --no-enable-prefix-caching \
    --load-format sharded_state
```

::::
:::::

:::{note}

- [vLLM Serving Arguments documentation](https://docs.vllm.com.cn/en/latest/cli/serve/?h=block+size#arguments) — Additional parameter details for vLLM serve commands.
- [Environment Variables](../../user_guide/configuration/env_vars.md) — Ascend-specific environment variables (`HCCL_*`, etc.).
:::

**Service Verification:**

If the service starts successfully, the following startup log will be displayed:

```text
(APIServer pid=<pid>) INFO:     Started server process [<pid>]
(APIServer pid=<pid>) INFO:     Waiting for application startup.
(APIServer pid=<pid>) INFO:     Application startup complete.
```

## 6 Functional Verification

After the service is started, the model can be invoked by sending a prompt.

**Chat Completions API:**

```bash
curl http://localhost:<port>/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "qwen3",
        "messages": [
            {"role": "user", "content": "Give me a short introduction to large language models."}
        ],
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 20,
        "max_completion_tokens": 4096
    }'
```

Expected result: HTTP 200 with a JSON response containing the `choices` field with generated text.

## 7 Accuracy Evaluation

### Using AISBench

For setup details, including installation, dataset download, and configuration, please refer to [Using AISBench](../../developer_guide/evaluation/using_ais_bench.md).

The following is an example configuration for the accuracy evaluation config file:

**Accuracy Evaluation Config File:**

```bash
# Example configuration: benchmarks/ais_bench/benchmark/configs/models/vllm_api/vllm_api_general_chat.py
from ais_bench.benchmark.models import VLLMCustomAPIChat
from ais_bench.benchmark.utils.model_postprocessors import extract_non_reasoning_content

models = [
    dict(
        attr="service",
        type=VLLMCustomAPIChat,
        abbr='vllm-api-general-chat',
        path="your_model_path",
        model="qwen3",
        request_rate = 0,
        retry = 2,
        host_ip = "127.0.0.1",
        host_port = 2001,
        max_out_len = 32768,
        batch_size = 32,
        trust_remote_code=False,
        generation_kwargs = dict(
            temperature = 0.6,
            top_k = 20,
            top_p = 0.95,
        ),
        pred_postprocessor=dict(type=extract_non_reasoning_content)
    )
]
```

**Run the accuracy evaluation using the aime2025 dataset as an example:**

```bash
ais_bench --models vllm_api_general_chat --datasets aime2025_gen_0_shot_chat_prompt --debug
```

> The --models parameter value corresponds to the abbr field in the configuration file above. Adjust max_out_len, batch_size, and dataset tasks based on your scenario.

## 8 Performance Evaluation

### Using AISBench

For setup details, including installation, dataset download, and configuration, please refer to [Using AISBench](../../developer_guide/evaluation/using_ais_bench.md#execute-performance-evaluation) for details.

The following is an example configuration for the accuracy evaluation config file:

```bash
# Example configuration: benchmarks/ais_bench/benchmark/configs/models/vllm_api/vllm_api_stream_chat.py
from ais_bench.benchmark.models import VLLMCustomAPIChat
from ais_bench.benchmark.utils.postprocess.model_postprocessors import extract_non_reasoning_content

models = [
    dict(
        attr="service",
        type=VLLMCustomAPIChat,
        abbr="vllm-api-stream-chat",
        path="your_model_path",
        model="qwen3",
        stream=True,
        request_rate=0,
        use_timestamp=False,
        retry=2,
        host_ip="127.0.0.1",
        host_port=8004,
        max_out_len=1500,
        batch_size=90,
        trust_remote_code=False,
        generation_kwargs=dict(
            temperature=0,
            ignore_eos = True
        ),
    )
]
```

**Run the performance evaluation using the GSM8K dataset as an example:**

```bash
ais_bench --models vllm_api_stream_chat --datasets gsm8k_gen_0_shot_cot_str_perf --debug --summarizer default_perf --mode perf --num-prompts 360
```

### Using vLLM Benchmark

Refer to [vLLM benchmark](https://docs.vllm.ai/en/latest/benchmarking/) for more details.

There are three `vllm bench` subcommands:

- `latency`: Benchmark the latency of a single batch of requests.
- `serve`: Benchmark the online serving throughput.
- `throughput`: Benchmark offline inference throughput.

Take `serve` as an example:

```shell
vllm bench serve \
    --model your_model_path \
    --served-model-name qwen3 \
    --port <port> \
    --dataset-name random \
    --random-input 200 \
    --num-prompts 200 \
    --request-rate 1 \
    --save-result \
    --result-dir ./
```

After several minutes, you will get the performance evaluation result.

## 9 Performance Tuning

### 9.1 Recommended Configurations

> **Note**: The following configurations are validated in specific test environments and are for reference only. The optimal configuration depends on factors such as maximum input/output length, prefix cache hit rate, precision requirements, and deployment machine ratios. It is recommended to refer to Section 9.2 for tuning based on actual conditions.

#### Table 1: Scenario Overview

| Scenario | Deployment Mode | *Total NPUs | Weight Version | Key Considerations |
|----------|----------------|-------------|----------------|---------------------|
| High Throughput | Single-Node (TP4) | 4 (Atlas A3 inference products) | W8A8 | 4-card TP maximizes concurrent request processing |
| Long Context | Single-Node (TP4) | 4 (Atlas A3 inference products) | W8A8 | 4-card TP extends context window for long sequences |
| Low Latency | Single-Node (TP8) | 8 (Atlas A3 inference products) | W8A8 | 8-card TP reduces per-token latency for interactive responses |

> `*Total NPUs` indicates the total number of NPUs used across all nodes.

#### Table 2: Detailed Node Configuration

| Scenario | Configuration | #NPUs | TP | DP | FUSED_MC2 | EP Switch | Async Scheduling |
|----------|---------------|-------|----|----|-------------|--------------|--------------|
| High Throughput | Single-Node | 4 | 4 | 1 | Off | Off | On |
| Long Context | Single-Node | 4 | 4 | 1 | Off | Off | On |
| Low Latency | Single-Node | 8 | 8 | 1 | Off | Off | On |

For detailed parameter descriptions, please refer to the deployment examples in [Section 5](#5-online-service-deployment)

<u>High Throughput Configuration:</u>

```bash
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export TASK_QUEUE_ENABLE=1
export HCCL_OP_EXPANSION_MODE="AIV"

vllm serve your_model_path \
  --served-model-name qwen3 \
  --trust-remote-code \
  --distributed-executor-backend mp \
  --tensor-parallel-size 4 \
  --max-model-len 5500 \
  --max-num-batched-tokens 40960 \
  --no-enable-prefix-caching \
  --async-scheduling \
  --quantization ascend \
  --compilation-config '{"cudagraph_mode":"FULL_DECODE_ONLY","cudagraph_capture_sizes":[4,8,64,72,76,80,96,100,120,140,144,160,192,216,240,252,288,320,336,360,384,400,408,416,420,432,480,540,576,600]}' \
  --additional-config '{"weight_prefetch_config":{"enabled":true}, "enable_flashcomm1": true}' \
  --host <host_ip> \
  --port <port> \
  --block-size 128 \
  --gpu-memory-utilization 0.9
```

<u>Long Context Configuration:</u>

```bash
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export TASK_QUEUE_ENABLE=1
export HCCL_OP_EXPANSION_MODE="AIV"

vllm serve your_model_path \
  --host <host_ip> \
  --port <port> \
  --served-model-name qwen3 \
  --trust-remote-code \
  --seed 1024 \
  --max-model-len 135000 \
  --max-num-batched-tokens 40960 \
  --tensor-parallel-size 4 \
  --distributed-executor-backend "mp" \
  --async-scheduling \
  --no-enable-prefix-caching \
  --speculative-config '{"method": "eagle3", "model":"your_eagle3_model_path", "num_speculative_tokens": 3}' \
  --compilation-config '{"cudagraph_mode": "FULL_DECODE_ONLY"}' \
  --hf-overrides '{"rope_parameters": {"rope_type":"yarn","rope_theta":1000000,"factor":4,"original_max_position_embeddings":131072}}' \
  --gpu-memory-utilization 0.9 \
  --quantization ascend \
  --additional-config '{"enable_flashcomm1": true}'
```

<u>Low Latency Configuration:</u>

```bash
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export TASK_QUEUE_ENABLE=1
export HCCL_OP_EXPANSION_MODE="AIV"

vllm serve your_model_path \
  --served-model-name qwen3 \
  --trust-remote-code \
  --distributed-executor-backend mp \
  --tensor-parallel-size 8 \
  --max-model-len 5500 \
  --max-num-batched-tokens 40960 \
  --no-enable-prefix-caching \
  --async-scheduling \
  --quantization ascend \
  --compilation-config '{"cudagraph_mode": "FULL_DECODE_ONLY","cudagraph_capture_sizes":[1,2,4,8,16,32,64,72,76,80,96,100,120,140,144,160,192,216,240,252,288,320,336,360,384,400,408,416,420,432,480,540,576,600]}' \
  --speculative-config '{"method": "eagle3", "model":"your_eagle3_model_path", "enforce_eager": true, "num_speculative_tokens": 3}' \
  --port <port> \
  --block-size 128 \
  --gpu-memory-utilization 0.9
```

### 9.2 Tuning Guidelines

#### 9.2.1 General Tuning Reference

Please refer to the [Public Performance Tuning Documentation](../../developer_guide/performance_and_debug/optimization_and_tuning.md) for tuning methods.
Please refer to the [Feature Guide](../../user_guide/support_matrix/feature_matrix.md) for detailed feature descriptions.

## 10 FAQ

### 7. FullGraph Optimization

ACLGraph offers several key optimizations to improve model execution efficiency. By replaying the entire model execution graph at once, we significantly reduce dispatch latency compared to multiple smaller replays. This approach also stabilizes multi-device performance, as capturing the model as a single static graph mitigates dispatch fluctuations across devices. Additionally, consolidating graph captures frees up streams, allowing for the capture of more graphs and optimizing resource usage, ultimately leading to improved system efficiency and reduced overhead.

The configuration compilation_config = { "cudagraph_mode": "FULL_DECODE_ONLY"} is used when starting the service. This setup is necessary to enable the aclgraph's full decode-only mode.

### 8. Asynchronous Scheduling

Asynchronous scheduling is a technique used to optimize inference efficiency. It allows non-blocking task scheduling to improve concurrency and throughput, especially when processing large-scale models.

## Optimization Highlights

Building on the specific example scenarios outlined earlier, this section highlights the key tuning points that played a crucial role in achieving optimal performance. By focusing on the most impactful adjustments to hyperparameters and optimizations, we’ll emphasize the strategies that can be leveraged to maximize throughput, minimize latency, and ensure efficient resource utilization in various environments. These insights will help guide you in fine-tuning your own configurations for the best possible results.

### 1.Prefetch Buffer Size

Setting the right prefetch buffer size is essential for optimizing weight loading and the size of this prefetch buffer is directly related to the time that can be hidden by vector computations. To achieve a near-perfect overlap between the prefetch and computation streams, you can flexibly adjust the buffer size by profiling and observing the degree of overlap at different buffer sizes.

For example, in the real-world scenario mentioned above, I set the prefetch buffer size for the gate_up_proj and down_proj in the MLP to 18MB. The reason for this is that, at this value, the vector computations of RMSNorm and SiLU can effectively hide the prefetch stream, thereby accelerating the Matmul computations of the two linear layers.

### 2.Max-num-batched-tokens

The max-num-batched-tokens parameter determines the maximum number of tokens that can be processed in a single batch. Adjusting this value helps to balance throughput and memory usage. Setting this value too small can negatively impact end-to-end performance, as fewer tokens are processed per batch, potentially leading to inefficiencies. Conversely, setting it too large increases the risk of Out of Memory (OOM) errors due to excessive memory consumption.

In the above real-world scenario, we not only conducted extensive testing to determine the most cost-effective value, but also took into account the accumulation of decode tokens when enabling chunked prefill. If the value is set too small, a single request may be chunked multiple times, and during the early stages of inference, a batch may contain only a small number of decode tokens. This can result in the end-to-end throughput falling short of expectations.

### 3.Cudagraph_capture_sizes

The cudagraph_capture_sizes parameter controls the granularity of graph captures during the inference process. Adjusting this value determines how much of the computation graph is captured at once, which can significantly impact both performance and memory usage.

If this list is not manually specified, it will be filled with a series of evenly distributed values, which typically ensures good performance. However, if you want to fine-tune it further, manually specifying the values will yield better results. This is because if the batch size falls between two sizes, the framework will automatically pad the token count to the larger size. This often leads to actual performance deviating from the expected or even degrading.

Therefore, like the above real-world scenario, when adjusting the benchmark request concurrency, we always ensure that the concurrency is actually included in the cudagraph_capture_sizes list. This way, during the decode phase, padding operations are essentially avoided, ensuring the reliability of the experimental data.

It's important to note that if you enable FlashComm_v1, the values in this list must be integer multiples of the TP size. Any values that do not meet this condition will be automatically filtered out. Therefore, I recommend incrementally adding concurrency based on the TP size after enabling FlashComm_v1.
