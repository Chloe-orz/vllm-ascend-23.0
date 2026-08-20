#!/usr/bin/env bash
# 两边一云（2E1C）启动脚本 —— 云侧（10.0.0.13，TP=4，物理卡 0-3）
# 用法：MODEL=/path/to/model bash start_cloud.sh
set -euo pipefail
MODEL=${MODEL:?export MODEL=/path/to/model}
REGISTRY=${REGISTRY:-$(dirname "$0")/registry_2e1c.yaml}

# 物理选卡（本机用哪几张卡）与全局 rank 分配（必须匹配注册表 ranks）
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3
export RANK_START=2   # 本实例首个进程的全局 rank = 注册表 clouds[0].ranks[0]

vllm serve "$MODEL" \
  --headless \
  --enable-edge-cloud \
  --cloud-id 0 \
  --role-registry "$REGISTRY" \
  --cloud-npu-count 4 \
  --tensor-parallel-size 4 \
  --additional-config '{"edge_cloud_config":{"enabled":true,"role":"cloud","mode":"embedding_only","pd_separation":{"enabled":true}}}' \
  --master-addr 10.0.0.13 --master-port 29600 \
  2>&1 | tee /var/log/edge_cloud/cloud_c0.log
