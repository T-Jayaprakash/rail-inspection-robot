@echo off
REM Windows: renders output\demo_inspection.mp4 (takes a few minutes)
pip install -r requirements.txt
python demo\make_demo_video.py
pause
