# ==============================================================
# backend/ws_manager.py
# Manages active WebSocket connections.
# When the queue worker processes a message, it calls
# ws_manager.broadcast() to push the update to all
# connected browser clients simultaneously.
# ==============================================================

import asyncio
from typing import List
from fastapi import WebSocket


class WebSocketManager:
    """
    Tracks all active WebSocket connections and broadcasts
    queue worker messages to every connected client.
    """

    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active.append(websocket)
        print(f"[WS] Client connected. Total: {len(self.active)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active:
            self.active.remove(websocket)
        print(f"[WS] Client disconnected. Total: {len(self.active)}")

    async def broadcast(self, message: dict):
        """
        Send a message dict to all connected clients as JSON.
        Silently removes any client that has disconnected.
        """
        disconnected = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)

    async def send_to(self, websocket: WebSocket, message: dict):
        """Send a message to a single specific client."""
        try:
            await websocket.send_json(message)
        except Exception:
            self.disconnect(websocket)


# Global singleton -- imported by api.py and queue_worker setup
ws_manager = WebSocketManager()
