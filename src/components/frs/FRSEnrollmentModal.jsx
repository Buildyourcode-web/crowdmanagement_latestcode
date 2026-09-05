import { useState, useRef } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export default function FRSEnrollmentModal({ isOpen, onClose, onEnrolled }) {
  const [enrollMode, setEnrollMode] = useState("file"); // "file" | "camera"
  const [name, setName] = useState("");
  const [category, setCategory] = useState("Authorized Watchlist");
  const [selectedFile, setSelectedFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const fileInputRef = useRef(null);

  if (!isOpen) return null;

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    setError(null);
    setPreviewUrl(URL.createObjectURL(file));
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    setError(null);
    setPreviewUrl(URL.createObjectURL(file));
  };

  const handleFileSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!name.trim()) {
      setError("Please enter the person's name.");
      return;
    }
    if (!selectedFile) {
      setError("Please upload a frontal face photo.");
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    const formData = new FormData();
    formData.append("name", name.trim());
    formData.append("category", category);
    formData.append("photo", selectedFile);

    try {
      const token = localStorage.getItem("byc_access_token");
      const headers = { "Content-Type": "multipart/form-data" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await axios.post(`${API_BASE}/api/v1/frs-engine/enroll`, formData, { headers });
      setSuccess(res.data);
      if (onEnrolled) onEnrolled(res.data);
      setTimeout(() => {
        onClose();
      }, 1800);
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || "Failed to enroll person.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleCameraSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!name.trim()) {
      setError("Please enter the person's name.");
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const token = localStorage.getItem("byc_access_token");
      const headers = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await axios.post(
        `${API_BASE}/api/v1/frs-engine/enroll-from-camera`,
        {
          name: name.trim(),
          category,
          camera_id: "CAM-KHB-001",
        },
        { headers }
      );
      setSuccess(res.data);
      if (onEnrolled) onEnrolled(res.data);
      setTimeout(() => {
        onClose();
      }, 1800);
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || "Failed to enroll from live camera.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0, 0, 0, 0.75)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: 20,
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="cc-card"
        style={{
          width: "100%",
          maxWidth: 480,
          background: "var(--cc-bg-card, #111927)",
          border: "1px solid var(--cc-border, #1e293b)",
          borderRadius: 8,
          boxShadow: "0 20px 40px rgba(0,0,0,0.6)",
          overflow: "hidden",
        }}
      >
        {/* Modal Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "14px 18px",
            background: "var(--cc-bg-secondary, #0a0f18)",
            borderBottom: "1px solid var(--cc-border, #1e293b)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <i className="bi bi-person-plus-fill" style={{ color: "var(--cc-accent, #38bdf8)", fontSize: 18 }} />
            <div>
              <div style={{ fontSize: 14, fontWeight: 800, color: "var(--cc-text-primary, #f8fafc)" }}>
                Enroll Watchlist Person
              </div>
              <div style={{ fontSize: 11, color: "var(--cc-text-muted, #94a3b8)" }}>
                Biometric Embedding Extraction via InsightFace Buffalo_L
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--cc-text-muted)",
              cursor: "pointer",
              fontSize: 18,
            }}
          >
            <i className="bi bi-x-lg" />
          </button>
        </div>

        {/* Mode Selector Tabs */}
        <div style={{ display: "flex", background: "var(--cc-bg-secondary, #0a0f18)", borderBottom: "1px solid var(--cc-border)", padding: "8px 18px", gap: 8 }}>
          <button
            type="button"
            className={`cc-btn${enrollMode === "file" ? " cc-btn-primary" : ""}`}
            style={{ flex: 1, justifyContent: "center", fontSize: 12, padding: "6px 12px" }}
            onClick={() => { setEnrollMode("file"); setError(null); }}
          >
            <i className="bi bi-file-earmark-image" style={{ marginRight: 6 }} /> Upload Photo File
          </button>
          <button
            type="button"
            className={`cc-btn${enrollMode === "camera" ? " cc-btn-primary" : ""}`}
            style={{ flex: 1, justifyContent: "center", fontSize: 12, padding: "6px 12px" }}
            onClick={() => { setEnrollMode("camera"); setError(null); }}
          >
            <i className="bi bi-camera-video" style={{ marginRight: 6 }} /> 1-Click Live Camera Snapshot
          </button>
        </div>

        {/* Form Body */}
        <div style={{ padding: "18px 20px" }}>
          {error && (
            <div
              style={{
                padding: "8px 12px",
                marginBottom: 14,
                background: "rgba(239, 68, 68, 0.15)",
                border: "1px solid #ef4444",
                borderRadius: 4,
                color: "#f87171",
                fontSize: 12,
              }}
            >
              <i className="bi bi-exclamation-triangle-fill" style={{ marginRight: 6 }} />
              {error}
            </div>
          )}

          {success && (
            <div
              style={{
                padding: "8px 12px",
                marginBottom: 14,
                background: "rgba(34, 197, 94, 0.15)",
                border: "1px solid #22c55e",
                borderRadius: 4,
                color: "#4ade80",
                fontSize: 12,
              }}
            >
              <i className="bi bi-check-circle-fill" style={{ marginRight: 6 }} />
              {success.message} ({success.reference_id}) — Face Quality: {Math.round(success.det_score * 100)}%
            </div>
          )}

          {/* Name Field */}
          <div style={{ marginBottom: 14 }}>
            <label className="cc-label" style={{ display: "block", marginBottom: 6 }}>
              FULL NAME / IDENTITY LABEL *
            </label>
            <input
              type="text"
              className="cc-input"
              style={{ width: "100%", padding: "8px 12px", fontSize: 13 }}
              placeholder="e.g. Ram, Satish, Praveen Kumar"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={loading}
              autoFocus
            />
          </div>

          {/* Category Field */}
          <div style={{ marginBottom: 14 }}>
            <label className="cc-label" style={{ display: "block", marginBottom: 6 }}>
              WATCHLIST CATEGORY
            </label>
            <select
              className="cc-input"
              style={{ width: "100%", padding: "8px 12px", fontSize: 13 }}
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              disabled={loading}
            >
              <option value="Authorized Watchlist">Authorized Watchlist</option>
              <option value="VIP / Dignitary">VIP / Dignitary</option>
              <option value="Missing Person Registry">Missing Person Registry</option>
              <option value="Suspect Under Surveillance">Suspect Under Surveillance</option>
            </select>
          </div>

          {/* Mode 1: File Upload */}
          {enrollMode === "file" && (
            <div style={{ marginBottom: 18 }}>
              <label className="cc-label" style={{ display: "block", marginBottom: 6 }}>
                FRONTAL FACE PHOTOGRAPH *
              </label>
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                style={{
                  border: "2px dashed var(--cc-border, #334155)",
                  borderRadius: 6,
                  padding: previewUrl ? 10 : 20,
                  textAlign: "center",
                  cursor: "pointer",
                  background: "rgba(15, 23, 42, 0.4)",
                  transition: "border-color 0.2s",
                }}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  style={{ display: "none" }}
                  onChange={handleFileChange}
                />

                {previewUrl ? (
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 14 }}>
                    <img
                      src={previewUrl}
                      alt="Preview"
                      style={{
                        width: 75,
                        height: 90,
                        objectFit: "cover",
                        borderRadius: 4,
                        border: "1px solid var(--cc-border)",
                      }}
                    />
                    <div style={{ textAlign: "left" }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: "var(--cc-text-primary)" }}>
                        {selectedFile?.name}
                      </div>
                      <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 2 }}>
                        {Math.round((selectedFile?.size || 0) / 1024)} KB · Click to change photo
                      </div>
                    </div>
                  </div>
                ) : (
                  <>
                    <i className="bi bi-cloud-arrow-up" style={{ fontSize: 26, color: "var(--cc-accent)" }} />
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--cc-text-primary)", marginTop: 4 }}>
                      Click or drag & drop frontal photo here
                    </div>
                    <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 2 }}>
                      Clear frontal portrait photo recommended (tight crop saved automatically)
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Mode 2: Live Camera Snapshot */}
          {enrollMode === "camera" && (
            <div style={{ marginBottom: 18 }}>
              <label className="cc-label" style={{ display: "block", marginBottom: 6 }}>
                LIVE CCTV CAMERA VIEW (Face Camera Directly)
              </label>
              <div
                style={{
                  position: "relative",
                  width: "100%",
                  height: 190,
                  background: "#000",
                  borderRadius: 6,
                  overflow: "hidden",
                  border: "1px solid var(--cc-border)",
                }}
              >
                <img
                  src={`${API_BASE}/api/v1/frs-engine/cameras/CAM-KHB-001/stream`}
                  alt="Live RTSP Camera Stream"
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
                <div
                  style={{
                    position: "absolute",
                    bottom: 6,
                    left: 8,
                    background: "rgba(0,0,0,0.7)",
                    padding: "2px 6px",
                    borderRadius: 3,
                    fontSize: 10,
                    color: "#22c55e",
                    fontFamily: "var(--cc-font-mono)",
                  }}
                >
                  ● CAM-KHB-001 LIVE STREAM
                </div>
              </div>
              <div style={{ fontSize: 11, color: "var(--cc-text-muted)", marginTop: 6, textAlign: "center" }}>
                Face the camera straight on with good lighting. The system crops a clean portrait automatically.
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button
              type="button"
              className="cc-btn"
              onClick={onClose}
              disabled={loading}
              style={{ padding: "7px 14px", fontSize: 12 }}
            >
              Cancel
            </button>

            {enrollMode === "file" ? (
              <button
                type="button"
                className="cc-btn cc-btn-primary"
                onClick={handleFileSubmit}
                disabled={loading}
                style={{ padding: "7px 18px", fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}
              >
                {loading ? (
                  <>
                    <span className="spinner-border spinner-border-sm" style={{ width: 12, height: 12 }} />
                    Extracting 512-D Embedding...
                  </>
                ) : (
                  <>
                    <i className="bi bi-shield-lock-fill" /> Enroll Photo into Gallery
                  </>
                )}
              </button>
            ) : (
              <button
                type="button"
                className="cc-btn cc-btn-primary"
                onClick={handleCameraSubmit}
                disabled={loading}
                style={{ padding: "7px 18px", fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}
              >
                {loading ? (
                  <>
                    <span className="spinner-border spinner-border-sm" style={{ width: 12, height: 12 }} />
                    Capturing & Enrolling...
                  </>
                ) : (
                  <>
                    <i className="bi bi-camera-fill" /> Capture Snapshot & Enroll
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
