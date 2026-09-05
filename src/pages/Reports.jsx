// Reports page — stub for Phase 2
export default function Reports() {
  return (
    <div className="cc-page">
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title">Reports</div>
          <div className="cc-page-subtitle">Event and operational reports</div>
        </div>
        <button className="cc-btn cc-btn-primary" style={{ fontSize: 11 }}>
          <i className="bi bi-download" /> Export
        </button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
        {[
          { icon: "bi-people-fill", label: "Attendance Report", sub: "Daily visitor counts, peak hours, zone distribution", date: "Today" },
          { icon: "bi-exclamation-triangle-fill", label: "Incident Report", sub: "All incidents, response times, resolutions", date: "Today" },
          { icon: "bi-camera-video-fill", label: "Camera Uptime Report", sub: "Camera availability, FPS, latency summary", date: "Today" },
          { icon: "bi-person-bounding-box", label: "FRS Activity Report", sub: "FRS scans, candidates, review outcomes", date: "Today" },
          { icon: "bi-graph-up", label: "Crowd Analytics Report", sub: "Zone analytics, flow patterns, density", date: "Today" },
          { icon: "bi-shield-exclamation", label: "Security Summary", sub: "Alerts, incidents, police response", date: "Today" },
        ].map((r) => (
          <div key={r.label} className="cc-card" style={{ cursor: "pointer" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              <i className={`bi ${r.icon}`} style={{ fontSize: 20, color: "var(--cc-accent)" }} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--cc-text-primary)" }}>{r.label}</div>
                <div style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>{r.date}</div>
              </div>
            </div>
            <div style={{ fontSize: 11, color: "var(--cc-text-secondary)", marginBottom: 12 }}>{r.sub}</div>
            <div style={{ display: "flex", gap: 6 }}>
              <button className="cc-btn" style={{ fontSize: 11 }}><i className="bi bi-eye" /> View</button>
              <button className="cc-btn" style={{ fontSize: 11 }}><i className="bi bi-download" /> PDF</button>
              <button className="cc-btn" style={{ fontSize: 11 }}><i className="bi bi-filetype-csv" /> CSV</button>
            </div>
          </div>
        ))}
      </div>
      <div style={{ padding: "16px", background: "var(--cc-bg-secondary)", border: "1px solid var(--cc-border)", borderRadius: "var(--cc-radius)", fontSize: 12, color: "var(--cc-text-muted)", textAlign: "center" }}>
        <i className="bi bi-info-circle" style={{ marginRight: 6 }} />
        Report generation will be connected to FastAPI backend in Phase 2
      </div>
    </div>
  );
}
