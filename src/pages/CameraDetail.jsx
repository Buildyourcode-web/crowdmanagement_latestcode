// Camera Detail page — Real Stream Information, Health, and Actions
import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import StatusBadge from "../components/common/StatusBadge.jsx";
import {
  getCameraById,
  testCameraStream,
  toggleCameraStatus,
  updateCamera,
  getZones,
} from "../services/cameraService.js";
import {
  getCameraAIConfig,
  validateCameraAIProfile,
  assignCameraAIProfile,
  updateCameraAIProfile,
  removeCameraAIProfile,
  getCameraROIConfig,
  getCameraAIMode,
  switchCameraAIMode,
} from "../services/aiService.js";
import {
  getCameraCrowdMetrics,
  startCrowdPipeline,
  stopCrowdPipeline,
} from "../services/crowdService.js";
import {
  getCameraQueueMetrics,
  startQueuePipeline,
  stopQueuePipeline,
} from "../services/queueService.js";
import ROIEditor from "../components/ai/ROIEditor.jsx";
import { LoadingState, ErrorState } from "../components/common/States.jsx";

const BACKEND = `http://${window.location.hostname}:8000`;

function CameraFeed({ camera }) {
  const containerRef = useRef(null);
  const [streamError, setStreamError] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const [isBrowserFullscreen, setIsBrowserFullscreen] = useState(false);

  const camCode = camera?.camera_code || camera?.id;
  const isKhbOrWorking = camCode === "CAM-KHB-001" || camCode?.startsWith("FRS-") || camera?.stream_url || camera?.status === "online";

  const streamSrc = camera?.stream_url
    ? (camera.stream_url.startsWith("http") ? camera.stream_url : `${BACKEND}${camera.stream_url}`)
    : `${BACKEND}/api/v1/frs-engine/cameras/${camCode || "CAM-KHB-001"}/stream`;

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch((err) => console.error(err));
      setIsBrowserFullscreen(true);
    } else {
      document.exitFullscreen().catch((err) => console.error(err));
      setIsBrowserFullscreen(false);
    }
  };

  useEffect(() => {
    const onFsChange = () => setIsBrowserFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);

  if (camera?.status === "offline" || camera?.stream_status === "OFFLINE" || camera?.enabled === false) {
    return (
      <div
        style={{
          aspectRatio: "16/9",
          background: "#050810",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 12,
          border: "1px solid var(--cc-red-border)",
        }}
      >
        <i className="bi bi-camera-video-off-fill" style={{ fontSize: 44, color: "var(--cc-red)", opacity: 0.6 }} />
        <div style={{ fontSize: 13, fontWeight: 700, color: "var(--cc-red)" }}>CAMERA OFFLINE / DISABLED</div>
        <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>
          {camera.last_error ? `Error: ${camera.last_error}` : "RTSP stream is not reachable"}
        </div>
      </div>
    );
  }

  // Active video stream for working cameras
  if (isKhbOrWorking && !streamError) {
    return (
      <div
        ref={containerRef}
        style={{
          position: "relative",
          aspectRatio: isBrowserFullscreen ? undefined : "16/9",
          width: "100%",
          height: isBrowserFullscreen ? "100vh" : "100%",
          background: "#000",
          overflow: "hidden",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <img
          key={retryCount}
          src={`${streamSrc}?t=${retryCount}`}
          alt="Live Stream"
          style={{ width: "100%", height: "100%", objectFit: "contain" }}
          onError={() => setStreamError(true)}
        />
        <div
          style={{
            position: "absolute",
            top: 10,
            left: 12,
            fontFamily: "var(--cc-font-mono)",
            fontSize: 11,
            color: "#fff",
            background: "rgba(0,0,0,0.75)",
            padding: "4px 8px",
            borderRadius: 3,
            backdropFilter: "blur(4px)",
          }}
        >
          {camCode} — {camera.resolution || "1080p"} ({camera.fps || 25} FPS)
        </div>
        <div style={{ position: "absolute", top: 10, right: 12, display: "flex", gap: 8, alignItems: "center" }}>
          <div
            style={{
              fontSize: 11,
              color: "var(--cc-green)",
              fontWeight: 700,
              background: "rgba(0,0,0,0.75)",
              padding: "4px 8px",
              borderRadius: 3,
              backdropFilter: "blur(4px)",
            }}
          >
            ● LIVE STREAM
          </div>
          <button
            className="cc-btn cc-btn-primary"
            onClick={toggleFullscreen}
            style={{ fontSize: 11, padding: "4px 10px", display: "flex", alignItems: "center", gap: 4 }}
          >
            <i className={`bi ${isBrowserFullscreen ? "bi-fullscreen-exit" : "bi-arrows-fullscreen"}`} />
            {isBrowserFullscreen ? "Exit Fullscreen" : "Full Screen"}
          </button>
        </div>
        {camera.is_frs_camera && (
          <div
            style={{
              position: "absolute",
              bottom: 10,
              right: 12,
              fontSize: 10,
              color: "var(--cc-accent)",
              fontWeight: 800,
              background: "rgba(0,0,0,0.8)",
              padding: "4px 8px",
              borderRadius: 3,
              border: "1px solid rgba(56,189,248,0.4)",
            }}
          >
            FRS BIOMETRIC AI ACTIVE
          </div>
        )}
      </div>
    );
  }

  // Clean placeholder when disconnected
  return (
    <div
      style={{
        aspectRatio: "16/9",
        background: "#050810",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 10,
        border: "1px solid var(--cc-border)",
        padding: 20,
        textAlign: "center",
      }}
    >
      <i className="bi bi-camera-video" style={{ fontSize: 40, color: "var(--cc-text-muted)", opacity: 0.6 }} />
      <div style={{ fontSize: 13, fontWeight: 700, color: "var(--cc-text-primary)" }}>
        {streamError ? "AWAITING STREAM RECONNECT" : "LIVE PREVIEW NOT CONFIGURED"}
      </div>
      <div style={{ fontSize: 11, color: "var(--cc-text-muted)", maxWidth: 360, lineHeight: 1.5 }}>
        {streamError
          ? "RTSP live stream interrupted or initializing. Click reconnect to refresh."
          : `RTSP stream registered (${camera.resolution || "1080p"}, ${camera.fps || 25} FPS).`}
      </div>
      <button
        className="cc-btn cc-btn-primary"
        style={{ fontSize: 11, padding: "4px 12px", marginTop: 6 }}
        onClick={() => {
          setStreamError(false);
          setRetryCount((c) => c + 1);
        }}
      >
        <i className="bi bi-arrow-clockwise" /> Reconnect Live Stream
      </button>
      <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 10, color: "var(--cc-blue)", marginTop: 4 }}>
        Target: {camera.rtsp_url || "rtsp://configured-endpoint"}
      </div>
    </div>
  );
}

export default function CameraDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [camera, setCamera] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const camCode = camera?.camera_code || camera?.id || id;
  const streamSrc = camera?.stream_url
    ? (camera.stream_url.startsWith("http") ? camera.stream_url : `${BACKEND}${camera.stream_url}`)
    : `${BACKEND}/api/v1/frs-engine/cameras/${camCode || "CAM-KHB-001"}/stream`;

  // Stream Testing state
  const [testing, setTesting] = useState(false);
  const [testResultMsg, setTestResultMsg] = useState(null);

  // Edit modal state
  const [showEdit, setShowEdit] = useState(false);
  const [editForm, setEditForm] = useState({});
  const [zones, setZones] = useState([]);
  const [editSaving, setEditSaving] = useState(false);

  const fetchCamera = useCallback(async () => {
    try {
      const res = await getCameraById(id);
      const data = res?.data || res;
      setCamera(data);
      setEditForm({
        name: data.name || "",
        label: data.label || "",
        description: data.description || "",
        zone_code: data.zone || "",
        camera_type: data.camera_type || "CROWD",
        location_name: data.location_name || "",
        fps: data.fps || 25,
        resolution: data.resolution || "1080p",
      });
    } catch (e) {
      // Fallback: check in-memory FRS engine cameras
      try {
        const engRes = await fetch(`${BACKEND}/api/v1/frs-engine/cameras`);
        if (engRes.ok) {
          const engList = await engRes.json();
          const match = engList.find((c) => c.camera_id.toLowerCase() === id.toLowerCase() || c.camera_id === id);
          if (match) {
            const fallbackData = {
              id: match.camera_id,
              camera_code: match.camera_id,
              name: match.name,
              label: match.name,
              description: `Live RTSP Video Channel (${match.camera_type})`,
              zone: "ZONE-A",
              camera_type: match.camera_type || "FRS",
              status: match.status === "online" ? "online" : "degraded",
              stream_status: "ONLINE",
              is_frs_camera: match.is_frs,
              stream_url: match.stream_url,
              rtsp_url: match.rtsp_url,
              resolution: "1080p",
              fps: 25,
              enabled: true,
            };
            setCamera(fallbackData);
            setEditForm(fallbackData);
            return;
          }
        }
      } catch (_) {}
      setError(e.message || "Failed to load camera.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  // AI Profile Assignment state
  const [aiConfig, setAiConfig] = useState(null);
  const [loadingAiConfig, setLoadingAiConfig] = useState(false);
  const [selectedProfile, setSelectedProfile] = useState(null);
  const [validatingCapacity, setValidatingCapacity] = useState(false);
  const [validationResult, setValidationResult] = useState(null);
  const [applyingConfig, setApplyingConfig] = useState(false);
  const [configFeedback, setConfigFeedback] = useState(null);

  const fetchAIConfig = useCallback(async () => {
    if (!id) return;
    setLoadingAiConfig(true);
    try {
      const data = await getCameraAIConfig(id);
      setAiConfig(data);
    } catch (err) {
      console.warn("Could not load camera AI config:", err);
    } finally {
      setLoadingAiConfig(false);
    }
  }, [id]);

  // Step 5: ROI Configuration state
  const [roiSummary, setRoiSummary] = useState(null);
  const [activeROIEditor, setActiveROIEditor] = useState(null);

  const fetchROIConfig = useCallback(async () => {
    if (!id) return;
    try {
      const data = await getCameraROIConfig(id);
      setRoiSummary(data);
    } catch (err) {
      console.warn("Could not load camera ROI config:", err);
    }
  }, [id]);

  // Step 6: Real-Time Crowd AI Pipeline Telemetry state
  const [crowdMetrics, setCrowdMetrics] = useState(null);
  const [operatingPipeline, setOperatingPipeline] = useState(false);
  const [pipelineError, setPipelineError] = useState(null);

  const fetchCrowdMetrics = useCallback(async () => {
    if (!id) return;
    try {
      const res = await getCameraCrowdMetrics(id);
      const data = res?.data || res;
      setCrowdMetrics(data);
    } catch {
      // ignore
    }
  }, [id]);

  // Step 7: Real-Time Queue AI Pipeline Telemetry state
  const [queueMetrics, setQueueMetrics] = useState(null);
  const [operatingQueuePipeline, setOperatingQueuePipeline] = useState(false);
  const [queuePipelineError, setQueuePipelineError] = useState(null);

  const fetchQueueMetrics = useCallback(async () => {
    if (!id) return;
    try {
      const res = await getCameraQueueMetrics(id);
      const data = res?.data || res;
      setQueueMetrics(data);
    } catch {
      // ignore
    }
  }, [id]);

  // Step 8: Exclusive AI Mode & Logical IDs state
  const [aiModeInfo, setAIModeInfo] = useState(null);
  const [switchingMode, setSwitchingMode] = useState(false);
  const [modeError, setModeError] = useState(null);

  const fetchAIMode = useCallback(async () => {
    if (!id) return;
    try {
      const data = await getCameraAIMode(id);
      setAIModeInfo(data);
    } catch (err) {
      console.warn("Could not load camera AI mode:", err);
    }
  }, [id]);

  const handleSwitchMode = async (targetMode) => {
    setSwitchingMode(true);
    setModeError(null);
    try {
      const res = await switchCameraAIMode(id, targetMode);
      setAIModeInfo(res);
      await fetchCamera();
      await fetchAIConfig();
      await fetchCrowdMetrics();
      await fetchQueueMetrics();
      setConfigFeedback({
        type: "success",
        text: `Camera AI Mode successfully switched to ${targetMode}. Single-camera exclusive resource isolation enforced.`,
      });
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === "object" ? detail.message : (detail || err.message || "Failed to switch AI mode");
      setModeError(msg);
    } finally {
      setSwitchingMode(false);
    }
  };

  const metricsInFlightRef = useRef(false);
  const metricsTimerRef = useRef(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    fetchCamera();
    fetchAIConfig();
    fetchROIConfig();
    fetchCrowdMetrics();
    fetchQueueMetrics();
    fetchAIMode();
    getZones().then((res) => {
      const list = Array.isArray(res) ? res : res?.data || [];
      if (isMountedRef.current) setZones(list);
    }).catch(() => {});

    // Adaptive request-aware metrics polling (5s)
    const pollMetrics = async () => {
      if (metricsInFlightRef.current) return;
      metricsInFlightRef.current = true;
      try {
        await Promise.allSettled([fetchCrowdMetrics(), fetchQueueMetrics()]);
      } finally {
        metricsInFlightRef.current = false;
      }
    };

    const scheduleNext = () => {
      clearTimeout(metricsTimerRef.current);
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      metricsTimerRef.current = setTimeout(async () => {
        if (isMountedRef.current && document.visibilityState === "visible") {
          await pollMetrics();
          scheduleNext();
        }
      }, 5000);
    };

    scheduleNext();

    const handleVis = () => {
      if (document.visibilityState === "visible") {
        pollMetrics();
        scheduleNext();
      } else {
        clearTimeout(metricsTimerRef.current);
      }
    };
    document.addEventListener("visibilitychange", handleVis);

    return () => {
      isMountedRef.current = false;
      clearTimeout(metricsTimerRef.current);
      document.removeEventListener("visibilitychange", handleVis);
    };
  }, [fetchCamera, fetchAIConfig, fetchROIConfig, fetchCrowdMetrics, fetchQueueMetrics]);

  const handleStartCrowdPipeline = async () => {
    setOperatingPipeline(true);
    setPipelineError(null);
    try {
      await startCrowdPipeline(id);
      await fetchCrowdMetrics();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === "object" ? detail.message : (detail || err.message || "Failed to start pipeline");
      setPipelineError(msg);
    } finally {
      setOperatingPipeline(false);
    }
  };

  const handleStopCrowdPipeline = async () => {
    setOperatingPipeline(true);
    setPipelineError(null);
    try {
      await stopCrowdPipeline(id);
      await fetchCrowdMetrics();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === "object" ? detail.message : (detail || err.message || "Failed to stop pipeline");
      setPipelineError(msg);
    } finally {
      setOperatingPipeline(false);
    }
  };

  const handleStartQueuePipeline = async () => {
    setOperatingQueuePipeline(true);
    setQueuePipelineError(null);
    try {
      await startQueuePipeline(id);
      await fetchQueueMetrics();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === "object" ? detail.message : (detail || err.message || "Failed to start queue pipeline");
      setQueuePipelineError(msg);
    } finally {
      setOperatingQueuePipeline(false);
    }
  };

  const handleStopQueuePipeline = async () => {
    setOperatingQueuePipeline(true);
    setQueuePipelineError(null);
    try {
      await stopQueuePipeline(id);
      await fetchQueueMetrics();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === "object" ? detail.message : (detail || err.message || "Failed to stop queue pipeline");
      setQueuePipelineError(msg);
    } finally {
      setOperatingQueuePipeline(false);
    }
  };

  const handleTestStream = async () => {
    setTesting(true);
    setTestResultMsg(null);
    try {
      const res = await testCameraStream(id, 6.0);
      const data = res?.data || res;
      if (data.stream_available) {
        setTestResultMsg({ type: "success", text: `Stream reachable: ${data.resolution} @ ${data.fps}fps (${data.codec?.toUpperCase()}) - ${data.stability}` });
      } else {
        setTestResultMsg({ type: "error", text: `Stream test failed: ${data.error_message || data.error_code}` });
      }
      await fetchCamera();
    } catch (err) {
      setTestResultMsg({ type: "error", text: err.response?.data?.detail?.message || err.message || "Test request failed." });
    } finally {
      setTesting(false);
    }
  };

  const handleToggleStatus = async () => {
    try {
      await toggleCameraStatus(id);
      await fetchCamera();
    } catch (err) {
      alert("Failed to toggle camera status.");
    }
  };

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    setEditSaving(true);
    try {
      await updateCamera(id, editForm);
      setShowEdit(false);
      await fetchCamera();
      await fetchAIConfig();
    } catch (err) {
      alert(err.response?.data?.detail?.message || "Failed to update camera.");
    } finally {
      setEditSaving(false);
    }
  };

  const handleOpenAssignModal = async (profile) => {
    setSelectedProfile(profile);
    setValidationResult(null);
    setValidatingCapacity(true);
    try {
      const result = await validateCameraAIProfile(id, {
        profile_id: profile.profile_id,
        enabled: true,
      });
      setValidationResult(result);
    } catch (err) {
      setValidationResult({
        verdict: "BLOCKED",
        status: "ERROR",
        reason: err.response?.data?.error?.message || err.response?.data?.detail?.message || err.message || "Failed to validate capacity.",
      });
    } finally {
      setValidatingCapacity(false);
    }
  };

  const handleApplyAssignment = async () => {
    if (!selectedProfile) return;
    setApplyingConfig(true);
    try {
      await assignCameraAIProfile(id, {
        profile_id: selectedProfile.profile_id,
        enabled: true,
      });
      setConfigFeedback({
        type: "success",
        text: "Configuration saved. AI pipeline startup will be available in the deployment/orchestration stage.",
      });
      setSelectedProfile(null);
      setValidationResult(null);
      await fetchAIConfig();
    } catch (err) {
      setConfigFeedback({
        type: "error",
        text: err.response?.data?.error?.message || err.response?.data?.detail?.message || "Failed to assign AI profile.",
      });
    } finally {
      setApplyingConfig(false);
    }
  };

  const handleRemoveAssignment = async (profileId) => {
    if (!window.confirm(`Are you sure you want to remove AI profile '${profileId}' from this camera?`)) return;
    try {
      await removeCameraAIProfile(id, profileId);
      setConfigFeedback({
        type: "info",
        text: `AI Profile '${profileId}' removed from camera.`,
      });
      await fetchAIConfig();
    } catch (err) {
      alert(err.response?.data?.error?.message || "Failed to remove assignment.");
    }
  };

  const handleToggleAssignmentEnabled = async (profileId, currentEnabled) => {
    try {
      await updateCameraAIProfile(id, profileId, {
        profile_id: profileId,
        enabled: !currentEnabled,
      });
      await fetchAIConfig();
    } catch (err) {
      alert(err.response?.data?.error?.message || "Failed to toggle assignment state.");
    }
  };

  if (loading) return <LoadingState />;
  if (error || !camera) return <ErrorState message={error || "Camera not found"} onRetry={() => navigate("/cameras")} />;

  const isOnline = camera.status === "online" || camera.stream_status === "ONLINE";

  return (
    <div className="cc-page">
      {/* Header */}
      <div className="cc-page-header">
        <div>
          <button className="cc-btn" onClick={() => navigate("/cameras")} style={{ marginBottom: 6 }}>
            <i className="bi bi-arrow-left" /> Back to Cameras
          </button>
          <div className="cc-page-title">{camera.id || camera.camera_code}</div>
          <div className="cc-page-subtitle">{camera.name} — {camera.zone || "Unassigned"}</div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button
            className="cc-btn cc-btn-secondary"
            onClick={handleTestStream}
            disabled={testing}
            style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 6 }}
          >
            {testing ? <span className="spinner-border spinner-border-sm" /> : <i className="bi bi-broadcast" />}
            {testing ? "Testing Stream..." : "TEST STREAM"}
          </button>
          <button
            className="cc-btn cc-btn-secondary"
            onClick={() => setShowEdit(true)}
            style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 6 }}
          >
            <i className="bi bi-pencil-fill" />
            EDIT CAMERA
          </button>
          <button
            className={`cc-btn ${camera.enabled ? "cc-btn-danger" : "cc-btn-primary"}`}
            onClick={handleToggleStatus}
            style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 6 }}
          >
            <i className={`bi ${camera.enabled ? "bi-slash-circle" : "bi-check-circle"}`} />
            {camera.enabled ? "DISABLE CAMERA" : "ENABLE CAMERA"}
          </button>
          <StatusBadge status={camera.status} />
        </div>
      </div>

      {/* Test Result Alert Banner */}
      {testResultMsg && (
        <div
          style={{
            marginBottom: 14,
            padding: "10px 14px",
            borderRadius: 6,
            fontSize: 12,
            background: testResultMsg.type === "success" ? "rgba(63,185,80,0.1)" : "rgba(248,81,73,0.1)",
            border: `1px solid ${testResultMsg.type === "success" ? "var(--cc-green)" : "var(--cc-red)"}`,
            color: testResultMsg.type === "success" ? "var(--cc-green)" : "var(--cc-red)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <span>
            <i className={`bi ${testResultMsg.type === "success" ? "bi-check-circle-fill" : "bi-exclamation-triangle-fill"}`} style={{ marginRight: 8 }} />
            {testResultMsg.text}
          </span>
          <button onClick={() => setTestResultMsg(null)} style={{ background: "none", border: "none", color: "inherit", cursor: "pointer" }}>
            ✕
          </button>
        </div>
      )}

      {/* AI Config Feedback Alert Banner */}
      {configFeedback && (
        <div
          style={{
            marginBottom: 14,
            padding: "10px 14px",
            borderRadius: 6,
            fontSize: 12,
            background: configFeedback.type === "success" ? "rgba(63,185,80,0.1)" : configFeedback.type === "info" ? "rgba(88,166,255,0.1)" : "rgba(248,81,73,0.1)",
            border: `1px solid ${configFeedback.type === "success" ? "var(--cc-green)" : configFeedback.type === "info" ? "var(--cc-blue)" : "var(--cc-red)"}`,
            color: configFeedback.type === "success" ? "var(--cc-green)" : configFeedback.type === "info" ? "var(--cc-blue)" : "var(--cc-red)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <span>
            <i className={`bi ${configFeedback.type === "success" ? "bi-check-circle-fill" : configFeedback.type === "info" ? "bi-info-circle-fill" : "bi-exclamation-triangle-fill"}`} style={{ marginRight: 8 }} />
            {configFeedback.text}
          </span>
          <button onClick={() => setConfigFeedback(null)} style={{ background: "none", border: "none", color: "inherit", cursor: "pointer" }}>
            ✕
          </button>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 14 }}>
        {/* Left Column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
            <CameraFeed camera={camera} />
          </div>

          {/* Stream & Network Technical Info */}
          <div className="cc-card">
            <div className="cc-section-title" style={{ marginBottom: 12 }}>RTSP Stream & Network Configuration</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
              {[
                { label: "IP Address", value: camera.private_ip || "—", mono: true },
                { label: "Port", value: camera.port || 554, mono: true },
                { label: "Protocol", value: (camera.protocol || "rtsp").toUpperCase() },
                { label: "Codec", value: (camera.codec || "h264").toUpperCase() },
                { label: "Resolution", value: camera.resolution || "1080p" },
                { label: "FPS", value: `${camera.fps || 25} fps` },
                { label: "Latency", value: `${camera.latency_ms || camera.latency || 0}ms` },
                { label: "Stability", value: camera.stream_stability || "UNKNOWN" },
              ].map((item) => (
                <div key={item.label} style={{ background: "var(--cc-bg-primary)", padding: "8px 10px", borderRadius: 4 }}>
                  <div style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>{item.label}</div>
                  <div style={{ fontFamily: item.mono ? "var(--cc-font-mono)" : "inherit", fontSize: 12, fontWeight: 700, color: "var(--cc-text-primary)", marginTop: 2 }}>
                    {item.value}
                  </div>
                </div>
              ))}
            </div>

            <div style={{ marginTop: 12, fontSize: 11, color: "var(--cc-text-muted)", display: "flex", justifyContent: "space-between" }}>
              <span>Endpoint: <code style={{ color: "var(--cc-blue)" }}>{camera.rtsp_url || "Not configured"}</code></span>
              <span>Credentials: <strong style={{ color: "var(--cc-green)" }}>Encrypted at Rest</strong></span>
            </div>
          </div>

          {/* Exclusive AI Mode Switching & Single-Camera Isolation Card */}
          <div className="cc-card" style={{ border: "1px solid var(--cc-border-accent, #30363d)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <div className="cc-section-title" style={{ margin: 0 }}>
                <i className="bi bi-toggles2" style={{ marginRight: 6, color: "var(--cc-accent, #58a6ff)" }} />
                Camera Exclusive AI Mode Control
              </div>
              <span style={{
                fontSize: 10,
                fontWeight: 700,
                padding: "3px 8px",
                borderRadius: 4,
                fontFamily: "var(--cc-font-mono)",
                background: (aiModeInfo?.current_mode || camera?.ai_mode) === "CROWD_ACTIVE" ? "rgba(63,185,80,0.15)" : (aiModeInfo?.current_mode || camera?.ai_mode) === "FRS_ACTIVE" ? "rgba(88,166,255,0.15)" : "rgba(139,148,158,0.15)",
                color: (aiModeInfo?.current_mode || camera?.ai_mode) === "CROWD_ACTIVE" ? "var(--cc-green)" : (aiModeInfo?.current_mode || camera?.ai_mode) === "FRS_ACTIVE" ? "var(--cc-blue)" : "var(--cc-text-muted)",
                border: `1px solid ${(aiModeInfo?.current_mode || camera?.ai_mode) === "CROWD_ACTIVE" ? "rgba(63,185,80,0.3)" : (aiModeInfo?.current_mode || camera?.ai_mode) === "FRS_ACTIVE" ? "rgba(88,166,255,0.3)" : "rgba(139,148,158,0.3)"}`
              }}>
                CURRENT MODE: {aiModeInfo?.current_mode || camera?.ai_mode || "IDLE"}
              </span>
            </div>

            {modeError && (
              <div style={{
                marginBottom: 10,
                padding: "8px 12px",
                borderRadius: 4,
                fontSize: 11,
                background: "rgba(248,81,73,0.1)",
                border: "1px solid var(--cc-red)",
                color: "var(--cc-red)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between"
              }}>
                <span><i className="bi bi-exclamation-triangle-fill" style={{ marginRight: 6 }} />{modeError}</span>
                <button onClick={() => setModeError(null)} style={{ background: "none", border: "none", color: "inherit", cursor: "pointer" }}>✕</button>
              </div>
            )}

            {/* Camera Logical Identities Grid */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 14 }}>
              <div style={{ background: "var(--cc-bg-primary)", padding: "8px 10px", borderRadius: 4, border: "1px solid var(--cc-border)" }}>
                <div style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>PHYSICAL CAMERA</div>
                <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 12, fontWeight: 700, color: "var(--cc-text-primary)", marginTop: 2 }}>
                  {camera.camera_code || camera.id}
                </div>
                <div style={{ fontSize: 9, color: "var(--cc-text-muted)", marginTop: 2 }}>Hardware Sensor</div>
              </div>

              <div style={{ background: "var(--cc-bg-primary)", padding: "8px 10px", borderRadius: 4, border: "1px solid var(--cc-border)" }}>
                <div style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>FRS LOGICAL ID</div>
                <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 12, fontWeight: 700, color: "var(--cc-blue)", marginTop: 2 }}>
                  {aiModeInfo?.frs_logical_id || camera?.logical_id_frs || `${camera.camera_code || camera.id}-FRS`}
                </div>
                <div style={{ fontSize: 9, marginTop: 2, fontWeight: 700, color: (aiModeInfo?.frs_status || camera?.frs_status) === "RUNNING" ? "var(--cc-green)" : "var(--cc-text-muted)" }}>
                  Status: {aiModeInfo?.frs_status || camera?.frs_status || "DISCONNECTED"}
                </div>
              </div>

              <div style={{ background: "var(--cc-bg-primary)", padding: "8px 10px", borderRadius: 4, border: "1px solid var(--cc-border)" }}>
                <div style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>CROWD LOGICAL ID</div>
                <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 12, fontWeight: 700, color: "var(--cc-green)", marginTop: 2 }}>
                  {aiModeInfo?.crowd_logical_id || camera?.logical_id_crowd || `${camera.camera_code || camera.id}-CROWD`}
                </div>
                <div style={{ fontSize: 9, marginTop: 2, fontWeight: 700, color: (aiModeInfo?.crowd_status || camera?.crowd_status) === "RUNNING" ? "var(--cc-green)" : "var(--cc-text-muted)" }}>
                  Status: {aiModeInfo?.crowd_status || camera?.crowd_status || "DISCONNECTED"}
                </div>
              </div>
            </div>

            {/* Exclusive Mode Action Buttons */}
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              {(aiModeInfo?.current_mode || camera?.ai_mode) === "CROWD_ACTIVE" ? (
                <>
                  <button
                    className="cc-btn cc-btn-primary"
                    onClick={() => handleSwitchMode("FRS")}
                    disabled={switchingMode}
                    style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 6 }}
                  >
                    {switchingMode ? <span className="spinner-border spinner-border-sm" /> : <i className="bi bi-person-badge" />}
                    {switchingMode ? "SWITCHING MODE..." : "SWITCH TO FRS"}
                  </button>
                  <button
                    className="cc-btn cc-btn-secondary"
                    onClick={() => handleSwitchMode("IDLE")}
                    disabled={switchingMode}
                    style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 6, color: "var(--cc-red)", borderColor: "rgba(248,81,73,0.3)" }}
                  >
                    <i className="bi bi-stop-circle" />
                    STOP AI
                  </button>
                </>
              ) : (aiModeInfo?.current_mode || camera?.ai_mode) === "FRS_ACTIVE" ? (
                <>
                  <button
                    className="cc-btn cc-btn-primary"
                    onClick={() => handleSwitchMode("CROWD")}
                    disabled={switchingMode}
                    style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 6 }}
                  >
                    {switchingMode ? <span className="spinner-border spinner-border-sm" /> : <i className="bi bi-people-fill" />}
                    {switchingMode ? "SWITCHING MODE..." : "SWITCH TO CROWD"}
                  </button>
                  <button
                    className="cc-btn cc-btn-secondary"
                    onClick={() => handleSwitchMode("IDLE")}
                    disabled={switchingMode}
                    style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 6, color: "var(--cc-red)", borderColor: "rgba(248,81,73,0.3)" }}
                  >
                    <i className="bi bi-stop-circle" />
                    STOP AI
                  </button>
                </>
              ) : (
                <>
                  <button
                    className="cc-btn cc-btn-primary"
                    onClick={() => handleSwitchMode("CROWD")}
                    disabled={switchingMode}
                    style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 6 }}
                  >
                    {switchingMode ? <span className="spinner-border spinner-border-sm" /> : <i className="bi bi-people-fill" />}
                    {switchingMode ? "SWITCHING MODE..." : "START CROWD"}
                  </button>
                  <button
                    className="cc-btn cc-btn-secondary"
                    onClick={() => handleSwitchMode("FRS")}
                    disabled={switchingMode}
                    style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 6, borderColor: "var(--cc-blue)", color: "var(--cc-blue)" }}
                  >
                    {switchingMode ? <span className="spinner-border spinner-border-sm" /> : <i className="bi bi-person-badge" />}
                    {switchingMode ? "SWITCHING MODE..." : "START FRS"}
                  </button>
                </>
              )}
              <span style={{ fontSize: 11, color: "var(--cc-text-muted)", marginLeft: "auto" }}>
                Maximum active AI mode: <strong>1</strong> (Strict Mutex)
              </span>
            </div>
          </div>

          {/* AI Configuration & Profile Assignment Card */}
          <div className="cc-card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <div className="cc-section-title" style={{ margin: 0 }}>
                <i className="bi bi-cpu" style={{ marginRight: 6, color: "var(--cc-blue)" }} />
                AI Profile Configuration
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>Camera Purpose:</span>
                <select
                  className="cc-input"
                  value={camera?.camera_type || "CROWD"}
                  onChange={async (e) => {
                    const newType = e.target.value;
                    try {
                      await updateCamera(id, { camera_type: newType });
                      await fetchCamera();
                      await fetchAIConfig();
                      setConfigFeedback({
                        type: "success",
                        text: `Camera purpose updated to ${newType}. Compatible profiles refreshed.`,
                      });
                    } catch (err) {
                      alert("Failed to update camera purpose: " + (err.response?.data?.detail?.message || err.message));
                    }
                  }}
                  style={{
                    fontSize: 11,
                    padding: "3px 8px",
                    fontWeight: 700,
                    background: "var(--cc-bg-primary)",
                    color: "var(--cc-blue)",
                    borderColor: "var(--cc-border)",
                    cursor: "pointer",
                    borderRadius: 4,
                  }}
                >
                  <option value="CROWD">CROWD (Entry/Exit & Zone)</option>
                  <option value="QUEUE">QUEUE (Queue Length & Wait Time)</option>
                  <option value="MULTI_PURPOSE">MULTI_PURPOSE (All: Entry/Exit + Queue + Zone)</option>
                  <option value="FRS">FRS (Face Recognition)</option>
                  <option value="GENERAL">GENERAL (Video Safety)</option>
                </select>
              </div>
            </div>

            <div style={{ fontSize: 11, color: "var(--cc-text-secondary)", marginBottom: 12, background: "var(--cc-bg-primary)", padding: "8px 12px", borderRadius: 4, border: "1px solid var(--cc-border)" }}>
              <i className="bi bi-info-circle" style={{ marginRight: 6, color: "var(--cc-blue)" }} />
              <strong>Desired Configuration Only:</strong> Assigning a profile configures the intended AI pipeline. No inference or DeepStream processes will be started until the Orchestration phase.
            </div>

            {/* Currently Assigned Profiles */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "var(--cc-text-muted)", textTransform: "uppercase", marginBottom: 8 }}>
                Assigned AI Profiles ({aiConfig?.assignments?.length || 0})
              </div>
              {aiConfig?.assignments?.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {aiConfig.assignments.map((asgn) => (
                    <div
                      key={asgn.id}
                      style={{
                        padding: "12px 14px",
                        background: "var(--cc-bg-primary)",
                        border: "1px solid rgba(63,185,80,0.3)",
                        borderRadius: 6,
                        display: "flex",
                        flexDirection: "column",
                        gap: 10,
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span style={{ fontWeight: 700, fontSize: 13, color: "var(--cc-text-primary)" }}>{asgn.profile_name}</span>
                            <span style={{ fontSize: 10, background: asgn.enabled ? "rgba(63,185,80,0.15)" : "rgba(139,148,158,0.2)", color: asgn.enabled ? "var(--cc-green)" : "var(--cc-text-muted)", padding: "2px 6px", borderRadius: 3, fontWeight: 700 }}>
                              {asgn.enabled ? "ACTIVE (Configured)" : "DISABLED"}
                            </span>
                          </div>
                          {asgn.workload_estimate && (
                            <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 4, fontFamily: "var(--cc-font-mono)" }}>
                              Est. GPU: {asgn.workload_estimate.estimated_gpu_load_percent}% | VRAM: {asgn.workload_estimate.estimated_vram_gb}GB | CPU: {asgn.workload_estimate.estimated_cpu_percent}% | RAM: {asgn.workload_estimate.estimated_ram_mb}MB
                            </div>
                          )}
                          {/* Step 5: ROI Readiness indicator */}
                          {roiSummary?.readiness_by_profile?.[asgn.profile_id] && asgn.profile_id !== "FRS_STANDARD" && (
                            <div style={{ marginTop: 4, display: "flex", alignItems: "center", gap: 6 }}>
                              <span style={{
                                fontSize: 9,
                                fontWeight: 700,
                                padding: "2px 6px",
                                borderRadius: 3,
                                background: roiSummary.readiness_by_profile[asgn.profile_id].is_ready ? "rgba(63,185,80,0.15)" : "rgba(210,153,34,0.15)",
                                color: roiSummary.readiness_by_profile[asgn.profile_id].is_ready ? "var(--cc-green)" : "var(--cc-yellow)",
                                border: `1px solid ${roiSummary.readiness_by_profile[asgn.profile_id].is_ready ? "rgba(63,185,80,0.3)" : "rgba(210,153,34,0.3)"}`
                              }}>
                                GEOMETRY: {roiSummary.readiness_by_profile[asgn.profile_id].status.replace(/_/g, " ")}
                              </span>
                              <span style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>
                                {roiSummary.readiness_by_profile[asgn.profile_id].message}
                              </span>
                            </div>
                          )}
                          <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 2 }}>
                            Assigned by <strong>{asgn.assigned_by}</strong> on {new Date(asgn.assigned_at).toLocaleDateString()}
                          </div>
                        </div>
                        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6 }}>
                          {asgn.profile_id !== "FRS_STANDARD" && (
                            <>
                              {/* Entry / Exit Counting button */}
                              <button
                                className="cc-btn cc-btn-secondary"
                                style={{ fontSize: 11, padding: "4px 8px", borderColor: "#bc8cff", color: "#bc8cff", display: "flex", alignItems: "center", gap: 4 }}
                                onClick={() => setActiveROIEditor({
                                  profile_id: asgn.profile_id,
                                  profile_name: asgn.profile_name,
                                  initial_tool: asgn.profile_id.includes("QUEUE") ? "ENTRY_LINE" : "COUNTING_LINE",
                                  initial_objective: "ENTRY_EXIT"
                                })}
                                title="Configure Entry/Exit Counting Line"
                              >
                                <i className="bi bi-arrow-left-right" />
                                Entry/Exit Line
                              </button>

                              {/* Zone Area button */}
                              <button
                                className="cc-btn cc-btn-secondary"
                                style={{ fontSize: 11, padding: "4px 8px", borderColor: "#3fb950", color: "#3fb950", display: "flex", alignItems: "center", gap: 4 }}
                                onClick={() => setActiveROIEditor({
                                  profile_id: asgn.profile_id,
                                  profile_name: asgn.profile_name,
                                  initial_tool: "CROWD_ROI",
                                  initial_objective: "ZONE"
                                })}
                                title="Configure Zone / Crowd Area Polygon"
                              >
                                <i className="bi bi-bounding-box" />
                                Zone Area
                              </button>

                              {/* Queue Area button */}
                              <button
                                className="cc-btn cc-btn-secondary"
                                style={{ fontSize: 11, padding: "4px 8px", borderColor: "#d29922", color: "#d29922", display: "flex", alignItems: "center", gap: 4 }}
                                onClick={() => setActiveROIEditor({
                                  profile_id: asgn.profile_id,
                                  profile_name: asgn.profile_name,
                                  initial_tool: "QUEUE_ROI",
                                  initial_objective: "QUEUE"
                                })}
                                title="Configure Waiting Queue Area Polygon"
                              >
                                <i className="bi bi-people" />
                                Queue Area
                              </button>

                              {/* All Tools */}
                              <button
                                className="cc-btn cc-btn-secondary"
                                style={{ fontSize: 11, padding: "4px 8px", borderColor: "var(--cc-accent)", color: "var(--cc-accent)", display: "flex", alignItems: "center", gap: 4 }}
                                onClick={() => setActiveROIEditor({
                                  profile_id: asgn.profile_id,
                                  profile_name: asgn.profile_name,
                                  initial_tool: "COUNTING_LINE",
                                  initial_objective: "ALL"
                                })}
                                title="Open ROI Editor with all tools"
                              >
                                <i className="bi bi-sliders" />
                                All ROIs
                              </button>
                            </>
                          )}
                          <button
                            className="cc-btn cc-btn-secondary"
                            style={{ fontSize: 11, padding: "4px 8px" }}
                            onClick={() => handleToggleAssignmentEnabled(asgn.profile_id, asgn.enabled)}
                          >
                            {asgn.enabled ? "Disable" : "Enable"}
                          </button>
                          <button
                            className="cc-btn cc-btn-secondary"
                            style={{ fontSize: 11, padding: "4px 8px", color: "var(--cc-red)" }}
                            onClick={() => handleRemoveAssignment(asgn.profile_id)}
                          >
                            Remove
                          </button>
                        </div>
                      </div>

                      {/* Step 6: Crowd AI Real-Time Pipeline Telemetry Panel */}
                      {asgn.profile_id.startsWith("CROWD") && (
                        <div style={{ marginTop: 6, padding: "10px 12px", background: "rgba(0,0,0,0.25)", borderRadius: 6, border: "1px solid var(--cc-border)" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--cc-text-muted)" }}>
                                Crowd AI Inference
                              </span>
                              <span style={{
                                fontSize: 10,
                                fontWeight: 700,
                                padding: "2px 6px",
                                borderRadius: 3,
                                background: crowdMetrics?.status === "RUNNING" ? "rgba(63,185,80,0.2)" : "rgba(139,148,158,0.2)",
                                color: crowdMetrics?.status === "RUNNING" ? "var(--cc-green)" : "var(--cc-text-muted)",
                                border: `1px solid ${crowdMetrics?.status === "RUNNING" ? "rgba(63,185,80,0.4)" : "rgba(139,148,158,0.3)"}`,
                              }}>
                                {crowdMetrics?.status || "STOPPED"}
                              </span>
                            </div>
                            <div>
                              {crowdMetrics?.status === "RUNNING" ? (
                                <button
                                  type="button"
                                  className="cc-btn cc-btn-secondary"
                                  style={{ fontSize: 11, padding: "3px 8px", color: "var(--cc-red)", borderColor: "rgba(248,81,73,0.3)" }}
                                  disabled={operatingPipeline}
                                  onClick={handleStopCrowdPipeline}
                                >
                                  {operatingPipeline ? "Stopping..." : "Stop Pipeline"}
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  className="cc-btn cc-btn-secondary"
                                  style={{ fontSize: 11, padding: "3px 8px", color: "var(--cc-green)", borderColor: "rgba(63,185,80,0.3)" }}
                                  disabled={operatingPipeline || !asgn.enabled}
                                  onClick={handleStartCrowdPipeline}
                                >
                                  {operatingPipeline ? "Starting..." : "Start Pipeline"}
                                </button>
                              )}
                            </div>
                          </div>

                          {pipelineError && (
                            <div style={{ fontSize: 11, color: "var(--cc-red)", background: "rgba(248,81,73,0.1)", padding: "6px 10px", borderRadius: 4, marginBottom: 8, border: "1px solid rgba(248,81,73,0.3)" }}>
                              <i className="bi bi-exclamation-triangle-fill" style={{ marginRight: 6 }} />
                              {pipelineError}
                            </div>
                          )}

                          {crowdMetrics?.status === "RUNNING" ? (
                            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8, marginTop: 6, background: "rgba(255,255,255,0.02)", padding: "8px 10px", borderRadius: 4 }}>
                              <div>
                                <div style={{ fontSize: 9, color: "var(--cc-text-muted)" }}>COUNT</div>
                                <div style={{ fontSize: 16, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-primary)" }}>
                                  {crowdMetrics.count ?? 0}
                                </div>
                              </div>
                              <div>
                                <div style={{ fontSize: 9, color: "var(--cc-text-muted)" }}>DENSITY</div>
                                <div style={{ fontSize: 12, fontWeight: 700, color: crowdMetrics.density_level === "CRITICAL" ? "var(--cc-red)" : crowdMetrics.density_level === "HIGH" ? "var(--cc-yellow)" : "var(--cc-green)" }}>
                                  {crowdMetrics.density_level} ({crowdMetrics.density})
                                </div>
                              </div>
                              <div>
                                <div style={{ fontSize: 9, color: "var(--cc-text-muted)" }}>INFLOW</div>
                                <div style={{ fontSize: 12, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: "var(--cc-blue)" }}>
                                  {crowdMetrics.inflow !== null && crowdMetrics.inflow !== undefined ? `+${crowdMetrics.inflow}/min` : "unavailable"}
                                </div>
                              </div>
                              <div>
                                <div style={{ fontSize: 9, color: "var(--cc-text-muted)" }}>OUTFLOW</div>
                                <div style={{ fontSize: 12, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-muted)" }}>
                                  {crowdMetrics.outflow !== null && crowdMetrics.outflow !== undefined ? `-${crowdMetrics.outflow}/min` : "unavailable"}
                                </div>
                              </div>
                              <div>
                                <div style={{ fontSize: 9, color: "var(--cc-text-muted)" }}>RISK</div>
                                <div style={{ fontSize: 12, fontWeight: 700, color: crowdMetrics.risk_level === "CRITICAL" ? "var(--cc-red)" : crowdMetrics.risk_level === "HIGH" ? "var(--cc-yellow)" : "var(--cc-green)" }}>
                                  {crowdMetrics.risk_level} ({crowdMetrics.risk_score})
                                </div>
                              </div>
                            </div>
                          ) : (
                            <div style={{ fontSize: 11, color: "var(--cc-text-muted)", fontStyle: "italic" }}>
                              Pipeline idle. Click "Start Pipeline" to activate real-time headcount, density, and flow inference.
                            </div>
                          )}
                        </div>
                      )}

                      {/* Step 7: Queue AI Real-Time Pipeline Telemetry Panel */}
                      {asgn.profile_id.includes("QUEUE") && (
                        <div style={{ marginTop: 6, padding: "10px 12px", background: "rgba(0,0,0,0.25)", borderRadius: 6, border: "1px solid var(--cc-border)" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--cc-text-muted)" }}>
                                Queue AI Inference
                              </span>
                              <span style={{
                                fontSize: 10,
                                fontWeight: 700,
                                padding: "2px 6px",
                                borderRadius: 3,
                                background: queueMetrics?.status === "RUNNING" ? "rgba(63,185,80,0.2)" : queueMetrics?.status === "FAILED" ? "rgba(248,81,73,0.2)" : "rgba(139,148,158,0.2)",
                                color: queueMetrics?.status === "RUNNING" ? "var(--cc-green)" : queueMetrics?.status === "FAILED" ? "var(--cc-red)" : "var(--cc-text-muted)",
                                border: `1px solid ${queueMetrics?.status === "RUNNING" ? "rgba(63,185,80,0.4)" : queueMetrics?.status === "FAILED" ? "rgba(248,81,73,0.4)" : "rgba(139,148,158,0.3)"}`,
                              }}>
                                {queueMetrics?.status || "STOPPED"}
                              </span>
                            </div>
                            <div>
                              {queueMetrics?.status === "RUNNING" ? (
                                <button
                                  type="button"
                                  className="cc-btn cc-btn-secondary"
                                  style={{ fontSize: 11, padding: "3px 8px", color: "var(--cc-red)", borderColor: "rgba(248,81,73,0.3)" }}
                                  disabled={operatingQueuePipeline}
                                  onClick={handleStopQueuePipeline}
                                >
                                  {operatingQueuePipeline ? "Stopping..." : "Stop Queue Pipeline"}
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  className="cc-btn cc-btn-secondary"
                                  style={{ fontSize: 11, padding: "3px 8px", color: "var(--cc-green)", borderColor: "rgba(63,185,80,0.3)" }}
                                  disabled={operatingQueuePipeline || !asgn.enabled}
                                  onClick={handleStartQueuePipeline}
                                >
                                  {operatingQueuePipeline ? "Starting..." : "Start Queue Pipeline"}
                                </button>
                              )}
                            </div>
                          </div>

                          {queuePipelineError && (
                            <div style={{ fontSize: 11, color: "var(--cc-red)", background: "rgba(248,81,73,0.1)", padding: "6px 10px", borderRadius: 4, marginBottom: 8, border: "1px solid rgba(248,81,73,0.3)" }}>
                              <i className="bi bi-exclamation-triangle-fill" style={{ marginRight: 6 }} />
                              {queuePipelineError}
                            </div>
                          )}

                          {queueMetrics?.status === "RUNNING" ? (
                            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, marginTop: 6, background: "rgba(255,255,255,0.02)", padding: "8px 10px", borderRadius: 4 }}>
                              <div>
                                <div style={{ fontSize: 9, color: "var(--cc-text-muted)" }}>QUEUE COUNT</div>
                                <div style={{ fontSize: 16, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-primary)" }}>
                                  {queueMetrics.queue_count ?? 0}
                                </div>
                              </div>
                              <div>
                                <div style={{ fontSize: 9, color: "var(--cc-text-muted)" }}>OCCUPANCY</div>
                                <div style={{ fontSize: 12, fontWeight: 700, color: queueMetrics.occupancy_status === "CRITICAL" ? "var(--cc-red)" : queueMetrics.occupancy_status === "WARNING" ? "var(--cc-yellow)" : "var(--cc-green)" }}>
                                  {queueMetrics.occupancy_percentage !== null && queueMetrics.occupancy_percentage !== undefined ? `${queueMetrics.occupancy_percentage}%` : (queueMetrics.occupancy_note || "Not set")}
                                </div>
                              </div>
                              <div>
                                <div style={{ fontSize: 9, color: "var(--cc-text-muted)" }}>AVG WAIT</div>
                                <div style={{ fontSize: 12, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: "var(--cc-blue)" }}>
                                  {queueMetrics.average_wait_seconds ? `${Math.floor(queueMetrics.average_wait_seconds / 60)}m ${queueMetrics.average_wait_seconds % 60}s` : "insufficient_data"}
                                </div>
                              </div>
                              <div>
                                <div style={{ fontSize: 9, color: "var(--cc-text-muted)" }}>QUEUE LENGTH</div>
                                <div style={{ fontSize: 12, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-primary)" }}>
                                  {queueMetrics.queue_length?.value} {queueMetrics.queue_length?.unit === "meters" ? "m" : "extent"}
                                </div>
                              </div>
                              <div>
                                <div style={{ fontSize: 9, color: "var(--cc-text-muted)" }}>INFLOW / OUTFLOW</div>
                                <div style={{ fontSize: 11, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-primary)" }}>
                                  +{queueMetrics.inflow ?? 0} / -{queueMetrics.outflow ?? 0}/min
                                </div>
                              </div>
                              <div>
                                <div style={{ fontSize: 9, color: "var(--cc-text-muted)" }}>DIRECTION</div>
                                <div style={{ fontSize: 11, fontWeight: 700, color: queueMetrics.queue_direction === "FORWARD" ? "var(--cc-green)" : queueMetrics.queue_direction === "BACKWARD" ? "var(--cc-yellow)" : "var(--cc-text-muted)" }}>
                                  {queueMetrics.queue_direction}
                                </div>
                              </div>
                              <div>
                                <div style={{ fontSize: 9, color: "var(--cc-text-muted)" }}>DENSITY</div>
                                <div style={{ fontSize: 11, fontWeight: 700, color: queueMetrics.density_level === "CRITICAL" ? "var(--cc-red)" : queueMetrics.density_level === "HIGH" ? "var(--cc-yellow)" : "var(--cc-green)" }}>
                                  {queueMetrics.density_level} ({queueMetrics.density})
                                </div>
                              </div>
                              <div>
                                <div style={{ fontSize: 9, color: "var(--cc-text-muted)" }}>RISK</div>
                                <div style={{ fontSize: 12, fontWeight: 700, color: queueMetrics.risk_level === "CRITICAL" ? "var(--cc-red)" : queueMetrics.risk_level === "HIGH" ? "var(--cc-yellow)" : "var(--cc-green)" }}>
                                  {queueMetrics.risk_level} ({queueMetrics.risk_score})
                                </div>
                              </div>
                            </div>
                          ) : (
                            <div style={{ fontSize: 11, color: "var(--cc-text-muted)", fontStyle: "italic" }}>
                              Queue pipeline idle. Click "Start Queue Pipeline" to activate real-time headcount, dwell-time, and length inference.
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: 12, color: "var(--cc-text-muted)", fontStyle: "italic", padding: "8px 0" }}>
                  No AI profiles assigned to this camera yet. Select a compatible profile below to preview and assign.
                </div>
              )}
            </div>

            {/* Available Compatible Profiles */}
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: "var(--cc-text-muted)", textTransform: "uppercase", marginBottom: 8 }}>
                Available AI Profiles
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                {aiConfig?.available_profiles?.map((prof) => (
                  <div
                    key={prof.profile_id}
                    style={{
                      padding: 12,
                      borderRadius: 6,
                      background: "var(--cc-bg-primary)",
                      border: `1px solid ${prof.assigned ? "rgba(63,185,80,0.3)" : prof.compatible ? "var(--cc-border)" : "rgba(248,81,73,0.2)"}`,
                      opacity: prof.compatible ? 1 : 0.65,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                      <div style={{ fontWeight: 600, fontSize: 12, color: "var(--cc-text-primary)" }}>{prof.name}</div>
                      <span
                        style={{
                          fontSize: 9,
                          fontWeight: 700,
                          padding: "2px 6px",
                          borderRadius: 3,
                          background: prof.assigned
                            ? "rgba(63,185,80,0.15)"
                            : prof.compatible
                            ? "rgba(88,166,255,0.15)"
                            : "rgba(248,81,73,0.15)",
                          color: prof.assigned
                            ? "var(--cc-green)"
                            : prof.compatible
                            ? "var(--cc-blue)"
                            : "var(--cc-red)",
                        }}
                      >
                        {prof.assigned ? "ASSIGNED" : prof.compatible ? "COMPATIBLE" : "INCOMPATIBLE"}
                      </span>
                    </div>
                    <div style={{ fontSize: 11, color: "var(--cc-text-muted)", marginBottom: 8 }}>
                      {prof.description}
                    </div>
                    <div style={{ fontSize: 10, fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-secondary)", marginBottom: 10 }}>
                      GPU: {prof.workload?.estimated_gpu_load_percent}% | VRAM: {prof.workload?.estimated_vram_gb}GB | CPU: {prof.workload?.estimated_cpu_percent}%
                    </div>
                    {prof.compatible && !prof.assigned && (
                      <button
                        className="cc-btn cc-btn-primary"
                        style={{ width: "100%", fontSize: 11, padding: "5px 0" }}
                        onClick={() => handleOpenAssignModal(prof)}
                      >
                        <i className="bi bi-sliders" style={{ marginRight: 6 }} />
                        Preview & Assign
                      </button>
                    )}
                    {!prof.compatible && (
                      <div style={{ fontSize: 10, color: "var(--cc-red)" }}>
                        {prof.compatibility_reason || "Not compatible with this camera purpose"}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Description & Operational Details */}
          {camera.description && (
            <div className="cc-card">
              <div className="cc-section-title" style={{ marginBottom: 6 }}>Operational Scope</div>
              <div style={{ fontSize: 12, color: "var(--cc-text-secondary)", lineHeight: 1.5 }}>
                {camera.description}
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Health & Diagnostics Panel */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div className="cc-card">
            <div className="cc-section-title" style={{ marginBottom: 12 }}>Stream Health & Status</div>
            {[
              { label: "Operational State", value: camera.enabled ? "ENABLED" : "DISABLED", ok: camera.enabled },
              { label: "Stream Status", value: camera.stream_status || "NOT_TESTED", ok: camera.stream_status === "ONLINE" },
              { label: "Stream Stability", value: camera.stream_stability || "UNKNOWN", ok: camera.stream_stability === "STABLE" },
              { label: "FPS Output", value: camera.fps ? `${camera.fps} fps` : "—", ok: (camera.fps || 0) >= 15 },
              { label: "Latency", value: camera.latency_ms ? `${camera.latency_ms}ms` : "—", ok: (camera.latency_ms || 0) < 150 },
              { label: "Reconnect Count", value: camera.reconnect_count ?? 0, ok: (camera.reconnect_count || 0) === 0 },
              { label: "Last Tested", value: camera.last_tested_at ? new Date(camera.last_tested_at).toLocaleTimeString() : "Never", ok: Boolean(camera.last_tested_at) },
              { label: "Last Seen", value: camera.last_seen_at ? new Date(camera.last_seen_at).toLocaleTimeString() : "Never", ok: Boolean(camera.last_seen_at) },
            ].map((row) => (
              <div key={row.label} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--cc-border-light)", fontSize: 12 }}>
                <span style={{ color: "var(--cc-text-muted)" }}>{row.label}</span>
                <span style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 600, color: row.ok ? "var(--cc-green)" : "var(--cc-yellow)" }}>
                  {row.value}
                </span>
              </div>
            ))}
          </div>

          <div className="cc-card">
            <div className="cc-section-title" style={{ marginBottom: 10 }}>Zone & Purpose</div>
            <div style={{ fontSize: 12 }}>
              <div style={{ marginBottom: 8 }}>
                <div className="cc-label">Zone</div>
                <div style={{ fontWeight: 600, color: "var(--cc-text-primary)" }}>{camera.zone || "Unassigned"}</div>
              </div>
              <div style={{ marginBottom: 8 }}>
                <div className="cc-label">Location</div>
                <div style={{ color: "var(--cc-text-secondary)" }}>{camera.location_name || "—"}</div>
              </div>
              <div style={{ marginBottom: 8 }}>
                <div className="cc-label">Intended AI Purpose</div>
                <div style={{ display: "inline-block", marginTop: 2, padding: "3px 8px", background: "rgba(88,166,255,0.1)", border: "1px solid rgba(88,166,255,0.3)", borderRadius: 3, fontSize: 10, fontWeight: 700, color: "var(--cc-blue)" }}>
                  {camera.camera_type || "CROWD"}
                </div>
              </div>
              {camera.is_frs && (
                <div style={{ marginTop: 8, padding: "6px 10px", background: "var(--cc-blue-dim)", border: "1px solid var(--cc-blue-border)", borderRadius: "var(--cc-radius-sm)", fontSize: 11, color: "var(--cc-blue)", fontWeight: 600 }}>
                  <i className="bi bi-person-bounding-box" style={{ marginRight: 6 }} />
                  FRS Purpose Active
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Edit Camera Modal */}
      {showEdit && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.65)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1050 }}>
          <div className="cc-card" style={{ width: 500, maxWidth: "90vw", padding: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: "var(--cc-text-primary)" }}>Edit Camera Configuration</div>
              <button onClick={() => setShowEdit(false)} style={{ background: "none", border: "none", color: "var(--cc-text-muted)", cursor: "pointer", fontSize: 16 }}>✕</button>
            </div>
            <form onSubmit={handleSaveEdit} style={{ display: "grid", gap: 12 }}>
              <div>
                <label className="cc-label">Camera Name</label>
                <input
                  type="text"
                  className="cc-input"
                  value={editForm.name || ""}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                  style={{ width: "100%" }}
                  required
                />
              </div>
              <div>
                <label className="cc-label">Operational Zone</label>
                <select
                  className="cc-input"
                  value={editForm.zone_code || ""}
                  onChange={(e) => setEditForm({ ...editForm, zone_code: e.target.value })}
                  style={{ width: "100%" }}
                >
                  <option value="">-- Unassigned --</option>
                  {zones.map((z) => (
                    <option key={z.id || z.zone_code} value={z.zone_code}>{z.zone_code} — {z.label || z.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="cc-label">Location Landmark</label>
                <input
                  type="text"
                  className="cc-input"
                  value={editForm.location_name || ""}
                  onChange={(e) => setEditForm({ ...editForm, location_name: e.target.value })}
                  style={{ width: "100%" }}
                />
              </div>
              <div>
                <label className="cc-label">Camera Purpose</label>
                <select
                  className="cc-input"
                  value={editForm.camera_type || "CROWD"}
                  onChange={(e) => setEditForm({ ...editForm, camera_type: e.target.value })}
                  style={{ width: "100%" }}
                >
                  <option value="CROWD">Crowd AI</option>
                  <option value="QUEUE">Queue AI</option>
                  <option value="FRS">FRS Biometric</option>
                  <option value="GENERAL">General Overview</option>
                  <option value="MULTI_PURPOSE">Multi-Purpose</option>
                </select>
              </div>
              <div>
                <label className="cc-label">Description</label>
                <textarea
                  className="cc-input"
                  rows={2}
                  value={editForm.description || ""}
                  onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                  style={{ width: "100%" }}
                />
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 8 }}>
                <button type="button" className="cc-btn cc-btn-secondary" onClick={() => setShowEdit(false)}>Cancel</button>
                <button type="submit" className="cc-btn cc-btn-primary" disabled={editSaving}>
                  {editSaving ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Capacity Preview & Assignment Modal */}
      {selectedProfile && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1050 }}>
          <div className="cc-card" style={{ width: 620, maxWidth: "92vw", padding: 22 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, borderBottom: "1px solid var(--cc-border)", paddingBottom: 10 }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, color: "var(--cc-text-primary)" }}>
                  Assign AI Profile: {selectedProfile.name}
                </div>
                <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>
                  Pre-flight Server Capacity & Workload Validation
                </div>
              </div>
              <button onClick={() => { setSelectedProfile(null); setValidationResult(null); }} style={{ background: "none", border: "none", color: "var(--cc-text-muted)", cursor: "pointer", fontSize: 16 }}>✕</button>
            </div>

            {validatingCapacity ? (
              <div style={{ textAlign: "center", padding: "30px 0" }}>
                <i className="bi bi-arrow-repeat spin" style={{ fontSize: 28, color: "var(--cc-blue)" }} />
                <div style={{ fontSize: 12, color: "var(--cc-text-muted)", marginTop: 8 }}>Inspecting server capacity & projected utilization...</div>
              </div>
            ) : validationResult ? (
              <div>
                {/* Verdict Alert */}
                <div
                  style={{
                    padding: "10px 14px",
                    borderRadius: 6,
                    fontSize: 12,
                    marginBottom: 14,
                    background: validationResult.verdict === "ALLOWED" ? "rgba(63,185,80,0.12)" : validationResult.verdict === "WARNING" ? "rgba(210,153,34,0.12)" : "rgba(248,81,73,0.12)",
                    border: `1px solid ${validationResult.verdict === "ALLOWED" ? "var(--cc-green)" : validationResult.verdict === "WARNING" ? "var(--cc-yellow)" : "var(--cc-red)"}`,
                    color: validationResult.verdict === "ALLOWED" ? "var(--cc-green)" : validationResult.verdict === "WARNING" ? "var(--cc-yellow)" : "var(--cc-red)",
                  }}
                >
                  <div style={{ fontWeight: 700, display: "flex", alignItems: "center", gap: 6 }}>
                    <i className={`bi ${validationResult.verdict === "ALLOWED" ? "bi-check-circle-fill" : validationResult.verdict === "WARNING" ? "bi-exclamation-circle-fill" : "bi-slash-circle-fill"}`} />
                    {validationResult.verdict === "ALLOWED" ? "✓ Capacity Available" : validationResult.verdict === "WARNING" ? "⚠ Safe Headroom Warning" : "✕ Capacity Exceeded — Assignment Blocked"}
                  </div>
                  <div style={{ marginTop: 4, fontSize: 11, opacity: 0.9 }}>
                    {validationResult.reason}
                  </div>
                </div>

                {/* Resource Breakdown Table */}
                <div style={{ background: "var(--cc-bg-primary)", borderRadius: 6, padding: 12, border: "1px solid var(--cc-border)", marginBottom: 14 }}>
                  <div style={{ display: "grid", gridTemplateColumns: "100px 1fr 1fr 1fr 1fr", gap: 8, fontSize: 11, fontWeight: 700, color: "var(--cc-text-muted)", borderBottom: "1px solid var(--cc-border)", paddingBottom: 6 }}>
                    <span>Resource</span>
                    <span>Current</span>
                    <span>Profile Req.</span>
                    <span>Projected</span>
                    <span>Safe Ceiling</span>
                  </div>

                  {[
                    {
                      label: "GPU Load",
                      cur: `${validationResult.current_utilization?.gpu_percent ?? 0}%`,
                      req: `+${validationResult.requested_utilization?.gpu_percent ?? 0}%`,
                      proj: `${validationResult.projected_utilization?.gpu_percent ?? 0}%`,
                      safe: `${validationResult.safe_budget?.gpu_percent ?? 70}%`,
                      exceeded: (validationResult.projected_utilization?.gpu_percent || 0) > (validationResult.hard_max_budget?.gpu_percent || 90),
                    },
                    {
                      label: "VRAM",
                      cur: `${validationResult.current_utilization?.vram_gb ?? 0} GB`,
                      req: `+${validationResult.requested_utilization?.vram_gb ?? 0} GB`,
                      proj: `${validationResult.projected_utilization?.vram_gb ?? 0} GB`,
                      safe: `${validationResult.safe_budget?.vram_gb ?? 12} GB`,
                      exceeded: (validationResult.projected_utilization?.vram_gb || 0) > (validationResult.hard_max_budget?.vram_gb || 16),
                    },
                    {
                      label: "CPU Load",
                      cur: `${validationResult.current_utilization?.cpu_percent ?? 0}%`,
                      req: `+${validationResult.requested_utilization?.cpu_percent ?? 0}%`,
                      proj: `${validationResult.projected_utilization?.cpu_percent ?? 0}%`,
                      safe: `${validationResult.safe_budget?.cpu_percent ?? 75}%`,
                      exceeded: (validationResult.projected_utilization?.cpu_percent || 0) > (validationResult.hard_max_budget?.cpu_percent || 85),
                    },
                    {
                      label: "RAM",
                      cur: `${validationResult.current_utilization?.ram_gb ?? 0} GB`,
                      req: `+${validationResult.requested_utilization?.ram_gb ?? 0} GB`,
                      proj: `${validationResult.projected_utilization?.ram_gb ?? 0} GB`,
                      safe: `${validationResult.safe_budget?.ram_gb ?? 24} GB`,
                      exceeded: (validationResult.projected_utilization?.ram_gb || 0) > (validationResult.hard_max_budget?.ram_gb || 32),
                    },
                  ].map((row) => (
                    <div key={row.label} style={{ display: "grid", gridTemplateColumns: "100px 1fr 1fr 1fr 1fr", gap: 8, fontSize: 11, padding: "6px 0", borderBottom: "1px solid var(--cc-border-light)", color: row.exceeded ? "var(--cc-red)" : "var(--cc-text-primary)" }}>
                      <span style={{ fontWeight: 600 }}>{row.label}</span>
                      <span style={{ fontFamily: "var(--cc-font-mono)" }}>{row.cur}</span>
                      <span style={{ fontFamily: "var(--cc-font-mono)", color: "var(--cc-blue)" }}>{row.req}</span>
                      <span style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 700, color: row.exceeded ? "var(--cc-red)" : "inherit" }}>{row.proj}</span>
                      <span style={{ fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-muted)" }}>{row.safe}</span>
                    </div>
                  ))}
                </div>

                {/* Clear Disclaimers */}
                <div style={{ fontSize: 11, color: "var(--cc-text-muted)", background: "rgba(255,255,255,0.02)", padding: "8px 12px", borderRadius: 4, marginBottom: 14, border: "1px solid var(--cc-border-light)" }}>
                  <i className="bi bi-shield-check" style={{ marginRight: 6, color: "var(--cc-green)" }} />
                  Saving this AI configuration does <strong>NOT</strong> start video inference. Pipelines remain idle until the Orchestrator stage.
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
                  <button
                    type="button"
                    className="cc-btn cc-btn-secondary"
                    onClick={() => { setSelectedProfile(null); setValidationResult(null); }}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="cc-btn cc-btn-primary"
                    disabled={applyingConfig || validationResult.verdict === "BLOCKED"}
                    onClick={handleApplyAssignment}
                  >
                    {applyingConfig ? "Applying..." : "Apply Configuration"}
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}

      {/* Step 5: Visual ROI Editor Modal */}
      {activeROIEditor && (
        <ROIEditor
          camera={camera}
          profileId={activeROIEditor.profile_id}
          profileName={activeROIEditor.profile_name}
          initialTool={activeROIEditor.initial_tool}
          initialObjective={activeROIEditor.initial_objective}
          streamUrl={streamSrc}
          onClose={() => setActiveROIEditor(null)}
          onSaved={() => {
            fetchROIConfig();
            fetchAIConfig();
          }}
        />
      )}
    </div>
  );
}
