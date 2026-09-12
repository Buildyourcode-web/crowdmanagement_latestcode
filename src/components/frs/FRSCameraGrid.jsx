// Dedicated FRS Camera Grid (Section 11) — with live MJPEG stream support
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getBackendUrl } from "../../utils/urlConfig.js";

const BACKEND = getBackendUrl();

export default function FRSCameraGrid({ cameras = [] }) {
  const navigate = useNavigate();
  const [engineCams, setEngineCams] = useState([]);

  // Fetch live FRS engine cameras (RTSP workers)
  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(`${BACKEND}/api/v1/frs-engine/cameras`);
        if (res.ok) {
          const data = await res.json();
          setEngineCams(data);
        }
      } catch {
        // ignore
      }
    };
    load();
    const t = setInterval(load, 5000); // refresh every 5s
    return () => clearInterval(t);
  }, []);

  // Merge: engine cams at top, then DB cams (deduplicated)
  const allCams = [
    ...engineCams.map((c) => ({
      id: c.camera_id,
      name: c.name,
      status: c.status,
      location: "Live RTSP",
      zone: "FRS",
      fps: 25,
      faceDetections: c.detections_count,
      possibleMatches: 0,
      stream_url: c.stream_url,
      is_engine: true,
    })),
    ...cameras.filter((c) => !engineCams.some((e) => e.camera_id === c.id)),
  ];

  if (allCams.length === 0) {
    return (
      <div className="cc-card" style={{ textAlign: "center", padding: "48px 20px" }}>
        <i className="bi bi-camera-video-off" style={{ fontSize: 36, color: "var(--cc-text-muted)", display: "block", marginBottom: 8 }} />
        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--cc-text-primary)" }}>No FRS cameras active</div>
        <div style={{ fontSize: 11, color: "var(--cc-text-muted)", marginTop: 4 }}>
          Add an RTSP stream via <strong>Camera Wall → Add FRS Camera</strong>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10 }}>
      {allCams.map((cam) => {
        const isOnline = cam.status === "online" || cam.status === "starting";
        const displayId = cam.logical_id_frs || (cam.id?.endsWith("-FRS") ? cam.id : (cam.id?.startsWith("CAM-") ? `${cam.id}-FRS` : cam.id));
        return (
          <div
            key={cam.id}
            className="cc-card"
            style={{
              cursor: "pointer",
              borderLeft: `3px solid ${isOnline ? "var(--cc-green)" : "var(--cc-red)"}`,
              padding: 0,
              overflow: "hidden",
            }}
            onClick={() => cam.is_engine ? null : navigate(`/frs/cameras/${cam.id}`)}
          >
            {/* Live stream preview */}
            {cam.stream_url ? (
              <div style={{ position: "relative", background: "#000", height: 160, overflow: "hidden" }}>
                <img
                  src={`${BACKEND}${cam.stream_url}`}
                  alt={`FRS Live: ${displayId}`}
                  style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                  onError={(e) => {
                    e.target.style.display = "none";
                    e.target.nextSibling.style.display = "flex";
                  }}
                />
                {/* Fallback if stream not ready */}
                <div style={{ display: "none", position: "absolute", inset: 0, alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 6, background: "#111" }}>
                  <i className="bi bi-camera-video" style={{ fontSize: 28, color: "var(--cc-text-muted)" }} />
                  <span style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>Stream starting...</span>
                </div>
                {/* Live overlay badges */}
                <div style={{ position: "absolute", top: 6, left: 8, fontFamily: "var(--cc-font-mono)", fontSize: 8, color: "rgba(88,166,255,0.9)", background: "rgba(0,0,0,0.6)", padding: "1px 5px", borderRadius: 2 }}>
                  {displayId}
                </div>
                <div style={{ position: "absolute", top: 6, right: 8, fontSize: 8, color: "var(--cc-green)", fontWeight: 700, background: "rgba(0,0,0,0.6)", padding: "1px 5px", borderRadius: 2 }}>
                  ● LIVE FRS
                </div>
                {cam.faceDetections > 0 && (
                  <div style={{ position: "absolute", bottom: 6, right: 8, fontSize: 9, color: "var(--cc-orange)", fontWeight: 700, background: "rgba(0,0,0,0.7)", padding: "1px 6px", borderRadius: 2 }}>
                    {cam.faceDetections} detections
                  </div>
                )}
              </div>
            ) : (
              <div style={{ height: 120, background: "var(--cc-bg-panel)", display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 6 }}>
                <i className="bi bi-camera-video-fill" style={{ fontSize: 28, color: isOnline ? "var(--cc-green)" : "var(--cc-text-muted)", opacity: 0.6 }} />
                <span style={{ fontSize: 9, color: isOnline ? "var(--cc-green)" : "var(--cc-red)", fontWeight: 700, letterSpacing: "0.06em" }}>
                  {isOnline ? "● ONLINE" : "○ OFFLINE"}
                </span>
              </div>
            )}

            {/* Camera info */}
            <div style={{ padding: "8px 10px" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                <span style={{ fontFamily: "var(--cc-font-mono)", fontSize: 11, fontWeight: 700, color: "var(--cc-text-primary)" }}>
                  {displayId}
                </span>
                <span
                  className="cc-badge"
                  style={{
                    fontSize: 9,
                    background: isOnline ? "var(--cc-green-dim)" : "var(--cc-red-dim)",
                    color: isOnline ? "var(--cc-green)" : "var(--cc-red)",
                    borderColor: isOnline ? "var(--cc-green-border)" : "var(--cc-red-border)",
                  }}
                >
                  {(cam.status || "unknown").toUpperCase()}
                </span>
              </div>

              <div style={{ fontSize: 12, fontWeight: 600, color: "var(--cc-text-primary)", marginBottom: 2 }}>
                {cam.name}
              </div>
              <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginBottom: 8, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {cam.location} • {cam.zone}
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6, fontSize: 10, borderTop: "1px solid var(--cc-border-light)", paddingTop: 6 }}>
                <div>
                  <div className="cc-label">FPS</div>
                  <div style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 600, color: isOnline ? "var(--cc-text-primary)" : "var(--cc-text-muted)" }}>
                    {cam.fps > 0 ? `${cam.fps}` : "—"}
                  </div>
                </div>
                <div>
                  <div className="cc-label">Scans</div>
                  <div style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 600, color: "var(--cc-blue)" }}>
                    {cam.faceDetections ?? 0}
                  </div>
                </div>
                <div>
                  <div className="cc-label">Matches</div>
                  <div style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 700, color: (cam.possibleMatches ?? 0) > 0 ? "var(--cc-orange)" : "var(--cc-text-muted)" }}>
                    {cam.possibleMatches ?? 0}
                  </div>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
