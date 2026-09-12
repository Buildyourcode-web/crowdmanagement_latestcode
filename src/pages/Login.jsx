// Login page — Real backend authentication
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAppStore } from "../store/useAppStore.js";
import { EVENT_CONFIG } from "../config/eventConfig.js";
import axios from "axios";
import { getApiBaseUrl } from "../utils/urlConfig.js";

const API_BASE_URL = getApiBaseUrl();

export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { login, theme, toggleTheme } = useAppStore();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username || !password) { setError("Username and password required"); return; }
    setLoading(true);
    setError("");
    try {
      const res = await axios.post(`${API_BASE_URL}/api/v1/auth/login`, { username, password });
      const data = res.data?.data;
      const accessToken = data.access_token;
      localStorage.setItem("byc_access_token", accessToken);
      localStorage.setItem("byc_refresh_token", data.refresh_token);

      // Fetch current profile
      let profile = { name: username, role: "SUPER_ADMIN", initials: username.slice(0, 2).toUpperCase() };
      try {
        const meRes = await axios.get(`${API_BASE_URL}/api/v1/auth/me`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        const u = meRes.data?.data;
        if (u) {
          profile = {
            name: u.full_name || u.username,
            role: u.role || "SUPER_ADMIN",
            initials: u.initials || (u.full_name || u.username).slice(0, 2).toUpperCase(),
            username: u.username,
            email: u.email,
          };
        }
      } catch (meErr) {
        console.warn("[Login] Could not fetch profile, using defaults:", meErr);
      }

      login(profile);
      navigate("/dashboard");
    } catch (err) {
      const msg = err.response?.data?.message || err.response?.data?.detail || "Invalid credentials. Please try again.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--cc-bg-root)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
        position: "relative",
      }}
    >
      {/* Theme toggle in corner */}
      <button
        onClick={toggleTheme}
        className="cc-btn"
        style={{
          position: "absolute",
          top: 20,
          right: 20,
          zIndex: 10,
          padding: "6px 12px",
          display: "flex",
          alignItems: "center",
          gap: 6,
          fontSize: 12,
        }}
        title={theme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode"}
      >
        <i className={`bi ${theme === "dark" ? "bi-sun-fill" : "bi-moon-stars-fill"}`} style={{ color: theme === "dark" ? "var(--cc-yellow)" : "var(--cc-accent)" }} />
        <span>{theme === "dark" ? "Light Mode" : "Dark Mode"}</span>
      </button>

      {/* Background pattern */}
      <div
        style={{
          position: "fixed", inset: 0, zIndex: 0, pointerEvents: "none",
          backgroundImage: "repeating-linear-gradient(0deg,rgba(255,255,255,0.012) 0px,rgba(255,255,255,0.012) 1px,transparent 1px,transparent 40px),repeating-linear-gradient(90deg,rgba(255,255,255,0.012) 0px,rgba(255,255,255,0.012) 1px,transparent 1px,transparent 40px)",
        }}
      />

      <div style={{ position: "relative", zIndex: 1, width: "100%", maxWidth: 380 }}>
        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: 36 }}>
          <div
            style={{
              width: 56, height: 56, background: "var(--cc-accent)", borderRadius: 8,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 22, fontWeight: 900, color: "#fff", margin: "0 auto 16px",
              letterSpacing: "-0.03em",
            }}
          >
            BYC
          </div>
          <div style={{ fontSize: 16, fontWeight: 700, color: "var(--cc-text-primary)", letterSpacing: "0.03em" }}>
            BYC AI COMMAND CENTER
          </div>
          <div style={{ fontSize: 11, color: "var(--cc-text-muted)", marginTop: 4, letterSpacing: "0.05em" }}>
            {EVENT_CONFIG.name.toUpperCase()} {EVENT_CONFIG.year}
          </div>
          <div style={{ fontSize: 9, color: "var(--cc-red)", fontWeight: 700, marginTop: 6, letterSpacing: "0.06em" }}>
            AUTHORIZED PERSONNEL ONLY
          </div>
        </div>

        {/* Login form */}
        <form
          onSubmit={handleSubmit}
          style={{
            background: "var(--cc-bg-card)",
            border: "1px solid var(--cc-border)",
            borderRadius: "var(--cc-radius-md)",
            padding: "28px 28px",
          }}
        >
          <div style={{ marginBottom: 16 }}>
            <label className="cc-label" style={{ display: "block", marginBottom: 6 }}>Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
              style={{
                width: "100%", padding: "9px 12px", background: "var(--cc-bg-input)",
                border: "1px solid var(--cc-border)", borderRadius: "var(--cc-radius)",
                color: "var(--cc-text-primary)", fontSize: 13, outline: "none",
              }}
              autoComplete="username"
            />
          </div>

          <div style={{ marginBottom: 20 }}>
            <label className="cc-label" style={{ display: "block", marginBottom: 6 }}>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              style={{
                width: "100%", padding: "9px 12px", background: "var(--cc-bg-input)",
                border: "1px solid var(--cc-border)", borderRadius: "var(--cc-radius)",
                color: "var(--cc-text-primary)", fontSize: 13, outline: "none",
              }}
              autoComplete="current-password"
            />
          </div>

          {error && (
            <div style={{ fontSize: 11, color: "var(--cc-red)", marginBottom: 12, padding: "6px 10px", background: "var(--cc-red-dim)", border: "1px solid var(--cc-red-border)", borderRadius: "var(--cc-radius-sm)" }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%", padding: "10px", background: "var(--cc-accent)",
              border: "none", borderRadius: "var(--cc-radius)", color: "#fff",
              fontSize: 13, fontWeight: 700, letterSpacing: "0.05em", cursor: loading ? "wait" : "pointer",
              opacity: loading ? 0.7 : 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
            }}
          >
            {loading ? (
              <>
                <div style={{ width: 14, height: 14, border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "#fff", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
                AUTHENTICATING...
              </>
            ) : (
              <>
                <i className="bi bi-shield-lock-fill" />
                SIGN IN
              </>
            )}
          </button>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </form>

        {/* System status footer */}
        <div style={{ textAlign: "center", marginTop: 20, fontSize: 10 }}>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "var(--cc-text-muted)" }}>
            <span className="cc-live-dot" style={{ width: 6, height: 6 }} />
            System Status: ONLINE
          </div>
          <div style={{ color: "var(--cc-text-muted)", marginTop: 4 }}>
            Authorized Access Only
          </div>
        </div>
      </div>
    </div>
  );
}
