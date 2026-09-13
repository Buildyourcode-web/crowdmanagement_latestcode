import React, { useEffect, useState, useCallback } from "react";
import { getFestival10DaysAnalytics, downloadFestival10DaysCsv } from "../services/analyticsService.js";
import { LoadingState } from "../components/common/States.jsx";
import { useEventStore } from "../store/useEventStore.js";

export default function Reports() {
  const activeEventId = useEventStore((s) => s.activeEventId);
  const [festData, setFestData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await getFestival10DaysAnalytics(activeEventId);
      setFestData(res?.data || res);
    } catch (err) {
      setError(err.message || "Failed to load festival report");
    } finally {
      setLoading(false);
    }
  }, [activeEventId]);

  useEffect(() => {
    loadData();
  }, [loadData, activeEventId]);

  const handleDownload = async () => {
    try {
      setDownloading(true);
      await downloadFestival10DaysCsv(activeEventId);
    } catch (err) {
      alert("Error exporting CSV: " + err.message);
    } finally {
      setDownloading(false);
    }
  };

  if (loading && !festData) return <LoadingState />;

  const days = festData?.days || [];
  const grandTotal = festData?.grand_total_footfall ?? 0;
  const totalEntries = festData?.total_entries_10days ?? 0;
  const totalExits = festData?.total_exits_10days ?? 0;
  const currentDay = festData?.current_day ?? 1;

  return (
    <div className="cc-page">
      {/* ── Header ── */}
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title">Festival & Operational Reports</div>
          <div className="cc-page-subtitle">
            {festData?.event_name || "Festival Command Center"} — Official {days.length > 0 ? `${days.length}-Day` : "Festival"} Attendance & Gate Flow Audit
          </div>
        </div>

        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <button
            className="cc-btn"
            style={{ fontSize: 12 }}
            onClick={loadData}
            title="Refresh latest count telemetry"
          >
            <i className="bi bi-arrow-clockwise" /> Refresh
          </button>
          <button
            className="cc-btn"
            style={{ fontSize: 12 }}
            onClick={() => window.print()}
            title="Print or export as PDF"
          >
            <i className="bi bi-printer" /> Print / PDF
          </button>
          <button
            className="cc-btn cc-btn-primary"
            style={{ fontSize: 12, fontWeight: 700 }}
            onClick={handleDownload}
            disabled={downloading}
          >
            <i className={`bi ${downloading ? "bi-hourglass-split" : "bi-download"}`} />{" "}
            {downloading ? "Generating CSV..." : `Download ${days.length > 0 ? `${days.length}-Day` : "Festival"} CSV`}
          </button>
        </div>
      </div>

      {/* ── KPI Summary Cards ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, marginBottom: 20 }}>
        <div className="cc-card">
          <div className="cc-label" style={{ marginBottom: 6 }}>
            Grand Total Traffic (Entry + Exit)
          </div>
          <div
            style={{
              fontFamily: "var(--cc-font-mono)",
              fontSize: 26,
              fontWeight: 800,
              color: "var(--cc-accent)",
            }}
          >
            {grandTotal.toLocaleString()}
          </div>
          <div style={{ fontSize: 11, color: "var(--cc-text-muted)", marginTop: 4 }}>
            Formula: Total Entry + Total Exit
          </div>
        </div>

        <div className="cc-card">
          <div className="cc-label" style={{ marginBottom: 6 }}>
            Total Entries (4 Entry Gates)
          </div>
          <div
            style={{
              fontFamily: "var(--cc-font-mono)",
              fontSize: 26,
              fontWeight: 800,
              color: "#3fb950",
            }}
          >
            {totalEntries.toLocaleString()}
          </div>
          <div style={{ fontSize: 11, color: "var(--cc-text-muted)", marginTop: 4 }}>
            Gates EN-01, 02, 03, 04
          </div>
        </div>

        <div className="cc-card">
          <div className="cc-label" style={{ marginBottom: 6 }}>
            Total Exits (4 Exit Gates)
          </div>
          <div
            style={{
              fontFamily: "var(--cc-font-mono)",
              fontSize: 26,
              fontWeight: 800,
              color: "#f85149",
            }}
          >
            {totalExits.toLocaleString()}
          </div>
          <div style={{ fontSize: 11, color: "var(--cc-text-muted)", marginTop: 4 }}>
            Gates EX-01, 02, 03, 04
          </div>
        </div>

        <div className="cc-card">
          <div className="cc-label" style={{ marginBottom: 6 }}>
            Festival Calendar Progress
          </div>
          <div
            style={{
              fontFamily: "var(--cc-font-mono)",
              fontSize: 26,
              fontWeight: 800,
              color: "#d29922",
            }}
          >
            Day {currentDay} of 10
          </div>
          <div style={{ fontSize: 11, color: "var(--cc-text-muted)", marginTop: 4 }}>
            {festData?.start_date} to {festData?.end_date}
          </div>
        </div>
      </div>

      {/* ── 10-Day Festival Day-Wise Attendance Table ── */}
      <div className="cc-card" style={{ marginBottom: 20, overflow: "hidden" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            paddingBottom: 12,
            borderBottom: "1px solid var(--cc-border)",
            marginBottom: 14,
          }}
        >
          <div>
            <div className="cc-section-title" style={{ margin: 0, display: "flex", alignItems: "center", gap: 8 }}>
              <i className="bi bi-calendar3" style={{ color: "var(--cc-accent)" }} />
              <span>{days.length > 0 ? `${days.length}-Day` : "Festival"} Day-Wise Footfall & Attendance</span>
            </div>
            <div style={{ fontSize: 11, color: "var(--cc-text-muted)", marginTop: 2 }}>
              Verified line-crossing counts aggregated across all 4 Entry and 4 Exit AI cameras
            </div>
          </div>

          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <span
              style={{
                fontSize: 11,
                padding: "3px 10px",
                borderRadius: 12,
                background: "var(--cc-bg-secondary)",
                border: "1px solid var(--cc-border)",
                color: "var(--cc-text-secondary)",
                fontWeight: 600,
              }}
            >
              10 Scheduled Festival Days
            </span>
          </div>
        </div>

        {error && (
          <div style={{ padding: 12, background: "rgba(248,81,73,0.1)", border: "1px solid #f85149", borderRadius: 6, color: "#f85149", marginBottom: 14, fontSize: 12 }}>
            <i className="bi bi-exclamation-octagon-fill" style={{ marginRight: 6 }} /> {error}
          </div>
        )}

        <div style={{ overflowX: "auto" }}>
          <table className="cc-table" style={{ width: "100%", textAlign: "left", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--cc-border)", background: "var(--cc-bg-secondary)" }}>
                <th style={{ padding: "10px 14px", fontSize: 11, color: "var(--cc-text-muted)", fontWeight: 700 }}>DAY</th>
                <th style={{ padding: "10px 14px", fontSize: 11, color: "var(--cc-text-muted)", fontWeight: 700 }}>DATE</th>
                <th style={{ padding: "10px 14px", fontSize: 11, color: "var(--cc-text-muted)", fontWeight: 700 }}>DAY OF WEEK</th>
                <th style={{ padding: "10px 14px", fontSize: 11, color: "#3fb950", fontWeight: 700, textAlign: "right" }}>ENTRY (4 GATES)</th>
                <th style={{ padding: "10px 14px", fontSize: 11, color: "#f85149", fontWeight: 700, textAlign: "right" }}>EXIT (4 GATES)</th>
                <th style={{ padding: "10px 14px", fontSize: 11, color: "var(--cc-accent)", fontWeight: 700, textAlign: "right" }}>TOTAL (ENTRY + EXIT)</th>
                <th style={{ padding: "10px 14px", fontSize: 11, color: "var(--cc-text-muted)", fontWeight: 700, textAlign: "right" }}>NET INSIDE</th>
                <th style={{ padding: "10px 14px", fontSize: 11, color: "var(--cc-text-muted)", fontWeight: 700, textAlign: "center" }}>PEAK HOUR</th>
                <th style={{ padding: "10px 14px", fontSize: 11, color: "var(--cc-text-muted)", fontWeight: 700, textAlign: "center" }}>STATUS</th>
              </tr>
            </thead>
            <tbody>
              {days.map((d) => {
                const isToday = d.status === "TODAY";
                const isCompleted = d.status === "COMPLETED";

                return (
                  <tr
                    key={d.day_number}
                    style={{
                      borderBottom: "1px solid var(--cc-border)",
                      background: isToday ? "rgba(188,140,255,0.06)" : "transparent",
                      fontWeight: isToday ? 600 : "normal",
                    }}
                  >
                    <td style={{ padding: "12px 14px", fontSize: 13, fontFamily: "var(--cc-font-mono)", fontWeight: 700 }}>
                      Day {d.day_number}
                    </td>
                    <td style={{ padding: "12px 14px", fontSize: 13, color: "var(--cc-text-primary)" }}>
                      {d.date}
                    </td>
                    <td style={{ padding: "12px 14px", fontSize: 13, color: "var(--cc-text-secondary)" }}>
                      {d.day_name}
                    </td>
                    <td
                      style={{
                        padding: "12px 14px",
                        fontSize: 14,
                        fontFamily: "var(--cc-font-mono)",
                        fontWeight: 700,
                        color: "#3fb950",
                        textAlign: "right",
                      }}
                    >
                      {d.entry_count.toLocaleString()}
                    </td>
                    <td
                      style={{
                        padding: "12px 14px",
                        fontSize: 14,
                        fontFamily: "var(--cc-font-mono)",
                        fontWeight: 700,
                        color: "#f85149",
                        textAlign: "right",
                      }}
                    >
                      {d.exit_count.toLocaleString()}
                    </td>
                    <td
                      style={{
                        padding: "12px 14px",
                        fontSize: 15,
                        fontFamily: "var(--cc-font-mono)",
                        fontWeight: 800,
                        color: "var(--cc-accent)",
                        textAlign: "right",
                      }}
                    >
                      {d.total_count.toLocaleString()}
                    </td>
                    <td
                      style={{
                        padding: "12px 14px",
                        fontSize: 13,
                        fontFamily: "var(--cc-font-mono)",
                        color: "var(--cc-text-secondary)",
                        textAlign: "right",
                      }}
                    >
                      {d.net_inside.toLocaleString()}
                    </td>
                    <td style={{ padding: "12px 14px", fontSize: 12, color: "var(--cc-text-muted)", textAlign: "center" }}>
                      {d.peak_hour}
                    </td>
                    <td style={{ padding: "12px 14px", textAlign: "center" }}>
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 700,
                          padding: "3px 8px",
                          borderRadius: 4,
                          background: isToday
                            ? "rgba(188,140,255,0.2)"
                            : isCompleted
                            ? "rgba(63,185,80,0.15)"
                            : "var(--cc-bg-secondary)",
                          color: isToday ? "var(--cc-accent)" : isCompleted ? "#3fb950" : "var(--cc-text-muted)",
                          border: `1px solid ${isToday ? "var(--cc-accent)" : isCompleted ? "#3fb950" : "var(--cc-border)"}`,
                        }}
                      >
                        {d.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr style={{ background: "var(--cc-bg-secondary)", fontWeight: 800, borderTop: "2px solid var(--cc-border)" }}>
                <td colSpan={3} style={{ padding: "12px 14px", fontSize: 13, color: "var(--cc-text-primary)" }}>
                  TOTAL {days.length > 0 ? `${days.length}-DAY` : "FESTIVAL"} FOOTFALL (INFLOW)
                </td>
                <td style={{ padding: "12px 14px", fontSize: 15, fontFamily: "var(--cc-font-mono)", color: "#3fb950", textAlign: "right" }}>
                  {totalEntries.toLocaleString()}
                </td>
                <td style={{ padding: "12px 14px", fontSize: 15, fontFamily: "var(--cc-font-mono)", color: "#f85149", textAlign: "right" }}>
                  {totalExits.toLocaleString()}
                </td>
                <td style={{ padding: "12px 14px", fontSize: 16, fontFamily: "var(--cc-font-mono)", color: "var(--cc-accent)", textAlign: "right" }}>
                  {grandTotal.toLocaleString()}
                </td>
                <td colSpan={3} style={{ padding: "12px 14px", fontSize: 11, color: "var(--cc-text-muted)", textAlign: "center" }}>
                  Total Footfall = Cumulative Entries
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      {/* ── Secondary Fleet Reports ── */}
      <div className="cc-section-title" style={{ marginBottom: 12 }}>
        Additional Operational & Security Audit Reports
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {[
          {
            icon: "bi-camera-video-fill",
            label: "8-Camera Fleet Telemetry Audit",
            sub: "4 Entry Cameras & 4 Exit Cameras live RTSP stream uptime & line detection status",
            format: "CSV",
            onExport: handleDownload,
          },
          {
            icon: "bi-shield-exclamation",
            label: "Incident & Security Response Audit",
            sub: "All police and marshal dispatches, crowd density alerts, and bottleneck resolutions",
            format: "PDF",
            onExport: () => window.print(),
          },
          {
            icon: "bi-person-bounding-box",
            label: "FRS Watchlist & Compliance Audit",
            sub: "100% human-in-the-loop review compliance verification for authorized personnel",
            format: "PDF",
            onExport: () => window.print(),
          },
        ].map((r) => (
          <div key={r.label} className="cc-card">
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <i className={`bi ${r.icon}`} style={{ fontSize: 20, color: "var(--cc-accent)" }} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--cc-text-primary)" }}>{r.label}</div>
                <div style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>Automated Real-Time Telemetry</div>
              </div>
            </div>
            <div style={{ fontSize: 11, color: "var(--cc-text-secondary)", marginBottom: 14, minHeight: 32 }}>
              {r.sub}
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="cc-btn cc-btn-primary" style={{ fontSize: 11 }} onClick={r.onExport}>
                <i className="bi bi-download" /> Export {r.format}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

