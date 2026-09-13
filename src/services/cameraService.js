// Camera Service — Real backend API client
import apiClient from "./apiClient.js";

export async function getCameras(filters = {}) {
  const res = await apiClient.get("/api/v1/cameras", { params: filters });
  return res.data;
}

export async function getCameraById(id) {
  const res = await apiClient.get(`/api/v1/cameras/${id}`);
  return res.data;
}

export async function createCamera(payload) {
  const res = await apiClient.post("/api/v1/cameras", payload);
  return res.data;
}

export async function updateCamera(id, payload) {
  const res = await apiClient.patch(`/api/v1/cameras/${id}`, payload);
  return res.data;
}

export async function deleteCamera(id) {
  try {
    const res = await apiClient.delete(`/api/v1/cameras/${id}`);
    return res?.data || res;
  } catch (e) {
    const fallbackRes = await apiClient.delete(`/api/v1/frs-engine/cameras/${id}`);
    return fallbackRes?.data || fallbackRes;
  }
}

export async function toggleCameraStatus(id, enabled = null) {
  const params = enabled !== null ? { enabled } : {};
  const res = await apiClient.patch(`/api/v1/cameras/${id}/toggle-status`, null, { params });
  return res.data;
}

export async function toggleCameraFRS(id, enabled = null) {
  const params = enabled !== null ? { enabled } : {};
  try {
    const res = await apiClient.patch(`/api/v1/cameras/${id}/toggle-frs`, null, { params });
    return res.data;
  } catch (e) {
    const fallbackRes = await apiClient.patch(`/api/v1/frs-engine/cameras/${id}/toggle-frs`, null, { params });
    return fallbackRes.data;
  }
}

export async function testCameraStream(id, timeoutSec = 6.0) {
  const res = await apiClient.post(`/api/v1/cameras/${id}/test-stream`, null, {
    params: { timeout_sec: timeoutSec },
  });
  return res.data;
}

export async function testAdHocStream(payload) {
  const res = await apiClient.post("/api/v1/cameras/test-stream", payload);
  return res.data;
}

export async function getCameraStats() {
  const res = await apiClient.get("/api/v1/cameras/stats");
  return res.data;
}

export async function getCameraHealth(id) {
  const res = await apiClient.get(`/api/v1/cameras/${id}/health`);
  return res.data;
}

export async function getCameraEvents(id) {
  const res = await apiClient.get(`/api/v1/cameras/${id}/events`);
  return res.data;
}

export async function bulkValidateCameras(rows) {
  const res = await apiClient.post("/api/v1/cameras/bulk-validate", rows);
  return res.data;
}

export async function bulkImportCameras(cameras) {
  const res = await apiClient.post("/api/v1/cameras/bulk-import", { cameras });
  return res.data;
}

export async function getZones() {
  const res = await apiClient.get("/api/v1/zones");
  return res.data;
}
