"""Records an inspection run for the online (static) dashboard in web/.

Writes web/replay.mp4 (track cam | front cam, side by side) and web/replay.json
(sensor state per frame, events, defects with photo close-ups).
"""
import base64
import json
import os
import subprocess
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rail_inspector import config as C                  # noqa: E402
from rail_inspector.engine import InspectionEngine      # noqa: E402
from rail_inspector.sources import SimSource            # noqa: E402
from rail_inspector.track_world import TrackWorld       # noqa: E402

FPS, STEP = 15, 2           # engine runs at 30 Hz, every 2nd frame is recorded
OUT = os.path.join(ROOT, "web")


def b64jpg(img, scale=3):
    if img is None:
        return None
    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()


def main():
    os.makedirs(OUT, exist_ok=True)
    world = TrackWorld.demo()
    eng = InspectionEngine(SimSource(world))
    W, H = C.CAM_W + 400, C.CAM_H        # track 720x480 | front 400x225 (+ padding)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow",
                           "-crf", "27", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                           os.path.join(OUT, "replay.mp4")], stdin=subprocess.PIPE)
    frames, n = [], 0
    started = False
    while True:
        if not started and eng.t >= 1.0:
            eng.command("start")
            started = True
        s = eng.step(1 / 30)
        n += 1
        if n % STEP == 0:
            canvas = np.full((H, W, 3), (23, 17, 13), np.uint8)
            canvas[:, :C.CAM_W] = eng.track_annot
            front = cv2.resize(eng.front_annot, (400, 225), interpolation=cv2.INTER_AREA)
            canvas[:225, C.CAM_W:] = front
            ff.stdin.write(canvas.tobytes())
            frames.append([round(s["t"], 2), s["status"], s["pos_m"], s["speed_mps"], s["target_mps"],
                           s["range_m"], s["cam_obstacle_m"], s["gauge_mm"], s["battery_pct"],
                           s["vibration_g"], round(s["chainage_km"], 4), s["lat"], s["lon"]])
        if eng.status == "COMPLETED" and eng.t > 2:
            break
    for _ in range(FPS * 2):        # hold the last frame for 2 s
        ff.stdin.write(canvas.tobytes())
        frames.append(frames[-1][:1] and [frames[-1][0] + 1 / FPS] + frames[-1][1:])
    ff.stdin.close()
    ff.wait()

    defects = []
    for d in eng.log.confirmed():
        dd = d.to_dict()
        defects.append({k: dd[k] for k in ("id", "type", "severity", "rail", "detail", "pos_m", "end_m",
                                            "chainage", "lat", "lon", "t_run")} | {"img": b64jpg(d.snapshot)})
    data = {
        "fps": FPS,
        "length_m": world.length_m,
        "nominal_gauge": C.NOMINAL_GAUGE_MM, "tol": C.GAUGE_TOLERANCE_MM,
        "max_speed": C.MAX_SPEED_MPS, "range_max": C.RANGE_SENSOR_MAX_M, "stop_m": C.OBSTACLE_STOP_M,
        "start_km": C.START_CHAINAGE_KM,
        "cols": ["t", "status", "pos", "speed", "target", "range", "cam", "gauge", "bat", "vib", "km", "lat", "lon"],
        "frames": frames,
        "messages": list(reversed(eng.messages)),
        "alerts": list(reversed(eng.alerts)),
        "defects": defects,
        "gauge_profile": eng.gauge_profile,
        "truth": {"cracks": len(world.cracks), "gauge": len(world.gauge_faults), "obstacles": len(world.obstacles)},
    }
    with open(os.path.join(OUT, "replay.json"), "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print("frames", len(frames), "defects", len(defects))


if __name__ == "__main__":
    main()
