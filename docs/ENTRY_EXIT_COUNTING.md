# Entry & Exit Line Counting: Vector Geometry & Anti-Duplication Engine

## 1. Overview
The **Entry/Exit Counting Engine** converts continuous multi-object tracking trajectories into discrete, auditable pedestrian crossing events (`PERSON_ENTRY` and `PERSON_EXIT`) for venue gates and pandal access points.

---

## 2. Geometry Setup & Coordinates
All coordinates are normalized to $[0.0, 1.0]$ relative to stream resolution $(W, H)$.

### 2.1. Line Geometries
- **ENTRY_LINE**: 2 points $[(x_1, y_1), (x_2, y_2)]$ representing the physical entry threshold.
- **EXIT_LINE**: 2 points $[(x_1, y_1), (x_2, y_2)]$ representing the physical exit threshold.
- **DIRECTION_LINE**: 2 points $[(x_A, y_A), (x_B, y_B)]$ defining the authorized forward vector $\vec{D} = (x_B - x_A, y_B - y_A)$.

### 2.2. Tracking Ground-Plane Point
Every person's position is grounded using the **bottom-center point**:
$$P_t = \left(\frac{x_{\min} + x_{\max}}{2},\; y_{\max}\right)$$

---

## 3. Intersection & Direction Vector Mathematics

### 3.1. Segment Intersection
Let the person's movement segment between frame $t-1$ and frame $t$ be $S = \overline{P_{t-1} P_t}$.
Let the boundary line be $L = \overline{L_1 L_2}$.

The segments intersect if and only if:
$$\text{CCW}(L_1, L_2, P_{t-1}) \ne \text{CCW}(L_1, L_2, P_t) \quad \land \quad \text{CCW}(P_{t-1}, P_t, L_1) \ne \text{CCW}(P_{t-1}, P_t, L_2)$$
where $\text{CCW}(A, B, C) = (B_x - A_x)(C_y - A_y) - (B_y - A_y)(C_x - A_x) > 0$.

### 3.2. Direction Validation
The person's motion vector is $\vec{M} = P_t - P_{t-1}$.
The alignment with the configured authorized direction vector $\vec{D}$ is verified using the dot product:
$$\cos(\theta) = \frac{\vec{M} \cdot \vec{D}}{\|\vec{M}\| \|\vec{D}\|}$$
- If $\vec{M} \cdot \vec{D} > 0$: The crossing is **FORWARD** (valid).
- If $\vec{M} \cdot \vec{D} \le 0$: The crossing is **REVERSE** (ignored or recorded as counter-flow anomaly).

---

## 4. Anti-Duplicate Temporal Cooldown Engine

### 4.1. The Multi-Frame Problem
A person moving slowly across an entry line at 15 FPS may linger across the line boundary over 5–20 consecutive video frames. Without temporal deduplication, this generates spurious multiple entry events.

### 4.2. Suppression Logic
1. When a track $T$ cross $L$ in valid direction $D$, an event is created.
2. The crossing key is recorded:
   $$\text{Key} = (T.\text{track\_id},\; L.\text{line\_id},\; D)$$
3. The timestamp of the crossing $t_{\text{cross}}$ is saved in an in-memory TTL cache with cooldown window $\Delta t_{\text{cooldown}}$ (default: 60.0 seconds).
4. Any crossing detection matching the same Key where $t_{\text{now}} - t_{\text{cross}} < \Delta t_{\text{cooldown}}$ is **strictly suppressed**.
5. Once a person completes passage and the cooldown expires, the key is evicted.

---

## 5. Multi-Camera Counting Guidelines
- Gates with multiple physical lanes must use non-overlapping camera fields of view or separate lane line geometries.
- Total platform entries equals the sum of deduplicated `PERSON_ENTRY` events across all gate cameras.
- Total platform exits equals the sum of deduplicated `PERSON_EXIT` events across all gate cameras.
