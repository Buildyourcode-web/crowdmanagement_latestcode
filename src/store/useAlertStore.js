// Alert Store — loaded from backend API
import { create } from "zustand";

export const useAlertStore = create((set, get) => ({
  alerts: [],
  criticalCount: 0,
  liveFlash: false,

  setAlerts: (alerts) =>
    set({
      alerts,
      criticalCount: alerts.filter((a) => a.severity === "critical" && !a.acknowledged).length,
    }),

  addAlert: (alert) =>
    set((s) => {
      const alerts = [alert, ...s.alerts];
      return {
        alerts,
        criticalCount: alerts.filter((a) => a.severity === "critical" && !a.acknowledged).length,
        liveFlash: true,
      };
    }),

  acknowledgeAlert: (id) =>
    set((s) => {
      const alerts = s.alerts.map((a) => (a.id === id ? { ...a, acknowledged: true } : a));
      return {
        alerts,
        criticalCount: alerts.filter((a) => a.severity === "critical" && !a.acknowledged).length,
      };
    }),

  clearFlash: () => set({ liveFlash: false }),
}));
