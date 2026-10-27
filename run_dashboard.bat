@echo off
REM Windows: double-click to start the live dashboard in simulation mode
pip install -r requirements.txt
start http://localhost:5000
python dashboard\app.py
