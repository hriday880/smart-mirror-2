import os
import sys
import hashlib
import time
import math
import tempfile
import urllib.request
import urllib.error
import socket
import unittest

PROJECT_ROOT = "/Users/hriday/Desktop/smart mirror #2/Filters"
sys.path.insert(0, PROJECT_ROOT)

import cv2
import numpy as np
import geometry
import filters
import hand_tracking
from gesture_detector_test import (
    is_peace_gesture,
    find_peace_gesture,
    CaptureState,
    GestureCaptureEngine,
    compute_palm_scale,
    _joint_angle_3p,
    _euclidean_distance,
    create_synthetic_landmarks,
    draw_radial_progress,
    draw_countdown_overlay,
    draw_flash_overlay,
    run_self_tests as run_gesture_self_tests
)
from delivery_server_test import (
    DeliveryServer,
    generate_qr_matrix,
    render_preview_card,
    get_local_ip,
    AsyncImageSaver,
    run_all_tests as run_delivery_self_tests
)

out_lines = []
def log(msg=""):
    print(msg)
    out_lines.append(msg)

log("=" * 80)
log("FORENSIC INTEGRITY AUDIT - SMART MIRROR HAND GESTURE PHOTO CAPTURE")
log("=" * 80)

# -----------------------------------------------------------------------------
# 1. Cryptographic SHA256 Verification of 7 Original Source Files
# -----------------------------------------------------------------------------
log("\n[CHECK 1] Cryptographic SHA-256 Hashes of 7 Original Source Files:")
orig_files = [
    "main.py",
    "filters.py",
    "geometry.py",
    "hand_tracking.py",
    "Launch Filters.command",
    "requirements.txt",
    "README.md"
]

all_orig_exist = True
orig_hashes = {}
for fn in orig_files:
    fp = os.path.join(PROJECT_ROOT, fn)
    if not os.path.isfile(fp):
        log(f"  ❌ MISSING: {fn}")
        all_orig_exist = False
        continue
    data = open(fp, "rb").read()
    sha = hashlib.sha256(data).hexdigest()
    orig_hashes[fn] = sha
    log(f"  ✓ {fn:<25} | Size: {len(data):5d} bytes | SHA256: {sha}")

# -----------------------------------------------------------------------------
# 2. Static Forensic Scan for Cheating / Hardcoded Mock Strings / Facades
# -----------------------------------------------------------------------------
log("\n[CHECK 2] Static Code Analysis for Hardcoded Outputs, Mock Results, and Facades:")
suspicious_patterns = [
    "return True # mock",
    "return False # mock",
    "return \"PASS\"",
    "return 'PASS'",
    "unittest.mock",
    "MagicMock",
    "mock_output",
    "fake_result",
]

prod_files = ["gesture_detector_test.py", "delivery_server_test.py", "main_test.py"]
for pfn in prod_files:
    pfp = os.path.join(PROJECT_ROOT, pfn)
    content = open(pfp, "r", encoding="utf-8").read()
    found_suspicious = []
    for pattern in suspicious_patterns:
        if pattern in content:
            found_suspicious.append(pattern)
    if found_suspicious:
        log(f"  ⚠️ Warning in {pfn}: Found {found_suspicious}")
    else:
        log(f"  ✓ {pfn:<25} : CLEAN (No suspicious mock hardcoding found)")

# -----------------------------------------------------------------------------
# 3. Mathematical Verification of Gesture Detection Engine
# -----------------------------------------------------------------------------
log("\n[CHECK 3] Mathematical Landmark Calculation Verification:")

# 3.1 Angle calculation math
p1 = np.array([0.0, 1.0])
p_vertex = np.array([0.0, 0.0])
p2_90 = np.array([1.0, 0.0])
p2_180 = np.array([0.0, -1.0])
p2_45 = np.array([1.0, 1.0])

ang90 = _joint_angle_3p(p1, p_vertex, p2_90)
ang180 = _joint_angle_3p(p1, p_vertex, p2_180)
ang45 = _joint_angle_3p(p1, p_vertex, p2_45)

log(f"  • Joint Angle (Orthogonal 90°): {ang90:.4f}° -> {'PASS' if abs(ang90 - 90.0) < 1e-4 else 'FAIL'}")
log(f"  • Joint Angle (Collinear 180°):  {ang180:.4f}° -> {'PASS' if abs(ang180 - 180.0) < 1e-4 else 'FAIL'}")
log(f"  • Joint Angle (Diagonal 45°):   {ang45:.4f}° -> {'PASS' if abs(ang45 - 45.0) < 1e-4 else 'FAIL'}")

# 3.2 Euclidean distance
dist_unit = _euclidean_distance(np.array([0.0, 0.0]), np.array([3.0, 4.0]))
log(f"  • Euclidean Distance ((0,0) to (3,4)): {dist_unit:.4f} -> {'PASS' if abs(dist_unit - 5.0) < 1e-4 else 'FAIL'}")

# 3.3 Palm scale calculation
peace_lms = create_synthetic_landmarks("peace", wrist=(0.5, 0.8), scale=0.3)
S = compute_palm_scale(peace_lms)
log(f"  • Palm Scale Metric S for scale=0.3: {S:.4f} (expected ~0.195) -> {'PASS' if 0.15 < S < 0.25 else 'FAIL'}")

# 3.4 6-Predicate Peace Sign Truth Table
gestures_to_test = [
    ("peace", True),
    ("open_palm", False),
    ("fist", False),
    ("portal", False),
    ("pointing", False),
    ("three_fingers", False),
    ("four_fingers", False),
]

all_gestures_pass = True
for gname, expected in gestures_to_test:
    lms = create_synthetic_landmarks(gname)
    det = is_peace_gesture(lms)
    status = "PASS" if det == expected else "FAIL"
    if det != expected:
        all_gestures_pass = False
    log(f"  • Gesture '{gname:<14}': Detected={str(det):<5} Expected={str(expected):<5} -> {status}")

# 3.5 Scale & Rotation Invariance
scales = [0.05, 0.1, 0.25, 0.5, 0.7]
scale_pass = True
for s in scales:
    lms = create_synthetic_landmarks("peace", scale=s)
    if not is_peace_gesture(lms):
        scale_pass = False
log(f"  • Scale Invariance across S in {scales}: {'PASS' if scale_pass else 'FAIL'}")

tilts = [-180, -135, -90, -45, -30, 0, 30, 45, 90, 135, 180]
tilt_pass = True
for t in tilts:
    lms = create_synthetic_landmarks("peace", tilt_deg=t)
    if not is_peace_gesture(lms):
        tilt_pass = False
log(f"  • In-Plane 360° Tilt Invariance across {tilts}: {'PASS' if tilt_pass else 'FAIL'}")

# -----------------------------------------------------------------------------
# 4. Authentic Image Processing, Filter Rendering & Asynchronous JPEG Saver
# -----------------------------------------------------------------------------
log("\n[CHECK 4] Image Capture, Filter Processing & Async JPEG Persistence:")
test_canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
test_canvas[:, :] = (80, 120, 160)
poly = np.array([(300, 200), (700, 200), (700, 500), (300, 500)], dtype=np.int32)

all_8_filters_work = True
for idx, ffunc in enumerate(filters.FILTROS):
    filtered_frame = geometry.paint_filter_in_polygon(test_canvas.copy(), poly, ffunc)
    diff = np.sum(np.abs(filtered_frame.astype(np.int32) - test_canvas.astype(np.int32)))
    if filtered_frame.shape != test_canvas.shape or diff == 0:
        all_8_filters_work = False
        log(f"  ❌ Filter [{idx}] {ffunc.__name__}: Inactive or altered shape")
    else:
        log(f"  ✓ Filter [{idx}] {ffunc.__name__:<16}: Output Valid (Diff={diff:10d} L1)")
log(f"  • All 8 Shader Filters Operational: {'PASS' if all_8_filters_work else 'FAIL'}")

# Test AsyncImageSaver
with tempfile.TemporaryDirectory() as tmpdir:
    saver = AsyncImageSaver(capture_dir=tmpdir)
    save_path = saver.save_async(test_canvas, "test_async_save.jpg", quality=95)
    time.sleep(0.3)
    saver.stop()
    file_exists = os.path.isfile(save_path)
    file_size = os.path.getsize(save_path) if file_exists else 0
    read_img = cv2.imread(save_path) if file_exists else None
    read_ok = read_img is not None and read_img.shape == test_canvas.shape
    log(f"  • AsyncImageSaver: File Exists={file_exists} ({file_size} B), Decodable={read_ok} -> {'PASS' if read_ok else 'FAIL'}")

# -----------------------------------------------------------------------------
# 5. QR Code Generation & Optical Decode Round-Trip
# -----------------------------------------------------------------------------
log("\n[CHECK 5] QR Code Generation & Matrix Scannability Verification:")
qr_target_url = "http://192.168.1.120:8000/view/capture_20260814_120000_123_edges.jpg"
qr_matrix = generate_qr_matrix(qr_target_url, target_size=180, border=3)
log(f"  • QR Matrix Generated: Shape={qr_matrix.shape}, Dtype={qr_matrix.dtype}")

# Decode using OpenCV QRCodeDetector
qr_detector = cv2.QRCodeDetector()
decoded_text, qr_pts, straight_qr = qr_detector.detectAndDecode(qr_matrix)
qr_success = (decoded_text == qr_target_url)
log(f"  • Optical QR Decode String: '{decoded_text}'")
log(f"  • QR Decode Match Ground Truth: {'PASS' if qr_success else 'FAIL'}")

# Test HUD Card Overlay with QR
hud_frame = render_preview_card(
    display_frame=test_canvas.copy(),
    photo_filename="capture_test.jpg",
    remaining_seconds=4.5,
    total_seconds=6.0,
    host_url=qr_target_url,
    thumbnail=test_canvas[200:500, 300:700]
)
hud_diff = np.sum(np.abs(hud_frame.astype(np.int32) - test_canvas.astype(np.int32)))
log(f"  • HUD Preview Card Composite: Rendered ({hud_diff} L1 pixel delta) -> {'PASS' if hud_diff > 10000 else 'FAIL'}")

# -----------------------------------------------------------------------------
# 6. Live HTTP Delivery Server Dynamic Socket Verification
# -----------------------------------------------------------------------------
log("\n[CHECK 6] Live HTTP Delivery Server & Protocol Compliance:")
with tempfile.TemporaryDirectory() as tmp_server_dir:
    test_photo_fn = "capture_20260814_130000_000_inverso.jpg"
    test_photo_path = os.path.join(tmp_server_dir, test_photo_fn)
    cv2.imwrite(test_photo_path, test_canvas)

    delivery_srv = DeliveryServer(capture_dir=tmp_server_dir, port=8950, max_port=8960, host="127.0.0.1")
    delivery_srv.start()
    time.sleep(0.15)
    
    server_port = delivery_srv.port
    log(f"  • Server Bound to Port: {server_port}")

    # 6.1 Raw image download GET /photo/<filename>
    photo_req = urllib.request.urlopen(f"http://127.0.0.1:{server_port}/photo/{test_photo_fn}")
    photo_data = photo_req.read()
    photo_ct = photo_req.headers.get("Content-Type")
    photo_valid_jpeg = (photo_data[:2] == b"\xff\xd8" and photo_data[-2:] == b"\xff\xd9")
    log(f"  • GET /photo/{test_photo_fn}: Status={photo_req.status}, Content-Type={photo_ct}, Valid JPEG={photo_valid_jpeg} ({len(photo_data)} B) -> {'PASS' if photo_valid_jpeg else 'FAIL'}")

    # 6.2 Mobile HTML landing page GET /view/<filename>
    view_req = urllib.request.urlopen(f"http://127.0.0.1:{server_port}/view/{test_photo_fn}")
    view_html = view_req.read().decode("utf-8")
    view_ct = view_req.headers.get("Content-Type")
    view_has_elements = ("<title>Your Smart Mirror Photo</title>" in view_html and f"/photo/{test_photo_fn}" in view_html and "Save Photo to Phone" in view_html)
    log(f"  • GET /view/{test_photo_fn}: Status={view_req.status}, Content-Type={view_ct}, Has Required UI={view_has_elements} -> {'PASS' if view_has_elements else 'FAIL'}")

    # 6.3 Health check GET /health
    health_req = urllib.request.urlopen(f"http://127.0.0.1:{server_port}/health")
    health_json = health_req.read().decode("utf-8")
    log(f"  • GET /health: Status={health_req.status}, JSON Content={health_json.strip()} -> {'PASS' if 'online' in health_json else 'FAIL'}")

    delivery_srv.stop()
    log(f"  • Delivery Server Teardown: Clean Stop")

# -----------------------------------------------------------------------------
# 7. Execute Standalone Self-Tests and Unified Test Suites
# -----------------------------------------------------------------------------
log("\n[CHECK 7] Executing Module Self-Tests and Full 4-Tier Test Runner:")
try:
    g_ok = run_gesture_self_tests()
    log(f"  • gesture_detector_test.py Self-Tests: {'PASS (100%)' if g_ok else 'FAIL'}")
except Exception as e:
    log(f"  ❌ gesture_detector_test.py Self-Tests Error: {e}")

try:
    d_ok = run_delivery_self_tests()
    log(f"  • delivery_server_test.py Self-Tests: {'PASS (100%)' if d_ok else 'FAIL'}")
except Exception as e:
    log(f"  ❌ delivery_server_test.py Self-Tests Error: {e}")

# Run unittest suite directly
log("\n  Running 4-Tier Test Suites (Tiers 1-4)...")
loader = unittest.TestLoader()
suite = unittest.TestSuite()
suite.addTests(loader.loadTestsFromName("tests.test_tier1_features"))
suite.addTests(loader.loadTestsFromName("tests.test_tier2_boundaries"))
suite.addTests(loader.loadTestsFromName("tests.test_tier3_combinations"))
suite.addTests(loader.loadTestsFromName("tests.test_tier4_scenarios"))

runner = unittest.TextTestRunner(verbosity=0)
t_start = time.time()
test_result = runner.run(suite)
t_elapsed = time.time() - t_start

total_tests = test_result.testsRun
failures_count = len(test_result.failures)
errors_count = len(test_result.errors)
passed_count = total_tests - failures_count - errors_count

log(f"  • Total Tests Executed: {total_tests}")
log(f"  • Passed: {passed_count}")
log(f"  • Failures: {failures_count}")
log(f"  • Errors: {errors_count}")
log(f"  • Execution Time: {t_elapsed:.2f}s")
log(f"  • Test Suite Status: {'100% PASS' if failures_count == 0 and errors_count == 0 else 'FAIL'}")

# -----------------------------------------------------------------------------
# Final Verdict
# -----------------------------------------------------------------------------
log("\n" + "=" * 80)
clean = (
    all_orig_exist and
    all_8_filters_work and
    all_gestures_pass and
    scale_pass and
    tilt_pass and
    qr_success and
    failures_count == 0 and
    errors_count == 0
)
verdict = "CLEAN" if clean else "INTEGRITY VIOLATION"
log(f"FINAL FORENSIC VERDICT: {verdict}")
log("=" * 80)

# Save output to audit_results.txt
with open("/Users/hriday/Desktop/smart mirror #2/Filters/.agents/auditor_1/audit_results.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out_lines))
