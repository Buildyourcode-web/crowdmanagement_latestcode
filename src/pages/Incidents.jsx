// Incidents page — incident management with lifecycle tracking
import { useEffect, useState } from "react";
import StatusBadge from "../components/common/StatusBadge.jsx";
import { getIncidents, updateIncidentStatus } from "../services/incidentService.js";
import { LoadingState } from "../components/common/States.jsx";

const LIFECYCLE = ["detected", "acknowledged", "assigned", "responding", "resolved"];
const SEV_COLORS = { critical: "var(--cc-red)", high: "var(--cc-orange)", medium: "var(--cc-yellow)", low: "var(--cc-green)" };

function Timeline({ incident }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 0, marginTop: 12 }}>
      {LIFECYCLE.map((step, i) => {
        const completed = incident.timeline?.includes(step);
        const isCurrent = incident.timeline?.[incident.timeline.length - 1] === step;
        return (
          <div key={step} style={{ display: "flex", alignItems: "center", flex: 1 }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flex: 1 }}>
              <div
                style={{
                  width: 20, height: 20, borderRadius: "50%", border: `2px solid ${completed ? (isCurrent ? "var(--cc-accent)" : "var(--cc-green)") : "var(--cc-border)"}`,
                  background: completed ? (isCurrent ? "var(--cc-accent)" : "var(--cc-green-dim)") : "var(--cc-bg-card)",
                  display: "flex", alignItems: "center", justifyContent: "center", fontSize: 9, color: completed ? (isCurrent ? "#fff" : "var(--cc-green)") : "var(--cc-text-muted)",
                }}
              >
                {completed && <i className={`bi bi-${isCurrent ? "circle-fill" : "check"}`} />}
              </div>
              <span style={{ fontSize: 8, fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: completed ? "var(--cc-text-secondary)" : "var(--cc-text-muted)", marginTop: 3, textAlign: "center" }}>
                {step}
              </span>
            </div>
            {i < LIFECYCLE.length - 1 && (
              <div style={{ height: 2, width: 20, background: incident.timeline?.includes(LIFECYCLE[i + 1]) ? "var(--cc-green)" : "var(--cc-border)", flexShrink: 0, marginBottom: 12 }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function Incidents() {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    getIncidents().then((d) => { setIncidents(d); setLoading(false); });
  }, []);

  const filtered = filter === "all" ? incidents : incidents.filter((i) => i.status === filter);

  if (loading) return <LoadingState />;

  return (
    <div className="cc-page">
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title">Incident Management</div>
          <div className="cc-page-subtitle">{incidents.filter((i) => i.status !== "resolved").length} active  {incidents.length} total</div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 6, marginBottom: 4 }}>
        {[["all", "All"], ["detected", "Detected"], ["acknowledged", "Acknowledged"], ["responding", "Responding"], ["resolved", "Resolved"]].map(([k, l]) => (
          <button key={k} className={`cc-btn${filter === k ? " cc-btn-primary" : ""}`} style={{ fontSize: 11 }} onClick={() => setFilter(k)}>{l}</button>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: selected ? "1fr 1fr" : "1fr", gap: 12 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {filtered.map((inc) => (
            <div
              key={inc.id}
              className="cc-card"
              style={{
                cursor: "pointer",
                borderLeft: `3px solid ${SEV_COLORS[inc.severity]}`,
                background: selected?.id === inc.id ? "var(--cc-bg-card-hover)" : undefined,
              }}
              onClick={() => setSelected(selected?.id === inc.id ? null : inc)}
            >
              <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4, flexWrap: "wrap" }}>
                    <span style={{ fontFamily: "var(--cc-font-mono)", fontSize: 12, fontWeight: 700, color: "var(--cc-text-primary)" }}>{inc.id}</span>
                    <StatusBadge status={inc.severity} />
                    <span className="cc-badge info">{inc.status.toUpperCase()}</span>
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--cc-text-primary)", marginBottom: 4 }}>{inc.typeLabel}</div>
                  <div style={{ fontSize: 11, color: "var(--cc-text-secondary)", marginBottom: 4 }}>{inc.location}</div>
                  {inc.assignedTeam && (
                    <div style={{ fontSize: 11, color: "var(--cc-blue)" }}>
                      <i className="bi bi-person-fill" style={{ marginRight: 4 }} />
                      {inc.assignedTeamLabel}
                    </div>
                  )}
                </div>
                <div style={{ fontSize: 10, color: "var(--cc-text-muted)", textAlign: "right", flexShrink: 0 }}>
                  {new Date(inc.detectedAt).toLocaleTimeString("en-IN", { hour12: false, timeZone: "Asia/Kolkata" })}
                </div>
              </div>
              <Timeline incident={inc} />
            </div>
          ))}
        </div>

        {/* Detail panel */}
        {selected && (
          <div className="cc-card">
            <div style={{ display: "flex", align: "center", justifyContent: "space-between", marginBottom: 14 }}>
              <div style={{ fontWeight: 700, fontSize: 14, color: "var(--cc-text-primary)" }}>{selected.id}</div>
              <button className="cc-btn" style={{ fontSize: 11 }} onClick={() => setSelected(null)}><i className="bi bi-x" /></button>
            </div>
            <div style={{ fontSize: 12, color: "var(--cc-text-secondary)", lineHeight: 1.6, marginBottom: 14 }}>{selected.description}</div>

            {/* Notes */}
            <div className="cc-section-title" style={{ marginBottom: 10 }}>Timeline Notes</div>
            {selected.notes?.map((n, i) => (
              <div key={i} style={{ padding: "8px 0", borderBottom: "1px solid var(--cc-border-light)", fontSize: 11 }}>
                <div style={{ display: "flex", gap: 8, marginBottom: 2 }}>
                  <span style={{ fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-muted)", fontSize: 10 }}>{new Date(n.time).toLocaleTimeString("en-IN", { hour12: false, timeZone: "Asia/Kolkata" })}</span>
                  <span style={{ fontWeight: 600, color: "var(--cc-blue)" }}>{n.author}</span>
                </div>
                <div style={{ color: "var(--cc-text-secondary)" }}>{n.text}</div>
              </div>
            ))}

            {/* Cameras */}
            {selected.cameras?.length > 0 && (
              <div style={{ marginTop: 14 }}>
                <div className="cc-section-title" style={{ marginBottom: 8 }}>Related Cameras</div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {selected.cameras.map((c) => (
                    <span key={c} style={{ fontFamily: "var(--cc-font-mono)", fontSize: 11, padding: "2px 8px", background: "var(--cc-blue-dim)", border: "1px solid var(--cc-blue-border)", borderRadius: "var(--cc-radius-sm)", color: "var(--cc-blue)" }}>{c}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
