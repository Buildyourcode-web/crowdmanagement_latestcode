// Crowd Management Service — Real backend aggregation API
import apiClient from "./apiClient.js";

/**
 * Fetches unified crowd management summary from backend.
 * @param {Object} params - { time_range, mode, camera_id, risk_level }
 * @returns {Promise<Object>}
 */
export async function getCrowdManagementSummary(params = {}) {
  const query = {};
  if (params.time_range) query.time_range = params.time_range;
  if (params.mode && params.mode !== "all") query.mode = params.mode;
  if (params.camera_id && params.camera_id !== "all") query.camera_id = params.camera_id;
  if (params.risk_level && params.risk_level !== "all") query.risk_level = params.risk_level;

  const res = await apiClient.get("/api/v1/crowd-management/summary", { params: query });
  return res.data;
}
