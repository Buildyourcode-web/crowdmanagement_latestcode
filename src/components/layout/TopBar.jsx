import { useEffect, useState, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAppStore } from "../../store/useAppStore.js";
import { useAlertStore } from "../../store/useAlertStore.js";
import { useSystemStore } from "../../store/useSystemStore.js";
import { useEventStore } from "../../store/useEventStore.js";
import { EVENT_CONFIG } from "../../config/eventConfig.js";
import logoBold from "../../assets/LOGO_Bold.png";

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
  const { events, activeEvent, activeEventId, setActiveEvent, fetchEvents, sites, activeSiteId, setActiveSiteId } = useEventStore();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef(null);
  const [eventMenuOpen, setEventMenuOpen] = useState(false);
  const eventMenuRef = useRef(null);
  const [siteMenuOpen, setSiteMenuOpen] = useState(false);
  const siteMenuRef = useRef(null);

  useEffect(() => {
    fetchEvents();
  }, []);

  // Close dropdowns on outside click
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target)) {
        setUserMenuOpen(false);
      }
      if (eventMenuRef.current && !eventMenuRef.current.contains(event.target)) {
        setEventMenuOpen(false);
      }
      if (siteMenuRef.current && !siteMenuRef.current.contains(event.target)) {
        setSiteMenuOpen(false);
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
        <div className="cc-topbar-logo">
          <img src={logoBold} alt="BYC Logo" />
        </div>
        {!sidebarCollapsed && (
          <div className="cc-topbar-brand-text">
            <span className="cc-topbar-brand-name">{activeEvent?.name || EVENT_CONFIG.shortName}</span>
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

      {/* Event & Site Selector in Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: 12 }}>
        {/* Event Dropdown */}
        <div className="dropdown" ref={eventMenuRef} style={{ position: "relative" }}>
          <button
            className="btn btn-sm d-flex align-items-center gap-2"
            style={{
              background: "var(--cc-bg-secondary, rgba(255,255,255,0.05))",
              border: "1px solid var(--cc-border)",
              color: "var(--cc-text-primary)",
              fontSize: 12,
              fontWeight: 600,
              padding: "4px 10px",
              borderRadius: 6,
              cursor: "pointer",
            }}
            type="button"
            onClick={() => setEventMenuOpen((o) => !o)}
          >
            <span className="cc-live-dot" style={{ width: 7, height: 7 }} />
            <span style={{ maxWidth: 160, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {activeEvent?.name || "Select Event"}
            </span>
            <i className={`bi bi-chevron-${eventMenuOpen ? "up" : "down"}`} style={{ fontSize: 10, color: "var(--cc-text-muted)" }} />
          </button>
          {eventMenuOpen && (
            <ul
              className="dropdown-menu dropdown-menu-dark shadow show"
              style={{
                display: "block",
                position: "absolute",
                top: "100%",
                left: 0,
                marginTop: 4,
                background: "var(--cc-card-bg)",
                borderColor: "var(--cc-border)",
                fontSize: 12,
                minWidth: 260,
                zIndex: 1060,
              }}
            >
              <li className="dropdown-header text-muted" style={{ fontSize: 10, letterSpacing: 0.5 }}>
                ACCESSIBLE FESTIVALS & EVENTS
              </li>
              {events.map((evt) => (
                <li key={evt.id}>
                  <button
                    className={`dropdown-item d-flex justify-content-between align-items-center py-2 ${evt.id === activeEventId ? "active" : ""}`}
                    onClick={() => {
                      setActiveEvent(evt);
                      setEventMenuOpen(false);
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600 }}>{evt.name}</div>
                      <small style={{ color: "var(--cc-text-muted)" }}>
                        {evt.code} • {evt.site_count || 0} Sites
                      </small>
                    </div>
                    <span className={`badge ${evt.status === "ACTIVE" || evt.status === "LIVE" ? "bg-success" : "bg-secondary"}`} style={{ fontSize: 9 }}>
                      {evt.status}
                    </span>
                  </button>
                </li>
              ))}
              <li><hr className="dropdown-divider" style={{ borderColor: "var(--cc-border)" }} /></li>
              <li>
                <Link
                  to="/events"
                  className="dropdown-item py-2 text-primary d-flex align-items-center gap-2"
                  onClick={() => setEventMenuOpen(false)}
                >
                  <i className="bi bi-gear" />
                  Manage All Events
                </Link>
              </li>
            </ul>
          )}
        </div>

        {/* Site Dropdown (if active event has sites) */}
        {sites && sites.length > 0 && (
          <div className="dropdown" ref={siteMenuRef} style={{ position: "relative" }}>
            <button
              className="btn btn-sm d-flex align-items-center gap-2"
              style={{
                background: activeSiteId ? "rgba(45, 126, 247, 0.15)" : "var(--cc-bg-secondary, rgba(255,255,255,0.05))",
                border: activeSiteId ? "1px solid var(--cc-accent)" : "1px solid var(--cc-border)",
                color: activeSiteId ? "var(--cc-accent)" : "var(--cc-text-muted)",
                fontSize: 12,
                padding: "4px 10px",
                borderRadius: 6,
                cursor: "pointer",
              }}
              type="button"
              onClick={() => setSiteMenuOpen((o) => !o)}
            >
              <i className="bi bi-geo-alt" style={{ fontSize: 11 }} />
              <span style={{ maxWidth: 120, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {sites.find((s) => s.id === activeSiteId)?.site_name || "All Sites"}
              </span>
              <i className={`bi bi-chevron-${siteMenuOpen ? "up" : "down"}`} style={{ fontSize: 10 }} />
            </button>
            {siteMenuOpen && (
              <ul
                className="dropdown-menu dropdown-menu-dark shadow show"
                style={{
                  display: "block",
                  position: "absolute",
                  top: "100%",
                  left: 0,
                  marginTop: 4,
                  background: "var(--cc-card-bg)",
                  borderColor: "var(--cc-border)",
                  fontSize: 12,
                  minWidth: 200,
                  zIndex: 1060,
                }}
              >
                <li>
                  <button
                    className={`dropdown-item py-2 ${!activeSiteId ? "active" : ""}`}
                    onClick={() => {
                      setActiveSiteId(null);
                      setSiteMenuOpen(false);
                    }}
                  >
                    <i className="bi bi-grid me-2" />
                    All Sites (Full Event)
                  </button>
                </li>
                <li><hr className="dropdown-divider" style={{ borderColor: "var(--cc-border)" }} /></li>
                {sites.map((s) => (
                  <li key={s.id}>
                    <button
                      className={`dropdown-item py-2 ${s.id === activeSiteId ? "active" : ""}`}
                      onClick={() => {
                        setActiveSiteId(s.id);
                        setSiteMenuOpen(false);
                      }}
                    >
                      <div style={{ fontWeight: 600 }}>{s.site_name}</div>
                      <small style={{ color: "var(--cc-text-muted)" }}>{s.site_code}</small>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {/* Center info */}
      <div className="cc-topbar-center">
        <Clock />
        <span style={{ color: "var(--cc-text-muted)", fontSize: 11 }}>
          {new Date().toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}
        </span>
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
