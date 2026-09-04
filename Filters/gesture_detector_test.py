"""
gesture_detector_test.py - Gesture Detection & Capture State Machine Module

Implements:
1. Scale-Invariant Peace Sign (✌️) Detection with 6 landmark predicates:
   - Landmark normalization via Palm Scale Metric: S = ||p_9 - p_0||_2
   - Index tip extended (theta >= 140 deg, tip-to-wrist ratio > 1.15, tip-to-mcp >= 0.65 * S)
   - Middle tip extended (theta >= 140 deg, tip-to-wrist ratio > 1.15, tip-to-mcp >= 0.65 * S)
   - Ring tip curled (distance inversion / palm proximity <= 0.65 * S, curl angle <= 135 deg)
   - Pinky tip curled (distance inversion / palm proximity <= 0.65 * S, curl angle <= 135 deg)
   - V-formation divergence (8 deg <= theta_V <= 65 deg, tip separation >= 0.20 * S)
   - Thumb tucked across palm (not extended outward from wrist and palm proximity <= 0.75 * S)
2. 6-State Capture Finite State Machine (FSM):
   - States: IDLE, ARMED, COUNTDOWN, FLASH, PREVIEW, COOLDOWN
   - Hold confirmation (T_hold = 0.7s) with radial sweep progress
   - Countdown duration (T_countdown = 3.0s) with integer ticks (3, 2, 1) and pulse phase
   - Flash alpha decay (T_flash = 0.15s) with exponential decay
   - Preview duration (T_preview = 6.0s)
   - Cooldown lockout (T_cooldown = 2.0s)
   - Snapshot trigger flag emitted exactly on transition from COUNTDOWN to FLASH
3. Visual HUD Rendering Helpers:
   - draw_radial_progress: Sweeping circular progress ring around detected hand
   - draw_countdown_overlay: Pulsing countdown digits (3-2-1) with drop shadow & banner
   - draw_flash_overlay: Camera shutter flash whiteout blend
4. Standalone self-test suite when executed as __main__.
"""

import sys
import time
import math
from enum import Enum
from typing import List, Tuple, Dict, Any, Optional, Union
import numpy as np
import cv2

# MediaPipe Hand Landmarks Index Map
WRIST = 0
THUMB_CMC = 1
THUMB_MCP = 2
THUMB_IP = 3
THUMB_TIP = 4
INDEX_MCP = 5
INDEX_PIP = 6
INDEX_DIP = 7
INDEX_TIP = 8
MIDDLE_MCP = 9
MIDDLE_PIP = 10
MIDDLE_DIP = 11
MIDDLE_TIP = 12
RING_MCP = 13
RING_PIP = 14
RING_DIP = 15
RING_TIP = 16
PINKY_MCP = 17
PINKY_PIP = 18
PINKY_DIP = 19
PINKY_TIP = 20


# =============================================================================
# Geometric & Landmark Utilities
# =============================================================================

def _extract_landmark_points(
    hand_landmarks: Any,
    frame_shape: Optional[Tuple[int, int]] = None
) -> np.ndarray:
    """
    Extracts 21 2D landmark points as a numpy array of shape (21, 2).
    Supports MediaPipe NormalizedLandmarkList, objects with .landmark attribute,
    lists of objects with .x/.y, dicts with 'x'/'y', or numpy arrays.
    
    If frame_shape (height, width) is provided, coordinates are scaled to pixel space.
    Otherwise, normalized coordinates are returned.
    """
    if isinstance(hand_landmarks, np.ndarray):
        pts = hand_landmarks[:, :2].copy()
        if frame_shape is not None and np.max(pts) <= 1.05:
            h, w = frame_shape[:2]
            pts[:, 0] *= w
            pts[:, 1] *= h
        return pts

    # If it's a MediaPipe NormalizedLandmarkList or container with .landmark attribute
    raw_lms = getattr(hand_landmarks, "landmark", hand_landmarks)
    
    pts = []
    for lm in raw_lms:
        if hasattr(lm, "x") and hasattr(lm, "y"):
            pts.append([lm.x, lm.y])
        elif isinstance(lm, dict) and "x" in lm and "y" in lm:
            pts.append([lm["x"], lm["y"]])
        elif isinstance(lm, (list, tuple)) and len(lm) >= 2:
            pts.append([lm[0], lm[1]])
        else:
            raise ValueError(f"Unrecognized landmark element format: {lm}")

    pts_np = np.array(pts, dtype=np.float64)
    if frame_shape is not None:
        h, w = frame_shape[:2]
        pts_np[:, 0] *= w
        pts_np[:, 1] *= h
    return pts_np


def _euclidean_distance(p1: np.ndarray, p2: np.ndarray) -> float:
    """Calculates Euclidean distance between two 2D points."""
    return float(np.linalg.norm(p1 - p2))


def _joint_angle_3p(p_a: np.ndarray, p_b: np.ndarray, p_c: np.ndarray) -> float:
    """
    Calculates the joint angle at vertex p_b between vectors (p_a - p_b) and (p_c - p_b).
    Returns degrees in [0.0, 180.0].
    For a straight extended finger (e.g. MCP -> PIP -> TIP), angle is ~180 degrees.
    For a curled finger bent back towards MCP, angle is <= 120 degrees.
    """
    u = p_a - p_b
    v = p_c - p_b
    norm_u = np.linalg.norm(u)
    norm_v = np.linalg.norm(v)
    if norm_u < 1e-7 or norm_v < 1e-7:
        return 0.0
    cos_theta = np.dot(u, v) / (norm_u * norm_v)
    cos_theta = np.clip(cos_theta, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_theta)))


def compute_palm_scale(landmarks_2d: np.ndarray) -> float:
    """
    Computes Palm Scale Metric: S = ||p_9 (MIDDLE_MCP) - p_0 (WRIST)||_2.
    """
    if landmarks_2d.shape[0] < 10:
        return 0.0
    return _euclidean_distance(landmarks_2d[MIDDLE_MCP], landmarks_2d[WRIST])


# =============================================================================
# Peace Sign (✌️) Detection
# =============================================================================

def is_peace_gesture(
    hand_landmarks: Any,
    frame_shape: Optional[Tuple[int, int]] = None
) -> bool:
    """
    Evaluates whether the given hand landmark set satisfies the 6-predicate Peace Sign:
    1. Index tip extended (theta >= 140 deg, tip-to-wrist ratio > 1.15, tip-to-mcp >= 0.65 * S)
    2. Middle tip extended (theta >= 140 deg, tip-to-wrist ratio > 1.15, tip-to-mcp >= 0.65 * S)
    3. Ring tip curled (distance inversion / palm proximity <= 0.65 * S, curl angle <= 135 deg)
    4. Pinky tip curled (distance inversion / palm proximity <= 0.65 * S, curl angle <= 135 deg)
    5. V-divergence (8 deg <= theta_V <= 65 deg, tip separation >= 0.20 * S)
    6. Thumb tucked across palm (not extended outward from wrist and palm proximity <= 0.75 * S)
    """
    try:
        pts = _extract_landmark_points(hand_landmarks, frame_shape)
    except Exception:
        return False

    if pts.shape[0] < 21:
        return False

    # Guard against NaN / Inf poisoned landmarks: any non-finite coordinate
    # invalidates the entire observation and must evaluate to False.
    if not np.all(np.isfinite(pts)):
        return False

    # Palm scale metric S
    S = compute_palm_scale(pts)
    if S < 1e-4:
        return False

    # -------------------------------------------------------------------------
    # Predicate 1: Index Finger Full Extension
    # -------------------------------------------------------------------------
    idx_angle = _joint_angle_3p(pts[INDEX_MCP], pts[INDEX_PIP], pts[INDEX_TIP])
    dist_idx_wrist = _euclidean_distance(pts[INDEX_TIP], pts[WRIST])
    dist_idx_pip_wrist = _euclidean_distance(pts[INDEX_PIP], pts[WRIST])
    dist_idx_mcp = _euclidean_distance(pts[INDEX_TIP], pts[INDEX_MCP])

    idx_extended = (
        idx_angle >= 140.0 and
        dist_idx_wrist > 1.15 * dist_idx_pip_wrist and
        dist_idx_mcp >= 0.65 * S
    )
    if not idx_extended:
        return False

    # -------------------------------------------------------------------------
    # Predicate 2: Middle Finger Full Extension
    # -------------------------------------------------------------------------
    mid_angle = _joint_angle_3p(pts[MIDDLE_MCP], pts[MIDDLE_PIP], pts[MIDDLE_TIP])
    dist_mid_wrist = _euclidean_distance(pts[MIDDLE_TIP], pts[WRIST])
    dist_mid_pip_wrist = _euclidean_distance(pts[MIDDLE_PIP], pts[WRIST])
    dist_mid_mcp = _euclidean_distance(pts[MIDDLE_TIP], pts[MIDDLE_MCP])

    mid_extended = (
        mid_angle >= 140.0 and
        dist_mid_wrist > 1.15 * dist_mid_pip_wrist and
        dist_mid_mcp >= 0.65 * S
    )
    if not mid_extended:
        return False

    # -------------------------------------------------------------------------
    # Predicate 3: Ring Finger Full Curl
    # -------------------------------------------------------------------------
    dist_ring_wrist = _euclidean_distance(pts[RING_TIP], pts[WRIST])
    dist_ring_pip_wrist = _euclidean_distance(pts[RING_PIP], pts[WRIST])
    dist_ring_mcp = _euclidean_distance(pts[RING_TIP], pts[RING_MCP])
    ring_angle = _joint_angle_3p(pts[RING_MCP], pts[RING_PIP], pts[RING_TIP])

    ring_tucked = (
        (dist_ring_wrist < dist_ring_pip_wrist * 1.05 or dist_ring_mcp <= 0.65 * S) and
        ring_angle <= 135.0
    )
    if not ring_tucked:
        return False

    # -------------------------------------------------------------------------
    # Predicate 4: Pinky Finger Full Curl
    # -------------------------------------------------------------------------
    dist_pinky_wrist = _euclidean_distance(pts[PINKY_TIP], pts[WRIST])
    dist_pinky_pip_wrist = _euclidean_distance(pts[PINKY_PIP], pts[WRIST])
    dist_pinky_mcp = _euclidean_distance(pts[PINKY_TIP], pts[PINKY_MCP])
    pinky_angle = _joint_angle_3p(pts[PINKY_MCP], pts[PINKY_PIP], pts[PINKY_TIP])

    pinky_tucked = (
        (dist_pinky_wrist < dist_pinky_pip_wrist * 1.05 or dist_pinky_mcp <= 0.65 * S) and
        pinky_angle <= 135.0
    )
    if not pinky_tucked:
        return False

    # -------------------------------------------------------------------------
    # Predicate 5: V-Formation Angular & Distance Separation
    # -------------------------------------------------------------------------
    v_index = pts[INDEX_TIP] - pts[INDEX_MCP]
    v_middle = pts[MIDDLE_TIP] - pts[MIDDLE_MCP]
    norm_idx = np.linalg.norm(v_index)
    norm_mid = np.linalg.norm(v_middle)

    if norm_idx < 1e-7 or norm_mid < 1e-7:
        return False

    cos_v = np.dot(v_index, v_middle) / (norm_idx * norm_mid)
    cos_v = np.clip(cos_v, -1.0, 1.0)
    theta_v = float(np.degrees(np.arccos(cos_v)))
    dist_tips = _euclidean_distance(pts[INDEX_TIP], pts[MIDDLE_TIP])

    v_formation = (
        8.0 <= theta_v <= 65.0 and
        dist_tips >= 0.20 * S
    )
    if not v_formation:
        return False

    # -------------------------------------------------------------------------
    # Predicate 6: Thumb Tucked Across Palm
    # -------------------------------------------------------------------------
    dist_thumb_wrist = _euclidean_distance(pts[THUMB_TIP], pts[WRIST])
    dist_thumb_mcp_wrist = _euclidean_distance(pts[THUMB_MCP], pts[WRIST])
    not_extended_outward = (dist_thumb_wrist <= dist_thumb_mcp_wrist * 1.25)

    dist_thumb_ring_mcp = _euclidean_distance(pts[THUMB_TIP], pts[RING_MCP])
    dist_thumb_ring_pip = _euclidean_distance(pts[THUMB_TIP], pts[RING_PIP])
    dist_thumb_mid_mcp = _euclidean_distance(pts[THUMB_TIP], pts[MIDDLE_MCP])
    dist_thumb_pinky_mcp = _euclidean_distance(pts[THUMB_TIP], pts[PINKY_MCP])

    min_thumb_dist = min(
        dist_thumb_ring_mcp,
        dist_thumb_ring_pip,
        dist_thumb_mid_mcp,
        dist_thumb_pinky_mcp
    )
    thumb_tucked = not_extended_outward and (min_thumb_dist <= 0.75 * S)
    if not thumb_tucked:
        return False

    return True


def find_peace_gesture(
    multi_hand_landmarks: Optional[List[Any]],
    frame_shape: Optional[Tuple[int, int]] = None
) -> Tuple[bool, Optional[int], Optional[Tuple[int, int]], Optional[np.ndarray]]:
    """
    Searches multi_hand_landmarks for any hand making the Peace Sign.
    Returns:
        (found, hand_index, center_point_xy, landmark_points)
    """
    if not multi_hand_landmarks:
        return False, None, None, None

    for idx, hand_lms in enumerate(multi_hand_landmarks):
        if is_peace_gesture(hand_lms, frame_shape):
            pts = _extract_landmark_points(hand_lms, frame_shape)
            center_x = int(pts[MIDDLE_MCP, 0])
            center_y = int(pts[MIDDLE_MCP, 1])
            return True, idx, (center_x, center_y), pts

    return False, None, None, None


# =============================================================================
# 6-State Capture Finite State Machine (FSM)
# =============================================================================

class CaptureState(Enum):
    IDLE = "IDLE"
    ARMED = "ARMED"
    COUNTDOWN = "COUNTDOWN"
    FLASH = "FLASH"
    PREVIEW = "PREVIEW"
    COOLDOWN = "COOLDOWN"


class GestureCaptureEngine:
    """
    Manages the 6-state Photo Capture FSM:
    - IDLE: Live feed, looking for Peace Sign.
    - ARMED: Gesture detected, holding intent (0.7s) with radial progress sweep.
    - COUNTDOWN: 3.0s interactive countdown (3, 2, 1) with pulse ticks.
    - FLASH: 0.15s camera flash whiteout with exponential decay & snapshot trigger.
    - PREVIEW: 6.0s photo preview & QR card presentation.
    - COOLDOWN: 2.0s debounce lockout to prevent accidental re-triggering.
    """

    def __init__(
        self,
        hold_duration: float = 0.7,
        countdown_duration: float = 3.0,
        flash_duration: float = 0.15,
        preview_duration: float = 6.0,
        cooldown_duration: float = 2.0
    ):
        self.hold_duration = hold_duration
        self.countdown_duration = countdown_duration
        self.flash_duration = flash_duration
        self.preview_duration = preview_duration
        self.cooldown_duration = cooldown_duration

        self.state: CaptureState = CaptureState.IDLE
        self.hold_start_time: Optional[float] = None
        self.countdown_start_time: Optional[float] = None
        self.flash_start_time: Optional[float] = None
        self.preview_start_time: Optional[float] = None
        self.cooldown_start_time: Optional[float] = None

        self.last_countdown_integer: int = 0
        self.hold_center: Optional[Tuple[int, int]] = None

    def reset(self) -> None:
        """Resets state machine immediately to IDLE."""
        self.state = CaptureState.IDLE
        self.hold_start_time = None
        self.countdown_start_time = None
        self.flash_start_time = None
        self.preview_start_time = None
        self.cooldown_start_time = None
        self.last_countdown_integer = 0
        self.hold_center = None

    def trigger_preview(self, current_time: Optional[float] = None) -> None:
        """Transitions explicitly to PREVIEW state."""
        now = current_time if current_time is not None else time.time()
        self.state = CaptureState.PREVIEW
        self.preview_start_time = now

    def dismiss_preview(self, current_time: Optional[float] = None) -> None:
        """Dismisses PREVIEW state early and enters COOLDOWN."""
        if self.state == CaptureState.PREVIEW:
            now = current_time if current_time is not None else time.time()
            self.state = CaptureState.COOLDOWN
            self.cooldown_start_time = now

    def force_trigger_countdown(self, current_time: Optional[float] = None) -> None:
        """Manually trigger the countdown (e.g. via button click)."""
        if self.state in (CaptureState.IDLE, CaptureState.ARMED, CaptureState.COOLDOWN):
            now = current_time if current_time is not None else time.time()
            self.state = CaptureState.COUNTDOWN
            self.countdown_start_time = now
            self.last_countdown_integer = int(math.ceil(self.countdown_duration))


    def update(
        self,
        multi_hand_landmarks: Optional[List[Any]],
        frame_shape: Tuple[int, int] = (720, 1280),
        current_time: Optional[float] = None
    ) -> Tuple[CaptureState, Dict[str, Any]]:
        """
        Processes detected hands and advances the state machine.
        
        Returns:
            (state, metadata)
            metadata = {
                'state': CaptureState,
                'hold_progress': float [0.0, 1.0],
                'hold_center': Optional[Tuple[int, int]],
                'countdown_remaining': float,
                'countdown_integer': int,
                'is_integer_tick': bool,
                'flash_alpha': float [0.0, 1.0],
                'preview_remaining': float,
                'trigger_snap': bool,
                'peace_detected': bool,
                'hand_center': Optional[Tuple[int, int]]
            }
        """
        now = current_time if current_time is not None else time.time()
        
        # Detect Peace Sign among all currently visible hands
        peace_detected, _, hand_center, _ = find_peace_gesture(multi_hand_landmarks, frame_shape)
        trigger_snap = False
        is_integer_tick = False
        hold_progress = 0.0
        countdown_remaining = 0.0
        countdown_int = 0
        flash_alpha = 0.0
        preview_remaining = 0.0

        # State Dispatch
        if self.state == CaptureState.IDLE:
            if peace_detected:
                self.state = CaptureState.ARMED
                self.hold_start_time = now
                self.hold_center = hand_center
                hold_progress = 0.0
            else:
                self.hold_center = None

        elif self.state == CaptureState.ARMED:
            if peace_detected:
                self.hold_center = hand_center
                start_t = self.hold_start_time if self.hold_start_time is not None else now
                elapsed = now - start_t
                hold_progress = min(1.0, max(0.0, elapsed / self.hold_duration))
                
                if elapsed >= self.hold_duration:
                    self.state = CaptureState.COUNTDOWN
                    self.countdown_start_time = now
                    countdown_remaining = self.countdown_duration
                    countdown_int = int(math.ceil(countdown_remaining))
                    self.last_countdown_integer = countdown_int
                    is_integer_tick = True
            else:
                # Dropped gesture before hold confirmation -> cancel back to IDLE
                self.state = CaptureState.IDLE
                self.hold_start_time = None
                self.hold_center = None
                hold_progress = 0.0

        elif self.state == CaptureState.COUNTDOWN:
            start_t = self.countdown_start_time if self.countdown_start_time is not None else now
            elapsed = now - start_t
            countdown_remaining = max(0.0, self.countdown_duration - elapsed)
            countdown_int = int(math.ceil(countdown_remaining))

            if countdown_int != self.last_countdown_integer and countdown_int > 0:
                is_integer_tick = True
                self.last_countdown_integer = countdown_int

            if elapsed >= self.countdown_duration:
                # Countdown finished -> Trigger Snapshot & Transition to FLASH
                self.state = CaptureState.FLASH
                self.flash_start_time = now
                trigger_snap = True
                countdown_remaining = 0.0
                countdown_int = 0
                flash_alpha = 0.95

        elif self.state == CaptureState.FLASH:
            start_t = self.flash_start_time if self.flash_start_time is not None else now
            elapsed = now - start_t
            if elapsed < self.flash_duration:
                # Exponential decay from 0.95 to ~0.0
                decay = math.exp(- (elapsed / self.flash_duration) * 2.8)
                flash_alpha = float(min(1.0, max(0.0, 0.95 * decay)))
            else:
                self.state = CaptureState.PREVIEW
                self.preview_start_time = now
                flash_alpha = 0.0
                preview_remaining = self.preview_duration

        elif self.state == CaptureState.PREVIEW:
            start_t = self.preview_start_time if self.preview_start_time is not None else now
            elapsed = now - start_t
            preview_remaining = max(0.0, self.preview_duration - elapsed)
            if elapsed >= self.preview_duration:
                self.state = CaptureState.COOLDOWN
                self.cooldown_start_time = now
                preview_remaining = 0.0

        elif self.state == CaptureState.COOLDOWN:
            start_t = self.cooldown_start_time if self.cooldown_start_time is not None else now
            elapsed = now - start_t
            if elapsed >= self.cooldown_duration:
                self.state = CaptureState.IDLE
                self.cooldown_start_time = None

        metadata = {
            'state': self.state,
            'hold_progress': float(hold_progress),
            'hold_center': self.hold_center,
            'countdown_remaining': float(countdown_remaining),
            'countdown_integer': int(countdown_int),
            'is_integer_tick': bool(is_integer_tick),
            'flash_alpha': float(flash_alpha),
            'preview_remaining': float(preview_remaining),
            'trigger_snap': bool(trigger_snap),
            'peace_detected': bool(peace_detected),
            'hand_center': hand_center
        }

        return self.state, metadata


# =============================================================================
# Visual HUD Rendering Helpers
# =============================================================================

def draw_radial_progress(
    frame: np.ndarray,
    center: Optional[Tuple[int, int]],
    progress: float,
    color: Tuple[int, int, int] = (0, 255, 255),
    radius: int = 50,
    thickness: int = 5
) -> np.ndarray:
    """
    Renders an animated glowing circular sweep progress ring around `center`.
    """
    if center is None or progress <= 0.001:
        return frame

    h, w = frame.shape[:2]
    cx, cy = int(center[0]), int(center[1])
    cx = max(radius + thickness, min(w - radius - thickness, cx))
    cy = max(radius + thickness, min(h - radius - thickness, cy))

    # Background track circle (subtle dark translucent ring)
    cv2.circle(frame, (cx, cy), radius, (50, 50, 50), thickness, lineType=cv2.LINE_AA)

    # Active progress sweep arc
    deg = int(np.clip(progress, 0.0, 1.0) * 360)
    if deg > 0:
        cv2.ellipse(
            frame,
            (cx, cy),
            (radius, radius),
            0,
            -90,
            -90 + deg,
            color,
            thickness,
            lineType=cv2.LINE_AA
        )
        # Glowing leading tip dot
        rad = np.radians(-90 + deg)
        tip_x = int(cx + radius * np.cos(rad))
        tip_y = int(cy + radius * np.sin(rad))
        cv2.circle(frame, (tip_x, tip_y), thickness + 3, (255, 255, 255), -1, lineType=cv2.LINE_AA)
        cv2.circle(frame, (tip_x, tip_y), thickness + 1, color, -1, lineType=cv2.LINE_AA)

    # Center prompt icon / text
    cv2.circle(frame, (cx, cy), 6, color, -1, lineType=cv2.LINE_AA)

    return frame


def draw_countdown_overlay(
    frame: np.ndarray,
    seconds_left: float,
    is_integer_tick: bool = False
) -> np.ndarray:
    """
    Renders a pulsing countdown numeral (3, 2, 1) and guidance top banner.
    """
    if seconds_left <= 0.0:
        return frame

    h, w = frame.shape[:2]
    count_int = int(math.ceil(seconds_left))
    count_str = str(max(1, count_int))

    # Calculate pulse oscillation based on fractional second remaining
    frac = seconds_left - math.floor(seconds_left)
    if frac == 0.0:
        frac = 1.0
    pulse = 1.0 + 0.30 * (frac ** 2)
    font_scale = 4.8 * pulse
    thickness = max(4, int(9 * pulse))

    # 1. Top Glassmorphic Guidance Banner
    banner_text = "Pose for the camera! [Photo Capture]"
    banner_font = cv2.FONT_HERSHEY_DUPLEX
    banner_scale = 0.85
    banner_thickness = 2
    (tw, th), _ = cv2.getTextSize(banner_text, banner_font, banner_scale, banner_thickness)

    bx = (w - tw) // 2
    by = 65
    pad_x, pad_y = 28, 14

    # Dark translucent pill banner
    overlay = frame.copy()
    cv2.rectangle(
        overlay,
        (bx - pad_x, by - th - pad_y),
        (bx + tw + pad_x, by + pad_y),
        (15, 15, 15),
        -1
    )
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)
    cv2.rectangle(
        frame,
        (bx - pad_x, by - th - pad_y),
        (bx + tw + pad_x, by + pad_y),
        (0, 215, 255),
        2,
        lineType=cv2.LINE_AA
    )
    cv2.putText(
        frame,
        banner_text,
        (bx, by),
        banner_font,
        banner_scale,
        (255, 255, 255),
        banner_thickness,
        lineType=cv2.LINE_AA
    )

    # 2. Giant Centered Countdown Numeral
    num_font = cv2.FONT_HERSHEY_SIMPLEX
    (nw, nh), _ = cv2.getTextSize(count_str, num_font, font_scale, thickness)
    cx = (w - nw) // 2
    cy = (h + nh) // 2

    # Circular backplate halo
    radius = int(max(nw, nh) * 0.85) + 35
    cv2.circle(overlay, (w // 2, h // 2), radius, (15, 15, 15), -1)
    cv2.addWeighted(overlay, 0.50, frame, 0.50, 0, frame)
    cv2.circle(frame, (w // 2, h // 2), radius, (0, 215, 255), 3, lineType=cv2.LINE_AA)

    # Drop shadow
    cv2.putText(
        frame,
        count_str,
        (cx + 6, cy + 6),
        num_font,
        font_scale,
        (0, 0, 0),
        thickness + 5,
        lineType=cv2.LINE_AA
    )
    # Bright Gold / Neon Cyan Numeral
    cv2.putText(
        frame,
        count_str,
        (cx, cy),
        num_font,
        font_scale,
        (0, 230, 255),
        thickness,
        lineType=cv2.LINE_AA
    )
    cv2.putText(
        frame,
        count_str,
        (cx, cy),
        num_font,
        font_scale,
        (255, 255, 255),
        max(1, thickness // 3),
        lineType=cv2.LINE_AA
    )

    return frame


def draw_flash_overlay(
    frame: np.ndarray,
    alpha: float
) -> np.ndarray:
    """
    Applies camera shutter flash whiteout blend onto frame with blending factor alpha [0.0, 1.0].
    """
    if alpha <= 0.001:
        return frame

    alpha_clamped = float(min(1.0, max(0.0, alpha)))
    white_overlay = np.full_like(frame, 255)
    return cv2.addWeighted(frame, 1.0 - alpha_clamped, white_overlay, alpha_clamped, 0.0)


# =============================================================================
# Synthetic Landmark Generator & Standalone Self-Test Suite
# =============================================================================

def create_synthetic_landmarks(
    hand_type: str = "peace",
    wrist: Tuple[float, float] = (0.5, 0.8),
    scale: float = 0.3,
    tilt_deg: float = 0.0,
    v_divergence: float = 22.0
) -> np.ndarray:
    """
    Generates realistic 21 2D synthetic hand landmark arrays for automated testing.
    hand_type options:
    - 'peace': Extended Index & Middle, curled Ring & Pinky, tucked Thumb.
    - 'open_palm': All 5 fingers extended outward.
    - 'fist': All 5 fingers curled tight.
    - 'portal': Index & Thumb extended, Middle + Ring + Pinky curled.
    - 'pointing': Index extended only.
    - 'three_fingers': Thumb + Index + Middle extended.
    - 'four_fingers': Index + Middle + Ring + Pinky extended.
    """
    rad = np.radians(tilt_deg)
    rot = np.array([
        [np.cos(rad), -np.sin(rad)],
        [np.sin(rad),  np.cos(rad)]
    ])

    # Determine finger states
    thumb_ext = hand_type in ("open_palm", "portal", "three_fingers")
    index_ext = hand_type in ("peace", "open_palm", "portal", "pointing", "three_fingers", "four_fingers")
    middle_ext = hand_type in ("peace", "open_palm", "three_fingers", "four_fingers")
    ring_ext = hand_type in ("open_palm", "four_fingers")
    pinky_ext = hand_type in ("open_palm", "four_fingers")

    pts: Dict[int, np.ndarray] = {}
    pts[WRIST] = np.array([0.0, 0.0])

    # Thumb
    pts[THUMB_CMC] = np.array([-0.18, 0.15])
    pts[THUMB_MCP] = np.array([-0.28, 0.30])
    pts[THUMB_IP] = np.array([-0.30, 0.42]) if thumb_ext else np.array([-0.15, 0.35])
    pts[THUMB_TIP] = np.array([-0.35, 0.55]) if thumb_ext else np.array([-0.05, 0.38])

    # Index
    pts[INDEX_MCP] = np.array([-0.15, 0.60])
    if index_ext:
        v_rad = np.radians(-v_divergence / 2.0)
        dir_idx = np.array([np.sin(v_rad), np.cos(v_rad)])
        pts[INDEX_PIP] = pts[INDEX_MCP] + dir_idx * 0.25
        pts[INDEX_DIP] = pts[INDEX_MCP] + dir_idx * 0.45
        pts[INDEX_TIP] = pts[INDEX_MCP] + dir_idx * 0.65
    else:
        pts[INDEX_PIP] = np.array([-0.15, 0.75])
        pts[INDEX_DIP] = np.array([-0.15, 0.68])
        pts[INDEX_TIP] = np.array([-0.15, 0.58])

    # Middle (Palm scale landmark)
    pts[MIDDLE_MCP] = np.array([0.0, 0.65])
    if middle_ext:
        v_rad = np.radians(v_divergence / 2.0)
        dir_mid = np.array([np.sin(v_rad), np.cos(v_rad)])
        pts[MIDDLE_PIP] = pts[MIDDLE_MCP] + dir_mid * 0.27
        pts[MIDDLE_DIP] = pts[MIDDLE_MCP] + dir_mid * 0.48
        pts[MIDDLE_TIP] = pts[MIDDLE_MCP] + dir_mid * 0.70
    else:
        pts[MIDDLE_PIP] = np.array([0.0, 0.80])
        pts[MIDDLE_DIP] = np.array([0.0, 0.73])
        pts[MIDDLE_TIP] = np.array([0.0, 0.63])

    # Ring
    pts[RING_MCP] = np.array([0.15, 0.58])
    if ring_ext:
        pts[RING_PIP] = np.array([0.15, 0.82])
        pts[RING_DIP] = np.array([0.15, 1.02])
        pts[RING_TIP] = np.array([0.15, 1.20])
    else:
        pts[RING_PIP] = np.array([0.15, 0.72])
        pts[RING_DIP] = np.array([0.15, 0.65])
        pts[RING_TIP] = np.array([0.15, 0.55])

    # Pinky
    pts[PINKY_MCP] = np.array([0.28, 0.50])
    if pinky_ext:
        pts[PINKY_PIP] = np.array([0.28, 0.70])
        pts[PINKY_DIP] = np.array([0.28, 0.88])
        pts[PINKY_TIP] = np.array([0.28, 1.03])
    else:
        pts[PINKY_PIP] = np.array([0.28, 0.63])
        pts[PINKY_DIP] = np.array([0.28, 0.56])
        pts[PINKY_TIP] = np.array([0.28, 0.48])

    # Transform to image coordinates (wrist offset, scale, rotation)
    transformed_pts = []
    wrist_np = np.array(wrist, dtype=np.float64)
    for i in range(21):
        local_p = pts[i]
        r_p = rot @ local_p
        # In screen coordinates, positive y is downward
        screen_pt = wrist_np + np.array([r_p[0] * scale, -r_p[1] * scale])
        transformed_pts.append(screen_pt)

    return np.array(transformed_pts, dtype=np.float64)


def run_self_tests() -> bool:
    """
    Executes comprehensive standalone self-test suite for Gesture Detector & Capture FSM.
    """
    print("=" * 70, flush=True)
    print("RUNNING GESTURE DETECTOR & CAPTURE FSM SELF-TEST SUITE", flush=True)
    print("=" * 70, flush=True)

    pass_count = 0
    total_tests = 0

    # -------------------------------------------------------------------------
    # Test Group 1: Positive Peace Sign Detection & Invariances
    # -------------------------------------------------------------------------
    print("\n[Group 1] Testing Positive Peace Sign Detection & Invariances...", flush=True)

    # 1.1 Standard Upright Peace Sign
    total_tests += 1
    lms_upright = create_synthetic_landmarks("peace")
    assert is_peace_gesture(lms_upright), "Standard upright Peace Sign failed detection!"
    pass_count += 1
    print("  ✓ 1.1 Standard upright Peace Sign: PASS", flush=True)

    # 1.2 Scale Invariance across distances (S = 0.05 to 0.65)
    total_tests += 1
    for s in [0.05, 0.10, 0.20, 0.35, 0.50, 0.65]:
        lms_scaled = create_synthetic_landmarks("peace", scale=s)
        assert is_peace_gesture(lms_scaled), f"Peace Sign at scale {s} failed detection!"
    pass_count += 1
    print("  ✓ 1.2 Scale Invariance (S=0.05 to 0.65): PASS", flush=True)

    # 1.3 Full 360-degree Tilt / Rotation Invariance
    total_tests += 1
    for tilt in [-180, -135, -90, -60, -45, -30, 0, 30, 45, 60, 90, 135, 180]:
        lms_tilted = create_synthetic_landmarks("peace", tilt_deg=tilt)
        assert is_peace_gesture(lms_tilted), f"Peace Sign at tilt {tilt}° failed detection!"
    pass_count += 1
    print("  ✓ 1.3 360° Tilt / Rotation Invariance (-180° to +180°): PASS", flush=True)

    # 1.4 V-formation Divergence Range (12° to 55°)
    total_tests += 1
    for v_div in [12.0, 18.0, 25.0, 35.0, 45.0, 55.0]:
        lms_v = create_synthetic_landmarks("peace", v_divergence=v_div)
        assert is_peace_gesture(lms_v), f"Peace Sign with V-divergence {v_div}° failed detection!"
    pass_count += 1
    print("  ✓ 1.4 V-formation Divergence Tolerance (12° to 55°): PASS", flush=True)

    # -------------------------------------------------------------------------
    # Test Group 2: Negative Gestures & Non-Interference Guard
    # -------------------------------------------------------------------------
    print("\n[Group 2] Testing Negative Gestures & Non-Interference Guard...", flush=True)

    # 2.1 Open Palm (🖐️)
    total_tests += 1
    lms_palm = create_synthetic_landmarks("open_palm")
    assert not is_peace_gesture(lms_palm), "Open Palm falsely detected as Peace Sign!"
    pass_count += 1
    print("  ✓ 2.1 Negative: Open Palm (all 5 extended): REJECTED (PASS)", flush=True)

    # 2.2 Fist (✊)
    total_tests += 1
    lms_fist = create_synthetic_landmarks("fist")
    assert not is_peace_gesture(lms_fist), "Fist falsely detected as Peace Sign!"
    pass_count += 1
    print("  ✓ 2.2 Negative: Fist (all curled): REJECTED (PASS)", flush=True)

    # 2.3 Portal Gesture Hand (Thumb + Index extended, Middle curled)
    total_tests += 1
    lms_portal = create_synthetic_landmarks("portal")
    assert not is_peace_gesture(lms_portal), "Portal gesture hand falsely detected as Peace Sign!"
    pass_count += 1
    print("  ✓ 2.3 Negative: Portal Filter Hand (Thumb+Index): REJECTED (PASS)", flush=True)

    # 2.4 Pointing / Finger Gun (Index extended only)
    total_tests += 1
    lms_pointing = create_synthetic_landmarks("pointing")
    assert not is_peace_gesture(lms_pointing), "Pointing finger falsely detected as Peace Sign!"
    pass_count += 1
    print("  ✓ 2.4 Negative: Pointing Finger (Index only): REJECTED (PASS)", flush=True)

    # 2.5 Three Fingers (Thumb + Index + Middle)
    total_tests += 1
    lms_three = create_synthetic_landmarks("three_fingers")
    assert not is_peace_gesture(lms_three), "Three Fingers falsely detected as Peace Sign!"
    pass_count += 1
    print("  ✓ 2.5 Negative: Three Fingers (Thumb+Index+Middle): REJECTED (PASS)", flush=True)

    # 2.6 Four Fingers (Index + Middle + Ring + Pinky)
    total_tests += 1
    lms_four = create_synthetic_landmarks("four_fingers")
    assert not is_peace_gesture(lms_four), "Four Fingers falsely detected as Peace Sign!"
    pass_count += 1
    print("  ✓ 2.6 Negative: Four Fingers (Index..Pinky): REJECTED (PASS)", flush=True)

    # -------------------------------------------------------------------------
    # Test Group 3: 6-State Capture FSM Lifecycle & Transitions
    # -------------------------------------------------------------------------
    print("\n[Group 3] Testing 6-State Capture FSM Lifecycle & Transitions...", flush=True)

    # 3.1 Full Capture Lifecycle: IDLE -> ARMED -> COUNTDOWN -> FLASH -> PREVIEW -> COOLDOWN -> IDLE
    total_tests += 1
    engine = GestureCaptureEngine(
        hold_duration=0.7,
        countdown_duration=3.0,
        flash_duration=0.15,
        preview_duration=6.0,
        cooldown_duration=2.0
    )

    t = 0.0
    dt = 0.0333  # ~30 FPS
    states_visited = []
    snap_triggered = False
    integer_ticks_recorded = []

    while t <= 13.0:
        hand_active = (0.5 <= t <= 4.5)
        hands = [lms_upright] if hand_active else []
        st, meta = engine.update(hands, frame_shape=(720, 1280), current_time=t)

        if st not in states_visited:
            states_visited.append(st)

        if meta["trigger_snap"]:
            snap_triggered = True

        if meta["is_integer_tick"]:
            integer_ticks_recorded.append((round(t, 2), meta["countdown_integer"]))

        t += dt

    expected_states = [
        CaptureState.IDLE,
        CaptureState.ARMED,
        CaptureState.COUNTDOWN,
        CaptureState.FLASH,
        CaptureState.PREVIEW,
        CaptureState.COOLDOWN
    ]
    assert states_visited == expected_states, f"State sequence mismatch! Got: {states_visited}"
    assert snap_triggered, "Snapshot trigger flag was NOT emitted on transition to FLASH!"
    assert len(integer_ticks_recorded) >= 3, f"Expected at least 3 integer ticks, got: {integer_ticks_recorded}"
    pass_count += 1
    print("  ✓ 3.1 Full FSM Lifecycle & Snapshot Trigger: PASS", flush=True)

    # 3.2 Premature Gesture Drop (Hold Abort)
    total_tests += 1
    engine_abort = GestureCaptureEngine(hold_duration=0.7)
    engine_abort.update([lms_upright], current_time=0.0)
    st, _ = engine_abort.update([lms_upright], current_time=0.3)
    assert st == CaptureState.ARMED, "Expected ARMED at t=0.3s"
    # Drop gesture before 0.7s
    st, meta = engine_abort.update([], current_time=0.4)
    assert st == CaptureState.IDLE, f"Expected reset to IDLE after drop, got {st}"
    assert meta["hold_progress"] == 0.0, "Hold progress was not reset"
    pass_count += 1
    print("  ✓ 3.2 Premature Hold Drop -> Clean IDLE Abort: PASS", flush=True)

    # 3.3 Cooldown Lockout Guard
    total_tests += 1
    engine_cd = GestureCaptureEngine(cooldown_duration=2.0)
    engine_cd.state = CaptureState.COOLDOWN
    engine_cd.cooldown_start_time = 10.0
    # Peace sign during cooldown must be ignored
    st, meta = engine_cd.update([lms_upright], current_time=11.0)
    assert st == CaptureState.COOLDOWN, "Gesture during cooldown wrongly changed state!"
    # After cooldown expires, transitions to IDLE
    st, _ = engine_cd.update([], current_time=12.1)
    assert st == CaptureState.IDLE, f"Expected transition to IDLE after cooldown, got {st}"
    pass_count += 1
    print("  ✓ 3.3 Cooldown Lockout Protection: PASS", flush=True)

    # 3.4 Manual Preview Dismissal
    total_tests += 1
    engine_pv = GestureCaptureEngine(preview_duration=6.0)
    engine_pv.state = CaptureState.PREVIEW
    engine_pv.preview_start_time = 0.0
    engine_pv.dismiss_preview(current_time=1.5)
    assert engine_pv.state == CaptureState.COOLDOWN, "Dismiss preview did not transition to COOLDOWN"
    pass_count += 1
    print("  ✓ 3.4 Manual Preview Dismissal: PASS", flush=True)

    # -------------------------------------------------------------------------
    # Test Group 4: Visual HUD Rendering Helpers
    # -------------------------------------------------------------------------
    print("\n[Group 4] Testing Visual HUD Rendering Helpers...", flush=True)

    # 4.1 Radial Progress Rendering
    total_tests += 1
    dummy_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    res_progress = draw_radial_progress(dummy_frame.copy(), (640, 360), 0.65)
    assert res_progress.shape == (720, 1280, 3), "Shape altered during radial progress render!"
    assert np.sum(res_progress) > 0, "Radial progress did not render any pixels!"
    pass_count += 1
    print("  ✓ 4.1 draw_radial_progress: PASS", flush=True)

    # 4.2 Countdown Numeral & Banner Rendering
    total_tests += 1
    res_cd = draw_countdown_overlay(dummy_frame.copy(), 2.45, is_integer_tick=False)
    assert res_cd.shape == (720, 1280, 3), "Shape altered during countdown overlay render!"
    assert np.sum(res_cd) > 0, "Countdown overlay did not render any pixels!"
    pass_count += 1
    print("  ✓ 4.2 draw_countdown_overlay: PASS", flush=True)

    # 4.3 Flash Overlay Blending
    total_tests += 1
    res_flash = draw_flash_overlay(dummy_frame.copy(), 0.85)
    assert res_flash.shape == (720, 1280, 3), "Shape altered during flash render!"
    mean_val = np.mean(res_flash)
    assert 200 <= mean_val <= 255, f"Flash brightness unexpected: {mean_val}"
    pass_count += 1
    print("  ✓ 4.3 draw_flash_overlay (alpha blend): PASS", flush=True)

    # -------------------------------------------------------------------------
    # Test Summary
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70, flush=True)
    print(f"SELF-TEST COMPLETE: {pass_count}/{total_tests} ASSERTIONS PASSED (100% SUCCESS)", flush=True)
    print("=" * 70, flush=True)
    return True


if __name__ == "__main__":
    success = run_self_tests()
    if not success:
        sys.exit(1)
    sys.exit(0)
