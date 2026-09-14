// Dashboard — Clean BYC AI Command Center Dashboard
import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import { getDashboardSummary } from "../services/dashboardService.js";
import { getFestival10DaysAnalytics, downloadFestival10DaysCsv } from "../services/analyticsService.js";
import { realtimeService } from "../services/realtimeService.js";
import { useDashboardStore } from "../store/useDashboardStore.js";
import { useEventStore } from "../store/useEventStore.js";
import { useAppStore } from "../store/useAppStore.js";
import { getChartTheme } from "../utils/chartTheme.js";

const DATE_RANGE_OPTIONS = [
  { id: "today", label: "TODAY" },
  { id: "yesterday", label: "YESTERDAY" },
  { id: "7days", label: "LAST 7 DAYS" },
  { id: "festival", label: "FESTIVAL" },
];

export default function Dashboard() {
  const navigate = useNavigate();
  const theme = useAppStore((s) => s.theme);
  const ct = getChartTheme(theme);
  const activeEventId = useEventStore((s) => s.activeEventId);

  // Zustand State Selectors (fine-grained to prevent redundant renders)
  const dateRange = useDashboardStore((s) => s.dateRange);
  const selectedDayNumber = useDashboardStore((s) => s.selectedDayNumber);
  const data = useDashboardStore((s) => s.data);
  const loading = useDashboardStore((s) => s.loading);
  const isRefreshing = useDashboardStore((s) => s.isRefreshing);
  const isRangeLoading = useDashboardStore((s) => s.isRangeLoading);
  const error = useDashboardStore((s) => s.error);
  const dataStatus = useDashboardStore((s) => s.dataStatus);
  const setDateRange = useDashboardStore((s) => s.setDateRange);
  const setSelectedDay = useDashboardStore((s) => s.setSelectedDay);

  const [selectedZoneCode, setSelectedZoneCode] = useState("all");
  const [clockStr, setClockStr] = useState("");
  const [fest10Data, setFest10Data] = useState(null);
  const [downloadingCsv, setDownloadingCsv] = useState(false);
  const inFlightRef = useRef(false);
  const pendingRef = useRef(false);
  const timerRef = useRef(null);
  const isMountedRef = useRef(true);

  // 1. Precise Header Clock
  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      setClockStr(
        now.toLocaleTimeString("en-GB", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        })
      );
    };
    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  }, []);

  const currentIstHour = useMemo(() => {
    const now = new Date();
    const utc = now.getTime() + now.getTimezoneOffset() * 60000;
    const ist = new Date(utc + 3600000 * 5.5);
    return ist.getHours();
  }, [clockStr]);

  // Dynamic Event Days derived from active event template
  const eventDaysList = useMemo(() => {
    if (data?.event_days && Array.isArray(data.event_days) && data.event_days.length > 0) {
      return data.event_days;
    }
    if (fest10Data?.days && Array.isArray(fest10Data.days) && fest10Data.days.length > 0) {
      return fest10Data.days;
    }
    return [
      { day_number: 1, date: "14 Sep", label: "Day 1 (14 Sep)", status: "TODAY" },
    ];
  }, [data?.event_days, fest10Data?.days]);

  // 2. Fetch authoritative dashboard summary with stable callback
  const loadData = useCallback(async (silent = false, overrideRange = null, overrideDayNumber = undefined) => {
    const store = useDashboardStore.getState();
    const range = (overrideRange !== null ? overrideRange : (store.dateRange || "today")).toLowerCase();
    const dayNum = overrideDayNumber !== undefined ? overrideDayNumber : store.selectedDayNumber;

    if (inFlightRef.current && overrideRange === null && overrideDayNumber === undefined) {
      pendingRef.current = true;
      return;
    }
    inFlightRef.current = true;
    if (!silent && !store.data) store.setLoading(true);
    if (!silent) store.setIsRefreshing(true);

    try {
      const [res, festRes] = await Promise.allSettled([
        getDashboardSummary(range, true, dayNum),
        getFestival10DaysAnalytics(),
      ]);
      if (!isMountedRef.current) return;
      if (res.status === "fulfilled" && res.value) {
        store.setDashboardData(res.value, range, dayNum);
      }
      if (festRes.status === "fulfilled" && festRes.value) {
        setFest10Data(festRes.value?.data || festRes.value);
      }
    } catch (err) {
      console.error("[Dashboard] Fetch error:", err);
      if (!isMountedRef.current) return;
      if (!useDashboardStore.getState().data) {
        useDashboardStore.getState().setError("Failed to load Command Center summary.");
      }
    } finally {
      if (isMountedRef.current) {
        useDashboardStore.getState().setLoading(false);
        useDashboardStore.getState().setIsRefreshing(false);
      }
      inFlightRef.current = false;
      if (pendingRef.current && isMountedRef.current) {
        pendingRef.current = false;
        setTimeout(() => {
          if (isMountedRef.current) {
            const curRange = useDashboardStore.getState().dateRange || "today";
            const curDay = useDashboardStore.getState().selectedDayNumber;
            loadData(true, curRange, curDay);
          }
        }, 1000);
      }
    }
  }, []);

  // 3. Mount & Polling with Tab Visibility Awareness
  useEffect(() => {
    isMountedRef.current = true;
    const initialRange = useDashboardStore.getState().dateRange || "today";
    const initialDay = useDashboardStore.getState().selectedDayNumber;
    loadData(false, initialRange, initialDay);

    const scheduleNext = () => {
      clearTimeout(timerRef.current);
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      timerRef.current = setTimeout(async () => {
        if (isMountedRef.current && document.visibilityState === "visible") {
          const curRange = useDashboardStore.getState().dateRange || "today";
          const curDay = useDashboardStore.getState().selectedDayNumber;
          await loadData(true, curRange, curDay);
          scheduleNext();
        }
      }, 5000);
    };

    scheduleNext();

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        const curRange = useDashboardStore.getState().dateRange || "today";
        const curDay = useDashboardStore.getState().selectedDayNumber;
        loadData(true, curRange, curDay);
        scheduleNext();
      } else {
        clearTimeout(timerRef.current);
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    // 4. WebSocket Real-time event listener (Strict canonical consistency)
    let wsDebounceTimer = null;
    const unsubWs = realtimeService.subscribe((msg, eventType, payload) => {
      const type = String(eventType || msg?.type || "").toLowerCase();
      const dataPayload = payload || msg?.payload || msg;

      if (
        type === "crowd_telemetry" ||
        type === "crowd_update" ||
        type === "crowd_metrics" ||
        type === "crowd_metrics_updated" ||
        type === "line_crossing"
      ) {
        useDashboardStore.getState().patchDashboardCrossing(dataPayload);
        if (dataPayload?.today_entries === undefined || dataPayload?.today_exits === undefined) {
          // Debounce fetch from PostgreSQL canonical ledger
          if (wsDebounceTimer) clearTimeout(wsDebounceTimer);
          wsDebounceTimer = setTimeout(() => {
            const curRange = useDashboardStore.getState().dateRange || "today";
            const curDay = useDashboardStore.getState().selectedDayNumber;
            loadData(true, curRange, curDay);
          }, 1500);
        }
      } else if (type === "zone_update") {
        if (dataPayload?.zone_code) {
          useDashboardStore.getState().patchZoneDensity(
            dataPayload.zone_code,
            dataPayload.current_people ?? dataPayload.headcount,
            dataPayload.capacity,
            dataPayload.status,
            dataPayload.density_pct
          );
        }
      } else if (
        type === "new_alert" ||
        type === "frs_candidate" ||
        type === "pipeline_state_changed" ||
        type === "pipeline_started" ||
        type === "pipeline_stopped"
      ) {
        loadData(true);
      }
    });

    const unsubStatus = realtimeService.subscribeStatus((status) => {
      useDashboardStore.getState().setDataStatus(status);
    });

    return () => {
      isMountedRef.current = false;
      clearTimeout(timerRef.current);
      if (wsDebounceTimer) clearTimeout(wsDebounceTimer);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      unsubWs();
      unsubStatus();
    };
  }, [loadData]);

  // Re-fetch immediately when active event selection changes
  useEffect(() => {
    if (activeEventId) {
      useDashboardStore.getState().setLoading(true);
      const curRange = useDashboardStore.getState().dateRange || "today";
      const curDay = useDashboardStore.getState().selectedDayNumber;
      loadData(false, curRange, curDay);
    }
  }, [activeEventId, loadData]);

  // Handle Event Day Change
  const handleEventDaySelect = (dayNum, rangeStr = null) => {
    if (rangeStr === "festival") {
      setSelectedDay(null, "festival");
      loadData(false, "festival", null);
    } else if (dayNum !== null && dayNum !== undefined) {
      setSelectedDay(dayNum, null);
      loadData(false, null, dayNum);
    } else {
      setSelectedDay(null, "today");
      loadData(false, "today", null);
    }
  };

  // Memoized Chart Options (Matching 24-Hour Person Count Distribution aesthetic)
  const hourlyChartOption = useMemo(() => {
    if (!data?.hourly_flow || data.hourly_flow.length === 0) return null;

    const hours = data.hourly_flow.map((p) => p.hour);
    const isToday = (dateRange || "TODAY") === "TODAY";
    const isYesterday = (dateRange || "").toUpperCase() === "YESTERDAY";
    const currentHourStr = `${String(currentIstHour).padStart(2, "0")}:00`;

    const barData = data.hourly_flow.map((p, idx) => {
      const isCurrent =
        isToday &&
        (p.hour === currentHourStr ||
          (hours.indexOf(currentHourStr) === -1 && idx === currentIstHour));

      const isYesterdayPeak =
        isYesterday &&
        data.peak_hour &&
        data.peak_hour !== "—" &&
        data.peak_hour.startsWith(p.hour);

      const isCurrentDay =
        !isToday &&
        !isYesterday &&
        (p.hour?.toLowerCase().includes("today") ||
          (dateRange === "7DAYS" && idx === data.hourly_flow.length - 1) ||
          (dateRange === "FESTIVAL" && p.hour?.includes("Day 1")));

      const isHighlighted = isCurrent || isYesterdayPeak || isCurrentDay;

      return {
        value: p.entry,
        exitValue: p.exit,
        isCurrent: isHighlighted,
        itemStyle: isHighlighted
          ? {
              color: {
                type: "linear",
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: "#fbb034" },
                  { offset: 1, color: "#f5a623" },
                ],
              },
              borderColor: "#fbbf24",
              borderWidth: 1.5,
              borderRadius: [6, 6, 0, 0],
              shadowColor: "rgba(245, 166, 35, 0.4)",
              shadowBlur: 8,
            }
          : {
              color: {
                type: "linear",
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: "#2da8e8" },
                  { offset: 1, color: "#1f7fb8" },
                ],
              },
              borderRadius: [6, 6, 0, 0],
            },
      };
    });

    return {
      backgroundColor: "transparent",
      grid: { top: 25, right: 15, bottom: 45, left: 55 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(13, 20, 30, 0.96)",
        borderColor: "rgba(45, 168, 232, 0.3)",
        borderWidth: 1,
        padding: [10, 14],
        textStyle: { color: "#fff", fontSize: 12 },
        formatter: (params) => {
          const p = params[0];
          const raw = data.hourly_flow[p.dataIndex];
          const isCurr = p.data?.isCurrent;
          return `
            <div style="font-weight:700;margin-bottom:6px;color:${isCurr ? '#fbb034' : '#2da8e8'};display:flex;align-items:center;gap:6px">
              <span>${p.name}</span>
              ${isCurr ? '<span style="font-size:9px;background:rgba(251,176,52,0.2);color:#fbb034;padding:1px 5px;border-radius:3px;border:1px solid #fbb034">CURRENT</span>' : ''}
            </div>
            <div style="display:flex;justify-content:space-between;gap:20px;margin-bottom:3px">
              <span style="color:#8b949e">Person Count:</span>
              <strong style="font-family:monospace;color:#fff">${(p.value || 0).toLocaleString()}</strong>
            </div>
            ${raw?.exit ? `
            <div style="display:flex;justify-content:space-between;gap:20px">
              <span style="color:#8b949e">Exits:</span>
              <span style="font-family:monospace;color:#58a6ff">${raw.exit.toLocaleString()}</span>
            </div>` : ''}
          `;
        },
      },
      xAxis: {
        type: "category",
        data: hours,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: "#718294",
          fontSize: 10,
          interval: 0,
          rotate: 45,
        },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: {
          show: true,
          lineStyle: { color: "rgba(255, 255, 255, 0.04)", type: "dashed" },
        },
        axisLabel: {
          formatter: (v) => v.toLocaleString(),
          color: "#718294",
          fontSize: 10,
        },
      },
      series: [
        {
          name: "Person Count",
          type: "bar",
          data: barData,
          barMaxWidth: 22,
          barCategoryGap: "28%",
        },
      ],
    };
  }, [data?.hourly_flow, dateRange, currentIstHour]);

  // Daily Trend Table / Chart Option
  const statusColor = dataStatus === "LIVE DATA" ? "#3fb950" : dataStatus === "DEGRADED" ? "#e3b341" : "#8b949e";

  return (
    <div className="cc-page" style={{ gap: 14, paddingBottom: 30 }}>
      {/* ========================================================================= */}
      {/* SECTION 1: TOP HEADER */}
      {/* ========================================================================= */}
      <div className="cc-page-header" style={{ marginBottom: 0, paddingBottom: 10, borderBottom: "1px solid var(--cc-border)" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h1 className="cc-page-title" style={{ fontSize: 20, letterSpacing: "0.04em", margin: 0 }}>
              COMMAND CENTER
            </h1>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "2px 8px",
                background: "rgba(255, 255, 255, 0.04)",
                border: "1px solid var(--cc-border)",
                borderRadius: 12,
                fontSize: 10,
                fontFamily: "var(--cc-font-mono)",
                color: statusColor,
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  backgroundColor: statusColor,
                  boxShadow: `0 0 6px ${statusColor}`,
                }}
              />
              {dataStatus}
            </div>
          </div>
          <div className="cc-page-subtitle" style={{ fontSize: 12, color: "var(--cc-text-muted)", marginTop: 2 }}>
            Khairatabad Ganesh Festival 2026 — Live Operations
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ fontSize: 11, fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-muted)", marginRight: 6 }}>
            {clockStr} IST
          </div>
          <button className="cc-btn cc-btn-sm" onClick={() => loadData(false)} disabled={isRefreshing} title="Refresh Live Data">
            <i className={`bi bi-arrow-clockwise ${isRefreshing ? "cc-spin" : ""}`} />
            {isRefreshing ? "Updating..." : "Refresh"}
          </button>
          <button className="cc-btn cc-btn-sm" onClick={() => navigate("/cameras")}>
            <i className="bi bi-camera-video-fill" /> Cameras
          </button>
          <button className="cc-btn cc-btn-sm" onClick={() => navigate("/crowd-management")}>
            <i className="bi bi-people-fill" /> Crowd & Zones
          </button>
        </div>
      </div>

      {error && !data && (
        <div style={{ padding: 12, background: "rgba(248, 81, 73, 0.1)", border: "1px solid var(--cc-red)", borderRadius: 6, color: "var(--cc-red)", fontSize: 13, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>{error}</span>
          <button className="cc-btn cc-btn-sm" onClick={() => loadData(false)}>Retry</button>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SECTION 2 & 9: HERO KPI + PEOPLE MOVEMENT PANEL */}
      {/* ========================================================================= */}
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 1fr 1fr", gap: 10 }}>
        {/* HERO KPI — Festival Total Footfall (all days 14-24 Sept) */}
        <div
          className="cc-card"
          onClick={() => navigate("/reports")}
          style={{
            cursor: "pointer",
            background: "linear-gradient(135deg, rgba(188, 140, 255, 0.12) 0%, rgba(13, 17, 23, 0.95) 100%)",
            border: "1.5px solid rgba(188, 140, 255, 0.4)",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            padding: "12px 14px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--cc-text-muted)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
              Festival Total {fest10Data?.start_date && fest10Data?.end_date ? `(${fest10Data.start_date} – ${fest10Data.end_date})` : ""}
            </span>
            <span style={{ fontSize: 10, background: "rgba(188, 140, 255, 0.2)", border: "1px solid rgba(188, 140, 255, 0.4)", color: "#bc8cff", padding: "1px 6px", borderRadius: 4, fontFamily: "var(--cc-font-mono)", fontWeight: 700 }}>
              {fest10Data ? `Day ${fest10Data.current_day} of ${fest10Data.days?.length || 11}` : (data?.festival_day_label || "Day 1")}
            </span>
          </div>

          <div style={{ margin: "6px 0" }}>
            <div style={{ fontSize: 28, fontWeight: 800, fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-primary)", letterSpacing: "0.02em" }}>
              {loading && !data ? "—" : (
                data?.festival_total_entries ??
                fest10Data?.total_entries_10days ??
                data?.total_visitors_festival ??
                0
              ).toLocaleString()}
            </div>
            <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>
              {`Total unique entries across all ${fest10Data?.days?.length || 11} festival days`}
            </div>
          </div>
        </div>

        {/* RANGE-AWARE ENTRY */}
        <div className="cc-card" style={{ padding: "12px 14px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: "var(--cc-text-muted)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
            Total Entry ({data?.selected_range_label || (dateRange === "7DAYS" ? "Last 7 Days" : dateRange === "FESTIVAL" ? "Festival" : dateRange === "YESTERDAY" ? "Yesterday" : "Today")})
          </span>
          <div style={{ fontSize: 28, fontWeight: 800, fontFamily: "var(--cc-font-mono)", color: "#3fb950" }}>
            {isRangeLoading ? (
              <span style={{ opacity: 0.5, fontSize: 20 }}>Updating...</span>
            ) : loading && !data ? (
              "—"
            ) : (
              (data?.today_entries || 0).toLocaleString()
            )}
          </div>
          <span style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>
            All entry cameras — line crossings IN ({data?.selected_range_label || (dateRange === "YESTERDAY" ? "Yesterday" : "Selected Period")})
          </span>
        </div>

        {/* RANGE-AWARE EXIT */}
        <div className="cc-card" style={{ padding: "12px 14px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: "var(--cc-text-muted)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
            Total Exit ({data?.selected_range_label || (dateRange === "7DAYS" ? "Last 7 Days" : dateRange === "FESTIVAL" ? "Festival" : dateRange === "YESTERDAY" ? "Yesterday" : "Today")})
          </span>
          <div style={{ fontSize: 28, fontWeight: 800, fontFamily: "var(--cc-font-mono)", color: "#f85149" }}>
            {isRangeLoading ? (
              <span style={{ opacity: 0.5, fontSize: 20 }}>Updating...</span>
            ) : loading && !data ? (
              "—"
            ) : (
              (data?.today_exits || 0).toLocaleString()
            )}
          </div>
          <span style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>
            All exit cameras — line crossings OUT ({data?.selected_range_label || (dateRange === "YESTERDAY" ? "Yesterday" : "Selected Period")})
          </span>
        </div>

        {/* RANGE-AWARE PEAK */}
        <div className="cc-card" style={{ padding: "12px 14px", display: "flex", flexDirection: "column", justifyContent: "space-between", borderLeft: "3px solid #e3b341" }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: "var(--cc-text-muted)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
            Peak {dateRange === "7DAYS" || dateRange === "FESTIVAL" ? "Day" : "Hour"} ({data?.selected_range_label || (dateRange === "7DAYS" ? "Last 7 Days" : dateRange === "FESTIVAL" ? "Festival" : dateRange === "YESTERDAY" ? "Yesterday" : "Today")})
          </span>
          <div style={{ fontSize: 18, fontWeight: 800, fontFamily: "var(--cc-font-mono)", color: "#e3b341", marginTop: 4 }}>
            {isRangeLoading ? (
              <span style={{ opacity: 0.5, fontSize: 14 }}>Updating...</span>
            ) : loading && !data ? (
              "—"
            ) : data?.peak_hour && data.peak_hour !== "—" ? (
              data.peak_hour
            ) : (
              "No data"
            )}
          </div>
          <span style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>Highest visitor inflow period</span>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* SECTION 3 & 4: 24-HOUR PERSON COUNT DISTRIBUTION (MATCHING REFERENCE UI) */}
      {/* ========================================================================= */}
      <div
        className="cc-card"
        style={{
          padding: 0,
          overflow: "hidden",
          background: "#131b26",
          border: "1px solid rgba(45, 168, 232, 0.22)",
          borderRadius: 14,
          boxShadow: "0 4px 20px rgba(0, 0, 0, 0.35)",
        }}
      >
        <div
          className="cc-section-header"
          style={{
            padding: "14px 18px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 12,
            borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
            background: "rgba(255, 255, 255, 0.015)",
          }}
        >
          {/* Left: Icon + Title */}
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div
              style={{
                width: 30,
                height: 30,
                borderRadius: 7,
                background: "rgba(32, 133, 199, 0.16)",
                border: "1px solid rgba(45, 168, 232, 0.45)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#2da8e8",
                fontSize: 14,
              }}
            >
              <i className="bi bi-bar-chart-fill" />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontWeight: 800, fontSize: 15, color: "#fff", letterSpacing: "0.02em" }}>
                  {dateRange === "7DAYS"
                    ? "7-Day Person Count Distribution"
                    : dateRange === "FESTIVAL"
                    ? "Festival Day-Wise Person Count Distribution"
                    : dateRange === "YESTERDAY"
                    ? "Yesterday's 24-Hour Person Count Distribution"
                    : "24-Hour Person Count Distribution"}
                </span>
                {data?.peak_hour && data.peak_hour !== "—" && (
                  <span
                    style={{
                      fontSize: 10,
                      background: "rgba(245, 166, 35, 0.15)",
                      border: "1px solid rgba(245, 166, 35, 0.4)",
                      color: "#fbb034",
                      padding: "2px 8px",
                      borderRadius: 4,
                      fontFamily: "var(--cc-font-mono)",
                      fontWeight: 700,
                    }}
                  >
                    Peak: {data.peak_hour}
                  </span>
                )}
              </div>
              <div style={{ fontSize: 11, color: "#718294", marginTop: 2 }}>
                Real-time camera gate visitor entries and flow analytics
              </div>
            </div>
          </div>

          {/* Right: Date Range Buttons + Reference-Style Legend */}
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            {/* Dynamic Festival Day Selector */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                background: "rgba(0, 0, 0, 0.4)",
                padding: "3px 8px",
                borderRadius: 6,
                border: "1px solid rgba(255, 255, 255, 0.12)",
              }}
            >
              <label style={{ fontSize: 10, fontFamily: "var(--cc-font-mono)", fontWeight: 700, color: "var(--cc-text-muted)", textTransform: "uppercase" }}>
                Festival Day:
              </label>
              <select
                value={
                  selectedDayNumber
                    ? `day_${selectedDayNumber}`
                    : dateRange === "FESTIVAL"
                    ? "festival"
                    : "today"
                }
                onChange={(e) => {
                  const val = e.target.value;
                  if (val === "festival") {
                    handleEventDaySelect(null, "festival");
                  } else if (val.startsWith("day_")) {
                    const dNum = parseInt(val.replace("day_", ""), 10);
                    handleEventDaySelect(dNum, null);
                  } else {
                    handleEventDaySelect(null, "today");
                  }
                }}
                style={{
                  background: "rgba(13, 17, 23, 0.95)",
                  color: "#58a6ff",
                  border: "1px solid rgba(45, 168, 232, 0.35)",
                  borderRadius: 4,
                  padding: "4px 8px",
                  fontSize: 11,
                  fontFamily: "var(--cc-font-mono)",
                  fontWeight: 700,
                  cursor: "pointer",
                  outline: "none",
                }}
              >
                {eventDaysList.map((d) => (
                  <option key={d.day_number} value={`day_${d.day_number}`}>
                    {d.label || `Day ${d.day_number}: ${d.date}`} {d.status === "TODAY" ? "★ TODAY" : ""}
                  </option>
                ))}
                <option value="festival">Festival Total (All Days)</option>
              </select>
            </div>

            {/* Custom Legend Matching Screenshot */}
            <div style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 12, fontWeight: 700 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                <span
                  style={{
                    width: 12,
                    height: 12,
                    borderRadius: 3,
                    background: "#2085c7",
                    display: "inline-block",
                  }}
                />
                <span style={{ color: "#2da8e8" }}>
                  {dateRange === "7DAYS" || dateRange === "FESTIVAL" ? "Past Days" : "Past Hours"}
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                <span
                  style={{
                    width: 12,
                    height: 12,
                    borderRadius: 3,
                    background: "#f5a623",
                    border: "1px solid #fbbf24",
                    boxShadow: "0 0 6px rgba(245, 166, 35, 0.5)",
                    display: "inline-block",
                  }}
                />
                <span style={{ color: "#fbb034" }}>
                  {dateRange === "7DAYS" || dateRange === "FESTIVAL" ? "Today" : "Current Hour"}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div style={{ padding: "12px 16px 14px 16px" }}>
          {loading && !data ? (
            <div style={{ height: 250, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--cc-text-muted)" }}>
              Loading Person Count Distribution...
            </div>
          ) : hourlyChartOption ? (
            <ReactECharts option={hourlyChartOption} style={{ height: 260, width: "100%" }} notMerge={true} lazyUpdate={true} />
          ) : (
            <div style={{ height: 250, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--cc-text-muted)" }}>
              NO DATA FOR SELECTED PERIOD
            </div>
          )}
        </div>
      </div>

      {/* ========================================================================= */}
      {/* SECTION 5 & 7: QUEUE STATUS & FLOW + ZONE DENSITY */}
      {/* ========================================================================= */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        {/* QUEUE STATUS & FLOW */}
        <div className="cc-card" style={{ padding: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          <div className="cc-section-header" style={{ padding: "10px 14px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontWeight: 700, fontSize: 13, color: "var(--cc-text-primary)", letterSpacing: "0.04em" }}>
              QUEUE STATUS & FLOW
            </span>
            <button className="cc-btn cc-btn-sm" style={{ fontSize: 10 }} onClick={() => navigate("/crowd-management")}>
              View All Queues
            </button>
          </div>

          <div style={{ padding: "8px 12px", flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
            {loading && !data ? (
              <div style={{ padding: 20, textAlign: "center", color: "var(--cc-text-muted)" }}>Loading Queue Status...</div>
            ) : !data?.queues || data.queues.length === 0 ? (
              <div style={{ padding: 24, textAlign: "center", color: "var(--cc-text-muted)", fontSize: 12 }}>
                <i className="bi bi-inbox" style={{ fontSize: 24, display: "block", marginBottom: 6 }} />
                NO ACTIVE QUEUES CONFIGURED
              </div>
            ) : (
              data.queues.map((q, idx) => {
                const statusBadge = {
                  FAST: { color: "#3fb950", bg: "rgba(63, 185, 80, 0.15)", border: "#3fb950" },
                  NORMAL: { color: "#58a6ff", bg: "rgba(88, 166, 255, 0.15)", border: "#58a6ff" },
                  SLOW: { color: "#f0883e", bg: "rgba(240, 136, 62, 0.15)", border: "#f0883e" },
                  STOPPED: { color: "#f85149", bg: "rgba(248, 81, 73, 0.15)", border: "#f85149" },
                }[q.flow_status] || { color: "#8b949e", bg: "rgba(255,255,255,0.05)", border: "#8b949e" };

                return (
                  <div
                    key={idx}
                    onClick={() => navigate("/crowd-management")}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "8px 10px",
                      background: "rgba(255, 255, 255, 0.02)",
                      border: "1px solid var(--cc-border)",
                      borderRadius: 6,
                      cursor: "pointer",
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 12, color: "var(--cc-text-primary)" }}>{q.queue_name}</div>
                      <div style={{ fontSize: 10, color: "var(--cc-text-muted)", fontFamily: "var(--cc-font-mono)" }}>{q.camera_code}</div>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 13, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-primary)" }}>
                          {q.current_people.toLocaleString()}
                        </div>
                        <div style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>
                          {q.estimated_wait_minutes ? `~${q.estimated_wait_minutes} min wait` : "Minimal wait"}
                        </div>
                      </div>

                      <div
                        style={{
                          fontSize: 12,
                          fontWeight: 700,
                          fontFamily: "var(--cc-font-mono)",
                          padding: "5px 12px",
                          borderRadius: 6,
                          background: statusBadge.bg,
                          color: statusBadge.color,
                          border: `1.5px solid ${statusBadge.border}`,
                          minWidth: 90,
                          textAlign: "center",
                        }}
                      >
                        ● {q.flow_status}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* ZONE DENSITY */}
        <div className="cc-card" style={{ padding: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          <div className="cc-section-header" style={{ padding: "10px 14px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontWeight: 700, fontSize: 13, color: "var(--cc-text-primary)", letterSpacing: "0.04em" }}>
              ZONE DENSITY
            </span>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <select
                value={selectedZoneCode}
                onChange={(e) => setSelectedZoneCode(e.target.value)}
                style={{
                  fontSize: 10, padding: "3px 8px", borderRadius: 4,
                  background: "var(--cc-bg-input)", border: "1px solid var(--cc-border)",
                  color: "var(--cc-text-primary)", cursor: "pointer",
                }}
              >
                <option value="all">All Zones</option>
                <option value="ZONE-A">Zone A</option>
                <option value="ZONE-B">Zone B</option>
                <option value="ZONE-C">Zone C</option>
                <option value="ZONE-D">Zone D</option>
              </select>
              <button className="cc-btn cc-btn-sm" style={{ fontSize: 10 }} onClick={() => navigate("/crowd-management")}>
                View All Zones
              </button>
            </div>
          </div>

          <div style={{ padding: "8px 12px", flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
            {loading && !data ? (
              <div style={{ padding: 20, textAlign: "center", color: "var(--cc-text-muted)" }}>Loading Zone Density...</div>
            ) : (() => {
                const visibleZones = (data?.zones || []).filter(
                  (z) => selectedZoneCode === "all" || (z.zone_code || z.zone_name?.replace("Zone ", "ZONE-")) === selectedZoneCode
                );
                if (visibleZones.length === 0) {
                  return (
                    <div style={{ padding: 24, textAlign: "center", color: "var(--cc-text-muted)", fontSize: 12 }}>
                      <i className="bi bi-geo-alt" style={{ fontSize: 24, display: "block", marginBottom: 6 }} />
                      NO ACTIVE ZONES MONITORED
                    </div>
                  );
                }
                return visibleZones.map((z, idx) => {
                  const statusStyle = {
                    GREEN: { color: "#3fb950", bg: "rgba(63, 185, 80, 0.15)", border: "#3fb950" },
                    ORANGE: { color: "#f0883e", bg: "rgba(240, 136, 62, 0.15)", border: "#f0883e" },
                    RED: { color: "#f85149", bg: "rgba(248, 81, 73, 0.15)", border: "#f85149" },
                  }[z.status] || { color: "#3fb950", bg: "rgba(63, 185, 80, 0.15)", border: "#3fb950" };

                return (
                  <div
                    key={idx}
                    onClick={() => navigate("/crowd-management")}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "8px 10px",
                      background: "rgba(255, 255, 255, 0.02)",
                      border: "1px solid var(--cc-border)",
                      borderRadius: 6,
                      cursor: "pointer",
                    }}
                  >
                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                        <span style={{ fontWeight: 600, fontSize: 12, color: "var(--cc-text-primary)" }}>{z.zone_name}</span>
                        <span style={{ fontSize: 13, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-primary)" }}>
                          {(z.current_people !== undefined && z.current_people !== null ? z.current_people : 0).toLocaleString()} <span style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>/ {(z.capacity ?? 0).toLocaleString()}</span>
                        </span>
                      </div>
                      {/* Density progress bar */}
                      <div style={{ width: "100%", height: 5, background: "rgba(255,255,255,0.08)", borderRadius: 3, overflow: "hidden" }}>
                        <div
                          style={{
                            width: `${Math.min(100, z.density_pct)}%`,
                            height: "100%",
                            background: statusStyle.color,
                            transition: "width 0.4s ease",
                          }}
                        />
                      </div>
                    </div>

                    <div style={{ marginLeft: 16 }}>
                      <div
                        style={{
                          fontSize: 12,
                          fontWeight: 700,
                          fontFamily: "var(--cc-font-mono)",
                          padding: "5px 12px",
                          borderRadius: 6,
                          background: statusStyle.bg,
                          color: statusStyle.color,
                          border: `1.5px solid ${statusStyle.border}`,
                          minWidth: 90,
                          textAlign: "center",
                        }}
                      >
                        ● {z.status}
                      </div>
                    </div>
                  </div>
                );
              });
            })()}
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* SECTION 4 & 10: DAILY VISITOR TREND + TOP RISK AREAS */}
      {/* ========================================================================= */}
      <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 10 }}>
        {/* FESTIVAL DAY-WISE FOOTFALL & AUDIT */}
        <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
          <div className="cc-section-header" style={{ padding: "10px 14px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <i className="bi bi-calendar3" style={{ color: "var(--cc-accent)" }} />
              <span style={{ fontWeight: 700, fontSize: 13, color: "var(--cc-text-primary)", letterSpacing: "0.04em" }}>
                {fest10Data?.days ? `${fest10Data.days.length}-DAY FESTIVAL DAY-WISE REPORT` : "FESTIVAL DAY-WISE REPORT"}
              </span>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button
                className="cc-btn cc-btn-sm"
                style={{ fontSize: 10 }}
                onClick={async () => {
                  try {
                    setDownloadingCsv(true);
                    await downloadFestival10DaysCsv();
                  } catch (e) {
                    alert("Export failed: " + e.message);
                  } finally {
                    setDownloadingCsv(false);
                  }
                }}
                disabled={downloadingCsv}
              >
                <i className={`bi ${downloadingCsv ? "bi-hourglass-split" : "bi-download"}`} /> CSV
              </button>
              <button className="cc-btn cc-btn-sm" style={{ fontSize: 10 }} onClick={() => navigate("/reports")}>
                Full Report
              </button>
            </div>
          </div>

          <div style={{ padding: "6px 12px", maxHeight: 290, overflowY: "auto" }}>
            <table className="cc-table" style={{ width: "100%", fontSize: 11 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>Day</th>
                  <th style={{ textAlign: "left" }}>Date</th>
                  <th style={{ textAlign: "right", color: "#3fb950" }}>Entry (4 Gates)</th>
                  <th style={{ textAlign: "right", color: "#f85149" }}>Exit (4 Gates)</th>
                  <th style={{ textAlign: "right", color: "var(--cc-accent)" }}>Total Visitors</th>
                  <th style={{ textAlign: "center" }}>Peak</th>
                  <th style={{ textAlign: "center" }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {!fest10Data?.days || fest10Data.days.length === 0 ? (
                  <tr><td colSpan={7} style={{ textAlign: "center", padding: 16, color: "var(--cc-text-muted)" }}>Loading Festival Day-Wise Report...</td></tr>
                ) : (
                  fest10Data.days.map((row) => {
                    const isToday = row.status === "TODAY";
                    return (
                      <tr key={row.day_number} style={{ background: isToday ? "rgba(188,140,255,0.07)" : "transparent" }}>
                        <td style={{ fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: isToday ? "var(--cc-accent)" : "inherit" }}>
                          Day {row.day_number}
                        </td>
                        <td style={{ fontFamily: "var(--cc-font-mono)" }}>
                          {row.date.slice(5)} ({row.day_name.slice(0, 3)})
                        </td>
                        <td style={{ textAlign: "right", color: "#3fb950", fontFamily: "var(--cc-font-mono)", fontWeight: 600 }}>
                          {row.entry_count.toLocaleString()}
                        </td>
                        <td style={{ textAlign: "right", color: "#f85149", fontFamily: "var(--cc-font-mono)", fontWeight: 600 }}>
                          {row.exit_count.toLocaleString()}
                        </td>
                        <td style={{ textAlign: "right", fontWeight: 800, color: "var(--cc-accent)", fontFamily: "var(--cc-font-mono)" }}>
                          {row.entry_count.toLocaleString()}
                        </td>
                        <td style={{ textAlign: "center", fontSize: 10, color: "var(--cc-text-muted)" }}>
                          {row.peak_hour}
                        </td>
                        <td style={{ textAlign: "center" }}>
                          <span
                            style={{
                              fontSize: 9,
                              fontWeight: 700,
                              padding: "2px 6px",
                              borderRadius: 4,
                              background: isToday ? "rgba(188,140,255,0.2)" : row.status === "COMPLETED" ? "rgba(63,185,80,0.15)" : "rgba(255,255,255,0.05)",
                              color: isToday ? "#bc8cff" : row.status === "COMPLETED" ? "#3fb950" : "var(--cc-text-muted)",
                            }}
                          >
                            {row.status}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* TOP RISK AREAS */}
        <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
          <div className="cc-section-header" style={{ padding: "10px 14px", display: "flex", justifyContent: "space-between" }}>
            <span style={{ fontWeight: 700, fontSize: 13, color: "var(--cc-text-primary)", letterSpacing: "0.04em" }}>
              TOP RISK AREAS
            </span>
            <span style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>Max 5 Hotspots</span>
          </div>

          <div style={{ padding: "8px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
            {loading && !data ? (
              <div style={{ padding: 20, textAlign: "center", color: "var(--cc-text-muted)" }}>Analyzing risk areas...</div>
            ) : !data?.top_risk_areas || data.top_risk_areas.length === 0 ? (
              <div style={{ padding: 20, textAlign: "center", color: "#3fb950", fontSize: 12 }}>
                <i className="bi bi-shield-check" style={{ fontSize: 24, display: "block", marginBottom: 4 }} />
                ALL ZONES & QUEUES WITHIN NORMAL THRESHOLDS
              </div>
            ) : (
              data.top_risk_areas.map((r, idx) => (
                <div
                  key={idx}
                  onClick={() => navigate("/crowd-management")}
                  style={{
                    padding: "8px 10px",
                    background: "rgba(255, 255, 255, 0.02)",
                    borderLeft: `3px solid ${r.risk_level === "RED" ? "#f85149" : "#f0883e"}`,
                    borderTop: "1px solid var(--cc-border)",
                    borderRight: "1px solid var(--cc-border)",
                    borderBottom: "1px solid var(--cc-border)",
                    borderRadius: 4,
                    cursor: "pointer",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontWeight: 600, fontSize: 12, color: "var(--cc-text-primary)" }}>{r.name}</span>
                    <span style={{ fontSize: 10, fontWeight: 700, color: r.risk_level === "RED" ? "#f85149" : "#f0883e", fontFamily: "var(--cc-font-mono)" }}>
                      ● {r.risk_level}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: "var(--cc-text-muted)", marginTop: 2 }}>{r.reason}</div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* SECTION 11, 12 & 14: FRS REVIEW (MAX 2) + ACTIVE EVENTS + AI FLEET HEALTH */}
      {/* ========================================================================= */}
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr 1fr", gap: 10 }}>
        {/* RECENT FRS REVIEW (MAX 2) */}
        <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
          <div className="cc-section-header" style={{ padding: "10px 14px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontWeight: 700, fontSize: 13, color: "var(--cc-text-primary)", letterSpacing: "0.04em" }}>
              RECENT FRS REVIEW
            </span>
            <button className="cc-btn cc-btn-sm" style={{ fontSize: 10 }} onClick={() => navigate("/frs")}>
              Review Queue
            </button>
          </div>

          <div style={{ padding: "8px 12px", display: "flex", flexDirection: "column", gap: 8 }}>
            {!data?.recent_frs_candidates || data.recent_frs_candidates.length === 0 ? (
              <div style={{ padding: 18, textAlign: "center", color: "var(--cc-text-muted)", fontSize: 12 }}>
                <i className="bi bi-person-check" style={{ fontSize: 24, display: "block", marginBottom: 4 }} />
                NO PENDING FRS CANDIDATES
              </div>
            ) : (
              data.recent_frs_candidates.slice(0, 2).map((c) => (
                <div
                  key={c.id}
                  onClick={() => navigate("/frs")}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: 8,
                    background: "rgba(255, 255, 255, 0.02)",
                    border: "1px solid var(--cc-border)",
                    borderRadius: 6,
                    cursor: "pointer",
                  }}
                >
                  <div style={{ width: 44, height: 44, borderRadius: 4, overflow: "hidden", background: "#050e18", flexShrink: 0, border: "1px solid var(--cc-border)" }}>
                    {c.detected_image ? (
                      <img src={c.detected_image} alt="Detected" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                    ) : (
                      <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--cc-text-muted)" }}>
                        <i className="bi bi-person" />
                      </div>
                    )}
                  </div>

                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontWeight: 600, fontSize: 12, color: "var(--cc-text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {c.person_name}
                      </span>
                      <span style={{ fontSize: 11, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: "#3fb950" }}>
                        {c.match_score}%
                      </span>
                    </div>
                    <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 2 }}>
                      {c.camera_name} • {c.time_str}
                    </div>
                    <div style={{ display: "inline-block", fontSize: 9, fontWeight: 700, color: "var(--cc-yellow)", background: "rgba(210, 153, 34, 0.15)", padding: "1px 5px", borderRadius: 3, marginTop: 4 }}>
                      REVIEW REQUIRED
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* ACTIVE CRITICAL EVENTS (MAX 5) */}
        <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
          <div className="cc-section-header" style={{ padding: "10px 14px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontWeight: 700, fontSize: 13, color: "var(--cc-text-primary)", letterSpacing: "0.04em" }}>
              ACTIVE CRITICAL EVENTS
            </span>
            <button className="cc-btn cc-btn-sm" style={{ fontSize: 10 }} onClick={() => navigate("/alerts")}>
              All Alerts
            </button>
          </div>

          <div style={{ padding: "8px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
            {!data?.active_critical_events || data.active_critical_events.length === 0 ? (
              <div style={{ padding: 18, textAlign: "center", color: "#3fb950", fontSize: 12 }}>
                <i className="bi bi-check2-circle" style={{ fontSize: 24, display: "block", marginBottom: 4 }} />
                NO ACTIVE CRITICAL ALERTS
              </div>
            ) : (
              data.active_critical_events.slice(0, 4).map((evt) => (
                <div
                  key={evt.id}
                  onClick={() => navigate("/alerts")}
                  style={{
                    padding: "6px 8px",
                    background: "rgba(255, 255, 255, 0.02)",
                    borderLeft: `3px solid ${evt.severity === "CRITICAL" ? "#f85149" : "#f0883e"}`,
                    borderTop: "1px solid var(--cc-border)",
                    borderRight: "1px solid var(--cc-border)",
                    borderBottom: "1px solid var(--cc-border)",
                    borderRadius: 4,
                    cursor: "pointer",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontWeight: 600, fontSize: 11, color: "var(--cc-text-primary)" }}>{evt.type}</span>
                    <span style={{ fontSize: 9, fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-muted)" }}>{evt.time}</span>
                  </div>
                  <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 2 }}>{evt.location}</div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* AI & CAMERA FLEET HEALTH */}
        <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
          <div className="cc-section-header" style={{ padding: "10px 14px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontWeight: 700, fontSize: 13, color: "var(--cc-text-primary)", letterSpacing: "0.04em" }}>
              AI & CAMERA HEALTH
            </span>
            <button className="cc-btn cc-btn-sm" style={{ fontSize: 10 }} onClick={() => navigate("/ai-deployment")}>
              Deployments
            </button>
          </div>

          <div style={{ padding: "10px 12px", display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 8px", background: "rgba(255,255,255,0.02)", borderRadius: 4, border: "1px solid var(--cc-border)" }}>
              <span style={{ fontSize: 11, color: "var(--cc-text-secondary)" }}>Cameras Online</span>
              <span style={{ fontSize: 12, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: (data?.health?.cameras_online || 0) > 0 ? "#3fb950" : "#8b949e" }}>
                {data?.health?.cameras_online || 0} / {data?.health?.cameras_total || 0}
              </span>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 8px", background: "rgba(255,255,255,0.02)", borderRadius: 4, border: "1px solid var(--cc-border)" }}>
              <span style={{ fontSize: 11, color: "var(--cc-text-secondary)" }}>Crowd AI (YOLO11x)</span>
              <span style={{ fontSize: 11, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: (data?.health?.crowd_ai_running || 0) > 0 ? "#3fb950" : "#8b949e" }}>
                {(data?.health?.crowd_ai_running || 0) > 0 ? `${data.health.crowd_ai_running} RUNNING` : "STOPPED"}
              </span>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 8px", background: "rgba(255,255,255,0.02)", borderRadius: 4, border: "1px solid var(--cc-border)" }}>
              <span style={{ fontSize: 11, color: "var(--cc-text-secondary)" }}>Queue AI Pipelines</span>
              <span style={{ fontSize: 11, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: (data?.health?.queue_ai_running || 0) > 0 ? "#3fb950" : "#8b949e" }}>
                {(data?.health?.queue_ai_running || 0) > 0 ? `${data.health.queue_ai_running} RUNNING` : "STOPPED"}
              </span>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 8px", background: "rgba(255,255,255,0.02)", borderRadius: 4, border: "1px solid var(--cc-border)" }}>
              <span style={{ fontSize: 11, color: "var(--cc-text-secondary)" }}>FRS Engine (Buffalo_L)</span>
              <span style={{ fontSize: 11, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: (data?.health?.frs_running || 0) > 0 ? "#3fb950" : "#8b949e" }}>
                {(data?.health?.frs_running || 0) > 0 ? `${data.health.frs_running} RUNNING` : "STOPPED"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
