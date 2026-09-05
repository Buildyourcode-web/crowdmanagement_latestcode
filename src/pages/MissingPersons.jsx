// Missing Persons page
import { useEffect, useState } from "react";
import StatusBadge from "../components/common/StatusBadge.jsx";
import { getMissingPersons } from "../services/frsService.js";
import { LoadingState } from "../components/common/States.jsx";

const STATUS_COLORS = { searching: "medium", found: "low" };

export default function MissingPersons() {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    getMissingPersons().then((d) => { setCases(d); setLoading(false); });
  }, []);

  if (loading) return <LoadingState />;

  const searching = cases.filter((c) => c.status === "searching").length;

  return (
    <div className="cc-page">
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title">Missing Persons</div>
          <div className="cc-page-subtitle">{searching} active search{searching !== 1 ? "es" : ""}  {cases.length} total cases</div>
        </div>
        <div style={{ padding: "4px 10px", background: "var(--cc-yellow-dim)", border: "1px solid var(--cc-yellow-border)", borderRadius: "var(--cc-radius)", fontSize: 10, fontWeight: 700, color: "var(--cc-yellow)" }}>
          DEMO DATA NOT REAL PERSONS
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: selected ? "1fr 1fr" : "1fr", gap: 12 }}>
        {/* Case list */}
        <div>
          {cases.map((c) => (
            <div
              key={c.id}
              className="cc-card"
              style={{
                cursor: "pointer", marginBottom: 10,
                borderLeft: `3px solid ${c.status === "searching" ? "var(--cc-yellow)" : "var(--cc-green)"}`,
                background: selected?.id === c.id ? "var(--cc-bg-card-hover)" : undefined,
              }}
              onClick={() => setSelected(selected?.id === c.id ? null : c)}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                <span style={{ fontFamily: "var(--cc-font-mono)", fontSize: 13, fontWeight: 700, color: "var(--cc-text-primary)" }}>{c.id}</span>
                <StatusBadge status={STATUS_COLORS[c.status] || "info"} label={c.status.toUpperCase()} />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 12, marginBottom: 8 }}>
                <div><div className="cc-label">Description</div><div style={{ color: "var(--cc-text-secondary)" }}>{c.description}</div></div>
                <div><div className="cc-label">Age / Gender</div><div style={{ color: "var(--cc-text-secondary)" }}>{c.age} / {c.gender}</div></div>
                <div><div className="cc-label">Reported</div><div style={{ fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-primary)", fontSize: 11 }}>{new Date(c.reportedAt).toLocaleTimeString("en-IN", { hour12: false, timeZone: "Asia/Kolkata" })}</div></div>
                <div><div className="cc-label">Last Known Zone</div><div style={{ fontWeight: 600, color: "var(--cc-text-primary)" }}>{c.lastKnownZone}</div></div>
                {c.lastSeenCamera && (
                  <div><div className="cc-label">Last Camera</div><div style={{ fontFamily: "var(--cc-font-mono)", color: "var(--cc-blue)", fontSize: 11 }}>{c.lastSeenCamera}</div></div>
                )}
                <div><div className="cc-label">Last Seen</div><div style={{ fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-primary)", fontSize: 11 }}>{new Date(c.lastSeenTime).toLocaleTimeString("en-IN", { hour12: false, timeZone: "Asia/Kolkata" })}</div></div>
              </div>

              {c.candidateMatches?.length > 0 && (
                <div style={{ padding: "6px 10px", background: "var(--cc-yellow-dim)", border: "1px solid var(--cc-yellow-border)", borderRadius: "var(--cc-radius-sm)", fontSize: 11, color: "var(--cc-yellow)" }}>
                  <i className="bi bi-person-bounding-box" style={{ marginRight: 4 }} />
                  POSSIBLE FRS MATCH REQUIRES HUMAN REVIEW
                </div>
              )}

              <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 8 }}>{c.notes}</div>
            </div>
          ))}
        </div>

        {/* Detail panel */}
        {selected && (
          <div className="cc-card">
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
              <i className="bi bi-person-exclamation" style={{ fontSize: 20, color: "var(--cc-yellow)" }} />
              <div>
                <div style={{ fontWeight: 700, color: "var(--cc-text-primary)" }}>Case {selected.id}</div>
                <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>
                  Status: <span style={{ color: selected.status === "searching" ? "var(--cc-yellow)" : "var(--cc-green)", fontWeight: 600 }}>{selected.status.toUpperCase()}</span>
                </div>
              </div>
              <button className="cc-btn" style={{ marginLeft: "auto", fontSize: 11 }} onClick={() => setSelected(null)}>
                <i className="bi bi-x" /> Close
              </button>
            </div>

            {/* Timeline */}
            <div className="cc-section-title" style={{ marginBottom: 10 }}>Timeline</div>
            {[
              { label: "Reported", time: selected.reportedAt, color: "var(--cc-blue)" },
              { label: "Last Seen", time: selected.lastSeenTime, color: "var(--cc-yellow)" },
              selected.candidateMatches?.length > 0 && { label: "FRS Candidate", time: new Date().toISOString(), color: "var(--cc-orange)" },
            ].filter(Boolean).map((item, i) => (
              <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start", marginBottom: 10 }}>
                <div style={{ width: 10, height: 10, borderRadius: "50%", background: item.color, flexShrink: 0, marginTop: 2 }} />
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "var(--cc-text-primary)" }}>{item.label}</div>
                  <div style={{ fontSize: 10, fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-muted)" }}>
                    {new Date(item.time).toLocaleTimeString("en-IN", { hour12: false, timeZone: "Asia/Kolkata" })}
                  </div>
                </div>
              </div>
            ))}

            <hr className="cc-divider" style={{ margin: "14px 0" }} />

            <div style={{ fontSize: 11, color: "var(--cc-text-muted)", lineHeight: 1.5 }}>{selected.notes}</div>

            <div style={{ marginTop: 14, display: "flex", gap: 8 }}>
              <button className="cc-btn cc-btn-primary" style={{ fontSize: 11 }}>
                <i className="bi bi-camera-video" /> Check Cameras
              </button>
              <button className="cc-btn" style={{ fontSize: 11 }}>
                <i className="bi bi-broadcast" /> Broadcast Alert
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
