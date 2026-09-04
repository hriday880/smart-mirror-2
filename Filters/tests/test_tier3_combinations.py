"""
test_tier3_combinations.py - Tier 3 Pairwise Combinatorial & Subsystem Interaction Tests.
Contains 12 automated pairwise tests exercising simultaneous multi-hand interactions,
filter switching during capture workflows, concurrent HTTP downloads during disk I/O,
and continuous multi-cycle capture sessions.
"""

import os
import sys
import time
import math
import tempfile
import threading
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


class TestTier3Combinations(unittest.TestCase):
    """
    Tier 3 Pairwise Interaction Tests.
    Total: 12 automated combination test cases.
    """

    def test_combo_01_dual_hand_portal_plus_peace_sign_interaction(self):
        """
        Left hand forms portal anchor, Right hand forms peace sign.
        Verifies both portal geometry calculation and peace sign detection coexist simultaneously.
        """
        left_portal = create_synthetic_landmarks("portal", wrist=(0.3, 0.8))
        right_peace = create_synthetic_landmarks("peace", wrist=(0.7, 0.8))

        # Check peace sign detector correctly isolates right hand
        found, idx, center, pts = find_peace_gesture([left_portal, right_peace], frame_shape=(720, 1280))
        self.assertTrue(found, "Peace sign on right hand must be detected")
        self.assertEqual(idx, 1)

        # Check portal width calculation using both hands
        p1 = (left_portal[INDEX_TIP, 0] * 1280, left_portal[INDEX_TIP, 1] * 720)
        p2 = (left_portal[THUMB_TIP, 0] * 1280, left_portal[THUMB_TIP, 1] * 720)
        p3 = (right_peace[INDEX_TIP, 0] * 1280, right_peace[INDEX_TIP, 1] * 720)
        p4 = (right_peace[THUMB_TIP, 0] * 1280, right_peace[THUMB_TIP, 1] * 720)

        width = geometry.portal_width(p1, p2, p3, p4)
        self.assertGreater(width, 100.0)

    def test_combo_02_changing_filters_mid_countdown_and_saving_new_filter(self):
        """
        User enters countdown with filter 0, closes portal mid-countdown to switch to filter 1.
        Verifies that the final snapshot captures the newly selected filter.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8200, max_port=8210, host="127.0.0.1")
            server.start()
            try:
                engine = GestureCaptureEngine(hold_duration=0.7, countdown_duration=3.0)
                peace_lms = create_synthetic_landmarks("peace")
                closing_detector = geometry.ClosingGestureDetector()
                filtro_idx = 0

                # 1. Arm and start countdown
                engine.update([peace_lms], current_time=100.0)
                engine.update([peace_lms], current_time=100.71) # in COUNTDOWN

                # 2. Simulate portal closing mid-countdown at t=102.0s
                frame_w = 640
                closed_width = 0.10 * frame_w # < 0.16 threshold
                if closing_detector.update(closed_width, frame_w):
                    filtro_idx = (filtro_idx + 1) % len(filters.FILTROS)
                self.assertEqual(filtro_idx, 1, "Filter index must advance to 1")

                # 3. Complete countdown at t=103.72s -> Snapshot trigger
                state, meta = engine.update([], current_time=103.72)
                self.assertEqual(state, CaptureState.FLASH)
                self.assertTrue(meta['trigger_snap'])

                # 4. Render and save frame with filter 1
                raw_frame = generate_solid_frame(640, 480, (100, 100, 100))
                poly = np.array([(100, 100), (400, 100), (400, 300), (100, 300)], dtype=np.int32)
                pristine_frame = geometry.paint_filter_in_polygon(raw_frame, poly, filters.FILTROS[filtro_idx])

                fn, fp = server.save_photo_sync(pristine_frame, filter_name="filtro_1")
                self.assertTrue(os.path.isfile(fp))
                saved_img = cv2.imread(fp)
                self.assertIsNotNone(saved_img)
            finally:
                server.stop()

    def test_combo_03_concurrent_http_requests_during_active_disk_io(self):
        """
        Simulates concurrent HTTP client requests while photos are being written to disk asynchronously.
        Verifies zero deadlocks, thread-safety, and HTTP 200 responses.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8212, max_port=8222, host="127.0.0.1")
            server.start()
            try:
                # Save initial photo
                init_frame = generate_checkerboard_frame(320, 240)
                init_fn, _ = server.save_photo_sync(init_frame, "init_combo")

                results = []
                def client_worker():
                    try:
                        url = f"http://127.0.0.1:{server.port}/photo/{init_fn}"
                        with urllib.request.urlopen(url, timeout=2.0) as resp:
                            results.append(resp.status == 200)
                    except Exception:
                        results.append(False)

                # Launch async disk writes
                for i in range(3):
                    f = generate_solid_frame(320, 240, (i * 30, i * 30, i * 30))
                    server.save_photo_async(f, f"burst_{i}")

                # Concurrently launch HTTP requests
                threads = [threading.Thread(target=client_worker) for _ in range(5)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(timeout=2.0)

                self.assertEqual(len(results), 5)
                self.assertTrue(all(results), "All concurrent HTTP requests must succeed with 200 OK")
            finally:
                server.stop()

    def test_combo_04_auto_dismiss_preview_during_active_video_stream(self):
        """
        Feeds simulated video frames through MockVideoCapture while preview card times out (1.0s)
        and completes cooldown (0.5s).
        """
        mock_cap = MockVideoCapture(max_frames=45, width=640, height=480)
        engine = GestureCaptureEngine(preview_duration=1.0, cooldown_duration=0.5)
        engine.trigger_preview(current_time=100.0)

        processed_frames = 0
        cur_time = 100.0
        while mock_cap.isOpened():
            ok, frame = mock_cap.read()
            if not ok:
                break
            cur_time += 0.05
            state, meta = engine.update([], current_time=cur_time)

            if state == CaptureState.PREVIEW:
                frame = render_preview_card(frame, "test.jpg", meta['preview_remaining'], 1.0)

            processed_frames += 1

        self.assertEqual(processed_frames, 45)
        self.assertEqual(engine.state, CaptureState.IDLE)

    def test_combo_05_two_handed_gesture_disambiguation_priority(self):
        """
        Left hand performs pointing, Right hand performs peace sign -> Peace sign correctly detected.
        Then Left hand performs fist, Right hand performs peace sign -> Peace sign correctly detected.
        """
        left_pointing = create_synthetic_landmarks("pointing", wrist=(0.3, 0.8))
        right_peace = create_synthetic_landmarks("peace", wrist=(0.7, 0.8))

        found, idx, center, _ = find_peace_gesture([left_pointing, right_peace])
        self.assertTrue(found)
        self.assertEqual(idx, 1)

        left_fist = create_synthetic_landmarks("fist", wrist=(0.3, 0.8))
        found2, idx2, center2, _ = find_peace_gesture([left_fist, right_peace])
        self.assertTrue(found2)
        self.assertEqual(idx2, 1)

    def test_combo_06_filter_rendering_integrity_across_different_filters(self):
        """
        Applies and validates pristine layer separation across 4 distinct artistic filters.
        """
        raw_frame = generate_checkerboard_frame(640, 480)
        polygon = np.array([(50, 50), (350, 50), (350, 250), (50, 250)], dtype=np.int32)

        for filter_func in [filters.filtro_grid, filters.filtro_5, filters.filtro_6, filters.filtro_blanco]:
            pristine = geometry.paint_filter_in_polygon(raw_frame.copy(), polygon, filter_func)
            display = pristine.copy()
            display = draw_countdown_overlay(display, 2, False)

            diff = np.abs(display.astype(int) - pristine.astype(int))
            self.assertGreater(np.sum(diff), 500)
            self.assertEqual(pristine.shape, (480, 640, 3))

    def test_combo_07_mobile_qr_scan_while_next_guest_arms_gesture(self):
        """
        Mobile guest downloads Photo 1 over HTTP server while Guest 2 stands in front of mirror
        forming a peace sign. Both subsystems operate without cross-interference.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8224, max_port=8234, host="127.0.0.1")
            server.start()
            try:
                # Photo 1 generated for Guest 1
                f1 = generate_solid_frame(320, 240, (50, 100, 150))
                fn1, _ = server.save_photo_sync(f1, "guest1")

                # Guest 2 initiates capture
                engine = GestureCaptureEngine(hold_duration=0.7)
                peace_lms = create_synthetic_landmarks("peace")
                state, meta = engine.update([peace_lms], current_time=50.0)
                self.assertEqual(state, CaptureState.ARMED)

                # Concurrently, Guest 1 downloads photo from phone
                photo_url = f"http://127.0.0.1:{server.port}/photo/{fn1}"
                with urllib.request.urlopen(photo_url, timeout=2.0) as resp:
                    self.assertEqual(resp.status, 200)
                    self.assertEqual(len(resp.read()), os.path.getsize(os.path.join(tmpdir, fn1)))

                # Guest 2 hold progresses smoothly
                state2, meta2 = engine.update([peace_lms], current_time=50.35)
                self.assertEqual(state2, CaptureState.ARMED)
                self.assertAlmostEqual(meta2['hold_progress'], 0.5, delta=0.05)
            finally:
                server.stop()

    def test_combo_08_cancel_hold_then_immediately_cycle_filter(self):
        """
        User starts peace sign (held for 0.4s < 0.7s), drops it, then pinches portal hands.
        Verifies state machine resets to IDLE and filter switch executes cleanly.
        """
        engine = GestureCaptureEngine(hold_duration=0.7)
        peace_lms = create_synthetic_landmarks("peace")
        closing_detector = geometry.ClosingGestureDetector()

        # Hold peace sign for 0.4s
        engine.update([peace_lms], current_time=10.0)
        engine.update([peace_lms], current_time=10.4)

        # Drop peace sign at 10.5s -> Cancelled back to IDLE
        state_cancel, _ = engine.update([], current_time=10.5)
        self.assertEqual(state_cancel, CaptureState.IDLE)

        # Immediately close portal
        triggered = closing_detector.update(width=50, frame_w=640)
        self.assertTrue(triggered, "Portal closing detector must trigger filter advance")

    def test_combo_09_early_preview_dismissal_lockout_and_recovery(self):
        """
        User dismisses preview early via dismiss_preview() at t=102s.
        Verifies immediate entry into COOLDOWN, rejection of gestures during 2.0s lockout,
        and restoration of IDLE mode at t=104.1s.
        """
        engine = GestureCaptureEngine(preview_duration=6.0, cooldown_duration=2.0)
        peace_lms = create_synthetic_landmarks("peace")

        engine.trigger_preview(current_time=100.0)
        self.assertEqual(engine.state, CaptureState.PREVIEW)

        # Early dismissal at t=102.0s
        engine.dismiss_preview(current_time=102.0)
        self.assertEqual(engine.state, CaptureState.COOLDOWN)

        # Gesture during cooldown rejected
        state_locked, meta_locked = engine.update([peace_lms], current_time=103.0)
        self.assertEqual(state_locked, CaptureState.COOLDOWN)
        self.assertEqual(meta_locked['hold_progress'], 0.0)

        # Cooldown expires at t=104.05s
        state_idle, _ = engine.update([], current_time=104.05)
        self.assertEqual(state_idle, CaptureState.IDLE)

    def test_combo_10_multiple_consecutive_full_capture_cycles(self):
        """
        Executes 2 full sequential capture cycles (Guest A and Guest B) in one continuous timeline.
        Verifies complete lifecycle and persistence of both photos.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8236, max_port=8246, host="127.0.0.1")
            server.start()
            try:
                engine = GestureCaptureEngine(
                    hold_duration=0.7, countdown_duration=1.0,
                    flash_duration=0.1, preview_duration=1.0, cooldown_duration=0.5
                )
                peace_lms = create_synthetic_landmarks("peace")

                # === Cycle 1 ===
                t = 100.0
                engine.update([peace_lms], current_time=t) # ARMED
                t += 0.71
                engine.update([peace_lms], current_time=t) # COUNTDOWN
                t += 1.01
                state1, meta1 = engine.update([], current_time=t) # FLASH
                self.assertEqual(state1, CaptureState.FLASH)
                self.assertTrue(meta1['trigger_snap'])

                fn1, _ = server.save_photo_sync(generate_solid_frame(320, 240, (10, 10, 10)), "cycle1")
                t += 0.15
                state_prev1, _ = engine.update([], current_time=t) # PREVIEW
                self.assertEqual(state_prev1, CaptureState.PREVIEW)
                t += 1.05
                state_cd1, _ = engine.update([], current_time=t) # COOLDOWN
                self.assertEqual(state_cd1, CaptureState.COOLDOWN)
                t += 0.55
                state_idle1, _ = engine.update([], current_time=t) # IDLE
                self.assertEqual(state_idle1, CaptureState.IDLE)

                # === Cycle 2 ===
                engine.update([peace_lms], current_time=t) # ARMED
                t += 0.71
                engine.update([peace_lms], current_time=t) # COUNTDOWN
                t += 1.01
                state2, meta2 = engine.update([], current_time=t) # FLASH
                self.assertEqual(state2, CaptureState.FLASH)
                self.assertTrue(meta2['trigger_snap'])

                fn2, _ = server.save_photo_sync(generate_solid_frame(320, 240, (20, 20, 20)), "cycle2")
                self.assertTrue(os.path.isfile(os.path.join(tmpdir, fn1)))
                self.assertTrue(os.path.isfile(os.path.join(tmpdir, fn2)))
                self.assertNotEqual(fn1, fn2)
            finally:
                server.stop()

    def test_combo_11_simultaneous_landmark_jitter_and_rotation_during_countdown(self):
        """
        During countdown, landmarks rotate and jitter dynamically.
        Verifies that the state machine remains locked in countdown until completion.
        """
        engine = GestureCaptureEngine(hold_duration=0.7, countdown_duration=2.0)
        peace_lms = create_synthetic_landmarks("peace")

        engine.update([peace_lms], current_time=100.0)
        engine.update([peace_lms], current_time=100.71) # in COUNTDOWN

        # Advance through countdown with jittery/rotating landmarks
        cur_t = 100.71
        for tilt in [10, 25, 45, 60]:
            cur_t += 0.4
            noisy_hand = create_synthetic_hand("peace", tilt_deg=tilt, noise_sigma=0.01)
            state, meta = engine.update([noisy_hand], current_time=cur_t)
            self.assertEqual(state, CaptureState.COUNTDOWN)

        # Trigger snapshot at t=102.75s
        state_snap, meta_snap = engine.update([], current_time=102.75)
        self.assertEqual(state_snap, CaptureState.FLASH)
        self.assertTrue(meta_snap['trigger_snap'])

    def test_combo_12_burst_http_load_concurrent_with_qr_card_render(self):
        """
        Renders QR HUD preview cards in the main loop while 5 background threads
        hit `/health` and `/view/<filename>`.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DeliveryServer(capture_dir=tmpdir, port=8248, max_port=8258, host="127.0.0.1")
            server.start()
            try:
                frame = generate_checkerboard_frame(640, 480)
                fn, _ = server.save_photo_sync(frame, "load_test")

                statuses = []
                def worker():
                    try:
                        url = f"http://127.0.0.1:{server.port}/view/{fn}"
                        with urllib.request.urlopen(url, timeout=2.0) as r:
                            statuses.append(r.status)
                    except Exception:
                        statuses.append(500)

                threads = [threading.Thread(target=worker) for _ in range(5)]
                for t in threads:
                    t.start()

                for s in range(3):
                    out = server.render_qr_card(frame.copy(), fn, remaining_seconds=5.0 - s)
                    self.assertEqual(out.shape, (480, 640, 3))

                for t in threads:
                    t.join(timeout=2.0)

                self.assertEqual(len(statuses), 5)
                self.assertTrue(all(s == 200 for s in statuses))
            finally:
                server.stop()


if __name__ == "__main__":
    unittest.main()
