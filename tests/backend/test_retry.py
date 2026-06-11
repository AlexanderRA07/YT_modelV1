# ==============================================================
# tests/backend/test_retry.py
# Unit tests for the retry wrapper (retry.py).
# Uses pytest-asyncio for async tests.
# ==============================================================

import asyncio
import pytest

from backend.retry import with_retry, success_result, error_result


# --------------------------------------------------------------
# Result helper constructors
# --------------------------------------------------------------

class TestResultHelpers:
    def test_success_result_structure(self):
        r = success_result({"filename": "image1.jpg"})
        assert r["ok"] is True
        assert r["data"] == {"filename": "image1.jpg"}
        assert r["error"] is None

    def test_error_result_structure(self):
        r = error_result("kling", "Connection timeout", asset_id=3)
        assert r["ok"] is False
        assert r["data"] is None
        assert r["error"]["module"] == "kling"
        assert r["error"]["detail"] == "Connection timeout"
        assert r["error"]["asset_id"] == 3

    def test_error_result_without_asset_id(self):
        r = error_result("claude", "Rate limited")
        assert r["error"]["asset_id"] is None


# --------------------------------------------------------------
# with_retry behaviour
# --------------------------------------------------------------

class TestWithRetry:
    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        async def fn():
            return {"filename": "image1.jpg"}

        result = await with_retry(fn, module="test", max_retries=3)
        assert result["ok"] is True
        assert result["data"]["filename"] == "image1.jpg"

    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self):
        calls = []

        async def fn():
            calls.append(1)
            if len(calls) < 3:
                raise ValueError("Not ready yet")
            return "done"

        result = await with_retry(fn, module="test", max_retries=5)
        assert result["ok"] is True
        assert result["data"] == "done"
        assert len(calls) == 3

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_returns_error(self):
        async def fn():
            raise RuntimeError("always fails")

        result = await with_retry(fn, module="flux", max_retries=3)
        assert result["ok"] is False
        assert result["error"]["module"] == "flux"
        assert "All 3 attempts failed" in result["error"]["detail"]

    @pytest.mark.asyncio
    async def test_on_retry_callback_invoked(self):
        retry_log = []

        async def fn():
            raise ValueError("fail")

        async def on_retry(attempt: int, err: str):
            retry_log.append((attempt, err))

        result = await with_retry(fn, module="test", max_retries=3,
                                  on_retry=on_retry)
        assert result["ok"] is False
        # Callback fires before each retry (attempts 1 and 2), not after the final failure
        assert len(retry_log) == 2
        assert retry_log[0][0] == 1
        assert retry_log[1][0] == 2

    @pytest.mark.asyncio
    async def test_cancelled_error_propagates_immediately(self):
        async def fn():
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await with_retry(fn, module="test", max_retries=3)

    @pytest.mark.asyncio
    async def test_asset_id_included_in_error(self):
        async def fn():
            raise IOError("disk error")

        result = await with_retry(fn, module="kling", asset_id=7, max_retries=1)
        assert result["error"]["asset_id"] == 7

    @pytest.mark.asyncio
    async def test_max_retries_one_gives_single_attempt(self):
        calls = []

        async def fn():
            calls.append(1)
            raise Exception("fail")

        await with_retry(fn, module="test", max_retries=1)
        assert len(calls) == 1
