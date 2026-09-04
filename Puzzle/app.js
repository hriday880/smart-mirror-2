import {
  FilesetResolver,
  HandLandmarker,
} from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";

const LM = {
  WRIST: 0,
  THUMB_TIP: 4,
  INDEX_MCP: 5,
  INDEX_TIP: 8,
  MIDDLE_TIP: 12,
  RING_TIP: 16,
  PINKY_TIP: 20,
  MIDDLE_MCP: 9,
  RING_MCP: 13,
  PINKY_MCP: 17,
};

const PINCH_THRESHOLD = 0.055;
const FRAME_PADDING = 28;
const FREEZE_HOLD_MS = 400;
const COUNTDOWN_SECONDS = 3;
const FIST_HOLD_FRAMES = 15;
const DISCARD_HOLD_FRAMES = 45; // 1.5 seconds for destructive action
const IDLE_RESET_MS = 45000;
let idleTimer = null;

function resetIdleTimer() {
  if (idleTimer) clearTimeout(idleTimer);
  idleTimer = setTimeout(() => {
    if (appState !== "tracking") {
      statusText.textContent = "reset due to inactivity";
      resetEverything();
    }
  }, IDLE_RESET_MS);
}
const SNAP_DISTANCE_RATIO = 0.45;
const GRID = 3;
const LOAD_TIMEOUT_MS = 20000;

const PHOTOBOOTH_CONTRAST_ALPHA = 1.3;
const PHOTOBOOTH_BRIGHTNESS_BETA = 10;
const PHOTOBOOTH_NOISE_STD = 15;

const HAND_CONNECTIONS = [
  [0, 1], [1, 2], [2, 3], [3, 4],
  [0, 5], [5, 6], [6, 7], [7, 8],
  [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16],
  [13, 17], [17, 18], [18, 19], [19, 20],
  [0, 17],
];

const videoEl = document.getElementById("webcam");
const canvas = document.getElementById("sceneCanvas");
const ctx = canvas.getContext("2d", { willReadFrequently: true });

const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const loadingOverlay = document.getElementById("loadingOverlay");
const loaderText = document.getElementById("loaderText");
const loaderRetry = document.getElementById("loaderRetry");
const errorBanner = document.getElementById("errorBanner");
const progressBadge = document.getElementById("progressBadge");
const progressText = document.getElementById("progressText");

const qrOverlay = document.getElementById("qrOverlay");
const qrcodeCanvas = document.getElementById("qrcodeCanvas");
const qrCountdown = document.getElementById("qrCountdown");


let appState = "tracking";
let qrCountdownInterval = null;

const puzzle = {
  boardBox: null,
  pieces: [],
  solved: false,
  tileW: 0,
  tileH: 0,
};



// Waits up to ~3s for the QRCode global (local script or CDN fallback).
function waitForQrLibrary(maxMs = 3000) {
  if (typeof QRCode !== "undefined") return Promise.resolve(true);
  return new Promise((resolve) => {
    const startedAt = Date.now();
    const poll = setInterval(() => {
      if (typeof QRCode !== "undefined") {
        clearInterval(poll);
        resolve(true);
      } else if (Date.now() - startedAt > maxMs) {
        clearInterval(poll);
        resolve(false);
      }
    }, 100);
  });
}

// ---------------------------------------------------------------------------
// Save pipeline: upload photo -> ask server for LAN IP + port -> show QR.
// Each step reports a precise error message so failures are debuggable.
// ---------------------------------------------------------------------------
let serverPort = null; // discovered once from /api/ip

async function uploadPhoto(base64Data) {
  const res = await fetch("/api/upload", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ image: base64Data })
  });
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).error || ""; } catch (_e) { /* ignore */ }
    throw new Error(`Server rejected upload (HTTP ${res.status})${detail ? ": " + detail : ""}`);
  }
  const data = await res.json();
  if (!data.filename) throw new Error("Server response missing filename");
  return data.filename;
}

async function saveAndShowQR(snapshotCanvas, solvedTimeSec = null) {
  // 1. Prepare final image (add solve-time caption if provided)
  const finalCanvas = document.createElement("canvas");
  finalCanvas.width = snapshotCanvas.width;
  finalCanvas.height = snapshotCanvas.height;
  const fCtx = finalCanvas.getContext("2d");
  fCtx.drawImage(snapshotCanvas, 0, 0);

  if (solvedTimeSec !== null) {
    fCtx.save();
    fCtx.fillStyle = "rgba(0,0,0,0.6)";
    fCtx.fillRect(0, finalCanvas.height - 45, finalCanvas.width, 45);
    fCtx.fillStyle = "#fff";
    fCtx.font = "bold 26px sans-serif";
    fCtx.textAlign = "center";
    fCtx.fillText(`Solved in ${solvedTimeSec}s!`, finalCanvas.width / 2, finalCanvas.height - 14);
    fCtx.restore();
  }

  // Guard: QRCode library must be present. Give the fallback CDN script a
  // short window to arrive before declaring failure.
  if (!(await waitForQrLibrary())) {
    failSave("QR library failed to load - reload the page (an internet connection is needed once for the model anyway).");
    return;
  }

  appState = "saving";
  statusText.textContent = "saving your puzzle���";

  try {
    // 2. Discover LAN IP + real port from the server itself (no hardcoding)
    let ip = null, port = null;
    try {
      const ipRes = await fetch("/api/ip");
      if (!ipRes.ok) throw new Error(`HTTP ${ipRes.status}`);
      const info = await ipRes.json();
      ip = info.ip || null;
      port = info.port || null;
    } catch (_e) {
      // /api/ip unavailable -> still try the upload on same-origin
    }

    // 3. Upload
    const base64Data = finalCanvas.toDataURL("image/png");
    const filename = await uploadPhoto(base64Data);

    // Remember the actual serving port for future saves
    if (port) serverPort = port;

    // 4. Build the phone-facing URL:
    //    prefer server-reported IP+port; fall back to current origin.
    let url;
    if (ip && port) {
      url = `http://${ip}:${port}/view/${filename}`;
    } else {
      url = `${window.location.origin}/view/${filename}`;
    }

    // 5. Generate QR code (guarded above, but stay defensive)
    qrcodeCanvas.innerHTML = "";
    new QRCode(qrcodeCanvas, {
      text: url,
      width: 200,
      height: 200,
      colorDark: "#090d16",
      colorLight: "#ffffff",
      correctLevel: QRCode.CorrectLevel.H
    });

    // 6. Show QR overlay with countdown, then reset to tracking
    qrOverlay.classList.remove("hidden");
    let timeLeft = 10;
    qrCountdown.textContent = timeLeft;

    if (qrCountdownInterval) clearInterval(qrCountdownInterval);
    qrCountdownInterval = setInterval(() => {
      timeLeft--;
      if (timeLeft <= 0) {
        clearInterval(qrCountdownInterval);
        qrCountdownInterval = null;
        qrOverlay.classList.add("hidden");
        resetPuzzleOnly();
        appState = "tracking";
        statusText.textContent = "tracking ready";
      } else {
        qrCountdown.textContent = timeLeft;
      }
    }, 1000);

  } catch (err) {
    console.error("[PuzzleCam] save failed:", err);
    let msg = err?.message || "Unknown error";
    if (err instanceof TypeError && /fetch/i.test(msg)) {
      msg = "Cannot reach the local server. Is 'Start Puzzle Cam.command' still running?";
    }
    failSave(msg);
  }
}

function failSave(message) {
  errorBanner.textContent = `Save failed: ${message}`;
  errorBanner.style.display = "block";
  setTimeout(() => { errorBanner.style.display = "none"; }, 6000);
  resetPuzzleOnly();
  statusText.textContent = "tracking ready";
}

function resetEverything() {
  resetPuzzleOnly();
  statusText.textContent = "all reset";
}


function resetPuzzleOnly() {
  puzzle.boardBox = null;
  puzzle.pieces = [];
  puzzle.solved = false;
  puzzle.fullPhotoboothCanvas = null;
  appState = "tracking";
  countdown.active = false;
  drag.activeHand = null;
  drag.piece = null;
  fistHoldCounter = 0;
  openHandHoldCounter = 0;
  lastSeenFrame.box = null;
  lastSeenFrame.at = 0;
  updateProgressBadge();
}

function fitCanvasToWindow() {
  const stageEl = document.getElementById("stage");
  const vw = stageEl.clientWidth;
  const vh = stageEl.clientHeight;
  const videoAspect = canvas.width / canvas.height;
  const containerAspect = vw / vh;

  let cssWidth, cssHeight;
  if (containerAspect > videoAspect) {
    cssWidth = vw;
    cssHeight = vw / videoAspect;
  } else {
    cssHeight = vh;
    cssWidth = vh * videoAspect;
  }

  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${cssHeight}px`;
}

window.addEventListener("resize", fitCanvasToWindow);

async function initWebcam() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("This browser does not support getUserMedia.");
  }
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
    audio: false,
  });
  videoEl.srcObject = stream;

  await new Promise((resolve) => {
    videoEl.onloadedmetadata = () => {
      videoEl.play();
      resolve();
    };
  });

  canvas.width = videoEl.videoWidth;
  canvas.height = videoEl.videoHeight;
  fitCanvasToWindow();
}

function withTimeout(promise, ms, timeoutMessage) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(timeoutMessage)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

async function initHandLandmarker() {
  let vision;
  try {
    vision = await withTimeout(
      FilesetResolver.forVisionTasks(
        "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm"
      ),
      LOAD_TIMEOUT_MS,
      "Timeout loading MediaPipe runtime (WASM). Check your internet connection or if cdn.jsdelivr.net is blocked."
    );
  } catch (err) {
    throw err;
  }

  try {
    const handLandmarker = await withTimeout(
      HandLandmarker.createFromOptions(vision, {
        baseOptions: {
          modelAssetPath:
            "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
          delegate: "CPU",
        },
        runningMode: "video",
        numHands: 2,
        minHandDetectionConfidence: 0.8,
        minHandPresenceConfidence: 0.8,
        minTrackingConfidence: 0.8,
      }),
      LOAD_TIMEOUT_MS,
      "Timeout downloading HandLandmarker model (~10MB) with GPU."
    );
    return handLandmarker;
  } catch (gpuErr) {
    console.warn("[PuzzleCam] Failed with GPU delegate, retrying with CPU…", gpuErr);
  }

  try {
    const handLandmarker = await withTimeout(
      HandLandmarker.createFromOptions(vision, {
        baseOptions: {
          modelAssetPath:
            "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
          delegate: "CPU",
        },
        runningMode: "video",
        numHands: 2,
        minHandDetectionConfidence: 0.8,
        minHandPresenceConfidence: 0.8,
        minTrackingConfidence: 0.8,
      }),
      LOAD_TIMEOUT_MS,
      "Timeout downloading HandLandmarker model (~10MB) even with CPU. Check your connection or if storage.googleapis.com is blocked on your network."
    );
    return handLandmarker;
  } catch (cpuErr) {
    throw cpuErr;
  }
}

function dist2D(a, b) {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return Math.sqrt(dx * dx + dy * dy);
}

function isPinching(landmarks) {
  const scale = dist2D(landmarks[LM.WRIST], landmarks[LM.INDEX_MCP]) || 0.1;
  const pinchDist = dist2D(landmarks[LM.THUMB_TIP], landmarks[LM.INDEX_TIP]);
  return (pinchDist / scale) < 0.35;
}

function isFist(landmarks) {
  const wrist = landmarks[LM.WRIST];
  const pairs = [
    [LM.INDEX_TIP, LM.INDEX_MCP],
    [LM.MIDDLE_TIP, LM.MIDDLE_MCP],
    [LM.RING_TIP, LM.RING_MCP],
    [LM.PINKY_TIP, LM.PINKY_MCP],
  ];
  let curled = 0;
  for (const [tipIdx, mcpIdx] of pairs) {
    if (dist2D(landmarks[tipIdx], wrist) < dist2D(landmarks[mcpIdx], wrist)) curled++;
  }
  return curled >= 4;
}

function isOpenHand(landmarks) {
  const wrist = landmarks[LM.WRIST];
  const pairs = [
    [LM.INDEX_TIP, LM.INDEX_MCP],
    [LM.MIDDLE_TIP, LM.MIDDLE_MCP],
    [LM.RING_TIP, LM.RING_MCP],
    [LM.PINKY_TIP, LM.PINKY_MCP],
  ];
  let extended = 0;
  for (const [tipIdx, mcpIdx] of pairs) {
    if (dist2D(landmarks[tipIdx], wrist) > dist2D(landmarks[mcpIdx], wrist)) extended++;
  }
  return extended >= 4;
}

function toPixel(landmarkNorm) {
  return { x: landmarkNorm.x * canvas.width, y: landmarkNorm.y * canvas.height };
}

function mirrorLandmarkX(landmark) {
  return { x: 1 - landmark.x, y: landmark.y };
}

function computeHandFrame(indexTipA, indexTipB) {
  const a = toPixel(indexTipA);
  const b = toPixel(indexTipB);

  const minX = Math.min(a.x, b.x) - FRAME_PADDING;
  const maxX = Math.max(a.x, b.x) + FRAME_PADDING;
  const minY = Math.min(a.y, b.y) - FRAME_PADDING;
  const maxY = Math.max(a.y, b.y) + FRAME_PADDING;

  const x = Math.max(0, minX);
  const y = Math.max(0, minY);
  const width = Math.min(canvas.width, maxX) - x;
  const height = Math.min(canvas.height, maxY) - y;

  return { x, y, width, height };
}

const freezeGate = { holding: false, since: 0 };

const FRAME_GRACE_MS = 450;
const lastSeenFrame = { box: null, at: 0 };

const countdown = {
  active: false,
  startedAt: 0,
};

function startCountdown(frameBox) {
  puzzle.boardBox = { ...frameBox };
  appState = "countdown";
  countdown.active = true;
  countdown.startedAt = performance.now();
}

function drawCountdownOverlay(box) {
  const elapsed = (performance.now() - countdown.startedAt) / 1000;
  const remaining = COUNTDOWN_SECONDS - elapsed;

  if (remaining <= 0) {
    finishCountdownAndCapture(box);
    return;
  }

  applyBWInsideBox(box);

  ctx.save();
  ctx.strokeStyle = "#f5c518";
  ctx.lineWidth = 3;
  ctx.strokeRect(box.x, box.y, box.width, box.height);

  const n = Math.ceil(remaining);
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;

  ctx.fillStyle = "rgba(10,10,8,0.45)";
  ctx.fillRect(box.x, box.y, box.width, box.height);

  ctx.font = `${Math.max(48, Math.min(box.width, box.height) * 0.4)}px 'IBM Plex Mono', monospace`;
  ctx.fillStyle = "#f5c518";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(String(n), cx, cy);
  ctx.restore();

  statusText.textContent = `capturing in ${n}…`;
}

function gaussianNoise(std) {
  const u1 = Math.random() || 1e-6;
  const u2 = Math.random();
  const z0 = Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
  return z0 * std;
}

function applyPhotoboothEffect(imageData) {
  const d = imageData.data;
  for (let i = 0; i < d.length; i += 4) {
    const gray = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
    let v = gray * PHOTOBOOTH_CONTRAST_ALPHA + PHOTOBOOTH_BRIGHTNESS_BETA;
    v += gaussianNoise(PHOTOBOOTH_NOISE_STD);
    v = Math.max(0, Math.min(255, v));
    d[i] = d[i + 1] = d[i + 2] = v;
  }
  return imageData;
}

function shuffle(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

function finishCountdownAndCapture(box) {
  countdown.active = false;

  const mirroredFrame = document.createElement("canvas");
  mirroredFrame.width = canvas.width;
  mirroredFrame.height = canvas.height;
  const mirroredCtx = mirroredFrame.getContext("2d");
  mirroredCtx.save();
  mirroredCtx.translate(mirroredFrame.width, 0);
  mirroredCtx.scale(-1, 1);
  mirroredCtx.drawImage(videoEl, 0, 0, mirroredFrame.width, mirroredFrame.height);
  mirroredCtx.restore();

  const cropCanvas = document.createElement("canvas");
  cropCanvas.width = Math.max(1, Math.round(box.width));
  cropCanvas.height = Math.max(1, Math.round(box.height));
  const cropCtx = cropCanvas.getContext("2d");
  cropCtx.drawImage(
    mirroredFrame,
    box.x, box.y, box.width, box.height,
    0, 0, cropCanvas.width, cropCanvas.height
  );

  const fullImageData = cropCtx.getImageData(0, 0, cropCanvas.width, cropCanvas.height);
  applyPhotoboothEffect(fullImageData);
  cropCtx.putImageData(fullImageData, 0, 0);

  puzzle.fullPhotoboothCanvas = cropCanvas;

  const tileW = Math.floor(cropCanvas.width / GRID);
  const tileH = Math.floor(cropCanvas.height / GRID);
  const pieces = [];

  for (let row = 0; row < GRID; row++) {
    for (let col = 0; col < GRID; col++) {
      const sx = col * tileW;
      const sy = row * tileH;
      const w = col === GRID - 1 ? cropCanvas.width - sx : tileW;
      const h = row === GRID - 1 ? cropCanvas.height - sy : tileH;

      const pieceCanvas = document.createElement("canvas");
      pieceCanvas.width = w;
      pieceCanvas.height = h;
      pieceCanvas.getContext("2d").drawImage(cropCanvas, sx, sy, w, h, 0, 0, w, h);

      pieces.push({
        row, col,
        canvas: pieceCanvas,
        w, h,
        x: 0, y: 0,
        placed: false,
        dragging: false,
      });
    }
  }

  const slots = [];
  for (let row = 0; row < GRID; row++) {
    for (let col = 0; col < GRID; col++) {
      slots.push({ x: box.x + col * tileW, y: box.y + row * tileH });
    }
  }
  shuffle(slots);

  pieces.forEach((piece, i) => {
    piece.x = slots[i].x;
    piece.y = slots[i].y;
    if (isNearOwnCell(piece, box, tileW, tileH)) {
      snapPieceToCell(piece, box, tileW, tileH);
    }
  });

  puzzle.boardBox = box;
  puzzle.pieces = pieces;
  puzzle.tileW = tileW;
  puzzle.tileH = tileH;
  puzzle.solved = pieces.every((p) => p.placed);
  puzzle.startTime = performance.now();
  puzzle.solveTime = 0;
  appState = "puzzle";
  fistHoldCounter = 0;
  openHandHoldCounter = 0;
  updateProgressBadge();
}

const drag = {
  activeHand: null,
  piece: null,
  offsetX: 0,
  offsetY: 0,
};

function isNearOwnCell(piece, box, tileW, tileH) {
  const correctX = box.x + piece.col * tileW;
  const correctY = box.y + piece.row * tileH;
  const dx = piece.x - correctX;
  const dy = piece.y - correctY;
  const tolerance = Math.min(tileW, tileH) * SNAP_DISTANCE_RATIO;
  return Math.sqrt(dx * dx + dy * dy) < tolerance;
}

function reconcilePlacedState(box, tileW, tileH) {
  if (!box || !puzzle.pieces.length) return false;
  for (const piece of puzzle.pieces) {
    if (piece.displacing || piece.dragging) continue;
    piece.placed = isNearOwnCell(piece, box, tileW, tileH);
  }
  return puzzle.pieces.every((p) => p.placed);
}

function snapPieceToCell(piece, box, tileW, tileH) {
  displaceCellOccupant(piece, piece.row, piece.col, box, tileW, tileH);
  piece.x = box.x + piece.col * tileW;
  piece.y = box.y + piece.row * tileH;
  piece.placed = true;
}

function displaceCellOccupant(piece, targetRow, targetCol, box, tileW, tileH) {
  const cellX = box.x + targetCol * tileW;
  const cellY = box.y + targetRow * tileH;

  const occupant = puzzle.pieces.find((p) => {
    if (p === piece) return false;
    let px = p.x;
    let py = p.y;
    if (p.displacing && p.displaceTargetX !== undefined) {
      px = p.displaceTargetX;
      py = p.displaceTargetY;
    }
    const cx = px + p.w / 2;
    const cy = py + p.h / 2;
    const col = Math.floor((cx - box.x) / tileW);
    const row = Math.floor((cy - box.y) / tileH);
    return col === targetCol && row === targetRow;
  });
  if (!occupant) return;

  if (occupant.row === targetRow && occupant.col === targetCol && occupant.placed) {
    return;
  }

  occupant.placed = false;

  const freeCells = [];
  for (let row = 0; row < GRID; row++) {
    for (let col = 0; col < GRID; col++) {
      if (row === targetRow && col === targetCol) continue;
      const cx0 = box.x + col * tileW;
      const cy0 = box.y + row * tileH;
      const taken = puzzle.pieces.some((p) => {
        if (p === occupant || p === piece) return false;
        let px = p.x;
        let py = p.y;
        if (p.displacing && p.displaceTargetX !== undefined) {
          px = p.displaceTargetX;
          py = p.displaceTargetY;
        }
        const cx = px + p.w / 2;
        const cy = py + p.h / 2;
        const cCol = Math.floor((cx - box.x) / tileW);
        const cRow = Math.floor((cy - box.y) / tileH);
        return cCol === col && cRow === row;
      });
      if (!taken) freeCells.push({ row, col });
    }
  }

  let targetSlot;
  if (freeCells.length > 0) {
    targetSlot = freeCells[Math.floor(Math.random() * freeCells.length)];
  } else {
    targetSlot = { row: occupant.row, col: occupant.col };
  }

  const targetX = box.x + targetSlot.col * tileW;
  const targetY = box.y + targetSlot.row * tileH;

  animateDisplacement(occupant, targetX, targetY, box);
}

const DISPLACE_ANIM_MS = 220;

function animateDisplacement(piece, targetX, targetY, box) {
  piece.displaceTargetX = targetX;
  piece.displaceTargetY = targetY;
  const startX = piece.x;
  const startY = piece.y;
  const startedAt = performance.now();
  
  piece.displacing = true;
  const animId = Math.random();
  piece.animId = animId;

  function step() {
    if (piece.animId !== animId) return;
    const t = Math.min(1, (performance.now() - startedAt) / DISPLACE_ANIM_MS);
    const eased = 1 - Math.pow(1 - t, 3);

    piece.x = startX + (targetX - startX) * eased;
    piece.y = startY + (targetY - startY) * eased;

    if (t < 1) {
      requestAnimationFrame(step);
    } else {
      piece.x = targetX;
      piece.y = targetY;
      piece.displacing = false;
    }
  }

  requestAnimationFrame(step);
}

function findNearestPiece(px, py) {
  let best = null;
  let bestDist = Infinity;
  for (const piece of puzzle.pieces) {
    if (piece.displacing) continue;
    const cx = piece.x + piece.w / 2;
    const cy = piece.y + piece.h / 2;
    const d = Math.hypot(px - cx, py - cy);
    if (d < Math.max(piece.w, piece.h) * 0.75 && d < bestDist) {
      best = piece;
      bestDist = d;
    }
  }
  return best;
}

function handleDragForHand(handLabel, pinching, indexPx) {
  if (pinching) {
    if (drag.activeHand === null) {
      const candidate = findNearestPiece(indexPx.x, indexPx.y);
      if (candidate) {
        drag.activeHand = handLabel;
        drag.piece = candidate;
        drag.offsetX = indexPx.x - candidate.x;
        drag.offsetY = indexPx.y - candidate.y;
        candidate.dragging = true;
        candidate.placed = false;
      }
    } else if (drag.activeHand === handLabel && drag.piece) {
      drag.piece.x = indexPx.x - drag.offsetX;
      drag.piece.y = indexPx.y - drag.offsetY;
    }
  } else {
    if (drag.activeHand === handLabel && drag.piece) {
      const piece = drag.piece;
      piece.dragging = false;
      if (isNearOwnCell(piece, puzzle.boardBox, puzzle.tileW, puzzle.tileH)) {
        snapPieceToCell(piece, puzzle.boardBox, puzzle.tileW, puzzle.tileH);
      } else {
        const box = puzzle.boardBox;
        const cx = piece.x + piece.w / 2;
        const cy = piece.y + piece.h / 2;
        const dropCol = Math.min(
          GRID - 1,
          Math.max(0, Math.floor((cx - box.x) / puzzle.tileW))
        );
        const dropRow = Math.min(
          GRID - 1,
          Math.max(0, Math.floor((cy - box.y) / puzzle.tileH))
        );
        displaceCellOccupant(piece, dropRow, dropCol, box, puzzle.tileW, puzzle.tileH);
        
        piece.x = box.x + dropCol * puzzle.tileW;
        piece.y = box.y + dropRow * puzzle.tileH;
      }
      drag.activeHand = null;
      drag.piece = null;
      puzzle.solved = reconcilePlacedState(puzzle.boardBox, puzzle.tileW, puzzle.tileH);
      updateProgressBadge();
    }
  }
}

function clampPieceToBoard(piece) {
  const box = puzzle.boardBox;
  piece.x = Math.min(Math.max(piece.x, box.x), box.x + box.width - piece.w);
  piece.y = Math.min(Math.max(piece.y, box.y), box.y + box.height - piece.h);
}

function drawBoardAndPieces() {
  const box = puzzle.boardBox;

  ctx.save();
  ctx.fillStyle = "#000";
  ctx.fillRect(box.x, box.y, box.width, box.height);
  ctx.restore();

  ctx.save();
  ctx.strokeStyle = "rgba(245,197,24,0.18)";
  ctx.lineWidth = 1;
  for (let i = 1; i < GRID; i++) {
    ctx.beginPath();
    ctx.moveTo(box.x + i * puzzle.tileW, box.y);
    ctx.lineTo(box.x + i * puzzle.tileW, box.y + box.height);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(box.x, box.y + i * puzzle.tileH);
    ctx.lineTo(box.x + box.width, box.y + i * puzzle.tileH);
    ctx.stroke();
  }
  ctx.restore();

  const sorted = [...puzzle.pieces].sort((a, b) => (a.dragging ? 1 : 0) - (b.dragging ? 1 : 0));

  for (const piece of sorted) {
    ctx.save();
    if (piece.dragging) {
      ctx.shadowColor = "rgba(245,197,24,0.9)";
      ctx.shadowBlur = 14;
    }
    ctx.drawImage(piece.canvas, piece.x, piece.y, piece.w, piece.h);
    ctx.strokeStyle = piece.placed ? "#5fae6e" : "rgba(234,229,214,0.5)";
    ctx.lineWidth = piece.dragging ? 3 : 1.5;
    ctx.strokeRect(piece.x, piece.y, piece.w, piece.h);
    ctx.restore();
  }

  ctx.save();
  ctx.strokeStyle = puzzle.solved ? "#5fae6e" : "#f5c518";
  ctx.lineWidth = 3;
  ctx.strokeRect(box.x, box.y, box.width, box.height);
  ctx.restore();

  if (puzzle.solved) {
    ctx.save();
    ctx.fillStyle = "rgba(95,174,110,0.15)";
    ctx.fillRect(box.x, box.y, box.width, box.height);
    ctx.font = `${Math.max(20, box.width * 0.07)}px 'IBM Plex Mono', monospace`;
    ctx.fillStyle = "#5fae6e";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("COMPLETE! — make a fist to save", box.x + box.width / 2, box.y + box.height / 2);
    ctx.restore();
  }
}

function updateProgressBadge() {
  if (appState !== "puzzle") {
    progressBadge.classList.remove("visible", "solved");
    return;
  }
  const placedCount = puzzle.pieces.filter((p) => p.placed).length;
  
  const elapsedMs = puzzle.solved ? (puzzle.solveTime || 0) : (performance.now() - (puzzle.startTime || performance.now()));
  const timeLeft = Math.max(0, 60 - Math.floor(elapsedMs / 1000));
  
  if (puzzle.solved) {
    progressText.textContent = `solved in ${Math.floor((puzzle.solveTime || 0) / 1000)}s!`;
  } else {
    progressText.textContent = `${placedCount} / ${puzzle.pieces.length} pieces placed - ${timeLeft}s left`;
  }
  
  progressBadge.classList.add("visible");
  progressBadge.classList.toggle("solved", puzzle.solved);
}

function drawVideoFrame() {
  ctx.save();
  ctx.translate(canvas.width, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
  ctx.restore();
}

function applyBWInsideBox(box) {
  const x = Math.max(0, Math.round(box.x));
  const y = Math.max(0, Math.round(box.y));
  const w = Math.min(canvas.width - x, Math.round(box.width));
  const h = Math.min(canvas.height - y, Math.round(box.height));
  if (w <= 0 || h <= 0) return;

  const region = ctx.getImageData(x, y, w, h);
  applyPhotoboothEffect(region);
  ctx.putImageData(region, x, y);
}

function drawLiveFrameOverlay(box) {
  ctx.save();
  ctx.strokeStyle = "#f5c518";
  ctx.lineWidth = 3;
  ctx.strokeRect(box.x, box.y, box.width, box.height);

  const cornerLen = 18;
  ctx.lineWidth = 4;
  const corners = [
    [box.x, box.y, 1, 1],
    [box.x + box.width, box.y, -1, 1],
    [box.x, box.y + box.height, 1, -1],
    [box.x + box.width, box.y + box.height, -1, -1],
  ];
  for (const [cx, cy, dx, dy] of corners) {
    ctx.beginPath();
    ctx.moveTo(cx, cy + cornerLen * dy);
    ctx.lineTo(cx, cy);
    ctx.lineTo(cx + cornerLen * dx, cy);
    ctx.stroke();
  }
  ctx.restore();
}

function isPointInBoard(px, py, box) {
  if (!box) return false;
  return (
    px >= box.x &&
    px <= box.x + box.width &&
    py >= box.y &&
    py <= box.y + box.height
  );
}

function drawHandSkeleton(landmarksPx) {
  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.shadowColor = "rgba(255,255,255,0.85)";
  ctx.shadowBlur = 10;
  ctx.strokeStyle = "white";
  ctx.lineWidth = 3;

  for (const [iA, iB] of HAND_CONNECTIONS) {
    const a = landmarksPx[iA];
    const b = landmarksPx[iB];
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  }

  ctx.shadowBlur = 6;
  ctx.fillStyle = "white";
  for (const p of landmarksPx) {
    ctx.beginPath();
    ctx.arc(p.x, p.y, 3.2, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.restore();
}

function drawHandSkeletonsOverBoard(handsLandmarks, box) {
  if (!box || !handsLandmarks || handsLandmarks.length === 0) return;

  for (const lm of handsLandmarks) {
    const landmarksPx = lm.map((pt) => toPixel(mirrorLandmarkX(pt)));
    const overBoard = landmarksPx.some((p) => isPointInBoard(p.x, p.y, box));
    if (overBoard) {
      drawHandSkeleton(landmarksPx);
    }
  }
}





let handLandmarker = null;
let fistHoldCounter = 0;
let openHandHoldCounter = 0;

function processResults(result) {


  const handsLandmarks = result.landmarks || [];
  const noHands = handsLandmarks.length === 0;

  if (!noHands) {
    resetIdleTimer();
  }

  if (noHands) {
    statusDot.className = puzzle.solved ? "status-dot solved" : "status-dot";
    fistHoldCounter = 0;
    openHandHoldCounter = 0;
    freezeGate.holding = false;

    if (drag.activeHand && drag.piece) {
      handleDragForHand(drag.activeHand, false, { x: drag.piece.x, y: drag.piece.y });
    }

    if (appState === "tracking") {
      const sinceLastSeen = performance.now() - lastSeenFrame.at;
      if (lastSeenFrame.box && sinceLastSeen < FRAME_GRACE_MS) {
        applyBWInsideBox(lastSeenFrame.box);
        drawLiveFrameOverlay(lastSeenFrame.box);
      }
      statusText.textContent = "looking for hands…";
      return;
    }

    if (appState === "countdown") {
      drawCountdownOverlay(puzzle.boardBox);
      return;
    }

    if (appState === "puzzle") {
      puzzle.solved = reconcilePlacedState(puzzle.boardBox, puzzle.tileW, puzzle.tileH);
      updateProgressBadge();
      drawBoardAndPieces();
      statusText.textContent = puzzle.solved
        ? "puzzle complete! make a fist to save it"
        : "assemble the puzzle with a pinch";
      return;
    }

    return;
  }

  statusDot.className = puzzle.solved ? "status-dot solved" : "status-dot live";




    if (appState === "tracking") {
      if (handsLandmarks.length === 2) {
      const [handA, handB] = handsLandmarks;
      const indexA = mirrorLandmarkX(handA[LM.INDEX_TIP]);
      const indexB = mirrorLandmarkX(handB[LM.INDEX_TIP]);
      const frameBox = computeHandFrame(indexA, indexB);

      if (frameBox.width > 4 && frameBox.height > 4) {
        applyBWInsideBox(frameBox);
        drawLiveFrameOverlay(frameBox);
        lastSeenFrame.box = frameBox;
        lastSeenFrame.at = performance.now();
      }

      const bothPinching = isPinching(handA) && isPinching(handB);
      if (bothPinching && frameBox.width > 40 && frameBox.height > 40) {
        if (!freezeGate.holding) {
          freezeGate.holding = true;
          freezeGate.since = performance.now();
        }
        statusDot.className = "status-dot armed";
        statusText.textContent = "hold the pinch…";

        if (performance.now() - freezeGate.since > FREEZE_HOLD_MS) {
          freezeGate.holding = false;
          startCountdown(frameBox);
        }
      } else {
        freezeGate.holding = false;
        statusText.textContent = "hands tracked";
      }
    } else {
      freezeGate.holding = false;
      const sinceLastSeen = performance.now() - lastSeenFrame.at;
      if (lastSeenFrame.box && sinceLastSeen < FRAME_GRACE_MS) {
        applyBWInsideBox(lastSeenFrame.box);
        drawLiveFrameOverlay(lastSeenFrame.box);
        statusText.textContent = "hands tracked";
      } else {
        statusText.textContent = "hands tracked";
      }
    }
    return;
  }

  if (appState === "countdown") {
    drawCountdownOverlay(puzzle.boardBox);
    return;
  }

  if (appState === "puzzle") {
    const elapsedMs = puzzle.solved ? (puzzle.solveTime || 0) : (performance.now() - (puzzle.startTime || performance.now()));
    const timeLeft = Math.max(0, 60 - Math.floor(elapsedMs / 1000));
    
    if (timeLeft === 0 && !puzzle.solved) {
      appState = "saving";
      saveAndShowQR(puzzle.fullPhotoboothCanvas, null);
      return;
    }

    const labelsPresent = new Set();
    handsLandmarks.forEach((lm, i) => {
      const label = i === 0 ? "A" : "B";
      labelsPresent.add(label);
      const pinching = isPinching(lm);
      const indexPx = toPixel(mirrorLandmarkX(lm[LM.INDEX_TIP]));
      handleDragForHand(label, pinching, indexPx);
    });

    if (drag.activeHand && !labelsPresent.has(drag.activeHand) && drag.piece) {
      handleDragForHand(drag.activeHand, false, { x: drag.piece.x, y: drag.piece.y });
    }

    if (!drag.piece) {
      const wasSolved = puzzle.solved;
      puzzle.solved = reconcilePlacedState(puzzle.boardBox, puzzle.tileW, puzzle.tileH);
      if (!wasSolved && puzzle.solved) {
        puzzle.solveTime = performance.now() - (puzzle.startTime || performance.now());
        fistHoldCounter = 0;
      }
    }

    // Fist gesture (as documented in README):
    //   hold fist on a SOLVED board   -> save photo & show QR
    //   hold fist on an UNSOLVED board -> discard board and restart
    const anyFist = handsLandmarks.some((lm) => isFist(lm));
    const pinchOrDragBusy = !!drag.piece || handsLandmarks.some((lm) => isPinching(lm));

    if (anyFist && !pinchOrDragBusy) {
      fistHoldCounter++;
      if (puzzle.solved) {
        const secsLeft = Math.max(1, Math.ceil((FIST_HOLD_FRAMES - fistHoldCounter) / 30));
        statusText.textContent = `saving��� keep fist ${secsLeft}s`;
        if (fistHoldCounter >= FIST_HOLD_FRAMES) {
          fistHoldCounter = 0;
          appState = "saving";
          saveAndShowQR(puzzle.fullPhotoboothCanvas, Math.floor((puzzle.solveTime || 0) / 1000));
          return;
        }
      } else {
        const secsLeft = Math.max(1, Math.ceil((DISCARD_HOLD_FRAMES - fistHoldCounter) / 30));
        statusText.textContent = `discard board? keep fist ${secsLeft}s`;
        if (fistHoldCounter >= DISCARD_HOLD_FRAMES) {
          fistHoldCounter = 0;
          resetPuzzleOnly();
          statusText.textContent = "board discarded";
          return;
        }
      }
    } else {
      fistHoldCounter = 0;
    }
    updateProgressBadge();

    drawBoardAndPieces();
    drawHandSkeletonsOverBoard(handsLandmarks, puzzle.boardBox);

    statusText.textContent = "assemble puzzle with pinch";
  }
}

let lastVideoTime = -1;
let lastResult = null;
function renderLoop() {
  if (videoEl.readyState >= 2 && handLandmarker) {
    if (videoEl.currentTime !== lastVideoTime) {
      lastVideoTime = videoEl.currentTime;
      const nowMs = performance.now();
      lastResult = handLandmarker.detectForVideo(videoEl, nowMs);
    }
    drawVideoFrame();
    if (lastResult) {
      processResults(lastResult);
    }
  }
  requestAnimationFrame(renderLoop);
}

function showError(message) {
  errorBanner.textContent = message;
  errorBanner.style.display = "block";
}

function showLoaderError(message) {
  loaderText.textContent = message;
  loaderText.style.color = "#e0533d";
  loaderRetry.classList.remove("hidden");
}

function resetLoaderUI() {
  loadingOverlay.classList.remove("hidden");
  loaderText.style.color = "";
  loaderText.textContent = "loading HandLandmarker model…";
  loaderRetry.classList.add("hidden");
  errorBanner.style.display = "none";
}

async function boot() {
  resetLoaderUI();

  let settled = false;
  const watchdogMs = (LOAD_TIMEOUT_MS * 2) + 5000;
  const watchdog = setTimeout(() => {
    if (!settled) {
      showLoaderError("Loading is taking too long. Click retry or check your connection.");
    }
  }, watchdogMs);

  try {
    if (!videoEl.srcObject) {
      await initWebcam();
    }

    handLandmarker = await initHandLandmarker();

    settled = true;
    clearTimeout(watchdog);
    loadingOverlay.classList.add("hidden");
    statusText.textContent = "ready";

    // Early server check: warn NOW if saving won't work later.
    // (Camera + gestures are fully client-side, so everything seems fine
    // until you solve the puzzle and the upload silently fails.)
    fetch("/api/ip")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((info) => {
        if (info.port) serverPort = info.port;
      })
      .catch(() => {
        errorBanner.textContent =
          "Warning: local server not detected - you can play, but photos cannot be saved or shared. Launch the game via 'Start Puzzle Cam.command'.";
        errorBanner.style.display = "block";
        statusText.textContent = "server missing";
      });
    requestAnimationFrame(renderLoop);
  } catch (err) {
    settled = true;
    clearTimeout(watchdog);
    if (err && err.name === "NotAllowedError") {
      showLoaderError("Camera permission denied. Enable it in your browser settings and click retry.");
    } else if (err && err.name === "NotFoundError") {
      showLoaderError("No webcam found.");
    } else {
      showLoaderError((err && err.message) || "Error starting app.");
    }
  }
}

loaderRetry.addEventListener("click", () => {
  boot();
});


boot();