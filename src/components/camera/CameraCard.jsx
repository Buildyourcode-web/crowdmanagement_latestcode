// CameraCard — individual CCTV card with live video streaming and AI overlays
import { useState } from "react";
import StatusBadge from "../common/StatusBadge.jsx";

function CameraPlaceholder({ status, id, isFrs }) {
  if (status === "offline") {
    return (
      <div className="cc-camera-placeholder" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8 }}>
        <i className="bi bi-camera-video-off-fill" style={{ fontSize: 28, color: "var(--cc-red)", opacity: 0.6 }} />
        <span style={{ fontSize: 10, color: "var(--cc-red)", fontWeight: 600, letterSpacing: "0.06em" }}>OFFLINE</span>
      </div>
    );
  }
  if (status === "degraded") {
    return (
      <div className="cc-camera-placeholder" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8 }}>
        <div className="cc-camera-static" />
        <i className="bi bi-exclamation-triangle-fill" style={{ fontSize: 20, color: "var(--cc-yellow)", zIndex: 1 }} />
        <span style={{ fontSize: 10, color: "var(--cc-yellow)", fontWeight: 600, letterSpacing: "0.06em", zIndex: 1 }}>DEGRADED</span>
      </div>
    );
  }
  return (
    <div className="cc-camera-placeholder">
      <div className="cc-camera-static" />
      <div className="cc-camera-scan" />
      <div className="cc-camera-corner tl" />
      <div className="cc-camera-corner tr" />
      <div className="cc-camera-corner bl" />
      <div className="cc-camera-corner br" />

      {/* Simulated detection boxes */}
      {[...Array(3)].map((_, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            border: isFrs ? "1px solid rgba(56, 189, 248, 0.6)" : "1px solid rgba(88, 166, 255, 0.4)",
            borderRadius: 1,
            width: 14 + i * 8,
            height: 20 + i * 10,
            top: `${20 + i * 22}%`,
            left: `${15 + i * 25}%`,
            opacity: 0.7,
          }}
        />
      ))}

      {/* Overlay info */}
      <div style={{ position: "absolute", top: 6, left: 8, fontFamily: "var(--cc-font-mono)", fontSize: 8, color: isFrs ? "var(--cc-accent)" : "rgba(88,166,255,0.7)" }}>
        {id}
      </div>
      <div style={{ position: "absolute", top: 6, right: 8, fontSize: 8, color: "rgba(63,185,80,0.8)", fontWeight: 700, letterSpacing: "0.06em" }}>
        ● LIVE
      </div>
      <div
        style={{
          position: "absolute",
          bottom: 6,
          right: 8,
          fontSize: 8,
          fontWeight: 800,
          letterSpacing: "0.08em",
          background: "rgba(0,0,0,0.65)",
          color: isFrs ? "var(--cc-accent)" : "var(--cc-green)",
          border: isFrs ? "1px solid rgba(56, 189, 248, 0.4)" : "1px solid rgba(63, 185, 80, 0.4)",
          padding: "1px 5px",
          borderRadius: 2,
        }}
      >
        {isFrs ? "FRS AI" : "CROWD AI"}
      </div>
      <div style={{ position: "absolute", bottom: 6, left: 8, fontFamily: "var(--cc-font-mono)", fontSize: 8, color: "rgba(255,255,255,0.3)" }}>
        {new Date().toLocaleTimeString("en-IN", { hour12: false })}
      </div>
    </div>
  );
}

export default function CameraCard({ camera, onSelect, onToggleFrs, onFullscreen }) {
  const [streamError, setStreamError] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  if (!camera) return null;

  const isFrs = Boolean(camera.is_frs_camera || camera.isFRS || camera.is_frs);

  return (
    <div
      className="cc-card"
      style={{
        padding: 0,
        overflow: "hidden",
        cursor: "pointer",
        border: isFrs ? "1px solid rgba(56, 189, 248, 0.3)" : undefined,
      }}
      onClick={() => onFullscreen ? onFullscreen(camera) : onSelect?.(camera)}
    >
      {camera.stream_url && !streamError ? (
        <div className="cc-camera-placeholder" style={{ position: "relative", overflow: "hidden", background: "#000", height: 180 }}>
          <img
            key={retryCount}
            src={camera.stream_url.startsWith("http") ? `${camera.stream_url}?t=${retryCount}` : `http://${window.location.hostname}:8000${camera.stream_url}?t=${retryCount}`}
            alt={`Stream ${camera.id}`}
            style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
            onError={() => setStreamError(true)}
          />
          <div style={{ position: "absolute", top: 6, left: 8, fontFamily: "var(--cc-font-mono)", fontSize: 8, color: "rgba(88,166,255,0.9)", background: "rgba(0,0,0,0.6)", padding: "2px 6px", borderRadius: 2 }}>
            {camera.id}
          </div>
          <div style={{ position: "absolute", top: 6, right: 8, display: "flex", gap: 4, alignItems: "center" }}>
            <div style={{ fontSize: 8, color: "var(--cc-green)", fontWeight: 700, letterSpacing: "0.06em", background: "rgba(0,0,0,0.6)", padding: "2px 6px", borderRadius: 2 }}>
              ● LIVE STREAM
            </div>
            <button
              className="cc-btn"
              title="Full Screen Live View"
              style={{
                padding: "2px 6px",
                fontSize: 10,
                background: "rgba(0,0,0,0.75)",
                border: "1px solid rgba(255,255,255,0.3)",
                color: "#fff",
                cursor: "pointer",
                borderRadius: 2,
              }}
              onClick={(e) => {
                e.stopPropagation();
                onFullscreen ? onFullscreen(camera) : onSelect?.(camera);
              }}
            >
              <i className="bi bi-arrows-fullscreen" />
            </button>
          </div>
          {isFrs && (
            <div style={{ position: "absolute", bottom: 6, right: 8, fontSize: 9, color: "var(--cc-accent)", fontWeight: 800, letterSpacing: "0.08em", background: "rgba(0,0,0,0.75)", padding: "2px 6px", borderRadius: 2, border: "1px solid rgba(56,189,248,0.4)" }}>
              FRS BIOMETRIC AI
            </div>
          )}
        </div>
      ) : camera.stream_url && streamError ? (
        <div className="cc-camera-placeholder" style={{ position: "relative", overflow: "hidden", background: "#080c14", height: 180, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 6 }}>
          <div className="cc-camera-static" />
          <i className="bi bi-camera-video-fill" style={{ fontSize: 26, color: "var(--cc-accent)", zIndex: 1, opacity: 0.8 }} />
          <span style={{ fontSize: 11, color: "var(--cc-text-primary)", fontWeight: 700, zIndex: 1 }}>
            RTSP Live Stream
          </span>
          <span style={{ fontSize: 9, color: "var(--cc-text-muted)", zIndex: 1, textAlign: "center", padding: "0 12px" }}>
            Connecting / awaiting camera frames...
          </span>
          <button
            className="cc-btn cc-btn-primary"
            style={{ fontSize: 10, padding: "3px 10px", marginTop: 4, zIndex: 2 }}
            onClick={(e) => {
              e.stopPropagation();
              setStreamError(false);
              setRetryCount((c) => c + 1);
            }}
          >
            <i className="bi bi-arrow-clockwise" /> Reconnect
          </button>
          {isFrs && (
            <div style={{ position: "absolute", bottom: 6, right: 8, fontSize: 8, color: "var(--cc-accent)", fontWeight: 800, background: "rgba(0,0,0,0.7)", padding: "1px 5px", borderRadius: 2 }}>
              FRS AI
            </div>
          )}
        </div>
      ) : (
        <CameraPlaceholder status={camera.status} id={camera.id} isFrs={isFrs} />
      )}

      <div style={{ padding: "8px 10px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
          <span style={{ fontFamily: "var(--cc-font-mono)", fontSize: 11, fontWeight: 700, color: isFrs ? "var(--cc-accent)" : "var(--cc-text-primary)" }}>
            {camera.id}
          </span>
          <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
            {isFrs && (
              <span
                style={{
                  fontSize: 9,
                  fontWeight: 800,
                  padding: "1px 6px",
                  background: "var(--cc-blue-dim)",
                  border: "1px solid var(--cc-blue-border)",
                  borderRadius: "var(--cc-radius-sm)",
                  color: "var(--cc-accent)",
                }}
              >
                FRS
              </span>
            )}
            <StatusBadge status={camera.status} />
          </div>
        </div>
        <div style={{ fontSize: 11, color: "var(--cc-text-secondary)", marginBottom: 6, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {camera.label}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 4, fontSize: 10 }}>
          <div>
            <div className="cc-label">FPS</div>
            <div style={{ fontFamily: "var(--cc-font-mono)", color: camera.fps < 15 ? "var(--cc-yellow)" : "var(--cc-text-primary)" }}>
              {camera.fps ?? "25"}
            </div>
          </div>
          <div>
            <div className="cc-label">{isFrs ? "Scans" : "Latency"}</div>
            <div style={{ fontFamily: "var(--cc-font-mono)", color: isFrs ? "var(--cc-accent)" : "var(--cc-text-primary)" }}>
              {isFrs ? (camera.detections_count ?? 0) : ((camera.latency_ms ?? camera.latency) ? `${camera.latency_ms ?? camera.latency}ms` : "—")}
            </div>
          </div>
          <div>
            <div className="cc-label">People</div>
            <div style={{ fontFamily: "var(--cc-font-mono)", color: "var(--cc-blue)" }}>
              {camera.status === "online" ? (camera.people_count ?? camera.peopleCount ?? 0).toLocaleString() : "—"}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 8, paddingTop: 6, borderTop: "1px solid var(--cc-border)" }}>
          <button
            className="cc-btn"
            style={{
              fontSize: 9,
              padding: "2px 8px",
              display: "flex",
              alignItems: "center",
              gap: 4,
              fontWeight: 700,
              background: isFrs ? "var(--cc-blue-dim)" : "transparent",
              color: isFrs ? "var(--cc-accent)" : "var(--cc-text-muted)",
              borderColor: isFrs ? "var(--cc-blue-border)" : "var(--cc-border)",
            }}
            onClick={(e) => {
              e.stopPropagation();
              onToggleFrs?.(camera, !isFrs);
            }}
            title={isFrs ? "Disable FRS AI detection on this camera" : "Enable FRS AI detection on this camera"}
          >
            <i className={`bi ${isFrs ? "bi-person-check-fill" : "bi-person-bounding-box"}`} />
            {isFrs ? "FRS ACTIVE" : "ENABLE FRS"}
          </button>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <button
              className="cc-btn"
              style={{ fontSize: 9, padding: "2px 6px", display: "flex", alignItems: "center", gap: 3 }}
              onClick={(e) => {
                e.stopPropagation();
                onFullscreen ? onFullscreen(camera) : onSelect?.(camera);
              }}
              title="Open Full-Screen Live View"
            >
              <i className="bi bi-arrows-fullscreen" /> Full Screen
            </button>
            <span style={{ fontSize: 9, color: "var(--cc-text-muted)" }}>
              {camera.zone_code || camera.zone}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
