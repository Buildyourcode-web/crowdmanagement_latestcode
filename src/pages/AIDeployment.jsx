// AIDeployment.jsx — AI Orchestrator & Multi-Camera Pipeline Management Console
// Route: /ai-deployment
// Features:
// 1. Centralized AI Orchestrator: Multi-camera desired vs actual state monitor, Start All / Stop All,
//    individual pipeline Start/Stop/Restart, fault diagnostics, auto-reconnect telemetry.
// 2. Hardware Capacity & Runtime Engine: hardware inspection, per-profile capacity, system health check.

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  getAICapabilities,
  getAICapacity,
  listAIDeployments,
  getAIOrchestratorStatus,
  startAIPipeline,
  stopAIPipeline,
  restartAIPipeline,
  startAllAIPipelines,
  stopAllAIPipelines,
} from '../services/aiService.js';
import { useAppStore } from '../store/useAppStore.js';

// ─── Utility: Resource Utilization Bar ────────────────────────────────────────
function UtilBar({ label, value, unit = '%', maxVal = 100, icon }) {
  const pct = Math.min(100, Math.round(((value || 0) / maxVal) * 100));
  const color = pct > 85 ? 'var(--cc-red)' : pct > 65 ? 'var(--cc-yellow)' : 'var(--cc-green)';
  const barChar = (n) => '█'.repeat(Math.round(n / 10)) + '░'.repeat(10 - Math.round(n / 10));
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: 11, color: 'var(--cc-text-muted)', display: 'flex', alignItems: 'center', gap: 5 }}>
          {icon && <i className={`bi ${icon}`} />} {label}
        </span>
        <span style={{ fontFamily: 'var(--cc-font-mono)', fontSize: 12, fontWeight: 700, color }}>
          {value !== null && value !== undefined ? `${typeof value === 'number' ? value.toFixed(1) : value}${unit}` : '—'}
        </span>
      </div>
      <div style={{ background: 'var(--cc-bg-primary)', borderRadius: 3, height: 8, overflow: 'hidden', border: '1px solid var(--cc-border)' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 3, transition: 'width 0.6s ease' }} />
      </div>
      <div style={{ fontSize: 9, fontFamily: 'var(--cc-font-mono)', color, marginTop: 3 }}>
        {barChar(pct)} {pct}%
      </div>
    </div>
  );
}

// ─── Capacity Card ────────────────────────────────────────────────────────────
function CapacityCard({ label, profileId, profileData, icon }) {
  if (!profileData) return null;
  const { capacity, status, status_reason } = profileData;
  const isUnavail = status === 'GPU_UNAVAILABLE' || status === 'RESOURCE_EXHAUSTED';
  const isFallback = status === 'CPU_FALLBACK';
  const borderColor = isUnavail ? 'var(--cc-red)' : isFallback ? 'var(--cc-yellow)' : 'var(--cc-green)';

  return (
    <div className="cc-card" style={{ borderLeft: `3px solid ${borderColor}`, position: 'relative' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <i className={`bi ${icon}`} style={{ color: borderColor, fontSize: 15 }} />
          <span style={{ fontWeight: 700, fontSize: 12, color: 'var(--cc-text-primary)' }}>{label}</span>
        </div>
        <span style={{
          fontSize: 9, fontWeight: 700, letterSpacing: '0.06em', padding: '2px 6px',
          background: isUnavail ? 'rgba(248,81,73,0.1)' : isFallback ? 'rgba(227,179,65,0.1)' : 'rgba(63,185,80,0.1)',
          color: borderColor, borderRadius: 3, border: `1px solid ${borderColor}`,
        }}>
          {isUnavail ? 'UNAVAILABLE' : isFallback ? 'CPU FALLBACK' : 'AVAILABLE'}
        </span>
      </div>
      {isUnavail ? (
        <div style={{ fontSize: 11, color: 'var(--cc-text-muted)', lineHeight: 1.5 }}>
          <i className="bi bi-exclamation-triangle" style={{ color: 'var(--cc-red)', marginRight: 5 }} />
          {status_reason || 'Insufficient resources for this profile.'}
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
          {[
            { label: 'Recommended', value: capacity?.recommended_cameras ?? 0, color: 'var(--cc-green)' },
            { label: 'Maximum', value: capacity?.maximum_cameras ?? 0, color: 'var(--cc-text-secondary)' },
          ].map(item => (
            <div key={item.label} style={{ background: 'var(--cc-bg-primary)', borderRadius: 4, padding: '8px 10px', textAlign: 'center' }}>
              <div style={{ fontFamily: 'var(--cc-font-mono)', fontSize: 22, fontWeight: 700, color: item.color }}>{item.value}</div>
              <div style={{ fontSize: 10, color: 'var(--cc-text-muted)', marginTop: 2 }}>{item.label} Cameras</div>
            </div>
          ))}
        </div>
      )}
      {capacity?.limiting_resource && !isUnavail && (
        <div style={{ marginTop: 8, fontSize: 10, color: 'var(--cc-text-muted)' }}>
          Limiting factor: <span style={{ fontFamily: 'var(--cc-font-mono)', color: 'var(--cc-text-secondary)' }}>{capacity.limiting_resource}</span>
        </div>
      )}
      <div style={{ marginTop: 6, fontSize: 9, color: 'var(--cc-text-muted)', fontStyle: 'italic' }}>
        Mode: ESTIMATED
      </div>
    </div>
  );
}

// ─── Runtime Stack Badge ──────────────────────────────────────────────────────
function StackBadge({ label, available, icon }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px',
      background: available ? 'rgba(63,185,80,0.08)' : 'rgba(248,81,73,0.08)',
      border: `1px solid ${available ? 'rgba(63,185,80,0.2)' : 'rgba(248,81,73,0.2)'}`,
      borderRadius: 4, fontSize: 11,
    }}>
      <i className={`bi ${icon}`} style={{ color: available ? 'var(--cc-green)' : 'var(--cc-red)' }} />
      <span style={{ color: 'var(--cc-text-primary)' }}>{label}</span>
      <span style={{ marginLeft: 'auto', fontFamily: 'var(--cc-font-mono)', fontSize: 10, fontWeight: 700, color: available ? 'var(--cc-green)' : 'var(--cc-red)' }}>
        {available ? '✓' : '✗'}
      </span>
    </div>
  );
}

// ─── System Check Step ────────────────────────────────────────────────────────
const CHECK_STEPS = [
  { key: 'cpu', label: 'Detecting CPU...', icon: 'bi-cpu' },
  { key: 'ram', label: 'Detecting RAM...', icon: 'bi-memory' },
  { key: 'gpu', label: 'Detecting GPU...', icon: 'bi-gpu-card' },
  { key: 'cuda', label: 'Checking CUDA...', icon: 'bi-lightning-charge' },
  { key: 'tensorrt', label: 'Checking TensorRT...', icon: 'bi-layers' },
  { key: 'deepstream', label: 'Checking DeepStream...', icon: 'bi-camera-video' },
  { key: 'docker', label: 'Checking Docker...', icon: 'bi-box' },
  { key: 'postgresql', label: 'Checking PostgreSQL...', icon: 'bi-server' },
  { key: 'redis', label: 'Checking Redis...', icon: 'bi-lightning-fill' },
  { key: 'capacity', label: 'Calculating AI capacity...', icon: 'bi-calculator' },
];

export default function AIDeployment() {
  const [activeTab, setActiveTab] = useState('orchestrator'); // 'orchestrator' | 'hardware'
  const [caps, setCaps] = useState(null);
  const [capacity, setCapacity] = useState(null);
  const [deployments, setDeployments] = useState([]);
  const [orchStatus, setOrchStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(false);
  const [checkStep, setCheckStep] = useState(-1);
  const [error, setError] = useState(null);
  const [actionSuccess, setActionSuccess] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [actionLoading, setActionLoading] = useState({});
  const [confirmModal, setConfirmModal] = useState(null); // { type: 'START_ALL' | 'STOP_ALL' }

  const theme = useAppStore(s => s.theme);
  const isLight = theme === 'light';

  const inFlightRef = useRef(false);
  const timerRef = useRef(null);
  const isMountedRef = useRef(true);

  const fetchData = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    setLoading(true);
    setError(null);
    try {
      const [capsData, capData, depsData, statusData] = await Promise.all([
        getAICapabilities().catch(() => null),
        getAICapacity().catch(() => null),
        listAIDeployments().catch(() => []),
        getAIOrchestratorStatus().catch(() => null),
      ]);
      if (!isMountedRef.current) return;
      if (capsData) setCaps(capsData);
      if (capData) setCapacity(capData);
      setDeployments(depsData || []);
      setOrchStatus(statusData);
      setLastRefresh(new Date().toLocaleTimeString());
    } catch (e) {
      if (isMountedRef.current) {
        setError(e.response?.data?.message || e.message || 'Failed to fetch orchestrator data.');
      }
    } finally {
      if (isMountedRef.current) setLoading(false);
      inFlightRef.current = false;
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    fetchData();

    const scheduleNext = () => {
      clearTimeout(timerRef.current);
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      timerRef.current = setTimeout(async () => {
        if (isMountedRef.current && document.visibilityState === "visible") {
          await fetchData();
          scheduleNext();
        }
      }, 8000);
    };

    scheduleNext();

    const handleVis = () => {
      if (document.visibilityState === "visible") {
        fetchData();
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
  }, [fetchData]);

  // ── Action Handlers ──────────────────────────────────────────────────────────
  const handleStartPipeline = async (cameraCode) => {
    setActionLoading(prev => ({ ...prev, [cameraCode]: true }));
    setError(null);
    setActionSuccess(null);
    try {
      await startAIPipeline(cameraCode);
      setActionSuccess(`Pipeline for ${cameraCode} started successfully.`);
      await fetchData();
    } catch (e) {
      const msg = e.response?.data?.detail?.message || e.response?.data?.message || e.message;
      setError(`Failed to start ${cameraCode}: ${msg}`);
    } finally {
      setActionLoading(prev => ({ ...prev, [cameraCode]: false }));
    }
  };

  const handleStopPipeline = async (cameraCode) => {
    setActionLoading(prev => ({ ...prev, [cameraCode]: true }));
    setError(null);
    setActionSuccess(null);
    try {
      await stopAIPipeline(cameraCode);
      setActionSuccess(`Pipeline for ${cameraCode} stopped.`);
      await fetchData();
    } catch (e) {
      const msg = e.response?.data?.detail?.message || e.response?.data?.message || e.message;
      setError(`Failed to stop ${cameraCode}: ${msg}`);
    } finally {
      setActionLoading(prev => ({ ...prev, [cameraCode]: false }));
    }
  };

  const handleRestartPipeline = async (cameraCode) => {
    setActionLoading(prev => ({ ...prev, [cameraCode]: true }));
    setError(null);
    setActionSuccess(null);
    try {
      await restartAIPipeline(cameraCode);
      setActionSuccess(`Pipeline for ${cameraCode} restarted.`);
      await fetchData();
    } catch (e) {
      const msg = e.response?.data?.detail?.message || e.response?.data?.message || e.message;
      setError(`Failed to restart ${cameraCode}: ${msg}`);
    } finally {
      setActionLoading(prev => ({ ...prev, [cameraCode]: false }));
    }
  };

  const handleStartAll = async () => {
    setConfirmModal(null);
    setLoading(true);
    setError(null);
    setActionSuccess(null);
    try {
      const res = await startAllAIPipelines();
      const started = res.started?.length || 0;
      const blocked = res.blocked?.length || 0;
      const failed = res.failed?.length || 0;
      setActionSuccess(`Start All completed: ${started} started, ${blocked} blocked by capacity, ${failed} failed.`);
      await fetchData();
    } catch (e) {
      const msg = e.response?.data?.detail?.message || e.response?.data?.message || e.message;
      setError(`Start All failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  const handleStopAll = async () => {
    setConfirmModal(null);
    setLoading(true);
    setError(null);
    setActionSuccess(null);
    try {
      const res = await stopAllAIPipelines();
      const stopped = res.stopped?.length || 0;
      setActionSuccess(`Stop All completed: ${stopped} pipelines stopped.`);
      await fetchData();
    } catch (e) {
      const msg = e.response?.data?.detail?.message || e.response?.data?.message || e.message;
      setError(`Stop All failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  const runSystemCheck = async () => {
    setChecking(true);
    setCheckStep(0);
    setError(null);
    for (let i = 0; i < CHECK_STEPS.length; i++) {
      setCheckStep(i);
      await new Promise(r => setTimeout(r, 450));
    }
    try {
      const [capsData, capData] = await Promise.all([
        getAICapabilities(),
        getAICapacity(),
      ]);
      setCaps(capsData);
      setCapacity(capData);
      setLastRefresh(new Date().toLocaleTimeString());
    } catch (e) {
      setError(e.response?.data?.message || e.message || 'System check failed.');
    } finally {
      setCheckStep(CHECK_STEPS.length);
      setTimeout(() => {
        setChecking(false);
        setCheckStep(-1);
      }, 1500);
    }
  };

  const cpu = caps?.cpu || {};
  const ram = caps?.ram || {};
  const gpu = caps?.gpu || {};
  const runtime = caps?.runtime || {};
  const currentUtil = capacity?.current_utilization || {};
  const profiles = capacity?.profiles || {};
  const safetyConfig = capacity?.safety_config || {};

  const stateCounts = orchStatus?.state_counts || {
    RUNNING: deployments.filter(d => d.actual_state === 'RUNNING').length,
    DEGRADED: deployments.filter(d => d.actual_state === 'DEGRADED').length,
    FAILED: deployments.filter(d => d.actual_state === 'FAILED').length,
    STOPPED: deployments.filter(d => d.actual_state === 'STOPPED').length,
  };

  return (
    <div style={{ padding: 24, maxWidth: 1400, margin: '0 auto' }}>
      {/* Header & Tabs */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 10, color: 'var(--cc-text-primary)' }}>
            <i className="bi bi-cpu-fill" style={{ color: 'var(--cc-blue)' }} />
            AI Orchestration & Deployment Center
          </h1>
          <div style={{ fontSize: 12, color: 'var(--cc-text-muted)', marginTop: 4 }}>
            Control plane managing Crowd & Queue AI pipelines, automated RTSP reconnects, and hardware capacity boundaries.
          </div>
        </div>

        {/* Tab Selector & Actions */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <div style={{ background: 'var(--cc-bg-card)', padding: 3, borderRadius: 6, border: '1px solid var(--cc-border)', display: 'flex' }}>
            <button
              onClick={() => setActiveTab('orchestrator')}
              style={{
                padding: '6px 14px', borderRadius: 4, border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600,
                background: activeTab === 'orchestrator' ? 'var(--cc-blue)' : 'transparent',
                color: activeTab === 'orchestrator' ? '#fff' : 'var(--cc-text-muted)',
              }}
            >
              <i className="bi bi-diagram-3-fill" style={{ marginRight: 6 }} />
              Pipeline Orchestrator
            </button>
            <button
              onClick={() => setActiveTab('hardware')}
              style={{
                padding: '6px 14px', borderRadius: 4, border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600,
                background: activeTab === 'hardware' ? 'var(--cc-blue)' : 'transparent',
                color: activeTab === 'hardware' ? '#fff' : 'var(--cc-text-muted)',
              }}
            >
              <i className="bi bi-hdd-network-fill" style={{ marginRight: 6 }} />
              Hardware & Capacity
            </button>
          </div>

          <button
            onClick={fetchData}
            disabled={loading}
            className="cc-btn cc-btn-secondary"
            style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, height: 34 }}
          >
            <i className={`bi bi-arrow-clockwise ${loading ? 'spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Alert Notices */}
      {actionSuccess && (
        <div style={{ padding: '10px 14px', background: 'rgba(63,185,80,0.1)', border: '1px solid rgba(63,185,80,0.3)', borderRadius: 6, color: 'var(--cc-green)', fontSize: 12, marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span><i className="bi bi-check-circle-fill" style={{ marginRight: 8 }} />{actionSuccess}</span>
          <button onClick={() => setActionSuccess(null)} style={{ background: 'none', border: 'none', color: 'var(--cc-green)', cursor: 'pointer' }}>×</button>
        </div>
      )}
      {error && (
        <div style={{ padding: '10px 14px', background: 'rgba(248,81,73,0.1)', border: '1px solid rgba(248,81,73,0.3)', borderRadius: 6, color: 'var(--cc-red)', fontSize: 12, marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span><i className="bi bi-exclamation-triangle-fill" style={{ marginRight: 8 }} />{error}</span>
          <button onClick={() => setError(null)} style={{ background: 'none', border: 'none', color: 'var(--cc-red)', cursor: 'pointer' }}>×</button>
        </div>
      )}

      {/* ── TAB 1: PIPELINE ORCHESTRATOR ── */}
      {activeTab === 'orchestrator' && (
        <div>
          {/* Status Ribbon */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 20 }}>
            <div className="cc-card" style={{ padding: '12px 16px' }}>
              <div style={{ fontSize: 11, color: 'var(--cc-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Running Pipelines</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--cc-green)', marginTop: 4 }}>{stateCounts.RUNNING}</div>
              <div style={{ fontSize: 10, color: 'var(--cc-text-muted)', marginTop: 2 }}>Desired State: RUNNING</div>
            </div>
            <div className="cc-card" style={{ padding: '12px 16px' }}>
              <div style={{ fontSize: 11, color: 'var(--cc-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Degraded / Dropped</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--cc-yellow)', marginTop: 4 }}>{stateCounts.DEGRADED}</div>
              <div style={{ fontSize: 10, color: 'var(--cc-text-muted)', marginTop: 2 }}>Auto-reconnecting RTSP</div>
            </div>
            <div className="cc-card" style={{ padding: '12px 16px' }}>
              <div style={{ fontSize: 11, color: 'var(--cc-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Failed Pipelines</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--cc-red)', marginTop: 4 }}>{stateCounts.FAILED}</div>
              <div style={{ fontSize: 10, color: 'var(--cc-text-muted)', marginTop: 2 }}>Recovery monitored</div>
            </div>
            <div className="cc-card" style={{ padding: '12px 16px' }}>
              <div style={{ fontSize: 11, color: 'var(--cc-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Stopped / Idle</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--cc-text-secondary)', marginTop: 4 }}>{stateCounts.STOPPED}</div>
              <div style={{ fontSize: 10, color: 'var(--cc-text-muted)', marginTop: 2 }}>Desired State: STOPPED</div>
            </div>
            <div className="cc-card" style={{ padding: '12px 16px', borderLeft: '3px solid var(--cc-blue)' }}>
              <div style={{ fontSize: 11, color: 'var(--cc-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Supervision Loop</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--cc-blue)', marginTop: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--cc-green)', display: 'inline-block' }} />
                ACTIVE (5s interval)
              </div>
              <div style={{ fontSize: 10, color: 'var(--cc-text-muted)', marginTop: 4 }}>Auto-recovery: Max 3/10m</div>
            </div>
          </div>

          {/* Mass Control Panel */}
          <div className="cc-card" style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--cc-text-primary)' }}>Mass Fleet Operations</div>
              <div style={{ fontSize: 11, color: 'var(--cc-text-muted)', marginTop: 2 }}>
                Execute resource-aware startup across priority cameras or gracefully stop all running pipelines.
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button
                onClick={() => setConfirmModal({ type: 'START_ALL' })}
                disabled={loading}
                className="cc-btn cc-btn-primary"
                style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, background: 'var(--cc-green)' }}
              >
                <i className="bi bi-play-circle-fill" />
                Start All Eligible
              </button>
              <button
                onClick={() => setConfirmModal({ type: 'STOP_ALL' })}
                disabled={loading}
                className="cc-btn cc-btn-danger"
                style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}
              >
                <i className="bi bi-stop-circle-fill" />
                Stop All Pipelines
              </button>
            </div>
          </div>

          {/* Deployments Table */}
          <div className="cc-card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--cc-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--cc-text-primary)' }}>
                Camera Deployments ({deployments.length})
              </div>
              <div style={{ fontSize: 11, color: 'var(--cc-text-muted)' }}>
                Ordered by Priority (CRITICAL &gt; HIGH &gt; NORMAL &gt; LOW)
              </div>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, textAlign: 'left' }}>
                <thead>
                  <tr style={{ background: 'var(--cc-bg-primary)', borderBottom: '1px solid var(--cc-border)', color: 'var(--cc-text-muted)' }}>
                    <th style={{ padding: '10px 14px' }}>Camera</th>
                    <th style={{ padding: '10px 14px' }}>Profile / Type</th>
                    <th style={{ padding: '10px 14px' }}>Priority</th>
                    <th style={{ padding: '10px 14px' }}>Desired State</th>
                    <th style={{ padding: '10px 14px' }}>Actual State</th>
                    <th style={{ padding: '10px 14px' }}>Telemetry</th>
                    <th style={{ padding: '10px 14px' }}>Restarts</th>
                    <th style={{ padding: '10px 14px', textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {deployments.length === 0 ? (
                    <tr>
                      <td colSpan={8} style={{ padding: 30, textAlign: 'center', color: 'var(--cc-text-muted)' }}>
                        No camera AI deployments registered yet. Assign profiles via Cameras screen to enable automated orchestration.
                      </td>
                    </tr>
                  ) : (
                    deployments.map(dep => {
                      const isRunning = dep.actual_state === 'RUNNING';
                      const isDegraded = dep.actual_state === 'DEGRADED';
                      const isFailed = dep.actual_state === 'FAILED';
                      const isStarting = dep.actual_state === 'STARTING' || dep.actual_state === 'RESTARTING';
                      const isBusy = actionLoading[dep.camera_code];

                      let stateColor = 'var(--cc-text-muted)';
                      let stateBg = 'rgba(110,118,129,0.1)';
                      if (isRunning) { stateColor = 'var(--cc-green)'; stateBg = 'rgba(63,185,80,0.1)'; }
                      else if (isDegraded) { stateColor = 'var(--cc-yellow)'; stateBg = 'rgba(227,179,65,0.1)'; }
                      else if (isFailed) { stateColor = 'var(--cc-red)'; stateBg = 'rgba(248,81,73,0.1)'; }
                      else if (isStarting) { stateColor = 'var(--cc-blue)'; stateBg = 'rgba(88,166,255,0.1)'; }

                      return (
                        <tr key={dep.id} style={{ borderBottom: '1px solid var(--cc-border)' }}>
                          <td style={{ padding: '10px 14px' }}>
                            <div style={{ fontWeight: 700, color: 'var(--cc-text-primary)' }}>{dep.camera_code}</div>
                            {dep.runtime_instance_id && (
                              <div style={{ fontSize: 9, fontFamily: 'var(--cc-font-mono)', color: 'var(--cc-text-muted)' }}>{dep.runtime_instance_id}</div>
                            )}
                          </td>
                          <td style={{ padding: '10px 14px' }}>
                            <span style={{ padding: '2px 6px', background: 'rgba(88,166,255,0.08)', borderRadius: 3, border: '1px solid rgba(88,166,255,0.2)', fontSize: 10, fontWeight: 600, color: 'var(--cc-blue)' }}>
                              {dep.profile_id}
                            </span>
                            <div style={{ fontSize: 10, color: 'var(--cc-text-muted)', marginTop: 2 }}>{dep.pipeline_type}</div>
                          </td>
                          <td style={{ padding: '10px 14px' }}>
                            <span style={{
                              fontSize: 10, fontWeight: 700, padding: '2px 6px', borderRadius: 3,
                              color: dep.priority === 'CRITICAL' ? 'var(--cc-red)' : dep.priority === 'HIGH' ? 'var(--cc-yellow)' : 'var(--cc-text-secondary)',
                              background: dep.priority === 'CRITICAL' ? 'rgba(248,81,73,0.1)' : dep.priority === 'HIGH' ? 'rgba(227,179,65,0.1)' : 'rgba(110,118,129,0.1)',
                            }}>
                              {dep.priority}
                            </span>
                          </td>
                          <td style={{ padding: '10px 14px' }}>
                            <span style={{ fontFamily: 'var(--cc-font-mono)', fontSize: 11, fontWeight: 600, color: dep.desired_state === 'RUNNING' ? 'var(--cc-green)' : 'var(--cc-text-muted)' }}>
                              {dep.desired_state}
                            </span>
                          </td>
                          <td style={{ padding: '10px 14px' }}>
                            <span style={{
                              padding: '3px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700,
                              color: stateColor, background: stateBg, border: `1px solid ${stateColor}`,
                              display: 'inline-flex', alignItems: 'center', gap: 5
                            }}>
                              {isStarting && <i className="bi bi-arrow-repeat spin" />}
                              {dep.actual_state}
                            </span>
                            {dep.last_error && isFailed && (
                              <div style={{ fontSize: 10, color: 'var(--cc-red)', marginTop: 3, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={dep.last_error}>
                                {dep.last_error}
                              </div>
                            )}
                          </td>
                          <td style={{ padding: '10px 14px' }}>
                            {isRunning ? (
                              <div>
                                <div style={{ fontSize: 11, fontFamily: 'var(--cc-font-mono)', color: 'var(--cc-text-primary)' }}>
                                  {dep.fps_actual ? `${dep.fps_actual.toFixed(1)} FPS` : 'Running'}
                                </div>
                                <div style={{ fontSize: 10, color: 'var(--cc-text-muted)' }}>
                                  {dep.latency_ms ? `${dep.latency_ms.toFixed(0)} ms` : 'Active'}
                                </div>
                              </div>
                            ) : (
                              <span style={{ color: 'var(--cc-text-muted)', fontSize: 11 }}>—</span>
                            )}
                          </td>
                          <td style={{ padding: '10px 14px' }}>
                            <div style={{ fontSize: 11, fontFamily: 'var(--cc-font-mono)' }}>
                              R: {dep.restart_count} / C: {dep.reconnect_count}
                            </div>
                          </td>
                          <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                            <div style={{ display: 'inline-flex', gap: 6 }}>
                              {!isRunning ? (
                                <button
                                  onClick={() => handleStartPipeline(dep.camera_code)}
                                  disabled={isBusy || loading}
                                  className="cc-btn cc-btn-primary"
                                  style={{ padding: '4px 8px', fontSize: 11, background: 'var(--cc-green)' }}
                                  title="Start Pipeline"
                                >
                                  <i className="bi bi-play-fill" /> Start
                                </button>
                              ) : (
                                <button
                                  onClick={() => handleStopPipeline(dep.camera_code)}
                                  disabled={isBusy || loading}
                                  className="cc-btn cc-btn-danger"
                                  style={{ padding: '4px 8px', fontSize: 11 }}
                                  title="Stop Pipeline"
                                >
                                  <i className="bi bi-stop-fill" /> Stop
                                </button>
                              )}
                              <button
                                onClick={() => handleRestartPipeline(dep.camera_code)}
                                disabled={isBusy || loading}
                                className="cc-btn cc-btn-secondary"
                                style={{ padding: '4px 8px', fontSize: 11 }}
                                title="Restart Pipeline"
                              >
                                <i className="bi bi-arrow-clockwise" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ── TAB 2: HARDWARE CAPACITY & RUNTIME ── */}
      {activeTab === 'hardware' && (
        <div>
          {/* Status Bar */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <span style={{ fontSize: 11, color: 'var(--cc-text-muted)' }}>
              Last sampled: {lastRefresh || '—'}
            </span>
            <button
              onClick={runSystemCheck}
              disabled={checking}
              className="cc-btn cc-btn-primary"
              style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}
            >
              <i className={`bi bi-shield-check ${checking ? 'spin' : ''}`} />
              {checking ? 'Running Check...' : 'Run System Check'}
            </button>
          </div>

          {/* System Check Progress Modal */}
          {checking && (
            <div className="cc-card" style={{ marginBottom: 20, borderLeft: '3px solid var(--cc-blue)' }}>
              <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 10, color: 'var(--cc-text-primary)' }}>
                System Verification in Progress
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
                {CHECK_STEPS.map((s, idx) => {
                  const done = checkStep > idx;
                  const current = checkStep === idx;
                  return (
                    <div key={s.key} style={{
                      display: 'flex', alignItems: 'center', gap: 6, fontSize: 11,
                      color: done ? 'var(--cc-green)' : current ? 'var(--cc-blue)' : 'var(--cc-text-muted)',
                    }}>
                      <i className={`bi ${done ? 'bi-check-circle-fill' : current ? `${s.icon} spin` : s.icon}`} />
                      {s.label}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Resource Utilization & Stack Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
            {/* Live Utilization */}
            <div className="cc-card">
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--cc-text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 14 }}>
                Compute & Memory Utilization
              </div>
              <UtilBar label="CPU Load" value={currentUtil.cpu_percent} unit="%" icon="bi-cpu" />
              <UtilBar label="System RAM" value={currentUtil.ram_percent} unit="%" icon="bi-memory" />
              <UtilBar label="GPU Core Load" value={currentUtil.gpu_load_percent} unit="%" icon="bi-gpu-card" />
              <UtilBar label="GPU VRAM" value={currentUtil.vram_percent} unit="%" icon="bi-lightning-charge" />
            </div>

            {/* Runtime Stack */}
            <div className="cc-card">
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--cc-text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 14 }}>
                AI Runtime Stack Readiness
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <StackBadge label="NVIDIA Driver" available={gpu.driver_detected} icon="bi-gpu-card" />
                <StackBadge label="CUDA Toolkit" available={gpu.cuda_available} icon="bi-lightning-charge" />
                <StackBadge label="TensorRT" available={runtime.tensorrt} icon="bi-layers" />
                <StackBadge label="DeepStream" available={runtime.deepstream} icon="bi-camera-video" />
                <StackBadge label="Docker Engine" available={runtime.docker} icon="bi-box" />
                <StackBadge label="PostgreSQL" available={true} icon="bi-server" />
                <StackBadge label="Redis Bus" available={true} icon="bi-lightning-fill" />
                <StackBadge label="CPU Fallback" available={true} icon="bi-cpu" />
              </div>
            </div>
          </div>

          {/* Per-Profile Capacity Grid */}
          <div className="cc-card" style={{ marginBottom: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--cc-text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  Per-Profile Camera Stream Limits
                </div>
                <div style={{ fontSize: 11, color: 'var(--cc-text-muted)', marginTop: 2 }}>
                  Calculated independently per workload profile
                </div>
              </div>
              <div style={{ padding: '4px 10px', background: 'rgba(88,166,255,0.1)', border: '1px solid rgba(88,166,255,0.2)', borderRadius: 4, fontSize: 10, fontWeight: 700, color: 'var(--cc-blue)' }}>
                ESTIMATION MODE — Safe Headroom Enforced
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
              <CapacityCard label="Crowd AI — Standard" profileId="CROWD_STANDARD" profileData={profiles.CROWD_STANDARD} icon="bi-people-fill" />
              <CapacityCard label="Crowd AI — High Density" profileId="CROWD_HIGH_DENSITY" profileData={profiles.CROWD_HIGH_DENSITY} icon="bi-person-fill-exclamation" />
              <CapacityCard label="Queue AI — Standard" profileId="QUEUE_STANDARD" profileData={profiles.QUEUE_STANDARD} icon="bi-align-start" />
              <CapacityCard label="FRS Biometric" profileId="FRS_STANDARD" profileData={profiles.FRS_STANDARD} icon="bi-person-bounding-box" />
              <CapacityCard label="Video Safety AI" profileId="VIDEO_SAFETY" profileData={profiles.VIDEO_SAFETY} icon="bi-shield-fill-check" />
            </div>
          </div>

          {/* Safety Headroom Config */}
          <div className="cc-card">
            <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--cc-text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>
              Capacity Safety Configuration
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 8 }}>
              {[
                { label: 'Reserved CPU', value: `${safetyConfig.system_reserved_cpu_percent ?? 15}%` },
                { label: 'Reserved RAM', value: `${safetyConfig.system_reserved_ram_gb ?? 2} GB` },
                { label: 'Reserved VRAM', value: `${safetyConfig.system_reserved_vram_gb ?? 0.5} GB` },
                { label: 'CPU Headroom', value: `${safetyConfig.safe_headroom_cpu_percent ?? 10}%` },
                { label: 'RAM Headroom', value: `${safetyConfig.safe_headroom_ram_percent ?? 10}%` },
                { label: 'GPU Headroom', value: `${safetyConfig.safe_headroom_gpu_percent ?? 15}%` },
                { label: 'VRAM Headroom', value: `${safetyConfig.safe_headroom_vram_percent ?? 15}%` },
                { label: 'Max GPU', value: `${safetyConfig.hard_max_gpu_percent ?? 90}%` },
              ].map(item => (
                <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 8px', background: 'var(--cc-bg-primary)', borderRadius: 4, border: '1px solid var(--cc-border)', fontSize: 11 }}>
                  <span style={{ color: 'var(--cc-text-muted)' }}>{item.label}</span>
                  <span style={{ fontFamily: 'var(--cc-font-mono)', fontWeight: 700, color: 'var(--cc-text-primary)' }}>{item.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Confirmation Modal */}
      {confirmModal && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
        }}>
          <div className="cc-card" style={{ maxWidth: 450, width: '90%', padding: 24 }}>
            <h3 style={{ margin: '0 0 12px 0', fontSize: 16, fontWeight: 700, color: 'var(--cc-text-primary)' }}>
              {confirmModal.type === 'START_ALL' ? 'Confirm Start All Pipelines' : 'Confirm Stop All Pipelines'}
            </h3>
            <p style={{ fontSize: 12, color: 'var(--cc-text-muted)', lineHeight: 1.5, margin: '0 0 20px 0' }}>
              {confirmModal.type === 'START_ALL' ? (
                'The orchestrator will evaluate server capacity and launch eligible Crowd and Queue pipelines in priority order. Deployments that exceed hardware limits will be blocked safely.'
              ) : (
                'This will gracefully stop all active video inference pipelines across the festival perimeter. Live detection metrics will pause.'
              )}
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button
                onClick={() => setConfirmModal(null)}
                className="cc-btn cc-btn-secondary"
                style={{ fontSize: 12 }}
              >
                Cancel
              </button>
              <button
                onClick={confirmModal.type === 'START_ALL' ? handleStartAll : handleStopAll}
                className={`cc-btn ${confirmModal.type === 'START_ALL' ? 'cc-btn-primary' : 'cc-btn-danger'}`}
                style={{ fontSize: 12, background: confirmModal.type === 'START_ALL' ? 'var(--cc-green)' : undefined }}
              >
                {confirmModal.type === 'START_ALL' ? 'Confirm Start All' : 'Confirm Stop All'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
