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
# This file is a part of the vllm-ascend project.

import unittest
from unittest.mock import MagicMock, patch

from vllm_ascend.ascend_forward_context import MoECommType, select_moe_comm_method


class TestSelectMoeCommMethod(unittest.TestCase):
    @patch("vllm_ascend.ascend_forward_context.is_moe_model", return_value=True)
    def test_edge_cloud_uses_all_gather(self, _):
        """Edge-cloud mode must not use MC2/ALLTOALL paths.

        MC2/ALLTOALL exercise the MC2 process group, which can trigger
        collective operations across the edge-cloud boundary.  Force the
        ALLGATHER path so only local EP/TP groups are used.
        """
        vllm_config = MagicMock()
        vllm_config.parallel_config.enable_edge_cloud = True

        result = select_moe_comm_method(16, vllm_config)

        self.assertEqual(result, MoECommType.ALLGATHER)

    @patch("vllm_ascend.ascend_forward_context.is_moe_model", return_value=False)
    def test_non_moe_returns_none(self, _):
        vllm_config = MagicMock()
        vllm_config.parallel_config.enable_edge_cloud = False

        result = select_moe_comm_method(16, vllm_config)

        self.assertIsNone(result)
