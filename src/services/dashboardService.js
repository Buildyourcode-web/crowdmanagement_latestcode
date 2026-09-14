// Dashboard Service — API client for Command Center Dashboard
import apiClient from "./apiClient.js";

/**
 * Fetches unified dashboard summary from backend.
 * @param {string} dateRange - "today", "yesterday", "7days", "festival", "custom"
 * @param {boolean} skipCache
 * @param {number|null} dayNumber - Optional festival day number (1..N)
 * @returns {Promise<Object>}
 */
export async function getDashboardSummary(dateRange = "today", skipCache = false, dayNumber = null) {
  const params = { date_range: dateRange };
  if (dayNumber !== null && dayNumber !== undefined) {
    params.day_number = dayNumber;
  }
  const res = await apiClient.get("/api/v1/dashboard/summary", {
    params,
    skipCache,
  });
  return res?.data || res;
}
