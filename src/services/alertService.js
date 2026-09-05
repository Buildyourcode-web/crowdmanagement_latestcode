// Alert Service — Real backend API
import apiClient from "./apiClient.js";

export async function getAlerts(filters = {}) {
  const res = await apiClient.get("/api/v1/alerts", { params: filters });
  return res.data;
}

export async function acknowledgeAlert(id) {
  const res = await apiClient.post(`/api/v1/alerts/${id}/acknowledge`);
  return res.data;
}

export async function resolveAlert(id) {
  const res = await apiClient.post(`/api/v1/alerts/${id}/resolve`);
  return res.data;
}

export async function dismissAlert(id) {
  const res = await apiClient.post(`/api/v1/alerts/${id}/dismiss`);
  return res.data;
}

export async function getAlertStats() {
  const res = await apiClient.get("/api/v1/alerts/stats");
  return res.data;
}
