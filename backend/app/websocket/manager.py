import json
from typing import Dict, List, Optional, Set
from fastapi import WebSocket
from loguru import logger


class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Active clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Active clients: {len(self.active_connections)}")

    async def broadcast_event(
        self,
        event_type: str,
        payload: dict,
        event_id: Optional[str] = None,
        site_id: Optional[str] = None,
    ):
        message = {
            "type": event_type,
            "event_id": str(event_id) if event_id else payload.get("event_id"),
            "site_id": str(site_id) if site_id else payload.get("site_id"),
            "payload": payload,
        }
        json_str = json.dumps(message)
        dead_connections = []

        for connection in list(self.active_connections):
            try:
                await connection.send_text(json_str)
            except Exception:
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)


ws_manager = ConnectionManager()
