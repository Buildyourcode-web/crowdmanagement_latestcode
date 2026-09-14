import apiClient from "./apiClient.js";
import { getBackendUrl } from "../utils/urlConfig.js";

export async function getAttendanceAnalytics(dayNumber = null, dateRange = null) {
  const params = {};
  if (dayNumber !== null && dayNumber !== undefined) {
    params.day_number = dayNumber;
  }
  if (dateRange) {
    params.date_range = dateRange;
  }
  const res = await apiClient.get("/api/v1/analytics/attendance", { params });
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

export async function getOperationalFlowAnalytics() {
  const res = await apiClient.get("/api/v1/analytics/operational-flow");
  return res.data;
}

export async function getFestival10DaysAnalytics() {
  const res = await apiClient.get("/api/v1/analytics/festival-10days");
  return res.data;
}

export async function downloadFestival10DaysCsv() {
  const baseURL = getBackendUrl();
  const token = localStorage.getItem("byc_access_token");
  const eventId = localStorage.getItem("byc_active_event_id");
  const headers = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (eventId) headers["X-Event-ID"] = eventId;

  const res = await fetch(`${baseURL}/api/v1/reports/festival-10days/export`, { headers });
  if (!res.ok) throw new Error("Failed to export report");
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `Khairatabad_Ganesh_10Days_Attendance_Report.csv`;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(a);
}


