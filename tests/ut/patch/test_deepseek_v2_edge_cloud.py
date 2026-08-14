# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import torch
from vllm.sequence import IntermediateTensors

from vllm_ascend.patch.models.deepseek_v2_edge_cloud import (
    _forward_edge_cloud_segment_deepseek_v2,
)


def test_cloud_segment_stores_aux_hidden_states_in_public_tensor_map():
    input_hidden_states = torch.randn(2, 4)
    output_hidden_states = torch.randn(2, 4)
    model = SimpleNamespace(
        layers=[MagicMock(return_value=(output_hidden_states, None))],
        aux_hidden_state_layers=(0,),
    )
    boundary = IntermediateTensors({"hidden_states": output_hidden_states})

    with patch(
        "vllm_ascend.patch.models.deepseek_v2_edge_cloud.make_boundary_tensors",
        return_value=boundary,
    ):
        output = _forward_edge_cloud_segment_deepseek_v2(
            model,
            start_layer=0,
            end_layer=1,
            input_ids=None,
            positions=torch.zeros(2, dtype=torch.int64),
            inputs_embeds=input_hidden_states,
            is_first_segment=True,
            is_last_segment=False,
        )

    assert output is boundary
    torch.testing.assert_close(
        output.tensors["aux_hidden_states"], input_hidden_states
    )
