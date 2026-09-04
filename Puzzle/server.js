const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');

const PORT = Number(process.env.PORT) || 3000;
const PHOTOS_DIR = path.join(__dirname, 'photos');
const MAX_UPLOAD_BYTES = 50 * 1024 * 1024; // 50 MB safety cap for base64 payloads

// Ensure photos directory exists
if (!fs.existsSync(PHOTOS_DIR)) {
  fs.mkdirSync(PHOTOS_DIR, { recursive: true });
}

const MIME_TYPES = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml'
};

function getLocalIp() {
  const interfaces = os.networkInterfaces();
  for (const name of Object.keys(interfaces)) {
    for (const iface of interfaces[name]) {
      if (iface.family === 'IPv4' && !iface.internal) {
        return iface.address;
      }
    }
  }
  return '127.0.0.1';
}

/**
 * Extracts a safe photo filename from a request path segment.
 * Blocks directory traversal (".."), hidden files, and non-image extensions.
 * Returns null when the name is not acceptable.
 */
function safePhotoName(rawName) {
  if (!rawName) return null;
  let name;
  try {
    name = decodeURIComponent(rawName);
  } catch (_e) {
    return null;
  }
  const base = path.basename(name);
  if (!base || base.startsWith('.')) return null;
  if (!/^[A-Za-z0-9._-]+$/.test(base)) return null;
  if (!/\.(png|jpe?g)$/i.test(base)) return null;
  return base;
}

function htmlEscape(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function sendJson(res, status, payload) {
  res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(payload));
}

function renderMobileLandingHtml(filename, timestampStr) {
  const escapedFile = htmlEscape(filename);
  const escapedTs = htmlEscape(timestampStr);

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Your Smart Mirror Photo</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #090d16;
      color: #f1f5f9;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 16px;
    }
    .card {
      background: #131b2e;
      border: 1px solid #1e293b;
      border-radius: 20px;
      padding: 20px;
      max-width: 480px;
      width: 100%;
      box-shadow: 0 20px 40px rgba(0,0,0,0.6), 0 0 20px rgba(14, 165, 233, 0.15);
      text-align: center;
    }
    .badge {
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
    }
    h1 {
      font-size: 22px;
      font-weight: 800;
      margin-bottom: 6px;
      background: linear-gradient(to right, #38bdf8, #818cf8);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .subtitle {
      color: #94a3b8;
      font-size: 13px;
      margin-bottom: 16px;
    }
    .img-container {
      position: relative;
      width: 100%;
      border-radius: 14px;
      overflow: hidden;
      background: #020617;
      border: 2px solid #334155;
      margin-bottom: 20px;
      box-shadow: 0 8px 16px rgba(0,0,0,0.4);
    }
    .img-container img {
      width: 100%;
      height: auto;
      display: block;
      transition: transform 0.3s ease;
    }
    .actions {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .btn {
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
    }
    .btn-save {
      background: linear-gradient(135deg, #0284c7, #2563eb);
      color: white;
      box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4);
    }
    .btn-save:active {
      transform: scale(0.98);
      background: linear-gradient(135deg, #0369a1, #1d4ed8);
    }
    .btn-share {
      background: #1e293b;
      color: #38bdf8;
      border: 1px solid #334155;
    }
    .btn-share:active {
      background: #334155;
    }
    .footer {
      margin-top: 20px;
      color: #64748b;
      font-size: 11px;
    }
    .toast {
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
    }
    .toast.show {
      visibility: visible;
      opacity: 1;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">��� Fair Photo Booth</div>
    <h1>Your Capture is Ready!</h1>
    <p class="subtitle">Smart Mirror Puzzle &bull; ${escapedTs}</p>

    <div class="img-container">
      <img src="/photo/${escapedFile}" alt="Smart Mirror Photo" id="mirrorPhoto">
    </div>

    <div class="actions">
      <a href="/photo/${escapedFile}" download="${escapedFile}" class="btn btn-save" id="saveBtn">
        ���� Save Photo to Phone
      </a>
      <button class="btn btn-share" onclick="handleShare()">
        ���� Share Photo
      </button>
    </div>

    <div class="footer">
      Powered by Smart Mirror Interactive Booth &bull; Tap &amp; hold photo to save on iOS
    </div>
  </div>

  <div id="toast" class="toast">Link copied to clipboard!</div>

  <script>
    function showToast(msg) {
      const toast = document.getElementById("toast");
      toast.innerText = msg;
      toast.className = "toast show";
      setTimeout(() => { toast.className = "toast"; }, 2500);
    }

    async function handleShare() {
      const photoUrl = window.location.origin + "/photo/${escapedFile}";
      if (navigator.share) {
        try {
          await navigator.share({
            title: "My Smart Mirror Photo",
            text: "Check out my photo from the Smart Mirror Booth!",
            url: window.location.href
          });
        } catch (err) {
          if (err.name !== "AbortError") {
            copyLink();
          }
        }
      } else {
        copyLink();
      }
    }

    function copyLink() {
      navigator.clipboard.writeText(window.location.href).then(() => {
        showToast("Link copied to clipboard!");
      }).catch(() => {
        showToast("Share URL: " + window.location.href);
      });
    }
  </script>
</body>
</html>`;
}

function handlePhotoRequest(req, res, rawFilename) {
  const cleanName = safePhotoName(rawFilename);
  if (!cleanName) {
    res.writeHead(403, { 'Content-Type': 'text/plain' });
    res.end('403 Forbidden: invalid filename');
    return;
  }

  // Defense in depth: resolve and confirm the final path stays inside PHOTOS_DIR
  const filePath = path.join(PHOTOS_DIR, cleanName);
  if (!path.resolve(filePath).startsWith(path.resolve(PHOTOS_DIR) + path.sep)) {
    res.writeHead(403, { 'Content-Type': 'text/plain' });
    res.end('403 Forbidden');
    return;
  }

  fs.readFile(filePath, (err, content) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('404 Not Found');
    } else {
      res.writeHead(200, {
        'Content-Type': MIME_TYPES[path.extname(cleanName).toLowerCase()] || 'application/octet-stream',
        'Cache-Control': 'public, max-age=3600'
      });
      res.end(content);
    }
  });
}

const server = http.createServer((req, res) => {
  let pathname;
  try {
    pathname = decodeURIComponent((req.url || '/').split('?')[0]);
  } catch (_e) {
    res.writeHead(400, { 'Content-Type': 'text/plain' });
    res.end('400 Bad Request');
    return;
  }

  if (req.method === 'GET') {
    if (pathname === '/api/ip') {
      sendJson(res, 200, { ip: getLocalIp(), port: PORT });
      return;
    }

    if (pathname === '/health') {
      sendJson(res, 200, { status: 'online', timestamp: new Date().toISOString() });
      return;
    }

    if (pathname.startsWith('/view/')) {
      const rawName = pathname.slice('/view/'.length);
      const cleanName = safePhotoName(rawName);
      if (!cleanName) {
        res.writeHead(403, { 'Content-Type': 'text/plain' });
        res.end('403 Forbidden: invalid filename');
        return;
      }
      const ts = new Date().toLocaleString();
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
      res.end(renderMobileLandingHtml(cleanName, ts));
      return;
    }

    if (pathname.startsWith('/photo/')) {
      handlePhotoRequest(req, res, pathname.slice('/photo/'.length));
      return;
    }

    // Static file serving - always resolve relative to the project dir
    let relPath = pathname === '/' ? 'index.html' : pathname.slice(1);
    const filePath = path.normalize(path.join(__dirname, relPath));
    if (!filePath.startsWith(__dirname + path.sep)) {
      res.writeHead(403, { 'Content-Type': 'text/plain' });
      res.end('403 Forbidden');
      return;
    }

    const extname = String(path.extname(filePath)).toLowerCase();
    const contentType = MIME_TYPES[extname] || 'application/octet-stream';

    fs.readFile(filePath, (err, content) => {
      if (err) {
        if (err.code === 'ENOENT') {
          res.writeHead(404, { 'Content-Type': 'text/plain' });
          res.end('404 File Not Found');
        } else {
          res.writeHead(500, { 'Content-Type': 'text/plain' });
          res.end('500 Internal Server Error: ' + err.code);
        }
      } else {
        res.writeHead(200, { 'Content-Type': contentType });
        res.end(content);
      }
    });
  } else if (req.method === 'POST' && pathname === '/api/upload') {
    const chunks = [];
    let bodySize = 0;
    let aborted = false;

    req.on('data', chunk => {
      bodySize += chunk.length;
      if (bodySize > MAX_UPLOAD_BYTES) {
        aborted = true;
        res.writeHead(413, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Payload too large' }));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });

    req.on('end', () => {
      if (aborted) return;
      try {
        const data = JSON.parse(Buffer.concat(chunks).toString('utf8'));
        if (data.image && typeof data.image === 'string') {
          const base64Data = data.image.replace(/^data:image\/png;base64,/, "");
          if (!base64Data || !/^[A-Za-z0-9+/=]+$/.test(base64Data)) {
            sendJson(res, 400, { error: 'Invalid image data' });
            return;
          }
          const filename = `puzzlecam_${Date.now()}.png`;
          const filepath = path.join(PHOTOS_DIR, filename);
          fs.writeFile(filepath, base64Data, 'base64', (err) => {
            if (err) {
              sendJson(res, 500, { error: err.message });
            } else {
              sendJson(res, 200, { filename: filename });
            }
          });
        } else {
          sendJson(res, 400, { error: 'Bad Request: missing image field' });
        }
      } catch (_e) {
        sendJson(res, 400, { error: 'Invalid JSON' });
      }
    });

    req.on('error', () => {
      aborted = true;
    });
  } else {
    res.writeHead(405, { 'Content-Type': 'text/plain' });
    res.end('405 Method Not Allowed');
  }
});

server.on('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    console.error(`\n[ERROR] Port ${PORT} is already in use.`);
    console.error(`  -> Another PuzzleCam instance may be running.`);
    console.error(`  -> Fix: close the other app, or run:  PORT=${PORT + 1} node server.js\n`);
  } else if (err.code === 'EACCES') {
    console.error(`\n[ERROR] No permission to bind port ${PORT}. Try:  PORT=8080 node server.js\n`);
  } else {
    console.error('[ERROR] Server failed:', err);
  }
  process.exit(1);
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Server running at http://localhost:${PORT}/`);
  console.log(`LAN access for phones:  http://${getLocalIp()}:${PORT}/`);
  console.log('Press Ctrl+C to stop.');
});

// Graceful shutdown so Ctrl+C closes cleanly instead of hanging
function shutdown(signal) {
  console.log(`\n[${signal}] Shutting down PuzzleCam server...`);
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 1500).unref();
}
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
