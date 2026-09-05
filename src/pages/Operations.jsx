// Operations page — command center operations
import { useEffect, useState } from "react";
import StatusBadge from "../components/common/StatusBadge.jsx";
import { getPoliceUnits, getMedicalTeams, getEmergencyRoutes } from "../services/operationsService.js";
import { LoadingState } from "../components/common/States.jsx";

const UNIT_STATUS_COLOR = { available: "low", responding: "high", standby: "medium" };
const ROUTE_STATUS_COLOR = { clear: "low", partial: "high", blocked: "critical" };
const ROUTE_ICONS = { clear: "bi-check-circle-fill", partial: "bi-exclamation-circle-fill", blocked: "bi-x-circle-fill" };

export default function Operations() {
  const [police, setPolice] = useState([]);
  const [medical, setMedical] = useState([]);
  const [routes, setRoutes] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getPoliceUnits(), getMedicalTeams(), getEmergencyRoutes()])
      .then(([p, m, r]) => { setPolice(p); setMedical(m); setRoutes(r); setLoading(false); });
  }, []);

  if (loading) return <LoadingState />;

  const availablePolice = police.filter((u) => u.status === "available").length;
  const respondingPolice = police.filter((u) => u.status === "responding").length;

  return (
    <div className="cc-page">
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title">Operations Center</div>
          <div className="cc-page-subtitle">Police units, medical teams, emergency routes</div>
        </div>
      </div>

      
      <div style={{ display: "flex", gap: 8 }}>
        {[
          { label: "Police Units", value: police.length, sub: `${availablePolice} available`, color: "var(--cc-blue)" },
          { label: "Responding", value: respondingPolice, color: "var(--cc-orange)" },
          { label: "Medical Teams", value: medical.length, sub: `${medical.filter((m) => m.status === "available").length} available`, color: "var(--cc-green)" },
          { label: "Emergency Routes", value: routes.length, sub: `${routes.filter((r) => r.status === "clear").length} clear`, color: "var(--cc-text-primary)" },
          { label: "Routes Blocked", value: routes.filter((r) => r.status === "blocked").length, color: "var(--cc-red)" },
        ].map((s) => (
          <div key={s.label} className="cc-card" style={{ flex: 1 }}>
            <div className="cc-label">{s.label}</div>
            <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 22, fontWeight: 700, color: s.color }}>{s.value}</div>
            {s.sub && <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 2 }}>{s.sub}</div>}
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        
        <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
          <div className="cc-section-header"><div className="cc-section-title">Police Units</div></div>
          <div style={{ maxHeight: 400, overflow: "auto" }}>
            {police.map((unit) => (
              <div key={unit.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 14px", borderBottom: "1px solid var(--cc-border-light)" }}>
                <div style={{ width: 32, height: 32, borderRadius: "var(--cc-radius-sm)", background: "var(--cc-blue-dim)", border: "1px solid var(--cc-blue-border)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, color: "var(--cc-blue)", flexShrink: 0 }}>
                  {unit.id.replace("UNIT-", "")}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--cc-text-primary)" }}>{unit.name}</div>
                  <div style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>{unit.location} — {unit.zone}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <StatusBadge status={UNIT_STATUS_COLOR[unit.status]} label={unit.status.toUpperCase()} />
                  <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 2 }}>{unit.personnel} personnel</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
            <div className="cc-section-header"><div className="cc-section-title">Medical Teams</div></div>
            {medical.map((team) => (
              <div key={team.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 14px", borderBottom: "1px solid var(--cc-border-light)" }}>
                <i className="bi bi-heart-pulse-fill" style={{ color: "var(--cc-red)", fontSize: 16 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--cc-text-primary)" }}>{team.name}</div>
                  <div style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>{team.location}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <StatusBadge status={UNIT_STATUS_COLOR[team.status]} label={team.status.toUpperCase()} />
                  {team.ambulance && <div style={{ fontSize: 9, color: "var(--cc-red)", marginTop: 2 }}>🚑 Ambulance</div>}
                </div>
              </div>
            ))}
          </div>

          
          <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
            <div className="cc-section-header"><div className="cc-section-title">Emergency Routes</div></div>
            {routes.map((r) => (
              <div key={r.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 14px", borderBottom: "1px solid var(--cc-border-light)" }}>
                <i className={`bi ${ROUTE_ICONS[r.status]}`} style={{ color: r.status === "clear" ? "var(--cc-green)" : r.status === "partial" ? "var(--cc-orange)" : "var(--cc-red)", fontSize: 16 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--cc-text-primary)" }}>{r.name}</div>
                  <div style={{ fontSize: 10, color: "var(--cc-text-muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.description}</div>
                  {r.obstruction && <div style={{ fontSize: 10, color: "var(--cc-orange)", marginTop: 2 }}>{r.obstruction}</div>}
                </div>
                <div style={{ textAlign: "right", flexShrink: 0 }}>
                  <StatusBadge status={ROUTE_STATUS_COLOR[r.status]} label={r.status.toUpperCase()} />
                  {r.estimatedTime && <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 2 }}>ETA: {r.estimatedTime}</div>}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
