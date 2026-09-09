# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM Ascend project

import threading
from types import SimpleNamespace

import pytest
from vllm.v1.core.sched.output import BatchType, HiddenChannelType, SchedulerOutput

from vllm_ascend.core.passive_scheduler import PassiveScheduler
from vllm_ascend.edge_cloud import role_registry
from vllm_ascend.v1.engine.passive_core import MultiEdgeChannelMux, PassiveEngineCoreProc


class RecordingChannel:
    def __init__(self, output):
        self.outputs = [(1, output)]
        self.returned = []
        self.delivered = threading.Event()

    def consume_new_outputs(self):
        outputs, self.outputs = self.outputs, []
        if not outputs:
            # The subscriber has finished enqueueing the previous poll.
            self.delivered.set()
        return outputs

    def publish(self, output):
        self.returned.append(output)


@pytest.mark.parametrize("edge_ids", [None, [0], [7], [0, 1]], ids=["legacy", "one-edge", "edge-seven", "two-edges"])
@pytest.mark.parametrize("batch_type", [BatchType.PREFILL_FIRST, BatchType.DECODE_FIRST])
def test_registry_batches_reach_dispatch_and_return_to_source(monkeypatch, edge_ids, batch_type):
    registry = None if edge_ids is None else SimpleNamespace(edge_ids=edge_ids, config_digest="test-registry")
    monkeypatch.setattr(role_registry, "get_role_registry", lambda: registry)
    monkeypatch.setattr(PassiveScheduler, "_load_layer_slice_config", lambda self: None)
    config = SimpleNamespace(
        model_config=SimpleNamespace(hf_text_config=SimpleNamespace(num_hidden_layers=4)),
        parallel_config=SimpleNamespace(enable_edge_cloud=True, pipeline_parallel_size=2),
        additional_config={"edge_cloud_config": {"prefix_cache_coordination": {"enabled": True}}},
    )
    channels = {}
    for edge_id in edge_ids if edge_ids is not None else [0]:
        output = SchedulerOutput.make_empty()
        output.batch_type = batch_type
        # Both edges deliberately use identical IDs to exercise isolation.
        output.num_scheduled_tokens = {"request": 20}
        output.total_num_scheduled_tokens = 20
        output.head_token = "head"
        output.hidden_channel = (
            HiddenChannelType.prefill(1) if batch_type == BatchType.PREFILL_FIRST else HiddenChannelType.decode(1)
        )
        channels[edge_id] = RecordingChannel(output)
    subscriber = MultiEdgeChannelMux(channels) if registry is not None else channels[0]
    handled = []

    def handle_output(output):
        # The KV rewrite callback must see IDs in the cloud namespace.
        handled.append((list(output.num_scheduled_tokens), output.head_token))
        return output

    scheduler = PassiveScheduler(
        config,
        subscriber,
        scheduler_output_handler=handle_output,
    )
    engine = SimpleNamespace(
        vllm_config=config,
        _pp_pd_channel=subscriber,
        _published_post_out_tokens=set(),
    )
    try:
        for channel in channels.values():
            assert channel.delivered.wait(timeout=5), "subscriber did not drain its channel"
        scheduler.poll_and_classify()
        for edge_id, channel in channels.items():
            batch = scheduler.schedule()
            assert not batch.is_empty(), "received head segment was never dispatched"
            assert batch.slices == [None]
            output = batch.scheduler_output
            assert output.batch_type == batch_type
            expected_req_id = f"e{edge_id}-request" if registry is not None else "request"
            expected_head = f"{edge_id}:head" if registry is not None else "head"
            assert output.num_scheduled_tokens == {expected_req_id: 20}
            assert output.head_token == expected_head
            assert ([expected_req_id], expected_head) in handled

            PassiveEngineCoreProc._maybe_publish_post_out(engine, output)
            if batch_type == BatchType.PREFILL_FIRST:
                assert len(channel.returned) == 1
                tail = channel.returned[0]
                assert tail.batch_type == BatchType.PREFILL_LAST
                assert tail.head_token == "head"
                assert tail.edge_cloud_ack_only
                # Returning the tail must not mutate the cloud's head.
                assert output.head_token == expected_head
            else:
                assert not channel.returned  # Decode tails are edge-generated.
        assert len(handled) == len(channels)
        scheduler.poll_and_classify()
        assert scheduler.schedule().is_empty()
    finally:
        scheduler.shutdown()
