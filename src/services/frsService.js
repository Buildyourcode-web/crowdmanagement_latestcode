// FRS Service — Real backend API
import apiClient from "./apiClient.js";

export async function getFRSDashboard() {
  const res = await apiClient.get("/api/v1/frs/dashboard");
  return res.data;
}

export async function getFRSCameras() {
  const res = await apiClient.get("/api/v1/frs/cameras");
  return res.data;
}

export async function getFRSCamera(id) {
  const [camRes, eventsRes] = await Promise.all([
    apiClient.get(`/api/v1/cameras/${id}`),
    apiClient.get(`/api/v1/frs/cameras/${id}/events`),
  ]);
  return { ...camRes.data, events: eventsRes.data };
}

export async function getFRSDetections(filters = {}) {
  const res = await apiClient.get("/api/v1/frs/candidates", { params: filters });
  return res.data;
}

export async function getFRSDetection(id) {
  const res = await apiClient.get(`/api/v1/frs/candidates/${id}`);
  return res.data;
}

export async function getFRSHistory(filters = {}) {
  const res = await apiClient.get("/api/v1/frs/history", { params: filters });
  return res.data;
}

export async function reviewFRSCandidate(id, decision, notes = "", reason = "") {
  const res = await apiClient.post(`/api/v1/frs/candidates/${id}/review`, {
    decision,
    notes,
    reason,
  });
  return res.data;
}

export async function getFRSFleetStatus() {
  const res = await apiClient.get("/api/v1/frs/status");
  return res.data;
}

export async function getFRSFleetHealth() {
  const res = await apiClient.get("/api/v1/frs/health");
  return res.data;
}

export async function getFRSReferencePersons(filters = {}) {
  const res = await apiClient.get("/api/v1/frs/reference-persons", { params: filters });
  return res.data;
}

export async function enrollFRSReferencePerson(data) {
  const res = await apiClient.post("/api/v1/frs/reference-persons", data);
  return res.data;
}

export async function updateFRSReferencePerson(id, data) {
  const res = await apiClient.patch(`/api/v1/frs/reference-persons/${id}`, data);
  return res.data;
}

export async function deactivateFRSReferencePerson(id) {
  const res = await apiClient.delete(`/api/v1/frs/reference-persons/${id}`);
  return res.data;
}

export async function triggerFRSRetentionCleanup(retentionDays) {
  const res = await apiClient.post("/api/v1/frs/retention/cleanup", null, {
    params: { retention_days: retentionDays },
  });
  return res.data;
}

export async function getFRSConfig() {
  const res = await apiClient.get("/api/v1/frs/config");
  return res.data;
}

export async function updateFRSConfig(data) {
  const res = await apiClient.put("/api/v1/frs/config", data);
  return res.data;
}

export async function getMissingPersons(filters = {}) {
  const res = await apiClient.get("/api/v1/missing-persons", { params: filters });
  return res.data;
}

export async function getMissingPersonById(id) {
  const res = await apiClient.get(`/api/v1/missing-persons/${id}`);
  return res.data;
}

// Backward compatibility aliases
export async function getFRSStats() {
  return getFRSDashboard();
}

export async function getFRSAlerts() {
  const res = await apiClient.get("/api/v1/frs/candidates", { params: { status: "REVIEW_REQUIRED" } });
  return res.data;
}
