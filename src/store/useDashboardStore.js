// Dashboard Store — State management for Command Center Dashboard
import { create } from "zustand";

// Load initial cached snapshot for instant 0ms render (no blank dashes)
let initialCachedData = null;
const initialRangeCache = {};

try {
  const cachedStr = sessionStorage.getItem("byc_dashboard_cache");
  if (cachedStr) {
    initialCachedData = JSON.parse(cachedStr);
    const rKey = (initialCachedData.date_range_selected || "TODAY").toUpperCase();
    initialRangeCache[rKey] = initialCachedData;
  }
  ["TODAY", "YESTERDAY", "7DAYS", "FESTIVAL"].forEach((k) => {
    const s = sessionStorage.getItem(`byc_dashboard_cache_${k}`);
    if (s) {
      try {
        initialRangeCache[k] = JSON.parse(s);
      } catch (_) {}
    }
  });
} catch (_) {}

export const useDashboardStore = create((set, get) => ({
  dateRange: "TODAY",
  selectedDayNumber: null,
  data: initialCachedData,
  rangeCache: initialRangeCache,
  loading: initialCachedData ? false : true,
  isRefreshing: false,
  isRangeLoading: false,
  error: null,
  dataStatus: "LIVE DATA",
  lastUpdated: initialCachedData ? new Date().toISOString() : null,

  setSelectedDay: (dayNumber = null, range = "today") => {
    const current = get();
    const rangeKey = dayNumber ? `DAY_${dayNumber}` : (range || "TODAY").toUpperCase();
    
    set({
      selectedDayNumber: dayNumber,
      dateRange: (range || "today").toUpperCase(),
    });

    const cachedForRange = current.rangeCache?.[rangeKey];
    if (cachedForRange) {
      set({
        data: cachedForRange,
        isRangeLoading: false,
      });
    } else {
      set({
        isRangeLoading: true,
      });
    }
  },

  setDateRange: (range) => {
    const upper = (range || "TODAY").toUpperCase();
    const current = get();
    if (current.dateRange === upper && current.selectedDayNumber === null) return;

    const cachedForRange = current.rangeCache?.[upper];
    if (cachedForRange) {
      set({
        dateRange: upper,
        selectedDayNumber: null,
        data: cachedForRange,
        isRangeLoading: false,
      });
    } else {
      set({
        dateRange: upper,
        selectedDayNumber: null,
        isRangeLoading: true,
      });
    }
  },

  resetDashboardData: () => {
    try {
      sessionStorage.removeItem("byc_dashboard_cache");
      ["TODAY", "YESTERDAY", "7DAYS", "FESTIVAL"].forEach((k) => {
        sessionStorage.removeItem(`byc_dashboard_cache_${k}`);
      });
    } catch (_) {}
    set({
      data: null,
      rangeCache: {},
      selectedDayNumber: null,
      loading: true,
      isRefreshing: false,
      isRangeLoading: false,
      error: null,
      lastUpdated: null,
    });
  },

  setDataStatus: (status) =>
    set((s) => (s.dataStatus === status ? s : { dataStatus: status })),
  setLoading: (loading) =>
    set((s) => (s.loading === loading ? s : { loading })),
  setIsRefreshing: (isRefreshing) =>
    set((s) => (s.isRefreshing === isRefreshing ? s : { isRefreshing })),
  setIsRangeLoading: (isRangeLoading) =>
    set((s) => (s.isRangeLoading === isRangeLoading ? s : { isRangeLoading })),
  setError: (error) =>
    set((s) => (s.error === error ? s : { error })),

  setDashboardData: (payload, forRange = null, forDayNumber = null) => {
    const current = get();
    const dayNum = forDayNumber ?? payload?.selected_day_number ?? current.selectedDayNumber;
    const rangeKey = dayNum ? `DAY_${dayNum}` : (
      forRange ||
      payload?.date_range_selected ||
      current.dateRange ||
      "TODAY"
    ).toUpperCase();

    try {
      if (payload) {
        sessionStorage.setItem(`byc_dashboard_cache_${rangeKey}`, JSON.stringify(payload));
        sessionStorage.setItem("byc_dashboard_cache", JSON.stringify(payload));
      }
    } catch (_) {}

    const updatedCache = {
      ...(current.rangeCache || {}),
      [rangeKey]: payload,
    };

    set({
      data: payload,
      rangeCache: updatedCache,
      selectedDayNumber: dayNum,
      loading: false,
      isRefreshing: false,
      isRangeLoading: false,
      error: null,
      lastUpdated: new Date().toISOString(),
    });
  },

  // Authoritative real-time count updates
  patchDashboardCrossing: (payload) =>
    set((state) => {
      if (!state.data) return state;
      // If payload includes authoritative totals from backend, update directly
      if (payload?.today_entries !== undefined && payload?.today_exits !== undefined) {
        return {
          data: {
            ...state.data,
            today_entries: payload.today_entries,
            today_exits: payload.today_exits,
            current_occupancy: Math.max(0, payload.today_entries - payload.today_exits),
            net_flow: payload.today_entries - payload.today_exits,
            ...(payload.total_visitors_festival !== undefined ? {
              total_visitors_festival: payload.total_visitors_festival,
              festival_total_entries: payload.total_visitors_festival,
            } : {}),
          },
          lastUpdated: new Date().toISOString(),
        };
      }
      return state;
    }),

  // Partial real-time patch from WebSocket events
  patchDashboardMetrics: (patch) =>
    set((state) => {
      if (!state.data) return state;
      return {
        data: {
          ...state.data,
          ...patch,
        },
        lastUpdated: new Date().toISOString(),
      };
    }),

  patchZoneDensity: (zoneCode, currentPeople, capacity, status, densityPct) =>
    set((state) => {
      if (!state.data?.zones) return state;
      const updated = state.data.zones.map((z) => {
        if (z.zone_code === zoneCode || z.zone_name?.toUpperCase().replace(" ", "-") === zoneCode) {
          const cap = capacity !== undefined && capacity !== null ? capacity : z.capacity;
          const cur = currentPeople !== undefined && currentPeople !== null ? currentPeople : z.current_people;
          const pct = densityPct !== undefined && densityPct !== null ? densityPct : (cap > 0 ? Math.round((cur / cap) * 100) : 0);
          return {
            ...z,
            current_people: cur,
            capacity: cap,
            status: status || z.status,
            density_pct: pct,
          };
        }
        return z;
      });
      return {
        data: {
          ...state.data,
          zones: updated,
        },
        lastUpdated: new Date().toISOString(),
      };
    }),
}));
