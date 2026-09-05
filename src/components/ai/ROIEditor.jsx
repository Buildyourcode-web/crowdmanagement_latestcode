import React, { useState, useEffect, useRef, useMemo } from "react";
import {
  getCameraROIConfig,
  validateCameraROI,
  saveCameraROI,
  deleteCameraROI,
  getCameraSnapshotUrl,
} from "../../services/aiService";

const ROI_TYPE_META = {
  CROWD_ROI: { label: "Crowd ROI Polygon", color: "#3fb950", isLine: false, hint: "Polygon (min 3 points) defining where crowd density is measured" },
  QUEUE_ROI: { label: "Queue Area Polygon", color: "#d29922", isLine: false, hint: "Polygon defining waiting queue zone" },
  ENTRY_LINE: { label: "Queue Entry Line", color: "#58a6ff", isLine: true, direction: "IN", hint: "Line with 2 points marking where people enter queue" },
  EXIT_LINE: { label: "Queue Exit Line", color: "#f85149", isLine: true, direction: "OUT", hint: "Line with 2 points marking where people exit queue" },
  COUNTING_LINE: { label: "Counting Line", color: "#bc8cff", isLine: true, direction: "BOTH", hint: "Line with 2 points for bi-directional counting" },
  DIRECTION_LINE: { label: "Direction Line", color: "#388bfd", isLine: true, direction: "IN", hint: "Line vector indicating expected queue flow" },
  EXCLUSION_ZONE: { label: "Exclusion Zone", color: "#8b949e", isLine: false, hint: "Ignored zone (roads, trees, structures)" },
};

export default function ROIEditor({ camera, profileId, profileName, onClose, onSaved }) {
  const containerRef = useRef(null);
  const imageRef = useRef(null);

  const [snapshotUrl, setSnapshotUrl] = useState("");
  const [loadingSnapshot, setLoadingSnapshot] = useState(true);
  const [snapshotError, setSnapshotError] = useState(null);

  const [rois, setRois] = useState([]);
  const [readiness, setReadiness] = useState(null);

  // Available tools for this profile
  const availableTools = useMemo(() => {
    if (profileId === "CROWD_STANDARD" || profileId === "CROWD_HIGH_DENSITY") {
      return ["CROWD_ROI", "EXCLUSION_ZONE", "COUNTING_LINE"];
    }
    if (profileId === "QUEUE_STANDARD") {
      return ["QUEUE_ROI", "ENTRY_LINE", "EXIT_LINE", "DIRECTION_LINE", "EXCLUSION_ZONE"];
    }
    if (profileId === "VIDEO_SAFETY") {
      return ["EXCLUSION_ZONE", "COUNTING_LINE"];
    }
    return [];
  }, [profileId]);

  const [activeTool, setActiveTool] = useState(availableTools[0] || "CROWD_ROI");
  const [currentPoints, setCurrentPoints] = useState([]); // [{x: 0..1, y: 0..1}]
  const [history, setHistory] = useState([]);
  const [redoStack, setRedoStack] = useState([]);
  const [draggingIdx, setDraggingIdx] = useState(null);

  const [roiName, setRoiName] = useState("");
  const [direction, setDirection] = useState("BOTH");

  const [validationStatus, setValidationStatus] = useState(null); // { valid: bool, message: str }
  const [saving, setSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  // Stream status guard
  const isStreamVerified =
    camera?.enabled &&
    camera?.stream_status &&
    camera.stream_status.toUpperCase() !== "NOT_TESTED" &&
    camera.stream_status.toUpperCase() !== "OFFLINE";

  const streamWarningMessage = useMemo(() => {
    if (!camera?.enabled) return "Camera Offline — Camera is currently disabled";
    const status = (camera?.stream_status || "").toUpperCase();
    if (status === "NOT_TESTED") return "Camera stream not verified — Please perform RTSP test first";
    if (status === "OFFLINE") return "Camera Offline — ROI editor unavailable";
    return null;
  }, [camera]);

  // Load existing configurations and snapshot
  const refreshData = async () => {
    if (!camera?.id) return;
    try {
      const summary = await getCameraROIConfig(camera.id, profileId);
      setRois(summary.configurations || []);
      setReadiness(summary.readiness_by_profile?.[profileId] || null);
    } catch (err) {
      console.error("Failed to load ROI configurations:", err);
    }
  };

  useEffect(() => {
    refreshData();
    if (isStreamVerified) {
      setLoadingSnapshot(true);
      const url = getCameraSnapshotUrl(camera.id);
      setSnapshotUrl(url);
    } else {
      setLoadingSnapshot(false);
      setSnapshotError(streamWarningMessage);
    }
  }, [camera?.id, isStreamVerified]);

  // Update default name when tool changes
  useEffect(() => {
    const meta = ROI_TYPE_META[activeTool];
    setRoiName(`${meta?.label || activeTool} ${rois.filter((r) => r.roi_type === activeTool).length + 1}`);
    if (meta?.direction) setDirection(meta.direction);
    setCurrentPoints([]);
  }, [activeTool, rois]);

  // Canvas coordinate transformation
  const getNormalizedCoords = (e) => {
    if (!imageRef.current) return { x: 0, y: 0 };
    const rect = imageRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    return { x: Number(x.toFixed(4)), y: Number(y.toFixed(4)) };
  };

  const handleMouseMove = (e) => {
    const coords = getNormalizedCoords(e);
    setMousePos(coords);

    if (draggingIdx !== null && imageRef.current) {
      const updated = [...currentPoints];
      updated[draggingIdx] = coords;
      setCurrentPoints(updated);
    }
  };

  const handleCanvasClick = (e) => {
    if (!isStreamVerified || draggingIdx !== null) return;
    const coords = getNormalizedCoords(e);
    const meta = ROI_TYPE_META[activeTool];

    // Check if line tool (exactly 2 points)
    if (meta?.isLine) {
      if (currentPoints.length === 0) {
        pushHistory([...currentPoints]);
        setCurrentPoints([coords]);
      } else if (currentPoints.length === 1) {
        pushHistory([...currentPoints]);
        setCurrentPoints([...currentPoints, coords]);
        setValidationStatus(null);
      }
      return;
    }

    // Polygon tool (min 3 points)
    if (currentPoints.length >= 3) {
      // Check if clicked close to start point (close polygon)
      const first = currentPoints[0];
      const dist = Math.hypot(coords.x - first.x, coords.y - first.y);
      if (dist < 0.03) {
        setValidationStatus(null);
        return;
      }
    }

    pushHistory([...currentPoints]);
    setCurrentPoints([...currentPoints, coords]);
    setValidationStatus(null);
  };

  const pushHistory = (pts) => {
    setHistory((prev) => [...prev, pts]);
    setRedoStack([]);
  };

  const handleUndo = () => {
    if (history.length === 0) return;
    const prev = history[history.length - 1];
    setRedoStack((r) => [currentPoints, ...r]);
    setCurrentPoints(prev);
    setHistory((h) => h.slice(0, -1));
  };

  const handleRedo = () => {
    if (redoStack.length === 0) return;
    const next = redoStack[0];
    setHistory((h) => [...h, currentPoints]);
    setCurrentPoints(next);
    setRedoStack((r) => r.slice(1));
  };

  const handleReset = () => {
    setCurrentPoints([]);
    setHistory([]);
    setRedoStack([]);
    setValidationStatus(null);
    setStatusMessage("");
  };

  // Dry-run validation
  const handleValidate = async () => {
    const meta = ROI_TYPE_META[activeTool];
    let geom = {};
    if (meta?.isLine) {
      if (currentPoints.length !== 2) {
        setValidationStatus({ valid: false, message: "Line requires exactly 2 endpoints" });
        return;
      }
      geom = { start: currentPoints[0], end: currentPoints[1], direction };
    } else {
      if (currentPoints.length < 3) {
        setValidationStatus({ valid: false, message: "Polygon requires at least 3 vertices" });
        return;
      }
      geom = { points: currentPoints };
    }

    try {
      const res = await validateCameraROI(camera.id, {
        profile_id: profileId,
        roi_type: activeTool,
        geometry_json: geom,
      });
      if (res.valid) {
        setValidationStatus({ valid: true, message: "✓ Geometry is structurally valid and normalized (0.0 to 1.0)" });
      } else {
        setValidationStatus({ valid: false, message: `✕ ${res.error_message || "Validation failed"}` });
      }
    } catch (err) {
      const msg = err.response?.data?.detail?.message || err.message;
      setValidationStatus({ valid: false, message: `✕ ${msg}` });
    }
  };

  // Save ROI
  const handleSave = async () => {
    const meta = ROI_TYPE_META[activeTool];
    let geom = {};
    if (meta?.isLine) {
      if (currentPoints.length !== 2) {
        setValidationStatus({ valid: false, message: "Line requires exactly 2 endpoints" });
        return;
      }
      geom = { start: currentPoints[0], end: currentPoints[1], direction };
    } else {
      if (currentPoints.length < 3) {
        setValidationStatus({ valid: false, message: "Polygon requires at least 3 vertices" });
        return;
      }
      geom = { points: currentPoints };
    }

    setSaving(true);
    setStatusMessage("");
    try {
      await saveCameraROI(camera.id, {
        profile_id: profileId,
        roi_type: activeTool,
        name: roiName || `${meta?.label} ${rois.length + 1}`,
        geometry_json: geom,
        normalized: true,
        enabled: true,
      });

      setStatusMessage("Configuration saved successfully. AI inference has not been started.");
      setCurrentPoints([]);
      setHistory([]);
      setRedoStack([]);
      setValidationStatus(null);
      await refreshData();
      if (onSaved) onSaved();
    } catch (err) {
      const msg = err.response?.data?.detail?.message || err.message;
      setValidationStatus({ valid: false, message: `✕ ${msg}` });
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteROI = async (roiId) => {
    if (!window.confirm("Are you sure you want to delete this geometry configuration?")) return;
    try {
      await deleteCameraROI(camera.id, roiId);
      await refreshData();
      if (onSaved) onSaved();
    } catch (err) {
      alert("Failed to delete ROI: " + (err.response?.data?.detail?.message || err.message));
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(10, 12, 16, 0.88)",
        zIndex: 1000,
        display: "flex",
        flexDirection: "column",
        backdropFilter: "blur(4px)",
      }}
      onMouseUp={() => setDraggingIdx(null)}
    >
      {/* Top Header */}
      <div
        style={{
          height: 56,
          background: "var(--cc-bg-secondary)",
          borderBottom: "1px solid var(--cc-border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 20px",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ fontWeight: 800, fontSize: 16, color: "var(--cc-text-primary)" }}>
            Visual ROI & Counting-Line Configuration
          </div>
          <span style={{ fontSize: 12, color: "var(--cc-text-muted)" }}>•</span>
          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--cc-accent)", fontFamily: "var(--cc-font-mono)" }}>
            {camera?.camera_code} ({camera?.name})
          </span>
          <span style={{ fontSize: 12, color: "var(--cc-text-muted)" }}>•</span>
          <span style={{ fontSize: 12, fontWeight: 700, padding: "2px 8px", borderRadius: 4, background: "rgba(88,166,255,0.15)", color: "var(--cc-accent)" }}>
            {profileName || profileId}
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {readiness && (
            <div
              style={{
                fontSize: 11,
                fontWeight: 700,
                padding: "4px 10px",
                borderRadius: 4,
                background: readiness.is_ready ? "rgba(63,185,80,0.15)" : "rgba(210,153,34,0.15)",
                color: readiness.is_ready ? "var(--cc-green)" : "var(--cc-yellow)",
                border: `1px solid ${readiness.is_ready ? "rgba(63,185,80,0.3)" : "rgba(210,153,34,0.3)"}`,
              }}
            >
              CONFIGURATION: {readiness.status.replace(/_/g, " ")}
            </div>
          )}
          <button
            onClick={onClose}
            className="cc-btn cc-btn-secondary"
            style={{ padding: "5px 12px", fontSize: 12 }}
          >
            ✕ Close
          </button>
        </div>
      </div>

      {/* Main Content: Left Toolbar/Panel & Right Canvas */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Left Controls Panel */}
        <div
          style={{
            width: 320,
            background: "var(--cc-bg-secondary)",
            borderRight: "1px solid var(--cc-border)",
            display: "flex",
            flexDirection: "column",
            overflowY: "auto",
            padding: 16,
            gap: 16,
          }}
        >
          {/* Tool Selector */}
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--cc-text-muted)", textTransform: "uppercase", marginBottom: 8 }}>
              Select Geometry Tool
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {availableTools.map((tool) => {
                const meta = ROI_TYPE_META[tool];
                const isSelected = activeTool === tool;
                return (
                  <button
                    key={tool}
                    onClick={() => {
                      setActiveTool(tool);
                      handleReset();
                    }}
                    style={{
                      padding: "8px 12px",
                      borderRadius: 6,
                      background: isSelected ? "var(--cc-bg-root)" : "transparent",
                      border: `1px solid ${isSelected ? meta.color : "var(--cc-border)"}`,
                      color: isSelected ? "var(--cc-text-primary)" : "var(--cc-text-muted)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      cursor: "pointer",
                      textAlign: "left",
                      fontSize: 12,
                      fontWeight: isSelected ? 700 : 500,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <div style={{ width: 10, height: 10, borderRadius: meta.isLine ? 2 : "50%", background: meta.color }} />
                      <span>{meta.label}</span>
                    </div>
                    <span style={{ fontSize: 10, color: "var(--cc-text-muted)", fontFamily: "var(--cc-font-mono)" }}>
                      {meta.isLine ? "LINE" : "POLYGON"}
                    </span>
                  </button>
                );
              })}
            </div>
            <div style={{ fontSize: 11, color: "var(--cc-text-muted)", marginTop: 8, fontStyle: "italic" }}>
              {ROI_TYPE_META[activeTool]?.hint}
            </div>
          </div>

          {/* Geometry Properties */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div>
              <label style={{ fontSize: 11, fontWeight: 700, color: "var(--cc-text-muted)", display: "block", marginBottom: 4 }}>
                Geometry Label
              </label>
              <input
                type="text"
                value={roiName}
                onChange={(e) => setRoiName(e.target.value)}
                className="cc-input"
                style={{ width: "100%", padding: "6px 8px", fontSize: 12 }}
                placeholder="e.g. Main Courtyard Polygon"
              />
            </div>

            {ROI_TYPE_META[activeTool]?.isLine && (
              <div>
                <label style={{ fontSize: 11, fontWeight: 700, color: "var(--cc-text-muted)", display: "block", marginBottom: 4 }}>
                  Counting Direction
                </label>
                <select
                  value={direction}
                  onChange={(e) => setDirection(e.target.value)}
                  className="cc-input"
                  style={{ width: "100%", padding: "6px 8px", fontSize: 12 }}
                >
                  <option value="IN">IN (Entry Direction)</option>
                  <option value="OUT">OUT (Exit Direction)</option>
                  <option value="BOTH">BOTH (Bi-directional)</option>
                </select>
              </div>
            )}
          </div>

          {/* Drawing Status & Actions */}
          <div style={{ background: "var(--cc-bg-root)", padding: 12, borderRadius: 6, border: "1px solid var(--cc-border)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "var(--cc-text-muted)" }}>DRAFT VERTICES</span>
              <span style={{ fontSize: 11, color: "var(--cc-text-muted)", fontFamily: "var(--cc-font-mono)" }}>
                {currentPoints.length} {ROI_TYPE_META[activeTool]?.isLine ? "/ 2" : "points"}
              </span>
            </div>

            <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
              <button
                className="cc-btn cc-btn-secondary"
                style={{ flex: 1, padding: "4px 6px", fontSize: 11 }}
                onClick={handleUndo}
                disabled={history.length === 0}
              >
                Undo
              </button>
              <button
                className="cc-btn cc-btn-secondary"
                style={{ flex: 1, padding: "4px 6px", fontSize: 11 }}
                onClick={handleRedo}
                disabled={redoStack.length === 0}
              >
                Redo
              </button>
              <button
                className="cc-btn cc-btn-secondary"
                style={{ flex: 1, padding: "4px 6px", fontSize: 11 }}
                onClick={handleReset}
                disabled={currentPoints.length === 0}
              >
                Reset
              </button>
            </div>

            {/* Coordinates table preview */}
            {currentPoints.length > 0 && (
              <div style={{ maxHeight: 90, overflowY: "auto", fontSize: 10, fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-muted)" }}>
                {currentPoints.map((pt, i) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}>
                    <span>P{i + 1}:</span>
                    <span>x: {pt.x.toFixed(3)}, y: {pt.y.toFixed(3)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Validation Feedback */}
          {validationStatus && (
            <div
              style={{
                padding: "8px 10px",
                borderRadius: 4,
                fontSize: 11,
                fontWeight: 600,
                background: validationStatus.valid ? "rgba(63,185,80,0.15)" : "rgba(248,81,73,0.15)",
                color: validationStatus.valid ? "var(--cc-green)" : "var(--cc-red)",
                border: `1px solid ${validationStatus.valid ? "rgba(63,185,80,0.3)" : "rgba(248,81,73,0.3)"}`,
              }}
            >
              {validationStatus.message}
            </div>
          )}

          {/* Success notice */}
          {statusMessage && (
            <div
              style={{
                padding: "8px 10px",
                borderRadius: 4,
                fontSize: 11,
                fontWeight: 600,
                background: "rgba(63,185,80,0.15)",
                color: "var(--cc-green)",
                border: "1px solid rgba(63,185,80,0.3)",
              }}
            >
              ✓ {statusMessage}
            </div>
          )}

          {/* Primary Action Buttons */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: "auto" }}>
            <button
              className="cc-btn cc-btn-secondary"
              style={{ padding: "8px", fontSize: 12 }}
              onClick={handleValidate}
              disabled={currentPoints.length === 0 || !isStreamVerified}
            >
              Validate Geometry
            </button>
            <button
              className="cc-btn cc-btn-primary"
              style={{ padding: "10px", fontSize: 12, fontWeight: 700 }}
              onClick={handleSave}
              disabled={currentPoints.length === 0 || saving || !isStreamVerified}
            >
              {saving ? "Saving Configuration..." : "Save Configuration"}
            </button>
          </div>

          {/* Saved Geometries list */}
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--cc-text-muted)", textTransform: "uppercase", marginBottom: 6 }}>
              Saved Configurations ({rois.length})
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 150, overflowY: "auto" }}>
              {rois.map((roi) => {
                const meta = ROI_TYPE_META[roi.roi_type] || { label: roi.roi_type, color: "#58a6ff" };
                return (
                  <div
                    key={roi.id}
                    style={{
                      padding: "6px 8px",
                      background: "var(--cc-bg-root)",
                      border: "1px solid var(--cc-border)",
                      borderRadius: 4,
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      fontSize: 11,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 6, overflow: "hidden" }}>
                      <div style={{ width: 8, height: 8, borderRadius: "50%", background: meta.color, flexShrink: 0 }} />
                      <span style={{ fontWeight: 600, color: "var(--cc-text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {roi.name}
                      </span>
                      <span style={{ fontSize: 9, color: "var(--cc-text-muted)", fontFamily: "var(--cc-font-mono)" }}>
                        (v{roi.version})
                      </span>
                    </div>
                    <button
                      onClick={() => handleDeleteROI(roi.id)}
                      style={{
                        background: "none",
                        border: "none",
                        color: "var(--cc-red)",
                        cursor: "pointer",
                        fontSize: 11,
                        padding: "0 4px",
                      }}
                      title="Delete ROI"
                    >
                      ✕
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Right Canvas / Image Viewport */}
        <div
          ref={containerRef}
          style={{
            flex: 1,
            background: "#0d1117",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            position: "relative",
            overflow: "hidden",
            userSelect: "none",
          }}
          onMouseMove={handleMouseMove}
        >
          {/* Stream Warning / Offline Banner */}
          {streamWarningMessage && (
            <div
              style={{
                position: "absolute",
                top: 20,
                zIndex: 50,
                background: "rgba(248,81,73,0.9)",
                color: "#fff",
                padding: "10px 20px",
                borderRadius: 6,
                fontWeight: 700,
                fontSize: 13,
                boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
              }}
            >
              ⚠ {streamWarningMessage}
            </div>
          )}

          {/* Coordinate Readout Badge */}
          <div
            style={{
              position: "absolute",
              bottom: 12,
              left: 12,
              zIndex: 40,
              background: "rgba(10,12,16,0.8)",
              padding: "4px 8px",
              borderRadius: 4,
              border: "1px solid var(--cc-border)",
              fontFamily: "var(--cc-font-mono)",
              fontSize: 11,
              color: "var(--cc-text-muted)",
            }}
          >
            NORM: X: {mousePos.x.toFixed(4)} | Y: {mousePos.y.toFixed(4)}
          </div>

          {/* Non-inference disclaimer */}
          <div
            style={{
              position: "absolute",
              bottom: 12,
              right: 12,
              zIndex: 40,
              background: "rgba(10,12,16,0.8)",
              padding: "4px 10px",
              borderRadius: 4,
              border: "1px solid rgba(88,166,255,0.3)",
              fontSize: 10,
              color: "var(--cc-accent)",
              fontWeight: 600,
            }}
          >
            Spatial geometry configuration only. No inference is running.
          </div>

          {/* Snapshot Container with Interactive SVG */}
          {loadingSnapshot ? (
            <div style={{ color: "var(--cc-text-muted)", fontSize: 13 }}>
              Loading verified camera snapshot...
            </div>
          ) : snapshotError ? (
            <div style={{ textAlign: "center", color: "var(--cc-text-muted)", padding: 40 }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>📷</div>
              <div style={{ fontWeight: 600, color: "var(--cc-red)", marginBottom: 4 }}>
                {snapshotError}
              </div>
              <div style={{ fontSize: 12 }}>
                Camera must pass RTSP stream testing before visual geometry can be configured.
              </div>
            </div>
          ) : (
            <div
              style={{
                position: "relative",
                maxWidth: "96%",
                maxHeight: "92%",
                display: "inline-block",
                cursor: currentPoints.length > 0 ? "crosshair" : "default",
              }}
              onClick={handleCanvasClick}
            >
              <img
                ref={imageRef}
                src={snapshotUrl}
                alt="Camera Frame"
                style={{
                  display: "block",
                  maxWidth: "100%",
                  maxHeight: "82vh",
                  borderRadius: 4,
                  border: "1px solid var(--cc-border)",
                }}
                onError={() => {
                  setLoadingSnapshot(false);
                  setSnapshotError("Failed to fetch verified frame from camera stream");
                }}
                onLoad={() => setLoadingSnapshot(false)}
              />

              {/* Interactive SVG Overlay */}
              <svg
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  height: "100%",
                  pointerEvents: "auto",
                }}
                viewBox="0 0 1 1"
                preserveAspectRatio="none"
              >
                {/* 1. Render Saved Polygons */}
                {rois
                  .filter((r) => r.geometry_json?.points)
                  .map((r) => {
                    const meta = ROI_TYPE_META[r.roi_type] || { color: "#58a6ff" };
                    const ptsStr = r.geometry_json.points.map((p) => `${p.x},${p.y}`).join(" ");
                    return (
                      <g key={r.id}>
                        <polygon
                          points={ptsStr}
                          fill={meta.color}
                          fillOpacity={r.roi_type === "EXCLUSION_ZONE" ? 0.35 : 0.22}
                          stroke={meta.color}
                          strokeWidth={0.003}
                          strokeDasharray={r.roi_type === "EXCLUSION_ZONE" ? "0.01 0.005" : "none"}
                        />
                        {r.geometry_json.points[0] && (
                          <text
                            x={r.geometry_json.points[0].x}
                            y={Math.max(0.02, r.geometry_json.points[0].y - 0.01)}
                            fill={meta.color}
                            fontSize={0.022}
                            fontWeight="bold"
                            style={{ userSelect: "none" }}
                          >
                            {r.name}
                          </text>
                        )}
                      </g>
                    );
                  })}

                {/* 2. Render Saved Lines */}
                {rois
                  .filter((r) => r.geometry_json?.start && r.geometry_json?.end)
                  .map((r) => {
                    const meta = ROI_TYPE_META[r.roi_type] || { color: "#bc8cff" };
                    const { start, end, direction } = r.geometry_json;
                    const midX = (start.x + end.x) / 2;
                    const midY = (start.y + end.y) / 2;
                    return (
                      <g key={r.id}>
                        <line
                          x1={start.x}
                          y1={start.y}
                          x2={end.x}
                          y2={end.y}
                          stroke={meta.color}
                          strokeWidth={0.004}
                        />
                        <circle cx={start.x} cy={start.y} r={0.006} fill={meta.color} />
                        <circle cx={end.x} cy={end.y} r={0.006} fill={meta.color} />
                        <text
                          x={midX}
                          y={Math.max(0.02, midY - 0.01)}
                          fill={meta.color}
                          fontSize={0.02}
                          fontWeight="bold"
                          style={{ userSelect: "none" }}
                        >
                          {r.name} ({direction || "BOTH"})
                        </text>
                      </g>
                    );
                  })}

                {/* 3. Render Currently Active Draft Geometry */}
                {currentPoints.length > 0 && (
                  <g>
                    {/* Draft Polygon fill if >= 3 points */}
                    {!ROI_TYPE_META[activeTool]?.isLine && currentPoints.length >= 3 && (
                      <polygon
                        points={currentPoints.map((p) => `${p.x},${p.y}`).join(" ")}
                        fill={ROI_TYPE_META[activeTool]?.color || "#3fb950"}
                        fillOpacity={0.25}
                        stroke={ROI_TYPE_META[activeTool]?.color || "#3fb950"}
                        strokeWidth={0.003}
                      />
                    )}

                    {/* Draft Lines connecting points */}
                    {currentPoints.map((pt, i) => {
                      if (i === 0) return null;
                      const prev = currentPoints[i - 1];
                      return (
                        <line
                          key={i}
                          x1={prev.x}
                          y1={prev.y}
                          x2={pt.x}
                          y2={pt.y}
                          stroke={ROI_TYPE_META[activeTool]?.color || "#58a6ff"}
                          strokeWidth={0.003}
                          strokeDasharray="0.008 0.004"
                        />
                      );
                    })}

                    {/* Draggable Vertex Handles */}
                    {currentPoints.map((pt, i) => (
                      <circle
                        key={i}
                        cx={pt.x}
                        cy={pt.y}
                        r={0.008}
                        fill="#ffffff"
                        stroke={ROI_TYPE_META[activeTool]?.color || "#58a6ff"}
                        strokeWidth={0.003}
                        style={{ cursor: "grab" }}
                        onMouseDown={(e) => {
                          e.stopPropagation();
                          setDraggingIdx(i);
                        }}
                      />
                    ))}
                  </g>
                )}
              </svg>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
