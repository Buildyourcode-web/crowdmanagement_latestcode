// Crowd Management Command Center — Unified Crowd, Queue & Zone Intelligence Dashboard
import { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import KpiCard from "../components/common/KpiCard.jsx";
import StatusBadge from "../components/common/StatusBadge.jsx";
import { LoadingState, ErrorState } from "../components/common/States.jsx";
import { getCrowdManagementSummary } from "../services/crowdManagementService.js";
import { useAppStore } from "../store/useAppStore.js";
import { getChartTheme } from "../utils/chartTheme.js";

const WS_URL = `ws://${window.location.hostname}:8000/ws/v1/events`;

const RISK_COLORS = {
  LOW: "#3fb950",
  MODERATE: "#e3b341",
  MEDIUM: "#e3b341",
  HIGH: "#f0883e",
  CRITICAL: "#f85149",
};

export default function CrowdManagement() {
  const navigate = useNavigate();
  const theme = useAppStore((s) => s.theme);
  const ct = getChartTheme(theme);

  // Filter States
  const [modeFilter, setModeFilter] = useState("all"); // all, queue, zone
  const [cameraFilter, setCameraFilter] = useState("all");
  const [timeFilter, setTimeFilter] = useState("today"); // 15m, 1h, today
  const [riskFilter, setRiskFilter] = useState("all"); // all, low, medium, high, critical

  // Data & Lifecycle States
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef(null);

  const inFlightRef = useRef(false);
  const pendingRefreshRef = useRef(false);
  const timerRef = useRef(null);
  const isMountedRef = useRef(true);

  // Fetch summary from backend aggregation endpoint with in-flight guard
  const loadSummary = useCallback(async (silent = false) => {
    if (inFlightRef.current) {
      pendingRefreshRef.current = true;
      return;
    }
    inFlightRef.current = true;
    if (!silent) setIsRefreshing(true);
    try {
      const res = await getCrowdManagementSummary({
        time_range: timeFilter,
        mode: modeFilter,
        camera_id: cameraFilter,
        risk_level: riskFilter,
      });
      if (!isMountedRef.current) return;
      const data = res?.data || res;
      setSummary(data);
      setError(null);
    } catch (err) {
      console.error("[CrowdManagement] Fetch error:", err);
      if (!isMountedRef.current) return;
      if (!silent) setError("Failed to load Crowd Management telemetry.");
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
        setIsRefreshing(false);
      }
      inFlightRef.current = false;

      // Coalesce queued refresh if triggered during in-flight fetch
      if (pendingRefreshRef.current && isMountedRef.current) {
        pendingRefreshRef.current = false;
        loadSummary(true);
      }
    }
  }, [timeFilter, modeFilter, cameraFilter, riskFilter]);

  // Request-aware polling with tab visibility control
  useEffect(() => {
    isMountedRef.current = true;
    loadSummary();

    const scheduleNext = () => {
      clearTimeout(timerRef.current);
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      timerRef.current = setTimeout(async () => {
        if (isMountedRef.current && document.visibilityState === "visible") {
          await loadSummary(true);
          scheduleNext();
        }
      }, 5000);
    };

    scheduleNext();

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        loadSummary(true);
        scheduleNext();
      } else {
        clearTimeout(timerRef.current);
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      isMountedRef.current = false;
      clearTimeout(timerRef.current);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [loadSummary]);

  // WebSocket connection for real-time live events & telemetry
  useEffect(() => {
    let ws;
    let reconnectTimeout;

    const connectWS = () => {
      try {
        ws = new WebSocket(WS_URL);
        wsRef.current = ws;

        ws.onopen = () => {
          setWsConnected(true);
        };

        ws.onmessage = (evt) => {
          try {
            const msg = JSON.parse(evt.data);
            // Trigger quick silent refresh on crowd or queue events
            if (
              msg.type === "crowd_update" ||
              msg.type === "zone_update" ||
              msg.type === "queue_update" ||
              msg.type === "new_alert" ||
              msg.type === "PIPELINE_STARTED" ||
              msg.type === "PIPELINE_STOPPED"
            ) {
              loadSummary(true);
            }
          } catch {
            // ignore non-json
          }
        };

        ws.onclose = () => {
          setWsConnected(false);
          reconnectTimeout = setTimeout(connectWS, 4000);
        };

        ws.onerror = () => {
          setWsConnected(false);
        };
      } catch {
        setWsConnected(false);
        reconnectTimeout = setTimeout(connectWS, 4000);
      }
    };

    connectWS();
    return () => {
      clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, [loadSummary]);

  if (loading && !summary) return <LoadingState />;
  if (error && !summary) return <ErrorState message={error} onRetry={() => loadSummary()} />;

  // Destructure summary data
  const {
    total_people = 0,
    total_entries = 0,
    total_exits = 0,
    net_change = 0,
    active_cameras = 0,
    total_cameras = 0,
    active_queues = 0,
    high_risk_zones = 0,
    longest_queue = 0,
    longest_wait_seconds = 0,
    overall_risk = "LOW",
    queues = [],
    zones = [],
    cameras = [],
    risk_breakdown = {},
    high_risk_areas = [],
    events = [],
    trends = {},
  } = summary || {};

  // Formatted wait time
  const formattedWait =
    longest_wait_seconds > 0
      ? `${Math.floor(longest_wait_seconds / 60)}m ${longest_wait_seconds % 60}s`
      : "0m";

  // People Movement Chart Options
  const movementData = trends.movement || [];
  const movementChartOption = {
    backgroundColor: "transparent",
    textStyle: ct.textStyle,
    grid: { top: 30, right: 25, bottom: 35, left: 50 },
    legend: {
      data: ["Entries", "Exits", "People Inside"],
      textStyle: { color: ct.textStyle.color, fontSize: 11 },
      top: 0,
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: ct.tooltip.backgroundColor,
      borderColor: ct.tooltip.borderColor,
      borderWidth: ct.tooltip.borderWidth,
      textStyle: ct.tooltip.textStyle,
      extraCssText: ct.tooltip.extraCssText,
    },
    xAxis: {
      type: "category",
      data: movementData.map((d) => d.timestamp_label),
      axisLine: ct.axisLine,
      axisTick: { show: false },
      axisLabel: { color: ct.axisLabelColor, fontSize: 10 },
    },
    yAxis: {
      type: "value",
      axisLine: ct.axisLine,
      splitLine: ct.splitLine,
      axisLabel: {
        formatter: (v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v),
        color: ct.axisLabelColor,
        fontSize: 10,
      },
    },
    series: [
      {
        name: "Entries",
        type: "line",
        smooth: true,
        data: movementData.map((d) => d.entries),
        lineStyle: { color: "#3fb950", width: 2 },
        itemStyle: { color: "#3fb950" },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(63, 185, 80, 0.25)" },
              { offset: 1, color: "rgba(63, 185, 80, 0.0)" },
            ],
          },
        },
      },
      {
        name: "Exits",
        type: "line",
        smooth: true,
        data: movementData.map((d) => d.exits),
        lineStyle: { color: "#f0883e", width: 2 },
        itemStyle: { color: "#f0883e" },
      },
      {
        name: "People Inside",
        type: "line",
        smooth: true,
        data: movementData.map((d) => d.people_inside),
        lineStyle: { color: "#58a6ff", width: 2, type: "dashed" },
        itemStyle: { color: "#58a6ff" },
      },
    ],
  };

  // Queue Trend Chart Options
  const queueTrendData = trends.queue_trend || [];
  const queueChartOption = {
    backgroundColor: "transparent",
    textStyle: ct.textStyle,
    grid: { top: 25, right: 20, bottom: 35, left: 45 },
    legend: {
      data: ["Queue Count", "Inflow Rate", "Outflow Rate"],
      textStyle: { color: ct.textStyle.color, fontSize: 11 },
      top: 0,
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: ct.tooltip.backgroundColor,
      borderColor: ct.tooltip.borderColor,
      borderWidth: ct.tooltip.borderWidth,
      textStyle: ct.tooltip.textStyle,
    },
    xAxis: {
      type: "category",
      data: queueTrendData.map((d) => d.timestamp_label),
      axisLine: ct.axisLine,
      axisTick: { show: false },
      axisLabel: { color: ct.axisLabelColor, fontSize: 10 },
    },
    yAxis: {
      type: "value",
      axisLine: ct.axisLine,
      splitLine: ct.splitLine,
      axisLabel: { color: ct.axisLabelColor, fontSize: 10 },
    },
    series: [
      {
        name: "Queue Count",
        type: "line",
        smooth: true,
        data: queueTrendData.map((d) => d.queue_count),
        lineStyle: { color: "#58a6ff", width: 2 },
        areaStyle: { color: "rgba(88, 166, 255, 0.15)" },
      },
      {
        name: "Inflow Rate",
        type: "bar",
        data: queueTrendData.map((d) => d.inflow_rate),
        itemStyle: { color: "rgba(63, 185, 80, 0.7)" },
        barMaxWidth: 15,
      },
      {
        name: "Outflow Rate",
        type: "bar",
        data: queueTrendData.map((d) => d.outflow_rate),
        itemStyle: { color: "rgba(240, 136, 62, 0.7)" },
        barMaxWidth: 15,
      },
    ],
  };

  // Zone Density Trend Chart Options
  const zoneTrendData = trends.zone_trend || [];
  const zoneKeys =
    zoneTrendData.length > 0 && zoneTrendData[0].densities
      ? Object.keys(zoneTrendData[0].densities)
      : [];
  const zoneColors = ["#58a6ff", "#e3b341", "#f0883e", "#3fb950"];
  const zoneChartOption = {
    backgroundColor: "transparent",
    textStyle: ct.textStyle,
    grid: { top: 25, right: 20, bottom: 35, left: 45 },
    legend: {
      data: zoneKeys,
      textStyle: { color: ct.textStyle.color, fontSize: 11 },
      top: 0,
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: ct.tooltip.backgroundColor,
      borderColor: ct.tooltip.borderColor,
      borderWidth: ct.tooltip.borderWidth,
      textStyle: ct.tooltip.textStyle,
      formatter: (params) => {
        let res = `${params[0]?.axisValue}<br/>`;
        params.forEach((item) => {
          res += `${item.marker} ${item.seriesName}: <strong>${item.value}%</strong><br/>`;
        });
        return res;
      },
    },
    xAxis: {
      type: "category",
      data: zoneTrendData.map((d) => d.timestamp_label),
      axisLine: ct.axisLine,
      axisTick: { show: false },
      axisLabel: { color: ct.axisLabelColor, fontSize: 10 },
    },
    yAxis: {
      type: "value",
      max: 100,
      axisLine: ct.axisLine,
      splitLine: ct.splitLine,
      axisLabel: {
        formatter: "{value}%",
        color: ct.axisLabelColor,
        fontSize: 10,
      },
    },
    series: zoneKeys.map((k, idx) => ({
      name: k,
      type: "line",
      smooth: true,
      data: zoneTrendData.map((d) => d.densities[k] || 0),
      lineStyle: { color: zoneColors[idx % zoneColors.length], width: 2 },
      itemStyle: { color: zoneColors[idx % zoneColors.length] },
    })),
  };

  return (
    <div className="cc-page">
      {/* 1. Header & Live Indicator */}
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <i className="bi bi-people-fill" style={{ color: "var(--cc-text-accent)" }} />
            <span>Crowd Management</span>
          </div>
          <div className="cc-page-subtitle">
            Unified Command Center — Crowd Occupancy, Queue Telemetry & Zone Intelligence
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: 11,
              padding: "4px 10px",
              background: "var(--cc-bg-secondary)",
              borderRadius: "var(--cc-radius)",
              border: "1px solid var(--cc-border)",
            }}
          >
            <span
              className="cc-live-dot"
              style={{ background: wsConnected ? "var(--cc-green)" : "var(--cc-yellow)" }}
            />
            <span style={{ color: wsConnected ? "var(--cc-green)" : "var(--cc-yellow)", fontWeight: 600 }}>
              {wsConnected ? "LIVE STREAM ACTIVE" : "SYNCING VIA REST"}
            </span>
          </div>

          <button
            className="cc-btn cc-btn-secondary"
            onClick={() => loadSummary()}
            disabled={isRefreshing}
            style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}
          >
            <i className={`bi bi-arrow-repeat${isRefreshing ? " spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Filter Control Bar */}
      <div
        className="cc-card"
        style={{
          padding: "10px 14px",
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 12,
          background: "var(--cc-bg-secondary)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
          {/* Mode Filter */}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 11, color: "var(--cc-text-muted)", fontWeight: 600 }}>MODE:</span>
            <div className="cc-btn-group" style={{ display: "flex", gap: 2 }}>
              {[
                { id: "all", label: "All" },
                { id: "queue", label: "Queue" },
                { id: "zone", label: "Zone" },
              ].map((m) => (
                <button
                  key={m.id}
                  className={`cc-btn${modeFilter === m.id ? " cc-btn-primary" : ""}`}
                  style={{ fontSize: 11, padding: "3px 10px" }}
                  onClick={() => setModeFilter(m.id)}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>

          {/* Camera Filter */}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 11, color: "var(--cc-text-muted)", fontWeight: 600 }}>CAMERA:</span>
            <select
              className="cc-select"
              value={cameraFilter}
              onChange={(e) => setCameraFilter(e.target.value)}
              style={{
                fontSize: 11,
                padding: "3px 8px",
                background: "var(--cc-bg-input)",
                color: "var(--cc-text-primary)",
                border: "1px solid var(--cc-border)",
                borderRadius: "var(--cc-radius)",
              }}
            >
              <option value="all">All Cameras ({cameras.length})</option>
              {cameras.map((c) => (
                <option key={c.camera_code} value={c.camera_code}>
                  {c.logical_id_crowd || (c.camera_code?.endsWith("-CROWD") ? c.camera_code : `${c.camera_code}-CROWD`)} — {c.name}
                </option>
              ))}
            </select>
          </div>

          {/* Risk Filter */}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 11, color: "var(--cc-text-muted)", fontWeight: 600 }}>RISK:</span>
            <div className="cc-btn-group" style={{ display: "flex", gap: 2 }}>
              {["all", "low", "medium", "high", "critical"].map((r) => (
                <button
                  key={r}
                  className={`cc-btn${riskFilter === r ? " cc-btn-primary" : ""}`}
                  style={{ fontSize: 11, padding: "3px 9px", textTransform: "capitalize" }}
                  onClick={() => setRiskFilter(r)}
                >
                  {r === "all" ? "All" : r}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Time Period Filter */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 11, color: "var(--cc-text-muted)", fontWeight: 600 }}>PERIOD:</span>
          <div className="cc-btn-group" style={{ display: "flex", gap: 2 }}>
            {[
              { id: "15m", label: "Last 15m" },
              { id: "1h", label: "Last 1h" },
              { id: "today", label: "Today" },
            ].map((t) => (
              <button
                key={t.id}
                className={`cc-btn${timeFilter === t.id ? " cc-btn-primary" : ""}`}
                style={{ fontSize: 11, padding: "3px 10px" }}
                onClick={() => setTimeFilter(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 2. Top KPI Cards */}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 10 }}>
        <KpiCard
          label="Total People"
          value={total_people.toLocaleString()}
          severity={overall_risk.toLowerCase()}
          icon="bi-people-fill"
          sub="Current valid non-overlapping occupancy"
        />
        <KpiCard
          label={`Total Entries (${timeFilter === "15m" ? "15m" : timeFilter === "1h" ? "1h" : "Today"})`}
          value={total_entries.toLocaleString()}
          icon="bi-arrow-down-circle-fill"
          sub="Valid IN line-crossing events"
        />
        <KpiCard
          label={`Total Exits (${timeFilter === "15m" ? "15m" : timeFilter === "1h" ? "1h" : "Today"})`}
          value={total_exits.toLocaleString()}
          icon="bi-arrow-up-circle-fill"
          sub="Valid OUT line-crossing events"
        />
        <KpiCard
          label="Net Crowd Change"
          value={`${net_change >= 0 ? "+" : ""}${net_change.toLocaleString()}`}
          severity={net_change > 200 ? "high" : "normal"}
          icon="bi-graph-up-arrow"
          trend={net_change}
          sub="Cumulative delta in period"
        />
      </div>

      {/* 3. Secondary Compact Status Badges */}
      <div
        style={{
          display: "flex",
          gap: 10,
          padding: "8px 14px",
          background: "var(--cc-bg-secondary)",
          border: "1px solid var(--cc-border)",
          borderRadius: "var(--cc-radius)",
          fontSize: 12,
          flexWrap: "wrap",
          marginBottom: 14,
        }}
      >
        <span style={{ color: "var(--cc-text-muted)" }}>
          Active Cameras:{" "}
          <strong style={{ color: active_cameras > 0 ? "var(--cc-green)" : "var(--cc-red)" }}>
            {active_cameras} / {total_cameras}
          </strong>
        </span>
        <span style={{ color: "var(--cc-border-strong)" }}>|</span>
        <span style={{ color: "var(--cc-text-muted)" }}>
          Active Queues: <strong style={{ color: "var(--cc-blue)" }}>{active_queues}</strong>
        </span>
        <span style={{ color: "var(--cc-border-strong)" }}>|</span>
        <span style={{ color: "var(--cc-text-muted)" }}>
          High Risk Zones:{" "}
          <strong style={{ color: high_risk_zones > 0 ? "var(--cc-red)" : "var(--cc-green)" }}>
            {high_risk_zones}
          </strong>
        </span>
        <span style={{ color: "var(--cc-border-strong)" }}>|</span>
        <span style={{ color: "var(--cc-text-muted)" }}>
          Longest Queue: <strong style={{ color: "var(--cc-yellow)" }}>{longest_queue} persons</strong>
        </span>
        <span style={{ color: "var(--cc-border-strong)" }}>|</span>
        <span style={{ color: "var(--cc-text-muted)" }}>
          Longest Wait: <strong style={{ color: "var(--cc-orange)" }}>{formattedWait}</strong>
        </span>
        <span style={{ color: "var(--cc-border-strong)" }}>|</span>
        <span style={{ color: "var(--cc-text-muted)" }}>
          Overall Risk: <StatusBadge status={overall_risk} />
        </span>
      </div>

      {/* 4. People Movement Graph */}
      <div className="cc-card cc-chart" style={{ padding: 0, marginBottom: 14 }}>
        <div
          className="cc-section-header"
          style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
        >
          <div className="cc-section-title">
            <i className="bi bi-activity" style={{ marginRight: 6, color: "var(--cc-blue)" }} />
            People Movement — Entries, Exits & Occupancy Curve
          </div>
          <span className="cc-tag" style={{ fontSize: 10 }}>
            Period: {timeFilter.toUpperCase()}
          </span>
        </div>
        {movementData.length > 0 ? (
          <ReactECharts option={movementChartOption} style={{ height: 220 }} />
        ) : (
          <div
            style={{
              height: 220,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--cc-text-muted)",
              fontSize: 13,
              fontStyle: "italic",
            }}
          >
            No movement telemetry available
          </div>
        )}
      </div>

      {/* 5. Two-Column Area: Left = Queue Status Cards, Right = Zone Density Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
        {/* Left Column: Queue Status */}
        <div className="cc-card" style={{ padding: 0 }}>
          <div
            className="cc-section-header"
            style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
          >
            <div className="cc-section-title">
              <i className="bi bi-segmented-nav" style={{ marginRight: 6, color: "var(--cc-blue)" }} />
              Queue Status ({queues.length} Configured)
            </div>
            <span className="cc-tag">{active_queues} Running</span>
          </div>

          {queues.length === 0 ? (
            <div style={{ padding: "30px 20px", textAlign: "center", color: "var(--cc-text-muted)" }}>
              <i className="bi bi-info-circle" style={{ fontSize: 24, opacity: 0.5, display: "block", marginBottom: 6 }} />
              No Queue AI cameras configured.
            </div>
          ) : (
            <div style={{ padding: 10, display: "flex", flexDirection: "column", gap: 8 }}>
              {queues.map((q) => {
                const waitMin = q.average_wait_seconds !== null ? Math.round(q.average_wait_seconds / 60) : null;
                const isOnline = q.camera_status === "ONLINE";
                const isRunning = q.pipeline_status === "RUNNING";

                return (
                  <div
                    key={q.camera_code}
                    className="cc-card"
                    style={{
                      background: "var(--cc-bg-secondary)",
                      border: "1px solid var(--cc-border)",
                      padding: "10px 12px",
                      cursor: "pointer",
                      transition: "border-color 0.15s ease",
                    }}
                    onClick={() => navigate(`/cameras/${q.camera_id || q.camera_code}`)}
                    title="Click to view camera telemetry"
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: 13, color: "var(--cc-text-primary)" }}>
                          {(q.camera_code?.endsWith("-CROWD") ? q.camera_code : `${q.camera_code}-CROWD`)} — {q.queue_name}
                        </div>
                        <div style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>
                          {q.camera_name} {q.zone_code ? `• ${q.zone_code}` : ""}
                        </div>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span
                          className={`cc-badge ${isOnline ? "low" : "critical"}`}
                          style={{ fontSize: 9, padding: "2px 6px" }}
                        >
                          {q.camera_status}
                        </span>
                        <StatusBadge status={q.risk_level} />
                      </div>
                    </div>

                    {/* Metrics Grid */}
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(4, 1fr)",
                        gap: 6,
                        fontSize: 11,
                        background: "var(--cc-bg-panel)",
                        padding: "6px 8px",
                        borderRadius: "var(--cc-radius)",
                        marginTop: 4,
                      }}
                    >
                      <div>
                        <span style={{ color: "var(--cc-text-muted)", fontSize: 9, display: "block" }}>PEOPLE</span>
                        <strong style={{ fontFamily: "var(--cc-font-mono)", color: RISK_COLORS[q.risk_level] || "inherit" }}>
                          {isOnline && isRunning ? `${q.current_people} waiting` : "Camera offline"}
                        </strong>
                      </div>
                      <div>
                        <span style={{ color: "var(--cc-text-muted)", fontSize: 9, display: "block" }}>WAIT TIME</span>
                        <strong style={{ fontFamily: "var(--cc-font-mono)" }}>
                          {waitMin !== null ? `${waitMin} min` : "—"}
                        </strong>
                      </div>
                      <div>
                        <span style={{ color: "var(--cc-text-muted)", fontSize: 9, display: "block" }}>LENGTH</span>
                        <strong style={{ fontFamily: "var(--cc-font-mono)" }}>
                          {q.queue_length > 0 ? `${q.queue_length} ${q.queue_length_unit === "meters" ? "m" : "ext"}` : "0"}
                        </strong>
                      </div>
                      <div>
                        <span style={{ color: "var(--cc-text-muted)", fontSize: 9, display: "block" }}>IN / OUT</span>
                        <span style={{ fontFamily: "var(--cc-font-mono)", fontSize: 10 }}>
                          <span style={{ color: "var(--cc-green)" }}>+{q.inflow_rate ?? 0}</span> /{" "}
                          <span style={{ color: "var(--cc-orange)" }}>-{q.outflow_rate ?? 0}</span>
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right Column: Zone Density */}
        <div className="cc-card" style={{ padding: 0 }}>
          <div
            className="cc-section-header"
            style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
          >
            <div className="cc-section-title">
              <i className="bi bi-hexagon-fill" style={{ marginRight: 6, color: "var(--cc-blue)" }} />
              Zone Density ({zones.length} Configured)
            </div>
            <span className="cc-tag">Occupancy %</span>
          </div>

          {zones.length === 0 ? (
            <div style={{ padding: "30px 20px", textAlign: "center", color: "var(--cc-text-muted)" }}>
              <i className="bi bi-info-circle" style={{ fontSize: 24, opacity: 0.5, display: "block", marginBottom: 6 }} />
              No Zone cameras configured.
            </div>
          ) : (
            <div style={{ padding: 10, display: "flex", flexDirection: "column", gap: 8 }}>
              {zones.map((z) => {
                const isOnline = z.camera_status === "ONLINE";

                return (
                  <div
                    key={z.zone_code}
                    className="cc-card"
                    style={{
                      background: "var(--cc-bg-secondary)",
                      border: "1px solid var(--cc-border)",
                      padding: "10px 12px",
                      cursor: "pointer",
                      transition: "border-color 0.15s ease",
                    }}
                    onClick={() => navigate(z.zone_id ? `/zones/${z.zone_id}` : `/cameras/${z.camera_code}`)}
                    title="Click to view zone details"
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: 13, color: "var(--cc-text-primary)" }}>
                          {z.zone_code} — {z.zone_name}
                        </div>
                        <div style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>
                          Camera: {z.camera_code ? (z.camera_code.endsWith("-CROWD") ? z.camera_code : `${z.camera_code}-CROWD`) : "Aggregated"}
                        </div>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span
                          className={`cc-badge ${isOnline ? "low" : "critical"}`}
                          style={{ fontSize: 9, padding: "2px 6px" }}
                        >
                          {z.camera_status}
                        </span>
                        <StatusBadge status={z.risk_level} />
                      </div>
                    </div>

                    {/* Progress Bar */}
                    <div style={{ marginBottom: 6 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 3 }}>
                        <span style={{ color: "var(--cc-text-muted)" }}>Occupancy:</span>
                        <span style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 700, color: RISK_COLORS[z.risk_level] || "inherit" }}>
                          {z.density_pct}%
                        </span>
                      </div>
                      <div className="cc-progress" style={{ height: 6 }}>
                        <div
                          className="cc-progress-fill"
                          style={{
                            width: `${Math.min(100, z.density_pct)}%`,
                            background: RISK_COLORS[z.risk_level] || "var(--cc-green)",
                          }}
                        />
                      </div>
                    </div>

                    {/* Zone Details */}
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(3, 1fr)",
                        gap: 6,
                        fontSize: 11,
                        background: "var(--cc-bg-panel)",
                        padding: "6px 8px",
                        borderRadius: "var(--cc-radius)",
                      }}
                    >
                      <div>
                        <span style={{ color: "var(--cc-text-muted)", fontSize: 9, display: "block" }}>OCCUPANCY</span>
                        <strong style={{ fontFamily: "var(--cc-font-mono)" }}>
                          {z.current_people.toLocaleString()}
                        </strong>
                      </div>
                      <div>
                        <span style={{ color: "var(--cc-text-muted)", fontSize: 9, display: "block" }}>CAPACITY</span>
                        <span style={{ fontFamily: "var(--cc-font-mono)" }}>
                          {z.capacity.toLocaleString()}
                        </span>
                      </div>
                      <div>
                        <span style={{ color: "var(--cc-text-muted)", fontSize: 9, display: "block" }}>TREND</span>
                        <span
                          style={{
                            fontFamily: "var(--cc-font-mono)",
                            color: z.trend === "INCREASING" ? "var(--cc-red)" : z.trend === "DECREASING" ? "var(--cc-green)" : "inherit",
                          }}
                        >
                          {z.trend}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* 6. Two-Column Trend Graphs: Queue Trend & Zone Density Trend */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
        {/* Queue Trend */}
        <div className="cc-card cc-chart" style={{ padding: 0 }}>
          <div className="cc-section-header">
            <div className="cc-section-title">Queue Trend — Headcount & Flow</div>
          </div>
          {queueTrendData.length > 0 ? (
            <ReactECharts option={queueChartOption} style={{ height: 200 }} />
          ) : (
            <div
              style={{
                height: 200,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--cc-text-muted)",
                fontSize: 12,
                fontStyle: "italic",
              }}
            >
              No queue historical trend data
            </div>
          )}
        </div>

        {/* Zone Density Trend */}
        <div className="cc-card cc-chart" style={{ padding: 0 }}>
          <div className="cc-section-header">
            <div className="cc-section-title">Zone Density Trend — Density %</div>
          </div>
          {zoneTrendData.length > 0 ? (
            <ReactECharts option={zoneChartOption} style={{ height: 200 }} />
          ) : (
            <div
              style={{
                height: 200,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--cc-text-muted)",
                fontSize: 12,
                fontStyle: "italic",
              }}
            >
              No zone density trend data
            </div>
          )}
        </div>
      </div>

      {/* 7. Crowd Risk Section & High-Risk Areas List */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
        {/* Current Crowd Risk Breakdown */}
        <div className="cc-card" style={{ padding: 0 }}>
          <div className="cc-section-header">
            <div className="cc-section-title">Current Crowd Risk Assessment</div>
          </div>
          <div style={{ padding: 14 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
              <div>
                <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>OVERALL RISK LEVEL</div>
                <div style={{ fontSize: 20, fontWeight: 700, color: RISK_COLORS[overall_risk] || "inherit" }}>
                  {overall_risk}
                </div>
              </div>
              <StatusBadge status={overall_risk} />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, fontSize: 12 }}>
              <div style={{ background: "var(--cc-bg-secondary)", padding: "8px 10px", borderRadius: "var(--cc-radius)" }}>
                <span style={{ fontSize: 10, color: "var(--cc-text-muted)", display: "block" }}>DENSITY CONTRIBUTION</span>
                <strong style={{ fontFamily: "var(--cc-font-mono)", fontSize: 14 }}>
                  {risk_breakdown.density_contribution ?? 0}%
                </strong>
              </div>
              <div style={{ background: "var(--cc-bg-secondary)", padding: "8px 10px", borderRadius: "var(--cc-radius)" }}>
                <span style={{ fontSize: 10, color: "var(--cc-text-muted)", display: "block" }}>INFLOW PER MINUTE</span>
                <strong style={{ fontFamily: "var(--cc-font-mono)", fontSize: 14, color: "var(--cc-green)" }}>
                  +{risk_breakdown.inflow ?? 0}/m
                </strong>
              </div>
              <div style={{ background: "var(--cc-bg-secondary)", padding: "8px 10px", borderRadius: "var(--cc-radius)" }}>
                <span style={{ fontSize: 10, color: "var(--cc-text-muted)", display: "block" }}>HIGHEST RISK QUEUE</span>
                <span style={{ fontWeight: 600, color: "var(--cc-text-primary)" }}>
                  {risk_breakdown.highest_risk_queue || "None"}
                </span>
              </div>
              <div style={{ background: "var(--cc-bg-secondary)", padding: "8px 10px", borderRadius: "var(--cc-radius)" }}>
                <span style={{ fontSize: 10, color: "var(--cc-text-muted)", display: "block" }}>HIGHEST RISK ZONE</span>
                <span style={{ fontWeight: 600, color: "var(--cc-text-primary)" }}>
                  {risk_breakdown.highest_risk_zone || "None"}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* High-Risk Areas List */}
        <div className="cc-card" style={{ padding: 0 }}>
          <div className="cc-section-header">
            <div className="cc-section-title">Elevated Risk Sectors</div>
          </div>
          <div style={{ padding: 10, maxHeight: 190, overflowY: "auto" }}>
            {high_risk_areas.length === 0 ? (
              <div style={{ textAlign: "center", color: "var(--cc-text-muted)", padding: "30px 10px", fontSize: 12 }}>
                <i className="bi bi-shield-check" style={{ fontSize: 24, color: "var(--cc-green)", display: "block", marginBottom: 6 }} />
                All monitored areas are currently within safe thresholds.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {high_risk_areas.map((area, i) => (
                  <div
                    key={`${area.name}-${i}`}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "8px 12px",
                      background: "var(--cc-bg-secondary)",
                      border: "1px solid var(--cc-border)",
                      borderRadius: "var(--cc-radius)",
                      fontSize: 12,
                    }}
                  >
                    <div>
                      <span style={{ fontWeight: 600, color: "var(--cc-text-primary)" }}>{area.name}</span>
                      <span style={{ fontSize: 10, color: "var(--cc-text-muted)", marginLeft: 6 }}>
                        ({area.area_type}) • {area.camera_code?.endsWith("-CROWD") ? area.camera_code : `${area.camera_code}-CROWD`}
                      </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 700 }}>
                        {area.current_people} persons
                      </span>
                      <StatusBadge status={area.risk_level} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 8. Camera Status Table (7 Dynamic Cameras) */}
      <div className="cc-card" style={{ padding: 0, overflow: "hidden", marginBottom: 14 }}>
        <div
          className="cc-section-header"
          style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
        >
          <div className="cc-section-title">
            <i className="bi bi-camera-video-fill" style={{ marginRight: 6, color: "var(--cc-blue)" }} />
            Crowd Management Camera Status ({cameras.length} Monitored Streams)
          </div>
          <span className="cc-tag">Click camera row to view stream</span>
        </div>

        <div style={{ overflowX: "auto" }}>
          <table className="cc-table">
            <thead>
              <tr>
                <th>Camera Code</th>
                <th>Name</th>
                <th>Purpose</th>
                <th>Stream Status</th>
                <th>Processing FPS</th>
                <th>AI Pipeline Status</th>
                <th>Tracked Headcount</th>
                <th>Last Update</th>
              </tr>
            </thead>
            <tbody>
              {cameras.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ textAlign: "center", color: "var(--cc-text-muted)", padding: "20px 0" }}>
                    No Crowd Management cameras configured.
                  </td>
                </tr>
              ) : (
                cameras.map((cam) => {
                  const isOnline = cam.stream_status === "ONLINE";
                  const isRunning = cam.pipeline_status === "RUNNING";

                  return (
                    <tr
                      key={cam.camera_code}
                      onClick={() => navigate(`/cameras/${cam.camera_id || cam.camera_code}`)}
                      style={{ cursor: "pointer" }}
                      title="Open camera detail"
                    >
                      <td style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 700, color: "var(--cc-text-accent)" }}>
                        {cam.logical_id_crowd || (cam.camera_code?.endsWith("-CROWD") ? cam.camera_code : `${cam.camera_code}-CROWD`)}
                      </td>
                      <td>{cam.name}</td>
                      <td>
                        <span className="cc-badge info" style={{ fontSize: 9, padding: "2px 6px" }}>
                          {cam.purpose}
                        </span>
                      </td>
                      <td>
                        <span
                          className={`cc-badge ${isOnline ? "low" : "critical"}`}
                          style={{ fontSize: 9, padding: "2px 6px" }}
                        >
                          {cam.stream_status}
                        </span>
                      </td>
                      <td style={{ fontFamily: "var(--cc-font-mono)" }}>
                        {isRunning ? `${cam.fps.toFixed(1)} fps` : "0.0 fps"}
                      </td>
                      <td>
                        <span
                          style={{
                            fontSize: 10,
                            fontWeight: 600,
                            color: isRunning ? "var(--cc-green)" : "var(--cc-text-muted)",
                          }}
                        >
                          {cam.pipeline_status}
                        </span>
                      </td>
                      <td style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 600 }}>
                        {isOnline ? cam.current_people : "—"}
                      </td>
                      <td style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>
                        {cam.last_update ? new Date(cam.last_update).toLocaleTimeString() : "—"}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 9. Active Crowd Events Panel */}
      <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
        <div
          className="cc-section-header"
          style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
        >
          <div className="cc-section-title">
            <i className="bi bi-bell-fill" style={{ marginRight: 6, color: "var(--cc-orange)" }} />
            Active Crowd & Queue Incident Feed
          </div>
          <span className="cc-tag">{events.length} Events</span>
        </div>

        <div style={{ overflowX: "auto" }}>
          <table className="cc-table">
            <thead>
              <tr>
                <th>Severity</th>
                <th>Alert Code</th>
                <th>Title</th>
                <th>Message</th>
                <th>Target Area</th>
                <th>Detected At</th>
              </tr>
            </thead>
            <tbody>
              {events.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", color: "var(--cc-text-muted)", padding: "20px 0" }}>
                    No active crowd or queue alerts recorded.
                  </td>
                </tr>
              ) : (
                events.map((evt) => (
                  <tr key={evt.id || evt.alert_code}>
                    <td>
                      <StatusBadge status={evt.severity} />
                    </td>
                    <td style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 600 }}>{evt.alert_code}</td>
                    <td style={{ fontWeight: 600, color: "var(--cc-text-primary)" }}>{evt.title}</td>
                    <td style={{ color: "var(--cc-text-secondary)", fontSize: 11 }}>{evt.message}</td>
                    <td style={{ fontFamily: "var(--cc-font-mono)", fontSize: 11 }}>
                      {evt.camera_code || evt.zone_code || "—"}
                    </td>
                    <td style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>
                      {evt.detected_at ? new Date(evt.detected_at).toLocaleTimeString() : "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
