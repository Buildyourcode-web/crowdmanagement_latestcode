// System Store
import { create } from "zustand";

export const useSystemStore = create((set) => ({
  cpu: 0,
  ram: 0,
  gpu: 0,
  wsConnections: 0,
  systemStatus: "normal",

  setSystemHealth: (payload) =>
    set({
      cpu: payload.cpu ?? 0,
      ram: payload.ram ?? 0,
      gpu: payload.gpu ?? 0,
    }),
}));
