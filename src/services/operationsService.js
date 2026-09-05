// Operations Service — Real backend API
import apiClient from "./apiClient.js";

export async function getPoliceUnits() {
  const res = await apiClient.get("/api/v1/operations/police-units");
  return res.data;
}

export async function getMedicalTeams() {
  const res = await apiClient.get("/api/v1/operations/medical-units");
  return res.data;
}

export async function getEmergencyRoutes() {
  const res = await apiClient.get("/api/v1/operations/emergency-routes");
  return res.data;
}
