import React from "react";

export default function ZoneFlowMatrix({ flowData, loading }) {
  if (loading && !flowData) return null;

  const primaryCodes = ["ZONE-A", "ZONE-B", "ZONE-C", "ZONE-D"];
  const rawZones = flowData?.zones || [];
  const zones = rawZones.filter((z) => primaryCodes.includes((z.zone_code || "").toUpperCase())).length > 0
    ? rawZones.filter((z) => primaryCodes.includes((z.zone_code || "").toUpperCase()))
    : rawZones.slice(0, 4);

  const queues = flowData?.queues || [];
  const gates = flowData?.gates || [];

  // Don't render anything if there is no real live data
  const hasData = zones.length > 0 || queues.length > 0 || gates.length > 0;
  if (!hasData) return null;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 16, marginBottom: 20 }}>
      {/* ── Left Column: Zone Clearance & Density ── */}
      {zones.length > 0 && (
        <div className="cc-card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div className="cc-section-title" style={{ margin: 0, display: "flex", alignItems: "center", gap: 8 }}>
                <i className="bi bi-bounding-box" style={{ color: "var(--cc-green)" }} />
                <span>Zone Clearance &amp; Capacity Matrix</span>
              </div>
            </div>
            <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 8px", borderRadius: 4, background: "var(--cc-bg-secondary)", border: "1px solid var(--cc-border)", color: "var(--cc-text-secondary)" }}>
              {zones.length} Key Sectors
            </span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {zones.map((z) => {
              const pct = z.density_pct ?? 0;
              const isCritical = z.risk_level === "CRITICAL";
              const isWarning = z.risk_level === "WARNING";
              const barColor = isCritical ? "#f85149" : isWarning ? "#d29922" : "#3fb950";

              return (
                <div
                  key={z.zone_id || z.zone_code}
                  style={{
                    background: isCritical ? "rgba(248,81,73,0.08)" : "var(--cc-bg-secondary)",
                    border: `1px solid ${isCritical ? "rgba(248,81,73,0.5)" : "var(--cc-border)"}`,
                    borderRadius: 6,
                    padding: "12px 14px",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <strong style={{ fontSize: 13, color: "var(--cc-text-primary)" }}>{z.zone_name}</strong>
                      <span style={{ fontSize: 10, color: "var(--cc-text-muted)", fontFamily: "var(--cc-font-mono)", fontWeight: 700 }}>
                        ({z.zone_code})
                      </span>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      {z.clearance_needed && (
                        <span
                          style={{
                            fontSize: 10,
                            fontWeight: 800,
                            padding: "2px 8px",
                            borderRadius: 4,
                            background: isCritical ? "rgba(248,81,73,0.2)" : "rgba(210,153,34,0.2)",
                            color: isCritical ? "#f85149" : "#d29922",
                            border: `1px solid ${isCritical ? "#f85149" : "#d29922"}`,
                          }}
                        >
                          {z.clearance_priority}
                        </span>
                      )}
                      <span style={{ fontSize: 13, fontWeight: 700, fontFamily: "var(--cc-font-mono)", color: barColor }}>
                        {z.current_people ?? z.current_occupancy ?? 0} / {z.capacity} ({pct}%)
                      </span>
                    </div>
                  </div>

                  <div style={{ width: "100%", height: 7, background: "rgba(128,128,128,0.18)", borderRadius: 4, overflow: "hidden", marginBottom: 8 }}>
                    <div
                      style={{
                        width: `${Math.max(2, pct)}%`,
                        height: "100%",
                        background: barColor,
                        transition: "width 0.4s ease",
                        borderRadius: 4,
                      }}
                    />
                  </div>

                  <div style={{ fontSize: 11, color: "var(--cc-text-secondary)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span>{z.recommended_action}</span>
                    {z.marshals_needed > 0 && (
                      <span style={{ fontSize: 10, fontWeight: 800, color: "#d29922", whiteSpace: "nowrap", marginLeft: 8 }}>
                        <i className="bi bi-shield-fill-check" style={{ marginRight: 4 }} />
                        Deploy {z.marshals_needed} Marshals
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Right Column: Queues & Gates ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {/* Queue Health & Bottlenecks */}
        {queues.length > 0 && (
          <div className="cc-card" style={{ flex: 1 }}>
            <div className="cc-section-title" style={{ marginBottom: 4, display: "flex", alignItems: "center", gap: 8 }}>
              <i className="bi bi-people" style={{ color: "#d29922" }} />
              <span>Queue Movement &amp; Bottlenecks</span>
            </div>
            <div style={{ fontSize: 11, color: "var(--cc-text-muted)", marginBottom: 12 }}>
              Real-time queue velocity &amp; diversion intelligence
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {queues.slice(0, 3).map((q) => {
                const isStopped = q.movement_status === "STOPPED";
                const isSlow = q.movement_status === "SLOW";
                const badgeBg = isStopped ? "#f85149" : isSlow ? "#d29922" : "#238636";

                return (
                  <div
                    key={q.queue_id || q.queue_name}
                    style={{
                      background: isStopped ? "rgba(248,81,73,0.08)" : "var(--cc-bg-secondary)",
                      border: `1px solid ${isStopped ? "rgba(248,81,73,0.4)" : "var(--cc-border)"}`,
                      borderRadius: 6,
                      padding: "8px 12px",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                      <span style={{ fontSize: 12, fontWeight: 700, color: "var(--cc-text-primary)" }}>{q.queue_name}</span>
                      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                        <span style={{ fontSize: 11, fontFamily: "var(--cc-font-mono)", color: "var(--cc-text-muted)" }}>
                          ~{q.estimated_wait_min}m wait
                        </span>
                        <span
                          style={{
                            fontSize: 10,
                            fontWeight: 700,
                            padding: "2px 6px",
                            borderRadius: 4,
                            background: badgeBg,
                            color: "#fff",
                          }}
                        >
                          {q.movement_status}
                        </span>
                      </div>
                    </div>

                    <div style={{ fontSize: 11, color: "var(--cc-text-secondary)" }}>
                      {q.directive}
                    </div>

                    {q.diversion_route && (
                      <div
                        style={{
                          marginTop: 4,
                          fontSize: 10,
                          fontWeight: 600,
                          color: "var(--cc-accent)",
                          display: "flex",
                          alignItems: "center",
                          gap: 4,
                        }}
                      >
                        <i className="bi bi-signpost-2-fill" /> Reroute: {q.diversion_route}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Gates Regulation — only shown when real gate data exists */}
        {gates.length > 0 && (
          <div className="cc-card">
            <div className="cc-section-title" style={{ marginBottom: 4, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <i className="bi bi-arrow-left-right" style={{ color: "var(--cc-accent)" }} />
                <span>Gate Regulation</span>
              </div>
              <span style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>
                {gates.length} Gates
              </span>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 220, overflowY: "auto" }}>
              {gates.map((g, idx) => {
                const isEntry = (g.gate_type || "").toUpperCase().includes("ENTRY");
                const isCongested = g.status === "CONGESTED" || g.status === "SLOW";
                return (
                  <div
                    key={g.gate_name || idx}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "6px 10px",
                      borderRadius: 6,
                      background: "var(--cc-bg-secondary)",
                      border: `1px solid ${isCongested ? "rgba(210,153,34,0.4)" : "var(--cc-border)"}`,
                      fontSize: 11,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span
                        style={{
                          fontSize: 9,
                          fontWeight: 800,
                          padding: "2px 6px",
                          borderRadius: 4,
                          background: isEntry ? "rgba(188,140,255,0.18)" : "rgba(88,166,255,0.18)",
                          color: isEntry ? "#bc8cff" : "#58a6ff",
                          border: `1px solid ${isEntry ? "rgba(188,140,255,0.4)" : "rgba(88,166,255,0.4)"}`,
                        }}
                      >
                        {isEntry ? "ENTRY" : "EXIT"}
                      </span>
                      <div>
                        <div style={{ fontWeight: 700, color: "var(--cc-text-primary)" }}>{g.gate_name}</div>
                        <span style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>{g.action}</span>
                      </div>
                    </div>

                    <div style={{ textAlign: "right", whiteSpace: "nowrap", marginLeft: 10 }}>
                      <div style={{ fontFamily: "var(--cc-font-mono)", fontWeight: 700, color: "var(--cc-text-primary)" }}>
                        {g.flow_rate_per_min} <span style={{ fontSize: 9, color: "var(--cc-text-muted)" }}>/min</span>
                      </div>
                      <span
                        style={{
                          fontSize: 9,
                          fontWeight: 700,
                          color: g.status === "FLOWING" ? "#3fb950" : g.status === "SLOW" ? "#d29922" : "#f85149",
                        }}
                      >
                        {g.status}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
