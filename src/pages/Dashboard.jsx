// Dashboard — Clean BYC AI Command Center Dashboard
import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import { getDashboardSummary } from "../services/dashboardService.js";
import { getFestival10DaysAnalytics, downloadFestival10DaysCsv } from "../services/analyticsService.js";
import { realtimeService } from "../services/realtimeService.js";
import { useDashboardStore } from "../store/useDashboardStore.js";
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

  // Zustand State Selectors (fine-grained to prevent redundant renders)
  const dateRange = useDashboardStore((s) => s.dateRange);
  const data = useDashboardStore((s) => s.data);
  const loading = useDashboardStore((s) => s.loading);
  const isRefreshing = useDashboardStore((s) => s.isRefreshing);
  const error = useDashboardStore((s) => s.error);
  const dataStatus = useDashboardStore((s) => s.dataStatus);
  const setDateRange = useDashboardStore((s) => s.setDateRange);

  const [selectedZoneCode, setSelectedZoneCode] = useState("all");
  const [clockStr, setClockStr] = useState("");
  const [fest10Data, setFest10Data] = useState(null);
  const [downloadingCsv, setDownloadingCsv] = useState(false);
  const inFlightRef = useRef(false);
  const pendingRef = useRef(false);
  const timerRef = useRef(null);
  const isMountedRef = useRef(true);

  // 1. Live Clock
  useEffect(() => {
    const tick = () =>
      setClockStr(new Date().toLocaleTimeString("en-IN", { hour12: false, timeZone: "Asia/Kolkata" }));
    tick();
    const iv = setInterval(tick, 1000);
    return () => clearInterval(iv);
  }, []);

  // 2. Fetch authoritative dashboard summary with stable callback
  const loadData = useCallback(async (silent = false) => {
    if (inFlightRef.current) {
      pendingRef.current = true;
      return;
    }
    inFlightRef.current = true;
    const store = useDashboardStore.getState();
    if (!silent && !store.data) store.setLoading(true);
    if (!silent) store.setIsRefreshing(true);

    try {
      const range = (store.dateRange || "today").toLowerCase();
      const [res, festRes] = await Promise.allSettled([
        getDashboardSummary(range),
        getFestival10DaysAnalytics(),
      ]);
      if (!isMountedRef.current) return;
      if (res.status === "fulfilled" && res.value) {
        store.setDashboardData(res.value);
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
          if (isMountedRef.current) loadData(true);
        }, 1000);
      }
    }
  }, []);

  // 3. Mount & Polling with Tab Visibility Awareness
  useEffect(() => {
    isMountedRef.current = true;
    loadData();

    const scheduleNext = () => {
      clearTimeout(timerRef.current);
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      timerRef.current = setTimeout(async () => {
        if (isMountedRef.current && document.visibilityState === "visible") {
          await loadData(true);
          scheduleNext();
        }
      }, 5000);
    };

    scheduleNext();

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        loadData(true);
        scheduleNext();
      } else {
        clearTimeout(timerRef.current);
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    // 4. WebSocket Real-time event listener (Instant 0ms count reflection)
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
        if (dataPayload?.total_visitors_festival !== undefined) {
          useDashboardStore.getState().patchDashboardMetrics({
            total_visitors_festival: dataPayload.total_visitors_festival,
            today_entries: dataPayload.today_entries,
            today_exits: dataPayload.today_exits,
            current_occupancy: dataPayload.current_occupancy,
          });
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
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      unsubWs();
      unsubStatus();
    };
  }, [loadData]);

  // 5. Reload when dateRange changes
  useEffect(() => {
    loadData();
  }, [dateRange, loadData]);

  // Handle Date Range Change
  const handleDateRangeChange = (rangeId) => {
    setDateRange(rangeId.toUpperCase());
  };

  // Memoized Chart Options
  const hourlyChartOption = useMemo(() => {
    if (!data?.hourly_flow || data.hourly_flow.length === 0) return null;

    const hours = data.hourly_flow.map((p) => p.hour);
    const entries = data.hourly_flow.map((p) => p.entry);
    const exits = data.hourly_flow.map((p) => p.exit);

    return {
      backgroundColor: "transparent",
      textStyle: ct.textStyle,
      legend: {
        top: 6,
        right: 16,
        textStyle: ct.legendText,
        data: ["ENTRY", "EXIT"],
        icon: "roundRect",
      },
      grid: { top: 40, right: 20, bottom: 30, left: 50 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(13, 17, 23, 0.95)",
        borderColor: "rgba(255, 255, 255, 0.15)",
        borderWidth: 1,
        textStyle: { color: "#fff", fontSize: 12 },
        formatter: (params) => {
          let str = `<div style="font-weight:700;margin-bottom:4px;color:#8b949e">${params[0]?.axisValueLabel || ""}</div>`;
          params.forEach((p) => {
            const col = p.seriesName === "ENTRY" ? "#3fb950" : "#58a6ff";
            str += `<div style="display:flex;justify-content:space-between;gap:16px;color:${col}">
              <span>${p.seriesName}:</span>
              <span style="font-family:monospace;font-weight:700">${p.value?.toLocaleString()} pax</span>
            </div>`;
          });
          const ent = params.find((p) => p.seriesName === "ENTRY")?.value || 0;
          const ext = params.find((p) => p.seriesName === "EXIT")?.value || 0;
          const net = ent - ext;
          const netCol = net >= 0 ? "#3fb950" : "#f85149";
          str += `<div style="margin-top:4px;padding-top:4px;border-top:1px solid rgba(255,255,255,0.1);display:flex;justify-content:space-between;color:${netCol}">
            <span>NET FLOW:</span>
            <span style="font-family:monospace;font-weight:700">${net > 0 ? "+" : ""}${net.toLocaleString()} pax</span>
          </div>`;
          return str;
        },
      },
      xAxis: {
        type: "category",
        data: hours,
        axisLine: ct.axisLine,
        axisTick: { show: false },
        axisLabel: { color: ct.axisLabelColor, fontSize: 10 },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        axisLine: ct.axisLine,
        splitLine: ct.splitLine,
        axisLabel: {
          formatter: (v) => (v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v),
          color: ct.axisLabelColor,
          fontSize: 10,
        },
      },
      series: [
        {
          name: "ENTRY",
          type: "line",
          data: entries,
          smooth: true,
          showSymbol: false,
          lineStyle: { color: "#3fb950", width: 2.5 },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(63, 185, 80, 0.35)" },
                { offset: 1, color: "rgba(63, 185, 80, 0.0)" },
              ],
            },
          },
        },
        {
          name: "EXIT",
          type: "line",
          data: exits,
          smooth: true,
          showSymbol: false,
          lineStyle: { color: "#58a6ff", width: 2.5 },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(88, 166, 255, 0.35)" },
                { offset: 1, color: "rgba(88, 166, 255, 0.0)" },
              ],
            },
          },
        },
      ],
    };
  }, [data?.hourly_flow, ct]);

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
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 1fr 1fr 1.2fr", gap: 10 }}>
        {/* HERO KPI */}
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
              Total Footfall (Entry + Exit)
            </span>
            <span style={{ fontSize: 10, background: "rgba(188, 140, 255, 0.2)", border: "1px solid rgba(188, 140, 255, 0.4)", color: "#bc8cff", padding: "1px 6px", borderRadius: 4, fontFamily: "var(--cc-font-mono)", fontWeight: 700 }}>
              {fest10Data ? `Day ${fest10Data.current_day} of 10` : (data?.festival_day_label || "Day 1 of 10")}
            </span>
          </div>

          <div style={{ margin: "6px 0" }}>
            <div style={{ fontSize: 28, fontWeight: 800, fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-primary)", letterSpacing: "0.02em" }}>
              {loading && !data ? "—" : ((data?.today_entries || 0) + (data?.today_exits || 0)).toLocaleString()}
            </div>
            <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>
              Formula: <strong style={{ color: "#3fb950" }}>{(data?.today_entries || 0).toLocaleString()}</strong> (In) + <strong style={{ color: "#f85149" }}>{(data?.today_exits || 0).toLocaleString()}</strong> (Out)
            </div>
          </div>
        </div>

        {/* PEOPLE MOVEMENT: ENTRY */}
        <div className="cc-card" style={{ padding: "12px 14px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: "var(--cc-text-muted)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
            Total Entry (4 Gates)
          </span>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: "#3fb950" }}>
            {loading && !data ? "—" : (data?.today_entries || 0).toLocaleString()}
          </div>
          <span style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>CAM-ENTRY 01–04 crossings</span>
        </div>

        {/* PEOPLE MOVEMENT: EXIT */}
        <div className="cc-card" style={{ padding: "12px 14px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: "var(--cc-text-muted)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
            Total Exit (4 Gates)
          </span>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: "#f85149" }}>
            {loading && !data ? "—" : (data?.today_exits || 0).toLocaleString()}
          </div>
          <span style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>CAM-EXIT 01–04 crossings</span>
        </div>

        {/* PEOPLE MOVEMENT: NET FLOW */}
        <div className="cc-card" style={{ padding: "12px 14px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: "var(--cc-text-muted)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
            Net Flow
          </span>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: (data?.net_flow || 0) >= 0 ? "#3fb950" : "#f85149" }}>
            {loading && !data ? "—" : `${(data?.net_flow || 0) > 0 ? "+" : ""}${(data?.net_flow || 0).toLocaleString()}`}
          </div>
          <span style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>Entry minus Exit delta</span>
        </div>

        {/* PEOPLE MOVEMENT: CURRENT OCCUPANCY */}
        <div className="cc-card" style={{ padding: "12px 14px", display: "flex", flexDirection: "column", justifyContent: "space-between", borderLeft: "3px solid #e3b341" }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: "var(--cc-text-muted)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
            Inside Complex (Net)
          </span>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: "#e3b341" }}>
            {loading && !data ? "—" : (data?.current_occupancy || 0).toLocaleString()}
          </div>
          <span style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>Total Entry minus Total Exit</span>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* SECTION 3 & 4: HOURLY VISITOR FLOW & DATE RANGE SELECTOR */}
      {/* ========================================================================= */}
      <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
        <div className="cc-section-header" style={{ padding: "10px 14px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ fontWeight: 700, fontSize: 13, color: "var(--cc-text-primary)", letterSpacing: "0.04em" }}>
              VISITOR FLOW — HOURLY
            </span>
            {data?.peak_hour && data.peak_hour !== "—" && (
              <span style={{ fontSize: 10, background: "rgba(227, 179, 65, 0.15)", border: "1px solid var(--cc-yellow)", color: "var(--cc-yellow)", padding: "1px 6px", borderRadius: 4, fontFamily: "var(--cc-font-mono)" }}>
                Peak: {data.peak_hour}
              </span>
            )}
          </div>

          <div style={{ display: "flex", gap: 4 }}>
            {DATE_RANGE_OPTIONS.map((opt) => (
              <button
                key={opt.id}
                onClick={() => handleDateRangeChange(opt.id)}
                style={{
                  padding: "3px 8px",
                  fontSize: 10,
                  fontFamily: "var(--cc-font-mono)",
                  fontWeight: dateRange === opt.id.toUpperCase() ? 700 : 500,
                  background: dateRange === opt.id.toUpperCase() ? "var(--cc-blue)" : "rgba(255,255,255,0.04)",
                  color: dateRange === opt.id.toUpperCase() ? "#fff" : "var(--cc-text-secondary)",
                  border: "1px solid var(--cc-border)",
                  borderRadius: 4,
                  cursor: "pointer",
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ padding: "0 10px 6px 10px" }}>
          {loading && !data ? (
            <div style={{ height: 200, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--cc-text-muted)" }}>
              Loading Hourly Visitor Flow...
            </div>
          ) : hourlyChartOption ? (
            <ReactECharts option={hourlyChartOption} style={{ height: 210, width: "100%" }} notMerge={true} lazyUpdate={true} />
          ) : (
            <div style={{ height: 200, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--cc-text-muted)" }}>
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
                          {q.current_people.toLocaleString()} <span style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>pax</span>
                        </div>
                        <div style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>
                          {q.estimated_wait_minutes ? `~${q.estimated_wait_minutes} min wait` : "Minimal wait"}
                        </div>
                      </div>

                      <div
                        style={{
                          fontSize: 10,
                          fontWeight: 700,
                          fontFamily: "var(--cc-font-mono)",
                          padding: "2px 8px",
                          borderRadius: 4,
                          background: statusBadge.bg,
                          color: statusBadge.color,
                          border: `1px solid ${statusBadge.border}`,
                          minWidth: 70,
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
            ) : !data?.zones || data.zones.length === 0 ? (
              <div style={{ padding: 24, textAlign: "center", color: "var(--cc-text-muted)", fontSize: 12 }}>
                <i className="bi bi-geo-alt" style={{ fontSize: 24, display: "block", marginBottom: 6 }} />
                NO ACTIVE ZONES FOUND
              </div>
            ) : (
              data.zones
                .slice(0, 4)
                .filter((z) => selectedZoneCode === "all" || (z.zone_code || z.zone_name?.replace("Zone ", "ZONE-")) === selectedZoneCode)
                .map((z, idx) => {
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
                          fontSize: 10,
                          fontWeight: 700,
                          fontFamily: "var(--cc-font-mono)",
                          padding: "2px 8px",
                          borderRadius: 4,
                          background: statusStyle.bg,
                          color: statusStyle.color,
                          border: `1px solid ${statusStyle.border}`,
                          minWidth: 70,
                          textAlign: "center",
                        }}
                      >
                        ● {z.status}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* SECTION 4 & 10: DAILY VISITOR TREND + TOP RISK AREAS */}
      {/* ========================================================================= */}
      <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 10 }}>
        {/* 10-DAY FESTIVAL DAY-WISE FOOTFALL & AUDIT */}
        <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
          <div className="cc-section-header" style={{ padding: "10px 14px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <i className="bi bi-calendar3" style={{ color: "var(--cc-accent)" }} />
              <span style={{ fontWeight: 700, fontSize: 13, color: "var(--cc-text-primary)", letterSpacing: "0.04em" }}>
                10-DAY FESTIVAL DAY-WISE REPORT
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
                  <th style={{ textAlign: "right", color: "var(--cc-accent)" }}>Total (Entry+Exit)</th>
                  <th style={{ textAlign: "center" }}>Peak</th>
                  <th style={{ textAlign: "center" }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {!fest10Data?.days || fest10Data.days.length === 0 ? (
                  <tr><td colSpan={7} style={{ textAlign: "center", padding: 16, color: "var(--cc-text-muted)" }}>Loading 10-Day Festival Report...</td></tr>
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
                          {row.total_count.toLocaleString()}
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
