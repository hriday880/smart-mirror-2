"""
conftest.py - Test configuration, synthetic MediaPipe landmarks, and mock video capture.
Provides reusable fixtures and mock generators for the 4-tier testing suite.
"""

import math
import os
import sys
from typing import List, Tuple, Dict, Any, Optional
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Landmark Index Constants matching MediaPipe Hand specification
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


class MockLandmark:
    """Mock MediaPipe Normalized Landmark object."""
    def __init__(self, x: float, y: float, z: float = 0.0, visibility: float = 1.0):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)
        self.visibility = float(visibility)

    def __repr__(self):
        return f"MockLandmark(x={self.x:.4f}, y={self.y:.4f}, z={self.z:.4f})"


class MockLandmarkList:
    """Mock MediaPipe NormalizedLandmarkList containing 21 landmarks."""
    def __init__(self, landmarks: List[MockLandmark]):
        if len(landmarks) != 21:
            raise ValueError(f"Expected 21 landmarks for hand, got {len(landmarks)}")
        self.landmark = landmarks

    def __getitem__(self, idx: int) -> MockLandmark:
        return self.landmark[idx]

    def __len__(self) -> int:
        return len(self.landmark)

    def __iter__(self):
        return iter(self.landmark)


class MockClassification:
    """Mock MediaPipe Classification for handedness."""
    def __init__(self, label: str = "Right", score: float = 0.99):
        self.label = label
        self.score = score


class MockHandedness:
    """Mock MediaPipe Handedness container."""
    def __init__(self, label: str = "Right", score: float = 0.99):
        self.classification = [MockClassification(label=label, score=score)]


def create_synthetic_hand(
    gesture: str = "peace",
    wrist: Tuple[float, float] = (0.5, 0.8),
    scale: float = 0.35,
    tilt_deg: float = 0.0,
    hand_label: str = "Right",
    v_divergence: float = 24.0,
    noise_sigma: float = 0.0
) -> MockLandmarkList:
    """
    Generates a realistic 21-point MediaPipe NormalizedLandmarkList for various gestures.
    Uses precise geometric formulas invariant to scale and rotation.
    """
    from gesture_detector_test import create_synthetic_landmarks

    # Map gesture names
    g_map = {
        "peace": "peace",
        "portal": "portal",
        "open_palm": "open_palm",
        "fist": "fist",
        "thumbs_up": "pointing", # thumb-like / pointing negative
        "pointing": "pointing",
        "three_fingers": "three_fingers",
        "four_fingers": "four_fingers",
    }
    hand_type = g_map.get(gesture, "open_palm")

    pts_np = create_synthetic_landmarks(
        hand_type=hand_type,
        wrist=wrist,
        scale=scale,
        tilt_deg=tilt_deg,
        v_divergence=v_divergence
    )

    if hand_label == "Left":
        # Mirror along x-axis relative to wrist
        wx = wrist[0]
        pts_np[:, 0] = 2.0 * wx - pts_np[:, 0]

    if noise_sigma > 0.0:
        pts_np += np.random.normal(0, noise_sigma, pts_np.shape)

    landmarks = [MockLandmark(pts_np[i, 0], pts_np[i, 1]) for i in range(21)]
    return MockLandmarkList(landmarks)


class MockVideoCapture:
    """Mock cv2.VideoCapture for headless end-to-end testing."""
    def __init__(self, max_frames: int = 150, width: int = 640, height: int = 480, fps: int = 30):
        self.max_frames = max_frames
        self.current_frame = 0
        self.width = width
        self.height = height
        self.fps = fps
        self._is_opened = True
        self.properties = {
            3: float(width),   # CV_CAP_PROP_FRAME_WIDTH
            4: float(height),  # CV_CAP_PROP_FRAME_HEIGHT
            5: float(fps),     # CV_CAP_PROP_FPS
        }

    def isOpened(self) -> bool:
        return self._is_opened

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self.current_frame >= self.max_frames or not self._is_opened:
            return False, None
        self.current_frame += 1
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        frame[:, :, 0] = np.linspace(30, 80, self.width, dtype=np.uint8)
        frame[:, :, 1] = np.linspace(40, 90, self.height, dtype=np.uint8).reshape(-1, 1)
        frame[:, :, 2] = 60
        return True, frame

    def release(self) -> None:
        self._is_opened = False

    def get(self, prop_id: int) -> float:
        return self.properties.get(prop_id, 0.0)

    def set(self, prop_id: int, value: float) -> bool:
        self.properties[prop_id] = float(value)
        if prop_id == 3:
            self.width = int(value)
        elif prop_id == 4:
            self.height = int(value)
        elif prop_id == 5:
            self.fps = int(value)
        return True


def generate_solid_frame(w: int = 640, h: int = 480, color: Tuple[int, int, int] = (128, 128, 128)) -> np.ndarray:
    """Generates a solid color BGR uint8 test frame."""
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:] = color
    return frame


def generate_checkerboard_frame(w: int = 640, h: int = 480, square_size: int = 40) -> np.ndarray:
    """Generates a checkerboard test frame."""
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(0, h, square_size):
        for x in range(0, w, square_size):
            if ((x // square_size) + (y // square_size)) % 2 == 0:
                frame[y:y+square_size, x:x+square_size] = (220, 220, 220)
            else:
                frame[y:y+square_size, x:x+square_size] = (30, 30, 30)
    return frame
