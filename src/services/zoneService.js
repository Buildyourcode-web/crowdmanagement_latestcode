// Zone Service — Real backend API
import apiClient from "./apiClient.js";

export async function getZones() {
  const res = await apiClient.get("/api/v1/crowd/zones");
  return res.data;
}

export async function getZoneById(id) {
  const res = await apiClient.get(`/api/v1/zones/${id}`);
  return res.data;
}
