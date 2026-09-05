// Zones page — zone management
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import ZoneCard from "../components/zone/ZoneCard.jsx";
import { getZones } from "../services/zoneService.js";
import { LoadingState } from "../components/common/States.jsx";

export default function Zones() {
  const navigate = useNavigate();
  const [zones, setZones] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    getZones().then((z) => { setZones(z); setLoading(false); });
  }, []);

  const filtered = filter === "all" ? zones : zones.filter((z) => (z.risk || z.risk_level || "low").toLowerCase() === filter);

  if (loading) return <LoadingState />;

  return (
    <div className="cc-page">
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title">Zone Management</div>
          <div className="cc-page-subtitle">{zones.length} zones Click a zone for details</div>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {["all", "critical", "high", "medium", "low"].map((f) => (
            <button key={f} className={`cc-btn${filter === f ? " cc-btn-primary" : ""}`} style={{ fontSize: 11, padding: "4px 10px", textTransform: "capitalize" }} onClick={() => setFilter(f)}>
              {f === "all" ? "All" : f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Summary row */}
      <div style={{ display: "flex", gap: 12, padding: "8px 14px", background: "var(--cc-bg-secondary)", border: "1px solid var(--cc-border)", borderRadius: "var(--cc-radius)", fontSize: 12 }}>
        {["critical", "high", "medium", "low"].map((r) => {
          const count = zones.filter((z) => (z.risk || z.risk_level || "low").toLowerCase() === r).length;
          const colors = { critical: "var(--cc-red)", high: "var(--cc-orange)", medium: "var(--cc-yellow)", low: "var(--cc-green)" };
          return (
            <span key={r} style={{ color: "var(--cc-text-muted)" }}>
              {r.charAt(0).toUpperCase() + r.slice(1)}: <strong style={{ color: colors[r] }}>{count}</strong>
            </span>
          );
        })}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10 }}>
        {filtered.map((z) => (
          <ZoneCard key={z.id} zone={z} onClick={() => navigate(`/zones/${z.id}`)} />
        ))}
      </div>
    </div>
  );
}
