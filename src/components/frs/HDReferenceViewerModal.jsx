import { useState } from "react";

const getImageUrl = (url) => {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("data:")) return url;
  const base = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
  return `${base}${url.startsWith("/") ? "" : "/"}${url}`;
};

export default function HDReferenceViewerModal({ candidate, onClose }) {
  const [zoom, setZoom] = useState(1);

  if (!candidate) return null;

  const handleZoomIn = () => setZoom((z) => Math.min(2.5, z + 0.25));
  const handleZoomOut = () => setZoom((z) => Math.max(0.75, z - 0.25));
  const handleReset = () => setZoom(1);

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0,0,0,0.85)",
        backdropFilter: "blur(6px)",
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 20,
      }}
      onClick={onClose}
    >
      <div
        className="cc-card"
        style={{
          width: "100%",
          maxWidth: 680,
          maxHeight: "90vh",
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
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <i className="bi bi-person-bounding-box" style={{ color: "var(--cc-accent)", fontSize: 16 }} />
            <div>
              <div className="cc-section-title">HD Database Reference Viewer</div>
              <div style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>
                Reference ID: <strong style={{ color: "var(--cc-text-primary)" }}>{candidate.referenceId}</strong>
              </div>
            </div>
          </div>
          <button className="cc-btn" onClick={onClose} style={{ padding: "4px 8px" }}>
            <i className="bi bi-x-lg" />
          </button>
        </div>

        {/* Image Display Area */}
        <div
          style={{
            flex: 1,
            minHeight: 340,
            background: "#080c14",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            overflow: "hidden",
            position: "relative",
            padding: 20,
          }}
        >
          <div
            style={{
              transform: `scale(${zoom})`,
              transition: "transform 0.2s ease-out",
              width: 260,
              height: 312,
              borderRadius: "var(--cc-radius)",
              overflow: "hidden",
              border: "2px solid var(--cc-border-strong)",
              boxShadow: "0 8px 32px rgba(0,0,0,0.8)",
            }}
          >
            <img
              src={getImageUrl(candidate.referenceImage || candidate.reference_image)}
              alt={candidate.referenceName || candidate.reference_name}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          </div>

          {/* Floating Zoom Controls */}
          <div
            style={{
              position: "absolute",
              bottom: 12,
              right: 12,
              display: "flex",
              gap: 4,
              background: "rgba(10,13,16,0.85)",
              border: "1px solid var(--cc-border)",
              borderRadius: "var(--cc-radius)",
              padding: "3px 6px",
            }}
          >
            <button className="cc-btn" onClick={handleZoomOut} title="Zoom Out" style={{ padding: "3px 8px" }}>
              <i className="bi bi-zoom-out" />
            </button>
            <span style={{ fontSize: 11, fontFamily: "var(--cc-font-mono)", alignSelf: "center", minWidth: 42, textAlign: "center", color: "var(--cc-text-primary)" }}>
              {Math.round(zoom * 100)}%
            </span>
            <button className="cc-btn" onClick={handleZoomIn} title="Zoom In" style={{ padding: "3px 8px" }}>
              <i className="bi bi-zoom-in" />
            </button>
            <button className="cc-btn" onClick={handleReset} title="Fit to screen" style={{ padding: "3px 8px", fontSize: 10 }}>
              Fit
            </button>
          </div>
        </div>

        {/* Metadata Details */}
        <div style={{ padding: "14px 16px", background: "var(--cc-bg-secondary)", borderTop: "1px solid var(--cc-border)" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, fontSize: 11 }}>
            <div>
              <div className="cc-label">Reference Name</div>
              <div style={{ fontWeight: 600, color: "var(--cc-text-primary)", marginTop: 2 }}>{candidate.referenceName}</div>
            </div>
            <div>
              <div className="cc-label">Category</div>
              <div style={{ fontWeight: 600, color: "var(--cc-accent)", marginTop: 2 }}>{candidate.category}</div>
            </div>
            <div>
              <div className="cc-label">Status</div>
              <div style={{ fontWeight: 600, color: "var(--cc-green)", marginTop: 2 }}>{candidate.referenceStatus}</div>
            </div>
            <div>
              <div className="cc-label">Last Updated</div>
              <div style={{ fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-muted)", marginTop: 2 }}>{candidate.lastUpdated}</div>
            </div>
          </div>

          <div
            style={{
              marginTop: 10,
              padding: "6px 10px",
              background: "var(--cc-bg-card)",
              border: "1px solid var(--cc-border)",
              borderRadius: "var(--cc-radius-sm)",
              fontSize: 10,
              color: "var(--cc-text-muted)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span>
              <i className="bi bi-shield-check" style={{ color: "var(--cc-green)", marginRight: 4 }} />
              Audit ID: AUD-REF-{candidate.referenceId} — Biometric vectors sealed & protected
            </span>
            <span style={{ fontFamily: "var(--cc-font-mono)" }}>
              {new Date().toLocaleTimeString("en-IN", { hour12: false })} IST
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
