// Analytics page
import { useEffect, useState, useRef, useCallback } from "react";
import ReactECharts from "echarts-for-react";
import {
  getAttendanceAnalytics,
  getFestival10DaysAnalytics,
  downloadFestival10DaysCsv,
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
  const [selectedDayNumber, setSelectedDayNumber] = useState(null);
  const [selectedDateRange, setSelectedDateRange] = useState(null);
  const [attendance, setAttendance] = useState(null);
  const [flowData, setFlowData] = useState(null);
  const [fest10Data, setFest10Data] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [loading, setLoading] = useState(true);

  const isMountedRef = useRef(true);
  const inFlightRef = useRef(false);
  const timerRef = useRef(null);

  const loadAllAnalytics = useCallback(async (silent = false, dayNum = selectedDayNumber, dRange = selectedDateRange) => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    if (!silent) setLoading(true);

    try {
      const [a, f, fest] = await Promise.allSettled([
        getAttendanceAnalytics(dayNum, dRange),
        getOperationalFlowAnalytics(),
        getFestival10DaysAnalytics(),
      ]);
      if (!isMountedRef.current) return;
      if (a.status === "fulfilled" && a.value) setAttendance(a.value?.data || a.value);
      if (f.status === "fulfilled" && f.value) setFlowData(f.value?.data || f.value);
      if (fest.status === "fulfilled" && fest.value) setFest10Data(fest.value?.data || fest.value);
    } catch (e) {
      console.warn("[Analytics] Fetch error:", e);
    } finally {
      if (isMountedRef.current) setLoading(false);
      inFlightRef.current = false;
    }
  }, [activeEventId, selectedDayNumber, selectedDateRange]);

  // Immediately reload when the user switches to a different event
  useEffect(() => {
    if (!isMountedRef.current) return;
    inFlightRef.current = false; // reset in-flight guard so new event fetch isn't blocked
    loadAllAnalytics(false);
  }, [activeEventId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    isMountedRef.current = true;
    loadAllAnalytics(false, selectedDayNumber, selectedDateRange);

    const scheduleNext = () => {
      clearTimeout(timerRef.current);
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      timerRef.current = setTimeout(async () => {
        if (isMountedRef.current && document.visibilityState === "visible") {
          await loadAllAnalytics(true, selectedDayNumber, selectedDateRange);
          scheduleNext();
        }
      }, 5000);
    };

    scheduleNext();

    const handleVis = () => {
      if (document.visibilityState === "visible") {
        loadAllAnalytics(true, selectedDayNumber, selectedDateRange);
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
        loadAllAnalytics(true, selectedDayNumber, selectedDateRange);
      }
    });

    return () => {
      isMountedRef.current = false;
      clearTimeout(timerRef.current);
      document.removeEventListener("visibilitychange", handleVis);
      unsub();
    };
  }, [loadAllAnalytics, selectedDayNumber, selectedDateRange]);

  const handleDaySelect = (dayNum, rangeStr = null) => {
    if (rangeStr === "festival") {
      setSelectedDayNumber(null);
      setSelectedDateRange("festival");
      loadAllAnalytics(false, null, "festival");
    } else if (dayNum !== null && dayNum !== undefined) {
      setSelectedDayNumber(dayNum);
      setSelectedDateRange(null);
      loadAllAnalytics(false, dayNum, null);
    } else {
      setSelectedDayNumber(null);
      setSelectedDateRange("today");
      loadAllAnalytics(false, null, "today");
    }
  };

  // Immediately re-fetch all analytics when active event changes
  useEffect(() => {
    if (activeEventId) {
      setLoading(true);
      loadAllAnalytics(false);
    }
  }, [activeEventId, loadAllAnalytics]);

  if (loading) return <LoadingState />;

  const safeAttendance = attendance || { totalVisitorsToday: 0, peakHour: "—", peakCount: 0, avgPerHour: 0, hourly: [], daily: [] };

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

  const eventDaysList = (safeAttendance?.eventDays || safeAttendance?.event_days || fest10Data?.days || [
    { day_number: 1, date: "14 Sep", label: "Day 1 (14 Sep)", status: "TODAY" },
  ]);

  const currentDayLabel = safeAttendance?.selectedDayLabel || safeAttendance?.selected_day_label || (selectedDateRange === "festival" ? "Festival Total" : selectedDayNumber ? `Day ${selectedDayNumber}` : "Today");

  return (
    <div className="cc-page">
      <div className="cc-page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <div className="cc-page-title">Advanced Operational Analytics & Flow Control</div>
          <div className="cc-page-subtitle">Actionable crowd intelligence, tactical directives & zone clearance priority</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: "rgba(0, 0, 0, 0.4)",
              padding: "4px 10px",
              borderRadius: 6,
              border: "1px solid rgba(255, 255, 255, 0.12)",
            }}
          >
            <label style={{ fontSize: 10, fontFamily: "var(--cc-font-mono)", fontWeight: 700, color: "var(--cc-text-muted)", textTransform: "uppercase" }}>
              Analytics Day:
            </label>
            <select
              value={
                selectedDayNumber
                  ? `day_${selectedDayNumber}`
                  : selectedDateRange === "festival"
                  ? "festival"
                  : "today"
              }
              onChange={(e) => {
                const val = e.target.value;
                if (val === "festival") {
                  handleDaySelect(null, "festival");
                } else if (val.startsWith("day_")) {
                  const dNum = parseInt(val.replace("day_", ""), 10);
                  handleDaySelect(dNum, null);
                } else {
                  handleDaySelect(null, "today");
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
        </div>
      </div>

      {/* ── 1. Real-time Actionable Crowd Flow Directives ("Next em chesthe flow correct ga untadhi?") ── */}
      <FlowDirectivesCard flowData={flowData} loading={loading} />

      {/* ── 2. Zone Clearance & Queue Diversion Matrix ("Ee place clear cheyali? Ee entry ee exit?") ── */}
      <ZoneFlowMatrix flowData={flowData} loading={loading} />

      {/* ── 3. Attendance Overview KPIs ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 14 }}>
        {[
          {
            label: `Total Footfall (${currentDayLabel})`,
            value: (safeAttendance.totalFootfall ?? safeAttendance.total_footfall ?? safeAttendance.totalVisitorsToday ?? 0).toLocaleString(),
            color: "var(--cc-accent)",
          },
          {
            label: `Total Entries (${currentDayLabel})`,
            value: (safeAttendance.totalEntries ?? safeAttendance.total_entries ?? safeAttendance.totalVisitorsToday ?? 0).toLocaleString(),
            color: "#3fb950",
          },
          {
            label: `Total Exits (${currentDayLabel})`,
            value: (safeAttendance.totalExits ?? safeAttendance.total_exits ?? 0).toLocaleString(),
            color: "#f85149",
          },
          {
            label: `Peak Hour (${currentDayLabel})`,
            value: safeAttendance.peak_hour ?? safeAttendance.peakHour ?? "—",
            color: "#e3b341",
          },
        ].map((k) => (
          <div key={k.label} className="cc-card" style={{ padding: "12px 16px" }}>
            <div className="cc-label" style={{ marginBottom: 4 }}>{k.label}</div>
            <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 20, fontWeight: 700, color: k.color || "var(--cc-text-primary)" }}>{k.value}</div>
          </div>
        ))}
      </div>

      {/* ── Hourly Visitor Trend ── */}
      <div className="cc-card cc-chart" style={{ padding: 0, marginBottom: 14 }}>
        <div className="cc-section-header">
          <div className="cc-section-title">Hourly Visitor Trend ({currentDayLabel})</div>
        </div>
        <ReactECharts option={hourlyChart} style={{ height: 260 }} />
      </div>

      {/* ── Daily Attendance Trend ── */}
      <div className="cc-card cc-chart" style={{ padding: 0, marginBottom: 14 }}>
        <div className="cc-section-header">
          <div className="cc-section-title">Daily Attendance Trend</div>
        </div>
        <ReactECharts option={dailyChart} style={{ height: 220 }} />
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
                <th style={{ textAlign: "right", color: "var(--cc-accent)" }}>Total Footfall</th>
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
