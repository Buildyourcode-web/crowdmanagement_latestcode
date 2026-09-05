// FRS Detection History page (Section 9 & 17)
import { useEffect, useState, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import FRSSecurityBanner from "../components/frs/FRSSecurityBanner.jsx";
import FRSCandidateReviewModal from "../components/frs/FRSCandidateReviewModal.jsx";
import HDReferenceViewerModal from "../components/frs/HDReferenceViewerModal.jsx";
import { getFRSHistory, getFRSCameras } from "../services/frsService.js";
import { LoadingState } from "../components/common/States.jsx";

const ZONES = ["ALL", "ZONE-A", "ZONE-B", "ZONE-C", "ZONE-D", "ZONE-E", "ZONE-G", "ZONE-H", "ZONE-I", "ZONE-K", "ZONE-L"];
const STATUSES = ["ALL", "PENDING_REVIEW", "POSSIBLE_MATCH", "NOT_A_MATCH", "NEEDS_MORE_REVIEW", "DISMISSED", "CLOSED"];

export default function FRSHistory() {
  const navigate = useNavigate();
  const [history, setHistory] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);

  // Filters
  const [search, setSearch] = useState("");
  const [selectedCamera, setSelectedCamera] = useState("ALL");
  const [selectedZone, setSelectedZone] = useState("ALL");
  const [selectedStatus, setSelectedStatus] = useState("ALL");
  const [minScore, setMinScore] = useState("");

  // Modals
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [hdCandidate, setHdCandidate] = useState(null);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    try {
      const [res, cams] = await Promise.all([
        getFRSHistory({
          search,
          camera: selectedCamera,
          zone: selectedZone,
          status: selectedStatus,
          minScore,
        }),
        getFRSCameras(),
      ]);
      setHistory(Array.isArray(res) ? res : (res?.data || []));
      setCameras(cams);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [search, selectedCamera, selectedZone, selectedStatus, minScore]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const handleReset = () => {
    setSearch("");
    setSelectedCamera("ALL");
    setSelectedZone("ALL");
    setSelectedStatus("ALL");
    setMinScore("");
  };

  return (
    <div className="cc-page">
      <FRSSecurityBanner />

      {/* Page Header */}
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button className="cc-btn" onClick={() => navigate("/frs")} style={{ padding: "4px 8px" }}>
              <i className="bi bi-arrow-left" /> Back to FRS Live
            </button>
            <span>FRS Detection History & Audit Log</span>
          </div>
          <div className="cc-page-subtitle">
            Search, filter, and inspect past biometric candidate detections
          </div>
        </div>

        <div style={{ display: "flex", gap: 6 }}>
          <button className="cc-btn cc-btn-primary" style={{ fontSize: 11 }}>
            <i className="bi bi-download" /> Export Audit Log
          </button>
        </div>
      </div>

      {/* Filter Bar (Section 17) */}
      <div
        className="cc-card"
        style={{
          padding: 12,
          display: "grid",
          gridTemplateColumns: "1.5fr 1fr 1fr 1fr 1fr auto auto",
          gap: 8,
          alignItems: "center",
        }}
      >
        <div style={{ position: "relative" }}>
          <i
            className="bi bi-search"
            style={{ position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", color: "var(--cc-text-muted)", fontSize: 11 }}
          />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search candidate, ref ID, name..."
            style={{
              width: "100%",
              padding: "6px 8px 6px 26px",
              background: "var(--cc-bg-input)",
              border: "1px solid var(--cc-border)",
              borderRadius: "var(--cc-radius)",
              color: "var(--cc-text-primary)",
              fontSize: 11,
              outline: "none",
            }}
          />
        </div>

        <div>
          <select
            value={selectedCamera}
            onChange={(e) => setSelectedCamera(e.target.value)}
            style={{
              width: "100%",
              padding: "6px 8px",
              background: "var(--cc-bg-input)",
              border: "1px solid var(--cc-border)",
              borderRadius: "var(--cc-radius)",
              color: "var(--cc-text-primary)",
              fontSize: 11,
              outline: "none",
            }}
          >
            <option value="ALL">All Cameras</option>
            {cameras.map((c) => (
              <option key={c.id} value={c.id}>{c.id} ({c.name})</option>
            ))}
          </select>
        </div>

        <div>
          <select
            value={selectedZone}
            onChange={(e) => setSelectedZone(e.target.value)}
            style={{
              width: "100%",
              padding: "6px 8px",
              background: "var(--cc-bg-input)",
              border: "1px solid var(--cc-border)",
              borderRadius: "var(--cc-radius)",
              color: "var(--cc-text-primary)",
              fontSize: 11,
              outline: "none",
            }}
          >
            {ZONES.map((z) => (
              <option key={z} value={z}>{z === "ALL" ? "All Zones" : z}</option>
            ))}
          </select>
        </div>

        <div>
          <select
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
            style={{
              width: "100%",
              padding: "6px 8px",
              background: "var(--cc-bg-input)",
              border: "1px solid var(--cc-border)",
              borderRadius: "var(--cc-radius)",
              color: "var(--cc-text-primary)",
              fontSize: 11,
              outline: "none",
            }}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>{s === "ALL" ? "All Statuses" : s.replace(/_/g, " ")}</option>
            ))}
          </select>
        </div>

        <div>
          <select
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
            style={{
              width: "100%",
              padding: "6px 8px",
              background: "var(--cc-bg-input)",
              border: "1px solid var(--cc-border)",
              borderRadius: "var(--cc-radius)",
              color: "var(--cc-text-primary)",
              fontSize: 11,
              outline: "none",
            }}
          >
            <option value="">Any Score</option>
            <option value="90">≥ 90% Match</option>
            <option value="85">≥ 85% Match</option>
            <option value="80">≥ 80% Match</option>
          </select>
        </div>

        <button className="cc-btn cc-btn-primary" onClick={loadHistory} style={{ fontSize: 11 }}>
          <i className="bi bi-funnel-fill" /> Search
        </button>

        <button className="cc-btn" onClick={handleReset} style={{ fontSize: 11 }}>
          Reset
        </button>
      </div>

      {/* History Table (Section 9) */}
      <div className="cc-card" style={{ padding: 0, overflow: "hidden" }}>
        <div className="cc-section-header">
          <div className="cc-section-title">
            Detection Records ({history.length} Matches)
          </div>
          <div style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>
            Click any row to open full candidate review
          </div>
        </div>

        {loading ? (
          <LoadingState message="Loading detection logs..." />
        ) : history.length === 0 ? (
          <div style={{ textAlign: "center", padding: "40px", color: "var(--cc-text-muted)", fontSize: 12 }}>
            No FRS candidate detections match your filter criteria.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="cc-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Detected Face</th>
                  <th>Database Reference</th>
                  <th style={{ textAlign: "center" }}>Match Score</th>
                  <th>Camera</th>
                  <th>Location</th>
                  <th>Status</th>
                  <th style={{ textAlign: "right" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {history.map((row) => {
                  const isPending = row.status === "PENDING_REVIEW";
                  const scoreColor = row.matchScore >= 90 ? "var(--cc-orange)" : "var(--cc-yellow)";

                  return (
                    <tr
                      key={row.id}
                      style={{ cursor: "pointer" }}
                      onClick={() => setSelectedCandidate(row)}
                    >
                      <td style={{ fontFamily: "var(--cc-font-mono)", fontSize: 11, color: "var(--cc-text-primary)", whiteSpace: "nowrap" }}>
                        {row.timeStr}<br />
                        <span style={{ fontSize: 9, color: "var(--cc-text-muted)" }}>{row.dateStr}</span>
                      </td>

                      <td>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <div
                            style={{
                              width: 36,
                              height: 44,
                              background: "#080c14",
                              borderRadius: "var(--cc-radius-sm)",
                              overflow: "hidden",
                              border: "1px solid var(--cc-border)",
                              flexShrink: 0,
                            }}
                          >
                            <img src={row.detectedImage} alt="Crop" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                          </div>
                          <div>
                            <span style={{ fontFamily: "var(--cc-font-mono)", fontSize: 10, color: "var(--cc-text-primary)" }}>{row.id}</span>
                            <div style={{ fontSize: 9, color: "var(--cc-text-muted)" }}>{row.imageQuality}</div>
                          </div>
                        </div>
                      </td>

                      <td>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <div
                            style={{
                              width: 36,
                              height: 44,
                              background: "#080c14",
                              borderRadius: "var(--cc-radius-sm)",
                              overflow: "hidden",
                              border: "1px solid var(--cc-border)",
                              flexShrink: 0,
                            }}
                            onClick={(e) => {
                              e.stopPropagation();
                              setHdCandidate(row);
                            }}
                            title="Inspect HD Reference Photo"
                          >
                            <img src={row.referenceImage} alt="Ref" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                          </div>
                          <div>
                            <div style={{ fontWeight: 600, color: "var(--cc-text-primary)", fontSize: 11 }}>{row.referenceName}</div>
                            <span style={{ fontFamily: "var(--cc-font-mono)", fontSize: 10, color: "var(--cc-accent)" }}>{row.referenceId}</span>
                          </div>
                        </div>
                      </td>

                      <td style={{ textAlign: "center" }}>
                        <div style={{ fontFamily: "var(--cc-font-mono)", fontSize: 14, fontWeight: 700, color: scoreColor }}>
                          {row.matchScore}%
                        </div>
                        <div style={{ width: 60, height: 3, background: "var(--cc-border)", borderRadius: 2, margin: "2px auto 0", overflow: "hidden" }}>
                          <div style={{ width: `${row.matchScore}%`, height: "100%", background: scoreColor }} />
                        </div>
                      </td>

                      <td>
                        <span
                          style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 600, color: "var(--cc-accent)", fontSize: 11 }}
                        >
                          {row.cameraId}
                        </span>
                      </td>

                      <td style={{ fontSize: 11 }}>
                        <div style={{ color: "var(--cc-text-primary)", fontWeight: 500 }}>{row.location}</div>
                        <span style={{ color: "var(--cc-text-muted)", fontSize: 10 }}>{row.zone}</span>
                      </td>

                      <td>
                        <span
                          className="cc-badge"
                          style={{
                            fontSize: 9,
                            background: isPending ? "var(--cc-orange-dim)" : "var(--cc-bg-secondary)",
                            color: isPending ? "var(--cc-orange)" : row.status === "DISMISSED" ? "var(--cc-text-muted)" : "var(--cc-green)",
                            borderColor: isPending ? "var(--cc-orange-border)" : "var(--cc-border)",
                          }}
                        >
                          {row.status.replace(/_/g, " ")}
                        </span>
                      </td>

                      <td style={{ textAlign: "right" }}>
                        <button
                          className="cc-btn cc-btn-primary"
                          style={{ fontSize: 10, padding: "3px 10px" }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedCandidate(row);
                          }}
                        >
                          <i className="bi bi-shield-check" /> Review
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

      {/* Review Modal */}
      {selectedCandidate && (
        <FRSCandidateReviewModal
          candidate={selectedCandidate}
          onClose={() => setSelectedCandidate(null)}
          onReviewed={loadHistory}
        />
      )}

      {/* HD Viewer Modal */}
      {hdCandidate && (
        <HDReferenceViewerModal
          candidate={hdCandidate}
          onClose={() => setHdCandidate(null)}
        />
      )}
    </div>
  );
}
