# Project: Smart Mirror Hand Gesture Photo Capture

## Architecture
The Smart Mirror Hand Gesture Photo Capture system adds touchless photo booth capabilities to an existing OpenCV + MediaPipe smart mirror application, strictly isolated from production files.

```
                      ┌──────────────────────────────────────────────────────────┐
                      │                   CAMERA VIDEO STREAM                    │
                      └────────────────────────────┬─────────────────────────────┘
                                                   │
                                                   ▼
                      ┌──────────────────────────────────────────────────────────┐
                      │              MediaPipe Hands (max_num_hands=2)           │
                      └──────────────┬────────────────────────────┬──────────────┘
                                     │                            │
                     2-Hand Portal Landmarks             1/2-Hand Gesture Landmarks
                                     │                            │
                                     ▼                            ▼
                      ┌────────────────────────────┐┌────────────────────────────┐
                      │ geometry.py / filters.py   ││ gesture_detector_test.py   │
                      │ • Portal Geometry          ││ • Peace Sign Detection     │
                      │ • 8 Visual AR Filters      ││ • 6-State Capture FSM      │
                      └──────────────┬─────────────┘└─────────────┬──────────────┘
                                     │                            │
                                     │   ┌────────────────────────┘
                                     ▼   ▼
                      ┌──────────────────────────────────────────────────────────┐
                      │                      main_test.py                        │
                      │ • Pristine Filtered Frame Buffer Capture                 │
                      │ • Animated 3-2-1 Countdown & Shutter Flash               │
                      │ • Sound Effects & Visual Feedback HUD                    │
                      └──────────────┬────────────────────────────┬──────────────┘
                                     │                            │
                         Pristine Photo Buffer            Display Composite
                                     │                            │
                                     ▼                            ▼
                      ┌────────────────────────────┐┌────────────────────────────┐
                      │  delivery_server_test.py   ││         cv2.imshow         │
                      │  • Async JPEG Storage      ││  (Mirror Monitor UI)       │
                      │  • Background HTTP Server  │└────────────────────────────┘
                      │  • OpenCV QR Code HUD Card │
                      │  • Mobile Web Download Page│
                      └────────────────────────────┘
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | Test Environment Isolation | All new code resides in test files (`main_test.py`, `*_test.py`); original source files (`main.py`, `filters.py`, `geometry.py`, `hand_tracking.py`, `Launch Filters.command`, `requirements.txt`, `README.md`) remain 100% untouched. | M1 | ORIGINAL_REQUEST §R3 |
| F2 | macOS `test.command` Launcher | Executable double-clickable shell script with space-tolerant path resolution, venv activation, and graceful exit handling. | M1 | ORIGINAL_REQUEST §R4 |
| F3 | Scale-Invariant Peace Sign (✌️) Detection | 6-predicate geometric detector using joint angles and palm-scale metric $S=\|\mathbf{p}_9 - \mathbf{p}_0\|_2$, fully invariant to hand tilt, handedness, and distance. | M2 | ORIGINAL_REQUEST §R1 |
| F4 | Gesture Hold Confirmation & Radial Progress Ring | Debounce hold window ($T_{\text{hold}}=0.7\text{s}$) with glowing neon circular sweep progress HUD around hand. | M2 | Survey 2 |
| F5 | Animated 3-2-1 Countdown & Audio/Visual HUD | Pulsing numeric countdown overlay (3, 2, 1) over live interactive filter feed with acoustic tick cues. | M3 | Survey 2 |
| F6 | Shutter Flash Animation & Sound Feedback | 150ms exponential alpha decay screen flash overlay and audio shutter feedback. | M3 | Survey 2 |
| F7 | Pristine Layer-Separated Asynchronous Disk Saver | Separates clean filtered photo buffer from HUD overlay; saves high-quality JPEG (Q=95) in `captures/` without video stutter. | M3 | Survey 2, Survey 3 |
| F8 | Background LAN HTTP Delivery Server | Python `ThreadingHTTPServer` daemon with dynamic LAN IP discovery, auto-port hopping (8000-8020), `/photo/<filename>`, `/latest`, and responsive mobile HTML landing page. | M4 | ORIGINAL_REQUEST §R2 |
| F9 | Zero-Dependency OpenCV QR Code HUD Card | Built-in `cv2.QRCodeEncoder_create()` generates QR code rendered inside a semi-transparent HUD preview card on mirror. | M4 | ORIGINAL_REQUEST §R2 |
| F10 | Auto-Dismissal, Debounce Cooldown & Mirror Resumption | 6.0s auto-dismiss preview card with smooth fade-out and 2.0s cooldown lock-out before returning to live mirror mode. | M4 | ORIGINAL_REQUEST §R2 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Test Environment Isolation & `test.command` Launcher | Create `test.command` with full macOS execution permissions, verify virtualenv resolution, and verify original source file immutability. | none | DONE |
| M2 | Gesture Detection & Capture State Machine Engine | Implement `gesture_detector_test.py` with scale-invariant peace sign detection, hold-time tracking, and 6-state FSM. | none | DONE |
| M3 | Fair Delivery Server & QR Subsystem | Implement `delivery_server_test.py` with threaded HTTP server, dynamic IP discovery, mobile landing page, QR encoder, and HUD card renderer. | none | DONE |
| M4 | Augmented Test Application Integration | Implement `main_test.py` integrating camera loop, MediaPipe tracking, portal AR filters, gesture state machine, sound effects, and delivery HUD. | M1, M2, M3 | IN_PROGRESS |
| M-E2E | E2E Testing Suite Track | Independent test suite covering Tiers 1-4 in `tests/` with headless mocks, publishing `TEST_READY.md`. | none | IN_PROGRESS |
| M-Final | Final Integration & Adversarial Hardening | Pass 100% of E2E test suite (Tiers 1-4), execute Tier 5 adversarial stress testing, and pass Forensic Integrity Audit. | M4, M-E2E | PLANNED |

## Interface Contracts

### `gesture_detector_test.py` ↔ `main_test.py`
```python
class CaptureState(Enum):
    IDLE = "IDLE"
    ARMED = "ARMED"
    COUNTDOWN = "COUNTDOWN"
    FLASH = "FLASH"
    PREVIEW = "PREVIEW"
    COOLDOWN = "COOLDOWN"

class GestureCaptureEngine:
    def __init__(self, hold_duration: float = 0.7, countdown_duration: float = 3.0, preview_duration: float = 6.0, cooldown_duration: float = 2.0):
        ...
    def update(self, multi_hand_landmarks, frame_shape: Tuple[int, int]) -> Tuple[CaptureState, dict]:
        """
        Processes detected hands. Returns current state and metadata dict:
        {
            'state': CaptureState,
            'hold_progress': float [0.0, 1.0],
            'hold_center': (x, y),
            'countdown_remaining': float,
            'countdown_integer': int,
            'flash_alpha': float [0.0, 1.0],
            'preview_remaining': float,
            'trigger_snap': bool
        }
        """
```

### `delivery_server_test.py` ↔ `main_test.py`
```python
class DeliveryServer:
    def __init__(self, capture_dir: str = "captures", port: int = 8000):
        ...
    def start(self) -> None:
        """Starts daemon HTTP server in background thread."""
    def stop(self) -> None:
        """Stops HTTP server."""
    def get_photo_url(self, filename: str) -> str:
        """Returns reachable LAN URL for mobile landing page."""
    def save_photo_async(self, frame: np.ndarray, filter_name: str = "filter") -> str:
        """Asynchronously writes JPEG to disk and returns filename."""
    def render_qr_card(self, display_frame: np.ndarray, photo_filename: str, remaining_seconds: float) -> np.ndarray:
        """Overlays semi-transparent HUD card with thumbnail and QR code onto display_frame."""
```

## Code Layout
- Original Files (Immutable):
  - `main.py`
  - `filters.py`
  - `geometry.py`
  - `hand_tracking.py`
  - `Launch Filters.command`
  - `requirements.txt`
  - `README.md`
- Test Files & New Modules:
  - `test.command` (macOS double-clickable launcher)
  - `gesture_detector_test.py` (Gesture detection & temporal FSM)
  - `delivery_server_test.py` (Background HTTP server, QR encoding, HUD card)
  - `main_test.py` (Complete smart mirror application with photo capture & delivery)
  - `tests/` (Independent E2E test suite and headless test harnesses)
  - `captures/` (Directory for captured photos)
