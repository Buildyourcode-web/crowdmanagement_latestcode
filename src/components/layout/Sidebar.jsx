import { useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAppStore } from "../../store/useAppStore.js";
import { useAlertStore } from "../../store/useAlertStore.js";
import { EVENT_CONFIG } from "../../config/eventConfig.js";

const NAV_GROUPS = [
  {
    label: "Overview",
    items: [
      { path: "/dashboard", icon: "bi-grid-fill", label: "Dashboard" },
    ],
  },
  {
    label: "AI Intelligence",
    items: [
      { path: "/cameras", icon: "bi-camera-video-fill", label: "Cameras", alertKey: "cameras" },
      { path: "/crowd", icon: "bi-people-fill", label: "Crowd" },
      { path: "/queue", icon: "bi-segmented-nav", label: "Queue" },
      { path: "/zones", icon: "bi-hexagon-fill", label: "Zones" },
      { path: "/predictions", icon: "bi-graph-up-arrow", label: "Predictions" },
    ],
  },
  {
    label: "Security",
    items: [
      { path: "/frs", icon: "bi-person-bounding-box", label: "FRS" },
      { path: "/missing-persons", icon: "bi-person-exclamation", label: "Missing Persons" },
      { path: "/alerts", icon: "bi-exclamation-triangle-fill", label: "Alerts", alertKey: "alerts" },
      { path: "/incidents", icon: "bi-shield-exclamation", label: "Incidents" },
    ],
  },
  {
    label: "Operations",
    items: [
      // { path: "/operations", icon: "bi-diagram-3-fill", label: "Operations" },
      { path: "/analytics", icon: "bi-bar-chart-fill", label: "Analytics" },
      { path: "/reports", icon: "bi-file-earmark-text-fill", label: "Reports" },
    ],
  },
  {
    label: "System",
    items: [
      { path: "/system-health", icon: "bi-cpu-fill", label: "System Health" },
      { path: "/ai-deployment", icon: "bi-robot", label: "AI Deployment" },
      { path: "/settings", icon: "bi-gear-fill", label: "Settings" },
    ],
  },
];

export default function Sidebar() {
  const navigate = useNavigate();
  const collapsed = useAppStore((s) => s.sidebarCollapsed);
  const logout = useAppStore((s) => s.logout);
  const { criticalCount } = useAlertStore();
  const location = useLocation();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <aside className={`cc-sidebar${collapsed ? " collapsed" : ""}`}>
      <nav className="cc-sidebar-nav">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="cc-nav-group">
            {!collapsed && (
              <div className="cc-nav-group-label">{group.label}</div>
            )}
            {group.items.map((item) => {
              const isActive = location.pathname === item.path ||
                (item.path !== "/dashboard" && location.pathname.startsWith(item.path));
              const showBadge = item.alertKey === "alerts" && criticalCount > 0;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={`cc-nav-item${isActive ? " active" : ""}`}
                  title={collapsed ? item.label : ""}
                >
                  <i className={`bi ${item.icon}`} />
                  {!collapsed && <span>{item.label}</span>}
                  {!collapsed && showBadge && (
                    <span className="cc-nav-badge">{criticalCount}</span>
                  )}
                </NavLink>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="cc-sidebar-footer" style={{ display: "flex", flexDirection: "column", gap: 10, padding: collapsed ? "10px 4px" : "12px 14px" }}>
        {!collapsed ? (
          <>
            <div className="cc-sys-status">
              <span className="cc-live-dot" />
              <span>System Online</span>
            </div>
            <button
              onClick={handleLogout}
              className="cc-btn"
              style={{
                width: "100%",
                padding: "6px 12px",
                fontSize: 11,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 6,
                background: "rgba(248,81,73,0.1)",
                borderColor: "rgba(248,81,73,0.3)",
                color: "var(--cc-red)",
                borderRadius: "var(--cc-radius)",
                cursor: "pointer",
                fontWeight: 600,
                transition: "all 0.15s ease",
              }}
              title="Sign out of current session"
            >
              <i className="bi bi-box-arrow-right" />
              <span>Logout</span>
            </button>
          </>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
            <span className="cc-live-dot" title="System Online" />
            <button
              onClick={handleLogout}
              style={{
                background: "rgba(248,81,73,0.12)",
                border: "1px solid rgba(248,81,73,0.3)",
                borderRadius: "var(--cc-radius)",
                color: "var(--cc-red)",
                cursor: "pointer",
                fontSize: 14,
                padding: "6px 8px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
              title="Logout"
            >
              <i className="bi bi-box-arrow-right" />
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
