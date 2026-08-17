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
#

import sys
import types
from unittest.mock import MagicMock, patch

from tests.ut.base import TestBase
from vllm_ascend.profiler.msmemscope_profiler import MsMemScopeProfiler


def _make_fake_msmemscope():
    """Build a fake ``msmemscope`` module with the API surface we use."""
    fake = types.ModuleType("msmemscope")
    fake.config = MagicMock()
    fake.start = MagicMock()
    fake.stop = MagicMock()
    fake.take_snapshot = MagicMock()
    fake.RecordFunction = MagicMock()
    return fake


class TestMsMemScopeProfiler(TestBase):
    """Unit tests for the MsMemScopeProfiler wrapper."""

    def setUp(self):
        super().setUp()
        # Each test gets a fresh instance so started/import state does not
        # leak across tests.
        self.profiler = MsMemScopeProfiler()

    def test_get_instance_returns_singleton(self):
        with patch.object(MsMemScopeProfiler, "_instance", None):
            a = MsMemScopeProfiler.get_instance()
            b = MsMemScopeProfiler.get_instance()
            self.assertIs(a, b)

    def test_start_noop_when_package_missing(self):
        with patch.object(self.profiler, "_import_msmemscope", return_value=None):
            result = self.profiler.start(output_path="/tmp/out")
        self.assertFalse(result)
        self.assertFalse(self.profiler.started)

    def test_start_calls_config_and_start(self):
        fake = _make_fake_msmemscope()
        with patch.object(self.profiler, "_import_msmemscope", return_value=fake):
            result = self.profiler.start(output_path="/tmp/out")
        self.assertTrue(result)
        self.assertTrue(self.profiler.started)
        fake.config.assert_called_once()
        fake.start.assert_called_once()
        config_kwargs = fake.config.call_args.kwargs
        self.assertEqual(config_kwargs["output"], "/tmp/out")
        self.assertEqual(config_kwargs["analysis"], "leaks,decompose")
        self.assertEqual(config_kwargs["device"], "npu")

    def test_start_with_config_overrides(self):
        fake = _make_fake_msmemscope()
        with patch.object(self.profiler, "_import_msmemscope", return_value=fake):
            self.profiler.start(
                output_path=None,
                config={"events": "alloc", "level": "kernel"},
            )
        config_kwargs = fake.config.call_args.kwargs
        self.assertEqual(config_kwargs["events"], "alloc")
        self.assertEqual(config_kwargs["level"], "kernel")
        # Unmodified defaults are preserved.
        self.assertEqual(config_kwargs["device"], "npu")

    def test_start_skips_when_already_started(self):
        fake = _make_fake_msmemscope()
        with patch.object(self.profiler, "_import_msmemscope", return_value=fake):
            self.profiler.start()
            result = self.profiler.start()
        self.assertFalse(result)
        fake.config.assert_called_once()
        fake.start.assert_called_once()

    def test_start_swallows_config_exception(self):
        fake = _make_fake_msmemscope()
        fake.config.side_effect = RuntimeError("boom")
        with patch.object(self.profiler, "_import_msmemscope", return_value=fake):
            result = self.profiler.start()
        self.assertFalse(result)
        self.assertFalse(self.profiler.started)

    def test_stop_noop_when_not_started(self):
        fake = _make_fake_msmemscope()
        with patch.object(self.profiler, "_import_msmemscope", return_value=fake):
            self.profiler.stop()
        fake.stop.assert_not_called()

    def test_stop_calls_underlying_stop(self):
        fake = _make_fake_msmemscope()
        with patch.object(self.profiler, "_import_msmemscope", return_value=fake):
            self.profiler.start()
            self.profiler.stop()
        fake.stop.assert_called_once()
        self.assertFalse(self.profiler.started)

    def test_stop_swallows_exception(self):
        fake = _make_fake_msmemscope()
        fake.stop.side_effect = RuntimeError("boom")
        with patch.object(self.profiler, "_import_msmemscope", return_value=fake):
            self.profiler.start()
            self.profiler.stop()
        self.assertFalse(self.profiler.started)

    def test_mark_noop_when_not_started(self):
        fake = _make_fake_msmemscope()
        with patch.object(self.profiler, "_import_msmemscope", return_value=fake):
            with self.profiler.mark("test"):
                pass
        fake.RecordFunction.assert_not_called()

    def test_mark_uses_record_function_when_started(self):
        fake = _make_fake_msmemscope()
        with patch.object(self.profiler, "_import_msmemscope", return_value=fake):
            self.profiler.start()
            with self.profiler.mark("distributed_init"):
                pass
        fake.RecordFunction.assert_called_once_with("distributed_init")

    def test_mark_swallows_record_function_exception(self):
        fake = _make_fake_msmemscope()
        # Make RecordFunction(name) raise when used as a context manager.
        fake.RecordFunction.return_value.__enter__.side_effect = RuntimeError("boom")
        with patch.object(self.profiler, "_import_msmemscope", return_value=fake):
            self.profiler.start()
            # Should not raise even though RecordFunction fails.
            with self.profiler.mark("test"):
                pass

    def test_snapshot_noop_when_not_started(self):
        fake = _make_fake_msmemscope()
        with patch.object(self.profiler, "_import_msmemscope", return_value=fake):
            self.profiler.snapshot(name="test")
        fake.take_snapshot.assert_not_called()

    def test_snapshot_calls_take_snapshot(self):
        fake = _make_fake_msmemscope()
        with patch.object(self.profiler, "_import_msmemscope", return_value=fake):
            self.profiler.start()
            self.profiler.snapshot(name="after_warmup", device_mask=1)
        fake.take_snapshot.assert_called_once_with(device_mask=1, name="after_warmup")

    def test_snapshot_swallows_exception(self):
        fake = _make_fake_msmemscope()
        fake.take_snapshot.side_effect = RuntimeError("boom")
        with patch.object(self.profiler, "_import_msmemscope", return_value=fake):
            self.profiler.start()
            # Should not raise.
            self.profiler.snapshot()

    def test_import_msmemscope_caches_result(self):
        fake = _make_fake_msmemscope()
        with patch.dict(sys.modules, {"msmemscope": fake}):
            result1 = self.profiler._import_msmemscope()
            result2 = self.profiler._import_msmemscope()
        self.assertIs(result1, fake)
        self.assertIs(result2, fake)


if __name__ == "__main__":
    import unittest
    unittest.main()
