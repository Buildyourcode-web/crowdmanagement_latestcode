// API Client — Real backend integration
import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

// Request interceptor — attach JWT access token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("byc_access_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor — auto-refresh token on 401, clear session on failure
let isRefreshing = false;
let pendingQueue = [];

const processQueue = (error, token = null) => {
  pendingQueue.forEach((p) => (error ? p.reject(error) : p.resolve(token)));
  pendingQueue = [];
};

apiClient.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) =>
          pendingQueue.push({ resolve, reject })
        ).then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return apiClient(originalRequest);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      const refreshToken = localStorage.getItem("byc_refresh_token");
      if (!refreshToken) {
        // No refresh token — clear session
        localStorage.removeItem("byc_access_token");
        localStorage.removeItem("byc_refresh_token");
        window.location.href = "/login";
        return Promise.reject(error);
      }

      try {
        const res = await axios.post(`${API_BASE_URL}/api/v1/auth/refresh`, {
          refresh_token: refreshToken,
        });
        const newToken = res.data?.data?.access_token;
        localStorage.setItem("byc_access_token", newToken);
        apiClient.defaults.headers.common.Authorization = `Bearer ${newToken}`;
        processQueue(null, newToken);
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(originalRequest);
      } catch (refreshErr) {
        processQueue(refreshErr, null);
        localStorage.removeItem("byc_access_token");
        localStorage.removeItem("byc_refresh_token");
        window.location.href = "/login";
        return Promise.reject(refreshErr);
      } finally {
        isRefreshing = false;
      }
    }

    // Log other errors
    const msg = error.response?.data?.message || error.message;
    console.error(`[API Error] ${error.response?.status || "Network"}: ${msg}`);
    return Promise.reject(error);
  }
);

// ── Ultra-Fast Client In-Memory Request Cache ───────────────────────────────
// Eliminates loading lag when switching between categories/modules
const cache = new Map();
const inFlight = new Map();
const DEFAULT_CACHE_TTL = 30_000; // 30 seconds

function getCacheKey(url, params) {
  if (!params) return url;
  try {
    const sorted = Object.keys(params).sort().reduce((acc, k) => {
      acc[k] = params[k];
      return acc;
    }, {});
    return `${url}?${JSON.stringify(sorted)}`;
  } catch {
    return `${url}?${JSON.stringify(params)}`;
  }
}

export function invalidateApiCache(prefix = "") {
  if (!prefix) {
    cache.clear();
    return;
  }
  for (const key of cache.keys()) {
    if (key.includes(prefix)) {
      cache.delete(key);
    }
  }
}

// Wrap apiClient.get with cache and deduplication
const rawGet = apiClient.get.bind(apiClient);

apiClient.get = async function (url, config = {}) {
  // If skipCache is explicitly requested, bypass
  if (config.skipCache) {
    return rawGet(url, config);
  }

  const cacheKey = getCacheKey(url, config.params);
  const now = Date.now();
  const cached = cache.get(cacheKey);

  // 1. Cache HIT: Return immediately (0ms instant render!)
  if (cached && (now - cached.timestamp < (config.cacheTtl || DEFAULT_CACHE_TTL))) {
    return structuredClone(cached.data);
  }

  // 2. In-flight Deduplication: If already fetching this URL, share the same promise
  if (inFlight.has(cacheKey)) {
    return inFlight.get(cacheKey);
  }

  // 3. Cache MISS: Fetch from server
  const fetchPromise = rawGet(url, config)
    .then((data) => {
      cache.set(cacheKey, { data: structuredClone(data), timestamp: Date.now() });
      inFlight.delete(cacheKey);
      return data;
    })
    .catch((err) => {
      inFlight.delete(cacheKey);
      // Fallback: If network error or timeout but we have stale cache, return it gracefully
      if (cached) {
        console.warn(`[apiClient] Request failed for ${url}, using stale cached data`);
        return structuredClone(cached.data);
      }
      throw err;
    });

  inFlight.set(cacheKey, fetchPromise);
  return fetchPromise;
};

// Invalidate cache on write operations
const rawPost = apiClient.post.bind(apiClient);
apiClient.post = async function (url, ...args) {
  invalidateApiCache();
  return rawPost(url, ...args);
};

const rawPut = apiClient.put.bind(apiClient);
apiClient.put = async function (url, ...args) {
  invalidateApiCache();
  return rawPut(url, ...args);
};

const rawPatch = apiClient.patch.bind(apiClient);
apiClient.patch = async function (url, ...args) {
  invalidateApiCache();
  return rawPatch(url, ...args);
};

const rawDelete = apiClient.delete.bind(apiClient);
apiClient.delete = async function (url, ...args) {
  invalidateApiCache();
  return rawDelete(url, ...args);
};

export default apiClient;

