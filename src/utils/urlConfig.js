// URL Configuration — Dynamic resolution for development & production environments

/**
 * Returns the backend API base URL.
 * 
 * - When running in production (e.g. EC2 IP 13.233.154.239 or custom domain):
 *   Returns "" (relative path) so all /api/... and /static/... calls route
 *   through Nginx on the current origin (port 80/443). This avoids CORS,
 *   browser loopback blocks, and port 8000 firewall timeouts.
 * - When running in local development (Vite dev server on localhost):
 *   Returns "" (relative path) so requests route through Vite's dev server proxy
 *   (which forwards /api and /static to http://localhost:8000).
 * - If VITE_API_BASE_URL is explicitly set to a non-localhost remote URL, uses that.
 */
export function getBackendUrl() {
  const envUrl = (import.meta.env.VITE_API_BASE_URL || "").trim();

  if (typeof window !== "undefined") {
    const hostname = window.location.hostname;
    const isLocal = hostname === "localhost" || hostname === "127.0.0.1";

    // If we're on a remote host (e.g. AWS EC2), ignore any accidental localhost config
    if (!isLocal && envUrl.includes("localhost")) {
      return "";
    }

    if (envUrl) {
      return envUrl.replace(/\/+$/, "");
    }

    // Default: relative URLs route through Nginx in prod and Vite proxy in dev
    return "";
  }

  return envUrl.replace(/\/+$/, "");
}

export function getApiBaseUrl() {
  return getBackendUrl();
}

/**
 * Returns the WebSocket endpoint URL.
 * 
 * - On production server (e.g. http://13.233.154.239):
 *   Connects to ws://13.233.154.239/ws/v1/events (via Nginx reverse proxy on port 80).
 * - On HTTPS server (e.g. https://domain.com):
 *   Connects to wss://domain.com/ws/v1/events (via Nginx reverse proxy on port 443).
 * - On local development (http://localhost:5173):
 *   Connects to ws://localhost:5173/ws/v1/events (via Vite proxy to localhost:8000).
 */
export function getWsUrl() {
  const configuredWs = (import.meta.env.VITE_WS_URL || "").trim();

  if (typeof window !== "undefined") {
    const hostname = window.location.hostname;
    const isLocal = hostname === "localhost" || hostname === "127.0.0.1";

    if (configuredWs && (isLocal || !configuredWs.includes("localhost"))) {
      return `${configuredWs.replace(/\/+$/, "")}/ws/v1/events`;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    // window.location.host includes hostname and port (e.g. "13.233.154.239" or "localhost:5173")
    return `${protocol}//${window.location.host}/ws/v1/events`;
  }

  return "ws://localhost:8000/ws/v1/events";
}
