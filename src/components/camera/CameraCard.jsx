import { useState, useEffect } from "react";
import StatusBadge from "../common/StatusBadge.jsx";
import { getBackendUrl } from "../../utils/urlConfig.js";

const BACKEND = getBackendUrl();

function CameraPlaceholder({ status, id, isFrs }) {
  const isInactive = status === "offline" || status === "stopped" || status === "disconnected";
  if (isInactive) {
    return (
      <div className="cc-camera-placeholder" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, height: 180, background: "#080c14" }}>
        <i className="bi bi-camera-video-off-fill" style={{ fontSize: 28, color: status === "offline" ? "var(--cc-red)" : "var(--cc-text-muted)", opacity: 0.6 }} />
        <span style={{ fontSize: 10, color: status === "offline" ? "var(--cc-red)" : "var(--cc-text-muted)", fontWeight: 700, letterSpacing: "0.06em" }}>
          {status === "offline" ? "OFFLINE" : "STOPPED / DISCONNECTED"}
        </span>
        <span style={{ fontSize: 9, color: "var(--cc-text-muted)", opacity: 0.7 }}>
          {isFrs ? "FRS Pipeline Stopped" : "Crowd Pipeline Stopped"}
        </span>
      </div>
    );
  }
  if (status === "degraded") {
    return (
      <div className="cc-camera-placeholder" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, height: 180 }}>
        <div className="cc-camera-static" />
        <i className="bi bi-exclamation-triangle-fill" style={{ fontSize: 20, color: "var(--cc-yellow)", zIndex: 1 }} />
        <span style={{ fontSize: 10, color: "var(--cc-yellow)", fontWeight: 600, letterSpacing: "0.06em", zIndex: 1 }}>DEGRADED</span>
      </div>
    );
  }
  return (
    <div className="cc-camera-placeholder" style={{ height: 180 }}>
      <div className="cc-camera-static" />
      <div className="cc-camera-scan" />
      <div className="cc-camera-corner tl" />
      <div className="cc-camera-corner tr" />
      <div className="cc-camera-corner bl" />
      <div className="cc-camera-corner br" />

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

export default function CameraCard({ camera, onSelect, onToggleFrs, onFullscreen, onToggleCrowdAI, onConfigureROI, onRequestReassign, onRequestZoneSwitch }) {
  const [streamError, setStreamError] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  if (!camera) return null;

  const isFrs = Boolean(camera.is_frs_camera || camera.isFRS || camera.is_frs || camera.camera_type === "FRS");
  const isRunning = (camera.status === "online" || camera.status === "running") && Boolean(camera.stream_url) && !["stopped", "disconnected", "offline"].includes(camera.status);

  useEffect(() => {
    setStreamError(false);
  }, [camera?.id, camera?.stream_url, camera?.status]);

  useEffect(() => {
    if (streamError && isRunning) {
      const timer = setTimeout(() => {
        setStreamError(false);
        setRetryCount((c) => c + 1);
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [streamError, isRunning]);

  return (
    <div
      className="cc-card"
      style={{
        padding: 0,
        overflow: "hidden",
        cursor: "pointer",
        border: isFrs ? "1px solid rgba(56, 189, 248, 0.3)" : "1px solid rgba(63, 185, 80, 0.25)",
      }}
      onClick={() => onFullscreen ? onFullscreen(camera) : onSelect?.(camera)}
    >
      {isRunning && !streamError ? (
        <div className="cc-camera-placeholder" style={{ position: "relative", overflow: "hidden", background: "#000", height: 180 }}>
          <img
            key={retryCount}
            src={camera.stream_url.startsWith("http") ? `${camera.stream_url}?t=${retryCount}` : `${BACKEND}${camera.stream_url}?t=${retryCount}`}
            alt={`Stream ${camera.id}`}
            style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
            onError={() => setStreamError(true)}
          />
          <div style={{ position: "absolute", top: 6, left: 8, fontFamily: "var(--cc-font-mono)", fontSize: 8, color: isFrs ? "rgba(56,189,248,0.95)" : "rgba(63,185,80,0.95)", background: "rgba(0,0,0,0.65)", padding: "2px 6px", borderRadius: 2 }}>
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
          <div
            style={{
              position: "absolute",
              bottom: 6,
              right: 8,
              fontSize: 9,
              color: isFrs ? "var(--cc-accent)" : "var(--cc-green)",
              fontWeight: 800,
              letterSpacing: "0.08em",
              background: "rgba(0,0,0,0.75)",
              padding: "2px 6px",
              borderRadius: 2,
              border: isFrs ? "1px solid rgba(56,189,248,0.4)" : "1px solid rgba(63,185,80,0.4)",
            }}
          >
            {isFrs ? "FRS BIOMETRIC AI" : "CROWD SURVEILLANCE"}
          </div>
        </div>
      ) : isRunning && streamError ? (
        <div className="cc-camera-placeholder" style={{ position: "relative", overflow: "hidden", background: "#080c14", height: 180, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 6 }}>
          <div className="cc-camera-static" />
          <i className="bi bi-camera-video-fill" style={{ fontSize: 26, color: isFrs ? "var(--cc-accent)" : "var(--cc-green)", zIndex: 1, opacity: 0.8 }} />
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
        </div>
      ) : (
        <CameraPlaceholder status={camera.status || "stopped"} id={camera.id} isFrs={isFrs} />
      )}

      <div style={{ padding: "8px 10px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
          <span style={{ fontFamily: "var(--cc-font-mono)", fontSize: 11, fontWeight: 700, color: isFrs ? "var(--cc-accent)" : "var(--cc-text-primary)" }}>
            {camera.id}
          </span>
          <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <span
              style={{
                fontSize: 9,
                fontWeight: 800,
                padding: "1px 6px",
                background: isFrs ? "var(--cc-blue-dim)" : "rgba(63, 185, 80, 0.15)",
                border: isFrs ? "1px solid var(--cc-blue-border)" : "1px solid rgba(63, 185, 80, 0.3)",
                borderRadius: "var(--cc-radius-sm)",
                color: isFrs ? "var(--cc-accent)" : "var(--cc-green)",
              }}
            >
              {isFrs ? "FRS" : "CROWD"}
            </span>
            <StatusBadge
              status={isRunning ? "online" : "stopped"}
              label={isRunning ? "RUNNING" : "STOPPED"}
            />
          </div>
        </div>
        <div style={{ fontSize: 11, color: "var(--cc-text-secondary)", marginBottom: 4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {camera.label || camera.name}
        </div>

        {!isFrs && (() => {
          const purposes = (Array.isArray(camera.ai_purposes) && camera.ai_purposes.length > 0)
            ? camera.ai_purposes
            : ["ENTRY_EXIT"];
          const metaMap = {
            ENTRY: { label: "Entry Gate (IN Only)", color: "#3fb950", bg: "rgba(63, 185, 80, 0.12)", icon: "bi-box-arrow-in-right" },
            EXIT: { label: "Exit Gate (OUT Only)", color: "#f85149", bg: "rgba(248, 81, 73, 0.12)", icon: "bi-box-arrow-right" },
            ENTRY_EXIT: { label: "Two-Way Gate (IN & OUT)", color: "#bc8cff", bg: "rgba(188, 140, 255, 0.12)", icon: "bi-arrow-left-right" },
            ZONE: { label: "Zone Density", color: "#58a6ff", bg: "rgba(88, 166, 255, 0.12)", icon: "bi-bounding-box" },
            QUEUE: { label: "Queue Management", color: "#d29922", bg: "rgba(210, 153, 34, 0.12)", icon: "bi-people" },
          };
          return (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 6 }}>
              {purposes.map((purp) => {
                const meta = metaMap[purp] || { label: purp, color: "var(--cc-green)", bg: "rgba(63, 185, 80, 0.12)", icon: "bi-people-fill" };
                return (
                  <span
                    key={purp}
                    style={{
                      fontSize: 9,
                      fontWeight: 700,
                      padding: "2px 7px",
                      borderRadius: 3,
                      color: meta.color,
                      background: meta.bg,
                      border: `1px solid ${meta.color}40`,
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                    }}
                  >
                    <i className={`bi ${meta.icon}`} /> {meta.label}
                  </span>
                );
              })}
            </div>
          );
        })()}

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 4, fontSize: 10 }}>
          <div>
            <div className="cc-label">FPS</div>
            <div style={{ fontFamily: "var(--cc-font-mono)", color: isRunning ? (camera.fps < 15 ? "var(--cc-yellow)" : "var(--cc-text-primary)") : "var(--cc-text-muted)" }}>
              {isRunning ? (camera.fps ?? "25") : "0"}
            </div>
          </div>
          <div>
            <div className="cc-label">{isFrs ? "Scans" : "Latency"}</div>
            <div style={{ fontFamily: "var(--cc-font-mono)", color: isRunning ? (isFrs ? "var(--cc-accent)" : "var(--cc-text-primary)") : "var(--cc-text-muted)" }}>
              {isRunning
                ? (isFrs ? (camera.detections_count ?? 0) : ((camera.latency_ms ?? camera.latency) ? `${camera.latency_ms ?? camera.latency}ms` : "—"))
                : "—"}
            </div>
          </div>
          <div>
            <div className="cc-label">People</div>
            <div style={{ fontFamily: "var(--cc-font-mono)", color: isRunning ? "var(--cc-blue)" : "var(--cc-text-muted)" }}>
              {isRunning ? (camera.people_count ?? camera.peopleCount ?? 0).toLocaleString() : "0"}
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
              background: isRunning
                ? (isFrs ? "var(--cc-blue-dim)" : "rgba(63, 185, 80, 0.15)")
                : "transparent",
              color: isRunning
                ? (isFrs ? "var(--cc-accent)" : "var(--cc-green)")
                : "var(--cc-text-muted)",
              borderColor: isRunning
                ? (isFrs ? "var(--cc-blue-border)" : "rgba(63, 185, 80, 0.3)")
                : "var(--cc-border)",
            }}
            onClick={(e) => {
              e.stopPropagation();
              if (isFrs) {
                onToggleFrs?.(camera, !isRunning);
              } else {
                onToggleCrowdAI ? onToggleCrowdAI(camera, !isRunning) : onToggleFrs?.(camera, !isRunning);
              }
            }}
            title={
              isFrs
                ? (isRunning ? "Stop FRS detection on this camera" : "Start FRS detection on this camera")
                : (isRunning ? "Stop Crowd AI model on this camera" : "Start YOLO11x Human Detection AI on this camera")
            }
          >
            <i className={`bi ${isFrs ? (isRunning ? "bi-person-check-fill" : "bi-person-bounding-box") : (isRunning ? "bi-check-circle-fill" : "bi-cpu-fill")}`} />
            {isFrs
              ? (isRunning ? "FRS ACTIVE" : "ENABLE FRS")
              : (isRunning ? "CROWD AI ACTIVE" : "ENABLE AI MODEL")}
          </button>
          <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
            {!isFrs && (
              <>
                <button
                  className="cc-btn"
                  style={{ fontSize: 9, padding: "2px 6px", display: "flex", alignItems: "center", gap: 3, color: "#bc8cff", borderColor: "rgba(188, 140, 255, 0.4)" }}
                  onClick={(e) => {
                    e.stopPropagation();
                    onConfigureROI?.(camera);
                  }}
                  title="Configure Counting Line / Queue / Crowd ROI"
                >
                  <i className="bi bi-vector-pen" /> Set ROI
                </button>
                <button
                  className="cc-btn"
                  style={{ fontSize: 9, padding: "2px 6px", display: "flex", alignItems: "center", gap: 3, color: "#e3b341", borderColor: "rgba(227, 179, 65, 0.4)" }}
                  onClick={(e) => {
                    e.stopPropagation();
                    onRequestReassign?.(camera);
                  }}
                  title="Switch Camera Purpose (Entry/Exit, Queue, Zone)"
                >
                  <i className="bi bi-arrow-repeat" /> Switch Purpose
                </button>
              </>
            )}
            <button
              className="cc-btn"
              style={{ fontSize: 9, padding: "2px 6px", display: "flex", alignItems: "center", gap: 3 }}
              onClick={(e) => {
                e.stopPropagation();
                onFullscreen ? onFullscreen(camera) : onSelect?.(camera);
              }}
              title="Open Full-Screen Live View"
              disabled={!isRunning}
            >
              <i className="bi bi-arrows-fullscreen" /> Full Screen
            </button>
            <button
              className="cc-btn"
              style={{
                fontSize: 9,
                padding: "2px 7px",
                display: "flex",
                alignItems: "center",
                gap: 4,
                color: "var(--cc-text-muted)",
                border: "1px solid var(--cc-border)",
                background: "rgba(255,255,255,0.03)",
                cursor: onRequestZoneSwitch ? "pointer" : "default",
              }}
              onClick={(e) => {
                e.stopPropagation();
                onRequestZoneSwitch?.(camera);
              }}
              title="Click to Switch Camera Zone (Zone A, B, C, D)"
            >
              <i className="bi bi-geo-alt-fill" style={{ color: "#58a6ff" }} />
              {camera.zone_code || camera.zone || "Zone A"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
