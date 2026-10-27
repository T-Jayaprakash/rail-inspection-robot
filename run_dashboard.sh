#!/usr/bin/env bash
# Linux / macOS / Raspberry Pi: start the live dashboard (add --hardware on the robot)
cd "$(dirname "$0")"
pip install -r requirements.txt
python3 dashboard/app.py "$@"
