// Crowd Intelligence page
import { useEffect, useState } from "react";
import ReactECharts from "echarts-for-react";
import KpiCard from "../components/common/KpiCard.jsx";
import StatusBadge from "../components/common/StatusBadge.jsx";
import { useCrowdStore } from "../store/useCrowdStore.js";
import { getCrowdSummary, getZoneCrowdData, getCrowdTimeSeries, getQueueData } from "../services/crowdService.js";
import { LoadingState } from "../components/common/States.jsx";

import { useAppStore } from "../store/useAppStore.js";
import { getChartTheme } from "../utils/chartTheme.js";

const RISK_COLOR = { low: "#3fb950", medium: "#e3b341", high: "#f0883e", critical: "#f85149" };

export default function Crowd() {
  const { totalCrowd, inflowPerMin, outflowPerMin } = useCrowdStore();
  const theme = useAppStore((s) => s.theme);
  const ct = getChartTheme(theme);
  const [summary, setSummary] = useState(null);
  const [zones, setZones] = useState([]);
  const [timeSeries, setTimeSeries] = useState([]);
  const [queues, setQueues] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getCrowdSummary(), getZoneCrowdData(), getCrowdTimeSeries(), getQueueData()])
      .then(([s, z, ts, q]) => { setSummary(s); setZones(z); setTimeSeries(ts); setQueues(q); setLoading(false); });
  }, []);

  if (loading) return <LoadingState />;

  const chartOption = {
    backgroundColor: "transparent",
    textStyle: ct.textStyle,
    grid: { top: 30, right: 20, bottom: 40, left: 55 },
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
      data: timeSeries.map((t) => t.hour),
      axisLine: ct.axisLine,
      axisTick: { show: false },
      axisLabel: { interval: 3, color: ct.axisLabelColor },
    },
    yAxis: {
      type: "value",
      axisLine: ct.axisLine,
      splitLine: ct.splitLine,
      axisLabel: { formatter: (v) => v >= 1000 ? `${v / 1000}k` : v, color: ct.axisLabelColor },
    },
    series: [
      {
        name: "Crowd",
        type: "line",
        data: timeSeries.map((t) => t.crowd),
        smooth: true,
        lineStyle: { color: ct.primaryColor, width: 2 },
        areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: ct.isLight ? "rgba(2,132,199,0.25)" : "rgba(88,166,255,0.3)" }, { offset: 1, color: "rgba(88,166,255,0)" }] } },
        symbol: "none",
      },
    ],
  };

  const queueChartOption = {
    backgroundColor: "transparent",
    textStyle: ct.textStyle,
    grid: { top: 20, right: 10, bottom: 50, left: 50 },
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
      data: queues.map((q) => q.gate),
      axisLabel: { color: ct.axisLabelColor, rotate: 20 },
      axisLine: ct.axisLine,
      axisTick: { show: false },
    },
    yAxis: { type: "value", axisLabel: { color: ct.axisLabelColor }, splitLine: ct.splitLine, axisLine: ct.axisLine },
    series: [
      { name: "Queue Length", type: "bar", data: queues.map((q) => ({ value: q.length, itemStyle: { color: q.status === "high" ? ct.dangerColor : q.status === "medium" ? ct.secondaryColor : ct.successColor } })), barMaxWidth: 40 },
    ],
  };

  return (
    <div className="cc-page">
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title">Crowd Intelligence</div>
          <div className="cc-page-subtitle">Real-time crowd analytics AI powered</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className="cc-live-dot" />
          <span style={{ fontSize: 10, color: "var(--cc-green)" }}>LIVE UPDATE</span>
        </div>
      </div>

      {/* KPIs */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <KpiCard label="Current Crowd" value={(totalCrowd || 0).toLocaleString()} severity={totalCrowd > 38000 ? "critical" : "normal"} icon="bi-people-fill" sub={`${(((totalCrowd || 0) / 40000) * 100).toFixed(1)}% of total capacity`} />
        <KpiCard label="Inflow / min" value={inflowPerMin || 0} icon="bi-arrow-down-circle-fill" trend={(inflowPerMin || 0) - (outflowPerMin || 0)} />
        <KpiCard label="Outflow / min" value={outflowPerMin || 0} icon="bi-arrow-up-circle-fill" />
        <KpiCard label="Net Accumulation" value={`+${(inflowPerMin || 0) - (outflowPerMin || 0)}`} icon="bi-graph-up" severity={(inflowPerMin || 0) - (outflowPerMin || 0) > 200 ? "high" : "normal"} sub="per minute" />
        <KpiCard label="Avg Queue Wait" value={`${summary?.avg_queue_wait ?? summary?.avgQueueWait ?? 0} min`} icon="bi-hourglass-split" severity={(summary?.avg_queue_wait ?? summary?.avgQueueWait ?? 0) > 25 ? "high" : "normal"} />
      </div>

      {/* Charts row */}
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 12 }}>
        <div className="cc-card cc-chart" style={{ padding: 0 }}>
          <div className="cc-section-header"><div className="cc-section-title">Crowd Trend — Today</div></div>
          {timeSeries && timeSeries.some((t) => (t.crowd || 0) > 0 || (t.inflow || 0) > 0) ? (
            <ReactECharts option={chartOption} style={{ height: 220 }} />
          ) : (
            <div style={{ height: 220, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--cc-text-muted)", fontSize: 13, fontStyle: "italic" }}>
              No historical data available
            </div>
          )}
        </div>
        <div className="cc-card cc-chart" style={{ padding: 0 }}>
          <div className="cc-section-header"><div className="cc-section-title">Queue Lengths by Gate</div></div>
          {queues && queues.length > 0 ? (
            <ReactECharts option={queueChartOption} style={{ height: 220 }} />
          ) : (
            <div style={{ height: 220, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--cc-text-muted)", fontSize: 13, fontStyle: "italic" }}>
              No queue data available
            </div>
          )}
        </div>
      </div>

      {/* Zone table */}
      <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
        <div className="cc-section-header"><div className="cc-section-title">Zone-by-Zone Crowd Status</div></div>
        <div style={{ overflowX: "auto" }}>
          <table className="cc-table">
            <thead>
              <tr>
                <th>Zone</th>
                <th>People</th>
                <th>Capacity</th>
                <th>Occupancy</th>
                <th>Density</th>
                <th>Inflow</th>
                <th>Outflow</th>
                <th>Net</th>
                <th>Risk</th>
                <th>Prediction</th>
              </tr>
            </thead>
            <tbody>
              {zones.map((z) => {
                const people = z.people ?? z.current_people ?? 0;
                const capacity = z.capacity || 1;
                const risk = (z.risk || z.risk_level || "low").toLowerCase();
                const occupancyPct = z.occupancy_pct ?? z.occupancyPct ?? Math.round((people / capacity) * 100);
                const inflow = z.inflow || 0;
                const outflow = z.outflow || 0;
                const net = inflow - outflow;
                return (
                  <tr key={z.id || z.zone_code}>
                    <td><span style={{ fontWeight: 600, color: "var(--cc-text-primary)" }}>{z.name || z.zone_code}</span><br /><span style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>{z.label || z.name}</span></td>
                    <td style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 600, color: RISK_COLOR[risk] || "inherit" }}>{people.toLocaleString()}</td>
                    <td style={{ fontFamily: "var(--cc-font-mono)" }}>{(z.capacity || 0).toLocaleString()}</td>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <div className="cc-progress" style={{ width: 60, height: 4 }}>
                          <div className="cc-progress-fill" style={{ width: `${Math.min(100, (people / capacity) * 100)}%`, background: RISK_COLOR[risk] || "var(--cc-green)" }} />
                        </div>
                        <span style={{ fontFamily: "var(--cc-font-mono)", fontSize: 11, color: RISK_COLOR[risk] || "inherit" }}>{occupancyPct}%</span>
                      </div>
                    </td>
                    <td style={{ fontFamily: "var(--cc-font-mono)", fontSize: 11 }}>{z.density_label || z.densityLabel || "LOW"}</td>
                    <td style={{ fontFamily: "var(--cc-font-mono)", color: "var(--cc-green)" }}>{inflow}/m</td>
                    <td style={{ fontFamily: "var(--cc-font-mono)", color: "var(--cc-blue)" }}>{outflow}/m</td>
                    <td style={{ fontFamily: "var(--cc-font-mono)", color: net > 0 ? "var(--cc-red)" : "var(--cc-green)" }}>{net > 0 ? "+" : ""}{net}/m</td>
                    <td><StatusBadge status={risk} /></td>
                    <td style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>
                      {z.prediction?.critical_in_minutes || z.prediction?.criticalInMinutes ? <span style={{ color: "var(--cc-red)" }}>Critical in {z.prediction?.critical_in_minutes || z.prediction?.criticalInMinutes}m</span> :
                        z.prediction?.next_level || z.prediction?.nextLevel ? <span style={{ color: "var(--cc-yellow)" }}>{z.prediction?.next_level || z.prediction?.nextLevel} in {z.prediction?.next_level_in_minutes || z.prediction?.nextLevelInMinutes}m</span> : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Queue table */}
      <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
        <div className="cc-section-header"><div className="cc-section-title">Queue Analytics</div></div>
        <table className="cc-table">
          <thead>
            <tr><th>Queue</th><th>Gate</th><th>Zone</th><th>Length</th><th>Wait</th><th>Processing</th><th>Growth</th><th>Status</th></tr>
          </thead>
          <tbody>
            {queues.length === 0 ? (
              <tr><td colSpan={8} style={{ textAlign: "center", color: "var(--cc-text-muted)", padding: "20px 0" }}>No active queues</td></tr>
            ) : (
              queues.map((q) => (
                <tr key={q.id || q.gate}>
                  <td style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 600, color: "var(--cc-text-primary)" }}>{q.id}</td>
                  <td>{q.gate}</td>
                  <td style={{ color: "var(--cc-text-muted)" }}>{q.zone}</td>
                  <td style={{ fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-primary)", fontWeight: 600 }}>{q.length ?? 0}</td>
                  <td style={{ fontFamily: "var(--cc-font-mono)", color: (q.wait_minutes ?? q.waitMinutes ?? 0) > 20 ? "var(--cc-red)" : (q.wait_minutes ?? q.waitMinutes ?? 0) > 12 ? "var(--cc-yellow)" : "var(--cc-green)" }}>{q.wait_minutes ?? q.waitMinutes ?? 0} min</td>
                  <td style={{ fontFamily: "var(--cc-font-mono)" }}>{q.processing_rate ?? q.processingRate ?? 0}/min</td>
                  <td style={{ fontFamily: "var(--cc-font-mono)", color: (q.growth_rate ?? q.growthRate ?? 0) > 5 ? "var(--cc-red)" : (q.growth_rate ?? q.growthRate ?? 0) > 0 ? "var(--cc-yellow)" : "var(--cc-green)" }}>
                    {(q.growth_rate ?? q.growthRate ?? 0) > 0 ? "+" : ""}{q.growth_rate ?? q.growthRate ?? 0}/min
                  </td>
                  <td><StatusBadge status={q.status || "low"} /></td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
