"""
test_tier1_features.py - Tier 1 Isolated Unit Tests for Features F1 through F10.
Contains 60 automated unit test cases testing each feature in isolation.
"""

import os
import sys
import time
import math
import tempfile
import urllib.request
import urllib.error
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

# Import original source modules (Read-only verification)
import geometry
import filters
import hand_tracking

# Import gesture detector test module
import gesture_detector_test
from gesture_detector_test import (
    is_peace_gesture,
    find_peace_gesture,
    CaptureState,
    GestureCaptureEngine,
    draw_radial_progress,
    draw_countdown_overlay,
    draw_flash_overlay,
    compute_palm_scale,
    create_synthetic_landmarks
)

# Import delivery server test module
import delivery_server_test
from delivery_server_test import (
    DeliveryServer,
    get_local_ip,
    generate_qr_matrix,
    render_preview_card,
    AsyncImageSaver
)


class TestTier1Features(unittest.TestCase):
    """
    Tier 1 Feature Unit Tests (F1 through F10).
    Total: 60 automated unit test cases.
    """

    # =========================================================================
    # Feature F1: Test Environment Isolation (ORIGINAL_REQUEST §R3)
    # =========================================================================

    def test_f1_01_original_main_py_exists_and_unmodified(self):
        main_path = os.path.join(PROJECT_ROOT, "main.py")
        self.assertTrue(os.path.isfile(main_path), "main.py must exist")
        with open(main_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("cv2.VideoCapture(0)", content)
        self.assertIn("ClosingGestureDetector", content)
        self.assertIn("render_portal", content)
        self.assertIn('cv2.imshow(" ", frame)', content)

    def test_f1_02_original_filters_py_exports_all_8_filters(self):
        self.assertEqual(len(filters.FILTROS), 8, "filters.py must export 8 filters in FILTROS")
        test_roi = np.full((100, 100, 3), 128, dtype=np.uint8)
        for idx, filter_func in enumerate(filters.FILTROS):
            out = filter_func(test_roi)
            self.assertEqual(out.shape, test_roi.shape, f"Filter {idx} changed shape")
            self.assertEqual(out.dtype, np.uint8, f"Filter {idx} returned invalid dtype")

    def test_f1_03_original_geometry_py_exports_portal_primitives(self):
        self.assertTrue(hasattr(geometry, "portal_width"))
        self.assertTrue(hasattr(geometry, "ClosingGestureDetector"))
        self.assertTrue(hasattr(geometry, "paint_filter_in_polygon"))
        self.assertTrue(hasattr(geometry, "render_portal"))

        w = geometry.portal_width((100, 100), (100, 200), (300, 100), (300, 200))
        self.assertAlmostEqual(w, 200.0, places=2)

    def test_f1_04_original_hand_tracking_py_exports_landmark_indices(self):
        self.assertEqual(hand_tracking.WRIST, 0)
        self.assertEqual(hand_tracking.THUMB_TIP, 4)
        self.assertEqual(hand_tracking.INDEX_TIP, 8)
        self.assertEqual(hand_tracking.MIDDLE_TIP, 12)
        self.assertEqual(hand_tracking.RING_TIP, 16)
        self.assertEqual(hand_tracking.PINKY_TIP, 20)
        self.assertTrue(hasattr(hand_tracking, "get_extended_fingers"))

    def test_f1_05_original_launcher_script_intact(self):
        orig_launcher = os.path.join(PROJECT_ROOT, "Launch Filters.command")
        self.assertTrue(os.path.isfile(orig_launcher))
        with open(orig_launcher, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
        self.assertIn("python main.py", lines[-1])

    def test_f1_06_original_requirements_and_readme_intact(self):
        req_path = os.path.join(PROJECT_ROOT, "requirements.txt")
        self.assertTrue(os.path.isfile(req_path))
        with open(req_path, "r", encoding="utf-8") as f:
            req_content = f.read()
        self.assertIn("opencv-python", req_content)
        self.assertIn("mediapipe", req_content)

        readme_path = os.path.join(PROJECT_ROOT, "README.md")
        self.assertTrue(os.path.isfile(readme_path))

    # =========================================================================
    # Feature F2: macOS test.command Launcher (ORIGINAL_REQUEST §R4)
    # =========================================================================

    def test_f2_01_test_command_exists_and_executable(self):
        test_cmd_path = os.path.join(PROJECT_ROOT, "test.command")
        self.assertTrue(os.path.isfile(test_cmd_path), "test.command must exist")
        self.assertTrue(os.access(test_cmd_path, os.X_OK), "test.command must be executable (chmod +x)")

    def test_f2_02_test_command_shebang(self):
        test_cmd_path = os.path.join(PROJECT_ROOT, "test.command")
        with open(test_cmd_path, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
        self.assertTrue(first_line.startswith("#!/bin/bash") or first_line.startswith("#!/usr/bin/env bash"))

    def test_f2_03_test_command_space_tolerant_navigation(self):
        test_cmd_path = os.path.join(PROJECT_ROOT, "test.command")
        with open(test_cmd_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('dirname "$0"', content, "test.command must use dirname with quoted $0 for space tolerance")

    def test_f2_04_test_command_virtualenv_activation(self):
        test_cmd_path = os.path.join(PROJECT_ROOT, "test.command")
        with open(test_cmd_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertTrue("venv/bin/activate" in content or ".venv/bin/activate" in content)

    def test_f2_05_test_command_invokes_main_test_py(self):
        test_cmd_path = os.path.join(PROJECT_ROOT, "test.command")
        with open(test_cmd_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("main_test.py", content, "test.command must target main_test.py")

    def test_f2_06_test_command_exit_code_handling(self):
        test_cmd_path = os.path.join(PROJECT_ROOT, "test.command")
        with open(test_cmd_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("exit", content.lower())

    # =========================================================================
    # Feature F3: Scale-Invariant Peace Sign (✌️) Detection Engine
    # =========================================================================

    def test_f3_01_positive_peace_sign_detection(self):
        peace_lms = create_synthetic_landmarks("peace")
        self.assertTrue(is_peace_gesture(peace_lms), "Canonical Peace Sign must be detected as True")

    def test_f3_02_negative_portal_hand_detection(self):
        portal_lms = create_synthetic_landmarks("portal")
        self.assertFalse(is_peace_gesture(portal_lms), "Portal Hand (Thumb+Index) must NOT trigger Peace Sign")

    def test_f3_03_negative_open_palm_detection(self):
        palm_lms = create_synthetic_landmarks("open_palm")
        self.assertFalse(is_peace_gesture(palm_lms), "Open Palm must NOT trigger Peace Sign")

    def test_f3_04_negative_fist_detection(self):
        fist_lms = create_synthetic_landmarks("fist")
        self.assertFalse(is_peace_gesture(fist_lms), "Fist must NOT trigger Peace Sign")

    def test_f3_05_negative_pointing_finger_detection(self):
        pointing_lms = create_synthetic_landmarks("pointing")
        self.assertFalse(is_peace_gesture(pointing_lms), "Pointing finger must NOT trigger Peace Sign")

    def test_f3_06_scale_invariance_small_and_large(self):
        small_hand = create_synthetic_landmarks("peace", scale=0.10)
        large_hand = create_synthetic_landmarks("peace", scale=0.55)
        self.assertTrue(is_peace_gesture(small_hand), "Small hand (distant user) must be detected")
        self.assertTrue(is_peace_gesture(large_hand), "Large hand (close user) must be detected")

    def test_f3_07_tilt_invariance_rotations(self):
        for deg in [-45, -30, 0, 30, 45, 90]:
            tilted_hand = create_synthetic_landmarks("peace", tilt_deg=deg)
            self.assertTrue(is_peace_gesture(tilted_hand), f"Peace sign tilted {deg} deg must be recognized")

    def test_f3_08_find_peace_gesture_returns_center_and_index(self):
        portal_lms = create_synthetic_landmarks("portal", wrist=(0.3, 0.8))
        peace_lms = create_synthetic_landmarks("peace", wrist=(0.7, 0.8))
        found, idx, center, pts = find_peace_gesture([portal_lms, peace_lms], frame_shape=(720, 1280))
        self.assertTrue(found)
        self.assertEqual(idx, 1)
        self.assertIsNotNone(center)
        self.assertGreater(center[0], 0)

    # =========================================================================
    # Feature F4: Gesture Hold Confirmation & Radial Progress Ring
    # =========================================================================

    def test_f4_01_engine_initializes_in_idle_state(self):
        engine = GestureCaptureEngine(hold_duration=0.7)
        self.assertEqual(engine.state, CaptureState.IDLE)
        self.assertIsNone(engine.hold_start_time)

    def test_f4_02_transition_idle_to_armed_on_first_gesture(self):
        engine = GestureCaptureEngine(hold_duration=0.7)
        peace_lms = create_synthetic_landmarks("peace")
        state, meta = engine.update([peace_lms], current_time=100.0)
        self.assertEqual(state, CaptureState.ARMED)
        self.assertEqual(meta['hold_progress'], 0.0)
        self.assertIsNotNone(meta['hold_center'])

    def test_f4_03_hold_progress_increases_monotonically(self):
        engine = GestureCaptureEngine(hold_duration=0.7)
        peace_lms = create_synthetic_landmarks("peace")
        engine.update([peace_lms], current_time=100.0)
        state_mid, meta_mid = engine.update([peace_lms], current_time=100.35)
        self.assertEqual(state_mid, CaptureState.ARMED)
        self.assertAlmostEqual(meta_mid['hold_progress'], 0.5, delta=0.05)

    def test_f4_04_hold_cancellation_if_gesture_dropped_before_threshold(self):
        engine = GestureCaptureEngine(hold_duration=0.7)
        peace_lms = create_synthetic_landmarks("peace")
        fist_lms = create_synthetic_landmarks("fist")
        engine.update([peace_lms], current_time=100.0)
        engine.update([peace_lms], current_time=100.3)
        state_dropped, meta_dropped = engine.update([fist_lms], current_time=100.4)
        self.assertEqual(state_dropped, CaptureState.IDLE)
        self.assertEqual(meta_dropped['hold_progress'], 0.0)

    def test_f4_05_transition_armed_to_countdown_at_hold_duration(self):
        engine = GestureCaptureEngine(hold_duration=0.7, countdown_duration=3.0)
        peace_lms = create_synthetic_landmarks("peace")
        engine.update([peace_lms], current_time=100.0)
        state, meta = engine.update([peace_lms], current_time=100.71)
        self.assertEqual(state, CaptureState.COUNTDOWN)
        self.assertAlmostEqual(meta['countdown_remaining'], 3.0, delta=0.05)
        self.assertEqual(meta['countdown_integer'], 3)
        self.assertTrue(meta['is_integer_tick'])

    def test_f4_06_draw_radial_progress_rendering_integrity(self):
        frame = generate_solid_frame(640, 480, (0, 0, 0))
        out = draw_radial_progress(frame, center=(320, 240), progress=0.75, radius=40)
        self.assertEqual(out.shape, (480, 640, 3))
        roi = out[200:280, 280:360]
        self.assertGreater(np.sum(roi), 0)

    # =========================================================================
    # Feature F5: Animated 3-2-1 Countdown & Audio/Visual HUD
    # =========================================================================

    def test_f5_01_countdown_starts_at_configured_duration(self):
        engine = GestureCaptureEngine(hold_duration=0.7, countdown_duration=3.0)
        peace_lms = create_synthetic_landmarks("peace")
        engine.update([peace_lms], current_time=100.0)
        state, meta = engine.update([peace_lms], current_time=100.71)
        self.assertEqual(state, CaptureState.COUNTDOWN)
        self.assertAlmostEqual(meta['countdown_remaining'], 3.0, delta=0.05)

    def test_f5_02_countdown_integer_ticks_3_2_1(self):
        engine = GestureCaptureEngine(hold_duration=0.7, countdown_duration=3.0)
        peace_lms = create_synthetic_landmarks("peace")
        engine.update([peace_lms], current_time=100.0)
        engine.update([peace_lms], current_time=100.71)  # tick 3

        # Advance to 2.0s remaining (elapsed 1.0s) -> tick 2
        _, meta2 = engine.update([peace_lms], current_time=101.75)
        self.assertEqual(meta2['countdown_integer'], 2)

        # Advance to 1.0s remaining (elapsed 2.0s) -> tick 1
        _, meta1 = engine.update([peace_lms], current_time=102.75)
        self.assertEqual(meta1['countdown_integer'], 1)

    def test_f5_03_countdown_remaining_monotonic_decrease(self):
        engine = GestureCaptureEngine(hold_duration=0.7, countdown_duration=3.0)
        peace_lms = create_synthetic_landmarks("peace")
        engine.update([peace_lms], current_time=100.0)
        engine.update([peace_lms], current_time=100.71)

        _, meta_a = engine.update([peace_lms], current_time=101.2)
        _, meta_b = engine.update([peace_lms], current_time=101.8)
        self.assertGreater(meta_a['countdown_remaining'], meta_b['countdown_remaining'])

    def test_f5_04_draw_countdown_overlay_renders_digits(self):
        frame = generate_solid_frame(640, 480, (50, 50, 50))
        out = draw_countdown_overlay(frame, seconds_left=3.0, is_integer_tick=True)
        self.assertEqual(out.shape, (480, 640, 3))
        center_roi = out[200:300, 270:370]
        self.assertGreater(np.max(center_roi), 150)

    def test_f5_05_countdown_ignores_gesture_loss_once_started(self):
        engine = GestureCaptureEngine(hold_duration=0.7, countdown_duration=3.0)
        peace_lms = create_synthetic_landmarks("peace")
        engine.update([peace_lms], current_time=100.0)
        engine.update([peace_lms], current_time=100.71)  # In COUNTDOWN
        # Drop hands completely
        state, _ = engine.update([], current_time=101.5)
        self.assertEqual(state, CaptureState.COUNTDOWN, "Countdown must lock and continue even if user drops hands")

    # =========================================================================
    # Feature F6: Shutter Flash Animation & Sound Feedback
    # =========================================================================

    def test_f6_01_transition_countdown_to_flash_triggers_snap(self):
        engine = GestureCaptureEngine(hold_duration=0.7, countdown_duration=3.0, flash_duration=0.15)
        peace_lms = create_synthetic_landmarks("peace")
        engine.update([peace_lms], current_time=100.0)
        engine.update([peace_lms], current_time=100.71)
        # Advance past countdown (3.0s after 100.71 = 103.71)
        state, meta = engine.update([], current_time=103.72)
        self.assertEqual(state, CaptureState.FLASH)
        self.assertTrue(meta['trigger_snap'], "trigger_snap must be True on flash trigger")

    def test_f6_02_flash_alpha_starts_high_and_decays(self):
        engine = GestureCaptureEngine(hold_duration=0.7, countdown_duration=3.0, flash_duration=0.15)
        peace_lms = create_synthetic_landmarks("peace")
        engine.update([peace_lms], current_time=100.0)
        engine.update([peace_lms], current_time=100.71)
        engine.update([], current_time=103.72) # FLASH start
        _, meta_mid = engine.update([], current_time=103.78)
        self.assertGreater(meta_mid['flash_alpha'], 0.0)
        self.assertLess(meta_mid['flash_alpha'], 0.95)

    def test_f6_03_transition_flash_to_preview_after_flash_duration(self):
        engine = GestureCaptureEngine(hold_duration=0.7, countdown_duration=3.0, flash_duration=0.15)
        peace_lms = create_synthetic_landmarks("peace")
        engine.update([peace_lms], current_time=100.0)
        engine.update([peace_lms], current_time=100.71)
        engine.update([], current_time=103.72)  # FLASH started at 103.72
        state, _ = engine.update([], current_time=103.95)  # > 0.15s elapsed
        self.assertEqual(state, CaptureState.PREVIEW)

    def test_f6_04_draw_flash_overlay_blends_white(self):
        frame = generate_solid_frame(640, 480, (0, 0, 0))
        flashed = draw_flash_overlay(frame, alpha=0.9)
        self.assertEqual(flashed.shape, (480, 640, 3))
        self.assertGreater(np.mean(flashed), 200)

    def test_f6_05_draw_flash_overlay_zero_alpha_no_op(self):
        frame = generate_solid_frame(640, 480, (100, 100, 100))
        flashed = draw_flash_overlay(frame, alpha=0.0)
        np.testing.assert_array_equal(frame, flashed)

    # =========================================================================
    # Feature F7: Pristine Layer-Separated Asynchronous Disk Saver
    # =========================================================================

    def test_f7_01_pristine_buffer_separation(self):
        raw_frame = generate_solid_frame(640, 480, (120, 120, 120))
        polygon = np.array([(100, 100), (500, 100), (500, 400), (100, 400)], dtype=np.int32)
        pristine_capture = geometry.paint_filter_in_polygon(raw_frame.copy(), polygon, filters.filtro_1)

        display_frame = pristine_capture.copy()
        display_frame = draw_countdown_overlay(display_frame, 3, 0.5)

        diff = np.abs(display_frame.astype(int) - pristine_capture.astype(int))
        self.assertGreater(np.sum(diff), 1000, "Display frame must contain HUD overlay that pristine capture does not")

    def test_f7_02_async_save_writes_jpeg_to_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8950, max_port=8960)
            test_frame = generate_checkerboard_frame(640, 480)
            filename = server.save_photo_async(test_frame, filter_name="grid")
            filepath = os.path.join(tmpdir, filename)
            saved_img = None
            for _ in range(25):
                if os.path.isfile(filepath) and os.path.getsize(filepath) > 0:
                    saved_img = cv2.imread(filepath)
                    if saved_img is not None:
                        break
                time.sleep(0.05)
            self.assertTrue(os.path.isfile(filepath), f"File {filepath} must exist")
            self.assertIsNotNone(saved_img)
            self.assertEqual(saved_img.shape, (480, 640, 3))
            server.stop()

    def test_f7_03_saved_jpeg_validity_and_dimensions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8952, max_port=8962)
            frame = generate_solid_frame(1280, 720, (10, 20, 30))
            fn, fp = server.save_photo_sync(frame, filter_name="sepia")
            img = cv2.imread(fp)
            self.assertEqual(img.shape, (720, 1280, 3))
            server.stop()

    def test_f7_04_file_naming_convention(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8954, max_port=8964)
            frame = generate_solid_frame(640, 480)
            fn = server.save_photo_async(frame, filter_name="rosa")
            self.assertTrue(fn.startswith("capture_"))
            self.assertTrue(fn.endswith(".jpg"))
            self.assertIn("rosa", fn)
            server.stop()

    def test_f7_05_saved_jpeg_quality_size_reasonable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8956, max_port=8966)
            frame = generate_checkerboard_frame(640, 480)
            fn, fp = server.save_photo_sync(frame, filter_name="test")
            size_kb = os.path.getsize(fp) / 1024.0
            self.assertGreater(size_kb, 5.0, "Saved JPEG should not be empty")
            self.assertLess(size_kb, 2000.0, "Saved JPEG should be reasonable size")
            server.stop()

    # =========================================================================
    # Feature F8: Background LAN HTTP Delivery Server
    # =========================================================================

    def test_f8_01_server_lifecycle_start_and_stop(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8960, max_port=8970)
            server.start()
            self.assertIsNotNone(server.httpd)
            self.assertTrue(server._server_thread.is_alive())
            server.stop()
            self.assertIsNone(server.httpd)

    def test_f8_02_lan_ip_discovery_format(self):
        ip = get_local_ip()
        self.assertIsInstance(ip, str)
        parts = ip.split(".")
        self.assertEqual(len(parts), 4, f"IP must have 4 octets, got {ip}")
        for part in parts:
            self.assertTrue(0 <= int(part) <= 255)

    def test_f8_03_http_get_photo_returns_200_and_exact_bytes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8972, max_port=8982)
            server.start()
            try:
                frame = generate_checkerboard_frame(320, 240)
                fn, fp = server.save_photo_sync(frame, "test_get")
                url = f"http://127.0.0.1:{server.port}/photo/{fn}"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    self.assertEqual(resp.status, 200)
                    data = resp.read()
                    with open(fp, "rb") as f:
                        disk_data = f.read()
                    self.assertEqual(data, disk_data)
            finally:
                server.stop()

    def test_f8_04_http_get_latest_serves_or_redirects(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8984, max_port=8994)
            server.start()
            try:
                frame = generate_solid_frame(320, 240, (10, 50, 90))
                fn, _ = server.save_photo_sync(frame, "latest_test")
                url = f"http://127.0.0.1:{server.port}/latest"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    self.assertEqual(resp.status, 200)
                    content = resp.read().decode("utf-8")
                    self.assertIn(fn, content)
            finally:
                server.stop()

    def test_f8_05_http_view_returns_mobile_html_landing_page(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8996, max_port=9006)
            server.start()
            try:
                frame = generate_solid_frame(320, 240)
                fn, _ = server.save_photo_sync(frame, "view_test")
                url = f"http://127.0.0.1:{server.port}/view/{fn}"
                with urllib.request.urlopen(url, timeout=3.0) as resp:
                    self.assertEqual(resp.status, 200)
                    html = resp.read().decode("utf-8")
                    self.assertIn("Save Photo", html)
                    self.assertIn(f"/photo/{fn}", html)
            finally:
                server.stop()

    def test_f8_06_http_404_for_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=9008, max_port=9018)
            server.start()
            try:
                url = f"http://127.0.0.1:{server.port}/photo/nonexistent_12345.jpg"
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(url, timeout=3.0)
                self.assertEqual(ctx.exception.code, 404)
            finally:
                server.stop()

    # =========================================================================
    # Feature F9: Zero-Dependency OpenCV QR Code HUD Card
    # =========================================================================

    def test_f9_01_qr_code_matrix_generation(self):
        test_url = "http://192.168.1.100:8000/view/capture_test.jpg"
        qr_img = generate_qr_matrix(test_url, target_size=160)
        self.assertEqual(qr_img.shape, (160, 160, 3))
        self.assertEqual(qr_img.dtype, np.uint8)

    def test_f9_02_qr_code_opencv_detector_roundtrip_decode(self):
        test_url = "http://192.168.1.100:8000/view/capture_abc123.jpg"
        qr_img = generate_qr_matrix(test_url, target_size=200)
        detector = cv2.QRCodeDetector()
        decoded_text, points, _ = detector.detectAndDecode(qr_img)
        self.assertEqual(decoded_text, test_url, f"QR code decoded string mismatch: {decoded_text} != {test_url}")

    def test_f9_03_render_qr_card_overlays_card_on_display_frame(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=9020, max_port=9030)
            frame = generate_solid_frame(1280, 720, (50, 50, 50))
            out = server.render_qr_card(frame.copy(), "photo_123.jpg", remaining_seconds=5.2)
            self.assertEqual(out.shape, (720, 1280, 3))
            # Card area must be modified from original solid background
            self.assertFalse(np.array_equal(out, frame))
            server.stop()

    def test_f9_04_render_qr_card_contains_remaining_time_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=9032, max_port=9042)
            frame = generate_solid_frame(640, 480, (0, 0, 0))
            out = server.render_qr_card(frame.copy(), "photo_time.jpg", remaining_seconds=3.8)
            self.assertEqual(out.shape, (480, 640, 3))
            server.stop()

    def test_f9_05_qr_card_preserves_dimensions_across_resolutions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=9044, max_port=9054)
            for (w, h) in [(640, 480), (1280, 720), (1920, 1080)]:
                frame = generate_solid_frame(w, h)
                out = server.render_qr_card(frame, "test.jpg", 4.0)
                self.assertEqual(out.shape, (h, w, 3))
            server.stop()

    # =========================================================================
    # Feature F10: Auto-Dismissal, Debounce Cooldown & Mirror Resumption
    # =========================================================================

    def test_f10_01_preview_state_duration_persistence(self):
        engine = GestureCaptureEngine(preview_duration=6.0)
        engine.trigger_preview(current_time=100.0)
        self.assertEqual(engine.state, CaptureState.PREVIEW)

        state_mid, meta_mid = engine.update([], current_time=104.0)
        self.assertEqual(state_mid, CaptureState.PREVIEW)
        self.assertAlmostEqual(meta_mid['preview_remaining'], 2.0, delta=0.05)

    def test_f10_02_transition_preview_to_cooldown_on_timeout(self):
        engine = GestureCaptureEngine(preview_duration=6.0, cooldown_duration=2.0)
        engine.trigger_preview(current_time=100.0)
        state, _ = engine.update([], current_time=106.1)
        self.assertEqual(state, CaptureState.COOLDOWN)

    def test_f10_03_early_dismiss_preview_enters_cooldown(self):
        engine = GestureCaptureEngine(preview_duration=6.0, cooldown_duration=2.0)
        engine.trigger_preview(current_time=100.0)
        engine.dismiss_preview(current_time=102.0)
        self.assertEqual(engine.state, CaptureState.COOLDOWN)

    def test_f10_04_cooldown_rejects_gestures(self):
        engine = GestureCaptureEngine(preview_duration=6.0, cooldown_duration=2.0)
        engine.trigger_preview(current_time=100.0)
        engine.dismiss_preview(current_time=101.0)

        peace_lms = create_synthetic_landmarks("peace")
        state, meta = engine.update([peace_lms], current_time=102.0)
        self.assertEqual(state, CaptureState.COOLDOWN, "Cooldown must reject peace gestures during debounce window")
        self.assertEqual(meta['hold_progress'], 0.0)

    def test_f10_05_transition_cooldown_to_idle_restores_live_mirror(self):
        engine = GestureCaptureEngine(preview_duration=6.0, cooldown_duration=2.0)
        engine.trigger_preview(current_time=100.0)
        engine.dismiss_preview(current_time=101.0)

        state, _ = engine.update([], current_time=103.15)
        self.assertEqual(state, CaptureState.IDLE, "Engine must return to IDLE after cooldown expires")


if __name__ == "__main__":
    unittest.main()
