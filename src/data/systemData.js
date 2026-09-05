// DEMO DATA ONLY — System health mock data for Khairatabad Ganesh Festival 2026

export const SYSTEM_HEALTH = {
  cameras: { online: 97, total: 100, offline: 3 },
  gpu: {
    units: [
      { id: "GPU-01", label: "NVIDIA A100", utilization: 82, memory: 71, temperature: 68, inferenceMs: 28, status: "healthy" },
      { id: "GPU-02", label: "NVIDIA A100", utilization: 76, memory: 65, temperature: 64, inferenceMs: 32, status: "healthy" },
      { id: "GPU-03", label: "NVIDIA A100", utilization: 91, memory: 84, temperature: 72, inferenceMs: 24, status: "warning" },
      { id: "GPU-04", label: "NVIDIA A100", utilization: 58, memory: 52, temperature: 61, inferenceMs: 38, status: "healthy" },
    ],
    avgUtilization: 76.75,
  },
  cpu: { utilization: 58, cores: 64, threads: 128 },
  ram: { used: 62, total: 256, utilization: 62 },
  database: { status: "healthy", latency: 4, connections: 48, label: "PostgreSQL" },
  redis: { status: "healthy", latency: 1, memory: "4.2 GB", label: "Redis 7" },
  websocket: { status: "healthy", connections: 1842, messagesPerSec: 2850 },
  vpn: { status: "connected", latency: 12, peers: 6, label: "WireGuard VPN" },
  aiEngine: { status: "healthy", fps: 14, detectionsPerSec: 1420, modelsLoaded: 4 },
  frsEngine: { status: "healthy", fps: 14, scansPerSec: 14, camerasActive: 14 },
  network: { bandwidth: "2.4 Gbps", packetLoss: "0.02%", status: "healthy" },
  storage: { used: 3.2, total: 20, unit: "TB", status: "healthy" },
  overallStatus: "warning",
};

export const CAMERA_HEALTH_TABLE = [
  { id: "CAM-KHB-001", zone: "ZONE-A", status: "online", fps: 24, latency: 42, packetLoss: "0.3%", lastSeen: "LIVE" },
  { id: "CAM-KHB-002", zone: "ZONE-A", status: "online", fps: 24, latency: 38, packetLoss: "0.1%", lastSeen: "LIVE" },
  { id: "CAM-KHB-011", zone: "ZONE-B", status: "online", fps: 24, latency: 45, packetLoss: "0.2%", lastSeen: "LIVE" },
  { id: "CAM-KHB-042", zone: "ZONE-E", status: "offline", fps: 0, latency: null, packetLoss: null, lastSeen: "8 min ago" },
  { id: "CAM-KHB-022", zone: "ZONE-C", status: "degraded", fps: 9, latency: 180, packetLoss: "5.2%", lastSeen: "LIVE (degraded)" },
  { id: "CAM-KHB-056", zone: "ZONE-J", status: "online", fps: 24, latency: 41, packetLoss: "0.1%", lastSeen: "LIVE" },
  { id: "CAM-KHB-071", zone: "ZONE-H", status: "online", fps: 24, latency: 44, packetLoss: "0.4%", lastSeen: "LIVE" },
  { id: "CAM-KHB-082", zone: "ZONE-J", status: "offline", fps: 0, latency: null, packetLoss: null, lastSeen: "22 min ago" },
  { id: "CAM-KHB-091", zone: "ZONE-K", status: "online", fps: 24, latency: 39, packetLoss: "0.2%", lastSeen: "LIVE" },
  { id: "FRS-01", zone: "ZONE-A", status: "online", fps: 14, latency: 38, packetLoss: "0.1%", lastSeen: "LIVE" },
  { id: "FRS-15", zone: "ZONE-H", status: "offline", fps: 0, latency: null, packetLoss: null, lastSeen: "15 min ago" },
];

export default SYSTEM_HEALTH;
