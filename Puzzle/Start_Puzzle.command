#!/bin/bash
cd "$(dirname "$0")"

echo "Starting Puzzle Cam server..."
node server.js &
SERVER_PID=$!

# Wait a second for the server to bind
sleep 1

# Open the default web browser to the local server
open http://127.0.0.1:3000/

echo ""
echo "==========================================================="
echo "Puzzle Cam is running in your browser!"
echo "Keep this terminal window open while you use the app."
echo "To stop the app, simply close this window or press Ctrl+C."
echo "==========================================================="
echo ""

# Wait for the server process so the terminal stays open
wait $SERVER_PID
