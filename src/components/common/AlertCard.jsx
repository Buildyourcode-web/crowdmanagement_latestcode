// AlertCard — shows a single alert with severity styling and action buttons
import StatusBadge from "./StatusBadge.jsx";

const SEVERITY_ICONS = {
  critical: "bi-exclamation-octagon-fill",
  high: "bi-exclamation-triangle-fill",
  medium: "bi-exclamation-circle-fill",
  low: "bi-info-circle-fill",
};

export default function AlertCard({ alert, onAcknowledge, onViewMap, onViewCamera, compact }) {
  if (!alert) return null;
  const icon = SEVERITY_ICONS[alert.severity] || "bi-exclamation-circle";

  return (
    <div
      className="cc-card"
      style={{
        borderLeft: `2px solid var(--cc-${alert.severity === "medium" ? "yellow" : alert.severity === "high" ? "orange" : alert.severity === "low" ? "green" : "red"})`,
        marginBottom: 0,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10, marginBottom: 8 }}>
        <i
          className={`bi ${icon}`}
          style={{
            color: alert.severity === "critical" ? "var(--cc-red)" : alert.severity === "high" ? "var(--cc-orange)" : alert.severity === "medium" ? "var(--cc-yellow)" : "var(--cc-green)",
            fontSize: 16,
            flexShrink: 0,
            marginTop: 1,
          }}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <StatusBadge status={alert.severity} />
            <span style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>{alert.type?.toUpperCase()}</span>
            {alert.acknowledged && (
              <span style={{ fontSize: 10, color: "var(--cc-green)", marginLeft: "auto" }}>
                <i className="bi bi-check2-circle" /> ACK
              </span>
            )}
          </div>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--cc-text-primary)", marginTop: 4, lineHeight: 1.3 }}>
            {alert.title}
          </div>
          {!compact && (
            <div style={{ fontSize: 11, color: "var(--cc-text-secondary)", marginTop: 3 }}>
              {alert.message}
            </div>
          )}
        </div>
      </div>

      {!compact && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 11, marginBottom: 8 }}>
            {alert.zone && (
              <div>
                <span className="cc-label" style={{ display: "block" }}>Zone</span>
                <span style={{ color: "var(--cc-text-primary)", fontWeight: 500 }}>{alert.zone}</span>
              </div>
            )}
            {alert.metric && (
              <div>
                <span className="cc-label" style={{ display: "block" }}>Metric</span>
                <span style={{ color: "var(--cc-text-primary)", fontFamily: "var(--cc-font-mono)", fontWeight: 500 }}>{alert.metric}</span>
              </div>
            )}
            {alert.prediction && (
              <div style={{ gridColumn: "1/-1" }}>
                <span className="cc-label" style={{ display: "block" }}>AI Prediction</span>
                <span style={{ color: "var(--cc-orange)", fontWeight: 600 }}>{alert.prediction}</span>
              </div>
            )}
            {alert.recommendedAction && (
              <div style={{ gridColumn: "1/-1" }}>
                <span className="cc-label" style={{ display: "block" }}>Recommended Action</span>
                <span style={{ color: "var(--cc-text-secondary)" }}>{alert.recommendedAction}</span>
              </div>
            )}
          </div>
          <hr className="cc-divider" style={{ margin: "8px 0" }} />
        </>
      )}

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <span style={{ fontSize: 10, color: "var(--cc-text-muted)", marginRight: "auto", alignSelf: "center" }}>
          {alert.detectedAt ? new Date(alert.detectedAt).toLocaleTimeString("en-IN", { hour12: false, timeZone: "Asia/Kolkata" }) : ""}
        </span>
        {!alert.acknowledged && onAcknowledge && (
          <button className="cc-btn" onClick={() => onAcknowledge(alert.id)}>
            <i className="bi bi-check-circle" /> Acknowledge
          </button>
        )}
        {onViewCamera && alert.camera && (
          <button className="cc-btn" onClick={() => onViewCamera(alert.camera)}>
            <i className="bi bi-camera-video" /> Camera
          </button>
        )}
        {onViewMap && (
          <button className="cc-btn" onClick={() => onViewMap(alert.zone)}>
            <i className="bi bi-map" /> Map
          </button>
        )}
      </div>
    </div>
  );
}
