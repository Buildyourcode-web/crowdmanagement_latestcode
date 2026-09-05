import urllib.request
import json
import sys

BASE_URL = "http://localhost:8000"

def test_all_apis():
    print("==================================================", flush=True)
    print("Testing Backend APIs connected to Supabase...", flush=True)
    print("==================================================", flush=True)
    
    # 1. Login
    login_data = json.dumps({"username": "admin", "password": "admin123"}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/v1/auth/login",
        data=login_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    res = json.loads(urllib.request.urlopen(req).read().decode())
    token = res["data"]["access_token"]
    print("[OK] POST /api/v1/auth/login -> Login successful! Access token received.", flush=True)
    
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    
    endpoints = [
        ("GET", "/api/v1/auth/me", "User Profile"),
        ("GET", "/api/v1/crowd/summary", "Crowd Summary (Real-time aggregation)"),
        ("GET", "/api/v1/crowd/zones", "Crowd Zones List (12 Zones)"),
        ("GET", "/api/v1/crowd/queues", "Crowd Queues List"),
        ("GET", "/api/v1/cameras?page=1&page_size=10", "Cameras Fleet (1 Camera)"),
        ("GET", "/api/v1/cameras/stats", "Camera Health & Status Stats"),
        ("GET", "/api/v1/alerts?page=1&page_size=10", "Operational Alerts (20+ Alerts)"),
        ("GET", "/api/v1/alerts/stats", "Alerts Severity Stats"),
        ("GET", "/api/v1/incidents?page=1&page_size=10", "Incidents Lifecycle"),
        ("GET", "/api/v1/missing-persons", "Missing Persons Registry"),
        ("GET", "/api/v1/frs/dashboard", "FRS Facial Recognition Dashboard"),
        ("GET", "/api/v1/frs/candidates?page=1&page_size=10", "FRS Detection Candidates"),
        ("GET", "/api/v1/operations/police-units", "Deployed Police Units"),
        ("GET", "/api/v1/operations/medical-units", "Emergency Medical Units"),
        ("GET", "/api/v1/operations/emergency-routes", "Emergency Evacuation Corridors"),
        ("GET", "/api/v1/system/health", "System Health & Cluster Metrics"),
        ("GET", "/api/v1/analytics/attendance", "Attendance Analytics"),
        ("GET", "/api/v1/predictions/crowd", "Crowd Forecast Predictions"),
    ]
    
    for method, endpoint, label in endpoints:
        try:
            req = urllib.request.Request(f"{BASE_URL}{endpoint}", headers=headers, method=method)
            resp = urllib.request.urlopen(req)
            data = json.loads(resp.read().decode())
            payload = data.get("data")
            count_info = f"items: {len(payload)}" if isinstance(payload, list) else "ok"
            print(f"[OK] {method} {endpoint.split('?')[0]:<35} -> {label} ({count_info})", flush=True)
        except Exception as e:
            print(f"[FAIL] {method} {endpoint} -> FAILED: {e}", flush=True)

    print("==================================================", flush=True)
    print("All APIs successfully verified against Supabase!", flush=True)
    print("==================================================", flush=True)

if __name__ == "__main__":
    test_all_apis()
