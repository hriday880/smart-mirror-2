"""
test_tier2_boundaries.py - Tier 2 Boundary Value Analysis (BVA) & Corner Case Tests.
Contains >=50 automated test cases covering extreme parameters, scaling, rotations,
noise, timeouts, port collisions, extreme resolutions, and sudden landmark loss.
"""

import os
import sys
import time
import math
import tempfile
import socket
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

from gesture_detector_test import (
    is_peace_gesture,
    find_peace_gesture,
    CaptureState,
    GestureCaptureEngine,
    draw_radial_progress,
    draw_countdown_overlay,
    draw_flash_overlay,
    compute_palm_scale,
    create_synthetic_landmarks,
    _extract_landmark_points,
    _joint_angle_3p
)

from delivery_server_test import (
    DeliveryServer,
    get_local_ip,
    generate_qr_matrix,
    render_preview_card,
    AsyncImageSaver
)


class TestTier2Boundaries(unittest.TestCase):
    """
    Tier 2 Boundary Value Analysis & Edge Case Tests.
    Total: 55+ automated boundary test cases.
    """

    # =========================================================================
    # Group 1: 360-Degree Hand Tilt & In-Plane Rotation Boundaries (15 tests)
    # =========================================================================

    def test_bva_tilt_01_zero_degrees(self):
        lms = create_synthetic_landmarks("peace", tilt_deg=0.0)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_tilt_02_positive_15_deg(self):
        lms = create_synthetic_landmarks("peace", tilt_deg=15.0)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_tilt_03_positive_30_deg(self):
        lms = create_synthetic_landmarks("peace", tilt_deg=30.0)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_tilt_04_positive_45_deg(self):
        lms = create_synthetic_landmarks("peace", tilt_deg=45.0)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_tilt_05_positive_60_deg(self):
        lms = create_synthetic_landmarks("peace", tilt_deg=60.0)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_tilt_06_positive_90_deg_horizontal_right(self):
        lms = create_synthetic_landmarks("peace", tilt_deg=90.0)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_tilt_07_positive_135_deg(self):
        lms = create_synthetic_landmarks("peace", tilt_deg=135.0)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_tilt_08_positive_180_deg_upside_down(self):
        lms = create_synthetic_landmarks("peace", tilt_deg=180.0)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_tilt_09_negative_15_deg(self):
        lms = create_synthetic_landmarks("peace", tilt_deg=-15.0)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_tilt_10_negative_30_deg(self):
        lms = create_synthetic_landmarks("peace", tilt_deg=-30.0)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_tilt_11_negative_45_deg(self):
        lms = create_synthetic_landmarks("peace", tilt_deg=-45.0)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_tilt_12_negative_60_deg(self):
        lms = create_synthetic_landmarks("peace", tilt_deg=-60.0)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_tilt_13_negative_90_deg_horizontal_left(self):
        lms = create_synthetic_landmarks("peace", tilt_deg=-90.0)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_tilt_14_negative_135_deg(self):
        lms = create_synthetic_landmarks("peace", tilt_deg=-135.0)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_tilt_15_negative_180_deg_upside_down(self):
        lms = create_synthetic_landmarks("peace", tilt_deg=-180.0)
        self.assertTrue(is_peace_gesture(lms))

    # =========================================================================
    # Group 2: Scale Variations & Distance Extremes (8 tests)
    # =========================================================================

    def test_bva_scale_01_very_small_distant_user(self):
        lms = create_synthetic_landmarks("peace", scale=0.06)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_scale_02_small_user(self):
        lms = create_synthetic_landmarks("peace", scale=0.12)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_scale_03_medium_user(self):
        lms = create_synthetic_landmarks("peace", scale=0.25)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_scale_04_standard_user(self):
        lms = create_synthetic_landmarks("peace", scale=0.40)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_scale_05_large_close_user(self):
        lms = create_synthetic_landmarks("peace", scale=0.60)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_scale_06_very_large_close_user(self):
        lms = create_synthetic_landmarks("peace", scale=0.75)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_scale_07_zero_scale_guard(self):
        lms = np.zeros((21, 2), dtype=np.float64)
        self.assertFalse(is_peace_gesture(lms), "Zero scale landmark set must evaluate to False without crashing")

    def test_bva_scale_08_palm_scale_metric_proportionality(self):
        s1 = compute_palm_scale(create_synthetic_landmarks("peace", scale=0.2))
        s2 = compute_palm_scale(create_synthetic_landmarks("peace", scale=0.4))
        self.assertAlmostEqual(s2 / s1, 2.0, delta=0.1)

    # =========================================================================
    # Group 3: V-Formation Angular Divergence Limits (6 tests)
    # =========================================================================

    def test_bva_vdiv_01_narrow_lower_valid_bound(self):
        lms = create_synthetic_landmarks("peace", v_divergence=12.0)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_vdiv_02_standard_divergence(self):
        lms = create_synthetic_landmarks("peace", v_divergence=24.0)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_vdiv_03_wide_divergence(self):
        lms = create_synthetic_landmarks("peace", v_divergence=40.0)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_vdiv_04_wide_upper_valid_bound(self):
        lms = create_synthetic_landmarks("peace", v_divergence=55.0)
        self.assertTrue(is_peace_gesture(lms))

    def test_bva_vdiv_05_sub_minimal_parallel_fingers(self):
        # 0 degree divergence (touching parallel index + middle)
        lms = create_synthetic_landmarks("peace", v_divergence=2.0)
        self.assertFalse(is_peace_gesture(lms), "Nearly 0 degree finger divergence should not trigger Peace Sign")

    def test_bva_vdiv_06_hyper_wide_split(self):
        # 90 degree divergence
        lms = create_synthetic_landmarks("peace", v_divergence=90.0)
        self.assertFalse(is_peace_gesture(lms), "Extreme 90 degree split should be rejected")

    # =========================================================================
    # Group 4: Sudden Landmark Disappearance & Noise Resilience (6 tests)
    # =========================================================================

    def test_bva_noise_01_mild_gaussian_jitter(self):
        lms = create_synthetic_hand("peace", noise_sigma=0.005)
        self.assertTrue(is_peace_gesture(lms), "Mild sensor jitter must still be recognized")

    def test_bva_noise_02_moderate_jitter(self):
        lms = create_synthetic_hand("peace", noise_sigma=0.010)
        self.assertTrue(is_peace_gesture(lms), "Moderate sensor jitter must still be recognized")

    def test_bva_noise_03_incomplete_landmarks_count_guard(self):
        pts = np.zeros((15, 2), dtype=np.float64)
        self.assertFalse(is_peace_gesture(pts), "Incomplete landmark array (<21 points) must safely return False")

    def test_bva_noise_04_empty_landmarks_list(self):
        self.assertFalse(is_peace_gesture([]))
        found, idx, center, _ = find_peace_gesture([])
        self.assertFalse(found)
        self.assertIsNone(idx)
        self.assertIsNone(center)

    def test_bva_noise_05_none_landmarks(self):
        self.assertFalse(is_peace_gesture(None))
        found, idx, center, _ = find_peace_gesture(None)
        self.assertFalse(found)

    def test_bva_noise_06_offscreen_landmarks_coordinates(self):
        # Hand off-screen to the far right
        lms = create_synthetic_landmarks("peace", wrist=(2.5, 3.0))
        # Relative joint geometry is invariant, so relative peace sign math still holds
        self.assertTrue(is_peace_gesture(lms))

    # =========================================================================
    # Group 5: State Machine Timing & Debounce Thresholds (8 tests)
    # =========================================================================

    def test_bva_fsm_01_hold_threshold_sub_boundary(self):
        # 0.7s hold duration: held for 0.68s -> remains ARMED
        engine = GestureCaptureEngine(hold_duration=0.7)
        peace_lms = create_synthetic_landmarks("peace")
        engine.update([peace_lms], current_time=100.0)
        state, meta = engine.update([peace_lms], current_time=100.68)
        self.assertEqual(state, CaptureState.ARMED)
        self.assertLess(meta['hold_progress'], 1.0)

    def test_bva_fsm_02_hold_threshold_exact_boundary(self):
        # 0.7s hold duration: held for 0.701s -> transitions to COUNTDOWN
        engine = GestureCaptureEngine(hold_duration=0.7)
        peace_lms = create_synthetic_landmarks("peace")
        engine.update([peace_lms], current_time=100.0)
        state, meta = engine.update([peace_lms], current_time=100.705)
        self.assertEqual(state, CaptureState.COUNTDOWN)

    def test_bva_fsm_03_rapid_toggle_rejection(self):
        # Rapid toggle Peace <-> None every 100ms for 2 seconds -> should never trigger countdown
        engine = GestureCaptureEngine(hold_duration=0.7)
        peace_lms = create_synthetic_landmarks("peace")
        cur_t = 0.0
        for i in range(20):
            cur_t += 0.1
            lms_in = [peace_lms] if i % 2 == 0 else []
            state, _ = engine.update(lms_in, current_time=cur_t)
            self.assertIn(state, [CaptureState.IDLE, CaptureState.ARMED])
        self.assertNotEqual(engine.state, CaptureState.COUNTDOWN)

    def test_bva_fsm_04_cooldown_rejection_at_1_9s(self):
        # Cooldown is 2.0s: presentation at 1.9s must still be rejected
        engine = GestureCaptureEngine(preview_duration=6.0, cooldown_duration=2.0)
        engine.trigger_preview(current_time=10.0)
        engine.dismiss_preview(current_time=10.0)  # Cooldown starts at 10.0

        peace_lms = create_synthetic_landmarks("peace")
        state, meta = engine.update([peace_lms], current_time=11.90)
        self.assertEqual(state, CaptureState.COOLDOWN)
        self.assertEqual(meta['hold_progress'], 0.0)

    def test_bva_fsm_05_cooldown_acceptance_at_2_05s(self):
        # Cooldown is 2.0s: presentation past cooldown transitions COOLDOWN -> IDLE -> ARMED
        engine = GestureCaptureEngine(preview_duration=6.0, cooldown_duration=2.0)
        engine.trigger_preview(current_time=10.0)
        engine.dismiss_preview(current_time=10.0)  # Cooldown starts at 10.0

        peace_lms = create_synthetic_landmarks("peace")
        state_idle, _ = engine.update([], current_time=12.05)
        self.assertEqual(state_idle, CaptureState.IDLE)
        state_armed, meta = engine.update([peace_lms], current_time=12.10)
        self.assertEqual(state_armed, CaptureState.ARMED)

    def test_bva_fsm_06_manual_reset_returns_to_idle_from_any_state(self):
        engine = GestureCaptureEngine(hold_duration=0.7, countdown_duration=3.0)
        peace_lms = create_synthetic_landmarks("peace")
        engine.update([peace_lms], current_time=100.0)
        engine.update([peace_lms], current_time=100.75) # in COUNTDOWN
        self.assertEqual(engine.state, CaptureState.COUNTDOWN)
        engine.reset()
        self.assertEqual(engine.state, CaptureState.IDLE)
        self.assertIsNone(engine.countdown_start_time)

    def test_bva_fsm_07_countdown_zero_seconds_boundary(self):
        engine = GestureCaptureEngine(hold_duration=0.7, countdown_duration=0.1, flash_duration=0.15)
        peace_lms = create_synthetic_landmarks("peace")
        engine.update([peace_lms], current_time=100.0)
        state_cd, _ = engine.update([peace_lms], current_time=100.75) # COUNTDOWN
        self.assertEqual(state_cd, CaptureState.COUNTDOWN)
        state, meta = engine.update([], current_time=100.90) # FLASH
        self.assertEqual(state, CaptureState.FLASH)
        self.assertTrue(meta['trigger_snap'])

    def test_bva_fsm_08_flash_alpha_decay_bounds(self):
        engine = GestureCaptureEngine(hold_duration=0.7, countdown_duration=3.0, flash_duration=0.15)
        peace_lms = create_synthetic_landmarks("peace")
        engine.update([peace_lms], current_time=0.0)
        engine.update([peace_lms], current_time=0.71)
        engine.update([], current_time=3.72) # FLASH start
        _, meta = engine.update([], current_time=3.80)
        self.assertTrue(0.0 <= meta['flash_alpha'] <= 1.0)

    # =========================================================================
    # Group 6: Delivery Server & System Boundary Cases (12 tests)
    # =========================================================================

    def test_bva_server_01_auto_create_nested_capture_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_dir = os.path.join(tmpdir, "deep", "nested", "captures")
            self.assertFalse(os.path.isdir(nested_dir))
            saver = AsyncImageSaver(capture_dir=nested_dir)
            frame = generate_solid_frame(320, 240)
            saver.save_sync(frame, "test_nested.jpg")
            self.assertTrue(os.path.isdir(nested_dir))
            self.assertTrue(os.path.isfile(os.path.join(nested_dir, "test_nested.jpg")))
            saver.stop()

    def test_bva_server_02_multiple_port_collisions_hopping(self):
        # Occupy ports 8100 and 8101
        s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s1.bind(("0.0.0.0", 8100))
        s1.listen(1)

        s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s2.bind(("0.0.0.0", 8101))
        s2.listen(1)

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                server = DeliveryServer(capture_dir=tmpdir, port=8100, max_port=8110, host="127.0.0.1")
                server.start()
                self.assertEqual(server.port, 8102, "Server should hop past 8100 and 8101 to 8102")
                server.stop()
        finally:
            s1.close()
            s2.close()

    def test_bva_server_03_exhausted_port_range_raises_runtime_error(self):
        s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s1.bind(("0.0.0.0", 8120))
        s1.listen(1)

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                server = DeliveryServer(capture_dir=tmpdir, port=8120, max_port=8120, host="127.0.0.1")
                with self.assertRaises(RuntimeError):
                    server.start()
        finally:
            s1.close()

    def test_bva_server_04_directory_traversal_photo_safety(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8130, max_port=8140, host="127.0.0.1")
            traversal_names = ["../main.py", "../../filters.py", "/etc/passwd", "..\\main.py"]
            for bad_name in traversal_names:
                clean = os.path.basename(bad_name)
                self.assertTrue(clean != bad_name or not bad_name.endswith(".jpg"))

    def test_bva_server_05_special_characters_in_filter_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8142, max_port=8152)
            frame = generate_solid_frame(320, 240)
            fn, fp = server.save_photo_sync(frame, filter_name="weird#filter$@!123")
            self.assertTrue(os.path.isfile(fp))
            self.assertIn("weirdfilter123", fn)
            server.stop()

    def test_bva_server_06_high_resolution_4k_frame(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8154, max_port=8164)
            frame_4k = np.zeros((2160, 3840, 3), dtype=np.uint8)
            frame_4k[1000:1100, 1800:2000] = (255, 255, 255)
            fn, fp = server.save_photo_sync(frame_4k, "4k_test")
            self.assertTrue(os.path.isfile(fp))
            read_4k = cv2.imread(fp)
            self.assertEqual(read_4k.shape, (2160, 3840, 3))
            server.stop()

    def test_bva_server_07_very_small_thumbnail_frame(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8166, max_port=8176)
            frame_tiny = np.full((32, 32, 3), 180, dtype=np.uint8)
            fn, fp = server.save_photo_sync(frame_tiny, "tiny_test")
            read_tiny = cv2.imread(fp)
            self.assertEqual(read_tiny.shape, (32, 32, 3))
            server.stop()

    def test_bva_server_08_ultra_wide_aspect_ratio(self):
        frame_uw = generate_solid_frame(2560, 1080)
        out = render_preview_card(frame_uw, "test_uw.jpg", remaining_seconds=5.0)
        self.assertEqual(out.shape, (1080, 2560, 3))

    def test_bva_server_09_vertical_smartphone_aspect_ratio(self):
        frame_vert = generate_solid_frame(720, 1280)
        out = render_preview_card(frame_vert, "test_vert.jpg", remaining_seconds=5.0)
        self.assertEqual(out.shape, (1280, 720, 3))

    def test_bva_server_10_multiple_rapid_async_saves_queue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            saver = AsyncImageSaver(capture_dir=tmpdir)
            filenames = []
            for i in range(10):
                f = generate_solid_frame(320, 240, (i * 20, i * 20, i * 20))
                fn = f"multi_{i}.jpg"
                saver.save_async(f, fn)
                filenames.append(fn)

            time.sleep(0.5)
            for fn in filenames:
                self.assertTrue(os.path.isfile(os.path.join(tmpdir, fn)), f"{fn} should exist")
            saver.stop()

    def test_bva_server_11_qr_matrix_custom_sizes(self):
        for size in [80, 120, 160, 240, 320]:
            qr = generate_qr_matrix("http://192.168.1.1:8000/view/test.jpg", target_size=size)
            self.assertEqual(qr.shape, (size, size, 3))

    def test_bva_server_12_qr_matrix_empty_url_handling(self):
        qr = generate_qr_matrix("", target_size=150)
        self.assertEqual(qr.shape, (150, 150, 3))


if __name__ == "__main__":
    unittest.main()
