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
  data: initialCachedData,
  rangeCache: initialRangeCache,
  loading: initialCachedData ? false : true,
  isRefreshing: false,
  isRangeLoading: false,
  error: null,
  dataStatus: "LIVE DATA",
  lastUpdated: initialCachedData ? new Date().toISOString() : null,

  setDateRange: (range) => {
    const upper = (range || "TODAY").toUpperCase();
    const current = get();
    if (current.dateRange === upper) return;

    const cachedForRange = current.rangeCache?.[upper];
    if (cachedForRange) {
      // Instant 0ms switch to cached range data!
      set({
        dateRange: upper,
        data: cachedForRange,
        isRangeLoading: false,
      });
    } else {
      // Range not cached yet — mark range as loading so stale counts aren't shown
      set({
        dateRange: upper,
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

  setDashboardData: (payload, forRange = null) => {
    const current = get();
    const rangeKey = (
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
      loading: false,
      isRefreshing: false,
      isRangeLoading: false,
      error: null,
      lastUpdated: new Date().toISOString(),
    });
  },

  // Instant 0ms real-time count updates from line-crossing events
  patchDashboardCrossing: (payload) =>
    set((state) => {
      if (!state.data) return state;
      const crossing = (payload?.crossing || "").toUpperCase();
      const currentEntries = Number(state.data.today_entries) || 0;
      const currentExits = Number(state.data.today_exits) || 0;

      let newEntries = currentEntries;
      let newExits = currentExits;

      if (crossing === "IN") {
        newEntries += 1;
      } else if (crossing === "OUT") {
        newExits += 1;
      } else if (payload?.inflow_delta) {
        newEntries += Number(payload.inflow_delta) || 0;
      } else if (payload?.outflow_delta) {
        newExits += Number(payload.outflow_delta) || 0;
      }

      // Reconcile with absolute camera numbers if higher
      if (payload?.in_count !== undefined && Number(payload.in_count) > newEntries) {
        newEntries = Number(payload.in_count);
      }
      if (payload?.out_count !== undefined && Number(payload.out_count) > newExits) {
        newExits = Number(payload.out_count);
      }

      const newOccupancy = Math.max(0, newEntries - newExits);
      const newNetFlow = newEntries - newExits;

      return {
        data: {
          ...state.data,
          today_entries: newEntries,
          today_exits: newExits,
          current_occupancy: newOccupancy,
          net_flow: newNetFlow,
        },
        lastUpdated: new Date().toISOString(),
      };
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
