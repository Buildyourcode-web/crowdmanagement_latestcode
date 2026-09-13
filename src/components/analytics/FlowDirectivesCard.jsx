import React from "react";

export default function FlowDirectivesCard({ flowData, loading }) {
  if (loading && !flowData) return null;

  const directives = flowData?.top_directives || [];
  if (directives.length === 0) return null;

  const festStatus = flowData?.festival_status || "OPTIMAL";
  const netRate = flowData?.net_flow_rate_pax_min ?? 0;
  const totalInside = flowData?.total_inside_festival ?? 0;

  const statusColor = {
    CRITICAL: "#f85149",
    CONGESTED: "#d29922",
    MODERATE: "#58a6ff",
    OPTIMAL: "#3fb950",
  }[festStatus] || "#3fb950";

  return (
    <div
      className="cc-card"
      style={{
        marginBottom: 20,
        border: `1px solid ${festStatus === "CRITICAL" ? "rgba(248,81,73,0.5)" : "var(--cc-border)"}`,
        background: "var(--cc-card-bg)",
        position: "relative",
        boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
      }}
    >
      {/* Accent Header Bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 12,
          paddingBottom: 14,
          borderBottom: "1px solid var(--cc-border)",
          marginBottom: 16,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: 8,
              background: `${statusColor}20`,
              border: `1px solid ${statusColor}60`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: statusColor,
              fontSize: 20,
            }}
          >
            <i className="bi bi-compass-fill" />
          </div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ color: "var(--cc-text-primary)" }}>AI Crowd Flow &amp; Clearance Directives</span>
              <span
                style={{
                  fontSize: 11,
                  padding: "3px 10px",
                  borderRadius: 12,
                  background: `${statusColor}22`,
                  color: statusColor,
                  border: `1px solid ${statusColor}66`,
                  fontWeight: 800,
                  textTransform: "uppercase",
                }}
              >
                {festStatus}
              </span>
            </div>
            <div style={{ fontSize: 12, color: "var(--cc-text-muted)", marginTop: 2 }}>
              Ground Directives for Police, Temple Marshals &amp; Security In-Charges
            </div>
          </div>
        </div>

        {/* Live Metrics Pills */}
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <div
            style={{
              background: "var(--cc-bg-secondary)",
              padding: "6px 14px",
              borderRadius: 6,
              border: "1px solid var(--cc-border)",
              textAlign: "right",
            }}
          >
            <div style={{ fontSize: 10, color: "var(--cc-text-muted)", textTransform: "uppercase", fontWeight: 700 }}>Inside Complex</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: "var(--cc-text-primary)", fontFamily: "var(--cc-font-mono)" }}>
              {totalInside} <span style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>pax</span>
            </div>
          </div>

          <div
            style={{
              background: "var(--cc-bg-secondary)",
              padding: "6px 14px",
              borderRadius: 6,
              border: "1px solid var(--cc-border)",
              textAlign: "right",
            }}
          >
            <div style={{ fontSize: 10, color: "var(--cc-text-muted)", textTransform: "uppercase", fontWeight: 700 }}>Net Surge Rate</div>
            <div
              style={{
                fontSize: 16,
                fontWeight: 700,
                color: netRate > 15 ? "#f85149" : netRate > 0 ? "#d29922" : "#3fb950",
                fontFamily: "var(--cc-font-mono)",
              }}
            >
              {netRate > 0 ? `+${netRate}` : netRate} <span style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>/min</span>
            </div>
          </div>
        </div>
      </div>

      {/* Grid of Tactical Action Directives */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: 14,
        }}
      >
        {directives.map((item, idx) => {
          const isCritical = item.priority === "CRITICAL";
          const isWarning = item.priority === "WARNING";
          const borderCol = isCritical
            ? "rgba(248,81,73,0.5)"
            : isWarning
            ? "rgba(210,153,34,0.4)"
            : "var(--cc-border)";
          const bgCol = isCritical
            ? "rgba(248,81,73,0.08)"
            : isWarning
            ? "rgba(210,153,34,0.08)"
            : "var(--cc-bg-secondary)";
          const iconClass = isCritical
            ? "bi-exclamation-octagon-fill text-danger"
            : isWarning
            ? "bi-exclamation-triangle-fill text-warning"
            : "bi-check-circle-fill text-success";

          return (
            <div
              key={item.id || idx}
              style={{
                background: bgCol,
                border: `1px solid ${borderCol}`,
                borderRadius: 8,
                padding: "14px",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                gap: 10,
              }}
            >
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 800,
                      letterSpacing: 0.5,
                      textTransform: "uppercase",
                      color: isCritical ? "#f85149" : isWarning ? "#d29922" : "var(--cc-accent)",
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    <i className={`bi ${iconClass}`} />
                    {item.category.replace("_", " ")}
                  </span>
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      padding: "2px 8px",
                      borderRadius: 4,
                      background: isCritical ? "#f85149" : isWarning ? "#d29922" : "#238636",
                      color: "#fff",
                    }}
                  >
                    {item.priority}
                  </span>
                </div>

                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--cc-text-primary)", marginBottom: 6 }}>
                  {item.title}
                </div>

                <div
                  style={{
                    fontSize: 12,
                    lineHeight: 1.5,
                    color: "var(--cc-text-primary)",
                    background: "var(--cc-card-bg)",
                    padding: "10px 12px",
                    borderRadius: 6,
                    border: "1px solid var(--cc-border)",
                    marginBottom: 8,
                  }}
                >
                  <strong style={{ color: isCritical ? "#f85149" : "var(--cc-accent)" }}>ACTION: </strong>
                  {item.action}
                </div>
              </div>

              <div style={{ fontSize: 11, color: "var(--cc-text-muted)", display: "flex", flexDirection: "column", gap: 3 }}>
                <div>
                  <span style={{ color: "var(--cc-text-secondary)", fontWeight: 600 }}>Location:</span> {item.target_area}
                </div>
                <div>
                  <span style={{ color: "var(--cc-text-secondary)", fontWeight: 600 }}>Impact:</span> {item.impact}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
