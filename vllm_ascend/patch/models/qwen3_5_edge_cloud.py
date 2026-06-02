#
# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
# This file is a part of the vllm-ascend project.
#
# Licensed under the Apache License, Version 2.0 (the "License");
#

from vllm.logger import logger
from itertools import islice
from typing import Any

import torch
from vllm.distributed.parallel_state import get_pp_group
from vllm.model_executor.models.qwen3_5 import (
    Qwen3_5ForCausalLM,
    Qwen3_5ForCausalLMBase,
    Qwen3_5ForConditionalGeneration,
    Qwen3_5Model,
    Qwen3_5MoeForCausalLM,
    Qwen3_5MoeForConditionalGeneration,
)
from vllm.sequence import IntermediateTensors

# [DIAG] 请求计数器，仅用于首/次请求对比，不参与计算图
_seg_call_count = 0


def _forward_edge_cloud_segment_qwen3_5(
    self: Qwen3_5Model,
    start_layer: int,
    end_layer: int,
    input_ids: torch.Tensor | None,
    positions: torch.Tensor,
    intermediate_tensors: IntermediateTensors | None = None,
    inputs_embeds: torch.Tensor | None = None,
    is_first_segment: bool | None = None,
    is_last_segment: bool | None = None,
    **extra_layer_kwargs: Any,
) -> torch.Tensor | IntermediateTensors:
    num_layers = len(self.layers)
    assert 0 <= start_layer <= end_layer <= num_layers, (
        f"Invalid segment range [{start_layer}, {end_layer}) for {num_layers} layers"
    )

    if is_first_segment is None:
        is_first_segment = start_layer == 0 and get_pp_group().is_first_rank
    if is_last_segment is None:
        is_last_segment = end_layer == num_layers and get_pp_group().is_last_rank

    # [DIAG] 仅在非图捕获、非 profile 时记录 seg_a 关键状态，
    # 避免与 ACL 计算图冲突。记录首/次请求差异用于排查。
    if is_first_segment:
        from vllm_ascend.ascend_forward_context import _EXTRA_CTX

        if not _EXTRA_CTX.capturing and not getattr(_EXTRA_CTX, "in_profile_run", False):
            global _seg_call_count
            _seg_call_count += 1
            logger.info(
                "[EdgeCloud seg_a DIAG] call=%d start=%d end=%d "
                "input_ids_shape=%s positions[:5]=%s positions[-5:]=%s "
                "is_first_layer=%s layer_idx=%s",
                _seg_call_count, start_layer, end_layer,
                tuple(input_ids.shape) if input_ids is not None else None,
                positions[:5].tolist() if positions is not None else None,
                positions[-5:].tolist() if positions is not None else None,
                getattr(_EXTRA_CTX, "is_first_layer", None),
                _EXTRA_CTX.layer_idx,
            )

        if inputs_embeds is not None:
            hidden_states = inputs_embeds
        else:
            hidden_states = self.embed_input_ids(input_ids)

        if not _EXTRA_CTX.capturing and not getattr(_EXTRA_CTX, "in_profile_run", False):
            logger.info(
                "[EdgeCloud seg_a DIAG] call=%d after_embed "
                "hidden_mean=%.6f hidden_std=%.6f nan=%d inf=%d",
                _seg_call_count,
                hidden_states.float().mean().item(),
                hidden_states.float().std().item(),
                torch.isnan(hidden_states).sum().item(),
                torch.isinf(hidden_states).sum().item(),
            )

        residual = None
    else:
        assert intermediate_tensors is not None, (
            "intermediate_tensors is None in edge-cloud segment; "
            "check that all TP ranks receive tensors correctly."
        )
        hidden_states = intermediate_tensors["hidden_states"]
        residual = intermediate_tensors["residual"]

    for layer_idx, layer in enumerate(
        islice(self.layers, start_layer, end_layer), start=start_layer
    ):
        # [DIAG] 对 seg_a 的首层，使用 forward hook 捕获子模块中间输出
        _hooks = []
        _hook_stats = {}
        if is_first_segment and layer_idx == start_layer:
            from vllm_ascend.ascend_forward_context import _EXTRA_CTX

            if not _EXTRA_CTX.capturing and not getattr(_EXTRA_CTX, "in_profile_run", False):
                def _make_hook(name):
                    def _hook(_module, _args, _kwargs, output):
                        out = output[0] if isinstance(output, tuple) else output
                        if isinstance(out, torch.Tensor):
                            _hook_stats[name] = (
                                out.float().mean().item(),
                                out.float().std().item(),
                                torch.isnan(out).sum().item(),
                                torch.isinf(out).sum().item(),
                            )
                        # 同时捕获 residual（元组第二个元素）
                        if isinstance(output, tuple) and len(output) > 1:
                            res = output[1]
                            if isinstance(res, torch.Tensor):
                                _hook_stats[name + "_residual"] = (
                                    res.float().mean().item(),
                                    res.float().std().item(),
                                    torch.isnan(res).sum().item(),
                                    torch.isinf(res).sum().item(),
                                )
                    return _hook

                # 注意：self_attn.forward() 无返回值（原地写入 output），
                # 故 hook self_attn 内部实际返回 tensor 的子模块：
                #   qkv_proj → QKV 投影输出
                #   o_proj   → 注意力输出（QKV_proj → Q/K_norm → RoPE → Attn → O_proj）
                for sub_name, sub_mod in layer.named_modules():
                    if sub_name in (
                        "input_layernorm",
                        "self_attn.qkv_proj",
                        "self_attn.o_proj",
                        "post_attention_layernorm",
                        "mlp",
                    ):
                        h = sub_mod.register_forward_hook(_make_hook(sub_name), with_kwargs=True)
                        _hooks.append(h)

        hidden_states, residual = layer(
            hidden_states=hidden_states,
            residual=residual,
            positions=positions,
            **extra_layer_kwargs,
        )

        for h in _hooks:
            h.remove()

        # 记录首层各子模块的中间状态
        if is_first_segment and layer_idx == start_layer:
            from vllm_ascend.ascend_forward_context import _EXTRA_CTX

            if not _EXTRA_CTX.capturing and not getattr(_EXTRA_CTX, "in_profile_run", False):
                logger.info(
                    "[EdgeCloud seg_a DIAG] call=%d after_layer=%d "
                    "hidden_mean=%.6f hidden_std=%.6f nan=%d inf=%d "
                    "residual_mean=%.6f residual_std=%.6f",
                    _seg_call_count, layer_idx,
                    hidden_states.float().mean().item(),
                    hidden_states.float().std().item(),
                    torch.isnan(hidden_states).sum().item(),
                    torch.isinf(hidden_states).sum().item(),
                    residual.float().mean().item() if residual is not None else -1.0,
                    residual.float().std().item() if residual is not None else -1.0,
                )
                for name, (m, s, n, inf) in sorted(_hook_stats.items()):
                    logger.info(
                        "[EdgeCloud seg_a DIAG] call=%d %s "
                        "mean=%.6f std=%.6f nan=%d inf=%d",
                        _seg_call_count, name, m, s, n, inf,
                    )

    if not is_last_segment:
        if residual is None:
            residual = torch.zeros_like(hidden_states)
        return IntermediateTensors(
            {"hidden_states": hidden_states, "residual": residual}
        )

    hidden_states, _ = self.norm(hidden_states, residual)
    return hidden_states


def _qwen3_5_lm_forward_edge_cloud_segment(
    self: Qwen3_5ForCausalLMBase,
    start_layer: int,
    end_layer: int,
    input_ids: torch.Tensor | None,
    positions: torch.Tensor,
    intermediate_tensors: IntermediateTensors | None = None,
    inputs_embeds: torch.Tensor | None = None,
    **extra_layer_kwargs: Any,
) -> torch.Tensor | IntermediateTensors:
    return self.model.forward_edge_cloud_segment(
        start_layer,
        end_layer,
        input_ids,
        positions,
        intermediate_tensors,
        inputs_embeds,
        **extra_layer_kwargs,
    )


def _qwen3_5_cond_forward_edge_cloud_segment(
    self: Qwen3_5ForConditionalGeneration,
    start_layer: int,
    end_layer: int,
    input_ids: torch.Tensor | None,
    positions: torch.Tensor,
    intermediate_tensors: IntermediateTensors | None = None,
    inputs_embeds: torch.Tensor | None = None,
    **extra_layer_kwargs: Any,
) -> torch.Tensor | IntermediateTensors:
    return self.language_model.forward_edge_cloud_segment(
        start_layer,
        end_layer,
        input_ids,
        positions,
        intermediate_tensors,
        inputs_embeds,
        **extra_layer_kwargs,
    )


Qwen3_5Model.forward_edge_cloud_segment = _forward_edge_cloud_segment_qwen3_5
Qwen3_5ForCausalLMBase.forward_edge_cloud_segment = (
    _qwen3_5_lm_forward_edge_cloud_segment
)
Qwen3_5ForCausalLM.forward_edge_cloud_segment = _qwen3_5_lm_forward_edge_cloud_segment
Qwen3_5MoeForCausalLM.forward_edge_cloud_segment = (
    _qwen3_5_lm_forward_edge_cloud_segment
)
Qwen3_5ForConditionalGeneration.forward_edge_cloud_segment = (
    _qwen3_5_cond_forward_edge_cloud_segment
)
Qwen3_5MoeForConditionalGeneration.forward_edge_cloud_segment = (
    _qwen3_5_cond_forward_edge_cloud_segment
)
