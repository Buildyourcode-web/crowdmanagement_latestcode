// StatusBadge — reusable severity/status pill
export default function StatusBadge({ status, label, icon }) {
  const cls = status?.toLowerCase() || "info";
  return (
    <span className={`cc-badge ${cls}`}>
      {icon && <i className={`bi ${icon}`} />}
      {label || status?.toUpperCase()}
    </span>
  );
}
