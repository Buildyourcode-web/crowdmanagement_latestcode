# Crowd Management Dashboard: Operator Guide & System Architecture

## 1. Overview
The **Crowd Management Dashboard** (`/crowd-management`) is the unified single-pane-of-glass interface for monitoring pandal pedestrian flow, crowd density, entry/exit gates, and barricaded queue channels at Khairatabad Ganesh.

Per architectural standard, there are **no separate Crowd, Queue, or Zones pages**. All operational monitoring, alerting, telemetry, and spatial visualizations are consolidated under `/crowd-management`.

---

## 2. Dashboard Layout

### 2.1. Top KPI Summary Strip
- **Total People**: Current instantaneous valid occupancy across all non-overlapping monitored zones.
- **Total Entries**: Cumulative count of valid `PERSON_ENTRY` events across all gates for the selected timeframe.
- **Total Exits**: Cumulative count of valid `PERSON_EXIT` events across all gates for the selected timeframe.
- **Net Crowd Change**: Net inflow/outflow delta ($\text{Entries} - \text{Exits}$) indicating whether crowd is expanding or diminishing.

### 2.2. Secondary Operational Indicators
- **Active Cameras**: Number of camera streams actively executing inference pipelines.
- **Active Queues**: Number of active queue channels monitored.
- **High Risk Zones**: Count of monitored zones currently at WARNING or CRITICAL risk levels.
- **Longest Queue**: Queue name and current headcount of the largest line.
- **Longest Wait**: Maximum currently observed dwell time among all queues.
- **Overall Platform Risk**: Aggregated deterministic risk rating (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).

### 2.3. Analytics Trend Graphs
1. **People Movement Graph**: Time-series breakdown showing Entries, Exits, and instantaneous People Inside over 15m, 1h, 4h, or 24h.
2. **Queue Movement Graph**: Tracks total queue occupancy, inflow rate (/min), and outflow rate (/min).
3. **Zone Density Graph**: Multi-line comparative density and capacity utilization for Zone A, Zone B, etc.

### 2.4. Live Monitored Sectors
- **Zone Occupancy Cards**: Shows Zone name, assigned camera, headcount, capacity percentage, relative density level, and risk badge.
- **Queue Status Cards**: Shows Queue name, camera, active headcount, wait time (average & max), growth per minute, and movement state (`STEADY`, `GROWING`, `SURGING`, `STAGNANT`).

---

## 3. Real-Time Telemetry & APIs

- **HTTP Summary API**: `GET /api/v1/crowd-management/summary?timeframe=15m`
- **WebSocket Telemetry**: `/ws/v1/events` listening to Redis channel `crowd` and `queue`. Throttled to 2 updates/sec max to prevent browser DOM exhaustion.
- **Strict Data Integrity Rule**: All metrics originate directly from backend AI pipelines. The frontend never synthesizes counts, estimates, or FPS.
