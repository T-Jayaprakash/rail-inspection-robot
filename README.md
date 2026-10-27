# Autonomous Rail Track Inspection Robot

A small rail-mounted robot that drives along a railway track by itself, inspects it with cameras and sensors, and reports every defect live to a control-room dashboard:

| Feature | How it works |
|---|---|
| **Rail crack detection** | Down-looking camera → rail localisation → morphological *black-hat* filter → shape test (cracks are long and thin; rust and grease stains are round and get rejected) → severity graded by how far the crack runs across the rail head |
| **Track gauge measurement** | Both rails are found in every frame and the distance between their inner faces is measured. The nominal value is 1676 mm (Indian Broad Gauge) with a configurable ± tolerance |
| **Obstacle detection + auto-stop** | The front camera sees objects up to about 25 m ahead, so the robot slows down early. The ultrasonic or LiDAR sensor gives the exact distance up close and the robot does an emergency stop at 2 m. It waits until the track has been clear for 2 s, then resumes |
| **Geo-tagged defect log** | Every defect is stored with its chainage (km from the wheel encoder), GPS position, photo and severity. A critical defect sends an alert to the control room and fires the paint marker |
| **Live dashboard** | A browser UI showing both camera feeds, sensor tiles, a defect map, the gauge profile, the event log and the defect register, with START / STOP / manual drive controls. It opens on a phone or laptop over Wi-Fi |
| **Reports** | CSV for maintenance software, JSON, and a printable HTML report with defect photos (save it as a PDF from the browser) |

Without hardware, everything runs in **simulation mode**. A virtual robot drives on a synthetic track with known cracks, gauge faults and obstacles. The simulator only produces camera images and sensor readings. All detection runs in the real vision and control code, which is the same code that runs on the robot.

---

## Quick start

```bash
pip install -r requirements.txt

# 1. Live dashboard (simulation)
python dashboard/app.py
#    open http://localhost:5000  ->  press START AUTO

# 2. Render the demonstration video (about 2.5 min of video, takes 4-6 min to render)
python demo/make_demo_video.py
#    -> output/demo_inspection.mp4  + output/inspection_report.{csv,json,html}

# 3. Regenerate the block diagram / flowchart for the report
python docs/make_diagrams.py
```

On Windows you can double-click `run_dashboard.bat` or `make_video.bat` instead.

Useful options:

```bash
python dashboard/app.py --random --length 200 --seed 3     # different random track
python demo/make_demo_video.py --random --length 150 --seed 5 --out output/run2.mp4
```

Dashboard keyboard shortcuts: **W** = forward (hold), **S** = reverse (hold), **Space** = stop.

### On the real robot (Raspberry Pi)

```bash
pip install -r requirements.txt
python dashboard/app.py --hardware --port /dev/ttyUSB0 --track-cam 0 --front-cam 1 --section-length 500
```

Flash `firmware/rail_robot_esp32/rail_robot_esp32.ino` to the ESP32 with the Arduino IDE (board "ESP32 Dev Module", ESP32 core 3.x).

---

## Project structure

```
rail-inspection-robot/
├── rail_inspector/          core software (runs on the Raspberry Pi)
│   ├── config.py            all tunable parameters (gauge, tolerances, speeds, camera scale)
│   ├── vision.py            RailAnalyzer (rails, gauge, cracks) + ObstacleDetector
│   ├── engine.py            sensor fusion + control state machine + overlays
│   ├── defects.py           de-duplicated, geo-tagged defect log
│   ├── sources.py           SimSource (virtual robot) / HardwareSource (cameras + ESP32 serial)
│   ├── track_world.py       synthetic track + camera renderer used by the simulator
│   └── report.py            CSV / JSON / HTML report
├── dashboard/               Flask web dashboard (app.py, templates/, static/)
├── demo/make_demo_video.py  renders the demonstration video
├── firmware/rail_robot_esp32/rail_robot_esp32.ino   ESP32 motor + sensor controller
├── docs/                    project report, block diagram, flowchart
└── output/                  generated video and reports
```

## How the detection works

**1. Finding the rails.** Each frame is split into 8 horizontal bands. In every band the column-brightness profile is high-pass filtered, and the rail heads show up as bright runs about 72 mm wide. A band that disagrees with the frame median (debris, glare) is discarded.

**2. Gauge.** Gauge = (centre of right rail − centre of left rail) − rail-head width, converted to mm with the calibrated `MM_PER_PX`. The median over all bands is used. In the validation run the RMS error is under 1 mm.

**3. Cracks.** A black-hat transform (closing − image) with a vertical 3×11 kernel lights up thin dark lines that run *across* the rail. It is thresholded and masked to the rail head, then each blob is tested:
- length across the head ≥ 35 % of the head width
- aspect ratio (width / height) ≥ 1.8 and height ≤ 10 px, which rejects round rust or grease stains

Severity: MINOR ≥ 35 %, MAJOR ≥ 55 %, CRITICAL ≥ 80 % of the rail head. A crack must be seen in ≥ 2 frames before it is logged. Detections closer than 30 cm are merged into one defect.

**4. Obstacles.** In the front camera, coloured objects inside the track-corridor polygon are segmented, and their distance is estimated from where the object's base meets the ground (`d = f·h / (y − y_horizon)`). The ultrasonic or LiDAR sensor confirms the distance up close. In addition, the ESP32 firmware performs its **own hardware stop**, so the robot still stops if the Pi crashes.

### Upgrading to deep learning (future scope)

Replace `ObstacleDetector.detect()` with a YOLOv8n model (`ultralytics`) trained on railway obstacles, and add a YOLO-seg crack model trained on a rail-surface defect dataset such as RSDDs. The rest of the pipeline (logging, control, dashboard) stays the same.

## Calibration checklist for the real robot

1. Mount the track camera at a fixed height. Lay a ruler across the rails and set `MM_PER_PX` and `LEFT_RAIL_X` in `config.py`.
2. Add an LED ring light so cracks stay visible in shade and at night.
3. Run a few metres with the encoder and set `PULSES_PER_REV` / `WHEEL_DIA_M` in the firmware so the distance matches.
4. Test the ultrasonic stop distance (`STOP_CM`) with a box on the track before running autonomously.
5. Set `START_CHAINAGE_KM` and the GPS reference for your test section.

> Safety: test only on a non-operational or training track, with permission from the railway authorities, and with someone holding the E-stop.
