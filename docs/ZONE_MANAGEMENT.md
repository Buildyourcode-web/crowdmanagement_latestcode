# Zone Management: Polygon ROI Configuration, Density & Risk

## 1. Overview
**Zone Management** provides continuous spatial occupancy and crowd density monitoring across distinct sectors of the festival grounds (e.g. Zone A Sanctum Sanctorum, Zone B North Pandal, Zone C South Courtyard).

All zones are monitored and visualized inside the consolidated **Crowd Management** dashboard (`/crowd-management`).

---

## 2. Zone Geometry Configuration

### 2.1. Monitored Polygon (`CROWD_ROI`)
- Defined by an ordered set of normalized coordinates $[(x_1, y_1), (x_2, y_2), \dots, (x_k, y_k)]$ with $k \ge 3$.
- Bounded to the physical floor area visible in the camera frame where pilgrims circulate or gather.

### 2.2. Exclusion Zones (`EXCLUSION_ZONE`)
- Optional polygon masks subtracted from the monitored area.
- Used to exclude priest stages, deity platforms, security barricades, and media booths.
- Detections falling inside any active exclusion zone are strictly filtered out before headcount accumulation.

---

## 3. Instantaneous People Counting
For every frame:
1. YOLO11x detects person candidates (Class 0 only).
2. The multi-object tracker updates active tracks (`TRK-xxxx`).
3. For each active track, the bottom-center reference point is calculated.
4. Using the Jordan Curve (Ray-Casting) point-in-polygon algorithm:
   $$\text{Inside} = (\text{point} \in \text{CROWD\_ROI}) \land \neg(\exists Z_{\text{excl}} : \text{point} \in Z_{\text{excl}})$$
5. **Instantaneous Zone Count**: Number of active tracks satisfying $\text{Inside} == \text{True}$.
6. **Strict Non-Accumulation Invariant**: Occupancy is NEVER summed across frames.

---

## 4. Density Calculation & Labeling

### 4.1. Calibrated Physical Density
If the camera calibration matrix is configured with known floor area $A_{\text{m}^2}$:
$$\text{Density} = \frac{\text{Headcount}}{A_{\text{m}^2}} \quad [\text{persons} / \text{m}^2]$$

### 4.2. Relative Density (Default)
When physical calibration is absent, the system displays **RELATIVE DENSITY**:
$$\text{Relative Density} = \frac{\text{Headcount}}{\text{Configured Zone Capacity}} \times 100\%$$
- `LOW`: $< 50\%$ utilization.
- `MEDIUM`: $50\% - 75\%$ utilization.
- `HIGH`: $75\% - 90\%$ utilization.
- `CRITICAL`: $> 90\%$ utilization (triggers immediate alert).

---

## 5. Non-Overlapping Multi-Camera Monitoring
To compute total festival venue occupancy without double-counting:
- Ensure the primary zone cameras (e.g. CAM-06 and CAM-07) monitor disjoint spatial sectors.
- Total venue people count is the instantaneous sum of disjoint zone headcounts.
- Cross-camera face recognition or person re-identification is strictly avoided.
