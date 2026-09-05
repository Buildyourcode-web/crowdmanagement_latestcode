// Predictions page — predictive analytics
import { useEffect, useState } from "react";
import ReactECharts from "echarts-for-react";
import { getPredictions, getQueuePredictions, getZoneRiskPredictions } from "../services/predictionService.js";
import { LoadingState } from "../components/common/States.jsx";

import { useAppStore } from "../store/useAppStore.js";
import { getChartTheme } from "../utils/chartTheme.js";

export default function Predictions() {
  const theme = useAppStore((s) => s.theme);
  const ct = getChartTheme(theme);
  const [data, setData] = useState(null);
  const [queueData, setQueueData] = useState([]);
  const [zoneData, setZoneData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      getPredictions().catch(() => null),
      getQueuePredictions().catch(() => []),
      getZoneRiskPredictions().catch(() => []),
    ])
      .then(([d, q, z]) => {
        setData(d || {});
        setQueueData(Array.isArray(q) ? q : (q?.data || []));
        setZoneData(Array.isArray(z) ? z : (z?.data || []));
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <LoadingState />;

  const current = data?.current ?? data?.summary?.current ?? 0;
  const plus15 = data?.forecast_15_min ?? data?.summary?.plus15 ?? 0;
  const plus30 = data?.forecast_30_min ?? data?.summary?.plus30 ?? 0;
  const plus45 = data?.forecast_45_min ?? data?.summary?.plus45 ?? 0;
  const plus60 = data?.forecast_60_min ?? data?.summary?.plus60 ?? 0;

  const actual = data?.timeSeries?.actual || [["Now", current]];
  const predicted = data?.timeSeries?.predicted || [["+15m", plus15], ["+30m", plus30], ["+45m", plus45], ["+60m", plus60]];
  const lower = data?.timeSeries?.lower || [];
  const upper = data?.timeSeries?.upper || [];

  const mainChartOption = {
    backgroundColor: "transparent",
    textStyle: ct.textStyle,
    legend: {
      top: 8, right: 16,
      textStyle: ct.legendText,
      data: ["Actual", "Predicted"],
    },
    grid: { top: 50, right: 20, bottom: 50, left: 60 },
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
      data: [...actual.map((a) => a[0]), ...predicted.map((p) => p[0])],
      axisLine: ct.axisLine,
      axisTick: { show: false },
      axisLabel: { color: ct.axisLabelColor },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      axisLine: ct.axisLine,
      splitLine: ct.splitLine,
      axisLabel: { formatter: (v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v, color: ct.axisLabelColor },
    },
    series: [
      {
        name: "Actual",
        type: "line",
        data: actual.map((a) => a[1]),
        lineStyle: { color: ct.primaryColor, width: 2 },
        symbol: "circle",
        smooth: true,
      },
      {
        name: "Predicted",
        type: "line",
        data: [...Array(Math.max(0, actual.length - 1)).fill(null), actual[actual.length - 1]?.[1] ?? current, ...predicted.map((p) => p[1])],
        lineStyle: { color: ct.secondaryColor, width: 2, type: "dashed" },
        symbol: "circle",
        smooth: true,
      },
    ],
  };

  return (
    <div className="cc-page">
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title">Predictive Analytics</div>
          <div className="cc-page-subtitle">AI-powered crowd forecasting next 60 minutes</div>
        </div>
        <div style={{ padding: "4px 10px", background: "var(--cc-blue-dim)", border: "1px solid var(--cc-blue-border)", borderRadius: "var(--cc-radius)", fontSize: 10, fontWeight: 700, color: "var(--cc-blue)" }}>
          {data?.status || "LIVE AI FORECAST"}
        </div>
      </div>

      {/* Forecast summary */}
      <div style={{ display: "flex", gap: 8 }}>
        {[
          { label: "Current", value: current.toLocaleString(), color: "var(--cc-blue)", icon: "bi-people-fill" },
          { label: "+15 min", value: plus15.toLocaleString(), color: "var(--cc-green)", icon: "bi-graph-up" },
          { label: "+30 min", value: plus30.toLocaleString(), color: "var(--cc-yellow)", icon: "bi-graph-up" },
          { label: "+45 min", value: plus45.toLocaleString(), color: "var(--cc-orange)", icon: "bi-graph-up-arrow" },
          { label: "+60 min", value: plus60.toLocaleString(), color: "var(--cc-red)", icon: "bi-exclamation-triangle" },
        ].map((item) => (
          <div key={item.label} className="cc-card" style={{ flex: 1, borderLeft: `2px solid ${item.color}` }}>
            <div className="cc-label" style={{ marginBottom: 4 }}>{item.label}</div>
            <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 20, fontWeight: 700, color: item.color }}>{item.value}</div>
            <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 2 }}>predicted crowd</div>
          </div>
        ))}
      </div>

      {/* Main chart */}
      <div className="cc-card cc-chart" style={{ padding: 0 }}>
        <div className="cc-section-header">
          <div className="cc-section-title">Crowd Prediction — 60 Minute Window</div>
        </div>
        <ReactECharts option={mainChartOption} style={{ height: 280 }} />
      </div>

      {/* Zone predictions */}
      <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
        <div className="cc-section-header"><div className="cc-section-title">Zone-Level Risk Forecasts</div></div>
        <table className="cc-table">
          <thead>
            <tr><th>Zone</th><th>Current Risk</th><th>+30 min Forecast</th><th>Escalation Probability</th></tr>
          </thead>
          <tbody>
            {zoneData.length === 0 ? (
              <tr><td colSpan={4} style={{ textAlign: "center", color: "var(--cc-text-muted)", padding: "20px 0" }}>No high-risk zones forecasted</td></tr>
            ) : (
              zoneData.map((z) => (
                <tr key={z.zone}>
                  <td style={{ fontWeight: 600, color: "var(--cc-text-primary)" }}>{z.zone}</td>
                  <td style={{ fontFamily: "var(--cc-font-mono)", color: z.currentRisk === "CRITICAL" ? "var(--cc-red)" : "var(--cc-yellow)" }}>{z.currentRisk || z.current_risk || "NORMAL"}</td>
                  <td style={{ fontFamily: "var(--cc-font-mono)", color: z.predictedRisk30 === "CRITICAL" ? "var(--cc-red)" : "var(--cc-orange)" }}>{z.predictedRisk30 || z.predicted_risk_30 || "NORMAL"}</td>
                  <td style={{ fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-primary)" }}>{Math.round((z.probability || 0) * 100)}%</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Queue predictions */}
      <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
        <div className="cc-section-header"><div className="cc-section-title">Queue Wait Time Predictions</div></div>
        <table className="cc-table">
          <thead><tr><th>Gate</th><th>Current Wait</th><th>+30 min Wait</th><th>Trend</th></tr></thead>
          <tbody>
            {queueData.length === 0 ? (
              <tr><td colSpan={4} style={{ textAlign: "center", color: "var(--cc-text-muted)", padding: "20px 0" }}>No queue congestion forecasted</td></tr>
            ) : (
              queueData.map((q) => (
                <tr key={q.gate}>
                  <td style={{ fontWeight: 600 }}>{q.gate}</td>
                  <td style={{ fontFamily: "var(--cc-font-mono)" }}>{q.currentWaitMin ?? q.current_wait_min ?? 0} min</td>
                  <td style={{ fontFamily: "var(--cc-font-mono)", color: "var(--cc-yellow)" }}>{q.predictedWaitMin30 ?? q.predicted_wait_min_30 ?? 0} min</td>
                  <td><span className={`cc-badge ${q.trend || "stable"}`}>{(q.trend || "stable").toUpperCase()}</span></td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
