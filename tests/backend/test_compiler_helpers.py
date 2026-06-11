# ==============================================================
# tests/backend/test_compiler_helpers.py
# Unit tests for pure helper functions in compiler.py.
# No MoviePy, no file I/O — just logic.
# ==============================================================

from backend.compiler import _estimate_shot_duration, _format_duration_seconds


# --------------------------------------------------------------
# _estimate_shot_duration
# --------------------------------------------------------------

class TestEstimateShotDuration:
    def test_empty_narration_returns_minimum(self):
        assert _estimate_shot_duration("", "2min") == 3.0

    def test_whitespace_only_returns_minimum(self):
        assert _estimate_shot_duration("   ", "2min") == 3.0

    def test_short_narration_clamped_to_minimum(self):
        # 5 words / 2.5 wps = 2.0s → clamped to 3.0
        assert _estimate_shot_duration("one two three four five", "2min") == 3.0

    def test_normal_narration_word_count(self):
        # 25 words / 2.5 wps = 10.0s — no clamping
        text = " ".join(["word"] * 25)
        assert _estimate_shot_duration(text, "2min") == 10.0

    def test_very_long_narration_clamped_to_maximum(self):
        # 500 words / 2.5 = 200s → clamped to 30.0
        text = " ".join(["word"] * 500)
        assert _estimate_shot_duration(text, "2min") == 30.0

    def test_format_argument_ignored(self):
        # Format does not affect the calculation (driven by word count only)
        text = " ".join(["word"] * 25)
        assert _estimate_shot_duration(text, "1min") == _estimate_shot_duration(text, "15min")


# --------------------------------------------------------------
# _format_duration_seconds
# --------------------------------------------------------------

class TestFormatDurationSeconds:
    def test_one_minute(self):
        assert _format_duration_seconds("1min") == 60.0

    def test_two_minutes(self):
        assert _format_duration_seconds("2min") == 120.0

    def test_ten_minutes(self):
        assert _format_duration_seconds("10min") == 600.0

    def test_fifteen_minutes(self):
        assert _format_duration_seconds("15min") == 900.0

    def test_unknown_format_returns_default(self):
        # Falls back to 120.0 for unrecognised formats
        assert _format_duration_seconds("unknown") == 120.0
        assert _format_duration_seconds("") == 120.0
