# ==============================================================
# backend/queue_worker.py
# Async message queue for safe UI state updates.
# All background generation jobs post update messages here.
# A single worker coroutine consumes one message at a time,
# preventing race conditions when multiple assets finish at once.
# ==============================================================

import asyncio
from typing import Callable, Awaitable, Any, Optional
from datetime import datetime


# ==============================================================
# Message types
# ==============================================================
class MsgType:
    ASSET_STATE_CHANGE  = "asset_state_change"   # asset moved to new state
    ASSET_RETURNED      = "asset_returned"        # asset ready for review
    ASSET_ERROR         = "asset_error"           # asset hit error after retries
    PROJECT_ERROR       = "project_error"         # pipeline-level error, freeze project
    COMPILE_READY       = "compile_ready"         # minimum thresholds met
    STATUS_UPDATE       = "status_update"         # general informational message
    RETRY_NOTICE        = "retry_notice"          # a retry is in progress


# ==============================================================
# Message factory helpers
# ==============================================================

def make_message(msg_type: str, payload: dict) -> dict:
    return {
        "type":      msg_type,
        "payload":   payload,
        "timestamp": datetime.now().isoformat()
    }

def asset_state_msg(asset_id: int, asset_type: str,
                    new_state: str, filename: str = None) -> dict:
    return make_message(MsgType.ASSET_STATE_CHANGE, {
        "asset_id":   asset_id,
        "asset_type": asset_type,
        "new_state":  new_state,
        "filename":   filename
    })

def asset_returned_msg(asset_id: int, asset_type: str,
                       filename: str, prompt: str) -> dict:
    return make_message(MsgType.ASSET_RETURNED, {
        "asset_id":   asset_id,
        "asset_type": asset_type,
        "filename":   filename,
        "prompt":     prompt
    })

def asset_error_msg(asset_id: int, module: str, detail: str) -> dict:
    return make_message(MsgType.ASSET_ERROR, {
        "asset_id": asset_id,
        "module":   module,
        "detail":   detail
    })

def project_error_msg(module: str, detail: str,
                      asset_id: Optional[int] = None) -> dict:
    return make_message(MsgType.PROJECT_ERROR, {
        "module":   module,
        "detail":   detail,
        "asset_id": asset_id
    })

def compile_ready_msg() -> dict:
    return make_message(MsgType.COMPILE_READY, {})

def status_msg(text: str) -> dict:
    return make_message(MsgType.STATUS_UPDATE, {"text": text})

def retry_notice_msg(asset_id: int, module: str,
                     attempt: int, error: str) -> dict:
    return make_message(MsgType.RETRY_NOTICE, {
        "asset_id": asset_id,
        "module":   module,
        "attempt":  attempt,
        "error":    error
    })


# ==============================================================
# QueueWorker
# ==============================================================

class QueueWorker:
    """
    Single-consumer async message queue.

    Background jobs call worker.post(message) to enqueue an update.
    The worker processes one message at a time by calling the registered
    handler, ensuring the UI and project state are never updated concurrently.

    Usage:
        worker = QueueWorker()
        worker.register_handler(my_handler)   # async fn(message) -> None
        await worker.start()                  # begin consuming (runs forever)
        ...
        await worker.post(status_msg("Starting generation"))
        ...
        await worker.stop()
    """

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._handler: Optional[Callable[[dict], Awaitable[None]]] = None
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None

    # ----------------------------------------------------------
    # Handler registration
    # ----------------------------------------------------------
    def register_handler(self, handler: Callable[[dict], Awaitable[None]]):
        """
        Register the async function that processes each message.
        Typically this function updates ProjectState and pushes
        the change to connected websocket clients.

        handler signature: async def handler(message: dict) -> None
        """
        self._handler = handler

    # ----------------------------------------------------------
    # Start / stop
    # ----------------------------------------------------------
    async def start(self):
        """Start the background consumer coroutine."""
        if self._running:
            return
        if self._handler is None:
            raise RuntimeError(
                "QueueWorker: no handler registered. "
                "Call register_handler() before start()."
            )
        self._running = True
        self._task = asyncio.create_task(self._consume())
        print("[QueueWorker] Started.")

    async def stop(self):
        """Gracefully stop the consumer after draining the queue."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print("[QueueWorker] Stopped.")

    # ----------------------------------------------------------
    # Post a message
    # ----------------------------------------------------------
    async def post(self, message: dict):
        """
        Enqueue a message. Called by background generation jobs.
        Non-blocking -- returns immediately after enqueueing.
        """
        await self._queue.put(message)

    def post_nowait(self, message: dict):
        """
        Enqueue a message from a synchronous context.
        Raises QueueFull if the queue is at capacity (unlikely in practice).
        """
        self._queue.put_nowait(message)

    # ----------------------------------------------------------
    # Queue status
    # ----------------------------------------------------------
    def pending_count(self) -> int:
        """Return number of messages waiting to be processed."""
        return self._queue.qsize()

    # ----------------------------------------------------------
    # Internal consumer loop
    # ----------------------------------------------------------
    async def _consume(self):
        """
        Process messages one at a time from the queue.
        Runs until stop() is called.
        """
        while self._running:
            try:
                # Wait up to 1 second for a message, then loop to check _running
                message = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
                try:
                    await self._handler(message)
                except Exception as e:
                    # Handler errors must not crash the worker loop
                    print(
                        f"[QueueWorker] Handler error for message "
                        f"type={message.get('type')}: {e}"
                    )
                finally:
                    self._queue.task_done()

            except asyncio.TimeoutError:
                # No message arrived within timeout -- loop again
                continue
            except asyncio.CancelledError:
                break

        print("[QueueWorker] Consumer loop exited.")


# ==============================================================
# Global singleton instance
# Imported by pipeline.py and all connectors.
# ==============================================================
worker = QueueWorker()
