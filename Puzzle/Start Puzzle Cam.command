#!/bin/bash
# Start Puzzle Cam.command
# Double-click to launch PuzzleCam - the gesture-controlled photo puzzle game.
#   - Show BOTH hands and pinch (thumb + index) to freeze a capture frame
#   - Hold the pinch for the 3-2-1 countdown; the photo becomes a 3x3 puzzle
#   - Pinch & drag pieces to solve it; hold a FIST on the solved board to save
#   - Scan the QR code with your phone to download the result

APP_DIR="/Users/hriday/Desktop/smart mirror #2/Puzzle"
PORT="${PORT:-3000}"

cd "$APP_DIR" || { echo "[puzzle] ERROR: cannot find $APP_DIR"; exit 1; }

if ! command -v node >/dev/null 2>&1; then
    echo "[puzzle] ERROR: Node.js is not installed or not in PATH."
    read -r -p "Press Return to close this window..." _
    exit 1
fi

echo "Starting PuzzleCam server on port $PORT..."
node server.js &
SERVER_PID=$!

# Wait until the server actually answers (max ~5s)
READY=0
for _ in $(seq 1 25); do
    if curl -s --max-time 1 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
        READY=1
        break
    fi
    # If the server already died (e.g. port busy), stop waiting
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        break
    fi
    sleep 0.2
done

if [ "$READY" -eq 1 ]; then
    open "http://127.0.0.1:$PORT/"
    echo ""
    echo "==========================================================="
    echo " PuzzleCam is running in your browser!"
    echo " Keep this window OPEN while you play."
    echo " Quit: press Ctrl+C here, or just close this window."
    echo "==========================================================="
else
    echo ""
    echo "[puzzle] Server did not become ready - check the messages above."
fi

wait "$SERVER_PID" 2>/dev/null
EXIT_CODE=$?

read -r -p "PuzzleCam stopped. Press Return to close this window..." _
exit $EXIT_CODE
