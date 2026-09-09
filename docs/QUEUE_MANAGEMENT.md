# Queue Management: Barricade Flow, Dwell Times & Movement Analytics

## 1. Overview
**Queue Management** monitors pedestrian channels, darshan lines, and ticket counters across 4–5 designated CCTV cameras. It provides operations commanders with live visibility into line length, pedestrian dwell times, and bottleneck growth rates.

All queue data is displayed on the consolidated **Crowd Management** dashboard (`/crowd-management`).

---

## 2. Queue Configuration & Camera Allocation

### 2.1. Initial Camera Allocation (4–5 Channels)
- **Queue 1 (General Darshan Outer)**: Long approach channel along road barricades.
- **Queue 2 (General Darshan Inner)**: Sanctum sanctorum ramp approach.
- **Queue 3 (VIP / Special Entry)**: North gate express queue.
- **Queue 4 (Prasadam Counter Queue)**: Distribution queue.
- **Queue 5 (Footwear Counter Queue)**: Return depot queue.

### 2.2. Required Geometries per Queue Camera
1. `QUEUE_ROI`: Enclosing the designated queue stanchions or barricades.
2. `ENTRY_LINE`: Start of the queue line.
3. `EXIT_LINE`: End of the queue line (service counter or sanctorum threshold).
4. `DIRECTION_LINE`: Normal queue progression vector.

---

## 3. Queue Operational Metrics

### 3.1. People in Queue
Count of active tracks currently located inside the `QUEUE_ROI`:
$$\text{Queue Count} = \text{COUNT}(\{T \in \text{Tracks} \mid \text{point}(T) \in \text{QUEUE\_ROI}\})$$

### 3.2. Queue Length
- When physical calibration is configured: metric length in meters along the channel spline.
- When uncalibrated: **RELATIVE QUEUE LENGTH** expressed as the normalized fraction of the corridor occupied.

### 3.3. Dwell & Wait Time Computation
- Every tracked individual records timestamp $t_{\text{enter}}$ upon entering the `QUEUE_ROI`.
- Instantaneous dwell: $t_{\text{now}} - t_{\text{enter}}$.
- Completed dwell: Recorded when track crosses `EXIT_LINE`.
- Emits:
  - **Average Wait Time**: Mean completed dwell time over the past 15-minute moving window.
  - **Max Current Wait Time**: Longest current dwell of any person currently standing in the queue.
  - **Completed Samples**: Number of individuals who successfully completed the queue.

### 3.4. Movement Status Engine
Determines whether a queue is flowing smoothly or stalled:
- `DRAINING`: Outflow > Inflow + 3/min.
- `STEADY`: Inflow ≈ Outflow (delta within $\pm 3/\text{min}$).
- `GROWING`: Inflow > Outflow by 4 to 10/min.
- `SURGING`: Rapid accumulation (> 10/min growth).
- `STAGNANT`: Headcount $> 50$ with Outflow $< 2/\text{min}$ for $> 3$ minutes.
