"""
WebSocket endpoint: /ws/v1/events

Authentication & room assignment flow
--------------------------------------
1.  Client sends token (JWT access token) as a query parameter:
      ws://host/ws/v1/events?token=<JWT>&location_id=<id>&event_id=<id>&site_id=<id>

2.  Server decodes the JWT; rejects the connection (code 4401) if invalid.

3.  Server validates location_id + event_id against the DB using the same
    EventContext logic as REST endpoints.  Rejects (code 4403) on mismatch
    or access denial.

4.  Connection is placed into the matching isolated room via
    ws_manager.connect_with_context().

5.  On disconnect the socket is removed from the room automatically.

Existing callers that omit all query params (legacy / service-to-service) are
placed into the system room and continue to work as before.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.websocket.manager import ws_manager
from app.security.jwt import decode_token

router = APIRouter(tags=["WebSocket"])


class _WsReject(Exception):
    """Signals that the WebSocket connection should be closed with a specific code."""
    def __init__(self, code: int, reason: str):
        self.code = code
        self.reason = reason
        super().__init__(reason)


async def _resolve_ws_context(
    token: Optional[str],
    location_id_raw: Optional[str],
    event_id_raw: Optional[str],
    site_id_raw: Optional[str],
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Validate token + location/event context.

    Returns (user_id, location_id, event_id, site_id) as strings.
    Raises _WsReject on authentication or authorization failure.

    Intentionally does NOT use HTTP-style Depends() because WebSocket
    connections cannot return HTTP error responses.
    """
    # ----- JWT validation -----------------------------------------------
    if not token:
        # No token → system room only (legacy / internal service connections)
        return None, None, None, None

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise _WsReject(4401, "Invalid or expired authentication token")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise _WsReject(4401, "Token payload malformed")

    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise _WsReject(4401, "Invalid user ID in token")

    # ----- DB-side user & event validation ------------------------------
    try:
        from app.db.session import AsyncSessionLocal
        from app.models.user import User
        from app.models.role import Role
        from app.models.event import Event
        from app.models.location import Location
        from app.models.user_access import UserEventAccess

        async with AsyncSessionLocal() as db:
            # 1. Verify user still exists and is active
            user_stmt = (
                select(User)
                .options(selectinload(User.role).selectinload(Role.permissions))
                .where(User.id == user_uuid)
            )
            user_res = await db.execute(user_stmt)
            user = user_res.scalars().first()

            if not user or not user.is_active:
                raise _WsReject(4403, "User not found or inactive")

            is_super = user.is_super_admin

            # 2. Resolve location
            parsed_loc_id: Optional[uuid.UUID] = None
            if location_id_raw:
                try:
                    loc_uuid = uuid.UUID(location_id_raw)
                    loc_stmt = select(Location).where(
                        (Location.id == loc_uuid) | (Location.code == location_id_raw)
                    )
                except ValueError:
                    loc_stmt = select(Location).where(Location.code == location_id_raw)
                loc_res = await db.execute(loc_stmt)
                loc = loc_res.scalars().first()
                if not loc or not loc.is_active or loc.status != "ACTIVE":
                    raise _WsReject(4403, f"Location '{location_id_raw}' not found or inactive")
                parsed_loc_id = loc.id

            # 3. Resolve event
            parsed_evt_id: Optional[uuid.UUID] = None
            if event_id_raw:
                try:
                    evt_uuid = uuid.UUID(event_id_raw)
                    if is_super:
                        evt_stmt = select(Event).where(
                            (Event.id == evt_uuid) | (Event.code == event_id_raw)
                        )
                    else:
                        # Regular user must have UserEventAccess
                        access_sub = select(UserEventAccess.event_id).where(
                            UserEventAccess.user_id == user_uuid,
                            UserEventAccess.is_active == True,
                        )
                        evt_stmt = select(Event).where(
                            (Event.id == evt_uuid) | (Event.code == event_id_raw),
                            Event.id.in_(access_sub),
                        )
                except ValueError:
                    raise _WsReject(4403, f"Invalid event ID '{event_id_raw}'")

                evt_res = await db.execute(evt_stmt)
                event = evt_res.scalars().first()
                if not event:
                    raise _WsReject(4403, f"Event '{event_id_raw}' not accessible")

                # Cross-location mismatch guard
                evt_loc_id = getattr(event, "location_id", None)
                if (
                    parsed_loc_id
                    and evt_loc_id
                    and evt_loc_id != parsed_loc_id
                ):
                    raise _WsReject(4403, "Event does not belong to the provided location")

                parsed_evt_id = event.id
                # Auto-fill location from event if caller didn't send it
                if not parsed_loc_id:
                    parsed_loc_id = evt_loc_id


            # 4. Resolve site_id (optional – just normalise)
            parsed_site_id: Optional[str] = site_id_raw or None

            return (
                str(user_uuid),
                str(parsed_loc_id) if parsed_loc_id else None,
                str(parsed_evt_id) if parsed_evt_id else None,
                parsed_site_id,
            )

    except _WsReject:
        raise
    except Exception as e:
        logger.warning(f"[WS] Context resolution error: {e}")
        raise _WsReject(4500, "Internal error during context resolution")


@router.websocket("/ws/v1/events")
async def websocket_events_endpoint(
    websocket: WebSocket,
    token: Optional[str] = None,
    location_id: Optional[str] = None,
    event_id: Optional[str] = None,
    site_id: Optional[str] = None,
):
    """
    WebSocket endpoint for real-time isolated live events.

    Query parameters (all optional for backward compat with legacy clients):
      token        — JWT access token (required for isolated room placement)
      location_id  — Active location UUID or code
      event_id     — Active event UUID or code
      site_id      — Active site UUID (optional; scopes to site sub-room)
    """
    # --- Resolve context before accepting (reject before handshake if needed)
    resolved_location_id: Optional[str] = None
    resolved_event_id: Optional[str] = None
    resolved_site_id: Optional[str] = None
    user_id: Optional[str] = None

    try:
        user_id, resolved_location_id, resolved_event_id, resolved_site_id = (
            await _resolve_ws_context(token, location_id, event_id, site_id)
        )
    except _WsReject as rejection:
        await websocket.accept()
        await websocket.close(code=rejection.code, reason=rejection.reason)
        logger.warning(f"[WS] Rejected connection: {rejection.code} {rejection.reason}")
        return
    except Exception as e:
        await websocket.accept()
        await websocket.close(code=4500, reason="Internal server error")
        logger.error(f"[WS] Unexpected error during context resolution: {e}")
        return

    # --- Accept and register in the correct room
    if resolved_location_id and resolved_event_id:
        await ws_manager.connect_with_context(
            websocket=websocket,
            location_id=resolved_location_id,
            event_id=resolved_event_id,
            site_id=resolved_site_id,
            user_id=user_id,
        )
    else:
        # Unauthenticated / token-less → system room
        await ws_manager.connect(websocket)

    try:
        # Send initial connected greeting (same schema as before)
        await websocket.send_json({
            "type": "connected",
            "payload": {
                "message": "Connected to BYC AI Command Center Real-Time Event Bus",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "room": {
                    "location_id": resolved_location_id,
                    "event_id": resolved_event_id,
                    "site_id": resolved_site_id,
                },
            },
        })

        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"[WS] Error on connection: {e}")
        ws_manager.disconnect(websocket)
