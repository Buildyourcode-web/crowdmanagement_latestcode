// Analytics page
import { useEffect, useState, useRef, useCallback } from "react";
import ReactECharts from "echarts-for-react";
import {
  getAttendanceAnalytics,
  getCameraAnalytics,
  getFestival10DaysAnalytics,
  downloadFestival10DaysCsv,
  getIncidentAnalytics,
  getOperationalFlowAnalytics,
} from "../services/analyticsService.js";
import { realtimeService } from "../services/realtimeService.js";
import { LoadingState } from "../components/common/States.jsx";
import FlowDirectivesCard from "../components/analytics/FlowDirectivesCard.jsx";
import ZoneFlowMatrix from "../components/analytics/ZoneFlowMatrix.jsx";
import { useNavigate } from "react-router-dom";

import { useAppStore } from "../store/useAppStore.js";
import { useEventStore } from "../store/useEventStore.js";
import { getChartTheme } from "../utils/chartTheme.js";

export default function Analytics() {
  const navigate = useNavigate();
  const theme = useAppStore((s) => s.theme);
  const ct = getChartTheme(theme);
  const activeEventId = useEventStore((s) => s.activeEventId);
  const [attendance, setAttendance] = useState(null);
  const [camera, setCamera] = useState(null);
  const [incident, setIncident] = useState(null);
  const [flowData, setFlowData] = useState(null);
  const [fest10Data, setFest10Data] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [loading, setLoading] = useState(true);

  const isMountedRef = useRef(true);
  const inFlightRef = useRef(false);
  const timerRef = useRef(null);

  const loadAllAnalytics = useCallback(async (silent = false) => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    if (!silent) setLoading(true);

    try {
      const [a, c, i, f, fest] = await Promise.allSettled([
        getAttendanceAnalytics(),
        getCameraAnalytics(),
        getIncidentAnalytics(),
        getOperationalFlowAnalytics(),
        getFestival10DaysAnalytics(),
      ]);
      if (!isMountedRef.current) return;
      if (a.status === "fulfilled" && a.value) setAttendance(a.value?.data || a.value);
      if (c.status === "fulfilled" && c.value) setCamera(c.value?.data || c.value);
      if (i.status === "fulfilled" && i.value) setIncident(i.value?.data || i.value);
      if (f.status === "fulfilled" && f.value) setFlowData(f.value?.data || f.value);
      if (fest.status === "fulfilled" && fest.value) setFest10Data(fest.value?.data || fest.value);
    } catch (e) {
      console.warn("[Analytics] Fetch error:", e);
    } finally {
      if (isMountedRef.current) setLoading(false);
      inFlightRef.current = false;
    }
  }, [activeEventId]);

  // Immediately reload when the user switches to a different event
  useEffect(() => {
    if (!isMountedRef.current) return;
    inFlightRef.current = false; // reset in-flight guard so new event fetch isn't blocked
    loadAllAnalytics(false);
  }, [activeEventId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    isMountedRef.current = true;
    loadAllAnalytics();

    const scheduleNext = () => {
      clearTimeout(timerRef.current);
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      timerRef.current = setTimeout(async () => {
        if (isMountedRef.current && document.visibilityState === "visible") {
          await loadAllAnalytics(true);
          scheduleNext();
        }
      }, 5000);
    };

    scheduleNext();

    const handleVis = () => {
      if (document.visibilityState === "visible") {
        loadAllAnalytics(true);
        scheduleNext();
      } else {
        clearTimeout(timerRef.current);
      }
    };
    document.addEventListener("visibilitychange", handleVis);

    const unsub = realtimeService.subscribe((msg, eventType, payload) => {
      const norm = String(eventType || msg?.type || "").toLowerCase();
      if (
        norm === "crowd_telemetry" ||
        norm === "crowd_update" ||
        norm === "zone_update" ||
        norm === "line_crossing" ||
        norm === "queue_update"
      ) {
        loadAllAnalytics(true);
      }
    });

    return () => {
      isMountedRef.current = false;
      clearTimeout(timerRef.current);
      document.removeEventListener("visibilitychange", handleVis);
      unsub();
    };
  }, [loadAllAnalytics]);

  // Immediately re-fetch all analytics when active event changes
  useEffect(() => {
    if (activeEventId) {
      setLoading(true);
      loadAllAnalytics(false);
    }
  }, [activeEventId, loadAllAnalytics]);

  if (loading) return <LoadingState />;

  const safeAttendance = attendance || { totalVisitorsToday: 0, peakHour: "—", peakCount: 0, avgPerHour: 0, hourly: [], daily: [] };
  const safeIncident = incident || { total: 0, resolved: 0, active: 0, avgResolutionMin: 0, byType: [] };
  const safeCamera = camera || { uptime: "—", totalDetections: 0, avgFps: 0, avgLatencyMs: 0 };

  const hourlyChart = {
    backgroundColor: "transparent",
    textStyle: ct.textStyle,
    grid: { top: 25, right: 15, bottom: 45, left: 45 },
    tooltip: {
      trigger: "axis",
      backgroundColor: ct.tooltip.backgroundColor,
      borderColor: ct.tooltip.borderColor,
      borderWidth: ct.tooltip.borderWidth,
      textStyle: ct.tooltip.textStyle,
      extraCssText: ct.tooltip.extraCssText,
      formatter: (params) => {
        const p = params[0];
        return `<div style="font-weight:700;margin-bottom:2px">${p?.name || ""} IST</div>
                <div style="color:${ct.primaryColor}">Visitors: <b>${p?.value?.toLocaleString() || 0}</b></div>`;
      },
    },
    xAxis: {
      type: "category",
      data: (safeAttendance.hourly || []).map((h) => h.hour),
      axisLine: ct.axisLine,
      axisTick: { show: true, alignWithLabel: true },
      axisLabel: {
        color: ct.axisLabelColor,
        interval: 0, // Show EVERY 1 HOUR label!
        rotate: 35,  // Angled so all 24 labels (00:00 to 23:00) fit comfortably without overlap
        fontSize: 10,
      },
    },
    yAxis: {
      type: "value",
      axisLine: ct.axisLine,
      splitLine: ct.splitLine,
      axisLabel: { formatter: (v) => `${v.toLocaleString()}`, color: ct.axisLabelColor },
    },
    series: [
      {
        name: "Visitors",
        type: "bar",
        data: (safeAttendance.hourly || []).map((h) => ({
          value: h.visitors,
          itemStyle: {
            color: h.visitors > 0 && (h.visitors === safeAttendance.peak_count || h.visitors === safeAttendance.peakCount) ? ct.dangerColor : ct.primaryColor,
            borderRadius: [3, 3, 0, 0],
          },
        })),
        barMaxWidth: 16,
      },
    ],
  };

  const incidentPieChart = {
    backgroundColor: "transparent",
    textStyle: ct.textStyle,
    legend: { bottom: 5, textStyle: ct.legendText },
    series: [{
      type: "pie",
      radius: ["40%", "65%"],
      center: ["50%", "45%"],
      data: (safeIncident.byType || []).map((t, i) => ({
        name: t.type, value: t.count,
        itemStyle: { color: [ct.primaryColor, ct.dangerColor, ct.secondaryColor, ct.successColor, "#f0883e"][i % 5] },
      })),
      label: { show: false },
      labelLine: { show: false },
    }],
  };

  const dailyChart = {
    backgroundColor: "transparent",
    textStyle: ct.textStyle,
    grid: { top: 20, right: 20, bottom: 40, left: 70 },
    tooltip: {
      trigger: "axis",
      backgroundColor: ct.tooltip.backgroundColor,
      borderColor: ct.tooltip.borderColor,
      borderWidth: ct.tooltip.borderWidth,
      textStyle: ct.tooltip.textStyle,
      extraCssText: ct.tooltip.extraCssText,
    },
    xAxis: {
      type: "value",
      axisLine: ct.axisLine,
      axisLabel: { formatter: (v) => `${v.toLocaleString()}`, color: ct.axisLabelColor },
      splitLine: ct.splitLine,
    },
    yAxis: {
      type: "category",
      data: (safeAttendance.daily || []).map((d) => d.day),
      axisLine: ct.axisLine,
      axisLabel: { color: ct.isLight ? "#334155" : "#8b949e" },
      axisTick: { show: false },
    },
    series: [{
      type: "bar",
      data: (safeAttendance.daily || []).map((d) => d.visitors),
      barMaxWidth: 30,
      itemStyle: { color: ct.primaryColor, borderRadius: [0, 3, 3, 0] },
    }],
  };

  return (
    <div className="cc-page">
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title">Advanced Operational Analytics & Flow Control</div>
          <div className="cc-page-subtitle">Actionable crowd intelligence, tactical directives & zone clearance priority</div>
        </div>
      </div>

      {/* ── 1. Real-time Actionable Crowd Flow Directives ("Next em chesthe flow correct ga untadhi?") ── */}
      <FlowDirectivesCard flowData={flowData} loading={loading} />

      {/* ── 2. Zone Clearance & Queue Diversion Matrix ("Ee place clear cheyali? Ee entry ee exit?") ── */}
      <ZoneFlowMatrix flowData={flowData} loading={loading} />

      {/* ── 3. Attendance & Fleet Overview KPIs ── */}
      <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
        {[
          {
            label: "Total Footfall (Entry + Exit)",
            value: (fest10Data?.grand_total_footfall ?? safeAttendance.total_visitors_today ?? safeAttendance.total_today ?? safeAttendance.totalVisitorsToday ?? 0).toLocaleString(),
            color: "var(--cc-accent)",
          },
          {
            label: "Total Entries (4 Gates)",
            value: (fest10Data?.total_entries_10days ?? safeAttendance.total_visitors_today ?? safeAttendance.total_today ?? safeAttendance.totalVisitorsToday ?? 0).toLocaleString(),
            color: "#3fb950",
          },
          {
            label: "Total Exits (4 Gates)",
            value: (fest10Data?.total_exits_10days ?? 0).toLocaleString(),
            color: "#f85149",
          },
          { label: "Peak Hour", value: safeAttendance.peak_hour ?? safeAttendance.peakHour ?? "—" },
          { label: `Fleet Uptime (${camera?.cameras?.length ?? camera?.total_cameras ?? 0} Cams)`, value: safeCamera.uptime ?? "—" },
          { label: "Total Detections", value: (safeCamera.total_detections ?? safeCamera.totalDetections ?? 0).toLocaleString() },
          { label: "Avg FPS", value: safeCamera.avg_fps ?? safeCamera.avgFps ?? 0 },
          { label: "Incidents Total", value: safeIncident.total ?? 0 },
        ].map((k) => (
          <div key={k.label} className="cc-card" style={{ flex: 1, minWidth: 0 }}>
            <div className="cc-label" style={{ marginBottom: 4 }}>{k.label}</div>
            <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 17, fontWeight: 700, color: k.color || "var(--cc-text-primary)" }}>{k.value}</div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 12, marginBottom: 14 }}>
        <div className="cc-card cc-chart" style={{ padding: 0 }}>
          <div className="cc-section-header"><div className="cc-section-title">Hourly Visitor Trend (Today)</div></div>
          <ReactECharts option={hourlyChart} style={{ height: 220 }} />
        </div>
        <div className="cc-card cc-chart" style={{ padding: 0 }}>
          <div className="cc-section-header"><div className="cc-section-title">Incident Types</div></div>
          <ReactECharts option={incidentPieChart} style={{ height: 220 }} />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 14 }}>
        <div className="cc-card cc-chart" style={{ padding: 0 }}>
          <div className="cc-section-header"><div className="cc-section-title">Daily Attendance Trend</div></div>
          <ReactECharts option={dailyChart} style={{ height: 180 }} />
        </div>
        <div className="cc-card">
          <div className="cc-section-title" style={{ marginBottom: 14 }}>Incident Analytics & Resolution</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {[
              { label: "Total Incidents", value: safeIncident.total },
              { label: "Resolved", value: safeIncident.resolved, color: "var(--cc-green)" },
              { label: "Active", value: safeIncident.active, color: "var(--cc-red)" },
              { label: "Avg Resolution", value: `${safeIncident.avgResolutionMin} min` },
            ].map((s) => (
              <div key={s.label}>
                <div className="cc-label">{s.label}</div>
                <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 22, fontWeight: 700, color: s.color || "var(--cc-text-primary)" }}>{s.value}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── 4. 10-Day Festival Day-Wise Attendance & Clearance Audit Table ── */}
      <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
        <div
          className="cc-section-header"
          style={{ padding: "10px 14px", display: "flex", justifyContent: "space-between", alignItems: "center" }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <i className="bi bi-calendar-week" style={{ color: "var(--cc-accent)" }} />
            <span style={{ fontWeight: 700, fontSize: 13, color: "var(--cc-text-primary)", letterSpacing: "0.04em" }}>
              {fest10Data?.days ? `${fest10Data.days.length}-DAY FESTIVAL DAY-WISE ATTENDANCE AUDIT` : "FESTIVAL DAY-WISE ATTENDANCE AUDIT"}
            </span>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button
              className="cc-btn cc-btn-sm"
              style={{ fontSize: 11 }}
              onClick={async () => {
                try {
                  setDownloading(true);
                  await downloadFestival10DaysCsv();
                } catch (e) {
                  alert("Download failed: " + e.message);
                } finally {
                  setDownloading(false);
                }
              }}
              disabled={downloading}
            >
              <i className={`bi ${downloading ? "bi-hourglass-split" : "bi-download"}`} />{" "}
              {downloading ? "Exporting..." : "Download CSV"}
            </button>
            <button className="cc-btn cc-btn-sm cc-btn-primary" style={{ fontSize: 11 }} onClick={() => navigate("/reports")}>
              <i className="bi bi-file-earmark-text" /> Full Reports View
            </button>
          </div>
        </div>

        <div style={{ padding: "6px 12px", overflowX: "auto" }}>
          <table className="cc-table" style={{ width: "100%", fontSize: 11 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--cc-border)" }}>
                <th style={{ textAlign: "left" }}>Day</th>
                <th style={{ textAlign: "left" }}>Date</th>
                <th style={{ textAlign: "left" }}>Day Name</th>
                <th style={{ textAlign: "right", color: "#3fb950" }}>Entry (4 Gates)</th>
                <th style={{ textAlign: "right", color: "#f85149" }}>Exit (4 Gates)</th>
                <th style={{ textAlign: "right", color: "var(--cc-accent)" }}>Total (Entry + Exit)</th>
                <th style={{ textAlign: "right" }}>Net Inside</th>
                <th style={{ textAlign: "center" }}>Peak Hour</th>
                <th style={{ textAlign: "center" }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {!fest10Data?.days || fest10Data.days.length === 0 ? (
                <tr><td colSpan={9} style={{ textAlign: "center", padding: 16, color: "var(--cc-text-muted)" }}>Loading Festival Day-Wise Attendance...</td></tr>
              ) : (
                fest10Data.days.map((row) => {
                  const isToday = row.status === "TODAY";
                  return (
                    <tr key={row.day_number} style={{ background: isToday ? "rgba(188,140,255,0.06)" : "transparent" }}>
                      <td style={{ fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: isToday ? "var(--cc-accent)" : "inherit" }}>
                        Day {row.day_number}
                      </td>
                      <td style={{ fontFamily: "var(--cc-font-mono)" }}>{row.date}</td>
                      <td>{row.day_name}</td>
                      <td style={{ textAlign: "right", color: "#3fb950", fontFamily: "var(--cc-font-mono)", fontWeight: 600 }}>
                        {row.entry_count.toLocaleString()}
                      </td>
                      <td style={{ textAlign: "right", color: "#f85149", fontFamily: "var(--cc-font-mono)", fontWeight: 600 }}>
                        {row.exit_count.toLocaleString()}
                      </td>
                      <td style={{ textAlign: "right", fontWeight: 800, color: "var(--cc-accent)", fontFamily: "var(--cc-font-mono)" }}>
                        {row.total_count.toLocaleString()}
                      </td>
                      <td style={{ textAlign: "right", fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-secondary)" }}>
                        {row.net_inside.toLocaleString()}
                      </td>
                      <td style={{ textAlign: "center", color: "var(--cc-text-muted)" }}>{row.peak_hour}</td>
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
    </div>
  );
}
