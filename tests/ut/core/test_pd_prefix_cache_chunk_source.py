# SPDX-License-Identifier: Apache-2.0
"""Import-free regressions for prefix-cached edge-cloud prefill routing."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
SCHEDULER = ROOT / "vllm_ascend" / "core" / "pd_separated_scheduler.py"


def _method(name: str) -> ast.FunctionDef:
    module = ast.parse(SCHEDULER.read_text())
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"method {name} not found in {SCHEDULER}")


def _make_pick_prefill_harness():
    methods = [
        _method("_pick_prefill_first_batch"),
        _method("_update_from_output_prefill_last_chunk_prior"),
    ]
    for method in methods:
        method.decorator_list = []
        method.returns = None
        for arg in method.args.posonlyargs + method.args.args + method.args.kwonlyargs:
            arg.annotation = None

    class _Base:
        def _prepare_pf_running_state(self, saved_chunk_prefill_first, saved_running, saved_max_reqs):
            return [], 1, []

        def schedule(self):
            # Mirror the upstream waiting-request path: prefix lookup happens
            # inside schedule(), then _update_after_schedule advances the
            # request through the 669-token suffix before returning.
            request = self.waiting.pop(0)
            request.num_computed_tokens = 6144 + 669
            request.is_prefill_chunk = False
            self.running.append(request)
            return SimpleNamespace(
                total_num_scheduled_tokens=669,
                num_scheduled_tokens={request.request_id: 669},
            )

        def _register_pd_flight(self, scheduler_output):
            return None

        def _should_ahead_schedule(self, request, is_last):
            return not is_last

        def _cleanup_request_flight_state(self, request_id):
            self._pending_tail_count.pop(request_id, None)
            self._ahead_chunk_count.pop(request_id, None)
            self._prefill_flight_by_token = {
                token: flight
                for token, flight in self._prefill_flight_by_token.items()
                if flight.request_id != request_id
            }

    harness = ast.ClassDef(
        name="_Harness",
        bases=[ast.Name(id="_Base", ctx=ast.Load())],
        keywords=[],
        body=methods,
        decorator_list=[],
    )
    module = ast.fix_missing_locations(ast.Module(body=[harness], type_ignores=[]))
    namespace = {
        "_Base": _Base,
        "BatchType": SimpleNamespace(EMPTY="empty", PREFILL_FIRST="prefill_first"),
        "PrefillChunkFlight": lambda **kwargs: SimpleNamespace(**kwargs),
        "logger": SimpleNamespace(info=lambda *args, **kwargs: None),
        "uuid4": lambda: SimpleNamespace(hex="prefix-hit-flight"),
    }
    exec(compile(module, str(SCHEDULER), "exec"), namespace)
    return namespace["_Harness"]


def test_prefix_cached_waiting_request_marks_its_only_suffix_chunk_last() -> None:
    scheduler = _make_pick_prefill_harness()()
    request = SimpleNamespace(
        request_id="prefix-hit-request",
        num_prompt_tokens=6813,
        num_computed_tokens=0,
        is_prefill_chunk=True,
        chunk_num=1,
    )
    scheduler.running = []
    scheduler.chunk_prefill_first = []
    scheduler.waiting = [request]
    scheduler.max_num_running_reqs = 128
    scheduler.limit_prefill_batch_size = False
    scheduler.chunk_prefill_prior_enable = True
    scheduler.next_prefill_prior_enable = True
    scheduler.prefill_inflight_count = 0
    scheduler.prefill_last_pending = []
    scheduler._prefill_flight_by_token = {}
    scheduler._pending_tail_count = {}
    scheduler._ahead_chunk_count = {}
    scheduler.requests = {request.request_id: request}
    scheduler.hidden_channel_manager = SimpleNamespace(allocate_prefill=lambda head_token: "prefill_2")

    output = scheduler._pick_prefill_first_batch()
    flight = scheduler._prefill_flight_by_token[output.head_token]

    assert flight.is_last_chunk is True
    assert request in scheduler.prefill_last_pending
    assert request not in scheduler.chunk_prefill_first

    scheduler._update_from_output_prefill_last_chunk_prior(output)

    assert request in scheduler.running
    assert request.request_id not in scheduler._pending_tail_count
    assert output.head_token not in scheduler._prefill_flight_by_token
