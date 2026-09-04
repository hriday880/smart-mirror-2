"""
main_test.py - Smart Mirror Hand Gesture Photo Capture Application
==================================================================
Augmented test application integrating:
1. Touchless Peace Sign (✌️) Photo Capture with Hold Confirmation & 6-State FSM.
2. Dual-hand Portal AR Filter selection with 8 visual shader filters.
3. Strict Buffer Layering:
   - Pristine Layer: Clean camera frame + AR portal filtered content (no HUD/text/outlines),
     asynchronously persisted to disk at JPEG quality 95.
   - Display Layer: Interactive HUD composite with portal outlines, glowing radial hold
     progress ring, animated 3-2-1 countdown numeral, shutter flash, and QR preview card.
4. Background LAN HTTP Delivery Server with auto port-hopping and zero-dependency QR card.
5. Non-blocking acoustic audio cues for countdown ticks and shutter snap.
6. Full headless and synthetic gesture simulation support for CI and automated testing.
"""

import os
import tempfile
import sys
import time
import math
import argparse
import logging
import platform
import threading
import subprocess
from typing import Optional, List, Tuple, Dict, Any

# Ensure matplotlib font scanner does not fail on newer macOS system_profiler JSON output
os.environ.setdefault("MPLCONFIGDIR", os.path.join(tempfile.gettempdir(), "smart_mirror_mpl"))
try:
    _orig_check_output = subprocess.check_output
    def _safe_check_output(*args, **kwargs):
        if len(args) > 0 and isinstance(args[0], (list, tuple)) and "SPFontsDataType" in args[0]:
            return b'{"_items": []}'
        return _orig_check_output(*args, **kwargs)
    subprocess.check_output = _safe_check_output
except Exception:
    pass

import cv2
import numpy as np
import mediapipe as mp

# Original application modules (Read-only integration)
from hand_tracking import (
    INDEX_TIP, THUMB_TIP, WRIST, MIDDLE_TIP, RING_TIP, PINKY_TIP
)
from geometry import (
    render_portal, portal_width, ClosingGestureDetector, paint_filter_in_polygon
)
from filters import FILTROS

# Test environment subsystems
from gesture_detector_test import (
    CaptureState,
    GestureCaptureEngine,
    draw_radial_progress,
    draw_countdown_overlay,
    draw_flash_overlay,
    find_peace_gesture,
    create_synthetic_landmarks
)
from delivery_server_test import (
    DeliveryServer,
    render_preview_card,
    get_local_ip,
    DEFAULT_PORT,
    DEFAULT_CAPTURE_DIR
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [SmartMirror] %(message)s"
)
logger = logging.getLogger("SmartMirrorApp")


# ==============================================================================
# Audio Cue Manager
# ==============================================================================

class AudioCueManager:
    """
    Non-blocking sound manager for photo booth acoustic cues.
    Plays macOS system audio cues via afplay in daemon background threads,
    with graceful fallbacks to terminal bell or silent pass on other platforms.
    """
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._system = platform.system()

    def play_tick(self) -> None:
        """Plays countdown integer tick acoustic cue."""
        if not self.enabled:
            return
        self._dispatch("tick")

    def play_snap(self) -> None:
        """Plays shutter snap acoustic cue."""
        if not self.enabled:
            return
        self._dispatch("snap")

    def _dispatch(self, cue: str) -> None:
        thread = threading.Thread(
            target=self._worker,
            args=(cue,),
            daemon=True,
            name=f"AudioCue-{cue}"
        )
        thread.start()

    def _worker(self, cue: str) -> None:
        try:
            if self._system == "Darwin":
                # macOS system sound paths
                sound_file = (
                    "/System/Library/Sounds/Tink.aiff"
                    if cue == "tick"
                    else "/System/Library/Sounds/Hero.aiff"
                )
                if os.path.isfile(sound_file):
                    subprocess.run(
                        ["afplay", sound_file],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=0.8
                    )
                else:
                    print("\a", end="", flush=True)
            else:
                print("\a", end="", flush=True)
        except Exception:
            pass


# ==============================================================================
# Synthetic Landmark Wrappers (For Headless / Mock Execution)
# ==============================================================================

class MockLandmark:
    """Mock MediaPipe Normalized Landmark point."""
    def __init__(self, x: float, y: float, z: float = 0.0):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)

    def __repr__(self) -> str:
        return f"MockLandmark(x={self.x:.4f}, y={self.y:.4f})"


class MockHand:
    """Mock MediaPipe Hand landmark container containing 21 landmarks."""
    def __init__(self, landmarks_2d: np.ndarray):
        self.landmark = [MockLandmark(p[0], p[1]) for p in landmarks_2d]

    def __getitem__(self, idx: int) -> MockLandmark:
        return self.landmark[idx]

    def __len__(self) -> int:
        return len(self.landmark)

    def __iter__(self):
        return iter(self.landmark)


def generate_synthetic_frame(
    width: int = 1280,
    height: int = 720,
    frame_idx: int = 0
) -> np.ndarray:
    """
    Generates a realistic synthetic test video frame with an animated gradient
    and subtle ambient elements when physical camera is unavailable.
    """
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    
    # Animated color gradient
    shift = (frame_idx * 2) % 255
    y_grad = np.linspace(40 + (shift // 4), 90 + (shift // 4), height, dtype=np.uint8).reshape(-1, 1)
    x_grad = np.linspace(30, 80, width, dtype=np.uint8)
    
    frame[:, :, 0] = x_grad
    frame[:, :, 1] = y_grad
    frame[:, :, 2] = np.clip(60 + (shift // 5), 0, 255)

    # Ambient smart mirror room grid pattern
    for gx in range(0, width, 80):
        cv2.line(frame, (gx, 0), (gx, height), (70, 75, 85), 1)
    for gy in range(0, height, 80):
        cv2.line(frame, (0, gy), (width, gy), (70, 75, 85), 1)

    # Center silhouette indicator
    cv2.circle(frame, (width // 2, height // 2 - 40), 90, (90, 100, 115), -1)
    cv2.ellipse(frame, (width // 2, height // 2 + 180), (140, 110), 0, 0, 360, (90, 100, 115), -1)

    return frame


def build_mock_hands(
    mock_gesture: str,
    frame_idx: int = 0
) -> Tuple[List[MockHand], Optional[MockHand], Optional[MockHand]]:
    """
    Builds synthetic MediaPipe hand structures according to the requested mock gesture.
    Returns:
        (multi_hand_landmarks, left_hand, right_hand)
    """
    g = mock_gesture.lower().strip()
    if g == "none":
        return [], None, None

    if g == "peace":
        # Right hand making peace sign
        pts = create_synthetic_landmarks("peace", wrist=(0.60, 0.70), scale=0.32)
        hand = MockHand(pts)
        return [hand], None, hand

    elif g == "portal":
        # Dual hands forming portal polygon
        pts_left = create_synthetic_landmarks("portal", wrist=(0.35, 0.72), scale=0.30)
        pts_right = create_synthetic_landmarks("portal", wrist=(0.65, 0.72), scale=0.30)
        hand_left = MockHand(pts_left)
        hand_right = MockHand(pts_right)
        return [hand_left, hand_right], hand_left, hand_right

    elif g in ("open_palm", "palm"):
        pts = create_synthetic_landmarks("open_palm", wrist=(0.50, 0.70), scale=0.32)
        hand = MockHand(pts)
        return [hand], None, hand

    elif g == "fist":
        pts = create_synthetic_landmarks("fist", wrist=(0.50, 0.70), scale=0.32)
        hand = MockHand(pts)
        return [hand], None, hand

    # Default fallback
    pts = create_synthetic_landmarks("peace", wrist=(0.55, 0.70), scale=0.32)
    hand = MockHand(pts)
    return [hand], None, hand


# ==============================================================================
# CLI Argument Parsing
# ==============================================================================

def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parses command-line arguments for the smart mirror test application."""
    parser = argparse.ArgumentParser(
        description="Smart Mirror Hand Gesture Photo Capture (Augmented Test Application)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without GUI window / display output"
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=None,
        help="Limit execution to N video frames and exit cleanly"
    )
    parser.add_argument(
        "--mock-gesture",
        type=str,
        default=None,
        choices=["peace", "portal", "open_palm", "palm", "fist", "none"],
        help="Simulate synthetic hand landmarks for automated testing"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="Delivery server LAN HTTP port"
    )
    parser.add_argument(
        "--no-sound",
        action="store_true",
        help="Mute non-blocking acoustic cues"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_CAPTURE_DIR,
        help="Directory to save captured photos"
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="OpenCV VideoCapture device index"
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1280,
        help="Preferred video capture width"
    )
    parser.add_argument(
        "--height",
        type=int,
        default=720,
        help="Preferred video capture height"
    )
    return parser.parse_args(args)


# ==============================================================================
# Main Application Engine
# ==============================================================================

button_clicked = False
btn_rect = (0, 0, 0, 0)
filtro_index = 0
filter_btns = []
switch_camera_flag = False

FILTER_NAMES = [
    "Blueprint",
    "Pop Art",
    "Comic Book",
    "Glitch",
    "Thermal",
    "Vintage",
    "Dreamy",
    "Bubblegum",
]

def mouse_callback(event, x, y, flags, param):
    global button_clicked, btn_rect, filtro_index, filter_btns, switch_camera_flag
    if event == cv2.EVENT_LBUTTONDOWN:
        x1, y1, x2, y2 = btn_rect
        if x1 <= x <= x2 and y1 <= y <= y2:
            button_clicked = True
            
        for fx1, fy1, fx2, fy2, idx in filter_btns:
            if fx1 <= x <= fx2 and fy1 <= y <= fy2:
                if idx == 999:
                    switch_camera_flag = True
                else:
                    filtro_index = idx


def run_mirror_app(args: Optional[argparse.Namespace] = None) -> int:
    global button_clicked, btn_rect, filtro_index, filter_btns, switch_camera_flag
    """
    Executes the full Smart Mirror Photo Capture runtime loop.
    Returns process exit code (0 for clean termination).
    """
    if args is None:
        args = parse_args()

    logger.info("=" * 60)
    logger.info(" Starting Smart Mirror Hand Gesture Photo Booth")
    logger.info(f" Mode: {'Headless' if args.headless else 'Interactive GUI'}")
    logger.info(f" Delivery Server Port: {args.port} | Captures Dir: '{args.output_dir}'")
    if args.mock_gesture:
        logger.info(f" Synthetic Gesture Simulation: '{args.mock_gesture}'")
    if args.frames is not None:
        logger.info(f" Execution Frame Limit: {args.frames} frames")
    logger.info("=" * 60)

    # 1. Initialize Subsystems
    audio_mgr = AudioCueManager(enabled=not args.no_sound)
    
    delivery_server = DeliveryServer(
        capture_dir=args.output_dir,
        port=args.port
    )
    
    capture_engine = GestureCaptureEngine(
        hold_duration=0.7,
        countdown_duration=3.0,
        flash_duration=0.15,
        preview_duration=10.0,
        cooldown_duration=2.0
    )

    closing_detector = ClosingGestureDetector()
    filtro_index = 0
    current_photo_filename: Optional[str] = None

    # Start Delivery Server in background
    try:
        delivery_server.start()
    except Exception as e:
        logger.error(f"Failed to start DeliveryServer on port {args.port}: {e}")
        return 1

    # 2. Initialize Camera & MediaPipe
    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(
        max_num_hands=2,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.6
    )

    cap = None
    use_mock_video = False

    if args.mock_gesture is not None:
        use_mock_video = True
        logger.info("Mock gesture mode active: Using synthetic video frame generator.")
    else:
        try:
            cap = cv2.VideoCapture(args.camera_index)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
            else:
                logger.warning(f"Could not open cv2.VideoCapture({args.camera_index}).")
                if args.headless:
                    logger.info("Headless mode active: Falling back to synthetic video frame generator.")
                    use_mock_video = True
                else:
                    delivery_server.stop()
                    raise RuntimeError(
                        "No se pudo abrir la camara. Revisa el indice de camara o los permisos."
                    )
        except Exception as e:
            if args.headless:
                logger.info(f"Camera open error ({e}); falling back to synthetic generator in headless mode.")
                use_mock_video = True
            else:
                delivery_server.stop()
                raise

    frame_count = 0
    exit_code = 0

    button_clicked = False
    switch_camera_flag = False

    if not args.headless:
        cv2.namedWindow("Smart Mirror Photo Booth")
        cv2.setMouseCallback("Smart Mirror Photo Booth", mouse_callback)

    # Load Logo
    logo_img = cv2.imread("logo.jpeg")
    if logo_img is not None:
        logo_h, logo_w = logo_img.shape[:2]
        target_w = 120
        target_h = int(logo_h * (target_w / logo_w))
        logo_img = cv2.resize(logo_img, (target_w, target_h), interpolation=cv2.INTER_AREA)

    # 3. Main Video & Gesture Processing Loop
    try:
        while True:
            if switch_camera_flag:
                switch_camera_flag = False
                if cap is not None:
                    cap.release()
                args.camera_index = 1 if args.camera_index == 0 else 0
                logger.info(f"Switching camera to index {args.camera_index}")
                cap = cv2.VideoCapture(args.camera_index)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
                else:
                    logger.warning(f"Could not open camera {args.camera_index}, falling back to 0")
                    args.camera_index = 0
                    cap = cv2.VideoCapture(0)
                    
            # Check frame termination limit
            if args.frames is not None and frame_count >= args.frames:
                logger.info(f"Reached specified frame limit ({args.frames}). Exiting cleanly.")
                break

            # Read or generate frame
            if use_mock_video or cap is None:
                raw_frame = generate_synthetic_frame(args.width, args.height, frame_count)
            else:
                ok, raw_frame = cap.read()
                if not ok or raw_frame is None:
                    logger.warning("Camera stream read failed. Ending capture loop.")
                    break

            frame_count += 1

            # Mirror frame horizontally for natural smart mirror interaction
            mirrored_frame = cv2.flip(raw_frame, 1)
            h, w = mirrored_frame.shape[:2]

            # Initialize Strict Buffer Layers
            # Layer 1: Pristine Frame Buffer (clean filtered feed, NO HUD / text / overlays)
            pristine_frame = mirrored_frame.copy()
            # Layer 2: Display Frame Buffer (visual composite for mirror monitor)
            display_frame = mirrored_frame.copy()

            # Layer 3: Apply Logo Overlay to both frames
            if logo_img is not None:
                lh, lw = logo_img.shape[:2]
                if h > lh and w > lw:
                    pad_x, pad_y = 20, 20
                    y1, y2 = h - lh - pad_y, h - pad_y
                    x1, x2 = w - lw - pad_x, w - pad_x
                    pristine_frame[y1:y2, x1:x2] = logo_img
                    display_frame[y1:y2, x1:x2] = logo_img


            # Landmark Detection & Processing
            left_hand = None
            right_hand = None
            multi_lms: List[Any] = []

            if args.mock_gesture is not None:
                multi_lms, left_hand, right_hand = build_mock_hands(args.mock_gesture, frame_count)
            else:
                rgb = cv2.cvtColor(mirrored_frame, cv2.COLOR_BGR2RGB)
                results = hands.process(rgb)

                if results.multi_hand_landmarks and results.multi_handedness:
                    multi_lms = results.multi_hand_landmarks
                    for hand_landmarks, handedness in zip(
                        results.multi_hand_landmarks, results.multi_handedness
                    ):
                        raw_label = handedness.classification[0].label
                        # Normalize handedness because frame is horizontally mirrored
                        label = "Right" if raw_label == "Left" else "Left"

                        if label == "Left":
                            left_hand = hand_landmarks
                        else:
                            right_hand = hand_landmarks

            # 4. Dual-Hand Portal Geometry & AR Filter Application
            if left_hand is not None and right_hand is not None:
                lm_left = left_hand.landmark
                lm_right = right_hand.landmark

                p1 = (lm_left[INDEX_TIP].x * w, lm_left[INDEX_TIP].y * h)
                p2 = (lm_left[THUMB_TIP].x * w, lm_left[THUMB_TIP].y * h)
                p3 = (lm_right[INDEX_TIP].x * w, lm_right[INDEX_TIP].y * h)
                p4 = (lm_right[THUMB_TIP].x * w, lm_right[THUMB_TIP].y * h)

                width = portal_width(p1, p2, p3, p4)

                # Cycle filter when portal hands close together
                if closing_detector.update(width, w):
                    filtro_index = (filtro_index + 1) % len(FILTROS)
                    logger.info(f"Filter switched to [{filtro_index}]: {FILTROS[filtro_index].__name__}")

                portal_polygon = np.array([p1, p3, p4, p2], dtype=np.int32)

                # Apply AR filter to Pristine Frame (NO outlines or HUD)
                pristine_frame = paint_filter_in_polygon(
                    pristine_frame, portal_polygon, FILTROS[filtro_index]
                )

                # Apply AR filter & white portal outline to Display Frame
                display_frame = render_portal(
                    display_frame, p1, p2, p3, p4, FILTROS[filtro_index]
                )

            # 5. Gesture Capture State Machine Update
            state, meta = capture_engine.update(multi_lms, frame_shape=(h, w))

            # Acoustic Feedback Triggers
            if meta.get("is_integer_tick", False):
                audio_mgr.play_tick()

            # Snapshot Capture Event (COUNTDOWN -> FLASH transition)
            if meta.get("trigger_snap", False):
                filter_name = FILTROS[filtro_index].__name__
                # Asynchronously save PRISTINE filtered frame to disk at JPEG quality 95
                current_photo_filename = delivery_server.save_photo_async(
                    pristine_frame, filter_name=filter_name
                )
                audio_mgr.play_snap()
                logger.info(f"📸 SNAPSHOT TRIGGERED! Saved pristine frame as '{current_photo_filename}'")

            # 6. Display Composite HUD Layering
            
            # Button Logic & Render
            btn_x1, btn_y1 = w // 2 - 120, h - 90
            btn_x2, btn_y2 = w // 2 + 120, h - 20
            btn_rect = (btn_x1, btn_y1, btn_x2, btn_y2)

            if state in (CaptureState.IDLE, CaptureState.ARMED, CaptureState.COOLDOWN):
                cv2.rectangle(display_frame, (btn_x1, btn_y1), (btn_x2, btn_y2), (0, 150, 255), -1)
                cv2.rectangle(display_frame, (btn_x1, btn_y1), (btn_x2, btn_y2), (255, 255, 255), 2)
                cv2.putText(display_frame, "TAKE PHOTO", (btn_x1 + 35, btn_y1 + 45), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
            
            # Draw Filter Selection Buttons
            filter_btns.clear()
            f_btn_w, f_btn_h = 160, 45
            start_y = 100
            for i, name in enumerate(FILTER_NAMES):
                fx1, fy1 = 20, start_y + i * (f_btn_h + 15)
                fx2, fy2 = fx1 + f_btn_w, fy1 + f_btn_h
                filter_btns.append((fx1, fy1, fx2, fy2, i))
                
                # Highlight active filter
                bg_color = (0, 200, 0) if i == filtro_index else (50, 50, 50)
                cv2.rectangle(display_frame, (fx1, fy1), (fx2, fy2), bg_color, -1)
                cv2.rectangle(display_frame, (fx1, fy1), (fx2, fy2), (255, 255, 255), 1)
                cv2.putText(display_frame, name, (fx1 + 10, fy1 + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
                
            # Draw Switch Camera button top-right
            cam_btn_w, cam_btn_h = 180, 40
            cam_x1, cam_y1 = w - cam_btn_w - 20, 20
            cam_x2, cam_y2 = w - 20, 20 + cam_btn_h
            # store index 999 for camera switch
            filter_btns.append((cam_x1, cam_y1, cam_x2, cam_y2, 999))
            cv2.rectangle(display_frame, (cam_x1, cam_y1), (cam_x2, cam_y2), (100, 100, 100), -1)
            cv2.rectangle(display_frame, (cam_x1, cam_y1), (cam_x2, cam_y2), (255, 255, 255), 1)
            cv2.putText(display_frame, "SWITCH CAMERA", (cam_x1 + 15, cam_y1 + 27), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

            if button_clicked:
                button_clicked = False
                capture_engine.force_trigger_countdown()
                # Need to update state immediately to reflect countdown start visually
                state = CaptureState.COUNTDOWN
                meta["countdown_remaining"] = capture_engine.countdown_duration
                meta["is_integer_tick"] = True

            if state == CaptureState.COUNTDOWN:
                display_frame = draw_countdown_overlay(
                    display_frame,
                    meta.get("countdown_remaining", 0.0),
                    meta.get("is_integer_tick", False)
                )

            elif state == CaptureState.FLASH:
                display_frame = draw_flash_overlay(
                    display_frame,
                    meta.get("flash_alpha", 0.0)
                )

            elif state == CaptureState.PREVIEW and current_photo_filename:
                display_frame = delivery_server.render_preview_card(
                    display_frame,
                    current_photo_filename,
                    meta.get("preview_remaining", 0.0)
                )

            # Top-Left Live Status Indicator
            if not args.headless:
                host_ip = delivery_server.host
                port_num = delivery_server.port
                status_text = f"Smart Mirror Booth | LAN: http://{host_ip}:{port_num} | Filter [{filtro_index + 1}/8]"
                cv2.putText(
                    display_frame,
                    status_text,
                    (20, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 220, 255),
                    1,
                    cv2.LINE_AA
                )

            # 7. Render or Handle Display
            if not args.headless:
                cv2.imshow("Smart Mirror Photo Booth", display_frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q") or key == 27:
                    logger.info("Quit key ('q' / ESC) pressed. Terminating application.")
                    break
            else:
                # In headless / mock mode, yield briefly to maintain steady execution pacing
                time.sleep(0.001)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Unexpected error in capture loop: {e}", exc_info=True)
        exit_code = 1
    finally:
        # 8. Clean Teardown & Resource Deallocation
        logger.info("Performing clean shutdown...")
        try:
            delivery_server.stop()
        except Exception:
            pass

        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass

        try:
            cv2.destroyAllWindows()
        except Exception:
            pass

        logger.info(f"Smart Mirror session ended cleanly with exit code {exit_code}.")

    return exit_code


def main() -> None:
    """Primary entry point."""
    args = parse_args()
    code = run_mirror_app(args)
    sys.exit(code)


if __name__ == "__main__":
    main()
