# Adversarial Challenger Handoff Report — Challenger 1

**Author**: Challenger 1 (Empirical Challenger Agent)  
**Target Scope**: Gesture Detection Engine & Capture State Machine (`gesture_detector_test.py`, `main_test.py`, `delivery_server_test.py`)  
**Verdict**: **REQUEST_CHANGES** (2 Minor but High-Impact Defects Discovered & Empirically Confirmed)  
**Immutability Audit**: **100% UNTOUCHED (SHA-256 Verified)**  

---

## 1. Observation

Adversarial stress-testing was executed via the dedicated test harness `tests/test_adversarial_challenger.py` across 20 empirical stress vectors.

### Finding 1: Relative Timebase Zero Falsiness Bug in `GestureCaptureEngine`
- **Location**: `gesture_detector_test.py`, lines 423, 441, 459, 471, 479:
  ```python
  423: elapsed = now - (self.hold_start_time or now)
  441: elapsed = now - (self.countdown_start_time or now)
  459: elapsed = now - (self.flash_start_time or now)
  471: elapsed = now - (self.preview_start_time or now)
  479: elapsed = now - (self.cooldown_start_time or now)
  ```
- **Observed Behavior**:
  When a test harness, video stream, or relative clock provides `current_time = 0.0` at the start of a gesture hold:
  `self.hold_start_time = 0.0` is saved.
  In Python, `bool(0.0) is False`, so `(0.0 or now)` evaluates to `now`.
  Consequently, `elapsed = now - now = 0.0` on every subsequent frame regardless of `now` increasing (e.g. `now = 0.71s`).
  The FSM remains permanently frozen in `CaptureState.ARMED` and never transitions to `COUNTDOWN`.
- **Verbatim Error**:
  ```
  AssertionError: <CaptureState.ARMED: 'ARMED'> != <CaptureState.COUNTDOWN: 'COUNTDOWN'>
  ```

### Finding 2: Missing NaN / Inf / Finite Check in `is_peace_gesture()`
- **Location**: `gesture_detector_test.py`, lines 142-167 (`is_peace_gesture` and `_extract_landmark_points`)
- **Observed Behavior**:
  When corrupt landmark data containing `NaN`, `+Inf`, `-Inf`, or large floating point values ($10^{308}$) in intermediate unreferenced joints (`THUMB_CMC` (1), `THUMB_IP` (3), `INDEX_DIP` (7), `MIDDLE_DIP` (11), `RING_DIP` (15), `PINKY_DIP` (19)) is passed to `is_peace_gesture()`, the function fails to reject the array and returns `True`.
  Furthermore, passing large floats or infinities produces runtime divide/overflow warnings:
  ```
  RuntimeWarning: overflow encountered in dot
  RuntimeWarning: invalid value encountered in scalar divide
  ```

### Finding 3: Cryptographic Immutability of Original Files (Verified)
- Pre- and post-test SHA-256 hashes of all 7 original source files:
  | File | SHA-256 Checksum | Status |
  | :--- | :--- | :---: |
  | `main.py` | `050357ed1349451c5862f12f028f1fc31f65ff7b04cfe300843584af59004243` | **UNTOUCHED** |
  | `filters.py` | `91fbc360dc23de27c10b98655c7fc8cf47fad03c2badc60f9844c45d2a2fdcf9` | **UNTOUCHED** |
  | `geometry.py` | `e1b0d649d3a0d270d2a9bdc8c5109bcb6c323d47f42677b1bd26cbaf888bde3c` | **UNTOUCHED** |
  | `hand_tracking.py` | `0940d1f4350425c15dcd186e0acfe4e108dce748a1b2ff552c8caa2c61d3771e` | **UNTOUCHED** |
  | `Launch Filters.command` | `5db63ee1c60b7e6b1102081376dcd5f6b1e4e7673c56696e371c567565a8d48d` | **UNTOUCHED** |
  | `requirements.txt` | `c5bcfe66bb57624d8f115df3d3b4b8e95d9373298308b78698c22b4b8706ee5b` | **UNTOUCHED** |
  | `README.md` | `7fadbe289a2e05d822b92df9719bbfa8e84c28b1aa74f6a7598e04c695e90543` | **UNTOUCHED** |

---

## 2. Logic Chain

1. **Premise 1**: The gesture capture engine accepts `current_time: Optional[float] = None` to allow simulation, custom timestamps, and offline video processing.
2. **Premise 2**: When a simulation starts at time $t = 0.0$, `self.hold_start_time` is assigned `0.0`.
3. **Step 1**: In Python, `(0.0 or now)` evaluates to `now` because `0.0` is falsy.
4. **Step 2**: On subsequent calls at $t = 0.71$, `elapsed = now - (self.hold_start_time or now)` evaluates to `0.71 - (0.0 or 0.71) = 0.71 - 0.71 = 0.0`.
5. **Step 3**: Because `elapsed` remains `0.0`, `elapsed >= self.hold_duration (0.7)` is never satisfied, causing the FSM to freeze in `ARMED`.
6. **Inference 1**: The expression must be replaced with `(self.hold_start_time if self.hold_start_time is not None else now)` across all 5 FSM transition states.
7. **Premise 3**: MediaPipe landmark arrays may occasionally contain corrupted sensor readings (e.g. `NaN`, `Inf`) when hands partially leave the field of view or sensors experience packet loss.
8. **Step 4**: `is_peace_gesture()` inspects specific indices (0, 4, 5, 6, 8, 9, 10, 12, 13, 14, 16, 17, 18, 20) but leaves indices (1, 3, 7, 11, 15, 19) unchecked.
9. **Step 5**: When NaNs or Infinities reside in unreferenced indices, calculations do not throw exceptions, but NumPy emits divide-by-zero / overflow warnings and the corrupted array falsely returns `True`.
10. **Inference 2**: An explicit guard `if not np.isfinite(pts).all(): return False` must be added at the top of `is_peace_gesture()`.

---

## 3. Caveats

- In production running with `time.time()`, timestamps are epoch seconds (~1.7e9), which are truthy (`> 0.0`), meaning Bug 1 does not manifest on standard system clocks, but strictly impairs deterministic test runners, simulators, video file feeds, and relative timebases.
- The original source files are 100% untouched and isolated.
- The changes required are strictly isolated to `gesture_detector_test.py`.

---

## 4. Conclusion & Recommended Action

**Verdict**: **REQUEST_CHANGES**

### Actionable Fixes:
1. In `gesture_detector_test.py`, add finite array validation in `is_peace_gesture`:
   ```python
   # After extracting pts:
   if not np.isfinite(pts).all():
       return False
   ```
2. In `gesture_detector_test.py`, replace `(self.<state>_start_time or now)` with explicit `None` checks:
   - Line 423: `elapsed = now - (self.hold_start_time if self.hold_start_time is not None else now)`
   - Line 441: `elapsed = now - (self.countdown_start_time if self.countdown_start_time is not None else now)`
   - Line 459: `elapsed = now - (self.flash_start_time if self.flash_start_time is not None else now)`
   - Line 471: `elapsed = now - (self.preview_start_time if self.preview_start_time is not None else now)`
   - Line 479: `elapsed = now - (self.cooldown_start_time if self.cooldown_start_time is not None else now)`

---

## 5. Verification Method

To independently verify these findings and confirm the fix:

```bash
# 1. Run the empirical adversarial challenger suite
./venv/bin/python -m unittest tests/test_adversarial_challenger.py

# 2. Verify all 4 tiers of existing test suite continue to pass
./venv/bin/python tests/test_runner.py

# 3. Verify cryptographic hash immutability
./venv/bin/python -c '
import hashlib
for f in ["main.py", "filters.py", "geometry.py", "hand_tracking.py", "Launch Filters.command", "requirements.txt", "README.md"]:
    print(f, hashlib.sha256(open(f, "rb").read()).hexdigest())
'
```
