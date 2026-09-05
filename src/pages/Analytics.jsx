// Analytics page
import { useEffect, useState } from "react";
import ReactECharts from "echarts-for-react";
import { getAttendanceAnalytics, getCameraAnalytics, getIncidentAnalytics } from "../services/analyticsService.js";
import { LoadingState } from "../components/common/States.jsx";

import { useAppStore } from "../store/useAppStore.js";
import { getChartTheme } from "../utils/chartTheme.js";

export default function Analytics() {
  const theme = useAppStore((s) => s.theme);
  const ct = getChartTheme(theme);
  const [attendance, setAttendance] = useState(null);
  const [camera, setCamera] = useState(null);
  const [incident, setIncident] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getAttendanceAnalytics(), getCameraAnalytics(), getIncidentAnalytics()])
      .then(([a, c, i]) => { setAttendance(a); setCamera(c); setIncident(i); setLoading(false); });
  }, []);

  if (loading) return <LoadingState />;

  const hourlyChart = {
    backgroundColor: "transparent",
    textStyle: ct.textStyle,
    grid: { top: 20, right: 10, bottom: 50, left: 55 },
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
      data: attendance.hourly.map((h) => h.hour),
      axisLine: ct.axisLine,
      axisTick: { show: false },
      axisLabel: { color: ct.axisLabelColor, interval: 3 },
    },
    yAxis: {
      axisLine: ct.axisLine,
      splitLine: ct.splitLine,
      axisLabel: { formatter: (v) => `${(v / 1000).toFixed(0)}k`, color: ct.axisLabelColor },
    },
    series: [
      {
        type: "bar",
        data: attendance.hourly.map((h) => ({
          value: h.visitors,
          itemStyle: { color: h.visitors === attendance.peakCount ? ct.dangerColor : ct.primaryColor },
        })),
        barMaxWidth: 20,
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
      data: incident.byType.map((t, i) => ({
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
      axisLabel: { formatter: (v) => `${(v / 1000).toFixed(0)}k`, color: ct.axisLabelColor },
      splitLine: ct.splitLine,
    },
    yAxis: {
      type: "category",
      data: attendance.daily.map((d) => d.day),
      axisLine: ct.axisLine,
      axisLabel: { color: ct.isLight ? "#334155" : "#8b949e" },
      axisTick: { show: false },
    },
    series: [{
      type: "bar",
      data: attendance.daily.map((d) => d.visitors),
      barMaxWidth: 30,
      itemStyle: { color: ct.primaryColor, borderRadius: [0, 3, 3, 0] },
    }],
  };

  return (
    <div className="cc-page">
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title">Analytics</div>
          <div className="cc-page-subtitle">Event performance and operational data</div>
        </div>
      </div>

      {/* Attendance KPIs */}
      <div style={{ display: "flex", gap: 8 }}>
        {[
          { label: "Total Visitors Today", value: (attendance?.total_today ?? attendance?.totalVisitorsToday ?? 0).toLocaleString() },
          { label: "Peak Hour", value: attendance?.peak_hour ?? attendance?.peakHour ?? "—" },
          { label: "Peak Count", value: (attendance?.peak_count ?? attendance?.peakCount ?? 0).toLocaleString() },
          { label: "Avg / Hour", value: (attendance?.avg_per_hour ?? attendance?.avgPerHour ?? 0).toLocaleString() },
          { label: "Camera Uptime", value: camera?.uptime ?? "—" },
          { label: "Total Detections", value: (camera?.total_detections ?? camera?.totalDetections ?? 0).toLocaleString() },
          { label: "Avg FPS", value: camera?.avg_fps ?? camera?.avgFps ?? 0 },
          { label: "Incidents Total", value: incident?.total ?? 0 },
        ].map((k) => (
          <div key={k.label} className="cc-card" style={{ flex: 1, minWidth: 0 }}>
            <div className="cc-label" style={{ marginBottom: 4 }}>{k.label}</div>
            <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 18, fontWeight: 700, color: "var(--cc-text-primary)" }}>{k.value}</div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 12 }}>
        <div className="cc-card cc-chart" style={{ padding: 0 }}>
          <div className="cc-section-header"><div className="cc-section-title">Hourly Visitor Trend</div></div>
          <ReactECharts option={hourlyChart} style={{ height: 220 }} />
        </div>
        <div className="cc-card cc-chart" style={{ padding: 0 }}>
          <div className="cc-section-header"><div className="cc-section-title">Incident Types</div></div>
          <ReactECharts option={incidentPieChart} style={{ height: 220 }} />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div className="cc-card cc-chart" style={{ padding: 0 }}>
          <div className="cc-section-header"><div className="cc-section-title">Daily Attendance</div></div>
          <ReactECharts option={dailyChart} style={{ height: 180 }} />
        </div>
        <div className="cc-card">
          <div className="cc-section-title" style={{ marginBottom: 14 }}>Incident Analytics</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {[
              { label: "Total", value: incident.total },
              { label: "Resolved", value: incident.resolved, color: "var(--cc-green)" },
              { label: "Active", value: incident.active, color: "var(--cc-red)" },
              { label: "Avg Resolution", value: `${incident.avgResolutionMin} min` },
            ].map((s) => (
              <div key={s.label}>
                <div className="cc-label">{s.label}</div>
                <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 22, fontWeight: 700, color: s.color || "var(--cc-text-primary)" }}>{s.value}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
