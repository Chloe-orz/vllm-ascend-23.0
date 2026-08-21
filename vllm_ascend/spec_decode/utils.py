# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
import numpy as np
import torch


def update_num_computed_tokens_for_batch_change(
    num_computed_tokens: torch.Tensor,
    num_accepted_tokens: torch.Tensor,
    prev_positions: torch.Tensor,
    valid_sampled_token_count: torch.Tensor,
    prev_num_draft_tokens: torch.Tensor,
    cpu_num_computed_tokens: torch.Tensor,
    previous_num_computed_tokens: torch.Tensor | None = None,
) -> None:
    """Correct num_computed_tokens for async spec decode drift.

    Requests that had drafts: corrected = prev_gpu + valid_count.
    New requests or non-draft (e.g. prefills): use CPU value directly.
    """
    # Clamp because prev_positions can be -1 for new requests
    gather_indices = prev_positions.clamp(min=0)

    valid_counts = valid_sampled_token_count[gather_indices]
    if previous_num_computed_tokens is None:
        prev_computed = num_computed_tokens[gather_indices]
    else:
        # The explicit baseline is already arranged in current-batch request
        # order.  It is used by DSV4 edge-cloud MTP because the shared device
        # buffer and req_state may both be changed after the preceding target
        # SchedulerOutput (SO) was issued.
        prev_computed = previous_num_computed_tokens
    prev_drafts = prev_num_draft_tokens[gather_indices]

    participating = (prev_positions >= 0) & (prev_drafts > 0)
    corrected = prev_computed + valid_counts.int()

    n = prev_positions.shape[0]
    num_computed_tokens[:n].copy_(torch.where(participating, corrected, cpu_num_computed_tokens))
    num_accepted_tokens.copy_(torch.where(participating, valid_counts, num_accepted_tokens))


def correct_optimistic_seq_lens_cpu(
    optimistic_seq_lens_cpu_np: np.ndarray,
    prev_positions_np: np.ndarray,
    prev_num_draft_tokens_np: np.ndarray,
    valid_sampled_token_count_np: np.ndarray,
    num_reqs: int,
    previous_num_computed_tokens_np: np.ndarray | None = None,
    current_num_computed_tokens_np: np.ndarray | None = None,
) -> None:
    """Correct ``optimistic_seq_lens_cpu`` for async spec decode drift.

    The scheduler optimistically advances ``num_computed_tokens_cpu`` by the
    full number of tokens scheduled in the previous step (``prev_drafts + 1``
    per spec-decode request), assuming all drafts were accepted. The actual
    number of valid sampled tokens is ``valid_count = 1 + accepted_drafts``.
    The drift, equal to the number of rejected tokens, is therefore::

        rejected = prev_drafts + 1 - valid_count

    Subtracting this from the optimistic seq_lens recovers the true seq_lens
    that ``self.seq_lens`` (GPU) carries for participating requests, without
    touching the device. New requests (``prev_positions < 0``) and prefills
    (``prev_drafts == 0``) need no correction.

    Mirrors ``update_num_computed_tokens_for_batch_change`` on the CPU side.

    All arrays are sliced to ``num_reqs``; ``optimistic_seq_lens_cpu_np`` is
    modified in place.
    """
    prev_positions = prev_positions_np[:num_reqs]
    # Clamp negative entries (new requests) to 0; the participating mask zeroes
    # out their correction so the gathered values are don't-care.
    gather_indices = np.maximum(prev_positions, 0)
    prev_drafts = prev_num_draft_tokens_np[gather_indices]
    valid_counts = valid_sampled_token_count_np[gather_indices]

    participating = (prev_positions >= 0) & (prev_drafts > 0)
    # rejected_for_participating == correction; non-participating reqs end up
    # at zero via the mask multiply.
    if previous_num_computed_tokens_np is None:
        correction = (prev_drafts + 1 - valid_counts) * participating
        optimistic_seq_lens_cpu_np[:num_reqs] -= correction.astype(
            optimistic_seq_lens_cpu_np.dtype, copy=False
        )
        return

    assert current_num_computed_tokens_np is not None
    # The existing seq_lens were built from the current SO value. Replace that
    # base with the preceding target SO value plus the actual valid-token count.
    # This works whether the current SO is optimistic or has already been
    # settled by the PD scheduler.
    corrected_bases = previous_num_computed_tokens_np[:num_reqs] + valid_counts
    base_delta = (
        corrected_bases - current_num_computed_tokens_np[:num_reqs]
    ) * participating
    optimistic_seq_lens_cpu_np[:num_reqs] += base_delta.astype(
        optimistic_seq_lens_cpu_np.dtype, copy=False
    )
