// ActionCenter — AI decision-support panel (reads from store, calls real API on ack)
import { useNavigate } from "react-router-dom";
import { useAlertStore } from "../../store/useAlertStore.js";
import { acknowledgeAlert as apiAcknowledge } from "../../services/alertService.js";

const TYPE_LABELS = { crowd: "Crowd", frs: "FRS", medical: "Medical", camera: "Camera", traffic: "Traffic", security: "Security" };

function ActionItem({ alert, onAck }) {
  const navigate = useNavigate();
  const sevColor = alert.severity === "critical" ? "var(--cc-red)" : alert.severity === "high" ? "var(--cc-orange)" : alert.severity === "medium" ? "var(--cc-yellow)" : "var(--cc-green)";
  const sevBg = alert.severity === "critical" ? "var(--cc-red-dim)" : alert.severity === "high" ? "var(--cc-orange-dim)" : "var(--cc-yellow-dim)";
  const sevBorder = alert.severity === "critical" ? "var(--cc-red-border)" : alert.severity === "high" ? "var(--cc-orange-border)" : "var(--cc-yellow-border)";

  const alertType = alert.type || alert.alert_type || "";
  const alertZone = alert.zone || alert.zone_code || "";
  const alertCamera = alert.camera || alert.camera_code || "";
  const alertTitle = alert.title || alert.message || "Alert";
  const alertMetric = alert.metric || alert.details || "";
  const alertPrediction = alert.prediction || "";
  const alertAction = alert.recommended_action || alert.recommendedAction || "";

  return (
    <div
      style={{
        background: "var(--cc-bg-panel)",
        border: `1px solid ${sevBorder}`,
        borderLeft: `3px solid ${sevColor}`,
        borderRadius: "var(--cc-radius)",
        padding: "12px 14px",
        marginBottom: 8,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        <span
          style={{
            fontSize: 9, fontWeight: 800, letterSpacing: "0.08em",
            padding: "2px 6px", borderRadius: 2,
            background: sevBg, color: sevColor, border: `1px solid ${sevBorder}`,
          }}
        >
          {alert.severity?.toUpperCase()}
        </span>
        <span style={{ fontSize: 9, color: "var(--cc-text-muted)", marginLeft: "auto" }}>
          {TYPE_LABELS[alertType] || alertType}
        </span>
      </div>

      <div style={{ fontSize: 12, fontWeight: 700, color: "var(--cc-text-primary)", lineHeight: 1.3, marginBottom: 8 }}>
        {alertTitle}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 11, marginBottom: 8 }}>
        {alertZone && (
          <div>
            <div className="cc-label">Location</div>
            <div style={{ fontWeight: 600, color: "var(--cc-text-primary)" }}>{alertZone}</div>
          </div>
        )}
        {alertMetric && (
          <div>
            <div className="cc-label">Status</div>
            <div style={{ fontWeight: 600, color: sevColor, fontFamily: "var(--cc-font-mono)", fontSize: 10 }}>{alertMetric}</div>
          </div>
        )}
      </div>

      {alertPrediction && (
        <div style={{ fontSize: 10, color: "var(--cc-orange)", marginBottom: 6, fontWeight: 600 }}>
          <i className="bi bi-clock-history" style={{ marginRight: 4 }} />
          AI Prediction: {alertPrediction}
        </div>
      )}

      {alertAction && (
        <div style={{ marginBottom: 10 }}>
          <div className="cc-label" style={{ marginBottom: 3 }}>Recommended Action</div>
          <div style={{ fontSize: 11, color: "var(--cc-text-secondary)", lineHeight: 1.4 }}>{alertAction}</div>
        </div>
      )}

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {!alert.acknowledged && (
          <button className="cc-btn cc-btn-primary" style={{ fontSize: 11, padding: "4px 10px" }} onClick={() => onAck(alert.id)}>
            <i className="bi bi-check-circle" /> Acknowledge
          </button>
        )}
        {alertZone && (
          <button className="cc-btn" style={{ fontSize: 11, padding: "4px 10px" }} onClick={() => navigate("/live-map")}>
            <i className="bi bi-map" /> Map
          </button>
        )}
        {alertCamera && (
          <button className="cc-btn" style={{ fontSize: 11, padding: "4px 10px" }} onClick={() => navigate("/cameras")}>
            <i className="bi bi-camera-video" /> Camera
          </button>
        )}
        {alert.acknowledged && (
          <span style={{ fontSize: 10, color: "var(--cc-green)", alignSelf: "center" }}>
            <i className="bi bi-check2-all" /> Acknowledged
          </span>
        )}
      </div>
    </div>
  );
}

export default function ActionCenter() {
  const { alerts, acknowledgeAlert } = useAlertStore();
  const activeAlerts = alerts
    .filter((a) => ["critical", "high"].includes(a.severity) && !a.acknowledged)
    .slice(0, 6);

  const handleAck = async (id) => {
    try {
      await apiAcknowledge(id);
    } catch (e) {
      console.warn("[ActionCenter] Acknowledge API failed, updating store only:", e);
    }
    acknowledgeAlert(id);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <div className="cc-section-header" style={{ flexShrink: 0 }}>
        <div>
          <div className="cc-section-title">AI Action Center</div>
          <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 1 }}>Prioritized decisions</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className="cc-live-dot critical" />
          <span style={{ fontSize: 10, color: "var(--cc-red)", fontWeight: 600 }}>
            {activeAlerts.length} ACTIVE
          </span>
        </div>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: "10px" }}>
        {activeAlerts.length === 0 ? (
          <div style={{ textAlign: "center", padding: "40px 20px", color: "var(--cc-green)", fontSize: 12 }}>
            <i className="bi bi-shield-check" style={{ fontSize: 28, display: "block", marginBottom: 8 }} />
            All clear — no critical alerts
          </div>
        ) : (
          activeAlerts.map((a) => (
            <ActionItem key={a.id} alert={a} onAck={handleAck} />
          ))
        )}
      </div>
    </div>
  );
}
