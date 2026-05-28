from typing import Any, Callable

import torch
from vllm.config import ParallelConfig, get_current_vllm_config
from vllm.distributed.parallel_state import (
    GroupCoordinator,
    Handle,
    TensorMetadata,
    _split_tensor_dict,
    get_pp_group,
    get_tp_group,
    get_world_group,
    init_model_parallel_group,
)

from vllm_ascend.ascend_config import get_ascend_config
from vllm_ascend.utils import enable_dsa_cp_with_layer_shard, enable_sp, flashcomm2_enable
from vllm.logger import logger

# Currently, mc2 op need their own group coordinator.
_MC2: GroupCoordinator | None = None

# Module specific tensor parallel groups
_MLP_TP: GroupCoordinator | None = None
_OTP: GroupCoordinator | None = None
_LMTP: GroupCoordinator | None = None
_EMBED_TP: GroupCoordinator | None = None

# flashcomm specific groups
_FLASHCOMM2_OTP: GroupCoordinator | None = None
_FLASHCOMM2_ODP: GroupCoordinator | None = None
_FC3_QUANT_X: GroupCoordinator | None = None

# shard_weight across rank groups
_SHARD_WEIGHT: GroupCoordinator | None = None

_P_TP: GroupCoordinator | None = None

_DYNAMIC_EPLB: GroupCoordinator | None = None

# Edge-cloud pre-computed tensor metadata cache.
#
# The edge→cloud (e2c) and cloud→edge (c2e) directions can carry different
# tensor key sets: in embedding_only mode the edge sends only embeddings
# (no transformer layers run, so the residual would be a fabricated zero
# tensor), hence e2c drops "residual" while c2e (cloud→edge) still carries
# the real residual that the edge tail segment needs for its final norm.
# In head_tail mode both directions are identical (both carry residual).
_EDGE_CLOUD_TENSOR_META_E2C: "EdgeCloudTensorMeta | None" = None
_EDGE_CLOUD_TENSOR_META_C2E: "EdgeCloudTensorMeta | None" = None
# Dense (c2e) meta kept for backward-compatible access / tests.
_EDGE_CLOUD_TENSOR_META: "EdgeCloudTensorMeta | None" = None


@dataclass
class EdgeCloudTensorMeta:
    """Pre-computed tensor metadata for edge-cloud hidden state transfer.

    Avoids sending metadata via send_object/recv_object (pickle+Gloo) by
    computing it locally on both sides from config + SchedulerOutput.
    """
    # List of (key, TensorMetadata) pairs, matching the output of _split_tensor_dict
    metadata_list: list[tuple[str, Any]]
    # Ordered list of tensor keys (same order as metadata_list, only tensor entries)
    tensor_keys: list[str]
    # HC multiplier: DeepSeek V4 uses hc_mult > 1 (intermediate tensors are 3D);
    # standard models (Qwen3.5, Llama, etc.) use hc_mult = 1 (2D tensors).
    hc_mult: int
    # Whether to merge multiple tensors into a single send/recv to reduce HCCL
    # P2P protocol RTTs.  When True, edge_cloud_isend_tensor_dict concatenates
    # all tensors along dim=-1 before sending, and edge_cloud_irecv_tensor_dict
    # receives a single merged buffer then splits it back via narrow views.
    merge_payload: bool = False
    # Dtype of the merged tensor (same as hidden_dtype).
    merged_dtype: torch.dtype | None = None
    # Shape tail of the merged tensor (everything except dim-0).  For standard
    # 2D models this is (N * hidden_size,); for 3D (DeepSeek V4) this is
    # (hc_mult, N * hidden_size).
    merged_shape_tail: tuple[int, ...] | None = None
    # Per-tensor size along the concatenation dim=-1.  Used to narrow the
    # merged buffer back into individual logical tensors.
    split_sizes: list[int] | None = None
    # Ordered list of tensor keys that are actually transmitted over the wire.
    # In embedding_only mode the edge->cloud direction omits the zero residual,
    # so the receiver still allocates a residual buffer but zero-fills it locally
    # instead of receiving it. Defaults to tensor_keys when send/recv are identical.
    send_tensor_keys: list[str] | None = None


def _build_edge_cloud_tensor_meta(
    hidden_size: int,
    hidden_dtype: torch.dtype,
    recv_has_residual: bool,
    send_has_residual: bool,
    hc_mult: int,
) -> EdgeCloudTensorMeta:
    """Build a single direction's EdgeCloudTensorMeta.

    ``recv_has_residual`` controls which buffers the receiver allocates,
    while ``send_has_residual`` controls which tensors the sender puts on the
    wire. They differ in embedding_only mode: the receiver still wants a zero
    residual buffer so the model layers stay unchanged, but the sender omits
    the redundant zero residual to save cross-node bandwidth.
    """
    dtype = hidden_dtype
    device = "npu"

    # Determine shape template based on hc_mult:
    #   hc_mult == 1: standard 2D shape (Qwen3.5, Llama, etc.)
    #   hc_mult >  1: 3D shape with hc_mult dimension (DeepSeek V4)
    if hc_mult > 1:
        tensor_shape: tuple[int, ...] = (0, hc_mult, hidden_size)
    else:
        tensor_shape = (0, hidden_size)

    metadata_list: list[tuple[str, Any]] = [
        ("hidden_states", TensorMetadata(device, dtype, tensor_shape)),
    ]
    tensor_keys = ["hidden_states"]

    if recv_has_residual:
        metadata_list.append(
            ("residual", TensorMetadata(device, dtype, tensor_shape))
        )
        tensor_keys.append("residual")

    send_tensor_keys = [k for k in tensor_keys if k != "residual"]
    if send_has_residual:
        send_tensor_keys = list(tensor_keys)

    # Decide whether to merge all tensors into one send/recv.  Conditions:
    #   1) at least 2 tensors to merge,
    #   2) all share the same dtype and same non-last-dim shape (the
    #      EdgeCloudTensorMeta path guarantees this — both hidden_states and
    #      residual share the exact same TensorMetadata),
    #   3) env switch enabled (default True).
    # The merged buffer is allocated along dim=-1, so each tensor's contribution
    # is (hidden_size) bytes along that axis. The leading dims (num_tokens for
    # 2D, num_tokens x hc_mult for 3D) are preserved.
    from vllm_ascend import envs as envs_ascend
    env_enabled = envs_ascend.VLLM_ASCEND_EDGE_CLOUD_MERGE_PAYLOAD
    merge_payload = env_enabled and len(tensor_keys) >= 2 and len(send_tensor_keys) >= 2
    merged_dtype: torch.dtype | None = None
    merged_shape_tail: tuple[int, ...] | None = None
    split_sizes: list[int] | None = None
    if merge_payload:
        # Sanity: all metadata entries that are TensorMetadata must agree on
        # dtype and non-last-dim shape.  Different shape on the last dim is
        # allowed (we are concatenating along dim=-1).
        first_meta = next(
            v for _, v in metadata_list if isinstance(v, TensorMetadata)
        )
        merged_dtype = first_meta.dtype
        leading_dims = first_meta.size[:-1]  # everything except hidden_size
        last_dim_sum = 0
        sizes: list[int] = []
        for _, meta_v in metadata_list:
            if not isinstance(meta_v, TensorMetadata):
                continue
            if meta_v.dtype != merged_dtype or meta_v.size[:-1] != leading_dims:
                # Heterogeneous, fall back to no merge.
                merge_payload = False
                merged_dtype = None
                merged_shape_tail = None
                sizes = []
                break
            sizes.append(meta_v.size[-1])
            last_dim_sum += meta_v.size[-1]
        if merge_payload:
            # leading_dims keeps the placeholder 0 in dim 0; the runtime
            # tensor will use the real num_tokens.  merged_shape_tail is the
            # part *after* dim 0, so we drop the leading 0.
            merged_shape_tail = leading_dims[1:] + (last_dim_sum,)
            split_sizes = sizes

    return EdgeCloudTensorMeta(
        metadata_list=metadata_list,
        tensor_keys=tensor_keys,
        hc_mult=hc_mult,
        merge_payload=merge_payload,
        merged_dtype=merged_dtype,
        merged_shape_tail=merged_shape_tail,
        split_sizes=split_sizes,
        send_tensor_keys=send_tensor_keys,
    )


def init_edge_cloud_tensor_meta(
    hidden_size: int,
    hidden_dtype: torch.dtype = torch.bfloat16,
    has_residual: bool = True,
    hc_mult: int = 1,
    mode: str = "head_tail",
):
    """Initialize the pre-computed tensor metadata for edge-cloud transfers.

    Called once during worker initialization. The metadata is used by
    edge_cloud_irecv_tensor_dict to allocate receive buffers without
    requiring an inter-node metadata exchange.

    Two direction-specific metas are built because the edge→cloud and
    cloud→edge directions can carry different tensor key sets: in
    ``embedding_only`` mode the edge sends only embeddings (no transformer
    layers run, so the residual would be a fabricated zero tensor). To keep
    the model layers unchanged, the receiver still allocates a zero residual
    buffer locally; only the wire payload omits ``residual``. c2e always
    carries the real residual that the edge tail segment needs for its final
    norm. In ``head_tail`` mode both directions carry residual on the wire.

    Args:
        hidden_size: model hidden dimension (from hf_text_config.hidden_size)
        hidden_dtype: torch.dtype derived directly from model_config.dtype
            (equivalent to MindIE's config.torch_dtype from config.json),
            eliminating the need for a separate user-configured dtype string.
        has_residual: dynamically detected  True if the model produces a
            residual tensor in IntermediateTensors (most decoder models do).
        hc_mult: HC multiplier for DeepSeek V4's Hash Compression mechanism.
            When hc_mult > 1, intermediate tensors are 3D
            ``(num_tokens, hc_mult, hidden_size)`` instead of the standard 2D
            ``(num_tokens, hidden_size)``.  Defaults to 1 (standard models like
            Qwen3.5, Llama, etc.).
        mode: edge-cloud mode ("head_tail" or "embedding_only"). In
            embedding_only the edge→cloud direction omits the redundant zero
            residual; in head_tail both directions carry residual.
    """
    global _EDGE_CLOUD_TENSOR_META_E2C, _EDGE_CLOUD_TENSOR_META_C2E
    global _EDGE_CLOUD_TENSOR_META

    # e2c (edge→cloud): in embedding_only the edge runs no transformer layers,
    # so its residual would be a fabricated zero tensor carrying no information.
    # Drop it from the wire payload to halve the cross-node bandwidth, but the
    # receiver still allocates a zero residual buffer so model layers stay
    # unchanged. head_tail always runs >=1 head layer, so the residual is real
    # and must be transmitted.
    e2c_recv_has_residual = has_residual
    e2c_send_has_residual = has_residual and (mode != "embedding_only")
    # c2e (cloud→edge): the cloud produces a real residual that the edge tail
    # segment's final norm consumes, so it is always transmitted and received.
    c2e_recv_has_residual = has_residual
    c2e_send_has_residual = has_residual

    _EDGE_CLOUD_TENSOR_META_E2C = _build_edge_cloud_tensor_meta(
        hidden_size, hidden_dtype, e2c_recv_has_residual, e2c_send_has_residual, hc_mult,
    )
    _EDGE_CLOUD_TENSOR_META_C2E = _build_edge_cloud_tensor_meta(
        hidden_size, hidden_dtype, c2e_recv_has_residual, c2e_send_has_residual, hc_mult,
    )
    # Backward-compatible alias: dense (residual-carrying) meta.
    _EDGE_CLOUD_TENSOR_META = _EDGE_CLOUD_TENSOR_META_C2E

    logger.info(
        "[EdgeCloud] Initialized tensor meta (mode=%s): "
        "e2c recv_keys=%s send_keys=%s (merge=%s), "
        "c2e recv_keys=%s send_keys=%s (merge=%s), dtype=%s, "
        "hidden_size=%d, hc_mult=%d",
        mode,
        _EDGE_CLOUD_TENSOR_META_E2C.tensor_keys,
        _EDGE_CLOUD_TENSOR_META_E2C.send_tensor_keys,
        _EDGE_CLOUD_TENSOR_META_E2C.merge_payload,
        _EDGE_CLOUD_TENSOR_META_C2E.tensor_keys,
        _EDGE_CLOUD_TENSOR_META_C2E.send_tensor_keys,
        _EDGE_CLOUD_TENSOR_META_C2E.merge_payload,
        hidden_dtype,
        hidden_size,
        hc_mult,
    )


def get_edge_cloud_tensor_meta(
    direction: str | None = None,
) -> EdgeCloudTensorMeta:
    """Get the pre-computed edge-cloud tensor metadata for a direction.

    Args:
        direction: "e2c" (edge→cloud) or "c2e" (cloud→edge). When None,
            returns the dense (c2e) meta for backward compatibility.
    """
    if direction == "e2c":
        meta = _EDGE_CLOUD_TENSOR_META_E2C
    else:
        meta = _EDGE_CLOUD_TENSOR_META_C2E
    assert meta is not None, (
        "Edge-cloud tensor meta not initialized. "
        "Call init_edge_cloud_tensor_meta() first."
    )
    return meta


def _select_edge_cloud_meta_for_send() -> EdgeCloudTensorMeta:
    """Pick the send-direction meta based on this rank's edge/cloud role.

    In edge-cloud mode vLLM overrides ``get_pp_group().is_first_rank`` to
    return ``is_edge_device()`` for the PP group, so we use the explicit
    role helpers instead of raw PP rank.  Edge sends e2c; cloud sends c2e.
    """
    return get_edge_cloud_tensor_meta(
        "e2c" if is_edge_device() else "c2e"
    )


def _select_edge_cloud_meta_for_recv() -> EdgeCloudTensorMeta:
    """Pick the recv-direction meta based on this rank's edge/cloud role.

    In edge-cloud mode vLLM overrides ``get_pp_group().is_last_rank`` to
    return ``is_edge_device()`` for the PP group, so using it would swap
    the receive direction and allocate buffers for the wrong tensor key set
    (e.g. expecting a residual in embedding_only mode).  Edge receives c2e;
    cloud receives e2c.
    """
    return get_edge_cloud_tensor_meta(
        "e2c" if is_cloud_device() else "c2e"
    )


def init_ascend_model_parallel(
    parallel_config: ParallelConfig,
):
    if model_parallel_initialized():
        return
    assert torch.distributed.is_initialized()
    # Declare globals upfront to avoid "used prior to global declaration" errors
    global _MC2
    if parallel_config.enable_edge_cloud:
        # In edge-cloud mode, _MC2 is initialized with the same group_ranks as
        # upstream _EP: all edge workers form one EP group and all cloud
        # workers form another. Ranks are arranged by dp instance:
        # instance0_edge, instance0_cloud, instance1_edge, instance1_cloud.
        # P_TP / DYNAMIC_EPLB / fine-grained TP groups are skipped because
        # edge-cloud mode does not use the standard uniform rank layout
        # (DP * PP * PCP * TP).
        backend = torch.distributed.get_backend(get_world_group().device_group)
        edge_npu_count = parallel_config.edge_npu_count
        cloud_npu_count = parallel_config.cloud_npu_count
        if parallel_config.is_shared_model_edge:
            # Shared-model edge-cloud topology: the edge has a
            # single distributed rank (rank 0) and the cloud
            # occupies ranks 1..1 + N*C.
            ep_edge_ranks = [0]
            ep_cloud_ranks = list(
                range(1,
                      1 + parallel_config.data_parallel_size * cloud_npu_count))
        else:
            world_size_per_instance = edge_npu_count + cloud_npu_count
            ep_edge_ranks = []
            ep_cloud_ranks = []
            for dp_idx in range(parallel_config.data_parallel_size):
                base = dp_idx * world_size_per_instance
                ep_edge_ranks.extend(range(base, base + edge_npu_count))
                ep_cloud_ranks.extend(
                    range(base + edge_npu_count, base + world_size_per_instance))
        _MC2 = init_model_parallel_group(
            [ep_edge_ranks, ep_cloud_ranks],
            get_world_group().local_rank,
            backend,
            group_name="mc2",
        )

        # Phase6 hidden data-plane channels are still required in edge-cloud
        # mode.  The default PP group is PREFILL_1, the alternate PP group is
        # DECODE, and the extra hidden-channel group is PREFILL_2.
        pp_group = get_pp_group()
        if pp_group.world_size > 1:
            pp_group.create_alternate_groups(backend)
            if hasattr(pp_group, "create_hidden_channel_groups"):
                pp_group.create_hidden_channel_groups(backend)

        # Ascend-specific groups that are currently disabled by default
        # in edge-cloud mode. If enabled in the future, they must follow
        # the same edge/cloud separation principle:
        #   _DYNAMIC_EPLB, _FC3_QUANT_X,
        #   _OTP, _LMTP, _EMBED_TP, _MLP_TP,
        #   _FLASHCOMM2_OTP, _FLASHCOMM2_ODP,
        #   _SHARD_WEIGHT, _P_TP
        return
    world_size = torch.distributed.get_world_size()
    backend = torch.distributed.get_backend(get_world_group().device_group)
    global_tp_size = 1 if parallel_config.enable_edge_cloud else parallel_config.tensor_parallel_size
    global_dp_size = parallel_config.data_parallel_size
    global_pp_size = parallel_config.pipeline_parallel_size
    global_pcp_size = parallel_config.prefill_context_parallel_size

    # The layout of all ranks: ExternalDP * EP
    # ExternalDP is the data parallel group that is not part of the model,
    # every dp rank can generate independently (in verl integration).
    all_ranks = torch.arange(world_size).reshape(
        -1,
        global_dp_size,
        global_pp_size,
        global_pcp_size,
        global_tp_size,
    )

    pd_tp_ratio = get_ascend_config().pd_tp_ratio
    pd_head_ratio = get_ascend_config().pd_head_ratio
    global _P_TP
    assert _P_TP is None, "distributed prefill tensor parallel group is already initialized"
    prefill_tensor_model_parallel_size = pd_tp_ratio
    # divide alltoall groups
    if pd_head_ratio > 1 and get_current_vllm_config().kv_transfer_config.is_kv_producer:
        num_head_replica = get_ascend_config().num_head_replica
        remote_tp_size = global_tp_size // pd_tp_ratio
        if num_head_replica <= 1:
            group_ranks = all_ranks.view(-1, prefill_tensor_model_parallel_size).unbind(0)
        else:
            group_ranks = all_ranks.clone().view(
                global_dp_size * global_pp_size * global_pcp_size, -1, num_head_replica
            )  # [DP_size, num_head, num_head_replica]
            group_ranks = group_ranks.permute(0, 2, 1)
            group_ranks = group_ranks.reshape(-1, group_ranks.size(-1))  # [DP_size * num_head_replica, num_head]
            alltoall_group_size = group_ranks.size(-1) // remote_tp_size
            group_ranks = group_ranks.unsqueeze(-1).view(
                global_dp_size * global_pp_size * global_pcp_size,
                num_head_replica,
                -1,
                alltoall_group_size,
            )  # [DP_size, num_head_replica, num_alltoall_group, alltoall_group_size]
            group_ranks = group_ranks.reshape(-1, alltoall_group_size).unbind(0)
        group_ranks = [x.tolist() for x in group_ranks]
        local_rank = get_world_group().local_rank
        num = next((i for i, ranks in enumerate(group_ranks) if local_rank in ranks), None)
        _P_TP = init_model_parallel_group(group_ranks, get_world_group().local_rank, backend, group_name=f"p_tp_{num}")

    # EP like group ranks
    group_ranks = (
        all_ranks.transpose(1, 2)
        .reshape(
            -1,
            global_dp_size * global_pcp_size * global_tp_size,
        )
        .unbind(0)
    )
    group_ranks = [x.tolist() for x in group_ranks]

    _MC2 = init_model_parallel_group(group_ranks, get_world_group().local_rank, backend, group_name="mc2")

    if get_ascend_config().eplb_config.dynamic_eplb:
        global _DYNAMIC_EPLB
        _DYNAMIC_EPLB = init_model_parallel_group(
            group_ranks, get_world_group().local_rank, backend, group_name="dynamic_eplb"
        )

    if get_ascend_config().multistream_overlap_gate:
        global _FC3_QUANT_X
        _FC3_QUANT_X = init_model_parallel_group(
            group_ranks, get_world_group().local_rank, backend, group_name="fc3_quant_x"
        )

    if parallel_config.enable_edge_cloud:
        return

    # Initialize fine-grained TP process groups on Ascend for four components:
    # 1. LM Head: output logits projection (`lmhead_tensor_parallel_size`)
    # 2. O Proj: attention output projection (`oproj_tensor_parallel_size`)
    # 3. Embedding: The token embedding table at the input of the model (`embedding_tensor_parallel_size`)
    # 4. MLP: feed-forward network in transformer blocks (`mlp_tensor_parallel_size`)
    _group_cache = {}

    def _create_or_get_group(group_size: int, group_name: str) -> GroupCoordinator:
        if group_size is None:
            return None
        if group_size not in _group_cache:
            rank_grid = torch.arange(world_size).reshape(global_pp_size, global_dp_size, global_tp_size)
            num_chunks = global_dp_size // group_size
            group_ranks = []
            for pp_idx in range(global_pp_size):
                stage_ranks = rank_grid[pp_idx]  # (dp, tp)
                for chunk in range(num_chunks):
                    for tp_idx in range(global_tp_size):
                        group = stage_ranks[chunk * group_size : (chunk + 1) * group_size, tp_idx].tolist()
                        group_ranks.append(group)
            pg = init_model_parallel_group(group_ranks, get_world_group().local_rank, backend, group_name=group_name)
            _group_cache[group_size] = pg

        return _group_cache[group_size]

    otp_size = get_ascend_config().finegrained_tp_config.oproj_tensor_parallel_size
    lmhead_tp_size = get_ascend_config().finegrained_tp_config.lmhead_tensor_parallel_size
    embedding_tp_size = get_ascend_config().finegrained_tp_config.embedding_tensor_parallel_size
    mlp_tp_size = get_ascend_config().finegrained_tp_config.mlp_tensor_parallel_size

    global _OTP, _LMTP, _EMBED_TP, _MLP_TP

    if otp_size > 0:
        _OTP = _create_or_get_group(otp_size, "otp")
    if lmhead_tp_size > 0:
        _LMTP = _create_or_get_group(lmhead_tp_size, "lmheadtp")
    if embedding_tp_size > 0:
        _EMBED_TP = _create_or_get_group(embedding_tp_size, "emtp")
    if mlp_tp_size > 0:
        _MLP_TP = _create_or_get_group(mlp_tp_size, "mlptp")

    # TODO: Extract and unify the logic across different communication group.
    flashcomm2_otp_group_ranks = []
    if flashcomm2_enable():
        flashcomm2_otp_size = get_ascend_config().flashcomm2_oproj_tensor_parallel_size
        num_fc2_oproj_tensor_parallel_groups: int = global_tp_size // flashcomm2_otp_size
        global _FLASHCOMM2_OTP
        global _FLASHCOMM2_ODP

        _FLASHCOMM2_OTP = None
        _FLASHCOMM2_ODP = get_tp_group()

        if flashcomm2_otp_size > 1:
            odp_group_ranks: list[list[int]] = [
                [] for _ in range(flashcomm2_otp_size * global_dp_size * global_pp_size)
            ]
            for dp_group_index in range(global_dp_size):
                for pp_group_index in range(global_pp_size):
                    dp_pp_serial_index = dp_group_index * global_pp_size + pp_group_index
                    tp_base_rank = dp_pp_serial_index * global_tp_size
                    odp_base_index = dp_pp_serial_index * flashcomm2_otp_size

                    for i in range(num_fc2_oproj_tensor_parallel_groups):
                        ranks = []
                        for j in range(flashcomm2_otp_size):
                            tp_local_rank = i + j * num_fc2_oproj_tensor_parallel_groups
                            assert tp_local_rank < global_tp_size
                            global_rank = tp_base_rank + tp_local_rank
                            ranks.append(global_rank)

                            odp_group_index = odp_base_index + j
                            odp_group_ranks[odp_group_index].append(global_rank)
                        flashcomm2_otp_group_ranks.append(ranks)

            _FLASHCOMM2_OTP = init_model_parallel_group(
                flashcomm2_otp_group_ranks, get_world_group().local_rank, backend, group_name="flashcomm2_otp"
            )
            _FLASHCOMM2_ODP = init_model_parallel_group(
                odp_group_ranks, get_world_group().local_rank, backend, group_name="flashcomm2_odp"
            )

    def create_shard_weight_group(module_tp_group_ranks: None) -> GroupCoordinator:
        # Argument module_tp_group_ranks: The module specific tensor parallel group.
        # There are three situations.
        # 1. If it is None, then the TP_size of the specific module is 1 and is replicated linear layer.
        # 2. If it is not None, and the module tp_group is same as the global tp_group.
        # 3. If it is not None, and the module tp_group is different from the global tp_group.(eg. flashcomm2_otp)
        group_ranks = []
        pp_group_ranks = all_ranks.transpose(2, 4).reshape(-1, global_pp_size)
        if module_tp_group_ranks is None:
            # If it is None, then the TP_size of this shard weight is 1.
            shard_weight_group_ranks = pp_group_ranks.transpose(0, 1).unbind(0)
            group_ranks = [x.tolist() for x in shard_weight_group_ranks]
        else:
            # combine standard tp group and non-standard tp group to build  shard_weight comm_group
            module_tp_tanspose_ranks = module_tp_group_ranks.transpose(0, 1)
            G = world_size // (global_pp_size * module_tp_group_ranks.size(1))
            shard_weight_group_ranks = torch.stack([t.view(global_pp_size, G) for t in module_tp_tanspose_ranks], dim=1)
            group_ranks = shard_weight_group_ranks.view(-1, G).tolist()
        return init_model_parallel_group(group_ranks, get_world_group().local_rank, backend, group_name="shard_weight")

    # Create shard weight group if enabled
    if get_ascend_config().layer_sharding is not None:
        global _SHARD_WEIGHT
        if flashcomm2_enable():
            if len(flashcomm2_otp_group_ranks) == 0:
                FC2_group_ranks = None
            else:
                FC2_group_ranks = torch.tensor(flashcomm2_otp_group_ranks).squeeze(0)
            _SHARD_WEIGHT = create_shard_weight_group(FC2_group_ranks)
        elif enable_dsa_cp_with_layer_shard():
            # For dsa_cp, all shard layers are replicated.
            _SHARD_WEIGHT = create_shard_weight_group(None)
        else:
            # For standard tp, use global tp group_ranks
            tp_group_ranks = all_ranks.view(-1, global_tp_size)
            _SHARD_WEIGHT = create_shard_weight_group(tp_group_ranks)

    # Create alternate PP groups for dual-channel communication.
    # Primary (device_group/cpu_group): used for non-ALL_DECODE batches
    #   (ALL_PREFILL + PREFILL_DECODE_MIXED).
    # Alternate (alt_device_group/alt_cpu_group): used for ALL_DECODE batches.
    # Both groups cover the same PP ranks but are independent ProcessGroup
    # instances, allowing the HCCL backend to maintain separate communication
    # streams and avoid head-of-line blocking between decode and
    # prefill/mixed traffic.
    if global_pp_size > 1:
        pp_group = get_pp_group()
        backend = torch.distributed.get_backend(get_world_group().device_group)
        pp_group.create_alternate_groups(backend)
        if hasattr(pp_group, "create_hidden_channel_groups"):
            pp_group.create_hidden_channel_groups(backend)


def model_parallel_initialized():
    return _MC2 is not None


def get_mc2_group() -> GroupCoordinator:
    assert _MC2 is not None, "mc2 group is not initialized"
    return _MC2


def get_mlp_tp_group() -> GroupCoordinator:
    assert _MLP_TP is not None, "mlp group is not initialized"
    return _MLP_TP


def get_otp_group() -> GroupCoordinator:
    assert _OTP is not None, "output tensor parallel group is not initialized"
    return _OTP


def get_lmhead_tp_group() -> GroupCoordinator:
    assert _LMTP is not None, "lm head tensor parallel group is not initialized"
    return _LMTP


def get_embed_tp_group() -> GroupCoordinator:
    assert _EMBED_TP is not None, "emtp group is not initialized"
    return _EMBED_TP


def get_flashcomm2_otp_group() -> GroupCoordinator:
    return _FLASHCOMM2_OTP


def get_flashcomm2_odp_group() -> GroupCoordinator:
    assert _FLASHCOMM2_ODP is not None, "output data parallel group for flashcomm2 is not initialized"
    return _FLASHCOMM2_ODP


def get_shard_weight_group() -> GroupCoordinator:
    assert _SHARD_WEIGHT is not None, "output shard weight parallel group for flashcomm2 is not initialized"
    return _SHARD_WEIGHT


def get_p_tp_group() -> GroupCoordinator:
    assert _P_TP is not None, "distributed prefill tensor parallel group is not initialized"
    return _P_TP


def get_fc3_quant_x_group() -> GroupCoordinator:
    assert _FC3_QUANT_X is not None, "fc3 quant x group is not initialized"
    return _FC3_QUANT_X


def get_dynamic_eplb_group() -> GroupCoordinator:
    assert _DYNAMIC_EPLB is not None, "Dynamic eplb group is not initialized"
    return _DYNAMIC_EPLB


def destroy_ascend_model_parallel():
    global _MC2
    if _MC2:
        _MC2.destroy()
    _MC2 = None

    global _MLP_TP
    if _MLP_TP:
        _MLP_TP.destroy()
    _MLP_TP = None

    global _LMTP
    if _LMTP:
        _LMTP.destroy()
    _LMTP = None

    global _EMBED_TP
    if _EMBED_TP:
        _EMBED_TP.destroy()
    _EMBED_TP = None

    global _OTP
    if _OTP:
        _OTP.destroy()
    _OTP = None

    global _P_TP
    if _P_TP:
        _P_TP.destroy()
    _P_TP = None

    global _FLASHCOMM2_OTP
    if _FLASHCOMM2_OTP and get_ascend_config().flashcomm2_oproj_tensor_parallel_size != 1:
        _FLASHCOMM2_OTP.destroy()
        _FLASHCOMM2_OTP = None

    global _FLASHCOMM2_ODP
    if _FLASHCOMM2_ODP and get_ascend_config().flashcomm2_oproj_tensor_parallel_size != 1:
        _FLASHCOMM2_ODP.destroy()
        _FLASHCOMM2_ODP = None

    global _SHARD_WEIGHT
    if _SHARD_WEIGHT:
        _SHARD_WEIGHT.destroy()
    _SHARD_WEIGHT = None

    global _FC3_QUANT_X
    if _FC3_QUANT_X:
        _FC3_QUANT_X.destroy()
    _FC3_QUANT_X = None

    global _DYNAMIC_EPLB
    if _DYNAMIC_EPLB:
        _DYNAMIC_EPLB.destroy()
    _DYNAMIC_EPLB = None


def edge_cloud_broadcast_recv() -> tuple[
    dict[str, torch.Tensor | Any] | None,
    list[Handle],
    list[Callable[[], None]],
]:
    """Receive PP tensors and broadcast them within the local edge/cloud TP group."""
    pp_group = get_pp_group()
    tp_group = get_tp_group()
    is_pp_npu0 = pp_group.world_size == 2

    if is_pp_npu0:
        tensor_dict, comm_handles, comm_postprocess = pp_group.irecv_tensor_dict()
        assert tensor_dict is not None, (
            "edge_cloud_broadcast_recv: PP tensor_dict is None, "
            "sender may have failed."
        )

        metadata_list, _ = _split_tensor_dict(tensor_dict)
        tp_group.broadcast_object(metadata_list, src=0)

        def broadcast_postprocess():
            _, tensor_list = _split_tensor_dict(tensor_dict) if tensor_dict else (None, [])
            handles = []
            for tensor in tensor_list:
                if tensor.numel() == 0:
                    continue
                group = tp_group.cpu_group if tensor.is_cpu else tp_group.device_group
                handles.append(
                    torch.distributed.broadcast(
                        tensor, src=tp_group.ranks[0], group=group, async_op=True
                    )
                )
            for handle in handles:
                handle.wait()

        comm_postprocess.append(broadcast_postprocess)
        return tensor_dict, comm_handles, comm_postprocess

    metadata_list = tp_group.broadcast_object(None, src=0)
    if metadata_list is None:
        metadata_list = []
    recv_tensor_dict: dict[str, torch.Tensor | Any] = {}

    for key, value in metadata_list:
        if isinstance(value, TensorMetadata):
            tensor = torch.empty(value.size, dtype=value.dtype, device=value.device)
            recv_tensor_dict[key] = tensor
        else:
            recv_tensor_dict[key] = value

    def broadcast_postprocess():
        handles = []
        for tensor in recv_tensor_dict.values():
            if not isinstance(tensor, torch.Tensor) or tensor.numel() == 0:
                continue
            group = tp_group.cpu_group if tensor.is_cpu else tp_group.device_group
            handles.append(
                torch.distributed.broadcast(
                    tensor, src=tp_group.ranks[0], group=group, async_op=True
                )
            )
        for handle in handles:
            handle.wait()

    return recv_tensor_dict, [], [broadcast_postprocess]
