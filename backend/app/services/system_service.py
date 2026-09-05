import psutil
from app.schemas.system import (
    GPUClusterStatus,
    GPUUnitStatus,
    ServiceStatusItem,
    SystemHealthResponse,
)


class SystemService:
    @staticmethod
    def get_system_health() -> SystemHealthResponse:
        # Real CPU and RAM from psutil
        cpu_pct = round(psutil.cpu_percent(interval=0.1))
        ram_pct = round(psutil.virtual_memory().percent)

        # GPU: not connected yet — show unknown
        gpu_units = []

        return SystemHealthResponse(
            overallStatus="healthy",
            cpu=cpu_pct,
            ram=ram_pct,
            gpu=GPUClusterStatus(units=gpu_units, avgUtilization=0),
            cameras={"total": 0, "online": 0, "degraded": 0, "offline": 0, "avgFps": 0, "avgLatencyMs": 0},
            database=ServiceStatusItem(name="PostgreSQL", status="online", latencyMs=0),
            redis=ServiceStatusItem(name="Redis Cache", status="offline", latencyMs=0),
            websocket=ServiceStatusItem(name="WebSocket Server", status="online", connections=0),
            vpn=ServiceStatusItem(name="Field Mesh VPN", status="unknown"),
            aiEngine=ServiceStatusItem(name="Crowd AI Inference Engine", status="offline"),
            frsEngine=ServiceStatusItem(name="FRS Pipeline Engine", status="offline"),
            network=ServiceStatusItem(name="Control Room Fiber Uplink", status="online"),
        )
