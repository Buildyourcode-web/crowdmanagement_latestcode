import { useEffect, useState, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAppStore } from "../../store/useAppStore.js";
import { useAlertStore } from "../../store/useAlertStore.js";
import { useSystemStore } from "../../store/useSystemStore.js";
import { EVENT_CONFIG } from "../../config/eventConfig.js";

function Clock() {
  const [time, setTime] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <span className="cc-topbar-clock">
      {time.toLocaleTimeString("en-IN", { hour12: false, timeZone: "Asia/Kolkata" })}
      <span style={{ color: "var(--cc-text-muted)", marginLeft: 4 }}>IST</span>
    </span>
  );
}

export default function TopBar() {
  const navigate = useNavigate();
  const { sidebarCollapsed, toggleSidebar, toggleFullscreen, user, theme, toggleTheme, logout } = useAppStore();
  const { criticalCount } = useAlertStore();
  const { cpu, gpu } = useSystemStore();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target)) {
        setUserMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const displayName = user?.name || "Officer";
  const displayRole = user?.role || "ADMIN";
  const initials = user?.initials || displayName.slice(0, 2).toUpperCase();

  return (
    <header className="cc-topbar">
      {/* Brand / Logo */}
      <div className={`cc-topbar-brand${sidebarCollapsed ? " collapsed" : ""}`}>
        <div className="cc-topbar-logo">BYC</div>
        {!sidebarCollapsed && (
          <div className="cc-topbar-brand-text">
            <span className="cc-topbar-brand-name">{EVENT_CONFIG.shortName}</span>
            <span className="cc-topbar-brand-sub">BYC AI Command Center</span>
          </div>
        )}
      </div>

      {/* Sidebar toggle */}
      <button
        className="cc-topbar-icon-btn"
        onClick={toggleSidebar}
        title="Toggle Sidebar"
        style={{ flexShrink: 0 }}
      >
        <i className="bi bi-layout-sidebar" style={{ fontSize: 14 }} />
      </button>

      {/* Center info */}
      <div className="cc-topbar-center">
        <div className="cc-event-status">
          <span className="cc-live-dot" />
          <span className="cc-event-status-label">LIVE EVENT ACTIVE</span>
        </div>
        <Clock />
        <span style={{ color: "var(--cc-text-muted)", fontSize: 11 }}>
          {new Date().toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}
        </span>

        {/* System health mini pills */}
        <div style={{ display: "flex", gap: 6, marginLeft: 8 }}>
          <span style={{ fontSize: 10, color: "var(--cc-text-muted)" }}>CPU</span>
          <span style={{ fontSize: 10, fontFamily: "var(--cc-font-mono)", color: cpu > 80 ? "var(--cc-red)" : cpu > 65 ? "var(--cc-yellow)" : "var(--cc-green)" }}>
            {cpu}%
          </span>
          <span style={{ fontSize: 10, color: "var(--cc-text-muted)", marginLeft: 6 }}>GPU</span>
          <span style={{ fontSize: 10, fontFamily: "var(--cc-font-mono)", color: gpu > 90 ? "var(--cc-red)" : gpu > 75 ? "var(--cc-yellow)" : "var(--cc-green)" }}>
            {gpu}%
          </span>
        </div>
      </div>

      {/* Right actions */}
      <div className="cc-topbar-right">
        {/* Critical alert count */}
        {criticalCount > 0 && (
          <Link
            to="/alerts"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "3px 10px",
              background: "var(--cc-red-dim)",
              border: "1px solid var(--cc-red-border)",
              borderRadius: "var(--cc-radius)",
              color: "var(--cc-red)",
              fontSize: 11,
              fontWeight: 700,
              textDecoration: "none",
              animation: "cc-pulse 2s infinite",
            }}
          >
            <i className="bi bi-exclamation-triangle-fill" />
            {criticalCount} CRITICAL
          </Link>
        )}

        <button className="cc-topbar-icon-btn" title="Notifications">
          <i className="bi bi-bell" style={{ fontSize: 14 }} />
          {criticalCount > 0 && <span className="cc-alert-badge">{criticalCount}</span>}
        </button>

        <button
          className="cc-topbar-icon-btn"
          onClick={toggleTheme}
          title={theme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode"}
          style={{
            color: theme === "dark" ? "var(--cc-yellow)" : "var(--cc-accent)",
          }}
        >
          <i className={`bi ${theme === "dark" ? "bi-sun-fill" : "bi-moon-stars-fill"}`} style={{ fontSize: 14 }} />
        </button>

        <button
          className="cc-topbar-icon-btn"
          onClick={toggleFullscreen}
          title="Fullscreen Control Room Mode"
        >
          <i className="bi bi-arrows-fullscreen" style={{ fontSize: 13 }} />
        </button>

        {/* User profile with dropdown */}
        <div style={{ position: "relative" }} ref={userMenuRef}>
          <div
            className="cc-user-avatar"
            onClick={() => setUserMenuOpen((prev) => !prev)}
            title={`${displayName} — ${displayRole} (Click to open menu)`}
            style={{ cursor: "pointer", userSelect: "none" }}
          >
            {initials}
          </div>

          {userMenuOpen && (
            <div
              style={{
                position: "absolute",
                top: "100%",
                right: 0,
                marginTop: 8,
                width: 200,
                background: "var(--cc-bg-card)",
                border: "1px solid var(--cc-border)",
                borderRadius: "var(--cc-radius)",
                boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                padding: "8px 0",
                zIndex: 1000,
              }}
            >
              <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--cc-border)" }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--cc-text-primary)" }}>{displayName}</div>
                <div style={{ fontSize: 10, color: "var(--cc-text-muted)", marginTop: 2 }}>{displayRole}</div>
              </div>
              <Link
                to="/settings"
                onClick={() => setUserMenuOpen(false)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "8px 14px",
                  fontSize: 12,
                  color: "var(--cc-text-secondary)",
                  textDecoration: "none",
                }}
              >
                <i className="bi bi-gear" />
                Settings
              </Link>
              <button
                onClick={handleLogout}
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "8px 14px",
                  fontSize: 12,
                  color: "var(--cc-red)",
                  background: "transparent",
                  border: "none",
                  textAlign: "left",
                  cursor: "pointer",
                }}
              >
                <i className="bi bi-box-arrow-right" />
                Logout
              </button>
            </div>
          )}
        </div>

        {/* Quick direct logout button */}
        <button
          className="cc-topbar-icon-btn"
          onClick={handleLogout}
          title="Logout"
          style={{
            color: "var(--cc-red)",
            marginLeft: 2,
            border: "1px solid var(--cc-red-border, rgba(248,81,73,0.3))",
            background: "rgba(248,81,73,0.08)",
          }}
        >
          <i className="bi bi-box-arrow-right" style={{ fontSize: 14 }} />
        </button>
      </div>
    </header>
  );
}
