# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
# SPDX-FileCopyrightText: Songlin Yang, Yu Zhang
#
# This file contains code copied from the flash-linear-attention project.
# The original source code was licensed under the MIT license and included
# the following copyright notice:
# Copyright (c) 2023-2025, Songlin Yang, Yu Zhang
# ruff: noqa: E501
# mypy: ignore-errors
import os
import warnings

import torch
from einops import rearrange
from vllm.distributed import get_pcp_group
from vllm.forward_context import get_forward_context
from vllm.logger import init_logger
from vllm.model_executor.layers.fla.ops.utils import SUPPRESS_LEVEL

from vllm_ascend.ops.gdn_attn_builder import _compact_empty_segments

from .chunk_delta_h import chunk_gated_delta_rule_fwd_h  # noqa: F401
from .chunk_delta_hupdate import chunk_gated_delta_rule_fwd_hupdate
from .chunk_o import chunk_fwd_o  # noqa: F401
from .chunk_scaled_dot_kkt import chunk_scaled_dot_kkt_fwd
from .cumsum import chunk_local_cumsum
from .l2norm import l2norm_fwd
from .solve_tril import solve_tril
from .utils import input_guard, prepare_final_chunk_indices
from .wy_fast import recompute_w_u_fwd


_chunk_probe_guard_used = False
logger = init_logger(__name__)


def _kkt_diag_enabled() -> bool:
    return os.environ.get("VLLM_ASCEND_GDN_KKT_DIAG", "").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _kkt_tensor_diag(name: str, tensor: torch.Tensor) -> str:
    if tensor is None:
        return f"{name}=None"
    try:
        storage_nbytes = tensor.untyped_storage().nbytes()
    except Exception:
        storage_nbytes = -1
    return (
        f"{name}:shape={tuple(tensor.shape)} stride={tuple(tensor.stride())} "
        f"dtype={tensor.dtype} data_ptr={tensor.data_ptr()} "
        f"storage_ptr={tensor.untyped_storage().data_ptr()} "
        f"storage_nbytes={storage_nbytes}"
    )


def _kkt_memory_diag() -> str:
    for backend_name in ("npu", "cuda"):
        backend = getattr(torch, backend_name, None)
        if backend is not None and hasattr(backend, "memory_allocated"):
            try:
                return (
                    f"{backend_name}_memory_allocated={backend.memory_allocated()} "
                    f"{backend_name}_memory_reserved={backend.memory_reserved()}"
                )
            except Exception:
                pass
    return "memory_stats=unavailable"


def _kkt_value_diag(name: str, tensor: torch.Tensor) -> str:
    if tensor is None:
        return f"{name}=None"
    try:
        values = tensor.detach().float()
        finite = torch.isfinite(values)
        finite_values = values[finite]
        abs_max = "nan" if finite_values.numel() == 0 else str(finite_values.abs().max().item())
        mean = "nan" if finite_values.numel() == 0 else str(finite_values.mean().item())
        return (f"{name}:all_finite={bool(finite.all().item())} "
                f"nan_count={int(torch.isnan(values).sum().item())} "
                f"inf_count={int(torch.isinf(values).sum().item())} "
                f"abs_max={abs_max} mean={mean}")
    except Exception as exc:
        return f"{name}:value_diag_error={type(exc).__name__}:{exc}"


def _kkt_per_head_value_diag(name: str, tensor: torch.Tensor) -> str:
    """Summarize [B, T, H, ...] values separately for every head."""
    if tensor is None or tensor.ndim < 3:
        return f"{name}_per_head=unavailable"
    try:
        values = tensor.detach().float().movedim(2, 0).flatten(1)
        nonfinite = (~torch.isfinite(values)).sum(dim=1)
        finite_abs = torch.where(torch.isfinite(values), values.abs(), 0)
        abs_max = finite_abs.amax(dim=1)
        return (
            f"{name}_head_abs_max={abs_max.tolist()} "
            f"{name}_head_nonfinite={nonfinite.tolist()}"
        )
    except Exception as exc:
        return f"{name}_per_head_diag_error={type(exc).__name__}:{exc}"


def _kkt_head_diag(
    q: torch.Tensor,
    k: torch.Tensor,
    v: torch.Tensor,
    beta: torch.Tensor,
    g: torch.Tensor,
) -> str:
    """Describe the value-head to key-head mapping used by the KKT kernel."""
    q_heads = q.shape[2]
    k_heads = k.shape[2]
    value_heads = v.shape[2]
    beta_heads = beta.shape[2]
    gate_heads = g.shape[2]
    divisible = k_heads > 0 and beta_heads % k_heads == 0
    group_size = beta_heads // k_heads if divisible else -1
    max_k_head = (
        (beta_heads - 1) // group_size
        if beta_heads > 0 and group_size > 0
        else -1
    )
    shapes_match = (
        q_heads == k_heads
        and value_heads == beta_heads == gate_heads
        and divisible
        and max_k_head < k_heads
    )
    return (
        f"head_mapping_status={'PASS' if shapes_match else 'MISMATCH'} "
        f"q_heads={q_heads} k_heads={k_heads} value_heads={value_heads} "
        f"beta_heads={beta_heads} gate_heads={gate_heads} "
        f"value_heads_per_k_head={group_size} max_k_head_index={max_k_head} "
        f"kkt_launch_heads={beta_heads}"
    )


def _allocate_chunk_probe_guard(
    q: torch.Tensor,
    k: torch.Tensor,
    v: torch.Tensor,
) -> torch.Tensor:
    """Reserve the workspace size that avoids the first-request KKT issue."""
    return q.new_empty(q.numel() + k.numel() + v.numel())


def chunk_gated_delta_rule_fwd(
    q: torch.Tensor,
    k: torch.Tensor,
    v: torch.Tensor,
    g: torch.Tensor,
    beta: torch.Tensor,
    scale: float,
    initial_state: torch.Tensor,
    output_final_state: bool,
    cu_seqlens: torch.LongTensor | None = None,
    prebuilt_meta=None,
):
    forward_context = get_forward_context()
    num_decodes = 0
    attn_metadata = forward_context.attn_metadata
    if attn_metadata is not None and isinstance(attn_metadata, dict):
        attn_metadata = next(iter(attn_metadata.values()), None)
    if attn_metadata is not None:
        num_decodes = attn_metadata.num_decodes
    chunk_size = 64
    block_indices_cumsum = None if prebuilt_meta is None else prebuilt_meta.block_indices_cumsum
    cu_seqlens_host = None if prebuilt_meta is None else prebuilt_meta.cu_seqlens_host
    chunk_indices_chunk64 = None if prebuilt_meta is None else prebuilt_meta.chunk_indices_chunk64
    chunk_indices_chunk64_host = None if prebuilt_meta is None else prebuilt_meta.chunk_indices_chunk64_host
    chunk_offsets_chunk64 = None if prebuilt_meta is None else prebuilt_meta.chunk_offsets_chunk64
    update_chunk_offsets_chunk64 = None if prebuilt_meta is None else prebuilt_meta.update_chunk_offsets_chunk64
    final_chunk_indices_chunk64 = None if prebuilt_meta is None else prebuilt_meta.final_chunk_indices_chunk64
    chunk_indices_large_block = None if prebuilt_meta is None else prebuilt_meta.chunk_indices_large_block
    g = chunk_local_cumsum(
        g,
        chunk_size=chunk_size,
        cu_seqlens=cu_seqlens,
        block_indices=block_indices_cumsum,
    )
    # obtain WY representation. u is actually the new v.
    A = chunk_scaled_dot_kkt_fwd(
        k=k,
        beta=beta,
        g_cumsum=g,
        cu_seqlens=cu_seqlens,
        chunk_indices=chunk_indices_chunk64,
        output_dtype=torch.float32,
    )
    if _kkt_diag_enabled():
        logger.warning(
            "[GDN-KKT-DIAG] stage=after_kkt %s %s",
            _kkt_value_diag("A", A),
            _kkt_per_head_value_diag("A", A),
        )
    A = solve_tril(
        A=A,
        cu_seqlens=cu_seqlens,
        chunk_indices_large_block=chunk_indices_large_block,
        chunk_indices_bt=chunk_indices_chunk64,
        output_dtype=k.dtype,
    )
    if _kkt_diag_enabled():
        logger.warning(
            "[GDN-KKT-DIAG] stage=after_solve %s %s",
            _kkt_value_diag("A", A),
            _kkt_per_head_value_diag("A", A),
        )
    w, u = recompute_w_u_fwd(
        k=k,
        v=v,
        beta=beta,
        A=A,
        g_cumsum=g,
        cu_seqlens=cu_seqlens,
        chunk_indices=chunk_indices_chunk64,
    )
    if _kkt_diag_enabled():
        logger.warning("[GDN-KKT-DIAG] stage=after_recompute %s %s",
                       _kkt_value_diag("w", w), _kkt_value_diag("u", u))

    k_ascendc = k.to(torch.bfloat16).transpose(1, 2).contiguous()
    w_ascendc = w.to(torch.bfloat16).transpose(1, 2).contiguous()
    u_ascendc = u.to(torch.bfloat16).transpose(1, 2).contiguous()
    g_ascendc = g.transpose(1, 2).contiguous()
    q_ascendc = q.to(torch.bfloat16).transpose(1, 2).contiguous()

    cu_seqlens = None if cu_seqlens is None else cu_seqlens.to(torch.int64)
    chunk_indices = None if chunk_indices_chunk64 is None else chunk_indices_chunk64.to(torch.int64)
    if cu_seqlens_host is None and cu_seqlens is not None:
        cu_seqlens_host = tuple(cu_seqlens.tolist())
    if chunk_indices_chunk64_host is None and chunk_indices is not None:
        chunk_indices_chunk64_host = tuple(chunk_indices.flatten().tolist())
    # Compact zero-length segments for the AscendC kernels (see
    # _compact_empty_segments).  chunk_indices_chunk64 is already compact-
    # ranked and is reused as-is; only cu_seqlens / initial_state need
    # compacting.
    if prebuilt_meta is not None and hasattr(prebuilt_meta, "keep_meta"):
        cu_seqlens_kern = cu_seqlens_host if prebuilt_meta.cu_seqlens_kern is None else prebuilt_meta.cu_seqlens_kern
        keep_meta = prebuilt_meta.keep_meta
        initial_state_kern = (
            initial_state[keep_meta] if initial_state is not None and keep_meta is not None else initial_state
        )
    else:
        cu_seqlens_kern, initial_state_kern, keep_meta = _compact_empty_segments(
            cu_seqlens_host,
            initial_state,
            device=initial_state.device if initial_state is not None else None,
        )
    h, v_new, final_state = torch.ops._C_ascend.chunk_gated_delta_rule_fwd_h(
        k_ascendc,
        w_ascendc,
        u_ascendc,
        g=g_ascendc,
        gk=None,
        initial_state=initial_state_kern,
        output_final_state=True,
        chunk_size=64,
        save_new_value=True,
        cu_seqlens=cu_seqlens_kern,
        chunk_indices=chunk_indices_chunk64_host,
        use_exp2=False,
        transpose_state_layout=False,
    )
    if _kkt_diag_enabled():
        logger.warning("[GDN-KKT-DIAG] stage=after_h %s %s",
                       _kkt_value_diag("v_new", v_new),
                       _kkt_value_diag("final_state", final_state))
    if keep_meta is not None:
        # Scatter the compacted final_state back to the original [N, H, K, V]
        # layout the PCP state recursion expects; empty segments keep their
        # initial state.
        _fs_full = initial_state.clone()
        _fs_full[keep_meta] = final_state
        final_state = _fs_full

    if get_pcp_group().world_size > 1:
        # When integrating mtp, since `mix_qkv` has been split, `num_decode`
        # cannot be directly obtained from the metadata and needs to be recalculated.
        actual_num_decodes = getattr(prebuilt_meta, "num_decodes", None)
        if actual_num_decodes is None:
            actual_num_decodes = num_decodes
        h_update = chunk_gated_delta_rule_fwd_hupdate(
            k=k,
            w=w,
            u=u,
            g=g,
            cu_seqlens=cu_seqlens,
            chunk_indices=chunk_indices_chunk64,
            chunk_offsets=chunk_offsets_chunk64,
            update_chunk_offsets=update_chunk_offsets_chunk64,
            num_decodes=actual_num_decodes,
        )
        all_final_state = get_pcp_group().all_gather(final_state.unsqueeze(0), 0)
        final_chunk_indices = final_chunk_indices_chunk64
        if final_chunk_indices is None:
            final_chunk_indices = prepare_final_chunk_indices(cu_seqlens, chunk_size)
        final_h_update = h_update[:, final_chunk_indices, :, :, :]
        all_final_h_update = get_pcp_group().all_gather(final_h_update, 0)

        updated_state = final_state.new_empty(get_pcp_group().world_size, *final_state.shape)
        updated_state[0, ...] = all_final_state[0]
        for i in range(1, get_pcp_group().world_size):
            # correct_i = all_final_state[i] + Phi_i * (correct_{i-1} - s0)
            updated_final_state = all_final_state[i] + torch.matmul(
                all_final_h_update[i, ...], updated_state[i - 1, ...] - initial_state
            )
            updated_state[i, ...] = updated_final_state

        final_state = updated_state[-1, ...]

        if get_pcp_group().rank_in_group == 0:
            updated_h_state = torch.zeros_like(final_state)
        else:
            updated_h_state = updated_state[get_pcp_group().rank_in_group - 1, ...]

        if get_pcp_group().rank_in_group > 0:
            rerun_initial_state = initial_state.clone()
            prefill_seq_offset = actual_num_decodes
            prefill_slice = slice(prefill_seq_offset, final_state.shape[0])
            rerun_initial_state[prefill_slice] = updated_h_state[prefill_slice]
            h, v_new, _ = chunk_gated_delta_rule_fwd_h(
                k=k,
                w=w,
                u=u,
                g=g,
                initial_state=rerun_initial_state,
                output_final_state=True,
                cu_seqlens=cu_seqlens,
                chunk_indices=chunk_indices_chunk64,
                chunk_offsets=chunk_offsets_chunk64,
            )
            h = h.transpose(1, 2).contiguous()
            v_new = v_new.transpose(1, 2).contiguous()

    o_ascendc = torch.ops._C_ascend.chunk_fwd_o(
        q_ascendc,
        k_ascendc,
        v_new,
        h,
        scale,
        g=g_ascendc,
        g_gamma=None,
        cu_seqlens=cu_seqlens_host,
        chunk_indices=chunk_indices_chunk64_host,
        chunk_size=64,
        transpose_state_layout=False,
    )

    o = o_ascendc.to(torch.bfloat16).transpose(1, 2).contiguous()
    v_new = v_new.to(torch.bfloat16).transpose(1, 2).contiguous()
    h = h.to(torch.bfloat16).transpose(1, 2).contiguous()

    if SUPPRESS_LEVEL < 3:
        return g, o, A, final_state, None, None, None
    elif SUPPRESS_LEVEL >= 3:
        return g, o, A, final_state, w, h, v_new


class ChunkGatedDeltaRuleFunction(torch.autograd.Function):
    @staticmethod
    @input_guard
    def forward(
        ctx,
        q: torch.Tensor,
        k: torch.Tensor,
        v: torch.Tensor,
        g: torch.Tensor,
        beta: torch.Tensor,
        scale: float,
        initial_state: torch.Tensor,
        output_final_state: bool,
        cu_seqlens: torch.LongTensor | None = None,
        prebuilt_meta=None,
        use_qk_l2norm_in_kernel: bool = False,
    ):
        if use_qk_l2norm_in_kernel:
            q = l2norm_fwd(q)
            k = l2norm_fwd(k)
        chunk_probe_guard = None
        global _chunk_probe_guard_used
        probe_enabled = (
            os.environ.get("VLLM_ASCEND_GDN_PREFILL_PROBE", "")
            .strip()
            .lower()
            == "alloc_chunk_after_l2norm"
        )
        if _kkt_diag_enabled():
            logger.warning(
                "[GDN-KKT-DIAG] probe_used=%s probe_enabled=%s device=%s %s %s %s %s %s %s %s",
                _chunk_probe_guard_used,
                probe_enabled,
                q.device,
                _kkt_memory_diag(),
                _kkt_tensor_diag("q", q),
                _kkt_tensor_diag("k", k),
                _kkt_tensor_diag("v", v),
                _kkt_tensor_diag("beta", beta),
                _kkt_tensor_diag("g", g),
                _kkt_head_diag(q, k, v, beta, g),
            )
        if (
            not _chunk_probe_guard_used
            and probe_enabled
        ):
            chunk_probe_guard = _allocate_chunk_probe_guard(q, k, v)
            _chunk_probe_guard_used = True
            if _kkt_diag_enabled():
                logger.warning(
                    "[GDN-KKT-DIAG] probe_allocated %s %s",
                    _kkt_tensor_diag("probe_guard", chunk_probe_guard),
                    _kkt_memory_diag(),
                )
        g, o, A, final_state, w, h, v_new = chunk_gated_delta_rule_fwd(
            q=q,
            k=k,
            v=v,
            g=g,
            beta=beta,
            scale=scale,
            initial_state=initial_state,
            output_final_state=output_final_state,
            cu_seqlens=cu_seqlens,
            prebuilt_meta=prebuilt_meta,
        )
        if _kkt_diag_enabled():
            logger.warning(
                "[GDN-KKT-DIAG] completed %s %s %s %s",
                _kkt_tensor_diag("A", A),
                _kkt_tensor_diag("final_state", final_state),
                _kkt_memory_diag(),
                "probe_released=True",
            )
        del chunk_probe_guard
        ctx.scale = scale
        ctx.use_qk_l2norm_in_kernel = use_qk_l2norm_in_kernel
        return o.to(q.dtype), final_state


@torch.compiler.disable
def chunk_gated_delta_rule(
    q: torch.Tensor,
    k: torch.Tensor,
    v: torch.Tensor,
    g: torch.Tensor,
    beta: torch.Tensor,
    scale: float = None,
    initial_state: torch.Tensor = None,
    output_final_state: bool = False,
    cu_seqlens: torch.LongTensor | None = None,
    prebuilt_meta=None,
    head_first: bool = False,
    use_qk_l2norm_in_kernel: bool = False,
    chunk_indices: torch.Tensor | None = None,
    chunk_offsets: torch.Tensor | None = None,
    core_attn_out: torch.Tensor | None = None,
):
    r"""
    Args:
        q (torch.Tensor):
            queries of shape `[B, T, H, K]` if `head_first=False` else `[B, H, T, K]`.
        k (torch.Tensor):
            keys of shape `[B, T, H, K]` if `head_first=False` else `[B, H, T, K]`.
        v (torch.Tensor):
            values of shape `[B, T, H, V]` if `head_first=False` else `[B, H, T, V]`.
        g (torch.Tensor):
            (forget) gating tensor (in log space!) of shape `[B, T, H]` if `head_first=False` else `[B, H, T]`.
        beta (torch.Tensor):
            betas of shape `[B, T, H]` if `head_first=False` else `[B, H, T]`.
        scale (Optional[int]):
            Scale factor for the RetNet attention scores.
            If not provided, it will default to `1 / sqrt(K)`. Default: `None`.
        initial_state (Optional[torch.Tensor]):
            Initial state of shape `[N, H, K, V]` for `N` input sequences.
            For equal-length input sequences, `N` equals the batch size `B`.
            Default: `None`.
        output_final_state (Optional[bool]):
            Whether to output the final state of shape `[N, H, K, V]`. Default: `False`.
        cu_seqlens (torch.LongTensor):
            Cumulative sequence lengths of shape `[N+1]` used for variable-length training,
            consistent with the FlashAttention API.
        head_first (Optional[bool]):
            Whether the inputs are in the head-first format, which is not supported for variable-length inputs.
            Default: `False`.

    Returns:
        o (torch.Tensor):
            Outputs of shape `[B, T, H, V]` if `head_first=False` else `[B, H, T, V]`.
        final_state (torch.Tensor):
            Final state of shape `[N, H, K, V]` if `output_final_state=True` else `None`.

    Examples::
        >>> import torch
        >>> import torch.nn.functional as F
        >>> from einops import rearrange
        >>> from fla.ops.gated_delta_rule import chunk_gated_delta_rule
        # inputs with equal lengths
        >>> B, T, H, K, V = 4, 2048, 4, 512, 512
        >>> q = torch.randn(B, T, H, K, dtype=torch.bfloat16, device='cuda')
        >>> k = F.normalize(torch.randn(B, T, H, K, dtype=torch.bfloat16, device='cuda'), p=2, dim=-1)
        >>> v = torch.randn(B, T, H, V, dtype=torch.bfloat16, device='cuda')
        >>> beta = torch.rand(B, T, H, dtype=torch.bfloat16, device='cuda').sigmoid()
        >>> g = F.logsigmoid(torch.rand(B, T, H, dtype=torch.bfloat16, device='cuda'))
        >>> h0 = torch.randn(B, H, K, V, dtype=torch.bfloat16, device='cuda')
        >>> o, ht = chunk_gated_delta_rule(
            q, k, v, g, beta,
            initial_state=h0,
            output_final_state=True
        )
        # for variable-length inputs, the batch size `B` is expected to be 1 and `cu_seqlens` is required
        >>> q, k, v, beta, g = map(lambda x: rearrange(x, 'b t ... -> 1 (b t) ...'), (q, k, v, beta, g))
        # for a batch with 4 sequences, `cu_seqlens` with 5 start/end positions are expected
        >>> cu_seqlens = q.new_tensor([0, 2048, 4096, 6144, 8192], dtype=torch.long)
        >>> o_var, ht_var = chunk_gated_delta_rule(
            q, k, v, g, beta,
            initial_state=h0,
            output_final_state=True,
            cu_seqlens=cu_seqlens
        )
    """
    assert q.dtype == k.dtype == v.dtype
    assert q.dtype != torch.float32, "ChunkGatedDeltaRuleFunction does not support float32. Please use bfloat16."
    assert len(beta.shape) == 3, "beta must be of shape [B, T, H] if head_first=False, or [B, H, T] otherwise."

    if head_first:
        raise DeprecationWarning(
            "chunk_gated_delta_rule: head_first is deprecated and will be removed in a future version. "
            "Please use head_first=False for now instead.",
            stacklevel=2,
        )
        q, k, v, beta, g = map(lambda x: rearrange(x, "b h t ... -> b t h ..."), (q, k, v, beta, g))
    if not head_first and q.shape[1] < q.shape[2]:
        warnings.warn(
            f"chunk_gated_delta_rule: Input tensor shape suggests potential format mismatch: seq_len ({q.shape[1]}) < num_heads ({q.shape[2]}). "
            "This may indicate the inputs were passed in head-first format [B, H, T, ...] "
            "when head_first=False was specified. "
            "Please verify your input tensor format matches the expected shape [B, T, H, ...].",
            stacklevel=2,
        )
    if cu_seqlens is not None:
        if q.shape[0] != 1:
            raise ValueError(
                f"chunk_gated_delta_rule: The batch size is expected to be 1 rather than {q.shape[0]} when using `cu_seqlens`."
                f"Please flatten variable-length inputs before processing."
            )
        if initial_state is not None and initial_state.shape[0] != len(cu_seqlens) - 1:
            raise ValueError(
                f"chunk_gated_delta_rule: The number of initial states is expected to be equal to the number of input sequences, "
                f"i.e., {len(cu_seqlens) - 1} rather than {initial_state.shape[0]}."
            )
    if scale is None:
        scale = k.shape[-1] ** -0.5
    o, final_state = ChunkGatedDeltaRuleFunction.apply(
        q,
        k,
        v,
        g,
        beta,
        scale,
        initial_state,
        output_final_state,
        cu_seqlens,
        prebuilt_meta,
        use_qk_l2norm_in_kernel,
    )
    if head_first:
        o = rearrange(o, "b t h ... -> b h t ...")
    return o, final_state
