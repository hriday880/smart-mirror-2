#!/bin/bash
# test.command - macOS double-clickable launcher for the Smart Mirror
# Hand Gesture Photo Capture test application (main_test.py).
# Space-tolerant path resolution, virtualenv activation, graceful exit.

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1

if [ -f "$DIR/venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$DIR/venv/bin/activate"
else
    echo "[test.command] WARNING: venv not found at $DIR/venv - using system python"
fi

python main_test.py "$@"
EXIT_CODE=$?

deactivate >/dev/null 2>&1

echo ""
echo "[test.command] Smart Mirror Photo Booth exited with code $EXIT_CODE."
exit $EXIT_CODE
