"""Data sources for the inspection engine.

SimSource       - virtual robot on a synthetic track (no hardware needed)
HardwareSource  - real robot: 2 USB / Pi cameras + ESP32 over serial

Both expose the same interface:
    drive(speed_cmd_mps, dt)   -> send motor command
    read(t)                    -> (track_bgr, front_bgr, sensors_dict)
"""
import json
import math
import threading
import time

import numpy as np

from . import config as C
from .track_world import TrackWorld, TrackRenderer


class SimSource:
    name = "SIMULATION"

    def __init__(self, world: TrackWorld | None = None):
        self.world = world or TrackWorld.demo()
        self.render = TrackRenderer(self.world)
        self.pos_m = 0.0
        self.speed = 0.0
        self.battery = 98.0
        self.rng = np.random.default_rng(11)
        self.t = 0.0

    @property
    def track_length_m(self):
        return self.world.length_m

    def reset(self):
        self.pos_m, self.speed, self.battery = 0.0, 0.0, 98.0
        for o in self.world.obstacles:
            o.removed, o.stopped_since = False, None

    def drive(self, speed_cmd, dt):
        # first-order motor model with acceleration limit
        dv = np.clip(speed_cmd - self.speed, -C.ACCEL_MPS2 * 1.6 * dt, C.ACCEL_MPS2 * dt)
        self.speed += dv
        if abs(self.speed) < 0.01 and speed_cmd == 0:
            self.speed = 0.0
        self.pos_m = float(np.clip(self.pos_m + self.speed * dt, 0, self.world.length_m))
        self.battery = max(0.0, self.battery - (0.004 + 0.02 * abs(self.speed)) * dt)
        self.t += dt
        # obstacles are cleared by the field team some seconds after the robot stops
        for o in self.world.obstacles:
            if o.removed:
                continue
            d = o.pos_m - self.pos_m
            if 0 < d < C.OBSTACLE_STOP_M + 0.6 and abs(self.speed) < 0.02:
                o.stopped_since = o.stopped_since if o.stopped_since is not None else self.t
                if self.t - o.stopped_since > o.clears_after_s:
                    o.removed = True

    def read(self, t):
        track = self.render.track_frame(self.pos_m, abs(self.speed), t)
        front = self.render.front_frame(self.pos_m, t)
        # range sensor (ultrasonic / LiDAR) - only sees close objects
        o = self.world.next_obstacle(self.pos_m)
        rng = C.RANGE_SENSOR_MAX_M
        if o is not None:
            d = o.pos_m - self.pos_m
            if 0 < d < C.RANGE_SENSOR_MAX_M:
                rng = max(0.05, d + self.rng.normal(0, 0.02))
        # IMU vibration: background + spikes over cracks and rail joints
        vib = 0.04 + 0.03 * abs(self.speed) + abs(self.rng.normal(0, 0.012))
        for cr in self.world.cracks:
            if abs(cr.pos_m - self.pos_m) < 0.08 and abs(self.speed) > 0.1:
                vib += 0.35 * cr.frac
        gauge_dev = self.world.gauge_offset_mm(self.pos_m)
        vib += 0.004 * abs(gauge_dev) * abs(self.speed)
        sensors = {
            "encoder_m": self.pos_m,
            "speed_mps": self.speed,
            "range_m": float(rng),
            "battery_pct": self.battery,
            "vibration_g": float(vib),
            "temp_c": 41.0 + 2 * math.sin(t / 30),
            "tilt_deg": float(gauge_dev * 0.02 + self.rng.normal(0, 0.05)),
        }
        return track, front, sensors

    def close(self):
        pass


class HardwareSource:
    """Real robot.  Raspberry Pi 4/5 + ESP32 motor/sensor controller.

    Serial protocol (115200 baud, one JSON object per line), see
    firmware/rail_robot_esp32/rail_robot_esp32.ino:
        ESP32 -> Pi : {"enc":12.345,"spd":0.98,"us":3.10,"bat":11.9,"vib":0.06,"tmp":38.5,"tilt":0.2,"estop":0}
        Pi -> ESP32 : {"cmd":"drive","v":1.2}   /  {"cmd":"stop"}  /  {"cmd":"mark"}
    """
    name = "HARDWARE"

    def __init__(self, port="/dev/ttyUSB0", track_cam=0, front_cam=1, track_length_m=1000.0):
        import cv2
        import serial  # pip install pyserial

        self.cv2 = cv2
        self.ser = serial.Serial(port, 115200, timeout=0.05)
        self.cam_track = cv2.VideoCapture(track_cam)
        self.cam_front = cv2.VideoCapture(front_cam)
        for cam, (w, h) in ((self.cam_track, (C.CAM_W, C.CAM_H)), (self.cam_front, (C.FRONT_W, C.FRONT_H))):
            cam.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            cam.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        self.track_length_m = track_length_m
        self.last = {"enc": 0.0, "spd": 0.0, "us": C.RANGE_SENSOR_MAX_M, "bat": 12.4, "vib": 0.0,
                     "tmp": 0.0, "tilt": 0.0, "estop": 0}
        self._stop = False
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        while not self._stop:
            try:
                line = self.ser.readline().decode(errors="ignore").strip()
                if line.startswith("{"):
                    self.last.update(json.loads(line))
            except Exception:
                time.sleep(0.05)

    def _send(self, obj):
        self.ser.write((json.dumps(obj) + "\n").encode())

    def reset(self):
        self._send({"cmd": "reset_enc"})

    def drive(self, speed_cmd, dt):
        if speed_cmd == 0:
            self._send({"cmd": "stop"})
        else:
            self._send({"cmd": "drive", "v": round(float(speed_cmd), 2)})

    def mark(self):
        """Fire the paint-marker solenoid at the current spot."""
        self._send({"cmd": "mark"})

    def read(self, t):
        cv2 = self.cv2
        ok1, track = self.cam_track.read()
        ok2, front = self.cam_front.read()
        if not ok1:
            track = np.zeros((C.CAM_H, C.CAM_W, 3), np.uint8)
        if not ok2:
            front = np.zeros((C.FRONT_H, C.FRONT_W, 3), np.uint8)
        track = cv2.resize(track, (C.CAM_W, C.CAM_H))
        front = cv2.resize(front, (C.FRONT_W, C.FRONT_H))
        s = self.last
        # 3S Li-ion: 12.6 V full, 10.5 V empty
        bat_pct = float(np.clip((s["bat"] - 10.5) / (12.6 - 10.5) * 100, 0, 100))
        sensors = {
            "encoder_m": float(s["enc"]),
            "speed_mps": float(s["spd"]),
            "range_m": float(s["us"]),
            "battery_pct": bat_pct,
            "vibration_g": float(s["vib"]),
            "temp_c": float(s["tmp"]),
            "tilt_deg": float(s["tilt"]),
            "estop": int(s.get("estop", 0)),
        }
        return track, front, sensors

    def close(self):
        self._stop = True
        self._send({"cmd": "stop"})
        self.cam_track.release()
        self.cam_front.release()
