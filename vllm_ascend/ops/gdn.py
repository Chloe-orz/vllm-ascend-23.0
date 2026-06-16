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
#

import torch
from einops import rearrange
from vllm.distributed import get_pcp_group
from vllm.forward_context import get_forward_context
from vllm.model_executor.layers.fla.ops.l2norm import l2norm_fwd
from vllm.model_executor.layers.mamba.gdn.base import GatedDeltaNetAttention
from vllm.model_executor.layers.mamba.mamba_utils import MambaStateShapeCalculator
from vllm.triton_utils import triton
from vllm.v1.attention.backend import AttentionBackend, AttentionMetadata  # type: ignore
from vllm.v1.attention.backends.gdn_attn import GDNAttentionMetadata
from vllm.v1.attention.backends.utils import PAD_SLOT_ID

from vllm_ascend.ascend_forward_context import _EXTRA_CTX
from vllm_ascend.attention.utils import maybe_save_kv_layer_to_connector
from vllm_ascend.compilation.acl_graph import (
    get_draft_graph_params,
    get_graph_params,
)
from vllm_ascend.ops.triton.fla.chunk import chunk_gated_delta_rule
from vllm_ascend.ops.triton.fla.fused_qkvzba_split_reshape import fused_qkvzba_split_reshape_cat
from vllm_ascend.ops.triton.fla.utils import clear_ssm_states
from vllm_ascend.ops.triton.fused_gdn_gating import fused_gdn_gating_patch
from vllm_ascend.ops.triton.mamba.causal_conv1d import causal_conv1d_fn
from vllm_ascend.utils import vllm_version_is, weak_ref_tensors


def to_int64_tuple(tensor: torch.Tensor) -> tuple[int, ...]:
    tensor = tensor.to(torch.int64)
    if tensor.dim() == 0:
        return (tensor.item(),)
    return tuple(tensor.tolist())


def _check_and_get_host_args(attn_metadata, field_name: str, sub_field_name: str):
    if (fallback_meta := getattr(attn_metadata, field_name, None)) is None:
        raise RuntimeError(
            f"Expected attn_metadata.{field_name}.{sub_field_name} for patched GDN non-spec prefill path."
        )
    return fallback_meta


def get_non_spec_causal_conv1d_host_args(attn_metadata) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    fallback_meta = _check_and_get_host_args(attn_metadata, "non_spec_prefill_fallback_meta", "causal_conv1d")
    causal_conv1d_meta = fallback_meta.causal_conv1d
    return (
        to_int64_tuple(causal_conv1d_meta.query_start_loc_cpu),
        to_int64_tuple(causal_conv1d_meta.cache_indices_cpu),
        to_int64_tuple(causal_conv1d_meta.has_initial_state_cpu),
    )


def _maybe_reset_initial_state_for_layer_slice(
    attn_metadata: GDNAttentionMetadata,
    initial_state_mode_opt: tuple[int, ...],
) -> tuple[int, ...]:
    """Reset initial_state_mode to all-zeros when conv_state may be polluted.

    In edge-cloud layer-sliced inference, a decode batch can be interleaved
    between two prefill slices.  The decode path (causal_conv1d_update_npu)
    writes conv_state in-place using a sliding-window format that differs
    from the format expected by npu_causal_conv1d_custom's InitRing (FN
    mode).  When the same conv_state slots are reused across requests, the
    prefill request's slots may contain stale data left by a prior decode,
    causing aclnnCausalConv1d EZ9999 if has_initial_state=True.

    We detect the layer-sliced continuation scenario via the
    ``_is_layer_slice_continuation`` flag that PassiveScheduler /
    model_runner sets on the attention metadata before dispatching a
    non-first prefill slice.  In that case we force initial_state_mode to
    all-zeros so the CANN kernel initialises the ring buffer from scratch
    rather than reading potentially-polluted conv_state data.

    This is safe because: in a layer-sliced prefill, each GDN layer in a
    non-first slice has never processed the current request before, so its
    conv_state for the current request's slots genuinely has no valid
    initial state — even though the request-level context_lens > 0 may
    suggest otherwise.
    """
    if not getattr(attn_metadata, "_is_layer_slice_continuation", False):
        return initial_state_mode_opt

    # Force all entries to 0: no sequence should read initial state from
    # conv_state in a layer-slice continuation, because this layer has
    # never seen this request before.
    return tuple(0 for _ in initial_state_mode_opt)


def get_non_spec_chunked_prefill_meta(attn_metadata):
    fallback_meta = _check_and_get_host_args(attn_metadata, "non_spec_prefill_fallback_meta", "chunk")
    return fallback_meta.chunk


def _clone_chunked_prefill_meta(meta):
    """Clone all device tensors inside GDNChunkedPrefillMetadata.

    The chunked prefill metadata is backed by a 2-slot pool that is
    round-robin allocated per build() call.  In layer-slice continuation,
    an interleaved decode batch can trigger another build() that
    overwrites the pool slot still referenced by the saved
    _layerwise_attn_metadata.  Cloning decouples the metadata from
    the shared pool buffers.
    """
    return type(meta)(
        chunk_indices_chunk64=meta.chunk_indices_chunk64.clone(),
        chunk_offsets_chunk64=meta.chunk_offsets_chunk64.clone(),
        update_chunk_offsets_chunk64=meta.update_chunk_offsets_chunk64.clone(),
        final_chunk_indices_chunk64=meta.final_chunk_indices_chunk64.clone(),
        chunk_indices_large_block=meta.chunk_indices_large_block.clone(),
        block_indices_cumsum=meta.block_indices_cumsum.clone(),
        _buffer_slot=None,  # decoupled from pool
    )


class AscendGatedDeltaNetAttention(GatedDeltaNetAttention):
    def _split_ba_for_tp(self, ba: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        if hasattr(self, "split_ba"):
            return self.split_ba(ba)
        return ba.chunk(2, dim=-1)

    def get_state_shape(
        self,
    ) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
        return MambaStateShapeCalculator.gated_delta_net_state_shape(
            self.tp_size,
            self.num_k_heads,
            self.num_v_heads,
            self.head_k_dim,
            self.head_v_dim,
            self.conv_kernel_size,
            self.num_spec,
        )

    def _warmup_prefill_kernels(self, qkv_or_qkvz: torch.Tensor, v_dim: int) -> None:
        return

    def _warmup_prefill_kernels_v0202(self, mixed_qkv: torch.Tensor) -> None:
        return

    def get_attn_backend(self) -> type[AttentionBackend]:
        return AscendGDNAttentionBackend

    def forward(
        self,
        hidden_states: torch.Tensor,
        output: torch.Tensor,
    ):
        """
        Forward pass with three parts:
        1. Input projection
        2. Core attention (custom op)
        3. Output projection
        """
        num_tokens = hidden_states.size(0)
        if hasattr(self, "in_proj_qkv"):
            mixed_qkv, _ = self.in_proj_qkv(hidden_states)
            ba, _ = self.in_proj_ba(hidden_states)
            z, _ = self.in_proj_z(hidden_states)
            z = z.reshape(z.size(0), -1, self.head_v_dim)
            if vllm_version_is("0.20.2"):
                b, a = ba.chunk(2, dim=-1)
            else:
                b, a = self.split_ba(ba)
            b = b.contiguous()
            a = a.contiguous()
        else:
            if not self.gqa_interleaved_layout:
                mixed_qkvz, _ = self.in_proj_qkvz(hidden_states)
                num_tokens = mixed_qkvz.size(0)
                qkv_size = (self.key_dim * 2 + self.value_dim) // self.tp_size
                z_size = self.value_dim // self.tp_size
                mixed_qkv, z = mixed_qkvz.split([qkv_size, z_size], dim=-1)
                z = z.reshape(z.size(0), -1, self.head_v_dim)
                ba, _ = self.in_proj_ba(hidden_states)
                if vllm_version_is("0.20.2"):
                    b, a = ba.chunk(2, dim=-1)
                else:
                    b, a = self.split_ba(ba)

                b = b.contiguous()
                a = a.contiguous()
            else:
                projected_states_qkvz, _ = self.in_proj_qkvz(hidden_states)
                projected_states_ba, _ = self.in_proj_ba(hidden_states)
                num_tokens = projected_states_qkvz.size(0)

                mixed_qkv, z, b, a = fused_qkvzba_split_reshape_cat(
                    projected_states_qkvz,
                    projected_states_ba,
                    triton.cdiv(self.num_k_heads, self.tp_size),
                    triton.cdiv(self.num_v_heads, self.tp_size),
                    self.head_k_dim,
                    self.head_v_dim,
                )

        # ============================================================
        # Part 2: Core Attention (Custom Op)
        # ============================================================
        # Note: we should not use torch.empty here like other attention backends,
        # see discussions in https://github.com/vllm-project/vllm/pull/28182
        core_attn_out = torch.zeros(
            (num_tokens, self.num_v_heads // self.tp_size, self.head_v_dim),
            dtype=hidden_states.dtype,
            device=hidden_states.device,
        )

        torch.ops.vllm.qwen_gdn_attention_core(
            mixed_qkv,
            b,
            a,
            core_attn_out,
            self.prefix,
            False,
        )

        # ============================================================
        # Part 3: Output Projection
        # ============================================================
        maybe_save_kv_layer_to_connector("", [])
        z_shape_og = z.shape
        # Reshape input data into 2D tensor
        core_attn_out = core_attn_out.reshape(-1, core_attn_out.shape[-1])
        z = z.reshape(-1, z.shape[-1])
        core_attn_out = self.norm(core_attn_out, z)
        core_attn_out = core_attn_out.reshape(z_shape_og)
        core_attn_out = rearrange(core_attn_out, "... h d -> ... (h d)")
        output[:num_tokens], _ = self.out_proj(core_attn_out)

    def _forward_core(
        self,
        mixed_qkv: torch.Tensor,
        b: torch.Tensor,
        a: torch.Tensor,
        core_attn_out: torch.Tensor,
    ):
        """
        Core attention computation (called by custom op).
        """
        forward_context = get_forward_context()
        attn_metadata: AttentionMetadata = forward_context.attn_metadata

        if attn_metadata is None:
            # V1 profile run
            return

        assert isinstance(attn_metadata, dict)
        attn_metadata = attn_metadata[self.prefix]
        assert isinstance(attn_metadata, GDNAttentionMetadata)
        has_initial_state = attn_metadata.has_initial_state
        # Edge-cloud layer-sliced inference: when this is a non-first slice
        # continuation, conv_state and ssm_state for this layer have never
        # been populated by the current request.  Force has_initial_state
        # to an all-False tensor so that both the causal_conv1d and
        # recurrent attention kernels start from a clean zero state instead
        # of reading stale data left by a prior decode that was interleaved
        # between slices.
        _is_continuation = getattr(
            attn_metadata, "_is_layer_slice_continuation", False
        )
        if _is_continuation:
            if has_initial_state is not None:
                has_initial_state = torch.zeros_like(has_initial_state)
        spec_query_start_loc = attn_metadata.spec_query_start_loc
        non_spec_query_start_loc = attn_metadata.non_spec_query_start_loc
        spec_sequence_masks = attn_metadata.spec_sequence_masks
        spec_token_indx = attn_metadata.spec_token_indx
        non_spec_token_indx = attn_metadata.non_spec_token_indx
        spec_state_indices_tensor = attn_metadata.spec_state_indices_tensor  # noqa: E501
        non_spec_state_indices_tensor = attn_metadata.non_spec_state_indices_tensor  # noqa: E501

        # [ROOT-CAUSE-2 VERIFY] In layer-slice continuation, the
        # decode batch interleaved between slices rebuilds
        # common_attn_metadata and overwrites shared device buffers
        # (query_start_loc, state_indices, etc.) in-place.  The
        # _layerwise_attn_metadata saved by slice 0 holds references
        # to these shared buffers, so by the time slice 1+ reads them,
        # they contain decode-length values instead of the original
        # prefill-length values.  This causes chunk_gated_delta_rule
        # to compute wrong output positions → MTE write out of range.
        #
        # The CPU-side query_start_loc was already cloned in
        # patch_gdn_attn.py:528, but the device-side tensors were not.
        # Clone all shared device tensors to decouple them from the
        # shared buffers when running a layer-slice continuation.
        if _is_continuation:
            if non_spec_query_start_loc is not None:
                non_spec_query_start_loc = non_spec_query_start_loc.clone()
            if spec_query_start_loc is not None:
                spec_query_start_loc = spec_query_start_loc.clone()
            if non_spec_state_indices_tensor is not None:
                non_spec_state_indices_tensor = (
                    non_spec_state_indices_tensor.clone()
                )
            if spec_state_indices_tensor is not None:
                spec_state_indices_tensor = spec_state_indices_tensor.clone()
            if spec_token_indx is not None:
                spec_token_indx = spec_token_indx.clone()
            if non_spec_token_indx is not None:
                non_spec_token_indx = non_spec_token_indx.clone()
        self_kv_cache = self.kv_cache
        ssm_state = self_kv_cache[1]
        num_actual_tokens = attn_metadata.num_actual_tokens

        mixed_qkv = mixed_qkv[:num_actual_tokens]
        b = b[:num_actual_tokens]
        a = a[:num_actual_tokens]

        # 1. Convolution sequence transformation
        conv_weights = self.conv1d.weight.view(self.conv1d.weight.size(0), self.conv1d.weight.size(2))
        if spec_sequence_masks is not None:
            if attn_metadata.num_prefills == 0 and attn_metadata.num_decodes == 0:
                mixed_qkv_spec = mixed_qkv
                mixed_qkv_non_spec = None
            else:
                mixed_qkv_spec = mixed_qkv.index_select(0, spec_token_indx)
                mixed_qkv_non_spec = mixed_qkv.index_select(0, non_spec_token_indx)
        else:
            mixed_qkv_spec = None
            mixed_qkv_non_spec = mixed_qkv

        # 1.1: Process the multi-query part
        if spec_sequence_masks is not None:
            conv_weights_T = conv_weights.transpose(0, 1)
            activation_num = 1 if self.activation else 0
            (spec_qsl_host, spec_ci_host, spec_nat_host) = get_spec_causal_conv1d_update_host_args(attn_metadata)
            # capturing branch for conv1d update
            if _EXTRA_CTX.capturing:
                stream = torch_npu.npu.current_stream()
                event = torch.npu.ExternalEvent()
                event.wait(stream)
                event.reset(stream)
                graph_params = get_graph_params() if not _EXTRA_CTX.is_draft_model else get_draft_graph_params()
                graph_params.conv1d_events[num_actual_tokens].append(event)

                output_spec = torch.empty_like(mixed_qkv_spec)
                # Query length per spec request during capture (= num_spec + 1).
                # Used during update to align host args to capture's x.shape[0],
                # avoiding tiling validation failure when runtime has fewer spec
                # sequences than capture-time.
                spec_q_per_seq = int(attn_metadata.spec_state_indices_tensor.size(-1))
                # Store parameter references (use weak_ref for tensors, save host variables as tuples directly)
                graph_params.conv1d_params[num_actual_tokens].append(
                    (
                        weak_ref_tensors(output_spec),
                        weak_ref_tensors(mixed_qkv_spec),
                        weak_ref_tensors(conv_weights_T),
                        weak_ref_tensors(self_kv_cache[0]),
                        self.conv1d.bias,
                        activation_num,
                        PAD_SLOT_ID,
                        1,  # run_mode
                        "spec",
                        self.prefix,
                        spec_qsl_host,
                        spec_ci_host,
                        spec_nat_host,
                        spec_q_per_seq,
                    )
                )

                torch.npu.graph_task_group_begin(stream)
                torch.ops._C_ascend.npu_causal_conv1d_custom(
                    output_spec,
                    mixed_qkv_spec,
                    conv_weights_T,
                    conv_state=self_kv_cache[0],
                    bias_opt=self.conv1d.bias,
                    query_start_loc_opt=spec_qsl_host,
                    cache_indices_opt=spec_ci_host,
                    initial_state_mode_opt=(),
                    num_accepted_tokens_opt=spec_nat_host,
                    activation_mode=activation_num,
                    pad_slot_id=PAD_SLOT_ID,
                    run_mode=1,
                )
                handle = torch.npu.graph_task_group_end(stream)
                graph_params.conv1d_handles[num_actual_tokens].append(handle)
                mixed_qkv_spec = output_spec
            else:
                # for enforce eager
                output_spec = torch.empty_like(mixed_qkv_spec)
                torch.ops._C_ascend.npu_causal_conv1d_custom(
                    output_spec,
                    mixed_qkv_spec,
                    conv_weights_T,
                    conv_state=self_kv_cache[0],
                    bias_opt=self.conv1d.bias,
                    query_start_loc_opt=spec_qsl_host,
                    cache_indices_opt=spec_ci_host,
                    initial_state_mode_opt=(),
                    num_accepted_tokens_opt=spec_nat_host,
                    activation_mode=activation_num,
                    pad_slot_id=PAD_SLOT_ID,
                    run_mode=1,
                )
                mixed_qkv_spec = output_spec

        # 1.2: Process the remaining part
        if attn_metadata.num_prefills > 0:
            if mixed_qkv_non_spec is not None:
                conv_weights_T = conv_weights.transpose(0, 1)
                activation_num = 1 if self.activation else 0
                (
                    query_start_loc_opt,
                    cache_indices_opt,
                    initial_state_mode_opt,
                ) = get_non_spec_causal_conv1d_host_args(attn_metadata)

                # Edge-cloud layer-sliced inference: when a decode batch is
                # interleaved between two prefill slices, the decode path
                # (causal_conv1d_update_npu) in-place updates conv_state for
                # the decode requests' slots via a sliding-window write-back.
                # The slots occupied by the current prefill request may overlap
                # with those previously used by completed decode requests that
                # have since been freed and reassigned.  As a result, the
                # conv_state data at the prefill slots can be "polluted" by
                # the decode's sliding-window format, which is incompatible
                # with the format expected by npu_causal_conv1d_custom's
                # InitRing (FN mode reads width-1 history columns from
                # conv_state at a fixed offset, whereas decode writes them
                # at a shifted offset).  When has_initial_state=True under
                # these conditions, the CANN kernel reads stale/misaligned
                # conv_state data and triggers aclnnCausalConv1d EZ9999.
                #
                # Fix: detect the layer-sliced continuation scenario (where
                # conv_state for this layer was potentially written by a
                # decode since the prefill metadata was built) and force
                # initial_state_mode to all-zeros so the kernel initialises
                # the ring buffer from scratch instead of reading the
                # polluted conv_state.
                initial_state_mode_opt = _maybe_reset_initial_state_for_layer_slice(
                    attn_metadata, initial_state_mode_opt
                )

                # [ROOT-CAUSE-1 VERIFY] In layer-slice continuation, the
                # decode batch interleaved between slices writes conv_state
                # in a sliding-window format that leaves stale ring-buffer
                # cursor / offset metadata.  Even with initial_state_mode=0
                # (don't read conv_state as initial state), the CANN kernel
                # may still use conv_state internal metadata to compute
                # write-back addresses, causing MTE write out-of-range.
                # Fix: explicitly zero out conv_state slots for the current
                # prefill requests so the kernel starts from a clean state.
                #
                # NOTE: we intentionally avoid .item() / stream-sync here
                # because a prior layer's AICore async error would surface
                # at the first sync point, masking the real error location.
                _is_continuation = getattr(
                    attn_metadata, "_is_layer_slice_continuation", False
                )
                if _is_continuation:
                    _conv_state_base = self_kv_cache[0]
                    for _slot_idx in cache_indices_opt:
                        if _slot_idx != PAD_SLOT_ID and _slot_idx < _conv_state_base.size(0):
                            _conv_state_base[_slot_idx].zero_()

                mixed_qkv_non_spec = torch.ops._C_ascend.npu_causal_conv1d_custom(
                    mixed_qkv_non_spec,
                    conv_weights_T,
                    conv_state=self_kv_cache[0],
                    bias_opt=self.conv1d.bias,
                    query_start_loc_opt=non_spec_qsl_host,
                    cache_indices_opt=non_spec_ci_host,
                    initial_state_mode_opt=(),
                    num_accepted_tokens_opt=[],
                    activation_mode=activation_num,
                    pad_slot_id=PAD_SLOT_ID,
                    run_mode=1,
                )
                handle = torch.npu.graph_task_group_end(stream)
                graph_params.conv1d_handles[num_actual_tokens].append(handle)
                mixed_qkv_non_spec = output_non_spec
            else:
                output_non_spec = torch.empty_like(mixed_qkv_non_spec)
                torch.ops._C_ascend.npu_causal_conv1d_custom(
                    output_non_spec,
                    mixed_qkv_non_spec,
                    conv_weights_T,
                    conv_state=self_kv_cache[0],
                    bias_opt=self.conv1d.bias,
                    query_start_loc_opt=to_int64_tuple(non_spec_query_start_loc[: num_actual_tokens + 1]),
                    cache_indices_opt=to_int64_tuple(non_spec_state_indices_tensor[:num_actual_tokens]),
                    initial_state_mode_opt=[],
                    num_accepted_tokens_opt=[],
                    activation_mode=activation_num,
                    pad_slot_id=PAD_SLOT_ID,
                    run_mode=1,
                )
                mixed_qkv_non_spec = output_non_spec
        else:
            mixed_qkv_non_spec = None

        query_spec, key_spec, value_spec = self.rearrange_mixed_qkv(mixed_qkv_spec)
        query_non_spec, key_non_spec, value_non_spec = self.rearrange_mixed_qkv(mixed_qkv_non_spec)

        # 2. Recurrent attention
        g, beta = DeviceOperator.fused_gdn_gating(self.A_log, a, b, self.dt_bias)
        if spec_sequence_masks is not None:
            if attn_metadata.num_prefills == 0 and attn_metadata.num_decodes == 0:
                g_spec = g
                beta_spec = beta
                g_non_spec = None
                beta_non_spec = None
            else:
                g_spec = g.index_select(1, spec_token_indx)
                beta_spec = beta.index_select(1, spec_token_indx)
                g_non_spec = g.index_select(1, non_spec_token_indx)
                beta_non_spec = beta.index_select(1, non_spec_token_indx)
        else:
            g_spec = None
            beta_spec = None
            g_non_spec = g
            beta_non_spec = beta

        split_non_spec = (
            spec_sequence_masks is None and attn_metadata.num_prefills > 0 and attn_metadata.num_decodes > 0
        )
        num_decode_tokens = attn_metadata.num_decode_tokens

        # 2.1: Process the multi-query part
        if spec_sequence_masks is not None:
            actual_seq_lengths = attn_metadata.spec_decode_metadata.actual_seq_lengths
            query_spec = l2norm_fwd(query_spec)
            key_spec = l2norm_fwd(key_spec)
            # Dispatches to the vllm-ascend AscendC custom operator
            # (csrc/recurrent_gated_delta_rule), NOT the built-in CANN operator.
            # The custom op extends dtype support (e.g. float32 state) and is
            # loaded at runtime via ASCEND_CUSTOM_OPP_PATH.
            core_attn_out_spec = torch.ops._C_ascend.npu_recurrent_gated_delta_rule(
                query=query_spec.squeeze(0),
                key=key_spec.squeeze(0),
                value=value_spec.squeeze(0),
                g=g_spec.squeeze(0),
                beta=beta_spec.squeeze(0),
                state=ssm_state,
                scale=key_spec.shape[-1] ** -0.5,
                actual_seq_lengths=actual_seq_lengths,
                ssm_state_indices=spec_state_indices_tensor.flatten(),
                num_accepted_tokens=spec_causal_conv1d_meta.num_accepted_tokens.to(torch.int32),
            ).unsqueeze(0)
        else:
            core_attn_out_spec, last_recurrent_state = None, None

        # 2.2: Process non-spec-decode part in mixed non-spec batches
        if split_non_spec:
            assert mixed_qkv_non_spec is not None
            assert g_non_spec is not None
            assert beta_non_spec is not None
            query_decode, key_decode, value_decode = self.rearrange_mixed_qkv(mixed_qkv_non_spec[:num_decode_tokens])
            actual_seq_lengths = attn_metadata.non_spec_decode_metadata.actual_seq_lengths
            query_decode = l2norm_fwd(query_decode)
            key_decode = l2norm_fwd(key_decode)
            core_attn_out_decode = torch.ops._C_ascend.npu_recurrent_gated_delta_rule(
                query=query_decode.squeeze(0),
                key=key_decode.squeeze(0),
                value=value_decode.squeeze(0),
                g=g_non_spec[:, :num_decode_tokens].squeeze(0),
                beta=beta_non_spec[:, :num_decode_tokens].squeeze(0),
                state=ssm_state,
                scale=key_decode.shape[-1] ** -0.5,
                actual_seq_lengths=actual_seq_lengths,
                ssm_state_indices=non_spec_state_indices_tensor[: attn_metadata.num_decodes],
            ).unsqueeze(0)
        else:
            core_attn_out_decode = None

        # 2.3: Process the remaining part
        if attn_metadata.num_prefills > 0:
            initial_state = ssm_state[non_spec_state_indices_tensor].transpose(-1, -2).contiguous()
            clear_ssm_states(initial_state, has_initial_state)
            _prebuilt_meta = get_non_spec_chunked_prefill_meta(attn_metadata)
            # [ROOT-CAUSE-2 VERIFY] Clone pooled device tensors that may
            # have been overwritten by an interleaved decode batch.
            if _is_continuation:
                _prebuilt_meta = _clone_chunked_prefill_meta(_prebuilt_meta)
            (core_attn_out_non_spec, last_recurrent_state) = chunk_gated_delta_rule(
                q=query_non_spec,
                k=key_non_spec,
                v=value_non_spec,
                g=g_non_spec,
                beta=beta_non_spec,
                initial_state=initial_state,
                output_final_state=True,
                cu_seqlens=non_spec_query_start_loc,
                prebuilt_meta=_prebuilt_meta,
                head_first=False,
                use_qk_l2norm_in_kernel=True,
            )
            ssm_state[non_spec_state_indices_tensor] = (
                last_recurrent_state.transpose(-1, -2).contiguous().to(ssm_state.dtype)
            )
        elif attn_metadata.num_decodes > 0:
            actual_seq_lengths = attn_metadata.non_spec_decode_metadata.actual_seq_lengths
            query_non_spec = l2norm_fwd(query_non_spec)
            key_non_spec = l2norm_fwd(key_non_spec)
            # Dispatches to the vllm-ascend AscendC custom operator
            # (csrc/recurrent_gated_delta_rule), NOT the built-in CANN operator.
            core_attn_out_non_spec = torch.ops._C_ascend.npu_recurrent_gated_delta_rule(
                query=query_non_spec.squeeze(0),
                key=key_non_spec.squeeze(0),
                value=value_non_spec.squeeze(0),
                g=g_non_spec.squeeze(0) if g_non_spec is not None else g_non_spec,
                beta=beta_non_spec.squeeze(0) if beta_non_spec is not None else beta_non_spec,
                state=ssm_state,
                scale=key_non_spec.shape[-1] ** -0.5,
                actual_seq_lengths=actual_seq_lengths,
                ssm_state_indices=non_spec_state_indices_tensor,
            ).unsqueeze(0)
        else:
            core_attn_out_non_spec, last_recurrent_state = None, None

        # 3. Merge core attention output
        if spec_sequence_masks is not None and core_attn_out_non_spec is not None:
            merged_out = torch.empty(
                (1, num_actual_tokens, *core_attn_out_spec.shape[2:]),
                dtype=core_attn_out_non_spec.dtype,
                device=core_attn_out_non_spec.device,
            )
            merged_out.index_copy_(1, spec_token_indx, core_attn_out_spec)
            merged_out.index_copy_(1, non_spec_token_indx, core_attn_out_non_spec)
            core_attn_out[:num_actual_tokens] = merged_out.squeeze(0)
        elif spec_sequence_masks is not None:
            core_attn_out[:num_actual_tokens] = core_attn_out_spec.squeeze(0)
        else:
            core_attn_out[:num_actual_tokens] = core_attn_out_non_spec.squeeze(0)
