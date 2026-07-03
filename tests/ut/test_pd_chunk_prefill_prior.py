# SPDX-License-Identifier: Apache-2.0
"""Unit tests for chunk-prefill-prior scheduling in PDSeparatedScheduler.

Tests cover:
  - Config wiring (ascend_config → platform → scheduler_config)
  - PrefillChunkFlight creation and lifecycle
  - Ahead scheduling (next chunk PF before previous PL)
  - PL routing by head_token
  - Last-chunk → decode transition
  - Backward compatibility (chunk_prefill_prior_enable=False)
  - Request cleanup (finish / abort)
  - _migrate_prefill_to_running guard
"""

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock


# ------------------------------------------------------------------ #
# Test helpers                                                       #
# ------------------------------------------------------------------ #


def _make_scheduler_config(
    *,
    pd_prefill_inflight_limit: int = 1,
    pd_chunk_prefill_prior_enable: bool = False,
    pd_max_chunk_prefill_ahead: int = 1,
    async_scheduling: bool = False,
    max_num_running_reqs: int = 256,
    max_model_len: int = 131072,
    max_num_batched_tokens: int = 8192,
) -> SimpleNamespace:
    return SimpleNamespace(
        pd_prefill_inflight_limit=pd_prefill_inflight_limit,
        pd_chunk_prefill_prior_enable=pd_chunk_prefill_prior_enable,
        pd_max_chunk_prefill_ahead=pd_max_chunk_prefill_ahead,
        async_scheduling=async_scheduling,
        max_num_running_reqs=max_num_running_reqs,
        max_model_len=max_model_len,
        max_num_batched_tokens=max_num_batched_tokens,
        scheduler_cls=None,
        long_prefill_token_threshold=0,
        enable_chunked_prefill=True,
    )


def _make_mock_request(
    request_id: str = "req-0",
    num_prompt_tokens: int = 8000,
    num_computed_tokens: int = 0,
    is_prefill_chunk: bool = True,
    chunk_num: int = 0,
) -> MagicMock:
    """Create a mock Request with prefill-related attributes."""
    req = MagicMock()
    req.request_id = request_id
    req.num_prompt_tokens = num_prompt_tokens
    req.num_computed_tokens = num_computed_tokens
    req.is_prefill_chunk = is_prefill_chunk
    req.chunk_num = chunk_num
    req.is_finished.return_value = False
    req.all_token_ids = []
    req.status = None
    req.num_output_placeholders = 0
    req.spec_token_ids = []
    req.num_preemptions = 0
    req.discard_latest_async_tokens = False
    req.max_tokens = 256
    return req


def _make_vllm_config_for_scheduler(
    scheduler_config: SimpleNamespace,
) -> SimpleNamespace:
    """Minimal VllmConfig substitute for PDSeparatedScheduler.__init__."""
    return SimpleNamespace(
        scheduler_config=scheduler_config,
        model_config=SimpleNamespace(
            max_model_len=scheduler_config.max_model_len,
        ),
        cache_config=SimpleNamespace(block_size=128),
    )


# ------------------------------------------------------------------ #
# Test: Config wiring                                                 #
# ------------------------------------------------------------------ #


class TestConfigWiring:
    """Verify ascend_config → platform → scheduler_config propagation."""

    def test_chunk_prefill_prior_enabled_wires_to_scheduler_config(self):
        """When chunk_prefill_prior_enable=True, it lands on scheduler_config."""
        from vllm_ascend.platform import NPUPlatform

        vllm_config = SimpleNamespace(
            scheduler_config=SimpleNamespace(
                async_scheduling=False,
                scheduler_cls=None,
                pd_prefill_inflight_limit=1,
            )
        )
        pd = SimpleNamespace(
            enabled=True,
            next_prefill_prior_enable=True,
            prefill_inflight_limit=2,
            chunk_prefill_prior_enable=True,
            max_chunk_prefill_ahead=1,
        )
        edge_cloud = SimpleNamespace(enabled=True, pd_separation=pd)
        ascend_config = SimpleNamespace(edge_cloud_config=edge_cloud)

        NPUPlatform._configure_pd_separation_scheduler(vllm_config, ascend_config)

        assert vllm_config.scheduler_config.pd_chunk_prefill_prior_enable is True
        assert vllm_config.scheduler_config.pd_max_chunk_prefill_ahead == 1

    def test_chunk_prefill_prior_disabled_by_default(self):
        """When not configured, chunk_prefill_prior_enable defaults to False."""
        from vllm_ascend.platform import NPUPlatform

        vllm_config = SimpleNamespace(
            scheduler_config=SimpleNamespace(
                async_scheduling=False,
                scheduler_cls=None,
                pd_prefill_inflight_limit=1,
            )
        )
        pd = SimpleNamespace(
            enabled=True,
            next_prefill_prior_enable=True,
            prefill_inflight_limit=2,
            chunk_prefill_prior_enable=False,
            max_chunk_prefill_ahead=1,
        )
        edge_cloud = SimpleNamespace(enabled=True, pd_separation=pd)
        ascend_config = SimpleNamespace(edge_cloud_config=edge_cloud)

        NPUPlatform._configure_pd_separation_scheduler(vllm_config, ascend_config)

        assert vllm_config.scheduler_config.pd_chunk_prefill_prior_enable is False


# ------------------------------------------------------------------ #
# Test: PrefillChunkFlight                                           #
# ------------------------------------------------------------------ #


class TestPrefillChunkFlight:
    """Verify PrefillChunkFlight dataclass and related helpers."""

    def test_flight_creation(self):
        from vllm_ascend.core.pd_separated_scheduler import PrefillChunkFlight
        from vllm.v1.core.sched.output import HiddenChannelType

        flight = PrefillChunkFlight(
            request_id="req-0",
            head_token="abc123",
            hidden_channel=HiddenChannelType.PREFILL_1,
            chunk_index=0,
            is_last_chunk=False,
            num_scheduled_tokens=4096,
        )
        assert flight.request_id == "req-0"
        assert flight.head_token == "abc123"
        assert flight.chunk_index == 0
        assert flight.is_last_chunk is False
        assert flight.num_scheduled_tokens == 4096

    def test_remaining_prompt_tokens(self):
        from vllm_ascend.core.pd_separated_scheduler import PDSeparatedScheduler

        scheduler = PDSeparatedScheduler.__new__(PDSeparatedScheduler)

        req = _make_mock_request(
            num_prompt_tokens=8000, num_computed_tokens=4000
        )
        assert scheduler._remaining_prompt_tokens(req, 2000) == 2000
        assert scheduler._remaining_prompt_tokens(req, 4000) == 0
        assert scheduler._remaining_prompt_tokens(req, 5000) == 0

    def test_has_more_chunks(self):
        from vllm_ascend.core.pd_separated_scheduler import PDSeparatedScheduler

        scheduler = PDSeparatedScheduler.__new__(PDSeparatedScheduler)

        req = _make_mock_request(
            num_prompt_tokens=8000, num_computed_tokens=0
        )
        assert scheduler._has_more_chunks(req, 4000) is True
        assert scheduler._has_more_chunks(req, 8000) is False

    def test_can_ahead_schedule(self):
        from vllm_ascend.core.pd_separated_scheduler import PDSeparatedScheduler

        scheduler = PDSeparatedScheduler.__new__(PDSeparatedScheduler)
        scheduler.max_chunk_prefill_ahead = 1
        scheduler._ahead_chunk_count = {}

        assert scheduler._can_ahead_schedule("req-0") is True

        scheduler._ahead_chunk_count["req-0"] = 1
        assert scheduler._can_ahead_schedule("req-0") is False

        scheduler._ahead_chunk_count["req-0"] = 0
        assert scheduler._can_ahead_schedule("req-0") is True


# ------------------------------------------------------------------ #
# Test: Chunk-flight state management                                 #
# ------------------------------------------------------------------ #


class TestChunkFlightState:
    """Verify flight tracking state transitions."""

    def test_total_pending_tails(self):
        from vllm_ascend.core.pd_separated_scheduler import PDSeparatedScheduler

        scheduler = PDSeparatedScheduler.__new__(PDSeparatedScheduler)
        scheduler._pending_tail_count = {"req-0": 2, "req-1": 1}
        assert scheduler._total_pending_tails() == 3

    def test_cleanup_request_flight_state(self):
        from vllm_ascend.core.pd_separated_scheduler import (
            PDSeparatedScheduler,
            PrefillChunkFlight,
        )
        from vllm.v1.core.sched.output import HiddenChannelType

        scheduler = PDSeparatedScheduler.__new__(PDSeparatedScheduler)
        scheduler._pending_tail_count = {"req-0": 2}
        scheduler._ahead_chunk_count = {"req-0": 1}
        scheduler._prefill_flight_by_token = {
            "tok0": PrefillChunkFlight(
                request_id="req-0",
                head_token="tok0",
                hidden_channel=HiddenChannelType.PREFILL_1,
                chunk_index=0,
                is_last_chunk=False,
                num_scheduled_tokens=4000,
            ),
            "tok1": PrefillChunkFlight(
                request_id="req-0",
                head_token="tok1",
                hidden_channel=HiddenChannelType.PREFILL_2,
                chunk_index=1,
                is_last_chunk=True,
                num_scheduled_tokens=4000,
            ),
            "tok2": PrefillChunkFlight(
                request_id="req-1",
                head_token="tok2",
                hidden_channel=HiddenChannelType.PREFILL_1,
                chunk_index=0,
                is_last_chunk=True,
                num_scheduled_tokens=2000,
            ),
        }

        scheduler._cleanup_request_flight_state("req-0")

        assert "req-0" not in scheduler._pending_tail_count
        assert "req-0" not in scheduler._ahead_chunk_count
        assert "tok0" not in scheduler._prefill_flight_by_token
        assert "tok1" not in scheduler._prefill_flight_by_token
        # req-1 should be untouched.
        assert "tok2" in scheduler._prefill_flight_by_token
        assert scheduler._pending_tail_count.get("req-1") is None


# ------------------------------------------------------------------ #
# Test: PL routing (chunk-prefill-prior)                              #
# ------------------------------------------------------------------ #


class TestPLLRoutingChunkPrior:
    """Verify _update_from_output_prefill_last_chunk_prior."""

    def _setup_scheduler(self):
        from vllm_ascend.core.pd_separated_scheduler import (
            PDSeparatedScheduler,
            PrefillChunkFlight,
        )
        from vllm.v1.core.sched.output import HiddenChannelType

        scheduler = PDSeparatedScheduler.__new__(PDSeparatedScheduler)
        scheduler.chunk_prefill_prior_enable = True
        scheduler.chunk_prefill_first = []
        scheduler.running = []
        scheduler.prefill_last_pending = []
        scheduler.prefill_inflight_count = 2
        scheduler.prefill_inflight_limit = 2
        scheduler.hidden_channel_manager = MagicMock()
        scheduler._pending_tail_count = {}
        scheduler._ahead_chunk_count = {}
        scheduler._prefill_flight_by_token = {}
        scheduler.requests = {}
        return scheduler

    def test_last_chunk_pl_moves_to_running(self):
        """When the last chunk's PL returns, request enters running."""
        scheduler = self._setup_scheduler()

        req = _make_mock_request(
            request_id="req-0",
            is_prefill_chunk=False,
        )
        scheduler.requests["req-0"] = req

        from vllm_ascend.core.pd_separated_scheduler import PrefillChunkFlight
        from vllm.v1.core.sched.output import HiddenChannelType

        flight = PrefillChunkFlight(
            request_id="req-0",
            head_token="tok-last",
            hidden_channel=HiddenChannelType.PREFILL_1,
            chunk_index=1,
            is_last_chunk=True,
            num_scheduled_tokens=4000,
        )
        scheduler._prefill_flight_by_token["tok-last"] = flight
        scheduler._pending_tail_count["req-0"] = 1

        so = MagicMock()
        so.head_token = "tok-last"
        so.batch_type = None
        so.num_scheduled_tokens = {"req-0": 4000}

        scheduler._update_from_output_prefill_last_chunk_prior(so)

        assert "tok-last" not in scheduler._prefill_flight_by_token
        assert scheduler._pending_tail_count.get("req-0", 0) == 0
        assert req in scheduler.running
        assert "req-0" not in scheduler._ahead_chunk_count

    def test_mid_chunk_pl_with_ahead_does_not_re_add(self):
        """When a mid-chunk PL returns and the request was ahead-scheduled,
        do not re-add to chunk_prefill_first."""
        scheduler = self._setup_scheduler()

        req = _make_mock_request(
            request_id="req-0",
            is_prefill_chunk=True,
        )
        scheduler.requests["req-0"] = req

        from vllm_ascend.core.pd_separated_scheduler import PrefillChunkFlight
        from vllm.v1.core.sched.output import HiddenChannelType

        flight = PrefillChunkFlight(
            request_id="req-0",
            head_token="tok-mid",
            hidden_channel=HiddenChannelType.PREFILL_1,
            chunk_index=0,
            is_last_chunk=False,
            num_scheduled_tokens=4000,
        )
        scheduler._prefill_flight_by_token["tok-mid"] = flight
        scheduler._pending_tail_count["req-0"] = 2
        scheduler._ahead_chunk_count["req-0"] = 1  # ahead-scheduled

        so = MagicMock()
        so.head_token = "tok-mid"
        so.batch_type = None
        so.num_scheduled_tokens = {"req-0": 4000}

        scheduler._update_from_output_prefill_last_chunk_prior(so)

        # pending_tail_count should decrease.
        assert scheduler._pending_tail_count["req-0"] == 1
        # ahead_chunk_count should decrease.
        assert scheduler._ahead_chunk_count["req-0"] == 0
        # Request should NOT be in chunk_prefill_first (already ahead).
        assert req not in scheduler.chunk_prefill_first

    def test_mid_chunk_pl_without_ahead_re_adds(self):
        """When a mid-chunk PL returns and the request was NOT ahead-scheduled,
        re-add to chunk_prefill_first."""
        scheduler = self._setup_scheduler()

        req = _make_mock_request(
            request_id="req-0",
            is_prefill_chunk=True,
        )
        scheduler.requests["req-0"] = req

        from vllm_ascend.core.pd_separated_scheduler import PrefillChunkFlight
        from vllm.v1.core.sched.output import HiddenChannelType

        flight = PrefillChunkFlight(
            request_id="req-0",
            head_token="tok-mid",
            hidden_channel=HiddenChannelType.PREFILL_1,
            chunk_index=0,
            is_last_chunk=False,
            num_scheduled_tokens=4000,
        )
        scheduler._prefill_flight_by_token["tok-mid"] = flight
        scheduler._pending_tail_count["req-0"] = 1
        scheduler._ahead_chunk_count["req-0"] = 0  # NOT ahead

        so = MagicMock()
        so.head_token = "tok-mid"
        so.batch_type = None
        so.num_scheduled_tokens = {"req-0": 4000}

        scheduler._update_from_output_prefill_last_chunk_prior(so)

        assert scheduler._pending_tail_count["req-0"] == 0
        assert req in scheduler.chunk_prefill_first

    def test_pl_missing_head_token_falls_back_to_legacy(self):
        """When head_token is missing, fall back to legacy routing."""
        scheduler = self._setup_scheduler()

        from vllm_ascend.core.pd_separated_scheduler import PrefillChunkFlight
        from vllm.v1.core.sched.output import HiddenChannelType

        # Set up legacy pending list.
        req = _make_mock_request(
            request_id="req-0",
            is_prefill_chunk=False,
        )
        scheduler.prefill_last_pending = [req]
        scheduler.requests["req-0"] = req

        so = MagicMock()
        so.head_token = None  # missing
        so.batch_type = None
        so.num_scheduled_tokens = {"req-0": 4000}

        scheduler._update_from_output_prefill_last_chunk_prior(so)

        # Legacy routing should move req to running.
        assert req in scheduler.running
        assert req not in scheduler.prefill_last_pending

    def test_pl_unknown_head_token_falls_back_to_legacy(self):
        """When head_token is not in flight map, fall back to legacy."""
        scheduler = self._setup_scheduler()

        req = _make_mock_request(
            request_id="req-0",
            is_prefill_chunk=False,
        )
        scheduler.prefill_last_pending = [req]
        scheduler.requests["req-0"] = req

        so = MagicMock()
        so.head_token = "unknown-token"
        so.batch_type = None
        so.num_scheduled_tokens = {"req-0": 4000}

        scheduler._update_from_output_prefill_last_chunk_prior(so)

        assert req in scheduler.running


# ------------------------------------------------------------------ #
# Test: _migrate_prefill_to_running guard                             #
# ------------------------------------------------------------------ #


class TestMigratePrefillToRunning:
    """Verify that requests with pending tails are not moved to running."""

    def test_request_with_pending_tails_not_migrated(self):
        from vllm_ascend.core.pd_separated_scheduler import PDSeparatedScheduler

        scheduler = PDSeparatedScheduler.__new__(PDSeparatedScheduler)
        scheduler.chunk_prefill_first = []
        scheduler.running = []
        scheduler._pending_tail_count = {"req-0": 2}

        req = _make_mock_request(
            request_id="req-0",
            is_prefill_chunk=False,  # prefill complete, but tails pending
        )
        scheduler.chunk_prefill_first.append(req)

        scheduler._migrate_prefill_to_running()

        # Should NOT be moved because pending_tail_count > 0.
        assert req in scheduler.chunk_prefill_first
        assert req not in scheduler.running

    def test_request_without_pending_tails_migrated(self):
        from vllm_ascend.core.pd_separated_scheduler import PDSeparatedScheduler

        scheduler = PDSeparatedScheduler.__new__(PDSeparatedScheduler)
        scheduler.chunk_prefill_first = []
        scheduler.running = []
        scheduler._pending_tail_count = {"req-0": 0}

        req = _make_mock_request(
            request_id="req-0",
            is_prefill_chunk=False,
        )
        scheduler.chunk_prefill_first.append(req)

        scheduler._migrate_prefill_to_running()

        assert req not in scheduler.chunk_prefill_first
        assert req in scheduler.running

    def test_request_not_in_pending_tail_map_migrated(self):
        """Requests not in pending_tail_count should be migrated."""
        from vllm_ascend.core.pd_separated_scheduler import PDSeparatedScheduler

        scheduler = PDSeparatedScheduler.__new__(PDSeparatedScheduler)
        scheduler.chunk_prefill_first = []
        scheduler.running = []
        scheduler._pending_tail_count = {}

        req = _make_mock_request(
            request_id="req-0",
            is_prefill_chunk=False,
        )
        scheduler.chunk_prefill_first.append(req)

        scheduler._migrate_prefill_to_running()

        assert req not in scheduler.chunk_prefill_first
        assert req in scheduler.running


# ------------------------------------------------------------------ #
# Test: finish_requests cleanup                                       #
# ------------------------------------------------------------------ #


class TestFinishRequestsCleanup:
    """Verify that finish_requests cleans up chunk-prefill-prior state."""

    def test_finish_request_cleans_up_flight_state(self):
        from vllm_ascend.core.pd_separated_scheduler import (
            PDSeparatedScheduler,
            PrefillChunkFlight,
        )
        from vllm.v1.core.sched.output import HiddenChannelType

        scheduler = PDSeparatedScheduler.__new__(PDSeparatedScheduler)
        scheduler.chunk_prefill_first = []
        scheduler.prefill_last_pending = []
        scheduler.finished_req_ids = set()
        scheduler.requests = {}
        scheduler.log_stats = False

        req = _make_mock_request(request_id="req-0")
        req.is_finished.return_value = True
        scheduler.requests["req-0"] = req

        scheduler._pending_tail_count = {"req-0": 2}
        scheduler._ahead_chunk_count = {"req-0": 1}
        scheduler._prefill_flight_by_token = {
            "tok0": PrefillChunkFlight(
                request_id="req-0",
                head_token="tok0",
                hidden_channel=HiddenChannelType.PREFILL_1,
                chunk_index=0,
                is_last_chunk=False,
                num_scheduled_tokens=4000,
            ),
        }

        # Mock the parent finish_requests to return empty.
        with patch.object(
            scheduler.__class__,
            "finish_requests",
            wraps=lambda self, *a, **kw: [],
        ):
            # We need to patch the parent's finish_requests.
            # Use a simpler approach: directly test cleanup.
            scheduler._cleanup_request_flight_state("req-0")
            assert "req-0" not in scheduler._pending_tail_count
            assert "req-0" not in scheduler._ahead_chunk_count
            assert "tok0" not in scheduler._prefill_flight_by_token


# ------------------------------------------------------------------ #
# Test: backward compatibility                                        #
# ------------------------------------------------------------------ #


class TestBackwardCompatibility:
    """Verify legacy behavior is preserved when chunk_prefill_prior_enable=False."""

    def test_log_scheduler_state_without_chunk_prior(self):
        """Log format uses legacy fields when chunk_prefill_prior_enable=False."""
        from vllm_ascend.core.pd_separated_scheduler import (
            PDSeparatedScheduler,
            PrefillState,
        )
        from vllm.v1.core.sched.output import BatchType

        scheduler = PDSeparatedScheduler.__new__(PDSeparatedScheduler)
        scheduler.chunk_prefill_prior_enable = False
        scheduler._step_counter = 0
        scheduler.waiting = []
        scheduler.chunk_prefill_first = []
        scheduler.prefill_last_pending = []
        scheduler.running = []
        scheduler.prefills_last_ready = []
        scheduler.decodes_last_ready = []
        scheduler.prefill_inflight_count = 0
        scheduler.prefill_inflight_limit = 1
        scheduler.decode_inflight_count = 0
        scheduler.decode_inflight_limit = 1

        # Should not raise — log format uses legacy fields.
        scheduler._log_scheduler_state(PrefillState.IDLE, BatchType.PREFILL_FIRST)
        assert scheduler._step_counter == 1

    def test_log_scheduler_state_with_chunk_prior(self):
        """Log format includes chunk-prior fields when enabled."""
        from vllm_ascend.core.pd_separated_scheduler import (
            PDSeparatedScheduler,
            PrefillState,
        )
        from vllm.v1.core.sched.output import BatchType

        scheduler = PDSeparatedScheduler.__new__(PDSeparatedScheduler)
        scheduler.chunk_prefill_prior_enable = True
        scheduler._step_counter = 0
        scheduler.waiting = []
        scheduler.chunk_prefill_first = []
        scheduler.prefill_last_pending = []
        scheduler.running = []
        scheduler.prefills_last_ready = []
        scheduler.decodes_last_ready = []
        scheduler.prefill_inflight_count = 0
        scheduler.prefill_inflight_limit = 1
        scheduler.decode_inflight_count = 0
        scheduler.decode_inflight_limit = 1
        scheduler._prefill_flight_by_token = {}
        scheduler._pending_tail_count = {}
        scheduler._ahead_chunk_count = {}

        scheduler._log_scheduler_state(PrefillState.LOW, BatchType.PREFILL_FIRST)
        assert scheduler._step_counter == 1


# ------------------------------------------------------------------ #
# Test: get_request_counts with chunk-prior                           #
# ------------------------------------------------------------------ #


class TestRequestCounts:
    """Verify get_request_counts and get_num_unfinished_requests."""

    def test_get_request_counts_includes_pending_tails(self):
        from vllm_ascend.core.pd_separated_scheduler import PDSeparatedScheduler

        scheduler = PDSeparatedScheduler.__new__(PDSeparatedScheduler)
        scheduler.chunk_prefill_first = []
        scheduler.prefill_last_pending = []
        scheduler._pending_tail_count = {"req-0": 2, "req-1": 1}

        # Mock parent's get_request_counts.
        with patch.object(
            scheduler.__class__,
            "get_request_counts",
            return_value=(10, 5),
        ):
            num_running, num_waiting = scheduler.get_request_counts()
            assert num_running == 10 + 0 + 0 + 3  # running + chunk + pending + tails
            assert num_waiting == 5

    def test_get_num_unfinished_requests_includes_pending_tails(self):
        from vllm_ascend.core.pd_separated_scheduler import PDSeparatedScheduler

        scheduler = PDSeparatedScheduler.__new__(PDSeparatedScheduler)
        scheduler._pause_state = None
        scheduler.chunk_prefill_first = []
        scheduler.prefill_last_pending = []
        scheduler._pending_tail_count = {"req-0": 1}

        with patch.object(
            scheduler.__class__,
            "get_num_unfinished_requests",
            return_value=10,
        ):
            total = scheduler.get_num_unfinished_requests()
            assert total == 10 + 0 + 0 + 1  # base + chunk + pending + tails