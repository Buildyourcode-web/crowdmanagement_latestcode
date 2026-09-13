// AddCamera.jsx — 5-Step Camera Onboarding Wizard
// Route: /cameras/add
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { createCamera, testAdHocStream, getZones } from "../services/cameraService.js";
import { useAppStore } from "../store/useAppStore.js";
import { useEventStore } from "../store/useEventStore.js";

const STEPS = [
  { step: 1, title: "Camera Info", desc: "Identifier & label" },
  { step: 2, title: "RTSP Config", desc: "Stream credentials" },
  { step: 3, title: "Test Connection", desc: "Validate stream" },
  { step: 4, title: "Zone & Purpose", desc: "Location & usage" },
  { step: 5, title: "Review & Save", desc: "Finalize registration" },
];

const PROBE_MESSAGES = [
  "Connecting to camera network endpoint...",
  "Authenticating RTSP credentials...",
  "Inspecting stream header...",
  "Reading video track metadata...",
  "Checking packet stability & timing...",
];

export default function AddCamera() {
  const navigate = useNavigate();
  const theme = useAppStore((s) => s.theme);
  const isLight = theme === "light";
  const activeEventId = useEventStore((s) => s.activeEventId);

  const [currentStep, setCurrentStep] = useState(1);
  const [zones, setZones] = useState([]);
  const [zonesLoading, setZonesLoading] = useState(false);

  // Form state
  const [form, setForm] = useState({
    camera_id: "CAM-KHB-",
    name: "",
    description: "",
    // RTSP
    rtsp_url: "",
    username: "admin",
    password: "",
    private_ip: "",
    port: 554,
    stream_path: "/Streaming/Channels/101",
    protocol: "rtsp",
    // Zone & Purpose
    zone_code: "",
    location_name: "",
    latitude: "",
    longitude: "",
    camera_type: "CROWD",
    is_ptz: false,
  });

  // URL builder toggle
  const [useBuilder, setUseBuilder] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // Test Stream state
  const [testing, setTesting] = useState(false);
  const [testStage, setTestStage] = useState(0);
  const [testResult, setTestResult] = useState(null);
  const [testError, setTestError] = useState(null);

  // Save state
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Fetch zones on mount
  useEffect(() => {
    async function loadZones() {
      setZonesLoading(true);
      try {
        const res = await getZones();
        const list = Array.isArray(res) ? res : res?.data || [];
        setZones(list);
        if (list.length > 0 && !form.zone_code) {
          setForm((f) => ({ ...f, zone_code: list[0].zone_code || list[0].name }));
        }
      } catch (e) {
        console.warn("[AddCamera] Failed to load zones:", e);
      } finally {
        setZonesLoading(false);
      }
    }
    loadZones();
  }, []);

  const handleChange = (field, value) => {
    setForm((f) => ({ ...f, [field]: value }));
  };

  const handleApplyBuilder = () => {
    const ip = form.private_ip.trim() || "192.168.0.102";
    const port = form.port || 554;
    const path = form.stream_path.startsWith("/") ? form.stream_path : `/${form.stream_path}`;
    const generated = `${form.protocol}://${ip}:${port}${path}`;
    setForm((f) => ({ ...f, rtsp_url: generated }));
    setUseBuilder(false);
  };

  // Run RTSP Test
  const handleTestStream = async () => {
    setTesting(true);
    setTestResult(null);
    setTestError(null);
    setTestStage(0);

    // Run visual stages
    const stageTimer = setInterval(() => {
      setTestStage((prev) => (prev < PROBE_MESSAGES.length - 1 ? prev + 1 : prev));
    }, 450);

    try {
      const res = await testAdHocStream({
        camera_id: form.camera_id.trim(),
        rtsp_url: form.rtsp_url.trim(),
        username: form.username.trim() || null,
        password: form.password || null,
        timeout_sec: 6.0,
      });

      clearInterval(stageTimer);
      const data = res?.data || res;
      setTestResult(data);
      if (!data.stream_available) {
        setTestError(data.error_message || "Stream probe failed.");
      }
    } catch (err) {
      clearInterval(stageTimer);
      const msg = err.response?.data?.detail?.message || err.response?.data?.message || err.message || "RTSP test request failed.";
      setTestError(msg);
      setTestResult({
        stream_available: false,
        error_code: "CONNECTION_FAILED",
        error_message: msg,
      });
    } finally {
      setTesting(false);
    }
  };

  // Submit and Save Camera
  const handleSaveCamera = async () => {
    setSaving(true);
    setSaveError(null);

    const payload = {
      camera_id: form.camera_id.trim(),
      name: form.name.trim(),
      description: form.description.trim() || null,
      private_ip: form.private_ip.trim() || null,
      port: Number(form.port) || 554,
      rtsp_url: form.rtsp_url.trim() || null,
      username: form.username.trim() || null,
      password: form.password || null,
      zone_code: form.zone_code || null,
      camera_type: form.camera_type,
      location_name: form.location_name.trim() || null,
      latitude: form.latitude ? parseFloat(form.latitude) : null,
      longitude: form.longitude ? parseFloat(form.longitude) : null,
      is_ptz: form.is_ptz,
      resolution: testResult?.resolution || "1080p",
      fps: testResult?.fps || 25,
      event_id: activeEventId || null,
    };

    try {
      const res = await createCamera(payload);
      setSaveSuccess(true);
      setTimeout(() => {
        navigate(`/cameras/${form.camera_id.trim()}`);
      }, 1200);
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = detail?.message || err.response?.data?.message || err.message || "Failed to onboard camera.";
      setSaveError(msg);
    } finally {
      setSaving(false);
    }
  };

  // Validation per step
  const canGoNext = () => {
    if (currentStep === 1) {
      return form.camera_id.trim().length >= 4 && form.name.trim().length >= 2;
    }
    if (currentStep === 2) {
      return form.rtsp_url.trim().startsWith("rtsp://") || form.rtsp_url.trim().startsWith("rtsps://");
    }
    if (currentStep === 3) {
      return true; // operator can proceed even if untested or testing failed
    }
    if (currentStep === 4) {
      return Boolean(form.camera_type);
    }
    return true;
  };

  return (
    <div className="cc-page">
      {/* Page Header */}
      <div className="cc-page-header">
        <div>
          <button className="cc-btn" onClick={() => navigate("/cameras")} style={{ marginBottom: 6 }}>
            <i className="bi bi-arrow-left" /> Back to Cameras
          </button>
          <div className="cc-page-title">Onboard New IP Camera</div>
          <div className="cc-page-subtitle">
            Configure RTSP stream, inspect connectivity, and assign operational zone
          </div>
        </div>
      </div>

      {/* Wizard Steps Bar */}
      <div
        className="cc-card"
        style={{
          marginBottom: 16,
          padding: "12px 18px",
          display: "grid",
          gridTemplateColumns: "repeat(5, 1fr)",
          gap: 8,
          background: isLight ? "#ffffff" : "#0d1117",
        }}
      >
        {STEPS.map((s) => {
          const isActive = currentStep === s.step;
          const isDone = currentStep > s.step;
          const color = isActive ? "var(--cc-blue)" : isDone ? "var(--cc-green)" : "var(--cc-text-muted)";
          return (
            <div
              key={s.step}
              onClick={() => isDone && setCurrentStep(s.step)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                cursor: isDone ? "pointer" : "default",
                opacity: currentStep >= s.step ? 1 : 0.45,
                borderBottom: isActive ? `2px solid var(--cc-blue)` : "2px solid transparent",
                paddingBottom: 6,
              }}
            >
              <div
                style={{
                  width: 24,
                  height: 24,
                  borderRadius: "50%",
                  background: isDone ? "var(--cc-green)" : isActive ? "var(--cc-blue)" : "var(--cc-bg-secondary)",
                  color: isDone || isActive ? "#fff" : "var(--cc-text-muted)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 11,
                  fontWeight: 700,
                  flexShrink: 0,
                }}
              >
                {isDone ? "✓" : s.step}
              </div>
              <div style={{ overflow: "hidden" }}>
                <div style={{ fontSize: 11, fontWeight: 700, color, whiteSpace: "nowrap" }}>{s.title}</div>
                <div style={{ fontSize: 9, color: "var(--cc-text-muted)", whiteSpace: "nowrap" }}>{s.desc}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Step Content Card */}
      <div className="cc-card" style={{ maxWidth: 820, margin: "0 auto", padding: 24 }}>
        {/* ── STEP 1: Camera Information ── */}
        {currentStep === 1 && (
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 16, color: "var(--cc-text-primary)" }}>
              Step 1: Camera Identification
            </div>
            <div style={{ display: "grid", gap: 14 }}>
              <div>
                <label className="cc-label" style={{ display: "block", marginBottom: 4 }}>
                  Camera ID / Code <span style={{ color: "var(--cc-red)" }}>*</span>
                </label>
                <input
                  type="text"
                  className="cc-input"
                  placeholder="e.g. CAM-KHB-102"
                  value={form.camera_id}
                  onChange={(e) => handleChange("camera_id", e.target.value.toUpperCase())}
                  style={{ width: "100%", fontFamily: "var(--cc-font-mono)" }}
                />
                <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 3 }}>
                  Unique identifier used in system logs, alerts, and camera walls.
                </div>
              </div>

              <div>
                <label className="cc-label" style={{ display: "block", marginBottom: 4 }}>
                  Camera Name / Display Title <span style={{ color: "var(--cc-red)" }}>*</span>
                </label>
                <input
                  type="text"
                  className="cc-input"
                  placeholder="e.g. Khairatabad North Gate Entry High Angle"
                  value={form.name}
                  onChange={(e) => handleChange("name", e.target.value)}
                  style={{ width: "100%" }}
                />
              </div>

              <div>
                <label className="cc-label" style={{ display: "block", marginBottom: 4 }}>
                  Description / Operational Role
                </label>
                <textarea
                  className="cc-input"
                  rows={3}
                  placeholder="e.g. Monitors main queue ingress from Railway Station walkway towards Gate 1."
                  value={form.description}
                  onChange={(e) => handleChange("description", e.target.value)}
                  style={{ width: "100%", resize: "vertical" }}
                />
              </div>
            </div>
          </div>
        )}

        {/* ── STEP 2: RTSP Configuration ── */}
        {currentStep === 2 && (
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: "var(--cc-text-primary)" }}>
                Step 2: RTSP Stream Configuration
              </div>
              <button
                type="button"
                className="cc-btn cc-btn-secondary"
                onClick={() => setUseBuilder(!useBuilder)}
                style={{ fontSize: 11, padding: "4px 10px" }}
              >
                <i className="bi bi-tools" style={{ marginRight: 5 }} />
                {useBuilder ? "Enter Direct URL" : "Use RTSP URL Builder"}
              </button>
            </div>

            {useBuilder ? (
              <div
                style={{
                  background: isLight ? "#f1f5f9" : "var(--cc-bg-primary)",
                  padding: 14,
                  borderRadius: 6,
                  border: "1px solid var(--cc-border)",
                  marginBottom: 16,
                }}
              >
                <div style={{ fontSize: 11, fontWeight: 700, marginBottom: 10, color: "var(--cc-blue)" }}>
                  RTSP URL Generator
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "100px 1fr 100px 1fr", gap: 10 }}>
                  <div>
                    <label className="cc-label">Protocol</label>
                    <select
                      className="cc-input"
                      value={form.protocol}
                      onChange={(e) => handleChange("protocol", e.target.value)}
                      style={{ width: "100%" }}
                    >
                      <option value="rtsp">rtsp://</option>
                      <option value="rtsps">rtsps://</option>
                    </select>
                  </div>
                  <div>
                    <label className="cc-label">IP Address</label>
                    <input
                      type="text"
                      className="cc-input"
                      placeholder="192.168.0.102"
                      value={form.private_ip}
                      onChange={(e) => handleChange("private_ip", e.target.value)}
                      style={{ width: "100%" }}
                    />
                  </div>
                  <div>
                    <label className="cc-label">Port</label>
                    <input
                      type="number"
                      className="cc-input"
                      placeholder="554"
                      value={form.port}
                      onChange={(e) => handleChange("port", e.target.value)}
                      style={{ width: "100%" }}
                    />
                  </div>
                  <div>
                    <label className="cc-label">Stream Path</label>
                    <input
                      type="text"
                      className="cc-input"
                      placeholder="/Streaming/Channels/101"
                      value={form.stream_path}
                      onChange={(e) => handleChange("stream_path", e.target.value)}
                      style={{ width: "100%" }}
                    />
                  </div>
                </div>
                <div style={{ marginTop: 10, display: "flex", justifyContent: "flex-end" }}>
                  <button type="button" className="cc-btn cc-btn-primary" onClick={handleApplyBuilder} style={{ fontSize: 11 }}>
                    Generate & Apply URL
                  </button>
                </div>
              </div>
            ) : null}

            <div style={{ display: "grid", gap: 14 }}>
              <div>
                <label className="cc-label" style={{ display: "block", marginBottom: 4 }}>
                  RTSP URL <span style={{ color: "var(--cc-red)" }}>*</span>
                </label>
                <input
                  type="text"
                  className="cc-input"
                  placeholder="rtsp://192.168.0.102:554/Streaming/Channels/101"
                  value={form.rtsp_url}
                  onChange={(e) => handleChange("rtsp_url", e.target.value)}
                  style={{ width: "100%", fontFamily: "var(--cc-font-mono)", fontSize: 12 }}
                />
                <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 3 }}>
                  Supported vendors: Hikvision, Dahua, Uniview, Axis, CP Plus, and generic RTSP.
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label className="cc-label" style={{ display: "block", marginBottom: 4 }}>
                    Username (Optional)
                  </label>
                  <input
                    type="text"
                    className="cc-input"
                    placeholder="admin"
                    value={form.username}
                    onChange={(e) => handleChange("username", e.target.value)}
                    style={{ width: "100%" }}
                  />
                </div>
                <div>
                  <label className="cc-label" style={{ display: "block", marginBottom: 4 }}>
                    Password (Optional)
                  </label>
                  <div style={{ position: "relative" }}>
                    <input
                      type={showPassword ? "text" : "password"}
                      className="cc-input"
                      placeholder="••••••••"
                      value={form.password}
                      onChange={(e) => handleChange("password", e.target.value)}
                      style={{ width: "100%", paddingRight: 32 }}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      style={{
                        position: "absolute",
                        right: 8,
                        top: "50%",
                        transform: "translateY(-50%)",
                        background: "none",
                        border: "none",
                        color: "var(--cc-text-muted)",
                        cursor: "pointer",
                      }}
                    >
                      <i className={`bi ${showPassword ? "bi-eye-slash" : "bi-eye"}`} />
                    </button>
                  </div>
                </div>
              </div>

              <div>
                <label className="cc-label" style={{ display: "block", marginBottom: 4 }}>
                  Camera Private IP
                </label>
                <input
                  type="text"
                  className="cc-input"
                  placeholder="e.g. 192.168.0.102"
                  value={form.private_ip}
                  onChange={(e) => handleChange("private_ip", e.target.value)}
                  style={{ width: "100%", fontFamily: "var(--cc-font-mono)" }}
                />
                <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 3 }}>
                  Used for duplicate detection and network reachability diagnostics.
                </div>
              </div>

              <div
                style={{
                  padding: "8px 12px",
                  background: "rgba(88,166,255,0.06)",
                  border: "1px solid rgba(88,166,255,0.2)",
                  borderRadius: 4,
                  fontSize: 11,
                  color: "var(--cc-text-secondary)",
                }}
              >
                <i className="bi bi-shield-lock-fill" style={{ color: "var(--cc-blue)", marginRight: 6 }} />
                <strong>Credential Security:</strong> Camera passwords are encrypted at rest using AES-128 (Fernet).
                Passwords are never displayed in logs, API responses, or WebSockets.
              </div>
            </div>
          </div>
        )}

        {/* ── STEP 3: Test Connection ── */}
        {currentStep === 3 && (
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 8, color: "var(--cc-text-primary)" }}>
              Step 3: Test RTSP Stream Connection
            </div>
            <div style={{ fontSize: 11, color: "var(--cc-text-muted)", marginBottom: 16 }}>
              Validate that the camera RTSP stream is reachable, credentials authenticate, and video tracks can be decoded.
            </div>

            <div
              style={{
                background: isLight ? "#f8fafc" : "var(--cc-bg-primary)",
                padding: 16,
                borderRadius: 6,
                border: "1px solid var(--cc-border)",
                marginBottom: 16,
              }}
            >
              <div style={{ fontSize: 12, marginBottom: 8, display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--cc-text-muted)" }}>Target Stream:</span>
                <span style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 600, color: "var(--cc-text-primary)" }}>
                  {form.rtsp_url || "No RTSP URL specified"}
                </span>
              </div>

              <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
                <button
                  type="button"
                  className="cc-btn cc-btn-primary"
                  onClick={handleTestStream}
                  disabled={testing || !form.rtsp_url}
                  style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 18px" }}
                >
                  {testing ? (
                    <>
                      <span className="spinner-border spinner-border-sm" />
                      Testing Stream...
                    </>
                  ) : (
                    <>
                      <i className="bi bi-play-circle-fill" />
                      TEST CAMERA
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* In-progress inspection animation */}
            {testing && (
              <div
                style={{
                  padding: 14,
                  background: isLight ? "#f1f5f9" : "#050810",
                  border: "1px solid var(--cc-border)",
                  borderRadius: 6,
                  marginBottom: 16,
                }}
              >
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--cc-blue)", marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="spinner-border spinner-border-sm" />
                  Inspecting Camera Stream...
                </div>
                {PROBE_MESSAGES.map((msg, i) => {
                  const done = i < testStage;
                  const active = i === testStage;
                  return (
                    <div
                      key={msg}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        fontSize: 11,
                        padding: "3px 0",
                        color: done ? "var(--cc-green)" : active ? "var(--cc-text-primary)" : "var(--cc-text-muted)",
                        opacity: i > testStage + 1 ? 0.3 : 1,
                      }}
                    >
                      <i className={`bi ${done ? "bi-check-circle-fill" : active ? "bi-arrow-right-circle" : "bi-circle"}`} style={{ fontSize: 11 }} />
                      {msg}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Test Success Card */}
            {testResult && testResult.stream_available && !testing && (
              <div
                style={{
                  padding: 16,
                  background: "rgba(63,185,80,0.06)",
                  border: "1px solid var(--cc-green)",
                  borderRadius: 6,
                  marginBottom: 16,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--cc-green)", fontWeight: 700, fontSize: 13, marginBottom: 12 }}>
                  <i className="bi bi-check-circle-fill" style={{ fontSize: 16 }} />
                  CONNECTED — Stream Validated Successfully
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
                  {[
                    { label: "Resolution", value: testResult.resolution },
                    { label: "FPS", value: `${testResult.fps} fps` },
                    { label: "Codec", value: (testResult.codec || "H264").toUpperCase() },
                    { label: "Protocol", value: "RTSP" },
                    { label: "Latency", value: `${testResult.latency_ms || 0}ms` },
                    { label: "Stability", value: testResult.stability || "STABLE" },
                  ].map((item) => (
                    <div key={item.label} style={{ background: "var(--cc-bg-primary)", padding: "8px 10px", borderRadius: 4 }}>
                      <div style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>{item.label}</div>
                      <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 14, fontWeight: 700, color: "var(--cc-text-primary)", marginTop: 2 }}>
                        {item.value}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Test Failure Card */}
            {testResult && !testResult.stream_available && !testing && (
              <div
                style={{
                  padding: 16,
                  background: "rgba(248,81,73,0.06)",
                  border: "1px solid var(--cc-red)",
                  borderRadius: 6,
                  marginBottom: 16,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--cc-red)", fontWeight: 700, fontSize: 13, marginBottom: 8 }}>
                  <i className="bi bi-x-circle-fill" style={{ fontSize: 16 }} />
                  CONNECTION FAILED
                </div>
                <div style={{ fontSize: 12, color: "var(--cc-text-primary)", marginBottom: 8 }}>
                  <strong>Reason:</strong> {testResult.error_message || testError || "Stream inspection failed."}
                </div>
                {testResult.error_code && (
                  <div style={{ fontSize: 10, fontFamily: "var(--cc-font-mono)", color: "var(--cc-red)", marginBottom: 12 }}>
                    Code: {testResult.error_code}
                  </div>
                )}
                <div style={{ display: "flex", gap: 8 }}>
                  <button type="button" className="cc-btn cc-btn-secondary" onClick={() => setCurrentStep(2)} style={{ fontSize: 11 }}>
                    <i className="bi bi-pencil" style={{ marginRight: 4 }} />
                    EDIT CONFIG
                  </button>
                  <button type="button" className="cc-btn cc-btn-primary" onClick={handleTestStream} style={{ fontSize: 11 }}>
                    <i className="bi bi-arrow-clockwise" style={{ marginRight: 4 }} />
                    RETRY TEST
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── STEP 4: Zone & Purpose ── */}
        {currentStep === 4 && (
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 16, color: "var(--cc-text-primary)" }}>
              Step 4: Operational Zone & Purpose Assignment
            </div>
            <div style={{ display: "grid", gap: 14 }}>
              <div>
                <label className="cc-label" style={{ display: "block", marginBottom: 4 }}>
                  Operational Zone <span style={{ color: "var(--cc-red)" }}>*</span>
                </label>
                <select
                  className="cc-input"
                  value={form.zone_code}
                  onChange={(e) => handleChange("zone_code", e.target.value)}
                  style={{ width: "100%" }}
                >
                  <option value="">-- Select Precinct Zone --</option>
                  {zones.map((z) => (
                    <option key={z.id || z.zone_code} value={z.zone_code}>
                      {z.zone_code} — {z.label || z.name}
                    </option>
                  ))}
                </select>
                <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 3 }}>
                  Every camera is mapped to a primary operational zone for tactical surveillance.
                </div>
              </div>

              <div>
                <label className="cc-label" style={{ display: "block", marginBottom: 4 }}>
                  Location Name / Landmark
                </label>
                <input
                  type="text"
                  className="cc-input"
                  placeholder="e.g. North Gate Entry Walkway Arch #2"
                  value={form.location_name}
                  onChange={(e) => handleChange("location_name", e.target.value)}
                  style={{ width: "100%" }}
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label className="cc-label" style={{ display: "block", marginBottom: 4 }}>
                    Latitude (Optional)
                  </label>
                  <input
                    type="number"
                    step="0.0001"
                    className="cc-input"
                    placeholder="17.4175"
                    value={form.latitude}
                    onChange={(e) => handleChange("latitude", e.target.value)}
                    style={{ width: "100%" }}
                  />
                </div>
                <div>
                  <label className="cc-label" style={{ display: "block", marginBottom: 4 }}>
                    Longitude (Optional)
                  </label>
                  <input
                    type="number"
                    step="0.0001"
                    className="cc-input"
                    placeholder="78.4635"
                    value={form.longitude}
                    onChange={(e) => handleChange("longitude", e.target.value)}
                    style={{ width: "100%" }}
                  />
                </div>
              </div>

              <div>
                <label className="cc-label" style={{ display: "block", marginBottom: 4 }}>
                  Camera Purpose / Usage Type <span style={{ color: "var(--cc-red)" }}>*</span>
                </label>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
                  {[
                    { id: "CROWD", label: "Crowd AI", icon: "bi-people-fill", desc: "Density & movement" },
                    { id: "QUEUE", label: "Queue AI", icon: "bi-align-start", desc: "Wait time & lines" },
                    { id: "FRS", label: "FRS Biometric", icon: "bi-person-bounding-box", desc: "Face matching" },
                    { id: "GENERAL", label: "General", icon: "bi-eye-fill", desc: "Overview CCTV" },
                    { id: "MULTI_PURPOSE", label: "Multi-Purpose", icon: "bi-layers-fill", desc: "Shared stream" },
                  ].map((p) => {
                    const sel = form.camera_type === p.id;
                    return (
                      <div
                        key={p.id}
                        onClick={() => handleChange("camera_type", p.id)}
                        style={{
                          padding: "10px 12px",
                          borderRadius: 6,
                          border: sel ? "2px solid var(--cc-blue)" : "1px solid var(--cc-border)",
                          background: sel ? "rgba(88,166,255,0.08)" : "var(--cc-bg-primary)",
                          cursor: "pointer",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700, fontSize: 12, color: sel ? "var(--cc-blue)" : "var(--cc-text-primary)" }}>
                          <i className={`bi ${p.icon}`} />
                          {p.label}
                        </div>
                        <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 4 }}>{p.desc}</div>
                      </div>
                    );
                  })}
                </div>
                <div
                  style={{
                    marginTop: 10,
                    padding: "8px 12px",
                    background: isLight ? "#f8fafc" : "rgba(255,255,255,0.02)",
                    borderRadius: 4,
                    fontSize: 11,
                    color: "var(--cc-text-secondary)",
                  }}
                >
                  <i className="bi bi-info-circle" style={{ marginRight: 6, color: "var(--cc-blue)" }} />
                  This selection determines which AI configuration can be assigned later. No AI inference is started during onboarding.
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── STEP 5: Review & Save ── */}
        {currentStep === 5 && (
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 16, color: "var(--cc-text-primary)" }}>
              Step 5: Review & Save Camera
            </div>

            {saveError && (
              <div
                style={{
                  padding: "10px 14px",
                  background: "rgba(248,81,73,0.08)",
                  border: "1px solid var(--cc-red)",
                  borderRadius: 6,
                  color: "var(--cc-red)",
                  fontSize: 12,
                  marginBottom: 14,
                }}
              >
                <i className="bi bi-exclamation-triangle-fill" style={{ marginRight: 6 }} />
                {saveError}
              </div>
            )}

            {saveSuccess && (
              <div
                style={{
                  padding: "12px 16px",
                  background: "rgba(63,185,80,0.1)",
                  border: "1px solid var(--cc-green)",
                  borderRadius: 6,
                  color: "var(--cc-green)",
                  fontWeight: 700,
                  fontSize: 13,
                  marginBottom: 14,
                  textAlign: "center",
                }}
              >
                <i className="bi bi-check-circle-fill" style={{ marginRight: 8 }} />
                Camera registered successfully! Redirecting to camera detail...
              </div>
            )}

            <div
              style={{
                background: isLight ? "#f8fafc" : "var(--cc-bg-primary)",
                borderRadius: 6,
                border: "1px solid var(--cc-border)",
                padding: 16,
                marginBottom: 18,
              }}
            >
              {[
                { label: "Camera ID", value: form.camera_id, mono: true },
                { label: "Name", value: form.name },
                { label: "Purpose / Type", value: form.camera_type },
                { label: "Zone", value: form.zone_code || "Not assigned" },
                { label: "Location", value: form.location_name || "—" },
                { label: "Private IP", value: form.private_ip || "—", mono: true },
                { label: "RTSP URL", value: form.rtsp_url ? form.rtsp_url.replace(/:\/\/[^@]+@/, "://***:***@") : "—", mono: true },
                {
                  label: "Stream Status",
                  value: testResult?.stream_available ? "ONLINE (Validated)" : "NOT_TESTED",
                  color: testResult?.stream_available ? "var(--cc-green)" : "var(--cc-yellow)",
                },
                { label: "Resolution", value: testResult?.resolution || "1080p (Default)" },
                { label: "FPS", value: `${testResult?.fps || 25} fps` },
              ].map((row) => (
                <div
                  key={row.label}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    padding: "6px 0",
                    borderBottom: "1px solid var(--cc-border-light)",
                    fontSize: 12,
                  }}
                >
                  <span style={{ color: "var(--cc-text-muted)" }}>{row.label}</span>
                  <span
                    style={{
                      fontFamily: row.mono ? "var(--cc-font-mono)" : "inherit",
                      fontWeight: 600,
                      color: row.color || "var(--cc-text-primary)",
                      textAlign: "right",
                      maxWidth: 420,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {row.value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Wizard Footer Controls */}
        <div
          style={{
            marginTop: 24,
            paddingTop: 14,
            borderTop: "1px solid var(--cc-border-light)",
            display: "flex",
            justifyContent: "space-between",
          }}
        >
          {currentStep > 1 ? (
            <button
              type="button"
              className="cc-btn cc-btn-secondary"
              onClick={() => setCurrentStep(currentStep - 1)}
              disabled={saving}
            >
              <i className="bi bi-arrow-left" style={{ marginRight: 6 }} />
              Previous
            </button>
          ) : (
            <div />
          )}

          {currentStep < 5 ? (
            <button
              type="button"
              className="cc-btn cc-btn-primary"
              onClick={() => setCurrentStep(currentStep + 1)}
              disabled={!canGoNext()}
            >
              Next
              <i className="bi bi-arrow-right" style={{ marginLeft: 6 }} />
            </button>
          ) : (
            <button
              type="button"
              className="cc-btn cc-btn-primary"
              onClick={handleSaveCamera}
              disabled={saving || saveSuccess}
              style={{ padding: "8px 24px", fontWeight: 700 }}
            >
              {saving ? (
                <>
                  <span className="spinner-border spinner-border-sm" style={{ marginRight: 6 }} />
                  Saving Camera...
                </>
              ) : (
                <>
                  <i className="bi bi-check2-circle" style={{ marginRight: 6 }} />
                  SAVE CAMERA
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
