#!/bin/bash
echo "Starting Discord Bot Dashboard..."
python bot.py &
BOT_PID=$!
echo "Bot started (PID: $BOT_PID)"
python dashboard.py &
DASH_PID=$!
echo "Dashboard started (PID: $DASH_PID) → http://localhost:5000"
wait
