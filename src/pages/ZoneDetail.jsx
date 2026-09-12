// Zone Detail page
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import StatusBadge from "../components/common/StatusBadge.jsx";
import { getZoneById } from "../services/zoneService.js";
import { LoadingState, ErrorState } from "../components/common/States.jsx";

import { useAppStore } from "../store/useAppStore.js";
import { getChartTheme } from "../utils/chartTheme.js";

export default function ZoneDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const theme = useAppStore((s) => s.theme);
  const ct = getChartTheme(theme);
  const [zone, setZone] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getZoneById(id).then((z) => { setZone(z); setLoading(false); }).catch(() => setLoading(false));
  }, [id]);

  if (loading) return <LoadingState />;
  if (!zone) return <ErrorState message="Zone not found" onRetry={() => navigate("/zones")} />;

  const currentPeople = zone.people ?? zone.current_people ?? 0;
  const capacity = zone.capacity > 0 ? zone.capacity : 1;
  const occupancyPct = ((currentPeople / capacity) * 100).toFixed(1);

  const gaugeOption = {
    backgroundColor: "transparent",
    series: [{
      type: "gauge",
      startAngle: 200,
      endAngle: -20,
      min: 0, max: 150,
      splitNumber: 5,
      radius: "90%",
      pointer: { itemStyle: { color: zone.color } },
      axisLine: { lineStyle: { width: 12, color: [[0.67, ct.successColor], [0.87, ct.secondaryColor], [1, ct.dangerColor]] } },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      detail: {
        valueAnimation: true,
        formatter: "{value}%",
        fontSize: 22, fontWeight: 700, color: zone.color, fontFamily: "JetBrains Mono, monospace",
        offsetCenter: [0, "20%"],
      },
      data: [{ value: parseFloat(occupancyPct) || 0, name: "Occupancy" }],
    }],
  };

  const currentInflow = zone.inflow || 0;
  const currentOutflow = zone.outflow || 0;
  const flowOption = {
    backgroundColor: "transparent",
    textStyle: ct.textStyle,
    grid: { top: 20, right: 20, bottom: 40, left: 55 },
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
      data: ["Now-5m", "Now-4m", "Now-3m", "Now-2m", "Now-1m", "Now"],
      axisLine: ct.axisLine, axisTick: { show: false }, axisLabel: { color: ct.axisLabelColor },
    },
    yAxis: { axisLine: ct.axisLine, splitLine: ct.splitLine, axisLabel: { color: ct.axisLabelColor } },
    series: [
      { name: "Inflow", type: "bar", data: zone.flow_history?.inflow || [0, 0, 0, 0, 0, currentInflow], itemStyle: { color: ct.successColor }, barMaxWidth: 30 },
      { name: "Outflow", type: "bar", data: zone.flow_history?.outflow || [0, 0, 0, 0, 0, currentOutflow], itemStyle: { color: ct.primaryColor }, barMaxWidth: 30 },
    ],
  };

  return (
    <div className="cc-page">
      <div className="cc-page-header">
        <div>
          <button className="cc-btn" onClick={() => navigate("/zones")} style={{ marginBottom: 6 }}>
            <i className="bi bi-arrow-left" /> Back to Zones
          </button>
          <div className="cc-page-title" style={{ color: zone.color }}>{zone.name}</div>
          <div className="cc-page-subtitle">{zone.label}</div>
        </div>
        <StatusBadge status={zone.risk} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {/* Gauge */}
        <div className="cc-card cc-chart" style={{ padding: 0 }}>
          <div className="cc-section-header"><div className="cc-section-title">Occupancy</div></div>
          <ReactECharts option={gaugeOption} style={{ height: 200 }} />
        </div>

        {/* Flow chart */}
        <div className="cc-card cc-chart" style={{ padding: 0 }}>
          <div className="cc-section-header"><div className="cc-section-title">5-min Flow</div></div>
          <ReactECharts option={flowOption} style={{ height: 200 }} />
        </div>
      </div>

      {/* Stats grid */}
      <div className="cc-card">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
          {[
            { label: "People", value: (zone?.people ?? zone?.current_people ?? 0).toLocaleString(), color: zone?.color },
            { label: "Capacity", value: (zone?.capacity ?? 0).toLocaleString() },
            { label: "Occupancy", value: `${occupancyPct}%`, color: zone?.color },
            { label: "Density", value: zone?.density_label || zone?.densityLabel || "LOW", color: zone?.color },
            { label: "Inflow", value: `${zone?.inflow || 0}/min`, color: "var(--cc-green)" },
            { label: "Outflow", value: `${zone?.outflow || 0}/min`, color: "var(--cc-blue)" },
            { label: "Net Flow", value: `${(zone?.inflow || 0) > (zone?.outflow || 0) ? "+" : ""}${(zone?.inflow || 0) - (zone?.outflow || 0)}/min`, color: (zone?.inflow || 0) > (zone?.outflow || 0) ? "var(--cc-red)" : "var(--cc-green)" },
            { label: "Cameras", value: zone?.cameras?.length || 0 },
          ].map((item) => (
            <div key={item.label}>
              <div className="cc-label" style={{ marginBottom: 4 }}>{item.label}</div>
              <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 18, fontWeight: 700, color: item.color || "var(--cc-text-primary)" }}>{item.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* AI Prediction */}
      {zone.prediction?.criticalInMinutes && (
        <div style={{ padding: "12px 16px", background: "var(--cc-red-dim)", border: "1px solid var(--cc-red-border)", borderRadius: "var(--cc-radius)", borderLeft: "3px solid var(--cc-red)" }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--cc-red)", marginBottom: 4 }}>
            <i className="bi bi-clock-history" style={{ marginRight: 6 }} />
            AI PREDICTION — CRITICAL IN {zone.prediction.criticalInMinutes} MINUTES
          </div>
          <div style={{ fontSize: 11, color: "var(--cc-text-secondary)" }}>
            AI systems predict Zone {zone.name} will reach critical density in {zone.prediction.criticalInMinutes} minutes at current inflow/outflow rates.
            Immediate intervention is recommended.
          </div>
        </div>
      )}
    </div>
  );
}
