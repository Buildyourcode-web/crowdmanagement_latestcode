import { create } from 'zustand';
import * as settingsService from '../services/settingsService.js';

export const useSettingsStore = create((set, get) => ({
  // Data
  eventSettings: null,
  zoneSettings: [],
  cameraSettings: [],
  alertSettings: null,
  roles: [],
  permissions: [],
  notificationSettings: null,
  aiSettings: null,
  frsSettings: null,
  systemSettings: null,
  
  // UI state
  loading: {},
  error: {},
  saved: {},  // { section: true } for save success flash
  
  setLoading: (section, val) => set(s => ({ loading: { ...s.loading, [section]: val } })),
  setError: (section, err) => set(s => ({ error: { ...s.error, [section]: err } })),
  setSaved: (section, val) => set(s => ({ saved: { ...s.saved, [section]: val } })),
  
  // Loaders
  loadEventSettings: async () => {
    set(s => ({ loading: { ...s.loading, event: true }, error: { ...s.error, event: null } }));
    try {
      const data = await settingsService.getEventSettings();
      set({ eventSettings: data || null, loading: { ...get().loading, event: false } });
    } catch (e) {
      set(s => ({ loading: { ...s.loading, event: false }, error: { ...s.error, event: e.message } }));
    }
  },
  
  loadZoneSettings: async () => {
    set(s => ({ loading: { ...s.loading, zones: true } }));
    try {
      const data = await settingsService.getZoneSettings();
      const list = Array.isArray(data) ? data : data?.data ?? [];
      set({ zoneSettings: list, loading: { ...get().loading, zones: false } });
    } catch {
      set(s => ({ loading: { ...s.loading, zones: false } }));
    }
  },
  
  loadCameraSettings: async () => {
    set(s => ({ loading: { ...s.loading, cameras: true } }));
    try {
      const data = await settingsService.getCameraSettings();
      const list = Array.isArray(data) ? data : data?.data ?? [];
      set({ cameraSettings: list, loading: { ...get().loading, cameras: false } });
    } catch {
      set(s => ({ loading: { ...s.loading, cameras: false } }));
    }
  },
  
  loadAlertSettings: async () => {
    set(s => ({ loading: { ...s.loading, alerts: true } }));
    try {
      const data = await settingsService.getAlertSettings();
      set({ alertSettings: data || null, loading: { ...get().loading, alerts: false } });
    } catch {
      set(s => ({ loading: { ...s.loading, alerts: false } }));
    }
  },
  
  loadRoles: async () => {
    set(s => ({ loading: { ...s.loading, roles: true } }));
    try {
      const [roles, perms] = await Promise.all([settingsService.getRoles(), settingsService.getPermissions()]);
      set({
        roles: Array.isArray(roles) ? roles : [],
        permissions: Array.isArray(perms) ? perms : [],
        loading: { ...get().loading, roles: false },
      });
    } catch {
      set(s => ({ loading: { ...s.loading, roles: false } }));
    }
  },
  
  loadNotificationSettings: async () => {
    set(s => ({ loading: { ...s.loading, notifications: true } }));
    try {
      const data = await settingsService.getNotificationSettings();
      set({ notificationSettings: data || null, loading: { ...get().loading, notifications: false } });
    } catch {
      set(s => ({ loading: { ...s.loading, notifications: false } }));
    }
  },
  
  loadAISettings: async () => {
    set(s => ({ loading: { ...s.loading, ai: true } }));
    try {
      const data = await settingsService.getAISettings();
      set({ aiSettings: data || null, loading: { ...get().loading, ai: false } });
    } catch {
      set(s => ({ loading: { ...s.loading, ai: false } }));
    }
  },
  
  loadFRSSettings: async () => {
    set(s => ({ loading: { ...s.loading, frs: true } }));
    try {
      const data = await settingsService.getFRSSettings();
      set({ frsSettings: data || null, loading: { ...get().loading, frs: false } });
    } catch {
      set(s => ({ loading: { ...s.loading, frs: false } }));
    }
  },
  
  loadSystemSettings: async () => {
    set(s => ({ loading: { ...s.loading, system: true } }));
    try {
      const data = await settingsService.getSystemSettings();
      set({ systemSettings: data || null, loading: { ...get().loading, system: false } });
    } catch {
      set(s => ({ loading: { ...s.loading, system: false } }));
    }
  },
}));
