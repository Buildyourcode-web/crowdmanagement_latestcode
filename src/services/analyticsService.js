// Analytics Service — Real backend API
import apiClient from "./apiClient.js";

export async function getAttendanceAnalytics() {
  const res = await apiClient.get("/api/v1/analytics/attendance");
  return res.data;
}

export async function getIncidentAnalytics() {
  const res = await apiClient.get("/api/v1/analytics/incidents");
  return res.data;
}

export async function getCameraAnalytics() {
  const res = await apiClient.get("/api/v1/analytics/cameras");
  return res.data;
}

export async function getZoneAnalytics() {
  // Zone analytics come from crowd/zones endpoint
  const res = await apiClient.get("/api/v1/crowd/zones");
  const zones = res.data || [];
  const sorted = [...zones].sort((a, b) => (b.occupancy_pct || 0) - (a.occupancy_pct || 0));
  return {
    highestDensity: sorted[0]?.name || "—",
    highestRisk: sorted[0]?.name || "—",
    mostCongested: sorted[0]?.name || "—",
    longestQueue: "—",
  };
}
