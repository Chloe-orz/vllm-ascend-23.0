#
# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
# This file is a part of the vllm-ascend project.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn
from vllm.logger import logger
from vllm.model_executor.models.utils import PPMissingLayer


@dataclass
class EdgeCloudLayerPlan:
    """Defines the layer sharding strategy for edge-cloud collaborative inference.

    Args:
        role: "edge" or "cloud"
        total_layers: Total number of transformer layers in the model.
        k: Number of head/tail layers kept on Edge side. Can be:
           - int: symmetric (head_k == tail_k)
           - list/tuple of 2 ints: asymmetric [head_k, tail_k]
    """

    role: str
    total_layers: int
    k: int | list[int] | tuple[int, int] = 1

    def __post_init__(self):
        if isinstance(self.k, (list, tuple)) and len(self.k) == 2:
            self.head_k = int(self.k[0])
            self.tail_k = int(self.k[1])
        else:
            self.head_k = self.tail_k = int(self.k)

    def get_local_layers(self) -> set[int]:
        """Return the set of layer indices that should be kept on this node."""
        if self.role == "edge":
            return set(range(self.head_k)) | set(
                range(self.total_layers - self.tail_k, self.total_layers)
            )
        else:
            return set(range(self.head_k, self.total_layers - self.tail_k))

    def get_released_layers(self) -> set[int]:
        """Return the set of layer indices that can be skipped on this node."""
        all_layers = set(range(self.total_layers))
        return all_layers - self.get_local_layers()

    def validate(self):
        """Validate that the layer plan covers all layers without overlap."""
        edge_layers = (
            self.get_local_layers()
            if self.role == "edge"
            else set(range(self.head_k))
            | set(range(self.total_layers - self.tail_k, self.total_layers))
        )
        cloud_layers = (
            self.get_local_layers()
            if self.role == "cloud"
            else set(range(self.head_k, self.total_layers - self.tail_k))
        )
        assert (
            edge_layers | cloud_layers == set(range(self.total_layers))
        ), "Edge and Cloud layers must cover all layers"
        assert (
            edge_layers & cloud_layers == set()
        ), "Edge and Cloud layers must not overlap"


class LayerShardLoader:
    """Layer-wise weight sharding loader (V3 load-time pruning version).

    Core responsibility:
      1. apply_sharding(): Before load_weights(), replace non-local layers with
         PPMissingLayer so that AutoWeightsLoader automatically skips them.

    Note: V3 no longer needs release_layer_weights() because weights are never
    loaded in the first place. Also, since edge-cloud segmented forward uses
    islice to only iterate real layers, placeholder layers are never actually
    called — no need to convert PPMissingLayer to EdgeCloudMissingLayer.
    """

    @staticmethod
    def release_layer_weights(layer: nn.Module) -> None:
        """(v2 legacy, no longer called in V3) Release parameters and buffers of a single layer."""
        # Kept for backward compatibility with any v2 references.
        for param in layer.parameters(recurse=False):
            if param is not None and param.data is not None:
                param.data = torch.empty(0, device=param.device, dtype=param.dtype)
        for buf in layer.buffers(recurse=False):
            if buf is not None and buf.data is not None:
                buf.data = torch.empty(0, device=buf.device, dtype=buf.dtype)

    @classmethod
    def apply_sharding(
        cls,
        model: nn.Module,
        layer_plan: EdgeCloudLayerPlan,
        compilation_config: Any = None,
    ) -> None:
        """Apply layer sharding to the model (call before load_weights).

        Steps:
          1. Replace non-local Transformer layers with PPMissingLayer.
             AutoWeightsLoader._load_module() returns immediately on PPMissingLayer.
          2. On Cloud side, additionally replace embed_tokens / norm / lm_head
             with PPMissingLayer so their weights are also skipped.
          3. On Edge side, keep these modules for Embedding and Norm/LM Head computation.
          4. Clean up stale entries in compilation_config to prevent MoE custom
             ops from resolving replaced layers via static_forward_context.
        """
        if not hasattr(model, "model") or not hasattr(model.model, "layers"):
            raise ValueError(
                "Model must have 'model.layers' attribute for layer sharding. "
                f"Got model type: {type(model).__name__}"
            )

        num_layers = len(model.model.layers)
        local_layers = layer_plan.get_local_layers()

        # 1. Replace Transformer layers
        converted = 0
        for i in range(num_layers):
            if i not in local_layers:
                old_layer = model.model.layers[i]
                if isinstance(old_layer, PPMissingLayer):
                    continue
                model.model.layers[i] = PPMissingLayer()
                del old_layer
                converted += 1

        # 2. Cloud side: skip embed_tokens / norm / lm_head weight loading
        if layer_plan.role == "cloud":
            for module_name in ("embed_tokens", "norm"):
                module = getattr(model.model, module_name, None)
                if module is not None and not isinstance(module, PPMissingLayer):
                    setattr(model.model, module_name, PPMissingLayer())
            if (
                hasattr(model, "lm_head")
                and model.lm_head is not None
                and not isinstance(model.lm_head, PPMissingLayer)
            ):
                model.lm_head = PPMissingLayer()

        # 3. Clean up compilation_config stale references
        if compilation_config is not None:
            cls._clean_compilation_config(model, compilation_config)

        logger.info(
            "[LayerShardLoader] Role=%s, head_k=%d, tail_k=%d, "
            "kept_layers=%s, skipped_layers=%s, converted=%d",
            layer_plan.role,
            layer_plan.head_k,
            layer_plan.tail_k,
            sorted(local_layers),
            sorted(layer_plan.get_released_layers()),
            converted,
        )
        cls.validate_sharding(model, layer_plan)

    @classmethod
    def _clean_compilation_config(
        cls, model: nn.Module, compilation_config: Any
    ) -> None:
        """Remove stale MoE layer entries from compilation_config after sharding.

        FusedMoE.__init__ registers itself to ``static_forward_context`` and
        ``static_all_moe_layers``.  After apply_sharding replaces non-local
        layers with ``PPMissingLayer``, those cached module instances become
        stale.  The MoE custom op (when ``_USE_LAYERNAME=False``) resolves
        layers by indexing ``static_all_moe_layers`` and can accidentally pick
        up a stale instance, causing ``AttributeError`` on missing post-load
        attributes such as ``w13_weight_scale_fp32``.
        """
        # Build a set of module ids currently present in the model tree.
        # apply_sharding replaces non-local layers with PPMissingLayer, so
        # stale instances (old layers) are no longer referenced by the model.
        # We use id() instead of path matching because some modules register
        # themselves to static_forward_context with a key that does not match
        # their path in named_modules() (e.g. DSAAttention).
        model_module_ids = {id(m) for _, m in model.named_modules()}

        removed_prefixes: list[str] = []
        for prefix in list(compilation_config.static_forward_context.keys()):
            module = compilation_config.static_forward_context[prefix]
            current_type = module.__class__.__name__
            # Remove only if the instance is no longer in the model tree.
            should_remove = id(module) not in model_module_ids
            # Guard: never remove attention modules because some custom
            # attentions (e.g. DSAAttention) register with a key that does
            # not match their path in named_modules(), so id() comparison
            # can accidentally remove local attention layers.  Stale attention
            # entries do not cause AttributeError (only MoE does), so keeping
            # them is harmless -- get_kv_cache_spec() will filter local layers
            # by checking the real model anyway.
            if should_remove:
                from vllm.model_executor.layers.attention_layer_base import (
                    AttentionLayerBase,
                )

                if isinstance(module, AttentionLayerBase):
                    should_remove = False
                else:
                    try:
                        from vllm_ascend.ops.dsa import DSAAttention

                        if isinstance(module, DSAAttention):
                            should_remove = False
                    except ImportError:
                        pass
            logger.info(
                "[LayerShardLoader][Clean] prefix=%s, current_type=%s, "
                "in_model=%s, remove=%s",
                prefix,
                current_type,
                not should_remove,
                should_remove,
            )
            if should_remove:
                del compilation_config.static_forward_context[prefix]
                removed_prefixes.append(prefix)

        if removed_prefixes:
            logger.info(
                "[LayerShardLoader] Removed %d stale entries from "
                "static_forward_context: %s",
                len(removed_prefixes),
                removed_prefixes,
            )
        else:
            logger.info(
                "[LayerShardLoader] No stale entries removed from static_forward_context."
            )

        # static_all_moe_layers is a plain list; modify in-place so that
        # existing references (e.g. in ForwardContext) see the update.
        original_all_moe = list(compilation_config.static_all_moe_layers)
        compilation_config.static_all_moe_layers[:] = [
            p for p in original_all_moe if p not in removed_prefixes
        ]
        removed_moe = len(original_all_moe) - len(
            compilation_config.static_all_moe_layers
        )
        if removed_moe:
            logger.info(
                "[LayerShardLoader] Removed %d stale entries from "
                "static_all_moe_layers. Remaining: %d",
                removed_moe,
                len(compilation_config.static_all_moe_layers),
            )

    @classmethod
    def validate_sharding(cls, model: nn.Module, layer_plan: EdgeCloudLayerPlan) -> None:
        """验证层裁剪是否正确应用，检测 make_layers() 遗留的 PPMissingLayer 冲突。"""
        num_layers = len(model.model.layers)
        local_layers = layer_plan.get_local_layers()
        conflict = False
        for i in range(num_layers):
            is_missing = isinstance(model.model.layers[i], PPMissingLayer)
            should_be_local = i in local_layers
            if is_missing and should_be_local:
                logger.critical(
                    "[LayerShardLoader] CONFLICT: Layer %d is PPMissingLayer but should be "
                    "LOCAL on %s side. This usually means make_layers() created placeholders "
                    "before apply_sharding due to pipeline_parallel_size > 1. "
                    "Runtime forward WILL FAIL.",
                    i, layer_plan.role,
                )
                conflict = True
            elif not is_missing and not should_be_local:
                logger.warning(
                    "[LayerShardLoader] Layer %d is REAL but should be MISSING on %s side. "
                    "Weights for this layer will still be loaded.",
                    i, layer_plan.role,
                )
                conflict = True
        if not conflict:
            logger.info(
                "[LayerShardLoader] Sharding validation PASSED for %s side.", layer_plan.role
            )


