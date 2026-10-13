// Event & Site Zustand Store
import { create } from "zustand";
import { eventService } from "../services/eventService";
import { locationService } from "../services/locationService";
import { invalidateApiCache } from "../services/apiClient";
import { useDashboardStore } from "./useDashboardStore";
import { realtimeService } from "../services/realtimeService";


export const useEventStore = create((set, get) => ({
  events: [],
  locations: [],
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
      const [events, locations] = await Promise.all([
        eventService.getEvents().catch(() => []),
        locationService.getLocations().catch(() => []),
      ]);
      set({ events, locations: locations || [], isLoadingEvents: false });

      const currentActiveId = get().activeEventId || localStorage.getItem("byc_active_event_id");
      let currentLocationId = get().activeLocationId || localStorage.getItem("byc_active_location_id");

      // Resolve canonical location object and normalize currentLocationId to UUID
      if (locations && locations.length > 0) {
        const loc = locations.find(
          (l) =>
            (currentLocationId && (
              String(l.id).toLowerCase() === String(currentLocationId).toLowerCase() ||
              String(l.code).toLowerCase() === String(currentLocationId).toLowerCase() ||
              String(l.name).toLowerCase() === String(currentLocationId).toLowerCase()
            )) ||
            (get().activeLocationName && String(l.name).toLowerCase() === String(get().activeLocationName).toLowerCase())
        );
        if (loc) {
          currentLocationId = loc.id;
          set({ activeLocation: loc, activeLocationId: loc.id, activeLocationName: loc.name });
          try {
            localStorage.setItem("byc_active_location_id", loc.id);
            localStorage.setItem("byc_active_location_name", loc.name);
          } catch (e) {}
        }
      }

      let matched = events.find((e) => e.id === currentActiveId);

      // If active location is set, enforce that the active event belongs strictly to this location
      if (currentLocationId && (!matched || !matched.location_id || String(matched.location_id).toLowerCase() !== String(currentLocationId).toLowerCase())) {
        const loc = (locations || []).find((l) => String(l.id).toLowerCase() === String(currentLocationId).toLowerCase());
        const locClean = loc ? loc.name.toLowerCase().replace(/h$/i, "").replace(/h(?=a)/g, "") : "";
        const isLocMatch = (e) => {
          if (e.location_id && String(e.location_id).toLowerCase() === String(currentLocationId).toLowerCase()) return true;
          if (locClean && ((e.name && e.name.toLowerCase().replace(/h(?=a)/g, "").includes(locClean)) || (e.location && e.location.toLowerCase().replace(/h(?=a)/g, "").includes(locClean)))) return true;
          return false;
        };

        const locEvent =
          events.find((e) => isLocMatch(e) && (e.status === "ACTIVE" || e.status === "LIVE")) ||
          events.find((e) => isLocMatch(e));
        if (locEvent) {
          matched = locEvent;
        }
      }

      // If no valid active event and no location set, pick first active
      if (!matched && !currentLocationId) {
        matched = events.find((e) => e.status === "ACTIVE" || e.status === "LIVE") || events[0];
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

    // Synchronize activeLocationId and activeLocationName if event is assigned to a specific location
    const updates = {
      activeEvent: eventObj,
      activeEventId: eventId,
      activeSiteId: null,
    };
    if (eventObj.location_id) {
      const locId = eventObj.location_id;
      updates.activeLocationId = locId;
      try {
        localStorage.setItem("byc_active_location_id", locId);
      } catch (e) {}

      const locs = get().locations || [];
      const matchedLoc = locs.find((l) => l.id === locId);
      if (matchedLoc) {
        updates.activeLocation = matchedLoc;
        updates.activeLocationName = matchedLoc.name;
        try {
          localStorage.setItem("byc_active_location_name", matchedLoc.name);
        } catch (e) {}
      }
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