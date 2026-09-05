// Crowd Store — real-time crowd state fed by REST API polling
import { create } from "zustand";

export const useCrowdStore = create((set) => ({
  totalCrowd: 0,
  inflowPerMin: 0,
  outflowPerMin: 0,
  activeQueues: 0,
  occupancy: 0,
  avgQueueWait: 0,
  zones: {},
  lastUpdated: null,

  // Called by AppShell API poll — maps real backend field names
  setCrowdFromAPI: (d) =>
    set({
      totalCrowd: d.currentCrowd ?? d.totalCrowd ?? d.current_crowd ?? 0,
      inflowPerMin: d.inflowPerMin ?? d.inflow_per_min ?? 0,
      outflowPerMin: d.outflowPerMin ?? d.outflow_per_min ?? 0,
      activeQueues: d.activeQueues ?? d.active_queues ?? 0,
      occupancy: d.occupancy ?? 0,
      avgQueueWait: d.avgQueueWait ?? d.avg_queue_wait ?? 0,
      lastUpdated: new Date().toISOString(),
    }),

  // Zone updates from zones API
  setZoneUpdate: (payload) =>
    set((s) => ({
      zones: {
        ...s.zones,
        [payload.zoneId ?? payload.zone_code ?? payload.id]: {
          people: payload.people ?? payload.current_people ?? 0,
          density: payload.density ?? 0,
          inflow: payload.inflow ?? 0,
          outflow: payload.outflow ?? 0,
          updatedAt: payload.updatedAt ?? new Date().toISOString(),
        },
      },
    })),
}));
