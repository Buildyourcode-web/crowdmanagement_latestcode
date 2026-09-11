// Event & Site Zustand Store
import { create } from "zustand";
import { eventService } from "../services/eventService";

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

      const currentActiveId = get().activeEventId;
      let matched = events.find((e) => e.id === currentActiveId);

      // If saved activeEventId is not in user's accessible events, select first or active
      if (!matched && events.length > 0) {
        matched = events.find((e) => e.status === "ACTIVE" || e.status === "LIVE") || events[0];
      }

      if (matched) {
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
    } catch (e) {}

    // Reset site filter when event changes
    try {
      localStorage.removeItem("byc_active_site_id");
    } catch (e) {}

    set({
      activeEvent: eventObj,
      activeEventId: eventId,
      activeSiteId: null,
    });

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