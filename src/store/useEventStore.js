// Event & Site Zustand Store
import { create } from "zustand";
import { eventService } from "../services/eventService";
import { invalidateApiCache } from "../services/apiClient";
import { useDashboardStore } from "./useDashboardStore";

export const useEventStore = create((set, get) => ({
  events: [],
  activeEvent: null,
  activeEventId: localStorage.getItem("byc_active_event_id") || null,
  sites: [],
  activeSiteId: localStorage.getItem("byc_active_site_id") || null,
  isLoadingEvents: false,
  isLoadingSites: false,
  error: null,

  fetchEvents: async () => {
    set({ isLoadingEvents: true, error: null });
    try {
      const events = await eventService.getEvents();
      set({ events, isLoadingEvents: false });

      const currentActiveId = get().activeEventId || localStorage.getItem("byc_active_event_id");
      let matched = events.find((e) => e.id === currentActiveId);

      // If no valid active event currently selected, pick default
      if (!matched) {
        const khbEvent = events.find((e) => e.code === "KHB-2026" || e.name?.toLowerCase().includes("khairatabad"));
        matched = khbEvent || events.find((e) => e.status === "ACTIVE" || e.status === "LIVE") || events[0];
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

    set({
      activeEvent: eventObj,
      activeEventId: eventId,
      activeSiteId: null,
    });

    invalidateApiCache();

    get().fetchSites(eventId);
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
}));