// Dashboard Store — State management for Command Center Dashboard
import { create } from "zustand";

// Load initial cached snapshot for instant 0ms render (no blank dashes)
let initialCachedData = null;
const initialRangeCache = {};

const CACHE_VERSION = "v14_day2_exact";
try {
  if (sessionStorage.getItem("byc_cache_version") !== CACHE_VERSION) {
    sessionStorage.removeItem("byc_dashboard_cache");
    ["TODAY", "YESTERDAY", "7DAYS", "FESTIVAL"].forEach((k) => {
      sessionStorage.removeItem(`byc_dashboard_cache_${k}`);
    });
    sessionStorage.setItem("byc_cache_version", CACHE_VERSION);
  }

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
    const curData = current.data;

    // Strict monotonic protection: Today entries and festival totals MUST NEVER DECREASE!
    if (curData && payload) {
      const curTodayIn = Number(curData.today_entries || 0);
      const curFestIn = Number(curData.total_visitors_festival ?? curData.festival_total_entries ?? curTodayIn);
      const incomingTodayIn = Number(payload.today_entries || 0);
      const incomingFestIn = Number(payload.total_visitors_festival ?? payload.festival_total_entries ?? incomingTodayIn);

      if (curTodayIn > 0 && incomingTodayIn === 0) {
        payload.today_entries = curTodayIn;
        payload.current_occupancy = Math.max(0, curTodayIn - Number(payload.today_exits || 0));
        payload.net_flow = curTodayIn - Number(payload.today_exits || 0);
      }
      if (curFestIn > 0 && incomingFestIn === 0) {
        payload.total_visitors_festival = curFestIn;
        payload.festival_total_entries = curFestIn;
      }

      // Hourly protection: only block drop to exactly 0 (momentary glitch), allow all real corrections
      if (Array.isArray(payload.hourly_flow) && Array.isArray(curData.hourly_flow)) {
        payload.hourly_flow = payload.hourly_flow.map((bucket, idx) => {
          const curBucket = curData.hourly_flow.find((b) => b.hour === bucket.hour) || curData.hourly_flow[idx];
          const bIn = (bucket.entry || 0) === 0 && (curBucket?.entry || 0) > 0 ? curBucket.entry : (bucket.entry || 0);
          const bOut = (bucket.exit || 0) === 0 && (curBucket?.exit || 0) > 0 ? curBucket.exit : (bucket.exit || 0);
          return {
            ...bucket,
            entry: bIn,
            exit: bOut,
            net_flow: bIn - bOut,
          };
        });
      }
    }

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
      const inDelta = Number(
        payload?.inflow_delta ??
        payload?.delta_in ??
        payload?.in_delta ??
        (payload?.crossing === "IN" ? 1 : 0)
      );
      const outDelta = Number(
        payload?.outflow_delta ??
        payload?.delta_out ??
        payload?.out_delta ??
        (payload?.crossing === "OUT" ? 1 : 0)
      );

      const curTodayIn = Number(state.data.today_entries || 0);
      const curTodayOut = Number(state.data.today_exits || 0);
      const curFestIn = Number(
        state.data.total_visitors_festival !== undefined
          ? state.data.total_visitors_festival
          : (state.data.festival_total_entries || curTodayIn)
      );

      const incomingTodayIn = payload?.today_entries !== undefined && payload?.today_entries !== null
        ? Number(payload.today_entries)
        : null;
      const incomingTodayOut = payload?.today_exits !== undefined && payload?.today_exits !== null
        ? Number(payload.today_exits)
        : null;

      // CRITICAL: Never downgrade count if un-restarted camera worker has smaller local count than DB total!
      // Accept incoming total only if it's strictly greater; otherwise increment current count by live delta (+1)
      let nextTodayIn = curTodayIn;
      if (incomingTodayIn !== null && incomingTodayIn > curTodayIn) {
        nextTodayIn = incomingTodayIn;
      } else if (inDelta > 0) {
        nextTodayIn = curTodayIn + inDelta;
      }

      let nextTodayOut = curTodayOut;
      if (incomingTodayOut !== null && incomingTodayOut > curTodayOut) {
        nextTodayOut = incomingTodayOut;
      } else if (outDelta > 0) {
        nextTodayOut = curTodayOut + outDelta;
      }

      const diffIn = nextTodayIn - curTodayIn;
      const diffOut = nextTodayOut - curTodayOut;
      const nextFestIn = curFestIn + (diffIn > 0 ? diffIn : 0);

      // Real-time patch current hour bucket in 24-hour hourly_flow chart
      let updatedHourly = state.data.hourly_flow;
      if (Array.isArray(updatedHourly) && updatedHourly.length > 0 && (diffIn > 0 || diffOut > 0)) {
        const nowUtc = new Date();
        const istOffsetMs = 5.5 * 3600 * 1000;
        const istDate = new Date(nowUtc.getTime() + istOffsetMs);
        const currentHourStr = `${String(istDate.getUTCHours()).padStart(2, "0")}:00`;

        updatedHourly = updatedHourly.map((bucket) => {
          if (bucket.hour === currentHourStr) {
            const bIn = (bucket.entry || 0) + (diffIn > 0 ? diffIn : 0);
            const bOut = (bucket.exit || 0) + (diffOut > 0 ? diffOut : 0);
            return {
              ...bucket,
              entry: bIn,
              exit: bOut,
              net_flow: bIn - bOut,
            };
          }
          return bucket;
        });
      }

      return {
        data: {
          ...state.data,
          today_entries: nextTodayIn,
          today_exits: nextTodayOut,
          current_occupancy: Math.max(0, nextTodayIn - nextTodayOut),
          net_flow: nextTodayIn - nextTodayOut,
          total_visitors_festival: nextFestIn,
          festival_total_entries: nextFestIn,
          hourly_flow: updatedHourly,
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
