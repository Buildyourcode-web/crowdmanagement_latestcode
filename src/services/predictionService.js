// Prediction Service — Real backend API
import apiClient from "./apiClient.js";

export async function getPredictions() {
  const res = await apiClient.get("/api/v1/predictions/crowd");
  return res.data;
}

export async function getQueuePredictions() {
  const res = await apiClient.get("/api/v1/predictions/queues");
  return res.data;
}

export async function getZoneRiskPredictions() {
  const res = await apiClient.get("/api/v1/predictions/zones");
  return res.data;
}
