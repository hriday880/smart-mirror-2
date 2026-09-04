# Survey Explorer 2 Report: Gesture Recognition & Capture UX Architecture

**Author**: Survey Explorer 2 (Gesture & Capture UX Explorer)  
**Date**: 2026-08-14  
**Target Milestone**: Phase 0 — Survey & Scope Mapping  
**Output Path**: `/Users/hriday/Desktop/smart mirror #2/Filters/.agents/survey_explorer_2/handoff.md`

---

## 1. Observation

### 1.1 Codebase Inspection & Existing Landmarks Pipeline

Direct inspection of the repository reveals the current architectural components:

1. **Landmark Constants & Finger Extension (`hand_tracking.py:3-29`)**:
   ```python
   WRIST = 0
   THUMB_TIP, THUMB_MCP = 4, 2
   INDEX_TIP, INDEX_MCP = 8, 5
   MIDDLE_TIP, MIDDLE_MCP = 12, 9
   RING_TIP, RING_MCP = 16, 13
   PINKY_TIP, PINKY_MCP = 20, 17

   def _dist(lm, i, j, w, h):
       a = np.array([lm[i].x * w, lm[i].y * h])
       b = np.array([lm[j].x * w, lm[j].y * h])
       return np.linalg.norm(a - b)

   def get_extended_fingers(hand_landmarks, w, h):
       lm = hand_landmarks.landmark
       def is_extended(tip, mcp):
           return _dist(lm, tip, WRIST, w, h) > _dist(lm, mcp, WRIST, w, h) * 1.3
       return {
           "thumb": is_extended(THUMB_TIP, THUMB_MCP),
           "index": is_extended(INDEX_TIP, INDEX_MCP),
           "middle": is_extended(MIDDLE_TIP, MIDDLE_MCP),
           "ring": is_extended(RING_TIP, RING_MCP),
           "pinky": is_extended(PINKY_TIP, PINKY_MCP),
       }
   ```
   *Finding*: The existing extension test compares Euclidean distance from the WRIST to TIP vs WRIST to MCP with a static multiplier `1.3`. While simple, this does not check joint collinearity (e.g. curling towards palm vs extending sideways) or intermediate joint positions (`PIP`, `DIP`).

2. **MediaPipe Tracking Pipeline & Two-Handed Interaction (`main.py:10-66`)**:
   ```python
   mp_hands = mp.solutions.hands
   hands = mp_hands.Hands(
       max_num_hands=2,
       min_detection_confidence=0.6,
       min_tracking_confidence=0.6,
   )
   ```
   - Hands are classified as Left/Right (`main.py:43-49`).
   - Portal vertices $p1, p2, p3, p4$ are defined by Left Hand (Index Tip $8$, Thumb Tip $4$) and Right Hand (Index Tip $8$, Thumb Tip $4$).
   - Filter cycling is managed by `ClosingGestureDetector.update(width, w)` when the portal width drops below `0.16 * frame_w` and opens past `0.30 * frame_w`.

3. **Filter Rendering Pipeline (`geometry.py:32-61` & `filters.py:108-117`)**:
   - `paint_filter_in_polygon` applies the filter exclusively inside the quadrilateral mask.
   - `FILTROS` contains 8 visual effects (`filtro_grid`, `filtro_1`, `filtro_2`, `filtro_3`, `filtro_5`, `filtro_6`, `filtro_blanco`, `filtro_rosa`).
   - Frame rendering directly mutates `frame` and displays it via `cv2.imshow(" ", frame)`.

4. **User & Orchestrator Requirements (`ORIGINAL_REQUEST.md:14-19`)**:
   - **R1**: Reliable, robust hand gesture trigger using MediaPipe.
   - **R2**: Fair-ready capture workflow (instant capture, visual countdown, frictionless delivery).
   - **R3**: Zero modifications to original files (`main.py`, `filters.py`, `geometry.py`, `hand_tracking.py`). All work in isolated test modules (e.g., `main_test.py`, `gesture_detector_test.py`, `capture_pipeline_test.py`).
   - **R4**: Double-clickable `test.command` launcher.

---

## 2. Logic Chain

### 2.1 Candidate Gesture Comparative Matrix

In a busy fair setting, a capture gesture must balance **high intentionality** (no accidental triggers from natural talking/moving), **ergonomics/fun** (natural pose for a souvenir photo), **MediaPipe landmark stability**, and **non-interference with the two-handed portal filter system**.

| Candidate Gesture | MediaPipe Distinctiveness | False Positive Resistance | Fair / Photo Ergonomics | Portal Coexistence | Overall Suitability |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Peace Sign (✌️ / "V" Sign)**<br>*(Index + Middle extended, Ring + Pinky curled, Thumb folded)* | **Very High**<br>Extremely distinct geometric signature (two parallel/diverging extended fingers + two tucked fingers). | **Very High**<br>Rarely held stationary in casual movement; requires deliberate finger curling. | **Exceptional**<br>Globally iconic, joyful photo pose across all ages and cultures. | **Complete Separation**<br>Portal uses Thumb+Index with Middle curled; Peace uses Index+Middle with Thumb folded. | **10/10 (Primary Choice)** |
| **Open Palm (🖐️)**<br>*(All 5 fingers extended, palm facing camera)* | **High**<br>High landmark confidence; all 5 tips extended beyond MCPs. | **Low to Moderate**<br>Prone to false triggers during waving, greeting, adjusting hair, or pointing at mirror. | **Moderate**<br>Feels like a "stop" sign or traffic hand rather than a playful photo pose. | **Moderate**<br>Can trigger if user spreads fingers while reaching for the portal. | **7.5/10 (Secondary / Alt Choice)** |
| **Thumbs Up (👍)**<br>*(Thumb extended upward, 4 fingers curled)* | **Moderate to High**<br>Fist with vertical thumb; MediaPipe thumb tracking can jitter when pointing towards camera. | **High**<br>Deliberate gesture, uncommon in resting hand positions. | **Good**<br>Positive and friendly pose. | **High Separation**<br>No fingers extended except thumb. | **8.0/10 (Strong Alternative)** |
| **OK Sign (👌)**<br>*(Index tip touches Thumb tip, 3 fingers extended)* | **Moderate**<br>Requires detecting pinch contact $(d(4, 8) < \epsilon)$ + 3 fingers extended. | **High**<br>Specific geometric requirement. | **Moderate**<br>Can be awkward to hold towards mirror at certain angles. | **High Separation**<br>Portal keeps index and thumb apart. | **7.0/10** |
| **Pinch / Snap (🤏)**<br>*(Thumb tip and Index tip touching)* | **Low to Moderate**<br>Susceptible to perspective foreshortening and occlusions. | **Low**<br>Fingers touching is common when resting or closing portal. | **Low**<br>Not an intuitive selfie pose. | **Poor**<br>Conflicts directly with the closing portal filter transition. | **4.0/10 (Reject)** |
| **Pointing / Finger Gun (☝️ / 👉)**<br>*(Index extended, others curled)* | **Moderate**<br>Single extended finger. | **Low**<br>High false positives when users point at mirror features or companions. | **Moderate**<br>Can feel aggressive or ambiguous. | **Moderate** | **5.5/10 (Reject)** |
| **Fist (✊)**<br>*(All 5 fingers curled)* | **Moderate**<br>All tips close to wrist/palm. | **Low to Moderate**<br>Occurs naturally when hands are at rest or walking by. | **Low**<br>Unphotogenic. | **Low** | **4.0/10 (Reject)** |

**Architectural Recommendation**:
1. **Primary Trigger**: **Peace Sign (✌️)**. It maximizes delight, prevents accidental triggers, and functions as the natural photo pose.
2. **Secondary / Extensible Trigger**: Support a configurable gesture engine capable of recognizing **Peace Sign (✌️)**, **Open Palm (🖐️)**, and **Thumbs Up (👍)** through a clean pluggable interface.

---

### 2.2 Mathematical & Geometric Landmark Criteria

MediaPipe Hands provides 21 3D landmarks $(x_i, y_i, z_i)$ where $x, y \in [0.0, 1.0]$ are normalized by image width and height.

```
MediaPipe Hand Landmarks Index Map:
       8 (INDEX_TIP)    12 (MIDDLE_TIP)    16 (RING_TIP)    20 (PINKY_TIP)
       |                 |                  |                |
       7 (INDEX_DIP)    11 (MIDDLE_DIP)    15 (RING_DIP)    19 (PINKY_DIP)
       |                 |                  |                |
4 (THUMB_TIP)
       |                 6 (INDEX_PIP)    10 (MIDDLE_PIP)    14 (RING_PIP)    18 (PINKY_PIP)
3 (THUMB_IP)             |                  |                |                |
       |                 5 (INDEX_MCP)     9 (MIDDLE_MCP)   13 (RING_MCP)    17 (PINKY_MCP)
2 (THUMB_MCP)            \                  |                /                /
       |                  \                 |               /                /
1 (THUMB_CMC)              --------------------------------------------------
       \                                    |
        --------------------------------- 0 (WRIST)
```

#### 2.2.1 Scale Normalization Metric
To ensure mathematical criteria remain invariant to user distance from the camera (whether standing 0.8m or 2.5m away), we define a dynamic **Palm Scale Metric ($S$)**:
$$S = \|\mathbf{p}_{\text{MIDDLE\_MCP}} - \mathbf{p}_{\text{WRIST}}\|_2 = \sqrt{(x_9 - x_0)^2 + (y_9 - y_0)^2}$$
All Euclidean distances are evaluated relative to $S$ (dimensionless scale-invariant ratio).

#### 2.2.2 Joint Angle Calculation
For any three consecutive landmarks $A, B, C$ (e.g. $\text{MCP} \to \text{PIP} \to \text{TIP}$):
$$\vec{u} = \mathbf{p}_A - \mathbf{p}_B, \quad \vec{v} = \mathbf{p}_C - \mathbf{p}_B$$
$$\theta(A, B, C) = \arccos\left(\frac{\vec{u} \cdot \vec{v}}{\|\vec{u}\|_2 \|\vec{v}\|_2}\right) \times \frac{180^\circ}{\pi}$$
For a straight extended finger, $\theta \approx 180^\circ$ (collinear). For a curled finger, $\theta \le 110^\circ$.

#### 2.2.3 Precise Mathematical Conditions for Peace Sign (✌️)
A hand landmark set $\mathcal{L} = \{\mathbf{p}_0, \dots, \mathbf{p}_{20}\}$ satisfies the **Peace Sign** predicate if and only if ALL of the following 6 conditions evaluate to `True`:

1. **Index Finger Full Extension**:
   - *Distance Ratio*: $\|\mathbf{p}_8 - \mathbf{p}_0\|_2 > 1.20 \cdot \|\mathbf{p}_6 - \mathbf{p}_0\|_2$ (Tip further from Wrist than PIP).
   - *Collinearity Angle*: $\theta(\mathbf{p}_5, \mathbf{p}_6, \mathbf{p}_8) \ge 145^\circ$.
   - *Tip-to-MCP Distance*: $\|\mathbf{p}_8 - \mathbf{p}_5\|_2 \ge 0.70 \cdot S$.

2. **Middle Finger Full Extension**:
   - *Distance Ratio*: $\|\mathbf{p}_{12} - \mathbf{p}_0\|_2 > 1.20 \cdot \|\mathbf{p}_{10} - \mathbf{p}_0\|_2$.
   - *Collinearity Angle*: $\theta(\mathbf{p}_9, \mathbf{p}_{10}, \mathbf{p}_{12}) \ge 145^\circ$.
   - *Tip-to-MCP Distance*: $\|\mathbf{p}_{12} - \mathbf{p}_9\|_2 \ge 0.70 \cdot S$.

3. **Ring Finger Full Curl**:
   - *Distance Inversion*: $\|\mathbf{p}_{16} - \mathbf{p}_0\|_2 < \|\mathbf{p}_{14} - \mathbf{p}_0\|_2$ (Tip is tucked closer to wrist than PIP).
   - *Proximity to Palm*: $\|\mathbf{p}_{16} - \mathbf{p}_{13}\|_2 \le 0.55 \cdot S$.
   - *Curl Angle*: $\theta(\mathbf{p}_{13}, \mathbf{p}_{14}, \mathbf{p}_{16}) \le 120^\circ$.

4. **Pinky Finger Full Curl**:
   - *Distance Inversion*: $\|\mathbf{p}_{20} - \mathbf{p}_0\|_2 < \|\mathbf{p}_{18} - \mathbf{p}_0\|_2$.
   - *Proximity to Palm*: $\|\mathbf{p}_{20} - \mathbf{p}_{17}\|_2 \le 0.55 \cdot S$.
   - *Curl Angle*: $\theta(\mathbf{p}_{17}, \mathbf{p}_{18}, \mathbf{p}_{20}) \le 120^\circ$.

5. **V-Formation Angular Separation**:
   - Let $\vec{v}_{\text{index}} = \mathbf{p}_8 - \mathbf{p}_5$ and $\vec{v}_{\text{middle}} = \mathbf{p}_{12} - \mathbf{p}_9$.
   - Angular divergence: $\theta_V = \arccos\left(\frac{\vec{v}_{\text{index}} \cdot \vec{v}_{\text{middle}}}{\|\vec{v}_{\text{index}}\| \|\vec{v}_{\text{middle}}\|}\right) \times \frac{180^\circ}{\pi}$.
   - Criterion: $10^\circ \le \theta_V \le 60^\circ$ AND $\|\mathbf{p}_8 - \mathbf{p}_{12}\|_2 \ge 0.25 \cdot S$.

6. **Thumb Tucked / Restrained**:
   - Thumb tip $\mathbf{p}_4$ is folded across the palm or over the ring finger:
     $\min\left(\|\mathbf{p}_4 - \mathbf{p}_{13}\|_2, \|\mathbf{p}_4 - \mathbf{p}_{14}\|_2, \|\mathbf{p}_4 - \mathbf{p}_9\|_2\right) \le 0.75 \cdot S$.

---

### 2.3 Robustness Factors & Environmental Resilience

| Factor | Challenge in Fair Setting | Mitigation Strategy & Mathematical Solution |
| :--- | :--- | :--- |
| **False Positives** | Fast arm movements, scratching head, holding props, waving. | **Temporal Hold-Window Verification**: Gesture must be continuously held for $T_{\text{hold}} = 0.7\text{s}$ (approx. 20 consecutive frames at 30 FPS). Transient occurrences are discarded. |
| **Hand Orientation / Tilt** | Users naturally tilt their hand at $30^\circ - 60^\circ$ angles in selfies. | **Vector Angle Invariance**: Calculations use internal joint angles $(\theta)$ and relative vector dot products rather than static vertical screen axes $(y_{\text{tip}} < y_{\text{mcp}})$. Valid across all $360^\circ$ in-plane rotations. |
| **Handedness Parity** | Right vs Left hand anatomical mirror symmetry. | **Symmetric Coordinate Math**: Pure Euclidean relative distances and joint angles are identical for left and right hands. No handedness-specific branches required. |
| **Distance / Scale Variance** | User stands close ($0.8\text{m}$) or far ($3.0\text{m}$) from mirror. | **Palm Metric Normalization**: All absolute pixel distances are divided by $S = \|\mathbf{p}_9 - \mathbf{p}_0\|_2$. Thresholds operate in scale-free space. |
| **Dual-Hand Coexistence** | User operating the 2-hand portal filter vs single-hand posing. | **Multi-Hand Evaluation**: Iterate over all detected hands in `results.multi_hand_landmarks`. If either hand forms a sustained Peace sign, trigger capture while preserving portal rendering. |
| **Occlusion / Edge-of-Frame** | Hand partially outside camera FOV causing MediaPipe hallucination. | **Landmark Visibility & Boundary Guard**: Reject hand if any of landmarks $\{0, 4, 8, 12, 16, 20\}$ fall within 15px of frame edge or if detection confidence $< 0.65$. |
| **Lighting & Fair Noise** | Disco lights, spotlights, low-contrast fair booths. | **Hysteresis Smoothing**: Exponential moving average on landmark coordinates $(\alpha = 0.75)$ to eliminate high-frequency jitter. |

---

### 2.4 Interaction UX & Temporal State Machine

To provide an intuitive, arcade/photo-booth experience, the capture workflow is modeled as a 6-state Finite State Machine:

```
                  ┌──────────────────────────────────────────────┐
                  │                                              │
                  ▼                                              │
         ┌─────────────────┐                                     │
         │   STATE 0:      │                                     │
         │  IDLE / MIRROR  │◄─────────────────┐                  │
         └────────┬────────┘                  │                  │
                  │ Gesture Detected          │ Gesture Lost     │
                  ▼                           │ (Hold reset)     │
         ┌─────────────────┐                  │                  │
         │   STATE 1:      │──────────────────┘                  │
         │ ARMED / HOLDING │                                     │
         └────────┬────────┘                                     │
                  │ Hold Time >= 0.7s Complete                   │
                  ▼                                              │
         ┌─────────────────┐                                     │
         │   STATE 2:      │                                     │
         │ COUNTDOWN (3s)  │ (Live filter continues)             │
         └────────┬────────┘                                     │
                  │ Timer Expired (t = 0.0s)                     │
                  ▼                                              │
         ┌─────────────────┐                                     │
         │   STATE 3:      │                                     │
         │  FLASH & SNAP   │ (Save pristine clean + filtered)    │
         └────────┬────────┘                                     │
                  │ Flash Decay (0.2s)                           │
                  ▼                                              │
         ┌─────────────────┐                                     │
         │   STATE 4:      │                                     │
         │ DELIVERY / HUD  │ (QR Code + Preview Card + Save)     │
         └────────┬────────┘                                     │
                  │ Display Time (6.0s) Expired or Dismissed     │
                  ▼                                              │
         ┌─────────────────┐                                     │
         │   STATE 5:      │                                     │
         │ COOLDOWN (2.0s) │─────────────────────────────────────┘
         └─────────────────┘
```

#### Detailed State Specifications:

1. **State 0: IDLE / MIRROR**
   - Live camera feed running with active portal and filter rendering.
   - Constantly evaluates all detected hands against `is_peace_gesture(hand_landmarks)`.
   - Visual Feedback: Normal mirror HUD.

2. **State 1: ARMED / HOLDING INTENT**
   - Triggered on first frame where `is_peace_gesture == True`.
   - Timer `t_armed` tracks elapsed hold duration.
   - **Visual Feedback**:
     - A sleek circular progress ring sweeps around the detected hand $(x_9, y_9)$ in cyan/neon yellow: $\text{SweepAngle} = 360^\circ \times \frac{t_{\text{elapsed}}}{T_{\text{hold}}}$.
     - Subtle text prompt near top: `"Hold ✌️ to take photo..."`.
   - If gesture is dropped before $T_{\text{hold}} = 0.7\text{s}$, reset instantly to State 0.

3. **State 2: COUNTDOWN (3-2-1)**
   - Triggered when $t_{\text{elapsed}} \ge T_{\text{hold}}$.
   - Countdown duration: $T_{\text{countdown}} = 3.0\text{s}$ (3, 2, 1).
   - **Visual Feedback**:
     - Giant, pulsing countdown numeral $(3 \to 2 \to 1)$ rendered in center of screen with translucent drop shadow.
     - Fractional second pulse animation: scale oscillates $1.0 \to 1.25$ on each integer second tick.
     - Top banner: `"Pose for the camera! 📸"`.
     - Live video feed and portal filter remain 100% interactive so users can align their pose.
   - **Audio Feedback**:
     - Short acoustic beep or tick sound on each second ($3, 2, 1$) via macOS system sound (`/System/Library/Sounds/Ping.aiff` or `Tink.aiff`).

4. **State 3: FLASH & SNAP**
   - At $t = 0.0\text{s}$:
   - Capture clean frame buffer and filtered frame buffer instantly.
   - **Visual Flash Effect**:
     - High-intensity white screen flash overlay.
     - Frame 0: $\alpha = 0.95$ whiteout.
     - Exponential decay over 5 frames ($150\text{ms}$): $\alpha(k) = 0.95 \times e^{-k \times 0.6}$.
   - **Audio Feedback**:
     - High-fidelity camera shutter sound (`/System/Library/Components/CoreAudio.component/Contents/SharedSupport/SystemSounds/system/payment_success.caf` or standard camera shutter audio).

5. **State 4: DELIVERY / FAIR HUB PREVIEW**
   - Displays the captured image with the active filter.
   - Integrates with Explorer 3's Fair Delivery Hub (e.g. saves JPEG to `captures/capture_YYYYMMDD_HHMMSS.jpg`, displays QR code overlay or picture-in-picture preview card).
   - Display duration: 6 seconds auto-dismiss, or dismissible via hand wave.

6. **State 5: COOLDOWN / DEBOUNCE**
   - Enforces a $2.0\text{s}$ lock-out window where gesture triggering is disabled.
   - Prevents continuous accidental re-triggering while users lower their hands.

---

### 2.5 Frame Capture Pipeline & Buffer Strategy

To ensure zero UI artifacts (countdown digits, progress rings, flash whiteouts) contaminate the saved photo, the rendering pipeline must maintain strict **layer separation**:

```
 [ WebCam Video Input ]
          │
          ▼
   Raw BGR Frame (Flipped) ─────────► [ BUFFER 1: Clean Raw Frame ] ───► (Raw Archive)
          │
          ▼
  Portal Geometry & Filter
          │
          ▼
 [ BUFFER 2: Filtered Capture Frame ] ────────────────────────────────► [ JPEG DISK SAVER ]
          │                                                              (Pristine Output)
          ▼
 Overlay UI Layer
 (Countdown text, progress ring,
  portal borders, flash whiteout)
          │
          ▼
 [ BUFFER 3: Display Frame ] ────────────────────────────────────────► [ cv2.imshow Mirror ]
```

#### Buffer Separation Rules:
1. **Pristine Filtered Frame (`BUFFER 2`)**:
   - `capture_frame = paint_filter_in_polygon(raw_frame.copy(), polygon, active_filter)`
   - NO text overlays, NO landmark dots, NO countdown numbers, NO bounding box lines.
   - This exact frame is passed to the asynchronous image saver.
2. **Display Frame (`BUFFER 3`)**:
   - `display_frame = capture_frame.copy()`
   - Draw portal outlines (`cv2.polylines`), countdown numerals, hold-time progress ring, flash blend, and UI HUD cards.
   - Passed exclusively to `cv2.imshow`.
3. **Asynchronous Non-Blocking Disk Write**:
   - To prevent frame stutter or dropped video frames during JPEG encoding and disk I/O, writing is dispatched to a worker thread:
     ```python
     threading.Thread(target=cv2.imwrite, args=(filepath, capture_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])).start()
     ```
4. **Resolution Strategy**:
   - Explicitly request 720p/1080p from webcam during initialization:
     ```python
     cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
     cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
     ```
   - All geometric calculations are normalized, automatically scaling with any resolution.

---

## 3. Caveats

1. **Extreme Hand Angles / Foreshortening**:
   - If the user points their peace sign directly towards the camera lens (z-axis pointing), 2D distances between fingertips and knuckles compress. The angle check and palm-scale ratio mitigate this, but extreme foreshortening ($> 60^\circ$ out of plane) may require slightly more forgiving thresholds.
2. **Camera Sensor Auto-Exposure / Shutter Latency**:
   - In low-light fair environments, webcams increase exposure time (creating motion blur). The 3-second countdown provides ample time for users to steady their pose, minimizing motion blur.
3. **Multi-Person Backgrounds**:
   - In a crowded fair aisle, people passing in the background might be detected if `max_num_hands` is large. Maintaining `max_num_hands=2` and prioritizing hands occupying the largest bounding area (closest to mirror) guarantees robust foreground subject locking.

---

## 4. Conclusion

1. **Selected Primary Gesture**: **Peace Sign (✌️)** is the optimal capture trigger. It combines iconic photo-booth aesthetics with mathematically unambiguous landmark contrast and zero interference with the two-handed portal geometry.
2. **Mathematical Model**: Scale-invariant geometric formulation based on 6 landmark predicates normalized by palm length $S = \|\mathbf{p}_9 - \mathbf{p}_0\|_2$, featuring vector angle collinearity checks.
3. **UX State Machine**: 6-state interactive engine with $0.7\text{s}$ hold confirmation, animated 3-2-1 countdown, $150\text{ms}$ alpha-decay flash, and $2.0\text{s}$ cooldown debounce.
4. **Capture Pipeline**: 3-tier buffer architecture ensuring 100% clean, high-resolution filtered photos saved asynchronously without UI overlay contamination.

---

## 5. Verification Method

To independently verify the gesture recognition engine, temporal state machine, and capture buffer pipeline:

### 5.1 Standalone Test Suite Execution
Create isolated unit test suite `tests/test_gesture_capture.py` and run via project virtualenv:
```bash
source venv/bin/activate
pytest tests/test_gesture_capture.py -v
```

### 5.2 Synthetic Landmark Test Vectors
Verify landmark predicates against synthesized landmark arrays:
1. **Positive Peace Sign Vector**:
   - Index tip $(x=0.5, y=0.2)$, MCP $(x=0.5, y=0.5)$
   - Middle tip $(x=0.58, y=0.2)$, MCP $(x=0.58, y=0.5)$
   - Ring tip $(x=0.64, y=0.55)$, MCP $(x=0.64, y=0.5)$ [Curled]
   - Pinky tip $(x=0.70, y=0.56)$, MCP $(x=0.70, y=0.5)$ [Curled]
   - Wrist $(x=0.58, y=0.8)$
   - *Expected Output*: `is_peace_gesture() == True`.
2. **Negative Portal Hand Vector (Index + Thumb extended, Middle curled)**:
   - Index extended, Thumb extended, Middle curled.
   - *Expected Output*: `is_peace_gesture() == False` (Ensures portal manipulation never triggers photo capture).
3. **Negative Open Palm Vector (All 5 extended)**:
   - *Expected Output*: `is_peace_gesture() == False`.

### 5.3 State Machine Temporal Simulation
Simulate a sequence of 120 frames at 30 FPS:
- Frames 1–15: Gesture detected (Hold counter increments, state = `ARMED`).
- Frames 16–35: Gesture maintained (Hold threshold reached $\to$ state transition to `COUNTDOWN`).
- Frames 36–125: 3.0s Countdown progresses $(3 \to 2 \to 1)$.
- Frame 126: $t=0 \to$ State transition to `FLASH`, disk write callback invoked with clean filtered frame buffer.

### 5.4 Invalidation Conditions
- False positive trigger when performing the portal closing gesture.
- Any UI text or countdown numbers rendered into the saved JPEG file.
- State machine locking up if gesture is dropped mid-hold.
