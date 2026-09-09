// Queue Intelligence Dashboard — Real-time queue headcount, wait times, and bottleneck detection
import { useEffect, useState, useCallback, useRef } from "react";
import KpiCard from "../components/common/KpiCard.jsx";
import StatusBadge from "../components/common/StatusBadge.jsx";
import { getQueueStatus } from "../services/queueService.js";
import { getQueueData } from "../services/crowdService.js";
import { LoadingState } from "../components/common/States.jsx";
import { useNavigate } from "react-router-dom";

export default function Queue() {
  const navigate = useNavigate();
  const [pipelineStatus, setPipelineStatus] = useState(null);
  const [dbQueues, setDbQueues] = useState([]);
  const [loading, setLoading] = useState(true);

  const inFlightRef = useRef(false);
  const timerRef = useRef(null);
  const isMountedRef = useRef(true);

  const fetchStatus = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      const [pRes, qRes] = await Promise.allSettled([
        getQueueStatus(),
        getQueueData(),
      ]);
      if (!isMountedRef.current) return;
      if (pRes.status === "fulfilled") {
        setPipelineStatus(pRes.value?.data || pRes.value);
      }
      if (qRes.status === "fulfilled") {
        const data = qRes.value?.data || qRes.value || [];
        setDbQueues(Array.isArray(data) ? data : []);
      }
    } catch {
      // ignore
    } finally {
      if (isMountedRef.current) setLoading(false);
      inFlightRef.current = false;
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    fetchStatus();

    const scheduleNext = () => {
      clearTimeout(timerRef.current);
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      timerRef.current = setTimeout(async () => {
        if (isMountedRef.current && document.visibilityState === "visible") {
          await fetchStatus();
          scheduleNext();
        }
      }, 5000);
    };

    scheduleNext();

    const handleVis = () => {
      if (document.visibilityState === "visible") {
        fetchStatus();
        scheduleNext();
      } else {
        clearTimeout(timerRef.current);
      }
    };
    document.addEventListener("visibilitychange", handleVis);

    return () => {
      isMountedRef.current = false;
      clearTimeout(timerRef.current);
      document.removeEventListener("visibilitychange", handleVis);
    };
  }, [fetchStatus]);

  if (loading) return <LoadingState />;

  const activePipelines = pipelineStatus?.pipelines || [];
  const totalPeople = pipelineStatus?.total_people_in_queues || 0;
  const runningCount = pipelineStatus?.running_pipelines || 0;
  const criticalQueues = pipelineStatus?.critical_queues || [];

  // Compute average wait across active pipelines
  const waitTimes = activePipelines
    .map((p) => p.metrics?.average_wait_seconds)
    .filter((w) => w !== null && w !== undefined && w > 0);
  const avgWaitSec = waitTimes.length > 0
    ? Math.round(waitTimes.reduce((a, b) => a + b, 0) / waitTimes.length)
    : null;

  return (
    <div className="cc-page">
      {/* Header */}
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title">Queue Intelligence</div>
          <div className="cc-page-subtitle">Real-Time Queue Analytics, Dwell Times & Congestion Control</div>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <button className="cc-btn cc-btn-secondary" onClick={fetchStatus}>
            <i className="bi bi-arrow-repeat" style={{ marginRight: 6 }} /> Refresh
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="cc-kpi-grid">
        <KpiCard
          title="Total in Queues"
          value={totalPeople}
          unit="persons"
          icon="bi-people-fill"
          color="blue"
        />
        <KpiCard
          title="Active Queues"
          value={runningCount}
          unit="cameras"
          icon="bi-camera-video-fill"
          color="green"
        />
        <KpiCard
          title="Critical Queues"
          value={criticalQueues.length}
          unit="sectors"
          icon="bi-exclamation-octagon-fill"
          color={criticalQueues.length > 0 ? "red" : "gray"}
        />
        <KpiCard
          title="Average Wait Time"
          value={avgWaitSec ? `${Math.floor(avgWaitSec / 60)}m ${avgWaitSec % 60}s` : "insufficient_data"}
          unit={avgWaitSec ? "" : ""}
          icon="bi-clock-history"
          color="yellow"
        />
      </div>

      {/* Active Pipeline Queues Section */}
      <div className="cc-card" style={{ marginBottom: 16 }}>
        <div className="cc-card-header">
          <div className="cc-card-title">Live Queue AI Telemetry</div>
          <span className="cc-tag">{activePipelines.length} Active Stream{activePipelines.length !== 1 ? "s" : ""}</span>
        </div>

        {activePipelines.length === 0 ? (
          <div style={{ padding: "30px 20px", textAlign: "center", color: "var(--cc-text-muted)" }}>
            <i className="bi bi-segmented-nav" style={{ fontSize: 36, opacity: 0.4, display: "block", marginBottom: 8 }} />
            <div style={{ fontSize: 13, fontWeight: 600 }}>No Queue AI pipelines currently active</div>
            <div style={{ fontSize: 11, marginTop: 4 }}>
              Assign the <code>QUEUE_STANDARD</code> profile to a camera in Camera Detail and click Start Queue Pipeline.
            </div>
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="cc-table">
              <thead>
                <tr>
                  <th>Camera</th>
                  <th>Sector</th>
                  <th>Status</th>
                  <th>Headcount</th>
                  <th>Occupancy</th>
                  <th>Avg Wait</th>
                  <th>Length</th>
                  <th>Inflow / Outflow</th>
                  <th>Direction</th>
                  <th>Risk</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {activePipelines.map((p) => {
                  const m = p.metrics || {};
                  return (
                    <tr key={p.camera_code}>
                      <td style={{ fontWeight: 700, fontFamily: "var(--cc-font-mono)" }}>
                        {p.camera_code}
                      </td>
                      <td>{p.queue_name || "Queue Line"}</td>
                      <td>
                        <span style={{
                          fontSize: 10,
                          fontWeight: 700,
                          padding: "2px 6px",
                          borderRadius: 3,
                          background: p.state === "RUNNING" ? "rgba(63,185,80,0.15)" : "rgba(139,148,158,0.15)",
                          color: p.state === "RUNNING" ? "var(--cc-green)" : "var(--cc-text-muted)",
                        }}>
                          {p.state}
                        </span>
                      </td>
                      <td style={{ fontWeight: 700, fontFamily: "var(--cc-font-mono)", fontSize: 14 }}>
                        {m.queue_count ?? 0}
                      </td>
                      <td>
                        {m.occupancy_percentage !== null && m.occupancy_percentage !== undefined
                          ? `${m.occupancy_percentage}%`
                          : <span style={{ color: "var(--cc-text-muted)", fontSize: 11 }}>N/A</span>}
                      </td>
                      <td style={{ color: "var(--cc-blue)", fontWeight: 600 }}>
                        {m.average_wait_seconds
                          ? `${Math.floor(m.average_wait_seconds / 60)}m ${m.average_wait_seconds % 60}s`
                          : <span style={{ color: "var(--cc-text-muted)", fontSize: 11 }}>insufficient_data</span>}
                      </td>
                      <td>
                        {m.queue_length?.value ? `${m.queue_length.value} ${m.queue_length.unit}` : "0.0"}
                      </td>
                      <td style={{ fontFamily: "var(--cc-font-mono)", fontSize: 11 }}>
                        +{m.inflow ?? 0} / -{m.outflow ?? 0}/min
                      </td>
                      <td>
                        <span style={{
                          fontSize: 10,
                          fontWeight: 600,
                          color: m.queue_direction === "FORWARD" ? "var(--cc-green)" : m.queue_direction === "BACKWARD" ? "var(--cc-yellow)" : "var(--cc-text-muted)",
                        }}>
                          {m.queue_direction || "UNKNOWN"}
                        </span>
                      </td>
                      <td>
                        <span style={{
                          fontSize: 10,
                          fontWeight: 700,
                          padding: "2px 6px",
                          borderRadius: 3,
                          background: m.risk_level === "CRITICAL" ? "rgba(248,81,73,0.2)" : m.risk_level === "HIGH" ? "rgba(210,153,34,0.2)" : "rgba(63,185,80,0.2)",
                          color: m.risk_level === "CRITICAL" ? "var(--cc-red)" : m.risk_level === "HIGH" ? "var(--cc-yellow)" : "var(--cc-green)",
                        }}>
                          {m.risk_level} ({m.risk_score})
                        </span>
                      </td>
                      <td>
                        <button
                          className="cc-btn cc-btn-secondary"
                          style={{ fontSize: 10, padding: "2px 6px" }}
                          onClick={() => navigate(`/cameras/${p.camera_id}`)}
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Historical Queue Analytics (No fake data fallback) */}
      <div className="cc-card">
        <div className="cc-card-header">
          <div className="cc-card-title">Queue Wait Time Trends (24h)</div>
        </div>
        <div style={{ padding: "40px 20px", textAlign: "center", color: "var(--cc-text-muted)", fontStyle: "italic" }}>
          No historical data available.
        </div>
      </div>
    </div>
  );
}
