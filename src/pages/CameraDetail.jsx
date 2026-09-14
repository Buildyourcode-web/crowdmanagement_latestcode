// CameraDetail — Simplified: live feed + live counts + single ROI button
import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import StatusBadge from "../components/common/StatusBadge.jsx";
import { getCameraById, updateCamera, getZones, deleteCamera } from "../services/cameraService.js";
import { getCameraROIConfig } from "../services/aiService.js";
import ROIEditor from "../components/ai/ROIEditor.jsx";
import { LoadingState, ErrorState } from "../components/common/States.jsx";
import { getBackendUrl } from "../utils/urlConfig.js";

const BACKEND = getBackendUrl();

// Purpose meta: colors + labels + icons + ROI tool mapping
const PURPOSE_META = {
  ENTRY:      { label: "Entry Gate",  color: "#3fb950", icon: "bi-box-arrow-in-right", bg: "rgba(63,185,80,0.12)",  border: "rgba(63,185,80,0.3)",  roiTool: "ENTRY_LINE",   roiLabel: "Configure Entry Gate & Queue Corridor" },
  EXIT:       { label: "Exit Gate",   color: "#f85149", icon: "bi-box-arrow-right",    bg: "rgba(248,81,73,0.12)", border: "rgba(248,81,73,0.3)", roiTool: "EXIT_LINE",    roiLabel: "Configure Exit Gate & Queue Corridor" },
  ZONE:       { label: "Zone Density",          color: "#58a6ff", icon: "bi-bounding-box",       bg: "rgba(88,166,255,0.12)", border: "rgba(88,166,255,0.3)", roiTool: "CROWD_ROI", roiLabel: "Configure Zone Area" },
  FRS:        { label: "Face Recognition",      color: "#58a6ff", icon: "bi-person-bounding-box", bg: "rgba(88,166,255,0.12)", border: "rgba(88,166,255,0.3)", roiTool: null, roiLabel: null },
};

function getAllPurposes(camera, liveData) {
  const list = liveData?.ai_purposes || camera?.ai_purposes;
  if (Array.isArray(list) && list.length > 0) {
    return list.map((p) => String(p).toUpperCase());
  }
  const t = camera?.camera_type?.toUpperCase() || "";
  if (t === "FRS") return ["FRS"];
  if (t === "QUEUE") return ["QUEUE"];
  if (t === "ZONE") return ["ZONE"];
  if (t === "EXIT") return ["EXIT"];
  return ["ENTRY"];
}

function PurposeBadge({ camera, liveData }) {
  const purposes = getAllPurposes(camera, liveData);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {purposes.map((key) => {
        const m = PURPOSE_META[key] || PURPOSE_META.ENTRY;
        return (
          <span
            key={key}
            style={{
              padding: "4px 10px",
              borderRadius: 4,
              fontSize: 11,
              fontWeight: 700,
              background: m.bg,
              color: m.color,
              border: `1px solid ${m.border}`,
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <i className={`bi ${m.icon}`} /> {m.label}
          </span>
        );
      })}
    </div>
  );
}

function LiveCountsBar({ liveData, camera }) {
  const purposes = getAllPurposes(camera, liveData);
  if (purposes.includes("FRS") && purposes.length === 1) return null;

  const inCount   = liveData?.in_count ?? 0;
  const outCount  = liveData?.out_count ?? 0;
  const occupancy = liveData?.occupancy_count ?? Math.max(0, inCount - outCount);

  const hasLineCounting = purposes.some((p) => ["ENTRY", "EXIT", "ENTRY_EXIT"].includes(p));
  const hasZone = purposes.includes("ZONE");
  const hasQueue = purposes.includes("QUEUE");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {/* 1. Footfall Line Crossing Counts */}
      {hasLineCounting && (
        <div style={{ display: "flex", gap: 12, padding: "8px 14px", background: "rgba(0,0,0,0.4)",
          borderRadius: 6, border: "1px solid rgba(63,185,80,0.3)", flexWrap: "wrap", alignItems: "center" }}>
          {purposes.includes("ENTRY") && !purposes.includes("EXIT") ? (
            <div style={{ textAlign: "center", minWidth: 90 }}>
              <div style={{ fontSize: 9, color: "#3fb950", fontWeight: 700, textTransform: "uppercase" }}>TOTAL ENTERED (IN)</div>
              <div style={{ fontSize: 26, fontWeight: 800, fontFamily: "monospace", color: "#3fb950" }}>{inCount}</div>
            </div>
          ) : purposes.includes("EXIT") && !purposes.includes("ENTRY") ? (
            <div style={{ textAlign: "center", minWidth: 90 }}>
              <div style={{ fontSize: 9, color: "#f85149", fontWeight: 700, textTransform: "uppercase" }}>TOTAL EXITED (OUT)</div>
              <div style={{ fontSize: 26, fontWeight: 800, fontFamily: "monospace", color: "#f85149" }}>{outCount}</div>
            </div>
          ) : (
            <>
              <div style={{ textAlign: "center", minWidth: 60 }}>
                <div style={{ fontSize: 9, color: "#8b949e", textTransform: "uppercase" }}>IN (ENTERED)</div>
                <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "monospace", color: "#3fb950" }}>{inCount}</div>
              </div>
              <div style={{ width: 1, background: "rgba(255,255,255,0.1)" }} />
              <div style={{ textAlign: "center", minWidth: 60 }}>
                <div style={{ fontSize: 9, color: "#8b949e", textTransform: "uppercase" }}>OUT (EXITED)</div>
                <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "monospace", color: "#f85149" }}>{outCount}</div>
              </div>
              <div style={{ width: 1, background: "rgba(255,255,255,0.1)" }} />
              <div style={{ textAlign: "center", minWidth: 70 }}>
                <div style={{ fontSize: 9, color: "#8b949e", textTransform: "uppercase" }}>NET INSIDE</div>
                <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "monospace", color: "#58a6ff" }}>{occupancy}</div>
              </div>
            </>
          )}
        </div>
      )}

      {/* 2. Zone Density Counts */}
      {hasZone && (() => {
        const zoneData  = liveData?.zone_data?.[0] || {};
        const count     = zoneData.count ?? occupancy;
        const capacity  = zoneData.capacity ?? liveData?.zone_capacity ?? 50;
        const pct       = Math.min(100, Math.round((count / capacity) * 100));
        const isAlert   = pct >= 90;
        const isWarn    = pct >= 70;
        return (
          <div style={{ display: "flex", gap: 12, alignItems: "center", padding: "8px 14px",
            background: isAlert ? "rgba(248,81,73,0.12)" : "rgba(0,0,0,0.4)",
            borderRadius: 6,
            border: `1px solid ${isAlert ? "rgba(248,81,73,0.5)" : "rgba(188,140,255,0.3)"}`,
            flexWrap: "wrap" }}>
            {isAlert && (
              <div style={{ display: "flex", alignItems: "center", gap: 6, color: "#f85149", fontWeight: 700, fontSize: 12 }}>
                <i className="bi bi-exclamation-triangle-fill" /> ZONE CAPACITY SURGE
              </div>
            )}
            <div style={{ textAlign: "center", minWidth: 60 }}>
              <div style={{ fontSize: 9, color: "#8b949e", textTransform: "uppercase" }}>IN ZONE</div>
              <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "monospace",
                color: isAlert ? "#f85149" : isWarn ? "#d29922" : "#bc8cff" }}>{count}</div>
            </div>
            <div style={{ width: 1, height: 28, background: "rgba(255,255,255,0.1)" }} />
            <div style={{ textAlign: "center", minWidth: 60 }}>
              <div style={{ fontSize: 9, color: "#8b949e", textTransform: "uppercase" }}>CAPACITY</div>
              <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "monospace", color: "#8b949e" }}>{capacity}</div>
            </div>
            <div style={{ width: 1, height: 28, background: "rgba(255,255,255,0.1)" }} />
            <div style={{ textAlign: "center", minWidth: 60 }}>
              <div style={{ fontSize: 9, color: "#8b949e", textTransform: "uppercase" }}>DENSITY</div>
              <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "monospace",
                color: isAlert ? "#f85149" : isWarn ? "#d29922" : "#bc8cff" }}>{pct}%</div>
            </div>
          </div>
        );
      })()}

      {/* 3. Queue Movement Counts */}
      {hasQueue && (() => {
        const rawStatus = liveData?.queue_movement_status || "STOPPED";
        const status = rawStatus === "FAST" ? "MOVING" : rawStatus;
        const statusColor = {
          MOVING: "#3fb950",
          FAST: "#3fb950",
          SLOW: "#d29922",
          STOPPED: "#f85149",
          EMPTY: "#8b949e",
        }[status] || "#8b949e";
        return (
          <div style={{ display: "flex", gap: 16, alignItems: "center", padding: "8px 16px",
            background: "rgba(0,0,0,0.4)", borderRadius: 6, border: `1px solid ${statusColor}55`, flexWrap: "wrap" }}>
            <div style={{ textAlign: "center", minWidth: 60 }}>
              <div style={{ fontSize: 9, color: "#8b949e", textTransform: "uppercase" }}>IN QUEUE</div>
              <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "monospace", color: "#d29922" }}>{occupancy}</div>
            </div>
            <div style={{ width: 1, height: 28, background: "rgba(255,255,255,0.1)" }} />
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 9, color: "#8b949e", textTransform: "uppercase" }}>QUEUE STATUS</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: statusColor, marginTop: 3 }}>
                <i className={`bi ${status === "MOVING" ? "bi-arrow-right-circle-fill" : status === "SLOW" ? "bi-hourglass-split" : "bi-pause-circle-fill"}`} style={{ marginRight: 6 }} />
                {status}
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

function CameraFeed({ camera }) {
  const containerRef = useRef(null);
  const [streamError, setStreamError] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const [isTabVisible, setIsTabVisible] = useState(
    typeof document !== "undefined" ? document.visibilityState === "visible" : true
  );
  const [visibilityTick, setVisibilityTick] = useState(() => Date.now());

  useEffect(() => {
    const handleVis = () => {
      if (document.visibilityState === "visible") {
        setIsTabVisible(true);
        setVisibilityTick(Date.now());
        setStreamError(false);
      } else {
        setIsTabVisible(false);
      }
    };
    document.addEventListener("visibilitychange", handleVis);
    return () => document.removeEventListener("visibilitychange", handleVis);
  }, []);

  const camCode = camera?.camera_code || camera?.id;
  const baseSrc = camera?.stream_url
    ? (camera.stream_url.startsWith("http") ? camera.stream_url : `${BACKEND}${camera.stream_url}`)
    : (camCode ? `${BACKEND}/api/v1/frs-engine/cameras/${camCode}/stream` : "");
  const streamSrc = baseSrc ? `${baseSrc}${baseSrc.includes("?") ? "&" : "?"}t=${visibilityTick}` : "";

  if (camera?.status === "offline" || camera?.enabled === false) {
    return (
      <div style={{ aspectRatio: "16/9", background: "#050810", display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center", gap: 12, border: "1px solid rgba(248,81,73,0.4)" }}>
        <i className="bi bi-camera-video-off" style={{ fontSize: 36, color: "#f85149" }} />
        <div style={{ fontSize: 13, fontWeight: 700, color: "#f85149" }}>Camera Offline</div>
      </div>
    );
  }

  if (streamError) {
    return (
      <div style={{ aspectRatio: "16/9", background: "#050810", display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center", gap: 12 }}>
        <i className="bi bi-broadcast" style={{ fontSize: 32, color: "#58a6ff" }} />
        <div style={{ fontSize: 12, color: "#8b949e" }}>Stream unavailable — camera may be reconnecting</div>
        <button className="cc-btn cc-btn-primary" style={{ fontSize: 11 }}
          onClick={() => { setStreamError(false); setRetryCount(c => c + 1); setVisibilityTick(Date.now()); }}>
          <i className="bi bi-arrow-clockwise" /> Reconnect
        </button>
      </div>
    );
  }

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      {isTabVisible ? (
        <img
          key={`${retryCount}_${visibilityTick}`}
          src={streamSrc}
          alt="Live RTSP Stream"
          style={{ width: "100%", display: "block", background: "#050810" }}
          onError={() => setStreamError(true)}
        />
      ) : (
        <div style={{ aspectRatio: "16/9", background: "#050810" }} />
      )}
    </div>
  );
}

export default function CameraDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [camera, setCamera] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeROIEditor, setActiveROIEditor] = useState(null);
  const [liveData, setLiveData] = useState(null);
  const [roiSaved, setRoiSaved] = useState(false);
  const isMountedRef = useRef(true);
  const liveTimerRef = useRef(null);

  const camCode = camera?.camera_code || camera?.id || id;

  const fetchCamera = useCallback(async () => {
    try {
      const res = await getCameraById(id);
      const data = res?.data || res;
      if (isMountedRef.current) setCamera(data);
    } catch (e) {
      // Fallback: check FRS engine in-memory cameras
      try {
        const engRes = await fetch(`${BACKEND}/api/v1/frs-engine/cameras`);
        if (engRes.ok) {
          const engList = await engRes.json();
          const match = Array.isArray(engList)
            ? engList.find(c => c.camera_id?.toLowerCase() === id.toLowerCase())
            : (engList.camera_id?.toLowerCase() === id.toLowerCase() ? engList : null);
          if (match) {
            const fallback = {
              id: match.camera_id,
              camera_code: match.camera_id,
              name: match.name || match.camera_id,
              camera_type: match.camera_type || "CROWD",
              status: match.status === "online" ? "online" : "degraded",
              stream_url: match.stream_url,
              rtsp_url: match.rtsp_url,
              enabled: true,
              in_count: match.in_count,
              out_count: match.out_count,
              occupancy_count: match.occupancy_count,
              crowd_ai_active: match.crowd_ai_active,
              ai_purposes: match.ai_purposes,
            };
            if (isMountedRef.current) setCamera(fallback);
            return;
          }
        }
      } catch (_) {}
      if (isMountedRef.current) setError(e.message || "Camera not found.");
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, [id]);

  // Poll live counts from FRS engine every 3s
  const pollLiveCounts = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND}/api/v1/frs-engine/cameras`);
      if (!res.ok) return;
      const data = await res.json();
      const list = Array.isArray(data) ? data : [data];
      const match = list.find(c => c.camera_id?.toLowerCase() === id.toLowerCase());
      if (match && isMountedRef.current) setLiveData(match);
    } catch (_) {}
  }, [id]);

  useEffect(() => {
    isMountedRef.current = true;
    fetchCamera();
    pollLiveCounts();

    const schedule = () => {
      liveTimerRef.current = setTimeout(async () => {
        if (isMountedRef.current) {
          await pollLiveCounts();
          schedule();
        }
      }, 3000);
    };
    schedule();

    return () => {
      isMountedRef.current = false;
      clearTimeout(liveTimerRef.current);
    };
  }, [fetchCamera, pollLiveCounts]);

  if (loading) return <LoadingState />;
  if (error || !camera) return <ErrorState message={error || "Camera not found"} onRetry={() => navigate("/cameras")} />;

  const allPurposes = getAllPurposes(camera, liveData);
  const primaryPurpose = allPurposes[0] || "ENTRY_EXIT";
  const purpose = primaryPurpose;
  const pMeta = PURPOSE_META[primaryPurpose] || PURPOSE_META.ENTRY_EXIT;
  const isOnline = camera.status === "online" || camera.stream_status === "ONLINE";

  return (
    <div className="cc-page">
      {/* ── Header ── */}
      <div className="cc-page-header">
        <div>
          <button className="cc-btn" onClick={() => navigate("/cameras")} style={{ marginBottom: 6 }}>
            <i className="bi bi-arrow-left" /> Back to Cameras
          </button>
          <div className="cc-page-title">{camera.camera_code || camera.id}</div>
          <div className="cc-page-subtitle">{camera.name} — {camera.zone || camera.location_name || ""}</div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <PurposeBadge camera={camera} liveData={liveData} />
          <StatusBadge status={camera.status} />
          <button
            className="cc-btn"
            style={{
              padding: "5px 12px",
              fontSize: 11,
              display: "flex",
              alignItems: "center",
              gap: 5,
              color: "var(--cc-red)",
              borderColor: "rgba(248, 81, 73, 0.4)",
              background: "rgba(248, 81, 73, 0.1)",
              cursor: "pointer",
            }}
            onClick={async () => {
              if (window.confirm(`Are you sure you want to remove camera "${camera.name || camera.camera_code || camera.id}"? This will stop the live stream and delete the camera.`)) {
                try {
                  await deleteCamera(camera.camera_code || camera.id);
                  navigate("/cameras");
                } catch (err) {
                  alert("Failed to delete camera: " + (err.response?.data?.detail?.message || err.message));
                }
              }
            }}
            title="Delete this camera"
          >
            <i className="bi bi-trash3-fill" /> Delete Camera
          </button>
        </div>
      </div>

      {/* ROI Saved banner */}
      {roiSaved && (
        <div style={{ marginBottom: 12, padding: "10px 14px", borderRadius: 6, fontSize: 12,
          background: "rgba(63,185,80,0.1)", border: "1px solid #3fb950", color: "#3fb950",
          display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span><i className="bi bi-check-circle-fill" style={{ marginRight: 8 }} />ROI saved — live counting active.</span>
          <button onClick={() => setRoiSaved(false)} style={{ background: "none", border: "none", color: "inherit", cursor: "pointer" }}>✕</button>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", gap: 14 }}>
        {/* ── Left: Live Feed ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
            <CameraFeed camera={camera} />
          </div>

          {/* Live Counts */}
          <div className="cc-card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <div className="cc-section-title" style={{ margin: 0 }}>
                <i className="bi bi-activity" style={{ marginRight: 6, color: "var(--cc-green)" }} />
                Live Counts ({allPurposes.length} Active {allPurposes.length > 1 ? "Profiles" : "Profile"})
              </div>
              <span style={{ fontSize: 10, color: "#8b949e" }}>
                <span className="cc-live-dot" style={{ marginRight: 4 }} />
                Auto-refreshing every 3s
              </span>
            </div>
            <LiveCountsBar liveData={liveData} camera={camera} />
          </div>

          {/* ROI Configuration for each enabled purpose */}
          {allPurposes.some((p) => PURPOSE_META[p]?.roiTool) && (
            <div className="cc-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                <div>
                  <div className="cc-section-title" style={{ margin: 0 }}>
                    <i className="bi bi-diagram-2" style={{ marginRight: 6, color: "var(--cc-green)" }} />
                    ROI Configuration ({allPurposes.length} Active {allPurposes.length > 1 ? "Profiles" : "Profile"})
                  </div>
                  <div style={{ fontSize: 11, color: "#8b949e", marginTop: 4 }}>
                    Draw ROI boundaries on the live camera stream. You can configure detection areas for each active functionality.
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {allPurposes.map((purpKey) => {
                    const m = PURPOSE_META[purpKey];
                    if (!m?.roiTool) return null;
                    return (
                      <button
                        key={purpKey}
                        className="cc-btn cc-btn-primary"
                        style={{
                          fontSize: 12, padding: "8px 14px", background: m.bg,
                          borderColor: m.border, color: m.color, fontWeight: 700,
                          display: "flex", alignItems: "center", gap: 6, whiteSpace: "nowrap"
                        }}
                        onClick={() => setActiveROIEditor({
                          profile_id: purpKey === "QUEUE" ? "QUEUE_STANDARD" : "CROWD_STANDARD",
                          profile_name: m.label,
                          initial_tool: m.roiTool,
                          initial_objective: purpKey,
                        })}
                      >
                        <i className={`bi ${m.icon}`} />
                        {m.roiLabel}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ── Right: Info Panel ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {/* Camera Info */}
          <div className="cc-card">
            <div className="cc-section-title" style={{ marginBottom: 10 }}>Camera Info</div>
            {[
              { label: "Camera ID", value: camera.camera_code || camera.id, mono: true },
              { label: "Status",    value: camera.status || "online", color: isOnline ? "#3fb950" : "#f85149" },
              { label: "Purpose(s)",value: allPurposes.map((p) => PURPOSE_META[p]?.label || p).join(" + "), color: "var(--cc-green)" },
              { label: "Type",      value: camera.camera_type || "CROWD" },
              { label: "Zone",      value: camera.zone || "—" },
              { label: "Location",  value: camera.location_name || "—" },
              { label: "FPS",       value: `${camera.fps || 25} fps` },
              { label: "Resolution",value: camera.resolution || "1080p" },
            ].map(row => (
              <div key={row.label} style={{ display: "flex", justifyContent: "space-between",
                padding: "5px 0", borderBottom: "1px solid rgba(255,255,255,0.05)", fontSize: 12 }}>
                <span style={{ color: "#8b949e" }}>{row.label}</span>
                <span style={{ fontFamily: row.mono ? "monospace" : "inherit", fontWeight: 600,
                  color: row.color || "#c9d1d9" }}>{row.value}</span>
              </div>
            ))}
          </div>

          {/* Live AI Status */}
          <div className="cc-card">
            <div className="cc-section-title" style={{ marginBottom: 10 }}>AI Status</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                <span style={{ color: "#8b949e" }}>AI Mode</span>
                <span style={{ fontWeight: 700, color: liveData?.crowd_ai_active ? "#3fb950" : "#8b949e" }}>
                  {liveData?.crowd_ai_active ? "CROWD AI ACTIVE" : liveData?.is_frs ? "FRS ACTIVE" : "IDLE"}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                <span style={{ color: "#8b949e" }}>Active Purpose</span>
                <span style={{ fontWeight: 700, color: pMeta.color }}>{pMeta.label}</span>
              </div>
              {(allPurposes.includes("ENTRY") || allPurposes.includes("ENTRY_EXIT")) && (
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                  <span style={{ color: "#8b949e" }}>Total IN</span>
                  <span style={{ fontWeight: 700, color: "#3fb950" }}>{liveData?.in_count ?? 0}</span>
                </div>
              )}
              {(allPurposes.includes("EXIT") || allPurposes.includes("ENTRY_EXIT")) && (
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                  <span style={{ color: "#8b949e" }}>Total OUT</span>
                  <span style={{ fontWeight: 700, color: "#f85149" }}>{liveData?.out_count ?? 0}</span>
                </div>
              )}
              {allPurposes.includes("QUEUE") && (
                <>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                    <span style={{ color: "#8b949e" }}>People in Queue</span>
                    <span style={{ fontWeight: 700, color: "#d29922" }}>{liveData?.occupancy_count ?? 0}</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                    <span style={{ color: "#8b949e" }}>Queue Flow</span>
                    <span style={{ fontWeight: 700, color: (liveData?.queue_movement_status === "MOVING" || liveData?.queue_movement_status === "FAST") ? "#3fb950" : liveData?.queue_movement_status === "SLOW" ? "#d29922" : "#f85149" }}>
                      {liveData?.queue_movement_status === "FAST" ? "MOVING" : (liveData?.queue_movement_status || "STOPPED")}
                    </span>
                  </div>
                </>
              )}
              {allPurposes.includes("ZONE") && (
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                  <span style={{ color: "#8b949e" }}>People in Zone</span>
                  <span style={{ fontWeight: 700, color: "#3fb950" }}>{liveData?.occupancy_count ?? 0}</span>
                </div>
              )}
            </div>
          </div>

          {/* RTSP Info */}
          <div className="cc-card">
            <div className="cc-section-title" style={{ marginBottom: 8 }}>Stream</div>
            <div style={{ fontSize: 11, color: "#8b949e", wordBreak: "break-all", fontFamily: "monospace" }}>
              {camera.rtsp_url || "rtsp://configured-endpoint"}
            </div>
          </div>
        </div>
      </div>

      {/* ── ROI Editor Modal ── */}
      {activeROIEditor && (
        <ROIEditor
          camera={camera}
          profileId={activeROIEditor.profile_id}
          profileName={activeROIEditor.profile_name}
          initialTool={activeROIEditor.initial_tool}
          initialObjective={activeROIEditor.initial_objective}
          onClose={() => setActiveROIEditor(null)}
          onSaved={() => {
            setActiveROIEditor(null);
            setRoiSaved(true);
            fetchCamera();
            pollLiveCounts();
          }}
        />
      )}
    </div>
  );
}

