# BYC AI Platform — Operator Guide: Visual ROI & Counting-Line Configuration

This guide provides step-by-step instructions for command center operators configuring Region of Interest (ROI) polygons, counting lines, and exclusion areas for cameras deployed across the Khairatabad Ganesh festival precinct.

---

## 1. Overview & Operational Principles

The BYC AI platform requires precise spatial geometry to perform automated crowd density estimation, queue wait-time analysis, and perimeter safety monitoring.

### Key Rules:
1. **Resolution Independence**: All coordinates are automatically normalized between `0.0` and `1.0`. The system operates seamlessly regardless of display aspect ratio or RTSP stream resolution (1080p, 720p, 4K).
2. **Camera Verification**: You can only configure ROIs on cameras with a verified, active RTSP stream. Offline or unverified cameras will display an operational lock warning.
3. **Non-Inference Rule**: Configuring and saving ROIs **DOES NOT** start video inference pipelines. It prepares spatial parameters so that when the orchestrator starts the pipeline in later stages, the detection boundaries are already validated and active.
4. **Biometric Isolation**: Facial Recognition (FRS) cameras do not require ROI polygons and will reject crowd/queue geometry.

---

## 2. Step-by-Step Operator Workflow

### Step 2.1: Open Camera Details
1. Navigate to **Cameras** in the main navigation.
2. Click on the camera you wish to configure (e.g., `CAM-KHB-001` or a crowd camera).
3. In the camera detail overview, review the **Assigned AI Profiles** card.
4. Look at the **GEOMETRY** readiness badge:
   - `NOT CONFIGURED` (Gray): No spatial boundaries have been defined yet.
   - `PARTIALLY CONFIGURED` (Yellow): Some geometry is defined, but mandatory requirements are missing.
   - `READY FOR AI PIPELINE` (Green): All mandatory geometries are defined and validated.

### Step 2.2: Launch the ROI Editor
1. Click the **[Configure ROI]** button (or **[Configure Queue]** on queue cameras) next to the assigned profile.
2. The visual modal will open and load a live snapshot frame directly from the camera's RTSP stream.

### Step 2.3: Drawing a Crowd ROI Polygon
1. Under **ROI Type**, select **Crowd Density Region (CROWD_ROI)** or **Exclusion Zone (EXCLUSION_ZONE)**.
2. Enter a descriptive name (e.g., `"Main Courtyard Inflow Area"`).
3. In the Drawing Tools panel, click **Draw Polygon**.
4. Click points on the camera image to outline the region.
5. Double-click the last point or click **Finish Polygon** to close the shape (minimum 3 points).
6. To adjust any vertex, simply click and drag it to the desired position.

### Step 2.4: Drawing Queue Entry and Exit Lines
Queue monitoring requires an enclosed queue polygon and at least one entry and one exit line:
1. First, create and save the **Queue Area (QUEUE_ROI)** polygon enclosing the queue barricade.
2. Select **Entry Counting Line (ENTRY_LINE)**:
   - Click **Draw Line**.
   - Click the start point and drag to the end point across the entry opening.
   - Set the counting direction (default is `IN`).
3. Select **Exit Counting Line (EXIT_LINE)**:
   - Click **Draw Line**.
   - Click the start point and drag to the end point across the exit turnstile.
   - Set the counting direction (default is `OUT`).
4. Once all three geometries are created, the profile status will turn **READY FOR AI PIPELINE**.

### Step 2.5: Validating and Saving
1. Click **Validate Geometry** to run a dry-run check against backend validation rules.
2. Click **Save ROI Configuration** to persist the configuration.
3. The configuration will increment its version (e.g., `v1` $\rightarrow$ `v2`) and create an immutable audit record in the security audit log.

---

## 3. Supported Geometries by Profile

| AI Profile | Mandatory Requirements | Optional Geometries |
| :--- | :--- | :--- |
| **CROWD_STANDARD** | At least one `CROWD_ROI` polygon | `EXCLUSION_ZONE`, `COUNTING_LINE` |
| **CROWD_HIGH_DENSITY** | At least one `CROWD_ROI` polygon | `EXCLUSION_ZONE`, `COUNTING_LINE` |
| **QUEUE_STANDARD** | One `QUEUE_ROI` polygon, one `ENTRY_LINE`, one `EXIT_LINE` | `DIRECTION_LINE`, `EXCLUSION_ZONE` |
| **VIDEO_SAFETY** | At least one `SAFETY_BOUNDARY` polygon | `EXCLUSION_ZONE`, `COUNTING_LINE` |
| **FRS_STANDARD** | Biometric only — no ROI allowed | None |

---

## 4. Troubleshooting & FAQ

#### Why does the snapshot show "Camera Offline — ROI editor unavailable"?
The camera is offline or disabled. Bring the physical camera online and verify its network route before configuring spatial boundaries.

#### Why does the snapshot show "Camera stream not verified"?
The camera has been onboarded, but its RTSP stream has not been tested yet. Go back to the Camera Detail page and click **Test Stream** to verify RTSP connectivity first.

#### Can I edit an existing ROI after it is saved?
Yes. Click on the existing ROI in the configuration list to load its vertices, drag the points to their new locations, and click Save. The system will automatically create a new version (`v2`, `v3`, etc.) with full audit history.

#### Does saving an ROI start AI processing?
No. Saving ROI geometry updates the database state and notifies the system. AI inference pipelines will only be started when the deployment is activated via the Orchestrator.
