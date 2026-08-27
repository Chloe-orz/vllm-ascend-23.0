# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project
# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
# Edge-cloud multi-instance support (2E1C scenario).

"""Control-plane primitives for edge-cloud collaborative inference."""

from vllm_ascend.edge_cloud.prefix_protocol import (
    BLOCK_HASH_PREFIX,
    PROTOCOL_VERSION,
    TAIL_HASH_PREFIX,
    PrefixHasher,
    PrefixManifest,
    ProbeResult,
    UsageInfo,
)

__all__ = [
    "BLOCK_HASH_PREFIX",
    "PROTOCOL_VERSION",
    "TAIL_HASH_PREFIX",
    "PrefixHasher",
    "PrefixManifest",
    "ProbeResult",
    "UsageInfo",
]
