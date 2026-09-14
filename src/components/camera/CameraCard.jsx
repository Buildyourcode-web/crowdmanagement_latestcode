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

export default function CameraCard({ camera, onSelect, onToggleFrs, onFullscreen, onToggleCrowdAI, onConfigureROI, onRequestReassign, onRequestZoneSwitch, onDelete }) {
  const [streamError, setStreamError] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const [isTabVisible, setIsTabVisible] = useState(
    typeof document !== "undefined" ? document.visibilityState === "visible" : true
  );
  const [visibilityTick, setVisibilityTick] = useState(() => Date.now());

  if (!camera) return null;

  const isFrs = Boolean(camera.is_frs_camera || camera.isFRS || camera.is_frs || camera.camera_type === "FRS");
  const isRunning = (camera.status === "online" || camera.status === "running") && Boolean(camera.stream_url) && !["stopped", "disconnected", "offline"].includes(camera.status);

  const purposes = (Array.isArray(camera.ai_purposes) && camera.ai_purposes.length > 0)
    ? camera.ai_purposes
    : [isFrs ? "FRS" : "ENTRY"];
  const hasExit = purposes.includes("EXIT") && !purposes.includes("ENTRY");
  const hasZone = purposes.includes("ZONE") && !purposes.includes("ENTRY") && !purposes.includes("EXIT");
  const hasEntry = !isFrs && !hasExit && !hasZone;

  // Listen for tab switching to prevent background frame accumulation in browser TCP buffer
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        setIsTabVisible(true);
        setVisibilityTick(Date.now());
        setStreamError(false);
      } else {
        setIsTabVisible(false);
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, []);

  useEffect(() => {
    setStreamError(false);
  }, [camera?.id, camera?.stream_url, camera?.status]);

  useEffect(() => {
    if (streamError && isRunning && isTabVisible) {
      const timer = setTimeout(() => {
        setStreamError(false);
        setRetryCount((c) => c + 1);
        setVisibilityTick(Date.now());
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [streamError, isRunning, isTabVisible]);

  return (
    <div
      className="cc-card"
      style={{
        padding: 0,
        overflow: "hidden",
        cursor: "pointer",
        border: isFrs
          ? "1px solid rgba(56, 189, 248, 0.3)"
          : hasExit
          ? "1px solid rgba(248, 81, 73, 0.25)"
          : hasZone
          ? "1px solid rgba(88, 166, 255, 0.25)"
          : "1px solid rgba(63, 185, 80, 0.25)",
      }}
      onClick={() => onFullscreen ? onFullscreen(camera) : onSelect?.(camera)}
    >
      {isRunning && !streamError && isTabVisible ? (
        <div className="cc-camera-placeholder" style={{ position: "relative", overflow: "hidden", background: "#000", height: 180 }}>
          <img
            key={`${retryCount}_${visibilityTick}`}
            src={camera.stream_url.startsWith("http") ? `${camera.stream_url}?t=${visibilityTick}` : `${BACKEND}${camera.stream_url}?t=${visibilityTick}`}
            alt={`Stream ${camera.id}`}
            style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
            onError={() => setStreamError(true)}
          />
          <div style={{ position: "absolute", top: 6, left: 8, fontFamily: "var(--cc-font-mono)", fontSize: 8, color: isFrs ? "rgba(56,189,248,0.95)" : (hasExit ? "rgba(248,81,73,0.95)" : (hasZone ? "rgba(88,166,255,0.95)" : "rgba(63,185,80,0.95)")), background: "rgba(0,0,0,0.65)", padding: "2px 6px", borderRadius: 2 }}>
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
            {onDelete && (
              <button
                className="cc-btn"
                title="Remove Camera"
                style={{
                  padding: "2px 6px",
                  fontSize: 10,
                  background: "rgba(220, 38, 38, 0.8)",
                  border: "1px solid rgba(248, 81, 73, 0.5)",
                  color: "#fff",
                  cursor: "pointer",
                  borderRadius: 2,
                }}
                onClick={(e) => {
                  e.stopPropagation();
                  if (window.confirm(`Are you sure you want to remove camera "${camera.name || camera.label || camera.id}"?`)) {
                    onDelete(camera);
                  }
                }}
              >
                <i className="bi bi-trash3-fill" />
              </button>
            )}
          </div>
          <div
            style={{
              position: "absolute",
              bottom: 6,
              right: 8,
              fontSize: 9,
              color: isFrs ? "var(--cc-accent)" : (hasExit ? "#f85149" : (hasZone ? "#58a6ff" : "var(--cc-green)")),
              fontWeight: 800,
              letterSpacing: "0.08em",
              background: "rgba(0,0,0,0.75)",
              padding: "2px 6px",
              borderRadius: 2,
              border: isFrs
                ? "1px solid rgba(56,189,248,0.4)"
                : hasExit
                ? "1px solid rgba(248,81,73,0.4)"
                : hasZone
                ? "1px solid rgba(88,166,255,0.4)"
                : "1px solid rgba(63,185,80,0.4)",
            }}
          >
            {isFrs ? "FRS BIOMETRIC AI" : (hasExit ? "EXIT CORRIDOR AI" : (hasZone ? "ZONE DENSITY AI" : "ENTRY GATE AI"))}
          </div>
        </div>
      ) : isRunning && streamError ? (
        <div className="cc-camera-placeholder" style={{ position: "relative", overflow: "hidden", background: "#080c14", height: 180, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 6 }}>
          <div style={{ position: "absolute", top: 6, left: 8, fontFamily: "var(--cc-font-mono)", fontSize: 8, color: isFrs ? "rgba(56,189,248,0.95)" : "rgba(63,185,80,0.95)", background: "rgba(0,0,0,0.65)", padding: "2px 6px", borderRadius: 2 }}>
            {camera.id}
          </div>
          <div style={{ position: "absolute", top: 6, right: 8, display: "flex", gap: 4, alignItems: "center", zIndex: 3 }}>
            {onDelete && (
              <button
                className="cc-btn"
                title="Remove Camera"
                style={{
                  padding: "2px 6px",
                  fontSize: 10,
                  background: "rgba(220, 38, 38, 0.8)",
                  border: "1px solid rgba(248, 81, 73, 0.5)",
                  color: "#fff",
                  cursor: "pointer",
                  borderRadius: 2,
                }}
                onClick={(e) => {
                  e.stopPropagation();
                  if (window.confirm(`Are you sure you want to remove camera "${camera.name || camera.label || camera.id}"?`)) {
                    onDelete(camera);
                  }
                }}
              >
                <i className="bi bi-trash3-fill" />
              </button>
            )}
          </div>
          <div className="cc-camera-static" />
          <i className="bi bi-camera-video-fill" style={{ fontSize: 26, color: isFrs ? "var(--cc-accent)" : "var(--cc-green)", zIndex: 1, opacity: 0.8 }} />
          <span style={{ fontSize: 11, color: "var(--cc-text-primary)", fontWeight: 700, zIndex: 1 }}>
            RTSP Live Stream
          </span>
          <span style={{ fontSize: 9, color: "var(--cc-text-muted)", zIndex: 1, textAlign: "center", padding: "0 12px" }}>
            Stream unavailable or offline
          </span>
          <div style={{ display: "flex", gap: 8, marginTop: 4, zIndex: 2 }}>
            <button
              className="cc-btn cc-btn-primary"
              style={{ fontSize: 10, padding: "3px 10px" }}
              onClick={(e) => {
                e.stopPropagation();
                setStreamError(false);
                setRetryCount((c) => c + 1);
              }}
            >
              <i className="bi bi-arrow-clockwise" /> Reconnect
            </button>
            {onDelete && (
              <button
                className="cc-btn"
                style={{ fontSize: 10, padding: "3px 10px", background: "rgba(220,38,38,0.2)", border: "1px solid rgba(248,81,73,0.4)", color: "var(--cc-red)" }}
                onClick={(e) => {
                  e.stopPropagation();
                  if (window.confirm(`Remove camera "${camera.name || camera.label || camera.id}"?`)) {
                    onDelete(camera);
                  }
                }}
              >
                <i className="bi bi-trash3" /> Remove
              </button>
            )}
          </div>
        </div>
      ) : (
        <CameraPlaceholder status={camera.status || "stopped"} id={camera.id} isFrs={isFrs} />
      )}

      <div style={{ padding: "10px 12px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
          <span style={{ fontFamily: "var(--cc-font-mono)", fontSize: 12, fontWeight: 700, color: isFrs ? "var(--cc-accent)" : (hasExit ? "#f85149" : (hasZone ? "#58a6ff" : "#3fb950")) }}>
            {camera.id}
          </span>
          <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <span
              style={{
                fontSize: 9,
                fontWeight: 800,
                padding: "2px 7px",
                background: isFrs ? "var(--cc-blue-dim)" : (hasExit ? "rgba(248,81,73,0.15)" : (hasZone ? "rgba(88,166,255,0.15)" : "rgba(63,185,80,0.15)")),
                border: isFrs ? "1px solid var(--cc-blue-border)" : (hasExit ? "1px solid rgba(248,81,73,0.3)" : (hasZone ? "1px solid rgba(88,166,255,0.3)" : "1px solid rgba(63,185,80,0.3)")),
                borderRadius: "var(--cc-radius-sm)",
                color: isFrs ? "var(--cc-accent)" : (hasExit ? "#f85149" : (hasZone ? "#58a6ff" : "#3fb950")),
              }}
            >
              {isFrs ? "FRS BIOMETRIC" : (hasExit ? "EXIT GATE" : (hasZone ? `ZONE DENSITY (${camera.zone_code || 'ZONE-A'})` : "ENTRY GATE"))}
            </span>
            <StatusBadge
              status={isRunning ? "online" : "stopped"}
              label={isRunning ? "RUNNING" : "STOPPED"}
            />
          </div>
        </div>
        <div style={{ fontSize: 11, color: "var(--cc-text-secondary)", marginBottom: 8, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {camera.label || camera.name}
        </div>

        {/* Clean, Purpose-Tailored Metrics Display */}
        {isFrs ? (
          <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 8, padding: "8px 0", borderTop: "1px solid rgba(255,255,255,0.06)", alignItems: "center" }}>
            <div>
              <div className="cc-label" style={{ color: "var(--cc-accent)", fontSize: 11, fontWeight: 700 }}>Face Detections / Scans</div>
              <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 20, fontWeight: 800, color: "#fff" }}>
                {(camera.detections_count ?? 0).toLocaleString()}
              </div>
            </div>
            <div>
              <div className="cc-label" style={{ fontSize: 10 }}>Engine Mode</div>
              <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 11, fontWeight: 700, color: isRunning ? "var(--cc-green)" : "var(--cc-text-muted)", marginTop: 2 }}>
                {isRunning ? "● MATCHING ACTIVE" : "OFFLINE"}
              </div>
            </div>
          </div>
        ) : hasExit ? (
          <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 8, padding: "8px 0", borderTop: "1px solid rgba(255,255,255,0.06)", alignItems: "center" }}>
            <div>
              <div className="cc-label" style={{ color: "#f85149", fontSize: 11, fontWeight: 700 }}>↓ Exit Count (Today)</div>
              <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 20, fontWeight: 800, color: "#f85149" }}>
                {(camera.out_count ?? 0).toLocaleString()}
              </div>
            </div>
            <div>
              <div className="cc-label" style={{ fontSize: 10 }}>Queue Status</div>
              {(() => {
                const qStatus = camera.queue_movement_status || "MOVING";
                const qConfig = {
                  STOPPED: { label: "● STOPPED", color: "#f85149", bg: "rgba(248,81,73,0.15)", border: "#f85149" },
                  SLOW: { label: "● SLOW", color: "#d29922", bg: "rgba(210,153,34,0.15)", border: "#d29922" },
                  EMPTY: { label: "● EMPTY", color: "var(--cc-text-muted)", bg: "rgba(255,255,255,0.05)", border: "var(--cc-border)" },
                  MOVING: { label: "● MOVING", color: "#3fb950", bg: "rgba(63,185,80,0.15)", border: "#3fb950" },
                }[qStatus] || { label: "● MOVING", color: "#3fb950", bg: "rgba(63,185,80,0.15)", border: "#3fb950" };
                return (
                  <div style={{
                    display: "inline-block",
                    fontSize: 10.5,
                    fontWeight: 800,
                    fontFamily: "var(--cc-font-mono)",
                    padding: "3px 8px",
                    borderRadius: 4,
                    background: qConfig.bg,
                    color: qConfig.color,
                    border: `1px solid ${qConfig.border}`,
                    marginTop: 2,
                  }}>
                    {qConfig.label}
                  </div>
                );
              })()}
            </div>
          </div>
        ) : hasZone ? (
          <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 8, padding: "8px 0", borderTop: "1px solid rgba(255,255,255,0.06)", alignItems: "center" }}>
            <div>
              <div className="cc-label" style={{ color: "#58a6ff", fontSize: 11, fontWeight: 700 }}>
                People in {camera.zone_code || "Zone"}
              </div>
              <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 20, fontWeight: 800, color: "var(--cc-text-primary)" }}>
                {(camera.people_count ?? 0).toLocaleString()} <span style={{ fontSize: 11, color: "var(--cc-text-muted)", fontWeight: 400 }}>people</span>
              </div>
            </div>
            <div>
              <div className="cc-label" style={{ fontSize: 10 }}>Zone Status</div>
              {(() => {
                const count = camera.people_count ?? 0;
                const cap = camera.capacity || 100;
                const ratio = cap > 0 ? (count / cap) : 0;
                const zConfig = ratio >= 0.8
                  ? { label: "● CRITICAL", color: "#f85149", bg: "rgba(248,81,73,0.15)", border: "#f85149" }
                  : ratio >= 0.5
                  ? { label: "● MODERATE", color: "#d29922", bg: "rgba(210,153,34,0.15)", border: "#d29922" }
                  : { label: "● NORMAL", color: "#3fb950", bg: "rgba(63,185,80,0.15)", border: "#3fb950" };
                return (
                  <div style={{
                    display: "inline-block",
                    fontSize: 10.5,
                    fontWeight: 800,
                    fontFamily: "var(--cc-font-mono)",
                    padding: "3px 8px",
                    borderRadius: 4,
                    background: zConfig.bg,
                    color: zConfig.color,
                    border: `1px solid ${zConfig.border}`,
                    marginTop: 2,
                  }}>
                    {zConfig.label}
                  </div>
                );
              })()}
            </div>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 8, padding: "8px 0", borderTop: "1px solid rgba(255,255,255,0.06)", alignItems: "center" }}>
            <div>
              <div className="cc-label" style={{ color: "#3fb950", fontSize: 11, fontWeight: 700 }}>↑ Entry Count (Today)</div>
              <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 20, fontWeight: 800, color: "#3fb950" }}>
                {(camera.in_count ?? 0).toLocaleString()}
              </div>
            </div>
            <div>
              <div className="cc-label" style={{ fontSize: 10 }}>Queue Status</div>
              {(() => {
                const qStatus = camera.queue_movement_status || "MOVING";
                const qConfig = {
                  STOPPED: { label: "● STOPPED", color: "#f85149", bg: "rgba(248,81,73,0.15)", border: "#f85149" },
                  SLOW: { label: "● SLOW", color: "#d29922", bg: "rgba(210,153,34,0.15)", border: "#d29922" },
                  EMPTY: { label: "● EMPTY", color: "var(--cc-text-muted)", bg: "rgba(255,255,255,0.05)", border: "var(--cc-border)" },
                  MOVING: { label: "● MOVING", color: "#3fb950", bg: "rgba(63,185,80,0.15)", border: "#3fb950" },
                }[qStatus] || { label: "● MOVING", color: "#3fb950", bg: "rgba(63,185,80,0.15)", border: "#3fb950" };
                return (
                  <div style={{
                    display: "inline-block",
                    fontSize: 10.5,
                    fontWeight: 800,
                    fontFamily: "var(--cc-font-mono)",
                    padding: "3px 8px",
                    borderRadius: 4,
                    background: qConfig.bg,
                    color: qConfig.color,
                    border: `1px solid ${qConfig.border}`,
                    marginTop: 2,
                  }}>
                    {qConfig.label}
                  </div>
                );
              })()}
            </div>
          </div>
        )}

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
            {onDelete && (
              <button
                className="cc-btn"
                style={{
                  fontSize: 9,
                  padding: "2px 7px",
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  color: "var(--cc-red)",
                  borderColor: "rgba(248, 81, 73, 0.35)",
                  background: "rgba(248, 81, 73, 0.08)",
                }}
                onClick={(e) => {
                  e.stopPropagation();
                  if (window.confirm(`Remove camera "${camera.name || camera.label || camera.id}"? This will stop the live feed and delete the camera.`)) {
                    onDelete(camera);
                  }
                }}
                title="Remove this camera"
              >
                <i className="bi bi-trash3-fill" /> Remove
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
