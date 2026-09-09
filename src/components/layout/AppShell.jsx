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
    // Background poll every 30s for top-bar/global state
    const fetchCrowd = async () => {
      try {
        const res = await getCrowdSummary();
        const d = res?.data ?? res ?? {};
        setCrowdFromAPI(d);
      } catch (e) {
        // Network error — leave store values as-is
        console.warn("[AppShell] Crowd poll notice:", e.message);
      }
    };

    const timer = setInterval(fetchCrowd, POLL_MS);
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

