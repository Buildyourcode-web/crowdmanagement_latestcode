// Crowd Service — Real backend API
import apiClient from "./apiClient.js";

export async function getCrowdSummary() {
  const res = await apiClient.get("/api/v1/crowd/summary");
  return res.data;
}

export async function getZoneCrowdData() {
  const res = await apiClient.get("/api/v1/crowd/zones");
  return res.data;
}

export async function getCrowdTimeSeries() {
  const res = await apiClient.get("/api/v1/crowd/timeseries");
  return res.data;
}

export async function getQueueData(zone) {
  const params = zone ? { zone } : {};
  const res = await apiClient.get("/api/v1/crowd/queues", { params });
  return res.data;
}

// ── Step 6: Real-Time Crowd AI Telemetry & Pipeline Management ───────────────

export async function getCameraCrowdMetrics(cameraId) {
  const res = await apiClient.get(`/api/v1/crowd/cameras/${cameraId}/metrics`);
  return res.data;
}

export async function getZoneCrowdMetrics(zoneId) {
  const res = await apiClient.get(`/api/v1/crowd/zones/${zoneId}/metrics`);
  return res.data;
}

export async function getCrowdStatus() {
  const res = await apiClient.get("/api/v1/crowd/status");
  return res.data;
}

export async function getCrowdHealth() {
  const res = await apiClient.get("/api/v1/crowd/health");
  return res.data;
}

export async function startCrowdPipeline(cameraId) {
  const res = await apiClient.post(`/api/v1/crowd/pipelines/${cameraId}/start`);
  return res.data;
}

export async function stopCrowdPipeline(cameraId) {
  const res = await apiClient.post(`/api/v1/crowd/pipelines/${cameraId}/stop`);
  return res.data;
}

export async function getCrowdPipelineStatus(cameraId) {
  const res = await apiClient.get(`/api/v1/crowd/pipelines/${cameraId}/status`);
  return res.data;
}
