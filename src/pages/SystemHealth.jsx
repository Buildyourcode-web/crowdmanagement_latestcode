// System Health page
import { useEffect, useState } from "react";
import ReactECharts from "echarts-for-react";
import { getSystemHealth, getCameraHealthTable } from "../services/systemService.js";
import { useSystemStore } from "../store/useSystemStore.js";
import { LoadingState } from "../components/common/States.jsx";

import { useAppStore } from "../store/useAppStore.js";

function GaugeOption(value, color, isLight) {
  return {
    backgroundColor: "transparent",
    series: [{
      type: "gauge",
      startAngle: 200, endAngle: -20, min: 0, max: 100,
      radius: "85%",
      pointer: { show: false },
      axisLine: { lineStyle: { width: 10, color: [[value / 100, color], [1, isLight ? "#e2e8f0" : "#1e2730"]] } },
      axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false },
      detail: { formatter: `{value}%`, fontSize: 16, fontWeight: 700, color, fontFamily: "JetBrains Mono, monospace", offsetCenter: [0, "10%"] },
      data: [{ value }],
    }],
  };
}

export default function SystemHealth() {
  const [health, setHealth] = useState(null);
  const [camTable, setCamTable] = useState([]);
  const [loading, setLoading] = useState(true);
  const { cpu, ram, gpu } = useSystemStore();
  const theme = useAppStore((s) => s.theme);
  const isLight = theme === "light";

  useEffect(() => {
    Promise.all([getSystemHealth(), getCameraHealthTable()])
      .then(([h, c]) => { setHealth(h); setCamTable(c); setLoading(false); });
  }, []);

  if (loading) return <LoadingState />;

  const services = [
    { label: "Cameras", value: `${health?.cameras?.online ?? 0}/${health?.cameras?.total ?? 0}`, sub: "online", status: "healthy", icon: "bi-camera-video-fill" },
    { label: "Database", value: (health?.database?.status || "online").toUpperCase(), sub: `${health?.database?.latency ?? health?.database?.latencyMs ?? 0}ms`, status: health?.database?.status || "online", icon: "bi-server" },
    { label: "Redis", value: (health?.redis?.status || "offline").toUpperCase(), sub: health?.redis?.memory || "—", status: health?.redis?.status || "offline", icon: "bi-lightning-charge-fill" },
    { label: "WebSocket", value: (health?.websocket?.connections ?? 0).toLocaleString(), sub: "connections", status: health?.websocket?.status || "online", icon: "bi-wifi" },
    { label: "VPN", value: (health?.vpn?.status || "unknown").toUpperCase(), sub: `${health?.vpn?.latency ?? health?.vpn?.latencyMs ?? 0}ms`, status: "healthy", icon: "bi-shield-check-fill" },
    { label: "AI Engine", value: (health?.aiEngine?.status || "offline").toUpperCase(), sub: `${health?.aiEngine?.fps || 0} fps`, status: health?.aiEngine?.status || "offline", icon: "bi-cpu-fill" },
    { label: "FRS Engine", value: (health?.frsEngine?.status || "offline").toUpperCase(), sub: `${health?.frsEngine?.fps || 0} fps`, status: health?.frsEngine?.status || "offline", icon: "bi-person-bounding-box" },
    { label: "Network", value: health?.network?.bandwidth || "1 Gbps", sub: `${health?.network?.packetLoss || "0%"} loss`, status: health?.network?.status || "online", icon: "bi-hdd-network-fill" },
  ];

  return (
    <div className="cc-page">
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title">System Health</div>
          <div className="cc-page-subtitle">Infrastructure monitoring  real-time</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 10px", background: "var(--cc-yellow-dim)", border: "1px solid var(--cc-yellow-border)", borderRadius: "var(--cc-radius)", fontSize: 10, fontWeight: 700, color: "var(--cc-yellow)" }}>
          <i className="bi bi-exclamation-triangle" />
          {health.overallStatus.toUpperCase()}  GPU-03 high utilization
        </div>
      </div>

      {/* Resource gauges */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {[
          { label: "CPU", value: cpu, color: cpu > 80 ? "#f85149" : cpu > 65 ? "#e3b341" : "#3fb950" },
          { label: "RAM", value: ram, color: ram > 80 ? "#f85149" : ram > 65 ? "#e3b341" : "#3fb950" },
          { label: "GPU Avg", value: gpu, color: gpu > 85 ? "#f85149" : gpu > 70 ? "#e3b341" : "#3fb950" },
        ].map((r) => (
          <div key={r.label} className="cc-card cc-chart" style={{ padding: 0 }}>
            <div className="cc-section-header"><div className="cc-section-title">{r.label} Utilization</div></div>
            <ReactECharts option={GaugeOption(r.value, r.color, isLight)} style={{ height: 130 }} />
          </div>
        ))}
      </div>

      {/* GPU cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
        {health.gpu.units.map((gpu) => {
          const cls = gpu.status === "healthy" ? "low" : "medium";
          return (
            <div key={gpu.id} className="cc-card" style={{ borderLeft: `2px solid ${gpu.status === "warning" ? "var(--cc-yellow)" : "var(--cc-green)"}` }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                <span style={{ fontFamily: "var(--cc-font-mono)", fontSize: 12, fontWeight: 700, color: "var(--cc-text-primary)" }}>{gpu.id}</span>
                <span className={`cc-badge ${cls}`}>{gpu.status.toUpperCase()}</span>
              </div>
              <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginBottom: 10 }}>{gpu.label}</div>
              {[
                { label: "Utilization", value: `${gpu.utilization}%`, color: gpu.utilization > 85 ? "var(--cc-red)" : "var(--cc-text-primary)" },
                { label: "Memory", value: `${gpu.memory}%` },
                { label: "Temperature", value: `${gpu.temperature}°C`, color: gpu.temperature > 75 ? "var(--cc-orange)" : "var(--cc-text-primary)" },
                { label: "Inference", value: `${gpu.inferenceMs}ms` },
              ].map((item) => (
                <div key={item.label} style={{ display: "flex", justifyContent: "space-between", fontSize: 11, padding: "3px 0", borderBottom: "1px solid var(--cc-border-light)" }}>
                  <span style={{ color: "var(--cc-text-muted)" }}>{item.label}</span>
                  <span style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 600, color: item.color || "var(--cc-text-primary)" }}>{item.value}</span>
                </div>
              ))}
              <div style={{ marginTop: 8 }}>
                <div className="cc-progress" style={{ height: 3 }}>
                  <div className="cc-progress-fill" style={{ width: `${gpu.utilization}%`, background: gpu.utilization > 85 ? "var(--cc-red)" : gpu.utilization > 70 ? "var(--cc-yellow)" : "var(--cc-green)" }} />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Services */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
        {services.map((svc) => (
          <div key={svc.label} className="cc-card">
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <i className={`bi ${svc.icon}`} style={{ fontSize: 16, color: svc.status === "healthy" ? "var(--cc-green)" : "var(--cc-red)" }} />
              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--cc-text-primary)" }}>{svc.label}</span>
            </div>
            <div style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 700, fontSize: 14, color: svc.status === "healthy" ? "var(--cc-green)" : "var(--cc-red)" }}>{svc.value}</div>
            <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 2 }}>{svc.sub}</div>
          </div>
        ))}
      </div>

      {/* Camera health table */}
      <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
        <div className="cc-section-header"><div className="cc-section-title">Camera Health Summary</div></div>
        <div style={{ overflowX: "auto" }}>
          <table className="cc-table">
            <thead>
              <tr><th>Camera</th><th>Zone</th><th>Status</th><th>FPS</th><th>Latency</th><th>Packet Loss</th><th>Last Seen</th></tr>
            </thead>
            <tbody>
              {camTable.map((c) => (
                <tr key={c.id}>
                  <td style={{ fontFamily: "var(--cc-font-mono)", fontSize: 11, fontWeight: 600, color: "var(--cc-text-primary)" }}>{c.id}</td>
                  <td style={{ color: "var(--cc-text-muted)" }}>{c.zone}</td>
                  <td><span className={`cc-badge ${c.status}`}>{c.status.toUpperCase()}</span></td>
                  <td style={{ fontFamily: "var(--cc-font-mono)", color: (c.fps || 0) < 15 && c.fps > 0 ? "var(--cc-yellow)" : "var(--cc-text-primary)" }}>{c.fps || "—"}</td>
                  <td style={{ fontFamily: "var(--cc-font-mono)", color: (c.latency || 0) > 100 ? "var(--cc-orange)" : "var(--cc-text-primary)" }}>{c.latency ? `${c.latency}ms` : "—"}</td>
                  <td style={{ fontFamily: "var(--cc-font-mono)" }}>{c.packetLoss || "—"}</td>
                  <td style={{ color: c.status === "online" ? "var(--cc-green)" : "var(--cc-red)" }}>{c.lastSeen}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
