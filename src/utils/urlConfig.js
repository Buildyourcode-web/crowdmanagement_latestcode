// URL Configuration — Dynamic resolution for development & production environments

/**
 * Returns the backend API base URL.
 * 
 * - In production (e.g. EC2 instance or custom domain):
 *   Returns "" (relative path) so all /api/... and /static/... calls route
 *   through Nginx on the current origin (port 80/443). This avoids CORS,
 *   browser loopback blocks, and port firewall timeouts.
 * - In local development (Vite dev server on localhost):
 *   Returns "" (relative path) so requests route through Vite's dev server proxy.
 * - If VITE_API_BASE_URL is explicitly set to a remote URL, uses that.
 */
export function getBackendUrl() {
  const envUrl = (import.meta.env.VITE_API_BASE_URL || "").trim();

  if (typeof window !== "undefined") {
    const hostname = window.location.hostname;
    const isLocal = hostname === "localhost" || hostname === "127.0.0.1";

    // If on a remote host, ignore any accidental localhost config
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
 * Returns the WebSocket endpoint URL with authentication and context query params.
 *
 * The backend uses these params to:
 *  1. Validate the JWT token and identify the user.
 *  2. Place the socket into the correct isolated location/event room.
 *  3. Reject the connection if the token is invalid or context is mismatched.
 *
 * - On production server (e.g. http://13.233.154.239):
 *   Connects to ws://13.233.154.239/ws/v1/events?token=...&... (via Nginx reverse proxy).
 * - On HTTPS server (e.g. https://domain.com):
 *   Connects to wss://domain.com/ws/v1/events?token=...&... (via Nginx reverse proxy).
 * - On local development:
 *   Connects to ws://localhost:5173/ws/v1/events?token=...&... (via Vite proxy).
 */
export function getWsUrl() {
  const configuredWs = (import.meta.env.VITE_WS_URL || "").trim();

  let baseUrl = "";

  if (typeof window !== "undefined") {
    const hostname = window.location.hostname;
    const isLocal = hostname === "localhost" || hostname === "127.0.0.1";

    if (configuredWs && (isLocal || !configuredWs.includes("localhost"))) {
      baseUrl = `${configuredWs.replace(/\/+$/, "")}/ws/v1/events`;
    } else {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      baseUrl = `${protocol}//${window.location.host}/ws/v1/events`;
    }
  }

  if (!baseUrl) return "";

  // Append authentication + context query params for server-side room isolation
  const params = new URLSearchParams();

  try {
    // JWT access token — stored by the auth service on login
    const token =
      localStorage.getItem("byc_access_token") ||
      localStorage.getItem("access_token") ||
      localStorage.getItem("token");
    if (token) params.set("token", token);

    // Active context — set by useEventStore on location/event selection
    const locationId = localStorage.getItem("byc_active_location_id");
    if (locationId) params.set("location_id", locationId);

    const eventId = localStorage.getItem("byc_active_event_id");
    if (eventId) params.set("event_id", eventId);

    const siteId = localStorage.getItem("byc_active_site_id");
    if (siteId) params.set("site_id", siteId);
  } catch (e) {
    // localStorage unavailable (SSR / private mode) — continue without params
  }

  const queryString = params.toString();
  return queryString ? `${baseUrl}?${queryString}` : baseUrl;
}

