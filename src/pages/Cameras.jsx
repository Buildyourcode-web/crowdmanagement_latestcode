// Cameras page — Working CCTV Wall divided into FRS & Crowd Surveillance Sections
import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import CameraCard from "../components/camera/CameraCard.jsx";
import { getCameras, getCameraStats, toggleCameraFRS } from "../services/cameraService.js";
import { switchCameraAIMode } from "../services/aiService.js";
import { realtimeService } from "../services/realtimeService.js";
import { LoadingState } from "../components/common/States.jsx";
import ROIEditor from "../components/ai/ROIEditor.jsx";

const BACKEND = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`;
const DEFAULT_RTSP = "rtsp://admin:Veeru%40555@192.168.0.102:554/Streaming/Channels/101";

const GRID_SIZES = [
  { label: "4×", cols: 4 },
  { label: "3×", cols: 3 },
  { label: "2×", cols: 2 },
  { label: "1×", cols: 1 },
];

const PURPOSE_NAMES = {
  ENTRY: "Entry Gate (IN)",
  EXIT: "Exit Gate (OUT)",
  QUEUE: "Queue Management",
  ZONE: "Zone Management",
  ENTRY_EXIT: "Entry/Exit Counting",
};

const PURPOSE_META = {
  ENTRY: {
    label: "Entry Gate (IN Only)",
    icon: "bi-box-arrow-in-right",
    color: "#3fb950",
    profile_id: "CROWD_STANDARD",
    profile_name: "Entry Gate Line",
    initial_tool: "ENTRY_LINE",
    description: "Counts visitors entering (+1 IN count)",
  },
  EXIT: {
    label: "Exit Gate (OUT Only)",
    icon: "bi-box-arrow-right",
    color: "#f85149",
    profile_id: "CROWD_STANDARD",
    profile_name: "Exit Gate Line",
    initial_tool: "EXIT_LINE",
    description: "Counts visitors leaving (+1 OUT count)",
  },
  ENTRY_EXIT: {
    label: "Two-Way Gate (IN & OUT)",
    icon: "bi-arrow-left-right",
    color: "#bc8cff",
    profile_id: "CROWD_STANDARD",
    profile_name: "Two-Way Counting Line",
    initial_tool: "COUNTING_LINE",
    description: "In/Out 2-way gate line crossing & counting",
  },
  ZONE: {
    label: "Zone Density Monitoring",
    icon: "bi-bounding-box",
    color: "#58a6ff",
    profile_id: "CROWD_STANDARD",
    profile_name: "Crowd Density Zone",
    initial_tool: "CROWD_ROI",
    description: "Overcrowding risk & density monitoring",
  },
  QUEUE: {
    label: "Queue Management",
    icon: "bi-people",
    color: "#d29922",
    profile_id: "QUEUE_STANDARD",
    profile_name: "Queue Waiting Zone",
    initial_tool: "QUEUE_ROI",
    description: "Barricade queue depth & waiting time tracking",
  },
};

export const ZONE_PRESETS = [
  { code: "ZONE-A", name: "Zone A", label: "North Gate & Approach", color: "#3fb950", icon: "bi-geo-alt-fill", capacity: 10000 },
  { code: "ZONE-B", name: "Zone B", label: "Main Idol Darshan Arena", color: "#58a6ff", icon: "bi-geo-alt-fill", capacity: 20000 },
  { code: "ZONE-C", name: "Zone C", label: "VIP Enclosure & Stage", color: "#bc8cff", icon: "bi-geo-alt-fill", capacity: 6000 },
  { code: "ZONE-D", name: "Zone D", label: "Prasadam & Laddu Counters", color: "#d29922", icon: "bi-geo-alt-fill", capacity: 5000 },
];


export default function Cameras() {
  const navigate = useNavigate();
  const [dbCameras, setDbCameras] = useState([]);
  const [engineCameras, setEngineCameras] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [activeTab, setActiveTab] = useState("ALL"); // "ALL", "FRS", "CROWD"
  const [selectedZone, setSelectedZone] = useState("ALL"); // "ALL", "ZONE-A", "ZONE-B", "ZONE-C", "ZONE-D"
  const [gridCols, setGridCols] = useState(3);
  const [showAddModal, setShowAddModal] = useState(false);
  const [addForm, setAddForm] = useState({
    name: "Entry Gate 1 Camera",
    rtsp_url: DEFAULT_RTSP,
    camera_type: "CROWD",
    is_frs: false,
    ai_purposes: ["ENTRY"],
    zone_code: "ZONE-A",
  });

  const [zoneSwitchModal, setZoneSwitchModal] = useState({
    open: false,
    camera: null,
  });
  const [zoneSwitchLoading, setZoneSwitchLoading] = useState(false);

  const [reassignSelectModal, setReassignSelectModal] = useState({
    open: false,
    camera: null,
    selectedPurposes: ["ENTRY"],
  });
  const [reassignLoading, setReassignLoading] = useState(false);

  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState("");

  // Fullscreen Modal & 1-Click Enrollment State
  const [fullscreenCamera, setFullscreenCamera] = useState(null);
  const [isBrowserFullscreen, setIsBrowserFullscreen] = useState(false);
  const fullscreenContainerRef = useRef(null);
  const [modalStreamError, setModalStreamError] = useState(false);
  const [modalRetry, setModalRetry] = useState(0);

  const [enrollName, setEnrollName] = useState("");
  const [enrollCategory, setEnrollCategory] = useState("Authorized Watchlist");
  const [enrollLoading, setEnrollLoading] = useState(false);
  const [enrollStatus, setEnrollStatus] = useState(null);
  const [activeROIEditor, setActiveROIEditor] = useState(null);

  const engineInFlightRef = useRef(false);
  const engineTimerRef = useRef(null);
  const isMountedRef = useRef(true);

  // Load active FRS / RTSP engine camera workers with in-flight guard
  const loadEngineCameras = useCallback(async () => {
    if (engineInFlightRef.current) return;
    engineInFlightRef.current = true;
    try {
      const res = await fetch(`${BACKEND}/api/v1/frs-engine/cameras`);
      if (res.ok && isMountedRef.current) {
        const data = await res.json();
        const list = Array.isArray(data) ? data : [data];
        setEngineCameras(
          list.map((c) => ({
            id: c.camera_id,
            camera_code: c.camera_id,
            label: c.name,
            name: c.name,
            status: c.status === "online" ? "online" : (c.status === "error" ? "offline" : "degraded"),
            is_frs_camera: Boolean(c.is_frs || c.camera_type === "FRS"),
            is_frs: Boolean(c.is_frs || c.camera_type === "FRS"),
            camera_type: c.camera_type || (c.is_frs ? "FRS" : "CROWD"),
            stream_url: c.stream_url,
            fps: 25,
            zone_code: c.is_frs ? "ZONE-A" : "ZONE-B",
            detections_count: c.detections_count || 0,
            ai_status: c.status === "online" ? "online" : "offline",
            ai_purposes: c.ai_purposes || (c.is_frs ? [] : ["ENTRY_EXIT"]),
          }))
        );
      }
    } catch (e) {
      console.warn("[Cameras] Engine cams fetch:", e);
    } finally {
      engineInFlightRef.current = false;
    }
  }, []);

  // Load database cameras
  const loadDbCameras = useCallback(async () => {
    try {
      const [camsRes, statsRes] = await Promise.allSettled([
        getCameras({ page_size: 50 }),
        getCameraStats(),
      ]);
      if (!isMountedRef.current) return;
      const camsVal = camsRes.status === "fulfilled" ? camsRes.value : [];
      const statsVal = statsRes.status === "fulfilled" ? statsRes.value : null;
      const list = Array.isArray(camsVal) ? camsVal : (camsVal?.data || []);
      // Filter out any non-working, disabled, or legacy duplicate cameras
      setDbCameras(list.filter((c) => (c.status === "online" || c.status === "degraded") && c.enabled !== false && c.camera_code !== "CAM-KHB-001" && c.id !== "CAM-KHB-001"));
      if (statsVal) setStats(statsVal);
    } catch (e) {
      console.warn(e);
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    loadDbCameras();
    loadEngineCameras();

    const scheduleNext = () => {
      clearTimeout(engineTimerRef.current);
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      engineTimerRef.current = setTimeout(async () => {
        if (isMountedRef.current && document.visibilityState === "visible") {
          await loadEngineCameras();
          scheduleNext();
        }
      }, 5000);
    };

    scheduleNext();

    const handleVis = () => {
      if (document.visibilityState === "visible") {
        loadEngineCameras();
        scheduleNext();
      } else {
        clearTimeout(engineTimerRef.current);
      }
    };
    document.addEventListener("visibilitychange", handleVis);

    const unsubEvents = realtimeService.subscribe((msg, eventType) => {
      const type = eventType || msg?.type;
      if (
        type === "pipeline_state_changed" ||
        type === "PIPELINE_STARTED" ||
        type === "PIPELINE_STOPPED" ||
        type === "camera_update" ||
        type === "CAMERA_ADDED" ||
        type === "CAMERA_DELETED"
      ) {
        loadEngineCameras();
        loadDbCameras();
      }
    });

    return () => {
      isMountedRef.current = false;
      clearTimeout(engineTimerRef.current);
      document.removeEventListener("visibilitychange", handleVis);
      unsubEvents();
    };
  }, [loadDbCameras, loadEngineCameras]);

  // Build list of active working streams ONLY (no dummy screens, no offline placeholders)
  const activeStreamsMap = new Map();

  // 1. Live RTSP engine workers actively running
  for (const eng of engineCameras) {
    if (eng.status === "online" || eng.stream_url) {
      const isFrs = Boolean(eng.is_frs || eng.camera_type === "FRS");
      const camId = eng.camera_id || eng.id;
      activeStreamsMap.set(camId, {
        id: camId,
        camera_code: camId,
        name: eng.name || camId,
        label: eng.name || camId,
        status: "online",
        is_frs: isFrs,
        is_frs_camera: isFrs,
        camera_type: isFrs ? "FRS" : "CROWD",
        stream_url: eng.stream_url,
        fps: 25,
        zone_code: eng.zone_code || "ZONE-A",
        detections_count: eng.detections_count || 0,
        ai_purposes: eng.ai_purposes || (isFrs ? [] : ["ENTRY_EXIT", "ZONE"]),
        is_running: true,
      });
    }
  }

  // 2. Synchronize with database cameras if matching active stream
  for (const cam of dbCameras) {
    const camKey = cam.camera_code || cam.id;
    if (activeStreamsMap.has(camKey)) {
      const existing = activeStreamsMap.get(camKey);
      activeStreamsMap.set(camKey, {
        ...existing,
        name: cam.name || existing.name,
        label: cam.label || existing.label,
        zone: cam.zone || existing.zone_code,
      });
    } else if (cam.stream_status === "ONLINE" && cam.rtsp_url) {
      const isFrs = Boolean(cam.is_frs_camera || cam.camera_type === "FRS");
      activeStreamsMap.set(camKey, {
        ...cam,
        id: camKey,
        camera_code: camKey,
        is_frs: isFrs,
        is_frs_camera: isFrs,
        camera_type: isFrs ? "FRS" : "CROWD",
        status: "online",
        is_running: true,
        stream_url: `/api/v1/frs-engine/cameras/${camKey}/stream`,
        fps: cam.fps || 25,
        ai_purposes: cam.ai_purposes || (isFrs ? [] : ["ENTRY_EXIT", "ZONE"]),
      });
    }
  }

  // Apply search filter
  const filterBySearch = (cam) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      (cam.id || "").toLowerCase().includes(q) ||
      (cam.name || "").toLowerCase().includes(q) ||
      (cam.label || "").toLowerCase().includes(q)
    );
  };

  const filterByZone = (cam) => {
    if (selectedZone === "ALL") return true;
    const camZone = (cam.zone_code || cam.zone || "").toUpperCase().trim();
    const targetCode = selectedZone.toUpperCase().trim();
    if (camZone === targetCode) return true;
    const normCam = camZone.replace(/[^A-Z0-9]/g, "");
    const normTarget = targetCode.replace(/[^A-Z0-9]/g, "");
    if (normCam === normTarget) return true;

    const preset = ZONE_PRESETS.find((z) => z.code === selectedZone);
    if (preset) {
      const presetNorm = preset.name.toUpperCase().replace(/[^A-Z0-9]/g, "");
      if (normCam.includes(presetNorm) || presetNorm.includes(normCam)) return true;
      if (preset.label && camZone.includes(preset.label.toUpperCase())) return true;
    }
    return false;
  };

  const allUnfilteredCameras = Array.from(activeStreamsMap.values()).filter(filterBySearch);
  const allWorkingCameras = allUnfilteredCameras.filter(filterByZone);
  const frsCameras = allWorkingCameras.filter((c) => c.is_frs || c.camera_type === "FRS");
  const crowdCameras = allWorkingCameras.filter((c) => !c.is_frs && c.camera_type !== "FRS");

  const getZoneCamCount = (zoneCode) => {
    if (zoneCode === "ALL") return allUnfilteredCameras.length;
    return allUnfilteredCameras.filter((cam) => {
      const camZone = (cam.zone_code || cam.zone || "").toUpperCase().trim();
      const targetCode = zoneCode.toUpperCase().trim();
      if (camZone === targetCode) return true;
      if (camZone.replace(/[^A-Z0-9]/g, "") === targetCode.replace(/[^A-Z0-9]/g, "")) return true;
      const preset = ZONE_PRESETS.find((z) => z.code === zoneCode);
      if (preset) {
        const presetNorm = preset.name.toUpperCase().replace(/[^A-Z0-9]/g, "");
        if (camZone.replace(/[^A-Z0-9]/g, "").includes(presetNorm) || presetNorm.includes(camZone.replace(/[^A-Z0-9]/g, ""))) return true;
        if (preset.label && camZone.includes(preset.label.toUpperCase())) return true;
      }
      return false;
    }).length;
  };

  const handleAddCamera = async () => {
    if (!addForm.rtsp_url.trim()) {
      setAddError("RTSP Stream URL is required");
      return;
    }
    setAddLoading(true);
    setAddError("");
    try {
      const res = await fetch(`${BACKEND}/api/v1/frs-engine/cameras`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(addForm),
      });
      if (!res.ok) {
        const err = await res.json();
        setAddError(err.detail || "Failed to add camera stream");
      } else {
        const data = await res.json();
        setShowAddModal(false);
        await Promise.all([loadDbCameras(), loadEngineCameras()]);
        if (addForm.camera_type === "FRS") {
          setActiveTab("FRS");
        } else {
          setActiveTab("CROWD");
          const createdCam = {
            id: data.camera_id,
            camera_code: data.camera_id,
            stream_url: data.stream_url,
            name: data.name,
            ai_purposes: addForm.ai_purposes || ["ENTRY"],
          };
          const firstPurpose = (addForm.ai_purposes && addForm.ai_purposes[0]) || "ENTRY";
          const meta = PURPOSE_META[firstPurpose] || PURPOSE_META.ENTRY;
          setActiveROIEditor({
            camera: createdCam,
            profile_id: meta.profile_id,
            profile_name: meta.profile_name,
            initial_tool: meta.initial_tool,
            initial_objective: firstPurpose,
          });
        }
        setAddForm({
          name: "Entry Gate 1 Camera",
          rtsp_url: DEFAULT_RTSP,
          camera_type: "CROWD",
          is_frs: false,
          ai_purposes: ["ENTRY"],
          zone_code: "ZONE-A",
        });
      }
    } catch (e) {
      setAddError("Backend connection error — check backend is running");
    } finally {
      setAddLoading(false);
    }
  };

  const handleOpenZoneSwitch = (camera) => {
    setZoneSwitchModal({
      open: true,
      camera: camera,
    });
  };

  const handleConfirmZoneSwitch = async (targetZoneCode) => {
    const cam = zoneSwitchModal.camera;
    if (!cam) return;
    setZoneSwitchLoading(true);
    try {
      const camCode = cam.camera_code || cam.id;
      const res = await fetch(`${BACKEND}/api/v1/frs-engine/cameras/${camCode}/assign-zone?zone_code=${targetZoneCode}`, {
        method: "PATCH",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        alert(err.detail || "Failed to assign zone to camera");
        return;
      }
      setZoneSwitchModal({ open: false, camera: null });
      await Promise.all([loadDbCameras(), loadEngineCameras()]);
    } catch (err) {
      alert("Error assigning zone: " + err.message);
    } finally {
      setZoneSwitchLoading(false);
    }
  };

  const handleOpenReassign = (camera) => {
    const existing = (Array.isArray(camera.ai_purposes) && camera.ai_purposes.length > 0)
      ? camera.ai_purposes
      : ["ENTRY_EXIT"];
    setReassignSelectModal({
      open: true,
      camera: camera,
      selectedPurposes: existing,
      selectedZone: camera.zone_code || camera.zone || "ZONE-A",
    });
  };

  const handleToggleReassignPurpose = (purposeKey) => {
    setReassignSelectModal((prev) => {
      const curr = prev.selectedPurposes || [];
      if (curr.includes(purposeKey)) {
        if (curr.length <= 1) return prev; // keep at least 1
        return { ...prev, selectedPurposes: curr.filter((p) => p !== purposeKey) };
      } else {
        if (curr.length >= 2) {
          return { ...prev, selectedPurposes: [curr[1], purposeKey] };
        }
        return { ...prev, selectedPurposes: [...curr, purposeKey] };
      }
    });
  };

  const handleConfirmReassign = async () => {
    const cam = reassignSelectModal.camera;
    const targetPurposes = reassignSelectModal.selectedPurposes || ["ENTRY_EXIT"];
    if (!cam || targetPurposes.length === 0) return;
    setReassignLoading(true);
    try {
      const camCode = cam.camera_code || cam.id.replace("-CROWD", "").replace("-FRS", "");
      const purpParam = targetPurposes.join(",");
      const res = await fetch(`${BACKEND}/api/v1/frs-engine/cameras/${camCode}/reassign-purpose?new_purpose=${purpParam}`, {
        method: "PATCH",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        alert(err.detail || "Failed to reassign camera purposes");
        return;
      }

      // If ZONE purpose was chosen, also assign the selected zone
      if (targetPurposes.includes("ZONE") && reassignSelectModal.selectedZone) {
        try {
          await fetch(`${BACKEND}/api/v1/frs-engine/cameras/${camCode}/assign-zone?zone_code=${reassignSelectModal.selectedZone}`, {
            method: "PATCH",
          });
        } catch (_) {}
      }

      await Promise.all([loadDbCameras(), loadEngineCameras()]);

      if (fullscreenCamera && (fullscreenCamera.id === cam.id || fullscreenCamera.camera_code === camCode)) {
        setFullscreenCamera((prev) => (prev ? { ...prev, ai_purposes: targetPurposes, zone_code: reassignSelectModal.selectedZone || prev.zone_code } : null));
      }

      setReassignSelectModal({ open: false, camera: null, selectedPurposes: [], selectedZone: "ZONE-A" });

      const firstPurp = targetPurposes[0] || "ENTRY_EXIT";
      const meta = PURPOSE_META[firstPurp] || PURPOSE_META.ENTRY_EXIT;
      setActiveROIEditor({
        camera: { ...cam, ai_purposes: targetPurposes },
        profile_id: meta.profile_id,
        profile_name: meta.profile_name,
        initial_tool: meta.initial_tool,
        initial_objective: firstPurp,
      });
    } catch (err) {
      console.error("Failed to reassign camera purpose:", err);
      alert("Error reassigning camera: " + (err.message || err));
    } finally {
      setReassignLoading(false);
    }
  };

  const handleToggleFrs = async (camera, enabled) => {
    try {
      const code = camera.camera_code || camera.id.replace("-FRS", "").replace("-CROWD", "");
      if (enabled && (camera.ai_mode === "CROWD" || camera.crowd_status === "online" || camera.is_running)) {
        const confirmed = window.confirm(
          `[MUTUAL EXCLUSIVITY NOTICE]\nCamera "${camera.name || code}" is currently running Crowd Intelligence. Switching to Facial Recognition (FRS) will pause Crowd analytics on this physical stream to ensure dedicated inference bandwidth.\n\nDo you want to proceed with mode switch?`
        );
        if (!confirmed) return;
        try {
          await switchCameraAIMode(code, "FRS");
        } catch (e) {}
      }
      await toggleCameraFRS(code, enabled);
      await Promise.all([loadDbCameras(), loadEngineCameras()]);
      if (fullscreenCamera && (fullscreenCamera.id === camera.id || fullscreenCamera.camera_code === code)) {
        setFullscreenCamera((prev) => (prev ? { ...prev, is_frs_camera: enabled, is_frs: enabled, camera_type: enabled ? "FRS" : "CROWD" } : null));
      }
    } catch (e) {
      console.error("Failed to toggle camera FRS state:", e);
    }
  };

  const handleToggleCrowdAI = async (camera, enabled) => {
    try {
      const code = camera.camera_code || camera.id.replace("-FRS", "").replace("-CROWD", "");
      if (enabled && (camera.ai_mode === "FRS" || camera.is_frs_camera || camera.frs_status === "online")) {
        const confirmed = window.confirm(
          `[MUTUAL EXCLUSIVITY NOTICE]\nCamera "${camera.name || code}" is currently designated for Facial Recognition (FRS). Switching to Crowd Intelligence will transition AI processing away from FRS.\n\nDo you want to proceed with mode switch?`
        );
        if (!confirmed) return;
        try {
          await toggleCameraFRS(code, false);
        } catch (e) {}
      }
      if (enabled) {
        await switchCameraAIMode(code, "CROWD");
      } else {
        await switchCameraAIMode(code, "IDLE");
      }
      await Promise.all([loadDbCameras(), loadEngineCameras()]);
      if (fullscreenCamera && (fullscreenCamera.id === camera.id || fullscreenCamera.camera_code === code)) {
        setFullscreenCamera((prev) => (prev ? { ...prev, is_running: enabled, status: enabled ? "online" : "stopped" } : null));
      }
    } catch (e) {
      console.error("Failed to toggle Crowd AI model:", e);
    }
  };


  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape" && fullscreenCamera && !document.fullscreenElement) {
        setFullscreenCamera(null);
        setEnrollStatus(null);
      }
    };
    const handleFsChange = () => {
      setIsBrowserFullscreen(Boolean(document.fullscreenElement));
    };
    window.addEventListener("keydown", handleKeyDown);
    document.addEventListener("fullscreenchange", handleFsChange);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("fullscreenchange", handleFsChange);
    };
  }, [fullscreenCamera]);

  const toggleBrowserFullscreen = () => {
    if (!fullscreenContainerRef.current) return;
    if (!document.fullscreenElement) {
      fullscreenContainerRef.current.requestFullscreen().catch((err) => console.error(err));
      setIsBrowserFullscreen(true);
    } else {
      document.exitFullscreen().catch((err) => console.error(err));
      setIsBrowserFullscreen(false);
    }
  };

  const handleEnrollFromCamera = async () => {
    if (!enrollName.trim() || !fullscreenCamera) return;
    setEnrollLoading(true);
    setEnrollStatus(null);
    try {
      const res = await fetch(`${BACKEND}/api/v1/frs-engine/enroll-from-camera`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: enrollName.trim(),
          camera_id: fullscreenCamera.id || fullscreenCamera.camera_code,
          category: enrollCategory,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setEnrollStatus({ type: "error", message: data.detail || "Enrollment failed" });
      } else {
        setEnrollStatus({ type: "success", message: `Enrolled ${enrollName}! Real-time recognition is active.` });
        setEnrollName("");
        await loadEngineCameras();
      }
    } catch (e) {
      setEnrollStatus({ type: "error", message: e.message || "Failed to connect to backend" });
    } finally {
      setEnrollLoading(false);
    }
  };

  return (
    <div className="cc-page">
      {/* 1. Header */}
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title" style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span>Working CCTV Surveillance Wall</span>
            <span
              style={{
                fontSize: 10,
                padding: "2px 8px",
                background: "var(--cc-green-dim)",
                border: "1px solid var(--cc-green-border)",
                borderRadius: "var(--cc-radius-sm)",
                color: "var(--cc-green)",
                fontWeight: 700,
              }}
            >
              ACTIVE STREAMS ONLY
            </span>
          </div>
          <div className="cc-page-subtitle">
            Khairatabad Ganesh Festival 2026 — {allWorkingCameras.length} Active Operational Video Channels
          </div>
        </div>

        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {GRID_SIZES.map((g) => (
            <button
              key={g.cols}
              className={`cc-btn${gridCols === g.cols ? " cc-btn-primary" : ""}`}
              style={{ padding: "4px 10px", fontSize: 11 }}
              onClick={() => setGridCols(g.cols)}
            >
              {g.label}
            </button>
          ))}
          <button
            className="cc-btn cc-btn-secondary"
            onClick={() => navigate("/cameras/add")}
            style={{ marginLeft: 6, display: "flex", alignItems: "center", gap: 6, fontSize: 11 }}
          >
            <i className="bi bi-camera-reels-fill" /> Onboard Camera Wizard
          </button>
          <button
            className="cc-btn cc-btn-primary"
            onClick={() => setShowAddModal(true)}
            style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11 }}
          >
            <i className="bi bi-plus-circle-fill" /> Quick Stream Add
          </button>
        </div>
      </div>

      {/* 2. Stats Bar */}
      <div
        style={{
          display: "flex",
          gap: 16,
          padding: "10px 14px",
          background: "var(--cc-bg-secondary)",
          border: "1px solid var(--cc-border)",
          borderRadius: "var(--cc-radius)",
          fontSize: 12,
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <span style={{ color: "var(--cc-text-muted)" }}>
          Active Working Cameras:{" "}
          <strong style={{ color: "var(--cc-text-primary)", fontSize: 13 }}>{allWorkingCameras.length}</strong>
        </span>
        <span style={{ color: "var(--cc-text-muted)" }}>
          FRS AI Channels:{" "}
          <strong style={{ color: "var(--cc-accent)", fontSize: 13 }}>{frsCameras.length}</strong>
        </span>
        <span style={{ color: "var(--cc-text-muted)" }}>
          Crowd AI Channels:{" "}
          <strong style={{ color: "var(--cc-green)", fontSize: 13 }}>{crowdCameras.length}</strong>
        </span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          <span className="cc-live-dot" style={{ width: 8, height: 8 }} />
          <span style={{ color: "var(--cc-green)", fontSize: 11, fontWeight: 700 }}>
            BIOMETRIC FRS & CROWD AI ENGINES RUNNING
          </span>
        </div>
      </div>

      {/* 3. Section Filter Tabs */}
      <div
        style={{
          display: "flex",
          gap: 8,
          alignItems: "center",
          borderBottom: "1px solid var(--cc-border)",
          paddingBottom: 6,
        }}
      >
        <button
          className={`cc-btn${activeTab === "ALL" ? " cc-btn-primary" : ""}`}
          style={{ fontSize: 12, padding: "6px 14px" }}
          onClick={() => setActiveTab("ALL")}
        >
          <i className="bi bi-grid-fill" /> All Working Channels ({allWorkingCameras.length})
        </button>
        <button
          className={`cc-btn${activeTab === "FRS" ? " cc-btn-primary" : ""}`}
          style={{
            fontSize: 12,
            padding: "6px 14px",
            borderColor: activeTab === "FRS" ? "var(--cc-accent)" : "var(--cc-blue-border)",
            color: activeTab === "FRS" ? "#fff" : "var(--cc-accent)",
          }}
          onClick={() => setActiveTab("FRS")}
        >
          <i className="bi bi-person-bounding-box" /> FRS Cameras ({frsCameras.length})
        </button>
        <button
          className={`cc-btn${activeTab === "CROWD" ? " cc-btn-primary" : ""}`}
          style={{ fontSize: 12, padding: "6px 14px" }}
          onClick={() => setActiveTab("CROWD")}
        >
          <i className="bi bi-people-fill" /> Crowd Cameras ({crowdCameras.length})
        </button>

        {/* Search */}
        <div style={{ marginLeft: "auto", position: "relative", minWidth: 220 }}>
          <i
            className="bi bi-search"
            style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--cc-text-muted)", fontSize: 12 }}
          />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter working cameras..."
            style={{
              width: "100%",
              padding: "6px 10px 6px 30px",
              background: "var(--cc-bg-input)",
              border: "1px solid var(--cc-border)",
              borderRadius: "var(--cc-radius)",
              color: "var(--cc-text-primary)",
              fontSize: 12,
              boxSizing: "border-box",
            }}
          />
        </div>
      </div>

      {/* 3.1 Zone Filter Bar — Select Zone A, B, C, or D to view cameras assigned to that zone only */}
      <div
        style={{
          display: "flex",
          gap: 8,
          alignItems: "center",
          flexWrap: "wrap",
          padding: "8px 12px",
          background: "var(--cc-bg-secondary)",
          borderRadius: "var(--cc-radius)",
          border: "1px solid var(--cc-border)",
        }}
      >
        <div style={{ fontSize: 11, fontWeight: 700, color: "var(--cc-text-muted)", display: "flex", alignItems: "center", gap: 5, marginRight: 4 }}>
          <i className="bi bi-geo-alt-fill" style={{ color: "#58a6ff" }} />
          ZONE FILTER:
        </div>
        <button
          type="button"
          className={`cc-btn${selectedZone === "ALL" ? " cc-btn-primary" : ""}`}
          style={{ fontSize: 11, padding: "4px 12px", borderRadius: 20 }}
          onClick={() => setSelectedZone("ALL")}
        >
          All Zones ({allUnfilteredCameras.length})
        </button>
        {ZONE_PRESETS.map((z) => {
          const isSel = selectedZone === z.code;
          const count = getZoneCamCount(z.code);
          return (
            <button
              key={z.code}
              type="button"
              className="cc-btn"
              style={{
                fontSize: 11,
                padding: "4px 12px",
                borderRadius: 20,
                border: isSel ? `2px solid ${z.color}` : `1px solid ${z.color}40`,
                background: isSel ? `${z.color}25` : "transparent",
                color: isSel ? "#fff" : z.color,
                fontWeight: isSel ? 700 : 500,
                display: "flex",
                alignItems: "center",
                gap: 6,
                transition: "all 0.15s ease",
              }}
              onClick={() => setSelectedZone(z.code)}
            >
              <i className={`bi ${z.icon}`} style={{ color: z.color, fontSize: 11 }} />
              <span>{z.name}</span>
              <span
                style={{
                  fontSize: 9.5,
                  padding: "1px 6px",
                  borderRadius: 10,
                  background: isSel ? z.color : `${z.color}22`,
                  color: isSel ? "#000" : z.color,
                  fontWeight: 800,
                  marginLeft: 2,
                }}
              >
                {count}
              </span>
            </button>
          );
        })}

        {selectedZone !== "ALL" && (
          <button
            type="button"
            className="cc-btn"
            style={{
              marginLeft: "auto",
              fontSize: 10,
              padding: "2px 8px",
              color: "var(--cc-text-muted)",
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
            onClick={() => setSelectedZone("ALL")}
          >
            <i className="bi bi-x-circle" /> Reset to All Zones
          </button>
        )}
      </div>

      {loading ? (
        <LoadingState message="Loading live operational cameras..." />
      ) : allWorkingCameras.length === 0 ? (
        selectedZone !== "ALL" && allUnfilteredCameras.length > 0 ? (
          <div
            className="cc-card"
            style={{
              textAlign: "center",
              padding: "48px 24px",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 14,
              background: "var(--cc-bg-secondary)",
              border: "1px solid var(--cc-border)",
              borderRadius: "var(--cc-radius)",
            }}
          >
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: "50%",
                background: "rgba(88, 166, 255, 0.1)",
                border: "1px solid rgba(88, 166, 255, 0.25)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <i className="bi bi-geo-alt-fill" style={{ fontSize: 26, color: "var(--cc-accent)" }} />
            </div>
            <div>
              <div style={{ fontSize: 16, fontWeight: 700, color: "var(--cc-text-primary)", marginBottom: 6 }}>
                No Active Cameras in {ZONE_PRESETS.find((z) => z.code === selectedZone)?.name || selectedZone}
              </div>
              <div style={{ fontSize: 12, color: "var(--cc-text-muted)", maxWidth: 480, lineHeight: 1.5 }}>
                No camera stream is currently assigned to this zone ({ZONE_PRESETS.find((z) => z.code === selectedZone)?.label || ""}). You can switch an existing camera's zone or add a new RTSP camera stream assigned to this zone.
              </div>
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button
                className="cc-btn cc-btn-primary"
                onClick={() => setSelectedZone("ALL")}
                style={{ padding: "8px 16px", fontSize: 12 }}
              >
                View All Zones ({allUnfilteredCameras.length} cameras)
              </button>
              <button
                className="cc-btn cc-btn-secondary"
                onClick={() => {
                  setAddForm((f) => ({ ...f, camera_type: "CROWD", ai_purposes: ["ZONE"], zone_code: selectedZone }));
                  setShowAddModal(true);
                }}
                style={{ padding: "8px 16px", fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}
              >
                <i className="bi bi-plus-circle-fill" /> Add Stream to {ZONE_PRESETS.find((z) => z.code === selectedZone)?.name || "Zone"}
              </button>
            </div>
          </div>
        ) : (
          <div
            className="cc-card"
            style={{
              textAlign: "center",
              padding: "60px 24px",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 16,
              background: "var(--cc-bg-secondary)",
              border: "1px solid var(--cc-border)",
              borderRadius: "var(--cc-radius)",
            }}
          >
            <div
              style={{
                width: 64,
                height: 64,
                borderRadius: "50%",
                background: "rgba(88, 166, 255, 0.1)",
                border: "1px solid rgba(88, 166, 255, 0.25)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <i className="bi bi-camera-video-off" style={{ fontSize: 30, color: "var(--cc-accent)" }} />
            </div>
            <div>
              <div style={{ fontSize: 17, fontWeight: 700, color: "var(--cc-text-primary)", marginBottom: 6 }}>
                No Active RTSP Cameras Connected
              </div>
              <div style={{ fontSize: 13, color: "var(--cc-text-muted)", maxWidth: 480, lineHeight: 1.5 }}>
                Placeholder and dummy screens have been removed. Connect your RTSP stream URL to immediately launch live streaming with Multi-Purpose Crowd AI (Entry/Exit, Zone Density, Queue).
              </div>
            </div>
            <button
              className="cc-btn cc-btn-primary"
              onClick={() => setShowAddModal(true)}
              style={{ padding: "9px 20px", fontSize: 13, display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}
            >
              <i className="bi bi-plus-circle-fill" /> Connect Live RTSP Stream
            </button>
          </div>
        )
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          {/* ============================================================ */}
          {/* SECTION 1: FRS FACIAL RECOGNITION CAMERAS                    */}
          {/* ============================================================ */}
          {(activeTab === "ALL" || activeTab === "FRS") && (
            <div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 12,
                  paddingBottom: 6,
                  borderBottom: "1px solid var(--cc-blue-border)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <i className="bi bi-person-bounding-box" style={{ fontSize: 18, color: "var(--cc-accent)" }} />
                  <span style={{ fontSize: 14, fontWeight: 700, color: "var(--cc-text-primary)", letterSpacing: "0.03em" }}>
                    FRS Facial Recognition Cameras
                  </span>
                  <span
                    style={{
                      fontSize: 9,
                      padding: "2px 6px",
                      background: "var(--cc-blue-dim)",
                      border: "1px solid var(--cc-blue-border)",
                      borderRadius: "var(--cc-radius-sm)",
                      color: "var(--cc-accent)",
                      fontWeight: 800,
                    }}
                  >
                    BIOMETRIC RECOGNITION ACTIVE ({frsCameras.length})
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>
                  InsightFace Buffalo_L 512-D real-time facial matching
                </div>
              </div>

              {frsCameras.length === 0 ? (
                <div className="cc-card" style={{ textAlign: "center", padding: "30px 16px" }}>
                  <i className="bi bi-person-x" style={{ fontSize: 28, color: "var(--cc-text-muted)", marginBottom: 6 }} />
                  <div style={{ fontSize: 12, color: "var(--cc-text-muted)" }}>No FRS cameras matched.</div>
                </div>
              ) : (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: `repeat(${gridCols}, minmax(0, 1fr))`,
                    gap: 12,
                  }}
                >
                  {frsCameras.map((cam) => (
                    <CameraCard
                      key={cam.id}
                      camera={cam}
                      onSelect={(c) => setFullscreenCamera(c)}
                      onFullscreen={(c) => setFullscreenCamera(c)}
                      onToggleFrs={handleToggleFrs}
                      onRequestZoneSwitch={handleOpenZoneSwitch}
                    />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ============================================================ */}
          {/* SECTION 2: CROWD SURVEILLANCE & DENSITY CAMERAS               */}
          {/* ============================================================ */}
          {(activeTab === "ALL" || activeTab === "CROWD") && (
            <div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 12,
                  paddingBottom: 6,
                  borderBottom: "1px solid var(--cc-border)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <i className="bi bi-people-fill" style={{ fontSize: 18, color: "var(--cc-green)" }} />
                  <span style={{ fontSize: 14, fontWeight: 700, color: "var(--cc-text-primary)", letterSpacing: "0.03em" }}>
                    Crowd Surveillance & Density Cameras
                  </span>
                  <span
                    style={{
                      fontSize: 9,
                      padding: "2px 6px",
                      background: "rgba(63, 185, 80, 0.15)",
                      border: "1px solid rgba(63, 185, 80, 0.3)",
                      borderRadius: "var(--cc-radius-sm)",
                      color: "var(--cc-green)",
                      fontWeight: 800,
                    }}
                  >
                    HEADCOUNT & FLOW MONITORING ({crowdCameras.length})
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>
                  Real-time occupancy, crowd density & bottleneck detection
                </div>
              </div>

              {crowdCameras.length === 0 ? (
                <div className="cc-card" style={{ textAlign: "center", padding: "30px 16px" }}>
                  <i className="bi bi-people" style={{ fontSize: 28, color: "var(--cc-text-muted)", marginBottom: 6 }} />
                  <div style={{ fontSize: 12, color: "var(--cc-text-muted)" }}>No crowd surveillance cameras matched.</div>
                </div>
              ) : (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: `repeat(${gridCols}, minmax(0, 1fr))`,
                    gap: 12,
                  }}
                >
                  {crowdCameras.map((cam) => {
                    const currentPurp = (cam.ai_purposes && cam.ai_purposes[0]) || "ENTRY_EXIT";
                    const meta = PURPOSE_META[currentPurp] || PURPOSE_META.ENTRY_EXIT;
                    return (
                      <CameraCard
                        key={cam.id}
                        camera={cam}
                        onSelect={(c) => setFullscreenCamera(c)}
                        onFullscreen={(c) => setFullscreenCamera(c)}
                        onToggleFrs={handleToggleFrs}
                        onToggleCrowdAI={handleToggleCrowdAI}
                        onRequestReassign={handleOpenReassign}
                        onRequestZoneSwitch={handleOpenZoneSwitch}
                        onConfigureROI={(c) => setActiveROIEditor({
                          camera: c,
                          profile_id: meta.profile_id,
                          profile_name: meta.profile_name,
                          initial_tool: meta.initial_tool,
                          initial_objective: currentPurp,
                        })}
                      />
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 4. Add Camera Modal */}
      {showAddModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.75)",
            backdropFilter: "blur(3px)",
            zIndex: 1000,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div className="cc-card" style={{ width: 500, padding: 24, position: "relative" }}>
            <button
              onClick={() => { setShowAddModal(false); setAddError(""); }}
              style={{ position: "absolute", top: 14, right: 14, background: "none", border: "none", color: "var(--cc-text-muted)", fontSize: 18, cursor: "pointer" }}
            >
              <i className="bi bi-x-lg" />
            </button>
            <div className="cc-section-title" style={{ marginBottom: 6, display: "flex", alignItems: "center", gap: 8 }}>
              <i className="bi bi-camera-video-fill" style={{ color: "var(--cc-accent)" }} />
              <span>Add Live RTSP Camera</span>
            </div>
            <div style={{ fontSize: 11, color: "var(--cc-text-muted)", marginBottom: 16 }}>
              Connect a real RTSP stream URL to immediately add a working camera to the grid.
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {/* Camera Type Selector */}
              <div>
                <div className="cc-label" style={{ marginBottom: 6 }}>Camera Purpose / Section</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <button
                    type="button"
                    className={`cc-btn${addForm.camera_type === "FRS" ? " cc-btn-primary" : ""}`}
                    style={{ padding: "8px 12px", justifyContent: "center", fontSize: 12 }}
                    onClick={() => setAddForm((f) => ({ ...f, camera_type: "FRS", is_frs: true, name: "Khairatabad Gate FRS Camera" }))}
                  >
                    <i className="bi bi-person-bounding-box" /> FRS Camera
                  </button>
                  <button
                    type="button"
                    className={`cc-btn${addForm.camera_type === "CROWD" ? " cc-btn-primary" : ""}`}
                    style={{ padding: "8px 12px", justifyContent: "center", fontSize: 12 }}
                    onClick={() => setAddForm((f) => ({ ...f, camera_type: "CROWD", is_frs: false, name: "Main Pandal Crowd Camera" }))}
                  >
                    <i className="bi bi-people-fill" /> Crowd Camera
                  </button>
                </div>
              </div>

              {/* If Crowd Camera is chosen: Multi-Choice Purpose Profile (Up to 2) */}
              {addForm.camera_type === "CROWD" && (
                <div style={{ background: "rgba(15, 23, 42, 0.75)", padding: 12, borderRadius: 8, border: "1px solid var(--cc-border)" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                    <div className="cc-label" style={{ marginBottom: 0, color: "var(--cc-text-primary)", fontWeight: 700 }}>
                      Crowd Functionalities (Select 1 or 2):
                    </div>
                    <span style={{ fontSize: 10, color: (addForm.ai_purposes?.length || 0) === 2 ? "var(--cc-green)" : "var(--cc-accent)", fontWeight: 700 }}>
                      {addForm.ai_purposes?.length || 0}/2 Active
                    </span>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 8 }}>
                    {[
                      {
                        key: "ENTRY",
                        title: "1. Entry Gate (IN Only)",
                        icon: "bi-box-arrow-in-right",
                        color: "#3fb950",
                        desc: "ఎంట్రీ గేట్ వద్ద లోపలికి వచ్చే భక్తులను మాత్రమే లెక్కిస్తుంది (Dedicated Entry Gate Camera)",
                      },
                      {
                        key: "EXIT",
                        title: "2. Exit Gate (OUT Only)",
                        icon: "bi-box-arrow-right",
                        color: "#f85149",
                        desc: "ఎగ్జిట్ గేట్ వద్ద బయటకు వెళ్ళే భక్తులను మాత్రమే లెక్కిస్తుంది (Dedicated Exit Gate Camera)",
                      },
                      {
                        key: "ENTRY_EXIT",
                        title: "3. Two-Way Gate (IN & OUT)",
                        icon: "bi-arrow-left-right",
                        color: "#bc8cff",
                        desc: "రెండు వైపులా ప్రయాణించే గేట్ వద్ద IN & OUT రెండింటినీ లెక్కిస్తుంది (Bi-directional)",
                      },
                      {
                        key: "ZONE",
                        title: "4. Zone Density Monitoring",
                        icon: "bi-bounding-box",
                        color: "#58a6ff",
                        desc: "ఆవరణ లేదా మండపంలో జనం సాంద్రత (Density) & Capacity % లెక్కిస్తుంది",
                      },
                      {
                        key: "QUEUE",
                        title: "5. Queue Management",
                        icon: "bi-people",
                        color: "#d29922",
                        desc: "క్యూ లైన్ బారికేడ్లలో భక్తుల సంఖ్య & కదలిక వేగం ట్రాక్ చేస్తుంది",
                      },
                    ].map((item) => {
                      const isChecked = (addForm.ai_purposes || []).includes(item.key);
                      return (
                        <div
                          key={item.key}
                          onClick={() => {
                            setAddForm((prev) => {
                              const curr = prev.ai_purposes || [];
                              let next = [];
                              if (curr.includes(item.key)) {
                                if (curr.length <= 1) return prev; // keep at least 1
                                next = curr.filter((k) => k !== item.key);
                              } else {
                                if (curr.length >= 2) {
                                  next = [curr[1], item.key];
                                } else {
                                  next = [...curr, item.key];
                                }
                              }
                              let autoName = prev.name;
                              if (!autoName || autoName.includes("Gate") || autoName.includes("Camera")) {
                                if (next.includes("ENTRY") && !next.includes("EXIT")) autoName = "North Entry Gate Camera";
                                else if (next.includes("EXIT") && !next.includes("ENTRY")) autoName = "South Exit Gate Camera";
                                else if (next.includes("ZONE")) autoName = "Main Pandal Zone Camera";
                                else if (next.includes("QUEUE")) autoName = "Darshan Queue Camera";
                              }
                              return { ...prev, ai_purposes: next, name: autoName };
                            });
                          }}
                          style={{
                            padding: "8px 12px",
                            borderRadius: 6,
                            cursor: "pointer",
                            border: isChecked ? `2px solid ${item.color}` : "1px solid var(--cc-border)",
                            background: isChecked ? `${item.color}18` : "transparent",
                            transition: "all 0.15s ease",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                          }}
                        >
                          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <i className={`bi ${item.icon}`} style={{ fontSize: 16, color: isChecked ? item.color : "var(--cc-text-muted)" }} />
                            <div>
                              <div style={{ fontWeight: 700, fontSize: 12, color: isChecked ? item.color : "var(--cc-text-primary)" }}>
                                {item.title}
                              </div>
                              <div style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>
                                {item.desc}
                              </div>
                            </div>
                          </div>
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={() => {}}
                            style={{ width: 16, height: 16, accentColor: item.color, cursor: "pointer" }}
                          />
                        </div>
                      );
                    })}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 8 }}>
                    <i className="bi bi-info-circle" style={{ marginRight: 4 }} />
                    Single camera can run <strong>up to 2 functionalities</strong> concurrently (e.g. Entry Gate + Zone Density, or Exit Gate + Queue).
                  </div>
                </div>
              )}

              {/* Zone Assignment — ONLY displayed when Zone Density Monitoring (ZONE) is selected */}
              {addForm.camera_type === "CROWD" && (addForm.ai_purposes || []).includes("ZONE") && (
                <div style={{ background: "rgba(15,23,42,0.75)", padding: 12, borderRadius: 8, border: "1px solid var(--cc-border)" }}>
                  <div className="cc-label" style={{ marginBottom: 8, fontWeight: 700, fontSize: 11, display: "flex", alignItems: "center", gap: 6 }}>
                    <i className="bi bi-geo-alt-fill" style={{ color: "#58a6ff" }} /> Assign to Zone:
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                    {ZONE_PRESETS.map((z) => (
                      <div
                        key={z.code}
                        onClick={() => setAddForm((f) => ({ ...f, zone_code: z.code }))}
                        style={{
                          padding: "8px 10px",
                          borderRadius: 6,
                          cursor: "pointer",
                          border: addForm.zone_code === z.code ? `2px solid ${z.color}` : "1px solid var(--cc-border)",
                          background: addForm.zone_code === z.code ? `${z.color}22` : "transparent",
                          transition: "all 0.15s",
                        }}
                      >
                        <div style={{ fontWeight: 700, fontSize: 11, color: addForm.zone_code === z.code ? z.color : "var(--cc-text-primary)", display: "flex", alignItems: "center", gap: 5 }}>
                          <i className={`bi ${z.icon}`} style={{ color: z.color }} /> {z.name}
                        </div>
                        <div style={{ fontSize: 9.5, color: "var(--cc-text-muted)", marginTop: 2 }}>{z.label}</div>
                        <div style={{ fontSize: 9, color: "var(--cc-text-muted)", fontFamily: "var(--cc-font-mono)" }}>Cap: {z.capacity.toLocaleString()}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <div className="cc-label" style={{ marginBottom: 4 }}>Camera Location Name</div>
                <input
                  value={addForm.name}
                  onChange={(e) => setAddForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder="e.g. North Gate Entry Camera"
                  style={{ width: "100%", padding: "8px 10px", background: "var(--cc-bg-input)", border: "1px solid var(--cc-border)", borderRadius: "var(--cc-radius)", color: "var(--cc-text-primary)", fontSize: 13, boxSizing: "border-box" }}
                />
              </div>

              <div>
                <div className="cc-label" style={{ marginBottom: 4 }}>RTSP Stream URL</div>
                <input
                  value={addForm.rtsp_url}
                  onChange={(e) => setAddForm((f) => ({ ...f, rtsp_url: e.target.value }))}
                  placeholder="rtsp://admin:password@ip:554/stream"
                  style={{ width: "100%", padding: "8px 10px", background: "var(--cc-bg-input)", border: "1px solid var(--cc-border)", borderRadius: "var(--cc-radius)", color: "var(--cc-text-primary)", fontSize: 12, fontFamily: "var(--cc-font-mono)", boxSizing: "border-box" }}
                />
              </div>

              {/* Quick Presets */}
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <button
                  type="button"
                  className="cc-btn"
                  style={{ fontSize: 10, padding: "3px 8px" }}
                  onClick={() => setAddForm((f) => ({ ...f, rtsp_url: DEFAULT_RTSP }))}
                >
                  <i className="bi bi-lightning-fill" style={{ color: "var(--cc-accent)" }} /> Default Camera RTSP
                </button>
                <button
                  type="button"
                  className="cc-btn"
                  style={{ fontSize: 10, padding: "3px 8px" }}
                  onClick={() => setAddForm((f) => ({ ...f, rtsp_url: "0", name: "Local USB Webcam" }))}
                >
                  <i className="bi bi-webcam-fill" /> USB Webcam (0)
                </button>
              </div>

              {addError && (
                <div style={{ fontSize: 11, color: "var(--cc-red)", padding: "8px 10px", background: "var(--cc-red-dim)", border: "1px solid var(--cc-red-border)", borderRadius: "var(--cc-radius-sm)" }}>
                  <i className="bi bi-exclamation-octagon-fill" style={{ marginRight: 6 }} />
                  {addError}
                </div>
              )}

              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 6 }}>
                <button className="cc-btn" onClick={() => { setShowAddModal(false); setAddError(""); }}>
                  Cancel
                </button>
                <button className="cc-btn cc-btn-primary" onClick={handleAddCamera} disabled={addLoading}>
                  {addLoading ? (
                    <><i className="bi bi-hourglass-split" /> Initializing Stream...</>
                  ) : (
                    <><i className="bi bi-play-fill" /> Add & Start Stream</>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 5. Full-Screen Live Video Modal / Lightbox */}
      {fullscreenCamera && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(3, 7, 18, 0.94)",
            backdropFilter: "blur(8px)",
            zIndex: 1200,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: isBrowserFullscreen ? 0 : 20,
          }}
          onClick={() => {
            if (!document.fullscreenElement) {
              setFullscreenCamera(null);
              setEnrollStatus(null);
            }
          }}
        >
          <div
            ref={fullscreenContainerRef}
            className="cc-card"
            style={{
              width: isBrowserFullscreen ? "100vw" : "94vw",
              maxWidth: isBrowserFullscreen ? "none" : 1280,
              height: isBrowserFullscreen ? "100vh" : "90vh",
              maxHeight: isBrowserFullscreen ? "none" : 880,
              padding: 0,
              overflow: "hidden",
              display: "flex",
              flexDirection: "column",
              background: "#030712",
              border: "1px solid var(--cc-blue-border)",
              boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.9)",
              borderRadius: isBrowserFullscreen ? 0 : "var(--cc-radius-lg)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "12px 18px",
                borderBottom: "1px solid var(--cc-border)",
                background: "rgba(15, 23, 42, 0.85)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <i
                  className={`bi ${fullscreenCamera.is_frs || fullscreenCamera.is_frs_camera ? "bi-person-bounding-box" : "bi-camera-video-fill"}`}
                  style={{ fontSize: 20, color: "var(--cc-accent)" }}
                />
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "var(--cc-text-primary)", display: "flex", alignItems: "center", gap: 8 }}>
                    <span>{fullscreenCamera.name || fullscreenCamera.label}</span>
                    <span style={{ fontFamily: "var(--cc-font-mono)", fontSize: 11, color: "var(--cc-accent)", background: "var(--cc-blue-dim)", padding: "1px 6px", borderRadius: 3, border: "1px solid var(--cc-blue-border)" }}>
                      {fullscreenCamera.id || fullscreenCamera.camera_code}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>
                    {fullscreenCamera.zone_code || "ZONE-A"} • {fullscreenCamera.resolution || "1080p"} HD • 25 FPS RTSP Stream
                  </div>
                </div>
              </div>

              {/* Controls */}
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {!(fullscreenCamera.camera_type === "CROWD" || !fullscreenCamera.is_frs) ? (
                  /* FRS Camera: Keep existing FRS Active / Enable FRS button unchanged */
                  <button
                    className="cc-btn"
                    style={{
                      fontSize: 11,
                      padding: "4px 10px",
                      fontWeight: 700,
                      background: (fullscreenCamera.is_frs || fullscreenCamera.is_frs_camera) ? "var(--cc-blue-dim)" : "transparent",
                      color: (fullscreenCamera.is_frs || fullscreenCamera.is_frs_camera) ? "var(--cc-accent)" : "var(--cc-text-muted)",
                      borderColor: (fullscreenCamera.is_frs || fullscreenCamera.is_frs_camera) ? "var(--cc-blue-border)" : "var(--cc-border)",
                    }}
                    onClick={() => handleToggleFrs(fullscreenCamera, !(fullscreenCamera.is_frs || fullscreenCamera.is_frs_camera))}
                  >
                    <i className={`bi ${(fullscreenCamera.is_frs || fullscreenCamera.is_frs_camera) ? "bi-person-check-fill" : "bi-person-bounding-box"}`} />
                    {(fullscreenCamera.is_frs || fullscreenCamera.is_frs_camera) ? "FRS ACTIVE" : "ENABLE FRS"}
                  </button>
                ) : (
                  /* Crowd Camera: NEVER show "ENABLE FRS"! Show "ENABLE AI MODEL" / "CROWD AI ACTIVE" */
                  <button
                    className="cc-btn"
                    style={{
                      fontSize: 11,
                      padding: "4px 10px",
                      fontWeight: 700,
                      background: fullscreenCamera.is_running ? "rgba(63, 185, 80, 0.15)" : "transparent",
                      color: fullscreenCamera.is_running ? "var(--cc-green)" : "var(--cc-text-primary)",
                      borderColor: fullscreenCamera.is_running ? "rgba(63, 185, 80, 0.4)" : "var(--cc-border)",
                      display: "flex",
                      alignItems: "center",
                      gap: 5,
                    }}
                    onClick={async () => {
                      const code = fullscreenCamera.camera_code || fullscreenCamera.id.replace("-CROWD", "");
                      try {
                        if (fullscreenCamera.is_running) {
                          await switchCameraAIMode(code, "IDLE");
                        } else {
                          await switchCameraAIMode(code, "CROWD");
                        }
                        await Promise.all([loadDbCameras(), loadEngineCameras()]);
                        setFullscreenCamera((prev) => prev ? ({ ...prev, is_running: !prev.is_running, status: !prev.is_running ? "online" : "stopped" }) : null);
                      } catch (err) {
                        console.error("Failed to toggle Crowd AI model:", err);
                      }
                    }}
                  >
                    <i className={`bi ${fullscreenCamera.is_running ? "bi-check-circle-fill" : "bi-cpu-fill"}`} />
                    {fullscreenCamera.is_running ? "CROWD AI ACTIVE" : "ENABLE AI MODEL"}
                  </button>
                )}

                <button
                  className="cc-btn cc-btn-primary"
                  onClick={toggleBrowserFullscreen}
                  style={{ fontSize: 11, padding: "4px 10px", display: "flex", alignItems: "center", gap: 4 }}
                  title="Toggle 100% monitor fullscreen"
                >
                  <i className={`bi ${isBrowserFullscreen ? "bi-fullscreen-exit" : "bi-arrows-fullscreen"}`} />
                  {isBrowserFullscreen ? "Exit Fullscreen" : "Monitor Fullscreen"}
                </button>

                <button
                  className="cc-btn cc-btn-secondary"
                  onClick={() => navigate(`/cameras/${fullscreenCamera.id || fullscreenCamera.camera_code}`)}
                  style={{ fontSize: 11, padding: "4px 10px", display: "flex", alignItems: "center", gap: 4 }}
                >
                  <i className="bi bi-gear-fill" /> Diagnostics
                </button>

                <button
                  onClick={() => {
                    setFullscreenCamera(null);
                    setEnrollStatus(null);
                  }}
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--cc-text-muted)",
                    fontSize: 20,
                    cursor: "pointer",
                    padding: "2px 8px",
                  }}
                  title="Close (Esc)"
                >
                  <i className="bi bi-x-lg" />
                </button>
              </div>
            </div>

            {/* Video Viewport */}
            <div
              style={{
                flex: 1,
                position: "relative",
                background: "#000",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                overflow: "hidden",
                minHeight: 0,
              }}
            >
              {!modalStreamError ? (
                <img
                  key={modalRetry}
                  src={
                    fullscreenCamera.stream_url
                      ? (fullscreenCamera.stream_url.startsWith("http")
                          ? `${fullscreenCamera.stream_url}?t=${modalRetry}`
                          : `${BACKEND}${fullscreenCamera.stream_url}?t=${modalRetry}`)
                      : (fullscreenCamera.is_frs || fullscreenCamera.is_frs_camera
                          ? `${BACKEND}/api/v1/frs-engine/cameras/${fullscreenCamera.camera_code || fullscreenCamera.id}/stream?t=${modalRetry}`
                          : `${BACKEND}/api/v1/frs-engine/cameras/${(fullscreenCamera.camera_code || fullscreenCamera.id).replace("-CROWD", "")}-CROWD/stream?t=${modalRetry}`)
                  }
                  alt={`Live Fullscreen ${fullscreenCamera.id}`}
                  style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }}
                  onError={() => setModalStreamError(true)}
                />
              ) : (
                <div style={{ textAlign: "center", padding: 30, display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
                  <i className="bi bi-camera-video-off-fill" style={{ fontSize: 40, color: "var(--cc-yellow)" }} />
                  <div style={{ fontSize: 14, fontWeight: 700, color: "var(--cc-text-primary)" }}>Stream Connection Paused</div>
                  <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>Awaiting RTSP stream frames from camera...</div>
                  <button
                    className="cc-btn cc-btn-primary"
                    onClick={() => {
                      setModalStreamError(false);
                      setModalRetry((r) => r + 1);
                    }}
                    style={{ fontSize: 11, padding: "4px 14px", marginTop: 6 }}
                  >
                    <i className="bi bi-arrow-clockwise" /> Reconnect Live Stream
                  </button>
                </div>
              )}

              {/* Status Badges Overlay */}
              <div style={{ position: "absolute", top: 12, left: 16, display: "flex", gap: 8, alignItems: "center" }}>
                <div style={{ fontSize: 10, color: "var(--cc-green)", fontWeight: 700, background: "rgba(0,0,0,0.75)", padding: "3px 8px", borderRadius: 3, backdropFilter: "blur(4px)" }}>
                  ● LIVE BROADCAST
                </div>
                <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 10, color: "#fff", background: "rgba(0,0,0,0.75)", padding: "3px 8px", borderRadius: 3, backdropFilter: "blur(4px)" }}>
                  25 FPS • 1080p HD
                </div>
              </div>

              {(fullscreenCamera.is_frs || fullscreenCamera.is_frs_camera) ? (
                <div
                  style={{
                    position: "absolute",
                    top: 12,
                    right: 16,
                    fontSize: 10,
                    color: "var(--cc-accent)",
                    fontWeight: 800,
                    background: "rgba(0,0,0,0.8)",
                    padding: "3px 8px",
                    borderRadius: 3,
                    border: "1px solid rgba(56,189,248,0.4)",
                    backdropFilter: "blur(4px)",
                  }}
                >
                  FRS BIOMETRIC AI DETECTING
                </div>
              ) : (
                <div
                  style={{
                    position: "absolute",
                    top: 12,
                    right: 16,
                    fontSize: 10,
                    color: "var(--cc-green)",
                    fontWeight: 800,
                    background: "rgba(0,0,0,0.8)",
                    padding: "3px 8px",
                    borderRadius: 3,
                    border: "1px solid rgba(63,185,80,0.4)",
                    backdropFilter: "blur(4px)",
                  }}
                >
                  CROWD SURVEILLANCE & DENSITY
                </div>
              )}
            </div>

            {/* Quick Actions Bar */}
            <div
              style={{
                padding: "10px 18px",
                borderTop: "1px solid var(--cc-border)",
                background: "rgba(15, 23, 42, 0.95)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 16,
                flexWrap: "wrap",
              }}
            >
              {(fullscreenCamera.is_frs || fullscreenCamera.is_frs_camera) ? (
                <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 320 }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "var(--cc-accent)", whiteSpace: "nowrap", display: "flex", alignItems: "center", gap: 6 }}>
                    <i className="bi bi-camera-fill" /> 1-Click Face Enroll:
                  </span>
                  <input
                    value={enrollName}
                    onChange={(e) => setEnrollName(e.target.value)}
                    placeholder="Enter person name to enroll (e.g. Ramesh Kumar)..."
                    style={{
                      flex: 1,
                      maxWidth: 280,
                      padding: "6px 10px",
                      background: "var(--cc-bg-input)",
                      border: "1px solid var(--cc-border)",
                      borderRadius: "var(--cc-radius)",
                      color: "var(--cc-text-primary)",
                      fontSize: 12,
                    }}
                    onKeyDown={(e) => e.key === "Enter" && handleEnrollFromCamera()}
                  />
                  <button
                    className="cc-btn cc-btn-primary"
                    onClick={handleEnrollFromCamera}
                    disabled={enrollLoading || !enrollName.trim()}
                    style={{ fontSize: 11, padding: "6px 12px", whiteSpace: "nowrap", display: "flex", alignItems: "center", gap: 6 }}
                  >
                    {enrollLoading ? (
                      <><i className="bi bi-hourglass-split" /> Enrolling...</>
                    ) : (
                      <><i className="bi bi-person-plus-fill" /> Snap & Enroll Face</>
                    )}
                  </button>
                </div>
              ) : (() => {
                const purps = (fullscreenCamera.ai_purposes && fullscreenCamera.ai_purposes.length > 0)
                  ? fullscreenCamera.ai_purposes
                  : ["ENTRY_EXIT"];
                return (
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flex: 1, flexWrap: "wrap" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      {purps.map((pKey) => {
                        const m = PURPOSE_META[pKey] || PURPOSE_META.ENTRY_EXIT;
                        return (
                          <span
                            key={pKey}
                            style={{
                              fontSize: 12,
                              fontWeight: 700,
                              color: m.color,
                              display: "flex",
                              alignItems: "center",
                              gap: 6,
                              padding: "3px 8px",
                              borderRadius: 4,
                              background: "rgba(0,0,0,0.4)",
                              border: `1px solid ${m.color}44`,
                            }}
                          >
                            <i className={`bi ${m.icon}`} /> {m.label}
                          </span>
                        );
                      })}
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      {purps.map((pKey) => {
                        const m = PURPOSE_META[pKey] || PURPOSE_META.ENTRY_EXIT;
                        return (
                          <button
                            key={pKey}
                            className="cc-btn cc-btn-secondary"
                            style={{
                              fontSize: 11,
                              padding: "5px 12px",
                              borderColor: m.color,
                              color: m.color,
                              display: "flex",
                              alignItems: "center",
                              gap: 6,
                              fontWeight: 600,
                            }}
                            onClick={() => setActiveROIEditor({
                              camera: fullscreenCamera,
                              profile_id: m.profile_id,
                              profile_name: m.profile_name,
                              initial_tool: m.initial_tool,
                              initial_objective: pKey,
                            })}
                            title={`Configure ROI / Lines for ${m.label}`}
                          >
                            <i className="bi bi-vector-pen" /> Configure {m.label} ROI
                          </button>
                        );
                      })}
                      <button
                        className="cc-btn"
                        style={{ fontSize: 11, padding: "5px 12px", borderColor: "rgba(227, 179, 65, 0.5)", color: "#e3b341", background: "rgba(227, 179, 65, 0.12)", display: "flex", alignItems: "center", gap: 6, fontWeight: 600 }}
                        onClick={() => handleOpenReassign(fullscreenCamera)}
                        title="Switch this camera to another purpose (Entry/Exit, Queue, Zone)"
                      >
                        <i className="bi bi-arrow-repeat" /> Switch Functionalities
                      </button>
                      <button
                        className="cc-btn"
                        style={{ fontSize: 11, padding: "5px 12px", borderColor: "rgba(88,166,255,0.4)", color: "#58a6ff", background: "rgba(88,166,255,0.10)", display: "flex", alignItems: "center", gap: 6, fontWeight: 600 }}
                        onClick={() => handleOpenZoneSwitch(fullscreenCamera)}
                        title="Reassign camera to a different zone (A/B/C/D)"
                      >
                        <i className="bi bi-geo-alt-fill" /> Switch Zone
                      </button>
                    </div>
                  </div>
                );
              })()}

              {enrollStatus && (
                <div
                  style={{
                    fontSize: 11,
                    padding: "4px 10px",
                    borderRadius: "var(--cc-radius-sm)",
                    background: enrollStatus.type === "success" ? "var(--cc-green-dim)" : "var(--cc-red-dim)",
                    color: enrollStatus.type === "success" ? "var(--cc-green)" : "var(--cc-red)",
                    border: `1px solid ${enrollStatus.type === "success" ? "var(--cc-green-border)" : "var(--cc-red-border)"}`,
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  <i className={`bi ${enrollStatus.type === "success" ? "bi-check-circle-fill" : "bi-exclamation-circle-fill"}`} />
                  {enrollStatus.message}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {activeROIEditor && (
        <ROIEditor
          camera={activeROIEditor.camera}
          profileId={activeROIEditor.profile_id}
          profileName={activeROIEditor.profile_name}
          initialTool={activeROIEditor.initial_tool}
          initialObjective={activeROIEditor.initial_objective}
          streamUrl={
            `${BACKEND}/api/v1/frs-engine/cameras/${(activeROIEditor.camera.camera_code || activeROIEditor.camera.id).replace("-CROWD", "").replace("-FRS", "")}/raw-stream`
          }
          onClose={() => setActiveROIEditor(null)}
          onSaved={async () => {
            await Promise.all([loadDbCameras(), loadEngineCameras()]);
          }}
        />
      )}

      {/* 5. Purpose Selection Dialog (when user clicks Switch Purpose) */}
      {reassignSelectModal.open && reassignSelectModal.camera && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.75)",
            backdropFilter: "blur(4px)",
            zIndex: 1050,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 16,
          }}
        >
          <div className="cc-card" style={{ width: 520, maxWidth: "95vw", padding: 22, position: "relative", border: "1px solid var(--cc-border)" }}>
            <button
              onClick={() => setReassignSelectModal({ open: false, camera: null, selectedPurposes: [] })}
              style={{ position: "absolute", top: 14, right: 14, background: "none", border: "none", color: "var(--cc-text-muted)", fontSize: 18, cursor: "pointer" }}
            >
              <i className="bi bi-x-lg" />
            </button>
            <div className="cc-section-title" style={{ marginBottom: 4, display: "flex", alignItems: "center", gap: 8 }}>
              <i className="bi bi-arrow-repeat" style={{ color: "#e3b341" }} />
              <span>Configure Crowd Functionalities</span>
            </div>
            <div style={{ fontSize: 11, color: "var(--cc-text-muted)", marginBottom: 14 }}>
              Camera: <strong style={{ color: "var(--cc-text-primary)" }}>{reassignSelectModal.camera.name || reassignSelectModal.camera.id}</strong> ({reassignSelectModal.camera.camera_code || reassignSelectModal.camera.id})
            </div>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10, padding: "8px 12px", background: "rgba(227, 179, 65, 0.08)", border: "1px solid rgba(227, 179, 65, 0.25)", borderRadius: 6 }}>
              <span style={{ fontSize: 11, color: "var(--cc-yellow)", fontWeight: 700 }}>
                Select 1 or 2 Functionalities:
              </span>
              <span style={{ fontSize: 10, color: (reassignSelectModal.selectedPurposes?.length || 0) === 2 ? "var(--cc-green)" : "var(--cc-yellow)", fontWeight: 800 }}>
                {reassignSelectModal.selectedPurposes?.length || 0}/2 Selected
              </span>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 18 }}>
              {[
                {
                  key: "ENTRY",
                  title: "1. Entry Gate (IN Only)",
                  icon: "bi-box-arrow-in-right",
                  color: "#3fb950",
                  desc: "ఎంట్రీ గేట్ వద్ద లోపలికి వచ్చే వారిని మాత్రమే లెక్కిస్తుంది (Counts entering footfall)",
                },
                {
                  key: "EXIT",
                  title: "2. Exit Gate (OUT Only)",
                  icon: "bi-box-arrow-right",
                  color: "#f85149",
                  desc: "ఎగ్జిట్ గేట్ వద్ద బయటకు వెళ్ళే వారిని మాత్రమే లెక్కిస్తుంది (Counts exiting footfall)",
                },
                {
                  key: "ENTRY_EXIT",
                  title: "3. Two-Way Gate (IN & OUT)",
                  icon: "bi-arrow-left-right",
                  color: "#bc8cff",
                  desc: "రెండు వైపులా ప్రయాణించే గేట్ వద్ద IN & OUT రెండింటినీ లెక్కిస్తుంది",
                },
                {
                  key: "ZONE",
                  title: "4. Zone Density Monitoring",
                  icon: "bi-bounding-box",
                  color: "#58a6ff",
                  desc: "ఆవరణ లేదా మండపంలో జనం సాంద్రత & Capacity % లెక్కిస్తుంది",
                },
                {
                  key: "QUEUE",
                  title: "5. Queue Management",
                  icon: "bi-people",
                  color: "#d29922",
                  desc: "క్యూ లైన్ బారికేడ్లలో భక్తుల సంఖ్య & కదలిక వేగం ట్రాక్ చేస్తుంది",
                },
              ].map((item) => {
                const isChecked = (reassignSelectModal.selectedPurposes || []).includes(item.key);
                return (
                  <div
                    key={item.key}
                    onClick={() => handleToggleReassignPurpose(item.key)}
                    style={{
                      padding: "10px 14px",
                      borderRadius: 8,
                      border: isChecked ? `2px solid ${item.color}` : "1px solid var(--cc-border)",
                      background: isChecked ? `${item.color}15` : "rgba(15, 23, 42, 0.6)",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      transition: "all 0.15s ease",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <div
                        style={{
                          width: 36,
                          height: 36,
                          borderRadius: 6,
                          background: `${item.color}20`,
                          color: item.color,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 18,
                        }}
                      >
                        <i className={`bi ${item.icon}`} />
                      </div>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: isChecked ? item.color : "var(--cc-text-primary)" }}>
                          {item.title}
                        </div>
                        <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>
                          {item.desc}
                        </div>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => {}}
                      style={{ width: 16, height: 16, accentColor: item.color, cursor: "pointer" }}
                    />
                  </div>
                );
              })}
            </div>

            {/* Zone Assignment — ONLY displayed when Zone Density Monitoring (ZONE) is selected */}
            {(reassignSelectModal.selectedPurposes || []).includes("ZONE") && (
              <div style={{ background: "rgba(15,23,42,0.75)", padding: 12, borderRadius: 8, border: "1px solid var(--cc-border)", marginBottom: 14 }}>
                <div className="cc-label" style={{ marginBottom: 8, fontWeight: 700, fontSize: 11, display: "flex", alignItems: "center", gap: 6 }}>
                  <i className="bi bi-geo-alt-fill" style={{ color: "#58a6ff" }} /> Assign to Zone:
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  {ZONE_PRESETS.map((z) => {
                    const isSelected = (reassignSelectModal.selectedZone || reassignSelectModal.camera?.zone_code || "ZONE-A") === z.code;
                    return (
                      <div
                        key={z.code}
                        onClick={() => setReassignSelectModal((prev) => ({ ...prev, selectedZone: z.code }))}
                        style={{
                          padding: "8px 10px",
                          borderRadius: 6,
                          cursor: "pointer",
                          border: isSelected ? `2px solid ${z.color}` : "1px solid var(--cc-border)",
                          background: isSelected ? `${z.color}22` : "transparent",
                          transition: "all 0.15s",
                        }}
                      >
                        <div style={{ fontWeight: 700, fontSize: 11, color: isSelected ? z.color : "var(--cc-text-primary)", display: "flex", alignItems: "center", gap: 5 }}>
                          <i className={`bi ${z.icon}`} style={{ color: z.color }} /> {z.name}
                        </div>
                        <div style={{ fontSize: 9.5, color: "var(--cc-text-muted)", marginTop: 2 }}>{z.label}</div>
                        <div style={{ fontSize: 9, color: "var(--cc-text-muted)", fontFamily: "var(--cc-font-mono)" }}>Cap: {z.capacity.toLocaleString()}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginBottom: 16, lineHeight: 1.5 }}>
              <i className="bi bi-info-circle" style={{ marginRight: 4 }} />
              Updating functionalities re-initializes the camera AI pipeline and allows configuring new ROIs.
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button
                type="button"
                className="cc-btn"
                onClick={() => setReassignSelectModal({ open: false, camera: null, selectedPurposes: [] })}
                disabled={reassignLoading}
                style={{ padding: "7px 16px", fontSize: 12 }}
              >
                Cancel
              </button>
              <button
                type="button"
                className="cc-btn cc-btn-primary"
                onClick={handleConfirmReassign}
                disabled={reassignLoading || (reassignSelectModal.selectedPurposes?.length || 0) === 0}
                style={{
                  padding: "7px 20px",
                  fontSize: 12,
                  background: "var(--cc-green)",
                  borderColor: "var(--cc-green)",
                  color: "#fff",
                  fontWeight: 700,
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                {reassignLoading ? (
                  <><i className="bi bi-hourglass-split" /> Saving...</>
                ) : (
                  <><i className="bi bi-check-circle-fill" /> Save & Apply Functionalities</>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ===== ZONE SWITCH MODAL ===== */}
      {zoneSwitchModal.open && zoneSwitchModal.camera && (
        <div
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.72)",
            display: "flex", alignItems: "center", justifyContent: "center",
            zIndex: 1100, padding: 16,
          }}
          onClick={(e) => { if (e.target === e.currentTarget) setZoneSwitchModal({ open: false, camera: null }); }}
        >
          <div
            style={{
              background: "var(--cc-bg-card)", border: "1px solid var(--cc-border)",
              borderRadius: 12, padding: "24px 24px 20px", maxWidth: 420, width: "100%",
              boxShadow: "0 24px 60px rgba(0,0,0,0.6)",
            }}
          >
            {/* Header */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
              <div style={{ width: 36, height: 36, borderRadius: 8, background: "rgba(88,166,255,0.15)", border: "1px solid rgba(88,166,255,0.35)", display: "flex", alignItems: "center", justifyContent: "center", color: "#58a6ff", fontSize: 18, flexShrink: 0 }}>
                <i className="bi bi-geo-alt-fill" />
              </div>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, color: "var(--cc-text-primary)" }}>Switch Zone Assignment</div>
                <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>
                  Camera: {zoneSwitchModal.camera.name || zoneSwitchModal.camera.id} ({zoneSwitchModal.camera.camera_code || zoneSwitchModal.camera.id})
                </div>
              </div>
            </div>

            <p style={{ fontSize: 12, color: "var(--cc-text-muted)", marginBottom: 14, lineHeight: 1.5 }}>
              Select the zone you want to assign this camera to. The live feed will immediately start contributing counts to the selected zone.
            </p>

            {/* Zone Tiles */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
              {ZONE_PRESETS.map((z) => {
                const isCurrent = (zoneSwitchModal.camera.zone_code || "ZONE-A") === z.code;
                return (
                  <button
                    key={z.code}
                    type="button"
                    disabled={zoneSwitchLoading}
                    onClick={() => handleConfirmZoneSwitch(z.code)}
                    style={{
                      padding: "12px 10px", borderRadius: 8, cursor: zoneSwitchLoading ? "not-allowed" : "pointer",
                      border: isCurrent ? `2px solid ${z.color}` : "1px solid var(--cc-border)",
                      background: isCurrent ? `${z.color}22` : "rgba(255,255,255,0.02)",
                      textAlign: "left", transition: "all 0.15s",
                    }}
                  >
                    <div style={{ fontWeight: 700, fontSize: 12, color: z.color, display: "flex", alignItems: "center", gap: 6 }}>
                      <i className={`bi ${z.icon}`} /> {z.name}
                      {isCurrent && <span style={{ fontSize: 9, background: `${z.color}33`, padding: "1px 5px", borderRadius: 3, marginLeft: "auto" }}>CURRENT</span>}
                    </div>
                    <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 3 }}>{z.label}</div>
                    <div style={{ fontSize: 9.5, color: "var(--cc-text-muted)", fontFamily: "var(--cc-font-mono)", marginTop: 2 }}>Cap: {z.capacity.toLocaleString()}</div>
                  </button>
                );
              })}
            </div>

            {/* Footer */}
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button
                type="button"
                className="cc-btn"
                onClick={() => setZoneSwitchModal({ open: false, camera: null })}
                disabled={zoneSwitchLoading}
                style={{ fontSize: 12, padding: "7px 18px" }}
              >
                {zoneSwitchLoading ? <><i className="bi bi-hourglass-split" /> Switching...</> : "Cancel"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
