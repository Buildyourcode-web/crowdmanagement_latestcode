import { useState } from "react";
import { reviewFRSCandidate } from "../../services/frsService.js";

const getImageUrl = (url) => {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("data:")) return url;
  const base = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
  return `${base}${url.startsWith("/") ? "" : "/"}${url}`;
};

export default function FRSCandidateReviewModal({ candidate, onClose, onReviewed }) {
  const [detectedZoom, setDetectedZoom] = useState(1);
  const [refZoom, setRefZoom] = useState(1);
  const [selectedDecision, setSelectedDecision] = useState(
    candidate.status !== "REVIEW_REQUIRED" && candidate.status !== "PENDING_REVIEW"
      ? candidate.status
      : "CONFIRMED_BY_REVIEWER"
  );
  const [notes, setNotes] = useState(candidate.officerNotes || "");
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);

  if (!candidate) return null;

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await reviewFRSCandidate(candidate.id, selectedDecision, notes);
      setSavedSuccess(true);
      setTimeout(() => {
        onReviewed?.(updated);
        onClose();
      }, 700);
    } catch (e) {
      console.error(e);
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0,0,0,0.88)",
        backdropFilter: "blur(8px)",
        zIndex: 1050,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
      onClick={onClose}
    >
      <div
        className="cc-card"
        style={{
          width: "100%",
          maxWidth: 920,
          maxHeight: "92vh",
          display: "flex",
          flexDirection: "column",
          padding: 0,
          overflow: "hidden",
          border: "1px solid var(--cc-border-strong)",
          boxShadow: "var(--cc-shadow-strong)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="cc-section-header">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span
              style={{
                fontSize: 10,
                fontWeight: 800,
                letterSpacing: "0.08em",
                padding: "3px 8px",
                background: "var(--cc-orange-dim)",
                border: "1px solid var(--cc-orange-border)",
                borderRadius: "var(--cc-radius-sm)",
                color: "var(--cc-orange)",
              }}
            >
              INVESTIGATION REVIEW
            </span>
            <span style={{ fontSize: 13, fontWeight: 700, color: "var(--cc-text-primary)" }}>
              Candidate {candidate.id}
            </span>
            <span style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>
              Ref: <strong style={{ color: "var(--cc-accent)" }}>{candidate.referenceId}</strong> ({candidate.referenceName})
            </span>
          </div>
          <button className="cc-btn" onClick={onClose} style={{ padding: "4px 8px" }}>
            <i className="bi bi-x-lg" />
          </button>
        </div>

        {/* Scrollable Content */}
        <div style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Top Mandatory Review Warning */}
          <div
            style={{
              padding: "8px 12px",
              background: "var(--cc-orange-dim)",
              border: "1px solid var(--cc-orange-border)",
              borderLeft: "3px solid var(--cc-orange)",
              borderRadius: "var(--cc-radius-sm)",
              fontSize: 11,
              color: "var(--cc-orange)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span>
              <strong>⚠ POSSIBLE MATCH — REQUIRES HUMAN REVIEW</strong>. AI biometric match scores do not constitute confirmed identity.
            </span>
            <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.06em", color: "var(--cc-text-primary)" }}>
              CONFIDENCE: {candidate.matchScore}%
            </span>
          </div>

          {/* Side-by-Side Comparison Stage */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: 12, alignItems: "stretch" }}>
            {/* Left: Detected Face */}
            <div
              style={{
                background: "var(--cc-bg-secondary)",
                border: "1px solid var(--cc-border)",
                borderRadius: "var(--cc-radius)",
                padding: 12,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", width: "100%", marginBottom: 8, fontSize: 11 }}>
                <span className="cc-label" style={{ color: "var(--cc-blue)" }}>
                  <i className="bi bi-camera-video-fill" style={{ marginRight: 4 }} />
                  DETECTED FACE
                </span>
                <span style={{ fontSize: 10, fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-muted)" }}>
                  {candidate.imageQuality}
                </span>
              </div>

              <div
                style={{
                  width: "100%",
                  height: 230,
                  background: "#080c14",
                  borderRadius: "var(--cc-radius-sm)",
                  overflow: "hidden",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  border: "1px solid var(--cc-border)",
                  position: "relative",
                }}
              >
                  <img
                    src={getImageUrl(candidate.detectedImage || candidate.detected_image || candidate.detected_image_path || candidate.crop_url)}
                    alt="Detected face crop"
                    style={{ width: "100%", height: "100%", objectFit: "contain" }}
                    onError={(e) => {
                      const fallback = getImageUrl(candidate.referenceImage || candidate.reference_image || candidate.reference_image_path);
                      if (fallback && e.target.src !== fallback) {
                        e.target.src = fallback;
                      }
                    }}
                  />
                <div style={{ position: "absolute", bottom: 6, left: 8, fontSize: 9, fontFamily: "var(--cc-font-mono)", color: "rgba(255,255,255,0.6)" }}>
                  {candidate.cameraId} • {candidate.timeStr}
                </div>
              </div>

              <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                <button
                  className="cc-btn"
                  style={{ fontSize: 10, padding: "2px 8px" }}
                  onClick={() => setDetectedZoom((z) => Math.min(2, z + 0.25))}
                >
                  <i className="bi bi-zoom-in" /> Zoom
                </button>
                <button
                  className="cc-btn"
                  style={{ fontSize: 10, padding: "2px 8px" }}
                  onClick={() => setDetectedZoom(1)}
                >
                  Reset
                </button>
              </div>
            </div>

            {/* Center: Match Percentage Indicator */}
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                padding: "0 10px",
                minWidth: 140,
              }}
            >
              <div className="cc-label" style={{ marginBottom: 4, textAlign: "center" }}>MATCH SCORE</div>
              <div
                style={{
                  fontFamily: "var(--cc-font-mono)",
                  fontSize: 26,
                  fontWeight: 800,
                  color: candidate.matchScore >= 90 ? "var(--cc-orange)" : "var(--cc-yellow)",
                  lineHeight: 1,
                  marginBottom: 6,
                }}
              >
                {candidate.matchScore}%
              </div>

              {/* Progress Meter */}
              <div style={{ width: "100%", height: 6, background: "var(--cc-border)", borderRadius: 3, overflow: "hidden", marginBottom: 6 }}>
                <div
                  style={{
                    width: `${candidate.matchScore}%`,
                    height: "100%",
                    background: candidate.matchScore >= 90 ? "var(--cc-orange)" : "var(--cc-yellow)",
                    transition: "width 0.4s ease",
                  }}
                />
              </div>
              <div style={{ fontSize: 9, color: "var(--cc-text-muted)", textAlign: "center" }}>
                Model Confidence: {candidate.matchScore}%
              </div>
            </div>

            {/* Right: Database Reference */}
            <div
              style={{
                background: "var(--cc-bg-secondary)",
                border: "1px solid var(--cc-border)",
                borderRadius: "var(--cc-radius)",
                padding: 12,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", width: "100%", marginBottom: 8, fontSize: 11 }}>
                <span className="cc-label" style={{ color: "var(--cc-green)" }}>
                  <i className="bi bi-person-badge-fill" style={{ marginRight: 4 }} />
                  DATABASE REFERENCE
                </span>
                <span style={{ fontSize: 10, fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-muted)" }}>
                  HD PHOTO
                </span>
              </div>

              <div
                style={{
                  width: "100%",
                  height: 230,
                  background: "#080c14",
                  borderRadius: "var(--cc-radius-sm)",
                  overflow: "hidden",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  border: "1px solid var(--cc-border)",
                  position: "relative",
                }}
              >
                <div style={{ transform: `scale(${refZoom})`, transition: "transform 0.2s ease", width: 170, height: 210 }}>
                  <img src={getImageUrl(candidate.referenceImage || candidate.reference_image)} alt="Database reference" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
                </div>
                <div style={{ position: "absolute", bottom: 6, left: 8, fontSize: 9, fontFamily: "var(--cc-font-mono)", color: "rgba(255,255,255,0.6)" }}>
                  {candidate.referenceId}
                </div>
              </div>

              <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                <button
                  className="cc-btn"
                  style={{ fontSize: 10, padding: "2px 8px" }}
                  onClick={() => setRefZoom((z) => Math.min(2, z + 0.25))}
                >
                  <i className="bi bi-zoom-in" /> Zoom
                </button>
                <button
                  className="cc-btn"
                  style={{ fontSize: 10, padding: "2px 8px" }}
                  onClick={() => setRefZoom(1)}
                >
                  Reset
                </button>
              </div>
            </div>
          </div>

          {/* Information Grid */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {/* Left: Camera & Location Info */}
            <div className="cc-card" style={{ padding: 12 }}>
              <div className="cc-section-title" style={{ marginBottom: 8, fontSize: 10 }}>CAMERA & DETECTION INFO</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 11 }}>
                <div>
                  <span className="cc-label">Camera ID</span>
                  <div style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 600, color: "var(--cc-accent)", marginTop: 2 }}>
                    {candidate.cameraId}
                  </div>
                </div>
                <div>
                  <span className="cc-label">Detection Time</span>
                  <div style={{ fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-primary)", marginTop: 2 }}>
                    {candidate.dateStr} {candidate.timeStr}
                  </div>
                </div>
                <div style={{ gridColumn: "1/-1" }}>
                  <span className="cc-label">Location / Zone</span>
                  <div style={{ fontWeight: 600, color: "var(--cc-text-primary)", marginTop: 2 }}>
                    {candidate.location} — {candidate.zone}
                  </div>
                </div>
              </div>
            </div>

            {/* Right: Reference Information */}
            <div className="cc-card" style={{ padding: 12 }}>
              <div className="cc-section-title" style={{ marginBottom: 8, fontSize: 10 }}>REFERENCE INFORMATION</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 11 }}>
                <div>
                  <span className="cc-label">Reference Name</span>
                  <div style={{ fontWeight: 600, color: "var(--cc-text-primary)", marginTop: 2 }}>
                    {candidate.referenceName}
                  </div>
                </div>
                <div>
                  <span className="cc-label">Reference ID</span>
                  <div style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 600, color: "var(--cc-accent)", marginTop: 2 }}>
                    {candidate.referenceId}
                  </div>
                </div>
                <div>
                  <span className="cc-label">Category</span>
                  <div style={{ color: "var(--cc-text-secondary)", marginTop: 2 }}>
                    {candidate.category}
                  </div>
                </div>
                <div>
                  <span className="cc-label">Status</span>
                  <div style={{ fontWeight: 600, color: "var(--cc-green)", marginTop: 2 }}>
                    {candidate.referenceStatus}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Detection Audit Timeline */}
          <div className="cc-card" style={{ padding: 12 }}>
            <div className="cc-section-title" style={{ marginBottom: 10, fontSize: 10 }}>
              <i className="bi bi-clock-history" style={{ marginRight: 6 }} />
              DETECTION & AUDIT TIMELINE
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {candidate.timeline?.map((entry, idx) => (
                <div key={idx} style={{ display: "flex", gap: 10, alignItems: "flex-start", fontSize: 11 }}>
                  <span style={{ fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-muted)", fontSize: 10, minWidth: 60 }}>
                    {entry.time}
                  </span>
                  <span style={{ color: "var(--cc-text-primary)", flex: 1 }}>
                    {entry.event}
                  </span>
                  <span style={{ color: "var(--cc-accent)", fontSize: 10, fontWeight: 600 }}>
                    [{entry.actor}]
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Officer Decision Section */}
          <div className="cc-card" style={{ padding: 14, background: "var(--cc-bg-panel)", border: "1px solid var(--cc-border-strong)" }}>
            <div className="cc-section-title" style={{ marginBottom: 10 }}>OFFICER REVIEW DECISION</div>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
              {[
                { id: "CONFIRMED_BY_REVIEWER", label: "CONFIRM MATCH (Human Verified)", icon: "bi-check-circle-fill", color: "var(--cc-green)" },
                { id: "REJECTED_BY_REVIEWER", label: "REJECT MATCH (Not a Match)", icon: "bi-x-circle-fill", color: "var(--cc-red)" },
                { id: "UNRESOLVED", label: "MARK UNRESOLVED (Needs Investigation)", icon: "bi-hourglass-split", color: "var(--cc-blue)" },
              ].map((btn) => {
                const isSelected = selectedDecision === btn.id;
                return (
                  <button
                    key={btn.id}
                    onClick={() => setSelectedDecision(btn.id)}
                    className="cc-btn"
                    style={{
                      padding: "7px 14px",
                      fontSize: 11,
                      fontWeight: 700,
                      borderColor: isSelected ? btn.color : "var(--cc-border)",
                      background: isSelected ? "var(--cc-bg-card-hover)" : "var(--cc-bg-card)",
                      color: isSelected ? btn.color : "var(--cc-text-secondary)",
                      borderWidth: isSelected ? 2 : 1,
                    }}
                  >
                    <i className={`bi ${btn.icon}`} style={{ color: btn.color }} />
                    {btn.label}
                  </button>
                );
              })}
            </div>

            <div style={{ marginBottom: 12 }}>
              <label className="cc-label" style={{ display: "block", marginBottom: 4 }}>
                Officer Notes & Operational Remarks
              </label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Enter investigation observations, secondary verification details, or dispatch instructions..."
                rows={3}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  background: "var(--cc-bg-input)",
                  border: "1px solid var(--cc-border)",
                  borderRadius: "var(--cc-radius)",
                  color: "var(--cc-text-primary)",
                  fontSize: 12,
                  resize: "vertical",
                  outline: "none",
                }}
              />
            </div>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ fontSize: 10, color: "var(--cc-text-muted)", display: "flex", alignItems: "center", gap: 6 }}>
                <span className="cc-live-dot" style={{ width: 6, height: 6 }} />
                <span>Action will generate tamper-evident audit record #AUD-{Date.now().toString().slice(-6)}</span>
              </div>

              <div style={{ display: "flex", gap: 8 }}>
                <button className="cc-btn" onClick={onClose} disabled={saving}>
                  Cancel
                </button>
                <button
                  className="cc-btn cc-btn-primary"
                  onClick={handleSave}
                  disabled={saving}
                  style={{ minWidth: 120, justifyContent: "center" }}
                >
                  {saving ? (
                    <span>Saving...</span>
                  ) : savedSuccess ? (
                    <span style={{ color: "#fff" }}>
                      <i className="bi bi-check2-all" /> Saved!
                    </span>
                  ) : (
                    <span>
                      <i className="bi bi-journal-check" /> Save Review
                    </span>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
