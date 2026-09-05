// FRS Camera Detail view (Section 12)
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import FRSSecurityBanner from "../components/frs/FRSSecurityBanner.jsx";
import FRSCandidateCard from "../components/frs/FRSCandidateCard.jsx";
import { getFRSCamera } from "../services/frsService.js";
import { LoadingState, ErrorState } from "../components/common/States.jsx";

export default function FRSCameraDetail() {
  const { cameraId } = useParams();
  const navigate = useNavigate();
  const [camera, setCamera] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    getFRSCamera(cameraId)
      .then(setCamera)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [cameraId]);

  if (loading) return <LoadingState message="Connecting to FRS camera telemetry..." />;
  if (error || !camera) return <ErrorState message={error || "FRS Camera not found"} onRetry={() => navigate("/frs")} />;

  const isOnline = camera.status === "online";

  return (
    <div className="cc-page">
      <FRSSecurityBanner />

      {/* Header */}
      <div className="cc-page-header">
        <div>
          <button className="cc-btn" onClick={() => navigate("/frs")} style={{ marginBottom: 6, padding: "3px 8px" }}>
            <i className="bi bi-arrow-left" /> Back to FRS Command
          </button>
          <div className="cc-page-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span>{camera.camera_code || camera.id} — {camera.name}</span>
            <span
              className="cc-badge"
              style={{
                fontSize: 9,
                background: isOnline ? "var(--cc-green-dim)" : "var(--cc-red-dim)",
                color: isOnline ? "var(--cc-green)" : "var(--cc-red)",
                borderColor: isOnline ? "var(--cc-green-border)" : "var(--cc-red-border)",
              }}
            >
              {(camera.status || "online").toUpperCase()}
            </span>
          </div>
          <div className="cc-page-subtitle">{camera.label || camera.location || camera.name} ({camera.zone_code || camera.zone || "ZONE-A"})</div>
        </div>

        <div style={{ display: "flex", gap: 6 }}>
          <button className="cc-btn" onClick={() => navigate("/live-map")}>
            <i className="bi bi-map-fill" /> View Location on Map
          </button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 14 }}>
        {/* Left: Simulated FRS Camera Live Preview */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
            <div className="cc-section-header">
              <div className="cc-section-title">
                <i className="bi bi-broadcast" style={{ marginRight: 6 }} />
                FRS Live Channel Stream
              </div>
              <span style={{ fontSize: 10, color: "var(--cc-green)", fontWeight: 700 }}>
                ● 24 FPS ACTIVE
              </span>
            </div>

            <div
              style={{
                aspectRatio: "16/9",
                background: "#050810",
                position: "relative",
                overflow: "hidden",
              }}
            >
              {/* Scanline */}
              <div className="cc-camera-static" />
              <div className="cc-camera-scan" />
              <div className="cc-camera-corner tl" />
              <div className="cc-camera-corner tr" />
              <div className="cc-camera-corner bl" />
              <div className="cc-camera-corner br" />

              {/* Bounding Boxes on Simulated Crowd Heads */}
              <div
                style={{
                  position: "absolute",
                  top: "28%",
                  left: "35%",
                  width: 44,
                  height: 54,
                  border: "1.5px solid #38bdf8",
                  borderRadius: 1,
                }}
              >
                <span style={{ position: "absolute", top: -14, left: 0, background: "#0284c7", color: "#fff", fontSize: 8, padding: "1px 3px", fontFamily: "monospace" }}>
                  SCAN: 94.2%
                </span>
              </div>

              <div
                style={{
                  position: "absolute",
                  top: "42%",
                  left: "58%",
                  width: 38,
                  height: 48,
                  border: "1px solid rgba(56, 189, 248, 0.4)",
                  borderRadius: 1,
                }}
              >
                <span style={{ position: "absolute", top: -12, left: 0, background: "rgba(15,23,42,0.8)", color: "#94a3b8", fontSize: 7, padding: "0 2px", fontFamily: "monospace" }}>
                  FACE [Q: 88]
                </span>
              </div>

              <div style={{ position: "absolute", top: 8, left: 10, fontFamily: "var(--cc-font-mono)", fontSize: 10, color: "rgba(88,166,255,0.8)" }}>
                {camera.id} — 1080p @ {camera.fps}fps
              </div>
              <div style={{ position: "absolute", bottom: 8, left: 10, fontFamily: "var(--cc-font-mono)", fontSize: 10, color: "rgba(255,255,255,0.4)" }}>
                {new Date().toLocaleTimeString("en-IN", { hour12: false })} IST
              </div>
              <div style={{ position: "absolute", bottom: 8, right: 10, fontSize: 10, color: "var(--cc-green)", fontWeight: 700 }}>
                AI PIPELINE: RUNNING ({camera.latency}ms)
              </div>
            </div>
          </div>

          {/* Telemetry Stats Grid */}
          <div className="cc-card">
            <div className="cc-section-title" style={{ marginBottom: 12 }}>FRS Performance Telemetry</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
              {[
                { label: "FRS STATUS", value: isOnline ? "ONLINE" : "OFFLINE", color: isOnline ? "var(--cc-green)" : "var(--cc-red)" },
                { label: "FPS", value: `${camera.fps} FPS`, color: "var(--cc-text-primary)" },
                { label: "LATENCY", value: `${camera.latency}ms`, color: "var(--cc-blue)" },
                { label: "FACE DETECTIONS", value: camera.faceDetections, color: "var(--cc-text-primary)" },
                { label: "POSSIBLE MATCHES", value: camera.possibleMatches, color: "var(--cc-orange)" },
                { label: "PENDING REVIEW", value: camera.pendingReview, color: "var(--cc-red)" },
              ].map((m) => (
                <div key={m.label} style={{ padding: "8px 10px", background: "var(--cc-bg-secondary)", borderRadius: "var(--cc-radius)" }}>
                  <div className="cc-label" style={{ marginBottom: 4 }}>{m.label}</div>
                  <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 16, fontWeight: 700, color: m.color }}>
                    {m.value}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Recent Events on This FRS Camera */}
        <div>
          <div className="cc-section-title" style={{ marginBottom: 10 }}>
            Recent FRS Detections on {camera.id}
          </div>

          {camera.events?.length === 0 ? (
            <div className="cc-card" style={{ padding: 24, textAlign: "center", color: "var(--cc-text-muted)", fontSize: 11 }}>
              No recent biometric match triggers on this channel.
            </div>
          ) : (
            camera.events.map((evt) => (
              <FRSCandidateCard
                key={evt.id}
                candidate={evt}
                onReviewUpdated={() => getFRSCamera(cameraId).then(setCamera)}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
