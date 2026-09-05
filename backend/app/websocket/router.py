import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from app.websocket.manager import ws_manager

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/v1/events")
async def websocket_events_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time live events.
    Clients receive crowd_update, zone_update, camera_status, new_alert, frs_candidate, etc.
    """
    await ws_manager.connect(websocket)
    try:
        # Send initial connected greeting
        await websocket.send_json({
            "type": "connected",
            "payload": {
                "message": "Connected to BYC AI Command Center Real-Time Event Bus",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        })
        while True:
            # Keep connection open and listen for ping / client heartbeats
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)
