"""
WebSocket Server-Side Isolation Tests
=====================================
Tests A–J as specified in the implementation requirements.

These tests use FastAPI's TestClient for synchronous WebSocket connections
so they do NOT require a running server or Redis. The DB session is mocked
so no real data is written.

All tests validate that the ConnectionManager + router enforce
server-side room-based isolation.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi.testclient import TestClient

# ─── Helpers ────────────────────────────────────────────────────────────────

SECRET = "byc_super_secret_jwt_key_khairatabad_2026_production_change_me"
ALGORITHM = "HS256"

# Canonical test UUIDs
LOC_KHB = "d10d4b09-1773-432d-939b-948150fed631"   # Khairatabad
LOC_BAL = "076b29ca-e36a-4b52-9350-0da893c8e860"   # Balapur
EVT_KHB = "fa46350f-5d70-490c-9210-1d14a9f19952"   # Khairatabad Ganesh Festival
EVT_BAL = "e0a14aa1-b86f-437c-959b-de4cf4ee3fe4"   # Balapur Dasara
EVT_KHB2 = "aaaaaaaa-0000-0000-0000-000000000001"  # Khairatabad – second event
SITE_A = "cccccccc-0000-0000-0000-000000000001"
SITE_B = "cccccccc-0000-0000-0000-000000000002"
USER_ID = str(uuid.uuid4())


def _make_token(user_id: str = USER_ID, is_active: bool = True) -> str:
    payload = {
        "sub": user_id,
        "role": "SUPER_ADMIN",
        "permissions": [],
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def _expired_token(user_id: str = USER_ID) -> str:
    payload = {
        "sub": user_id,
        "role": "SUPER_ADMIN",
        "permissions": [],
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        "type": "access",
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


# ─── Minimal FastAPI app for testing ────────────────────────────────────────

from fastapi import FastAPI
from app.websocket.manager import ConnectionManager, _SYSTEM_ROOM


def _make_app():
    """Create an isolated FastAPI app with a fresh ConnectionManager for each test."""
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from app.websocket.manager import ConnectionManager

    app = FastAPI()
    mgr = ConnectionManager()

    @app.websocket("/ws/test")
    async def ws_endpoint(
        websocket: WebSocket,
        location_id: Optional[str] = None,
        event_id: Optional[str] = None,
        site_id: Optional[str] = None,
    ):
        """Simplified test endpoint — no JWT validation, context supplied directly."""
        await mgr.connect_with_context(
            websocket=websocket,
            location_id=location_id,
            event_id=event_id,
            site_id=site_id,
            user_id="test-user",
        )
        try:
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            mgr.disconnect(websocket)

    return app, mgr


# ─── Unit tests: ConnectionManager room routing ──────────────────────────────

class TestConnectionManagerRooms:
    """Unit tests for ConnectionManager room isolation (no HTTP server needed)."""

    def _new_mgr(self) -> ConnectionManager:
        return ConnectionManager()

    # -- Test A: Khairatabad → Khairatabad event received --------------------

    @pytest.mark.asyncio
    async def test_A_khairatabad_receives_own_event(self):
        """Khairatabad socket receives a Khairatabad event."""
        mgr = self._new_mgr()
        ws = AsyncMock()
        await mgr.connect_with_context(ws, LOC_KHB, EVT_KHB)

        await mgr.broadcast_event(
            "crowd_update", {"data": "khb"}, location_id=LOC_KHB, event_id=EVT_KHB
        )

        ws.send_text.assert_called_once()
        msg = json.loads(ws.send_text.call_args[0][0])
        assert msg["type"] == "crowd_update"
        assert msg["location_id"] == LOC_KHB

    # -- Test B: Balapur → Balapur event received ----------------------------

    @pytest.mark.asyncio
    async def test_B_balapur_receives_own_event(self):
        """Balapur socket receives a Balapur event."""
        mgr = self._new_mgr()
        ws = AsyncMock()
        await mgr.connect_with_context(ws, LOC_BAL, EVT_BAL)

        await mgr.broadcast_event(
            "crowd_update", {"data": "bal"}, location_id=LOC_BAL, event_id=EVT_BAL
        )

        ws.send_text.assert_called_once()
        msg = json.loads(ws.send_text.call_args[0][0])
        assert msg["location_id"] == LOC_BAL

    # -- Test C: Khairatabad event — Balapur socket receives NOTHING ----------

    @pytest.mark.asyncio
    async def test_C_balapur_socket_does_not_receive_khairatabad_event(self):
        """Balapur socket MUST NOT receive a Khairatabad event."""
        mgr = self._new_mgr()

        ws_khb = AsyncMock()
        ws_bal = AsyncMock()
        await mgr.connect_with_context(ws_khb, LOC_KHB, EVT_KHB)
        await mgr.connect_with_context(ws_bal, LOC_BAL, EVT_BAL)

        await mgr.broadcast_event(
            "crowd_update", {"data": "khb_event"}, location_id=LOC_KHB, event_id=EVT_KHB
        )

        ws_khb.send_text.assert_called_once()   # Khairatabad received
        ws_bal.send_text.assert_not_called()    # Balapur received NOTHING

    # -- Test D: Balapur event — Khairatabad socket receives NOTHING ----------

    @pytest.mark.asyncio
    async def test_D_khairatabad_socket_does_not_receive_balapur_event(self):
        """Khairatabad socket MUST NOT receive a Balapur event."""
        mgr = self._new_mgr()

        ws_khb = AsyncMock()
        ws_bal = AsyncMock()
        await mgr.connect_with_context(ws_khb, LOC_KHB, EVT_KHB)
        await mgr.connect_with_context(ws_bal, LOC_BAL, EVT_BAL)

        await mgr.broadcast_event(
            "new_alert", {"data": "bal_event"}, location_id=LOC_BAL, event_id=EVT_BAL
        )

        ws_bal.send_text.assert_called_once()   # Balapur received
        ws_khb.send_text.assert_not_called()    # Khairatabad received NOTHING

    # -- Test E: Same location, different events — only matching event receives

    @pytest.mark.asyncio
    async def test_E_same_location_different_events_isolated(self):
        """Two sockets on the same location but different events are isolated."""
        mgr = self._new_mgr()

        ws_evt1 = AsyncMock()
        ws_evt2 = AsyncMock()
        await mgr.connect_with_context(ws_evt1, LOC_KHB, EVT_KHB)
        await mgr.connect_with_context(ws_evt2, LOC_KHB, EVT_KHB2)

        await mgr.broadcast_event(
            "zone_update", {"data": "event1_only"}, location_id=LOC_KHB, event_id=EVT_KHB
        )

        ws_evt1.send_text.assert_called_once()
        ws_evt2.send_text.assert_not_called()

    # -- Test F: Same event, different sites — site-specific events isolated --

    @pytest.mark.asyncio
    async def test_F_same_event_different_sites_isolated(self):
        """Site-specific events only reach the matching site's socket."""
        mgr = self._new_mgr()

        ws_site_a = AsyncMock()
        ws_site_b = AsyncMock()
        ws_no_site = AsyncMock()  # Connected at event level, no site filter

        await mgr.connect_with_context(ws_site_a, LOC_KHB, EVT_KHB, site_id=SITE_A)
        await mgr.connect_with_context(ws_site_b, LOC_KHB, EVT_KHB, site_id=SITE_B)
        await mgr.connect_with_context(ws_no_site, LOC_KHB, EVT_KHB, site_id=None)

        # Broadcast with site_id=SITE_A context
        await mgr.broadcast_event(
            "queue_update",
            {"data": "site_a_event"},
            location_id=LOC_KHB,
            event_id=EVT_KHB,
            site_id=SITE_A,
        )

        # SITE_A socket receives it (matched via site-specific room)
        ws_site_a.send_text.assert_called_once()
        # SITE_B socket receives NOTHING
        ws_site_b.send_text.assert_not_called()
        # No-site socket receives it (event-level room included)
        ws_no_site.send_text.assert_called_once()

    # -- Test H: Disconnect cleanup — no stale room references ---------------

    @pytest.mark.asyncio
    async def test_H_disconnect_cleans_up_room(self):
        """After disconnect, socket is removed from room; no stale references."""
        mgr = self._new_mgr()

        ws = AsyncMock()
        await mgr.connect_with_context(ws, LOC_KHB, EVT_KHB)

        # Verify it's registered
        assert ws in mgr.active_connections
        room_key = (LOC_KHB, EVT_KHB, None)
        assert ws in mgr._rooms.get(room_key, set())

        # Disconnect
        mgr.disconnect(ws)

        # Room and global set cleaned up
        assert ws not in mgr.active_connections
        assert ws not in mgr._rooms.get(room_key, set())

    @pytest.mark.asyncio
    async def test_H2_disconnect_removes_empty_room(self):
        """When the last socket in a room disconnects, the room entry is removed."""
        mgr = self._new_mgr()
        ws = AsyncMock()
        await mgr.connect_with_context(ws, LOC_KHB, EVT_KHB)

        room_key = (LOC_KHB, EVT_KHB, None)
        assert room_key in mgr._rooms

        mgr.disconnect(ws)

        # Empty room should be pruned entirely
        assert room_key not in mgr._rooms

    # -- Test I: System-room / no-context broadcast stays in system room ------

    @pytest.mark.asyncio
    async def test_I_no_context_event_goes_to_system_room_only(self):
        """Events without location/event context go to system room only."""
        mgr = self._new_mgr()

        ws_sys = AsyncMock()
        ws_khb = AsyncMock()

        # System-room connection (no context)
        await mgr.connect(ws_sys)
        # Authenticated room connection
        await mgr.connect_with_context(ws_khb, LOC_KHB, EVT_KHB)

        # Broadcast without any context → system room only
        await mgr.broadcast_event("system_health", {"status": "ok"})

        ws_sys.send_text.assert_called_once()
        ws_khb.send_text.assert_not_called()

    # -- Test I2: Existing WS message schema preserved -------------------------

    @pytest.mark.asyncio
    async def test_I2_message_schema_backward_compatible(self):
        """Outgoing message schema must include type, event_id, site_id, location_id, payload."""
        mgr = self._new_mgr()
        ws = AsyncMock()
        await mgr.connect_with_context(ws, LOC_KHB, EVT_KHB)

        payload = {"count": 42, "camera_id": "cam-001"}
        await mgr.broadcast_event(
            "crowd_update", payload, location_id=LOC_KHB, event_id=EVT_KHB
        )

        ws.send_text.assert_called_once()
        msg = json.loads(ws.send_text.call_args[0][0])

        # Required schema fields
        assert "type" in msg
        assert "event_id" in msg
        assert "site_id" in msg
        assert "location_id" in msg
        assert "payload" in msg
        assert msg["type"] == "crowd_update"
        assert msg["payload"] == payload

    # -- Test: Multiple rooms coexist without cross-contamination -------------

    @pytest.mark.asyncio
    async def test_multiple_rooms_no_cross_contamination(self):
        """Three rooms simultaneously — each event reaches only its room."""
        mgr = self._new_mgr()

        ws_khb = AsyncMock()
        ws_bal = AsyncMock()
        ws_sys = AsyncMock()

        await mgr.connect_with_context(ws_khb, LOC_KHB, EVT_KHB)
        await mgr.connect_with_context(ws_bal, LOC_BAL, EVT_BAL)
        await mgr.connect(ws_sys)

        # Fire KHB event
        await mgr.broadcast_event("crowd_update", {}, location_id=LOC_KHB, event_id=EVT_KHB)
        assert ws_khb.send_text.call_count == 1
        assert ws_bal.send_text.call_count == 0
        assert ws_sys.send_text.call_count == 0

        # Fire BAL event
        await mgr.broadcast_event("new_alert", {}, location_id=LOC_BAL, event_id=EVT_BAL)
        assert ws_khb.send_text.call_count == 1  # unchanged
        assert ws_bal.send_text.call_count == 1
        assert ws_sys.send_text.call_count == 0

        # Fire system event
        await mgr.broadcast_event("system_health", {})
        assert ws_khb.send_text.call_count == 1  # unchanged
        assert ws_bal.send_text.call_count == 1  # unchanged
        assert ws_sys.send_text.call_count == 1

    # -- Test: Dead connection cleanup ----------------------------------------

    @pytest.mark.asyncio
    async def test_dead_connection_pruned_during_broadcast(self):
        """A socket that raises on send_text is pruned from the room."""
        mgr = self._new_mgr()

        dead_ws = AsyncMock()
        dead_ws.send_text.side_effect = Exception("connection lost")

        good_ws = AsyncMock()

        await mgr.connect_with_context(dead_ws, LOC_KHB, EVT_KHB)
        await mgr.connect_with_context(good_ws, LOC_KHB, EVT_KHB)

        await mgr.broadcast_event("crowd_update", {}, location_id=LOC_KHB, event_id=EVT_KHB)

        # Good socket received the message
        good_ws.send_text.assert_called_once()
        # Dead socket removed
        assert dead_ws not in mgr.active_connections

    # -- Test: get_room_summary -----------------------------------------------

    @pytest.mark.asyncio
    async def test_get_room_summary(self):
        """get_room_summary returns accurate per-room counts."""
        mgr = self._new_mgr()

        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws3 = AsyncMock()

        await mgr.connect_with_context(ws1, LOC_KHB, EVT_KHB)
        await mgr.connect_with_context(ws2, LOC_KHB, EVT_KHB)
        await mgr.connect_with_context(ws3, LOC_BAL, EVT_BAL)

        summary = mgr.get_room_summary()
        khb_key = str((LOC_KHB, EVT_KHB, None))
        bal_key = str((LOC_BAL, EVT_BAL, None))

        assert summary.get(khb_key) == 2
        assert summary.get(bal_key) == 1


# ─── Test G: Unauthorized context (JWT router validation) ───────────────────

class TestWebSocketAuthentication:
    """Test the router-level JWT + context validation logic."""

    @pytest.mark.asyncio
    async def test_G_invalid_token_rejected(self):
        """A connection with a forged/expired token must be rejected (close 4401)."""
        from app.websocket.router import _resolve_ws_context, _WsReject

        bad_token = "not.a.valid.token"
        with pytest.raises(_WsReject) as exc_info:
            await _resolve_ws_context(bad_token, LOC_KHB, EVT_KHB, None)
        assert exc_info.value.code == 4401

    @pytest.mark.asyncio
    async def test_G_expired_token_rejected(self):
        """An expired JWT must be rejected (close 4401)."""
        from app.websocket.router import _resolve_ws_context, _WsReject

        expired = _expired_token()
        with pytest.raises(_WsReject) as exc_info:
            await _resolve_ws_context(expired, LOC_KHB, EVT_KHB, None)
        assert exc_info.value.code == 4401

    @pytest.mark.asyncio
    async def test_G_no_token_goes_to_system_room(self):
        """A connection without a token is placed in the system room (no error)."""
        from app.websocket.router import _resolve_ws_context

        # No token → returns all None, no exception raised
        result = await _resolve_ws_context(None, None, None, None)
        assert result == (None, None, None, None)

