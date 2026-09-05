// MapView — MapLibre GL JS based GIS map with zones, cameras, gates and theme responsiveness
import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { ZONES, GATES } from "../../data/zones.js";
import { CAMERAS } from "../../data/cameras.js";
import { useAppStore } from "../../store/useAppStore.js";

const RISK_COLORS = {
  low: "#3fb950",
  medium: "#e3b341",
  high: "#f0883e",
  critical: "#f85149",
};

function buildZoneGeoJSON() {
  return {
    type: "FeatureCollection",
    features: ZONES.map((z) => ({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [z.coordinates] },
      properties: {
        id: z.id, name: z.name, people: z.people, capacity: z.capacity,
        risk: z.risk, densityLabel: z.densityLabel, inflow: z.inflow, outflow: z.outflow,
        color: RISK_COLORS[z.risk] || "#58a6ff",
        label: z.label,
      },
    })),
  };
}

function buildCameraGeoJSON(cameras) {
  return {
    type: "FeatureCollection",
    features: cameras.map((c) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: c.coordinates },
      properties: {
        id: c.id, label: c.label, status: c.status,
        isFRS: c.isFRS, zone: c.zone, peopleCount: c.peopleCount,
      },
    })),
  };
}

function buildGateGeoJSON() {
  return {
    type: "FeatureCollection",
    features: GATES.map((g) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: g.coordinates },
      properties: { id: g.id, name: g.name, label: g.label, status: g.status, flowRate: g.flowRate },
    })),
  };
}

export default function MapView({ layers = { zones: true, cameras: true, gates: true, heatmap: true }, onZoneClick }) {
  const mapContainer = useRef(null);
  const map = useRef(null);
  const [mapReady, setMapReady] = useState(false);
  const theme = useAppStore((s) => s.theme);

  const tileUrl = theme === "light"
    ? "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png"
    : "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png";
  const tileUrlB = theme === "light"
    ? "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png"
    : "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png";

  useEffect(() => {
    if (!mapContainer.current) return;

    if (map.current) {
      map.current.remove();
      map.current = null;
      setMapReady(false);
    }

    const isLight = theme === "light";

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {
          "carto-base": {
            type: "raster",
            tiles: [tileUrl, tileUrlB],
            tileSize: 256,
            attribution: "© CartoDB © OpenStreetMap contributors",
          },
        },
        layers: [{ id: "carto-base-layer", type: "raster", source: "carto-base" }],
      },
      center: [78.4740, 17.4240],
      zoom: 14.5,
      bearing: 0,
      pitch: 0,
    });

    map.current.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.current.addControl(new maplibregl.ScaleControl(), "bottom-right");

    map.current.on("load", () => {
      const m = map.current;
      if (!m) return;

      // Zone fills
      m.addSource("zones", { type: "geojson", data: buildZoneGeoJSON() });
      m.addLayer({
        id: "zone-fill",
        type: "fill",
        source: "zones",
        paint: {
          "fill-color": ["get", "color"],
          "fill-opacity": isLight ? 0.25 : 0.2,
        },
      });
      m.addLayer({
        id: "zone-border",
        type: "line",
        source: "zones",
        paint: {
          "line-color": ["get", "color"],
          "line-width": 2,
          "line-opacity": 0.85,
        },
      });

      // Zone labels
      m.addLayer({
        id: "zone-labels",
        type: "symbol",
        source: "zones",
        layout: {
          "text-field": ["concat", ["get", "name"], "\n", ["to-string", ["get", "people"]]],
          "text-font": ["Open Sans Regular"],
          "text-size": 11,
          "text-anchor": "center",
        },
        paint: {
          "text-color": isLight ? "#0f172a" : "#e6edf3",
          "text-halo-color": isLight ? "#ffffff" : "#000000",
          "text-halo-width": 1.5,
        },
      });

      // Cameras
      m.addSource("cameras", { type: "geojson", data: buildCameraGeoJSON(CAMERAS.slice(0, 50)) });
      m.addLayer({
        id: "camera-points",
        type: "circle",
        source: "cameras",
        paint: {
          "circle-radius": 4.5,
          "circle-color": [
            "match", ["get", "status"],
            "online", "#16a34a",
            "offline", "#dc2626",
            "degraded", "#ca8a04",
            "#0284c7",
          ],
          "circle-stroke-color": isLight ? "#ffffff" : "#000000",
          "circle-stroke-width": 1,
          "circle-opacity": 0.9,
        },
      });

      // Gates
      m.addSource("gates", { type: "geojson", data: buildGateGeoJSON() });
      m.addLayer({
        id: "gate-points",
        type: "circle",
        source: "gates",
        paint: {
          "circle-radius": 7,
          "circle-color": [
            "match", ["get", "status"],
            "open", "#0284c7",
            "restricted", "#ea580c",
            "closed", "#dc2626",
            "#64748b",
          ],
          "circle-stroke-color": isLight ? "#ffffff" : "#e6edf3",
          "circle-stroke-width": 2,
        },
      });

      // Zone click handler
      m.on("click", "zone-fill", (e) => {
        const props = e.features[0].properties;
        const people = props.people ?? props.current_people ?? 0;
        const capacity = props.capacity || 1;
        const occupancyPct = ((people / capacity) * 100).toFixed(1);
        const risk = (props.risk || props.risk_level || "low").toLowerCase();
        const popupHtml = `
          <div style="padding:12px;min-width:200px;font-family:system-ui;font-size:12px">
            <div style="font-weight:700;font-size:14px;color:${isLight ? "#0f172a" : "#e6edf3"};margin-bottom:4px">${props.name || props.zone_code}</div>
            <div style="color:${isLight ? "#64748b" : "#8b949e"};font-size:10px;margin-bottom:10px">${props.label || props.name}</div>
            <table style="width:100%;border-collapse:collapse">
              ${[
                ["Population", people.toLocaleString()],
                ["Capacity", (props.capacity || 0).toLocaleString()],
                ["Occupancy", `${occupancyPct}%`],
                ["Density", props.density_label || props.densityLabel || "LOW"],
                ["Inflow", `${props.inflow || 0}/min`],
                ["Outflow", `${props.outflow || 0}/min`],
              ].map(([k, v]) => `<tr><td style="padding:3px 0;color:${isLight ? "#64748b" : "#8b949e"}">${k}</td><td style="padding:3px 0;color:${isLight ? "#0f172a" : "#e6edf3"};font-weight:600;text-align:right">${v}</td></tr>`).join("")}
            </table>
            <div style="margin-top:10px;padding:4px 8px;border-radius:3px;background:${risk === "critical" ? "rgba(220,38,38,0.15)" : risk === "high" ? "rgba(234,88,12,0.15)" : "rgba(22,163,74,0.15)"};color:${RISK_COLORS[risk] || "#0284c7"};font-weight:700;font-size:10px;letter-spacing:0.06em">
              RISK: ${risk.toUpperCase()}
            </div>
          </div>
        `;
        new maplibregl.Popup({ closeButton: true, maxWidth: "280px" })
          .setLngLat(e.lngLat)
          .setHTML(popupHtml)
          .addTo(m);
        if (onZoneClick) onZoneClick(props);
      });

      m.on("mouseenter", "zone-fill", () => { m.getCanvas().style.cursor = "pointer"; });
      m.on("mouseleave", "zone-fill", () => { m.getCanvas().style.cursor = ""; });
      m.on("mouseenter", "camera-points", () => { m.getCanvas().style.cursor = "pointer"; });
      m.on("mouseleave", "camera-points", () => { m.getCanvas().style.cursor = ""; });

      setMapReady(true);
    });

    return () => {
      map.current?.remove();
      map.current = null;
    };
  }, [theme]);

  // Toggle layers
  useEffect(() => {
    if (!mapReady || !map.current) return;
    const m = map.current;
    const toggle = (layerId, visible) => {
      if (m.getLayer(layerId)) {
        m.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
      }
    };
    toggle("zone-fill", layers.zones ?? true);
    toggle("zone-border", layers.zones ?? true);
    toggle("zone-labels", layers.zones ?? true);
    toggle("camera-points", layers.cameras ?? true);
    toggle("gate-points", layers.gates ?? true);
  }, [layers, mapReady]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <div ref={mapContainer} style={{ width: "100%", height: "100%" }} />
      {/* Legend */}
      <div
        style={{
          position: "absolute", bottom: 36, left: 10,
          background: "var(--cc-bg-panel)", border: "1px solid var(--cc-border)",
          boxShadow: "var(--cc-shadow)",
          borderRadius: "var(--cc-radius)", padding: "8px 12px", fontSize: 10,
        }}
      >
        {[
          { color: "#16a34a", label: "Low Risk" },
          { color: "#ca8a04", label: "Medium" },
          { color: "#ea580c", label: "High" },
          { color: "#dc2626", label: "Critical" },
        ].map((item) => (
          <div key={item.label} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
            <div style={{ width: 10, height: 10, borderRadius: 2, background: item.color }} />
            <span style={{ color: "var(--cc-text-secondary)" }}>{item.label}</span>
          </div>
        ))}
        <div style={{ borderTop: "1px solid var(--cc-border)", marginTop: 4, paddingTop: 4, display: "flex", gap: 8 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 4, color: "var(--cc-text-muted)" }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#16a34a", display: "inline-block" }} /> Camera
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 4, color: "var(--cc-text-muted)" }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#0284c7", display: "inline-block" }} /> Gate
          </span>
        </div>
      </div>
    </div>
  );
}
