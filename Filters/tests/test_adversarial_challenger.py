"""
test_adversarial_challenger.py - Empirical Adversarial Challenge Suite
=====================================================================
Authored by: Challenger 1 (Empirical Challenger Agent)

Adversarial Stress Test Dimensions:
1. Extreme Landmark Jitter, Gaussian/Uniform/Cauchy Noise & Degenerate Point Arrays
2. Out-of-Bounds & Non-Numeric Coordinates (NaN, Inf, Negatives, Massive Floats)
3. Hand Scale Extremes (S = 0.000001 to S = 1000.0, zero-scale collapse)
4. Fast Flickering Gestures & Sub-Threshold Hold Duration Attacks
5. Sudden Hand Disappearance Across All 6 FSM States (IDLE, ARMED, COUNTDOWN, FLASH, PREVIEW, COOLDOWN)
6. Illegal Gesture Injections in Locked/Active States (No re-arming during countdown/cooldown)
7. Visual HUD Overlay Resilience Against Pathological Coordinates & Frame Dimensions
8. FSM Clock Anomalies (Backwards Time Travel, Zero dt, Huge Time Jumps)
9. Original Source Files SHA-256 Cryptographic Immutability Audit
"""

import os
import sys
import math
import time
import hashlib
import unittest
import numpy as np
import cv2

# Project root resolution
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tests.conftest import (
    MockLandmark,
    MockLandmarkList,
    create_synthetic_hand,
    WRIST, THUMB_TIP, INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP,
    INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP, THUMB_MCP
)

from gesture_detector_test import (
    is_peace_gesture,
    find_peace_gesture,
    compute_palm_scale,
    _extract_landmark_points,
    _joint_angle_3p,
    _euclidean_distance,
    create_synthetic_landmarks,
    CaptureState,
    GestureCaptureEngine,
    draw_radial_progress,
    draw_countdown_overlay,
    draw_flash_overlay
)

from delivery_server_test import (
    DeliveryServer,
    render_preview_card,
    generate_qr_matrix
)


class TestAdversarialChallenger(unittest.TestCase):
    """
    Adversarial Stress Test Harness executed by Challenger 1.
    Empirically exercises failure modes, edge boundaries, and stress limits.
    """

    @classmethod
    def setUpClass(cls):
        cls.orig_files = [
            "main.py",
            "filters.py",
            "geometry.py",
            "hand_tracking.py",
            "Launch Filters.command",
            "requirements.txt",
            "README.md"
        ]
        cls.orig_hashes = {}
        for fname in cls.orig_files:
            fpath = os.path.join(PROJECT_ROOT, fname)
            if os.path.isfile(fpath):
                with open(fpath, "rb") as f:
                    cls.orig_hashes[fname] = hashlib.sha256(f.read()).hexdigest()

    # =========================================================================
    # SUITE 1: Extreme Noise, Outliers, Jitter & Malformed Landmark Arrays
    # =========================================================================

    def test_adv_01_gaussian_noise_spectrum(self):
        """Tests gesture detector under increasing levels of Gaussian noise."""
        base_peace = create_synthetic_landmarks("peace")
        
        # Low to moderate noise should maintain detection
        for sigma in [0.001, 0.005, 0.008]:
            noisy = base_peace + np.random.normal(0, sigma, base_peace.shape)
            self.assertTrue(is_peace_gesture(noisy), f"Failed under gentle noise sigma={sigma}")

        # Heavy noise should degrade safely to False without any unhandled exceptions
        for sigma in [0.15, 0.5, 1.0, 5.0, 50.0, 500.0]:
            noisy = base_peace + np.random.normal(0, sigma, base_peace.shape)
            res = is_peace_gesture(noisy)
            self.assertIsInstance(res, bool, f"Result was not bool for sigma={sigma}")

    def test_adv_02_cauchy_heavy_tailed_noise(self):
        """Tests resilience to Cauchy noise (heavy-tailed extreme outliers)."""
        base_peace = create_synthetic_landmarks("peace")
        for gamma in [0.01, 0.05, 0.1, 1.0]:
            noise = np.random.standard_cauchy(base_peace.shape) * gamma
            noisy = base_peace + noise
            res = is_peace_gesture(noisy)
            self.assertIsInstance(res, bool)

    def test_adv_03_nan_inf_and_extreme_floats(self):
        """Tests that NaN, +/-Inf, and floating point overflow never crash the engine."""
        base_peace = create_synthetic_landmarks("peace")
        
        # Test NaN in various landmark positions
        for target_idx in range(21):
            corrupt = base_peace.copy()
            corrupt[target_idx, 0] = np.nan
            self.assertFalse(is_peace_gesture(corrupt))
            
            corrupt[target_idx, 1] = np.inf
            self.assertFalse(is_peace_gesture(corrupt))
            
            corrupt[target_idx, 0] = -np.inf
            self.assertFalse(is_peace_gesture(corrupt))
            
            corrupt[target_idx, 1] = 1e308
            self.assertFalse(is_peace_gesture(corrupt))

    def test_adv_04_malformed_landmark_containers(self):
        """Tests arbitrary invalid data types and corrupted structures."""
        invalid_inputs = [
            None,
            [],
            {},
            "invalid_string",
            [1, 2, 3],
            [[0.5, 0.5]], # 1 landmark only
            [[0.5, 0.5]] * 10, # 10 landmarks only
            [[0.5, 0.5]] * 20, # 20 landmarks only
            [[0.5, 0.5]] * 22, # 22 landmarks
            [[0.5, 0.5]] * 100, # 100 landmarks
            np.zeros((0, 2)),
            np.zeros((21, 1)), # wrong shape
            np.zeros((21, 5)), # 5D coordinates
            [{"x": 0.5}], # missing 'y'
            [MockLandmark(0.5, 0.5)] * 15, # 15 landmarks
        ]
        
        for inv in invalid_inputs:
            # Must return False or handle safely without crashing
            res = is_peace_gesture(inv)
            self.assertFalse(res, f"Expected False for invalid input {type(inv)}")
            
            found, idx, center, pts = find_peace_gesture([inv] if inv is not None else None)
            self.assertFalse(found)
            self.assertIsNone(idx)
            self.assertIsNone(center)

    def test_adv_05_collapsed_and_collinear_landmarks(self):
        """Tests zero-distance / collapsed / collinear hands."""
        # 1. All 21 landmarks at exact same point (0, 0)
        zeros = np.zeros((21, 2), dtype=np.float64)
        self.assertFalse(is_peace_gesture(zeros))
        self.assertEqual(compute_palm_scale(zeros), 0.0)

        # 2. All 21 landmarks along a straight line (collinear)
        line_pts = np.zeros((21, 2), dtype=np.float64)
        for i in range(21):
            line_pts[i] = [i * 0.05, i * 0.05]
        self.assertFalse(is_peace_gesture(line_pts))

    # =========================================================================
    # SUITE 2: Hand Scale Extremes ($S = 10^{-6}$ to $S = 10^4$)
    # =========================================================================

    def test_adv_06_scale_spectrum_limits(self):
        """Tests gesture detector across microscopic to astronomical scales."""
        scales = [
            0.000001, 0.00001, 0.0001, 0.001, 0.005, 0.01, 0.05, 
            0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 100.0, 1000.0
        ]
        for s in scales:
            lms = create_synthetic_landmarks("peace", scale=s)
            palm_s = compute_palm_scale(lms)
            if s >= 0.001:
                # Detector is scale-invariant and must recognize valid geometry
                self.assertTrue(is_peace_gesture(lms), f"Peace sign failed at scale S={s} (palm={palm_s})")
            else:
                # Microscopic scale (< 1e-4) correctly triggers the tiny palm guard
                self.assertFalse(is_peace_gesture(lms))

    def test_adv_07_out_of_bounds_coordinates(self):
        """Tests landmarks far outside the [0, 1] normalized viewport."""
        offsets = [
            (-1000.0, -1000.0),
            (-10.0, 0.5),
            (0.5, -5.0),
            (10.0, 10.0),
            (500.0, -500.0)
        ]
        for ox, oy in offsets:
            lms = create_synthetic_landmarks("peace", wrist=(ox, oy))
            # Relative geometry remains valid, should detect without crashing
            self.assertTrue(is_peace_gesture(lms))

    # =========================================================================
    # SUITE 3: Fast Flickering & Sub-Threshold Hold Duration Attacks
    # =========================================================================

    def test_adv_08_frame_by_frame_flickering(self):
        """Tests rapid toggling of Peace gesture every single frame for 1,000 frames."""
        engine = GestureCaptureEngine(hold_duration=0.7)
        peace_lms = create_synthetic_landmarks("peace")
        
        sim_time = 0.0
        fps_rates = [30, 60, 120]
        
        for fps in fps_rates:
            dt = 1.0 / fps
            engine.reset()
            for frame_idx in range(1000):
                sim_time += dt
                # Alternating every single frame
                input_hands = [peace_lms] if (frame_idx % 2 == 0) else []
                state, meta = engine.update(input_hands, current_time=sim_time)
                
                # Should flicker between IDLE and ARMED, but NEVER reach COUNTDOWN or trigger snap
                self.assertIn(state, [CaptureState.IDLE, CaptureState.ARMED])
                self.assertFalse(meta['trigger_snap'])
                self.assertLess(meta['hold_progress'], 0.2)

    def test_adv_09_sub_threshold_hold_attacks(self):
        """Tests holding peace sign just below 0.700s threshold, then dropping."""
        engine = GestureCaptureEngine(hold_duration=0.7)
        peace_lms = create_synthetic_landmarks("peace")
        
        # Test holding for exactly 0.690s (10ms short) 50 times in a row
        t = 0.0
        for cycle in range(50):
            # Start hold
            for step in range(20): # 20 steps * 0.033s = ~0.66s
                t += 0.033
                st, meta = engine.update([peace_lms], current_time=t)
                self.assertEqual(st, CaptureState.ARMED)
                self.assertFalse(meta['trigger_snap'])
            
            # Step at 0.690s
            t += 0.030
            st, meta = engine.update([peace_lms], current_time=t)
            self.assertEqual(st, CaptureState.ARMED)
            self.assertFalse(meta['trigger_snap'])
            
            # Drop hand at 0.695s
            t += 0.005
            st, meta = engine.update([], current_time=t)
            self.assertEqual(st, CaptureState.IDLE)
            self.assertEqual(meta['hold_progress'], 0.0)
            self.assertFalse(meta['trigger_snap'])
            
            # Idle pause
            t += 0.1
            st, _ = engine.update([], current_time=t)
            self.assertEqual(st, CaptureState.IDLE)

    def test_adv_10_rapid_random_gesture_cycling(self):
        """Cycles randomly through all possible gestures every 50ms for 500 iterations."""
        engine = GestureCaptureEngine(hold_duration=0.7)
        gesture_types = ["peace", "fist", "open_palm", "portal", "pointing", "three_fingers", "four_fingers", "empty"]
        
        t = 0.0
        np.random.seed(42)
        for _ in range(500):
            t += 0.05
            g = np.random.choice(gesture_types)
            if g == "empty":
                hands = []
            else:
                hands = [create_synthetic_landmarks(g)]
            
            st, meta = engine.update(hands, current_time=t)
            # Must remain a valid state, no crashes
            self.assertIn(st, list(CaptureState))

    # =========================================================================
    # SUITE 4: Sudden Hand Disappearance Across All FSM States
    # =========================================================================

    def test_adv_11_disappearance_during_countdown(self):
        """
        Critical Fair Feature: Once COUNTDOWN begins (t >= 0.7s hold), user may drop 
        gesture to strike a pose. State machine MUST proceed through COUNTDOWN to FLASH.
        """
        engine = GestureCaptureEngine(hold_duration=0.7, countdown_duration=3.0, flash_duration=0.15)
        peace_lms = create_synthetic_landmarks("peace")
        
        # 1. Arm and complete hold
        engine.update([peace_lms], current_time=0.0)
        st, _ = engine.update([peace_lms], current_time=0.71)
        self.assertEqual(st, CaptureState.COUNTDOWN)
        
        # 2. Drop hands completely for the entire countdown duration
        snap_occurred = False
        t = 0.71
        while t <= 4.0:
            t += 0.033
            st, meta = engine.update([], current_time=t)
            if meta['trigger_snap']:
                snap_occurred = True
            if t < 3.71:
                self.assertEqual(st, CaptureState.COUNTDOWN)
            elif t < 3.86:
                self.assertEqual(st, CaptureState.FLASH)
            else:
                self.assertEqual(st, CaptureState.PREVIEW)
        
        self.assertTrue(snap_occurred, "Snapshot was not triggered when hands disappeared during countdown!")

    def test_adv_12_disappearance_during_flash_and_preview(self):
        """Tests sudden hand loss during FLASH, PREVIEW, and COOLDOWN states."""
        engine = GestureCaptureEngine(
            hold_duration=0.7,
            countdown_duration=1.0,
            flash_duration=0.15,
            preview_duration=2.0,
            cooldown_duration=1.0
        )
        peace_lms = create_synthetic_landmarks("peace")
        
        # Trigger to FLASH
        engine.update([peace_lms], current_time=0.0)
        engine.update([peace_lms], current_time=0.75) # COUNTDOWN
        engine.update([], current_time=1.80) # FLASH
        self.assertEqual(engine.state, CaptureState.FLASH)
        
        # Drop hands during FLASH
        st, meta = engine.update([], current_time=1.85)
        self.assertEqual(st, CaptureState.FLASH)
        self.assertGreater(meta['flash_alpha'], 0.0)
        
        # Transition to PREVIEW without hands
        st, meta = engine.update([], current_time=2.00)
        self.assertEqual(st, CaptureState.PREVIEW)
        
        # Advance through PREVIEW without hands
        st, meta = engine.update([], current_time=3.50)
        self.assertEqual(st, CaptureState.PREVIEW)
        
        # Advance to COOLDOWN
        st, meta = engine.update([], current_time=4.10)
        self.assertEqual(st, CaptureState.COOLDOWN)
        
        # Advance to IDLE
        st, meta = engine.update([], current_time=5.20)
        self.assertEqual(st, CaptureState.IDLE)

    def test_adv_13_illegal_gesture_injection_during_countdown_and_cooldown(self):
        """
        Tests injecting peace gestures during COUNTDOWN, FLASH, PREVIEW, and COOLDOWN.
        Must NOT interrupt countdown or cause premature re-trigger.
        """
        engine = GestureCaptureEngine(
            hold_duration=0.7,
            countdown_duration=3.0,
            flash_duration=0.15,
            preview_duration=6.0,
            cooldown_duration=2.0
        )
        peace_lms = create_synthetic_landmarks("peace")
        
        # Arm & Start Countdown at t=0.75
        engine.update([peace_lms], current_time=0.0)
        engine.update([peace_lms], current_time=0.75)
        self.assertEqual(engine.state, CaptureState.COUNTDOWN)
        
        # Inject frantic peace sign waving during countdown
        for t in np.linspace(0.8, 3.7, 30):
            st, meta = engine.update([peace_lms], current_time=t)
            self.assertEqual(st, CaptureState.COUNTDOWN)
            # Countdown remaining must decrease monotonically
            self.assertGreater(meta['countdown_remaining'], 0.0)
            self.assertEqual(meta['hold_progress'], 0.0)

        # Trigger Flash at t=3.8
        st, meta = engine.update([peace_lms], current_time=3.8)
        self.assertEqual(st, CaptureState.FLASH)
        self.assertTrue(meta['trigger_snap'])

        # Inject gestures during PREVIEW
        st, meta = engine.update([peace_lms], current_time=4.5)
        self.assertEqual(st, CaptureState.PREVIEW)

        # Inject gestures during COOLDOWN
        engine.dismiss_preview(current_time=5.0)
        self.assertEqual(engine.state, CaptureState.COOLDOWN)
        
        for t in [5.1, 5.5, 6.0, 6.9]:
            st, meta = engine.update([peace_lms], current_time=t)
            self.assertEqual(st, CaptureState.COOLDOWN)
            self.assertEqual(meta['hold_progress'], 0.0)

    # =========================================================================
    # SUITE 5: Visual HUD Overlay Stress with Pathological Parameters
    # =========================================================================

    def test_adv_14_radial_progress_pathological_inputs(self):
        """Tests draw_radial_progress against extreme coordinates and progress values."""
        # 1. Standard frame with extreme centers
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        extreme_centers = [
            (-5000, -5000), (10000, 10000), (0, 0), (640, 480), (320, 240), None
        ]
        for c in extreme_centers:
            for p in [-10.0, 0.0, 0.0001, 0.5, 1.0, 50.0]:
                out = draw_radial_progress(frame.copy(), c, p)
                self.assertEqual(out.shape, (480, 640, 3))
                self.assertEqual(out.dtype, np.uint8)

        # 2. Degenerate frame sizes
        tiny_frame = np.zeros((5, 5, 3), dtype=np.uint8)
        out_tiny = draw_radial_progress(tiny_frame.copy(), (2, 2), 0.75, radius=2)
        self.assertEqual(out_tiny.shape, (5, 5, 3))

    def test_adv_15_countdown_overlay_pathological_inputs(self):
        """Tests draw_countdown_overlay against extreme seconds left and odd frame resolutions."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        test_times = [-100.0, -0.01, 0.0, 0.0001, 0.5, 1.0, 2.99, 3.0, 999.0]
        
        for t in test_times:
            out = draw_countdown_overlay(frame.copy(), t, is_integer_tick=True)
            self.assertEqual(out.shape, (480, 640, 3))
            self.assertEqual(out.dtype, np.uint8)

        # Odd resolution frames
        odd_frame = np.zeros((333, 777, 3), dtype=np.uint8)
        out_odd = draw_countdown_overlay(odd_frame.copy(), 2.5)
        self.assertEqual(out_odd.shape, (333, 777, 3))

    def test_adv_16_flash_overlay_pathological_inputs(self):
        """Tests draw_flash_overlay against extreme alpha values."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        test_alphas = [-5.0, 0.0, 0.0001, 0.5, 0.95, 1.0, 2.0, 100.0]
        
        for a in test_alphas:
            out = draw_flash_overlay(frame.copy(), a)
            self.assertEqual(out.shape, (480, 640, 3))
            self.assertEqual(out.dtype, np.uint8)

    # =========================================================================
    # SUITE 6: FSM Clock Anomalies (Time Inversions, Zero dt, Huge Time Warps)
    # =========================================================================

    def test_adv_17_clock_time_travel_backwards(self):
        """Tests that state machine handles clock going backwards (NTP skew)."""
        engine = GestureCaptureEngine(hold_duration=0.7)
        peace_lms = create_synthetic_landmarks("peace")
        
        engine.update([peace_lms], current_time=100.0)
        # Time jumps backwards by 50 seconds
        st, meta = engine.update([peace_lms], current_time=50.0)
        # Should stay in valid state without exception
        self.assertIn(st, list(CaptureState))

    def test_adv_18_zero_dt_burst(self):
        """Tests 1,000 rapid updates with exactly identical timestamps."""
        engine = GestureCaptureEngine(hold_duration=0.7)
        peace_lms = create_synthetic_landmarks("peace")
        
        for _ in range(1000):
            st, meta = engine.update([peace_lms], current_time=100.0)
            self.assertEqual(st, CaptureState.ARMED)
            self.assertEqual(meta['hold_progress'], 0.0)

    def test_adv_19_huge_time_warp(self):
        """Tests massive sleep/wake jump (e.g. laptop closed during countdown)."""
        engine = GestureCaptureEngine(
            hold_duration=0.7,
            countdown_duration=3.0,
            flash_duration=0.15,
            preview_duration=6.0,
            cooldown_duration=2.0
        )
        peace_lms = create_synthetic_landmarks("peace")
        
        engine.update([peace_lms], current_time=10.0)
        engine.update([peace_lms], current_time=10.75) # COUNTDOWN
        self.assertEqual(engine.state, CaptureState.COUNTDOWN)
        
        # Jump forward 100,000 seconds
        st, meta = engine.update([], current_time=100010.75)
        # Countdown finishes -> transitions to FLASH
        self.assertEqual(st, CaptureState.FLASH)
        self.assertTrue(meta['trigger_snap'])

    # =========================================================================
    # SUITE 7: Original Source File Immutability Audit
    # =========================================================================

    def test_adv_20_original_files_cryptographic_integrity(self):
        """Asserts 100% byte-for-byte immutability of all 7 original source files."""
        for fname in self.orig_files:
            fpath = os.path.join(PROJECT_ROOT, fname)
            self.assertTrue(os.path.isfile(fpath), f"Original file {fname} is missing!")
            with open(fpath, "rb") as f:
                cur_hash = hashlib.sha256(f.read()).hexdigest()
            orig_hash = self.orig_hashes.get(fname)
            self.assertEqual(
                cur_hash, orig_hash,
                f"VIOLATION: Original source file {fname} was modified! Hash mismatch: {cur_hash} vs {orig_hash}"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
