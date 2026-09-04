# Handoff Report: Milestone M2 — Gesture Detection & Capture State Machine Engine

**Worker**: Worker M2 (Gesture Detection & Capture State Machine Worker)  
**Date**: 2026-08-14  
**Working Directory**: `/Users/hriday/Desktop/smart mirror #2/Filters/.agents/worker_m2_gesture`  
**Target File Exclusively Owned**: `/Users/hriday/Desktop/smart mirror #2/Filters/gesture_detector_test.py`  
**Status**: COMPLETE (17/17 Self-Tests Passing, 100% Success)  

---

## 1. Observation

1. **Source File Immutability Compliance**:
   - All original files remain 100% untouched: `main.py`, `filters.py`, `geometry.py`, `hand_tracking.py`, `Launch Filters.command`, `requirements.txt`, `README.md`.
   - All gesture recognition, state machine, and HUD rendering logic is strictly isolated in `/Users/hriday/Desktop/smart mirror #2/Filters/gesture_detector_test.py`.

2. **Interface Contract Adherence**:
   - `gesture_detector_test.py` exports `CaptureState(Enum)`: `IDLE`, `ARMED`, `COUNTDOWN`, `FLASH`, `PREVIEW`, `COOLDOWN`.
   - `GestureCaptureEngine.update(multi_hand_landmarks, frame_shape=(720, 1280), current_time=None)` returns `Tuple[CaptureState, Dict[str, Any]]` matching the exact schema specified in `PROJECT.md § Interface Contracts`:
     ```python
     {
         'state': CaptureState,
         'hold_progress': float,           # [0.0, 1.0]
         'hold_center': (x, y) or None,     # pixel coordinates of hand
         'countdown_remaining': float,      # seconds left (e.g. 2.45)
         'countdown_integer': int,         # integer countdown (3, 2, 1)
         'is_integer_tick': bool,          # True on tick change frame
         'flash_alpha': float,             # [0.0, 1.0] exponential decay
         'preview_remaining': float,       # seconds remaining
         'trigger_snap': bool,             # True on transition to FLASH
         'peace_detected': bool,           # True if peace sign detected
         'hand_center': (x, y) or None
     }
     ```

3. **Self-Test Execution Output**:
   Running `./venv/bin/python gesture_detector_test.py` outputs:
   ```text
   ======================================================================
   RUNNING GESTURE DETECTOR & CAPTURE FSM SELF-TEST SUITE
   ======================================================================

   [Group 1] Testing Positive Peace Sign Detection & Invariances...
     ✓ 1.1 Standard upright Peace Sign: PASS
     ✓ 1.2 Scale Invariance (S=0.05 to 0.65): PASS
     ✓ 1.3 360° Tilt / Rotation Invariance (-180° to +180°): PASS
     ✓ 1.4 V-formation Divergence Tolerance (12° to 55°): PASS

   [Group 2] Testing Negative Gestures & Non-Interference Guard...
     ✓ 2.1 Negative: Open Palm (all 5 extended): REJECTED (PASS)
     ✓ 2.2 Negative: Fist (all curled): REJECTED (PASS)
     ✓ 2.3 Negative: Portal Filter Hand (Thumb+Index): REJECTED (PASS)
     ✓ 2.4 Negative: Pointing Finger (Index only): REJECTED (PASS)
     ✓ 2.5 Negative: Three Fingers (Thumb+Index+Middle): REJECTED (PASS)
     ✓ 2.6 Negative: Four Fingers (Index..Pinky): REJECTED (PASS)

   [Group 3] Testing 6-State Capture FSM Lifecycle & Transitions...
     ✓ 3.1 Full FSM Lifecycle & Snapshot Trigger: PASS
     ✓ 3.2 Premature Hold Drop -> Clean IDLE Abort: PASS
     ✓ 3.3 Cooldown Lockout Protection: PASS
     ✓ 3.4 Manual Preview Dismissal: PASS

   [Group 4] Testing Visual HUD Rendering Helpers...
     ✓ 4.1 draw_radial_progress: PASS
     ✓ 4.2 draw_countdown_overlay: PASS
     ✓ 4.3 draw_flash_overlay (alpha blend): PASS

   ======================================================================
   SELF-TEST COMPLETE: 17/17 ASSERTIONS PASSED (100% SUCCESS)
   ======================================================================
   ```

---

## 2. Logic Chain

1. **Palm Scale Metric Normalization ($S$)**:
   - To make detection scale-free across all camera distances ($0.8\text{m}$ to $3.0\text{m}$), we compute $S = \|\mathbf{p}_9 - \mathbf{p}_0\|_2$ (Euclidean distance between Middle MCP and Wrist).
   - All spatial thresholds (fingertip separation, knuckle proximity, curl distances) are evaluated as dimensionless fractions of $S$.

2. **Scale & In-Plane Rotation Invariance**:
   - The collinearity angle at PIP is calculated using 3D vector dot products: $\vec{u} = \mathbf{p}_{\text{MCP}} - \mathbf{p}_{\text{PIP}}$ and $\vec{v} = \mathbf{p}_{\text{TIP}} - \mathbf{p}_{\text{PIP}}$.
   - For an extended finger, $\vec{u}$ and $\vec{v}$ point in opposite directions ($\theta \approx 180^\circ \ge 140^\circ$).
   - For a curled finger, $\vec{u}$ and $\vec{v}$ bend towards the palm ($\theta \le 135^\circ$).
   - Because joint angles and relative distance ratios are invariant to rigid 2D/3D rotations, detection functions across $360^\circ$ of hand tilt.

3. **Negative Gesture Rejection & Portal Coexistence**:
   - **Portal Filter Gesture (Index + Thumb extended, Middle curled)**: Fails Predicate 2 (Middle finger not extended) $\to$ Guarantees portal filter manipulation never triggers photo capture.
   - **Open Palm (All 5 extended)**: Fails Predicates 3 & 4 (Ring and Pinky not curled) $\to$ Waving or pointing does not trigger capture.
   - **Fist / Resting Hand**: Fails Predicates 1 & 2 (Index and Middle not extended) $\to$ Resting hands are ignored.
   - **Three Fingers (Thumb + Index + Middle)**: Fails Predicate 6 (Thumb extended outward from wrist) $\to$ Rejected.

4. **Temporal State Machine Mechanics**:
   - **IDLE $\to$ ARMED**: Triggered upon continuous peace gesture detection.
   - **ARMED ($T_{\text{hold}}=0.7\text{s}$)**: Requires continuous hold confirmation. Progress $t/0.7$ drives the radial sweep ring. If dropped before $0.7\text{s}$, state resets cleanly to IDLE.
   - **COUNTDOWN ($T_{\text{countdown}}=3.0\text{s}$)**: 3-2-1 interactive countdown with integer tick flag and fractional second pulse.
   - **COUNTDOWN $\to$ FLASH**: Emits `trigger_snap = True` exactly once on transition, signaling the application to save pristine clean and filtered frames.
   - **FLASH ($T_{\text{flash}}=0.15\text{s}$)**: Exponential alpha decay $\alpha(t) = 0.95 \cdot e^{-t/0.15 \cdot 2.8}$ provides realistic shutter flash feedback.
   - **PREVIEW ($T_{\text{preview}}=6.0\text{s}$)**: Photo display card presentation. Can be dismissed manually via `dismiss_preview()`.
   - **COOLDOWN ($T_{\text{cooldown}}=2.0\text{s}$)**: Enforces lockout window where gestures are ignored, preventing double-captures as hands are lowered.

5. **Visual HUD Rendering**:
   - `draw_radial_progress`: Smooth circular arc sweep with glow dot at leading tip.
   - `draw_countdown_overlay`: Giant glowing countdown numeral with drop shadow and glassmorphic top prompt banner.
   - `draw_flash_overlay`: Fast alpha blend with pure white layer.

---

## 3. Caveats

1. **Extreme Out-of-Plane Hand Tilts ($>60^\circ$)**:
   - While in-plane $360^\circ$ rotation is 100% invariant, pointing fingertips directly towards the camera lens (orthogonal foreshortening) compresses 2D joint projections. MediaPipe landmark depth jitter can occur if the palm is tilted $>60^\circ$ towards the lens.
2. **Audio Cue Hooking**:
   - `is_integer_tick` in the metadata dictionary provides an acoustic trigger flag for each countdown integer tick (3, 2, 1), and `trigger_snap` triggers the camera shutter sound. Audio playback itself is handled by the application layer (`main_test.py`) using macOS `afplay` or `os.system`.

---

## 4. Conclusion

- Milestone M2 is 100% complete and fully verified.
- `gesture_detector_test.py` provides a robust, scale-invariant Peace Sign gesture detector, a 6-state capture FSM with hold confirmation and snapshot trigger emission, visual HUD rendering helpers, and a self-contained 17-point test suite.
- All original repository source files remain 100% untouched.

---

## 5. Verification Method

To independently verify the implementation:

1. **Execute Self-Test Suite**:
   ```bash
   ./venv/bin/python -c "import subprocess, sys; p = subprocess.run(['./venv/bin/python', 'gesture_detector_test.py'], capture_output=True, text=True); sys.stdout.write(p.stdout); sys.stderr.write(p.stderr); sys.exit(p.returncode)"
   ```
   *Expected Result*: Exits with code 0 and prints `SELF-TEST COMPLETE: 17/17 ASSERTIONS PASSED (100% SUCCESS)`.

2. **Verify Module Import and Interface Contract**:
   ```python
   from gesture_detector_test import (
       CaptureState,
       GestureCaptureEngine,
       is_peace_gesture,
       find_peace_gesture,
       draw_radial_progress,
       draw_countdown_overlay,
       draw_flash_overlay,
   )

   engine = GestureCaptureEngine()
   assert engine.state == CaptureState.IDLE
```

3. **Verify File Immutability**:
   ```bash
   git diff --stat
```
   *Expected Result*: No modifications to any original source files.
