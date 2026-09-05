// System Service — Real backend API
import apiClient from "./apiClient.js";

export async function getSystemHealth() {
  const res = await apiClient.get("/api/v1/system/health");
  return res.data;
}

export async function getGpuTelemetry() {
  const res = await apiClient.get("/api/v1/system/gpus");
  return res.data;
}

export async function getServicesStatus() {
  const res = await apiClient.get("/api/v1/system/services");
  return res.data;
}

// Alias for backward compatibility
export async function getCameraHealthTable() {
  const res = await apiClient.get("/api/v1/cameras", { params: { page_size: 100 } });
  const cameras = Array.isArray(res.data) ? res.data : (res.data?.data || []);
  return cameras;
}
