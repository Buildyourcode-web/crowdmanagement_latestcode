// aiService.js — API client for AI capabilities, dynamic capacity, profiles & camera assignments
import apiClient from "./apiClient.js";

/**
 * Fetch full server hardware, GPU, and runtime stack capabilities
 */
export async function getAICapabilities() {
  const res = await apiClient.get("/api/v1/ai/system/capabilities");
  return res.data?.data || res.data || res;
}

/**
 * Fetch dynamic AI capacity calculations and mixed workload projections
 */
export async function getAICapacity(params = {}) {
  const res = await apiClient.get("/api/v1/ai/system/capacity", { params });
  return res.data?.data || res.data || res;
}

/**
 * Pre-flight deployment capacity validator
 */
export async function validateAIDeployment(payload) {
  const res = await apiClient.post("/api/v1/ai/system/capacity/validate", payload);
  return res.data?.data || res.data || res;
}

/**
 * Capture a point-in-time capacity snapshot into the database
 */
export async function createCapacitySnapshot() {
  const res = await apiClient.post("/api/v1/ai/system/capacity/snapshots");
  return res.data?.data || res.data || res;
}

/**
 * Fetch registered standard AI workload profiles
 */
export async function listAIProfiles() {
  const res = await apiClient.get("/api/v1/ai/profiles");
  return res.data?.data || res.data || res;
}

/**
 * Fetch camera AI profile configuration, available compatible profiles, and capacity projection
 */
export async function getCameraAIConfig(cameraId) {
  const res = await apiClient.get(`/api/v1/cameras/${cameraId}/ai-config`);
  return res.data?.data || res.data || res;
}

/**
 * Pre-flight dry-run validation for assigning a profile to a camera
 */
export async function validateCameraAIProfile(cameraId, payload) {
  const res = await apiClient.post(`/api/v1/cameras/${cameraId}/ai-config/validate`, payload);
  return res.data?.data || res.data || res;
}

/**
 * Assign an AI profile to a camera (Configures state only - does NOT start AI inference)
 */
export async function assignCameraAIProfile(cameraId, payload) {
  const res = await apiClient.post(`/api/v1/cameras/${cameraId}/ai-config`, payload);
  return res.data?.data || res.data || res;
}

/**
 * Update an existing camera AI assignment (enable/disable or parameter overrides)
 */
export async function updateCameraAIProfile(cameraId, profileId, payload) {
  const res = await apiClient.patch(`/api/v1/cameras/${cameraId}/ai-config/${profileId}`, payload);
  return res.data?.data || res.data || res;
}

/**
 * Remove an AI profile assignment from a camera
 */
export async function removeCameraAIProfile(cameraId, profileId) {
  const res = await apiClient.delete(`/api/v1/cameras/${cameraId}/ai-config/${profileId}`);
  return res.data?.data || res.data || res;
}

/**
 * Fetch ROI configuration summary and readiness for a camera
 */
export async function getCameraROIConfig(cameraId, profileId = null) {
  const params = profileId ? { profile_id: profileId } : {};
  const res = await apiClient.get(`/api/v1/cameras/${cameraId}/roi-config`, { params });
  return res.data?.data || res.data || res;
}

/**
 * Pre-flight dry-run validation of an ROI geometry
 */
export async function validateCameraROI(cameraId, payload) {
  const res = await apiClient.post(`/api/v1/cameras/${cameraId}/roi-config/validate`, payload);
  return res.data?.data || res.data || res;
}

/**
 * Save new ROI configuration (Configures state only - does NOT start AI inference)
 */
export async function saveCameraROI(cameraId, payload) {
  const res = await apiClient.post(`/api/v1/cameras/${cameraId}/roi-config`, payload);
  return res.data?.data || res.data || res;
}

/**
 * Update existing ROI configuration
 */
export async function updateCameraROI(cameraId, roiId, payload) {
  const res = await apiClient.patch(`/api/v1/cameras/${cameraId}/roi-config/${roiId}`, payload);
  return res.data?.data || res.data || res;
}

/**
 * Delete an ROI configuration
 */
export async function deleteCameraROI(cameraId, roiId) {
  const res = await apiClient.delete(`/api/v1/cameras/${cameraId}/roi-config/${roiId}`);
  return res.data?.data || res.data || res;
}

/**
 * Generates verified snapshot URL for a camera
 */
export function getCameraSnapshotUrl(cameraId) {
  return `/api/v1/cameras/${cameraId}/snapshot?t=${Date.now()}`;
}

// ─── AI Orchestrator API Methods ─────────────────────────────────────────────

/**
 * Lists all camera AI deployments with desired/actual states and metrics
 */
export async function listAIDeployments() {
  const res = await apiClient.get("/api/v1/ai/orchestrator/deployments");
  return res.data?.data || res.data || res;
}

/**
 * Retrieves single deployment details
 */
export async function getAIDeployment(cameraCodeOrId) {
  const res = await apiClient.get(`/api/v1/ai/orchestrator/deployments/${cameraCodeOrId}`);
  return res.data?.data || res.data || res;
}

/**
 * Starts an AI pipeline instance through the orchestrator
 */
export async function startAIPipeline(cameraCodeOrId) {
  const res = await apiClient.post(`/api/v1/ai/orchestrator/pipelines/${cameraCodeOrId}/start`);
  return res.data?.data || res.data || res;
}

/**
 * Stops an AI pipeline instance gracefully
 */
export async function stopAIPipeline(cameraCodeOrId) {
  const res = await apiClient.post(`/api/v1/ai/orchestrator/pipelines/${cameraCodeOrId}/stop`);
  return res.data?.data || res.data || res;
}

/**
 * Restarts an AI pipeline with full resource cleanup and reconnection
 */
export async function restartAIPipeline(cameraCodeOrId) {
  const res = await apiClient.post(`/api/v1/ai/orchestrator/pipelines/${cameraCodeOrId}/restart`);
  return res.data?.data || res.data || res;
}

/**
 * Resource-aware Start All. Prioritizes deployments and halts at capacity limits.
 */
export async function startAllAIPipelines() {
  const res = await apiClient.post("/api/v1/ai/orchestrator/start-all");
  return res.data?.data || res.data || res;
}

/**
 * Gracefully stops all active pipelines across the platform
 */
export async function stopAllAIPipelines() {
  const res = await apiClient.post("/api/v1/ai/orchestrator/stop-all");
  return res.data?.data || res.data || res;
}

/**
 * Returns global orchestrator state counts and active pipelines
 */
export async function getAIOrchestratorStatus() {
  const res = await apiClient.get("/api/v1/ai/orchestrator/status");
  return res.data?.data || res.data || res;
}

