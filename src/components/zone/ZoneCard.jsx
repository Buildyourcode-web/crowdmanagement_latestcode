// ZoneCard — displays zone status and metrics
import { useNavigate } from "react-router-dom";
import StatusBadge from "../common/StatusBadge.jsx";

function pct(people, capacity) {
  if (!capacity || capacity <= 0) return 0;
  return Math.round(((people || 0) / capacity) * 100);
}

export default function ZoneCard({ zone, onClick }) {
  const navigate = useNavigate();
  if (!zone) return null;

  const people = zone.people ?? zone.current_people ?? 0;
  const capacity = zone.capacity || 1;
  const risk = (zone.risk || zone.risk_level || "low").toLowerCase();
  const occupancyPct = zone.occupancy_pct ?? zone.occupancyPct ?? pct(people, capacity);
  const densityLabel = zone.density_label || zone.densityLabel || "LOW";
  const inflow = zone.inflow || 0;
  const outflow = zone.outflow || 0;
  const color = zone.color || "var(--cc-border)";

  const handleClick = () => {
    if (onClick) onClick(zone);
    else navigate(`/zones/${zone.id || zone.zone_code}`);
  };

  return (
    <div
      className="cc-card"
      style={{ cursor: "pointer", borderLeft: `2px solid ${color}` }}
      onClick={handleClick}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: "var(--cc-text-primary)" }}>{zone.name || zone.zone_code}</div>
          <div style={{ fontSize: 11, color: "var(--cc-text-muted)", marginTop: 1 }}>{zone.label || zone.name}</div>
        </div>
        <StatusBadge status={risk} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
        <div>
          <div className="cc-label">People</div>
          <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 20, fontWeight: 700, color: color }}>{people.toLocaleString()}</div>
        </div>
        <div>
          <div className="cc-label">Capacity</div>
          <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 20, fontWeight: 700, color: "var(--cc-text-secondary)" }}>{(zone.capacity || 0).toLocaleString()}</div>
        </div>
        <div>
          <div className="cc-label">Occupancy</div>
          <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 13, fontWeight: 600, color: color }}>{occupancyPct}%</div>
        </div>
        <div>
          <div className="cc-label">Density</div>
          <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 13, fontWeight: 600, color: color }}>{densityLabel}</div>
        </div>
      </div>

      <div className="cc-progress">
        <div
          className={`cc-progress-fill ${risk}`}
          style={{ width: `${Math.min(100, occupancyPct)}%`, background: color }}
        />
      </div>

      <div style={{ display: "flex", gap: 12, marginTop: 8, fontSize: 11 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 4, color: "var(--cc-green)" }}>
          <i className="bi bi-arrow-down-circle" />
          <span style={{ fontFamily: "var(--cc-font-mono)" }}>{inflow}/min in</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 4, color: "var(--cc-blue)" }}>
          <i className="bi bi-arrow-up-circle" />
          <span style={{ fontFamily: "var(--cc-font-mono)" }}>{outflow}/min out</span>
        </div>
      </div>

      {(zone.prediction?.critical_in_minutes || zone.prediction?.criticalInMinutes) && (
        <div style={{ marginTop: 8, padding: "4px 8px", background: "var(--cc-red-dim)", border: "1px solid var(--cc-red-border)", borderRadius: "var(--cc-radius-sm)", fontSize: 10, color: "var(--cc-red)", fontWeight: 600 }}>
          <i className="bi bi-clock-history" style={{ marginRight: 4 }} />
          AI: Critical in {zone.prediction?.critical_in_minutes || zone.prediction?.criticalInMinutes} min
        </div>
      )}
    </div>
  );
}
