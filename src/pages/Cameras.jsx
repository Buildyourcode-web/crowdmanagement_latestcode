// Cameras page — Working CCTV Wall divided into FRS & Crowd Surveillance Sections
import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import CameraCard from "../components/camera/CameraCard.jsx";
import { getCameras, getCameraStats, toggleCameraFRS } from "../services/cameraService.js";
import { LoadingState } from "../components/common/States.jsx";

const BACKEND = `http://${window.location.hostname}:8000`;
const DEFAULT_RTSP = "rtsp://admin:Veeru%40555@192.168.0.102:554/Streaming/Channels/101";

const GRID_SIZES = [
  { label: "4×", cols: 4 },
  { label: "3×", cols: 3 },
  { label: "2×", cols: 2 },
  { label: "1×", cols: 1 },
];

export default function Cameras() {
  const navigate = useNavigate();
  const [dbCameras, setDbCameras] = useState([]);
  const [engineCameras, setEngineCameras] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [activeTab, setActiveTab] = useState("ALL"); // "ALL", "FRS", "CROWD"
  const [gridCols, setGridCols] = useState(3);
  const [showAddModal, setShowAddModal] = useState(false);
  const [addForm, setAddForm] = useState({
    name: "Khairatabad Gate FRS Camera",
    rtsp_url: DEFAULT_RTSP,
    camera_type: "FRS",
    is_frs: true,
  });
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

  // Load active FRS / RTSP engine camera workers
  const loadEngineCameras = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND}/api/v1/frs-engine/cameras`);
      if (res.ok) {
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
          }))
        );
      }
    } catch (e) {
      console.warn("[Cameras] Engine cams fetch:", e);
    }
  }, []);

  // Load database cameras
  const loadDbCameras = useCallback(async () => {
    try {
      const [camsRes, statsRes] = await Promise.allSettled([
        getCameras({ page_size: 50 }),
        getCameraStats(),
      ]);
      const camsVal = camsRes.status === "fulfilled" ? camsRes.value : [];
      const statsVal = statsRes.status === "fulfilled" ? statsRes.value : null;
      const list = Array.isArray(camsVal) ? camsVal : (camsVal?.data || []);
      // Filter out any non-working / deleted cameras
      setDbCameras(list.filter((c) => c.status === "online" || c.status === "degraded"));
      if (statsVal) setStats(statsVal);
    } catch (e) {
      console.warn(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDbCameras();
    loadEngineCameras();
    const interval = setInterval(loadEngineCameras, 5000);
    return () => clearInterval(interval);
  }, [loadDbCameras, loadEngineCameras]);

  // Combine working cameras without duplicates
  const allWorkingCameras = [
    ...engineCameras,
    ...dbCameras
      .filter((dbCam) => !engineCameras.some((eng) => eng.id === dbCam.id || eng.id === dbCam.camera_code))
      .map((dbCam) => ({
        ...dbCam,
        // If it's CAM-KHB-001, connect it to the live engine stream
        stream_url: dbCam.id === "CAM-KHB-001" ? "/api/v1/frs-engine/cameras/CAM-KHB-001/stream" : dbCam.stream_url,
      })),
  ];

  // Apply search filter if any
  const searchedCameras = allWorkingCameras.filter((cam) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      (cam.id || "").toLowerCase().includes(q) ||
      (cam.name || "").toLowerCase().includes(q) ||
      (cam.label || "").toLowerCase().includes(q)
    );
  });

  // Divide into FRS and Crowd sections
  const frsCameras = searchedCameras.filter((c) => Boolean(c.is_frs_camera || c.is_frs || c.camera_type === "FRS"));
  const crowdCameras = searchedCameras.filter((c) => !Boolean(c.is_frs_camera || c.is_frs || c.camera_type === "FRS"));

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
        setShowAddModal(false);
        setAddForm({
          name: "Khairatabad Gate FRS Camera",
          rtsp_url: DEFAULT_RTSP,
          camera_type: "FRS",
          is_frs: true,
        });
        await loadEngineCameras();
        if (addForm.camera_type === "FRS") setActiveTab("FRS");
        else if (addForm.camera_type === "CROWD") setActiveTab("CROWD");
      }
    } catch (e) {
      setAddError("Backend connection error — check backend is running");
    } finally {
      setAddLoading(false);
    }
  };

  const handleToggleFrs = async (camera, enabled) => {
    try {
      await toggleCameraFRS(camera.id || camera.camera_code, enabled);
      await Promise.all([loadDbCameras(), loadEngineCameras()]);
      if (fullscreenCamera && (fullscreenCamera.id === camera.id || fullscreenCamera.camera_code === camera.camera_code)) {
        setFullscreenCamera((prev) => (prev ? { ...prev, is_frs_camera: enabled, is_frs: enabled, camera_type: enabled ? "FRS" : "CROWD" } : null));
      }
    } catch (e) {
      console.error("Failed to toggle camera FRS state:", e);
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

      {loading ? (
        <LoadingState message="Loading live operational cameras..." />
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
                  {crowdCameras.map((cam) => (
                    <CameraCard
                      key={cam.id}
                      camera={cam}
                      onSelect={(c) => setFullscreenCamera(c)}
                      onFullscreen={(c) => setFullscreenCamera(c)}
                      onToggleFrs={handleToggleFrs}
                    />
                  ))}
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
                      : `${BACKEND}/api/v1/frs-engine/cameras/${fullscreenCamera.id || fullscreenCamera.camera_code}/stream?t=${modalRetry}`
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

              {(fullscreenCamera.is_frs || fullscreenCamera.is_frs_camera) && (
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
              )}
            </div>

            {/* 1-Click Enrollment & Quick Actions Bar */}
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
              {/* Enrollment Bar */}
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
    </div>
  );
}
