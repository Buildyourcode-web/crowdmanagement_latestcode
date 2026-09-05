# BYC AI Platform — Camera Onboarding & RTSP Deployment Guide

This guide details the procedure for site operators and field technicians to onboard physical IP cameras into the Khairatabad Ganesh Command & Control (C&C) Platform during Step 3.

---

## 1. Network & Hardware Prerequisites

Before registering an IP camera, ensure the following network criteria are met:

- **Subnet Connectivity**: The camera must be reachable from the BYC AI host server via the local network or VLAN.
- **RTSP Port**: Standard RTSP port `554` (or vendor custom port) must be open and accessible.
- **Video Encoders**: Video codec should be set to **H.264 (AVC)** or **H.265 (HEVC)**.
- **Frame Rate**: Recommended frame rate is **15 to 25 FPS** for crowd & surveillance cameras.
- **Resolution**: Recommended resolution is **1080p (1920×1080)**.

---

## 2. Common RTSP URL Formats by Vendor

| Vendor | Stream Format |
|---|---|
| **Hikvision** | `rtsp://<username>:<password>@<ip>:554/Streaming/Channels/101` (Main Stream) <br/> `rtsp://<username>:<password>@<ip>:554/Streaming/Channels/102` (Sub Stream) |
| **Dahua / CP Plus** | `rtsp://<username>:<password>@<ip>:554/cam/realmonitor?channel=1&subtype=0` |
| **Uniview** | `rtsp://<username>:<password>@<ip>:554/unicast/c1/s0/live` |
| **Axis** | `rtsp://<username>:<password>@<ip>:554/axis-media/media.amp?videocodec=h264` |
| **Generic ONVIF** | `rtsp://<username>:<password>@<ip>:554/live/ch0` or `/live/av0` |

---

## 3. Onboarding Procedure via UI Wizard

Navigate to **Cameras** → **[Onboard Camera Wizard]** (`/cameras/add`).

### Step 1: Camera Identification
1. **Camera ID**: Enter a unique station code following precinct naming conventions:
   - Format: `CAM-KHB-XXX` (e.g. `CAM-KHB-102`)
2. **Camera Name**: Enter a descriptive location title (e.g. `North Gate Entry Arch High Angle`).
3. **Description**: Detail the operational angle and queue coverage area.

### Step 2: RTSP Configuration
1. **RTSP URL**: Enter the RTSP endpoint directly or use the built-in **RTSP URL Builder**:
   - Provide IP (`192.168.0.102`), Port (`554`), and stream path (`/Streaming/Channels/101`).
2. **Credentials**:
   - Username: e.g. `admin`
   - Password: Input password (masked).
   - *Security Note*: Passwords are encrypted at rest using AES-128 (Fernet) and never displayed in public logs, error payloads, or WebSockets.

### Step 3: Test Connection
1. Click **[TEST CAMERA]**.
2. The platform initiates a real-time probe using `ffprobe`:
   - *Connecting...*
   - *Authenticating...*
   - *Inspecting stream...*
   - *Reading metadata...*
   - *Checking stability...*
3. **If CONNECTED**:
   - Inspect confirmed Resolution, FPS, Codec, Latency, and Stability rating.
4. **If CONNECTION FAILED**:
   - Review diagnostic error code (e.g. `RTSP_AUTH_FAILED`, `STREAM_TIMEOUT`).
   - Click **[EDIT CONFIG]** or **[RETRY TEST]**.

### Step 4: Zone & Operational Purpose
1. **Zone**: Assign to a primary precinct zone (e.g. `ZONE-A: North Gate`).
2. **Location Landmark**: Enter physical marker (e.g. `Archway Pillar #2`).
3. **Camera Purpose**:
   - `CROWD`: Crowd density, flow rate, and hotspot alerts.
   - `QUEUE`: Queue formation and waiting line analytics.
   - `FRS`: Biometric facial matching against suspect/missing person databases.
   - `GENERAL`: General perimeter overview CCTV.
   - `MULTI_PURPOSE`: Ingested stream shared across multiple pipelines.
   - *Note: Purpose selection specifies future AI profile assignment. No AI inference is started during onboarding.*

### Step 5: Review & Save
1. Review full configuration summary.
2. The platform performs duplicate conflict verification on `camera_id`, `private_ip`, and `rtsp_url`.
3. Click **[SAVE CAMERA]** to finalize.

---

## 4. Diagnostic Guide for RTSP Error Codes

| Error Code | Root Cause | Operator Remedy |
|---|---|---|
| `CAMERA_NOT_FOUND` | Camera ID not found in database | Check camera code spelling. |
| `INVALID_RTSP_URL` | Malformed URL syntax | URL must start with `rtsp://` or `rtsps://`. |
| `NETWORK_UNREACHABLE` | Host or subnet cannot be reached | Verify camera power, PoE injector, switch port, and IP subnet routing. |
| `RTSP_CONNECTION_FAILED` | RTSP port 554 refused connection | Ensure RTSP protocol is enabled in camera web UI settings. |
| `RTSP_AUTH_FAILED` | 401 Unauthorized from camera | Re-verify username and password in camera settings. |
| `STREAM_NOT_FOUND` | 404 Not Found stream path | Re-check stream channel number / URL path syntax. |
| `NO_VIDEO_TRACK` | Stream connected but has no video | Verify video encoder is active on the camera's sub-channel. |
| `UNSUPPORTED_CODEC` | Incompatible video codec | Change camera video encoding to H.264 or H.265 in camera settings. |
| `STREAM_TIMEOUT` | Probing timed out (>6s) | Check network congestion, high latency, or packet drop. |
| `FFPROBE_UNAVAILABLE` | ffprobe not in PATH on server | Install FFmpeg/ffprobe on the host server. |

---

## 5. Security & Key Management

- **Encryption at Rest**: Sensitive RTSP passwords and authenticated URLs are stored encrypted in the PostgreSQL `cameras` table (`password_encrypted`, `rtsp_url_encrypted`).
- **Key Derivation**: Keys are derived from `settings.JWT_SECRET_KEY` (or custom `CAMERA_ENCRYPTION_KEY` environment variable).
- **Zero Leakage**: All logs, API responses, and WebSocket broadcasts mask or strip credentials.
