// Live Map — full screen GIS command view
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import MapView from "../components/map/MapView.jsx";

const LAYER_OPTIONS = [
  { key: "zones", label: "Crowd Density / Zones", default: true },
  { key: "cameras", label: "Cameras", default: true },
  { key: "gates", label: "Gates", default: true },
  { key: "heatmap", label: "Heatmap Overlay", default: false },
];

export default function LiveMap() {
  const navigate = useNavigate();
  const [layers, setLayers] = useState(Object.fromEntries(LAYER_OPTIONS.map((l) => [l.key, l.default])));
  const [showLayerPanel, setShowLayerPanel] = useState(true);

  const toggleLayer = (key) => setLayers((prev) => ({ ...prev, [key]: !prev[key] }));

  return (
    <div className="cc-page-fullscreen" style={{ height: "100%", position: "relative", display: "flex", flexDirection: "column" }}>
      {/* Topbar */}
      <div
        style={{
          display: "flex", alignItems: "center", gap: 10, padding: "8px 14px",
          background: "rgba(10,13,16,0.95)", borderBottom: "1px solid var(--cc-border)",
          zIndex: 10, flexShrink: 0,
        }}
      >
        <button className="cc-btn" onClick={() => navigate("/dashboard")}>
          <i className="bi bi-arrow-left" /> Dashboard
        </button>
        <span style={{ fontSize: 13, fontWeight: 700, color: "var(--cc-text-primary)" }}>
          Live GIS Map — Khairatabad Venue
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: 8 }}>
          <span className="cc-live-dot" />
          <span style={{ fontSize: 10, color: "var(--cc-green)" }}>LIVE</span>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button className="cc-btn" onClick={() => setShowLayerPanel((p) => !p)}>
            <i className="bi bi-layers" /> Layers
          </button>
        </div>
      </div>

      {/* Map + overlays */}
      <div style={{ position: "relative", flex: 1 }}>
        <MapView layers={layers} onZoneClick={(z) => navigate(`/zones/${z.id}`)} />

        {/* Layer control panel */}
        {showLayerPanel && (
          <div
            style={{
              position: "absolute", top: 10, right: 10, zIndex: 100,
              background: "rgba(10,13,16,0.95)", border: "1px solid var(--cc-border)",
              borderRadius: "var(--cc-radius-md)", padding: "12px 14px", minWidth: 200,
            }}
          >
            <div className="cc-section-title" style={{ marginBottom: 10 }}>Map Layers</div>
            {LAYER_OPTIONS.map((opt) => (
              <label key={opt.key} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, cursor: "pointer", fontSize: 12 }}>
                <input
                  type="checkbox"
                  checked={layers[opt.key] ?? opt.default}
                  onChange={() => toggleLayer(opt.key)}
                  style={{ accentColor: "var(--cc-accent)" }}
                />
                <span style={{ color: "var(--cc-text-secondary)" }}>{opt.label}</span>
              </label>
            ))}
          </div>
        )}

        {/* Zone summary strip */}
        <div
          style={{
            position: "absolute", bottom: 40, left: "50%", transform: "translateX(-50%)",
            display: "flex", gap: 8, background: "rgba(10,13,16,0.9)", border: "1px solid var(--cc-border)",
            borderRadius: "var(--cc-radius)", padding: "8px 14px", fontSize: 11, whiteSpace: "nowrap",
            zIndex: 100,
          }}
        >
          {[
            { label: "Zone B", value: "CRITICAL", color: "var(--cc-red)" },
            { label: "Zone H", value: "HIGH", color: "var(--cc-orange)" },
            { label: "Zone A", value: "MEDIUM", color: "var(--cc-yellow)" },
            { label: "Zone C", value: "LOW", color: "var(--cc-green)" },
          ].map((z) => (
            <div key={z.label} style={{ display: "flex", gap: 5, alignItems: "center" }}>
              <span style={{ color: "var(--cc-text-muted)" }}>{z.label}:</span>
              <span style={{ fontWeight: 700, color: z.color }}>{z.value}</span>
              <span style={{ color: "var(--cc-border)", marginLeft: 4 }}>|</span>
            </div>
          ))}
          <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
            <span className="cc-live-dot" style={{ width: 6, height: 6 }} />
            <span style={{ color: "var(--cc-green)", fontWeight: 600 }}>97 cams online</span>
          </div>
        </div>
      </div>
    </div>
  );
}
