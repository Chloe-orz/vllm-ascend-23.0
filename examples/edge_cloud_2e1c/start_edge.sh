#!/usr/bin/env bash
# 两边一云（2E1C）启动脚本 —— 边侧（10.0.0.11 / 10.0.0.12，各 1 卡）
# 用法：MODEL=/path/to/model EDGE_ID=0|1 PHYSICAL_NPU=<本机卡号> bash start_edge.sh
set -euo pipefail
MODEL=${MODEL:?export MODEL=/path/to/model}
EDGE_ID=${EDGE_ID:?export EDGE_ID=0 或 1}
PHYSICAL_NPU=${PHYSICAL_NPU:-0}          # 本机物理卡号（默认 0）
REGISTRY=${REGISTRY:-$(dirname "$0")/registry_2e1c.yaml}

# 物理选卡（本机用哪张卡）；全局 rank 由注册表 edges[EDGE_ID].ranks 指定（=EDGE_ID）
export ASCEND_RT_VISIBLE_DEVICES=$PHYSICAL_NPU

vllm serve "$MODEL" \
  --enable-edge-cloud \
  --edge-id "$EDGE_ID" \
  --role-registry "$REGISTRY" \
  --edge-npu-count 1 \
  --cloud-npu-count 4 \
  --additional-config '{"edge_cloud_config":{"enabled":true,"role":"edge","mode":"embedding_only","pd_separation":{"enabled":true}}}' \
  --master-addr 10.0.0.13 --master-port 29600 \
  2>&1 | tee "/var/log/edge_cloud/edge_e${EDGE_ID}.log"
