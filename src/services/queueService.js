// Queue Service — Real backend API for Queue AI Real-Time Analytics
import apiClient from "./apiClient.js";

export async function getQueueCameraMetrics(cameraId) {
  const res = await apiClient.get(`/api/v1/queue/cameras/${cameraId}/metrics`);
  return res.data;
}

export const getCameraQueueMetrics = getQueueCameraMetrics;

export async function getQueueZoneMetrics(zoneId) {
  const res = await apiClient.get(`/api/v1/queue/zones/${zoneId}/metrics`);
  return res.data;
}

export async function getQueueStatus() {
  const res = await apiClient.get("/api/v1/queue/status");
  return res.data;
}

export async function getQueueHealth(cameraId = null) {
  const params = cameraId ? { camera_id: cameraId } : {};
  const res = await apiClient.get("/api/v1/queue/health", { params });
  return res.data;
}

export async function startQueuePipeline(cameraId) {
  const res = await apiClient.post(`/api/v1/queue/pipelines/${cameraId}/start`);
  return res.data;
}

export async function stopQueuePipeline(cameraId) {
  const res = await apiClient.post(`/api/v1/queue/pipelines/${cameraId}/stop`);
  return res.data;
}

export async function getQueuePipelineStatus(cameraId) {
  const res = await apiClient.get(`/api/v1/queue/pipelines/${cameraId}/status`);
  return res.data;
}
