"""
WebSocket Connection Manager with server-side room-based isolation.

Architecture:
- Every authenticated connection is placed into an isolated "room" keyed by
  (location_id, event_id, site_id).  site_id may be None → room covers all
  sites for that location+event pair.
- broadcast_event() routes messages ONLY to connections whose room matches the
  location_id + event_id (+ site_id if present) carried in the event.
- No event data ever crosses location or event boundaries on the wire.
- A special "system" room receives system-health / non-sensitive broadcasts.
- Backward-compat: callers that don't supply any context keys get routed to the
  system room only (e.g. SYSTEM_HEALTH).
"""

import json
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional, Set, Tuple

from fastapi import WebSocket
from loguru import logger


# ---------------------------------------------------------------------------
# Room key type: (location_id_str, event_id_str, site_id_str | None)
# ---------------------------------------------------------------------------
RoomKey = Tuple[str, str, Optional[str]]

# Sentinel room for messages that carry NO location/event context
_SYSTEM_ROOM: RoomKey = ("__system__", "__system__", None)


@dataclass
class _ConnectionMeta:
    """Authoritative context attached to each WebSocket by the server at accept-time."""
    location_id: Optional[str] = None
    event_id: Optional[str] = None
    site_id: Optional[str] = None
    user_id: Optional[str] = None

    @property
    def room_key(self) -> RoomKey:
        if self.location_id and self.event_id:
            return (self.location_id, self.event_id, self.site_id)
        return _SYSTEM_ROOM


class ConnectionManager:
    def __init__(self):
        # Backward-compat: keep this set populated so any code that reads
        # manager.active_connections still sees connected sockets.
        self.active_connections: Set[WebSocket] = set()

        # Internal room → set of sockets
        self._rooms: Dict[RoomKey, Set[WebSocket]] = {}

        # Socket → metadata (authoritative, set on connect)
        self._meta: Dict[WebSocket, _ConnectionMeta] = {}

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, websocket: WebSocket):
        """Legacy connect – places the socket into the system room only.

        Prefer connect_with_context() for authenticated, isolated connections.
        """
        await websocket.accept()
        meta = _ConnectionMeta()  # system room
        self._register(websocket, meta)
        logger.info(
            f"[WS] Client connected (system room). "
            f"Active: {len(self.active_connections)}"
        )

    async def connect_with_context(
        self,
        websocket: WebSocket,
        location_id: Optional[str],
        event_id: Optional[str],
        site_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        """Accept a WebSocket and place it into its authorised room.

        This is the primary entry-point for authenticated connections.
        The context values MUST already have been validated by the backend
        (JWT decode + EventContext resolution) before calling this method.
        """
        await websocket.accept()
        meta = _ConnectionMeta(
            location_id=str(location_id) if location_id else None,
            event_id=str(event_id) if event_id else None,
            site_id=str(site_id) if site_id else None,
            user_id=str(user_id) if user_id else None,
        )
        self._register(websocket, meta)
        logger.info(
            f"[WS] Client connected | room={meta.room_key} user={user_id} "
            f"Active: {len(self.active_connections)}"
        )

    def disconnect(self, websocket: WebSocket):
        """Remove a socket from its room and from all tracking structures."""
        meta = self._meta.pop(websocket, None)
        if meta:
            room_key = meta.room_key
            room = self._rooms.get(room_key)
            if room:
                room.discard(websocket)
                if not room:
                    del self._rooms[room_key]
            logger.info(
                f"[WS] Client disconnected | room={room_key} "
                f"Active: {len(self.active_connections) - 1}"
            )

        self.active_connections.discard(websocket)

    def _register(self, websocket: WebSocket, meta: _ConnectionMeta):
        self._meta[websocket] = meta
        room_key = meta.room_key
        if room_key not in self._rooms:
            self._rooms[room_key] = set()
        self._rooms[room_key].add(websocket)
        self.active_connections.add(websocket)

    # ------------------------------------------------------------------
    # Broadcast helpers
    # ------------------------------------------------------------------

    async def broadcast_event(
        self,
        event_type: str,
        payload: dict,
        event_id: Optional[str] = None,
        site_id: Optional[str] = None,
        location_id: Optional[str] = None,
    ):
        """Route an event to the correct isolated room(s).

        Resolution order:
        1. Use the explicit location_id / event_id / site_id arguments.
        2. Fall back to keys embedded in payload dict.
        3. If still missing → broadcast only to the system room
           (SYSTEM_HEALTH, heartbeats, etc.).
        """
        # Resolve routing context
        eff_loc = (
            str(location_id) if location_id
            else str(payload.get("location_id")) if payload.get("location_id")
            else None
        )
        eff_evt = (
            str(event_id) if event_id
            else str(payload.get("event_id")) if payload.get("event_id")
            else None
        )
        eff_site = (
            str(site_id) if site_id
            else str(payload.get("site_id")) if payload.get("site_id")
            else None
        )

        message = {
            "type": event_type,
            "event_id": eff_evt,
            "site_id": eff_site,
            "location_id": eff_loc,
            "payload": payload,
        }
        json_str = json.dumps(message)

        if eff_loc and eff_evt:
            await self._send_to_room(
                location_id=eff_loc,
                event_id=eff_evt,
                site_id=eff_site,
                json_str=json_str,
            )
        else:
            # No location/event context → system room only
            await self._send_to_room_by_key(_SYSTEM_ROOM, json_str)

    async def _send_to_room(
        self,
        location_id: str,
        event_id: str,
        site_id: Optional[str],
        json_str: str,
    ):
        """Send to the exact room + the parent site-less room if site_id is set."""
        target_keys: list[RoomKey] = [(location_id, event_id, None)]
        if site_id:
            target_keys.append((location_id, event_id, site_id))

        for key in target_keys:
            await self._send_to_room_by_key(key, json_str)

    async def _send_to_room_by_key(self, key: RoomKey, json_str: str):
        room = self._rooms.get(key)
        if not room:
            return

        dead: list[WebSocket] = []
        for ws in list(room):
            try:
                await ws.send_text(json_str)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def get_room_summary(self) -> dict:
        """Return a snapshot of rooms and their connection counts (for health endpoints)."""
        return {
            str(key): len(sockets)
            for key, sockets in self._rooms.items()
            if sockets
        }


ws_manager = ConnectionManager()
