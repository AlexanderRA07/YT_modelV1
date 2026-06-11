# ==============================================================
# tests/backend/test_asset_targets.py
# Unit tests for asset_targets.py.
# Pure logic — no I/O. All tests are synchronous.
# ==============================================================

import math
import pytest

from backend.asset_targets import (
    get_image_minimum, get_image_target, get_all_targets,
    get_compile_minimums, IMAGE_MINIMUMS, IMAGE_OVERAGE_RATIO
)


# --------------------------------------------------------------
# get_image_minimum
# --------------------------------------------------------------

class TestGetImageMinimum:
    def test_known_values(self):
        assert get_image_minimum("1min")  == 2
        assert get_image_minimum("2min")  == 3
        assert get_image_minimum("10min") == 10
        assert get_image_minimum("15min") == 15

    def test_all_formats_have_positive_minimum(self):
        for fmt in IMAGE_MINIMUMS:
            assert get_image_minimum(fmt) > 0

    def test_unknown_format_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown format"):
            get_image_minimum("5min")


# --------------------------------------------------------------
# get_image_target
# --------------------------------------------------------------

class TestGetImageTarget:
    def test_target_equals_ceiling_of_minimum_times_ratio(self):
        for fmt, minimum in IMAGE_MINIMUMS.items():
            expected = math.ceil(minimum * IMAGE_OVERAGE_RATIO)
            assert get_image_target(fmt) == expected

    def test_target_always_at_least_minimum(self):
        for fmt in IMAGE_MINIMUMS:
            assert get_image_target(fmt) >= get_image_minimum(fmt)

    def test_target_strictly_greater_when_ratio_above_one(self):
        if IMAGE_OVERAGE_RATIO > 1.0:
            for fmt in IMAGE_MINIMUMS:
                assert get_image_target(fmt) > get_image_minimum(fmt)


# --------------------------------------------------------------
# get_all_targets
# --------------------------------------------------------------

class TestGetAllTargets:
    def test_returns_all_required_keys(self):
        targets = get_all_targets("2min")
        for key in ["image", "animation", "voice", "music", "thumbnail", "image_minimum"]:
            assert key in targets

    def test_animation_is_none_on_demand_only(self):
        assert get_all_targets("10min")["animation"] is None

    def test_voice_is_one(self):
        for fmt in IMAGE_MINIMUMS:
            assert get_all_targets(fmt)["voice"] == 1

    def test_music_is_one(self):
        for fmt in IMAGE_MINIMUMS:
            assert get_all_targets(fmt)["music"] == 1

    def test_image_minimum_matches_standalone_function(self):
        for fmt in IMAGE_MINIMUMS:
            targets = get_all_targets(fmt)
            assert targets["image_minimum"] == get_image_minimum(fmt)

    def test_image_target_matches_standalone_function(self):
        for fmt in IMAGE_MINIMUMS:
            targets = get_all_targets(fmt)
            assert targets["image"] == get_image_target(fmt)


# --------------------------------------------------------------
# get_compile_minimums
# --------------------------------------------------------------

class TestGetCompileMinimums:
    def test_animation_minimum_matches_image_minimum(self):
        for fmt in IMAGE_MINIMUMS:
            mins = get_compile_minimums(fmt)
            assert mins["animation"] == mins["image"]

    def test_voice_music_thumbnail_always_one(self):
        for fmt in IMAGE_MINIMUMS:
            mins = get_compile_minimums(fmt)
            assert mins["voice"] == 1
            assert mins["music"] == 1
            assert mins["thumbnail"] == 1

    def test_image_minimum_matches_standalone_function(self):
        for fmt in IMAGE_MINIMUMS:
            mins = get_compile_minimums(fmt)
            assert mins["image"] == get_image_minimum(fmt)
