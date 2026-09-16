// FRS Candidate Card — Dedicated Side-by-Side Review Card
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import HDReferenceViewerModal from "./HDReferenceViewerModal.jsx";
import FRSCandidateReviewModal from "./FRSCandidateReviewModal.jsx";
import { getBackendUrl } from "../../utils/urlConfig.js";

const getImageUrl = (url) => {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("data:")) return url;
  const base = getBackendUrl();
  return `${base}${url.startsWith("/") ? "" : "/"}${url}`;
};

export default function FRSCandidateCard({ candidate, onReviewUpdated }) {
  const navigate = useNavigate();
  const [showHDModal, setShowHDModal] = useState(false);
  const [showReviewModal, setShowReviewModal] = useState(false);

  if (!candidate) return null;

  const isPending = candidate.status === "PENDING_REVIEW";
  const isPossible = candidate.status === "POSSIBLE_MATCH";
  const isDismissed = candidate.status === "DISMISSED";

  const statusColor = isPending
    ? "var(--cc-orange)"
    : isPossible
    ? "var(--cc-yellow)"
    : isDismissed
    ? "var(--cc-text-muted)"
    : "var(--cc-green)";

  return (
    <>
      <div
        className="cc-card"
        style={{
          borderLeft: `3px solid ${statusColor}`,
          padding: 0,
          overflow: "hidden",
          marginBottom: 14,
          background: "var(--cc-bg-card)",
          boxShadow: "var(--cc-shadow)",
        }}
      >
        {/* Card Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "9px 14px",
            background: "var(--cc-bg-secondary)",
            borderBottom: "1px solid var(--cc-border)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <i className="bi bi-person-bounding-box" style={{ color: candidate.category === "Pickpocket Watchlist" ? "var(--cc-red)" : "var(--cc-accent)", fontSize: 16 }} />
            <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.05em", color: candidate.category === "Pickpocket Watchlist" ? "var(--cc-red)" : "var(--cc-text-primary)" }}>
              {candidate.category === "Missing Person Registry"
                ? "POSSIBLE MISSING PERSON CANDIDATE"
                : candidate.category === "Pickpocket Watchlist"
                ? "🚨 PICKPOCKET WATCHLIST ALERT"
                : "POSSIBLE WATCHLIST MATCH"}
            </span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span
              style={{
                fontSize: 9,
                fontWeight: 800,
                letterSpacing: "0.08em",
                padding: "2px 7px",
                borderRadius: "var(--cc-radius-sm)",
                background: (candidate.priority === "HIGH" || candidate.priority === "CRITICAL") ? "var(--cc-red-dim)" : "var(--cc-yellow-dim)",
                color: (candidate.priority === "HIGH" || candidate.priority === "CRITICAL") ? "var(--cc-red)" : "var(--cc-yellow)",
                border: `1px solid ${(candidate.priority === "HIGH" || candidate.priority === "CRITICAL") ? "var(--cc-red-border)" : "var(--cc-yellow-border)"}`,
              }}
            >
              {candidate.priority} PRIORITY
            </span>

            <span
              className="cc-badge"
              style={{
                fontSize: 9,
                background: isPending ? "var(--cc-orange-dim)" : "var(--cc-bg-panel)",
                color: statusColor,
                borderColor: isPending ? "var(--cc-orange-border)" : "var(--cc-border)",
              }}
            >
              {candidate.status.replace(/_/g, " ")}
            </span>
          </div>
        </div>

        {/* Side-by-Side Images & Match Score Center Stage */}
        <div style={{ padding: "14px 16px" }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "170px 1fr 170px",
              gap: 16,
              alignItems: "center",
              marginBottom: 16,
            }}
          >
            {/* Left: Detected Face */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
              <div className="cc-label" style={{ marginBottom: 6, color: "var(--cc-blue)", width: "100%", textAlign: "center" }}>
                <i className="bi bi-camera-video" style={{ marginRight: 4 }} />
                DETECTED FACE
              </div>

              <div
                style={{
                  width: 160,
                  height: 190,
                  background: "#080c14",
                  borderRadius: "var(--cc-radius)",
                  border: "1px solid var(--cc-border-strong)",
                  overflow: "hidden",
                  position: "relative",
                  boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
                }}
              >
                <img
                  src={getImageUrl(candidate.detectedImage || candidate.detected_image || candidate.detected_image_path || candidate.crop_url)}
                  alt="Detected face crop"
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                  onError={(e) => {
                    const fallback = getImageUrl(candidate.referenceImage || candidate.reference_image || candidate.reference_image_path);
                    if (fallback && e.target.src !== fallback) {
                      e.target.src = fallback;
                    }
                  }}
                />
                <div
                  style={{
                    position: "absolute",
                    bottom: 4,
                    left: 6,
                    fontSize: 8,
                    fontFamily: "var(--cc-font-mono)",
                    color: "rgba(255,255,255,0.7)",
                  }}
                >
                  {candidate.cameraId}
                </div>
              </div>
              <div style={{ fontSize: 9, color: "var(--cc-text-muted)", marginTop: 4 }}>
                {candidate.imageQuality}
              </div>
            </div>

            {/* Middle: Prominent Match Score & Confidence */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", padding: "0 8px" }}>
              <div className="cc-label" style={{ marginBottom: 2 }}>MATCH SCORE</div>
              <div
                style={{
                  fontFamily: "var(--cc-font-mono)",
                  fontSize: 32,
                  fontWeight: 800,
                  color: candidate.matchScore >= 90 ? "var(--cc-orange)" : "var(--cc-yellow)",
                  lineHeight: 1,
                  marginBottom: 6,
                }}
              >
                {candidate.matchScore}%
              </div>

              {/* Progress Bar */}
              <div style={{ width: "100%", maxWidth: 180, height: 6, background: "var(--cc-border)", borderRadius: 3, overflow: "hidden", marginBottom: 6 }}>
                <div
                  style={{
                    width: `${candidate.matchScore}%`,
                    height: "100%",
                    background: candidate.matchScore >= 90 ? "var(--cc-orange)" : "var(--cc-yellow)",
                  }}
                />
              </div>

              <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginBottom: 10 }}>
                Model Confidence: <strong style={{ color: "var(--cc-text-primary)" }}>{candidate.matchScore}%</strong>
              </div>

              {/* Quick Status Tag */}
              <div
                style={{
                  padding: "4px 8px",
                  background: "var(--cc-orange-dim)",
                  border: "1px solid var(--cc-orange-border)",
                  borderRadius: "var(--cc-radius-sm)",
                  fontSize: 10,
                  fontWeight: 700,
                  color: "var(--cc-orange)",
                  letterSpacing: "0.04em",
                }}
              >
                REQUIRES HUMAN REVIEW
              </div>
            </div>

            {/* Right: Database Reference Photo */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
              <div className="cc-label" style={{ marginBottom: 6, color: "var(--cc-green)", width: "100%", textAlign: "center" }}>
                <i className="bi bi-person-badge" style={{ marginRight: 4 }} />
                DATABASE REFERENCE
              </div>

              <div
                style={{
                  width: 160,
                  height: 190,
                  background: "#080c14",
                  borderRadius: "var(--cc-radius)",
                  border: "1px solid var(--cc-border-strong)",
                  overflow: "hidden",
                  position: "relative",
                  cursor: "pointer",
                  boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
                }}
                onClick={() => setShowHDModal(true)}
                title="Click to open HD reference viewer"
              >
                <img
                  src={getImageUrl(candidate.referenceImage || candidate.reference_image)}
                  alt={candidate.referenceName || candidate.reference_name}
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
                <div
                  style={{
                    position: "absolute",
                    top: 6,
                    right: 6,
                    background: "rgba(0,0,0,0.6)",
                    borderRadius: 2,
                    padding: "2px 4px",
                    fontSize: 9,
                    color: "#fff",
                  }}
                >
                  <i className="bi bi-arrows-fullscreen" /> HD
                </div>
                <div
                  style={{
                    position: "absolute",
                    bottom: 4,
                    left: 6,
                    fontSize: 8,
                    fontFamily: "var(--cc-font-mono)",
                    color: "rgba(255,255,255,0.7)",
                  }}
                >
                  {candidate.referenceId}
                </div>
              </div>
              <button
                className="cc-btn"
                style={{ fontSize: 9, padding: "2px 8px", marginTop: 4 }}
                onClick={() => setShowHDModal(true)}
              >
                <i className="bi bi-zoom-in" /> View HD Photo
              </button>
            </div>
          </div>

          {/* Reference & Location Meta Grid */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: 10,
              padding: "10px 12px",
              background: "var(--cc-bg-secondary)",
              border: "1px solid var(--cc-border-light)",
              borderRadius: "var(--cc-radius)",
              fontSize: 11,
              marginBottom: 12,
            }}
          >
            <div>
              <div className="cc-label">Reference Name</div>
              <div style={{ fontWeight: 600, color: "var(--cc-text-primary)", marginTop: 2 }}>
                {candidate.referenceName}
              </div>
            </div>

            <div>
              <div className="cc-label">Reference ID</div>
              <div style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 700, color: "var(--cc-accent)", marginTop: 2 }}>
                {candidate.referenceId}
              </div>
            </div>

            <div>
              <div className="cc-label">Camera</div>
              <Link
                to={`/frs/cameras/${candidate.cameraId}`}
                style={{
                  fontFamily: "var(--cc-font-mono)",
                  fontWeight: 600,
                  color: "var(--cc-accent)",
                  marginTop: 2,
                  display: "inline-block",
                  textDecoration: "underline",
                }}
                title="Open FRS camera detail"
              >
                {candidate.cameraId}
              </Link>
            </div>

            <div>
              <div className="cc-label">Timestamp</div>
              <div style={{ fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-primary)", marginTop: 2 }}>
                {candidate.dateStr} • {candidate.timeStr}
              </div>
            </div>

            <div style={{ gridColumn: "1 / -1", display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: "1px solid var(--cc-border)", paddingTop: 6, marginTop: 4 }}>
              <div>
                <span className="cc-label" style={{ marginRight: 6 }}>Location:</span>
                <span style={{ fontWeight: 600, color: "var(--cc-text-primary)" }}>{candidate.location} ({candidate.zone})</span>
              </div>
              <div style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>
                Category: <strong>{candidate.category}</strong>
              </div>
            </div>
          </div>

          {/* Legal / Ethical Status Warning Box */}
          <div
            style={{
              padding: "6px 12px",
              background: "var(--cc-orange-dim)",
              border: "1px solid var(--cc-orange-border)",
              borderRadius: "var(--cc-radius-sm)",
              fontSize: 11,
              color: "var(--cc-orange)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 12,
            }}
          >
            <span>
              <strong>STATUS: REQUIRES HUMAN REVIEW</strong> — Biometric candidate match must be corroborated by authorized officer before taking action.
            </span>
          </div>

          {/* Action Buttons */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <button
              className="cc-btn cc-btn-primary"
              style={{ padding: "6px 16px", fontSize: 11, fontWeight: 700 }}
              onClick={() => setShowReviewModal(true)}
            >
              <i className="bi bi-shield-check" /> REVIEW CANDIDATE
            </button>

            <button
              className="cc-btn"
              style={{ fontSize: 11 }}
              onClick={() => navigate(`/frs/cameras/${candidate.cameraId}`)}
            >
              <i className="bi bi-camera-video-fill" /> VIEW CAMERA
            </button>

            <button
              className="cc-btn"
              style={{ fontSize: 11 }}
              onClick={() => navigate("/live-map")}
            >
              <i className="bi bi-map-fill" /> VIEW LOCATION
            </button>

            <button
              className="cc-btn"
              style={{ fontSize: 11, marginLeft: "auto", color: "var(--cc-text-muted)" }}
              onClick={() => setShowReviewModal(true)}
            >
              <i className="bi bi-x-circle" /> DISMISS
            </button>
          </div>
        </div>
      </div>

      {/* HD Photo Modal */}
      {showHDModal && (
        <HDReferenceViewerModal candidate={candidate} onClose={() => setShowHDModal(false)} />
      )}

      {/* Review & Investigation Modal */}
      {showReviewModal && (
        <FRSCandidateReviewModal
          candidate={candidate}
          onClose={() => setShowReviewModal(false)}
          onReviewed={onReviewUpdated}
        />
      )}
    </>
  );
}
