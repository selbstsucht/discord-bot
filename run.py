"""
Single entrypoint that starts both the Discord bot and the Flask dashboard.
Used by Railway (and any other platform that expects one process).
"""
import subprocess
import sys
import os
import signal

procs = []

def shutdown(sig, frame):
    for p in procs:
        p.terminate()
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

bot  = subprocess.Popen([sys.executable, '-u', 'bot.py'])
dash = subprocess.Popen([sys.executable, '-u', 'dashboard.py'])
procs = [bot, dash]

# If either process dies, kill both and exit (Railway will restart the service)
while True:
    if bot.poll() is not None:
        print(f'Bot exited with code {bot.returncode}', flush=True)
        dash.terminate()
        sys.exit(bot.returncode)
    if dash.poll() is not None:
        print(f'Dashboard exited with code {dash.returncode}', flush=True)
        bot.terminate()
        sys.exit(dash.returncode)
