// Dashboard Store — State management for Command Center Dashboard
import { create } from "zustand";

// Helper to get current IST date string (YYYY-MM-DD)
const getTodayIstString = () => {
  const now = new Date();
  const utc = now.getTime() + now.getTimezoneOffset() * 60000;
  const ist = new Date(utc + 3600000 * 5.5);
  return `${ist.getFullYear()}-${String(ist.getMonth() + 1).padStart(2, "0")}-${String(ist.getDate()).padStart(2, "0")}`;
};

const currentIstDateStr = getTodayIstString();
const CACHE_VERSION = `v17_${currentIstDateStr}`;

let initialCachedData = null;
const initialRangeCache = {};

try {
  // Purge any cache from previous versions or previous calendar dates
  if (sessionStorage.getItem("byc_cache_version") !== CACHE_VERSION) {
    sessionStorage.clear();
    sessionStorage.setItem("byc_cache_version", CACHE_VERSION);
  } else {
    const cachedStr = sessionStorage.getItem(`byc_dash_cache_${currentIstDateStr}`);
    if (cachedStr) {
      initialCachedData = JSON.parse(cachedStr);
      const rKey = (initialCachedData.date_range_selected || "TODAY").toUpperCase();
      initialRangeCache[rKey] = initialCachedData;
    }
  }
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
      sessionStorage.clear();
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

    // Canonical source of truth: payload from server is authoritative.
    // Never copy prior day's numbers or hours into this day's payload.
    const todayStr = getTodayIstString();
    try {
      if (payload) {
        sessionStorage.setItem(`byc_dash_cache_${rangeKey}_${todayStr}`, JSON.stringify(payload));
        sessionStorage.setItem(`byc_dash_cache_${todayStr}`, JSON.stringify(payload));
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

  // Real-time smooth counter increment from WebSocket crossing events
  patchDashboardCrossing: (payload) =>
    set((state) => {
      if (!state.data) return state;
      const inDelta = Number(payload?.inflow_delta || (payload?.crossing === "IN" ? 1 : 0));
      const outDelta = Number(payload?.outflow_delta || (payload?.crossing === "OUT" ? 1 : 0));

      if (inDelta <= 0 && outDelta <= 0) {
        return { lastUpdated: new Date().toISOString() };
      }

      const curTodayIn = Number(state.data.today_entries || 0);
      const curTodayOut = Number(state.data.today_exits || 0);
      const curFestIn = Number(
        state.data.festival_total_entries !== undefined
          ? state.data.festival_total_entries
          : (state.data.total_visitors_festival || curTodayIn)
      );

      const nextTodayIn = curTodayIn + inDelta;
      const nextTodayOut = curTodayOut + outDelta;
      const nextFestIn = curFestIn + inDelta;

      return {
        data: {
          ...state.data,
          today_entries: nextTodayIn,
          today_exits: nextTodayOut,
          current_occupancy: Math.max(0, nextTodayIn - nextTodayOut),
          net_flow: nextTodayIn - nextTodayOut,
          total_visitors_festival: nextFestIn,
          festival_total_entries: nextFestIn,
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
