// LoadingState, EmptyState, ErrorState common components

export function LoadingState({ message = "Loading data..." }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "48px 24px", gap: 12 }}>
      <div style={{ width: 32, height: 32, border: "2px solid var(--cc-border)", borderTopColor: "var(--cc-accent)", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
      <span style={{ fontSize: 12, color: "var(--cc-text-muted)" }}>{message}</span>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

export function EmptyState({ icon = "bi-inbox", title = "No data", message = "No records found." }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "48px 24px", gap: 10, opacity: 0.7 }}>
      <i className={`bi ${icon}`} style={{ fontSize: 36, color: "var(--cc-text-muted)" }} />
      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--cc-text-secondary)" }}>{title}</div>
      <div style={{ fontSize: 12, color: "var(--cc-text-muted)", textAlign: "center" }}>{message}</div>
    </div>
  );
}

export function ErrorState({ message = "Failed to load data.", onRetry }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "48px 24px", gap: 10 }}>
      <i className="bi bi-exclamation-triangle-fill" style={{ fontSize: 36, color: "var(--cc-red)" }} />
      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--cc-text-primary)" }}>Error</div>
      <div style={{ fontSize: 12, color: "var(--cc-text-muted)", textAlign: "center" }}>{message}</div>
      {onRetry && (
        <button className="cc-btn" onClick={onRetry}><i className="bi bi-arrow-clockwise" /> Retry</button>
      )}
    </div>
  );
}
