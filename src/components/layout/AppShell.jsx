import { useEffect } from "react";
import { Outlet } from "react-router-dom";
import TopBar from "./TopBar.jsx";
import Sidebar from "./Sidebar.jsx";
import { useCrowdStore } from "../../store/useCrowdStore.js";
import { getCrowdSummary } from "../../services/crowdService.js";

// Poll interval: 30 seconds
const POLL_MS = 30_000;

export default function AppShell() {
  const setCrowdFromAPI = useCrowdStore((s) => s.setCrowdFromAPI);

  useEffect(() => {
    // Initial fetch immediately on mount
    const fetchCrowd = async () => {
      try {
        const res = await getCrowdSummary();
        const d = res?.data ?? res ?? {};
        setCrowdFromAPI(d);
      } catch (e) {
        // Network error — leave store values as-is (zeros)
        console.warn("[AppShell] Crowd poll failed:", e.message);
      }
    };

    fetchCrowd();
    const timer = setInterval(fetchCrowd, POLL_MS);

    // Background pre-warm common categories so opening them is 0ms instant
    const prewarm = async () => {
      try {
        const [
          { getCameraStats, getCameras },
          { getZoneCrowdData },
          { getAlerts },
        ] = await Promise.all([
          import("../../services/cameraService.js"),
          import("../../services/crowdService.js"),
          import("../../services/alertService.js"),
        ]);
        // Fire and populate client cache in parallel
        Promise.allSettled([
          getCameraStats(),
          getCameras({ page_size: 12 }),
          getZoneCrowdData(),
          getAlerts({ page_size: 50 }),
        ]);
      } catch (e) {
        // Non-fatal pre-warm
      }
    };
    prewarm();

    return () => clearInterval(timer);
  }, [setCrowdFromAPI]);


  return (
    <div className="cc-shell">
      <TopBar />
      <div className="cc-body">
        <Sidebar />
        <main className="cc-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

