// Dashboard Service — API client for Command Center Dashboard
import apiClient from "./apiClient.js";

/**
 * Fetches unified dashboard summary from backend.
 * @param {string} dateRange - "today", "yesterday", "7days", "festival", "custom"
 * @returns {Promise<Object>}
 */
export async function getDashboardSummary(dateRange = "today", skipCache = false) {
  const res = await apiClient.get("/api/v1/dashboard/summary", {
    params: { date_range: dateRange },
    skipCache,
  });
  return res?.data || res;
}
