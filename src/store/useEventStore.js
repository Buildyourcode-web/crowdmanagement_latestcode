// Event & Site Zustand Store
import { create } from "zustand";
import { eventService } from "../services/eventService";
import { invalidateApiCache } from "../services/apiClient";
import { useDashboardStore } from "./useDashboardStore";
import { realtimeService } from "../services/realtimeService";


export const useEventStore = create((set, get) => ({
  events: [],
  activeEvent: null,
  activeEventId: localStorage.getItem("byc_active_event_id") || null,
  sites: [],
  activeSiteId: localStorage.getItem("byc_active_site_id") || null,
  activeLocation: null,
  activeLocationId: localStorage.getItem("byc_active_location_id") || null,
  activeLocationName: localStorage.getItem("byc_active_location_name") || null,
  isLoadingEvents: false,
  isLoadingSites: false,
  error: null,

  fetchEvents: async () => {
    set({ isLoadingEvents: true, error: null });
    try {
      const events = await eventService.getEvents();
      set({ events, isLoadingEvents: false });

      const currentActiveId = get().activeEventId || localStorage.getItem("byc_active_event_id");
      const currentLocationId = get().activeLocationId || localStorage.getItem("byc_active_location_id");

      let matched = events.find((e) => e.id === currentActiveId);

      // If no valid active event, respect the active location
      if (!matched) {
        if (currentLocationId) {
          // Pick the ACTIVE/LIVE event that belongs to this location first
          matched =
            events.find((e) => e.location_id === currentLocationId && (e.status === "ACTIVE" || e.status === "LIVE")) ||
            events.find((e) => e.location_id === currentLocationId);
        }
        // Only fall back to any global event when NO location is selected
        if (!matched && !currentLocationId) {
          matched = events.find((e) => e.status === "ACTIVE" || e.status === "LIVE") || events[0];
        }
      }

      if (matched && (!get().activeEvent || get().activeEvent.id !== matched.id)) {
        get().setActiveEvent(matched);
      }
    } catch (err) {
      console.error("Failed to fetch events:", err);
      set({ error: err.message, isLoadingEvents: false });
    }
  },

  setActiveEvent: (eventOrId) => {
    const events = get().events;
    const eventObj = typeof eventOrId === "object" ? eventOrId : events.find((e) => e.id === eventOrId);
    if (!eventObj) return;

    const eventId = eventObj.id;
    try {
      localStorage.setItem("byc_active_event_id", eventId);
      localStorage.setItem("byc_user_explicit_event", "true");
    } catch (e) {}

    // Reset site filter when event changes
    try {
      localStorage.removeItem("byc_active_site_id");
    } catch (e) {}

    // Reset dashboard data so new event's metrics immediately reload
    try {
      useDashboardStore.getState().resetDashboardData();
    } catch (e) {}

    // Synchronize activeLocationId if event is assigned to a specific location
    const updates = {
      activeEvent: eventObj,
      activeEventId: eventId,
      activeSiteId: null,
    };
    if (eventObj.location_id) {
      try {
        localStorage.setItem("byc_active_location_id", eventObj.location_id);
      } catch (e) {}
      updates.activeLocationId = eventObj.location_id;
    }

    set(updates);

    invalidateApiCache();

    get().fetchSites(eventId);

    // Reconnect WebSocket with new event context so backend places this
    // connection in the correct isolated room immediately.
    try {
      realtimeService.reconnectWithContext();
    } catch (e) {}
  },


  fetchSites: async (eventId = null) => {
    const targetEventId = eventId || get().activeEventId;
    if (!targetEventId) return;

    set({ isLoadingSites: true });
    try {
      const sites = await eventService.getSites(targetEventId);
      set({ sites, isLoadingSites: false });
    } catch (err) {
      console.error("Failed to fetch sites:", err);
      set({ isLoadingSites: false });
    }
  },

  setActiveSiteId: (siteId) => {
    if (siteId) {
      try {
        localStorage.setItem("byc_active_site_id", siteId);
      } catch (e) {}
    } else {
      try {
        localStorage.removeItem("byc_active_site_id");
      } catch (e) {}
    }
    set({ activeSiteId: siteId || null });
  },

  setActiveLocation: (loc) => {
    invalidateApiCache();
    if (!loc) {
      try {
        localStorage.removeItem("byc_active_location_id");
        localStorage.removeItem("byc_active_location_name");
        localStorage.removeItem("byc_active_event_id");
        localStorage.removeItem("byc_user_explicit_event");
        localStorage.removeItem("byc_active_site_id");
      } catch (e) {}
      set({
        activeLocation: null,
        activeLocationId: null,
        activeLocationName: null,
        activeEvent: null,
        activeEventId: null,
        activeSiteId: null,
      });
      return;
    }
    const locId = loc.id;
    const locName = loc.name;
    // Clear stale event/site from previous location so the backend
    // resolves a fresh event for the new location (no X-Event-ID header sent).
    try {
      localStorage.setItem("byc_active_location_id", locId);
      localStorage.setItem("byc_active_location_name", locName);
      localStorage.removeItem("byc_active_event_id");
      localStorage.removeItem("byc_user_explicit_event");
      localStorage.removeItem("byc_active_site_id");
    } catch (e) {}
    set({
      activeLocation: loc,
      activeLocationId: locId,
      activeLocationName: locName,
      activeEvent: null,
      activeEventId: null,
      activeSiteId: null,
    });

    // Reconnect WebSocket with new location context (event_id cleared above,
    // the new event will be fetched + WS reconnected again from setActiveEvent).
    try {
      realtimeService.reconnectWithContext();
    } catch (e) {}
  },


  clearActiveLocation: () => {
    invalidateApiCache();
    try {
      localStorage.removeItem("byc_active_location_id");
      localStorage.removeItem("byc_active_location_name");
    } catch (e) {}
    set({ activeLocation: null, activeLocationId: null, activeLocationName: null });
  },
}));