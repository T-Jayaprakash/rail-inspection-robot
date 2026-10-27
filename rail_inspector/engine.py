"""Inspection engine: vision + sensor fusion + autonomous control + logging.

This is the program that runs on the robot's Raspberry Pi.  It is used
unchanged by the live dashboard and by the demo-video generator.
"""
from collections import deque
import time

import cv2
import numpy as np

from . import config as C
from .defects import DefectLog, location
from .vision import RailAnalyzer, ObstacleDetector

SEV_COLOR = {"MINOR": (0, 215, 255), "MAJOR": (0, 140, 255), "CRITICAL": (40, 40, 235)}

STATUS_TEXT = {
    "IDLE": "READY",
    "INSPECTING": "INSPECTING",
    "SLOWING": "OBSTACLE AHEAD - SLOWING",
    "OBSTACLE_STOP": "STOPPED - OBSTACLE",
    "PAUSED": "PAUSED BY OPERATOR",
    "MANUAL": "MANUAL CONTROL",
    "COMPLETED": "INSPECTION COMPLETE",
}


class InspectionEngine:
    def __init__(self, source):
        self.src = source
        self.rail = RailAnalyzer()
        self.obst = ObstacleDetector()
        self.reset()

    def reset(self):
        if hasattr(self.src, "reset"):
            self.src.reset()
        self.log = DefectLog()
        self.t = 0.0
        self.status = "IDLE"
        self.target = 0.0
        self.manual_speed = 0.0
        self.cruise = C.CRUISE_SPEED_MPS
        self.clear_timer = 0.0
        self.messages = deque(maxlen=60)
        self.vib_hist = deque(maxlen=240)
        self.gauge_hist = deque(maxlen=240)
        self.gauge_profile = []          # (pos_m, gauge_mm) every ~10 cm
        self.frames_processed = 0
        self.fps = 0.0
        self._fps_t = time.time()
        self.alerts = deque(maxlen=10)
        self.last = {}
        self.track_annot = None
        self.front_annot = None
        self.say("System ready. Source: " + self.src.name)

    # ------------------------------------------------------------- commands
    def say(self, text, level="info"):
        self.messages.appendleft({"t": round(self.t, 1), "text": text, "level": level})

    def command(self, cmd, value=None):
        if cmd == "start":
            if self.status in ("IDLE", "PAUSED", "MANUAL", "COMPLETED"):
                if self.status == "COMPLETED":
                    return
                self.status = "INSPECTING"
                self.say("Autonomous inspection started")
        elif cmd == "stop":
            self.status = "PAUSED"
            self.manual_speed = 0.0
            self.say("Stopped by operator", "warn")
        elif cmd == "manual":
            self.status = "MANUAL"
            self.manual_speed = float(np.clip(value or 0.0, -C.MAX_SPEED_MPS, C.MAX_SPEED_MPS))
        elif cmd == "speed":
            self.cruise = float(np.clip(value, 0.1, C.MAX_SPEED_MPS))
            self.say(f"Cruise speed set to {self.cruise:.1f} m/s")
        elif cmd == "reset":
            self.reset()

    # ------------------------------------------------------------------ step
    def step(self, dt):
        self.t += dt
        track, front, s = self.src.read(self.t)
        pos = s["encoder_m"]

        # ---- vision on the track camera
        bands, gauge, cracks = self.rail.analyze(track)
        for c in cracks:
            wpos = pos + (C.CAM_H / 2 - c.row) * C.MM_PER_PX / 1000.0
            x, y, w, h = c.box
            crop = track[max(0, y - 40):y + h + 40, max(0, x - 40):x + w + 40].copy()
            ev = self.log.add_crack(c.rail, wpos, c.frac, self.t, crop)
            if ev:
                side = "LEFT" if ev.rail == "L" else "RIGHT"
                lvl = "crit" if ev.severity == "CRITICAL" else "warn"
                self.say(f"CRACK [{ev.severity}] {side} rail at km {ev.chainage_km:.3f}", lvl)
                if ev.severity == "CRITICAL":
                    self.alerts.appendleft({"t": round(self.t, 1),
                                            "text": f"ALERT sent to control room: critical crack km {ev.chainage_km:.3f}"})
                    if hasattr(self.src, "mark"):
                        self.src.mark()
        if gauge is not None:
            self.gauge_hist.append(gauge)
            if not self.gauge_profile or abs(pos - self.gauge_profile[-1][0]) >= 0.1:
                self.gauge_profile.append((round(pos, 2), round(gauge, 1)))
            ev = self.log.update_gauge(pos, gauge, self.t)
            if ev:
                self.say(f"GAUGE {ev.detail.split()[0].upper()} {gauge:.0f} mm at km {ev.chainage_km:.3f}", "warn")
        self.vib_hist.append(s["vibration_g"])

        # ---- obstacle: camera (long range) + range sensor (short range)
        od = self.obst.detect(front)
        cam_d = od.est_dist_m if od else None
        rng = s["range_m"]
        near = rng < C.OBSTACLE_STOP_M or (cam_d is not None and cam_d < C.OBSTACLE_STOP_M * 0.8)
        seen = cam_d is not None and cam_d < C.OBSTACLE_WARN_M

        # ---- control state machine
        st = self.status
        if st in ("INSPECTING", "SLOWING", "OBSTACLE_STOP"):
            if near:
                if st != "OBSTACLE_STOP":
                    self.say(f"EMERGENCY STOP - obstacle at {min(rng, cam_d or 99):.1f} m", "crit")
                    snap = None
                    if od:
                        x, y, w, h = od.box
                        snap = front[max(0, y - 10):y + h + 10, max(0, x - 10):x + w + 10].copy()
                    ev = self.log.add_obstacle(pos, min(rng, cam_d or rng), self.t, snap)
                    if ev:
                        self.alerts.appendleft({"t": round(self.t, 1),
                                                "text": f"ALERT: track obstructed at km {ev.chainage_km:.3f}"})
                self.status = "OBSTACLE_STOP"
                self.clear_timer = 0.0
            elif st == "OBSTACLE_STOP":
                self.clear_timer += dt
                if self.clear_timer >= C.RESUME_CLEAR_S and not seen:
                    self.status = "INSPECTING"
                    self.say("Track clear - resuming inspection", "ok")
            elif seen:
                if st != "SLOWING":
                    self.say(f"Obstacle detected {cam_d:.1f} m ahead - slowing down", "warn")
                self.status = "SLOWING"
            else:
                if st == "SLOWING":
                    self.say("Obstacle no longer in path", "ok")
                self.status = "INSPECTING"
            if pos >= self.src.track_length_m - 0.05:
                self.status = "COMPLETED"
                self.say("Inspection run complete - report ready", "ok")

        st = self.status
        if st == "INSPECTING":
            self.target = self.cruise
        elif st == "SLOWING":
            self.target = self.cruise * C.OBSTACLE_SLOW_FACTOR
        elif st == "MANUAL":
            self.target = self.manual_speed
            if near and self.target > 0:          # safety interlock even in manual
                self.target = 0.0
        else:
            self.target = 0.0
        self.src.drive(self.target, dt)

        # ---- bookkeeping
        self.frames_processed += 1
        now = time.time()
        if now - self._fps_t > 1.0:
            self.fps = self.frames_processed / max(1e-6, self.t) if self.t else 0
            self._fps_t = now
        km, lat, lon = location(pos)
        self.last = {
            "t": round(self.t, 2), "status": st, "status_text": STATUS_TEXT[st],
            "source": self.src.name,
            "pos_m": round(pos, 2), "length_m": self.src.track_length_m,
            "chainage_km": round(km, 4), "lat": round(lat, 6), "lon": round(lon, 6),
            "speed_mps": round(s["speed_mps"], 2), "target_mps": round(self.target, 2),
            "range_m": round(rng, 2), "cam_obstacle_m": round(cam_d, 1) if cam_d else None,
            "gauge_mm": round(gauge, 1) if gauge else None,
            "gauge_dev_mm": round(gauge - C.NOMINAL_GAUGE_MM, 1) if gauge else None,
            "battery_pct": round(s["battery_pct"], 1), "vibration_g": round(s["vibration_g"], 3),
            "temp_c": round(s["temp_c"], 1), "tilt_deg": round(s["tilt_deg"], 2),
            "summary": self.log.summary(),
            "live_cracks": len(cracks),
        }
        self.track_annot = self.annotate_track(track, bands, gauge, cracks)
        self.front_annot = self.annotate_front(front, od, rng)
        return self.last

    # ----------------------------------------------------------- overlays
    def annotate_track(self, img, bands, gauge, cracks):
        out = img.copy()
        for b in bands:
            for r in (b.left, b.right):
                if r:
                    cv2.line(out, (r[0] - 2, b.y0 + 2), (r[0] - 2, b.y1 - 2), (255, 220, 0), 1)
                    cv2.line(out, (r[1] + 1, b.y0 + 2), (r[1] + 1, b.y1 - 2), (255, 220, 0), 1)
        # gauge measurement line through the middle band
        mid = bands[len(bands) // 2]
        if mid.left and mid.right and gauge:
            y = (mid.y0 + mid.y1) // 2
            x1, x2 = mid.left[1] + 2, mid.right[0] - 2
            bad = abs(gauge - C.NOMINAL_GAUGE_MM) > C.GAUGE_TOLERANCE_MM
            col = (40, 40, 235) if bad else (90, 220, 90)
            cv2.arrowedLine(out, ((x1 + x2) // 2, y), (x1, y), col, 2, tipLength=0.03)
            cv2.arrowedLine(out, ((x1 + x2) // 2, y), (x2, y), col, 2, tipLength=0.03)
            label = f"GAUGE {gauge:.0f} mm ({gauge - C.NOMINAL_GAUGE_MM:+.0f})"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cx = (x1 + x2) // 2 - tw // 2
            cv2.rectangle(out, (cx - 6, y - th - 14), (cx + tw + 6, y - 6), (20, 20, 20), -1)
            cv2.putText(out, label, (cx, y - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2, cv2.LINE_AA)
        for c in cracks:
            x, y, w, h = c.box
            col = SEV_COLOR[c.severity]
            cv2.rectangle(out, (x - 6, y - 6), (x + w + 6, y + h + 6), col, 2)
            lab = f"CRACK {c.severity} {c.frac * 100:.0f}%"
            tx = x + w + 12 if c.rail == "L" else x - 12 - cv2.getTextSize(lab, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
            (tw, th), _ = cv2.getTextSize(lab, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(out, (tx - 4, y - th - 4), (tx + tw + 4, y + 4), col, -1)
            cv2.putText(out, lab, (tx, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(out, "TRACK CAM (down-looking)", (10, C.CAM_H - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (255, 255, 255), 1, cv2.LINE_AA)
        return out

    def annotate_front(self, img, od, rng):
        out = img.copy()
        ov = out.copy()
        cv2.fillPoly(ov, [self.obst.poly], (0, 200, 255) if od else (0, 255, 120))
        out = cv2.addWeighted(ov, 0.12, out, 0.88, 0)
        cv2.polylines(out, [self.obst.poly], True, (0, 255, 120), 1, cv2.LINE_AA)
        if od:
            x, y, w, h = od.box
            stop = od.est_dist_m < C.OBSTACLE_STOP_M or rng < C.OBSTACLE_STOP_M
            col = (40, 40, 235) if stop else (0, 165, 255)
            cv2.rectangle(out, (x - 4, y - 4), (x + w + 4, y + h + 4), col, 2)
            lab = f"OBSTACLE {od.est_dist_m:.1f} m"
            tw = cv2.getTextSize(lab, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0][0]
            cv2.rectangle(out, (x - 4, max(0, y - 24)), (x + tw + 4, max(18, y - 4)), col, -1)
            cv2.putText(out, lab, (x, max(14, y - 9)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1,
                        cv2.LINE_AA)
        cv2.putText(out, "FRONT CAM", (8, C.FRONT_H - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1,
                    cv2.LINE_AA)
        return out
