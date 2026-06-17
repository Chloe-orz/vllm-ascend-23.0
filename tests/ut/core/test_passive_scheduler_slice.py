# SPDX-License-Identifier: Apache-2.0
"""Unit tests for PassiveScheduler layer-slice boundary computation."""

import pytest

from vllm_ascend.core.passive_scheduler import PassiveScheduler


class TestComputeSliceBoundaries:
    """Tests for PassiveScheduler._compute_slice_boundaries."""

    @staticmethod
    def _sizes(boundaries: list[tuple[int, int]]) -> list[int]:
        return [end - start for start, end in boundaries]

    def test_example_62_layers_5_slices(self):
        """62 local layers / 5 slices -> [13, 13, 12, 12, 12]."""
        boundaries = PassiveScheduler._compute_slice_boundaries(62, 5)
        sizes = self._sizes(boundaries)
        assert sizes == [13, 13, 12, 12, 12]
        assert sum(sizes) == 62

    def test_example_60_layers_5_slices(self):
        """60 local layers / 5 slices -> [12, 12, 12, 12, 12]."""
        boundaries = PassiveScheduler._compute_slice_boundaries(60, 5)
        sizes = self._sizes(boundaries)
        assert sizes == [12, 12, 12, 12, 12]
        assert sum(sizes) == 60

    def test_example_61_layers_5_slices(self):
        """61 local layers / 5 slices -> [13, 12, 12, 12, 12]."""
        boundaries = PassiveScheduler._compute_slice_boundaries(61, 5)
        sizes = self._sizes(boundaries)
        assert sizes == [13, 12, 12, 12, 12]
        assert sum(sizes) == 61

    def test_example_63_layers_5_slices(self):
        """63 local layers / 5 slices -> [13, 13, 13, 12, 12]."""
        boundaries = PassiveScheduler._compute_slice_boundaries(63, 5)
        sizes = self._sizes(boundaries)
        assert sizes == [13, 13, 13, 12, 12]
        assert sum(sizes) == 63

    def test_single_slice(self):
        """All layers in one slice."""
        boundaries = PassiveScheduler._compute_slice_boundaries(62, 1)
        sizes = self._sizes(boundaries)
        assert sizes == [62]
        assert sum(sizes) == 62

    def test_each_layer_one_slice(self):
        """62 layers / 62 slices -> 62 slices of size 1."""
        boundaries = PassiveScheduler._compute_slice_boundaries(62, 62)
        sizes = self._sizes(boundaries)
        assert sizes == [1] * 62
        assert sum(sizes) == 62

    def test_more_slices_than_layers(self):
        """5 layers / 10 slices -> first 5 slices size 1, rest size 0."""
        boundaries = PassiveScheduler._compute_slice_boundaries(5, 10)
        sizes = self._sizes(boundaries)
        assert sizes == [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
        assert sum(sizes) == 5

    def test_zero_layers(self):
        """Zero local layers -> empty boundaries."""
        boundaries = PassiveScheduler._compute_slice_boundaries(0, 5)
        assert boundaries == []

    def test_zero_slices(self):
        """Zero slices -> empty boundaries."""
        boundaries = PassiveScheduler._compute_slice_boundaries(62, 0)
        assert boundaries == []

    def test_size_difference_at_most_one(self):
        """For any valid input, max(slice_size) - min(slice_size) <= 1."""
        for num_layers in [1, 7, 13, 29, 62, 100]:
            for num_slices in [1, 2, 3, 5, 7, 10, 13, num_layers, num_layers + 5]:
                boundaries = PassiveScheduler._compute_slice_boundaries(
                    num_layers, num_slices
                )
                if not boundaries:
                    continue
                sizes = self._sizes(boundaries)
                assert max(sizes) - min(sizes) <= 1, (
                    f"num_layers={num_layers}, num_slices={num_slices}, "
                    f"sizes={sizes}"
                )
                assert sum(sizes) == num_layers, (
                    f"sum mismatch: {sum(sizes)} != {num_layers}"
                )

    def test_larger_slices_come_first(self):
        """Slice sizes must be non-increasing."""
        for num_layers in [1, 10, 50, 99]:
            for num_slices in [1, 3, 7, 11, 20]:
                boundaries = PassiveScheduler._compute_slice_boundaries(
                    num_layers, num_slices
                )
                if not boundaries:
                    continue
                sizes = self._sizes(boundaries)
                for i in range(len(sizes) - 1):
                    assert sizes[i] >= sizes[i + 1], (
                        f"sizes not non-increasing: {sizes}"
                    )
