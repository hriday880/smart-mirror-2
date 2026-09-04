# Survey Explorer 3 Report: Fair Delivery, Environment Isolation & Automated Verification Architecture

**Author**: Survey Explorer 3 (Fair Delivery & Isolation Explorer)  
**Date**: 2026-08-14  
**Target Milestone**: Phase 0 — Survey & Scope Mapping  
**Working Directory**: `/Users/hriday/Desktop/smart mirror #2/Filters/.agents/survey_explorer_3`  
**Output Report**: `/Users/hriday/Desktop/smart mirror #2/Filters/.agents/survey_explorer_3/handoff.md`  

---

## 1. Observation

### 1.1 Existing Codebase & Execution Environment
Direct empirical inspection of the workspace `/Users/hriday/Desktop/smart mirror #2/Filters` reveals the following environment characteristics:

1. **Python Environment & Dependencies**:
   - Python Version: `Python 3.12.13`
   - Installed Core Packages:
     - `opencv-python` / `opencv-contrib-python`: `5.0.0.93`
     - `mediapipe`: `0.10.14`
     - `numpy`: `2.5.2`
     - `pillow`: `12.3.0`
   - `requirements.txt` contents (`requirements.txt:1-3`):
     ```text
     opencv-python
     mediapipe==0.10.14
     numpy
     ```

2. **OpenCV QR Code Capabilities**:
   - Running verification check on OpenCV `5.0.0.93` confirmed that `cv2.QRCodeEncoder` and `cv2.QRCodeDetector` are natively built-in and fully functional without requiring external packages:
     ```python
     encoder = cv2.QRCodeEncoder_create()
     qr_mat = encoder.encode("http://192.168.1.50:8000/photo.jpg")
     # Output: QR shape (37, 37), uint8 [0, 255]
     detector = cv2.QRCodeDetector()
     decoded_url, points, _ = detector.detectAndDecode(qr_bgr)
     # Verified: 100% roundtrip string match
     ```

3. **Existing Launcher Inspection (`Launch Filters.command:1-5`)**:
   ```bash
   #!/bin/bash
   cd "$(dirname "$0")"
   source venv/bin/activate
   python main.py
   ```
   - *Findings*:
     - The launcher is a simple POSIX bash shell script executed by macOS `Terminal.app`.
     - `cd "$(dirname "$0")"` safely handles paths with whitespace (e.g. `/Users/hriday/Desktop/smart mirror #2/Filters`).
     - Relies on local virtualenv `venv/bin/activate`.
     - Directly invokes `python main.py`.

4. **Original Source Files Immutability Target (`ORIGINAL_REQUEST.md:14-19`)**:
   - `main.py` (76 lines: core video capture loop, MediaPipe tracking, portal rendering, `cv2.imshow(" ", frame)`).
   - `geometry.py` (61 lines: `portal_width`, `ClosingGestureDetector`, `paint_filter_in_polygon`, `render_portal`).
   - `hand_tracking.py` (29 lines: landmark index constants, `_dist`, `get_extended_fingers`).
   - `filters.py` (117 lines: 8 visual effects in `FILTROS`).
   - `Launch Filters.command` (5 lines).
   - `requirements.txt` (3 lines).
   - `README.md` (97 lines).

---

## 2. Logic Chain

### 2.1 Fair-Ready Delivery Workflow Architecture (R2)

In a fast-paced fair environment, physical interaction (touching keyboards, mice, or touchscreens) is slow, unhygienic, and creates bottlenecks. The entire delivery lifecycle must be **100% contactless, automated, and instant**.

```
   ┌──────────────────────────────────────────────────────────────────────────────────────────┐
   │                                  FAIR DELIVERY LIFECYCLE                                 │
   └──────────────────────────────────────────────────────────────────────────────────────────┘
                                                │
   1. TRIGGER CAPTURE                           ▼
   ┌──────────────────────────────────────────────────────────────────────────────────────────┐
   │ • Peace Gesture (✌️) held for 0.7s -> 3-2-1 Countdown -> 150ms Screen Flash              │
   │ • Pristine Filtered Frame Buffer captured in memory                                     │
   └──────────────────────────────────────────────────────────────────────────────────────────┘
                                                │
   2. ASYNC LOCAL PERSISTENCE                   ▼
   ┌──────────────────────────────────────────────────────────────────────────────────────────┐
   │ • Dispatched to background I/O thread (zero camera loop stutter)                         │
   │ • Target path: `captures/photo_YYYYMMDD_HHMMSS_<filter>.jpg`                             │
   │ • Quality: JPEG Quality 95 (`cv2.IMWRITE_JPEG_QUALITY, 95`)                              │
   └──────────────────────────────────────────────────────────────────────────────────────────┘
                                                │
   3. BACKGROUND HTTP DELIVERY SERVER           ▼
   ┌──────────────────────────────────────────────────────────────────────────────────────────┐
   │ • Lightweight `http.server.ThreadingHTTPServer` running on background daemon thread      │
   │ • Dynamically discovers LAN IP (Wi-Fi router or Mac Local Hotspot, e.g. 192.168.1.42)   │
   │ • Port: 8000 (auto-fallback to 8001-8020 if port in use)                                 │
   │ • Endpoints:                                                                             │
   │   - `GET /photo/<filename>` -> Binary JPEG stream (`image/jpeg`)                         │
   │   - `GET /latest`           -> Redirects / serves latest captured photo                  │
   │   - `GET /view/<filename>`   -> Responsive Mobile Web Landing Page (1-tap Save & Share)  │
   └──────────────────────────────────────────────────────────────────────────────────────────┘
                                                │
   4. ZERO-DEPENDENCY QR ENCODING               ▼
   ┌──────────────────────────────────────────────────────────────────────────────────────────┐
   │ • Encodes URL (`http://<LAN_IP>:<PORT>/view/<filename>`) using `cv2.QRCodeEncoder`       │
   │ • Rescaled with nearest-neighbor interpolation (`cv2.INTER_NEAREST`) + quiet zone border │
   └──────────────────────────────────────────────────────────────────────────────────────────┘
                                                │
   5. HEADS-UP DISPLAY (HUD) PREVIEW CARD       ▼
   ┌──────────────────────────────────────────────────────────────────────────────────────────┐
   │ • Sleek translucent card overlaid on bottom-right/top-right mirror screen                │
   │ • Displays: Thumbnail Preview + QR Code + Dynamic Countdown Bar + Local URL              │
   │ • Fairgoer points phone camera at mirror screen -> Opens photo page instantly            │
   └──────────────────────────────────────────────────────────────────────────────────────────┘
                                                │
   6. AUTO-DISMISS & MIRROR RESUMPTION          ▼
   ┌──────────────────────────────────────────────────────────────────────────────────────────┐
   │ • Displays for 6.0 seconds -> Smooth alpha fade-out                                      │
   │ • Mirror returns to interactive filter mode instantly                                     │
   │ • 2.0s Debounce Cooldown prevents accidental re-capture while lowering hands             │
   └──────────────────────────────────────────────────────────────────────────────────────────┘
```

#### 2.1.1 Local Photo Storage Specification
- **Directory**: `captures/` (created automatically on startup via `os.makedirs("captures", exist_ok=True)`).
- **Naming Pattern**: `capture_YYYYMMDD_HHMMSS_{filter_index}.jpg` (e.g. `capture_20260814_165201_grid.jpg`).
  - Optional millisecond suffix to guarantee collision resistance: `datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]`.
- **Quality & Format**:
  - Format: Standard JPEG (`.jpg`).
  - Optimization parameter: `[cv2.IMWRITE_JPEG_QUALITY, 95]` (optimal balance between visual fidelity and small payload ~250-400 KB for rapid phone download over local Wi-Fi).
- **Buffer Layering Discipline**:
  - Saved photo contains **only** the user + active filter portal.
  - Saves **zero** countdown numbers, landmark wireframes, or HUD overlays.

#### 2.1.2 Dynamic LAN IP Discovery & Zero-Config Networking
In a fair environment, the host laptop may be connected to venue Wi-Fi, a portable 4G/5G mobile hotspot router, or broadcasting its own macOS local Wi-Fi hotspot (`Internet Sharing` or `Create Network`).

```python
import socket

def get_local_ip() -> str:
    """
    Determines the active LAN IPv4 address reachable by other devices on the same Wi-Fi.
    Uses UDP route discovery to probe default gateway without sending actual packets.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
    finally:
        s.close()
    return ip
```

#### 2.1.3 Lightweight Built-in HTTP Delivery Server
To avoid heavyweight external frameworks (`Flask`, `FastAPI`, `uvicorn`), the delivery subsystem uses Python standard library `http.server.ThreadingHTTPServer`.

- **Key Server Features**:
  1. **Non-Blocking Background Execution**: Runs inside a `threading.Thread(target=server.serve_forever, daemon=True)`.
  2. **Port Auto-Selection**: Tries port `8000`, scanning sequentially up to `8020` if `8000` is bound.
  3. **Direct Image Endpoint**: `GET /photo/<filename>` serves raw JPEG stream.
  4. **Latest Shortcut Endpoint**: `GET /latest` serves or redirects to the most recently captured image.
  5. **Mobile Landing Webpage (`GET /` or `GET /view/<filename>`)**:
     - Serves an ultra-lightweight, responsive HTML5/CSS page formatted specifically for mobile screens.
     - Features:
       - Large centered photo preview.
       - Prominent **"Save Photo to Phone"** button utilizing `<a href="/photo/..." download="...">`.
       - Native Mobile Share button using JavaScript `navigator.share()` API (iOS Safari / Android Chrome).
       - Smart Mirror Fair branding and timestamp.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Smart Mirror Photo</title>
  <style>
    body { background: #0f172a; color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; text-align: center; margin: 0; padding: 20px; }
    .card { background: #1e293b; border-radius: 16px; padding: 16px; max-width: 480px; margin: 0 auto; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
    img { width: 100%; border-radius: 12px; display: block; margin-bottom: 16px; }
    .btn { display: block; background: #3b82f6; color: white; text-decoration: none; padding: 14px; border-radius: 10px; font-weight: 600; font-size: 16px; margin: 8px 0; border: none; cursor: pointer; }
    .btn-share { background: #10b981; }
  </style>
</head>
<body>
  <div class="card">
    <h2>✨ Your Smart Mirror Photo ✨</h2>
    <img src="/photo/{FILENAME}" alt="Smart Mirror Capture">
    <a href="/photo/{FILENAME}" download="{FILENAME}" class="btn">📥 Save Photo</a>
    <button onclick="sharePhoto()" class="btn btn-share">📤 Share Photo</button>
  </div>
  <script>
    function sharePhoto() {
      if (navigator.share) {
        navigator.share({ title: 'My Smart Mirror Photo', url: window.location.href });
      }
    }
  </script>
</body>
</html>
```

#### 2.1.4 QR Code Generator Dependency Evaluation

| Solution | External Pip Dependencies | Generation Latency | Integration Complexity | Reliability / Portability | Evaluation Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **OpenCV Built-in (`cv2.QRCodeEncoder`)** | **None (0 dependencies)**<br>Built into OpenCV 4.5.4+ (v5.0 in venv) | **< 1.0 ms**<br>Direct C++ matrix encoding | **Very Low**<br>Native `numpy.ndarray` output, easy resize via `cv2.INTER_NEAREST` | **Exceptional**<br>Guaranteed to match OpenCV environment | **10/10 (Primary Engine)** |
| **`qrcode` (`python-qrcode`)** | Requires `qrcode` + `Pillow` | ~ 5-10 ms | Moderate (PIL $\to$ NumPy BGR conversion) | High (requires pip install) | **8/10 (Secondary Fallback)** |
| **`segno`** | Requires `segno` | ~ 3-5 ms | Moderate | High (requires pip install) | **7.5/10 (Alternative)** |
| **Pure Python Micro-Encoder** | **None (0 dependencies)** | ~ 2-5 ms | Moderate (custom module file) | High (standalone code) | **8.5/10 (Self-Contained Fallback)** |

**Recommendation**: Use **`cv2.QRCodeEncoder`** as the primary encoder. It produces pristine pixel-sharp QR matrices with zero additional package installations.

#### 2.1.5 HUD Preview Card & Touchless Dismissal
- **Layout & Visual Composition**:
  - Rendered in corner or lower quadrant of the mirror display.
  - Rounded semi-transparent dark container (`cv2.rectangle` with alpha blend `0.85`).
  - Scaled thumbnail of captured photo (e.g. 180x135 px).
  - High-contrast QR code with white margin (e.g. 160x160 px).
  - Countdown progress bar and timer badge: `"Scan with phone camera! [ 5s ]"`.
- **Auto-Dismissal & Debounce**:
  - Fixed display duration: $T_{\text{display}} = 6.0\text{s}$.
  - During display, the background video and filter continue rendering.
  - Smooth 0.3s alpha fade-out at expiry.
  - Followed by a $2.0\text{s}$ cooldown lockout to avoid immediate accidental re-triggering.

---

### 2.2 Test Environment Isolation Architecture (R3 & R4)

#### 2.2.1 Original Files Immutability Contract (R3)
The original project codebase must remain 100% untouched.

| Original File | Status | Access Pattern from Test Suite |
| :--- | :--- | :--- |
| `main.py` | **Read-Only / Untouched** | Baseline reference |
| `filters.py` | **Read-Only / Untouched** | Imported as `from filters import FILTROS` |
| `geometry.py` | **Read-Only / Untouched** | Imported as `from geometry import render_portal, portal_width, ClosingGestureDetector, paint_filter_in_polygon` |
| `hand_tracking.py` | **Read-Only / Untouched** | Imported as `from hand_tracking import INDEX_TIP, THUMB_TIP, WRIST, ...` |
| `Launch Filters.command` | **Read-Only / Untouched** | Baseline launcher reference |
| `requirements.txt` | **Read-Only / Untouched** | Untouched |
| `README.md` | **Read-Only / Untouched** | Untouched |

#### 2.2.2 Isolated Test Architecture & Companion Modules
All new functionality is implemented cleanly in dedicated test files:

```
Filters/
├── main.py                     <-- UNTOUCHED original app
├── filters.py                  <-- UNTOUCHED original filters
├── geometry.py                 <-- UNTOUCHED original geometry
├── hand_tracking.py            <-- UNTOUCHED original tracking
├── Launch Filters.command      <-- UNTOUCHED original launcher
│
├── main_test.py                <-- [NEW] Augmented test application (Capture + Delivery + HUD)
├── gesture_detector_test.py    <-- [NEW] Isolated robust gesture recognition engine
├── delivery_server_test.py     <-- [NEW] Isolated HTTP delivery & QR overlay engine
├── test.command                <-- [NEW] macOS double-clickable launcher
└── tests/
    ├── test_gesture_isolated.py<-- [NEW] Unit tests for gesture logic
    ├── test_delivery_server.py <-- [NEW] Unit tests for HTTP server & QR generator
    └── test_headless_e2e.py    <-- [NEW] Headless full-loop simulation test
```

#### 2.2.3 macOS Double-Clickable Launcher Specification (`test.command` / R4)

macOS `.command` files require specific shell handling to support double-click launching from Finder:

```bash
#!/bin/bash
# ==============================================================================
# Smart Mirror Photo Capture - Test Environment Launcher
# macOS Double-Clickable Shell Script
# ==============================================================================

# 1. Resolve repository root directory (handles spaces in path cleanly)
cd "$(dirname "$0")" || { echo "Failed to navigate to script directory"; exit 1; }

# 2. Display startup banner
echo "======================================================"
echo "  Smart Mirror Hand Gesture Photo Capture (Test Mode)"
echo "======================================================"
echo "Working Directory: $(pwd)"

# 3. Locate and activate Python virtual environment
if [ -f "venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
elif [ -f "../venv/bin/activate" ]; then
    echo "Activating parent virtual environment..."
    source ../venv/bin/activate
else
    echo "[WARNING] Virtual environment 'venv' not found. Using system python3."
fi

# 4. Verify Python and OpenCV availability
PYTHON_BIN=$(which python3 || which python)
echo "Using Python: $PYTHON_BIN"

# 5. Launch test application
echo "Starting main_test.py..."
python main_test.py "$@"
EXIT_CODE=$?

# 6. Graceful exit handling on error
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "[ERROR] Application exited with code $EXIT_CODE."
    echo "Press [Enter] to close this window..."
    read -r
fi

exit $EXIT_CODE
```

**Key Execution Requirements**:
1. File permissions: `chmod 755 test.command` (`chmod +x`).
2. Robust directory changing: `cd "$(dirname "$0")"` preserves relative paths regardless of where macOS Finder launches the script.
3. Interactive error hold: `read -r` prevents Terminal from instantly closing on crash, allowing developers to inspect tracebacks.

---

### 2.3 Headless / Automated Verification Architecture

Testing a computer vision application that relies on a physical webcam, MediaPipe ML models, and human hand gestures requires a **Headless Mocking Strategy** for automated CI/CD and unit testing.

```
   ┌──────────────────────────────────────────────────────────────────────────────────────────┐
   │                         HEADLESS VERIFICATION TEST HARNESS                               │
   └──────────────────────────────────────────────────────────────────────────────────────────┘
                                                │
   1. MOCK VIDEO STREAM                         ▼
   ┌──────────────────────────────────────────────────────────────────────────────────────────┐
   │ • `MockVideoCapture`: Yields synthetic 640x480 BGR frames                                │
   │ • Programmable frame counter (terminates cleanly after N frames)                          │
   └──────────────────────────────────────────────────────────────────────────────────────────┘
                                                │
   2. SYNTHETIC MEDIA PIPE LANDMARK INJECTION   ▼
   ┌──────────────────────────────────────────────────────────────────────────────────────────┐
   │ • `MockHandLandmarks`: Generates exact normalized 21-point MediaPipe landmark sets       │
   │ • Vectors: Peace Sign (✌️), Portal Hands, Open Palm (🖐️), Fist (✊), No Hands          │
   └──────────────────────────────────────────────────────────────────────────────────────────┘
                                                │
   3. TEMPORAL STATE MACHINE SIMULATION         ▼
   ┌──────────────────────────────────────────────────────────────────────────────────────────┐
   │ • Feed 25 frames of Peace Sign -> Verifies hold time threshold (0.7s)                     │
   │ • Feed 90 frames of Countdown  -> Verifies 3-2-1 timer progression                       │
   │ • Verify Flash trigger & Snapshot save callback                                          │
   │ • Feed 60 frames of Preview    -> Verifies QR overlay rendering and auto-dismiss         │
   └──────────────────────────────────────────────────────────────────────────────────────────┘
                                                │
   4. AUTOMATED HTTP & QR VERIFICATION          ▼
   ┌──────────────────────────────────────────────────────────────────────────────────────────┐
   │ • `urllib.request` performs `GET /photo/<filename>` & `GET /latest`                      │
   │ • Asserts HTTP 200 OK & binary checksum equality with saved file                         │
   │ • `cv2.QRCodeDetector` extracts & decodes QR code from preview frame                     │
   │ • Asserts decoded URL matches server host/port exactly                                   │
   └──────────────────────────────────────────────────────────────────────────────────────────┘
```

#### 2.3.1 Synthetic Landmark Generators
```python
class MockLandmark:
    def __init__(self, x: float, y: float, z: float = 0.0):
        self.x = x
        self.y = y
        self.z = z

class MockLandmarkList:
    def __init__(self, landmarks):
        self.landmark = landmarks

def create_synthetic_hand(gesture: str = "peace", wrist=(0.5, 0.8)) -> MockLandmarkList:
    """Generates a synthetic 21-landmark MediaPipe hand structure."""
    wx, wy = wrist
    if gesture == "peace":
        coords = {
            0: (wx, wy),
            1: (0.45, 0.72), 2: (0.43, 0.65), 3: (0.45, 0.60), 4: (0.50, 0.58), # Thumb tucked
            5: (0.48, 0.50), 6: (0.48, 0.40), 7: (0.48, 0.30), 8: (0.48, 0.20), # Index extended
            9: (0.52, 0.50), 10: (0.53, 0.40), 11: (0.54, 0.30), 12: (0.55, 0.20), # Middle extended
            13: (0.56, 0.52), 14: (0.56, 0.57), 15: (0.56, 0.62), 16: (0.56, 0.65), # Ring curled
            17: (0.60, 0.54), 18: (0.60, 0.58), 19: (0.60, 0.63), 20: (0.60, 0.66), # Pinky curled
        }
    elif gesture == "portal":
        coords = {
            0: (wx, wy),
            1: (0.45, 0.72), 2: (0.40, 0.65), 3: (0.35, 0.58), 4: (0.30, 0.50), # Thumb extended
            5: (0.48, 0.50), 6: (0.48, 0.40), 7: (0.48, 0.30), 8: (0.48, 0.20), # Index extended
            9: (0.52, 0.50), 10: (0.53, 0.55), 11: (0.54, 0.60), 12: (0.55, 0.65), # Middle curled
            13: (0.56, 0.52), 14: (0.56, 0.57), 15: (0.56, 0.62), 16: (0.56, 0.65), # Ring curled
            17: (0.60, 0.54), 18: (0.60, 0.58), 19: (0.60, 0.63), 20: (0.60, 0.66), # Pinky curled
        }
    else: # Open palm
        coords = {
            0: (wx, wy),
            1: (0.45, 0.72), 2: (0.40, 0.65), 3: (0.35, 0.58), 4: (0.30, 0.50),
            5: (0.48, 0.50), 6: (0.48, 0.40), 7: (0.48, 0.30), 8: (0.48, 0.20),
            9: (0.52, 0.50), 10: (0.52, 0.40), 11: (0.52, 0.30), 12: (0.52, 0.20),
            13: (0.56, 0.50), 14: (0.56, 0.40), 15: (0.56, 0.30), 16: (0.56, 0.20),
            17: (0.60, 0.50), 18: (0.60, 0.40), 19: (0.60, 0.30), 20: (0.60, 0.20),
        }
    return MockLandmarkList([MockLandmark(coords[i][0], coords[i][1]) for i in range(21)])
```

#### 2.3.2 Mock Video Capture Provider
```python
import numpy as np

class MockVideoCapture:
    def __init__(self, max_frames: int = 150, width: int = 640, height: int = 480):
        self.max_frames = max_frames
        self.current_frame = 0
        self.width = width
        self.height = height
        self._is_opened = True

    def isOpened(self) -> bool:
        return self._is_opened

    def read(self):
        if self.current_frame >= self.max_frames or not self._is_opened:
            return False, None
        self.current_frame += 1
        # Generate synthetic test frame
        frame = np.full((self.height, self.width, 3), 40, dtype=np.uint8)
        return True, frame

    def release(self):
        self._is_opened = False
```

---

## 3. Caveats

1. **Local Wi-Fi Network Subnet & Client Isolation**:
   - In some public fair venues, public Wi-Fi networks enable **Client Isolation** (preventing phones from talking to peer IP addresses on the same subnet).
   - *Mitigation*: The smart mirror should recommend using a local Mac Wi-Fi Hotspot or dedicated battery-powered travel router at the fair booth.
2. **Dynamic Port Conflicts**:
   - If port `8000` is in use by another service on the Mac, binding `8000` directly could fail.
   - *Mitigation*: Implement automatic port hopping (`8000` through `8020`) and bind to whatever port is freely available.
3. **macOS Gatekeeper & Terminal Permissions**:
   - First-time execution of `.command` scripts on macOS may require the execute bit `chmod +x test.command`.
   - Camera access permissions in macOS (`NSCameraUsageDescription`) apply to `Terminal.app` or `Python.app`.
4. **Daemon Thread Lifecycle**:
   - Background threads running `serve_forever` must be marked `daemon=True` so they do not block the Python process from exiting when the user presses `'q'`.

---

## 4. Conclusion

1. **Fair Delivery Architecture (R2)**:
   - **Persistence**: High-quality JPEG (`quality=95`) stored asynchronously in `captures/capture_YYYYMMDD_HHMMSS_<filter>.jpg` without blocking video processing.
   - **Delivery Server**: Built-in zero-dependency `http.server.ThreadingHTTPServer` running on a background daemon thread with automatic IP detection and port hopping.
   - **QR Code Engine**: Built-in `cv2.QRCodeEncoder_create()` generates instant QR codes without extra pip dependencies.
   - **HUD & Preview**: Overlay preview card with thumbnail, QR code, and 6.0s auto-dismiss timer + 2.0s cooldown lockout.
2. **Test Environment Isolation (R3 & R4)**:
   - Original files (`main.py`, `filters.py`, `geometry.py`, `hand_tracking.py`, `Launch Filters.command`, `requirements.txt`, `README.md`) remain 100% untouched.
   - All augmentations reside in `main_test.py`, `gesture_detector_test.py`, `delivery_server_test.py`, and `test.command`.
   - `test.command` provides double-click execution on macOS with robust path and venv resolution.
3. **Automated Verification Harness**:
   - `MockVideoCapture` and synthetic 21-point landmark generators enable 100% headless automated test coverage (`pytest`) for gesture recognition, state machine timing, disk persistence, QR generation, and HTTP downloads.

---

## 5. Verification Method

### 5.1 Independent Test Suite Verification
The complete test suite can be run using the project virtualenv:

```bash
# 1. Activate environment
source venv/bin/activate

# 2. Run unit and E2E headless tests
pytest tests/ -v
```

### 5.2 Specific Headless E2E Verification Script
Run the automated end-to-end simulation script:
```bash
python -m unittest discover -s tests -p "*_test.py"
```

### 5.3 Invalidation Conditions
- Any modification to original files (`git status` shows modifications to `main.py`, `filters.py`, `geometry.py`, `hand_tracking.py`, `Launch Filters.command`, `requirements.txt`).
- `test.command` failing to launch `main_test.py` when executed from Finder.
- HTTP server crashing or failing to serve the captured photo over LAN.
- QR code rendered on screen failing to decode with `cv2.QRCodeDetector()`.
- Video feed freezing or stuttering during photo capture and disk saving.
