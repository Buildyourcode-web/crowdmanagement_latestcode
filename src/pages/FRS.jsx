// FRS Command Center — Dedicated Facial Recognition System Module
import { useEffect, useState, useCallback, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import FRSSecurityBanner from "../components/frs/FRSSecurityBanner.jsx";
import FRSCandidateCard from "../components/frs/FRSCandidateCard.jsx";
import FRSCameraGrid from "../components/frs/FRSCameraGrid.jsx";
import FRSCandidateReviewModal from "../components/frs/FRSCandidateReviewModal.jsx";
import FRSEnrollmentModal from "../components/frs/FRSEnrollmentModal.jsx";
import { getFRSDashboard, getFRSDetections, getFRSCameras } from "../services/frsService.js";
import { realtimeService } from "../services/realtimeService.js";
import { LoadingState } from "../components/common/States.jsx";

const DEFAULT_KPIS = {
  cameras_online: 0,
  cameras_total: 0,
  detections_today: 0,
  possible_matches: 0,
  pending_review: 0,
  pendingReview: 0,
  watchlist_size: 0,
  watchlistSize: 0,
  activeAlerts: 0,
};

export default function FRS() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("feed");
  const [kpis, setKpis] = useState(null);
  const [detections, setDetections] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [showEnrollModal, setShowEnrollModal] = useState(false);
  const [loading, setLoading] = useState(true);
  const [wsConnected, setWsConnected] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedStatus, setSelectedStatus] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [alertReviewCandidate, setAlertReviewCandidate] = useState(null);

  const loadData = useCallback(async () => {
    try {
      const [dashRes, detRes, camRes] = await Promise.allSettled([
        getFRSDashboard(),
        getFRSDetections({ limit: 50 }),
        getFRSCameras(),
      ]);

      if (dashRes.status === "fulfilled" && dashRes.value) {
        setKpis(dashRes.value);
      }
      if (detRes.status === "fulfilled" && detRes.value) {
        const list = Array.isArray(detRes.value) ? detRes.value : (detRes.value?.data || []);
        setDetections(list);
      }
      if (camRes.status === "fulfilled" && camRes.value) {
        const list = Array.isArray(camRes.value) ? camRes.value : (camRes.value?.cameras || []);
        setCameras(list);
      }
    } catch (e) {
      console.warn("FRS load error:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  // WebSocket live candidate feed via centralized realtimeService
  useEffect(() => {
    const unsubStatus = realtimeService.subscribeStatus((status) => {
      setWsConnected(status === "LIVE DATA" || status === "UPDATING");
    });

    const unsubEvents = realtimeService.subscribe((msg, eventType, payload) => {
      const type = eventType || msg?.type;
      const data = payload || msg?.payload;
      if (type === "frs_candidate" && data) {
        setDetections((prev) => {
          const exists = prev.some((d) => d.id === data.id);
          if (exists) return prev;
          return [data, ...prev].slice(0, 100);
        });
        setKpis((k) => (k ? { ...k, pending_review: (k.pending_review || 0) + 1 } : k));
      }
    });

    return () => {
      unsubStatus();
      unsubEvents();
    };
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) return <LoadingState message="Loading FRS Command Center..." />;

  const filteredDetections = detections.filter((d) => {
    if (statusFilter === "PENDING") return d.status === "PENDING_REVIEW";
    if (statusFilter === "POSSIBLE") return d.status === "POSSIBLE_MATCH";
    if (statusFilter === "DISMISSED") return d.status === "DISMISSED";
    return true;
  });

  const pendingCandidate = detections.find((d) => d.status === "PENDING_REVIEW");

  return (
    <div className="cc-page">
      {/* 1. Security Banner */}
      <FRSSecurityBanner />

      {/* 2. Page Header */}
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span>FRS Command Center</span>
            <span
              style={{
                fontSize: 10,
                padding: "2px 8px",
                background: "var(--cc-blue-dim)",
                border: "1px solid var(--cc-blue-border)",
                borderRadius: "var(--cc-radius-sm)",
                color: "var(--cc-accent)",
                fontWeight: 700,
              }}
            >
              MODULE ISOLATED
            </span>
          </div>
          <div className="cc-page-subtitle">
            Khairatabad Ganesh Festival 2026 Authorized Biometric Investigation Console
          </div>
        </div>

        <div style={{ display: "flex", gap: 6 }}>
          <button
            className="cc-btn cc-btn-primary"
            style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700 }}
            onClick={() => setShowEnrollModal(true)}
          >
            <i className="bi bi-person-plus-fill" /> Enroll Person
          </button>
          <button className="cc-btn" onClick={() => navigate("/frs/history")}>
            <i className="bi bi-clock-history" /> Detection History
          </button>
          <button className="cc-btn" onClick={loadData}>
            <i className="bi bi-arrow-clockwise" /> Refresh
          </button>
        </div>
      </div>

      {/* 3. FRS Dashboard KPIs (Section 10) */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {[
          { label: "FRS CAMERAS", value: `${kpis?.cameras_online ?? kpis?.camerasOnline ?? 0} / ${kpis?.cameras_total ?? kpis?.camerasTotal ?? 0}`, sub: "online", color: "var(--cc-green)", icon: "bi-camera-video-fill" },
          { label: "DETECTIONS TODAY", value: (kpis?.detections_today ?? kpis?.detectionsToday ?? 0).toLocaleString(), sub: "scans", color: "var(--cc-text-primary)", icon: "bi-person-bounding-box" },
          { label: "POSSIBLE MATCHES", value: kpis?.possible_matches ?? kpis?.possibleMatches ?? 0, sub: "requires review", color: "var(--cc-orange)", icon: "bi-exclamation-octagon-fill" },
          { label: "PENDING REVIEW", value: kpis?.pending_review ?? kpis?.pendingReview ?? 0, sub: "urgent queue", color: "var(--cc-red)", icon: "bi-hourglass-top" },
          { label: "DISMISSED", value: kpis?.dismissed ?? 0, sub: "verified non-match", color: "var(--cc-text-muted)", icon: "bi-check2-circle" },
          { label: "ACTIVE CASES", value: kpis?.active_cases ?? kpis?.activeCases ?? 0, sub: "under surveillance", color: "var(--cc-yellow)", icon: "bi-shield-exclamation" },
        ].map((item) => (
          <div key={item.label} className="cc-card" style={{ flex: 1, minWidth: 140 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <div className="cc-label" style={{ marginBottom: 4 }}>{item.label}</div>
                <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 22, fontWeight: 700, color: item.color }}>
                  {item.value}
                </div>
                <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 2 }}>{item.sub}</div>
              </div>
              <i className={`bi ${item.icon}`} style={{ fontSize: 18, color: "var(--cc-text-muted)", opacity: 0.5 }} />
            </div>
          </div>
        ))}
      </div>

      {/* 4. Tab Navigation */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid var(--cc-border)", paddingBottom: 6 }}>
        <div style={{ display: "flex", gap: 6 }}>
          {[
            { id: "feed", label: `Live Candidates Feed (${kpis?.pending_review ?? kpis?.pendingReview ?? 0} Pending)`, icon: "bi-card-list" },
            { id: "cameras", label: `FRS Cameras (${cameras?.length ?? 0})`, icon: "bi-grid-fill" },
          ].map((tab) => (
            <button
              key={tab.id}
              className={`cc-btn${activeTab === tab.id ? " cc-btn-primary" : ""}`}
              style={{ fontSize: 12, padding: "5px 14px" }}
              onClick={() => setActiveTab(tab.id)}
            >
              <i className={`bi ${tab.icon}`} /> {tab.label}
            </button>
          ))}
        </div>

        {activeTab === "feed" && (
          <div style={{ display: "flex", gap: 4 }}>
            {["ALL", "PENDING", "POSSIBLE", "DISMISSED"].map((s) => (
              <button
                key={s}
                className={`cc-btn${statusFilter === s ? " cc-btn-primary" : ""}`}
                style={{ fontSize: 10, padding: "3px 8px" }}
                onClick={() => setStatusFilter(s)}
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 5. Main Content Area */}
      {activeTab === "cameras" ? (
        <div>
          <div className="cc-section-title" style={{ marginBottom: 10 }}>
            Dedicated FRS Camera Surveillance Grid (16 Channels)
          </div>
          <FRSCameraGrid cameras={cameras} />
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 310px", gap: 14, alignItems: "start" }}>
          {/* Left Column: Live Candidate Feed Cards */}
          <div>
            <div className="cc-section-title" style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 6 }}>
              <span className="cc-live-dot" style={{ background: wsConnected ? "var(--cc-green)" : "var(--cc-red)" }} />
              <span>LIVE CANDIDATE DETECTION STREAM</span>
              <span style={{ marginLeft: "auto", fontSize: 10, color: wsConnected ? "var(--cc-green)" : "var(--cc-text-muted)", fontFamily: "var(--cc-font-mono)" }}>
                {wsConnected ? "● LIVE" : "○ RECONNECTING..."}
              </span>
            </div>

            {filteredDetections.length === 0 ? (
              <div className="cc-card" style={{ textAlign: "center", padding: "48px 20px" }}>
                <i className="bi bi-shield-check" style={{ fontSize: 36, color: "var(--cc-green)", display: "block", marginBottom: 8 }} />
                <div style={{ fontSize: 14, fontWeight: 600, color: "var(--cc-text-primary)" }}>No candidates in this queue</div>
                <div style={{ fontSize: 11, color: "var(--cc-text-muted)", marginTop: 4 }}>
                  All detected face crops have been verified or dismissed by review officers.
                </div>
              </div>
            ) : (
              filteredDetections.map((candidate) => (
                <FRSCandidateCard
                  key={candidate.id}
                  candidate={candidate}
                  onReviewUpdated={loadData}
                />
              ))
            )}
          </div>

          {/* Right Column: FRS Dedicated Alert Panel (Section 16) */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {/* Urgent Alert Box */}
            {pendingCandidate && (
              <div
                className="cc-card"
                style={{
                  borderLeft: "3px solid var(--cc-red)",
                  padding: 14,
                  background: "var(--cc-bg-panel)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <span
                    style={{
                      fontSize: 9,
                      fontWeight: 800,
                      letterSpacing: "0.08em",
                      padding: "2px 6px",
                      borderRadius: 2,
                      background: "var(--cc-red-dim)",
                      color: "var(--cc-red)",
                      border: "1px solid var(--cc-red-border)",
                    }}
                  >
                    PRIORITY FRS ALERT
                  </span>
                  <span style={{ fontSize: 10, color: "var(--cc-text-muted)", marginLeft: "auto" }}>
                    {pendingCandidate.timeStr}
                  </span>
                </div>

                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--cc-text-primary)", marginBottom: 4 }}>
                  Possible Watchlist Candidate
                </div>
                <div style={{ fontSize: 11, color: "var(--cc-text-secondary)", marginBottom: 10 }}>
                  Subject matched reference record <strong style={{ color: "var(--cc-accent)" }}>{pendingCandidate.referenceId}</strong>.
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 11, marginBottom: 10 }}>
                  <div>
                    <div className="cc-label">Score</div>
                    <div style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 700, color: "var(--cc-orange)" }}>
                      {pendingCandidate.matchScore}%
                    </div>
                  </div>
                  <div>
                    <div className="cc-label">Camera</div>
                    <div style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 600, color: "var(--cc-text-primary)" }}>
                      {pendingCandidate.cameraId}
                    </div>
                  </div>
                  <div style={{ gridColumn: "1 / -1" }}>
                    <div className="cc-label">Location</div>
                    <div style={{ fontWeight: 600, color: "var(--cc-text-primary)" }}>
                      {pendingCandidate.location}
                    </div>
                  </div>
                </div>

                <div
                  style={{
                    padding: "6px 8px",
                    background: "var(--cc-orange-dim)",
                    border: "1px solid var(--cc-orange-border)",
                    borderRadius: "var(--cc-radius-sm)",
                    fontSize: 10,
                    fontWeight: 700,
                    color: "var(--cc-orange)",
                    marginBottom: 10,
                    textAlign: "center",
                  }}
                >
                  STATUS: PENDING HUMAN REVIEW
                </div>

                <button
                  className="cc-btn cc-btn-primary"
                  style={{ width: "100%", justifyContent: "center", fontSize: 11, fontWeight: 700 }}
                  onClick={() => setAlertReviewCandidate(pendingCandidate)}
                >
                  <i className="bi bi-shield-check" /> REVIEW NOW
                </button>
              </div>
            )}

            {/* Quick Links & Information Box */}
            <div className="cc-card" style={{ padding: 12 }}>
              <div className="cc-section-title" style={{ marginBottom: 8, fontSize: 10 }}>FRS MODULE POLICIES</div>
              <ul style={{ paddingLeft: 16, margin: 0, fontSize: 11, color: "var(--cc-text-secondary)", lineHeight: 1.6 }}>
                <li>All biometric candidate detections require double-blind confirmation.</li>
                <li>Candidate face crops are retained strictly per local regulatory retention policies.</li>
                <li>Biometric embeddings are protected in secure enclave memory.</li>
              </ul>

              <div style={{ marginTop: 12, borderTop: "1px solid var(--cc-border)", paddingTop: 8 }}>
                <Link
                  to="/frs/history"
                  style={{ fontSize: 11, color: "var(--cc-accent)", textDecoration: "none", fontWeight: 600 }}
                >
                  View Complete Historical Audit Log <i className="bi bi-arrow-right" />
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Alert Review Modal */}
      {alertReviewCandidate && (
        <FRSCandidateReviewModal
          candidate={alertReviewCandidate}
          onClose={() => setAlertReviewCandidate(null)}
          onReviewed={loadData}
        />
      )}

      {/* Enroll Person Modal */}
      {showEnrollModal && (
        <FRSEnrollmentModal
          onClose={() => setShowEnrollModal(false)}
          onEnrolled={() => {
            loadData();
          }}
        />
      )}
    </div>
  );
}
