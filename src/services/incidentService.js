// Incident Service — Real backend API
import apiClient from "./apiClient.js";

export async function getIncidents(filters = {}) {
  const res = await apiClient.get("/api/v1/incidents", { params: filters });
  return res.data;
}

export async function getIncidentById(id) {
  const res = await apiClient.get(`/api/v1/incidents/${id}`);
  return res.data;
}

export async function acknowledgeIncident(id) {
  const res = await apiClient.post(`/api/v1/incidents/${id}/acknowledge`);
  return res.data;
}

export async function assignIncident(id, assignedTeam, assignedTeamLabel, notes) {
  const res = await apiClient.post(`/api/v1/incidents/${id}/assign`, {
    assigned_team: assignedTeam,
    assigned_team_label: assignedTeamLabel,
    notes,
  });
  return res.data;
}

export async function resolveIncident(id, notes) {
  const res = await apiClient.post(`/api/v1/incidents/${id}/resolve`, { notes });
  return res.data;
}

export async function addIncidentNote(id, content) {
  const res = await apiClient.post(`/api/v1/incidents/${id}/notes`, { content });
  return res.data;
}

// Backward-compat alias
export async function updateIncidentStatus(id, status) {
  if (status === "resolved") return resolveIncident(id);
  if (status === "acknowledged") return acknowledgeIncident(id);
  return { success: true };
}
