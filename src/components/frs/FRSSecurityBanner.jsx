// FRS Security & Privacy UX Banner
export default function FRSSecurityBanner() {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "8px 14px",
        background: "var(--cc-orange-dim)",
        border: "1px solid var(--cc-orange-border)",
        borderLeft: "3px solid var(--cc-orange)",
        borderRadius: "var(--cc-radius)",
        fontSize: 12,
        color: "var(--cc-orange)",
        gap: 12,
        flexWrap: "wrap",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 600 }}>
        <i className="bi bi-shield-lock-fill" style={{ fontSize: 16 }} />
        <span>
          🔒 <strong>FRS — AUTHORIZED ACCESS ONLY</strong>: Biometric candidate information requires authorized officer access and mandatory human review.
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
            padding: "2px 8px",
            background: "rgba(0,0,0,0.25)",
            border: "1px solid var(--cc-orange-border)",
            borderRadius: "var(--cc-radius-sm)",
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: "0.05em",
          }}
        >
          <i className="bi bi-journal-check" /> AUDIT LOGGED
        </span>
      </div>
    </div>
  );
}
