"""
Real-time manager — owned by Member 4.

Member 1 must call manager.broadcast(event) AFTER a successful commit.
Contract:
  broadcast payload is {"type":"card.created|card.moved|card.deleted","card":{...}}
"""
from typing import List
from fastapi import WebSocket
import json
import asyncio

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, event: dict):
        """
        Broadcast a JSON event to all connected clients.
        Safe to call after DB commit; disconnected sockets are pruned.
        """
        if not self.active_connections:
            return
        message = json.dumps(event)
        # copy list to avoid mutation during iteration
        disconnected = []
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

# Singleton used by routes.py and main.py
manager = ConnectionManager()
