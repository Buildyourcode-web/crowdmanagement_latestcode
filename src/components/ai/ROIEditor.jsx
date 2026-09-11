import React, { useState, useEffect, useRef, useMemo } from "react";
import {
  getCameraROIConfig,
  validateCameraROI,
  saveCameraROI,
  deleteCameraROI,
  getCameraSnapshotUrl,
  switchCameraAIMode,
} from "../../services/aiService";

const ROI_TYPE_META = {
  COUNTING_LINE: {
    label: "Entry / Exit Counting Line",
    color: "#bc8cff",
    isLine: true,
    direction: "BOTH",
    hint: "గేట్ వద్ద 2 పాయింట్లు క్లిక్ చేయండి. లోపలికి వచ్చే వారిని (Entry), బయటకు వెళ్ళే వారిని (Exit) గణిస్తుంది (Bi-directional gate counting).",
  },
  CROWD_ROI: {
    label: "Zone / Crowd Area Polygon",
    color: "#3fb950",
    isLine: false,
    hint: "హాల్ లేదా ఆవరణ చుట్టూ 3+ పాయింట్లు క్లిక్ చేసి పాలిగాన్ బాక్స్ గీయండి. జనం సాంద్రత (Density) మరియు ఆక్యుపెన్సీని లెక్కిస్తుంది.",
  },
  QUEUE_ROI: {
    label: "Queue Waiting Area Polygon",
    color: "#d29922",
    isLine: false,
    hint: "క్యూ బారికేడ్ల చుట్టూ పాలిగాన్ బాక్స్ గీయండి. క్యూ లో ఉన్నవారి సంఖ్య (Headcount) మరియు వెయిటింగ్ టైమ్ లెక్కిస్తుంది.",
  },
  ENTRY_LINE: {
    label: "Queue Entry Line",
    color: "#58a6ff",
    isLine: true,
    direction: "IN",
    hint: "క్యూ లైన్ మొదలయ్యే చోట (Tail) 2 పాయింట్లు క్లిక్ చేయండి. క్యూ లోకి ప్రవేశించే వారిని గణిస్తుంది.",
  },
  EXIT_LINE: {
    label: "Queue Exit Line",
    color: "#f85149",
    isLine: true,
    direction: "OUT",
    hint: "క్యూ పూర్తయ్యే కౌంటర్/దర్శనం వద్ద (Head) 2 పాయింట్లు క్లిక్ చేయండి. సర్వీస్ రేట్ లెక్కిస్తుంది.",
  },
  DIRECTION_LINE: {
    label: "Queue Flow Direction Line",
    color: "#388bfd",
    isLine: true,
    direction: "IN",
    hint: "క్యూ ఏ దిశలో ముందుకు కదులుతుందో సూచించడానికి ఎంట్రీ నుండి ఎగ్జిట్ వైపు లైన్ గీయండి.",
  },
  EXCLUSION_ZONE: {
    label: "Exclusion Zone (మినహాయింపు)",
    color: "#8b949e",
    isLine: false,
    hint: "స్తంభాలు, గోడలు, లేదా చెట్ల చుట్టూ బాక్స్ గీస్తే AI వాటిని లెక్కింపు నుండి తొలగిస్తుంది.",
  },
};

export default function ROIEditor({
  camera,
  profileId,
  profileName,
  onClose,
  onSaved,
  streamUrl,
  initialTool,
  initialObjective,
}) {
  const containerRef = useRef(null);
  const imageRef = useRef(null);

  const BACKEND = `http://${window.location.hostname}:8000`;
  const camCode = camera?.camera_code || camera?.id;
  const effectiveStreamUrl =
    streamUrl ||
    (camera?.stream_url
      ? (camera.stream_url.startsWith("http") ? camera.stream_url : `${BACKEND}${camera.stream_url}`)
      : `${BACKEND}/api/v1/frs-engine/cameras/${camCode || "CAM-KHB-001"}/stream`);

  const [streamLoading, setStreamLoading] = useState(true);
  const [streamError, setStreamError] = useState(false);

  const [rois, setRois] = useState([]);
  const [readiness, setReadiness] = useState(null);

  // Assigned purpose locked to camera profile: ENTRY | EXIT | ZONE | QUEUE
  const assignedObjective = useMemo(() => {
    if (initialObjective && initialObjective !== "ALL") return initialObjective;
    if (camera?.ai_purposes && camera.ai_purposes.length > 0) {
      const p = String(camera.ai_purposes[0]).toUpperCase();
      if (p === "ENTRY" || (p.includes("ENTRY") && !p.includes("EXIT"))) return "ENTRY";
      if (p === "EXIT" || (p.includes("EXIT") && !p.includes("ENTRY"))) return "EXIT";
      if (p.includes("QUEUE")) return "QUEUE";
      if (p.includes("ZONE")) return "ZONE";
      return "ENTRY";
    }
    if (profileId?.includes("QUEUE")) return "QUEUE";
    if (profileId?.includes("ZONE")) return "ZONE";
    if (profileId?.includes("EXIT")) return "EXIT";
    return "ENTRY";
  }, [initialObjective, camera?.ai_purposes, profileId]);

  const [objective, setObjective] = useState(assignedObjective);

  // Available tools strictly locked to assigned profile (Single tool per purpose)
  const availableTools = useMemo(() => {
    if (objective === "ENTRY") {
      return ["ENTRY_LINE"];
    }
    if (objective === "EXIT") {
      return ["EXIT_LINE"];
    }
    if (objective === "ZONE") {
      return ["CROWD_ROI"];
    }
    if (objective === "QUEUE") {
      return ["QUEUE_ROI"];
    }
    if (objective === "ENTRY_EXIT") {
      return ["COUNTING_LINE"];
    }
    return ["ENTRY_LINE"];
  }, [objective]);

  const [activeTool, setActiveTool] = useState(initialTool || availableTools[0] || "COUNTING_LINE");

  useEffect(() => {
    setObjective(assignedObjective);
  }, [assignedObjective]);

  useEffect(() => {
    if (!availableTools.includes(activeTool)) {
      setActiveTool(availableTools[0] || "COUNTING_LINE");
    }
  }, [availableTools, activeTool]);
  const [currentPoints, setCurrentPoints] = useState([]); // [{x: 0..1, y: 0..1}]
  const [history, setHistory] = useState([]);
  const [redoStack, setRedoStack] = useState([]);
  const [draggingIdx, setDraggingIdx] = useState(null);

  const [roiName, setRoiName] = useState("");
  const [direction, setDirection] = useState("BOTH");
  const [warningThreshold, setWarningThreshold] = useState("50");
  const [dangerThreshold, setDangerThreshold] = useState("80");
  const [capacity, setCapacity] = useState("100");
  const [selectedZone, setSelectedZone] = useState(
    camera?.zone_code || camera?.zone || "ZONE-A"
  );

  const [validationStatus, setValidationStatus] = useState(null); // { valid: bool, message: str }
  const [saving, setSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  // Stream status guard — allow live drawing whenever camera is not offline
  const isStreamVerified = camera?.enabled !== false && camera?.status !== "offline" && !streamError;

  const streamWarningMessage = useMemo(() => {
    if (camera?.enabled === false) return "Camera Offline — Camera is currently disabled";
    if (camera?.status === "offline") return "Camera Offline — Stream is unreachable";
    if (streamError) return "Stream Connection Error — Could not connect to live feed";
    return null;
  }, [camera, streamError]);

  // Load existing configurations
  const refreshData = async () => {
    if (!camera?.id) return;
    try {
      const summary = await getCameraROIConfig(camera.id, profileId);
      const confs = summary.configurations || [];
      setRois(confs);
      setReadiness(summary.readiness_by_profile?.[profileId] || null);
      if (confs.length > 0) {
        const first = confs[0];
        const g = first.geometry_json || {};
        if (g.warning_threshold) setWarningThreshold(String(g.warning_threshold));
        if (g.danger_threshold) setDangerThreshold(String(g.danger_threshold));
        if (g.capacity) setCapacity(String(g.capacity));
        if (g.zone_code) setSelectedZone(g.zone_code);
        if (first.name) setRoiName(first.name);
      }
    } catch (err) {
      console.error("Failed to load ROI configurations:", err);
    }
  };

  useEffect(() => {
    refreshData();
    setStreamLoading(true);
    setStreamError(false);
  }, [camera?.id, effectiveStreamUrl]);

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
        const dist = Math.hypot(coords.x - currentPoints[0].x, coords.y - currentPoints[0].y);
        if (dist < 0.02) {
          setValidationStatus({ valid: false, message: "Line endpoints must be distinct. Click a second point across the gate or walkway." });
          return;
        }
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
        setValidationStatus({ valid: false, message: "Line requires exactly 2 endpoints across the entryway" });
        return;
      }
      const dist = Math.hypot(currentPoints[1].x - currentPoints[0].x, currentPoints[1].y - currentPoints[0].y);
      if (dist < 0.02) {
        setValidationStatus({ valid: false, message: "Line endpoints must be distinct. Click two different points across the gate or walkway." });
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
      const detail = err.response?.data?.detail;
      const msg = (typeof detail === "object" && detail?.message) ? detail.message : (typeof detail === "string" ? detail : err.message);
      setValidationStatus({ valid: false, message: `✕ ${msg}` });
    }
  };

  // Save ROI
  const handleSave = async () => {
    const meta = ROI_TYPE_META[activeTool];
    let geom = {};
    if (meta?.isLine) {
      if (currentPoints.length !== 2) {
        setValidationStatus({ valid: false, message: "Line requires exactly 2 endpoints across the entryway" });
        return;
      }
      const dist = Math.hypot(currentPoints[1].x - currentPoints[0].x, currentPoints[1].y - currentPoints[0].y);
      if (dist < 0.02) {
        setValidationStatus({ valid: false, message: "Line endpoints must be distinct. Click two different points across the gate or walkway." });
        return;
      }
      geom = { start: currentPoints[0], end: currentPoints[1], direction };
    } else {
      if (currentPoints.length < 3) {
        setValidationStatus({ valid: false, message: "Polygon requires at least 3 vertices" });
        return;
      }
      geom = {
        points: currentPoints,
        warning_threshold: parseInt(warningThreshold, 10) || 50,
        danger_threshold: parseInt(dangerThreshold, 10) || 80,
        capacity: parseInt(capacity, 10) || 100,
        zone_name: roiName || `${selectedZone} Density Area`,
        zone_code: (objective === "ZONE" || activeTool === "CROWD_ROI") ? selectedZone : (camera?.zone_code || "ZONE-A"),
      };
    }

    // Check if camera already has ROIs of another purpose/model
    const conflictingRois = (rois || []).filter((r) => {
      if (activeTool === "ENTRY_LINE") {
        return r.roi_type !== "ENTRY_LINE";
      }
      if (activeTool === "EXIT_LINE") {
        return r.roi_type !== "EXIT_LINE";
      }
      if (activeTool === "QUEUE_ROI" || activeTool === "DIRECTION_LINE") {
        return r.roi_type !== "QUEUE_ROI" && r.roi_type !== "DIRECTION_LINE";
      }
      if (activeTool === "CROWD_ROI" || activeTool === "ZONE_BOUNDARY") {
        return r.roi_type !== "CROWD_ROI" && r.roi_type !== "ZONE_BOUNDARY";
      }
      if (activeTool === "COUNTING_LINE") {
        return r.roi_type !== "COUNTING_LINE";
      }
      return false;
    });

    if (conflictingRois.length > 0) {
      const getPurposeName = (t) => {
        if (t === "ENTRY_LINE") return "Entry Gate (IN)";
        if (t === "EXIT_LINE") return "Exit Gate (OUT)";
        if (t.includes("QUEUE")) return "Queue Management";
        if (t.includes("CROWD") || t.includes("ZONE")) return "Zone Density";
        return "Line Counting";
      };

      const prevName = conflictingRois[0].name || conflictingRois[0].roi_type;
      const prevPurpose = getPurposeName(conflictingRois[0].roi_type);
      const newPurpose = getPurposeName(activeTool);

      const confirmMsg =
        `ఈ కెమెరా ఇప్పటికే "${prevPurpose}" (${prevName}) కొరకు ఉపయోగించబడుతోంది.\n\n` +
        `ఇప్పుడు మీరు "${newPurpose}" మోడల్‌ను సెట్ చేస్తున్నారు.\n` +
        `పాత ROI ని తీసివేసి (Remove) కొత్త కాన్ఫిగరేషన్‌ను సేవ్‌ చేయాలా?`;

      if (!window.confirm(confirmMsg)) {
        return;
      }

      // Delete conflicting previous ROIs from DB
      for (const cr of conflictingRois) {
        try {
          await deleteCameraROI(camera.id, cr.id);
        } catch (_) {}
      }
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

      // Automatically activate Crowd AI model (YOLO11x) so detection starts immediately
      const camCode = camera.camera_code || camera.id;
      try {
        await switchCameraAIMode(camCode, "CROWD");
      } catch (e) {
        console.warn("Auto-start Crowd AI notice:", e);
      }

      // If configuring Zone Density, sync camera zone assignment
      if (objective === "ZONE" || activeTool === "CROWD_ROI") {
        try {
          await fetch(`${BACKEND}/api/v1/frs-engine/cameras/${camCode}/assign-zone?zone_code=${selectedZone}`, {
            method: "PATCH",
          });
        } catch (e) {
          console.warn("Zone assignment sync notice:", e);
        }
      }

      setStatusMessage("Configuration saved successfully! YOLO11x Human Detection is active.");
      setCurrentPoints([]);
      setHistory([]);
      setRedoStack([]);
      setValidationStatus(null);
      await refreshData();
      if (onSaved) onSaved();
    } catch (err) {
      const errObj = err.response?.data?.error;
      const detail = err.response?.data?.detail;
      const msg =
        errObj?.message ||
        (typeof detail === "object" && !Array.isArray(detail) && detail?.message) ||
        (Array.isArray(detail) ? detail.map((d) => d.msg || JSON.stringify(d)).join(", ") : null) ||
        (typeof detail === "string" ? detail : err.message);
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
      if (err.response?.status === 404) {
        // Already deleted on server, refresh smoothly without intrusive alert
        await refreshData();
        if (onSaved) onSaved();
      } else {
        const detail = err.response?.data?.detail;
        const msg = (typeof detail === "object" && detail?.message) ? detail.message : (typeof detail === "string" ? detail : err.message);
        alert("Failed to delete ROI: " + msg);
      }
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
          {/* Locked Assigned Profile Header Banner */}
          <div
            style={{
              background:
                objective === "ENTRY"
                  ? "rgba(63, 185, 80, 0.1)"
                  : objective === "EXIT"
                  ? "rgba(248, 81, 73, 0.1)"
                  : objective === "QUEUE"
                  ? "rgba(210, 153, 34, 0.1)"
                  : "rgba(188, 140, 255, 0.1)",
              padding: "10px 12px",
              borderRadius: 6,
              border: `1px solid ${
                objective === "ENTRY"
                  ? "rgba(63, 185, 80, 0.3)"
                  : objective === "EXIT"
                  ? "rgba(248, 81, 73, 0.3)"
                  : objective === "QUEUE"
                  ? "rgba(210, 153, 34, 0.3)"
                  : "rgba(188, 140, 255, 0.3)"
              }`,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                fontSize: 12,
                fontWeight: 700,
                color:
                  objective === "ENTRY"
                    ? "#3fb950"
                    : objective === "EXIT"
                    ? "#f85149"
                    : objective === "QUEUE"
                    ? "#d29922"
                    : "#bc8cff",
              }}
            >
              <i
                className={`bi ${
                  objective === "ENTRY"
                    ? "bi-box-arrow-in-right"
                    : objective === "EXIT"
                    ? "bi-box-arrow-right"
                    : objective === "QUEUE"
                    ? "bi-people"
                    : "bi-bounding-box"
                }`}
              />
              <span>
                {objective === "ENTRY"
                  ? "Assigned: Entry Gate (IN)"
                  : objective === "EXIT"
                  ? "Assigned: Exit Gate (OUT)"
                  : objective === "QUEUE"
                  ? "Assigned: Queue Management"
                  : "Assigned: Zone Density Management"}
              </span>
            </div>
            <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 4, lineHeight: 1.3 }}>
              {objective === "ENTRY"
                ? "Draw an Entry Line across the gate to count visitors entering (IN)."
                : objective === "EXIT"
                ? "Draw an Exit Line across the gate to count visitors leaving (OUT)."
                : objective === "QUEUE"
                ? "Draw a waiting queue polygon around barricades to track people waiting."
                : "Draw a crowd density zone polygon to monitor area capacity."}
            </div>
          </div>

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
                      border: `1px solid ${isSelected ? meta?.color || "var(--cc-accent)" : "var(--cc-border)"}`,
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
                      <div style={{ width: 10, height: 10, borderRadius: meta?.isLine ? 2 : "50%", background: meta?.color || "var(--cc-accent)" }} />
                      <span>{meta?.label || tool}</span>
                    </div>
                    <span style={{ fontSize: 10, color: "var(--cc-text-muted)", fontFamily: "var(--cc-font-mono)" }}>
                      {meta?.isLine ? "LINE" : "POLYGON"}
                    </span>
                  </button>
                );
              })}
            </div>
            {ROI_TYPE_META[activeTool] && (
              <div
                style={{
                  fontSize: 11,
                  color: "var(--cc-text-secondary)",
                  marginTop: 10,
                  background: "var(--cc-bg-root)",
                  padding: "8px 10px",
                  borderRadius: 4,
                  borderLeft: `3px solid ${ROI_TYPE_META[activeTool]?.color || "var(--cc-accent)"}`,
                  lineHeight: 1.4,
                }}
              >
                <i className="bi bi-info-circle-fill" style={{ marginRight: 6, color: ROI_TYPE_META[activeTool]?.color }} />
                {ROI_TYPE_META[activeTool]?.hint}
              </div>
            )}
          </div>

          {/* Geometry Properties */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {/* Zone Selector — ONLY for Zone Density camera */}
            {(objective === "ZONE" || activeTool === "CROWD_ROI") && (
              <div style={{ background: "var(--cc-bg-root)", padding: "10px 12px", borderRadius: 6, border: "1px solid var(--cc-border)" }}>
                <label style={{ fontSize: 11, fontWeight: 700, color: "var(--cc-accent)", display: "flex", alignItems: "center", gap: 6, marginBottom: 8, textTransform: "uppercase" }}>
                  <i className="bi bi-geo-alt-fill" style={{ color: "#58a6ff" }} /> Select Zone (A, B, C, D):
                </label>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                  {[
                    { code: "ZONE-A", label: "Zone A", sub: "North Gate", color: "#3fb950" },
                    { code: "ZONE-B", label: "Zone B", sub: "Main Idol", color: "#58a6ff" },
                    { code: "ZONE-C", label: "Zone C", sub: "VIP Enclosure", color: "#bc8cff" },
                    { code: "ZONE-D", label: "Zone D", sub: "Prasadam", color: "#d29922" },
                  ].map((z) => {
                    const isSel = selectedZone === z.code;
                    return (
                      <button
                        key={z.code}
                        type="button"
                        onClick={() => {
                          setSelectedZone(z.code);
                          if (!roiName || roiName.includes("Polygon") || roiName.includes("Zone") || roiName.includes("Area")) {
                            setRoiName(`${z.label} Density Area`);
                          }
                        }}
                        style={{
                          padding: "8px 6px",
                          borderRadius: 6,
                          cursor: "pointer",
                          border: isSel ? `2px solid ${z.color}` : "1px solid var(--cc-border)",
                          background: isSel ? `${z.color}25` : "rgba(255,255,255,0.02)",
                          color: isSel ? z.color : "var(--cc-text-primary)",
                          fontWeight: 700,
                          fontSize: 11,
                          display: "flex",
                          flexDirection: "column",
                          alignItems: "center",
                          justifyContent: "center",
                          gap: 2,
                          transition: "all 0.15s ease",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                          <span style={{ width: 8, height: 8, borderRadius: "50%", background: z.color }} />
                          {z.label}
                        </div>
                        <span style={{ fontSize: 9.5, color: "var(--cc-text-muted)", fontWeight: 400 }}>{z.sub}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

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

            {ROI_TYPE_META[activeTool]?.isLine ? (
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
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, background: "var(--cc-bg-root)", padding: 10, borderRadius: 6, border: "1px solid var(--cc-border)" }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--cc-accent)", textTransform: "uppercase" }}>
                  Density Alert Thresholds
                </div>

                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 }}>
                    <label style={{ fontSize: 11, fontWeight: 600, color: "#d29922" }}>
                      Warning Threshold (Orange)
                    </label>
                    <span style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>people</span>
                  </div>
                  <input
                    type="number"
                    min="1"
                    value={warningThreshold}
                    onChange={(e) => setWarningThreshold(e.target.value)}
                    className="cc-input"
                    style={{ width: "100%", padding: "4px 8px", fontSize: 12 }}
                    placeholder="50"
                  />
                  <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 2 }}>
                    Zone turns Orange above this count
                  </div>
                </div>

                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 }}>
                    <label style={{ fontSize: 11, fontWeight: 600, color: "#f85149" }}>
                      Danger Threshold (Red)
                    </label>
                    <span style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>people</span>
                  </div>
                  <input
                    type="number"
                    min="1"
                    value={dangerThreshold}
                    onChange={(e) => setDangerThreshold(e.target.value)}
                    className="cc-input"
                    style={{ width: "100%", padding: "4px 8px", fontSize: 12 }}
                    placeholder="80"
                  />
                  <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 2 }}>
                    Zone turns Red above this count
                  </div>
                </div>

                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 }}>
                    <label style={{ fontSize: 11, fontWeight: 600, color: "var(--cc-text-secondary)" }}>
                      Max Capacity
                    </label>
                    <span style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>people</span>
                  </div>
                  <input
                    type="number"
                    min="1"
                    value={capacity}
                    onChange={(e) => setCapacity(e.target.value)}
                    className="cc-input"
                    style={{ width: "100%", padding: "4px 8px", fontSize: 12 }}
                    placeholder="100"
                  />
                </div>
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
                      {roi.geometry_json?.warning_threshold && (
                        <span style={{ fontSize: 9, color: "#d29922", background: "rgba(210,153,34,0.15)", padding: "1px 4px", borderRadius: 3 }}>
                          W:{roi.geometry_json.warning_threshold} D:{roi.geometry_json.danger_threshold}
                        </span>
                      )}
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

          {/* Live Feed Container with Interactive SVG */}
          {streamError ? (
            <div style={{ textAlign: "center", color: "var(--cc-text-muted)", padding: 40 }}>
              <div style={{ fontSize: 36, marginBottom: 12 }}>📹</div>
              <div style={{ fontWeight: 700, color: "var(--cc-red)", fontSize: 14, marginBottom: 6 }}>
                Live Stream Connection Failed
              </div>
              <div style={{ fontSize: 12, maxWidth: 360, margin: "0 auto" }}>
                Make sure the camera RTSP stream is online and reachable on the network.
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
              {streamLoading && (
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    background: "rgba(10,13,16,0.85)",
                    zIndex: 20,
                    color: "var(--cc-text-muted)",
                    fontSize: 12,
                    gap: 8,
                  }}
                >
                  <i className="bi bi-broadcast" style={{ color: "var(--cc-green)", animation: "pulse 1.5s infinite" }} />
                  Connecting to live camera feed...
                </div>
              )}
              <img
                ref={imageRef}
                src={effectiveStreamUrl}
                alt="Camera Live Feed"
                style={{
                  display: "block",
                  maxWidth: "100%",
                  maxHeight: "82vh",
                  borderRadius: 4,
                  border: "1px solid var(--cc-border)",
                  objectFit: "contain",
                }}
                onError={() => {
                  setStreamLoading(false);
                  setStreamError(true);
                }}
                onLoad={() => setStreamLoading(false)}
              />

              {/* Real-time Live Badge */}
              <div
                style={{
                  position: "absolute",
                  top: 10,
                  right: 10,
                  zIndex: 35,
                  fontSize: 10,
                  fontWeight: 700,
                  color: "var(--cc-green)",
                  background: "rgba(0,0,0,0.8)",
                  padding: "4px 8px",
                  borderRadius: 3,
                  backdropFilter: "blur(4px)",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  border: "1px solid rgba(63,185,80,0.4)",
                  pointerEvents: "none",
                  fontFamily: "var(--cc-font-mono)",
                }}
              >
                <span
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: "50%",
                    background: "var(--cc-green)",
                    boxShadow: "0 0 6px var(--cc-green)",
                  }}
                />
                LIVE FEED
              </div>

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
