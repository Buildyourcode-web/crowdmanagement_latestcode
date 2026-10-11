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
  const { events, activeEvent, activeEventId, setActiveEvent, fetchEvents, sites, activeSiteId, setActiveSiteId, activeLocationName } = useEventStore();
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
        {activeLocationName && (
          <span
            className="badge bg-primary text-uppercase d-none d-md-inline-flex align-items-center gap-1"
            style={{ fontSize: 11, padding: "5px 8px", fontWeight: 700, letterSpacing: 0.5, borderRadius: 6 }}
            title={`Active Location: ${activeLocationName}`}
          >
            <i className="bi bi-geo-alt-fill" style={{ fontSize: 10 }} />
            {activeLocationName}
          </span>
        )}

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
            <div
              style={{
                display: "block",
                position: "absolute",
                top: "100%",
                left: 0,
                marginTop: 6,
                background: "var(--cc-bg-card)",
                border: "1px solid var(--cc-border)",
                boxShadow: "0 10px 28px rgba(0,0,0,0.35)",
                borderRadius: 8,
                fontSize: 12,
                minWidth: 280,
                zIndex: 1060,
                padding: "6px 0",
              }}
            >
              <div
                style={{
                  fontSize: 10,
                  letterSpacing: 0.5,
                  fontWeight: 700,
                  color: "var(--cc-text-muted)",
                  padding: "6px 14px",
                  textTransform: "uppercase",
                }}
              >
                Accessible Festivals & Events
              </div>
              <div style={{ maxHeight: 320, overflowY: "auto" }}>
                {events.map((evt) => {
                  const isActive = evt.id === activeEventId;
                  return (
                    <button
                      key={evt.id}
                      type="button"
                      style={{
                        width: "100%",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        padding: "8px 14px",
                        background: isActive ? "var(--cc-accent)" : "transparent",
                        color: isActive ? "#ffffff" : "var(--cc-text-primary)",
                        border: "none",
                        textAlign: "left",
                        cursor: "pointer",
                        transition: "background 0.15s ease",
                      }}
                      onMouseEnter={(e) => {
                        if (!isActive) e.currentTarget.style.background = "var(--cc-bg-card-hover)";
                      }}
                      onMouseLeave={(e) => {
                        if (!isActive) e.currentTarget.style.background = "transparent";
                      }}
                      onClick={() => {
                        setActiveEvent(evt);
                        setEventMenuOpen(false);
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 600, color: isActive ? "#ffffff" : "var(--cc-text-primary)" }}>
                          {evt.name}
                        </div>
                        <small style={{ color: isActive ? "rgba(255,255,255,0.8)" : "var(--cc-text-muted)" }}>
                          {evt.code} • {evt.site_count || 0} Sites
                        </small>
                      </div>
                      <span
                        className={`badge ${evt.status === "ACTIVE" || evt.status === "LIVE" ? "bg-success" : "bg-secondary"}`}
                        style={{ fontSize: 9 }}
                      >
                        {evt.status}
                      </span>
                    </button>
                  );
                })}
              </div>
              <div style={{ height: 1, background: "var(--cc-border)", margin: "6px 0" }} />
              <Link
                to="/events"
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "8px 14px",
                  fontSize: 12,
                  color: "var(--cc-accent)",
                  textDecoration: "none",
                  fontWeight: 600,
                }}
                onClick={() => setEventMenuOpen(false)}
              >
                <i className="bi bi-gear" />
                Manage All Events
              </Link>
            </div>
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
              <div
                style={{
                  display: "block",
                  position: "absolute",
                  top: "100%",
                  left: 0,
                  marginTop: 6,
                  background: "var(--cc-bg-card)",
                  border: "1px solid var(--cc-border)",
                  boxShadow: "0 10px 28px rgba(0,0,0,0.35)",
                  borderRadius: 8,
                  fontSize: 12,
                  minWidth: 220,
                  zIndex: 1060,
                  padding: "6px 0",
                }}
              >
                <button
                  type="button"
                  style={{
                    width: "100%",
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "8px 14px",
                    background: !activeSiteId ? "var(--cc-accent)" : "transparent",
                    color: !activeSiteId ? "#ffffff" : "var(--cc-text-primary)",
                    border: "none",
                    textAlign: "left",
                    cursor: "pointer",
                  }}
                  onMouseEnter={(e) => {
                    if (activeSiteId) e.currentTarget.style.background = "var(--cc-bg-card-hover)";
                  }}
                  onMouseLeave={(e) => {
                    if (activeSiteId) e.currentTarget.style.background = "transparent";
                  }}
                  onClick={() => {
                    setActiveSiteId(null);
                    setSiteMenuOpen(false);
                  }}
                >
                  <i className="bi bi-grid" />
                  All Sites (Full Event)
                </button>
                <div style={{ height: 1, background: "var(--cc-border)", margin: "6px 0" }} />
                <div style={{ maxHeight: 280, overflowY: "auto" }}>
                  {sites.map((s) => {
                    const isActive = s.id === activeSiteId;
                    return (
                      <button
                        key={s.id}
                        type="button"
                        style={{
                          width: "100%",
                          display: "flex",
                          flexDirection: "column",
                          padding: "8px 14px",
                          background: isActive ? "var(--cc-accent)" : "transparent",
                          color: isActive ? "#ffffff" : "var(--cc-text-primary)",
                          border: "none",
                          textAlign: "left",
                          cursor: "pointer",
                        }}
                        onMouseEnter={(e) => {
                          if (!isActive) e.currentTarget.style.background = "var(--cc-bg-card-hover)";
                        }}
                        onMouseLeave={(e) => {
                          if (!isActive) e.currentTarget.style.background = "transparent";
                        }}
                        onClick={() => {
                          setActiveSiteId(s.id);
                          setSiteMenuOpen(false);
                        }}
                      >
                        <div style={{ fontWeight: 600, color: isActive ? "#ffffff" : "var(--cc-text-primary)" }}>
                          {s.site_name}
                        </div>
                        <small style={{ color: isActive ? "rgba(255,255,255,0.8)" : "var(--cc-text-muted)" }}>
                          {s.site_code}
                        </small>
                      </button>
                    );
                  })}
                </div>
              </div>
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
