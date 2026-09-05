// KpiCard — Command center metric display card
export default function KpiCard({ label, value, unit, sub, icon, severity, trend, onClick }) {
  const colors = {
    critical: "var(--cc-red)",
    high: "var(--cc-orange)",
    medium: "var(--cc-yellow)",
    low: "var(--cc-green)",
    info: "var(--cc-blue)",
    normal: "var(--cc-text-primary)",
  };
  const color = colors[severity] || colors.normal;

  return (
    <div
      className="cc-card"
      style={{
        cursor: onClick ? "pointer" : "default",
        borderLeft: severity && severity !== "normal" ? `2px solid ${color}` : undefined,
        flex: 1,
        minWidth: 0,
      }}
      onClick={onClick}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="cc-label" style={{ marginBottom: 6 }}>{label}</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
            <span
              style={{
                fontFamily: "var(--cc-font-mono)",
                fontSize: "clamp(18px, 2vw, 26px)",
                fontWeight: 700,
                color,
                lineHeight: 1,
              }}
            >
              {value}
            </span>
            {unit && (
              <span style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>{unit}</span>
            )}
          </div>
          {sub && (
            <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 4 }}>{sub}</div>
          )}
          {trend !== undefined && (
            <div style={{ fontSize: 10, marginTop: 4, color: trend > 0 ? "var(--cc-red)" : "var(--cc-green)", display: "flex", alignItems: "center", gap: 3 }}>
              <i className={`bi bi-arrow-${trend > 0 ? "up" : "down"}-short`} />
              {Math.abs(trend)}/min
            </div>
          )}
        </div>
        {icon && (
          <i className={`bi ${icon}`} style={{ fontSize: 20, color: "var(--cc-text-muted)", opacity: 0.5 }} />
        )}
      </div>
    </div>
  );
}
