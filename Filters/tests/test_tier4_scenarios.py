"""
test_tier4_scenarios.py - Tier 4 Real-World Application Scenarios (Fair Booth Simulations).
Contains 5 comprehensive end-to-end scenario tests:
  - S1: Solo Fairgoer Souvenir Selfie (Idle -> Armed -> Countdown -> Flash -> Pristine Save -> QR HUD -> Dismiss -> Cooldown -> Idle)
  - S2: Two-Person Portal Filter Selection followed by Peace Sign Photo (Portal Filter Change -> Peace Pose -> Pristine Filtered Save)
  - S3: Rapid Consecutive Fairgoers (Debounce Lockout, Queue Lifecycle, Multiple Unique Captures)
  - S4: Mobile Phone Wi-Fi Scan & Instant Photo Download Simulation (Full-Frame QR Detect -> HTTP Fetch -> SHA256 Integrity Verification)
  - S5: Launcher Cold-Start & Clean Termination via test.command (Finder Space Path Resolution, Venv Activation, Parameter Forwarding)
"""

import os
import sys
import time
import math
import hashlib
import tempfile
import subprocess
import urllib.request
import unittest
import numpy as np
import cv2

# Add workspace root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tests.conftest import (
    create_synthetic_hand,
    MockVideoCapture,
    generate_solid_frame,
    generate_checkerboard_frame,
    WRIST, THUMB_TIP, INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP
)

import geometry
import filters
import hand_tracking

from gesture_detector_test import (
    is_peace_gesture,
    find_peace_gesture,
    CaptureState,
    GestureCaptureEngine,
    draw_radial_progress,
    draw_countdown_overlay,
    draw_flash_overlay,
    create_synthetic_landmarks
)

from delivery_server_test import (
    DeliveryServer,
    get_local_ip,
    generate_qr_matrix,
    render_preview_card,
    AsyncImageSaver
)


class TestTier4Scenarios(unittest.TestCase):
    """
    Tier 4 Real-World Application Scenarios (S1 through S5).
    """

    def test_scenario_s1_solo_fairgoer_souvenir_selfie(self):
        """
        Scenario S1: Solo Fairgoer Souvenir Selfie.
        Full automated end-to-end simulation of a single guest taking a selfie.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8300, max_port=8310, host="127.0.0.1")
            server.start()
            try:
                engine = GestureCaptureEngine(
                    hold_duration=0.7,
                    countdown_duration=1.0,
                    flash_duration=0.1,
                    preview_duration=1.0,
                    cooldown_duration=0.5
                )

                # 1. Attendee approaches mirror (IDLE)
                state0, meta0 = engine.update([], current_time=100.0)
                self.assertEqual(state0, CaptureState.IDLE)

                # 2. Poses with peace sign (ARMED)
                peace_lms = create_synthetic_landmarks("peace", wrist=(0.5, 0.7))
                state_arm, meta_arm = engine.update([peace_lms], current_time=100.1)
                self.assertEqual(state_arm, CaptureState.ARMED)
                self.assertEqual(meta_arm['hold_progress'], 0.0)

                # 3. Holds pose for 0.7s -> Transition to COUNTDOWN
                state_cd, meta_cd = engine.update([peace_lms], current_time=100.81)
                self.assertEqual(state_cd, CaptureState.COUNTDOWN)
                self.assertTrue(meta_cd['is_integer_tick'])

                # 4. Countdown expires -> FLASH & SNAP
                state_flash, meta_flash = engine.update([], current_time=101.82)
                self.assertEqual(state_flash, CaptureState.FLASH)
                self.assertTrue(meta_flash['trigger_snap'])

                # 5. Capture pristine frame
                raw_frame = generate_checkerboard_frame(1280, 720)
                poly = np.array([(100, 100), (800, 100), (800, 600), (100, 600)], dtype=np.int32)
                pristine_frame = geometry.paint_filter_in_polygon(raw_frame, poly, filters.filtro_grid)

                # 6. Save photo
                photo_fn, photo_fp = server.save_photo_sync(pristine_frame, filter_name="grid")
                self.assertTrue(os.path.isfile(photo_fp))

                # 7. Render display composite with QR HUD card
                display_frame = pristine_frame.copy()
                composite = server.render_qr_card(display_frame, photo_fn, remaining_seconds=5.0)
                self.assertEqual(composite.shape, (720, 1280, 3))

                # 8. Flash decays -> PREVIEW
                state_prev, meta_prev = engine.update([], current_time=101.95)
                self.assertEqual(state_prev, CaptureState.PREVIEW)

                # 9. Preview expires -> COOLDOWN
                state_cdown, _ = engine.update([], current_time=103.0)
                self.assertEqual(state_cdown, CaptureState.COOLDOWN)

                # 10. Cooldown expires -> IDLE
                state_final, _ = engine.update([], current_time=103.6)
                self.assertEqual(state_final, CaptureState.IDLE)
            finally:
                server.stop()

    def test_scenario_s2_two_person_portal_filter_selection_and_capture(self):
        """
        Scenario S2: Two-Person Portal Filter Selection followed by Peace Sign Photo.
        Guests use portal gesture to cycle to Sepia filter (filtro_6), then pose for photo.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8312, max_port=8322, host="127.0.0.1")
            server.start()
            try:
                engine = GestureCaptureEngine(
                    hold_duration=0.7,
                    countdown_duration=1.0,
                    flash_duration=0.1,
                    preview_duration=1.0,
                    cooldown_duration=0.5
                )
                closing_detector = geometry.ClosingGestureDetector()
                filtro_idx = 0
                frame_w, frame_h = 1280, 720

                # 1. Step 1: Two guests form portal and bring hands close (close_ratio 0.16 * 1280 = 204.8)
                # First pinch: advances to filter 1
                if closing_detector.update(width=150.0, frame_w=frame_w):
                    filtro_idx = (filtro_idx + 1) % len(filters.FILTROS)
                self.assertEqual(filtro_idx, 1)

                # Separate hands (> 0.30 * 1280 = 384.0)
                closing_detector.update(width=500.0, frame_w=frame_w)

                # Second pinch: advances to filter 2
                if closing_detector.update(width=150.0, frame_w=frame_w):
                    filtro_idx = (filtro_idx + 1) % len(filters.FILTROS)
                self.assertEqual(filtro_idx, 2)

                # 2. Guest 2 poses with peace sign while keeping portal open
                left_portal = create_synthetic_landmarks("portal", wrist=(0.25, 0.8))
                right_peace = create_synthetic_landmarks("peace", wrist=(0.75, 0.8))

                t = 100.0
                engine.update([left_portal, right_peace], current_time=t) # ARMED
                t += 0.71
                engine.update([left_portal, right_peace], current_time=t) # COUNTDOWN
                t += 1.01
                state_snap, meta_snap = engine.update([], current_time=t) # FLASH
                self.assertEqual(state_snap, CaptureState.FLASH)
                self.assertTrue(meta_snap['trigger_snap'])

                # 3. Render pristine frame with filter 2
                raw = generate_checkerboard_frame(frame_w, frame_h)
                poly = np.array([(200, 150), (1000, 150), (1000, 600), (200, 600)], dtype=np.int32)
                pristine = geometry.paint_filter_in_polygon(raw, poly, filters.FILTROS[filtro_idx])

                fn, fp = server.save_photo_sync(pristine, filter_name=f"filter_{filtro_idx}")
                self.assertTrue(os.path.isfile(fp))
                saved_img = cv2.imread(fp)
                self.assertEqual(saved_img.shape, (720, 1280, 3))
            finally:
                server.stop()

    def test_scenario_s3_rapid_consecutive_fairgoers_debounce_lifecycle(self):
        """
        Scenario S3: Rapid Consecutive Fairgoers (Debounce & Queue Lifecycle).
        Guest 1 captures photo. Guest 2 tries during cooldown (blocked). Cooldown ends, Guest 2 captures.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8324, max_port=8334, host="127.0.0.1")
            server.start()
            try:
                engine = GestureCaptureEngine(
                    hold_duration=0.5,
                    countdown_duration=0.5,
                    flash_duration=0.1,
                    preview_duration=0.5,
                    cooldown_duration=1.0
                )
                peace_lms = create_synthetic_landmarks("peace")

                # Guest 1: Full capture cycle
                t = 100.0
                engine.update([peace_lms], current_time=t) # ARMED
                t += 0.51
                engine.update([peace_lms], current_time=t) # COUNTDOWN
                t += 0.51
                engine.update([], current_time=t) # FLASH
                fn1, fp1 = server.save_photo_sync(generate_solid_frame(320, 240, (10, 20, 30)), "guest1")
                t += 0.11
                engine.update([], current_time=t) # PREVIEW
                t += 0.51
                state_cd, _ = engine.update([], current_time=t) # COOLDOWN starts at t=101.63
                self.assertEqual(state_cd, CaptureState.COOLDOWN)

                # Guest 2 attempts capture at t=102.0 (cooldown active until 102.63) -> Blocked
                state_blocked, meta_blocked = engine.update([peace_lms], current_time=102.0)
                self.assertEqual(state_blocked, CaptureState.COOLDOWN)
                self.assertEqual(meta_blocked['hold_progress'], 0.0)

                # Cooldown expires at t=102.65
                state_idle, _ = engine.update([], current_time=102.65)
                self.assertEqual(state_idle, CaptureState.IDLE)

                # Guest 2 now triggers photo
                t = 102.70
                engine.update([peace_lms], current_time=t) # ARMED
                t += 0.51
                engine.update([peace_lms], current_time=t) # COUNTDOWN
                t += 0.51
                state2, meta2 = engine.update([], current_time=t) # FLASH
                self.assertEqual(state2, CaptureState.FLASH)
                self.assertTrue(meta2['trigger_snap'])
                fn2, fp2 = server.save_photo_sync(generate_solid_frame(320, 240, (40, 50, 60)), "guest2")

                # Verify both photos exist on disk
                self.assertTrue(os.path.isfile(fp1))
                self.assertTrue(os.path.isfile(fp2))
                self.assertNotEqual(fn1, fn2)
            finally:
                server.stop()

    def test_scenario_s4_mobile_qr_scan_and_instant_photo_download(self):
        """
        Scenario S4: Mobile Phone Wi-Fi Scan & Instant Photo Download Simulation.
        Decodes QR from composite display frame, downloads via HTTP GET, and verifies SHA256 checksum.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8336, max_port=8346, host="127.0.0.1")
            server.start()
            try:
                # 1. Capture pristine photo
                frame = generate_checkerboard_frame(1280, 720, square_size=60)
                cv2.circle(frame, (640, 360), 120, (0, 200, 255), -1)
                fn, fp = server.save_photo_sync(frame, filter_name="s4_qr")

                # Compute baseline SHA256 of saved file
                with open(fp, "rb") as f:
                    disk_bytes = f.read()
                expected_sha256 = hashlib.sha256(disk_bytes).hexdigest()

                # 2. Render mirror HUD card containing QR code onto 1280x720 composite
                mirror_display = frame.copy()
                composite_screen = server.render_qr_card(mirror_display, fn, remaining_seconds=5.5)

                # 3. Simulate phone camera optical QR scan using cv2.QRCodeDetector
                detector = cv2.QRCodeDetector()
                decoded_url, points, _ = detector.detectAndDecode(composite_screen)
                self.assertTrue(decoded_url.startswith("http://"), f"Decoded URL invalid: {decoded_url}")
                self.assertIn(fn, decoded_url)

                # 4. Mobile browser loads landing page
                with urllib.request.urlopen(decoded_url, timeout=3.0) as resp:
                    self.assertEqual(resp.status, 200)
                    html_body = resp.read().decode("utf-8")
                    self.assertIn(f"/photo/{fn}", html_body)
                    self.assertIn("Save Photo", html_body)

                # 5. Mobile browser downloads raw JPEG photo
                photo_download_url = f"http://127.0.0.1:{server.port}/photo/{fn}"
                with urllib.request.urlopen(photo_download_url, timeout=3.0) as resp:
                    self.assertEqual(resp.status, 200)
                    downloaded_bytes = resp.read()

                # 6. Verify 100% binary checksum match
                downloaded_sha256 = hashlib.sha256(downloaded_bytes).hexdigest()
                self.assertEqual(downloaded_sha256, expected_sha256, "Downloaded photo SHA256 must match original disk photo")
            finally:
                server.stop()

    def test_scenario_s5_launcher_cold_start_and_clean_termination(self):
        """
        Scenario S5: Launcher Cold-Start & Clean Termination via test.command.
        Validates macOS double-clickable script structure, virtualenv activation, and space tolerance.
        """
        launcher_path = os.path.join(PROJECT_ROOT, "test.command")
        self.assertTrue(os.path.isfile(launcher_path))
        self.assertTrue(os.access(launcher_path, os.X_OK))

        # Check bash syntax using bash -n
        res = subprocess.run(["bash", "-n", launcher_path], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"test.command syntax error: {res.stderr}")

        with open(launcher_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check space safety and dirname
        self.assertIn('DIR="$(cd "$(dirname "$0")" && pwd)"', content)
        # Check virtualenv activation
        self.assertIn("venv/bin/activate", content)
        # Check main_test.py execution
        self.assertIn("main_test.py", content)
        # Check parameter propagation
        self.assertIn('"$@"', content)


if __name__ == "__main__":
    unittest.main()
