# ==============================================================
# backend/retry.py
# Retry / freeze / error handling wrapper.
# Every connector call passes through this. On failure it
# retries up to MAX_RETRIES times, then freezes the module
# and reports a structured error to the queue for the UI.
# ==============================================================

import asyncio
import os
import traceback
from typing import Callable, Awaitable, Any, Optional

MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))
RETRY_DELAY_SECONDS = 3   # wait between retries


# ==============================================================
# Result dataclasses (plain dicts for simplicity)
# ==============================================================

def success_result(data: Any) -> dict:
    return {"ok": True, "data": data, "error": None}

def error_result(module: str, detail: str,
                 asset_id: Optional[int] = None) -> dict:
    return {
        "ok":       False,
        "data":     None,
        "error": {
            "module":   module,
            "detail":   detail,
            "asset_id": asset_id
        }
    }


# ==============================================================
# Core retry wrapper
# ==============================================================

async def with_retry(
    fn: Callable[[], Awaitable[Any]],
    module: str,
    asset_id: Optional[int] = None,
    max_retries: int = MAX_RETRIES,
    on_retry: Optional[Callable[[int, str], Awaitable[None]]] = None
) -> dict:
    """
    Call an async function with automatic retry on failure.

    Parameters
    ----------
    fn          : async callable that performs the API/generation call.
                  Should return a value on success or raise on failure.
    module      : name of the connector/module (e.g. "kling", "elevenlabs").
                  Used in error reporting.
    asset_id    : optional asset id this call is for. Used in error reporting.
    max_retries : maximum attempts before freezing (default: MAX_RETRIES from .env).
    on_retry    : optional async callback called before each retry attempt.
                  Receives (attempt_number, error_message). Useful for sending
                  a "retrying..." status update to the UI queue.

    Returns
    -------
    dict with keys: ok (bool), data (result or None), error (dict or None)

    Behaviour
    ---------
    - Attempt 1..max_retries: on exception, wait RETRY_DELAY_SECONDS and retry.
    - After max_retries exhausted: return error_result and do NOT raise.
      The pipeline reads ok=False and freezes the project + reports to UI.
    """
    last_error = ""

    for attempt in range(1, max_retries + 1):
        try:
            result = await fn()
            return success_result(result)

        except asyncio.CancelledError:
            # Never suppress task cancellation
            raise

        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            detail = (
                f"[{module}] Attempt {attempt}/{max_retries} failed.\n"
                f"Error: {last_error}\n"
                f"{traceback.format_exc()}"
            )
            print(detail)

            if attempt < max_retries:
                if on_retry:
                    await on_retry(attempt, last_error)
                await asyncio.sleep(RETRY_DELAY_SECONDS)
            else:
                # All retries exhausted
                final_detail = (
                    f"[{module}] All {max_retries} attempts failed. "
                    f"Module frozen.\nLast error: {last_error}"
                )
                print(final_detail)
                return error_result(module, final_detail, asset_id)

    # Should never reach here, but satisfy type checker
    return error_result(module, f"[{module}] Unexpected retry loop exit.", asset_id)


# ==============================================================
# Synchronous convenience wrapper (for non-async contexts)
# ==============================================================

def run_with_retry(
    fn: Callable,
    module: str,
    asset_id: Optional[int] = None,
    max_retries: int = MAX_RETRIES
) -> dict:
    """
    Synchronous version of with_retry for use outside async contexts.
    Wraps a plain (non-async) callable.
    """
    last_error = ""

    for attempt in range(1, max_retries + 1):
        try:
            result = fn()
            return success_result(result)

        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            print(
                f"[{module}] Attempt {attempt}/{max_retries} failed: {last_error}"
            )
            if attempt < max_retries:
                import time
                time.sleep(RETRY_DELAY_SECONDS)

    final_detail = (
        f"[{module}] All {max_retries} attempts failed. "
        f"Module frozen.\nLast error: {last_error}"
    )
    return error_result(module, final_detail, asset_id)
