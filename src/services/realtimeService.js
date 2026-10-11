import { useCrowdStore } from "../store/useCrowdStore.js";
import { useAlertStore } from "../store/useAlertStore.js";
import { useDashboardStore } from "../store/useDashboardStore.js";
import { getWsUrl } from "../utils/urlConfig.js";

class RealtimeService {
  constructor() {
    this.ws = null;
    this.listeners = new Set();
    this.statusListeners = new Set();
    this.status = "CONNECTING"; // CONNECTING, LIVE DATA, UPDATING, DEGRADED, OFFLINE
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 15;
    this.reconnectTimer = null;
    this.pingInterval = null;
    this.isExplicitlyClosed = false;
  }

  getWsUrl() {
    return getWsUrl();
  }

  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.isExplicitlyClosed = false;
    this.setStatus("CONNECTING");

    try {
      const url = this.getWsUrl();
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
        this.setStatus("LIVE DATA");
        this.startHeartbeat();
      };

      this.ws.onmessage = (event) => {
        try {
          if (event.data === "pong") return;
          const msg = JSON.parse(event.data);
          this.handleEvent(msg);
        } catch (err) {
          console.debug("[RealtimeService] Message parse error:", err);
        }
      };

      this.ws.onclose = () => {
        this.stopHeartbeat();
        if (!this.isExplicitlyClosed) {
          this.setStatus("DEGRADED");
          this.scheduleReconnect();
        } else {
          this.setStatus("OFFLINE");
        }
      };

      this.ws.onerror = (err) => {
        console.debug("[RealtimeService] WebSocket error:", err);
        this.setStatus("DEGRADED");
      };
    } catch (e) {
      console.warn("[RealtimeService] Connect failed:", e);
      this.setStatus("DEGRADED");
      this.scheduleReconnect();
    }
  }

  handleEvent(msg) {
    const eventType = msg.type || msg.event_type;
    const payload = msg.payload || msg.data || msg;

    // Multi-Location, Multi-Event & Multi-Site Isolation Filter:
    const activeLocationId = localStorage.getItem("byc_active_location_id");
    const activeEventId = localStorage.getItem("byc_active_event_id");
    const activeSiteId = localStorage.getItem("byc_active_site_id");

    const msgLocId = msg.location_id || payload?.location_id;
    if (activeLocationId && msgLocId && String(msgLocId) !== String(activeLocationId)) {
      return; // Discard message from another location
    }

    const msgEventId = msg.event_id || payload?.event_id;
    if (activeEventId && msgEventId && String(msgEventId) !== String(activeEventId)) {
      return; // Discard message from another event
    }

    const msgSiteId = msg.site_id || payload?.site_id;
    if (activeSiteId && msgSiteId && String(msgSiteId) !== String(activeSiteId)) {
      return; // Discard message from another site when filtered
    }

    // 1. Instant 0ms real-time state updates across shared stores
    const normalizedType = String(eventType || "").toLowerCase();

    if (
      normalizedType === "crowd_telemetry" ||
      normalizedType === "crowd_update" ||
      normalizedType === "crowd_metrics" ||
      normalizedType === "crowd_metrics_updated" ||
      normalizedType === "line_crossing"
    ) {
      useCrowdStore.getState().setCrowdFromAPI?.(payload);
    } else if (normalizedType === "zone_update") {
      useCrowdStore.getState().setZoneUpdate?.(payload);
      if (payload?.zone_code) {
        useDashboardStore.getState().patchZoneDensity?.(
          payload.zone_code,
          payload.current_people ?? payload.headcount,
          payload.capacity,
          payload.status,
          payload.density_pct
        );
      }
    } else if (normalizedType === "new_alert" || normalizedType === "alert") {
      useAlertStore.getState().addAlert?.(payload);
    }


    // 2. Notify all active page listeners
    this.listeners.forEach((listener) => {
      try {
        listener(msg, eventType, payload);
      } catch (err) {
        console.error("[RealtimeService] Listener error:", err);
      }
    });
  }

  startHeartbeat() {
    this.stopHeartbeat();
    this.pingInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send("ping");
      }
    }, 20000);
  }

  stopHeartbeat() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  scheduleReconnect() {
    if (this.reconnectTimer || this.isExplicitlyClosed) return;
    this.reconnectAttempts += 1;
    const delay = Math.min(30000, 1000 * Math.pow(1.5, this.reconnectAttempts));
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  subscribe(listener) {
    this.listeners.add(listener);
    if (!this.ws || this.ws.readyState === WebSocket.CLOSED) {
      this.connect();
    }
    return () => this.listeners.delete(listener);
  }

  subscribeStatus(listener) {
    this.statusListeners.add(listener);
    listener(this.status);
    return () => this.statusListeners.delete(listener);
  }

  setStatus(status) {
    this.status = status;
    this.statusListeners.forEach((l) => {
      try {
        l(status);
      } catch (e) {
        // ignore
      }
    });
  }

  disconnect() {
    this.isExplicitlyClosed = true;
    this.stopHeartbeat();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.setStatus("OFFLINE");
  }

  /**
   * Force a fresh WebSocket connection with the current active context
   * (location_id, event_id, site_id, token) from localStorage.
   *
   * Call this whenever the user changes their active location or event so that
   * the backend places the new socket into the correct isolated room immediately.
   * The old socket is cleanly closed first.
   */
  reconnectWithContext() {
    this.isExplicitlyClosed = false;
    this.reconnectAttempts = 0;
    this.stopHeartbeat();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      try { this.ws.close(); } catch (_) {}
      this.ws = null;
    }
    this.connect();
  }
}

export const realtimeService = new RealtimeService();

