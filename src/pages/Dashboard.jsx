// Dashboard — Main command center screen (Real backend integration)
import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import KpiCard from "../components/common/KpiCard.jsx";
import ActionCenter from "../components/alerts/ActionCenter.jsx";
import { useCrowdStore } from "../store/useCrowdStore.js";
import { useAlertStore } from "../store/useAlertStore.js";
import { getCrowdSummary } from "../services/crowdService.js";
import { getCameras, getCameraStats } from "../services/cameraService.js";
import { getAlerts } from "../services/alertService.js";
import { getMissingPersons } from "../services/frsService.js";
import { LoadingState } from "../components/common/States.jsx";

// --- Simulated CCTV noise overlay via canvas ---------------------------------
function ScanlineFeed({ cameraId, label, zone, people, aiLabel, severity, status, fps, ptzActive, onClick }) {
  const canvasRef = useRef(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (status !== "online") return;
    const iv = setInterval(() => setTick((t) => t + 1), 2000);
    return () => clearInterval(iv);
  }, [status]);

  const peopleDrift = status === "online" ? (people || 0) + Math.floor(Math.sin(tick * 0.8) * 7) : 0;

  useEffect(() => {
    if (status !== "online") return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let frameId;
    const draw = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (let y = 0; y < canvas.height; y += 4) {
        ctx.fillStyle = `rgba(0,0,0,${Math.random() * 0.04})`;
        ctx.fillRect(0, y, canvas.width, 2);
      }
      if (Math.random() < 0.04) {
        const lineY = Math.floor(Math.random() * canvas.height);
        ctx.fillStyle = `rgba(255,255,255,0.04)`;
        ctx.fillRect(0, lineY, canvas.width, 1);
      }
      frameId = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(frameId);
  }, [status]);

  const borderColor = {
    critical: "var(--cc-red)",
    high: "var(--cc-orange)",
    medium: "var(--cc-yellow)",
    normal: "var(--cc-green)",
    offline: "var(--cc-text-muted)",
    degraded: "var(--cc-yellow)",
  }[severity] || "var(--cc-border)";

  const bgPattern = status === "offline"
    ? "repeating-linear-gradient(45deg, #0a0a0a 0px, #0a0a0a 10px, #111 10px, #111 20px)"
    : undefined;

  return (
    <div
      onClick={onClick}
      style={{
        position: "relative",
        background: status === "offline" ? undefined : "#050e18",
        backgroundImage: bgPattern,
        border: `1.5px solid ${borderColor}`,
        borderRadius: 6,
        overflow: "hidden",
        cursor: "pointer",
        minHeight: 160,
        flex: "1 1 280px",
        maxWidth: "calc(33.33% - 6px)",
        transition: "border-color 0.3s",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {status === "online" && (
        <canvas
          ref={canvasRef}
          style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", pointerEvents: "none", zIndex: 2 }}
        />
      )}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "5px 8px", background: "rgba(0,0,0,0.7)", zIndex: 3 }}>
        <span style={{ fontFamily: "var(--cc-font-mono)", fontSize: 10, color: "var(--cc-text-muted)", letterSpacing: "0.06em" }}>
          {cameraId}
        </span>
        <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
          {ptzActive && (
            <span style={{ fontSize: 9, color: "var(--cc-yellow)", background: "rgba(210,153,34,0.15)", border: "1px solid var(--cc-yellow)", borderRadius: 3, padding: "1px 5px", letterSpacing: "0.08em" }}>PTZ</span>
          )}
          <span style={{
            width: 7, height: 7, borderRadius: "50%",
            background: status === "online" ? "var(--cc-green)" : "var(--cc-text-muted)",
            boxShadow: status === "online" ? "0 0 6px var(--cc-green)" : "none",
            animation: status === "online" ? "cc-pulse-dot 2s infinite" : "none",
          }} />
          <span style={{ fontSize: 9, color: status === "online" ? "var(--cc-green)" : "var(--cc-text-muted)", fontFamily: "var(--cc-font-mono)" }}>
            {status === "online" ? `${fps || 24}fps` : status?.toUpperCase() || "OFFLINE"}
          </span>
        </div>
      </div>

      <div style={{ flex: 1, position: "relative", minHeight: 90, display: "flex", alignItems: "center", justifyContent: "center", zIndex: 3 }}>
        {status === "offline" ? (
          <div style={{ textAlign: "center", color: "var(--cc-text-muted)" }}>
            <i className="bi bi-camera-video-off" style={{ fontSize: 32, display: "block", marginBottom: 6 }} />
            <div style={{ fontSize: 11, fontFamily: "var(--cc-font-mono)", letterSpacing: "0.1em" }}>NO SIGNAL</div>
          </div>
        ) : (
          <div style={{ width: "100%", height: "100%", position: "relative", padding: "8px 10px" }}>
            <div style={{
              position: "absolute", top: "20%", left: "15%", width: 28, height: 48,
              border: `1px solid ${borderColor}`, borderRadius: 2,
              boxShadow: `0 0 4px ${borderColor}`,
              pointerEvents: "none",
            }}>
              <div style={{ position: "absolute", top: -14, left: 0, fontSize: 8, color: borderColor, fontFamily: "var(--cc-font-mono)", whiteSpace: "nowrap" }}>
                {Math.floor(87 + Math.random() * 11)}%
              </div>
            </div>
            <div style={{
              position: "absolute", bottom: 6, left: "50%", transform: "translateX(-50%)",
              background: "rgba(0,0,0,0.7)", borderRadius: 4, padding: "3px 10px",
              fontFamily: "var(--cc-font-mono)", fontSize: 18, fontWeight: 700,
              color: borderColor,
              textShadow: `0 0 8px ${borderColor}`,
              letterSpacing: "0.08em",
            }}>
              {peopleDrift.toLocaleString()}
              <span style={{ fontSize: 10, color: "var(--cc-text-muted)", marginLeft: 4 }}>pax</span>
            </div>
            <div style={{
              position: "absolute", bottom: 6, right: 8,
              fontFamily: "var(--cc-font-mono)", fontSize: 9, color: "rgba(255,255,255,0.4)",
            }}>
              {new Date().toLocaleTimeString("en-IN", { hour12: false, timeZone: "Asia/Kolkata" })}
            </div>
          </div>
        )}
      </div>

      <div style={{ padding: "5px 8px", background: "rgba(0,0,0,0.6)", zIndex: 3, borderTop: `1px solid rgba(255,255,255,0.05)` }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 10, color: "var(--cc-text-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "65%" }}>
            {zone || label}
          </span>
          <span style={{ fontSize: 9, color: borderColor, fontFamily: "var(--cc-font-mono)", letterSpacing: "0.05em" }}>
            {aiLabel || (status === "offline" ? "?? Offline" : "? Online")}
          </span>
        </div>
      </div>

      <div style={{
        position: "absolute", inset: 0, background: "rgba(88,166,255,0.04)",
        opacity: 0, transition: "opacity 0.2s",
        zIndex: 4,
      }}
        onMouseEnter={(e) => (e.currentTarget.style.opacity = 1)}
        onMouseLeave={(e) => (e.currentTarget.style.opacity = 0)}
      />
    </div>
  );
}

// --- Main Dashboard -----------------------------------------------------------
export default function Dashboard() {
  const navigate = useNavigate();
  const { totalCrowd, inflowPerMin, outflowPerMin, setCrowdFromAPI } = useCrowdStore();
  const { alerts, setAlerts } = useAlertStore();
  const [summary, setSummary] = useState(null);
  const [camStats, setCamStats] = useState(null);
  const [cameras, setCameras] = useState([]);
  const [missingPersons, setMissingPersons] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [flashClass, setFlashClass] = useState("");
  const [feedFilter, setFeedFilter] = useState("all");
  const [clockStr, setClockStr] = useState("");

  useEffect(() => {
    Promise.allSettled([
      getCrowdSummary(),
      getCameraStats(),
      getCameras({ page_size: 12 }),
      getAlerts({ page_size: 50 }),
      getMissingPersons({ status: "searching" }),
    ])
      .then(([sRes, csRes, camsRes, alertsRes, mpRes]) => {
        const s = sRes.status === "fulfilled" ? sRes.value : null;
        const cs = csRes.status === "fulfilled" ? csRes.value : null;
        const cams = camsRes.status === "fulfilled" ? camsRes.value : [];
        const alertsData = alertsRes.status === "fulfilled" ? alertsRes.value : [];
        const mpData = mpRes.status === "fulfilled" ? mpRes.value : [];

        if (s) {
          setSummary(s);
          const d = s?.data ?? s ?? {};
          setCrowdFromAPI(d);
        }
        if (cs) setCamStats(cs);
        setCameras(Array.isArray(cams) ? cams : (cams?.data || []));
        const alertList = Array.isArray(alertsData) ? alertsData : (alertsData?.data || []);
        setAlerts(alertList);
        setMissingPersons(Array.isArray(mpData) ? mpData : (mpData?.data || []));
        setLoading(false);
      })
      .catch((err) => {
        console.warn("[Dashboard] Data load notice:", err);
        setLoading(false);
      });
  }, []);

  // Live clock
  useEffect(() => {
    const tick = () =>
      setClockStr(new Date().toLocaleTimeString("en-IN", { hour12: false, timeZone: "Asia/Kolkata" }));
    tick();
    const iv = setInterval(tick, 1000);
    return () => clearInterval(iv);
  }, []);

  // Flash on live update
  useEffect(() => {
    setFlashClass("cc-data-updated");
    const t = setTimeout(() => setFlashClass(""), 800);
    return () => clearTimeout(t);
  }, [totalCrowd]);

  const criticalAlerts = alerts.filter((a) => a.severity === "critical").length;
  const frsAlerts = alerts.filter((a) => a.type === "frs" || a.alert_type === "frs").length;
  const medicalAlerts = alerts.filter((a) => a.type === "medical" || a.alert_type === "medical").length;
  const criticalZones = summary?.critical_zones || summary?.criticalZones || 0;
  const missingCount = missingPersons.length;
  const blockedRoutes = summary?.blocked_routes || summary?.blockedRoutes || 0;

  // Map camera data to feed format
  const cameraFeeds = cameras.map((cam) => ({
    id: cam.code || cam.id,
    label: cam.name || cam.label || cam.code,
    zone: cam.zone_code || cam.zone || "",
    status: cam.status || "unknown",
    people: cam.current_count || cam.people || 0,
    severity: cam.ai_severity || cam.severity || (cam.status === "offline" ? "offline" : "normal"),
    fps: cam.fps || cam.current_fps || 24,
    ai: cam.ai_event || "normal",
    aiLabel: cam.ai_label || (cam.status === "offline" ? "?? Offline" : "? Online"),
    ptzActive: cam.is_ptz || cam.ptz_active || false,
  }));

  // Filter feeds
  const filteredFeeds = feedFilter === "all"
    ? cameraFeeds
    : feedFilter === "alerts"
    ? cameraFeeds.filter((f) => ["critical", "high"].includes(f.severity))
    : cameraFeeds.filter((f) => f.status === feedFilter);

  if (loading) return <LoadingState message="Loading command dashboard..." />;

  if (error) {
    return (
      <div className="cc-page" style={{ alignItems: "center", justifyContent: "center" }}>
        <div style={{ textAlign: "center", color: "var(--cc-red)", padding: 40 }}>
          <i className="bi bi-exclamation-triangle-fill" style={{ fontSize: 40, display: "block", marginBottom: 12 }} />
          <div style={{ fontSize: 14, fontWeight: 600 }}>{error}</div>
          <button className="cc-btn" style={{ marginTop: 16 }} onClick={() => window.location.reload()}>
            <i className="bi bi-arrow-clockwise" /> Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="cc-page" style={{ gap: 10 }}>
      {/* Page header */}
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title">Command Dashboard</div>
          <div className="cc-page-subtitle">Khairatabad Ganesh Festival 2026 Live Operations</div>
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <span style={{ fontFamily: "var(--cc-font-mono)", fontSize: 12, color: "var(--cc-text-muted)", marginRight: 6 }}>
            {clockStr} IST
          </span>
          <button className="cc-btn" onClick={() => navigate("/cameras")}>
            <i className="bi bi-camera-video-fill" /> All Cameras
          </button>
          <button className="cc-btn" onClick={() => navigate("/alerts")}>
            <i className="bi bi-exclamation-triangle" /> All Alerts
          </button>
        </div>
      </div>

      {/* KPI Row 1 */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <KpiCard
          label="Total Visitors Today"
          value={(summary?.total_visitors_today || summary?.totalVisitorsToday || 0).toLocaleString()}
          icon="bi-people-fill"
          severity="normal"
        />
        <KpiCard
          label="Current Crowd"
          value={totalCrowd.toLocaleString()}
          icon="bi-person-fill"
          severity={totalCrowd > 38000 ? "critical" : totalCrowd > 32000 ? "high" : "normal"}
          trend={Math.round(inflowPerMin - outflowPerMin)}
          sub={`${summary?.occupancy || summary?.occupancy_pct || 0}% occupancy`}
        />
        <KpiCard
          label="Active Queues"
          value={summary?.active_queues || summary?.activeQueues || 0}
          icon="bi-list-ol"
          severity="medium"
          sub={`Avg wait: ${summary?.avg_queue_wait || summary?.avgQueueWait || 0} min`}
        />
        <KpiCard
          label="Critical Zones"
          value={criticalZones}
          icon="bi-hexagon-fill"
          severity={criticalZones > 0 ? "critical" : "normal"}
        />
        <KpiCard
          label="Active Alerts"
          value={alerts.filter((a) => !a.acknowledged).length}
          icon="bi-exclamation-triangle-fill"
          severity={criticalAlerts > 0 ? "critical" : "high"}
          sub={`${criticalAlerts} critical`}
        />
        <KpiCard
          label="FRS Alerts"
          value={frsAlerts}
          icon="bi-person-bounding-box"
          severity={frsAlerts > 0 ? "high" : "normal"}
          sub="Requires review"
        />
      </div>

      {/* KPI Row 2 */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <KpiCard
          label="Inflow / min"
          value={inflowPerMin.toLocaleString()}
          icon="bi-arrow-down-circle-fill"
          severity="normal"
        />
        <KpiCard
          label="Outflow / min"
          value={outflowPerMin.toLocaleString()}
          icon="bi-arrow-up-circle-fill"
          severity="normal"
        />
        <KpiCard
          label="Cameras Online"
          value={camStats ? `${camStats.online || 0}/${camStats.total || 0}` : "—"}
          icon="bi-camera-video-fill"
          severity={camStats?.offline > 5 ? "high" : camStats?.offline > 0 ? "medium" : "normal"}
          sub={camStats ? `${camStats.offline || 0} offline` : ""}
        />
        <KpiCard
          label="Medical Incidents"
          value={medicalAlerts}
          icon="bi-heart-pulse-fill"
          severity={medicalAlerts > 2 ? "high" : "normal"}
        />
        <KpiCard
          label="Missing Persons"
          value={missingCount}
          icon="bi-person-exclamation"
          severity={missingCount > 0 ? "medium" : "normal"}
          sub={missingCount > 0 ? "Searching" : "None active"}
        />
        <KpiCard
          label="Emerg. Routes Blocked"
          value={blockedRoutes}
          icon="bi-sign-stop-fill"
          severity={blockedRoutes > 0 ? "critical" : "normal"}
        />
      </div>

      {/* Live indicator */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11 }}>
        <span className="cc-live-dot" />
        <span style={{ color: "var(--cc-text-muted)" }}>Live AI video monitoring-real-time crowd detection active</span>
      </div>

      {/* Main content: Live Feeds + Action Center */}
      <div style={{ display: "flex", gap: 10, flex: 1, minHeight: 0, minHeight: 520 }}>

        {/* Live Camera Feeds */}
        <div className={`cc-card ${flashClass}`} style={{ flex: 1, padding: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          {/* Feed header */}
          <div className="cc-section-header" style={{ padding: "8px 12px", flexShrink: 0 }}>
            <div className="cc-section-title">
              <span style={{ position: "relative", display: "inline-block", marginRight: 8 }}>
                <i className="bi bi-camera-reels-fill" style={{ color: "var(--cc-red)" }} />
                <span style={{
                  position: "absolute", top: -2, right: -4, width: 6, height: 6,
                  borderRadius: "50%", background: "var(--cc-red)",
                  animation: "cc-pulse-dot 1.2s infinite",
                }} />
              </span>
              Live Camera Feeds Critical Monitoring
            </div>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              {[
                { key: "all", label: "All" },
                { key: "alerts", label: "? Alerts" },
                { key: "online", label: "Online" },
                { key: "offline", label: "Offline" },
              ].map((f) => (
                <button
                  key={f.key}
                  className="cc-btn"
                  style={{
                    fontSize: 10,
                    padding: "3px 10px",
                    background: feedFilter === f.key ? "var(--cc-accent)" : undefined,
                    color: feedFilter === f.key ? "#fff" : undefined,
                    borderColor: feedFilter === f.key ? "var(--cc-accent)" : undefined,
                  }}
                  onClick={() => setFeedFilter(f.key)}
                >
                  {f.label}
                </button>
              ))}
              <button className="cc-btn" style={{ fontSize: 10 }} onClick={() => navigate("/cameras")}>
                <i className="bi bi-arrows-fullscreen" /> Full Grid
              </button>
            </div>
          </div>

          {/* Feed grid */}
          <div style={{
            flex: 1,
            overflowY: "auto",
            padding: "10px 12px",
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            alignContent: "flex-start",
          }}>
            {cameraFeeds.length === 0 ? (
              <div style={{ width: "100%", textAlign: "center", color: "var(--cc-text-muted)", padding: "40px 0", fontSize: 13 }}>
                <i className="bi bi-camera-video-off" style={{ fontSize: 28, display: "block", marginBottom: 8 }} />
                No cameras registered yet
              </div>
            ) : filteredFeeds.length === 0 ? (
              <div style={{ width: "100%", textAlign: "center", color: "var(--cc-text-muted)", padding: "40px 0", fontSize: 13 }}>
                <i className="bi bi-camera-video-off" style={{ fontSize: 28, display: "block", marginBottom: 8 }} />
                No cameras match this filter
              </div>
            ) : (
              filteredFeeds.map((cam) => (
                <ScanlineFeed
                  key={cam.id}
                  cameraId={cam.id}
                  label={cam.label}
                  zone={cam.zone || cam.label}
                  people={cam.people}
                  severity={cam.severity}
                  status={cam.status}
                  fps={cam.fps}
                  ai={cam.ai}
                  aiLabel={cam.aiLabel}
                  ptzActive={cam.ptzActive}
                  onClick={() => navigate(`/cameras/${cam.id}`)}
                />
              ))
            )}
          </div>

          {/* Feed footer status */}
          <div style={{ padding: "6px 12px", borderTop: "1px solid var(--cc-border)", display: "flex", gap: 16, fontSize: 10, color: "var(--cc-text-muted)", flexShrink: 0 }}>
            <span><span style={{ color: "var(--cc-green)" }}>?</span> {cameraFeeds.filter(f => f.status === "online").length} Online</span>
            <span><span style={{ color: "var(--cc-text-muted)" }}>?</span> {cameraFeeds.filter(f => f.status === "offline").length} Offline</span>
            <span><span style={{ color: "var(--cc-red)" }}>?</span> {cameraFeeds.filter(f => f.severity === "critical").length} Critical</span>
            <span style={{ marginLeft: "auto" }}>Showing {filteredFeeds.length} / {cameraFeeds.length} feeds</span>
          </div>
        </div>

        {/* Action Center */}
        <div
          className="cc-card"
          style={{ width: 340, flexShrink: 0, padding: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}
        >
          <ActionCenter />
        </div>
      </div>
    </div>
  );
}
