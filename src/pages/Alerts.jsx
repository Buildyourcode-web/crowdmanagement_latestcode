// Alerts page — centralized alert management
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import AlertCard from "../components/common/AlertCard.jsx";
import { useAlertStore } from "../store/useAlertStore.js";

const TYPE_FILTERS = ["all", "crowd", "frs", "medical", "camera", "security", "traffic"];
const SEV_FILTERS = ["all", "critical", "high", "medium", "low"];

export default function Alerts() {
  const navigate = useNavigate();
  const { alerts, acknowledgeAlert } = useAlertStore();
  const [sevFilter, setSevFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [search, setSearch] = useState("");

  const filtered = alerts
    .filter((a) => sevFilter === "all" || a.severity === sevFilter)
    .filter((a) => typeFilter === "all" || a.type === typeFilter)
    .filter((a) => !search || a.title.toLowerCase().includes(search.toLowerCase()) || a.zone?.toLowerCase().includes(search.toLowerCase()));

  const counts = SEV_FILTERS.slice(1).reduce((acc, s) => {
    acc[s] = alerts.filter((a) => a.severity === s).length;
    return acc;
  }, {});

  return (
    <div className="cc-page">
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title">Alert Management</div>
          <div className="cc-page-subtitle">{filtered.length} alerts {alerts.filter((a) => !a.acknowledged).length} unacknowledged</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className="cc-live-dot" />
          <span style={{ fontSize: 10, color: "var(--cc-green)" }}>LIVE</span>
        </div>
      </div>

      {/* Severity summary */}
      <div style={{ display: "flex", gap: 8 }}>
        {SEV_FILTERS.map((f) => {
          const colors = { critical: "var(--cc-red)", high: "var(--cc-orange)", medium: "var(--cc-yellow)", low: "var(--cc-green)", all: "var(--cc-blue)" };
          return (
            <button
              key={f}
              className={`cc-btn${sevFilter === f ? " cc-btn-primary" : ""}`}
              style={{ fontSize: 11, padding: "4px 12px", borderColor: sevFilter === f ? undefined : colors[f] }}
              onClick={() => setSevFilter(f)}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
              {f !== "all" && <span style={{ marginLeft: 4, fontFamily: "var(--cc-font-mono)", color: sevFilter === f ? "#fff" : colors[f] }}>({counts[f] || 0})</span>}
            </button>
          );
        })}
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <div style={{ position: "relative", flex: 1, minWidth: 200 }}>
          <i className="bi bi-search" style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--cc-text-muted)", fontSize: 12 }} />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search alerts..." style={{ width: "100%", padding: "7px 10px 7px 30px", background: "var(--cc-bg-input)", border: "1px solid var(--cc-border)", borderRadius: "var(--cc-radius)", color: "var(--cc-text-primary)", fontSize: 12 }} />
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {TYPE_FILTERS.map((t) => (
            <button key={t} className={`cc-btn${typeFilter === t ? " cc-btn-primary" : ""}`} style={{ fontSize: 11, padding: "4px 10px", textTransform: "capitalize" }} onClick={() => setTypeFilter(t)}>
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Alert list */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {filtered.length === 0 ? (
          <div style={{ textAlign: "center", padding: 40, color: "var(--cc-green)" }}>
            <i className="bi bi-shield-check" style={{ fontSize: 28, display: "block", marginBottom: 8 }} />
            No alerts match your filters
          </div>
        ) : (
          filtered.map((alert) => (
            <AlertCard
              key={alert.id}
              alert={alert}
              onAcknowledge={acknowledgeAlert}
              onViewMap={() => navigate("/live-map")}
              onViewCamera={() => navigate("/cameras")}
            />
          ))
        )}
      </div>
    </div>
  );
}
