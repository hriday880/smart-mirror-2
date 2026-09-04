"""
delivery_server_test.py - Smart Mirror Fair Delivery Server & QR Subsystem
==========================================================================
Provides:
  1. Dynamic LAN IP discovery (`get_local_ip()`) using UDP routing probe.
  2. Background daemon HTTP server (`ThreadingHTTPServer`) with automatic port hopping (8000-8020).
     - Endpoints:
       * GET /photo/<filename>   -> Serves raw binary JPEG image
       * GET /latest             -> Redirects / serves most recent capture
       * GET / or /view/<file>   -> Serves responsive mobile HTML landing page with 1-tap save & Web Share API
       * GET /health             -> JSON status endpoint
  3. Asynchronous high-resolution image persistence:
     - Saves pristine filtered image to `captures/capture_YYYYMMDD_HHMMSS_<filter>.jpg` at JPEG quality 95.
     - Background daemon thread queue avoids camera loop frame drops.
  4. Zero-dependency OpenCV QR Code Generator (`cv2.QRCodeEncoder_create()` + fallback).
  5. HUD Preview Card Overlay:
     - `render_preview_card(display_frame, photo_filename, remaining_seconds)`
     - Overlays semi-transparent card with photo thumbnail, pixel-sharp QR code, countdown timer, and local URL.
  6. Standalone self-test suite when executed as `__main__`.
"""

import os
import sys
import time
import socket
import logging
import threading
import queue
import html
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

import cv2
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [DeliveryServer] %(message)s"
)
logger = logging.getLogger("DeliveryServer")

# Global Configuration Defaults
DEFAULT_PORT = 8000
DEFAULT_MAX_PORT = 8020
DEFAULT_CAPTURE_DIR = "captures"
JPEG_QUALITY = 95
DEFAULT_PREVIEW_DURATION = 6.0


# ==============================================================================
# 1. Dynamic LAN IP Discovery
# ==============================================================================

def get_local_ip() -> str:
    """
    Determines the active LAN IPv4 address reachable by mobile devices on the same Wi-Fi.
    Uses UDP route discovery to probe the default gateway without sending actual network traffic.
    Falls back to hostname resolution or localhost loopback if offline.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 8.8.8.8:80 does not need to be reachable; the OS selects the active outbound interface
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
    finally:
        s.close()

    # If returned localhost, check if any non-loopback IPv4 interface is available
    if not ip or ip.startswith("127."):
        try:
            hostname = socket.gethostname()
            for addr in socket.getaddrinfo(hostname, None):
                candidate = addr[4][0]
                if candidate and not candidate.startswith("127.") and ":" not in candidate:
                    ip = candidate
                    break
        except Exception:
            pass

    return ip if ip else "127.0.0.1"


# ==============================================================================
# 2. Zero-Dependency QR Code Generator
# ==============================================================================

def _generate_qr_fallback(text: str, target_size: int = 180, border: int = 4) -> np.ndarray:
    """
    Fallback visual QR-like barcode matrix generator used if OpenCV's QRCodeEncoder
    encounters an unexpected platform limitation.
    """
    # Create a deterministic visual 2D matrix pattern based on hash of text
    import hashlib
    h = hashlib.sha256(text.encode("utf-8")).digest()
    n = 25
    mat = np.ones((n, n), dtype=np.uint8) * 255
    # Position patterns (finders)
    for r, c in [(0, 0), (0, n - 7), (n - 7, 0)]:
        mat[r:r+7, c:c+7] = 0
        mat[r+1:r+6, c+1:c+6] = 255
        mat[r+2:r+5, c+2:c+5] = 0
    # Fill data from hash
    bit_idx = 0
    for r in range(n):
        for c in range(n):
            if (r < 8 and (c < 8 or c >= n - 8)) or (r >= n - 8 and c < 8):
                continue
            byte_val = h[(bit_idx // 8) % len(h)]
            bit = (byte_val >> (bit_idx % 8)) & 1
            mat[r, c] = 0 if bit else 255
            bit_idx += 1
    
    padded = cv2.copyMakeBorder(mat, border, border, border, border, cv2.BORDER_CONSTANT, value=255)
    scaled = cv2.resize(padded, (target_size, target_size), interpolation=cv2.INTER_NEAREST)
    return cv2.cvtColor(scaled, cv2.COLOR_GRAY2BGR)


_QR_RENDER_CACHE: Dict[Tuple[str, int, int], np.ndarray] = {}
_QR_RENDER_CACHE_LOCK = threading.Lock()
_QR_RENDER_CACHE_MAX = 32


def _render_qr_candidate(
    matrix: np.ndarray,
    border_top: int,
    border_bottom: int,
    border_left: int,
    border_right: int,
    module_px: int,
    target_size: int,
) -> np.ndarray:
    """
    Renders a raw QR matrix onto a (target_size, target_size, 3) BGR canvas using
    integer module pitch (crisp nearest-neighbour blocks).

    Asymmetric quiet-zone borders are supported: when the bordered matrix size
    divides the target exactly (e.g. 40 modules * 5 px = 200 px), the code fills
    the canvas edge-to-edge. This grid alignment is critical: after an area
    downscale to 80 px every module lands on an exact 2 px boundary with zero
    aliasing, which keeps finder patterns machine-readable at extreme sizes.
    """
    padded = cv2.copyMakeBorder(
        matrix,
        border_top,
        border_bottom,
        border_left,
        border_right,
        cv2.BORDER_CONSTANT,
        value=255,
    )
    n_total = padded.shape[0]
    side = n_total * module_px
    scaled = cv2.resize(padded, (side, side), interpolation=cv2.INTER_NEAREST)

    if side >= target_size:
        crop = side - target_size
        off_top = crop * border_top // max(1, border_top + border_bottom)
        off_left = crop * border_left // max(1, border_left + border_right)
        off_top = min(max(off_top, 0), crop)
        off_left = min(max(off_left, 0), crop)
        canvas = scaled[off_top:off_top + target_size, off_left:off_left + target_size]
    else:
        canvas = np.full((target_size, target_size), 255, dtype=np.uint8)
        off_y = (target_size - side) // 2
        off_x = (target_size - side) // 2
        canvas[off_y:off_y + side, off_x:off_x + side] = scaled

    return cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)


def _qr_survives_stress(qr_bgr: np.ndarray, text: str) -> bool:
    """
    Deterministic micro-battery mirroring real-world phone-camera degradation:
      1. Baseline decode.
      2. 200 -> 80 px area downscale + nearest re-upscale (extreme distance).
      3. Additive Gaussian noise sigma=30 (low-light sensor gain).
    A candidate is only accepted if it survives all three probes.
    """
    detector = cv2.QRCodeDetector()
    if detector.detectAndDecode(qr_bgr)[0] != text:
        return False

    small = cv2.resize(qr_bgr, (80, 80), interpolation=cv2.INTER_AREA)
    restored = cv2.resize(small, (200, 200), interpolation=cv2.INTER_NEAREST)
    if detector.detectAndDecode(restored)[0] != text:
        return False

    noise = np.random.default_rng(7).normal(0, 30, qr_bgr.shape).astype(np.float32)
    noisy = np.clip(qr_bgr.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    return detector.detectAndDecode(noisy)[0] == text


def generate_qr_matrix(text: str, target_size: int = 180, border: int = 4) -> np.ndarray:
    """
    Generates a pixel-sharp 3-channel (BGR) QR code matrix image using OpenCV's
    built-in QRCodeEncoder, optimised for decodability under optical degradation
    (downscaling, sensor noise, perspective warp).

    Strategy (in order):
      1. Memoised cache lookup keyed by (text, target_size, border).
      2. "Grid-aligned" candidates: an asymmetric quiet zone is chosen so the
         bordered module count divides the target size exactly (e.g. 40 modules
         x 5 px = 200 px). Perfect alignment survives an area downscale to 80 px
         with zero aliasing. Every candidate must pass a deterministic decode
         battery before acceptance.
      3. Classic centred integer-pitch renders (also battery-verified).
      4. Unverified classic render (graceful degradation for tiny targets below
         the physical decode resolution floor).
      5. Visual fallback generator if OpenCV's encoder is unavailable.

    Parameters:
        text (str): The URL or text string to encode.
        target_size (int): Target pixel width and height (square).
        border (int): Preferred quiet zone padding width in modules for the
            classic centred layout (aligned layouts may use less).

    Returns:
        np.ndarray: BGR uint8 image of dimensions (target_size, target_size, 3).
    """
    cache_key = (text, int(target_size), int(border))
    with _QR_RENDER_CACHE_LOCK:
        cached = _QR_RENDER_CACHE.get(cache_key)
    if cached is not None:
        return cached.copy()

    def _cache_put(img: np.ndarray) -> np.ndarray:
        with _QR_RENDER_CACHE_LOCK:
            if len(_QR_RENDER_CACHE) >= _QR_RENDER_CACHE_MAX:
                _QR_RENDER_CACHE.clear()
            _QR_RENDER_CACHE[cache_key] = img
        return img.copy()

    matrix = None
    try:
        if hasattr(cv2, "QRCodeEncoder_create"):
            matrix = cv2.QRCodeEncoder_create().encode(text)
            if matrix is None or matrix.size == 0:
                matrix = None
    except Exception as e:
        logger.warning(f"cv2.QRCodeEncoder failed ({e}); using fallback generator.")

    if matrix is not None:
        n_modules = matrix.shape[0]
        candidates = []

        # 1. Exact grid alignment: bordered module count divides target evenly.
        for bt, bb, bl, br in ((1, 2, 1, 2), (2, 1, 2, 1), (1, 2, 2, 1)):
            total_v = n_modules + bt + bb
            total_h = n_modules + bl + br
            if total_v == total_h and total_v > 0 and target_size % total_v == 0:
                module_px = target_size // total_v
                if 1 <= module_px <= 24:
                    candidates.append((bt, bb, bl, br, module_px))

        # 2. Classic centred layout (symmetric quiet zone), pitches around the
        #    natural fit; accepted only if it passes the stress battery.
        classic_border = max(1, int(border))
        base_div = max(1, target_size // (n_modules + 2 * classic_border))
        for module_px in range(base_div, base_div + 3):
            candidates.append(
                (classic_border, classic_border, classic_border, classic_border, module_px)
            )

        seen = set()
        for cfg in candidates:
            if cfg in seen:
                continue
            seen.add(cfg)
            bt, bb, bl, br, module_px = cfg
            try:
                qr_bgr = _render_qr_candidate(matrix, bt, bb, bl, br, module_px, target_size)
                if qr_bgr.shape != (target_size, target_size, 3):
                    continue
                if _qr_survives_stress(qr_bgr, text):
                    return _cache_put(qr_bgr)
            except Exception:
                continue

        # 3. Graceful degradation: classic render without battery verification
        #    (tiny targets below the physical decode floor still need a shape).
        try:
            module_px = max(1, int(round(target_size / (n_modules + 2 * classic_border))))
            qr_bgr = _render_qr_candidate(
                matrix, classic_border, classic_border,
                classic_border, classic_border, module_px, target_size
            )
            if qr_bgr.shape == (target_size, target_size, 3):
                return _cache_put(qr_bgr)
        except Exception as e:
            logger.warning(f"QR classic render failed ({e}); using fallback generator.")

    fallback = _generate_qr_fallback(text, target_size, border)
    return _cache_put(fallback)


# ==============================================================================
# 3. Asynchronous High-Resolution Image Persistence
# ==============================================================================

class AsyncImageSaver:
    """
    Background worker thread managing asynchronous JPEG encoding and disk I/O.
    Prevents camera frame drops and UI stutter during photo capture.
    """
    def __init__(self, capture_dir: str = DEFAULT_CAPTURE_DIR):
        self.capture_dir = capture_dir
        os.makedirs(self.capture_dir, exist_ok=True)
        self._queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="AsyncImageSaverWorker"
        )
        self._thread.start()

    def _worker_loop(self) -> None:
        # Keep processing until the explicit None sentinel arrives (FIFO), so
        # every task enqueued before stop() is guaranteed to hit the disk.
        # Exiting on the stop flag alone would drop pending writes and could
        # race directory cleanups (files appearing after a tree walk).
        while True:
            try:
                task = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if task is None:
                self._queue.task_done()
                break

            filepath, frame_copy, quality, on_complete = task
            try:
                cv2.imwrite(filepath, frame_copy, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
                if on_complete:
                    on_complete(filepath, True)
            except Exception as e:
                logger.error(f"Failed to write image {filepath}: {e}")
                if on_complete:
                    on_complete(filepath, False)
            finally:
                self._queue.task_done()

    def save_async(
        self,
        frame: np.ndarray,
        filename: str,
        quality: int = JPEG_QUALITY,
        on_complete: Optional[callable] = None
    ) -> str:
        """
        Enqueues an image buffer for asynchronous writing to disk.
        Returns the absolute filepath immediately.
        """
        os.makedirs(self.capture_dir, exist_ok=True)
        filepath = os.path.join(self.capture_dir, filename)
        frame_copy = frame.copy()
        self._queue.put((filepath, frame_copy, quality, on_complete))
        return filepath

    def save_sync(
        self,
        frame: np.ndarray,
        filename: str,
        quality: int = JPEG_QUALITY
    ) -> str:
        """
        Synchronously saves an image to disk. Useful for testing and direct writes.
        """
        os.makedirs(self.capture_dir, exist_ok=True)
        filepath = os.path.join(self.capture_dir, filename)
        cv2.imwrite(filepath, frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        return filepath

    def stop(self) -> None:
        """Stops worker thread cleanly after draining all queued writes."""
        self._stop_event.set()
        self._queue.put(None)  # FIFO sentinel: processed after all pending tasks
        if self._thread.is_alive():
            self._thread.join(timeout=10.0)


# ==============================================================================
# 4. Mobile Landing Page HTML Generator
# ==============================================================================

def render_mobile_landing_html(
    filename: str,
    photo_url: str,
    server_host: str,
    filter_name: str = "Smart Mirror Filter",
    timestamp_str: str = ""
) -> str:
    """
    Renders an ultra-fast, responsive HTML5 mobile landing page with dark glassmorphism
    styling, large photo preview, one-tap save, and native Web Share integration.
    """
    escaped_file = html.escape(filename)
    escaped_url = html.escape(photo_url)
    escaped_filter = html.escape(filter_name.title())
    escaped_ts = html.escape(timestamp_str if timestamp_str else datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Your Smart Mirror Photo</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: #090d16;
      color: #f1f5f9;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 16px;
    }}
    .card {{
      background: #131b2e;
      border: 1px solid #1e293b;
      border-radius: 20px;
      padding: 20px;
      max-width: 480px;
      width: 100%;
      box-shadow: 0 20px 40px rgba(0,0,0,0.6), 0 0 20px rgba(14, 165, 233, 0.15);
      text-align: center;
    }}
    .badge {{
      display: inline-block;
      background: linear-gradient(135deg, #0ea5e9, #6366f1);
      color: white;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 1px;
      text-transform: uppercase;
      padding: 4px 12px;
      border-radius: 999px;
      margin-bottom: 12px;
    }}
    h1 {{
      font-size: 22px;
      font-weight: 800;
      margin-bottom: 6px;
      background: linear-gradient(to right, #38bdf8, #818cf8);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .subtitle {{
      color: #94a3b8;
      font-size: 13px;
      margin-bottom: 16px;
    }}
    .img-container {{
      position: relative;
      width: 100%;
      border-radius: 14px;
      overflow: hidden;
      background: #020617;
      border: 2px solid #334155;
      margin-bottom: 20px;
      box-shadow: 0 8px 16px rgba(0,0,0,0.4);
    }}
    .img-container img {{
      width: 100%;
      height: auto;
      display: block;
      transition: transform 0.3s ease;
    }}
    .actions {{
      display: flex;
      flex-direction: column;
      gap: 12px;
    }}
    .btn {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      width: 100%;
      padding: 14px 20px;
      border-radius: 12px;
      font-size: 16px;
      font-weight: 700;
      text-decoration: none;
      border: none;
      cursor: pointer;
      transition: all 0.2s ease;
    }}
    .btn-save {{
      background: linear-gradient(135deg, #0284c7, #2563eb);
      color: white;
      box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4);
    }}
    .btn-save:active {{
      transform: scale(0.98);
      background: linear-gradient(135deg, #0369a1, #1d4ed8);
    }}
    .btn-share {{
      background: #1e293b;
      color: #38bdf8;
      border: 1px solid #334155;
    }}
    .btn-share:active {{
      background: #334155;
    }}
    .footer {{
      margin-top: 20px;
      color: #64748b;
      font-size: 11px;
    }}
    .toast {{
      visibility: hidden;
      min-width: 200px;
      background-color: #334155;
      color: #fff;
      text-align: center;
      border-radius: 8px;
      padding: 10px;
      position: fixed;
      z-index: 100;
      bottom: 30px;
      font-size: 14px;
      opacity: 0;
      transition: opacity 0.3s, visibility 0.3s;
    }}
    .toast.show {{
      visibility: visible;
      opacity: 1;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">✨ Fair Photo Booth</div>
    <h1>Your Capture is Ready!</h1>
    <p class="subtitle">{escaped_filter} &bull; {escaped_ts}</p>
    
    <div class="img-container">
      <img src="/photo/{escaped_file}" alt="Smart Mirror Photo" id="mirrorPhoto">
    </div>
    
    <div class="actions">
      <a href="/photo/{escaped_file}" download="{escaped_file}" class="btn btn-save" id="saveBtn">
        📥 Save Photo to Phone
      </a>
      <button class="btn btn-share" onclick="handleShare()">
        📤 Share Photo
      </button>
    </div>

    <div class="footer">
      Powered by Smart Mirror Interactive Booth &bull; Tap &amp; hold photo to save on iOS
    </div>
  </div>

  <div id="toast" class="toast">Link copied to clipboard!</div>

  <script>
    function showToast(msg) {{
      const toast = document.getElementById("toast");
      toast.innerText = msg;
      toast.className = "toast show";
      setTimeout(() => {{ toast.className = "toast"; }}, 2500);
    }}

    async function handleShare() {{
      const photoUrl = window.location.origin + "/photo/{escaped_file}";
      if (navigator.share) {{
        try {{
          await navigator.share({{
            title: "My Smart Mirror Photo",
            text: "Check out my photo from the Smart Mirror Booth!",
            url: window.location.href
          }});
        }} catch (err) {{
          if (err.name !== "AbortError") {{
            copyLink();
          }}
        }}
      }} else {{
        copyLink();
      }}
    }}

    function copyLink() {{
      navigator.clipboard.writeText(window.location.href).then(() => {{
        showToast("Link copied to clipboard!");
      }}).catch(() => {{
        showToast("Share URL: " + window.location.href);
      }});
    }}
  </script>
</body>
</html>
"""


# ==============================================================================
# 5. Threaded HTTP Request Handler
# ==============================================================================

class DeliveryHTTPRequestHandler(BaseHTTPRequestHandler):
    """
    High-performance HTTP Request Handler for the Smart Mirror delivery subsystem.
    Handles image streaming, latest photo discovery, and mobile landing page rendering.
    """
    server_version = "SmartMirrorDelivery/2.0"

    def log_message(self, format: str, *args: Any) -> None:
        """Suppresses default stderr request logging for clean console output."""
        pass

    @property
    def delivery_server(self) -> 'DeliveryServer':
        return getattr(self.server, "delivery_server", None)

    def do_HEAD(self) -> None:
        self._handle_request(is_head=True)

    def do_GET(self) -> None:
        self._handle_request(is_head=False)

    def _handle_request(self, is_head: bool = False) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path.strip("/")

        # Endpoint: GET /health
        if path == "health" or path == "status":
            self._send_json(200, {
                "status": "online",
                "host": self.delivery_server.host if self.delivery_server else "127.0.0.1",
                "port": self.delivery_server.port if self.delivery_server else DEFAULT_PORT,
                "latest_photo": self.delivery_server.get_latest_filename() if self.delivery_server else None,
                "timestamp": datetime.now().isoformat()
            }, is_head)
            return

        # Endpoint: GET /latest
        if path == "latest":
            latest_fn = self.delivery_server.get_latest_filename() if self.delivery_server else None
            if latest_fn:
                self.send_response(302)
                self.send_header("Location", f"/view/{latest_fn}")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
            else:
                self._send_html(200, "<h2>No photos captured yet!</h2><p>Trigger a peace gesture in front of the mirror.</p>", is_head)
            return

        # Endpoint: GET /photo/<filename>
        if path.startswith("photo/"):
            filename = path[len("photo/"):].strip()
            self._serve_photo(filename, is_head)
            return

        # Endpoint: GET /view/<filename>
        if path.startswith("view/"):
            filename = path[len("view/"):].strip()
            self._serve_landing_page(filename, is_head)
            return

        # Endpoint: Root GET /
        if path == "":
            latest_fn = self.delivery_server.get_latest_filename() if self.delivery_server else None
            if latest_fn:
                self._serve_landing_page(latest_fn, is_head)
            else:
                self._send_html(200, "<h2>✨ Smart Mirror Photo Booth ✨</h2><p>Make a peace sign (✌️) to capture your photo!</p>", is_head)
            return

        # 404 Fallback
        self._send_error(404, f"Path /{path} not found.")

    def _serve_photo(self, filename: str, is_head: bool = False) -> None:
        # Sanitize filename against directory traversal
        clean_name = os.path.basename(filename)
        if clean_name != filename or not filename.lower().endswith((".jpg", ".jpeg", ".png")):
            self._send_error(403, "Access forbidden: Invalid filename.")
            return

        capture_dir = self.delivery_server.capture_dir if self.delivery_server else DEFAULT_CAPTURE_DIR
        filepath = os.path.join(capture_dir, clean_name)

        # Check in-memory frame cache first
        img_bytes = None
        if self.delivery_server and clean_name in self.delivery_server._memory_cache:
            frame = self.delivery_server._memory_cache[clean_name]
            success, enc = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
            if success:
                img_bytes = enc.tobytes()

        # Check disk if not in memory cache
        if img_bytes is None:
            if os.path.isfile(filepath):
                try:
                    with open(filepath, "rb") as f:
                        img_bytes = f.read()
                except Exception as e:
                    self._send_error(500, f"Failed to read photo file: {e}")
                    return
            else:
                self._send_error(404, f"Photo '{clean_name}' not found.")
                return

        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(img_bytes)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        if not is_head:
            try:
                self.wfile.write(img_bytes)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _serve_landing_page(self, filename: str, is_head: bool = False) -> None:
        clean_name = os.path.basename(filename)
        if clean_name != filename or not filename.lower().endswith((".jpg", ".jpeg", ".png")):
            self._send_error(403, "Access forbidden.")
            return

        host = self.delivery_server.host if self.delivery_server else "127.0.0.1"
        port = self.delivery_server.port if self.delivery_server else DEFAULT_PORT
        photo_url = f"http://{host}:{port}/photo/{clean_name}"
        
        # Parse filter name from filename if standard naming convention
        parts = clean_name.replace(".jpg", "").split("_")
        filter_name = parts[-1] if len(parts) >= 3 else "Mirror Portal"

        html_content = render_mobile_landing_html(
            filename=clean_name,
            photo_url=photo_url,
            server_host=f"{host}:{port}",
            filter_name=filter_name
        )
        self._send_html(200, html_content, is_head)

    def _send_html(self, status: int, content: str, is_head: bool = False) -> None:
        payload = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        if not is_head:
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _send_json(self, status: int, data: Dict[str, Any], is_head: bool = False) -> None:
        import json
        payload = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if not is_head:
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _send_error(self, status: int, message: str) -> None:
        err_html = f"<!DOCTYPE html><html><body style='background:#0f172a;color:#f8fafc;font-family:sans-serif;padding:40px;text-align:center;'><h2>Error {status}</h2><p>{html.escape(message)}</p></body></html>"
        self._send_html(status, err_html)


class _ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Threading HTTP server with daemon client threads."""
    daemon_threads = True
    allow_reuse_address = True


# ==============================================================================
# 6. Delivery Server Subsystem Class
# ==============================================================================

class DeliveryServer:
    """
    Daemon HTTP Delivery Server for the Smart Mirror.
    Provides automatic port hopping, dynamic LAN IP discovery, asynchronous image
    saving, mobile landing pages, and HUD card rendering.
    """
    def __init__(
        self,
        capture_dir: str = DEFAULT_CAPTURE_DIR,
        port: int = DEFAULT_PORT,
        max_port: int = DEFAULT_MAX_PORT,
        host: Optional[str] = None
    ):
        self.capture_dir = capture_dir
        self.requested_port = port
        self.max_port = max(max_port, port)  # never allow an empty bind range
        self.host = host if host else get_local_ip()
        self.port = port
        self.httpd: Optional[_ThreadedHTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None
        self._is_running = False
        
        # Async disk saver
        self.async_saver = AsyncImageSaver(capture_dir=self.capture_dir)
        
        # In-memory caches for fast preview & serving
        self._latest_filename: Optional[str] = None
        self._memory_cache: Dict[str, np.ndarray] = {}
        self._qr_cache: Dict[str, np.ndarray] = {}
        self._lock = threading.Lock()

    def start(self) -> None:
        """
        Binds to an available port in range [requested_port, max_port] and starts
        the background daemon HTTP server.
        """
        if self._is_running:
            logger.info(f"DeliveryServer already running on http://{self.host}:{self.port}")
            return

        bound = False
        last_err = None
        
        for try_port in range(self.requested_port, self.max_port + 1):
            try:
                # Bind to 0.0.0.0 so external Wi-Fi clients can connect
                server_address = ("", try_port)
                self.httpd = _ThreadedHTTPServer(server_address, DeliveryHTTPRequestHandler)
                self.httpd.delivery_server = self
                self.port = try_port
                bound = True
                break
            except OSError as e:
                last_err = e
                logger.debug(f"Port {try_port} busy, trying {try_port + 1}...")

        if not bound:
            raise RuntimeError(
                f"Failed to bind DeliveryServer in port range {self.requested_port}-{self.max_port}: {last_err}"
            )

        self._is_running = True
        self._server_thread = threading.Thread(
            target=self.httpd.serve_forever,
            daemon=True,
            name="DeliveryHTTPServerThread"
        )
        self._server_thread.start()
        logger.info(f"DeliveryServer active at http://{self.host}:{self.port} (Serving '{self.capture_dir}')")

    def stop(self) -> None:
        """Shuts down the background HTTP server and persistence worker.

        Idempotent: always drains the async saver queue even if the HTTP
        server was never started, so no pending write can land on disk
        after stop() returns (prevents post-teardown file races).
        """
        first_call = self._is_running
        self._is_running = False

        if first_call:
            if self.httpd:
                self.httpd.shutdown()
                self.httpd.server_close()
                self.httpd = None

            if self._server_thread and self._server_thread.is_alive():
                self._server_thread.join(timeout=1.0)
                self._server_thread = None

        self.async_saver.stop()
        if first_call:
            logger.info("DeliveryServer stopped successfully.")

    def get_photo_url(self, filename: str) -> str:
        """Returns reachable LAN URL for mobile landing page."""
        return f"http://{self.host}:{self.port}/view/{filename}"

    def get_raw_photo_url(self, filename: str) -> str:
        """Returns reachable LAN URL for direct raw photo image."""
        return f"http://{self.host}:{self.port}/photo/{filename}"

    def get_latest_url(self) -> str:
        """Returns reachable LAN URL for latest photo shortcut."""
        return f"http://{self.host}:{self.port}/latest"

    def get_latest_filename(self) -> Optional[str]:
        """Returns the filename of the most recent photo capture."""
        with self._lock:
            if self._latest_filename:
                return self._latest_filename

        # Scan captures directory if not in memory
        if os.path.isdir(self.capture_dir):
            files = [
                f for f in os.listdir(self.capture_dir)
                if f.lower().endswith((".jpg", ".jpeg", ".png"))
            ]
            if files:
                files.sort(
                    key=lambda fn: os.path.getmtime(os.path.join(self.capture_dir, fn)),
                    reverse=True
                )
                return files[0]
        return None

    def save_photo_async(self, frame: np.ndarray, filter_name: str = "filter") -> str:
        """
        Asynchronously writes high-quality JPEG to disk.
        Returns the generated unique filename immediately so UI can construct the QR code.
        """
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        millis = now.strftime("%f")[:3]
        safe_filter = "".join(c for c in filter_name if c.isalnum() or c in ("-", "_")).lower()
        filename = f"capture_{timestamp}_{millis}_{safe_filter}.jpg"

        with self._lock:
            self._latest_filename = filename
            self._memory_cache[filename] = frame.copy()
            # Cap in-memory cache to last 5 frames to prevent memory growth
            if len(self._memory_cache) > 5:
                oldest_key = next(iter(self._memory_cache))
                del self._memory_cache[oldest_key]

        # Dispatch async disk write
        self.async_saver.save_async(frame, filename, quality=JPEG_QUALITY)
        return filename

    def save_photo_sync(self, frame: np.ndarray, filter_name: str = "filter") -> Tuple[str, str]:
        """
        Synchronously saves high-quality JPEG to disk.
        Returns (filename, absolute_filepath).
        """
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        millis = now.strftime("%f")[:3]
        safe_filter = "".join(c for c in filter_name if c.isalnum() or c in ("-", "_")).lower()
        filename = f"capture_{timestamp}_{millis}_{safe_filter}.jpg"

        filepath = self.async_saver.save_sync(frame, filename, quality=JPEG_QUALITY)
        with self._lock:
            self._latest_filename = filename
            self._memory_cache[filename] = frame.copy()

        return filename, filepath

    def get_qr_image(self, photo_filename: str, size: int = 150) -> np.ndarray:
        """
        Returns cached or newly generated QR code for the given photo filename.
        """
        cache_key = f"{photo_filename}_{size}"
        with self._lock:
            if cache_key in self._qr_cache:
                return self._qr_cache[cache_key]

        url = self.get_photo_url(photo_filename)
        qr_img = generate_qr_matrix(url, target_size=size, border=3)
        with self._lock:
            self._qr_cache[cache_key] = qr_img
        return qr_img

    def render_preview_card(
        self,
        display_frame: np.ndarray,
        photo_filename: str,
        remaining_seconds: float,
        total_seconds: float = DEFAULT_PREVIEW_DURATION
    ) -> np.ndarray:
        """
        Renders a sleek HUD preview card overlay with thumbnail, QR code, and countdown timer.
        """
        # Retrieve thumbnail frame from memory cache or disk
        thumb_frame = None
        with self._lock:
            if photo_filename in self._memory_cache:
                thumb_frame = self._memory_cache[photo_filename]

        return render_preview_card(
            display_frame=display_frame,
            photo_filename=photo_filename,
            remaining_seconds=remaining_seconds,
            total_seconds=total_seconds,
            host_url=self.get_photo_url(photo_filename),
            thumbnail=thumb_frame
        )

    def render_qr_card(
        self,
        display_frame: np.ndarray,
        photo_filename: str,
        remaining_seconds: float
    ) -> np.ndarray:
        """Interface contract alias for render_preview_card."""
        return self.render_preview_card(display_frame, photo_filename, remaining_seconds)


# ==============================================================================
# 7. HUD Preview Card Overlay Function
# ==============================================================================

def render_preview_card(
    display_frame: np.ndarray,
    photo_filename: str,
    remaining_seconds: float,
    total_seconds: float = DEFAULT_PREVIEW_DURATION,
    host_url: Optional[str] = None,
    thumbnail: Optional[np.ndarray] = None,
    capture_dir: str = DEFAULT_CAPTURE_DIR
) -> np.ndarray:
    """
    Overlays a modern, high-contrast HUD preview card onto `display_frame`.
    
    Components:
      - Translucent dark glassmorphism container
      - Scaled photo thumbnail with accent border
      - Pixel-sharp QR code encoding the download URL
      - Glowing status headline and scan instructions
      - Animated countdown progress bar and auto-dismiss timer
      - Local LAN URL text
    """
    if remaining_seconds <= 0:
        return display_frame

    frame_h, frame_w = display_frame.shape[:2]
    out = display_frame.copy()

    # Determine card sizing dynamically based on display resolution
    card_w = min(560, int(frame_w * 0.85))
    card_h = min(220, int(frame_h * 0.45))
    
    # Position card at bottom-center with safe margin
    card_x = (frame_w - card_w) // 2
    card_y = frame_h - card_h - 20
    
    x1, y1 = card_x, card_y
    x2, y2 = card_x + card_w, card_y + card_h

    # Ensure bounds within frame
    x1 = max(0, min(x1, frame_w - 1))
    y1 = max(0, min(y1, frame_h - 1))
    x2 = max(x1 + 10, min(x2, frame_w))
    y2 = max(y1 + 10, min(y2, frame_h))

    # Compute fade-out alpha when countdown nears 0
    base_alpha = 0.88
    if remaining_seconds < 0.5:
        alpha = float(np.clip(base_alpha * (remaining_seconds / 0.5), 0.0, base_alpha))
    else:
        alpha = base_alpha

    # 1. Draw Translucent Card Background
    overlay = out.copy()
    # Dark slate background
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (18, 24, 38), -1)
    # Bright cyan top accent stripe
    cv2.rectangle(overlay, (x1, y1), (x2, y1 + 4), (255, 200, 0), -1)
    # Card outline border
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (60, 75, 95), 2)
    
    # Blend background
    roi = out[y1:y2, x1:x2]
    overlay_roi = overlay[y1:y2, x1:x2]
    cv2.addWeighted(overlay_roi, alpha, roi, 1.0 - alpha, 0, roi)

    # 2. Render Thumbnail Preview
    thumb_w = int(card_h * 0.72)
    thumb_h = int(thumb_w * 0.75)
    thumb_x = x1 + 16
    thumb_y = y1 + 16

    if thumbnail is None:
        # Try loading from disk
        disk_path = os.path.join(capture_dir, photo_filename)
        if os.path.isfile(disk_path):
            thumbnail = cv2.imread(disk_path)

    if thumbnail is not None and thumbnail.size > 0:
        try:
            resized_thumb = cv2.resize(thumbnail, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
            # Thumbnail border
            cv2.rectangle(
                out,
                (thumb_x - 2, thumb_y - 2),
                (thumb_x + thumb_w + 2, thumb_y + thumb_h + 2),
                (0, 215, 255),
                1
            )
            out[thumb_y:thumb_y + thumb_h, thumb_x:thumb_x + thumb_w] = resized_thumb
        except Exception:
            pass
    else:
        # Placeholder box
        cv2.rectangle(out, (thumb_x, thumb_y), (thumb_x + thumb_w, thumb_y + thumb_h), (40, 50, 70), -1)
        cv2.putText(
            out, "SAVING...",
            (thumb_x + 10, thumb_y + thumb_h // 2),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1
        )

    # 3. Render Pixel-Sharp QR Code (100% opacity for scan reliability)
    qr_size = min(140, card_h - 40)
    qr_x = x2 - qr_size - 16
    qr_y = y1 + 16

    url_to_encode = host_url if host_url else f"http://{get_local_ip()}:{DEFAULT_PORT}/view/{photo_filename}"
    qr_img = generate_qr_matrix(url_to_encode, target_size=qr_size, border=3)

    if qr_img is not None and qr_img.shape[0] == qr_size:
        # Paste QR code directly onto frame
        out[qr_y:qr_y + qr_size, qr_x:qr_x + qr_size] = qr_img
        # Outer thin border around QR code
        cv2.rectangle(
            out,
            (qr_x - 1, qr_y - 1),
            (qr_x + qr_size + 1, qr_y + qr_size + 1),
            (100, 115, 135),
            1
        )

    # 4. Render Text & Instructions
    text_x = thumb_x + thumb_w + 16
    text_max_w = qr_x - text_x - 10

    # Title
    cv2.putText(
        out, "PHOTO SAVED!",
        (text_x, y1 + 32),
        cv2.FONT_HERSHEY_DUPLEX, 0.65, (0, 235, 255), 1, cv2.LINE_AA
    )

    # Scan Prompt
    cv2.putText(
        out, "Scan QR to Download",
        (text_x, y1 + 54),
        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (240, 240, 250), 1, cv2.LINE_AA
    )

    # Direct URL snippet
    short_url = url_to_encode
    if len(short_url) > 34:
        short_url = short_url[:31] + "..."
    cv2.putText(
        out, short_url,
        (text_x, y1 + 74),
        cv2.FONT_HERSHEY_SIMPLEX, 0.36, (140, 160, 180), 1, cv2.LINE_AA
    )

    # 5. Render Animated Countdown Progress Bar
    bar_x1 = text_x
    bar_w = text_max_w
    bar_y = y1 + 92
    bar_h = 8

    # Background track
    cv2.rectangle(out, (bar_x1, bar_y), (bar_x1 + bar_w, bar_y + bar_h), (35, 45, 60), -1)

    # Fill progress
    progress_ratio = float(np.clip(remaining_seconds / max(total_seconds, 0.1), 0.0, 1.0))
    fill_w = int(bar_w * progress_ratio)

    # Progress color shifts: Green -> Yellow -> Red as timer counts down
    if progress_ratio > 0.5:
        bar_color = (0, 230, 100) # Green
    elif progress_ratio > 0.25:
        bar_color = (0, 200, 255) # Yellow
    else:
        bar_color = (60, 60, 255)  # Red

    if fill_w > 0:
        cv2.rectangle(out, (bar_x1, bar_y), (bar_x1 + fill_w, bar_y + bar_h), bar_color, -1)

    # Auto-dismiss label
    cv2.putText(
        out, f"Auto-close in {remaining_seconds:.1f}s",
        (bar_x1, bar_y + 22),
        cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 190, 205), 1, cv2.LINE_AA
    )

    return out


# ==============================================================================
# 8. Standalone Self-Test Verification Suite
# ==============================================================================

def run_all_tests() -> bool:
    """
    Executes a comprehensive, rigorous self-test suite covering:
      1. LAN IP discovery
      2. Zero-dependency OpenCV QR generator and roundtrip decode
      3. Async image persistence and JPEG quality 95 validation
      4. Background HTTP daemon and automatic port hopping
      5. HTTP endpoints (/photo, /view, /latest, /health, /404, path traversal security)
      6. HUD preview card rendering & full-frame QR decoding
      7. Server clean lifecycle management
    """
    print("\n" + "=" * 70)
    print("  Smart Mirror Delivery Server & QR Subsystem Self-Test Suite")
    print("=" * 70)
    
    test_captures_dir = "test_tmp_captures"
    os.makedirs(test_captures_dir, exist_ok=True)
    all_passed = True
    start_total_time = time.time()

    def report(name: str, passed: bool, details: str = ""):
        nonlocal all_passed
        status = " [ PASS ] " if passed else " [ FAIL ] "
        print(f"{status:<10} | {name:<45} | {details}")
        if not passed:
            all_passed = False

    # --------------------------------------------------------------------------
    # Test 1: Dynamic LAN IP Discovery
    # --------------------------------------------------------------------------
    try:
        t0 = time.time()
        ip = get_local_ip()
        octets = ip.split(".")
        valid_ip = (len(octets) == 4 and all(o.isdigit() and 0 <= int(o) <= 255 for o in octets))
        dt = (time.time() - t0) * 1000
        report("Dynamic LAN IP Discovery", valid_ip, f"Discovered IP: {ip} ({dt:.1f}ms)")
    except Exception as e:
        report("Dynamic LAN IP Discovery", False, f"Exception: {e}")

    # --------------------------------------------------------------------------
    # Test 2: OpenCV QR Code Generator Roundtrip Decode
    # --------------------------------------------------------------------------
    try:
        t0 = time.time()
        test_url = "http://192.168.1.100:8000/view/capture_20260814_172000_portal.jpg"
        qr_bgr = generate_qr_matrix(test_url, target_size=200, border=4)
        
        # Verify matrix properties
        shape_ok = (qr_bgr.shape == (200, 200, 3) and qr_bgr.dtype == np.uint8)
        
        # Verify decoding with cv2.QRCodeDetector
        detector = cv2.QRCodeDetector()
        decoded_text, pts, _ = detector.detectAndDecode(qr_bgr)
        match_ok = (decoded_text == test_url)
        dt = (time.time() - t0) * 1000
        
        report(
            "OpenCV QR Code Generator & Decoder",
            shape_ok and match_ok,
            f"Shape: {qr_bgr.shape}, Decoded: '{decoded_text[:28]}...' ({dt:.1f}ms)"
        )
    except Exception as e:
        report("OpenCV QR Code Generator & Decoder", False, f"Exception: {e}")

    # --------------------------------------------------------------------------
    # Test 3: QR Fallback Generator Integrity
    # --------------------------------------------------------------------------
    try:
        t0 = time.time()
        fallback_qr = _generate_qr_fallback("http://127.0.0.1:8000/latest", target_size=180, border=3)
        shape_ok = (fallback_qr.shape == (180, 180, 3) and fallback_qr.dtype == np.uint8)
        dt = (time.time() - t0) * 1000
        report("QR Fallback Generator Matrix", shape_ok, f"Shape: {fallback_qr.shape} ({dt:.1f}ms)")
    except Exception as e:
        report("QR Fallback Generator Matrix", False, f"Exception: {e}")

    # --------------------------------------------------------------------------
    # Test 4: Async High-Resolution Image Persistence (JPEG Q=95)
    # --------------------------------------------------------------------------
    saver = None
    try:
        t0 = time.time()
        saver = AsyncImageSaver(capture_dir=test_captures_dir)
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Draw distinctive visual content
        cv2.circle(dummy_frame, (320, 240), 100, (0, 255, 128), -1)
        cv2.putText(dummy_frame, "TEST PHOTO", (200, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

        saved_path = saver.save_async(dummy_frame, "test_async_save.jpg", quality=95)
        
        # Wait up to 1.5s for async disk write
        file_written = False
        for _ in range(15):
            if os.path.isfile(saved_path) and os.path.getsize(saved_path) > 0:
                file_written = True
                break
            time.sleep(0.1)

        # Validate loaded image
        read_back = cv2.imread(saved_path)
        img_ok = (read_back is not None and read_back.shape == (480, 640, 3))
        dt = (time.time() - t0) * 1000

        report(
            "Async Image Persistence (JPEG Q=95)",
            file_written and img_ok,
            f"Wrote {os.path.getsize(saved_path)} bytes ({dt:.1f}ms)"
        )
    except Exception as e:
        report("Async Image Persistence (JPEG Q=95)", False, f"Exception: {e}")
    finally:
        if saver:
            saver.stop()

    # --------------------------------------------------------------------------
    # Test 5: Server Port Hopping Simulation
    # --------------------------------------------------------------------------
    dummy_sock = None
    srv = None
    try:
        t0 = time.time()
        # Bind a dummy socket to port 8000 to force port collision
        dummy_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        dummy_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        dummy_sock.bind(("0.0.0.0", 8000))
        dummy_sock.listen(1)

        # Start DeliveryServer requesting port 8000; should hop to 8001
        srv = DeliveryServer(capture_dir=test_captures_dir, port=8000, max_port=8005, host="127.0.0.1")
        srv.start()
        
        hopped_ok = (srv.port == 8001)
        dt = (time.time() - t0) * 1000
        report(
            "Server Automatic Port Hopping",
            hopped_ok,
            f"Blocked 8000 -> Bound to {srv.port} ({dt:.1f}ms)"
        )
    except Exception as e:
        report("Server Automatic Port Hopping", False, f"Exception: {e}")
    finally:
        if srv:
            srv.stop()
        if dummy_sock:
            dummy_sock.close()

    # --------------------------------------------------------------------------
    # Test 6: HTTP Endpoints Verification (/photo, /view, /latest, /health, security)
    # --------------------------------------------------------------------------
    server = None
    try:
        t0 = time.time()
        server = DeliveryServer(capture_dir=test_captures_dir, port=8000, host="127.0.0.1")
        server.start()
        base_url = f"http://127.0.0.1:{server.port}"

        # 1. Create a known test photo
        test_photo_frame = np.full((360, 480, 3), 120, dtype=np.uint8)
        cv2.circle(test_photo_frame, (240, 180), 60, (0, 0, 255), -1)
        test_filename, _ = server.save_photo_sync(test_photo_frame, filter_name="portal")

        # 2. Test GET /photo/<filename>
        photo_req_url = f"{base_url}/photo/{test_filename}"
        with urllib.request.urlopen(photo_req_url, timeout=2.0) as resp:
            photo_status = resp.status
            photo_type = resp.headers.get("Content-Type", "")
            photo_data = resp.read()
            photo_ok = (photo_status == 200 and "image/jpeg" in photo_type and len(photo_data) > 0)

        # 3. Test GET /view/<filename>
        view_req_url = f"{base_url}/view/{test_filename}"
        with urllib.request.urlopen(view_req_url, timeout=2.0) as resp:
            view_status = resp.status
            view_html = resp.read().decode("utf-8")
            view_ok = (
                view_status == 200 and
                "Your Smart Mirror Photo" in view_html and
                f"/photo/{test_filename}" in view_html and
                "Save Photo to Phone" in view_html and
                "navigator.share" in view_html
            )

        # 4. Test GET /latest (redirects to view)
        latest_req_url = f"{base_url}/latest"
        req = urllib.request.Request(latest_req_url)
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            latest_ok = (resp.status == 200 and f"/photo/{test_filename}" in resp.read().decode("utf-8"))

        # 5. Test GET /health
        health_url = f"{base_url}/health"
        with urllib.request.urlopen(health_url, timeout=2.0) as resp:
            health_ok = (resp.status == 200 and "online" in resp.read().decode("utf-8"))

        # 6. Test GET /photo/<missing> -> 404
        missing_404_ok = False
        try:
            urllib.request.urlopen(f"{base_url}/photo/non_existent_file.jpg", timeout=2.0)
        except urllib.error.HTTPError as e:
            missing_404_ok = (e.code == 404)

        # 7. Test Directory Traversal Protection -> 403 Forbidden
        traversal_blocked = False
        try:
            urllib.request.urlopen(f"{base_url}/photo/../filters.py", timeout=2.0)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            traversal_blocked = True

        all_endpoints_ok = (
            photo_ok and view_ok and latest_ok and health_ok and missing_404_ok and traversal_blocked
        )
        dt = (time.time() - t0) * 1000

        report(
            "HTTP Endpoints & Security Checks",
            all_endpoints_ok,
            f"Photo(200), View(200), Latest(302->200), Health(200), 404 & Traversal safe ({dt:.1f}ms)"
        )
    except Exception as e:
        report("HTTP Endpoints & Security Checks", False, f"Exception: {e}")
    finally:
        if server:
            server.stop()

    # --------------------------------------------------------------------------
    # Test 7: HUD Preview Card Rendering & Full-Frame QR Detection
    # --------------------------------------------------------------------------
    try:
        t0 = time.time()
        # Create a realistic composite mirror frame (1280x720)
        mirror_frame = np.full((720, 1280, 3), (25, 25, 25), dtype=np.uint8)
        # Background gradient & features
        for y in range(720):
            mirror_frame[y, :] = (int(20 + y * 0.05), int(25 + y * 0.05), int(35 + y * 0.05))

        test_card_filename = "capture_20260814_172000_000_grid.jpg"
        test_url = f"http://192.168.1.50:8000/view/{test_card_filename}"

        # Render preview card overlay
        rendered_composite = render_preview_card(
            display_frame=mirror_frame,
            photo_filename=test_card_filename,
            remaining_seconds=4.5,
            total_seconds=6.0,
            host_url=test_url
        )

        # Assertions on output
        shape_ok = (rendered_composite.shape == (720, 1280, 3) and rendered_composite.dtype == np.uint8)

        # Detect QR code directly from the composite display frame
        detector = cv2.QRCodeDetector()
        decoded_from_frame, pts, _ = detector.detectAndDecode(rendered_composite)
        qr_detected_ok = (decoded_from_frame == test_url)
        dt = (time.time() - t0) * 1000

        report(
            "HUD Preview Card & Full-Frame QR Decode",
            shape_ok and qr_detected_ok,
            f"Decoded from 1280x720 composite: '{decoded_from_frame[:32]}...' ({dt:.1f}ms)"
        )
    except Exception as e:
        report("HUD Preview Card & Full-Frame QR Decode", False, f"Exception: {e}")

    # --------------------------------------------------------------------------
    # Test 8: Preview Card Smooth Fade-Out at Expiry
    # --------------------------------------------------------------------------
    try:
        t0 = time.time()
        base_frame = np.full((480, 640, 3), 50, dtype=np.uint8)
        # Expired timer remaining_seconds = 0.0 should return base frame unmodified
        f_expired = render_preview_card(base_frame, "test.jpg", remaining_seconds=0.0)
        expired_ok = np.array_equal(f_expired, base_frame)

        # Low timer remaining_seconds = 0.2 should produce faded overlay
        f_fading = render_preview_card(base_frame, "test.jpg", remaining_seconds=0.2)
        fading_ok = not np.array_equal(f_fading, base_frame)
        dt = (time.time() - t0) * 1000

        report(
            "Preview Card Auto-Dismiss & Fade Logic",
            expired_ok and fading_ok,
            f"0.0s dismissed: {expired_ok}, 0.2s fading: {fading_ok} ({dt:.1f}ms)"
        )
    except Exception as e:
        report("Preview Card Auto-Dismiss & Fade Logic", False, f"Exception: {e}")

    # --------------------------------------------------------------------------
    # Test 9: Complete DeliveryServer Lifecycle & Interface Contract Compliance
    # --------------------------------------------------------------------------
    try:
        t0 = time.time()
        srv_contract = DeliveryServer(capture_dir=test_captures_dir, port=8010, host="127.0.0.1")
        srv_contract.start()

        # Check PROJECT.md contract methods exist
        has_start = hasattr(srv_contract, "start")
        has_stop = hasattr(srv_contract, "stop")
        has_photo_url = hasattr(srv_contract, "get_photo_url")
        has_save_async = hasattr(srv_contract, "save_photo_async")
        has_render_qr = hasattr(srv_contract, "render_qr_card")

        # Execute contract calls
        test_frame = np.full((480, 640, 3), (100, 150, 200), dtype=np.uint8)
        fn = srv_contract.save_photo_async(test_frame, "filter")
        url = srv_contract.get_photo_url(fn)
        card_out = srv_contract.render_qr_card(test_frame, fn, 5.0)

        contract_calls_ok = (
            isinstance(fn, str) and fn.startswith("capture_") and
            isinstance(url, str) and fn in url and
            isinstance(card_out, np.ndarray) and card_out.shape == (480, 640, 3)
        )
        srv_contract.stop()

        dt = (time.time() - t0) * 1000
        all_contract_ok = (has_start and has_stop and has_photo_url and has_save_async and has_render_qr and contract_calls_ok)
        report(
            "Interface Contract Compliance (PROJECT.md)",
            all_contract_ok,
            f"Methods verified, async save & card render OK ({dt:.1f}ms)"
        )
    except Exception as e:
        report("Interface Contract Compliance (PROJECT.md)", False, f"Exception: {e}")

    # Clean up test captures
    try:
        import shutil
        if os.path.exists(test_captures_dir):
            shutil.rmtree(test_captures_dir, ignore_errors=True)
    except Exception:
        pass

    total_time = (time.time() - start_total_time) * 1000
    print("-" * 70)
    print(f"Summary: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'} in {total_time:.1f}ms")
    print("=" * 70 + "\n")
    return all_passed


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
