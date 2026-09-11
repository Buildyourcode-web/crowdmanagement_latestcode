from typing import List
from app.schemas.prediction import CrowdPredictionResponse, QueuePredictionItem, ZoneRiskPredictionItem


class PredictionService:
    @staticmethod
    def get_crowd_prediction() -> CrowdPredictionResponse:
        # Connect to real runtime crowd occupancy and flow trends
        cur_crowd = 0
        inflow = 0
        outflow = 0
        try:
            from app.frs_engine.frs_service import _active_workers, _workers_lock
            with _workers_lock:
                for w in _active_workers.values():
                    if getattr(w.state, "running", False) and getattr(w.state, "crowd_ai_active", False):
                        cur_crowd += getattr(w.state, "occupancy_count", 0)
                        inflow += getattr(w.state, "in_count", 0)
                        outflow += getattr(w.state, "out_count", 0)
        except Exception:
            pass

        # Calculate flow rate delta (growth per minute)
        flow_delta = max(-50, min(100, inflow - outflow))
        f15 = max(0, cur_crowd + int(flow_delta * 0.25))
        f30 = max(0, cur_crowd + int(flow_delta * 0.50))
        f45 = max(0, cur_crowd + int(flow_delta * 0.75))
        f60 = max(0, cur_crowd + int(flow_delta * 1.00))

        return CrowdPredictionResponse(
            status="LIVE AI FORECAST" if cur_crowd > 0 else "NO_DATA",
            current=cur_crowd,
            forecast_15_min=f15,
            forecast_30_min=f30,
            forecast_45_min=f45,
            forecast_60_min=f60,
            time_series={
                "actual": [["-45m", max(0, cur_crowd - 30)], ["-30m", max(0, cur_crowd - 20)], ["-15m", max(0, cur_crowd - 10)], ["Now", cur_crowd]],
                "predicted": [["+15m", f15], ["+30m", f30], ["+45m", f45], ["+60m", f60]],
                "lower": [["+15m", max(0, f15 - 5)], ["+30m", max(0, f30 - 10)], ["+45m", max(0, f45 - 15)], ["+60m", max(0, f60 - 20)]],
                "upper": [["+15m", f15 + 5], ["+30m", f30 + 10], ["+45m", f45 + 15], ["+60m", f60 + 20]],
            },
        )

    @staticmethod
    def get_queue_predictions() -> List[QueuePredictionItem]:
        items: List[QueuePredictionItem] = []
        try:
            from app.frs_engine.frs_service import _active_workers, _workers_lock
            with _workers_lock:
                for cid, w in _active_workers.items():
                    if getattr(w.state, "running", False) and getattr(w.state, "crowd_ai_active", False) and "QUEUE" in getattr(w.state, "ai_purposes", []):
                        cnt = getattr(w.state, "occupancy_count", 0)
                        mov = getattr(w.state, "queue_movement_status", "STOPPED")
                        cur_wait = round((cnt * 1.5) / 60) if cnt > 0 else 0
                        pred_wait = cur_wait + (5 if mov == "SLOW" else (10 if mov == "STOPPED" else 0))
                        items.append(
                            QueuePredictionItem(
                                gate=f"Gate {cid}",
                                current_wait_min=cur_wait,
                                predicted_wait_min_30=pred_wait,
                                trend="rising" if mov in ("SLOW", "STOPPED") and cnt > 20 else "stable",
                            )
                        )
        except Exception:
            pass
        return items

    @staticmethod
    def get_zone_risk_predictions() -> List[ZoneRiskPredictionItem]:
        items: List[ZoneRiskPredictionItem] = []
        try:
            from app.frs_engine.frs_service import _active_workers, _workers_lock
            with _workers_lock:
                for w in _active_workers.values():
                    if getattr(w.state, "running", False) and getattr(w.state, "crowd_ai_active", False) and "ZONE" in getattr(w.state, "ai_purposes", []):
                        zd = getattr(w.state, "zone_data", [])
                        for z in zd:
                            zname = z.get("name", "Zone")
                            zstat = z.get("status", "NORMAL")
                            cnt = z.get("count", 0)
                            w_thresh = z.get("warning_threshold", 50)
                            d_thresh = z.get("danger_threshold", 80)
                            cur_risk = "CRITICAL" if zstat == "DANGER" else ("HIGH" if zstat == "WARNING" else "NORMAL")
                            pred_risk = "CRITICAL" if cnt >= (w_thresh * 0.8) else ("HIGH" if cnt >= (w_thresh * 0.5) else "NORMAL")
                            prob = min(0.95, max(0.15, cnt / float(d_thresh))) if d_thresh > 0 else 0.5
                            items.append(
                                ZoneRiskPredictionItem(
                                    zone=zname,
                                    current_risk=cur_risk,
                                    predicted_risk_30=pred_risk,
                                    probability=round(prob, 2),
                                )
                            )
        except Exception:
            pass
        return items
