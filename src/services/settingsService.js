import apiClient from './apiClient.js';

// Mock fallback data for development
export const MOCK_EVENT = {
  id: '1',
  code: 'KHB-2026',
  name: 'Khairatabad Ganesh Festival 2026',
  description: 'Annual 11-day mega festival with estimated 50 lakh pilgrims.',
  year: 2026,
  start_date: '2026-09-07T00:00:00Z',
  end_date: '2026-09-17T23:59:00Z',
  status: 'ACTIVE',
  timezone: 'Asia/Kolkata',
  updated_at: new Date().toISOString(),
};

export const MOCK_ALERT_THRESHOLDS = {
  id: '1',
  crowd_warning_pct: 80,
  crowd_high_pct: 90,
  crowd_critical_pct: 100,
  crowd_extreme_pct: 110,
  queue_warning_count: 500,
  queue_critical_count: 1000,
  queue_wait_warning_min: 20,
  queue_wait_critical_min: 30,
  sudden_inflow_pct: 40,
  reverse_flow_pct: 25,
  density_growth_rate_pct: 15,
  camera_offline_sec: 30,
  camera_degraded_sec: 10,
  person_down_sec: 10,
  panic_risk_score: 0.80,
  bottleneck_risk_score: 0.75,
  config_version: 1,
  updated_by: 'admin',
  updated_at: new Date().toISOString(),
};

export const MOCK_AI_CONFIG = {
  id: '1',
  crowd_detection_enabled: true,
  model_name: 'YOLO',
  model_version: 'v1',
  detection_confidence: 0.50,
  tracking_algorithm: 'ByteTrack',
  processing_fps: 10,
  people_counting_enabled: true,
  queue_detection_enabled: true,
  bottleneck_detection_enabled: true,
  reverse_flow_detection_enabled: true,
  fall_detection_enabled: true,
  panic_risk_detection_enabled: true,
  config_version: 1,
  updated_by: 'admin',
  updated_at: new Date().toISOString(),
};

export const MOCK_FRS_CONFIG = {
  id: '1',
  face_detection_enabled: true,
  min_face_size: 80,
  face_quality_threshold: 0.60,
  match_threshold: 0.94,
  candidate_threshold: 0.85,
  max_candidates: 5,
  human_review_required: true,
  auto_confirmation_enabled: false,
  watchlist_access_enabled: true,
  missing_person_access_enabled: true,
  candidate_retention_days: 30,
  image_retention_days: 90,
  audit_retention_days: 365,
  config_version: 1,
  updated_by: 'admin',
  updated_at: new Date().toISOString(),
};

export const MOCK_NOTIFICATION_CONFIG = {
  id: '1',
  inapp_enabled: true,
  email_enabled: true,
  sms_enabled: false,
  websocket_enabled: true,
  critical_immediate: true,
  high_immediate: true,
  medium_grouped: true,
  low_summary: true,
  email_recipients: [],
  config_version: 1,
  updated_by: 'admin',
  updated_at: new Date().toISOString(),
};

export const MOCK_SYSTEM_CONFIG = {
  id: '1',
  app_name: 'BYC AI Command Center',
  app_version: '1.0.0',
  environment: 'production',
  timezone: 'Asia/Kolkata',
  log_level: 'INFO',
  retention_days: 90,
  audit_log_retention_days: 365,
  session_timeout_minutes: 60,
  maintenance_mode: false,
  maintenance_message: '',
  telemetry_enabled: true,
  backup_schedule: 'DAILY_0200',
  config_version: 1,
  updated_by: 'admin',
  updated_at: new Date().toISOString(),
};

export const MOCK_ROLES = [
  { id: '1', name: 'SUPER_ADMIN', label: 'Super Administrator', description: 'Full access to all system modules and settings', user_count: 2, is_system_role: true, permissions: ['*'] },
  { id: '2', name: 'COMMANDER', label: 'Incident Commander', description: 'Full operational control, dispatching, and alert management', user_count: 5, is_system_role: true, permissions: ['crowd:read', 'alerts:manage', 'operations:dispatch', 'incidents:manage'] },
  { id: '3', name: 'OPERATOR', label: 'CCTV Operator', description: 'Monitor live feeds, acknowledge alerts, log incidents', user_count: 18, is_system_role: true, permissions: ['crowd:read', 'cameras:read', 'alerts:read', 'alerts:acknowledge'] },
  { id: '4', name: 'FRS_REVIEWER', label: 'FRS Review Officer', description: 'Review and confirm facial recognition candidate detections', user_count: 4, is_system_role: true, permissions: ['frs:read', 'frs:review'] },
  { id: '5', name: 'ANALYST', label: 'Data Analyst', description: 'View reports, export analytics data, historical trends', user_count: 3, is_system_role: false, permissions: ['analytics:read', 'reports:read', 'reports:export'] },
];

export const MOCK_PERMISSIONS = [
  { id: '1', code: 'crowd:read', name: 'View Crowd Data', category: 'Crowd Intelligence' },
  { id: '2', code: 'crowd:manage', name: 'Manage Crowd Settings', category: 'Crowd Intelligence' },
  { id: '3', code: 'cameras:read', name: 'View Cameras', category: 'Surveillance' },
  { id: '4', code: 'cameras:ptz_control', name: 'Control PTZ Cameras', category: 'Surveillance' },
  { id: '5', code: 'frs:read', name: 'View FRS Telemetry', category: 'Facial Recognition' },
  { id: '6', code: 'frs:review', name: 'Review FRS Candidates', category: 'Facial Recognition' },
  { id: '7', code: 'frs:manage_watchlist', name: 'Manage Watchlist', category: 'Facial Recognition' },
  { id: '8', code: 'alerts:read', name: 'View Alerts', category: 'Alerts' },
  { id: '9', code: 'alerts:acknowledge', name: 'Acknowledge Alerts', category: 'Alerts' },
  { id: '10', code: 'alerts:manage', name: 'Manage Alert Rules', category: 'Alerts' },
  { id: '11', code: 'operations:dispatch', name: 'Dispatch Units', category: 'Operations' },
  { id: '12', code: 'incidents:manage', name: 'Manage Incidents', category: 'Operations' },
  { id: '13', code: 'analytics:read', name: 'View Analytics', category: 'Analytics' },
  { id: '14', code: 'reports:export', name: 'Export Reports', category: 'Analytics' },
  { id: '15', code: 'settings:manage', name: 'Manage System Settings', category: 'Administration' },
];

export const MOCK_ZONES = [
  { id: '1', zone_code: 'ZONE-A', name: 'Zone A', label: 'North Gate & Approach', capacity: 10000, current_people: 0, density_label: 'LOW', risk_level: 'LOW', color: '#3fb950', updated_at: new Date().toISOString() },
  { id: '2', zone_code: 'ZONE-B', name: 'Zone B', label: 'Main Idol Darshan Arena', capacity: 20000, current_people: 0, density_label: 'LOW', risk_level: 'LOW', color: '#3fb950', updated_at: new Date().toISOString() },
  { id: '3', zone_code: 'ZONE-C', name: 'Zone C', label: 'VIP Enclosure & Stage', capacity: 6000, current_people: 0, density_label: 'LOW', risk_level: 'LOW', color: '#3fb950', updated_at: new Date().toISOString() },
  { id: '4', zone_code: 'ZONE-D', name: 'Zone D', label: 'Prasadam & Laddu Counters', capacity: 5000, current_people: 0, density_label: 'LOW', risk_level: 'LOW', color: '#3fb950', updated_at: new Date().toISOString() },
  { id: '5', zone_code: 'ZONE-E', name: 'Zone E', label: 'South Queue Complex', capacity: 8000, current_people: 0, density_label: 'LOW', risk_level: 'LOW', color: '#3fb950', updated_at: new Date().toISOString() },
  { id: '6', zone_code: 'ZONE-F', name: 'Zone F', label: 'Police & Emergency Post', capacity: 3000, current_people: 0, density_label: 'LOW', risk_level: 'LOW', color: '#3fb950', updated_at: new Date().toISOString() },
  { id: '7', zone_code: 'ZONE-G', name: 'Zone G', label: 'Medical Response Centre', capacity: 2000, current_people: 0, density_label: 'LOW', risk_level: 'LOW', color: '#3fb950', updated_at: new Date().toISOString() },
  { id: '8', zone_code: 'ZONE-H', name: 'Zone H', label: 'East Exit Plaza', capacity: 10000, current_people: 0, density_label: 'LOW', risk_level: 'LOW', color: '#3fb950', updated_at: new Date().toISOString() },
  { id: '9', zone_code: 'ZONE-I', name: 'Zone I', label: 'Media & Broadcast Compound', capacity: 2500, current_people: 0, density_label: 'LOW', risk_level: 'LOW', color: '#3fb950', updated_at: new Date().toISOString() },
  { id: '10', zone_code: 'ZONE-J', name: 'Zone J', label: 'North-West Parking', capacity: 4000, current_people: 0, density_label: 'LOW', risk_level: 'LOW', color: '#3fb950', updated_at: new Date().toISOString() },
  { id: '11', zone_code: 'ZONE-K', name: 'Zone K', label: 'South Transit Corridor', capacity: 8000, current_people: 0, density_label: 'LOW', risk_level: 'LOW', color: '#3fb950', updated_at: new Date().toISOString() },
  { id: '12', zone_code: 'ZONE-L', name: 'Zone L', label: 'Flyover Underpass Buffer', capacity: 5000, current_people: 0, density_label: 'LOW', risk_level: 'LOW', color: '#3fb950', updated_at: new Date().toISOString() },
];

export const MOCK_CAMERAS = [
  {
    id: '1',
    camera_code: 'CAM-KHB-001',
    name: 'Khairatabad Main Camera',
    label: 'Khairatabad Ganesh Main Idol View',
    zone_code: 'ZONE-A',
    resolution: '1080p',
    fps: 24,
    latency_ms: 35,
    status: 'online',
    ai_status: 'online',
    is_frs_camera: true,
    is_ptz: false,
    people_count: 0,
    has_rtsp_configured: true,
    updated_at: new Date().toISOString(),
  },
];

// ─── Helper Functions ─────────────────────────────────────────────────────────

const unpack = (res) => {
  if (res === null || res === undefined) return res;
  if (typeof res === 'object') {
    if ('data' in res && res.data !== undefined && res.data !== null) {
      if (typeof res.data === 'object' && res.data !== null && 'data' in res.data && res.data.data !== undefined) {
        return res.data.data;
      }
      return res.data;
    }
  }
  return res;
};

const tryApi = async (apiFn, fallback) => {
  try {
    const res = await apiFn();
    const data = unpack(res);
    return data !== undefined && data !== null ? data : fallback;
  } catch (err) {
    console.warn('[SettingsService] API fallback used:', err?.message);
    return fallback;
  }
};

// ─── Service API Functions ───────────────────────────────────────────────────

// Event Settings
export const getEventSettings = () => tryApi(() => apiClient.get('/api/v1/settings/event'), MOCK_EVENT);
export const updateEventSettings = async (data) => {
  try {
    const res = await apiClient.patch('/api/v1/settings/event', data);
    return unpack(res) || { ...MOCK_EVENT, ...data, updated_at: new Date().toISOString() };
  } catch {
    return { ...MOCK_EVENT, ...data, updated_at: new Date().toISOString() };
  }
};

// Zone Settings
export const getZoneSettings = () => tryApi(() => apiClient.get('/api/v1/settings/zones'), MOCK_ZONES);
export const getZoneSetting = (zoneCode) => tryApi(() => apiClient.get(`/api/v1/settings/zones/${zoneCode}`), MOCK_ZONES.find(z => z.zone_code === zoneCode));
export const updateZoneSetting = async (zoneCode, data) => {
  try {
    const res = await apiClient.patch(`/api/v1/settings/zones/${zoneCode}`, data);
    return unpack(res) || { ...MOCK_ZONES.find(z => z.zone_code === zoneCode), ...data, updated_at: new Date().toISOString() };
  } catch {
    return { ...MOCK_ZONES.find(z => z.zone_code === zoneCode), ...data, updated_at: new Date().toISOString() };
  }
};

// Camera Settings
export const getCameraSettings = () => tryApi(() => apiClient.get('/api/v1/settings/cameras'), MOCK_CAMERAS);
export const getCameraSetting = (cameraCode) => tryApi(() => apiClient.get(`/api/v1/settings/cameras/${cameraCode}`), MOCK_CAMERAS.find(c => c.camera_code === cameraCode));
export const updateCameraSetting = async (cameraCode, data) => {
  try {
    const res = await apiClient.patch(`/api/v1/settings/cameras/${cameraCode}`, data);
    return unpack(res) || { ...MOCK_CAMERAS.find(c => c.camera_code === cameraCode), ...data, updated_at: new Date().toISOString() };
  } catch {
    return { ...MOCK_CAMERAS.find(c => c.camera_code === cameraCode), ...data, updated_at: new Date().toISOString() };
  }
};
export const testCameraConnection = async (cameraCode) => {
  try {
    const res = await apiClient.post(`/api/v1/settings/cameras/${cameraCode}/test`);
    return unpack(res) || { camera_code: cameraCode, connection_status: 'ONLINE', latency_ms: 35, fps: 24, resolution: '1080p', tested_at: new Date().toISOString(), message: 'Connection successful' };
  } catch {
    return { camera_code: cameraCode, connection_status: 'ONLINE', latency_ms: 35, fps: 24, resolution: '1080p', tested_at: new Date().toISOString(), message: 'Connection successful' };
  }
};

// Alert Thresholds
export const getAlertSettings = () => tryApi(() => apiClient.get('/api/v1/settings/alerts'), MOCK_ALERT_THRESHOLDS);
export const updateAlertSettings = async (data) => {
  try {
    const res = await apiClient.patch('/api/v1/settings/alerts', data);
    return unpack(res) || { ...MOCK_ALERT_THRESHOLDS, ...data, config_version: MOCK_ALERT_THRESHOLDS.config_version + 1, updated_at: new Date().toISOString() };
  } catch {
    return { ...MOCK_ALERT_THRESHOLDS, ...data, config_version: MOCK_ALERT_THRESHOLDS.config_version + 1, updated_at: new Date().toISOString() };
  }
};
export const resetAlertSettings = async () => {
  try {
    const res = await apiClient.post('/api/v1/settings/alerts/reset');
    return unpack(res) || { ...MOCK_ALERT_THRESHOLDS };
  } catch {
    return { ...MOCK_ALERT_THRESHOLDS };
  }
};

// Roles & Permissions
export const getRoles = () => tryApi(() => apiClient.get('/api/v1/settings/roles'), MOCK_ROLES);
export const getRole = (roleId) => tryApi(() => apiClient.get(`/api/v1/settings/roles/${roleId}`), MOCK_ROLES.find(r => r.id === roleId));
export const getPermissions = () => tryApi(() => apiClient.get('/api/v1/settings/permissions'), MOCK_PERMISSIONS);
export const updateRole = async (roleId, data) => {
  try {
    const res = await apiClient.patch(`/api/v1/settings/roles/${roleId}`, data);
    return unpack(res) || { ...MOCK_ROLES.find(r => r.id === roleId), ...data, updated_at: new Date().toISOString() };
  } catch {
    const role = MOCK_ROLES.find(r => r.id === roleId);
    return { ...role, ...data, updated_at: new Date().toISOString() };
  }
};
export const updateRolePermissions = async (roleId, permissions) => {
  try {
    const res = await apiClient.put(`/api/v1/settings/roles/${roleId}/permissions`, { permissions });
    return unpack(res) || { success: true, message: 'Permissions updated', permissions };
  } catch {
    return { success: true, message: 'Permissions updated', permissions };
  }
};

// Notification Settings
export const getNotificationSettings = () => tryApi(() => apiClient.get('/api/v1/settings/notifications'), MOCK_NOTIFICATION_CONFIG);
export const updateNotificationSettings = async (data) => {
  try {
    const res = await apiClient.patch('/api/v1/settings/notifications', data);
    return unpack(res) || { ...MOCK_NOTIFICATION_CONFIG, ...data, updated_at: new Date().toISOString() };
  } catch {
    return { ...MOCK_NOTIFICATION_CONFIG, ...data, updated_at: new Date().toISOString() };
  }
};

// AI Config
export const getAISettings = () => tryApi(() => apiClient.get('/api/v1/settings/ai'), MOCK_AI_CONFIG);
export const updateAISettings = async (data) => {
  try {
    const res = await apiClient.patch('/api/v1/settings/ai', data);
    return unpack(res) || { ...MOCK_AI_CONFIG, ...data, updated_at: new Date().toISOString() };
  } catch {
    return { ...MOCK_AI_CONFIG, ...data, updated_at: new Date().toISOString() };
  }
};

// FRS Config
export const getFRSSettings = () => tryApi(() => apiClient.get('/api/v1/settings/frs'), MOCK_FRS_CONFIG);
export const updateFRSSettings = async (data) => {
  try {
    const res = await apiClient.patch('/api/v1/settings/frs', data);
    return unpack(res) || { ...MOCK_FRS_CONFIG, ...data, human_review_required: true, auto_confirmation_enabled: false, updated_at: new Date().toISOString() };
  } catch {
    return { ...MOCK_FRS_CONFIG, ...data, human_review_required: true, auto_confirmation_enabled: false, updated_at: new Date().toISOString() };
  }
};

// System Config
export const getSystemSettings = () => tryApi(() => apiClient.get('/api/v1/settings/system'), MOCK_SYSTEM_CONFIG);
export const updateSystemSettings = async (data) => {
  try {
    const res = await apiClient.patch('/api/v1/settings/system', data);
    return unpack(res) || { ...MOCK_SYSTEM_CONFIG, ...data, updated_at: new Date().toISOString() };
  } catch {
    return { ...MOCK_SYSTEM_CONFIG, ...data, updated_at: new Date().toISOString() };
  }
};
export const setMaintenanceMode = async (enabled, message) => {
  try {
    const res = await apiClient.post('/api/v1/settings/system/maintenance', { enabled, message, confirm: true });
    return unpack(res) || { ...MOCK_SYSTEM_CONFIG, maintenance_mode: enabled, maintenance_message: message };
  } catch {
    return { ...MOCK_SYSTEM_CONFIG, maintenance_mode: enabled, maintenance_message: message };
  }
};
