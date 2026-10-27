"""Live control-room dashboard.

    python dashboard/app.py                         # simulation (no hardware)
    python dashboard/app.py --random --length 200   # random defects
    python dashboard/app.py --hardware --port /dev/ttyUSB0 --track-cam 0 --front-cam 1

Then open http://localhost:5000 (or http://<raspberry-pi-ip>:5000 from any
phone/laptop on the same Wi-Fi).
"""
import argparse
import os
import sys
import threading
import time

import cv2
from flask import Flask, Response, jsonify, render_template, request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rail_inspector import config as C                          # noqa: E402
from rail_inspector.engine import InspectionEngine              # noqa: E402
from rail_inspector.report import csv_text, html_report, write_reports  # noqa: E402

app = Flask(__name__)
ENGINE: InspectionEngine = None
LOCK = threading.Lock()
JPEG = {"track": None, "front": None}


def engine_loop(rate_hz):
    period = 1.0 / rate_hz
    last = time.time()
    while True:
        now = time.time()
        dt = min(0.2, now - last)
        last = now
        with LOCK:
            ENGINE.step(dt)
            for key, img in (("track", ENGINE.track_annot), ("front", ENGINE.front_annot)):
                ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ok:
                    JPEG[key] = buf.tobytes()
        time.sleep(max(0.0, period - (time.time() - now)))


def mjpeg(key):
    while True:
        frame = JPEG.get(key)
        if frame:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        time.sleep(0.05)


@app.route("/")
def index():
    return render_template("index.html", cfg={
        "nominal_gauge": C.NOMINAL_GAUGE_MM, "tol": C.GAUGE_TOLERANCE_MM,
        "max_speed": C.MAX_SPEED_MPS, "cruise": C.CRUISE_SPEED_MPS})


@app.route("/stream/<key>")
def stream(key):
    return Response(mjpeg(key), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/state")
def state():
    with LOCK:
        e = ENGINE
        prof = e.gauge_profile
        step = max(1, len(prof) // 400)
        return jsonify({
            **e.last,
            "messages": list(e.messages)[:12],
            "alerts": list(e.alerts),
            "defects": [d.to_dict() for d in e.log.confirmed()],
            "gauge_profile": prof[::step],
            "vib_hist": [round(v, 3) for v in list(e.vib_hist)[-120:]],
            "cruise": e.cruise,
        })


@app.route("/api/cmd", methods=["POST"])
def cmd():
    data = request.get_json(force=True)
    with LOCK:
        ENGINE.command(data.get("cmd"), data.get("value"))
    return jsonify(ok=True)


@app.route("/api/snapshot/<int:did>.jpg")
def snapshot(did):
    with LOCK:
        d = next((x for x in ENGINE.log.items if x.id == did), None)
        img = d.snapshot if d is not None else None
    if img is None:
        return "", 404
    img = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
    ok, buf = cv2.imencode(".jpg", img)
    return Response(buf.tobytes(), mimetype="image/jpeg")


@app.route("/report.csv")
def report_csv():
    with LOCK:
        txt = csv_text(ENGINE)
    return Response(txt, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=inspection_report.csv"})


@app.route("/report")
def report_html():
    with LOCK:
        write_reports(ENGINE, os.path.join(ROOT, "output"))
        return html_report(ENGINE)


def main():
    global ENGINE
    ap = argparse.ArgumentParser()
    ap.add_argument("--hardware", action="store_true", help="use the real robot instead of the simulator")
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--track-cam", type=int, default=0)
    ap.add_argument("--front-cam", type=int, default=1)
    ap.add_argument("--section-length", type=float, default=1000.0, help="hardware: metres to inspect")
    ap.add_argument("--random", action="store_true")
    ap.add_argument("--length", type=float, default=80.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--rate", type=float, default=20.0, help="processing rate (Hz)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--http-port", type=int, default=5000)
    args = ap.parse_args()

    if args.hardware:
        from rail_inspector.sources import HardwareSource
        src = HardwareSource(args.port, args.track_cam, args.front_cam, args.section_length)
    else:
        from rail_inspector.sources import SimSource
        from rail_inspector.track_world import TrackWorld
        print("Building simulated track ...")
        world = TrackWorld.random(args.length, args.seed) if args.random else TrackWorld.demo(args.length, args.seed)
        src = SimSource(world)
    ENGINE = InspectionEngine(src)
    threading.Thread(target=engine_loop, args=(args.rate,), daemon=True).start()
    print(f"Dashboard: http://localhost:{args.http_port}")
    app.run(host=args.host, port=args.http_port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
