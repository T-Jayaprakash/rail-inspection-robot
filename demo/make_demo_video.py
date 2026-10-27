"""Render a full demonstration video of an autonomous inspection run.

    python demo/make_demo_video.py                      # 80 m demo track -> output/demo_inspection.mp4
    python demo/make_demo_video.py --length 150 --random --seed 3

The robot, cameras and sensors are simulated, but every detection you see
in the video is produced by the real vision + control code in rail_inspector/.
"""
import argparse
import os
import subprocess
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rail_inspector import config as C                     # noqa: E402
from rail_inspector.engine import InspectionEngine         # noqa: E402
from rail_inspector.sources import SimSource               # noqa: E402
from rail_inspector.track_world import TrackWorld          # noqa: E402
from rail_inspector.report import write_reports            # noqa: E402

W, H, FPS = 1280, 720, 30
FONT_DIR = "/usr/share/fonts/truetype/dejavu/"


def font(size, bold=False):
    for name in (("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),):
        try:
            return ImageFont.truetype(os.path.join(FONT_DIR, name), size)
        except OSError:
            pass
    return ImageFont.load_default()


F = {k: font(*v) for k, v in {
    "title": (22, True), "h": (15, True), "s": (12, False), "sb": (12, True), "xs": (10, False),
    "big": (26, True), "mid": (18, True), "huge": (44, True), "lg": (30, True), "m": (16, False),
}.items()}

BG = (13, 17, 23)
PANEL = (22, 28, 37)
EDGE = (45, 55, 70)
TXT = (230, 236, 243)
MUTED = (140, 152, 168)
GREEN = (63, 200, 120)
AMBER = (245, 170, 40)
ORANGE = (255, 130, 40)
RED = (235, 64, 64)
CYAN = (60, 190, 230)
SEV_RGB = {"MINOR": (255, 205, 60), "MAJOR": ORANGE, "CRITICAL": RED}
STATUS_RGB = {"INSPECTING": GREEN, "SLOWING": AMBER, "OBSTACLE_STOP": RED, "COMPLETED": CYAN,
              "IDLE": MUTED, "PAUSED": AMBER, "MANUAL": CYAN}


def bgr2pil(img, size=None):
    if size:
        img = cv2.resize(img, size, interpolation=cv2.INTER_AREA)
    return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))


def panel(d, box, title=None):
    x0, y0, x1, y1 = box
    d.rounded_rectangle(box, 8, fill=PANEL, outline=EDGE)
    if title:
        d.text((x0 + 10, y0 + 7), title, font=F["sb"], fill=MUTED)


class Hud:
    def __init__(self, eng: InspectionEngine, world: TrackWorld):
        self.e = eng
        self.w = world
        self.last_crack = None
        self.flash = None          # (until_t, text, colour)
        self.seen_msgs = 0

    def tile(self, d, box, label, value, unit="", colour=TXT, sub=None, bar=None):
        panel(d, box)
        x0, y0, x1, y1 = box
        d.text((x0 + 10, y0 + 6), label, font=F["s"], fill=MUTED)
        d.text((x0 + 10, y0 + 24), value, font=F["big"], fill=colour)
        if unit:
            vw = d.textlength(value, font=F["big"])
            d.text((x0 + 14 + vw, y0 + 36), unit, font=F["s"], fill=MUTED)
        if sub:
            d.text((x0 + 10, y1 - (30 if bar is not None else 20)), sub, font=F["xs"], fill=MUTED)
        if bar is not None:
            frac, col = bar
            d.rounded_rectangle((x0 + 10, y1 - 12, x1 - 10, y1 - 7), 2, fill=(40, 48, 60))
            d.rounded_rectangle((x0 + 10, y1 - 12, x0 + 10 + int((x1 - x0 - 20) * max(0.02, min(1, frac))), y1 - 7),
                                2, fill=col)

    def frame(self, s):
        e = self.e
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)

        # --------------------------------------------------------- header
        d.rectangle((0, 0, W, 52), fill=(18, 23, 31))
        d.line((0, 52, W, 52), fill=EDGE)
        d.text((18, 9), "RAIL TRACK INSPECTION ROBOT", font=F["title"], fill=TXT)
        d.text((18, 33), "Autonomous crack | gauge | obstacle detection  -  Control Room Dashboard",
               font=F["s"], fill=MUTED)
        st = s["status"]
        col = STATUS_RGB.get(st, TXT)
        label = s["status_text"]
        tw = d.textlength(label, font=F["h"])
        blink = st != "OBSTACLE_STOP" or int(s["t"] * 3) % 2 == 0
        d.rounded_rectangle((W - 30 - tw - 34, 12, W - 18, 41), 14, fill=col if blink else PANEL, outline=col)
        d.ellipse((W - 30 - tw - 22, 22, W - 30 - tw - 12, 32), fill=(255, 255, 255) if blink else col)
        d.text((W - 26 - tw, 18), label, font=F["h"], fill=(10, 10, 10) if blink else col)
        d.text((W - 30 - tw - 200, 14), f"MODE: {s['source']}", font=F["sb"], fill=MUTED)
        mm, ss = divmod(int(s["t"]), 60)
        d.text((W - 30 - tw - 200, 30), f"RUN TIME  {mm:02d}:{ss:02d}", font=F["sb"], fill=MUTED)

        # ----------------------------------------------------- track camera
        tx, ty, tw_, th_ = 16, 64, 640, 427
        img.paste(bgr2pil(e.track_annot, (tw_, th_)), (tx, ty))
        d.rectangle((tx - 1, ty - 1, tx + tw_, ty + th_), outline=EDGE)
        d.rounded_rectangle((tx + 8, ty + 8, tx + 168, ty + 30), 6, fill=(0, 0, 0))
        d.ellipse((tx + 16, ty + 15, tx + 24, ty + 23), fill=RED if int(s["t"] * 2) % 2 else (120, 30, 30))
        d.text((tx + 30, ty + 12), "LIVE  TRACK CAMERA", font=F["sb"], fill=TXT)

        # flash banner for new critical events
        if self.flash and s["t"] < self.flash[0]:
            _, text, fcol = self.flash
            d.rectangle((tx, ty + th_ - 44, tx + tw_, ty + th_), fill=fcol)
            d.text((tx + 14, ty + th_ - 34), text, font=F["mid"], fill=(255, 255, 255))

        # ----------------------------------------------------- front camera
        fx, fy, fw, fh = 672, 64, 400, 225
        img.paste(bgr2pil(e.front_annot, (fw, fh)), (fx, fy))
        d.rectangle((fx - 1, fy - 1, fx + fw, fy + fh), outline=EDGE)
        d.rounded_rectangle((fx + 6, fy + 6, fx + 176, fy + 26), 6, fill=(0, 0, 0))
        d.text((fx + 14, fy + 9), "FRONT OBSTACLE CAM", font=F["sb"], fill=TXT)

        # ------------------------------------------------- crack close-up
        cx0, cy0, cx1, cy1 = 1084, 64, 1264, 289
        panel(d, (cx0, cy0, cx1, cy1), "LAST DEFECT CLOSE-UP")
        if self.last_crack is not None and self.last_crack.snapshot is not None:
            snap = self.last_crack.snapshot
            sh, sw = snap.shape[:2]
            k = min(160 / sw, 130 / sh)
            simg = bgr2pil(snap, (max(1, int(sw * k)), max(1, int(sh * k))))
            img.paste(simg, (cx0 + 10 + (160 - simg.width) // 2, cy0 + 28))
            dc = self.last_crack
            colr = SEV_RGB.get(dc.severity, TXT)
            d.text((cx0 + 10, cy0 + 164), f"{dc.type} - {dc.severity}", font=F["sb"], fill=colr)
            d.text((cx0 + 10, cy0 + 180), f"km {dc.chainage_km:.3f}  rail {dc.rail}", font=F["s"], fill=TXT)
            d.text((cx0 + 10, cy0 + 196), f"{dc.lat:.5f}, {dc.lon:.5f}", font=F["xs"], fill=MUTED)
        else:
            d.text((cx0 + 30, cy0 + 105), "no defects yet", font=F["s"], fill=MUTED)

        # ------------------------------------------------------- sensor tiles
        gx, gy, gw, gh, gap = 672, 300, 192, 92, 8
        boxes = [(gx + i * (gw + gap), gy + j * (gh + gap), gx + i * (gw + gap) + gw, gy + j * (gh + gap) + gh)
                 for j in range(2) for i in range(3)]
        sp = s["speed_mps"]
        self.tile(d, boxes[0], "SPEED", f"{sp:.2f}", "m/s", GREEN if sp > 0.05 else MUTED,
                  sub=f"target {s['target_mps']:.2f} m/s", bar=(sp / C.MAX_SPEED_MPS, GREEN))
        self.tile(d, boxes[1], "CHAINAGE", f"{s['chainage_km']:.3f}", "km", TXT,
                  sub=f"travelled {s['pos_m']:.1f} / {s['length_m']:.0f} m",
                  bar=(s['pos_m'] / s['length_m'], CYAN))
        g = s["gauge_mm"]
        gdev = s["gauge_dev_mm"] or 0
        gcol = RED if abs(gdev) > C.GAUGE_TOLERANCE_MM else GREEN
        self.tile(d, boxes[2], "TRACK GAUGE", f"{g:.0f}" if g else "--", "mm", gcol,
                  sub=f"nominal {C.NOMINAL_GAUGE_MM} ({gdev:+.0f} mm)")
        r = s["range_m"]
        rcol = RED if r < C.OBSTACLE_STOP_M else (AMBER if r < C.RANGE_SENSOR_MAX_M - 0.01 else GREEN)
        cam = s["cam_obstacle_m"]
        self.tile(d, boxes[3], "OBSTACLE RANGE", f"{r:.2f}" if r < C.RANGE_SENSOR_MAX_M - 0.01 else "CLEAR",
                  "m" if r < C.RANGE_SENSOR_MAX_M - 0.01 else "", rcol,
                  sub=f"camera: {cam:.1f} m" if cam else "camera: path clear")
        self.tile(d, boxes[4], "VIBRATION (IMU)", f"{s['vibration_g']:.2f}", "g",
                  RED if s["vibration_g"] > 0.25 else TXT)
        vh = list(e.vib_hist)[-80:]
        if len(vh) > 2:
            x0, y0, x1, y1 = boxes[4]
            pts = [(x0 + 100 + i * (82 / 80), y1 - 14 - min(1, v / 0.5) * 50) for i, v in enumerate(vh)]
            d.line(pts, fill=CYAN, width=2)
        bat = s["battery_pct"]
        self.tile(d, boxes[5], "BATTERY", f"{bat:.0f}", "%", GREEN if bat > 30 else RED,
                  sub=f"temp {s['temp_c']:.0f} C", bar=(bat / 100, GREEN if bat > 30 else RED))

        # ------------------------------------------------------- track map
        mx0, my0, mx1, my1 = 16, 503, 860, 704
        panel(d, (mx0, my0, mx1, my1), "TRACK DEFECT MAP  &  GAUGE PROFILE")
        sm = s["summary"]
        legend = [("Crack", RED), ("Gauge fault", AMBER), ("Obstacle", (190, 120, 255)), ("Robot", CYAN)]
        lx = mx1 - 10
        for name, colr in reversed(legend):
            lw = d.textlength(name, font=F["xs"])
            lx -= lw + 22
            d.ellipse((lx, my0 + 10, lx + 9, my0 + 19), fill=colr)
            d.text((lx + 13, my0 + 8), name, font=F["xs"], fill=MUTED)
        L = s["length_m"]
        px0, px1 = mx0 + 50, mx1 - 20

        def X(p):
            return px0 + (px1 - px0) * p / L

        # gauge profile chart
        cy_top, cy_bot = my0 + 32, my0 + 108
        tol = C.GAUGE_TOLERANCE_MM
        rng_mm = 30

        def Y(gv):
            return cy_bot - (gv - (C.NOMINAL_GAUGE_MM - rng_mm)) / (2 * rng_mm) * (cy_bot - cy_top)

        d.rectangle((px0, Y(C.NOMINAL_GAUGE_MM + tol), px1, Y(C.NOMINAL_GAUGE_MM - tol)), fill=(28, 44, 38))
        d.line((px0, Y(C.NOMINAL_GAUGE_MM), px1, Y(C.NOMINAL_GAUGE_MM)), fill=(50, 90, 70))
        for gv in (C.NOMINAL_GAUGE_MM - 20, C.NOMINAL_GAUGE_MM, C.NOMINAL_GAUGE_MM + 20):
            d.text((mx0 + 8, Y(gv) - 7), f"{gv}", font=F["xs"], fill=MUTED)
        prof = e.gauge_profile
        if len(prof) > 1:
            pts = [(X(p), Y(max(C.NOMINAL_GAUGE_MM - rng_mm, min(C.NOMINAL_GAUGE_MM + rng_mm, gv))))
                   for p, gv in prof[::2]]
            d.line(pts, fill=CYAN, width=2)

        # rail strip
        ry = my0 + 140
        d.rounded_rectangle((px0, ry - 9, px1, ry + 9), 4, fill=(38, 46, 58))
        for k in range(0, int(L) + 1, 10):
            d.line((X(k), ry + 10, X(k), ry + 15), fill=MUTED)
            d.text((X(k) - 8, ry + 17), f"{k}m", font=F["xs"], fill=MUTED)
        d.rectangle((px0, ry - 3, X(s["pos_m"]), ry + 3), fill=(40, 120, 150))
        for dft in e.log.confirmed():
            if dft.type == "GAUGE":
                d.rectangle((X(dft.pos_m), ry - 9, X(dft.end_m or dft.pos_m) + 2, ry + 9), fill=AMBER)
        for dft in e.log.confirmed():
            xx = X(dft.pos_m)
            if dft.type == "CRACK":
                colr = SEV_RGB[dft.severity]
                yy = ry - 16 if dft.rail == "L" else ry + 16
                d.polygon([(xx, ry), (xx - 6, yy), (xx + 6, yy)], fill=colr)
            elif dft.type == "OBSTACLE":
                d.rectangle((xx - 5, ry - 24, xx + 5, ry - 14), fill=(190, 120, 255))
        rx = X(s["pos_m"])
        d.polygon([(rx, ry - 12), (rx - 7, ry - 26), (rx + 7, ry - 26)], fill=CYAN)
        d.text((mx0 + 8, ry - 7), "L/R", font=F["xs"], fill=MUTED)

        # counters
        cy = my1 - 30
        items = [("CRACKS", sm["cracks"], RED), ("CRITICAL", sm["critical"], RED),
                 ("GAUGE", sm["gauge"], AMBER), ("OBSTACLES", sm["obstacles"], (190, 120, 255))]
        cxp = mx0 + 50
        for name, val, colr in items:
            d.text((cxp, cy), f"{val}", font=F["mid"], fill=colr)
            d.text((cxp + 24, cy + 5), name, font=F["xs"], fill=MUTED)
            cxp += 130
        d.text((mx1 - 250, cy + 4), f"GPS {s['lat']:.5f}, {s['lon']:.5f}", font=F["s"], fill=MUTED)

        # -------------------------------------------------------- event log
        ex0, ey0, ex1, ey1 = 872, 503, 1264, 704
        panel(d, (ex0, ey0, ex1, ey1), "EVENT LOG")
        lvl_col = {"info": MUTED, "warn": AMBER, "crit": RED, "ok": GREEN}
        yy = ey0 + 28
        for m in list(e.messages)[:8]:
            mm_, ss_ = divmod(int(m["t"]), 60)
            d.text((ex0 + 10, yy), f"{mm_:02d}:{ss_:02d}", font=F["xs"], fill=MUTED)
            txt = m["text"]
            while d.textlength(txt, font=F["s"]) > ex1 - ex0 - 60:
                txt = txt[:-2]
            d.text((ex0 + 48, yy - 1), txt, font=F["s"], fill=lvl_col.get(m["level"], TXT))
            yy += 21
        return img

    def on_step(self, s):
        e = self.e
        conf = e.log.confirmed()
        newest = max((x for x in conf if x.snapshot is not None), key=lambda x: x.t_run, default=None)
        if newest is not None and newest is not self.last_crack:
            self.last_crack = newest
            if newest.type == "CRACK" and newest.severity == "CRITICAL":
                self.flash = (s["t"] + 2.0, f"CRITICAL CRACK  -  km {newest.chainage_km:.3f}  -  alert sent", RED)
            elif newest.type == "OBSTACLE":
                self.flash = (s["t"] + 2.0, "OBSTACLE ON TRACK  -  EMERGENCY STOP", RED)


# ----------------------------------------------------------- title cards
def card_intro(t):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / H
        d.line((0, y, W, y), fill=(int(13 + 12 * k), int(17 + 18 * k), int(23 + 30 * k)))
    a = min(1.0, t / 0.8)
    c = lambda col: tuple(int(v * a + BG[i] * (1 - a)) for i, v in enumerate(col))  # noqa: E731
    d.text((80, 150), "AUTONOMOUS", font=F["lg"], fill=c(CYAN))
    d.text((80, 190), "RAIL TRACK INSPECTION ROBOT", font=F["huge"], fill=c(TXT))
    d.text((80, 255), "Final Year Project  -  Live System Demonstration", font=F["m"], fill=c(MUTED))
    feats = [
        ("Computer-vision crack detection", "rail-head cracks, severity grading, rust/stain rejection"),
        ("Track gauge measurement", f"nominal {C.NOMINAL_GAUGE_MM} mm (BG), +/-{C.GAUGE_TOLERANCE_MM} mm tolerance"),
        ("Obstacle detection & auto-stop", "front camera + ultrasonic / LiDAR range sensor"),
        ("Geo-tagged defect log", "chainage (km) + GPS, alerts to control room, PDF/CSV report"),
    ]
    for i, (h, sub) in enumerate(feats):
        ai = min(1.0, max(0.0, (t - 0.8 - i * 0.35) / 0.5))
        if ai <= 0:
            continue
        cc = lambda col: tuple(int(v * ai + BG[j] * (1 - ai)) for j, v in enumerate(col))  # noqa: E731
        y = 330 + i * 70
        d.rounded_rectangle((80, y, 90, y + 44), 3, fill=cc(GREEN))
        d.text((108, y), h, font=F["mid"], fill=cc(TXT))
        d.text((108, y + 24), sub, font=F["s"], fill=cc(MUTED))
    draw_robot(d, 760, 290, a)
    return img


def draw_robot(d, x, y, a=1.0):
    """Side-view schematic of the robot on the rail."""
    c = lambda col: tuple(int(v * a + BG[i] * (1 - a)) for i, v in enumerate(col))  # noqa: E731
    # rail + sleepers
    d.rectangle((x - 40, y + 250, x + 470, y + 262), fill=c((150, 158, 170)))
    for k in range(-30, 470, 60):
        d.rectangle((x + k, y + 262, x + k + 34, y + 276), fill=c((90, 96, 106)))
    # chassis
    d.rounded_rectangle((x + 40, y + 96, x + 400, y + 210), 12, fill=c((34, 44, 58)), outline=c(CYAN), width=2)
    d.text((x + 64, y + 106), "RAIL INSPECTION ROBOT", font=F["sb"], fill=c(TXT))
    d.text((x + 64, y + 126), "Raspberry Pi 5  +  ESP32", font=F["xs"], fill=c(MUTED))
    d.text((x + 64, y + 141), "2x DC geared motors, encoder", font=F["xs"], fill=c(MUTED))
    d.text((x + 64, y + 156), "Li-ion 3S 12 V pack", font=F["xs"], fill=c(MUTED))
    # wheels
    for wx in (x + 100, x + 340):
        d.ellipse((wx - 38, y + 182, wx + 38, y + 258), fill=c((60, 70, 84)), outline=c((170, 178, 190)), width=3)
        d.ellipse((wx - 8, y + 212, wx + 8, y + 228), fill=c((170, 178, 190)))
    # front camera + range sensor
    d.rounded_rectangle((x + 400, y + 130, x + 440, y + 160), 5, fill=c((20, 26, 34)), outline=c(GREEN), width=2)
    d.ellipse((x + 424, y + 137, x + 438, y + 151), fill=c(GREEN))
    for r in (18, 32, 46):
        d.arc((x + 440 - r, y + 145 - r, x + 440 + r, y + 145 + r), -35, 35, fill=c(GREEN), width=2)
    d.text((x + 380, y + 98), "front cam + ultrasonic", font=F["xs"], fill=c(GREEN))
    # down camera
    d.rectangle((x + 200, y + 210, x + 240, y + 226), fill=c((20, 26, 34)), outline=c(AMBER), width=2)
    d.polygon([(x + 205, y + 226), (x + 235, y + 226), (x + 255, y + 250), (x + 185, y + 250)], fill=c((70, 60, 30)))
    d.text((x + 180, y + 290), "down-looking track camera + LED light", font=F["xs"], fill=c(AMBER))
    # mast: GPS + antenna
    d.line((x + 80, y + 96, x + 80, y + 50), fill=c(MUTED), width=3)
    d.ellipse((x + 68, y + 36, x + 92, y + 60), fill=c(CYAN))
    d.text((x + 100, y + 40), "GPS + 4G/WiFi telemetry", font=F["xs"], fill=c(CYAN))
    d.rectangle((x + 300, y + 74, x + 330, y + 96), fill=c(RED))
    d.text((x + 266, y + 56), "E-stop / beacon", font=F["xs"], fill=c(RED))


def card_summary(eng, world, t, gauge_err):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((60, 40), "INSPECTION REPORT", font=F["lg"], fill=TXT)
    s = eng.last
    d.text((60, 82), f"Section km {C.START_CHAINAGE_KM:.3f} - {s['chainage_km']:.3f}   |   "
                     f"{s['pos_m']:.0f} m inspected in {s['t']:.0f} s   |   source: {s['source']}",
           font=F["m"], fill=MUTED)
    conf = eng.log.confirmed()
    cols = [60, 110, 220, 330, 420, 560]
    hdr = ["#", "TYPE", "CHAINAGE", "RAIL", "SEVERITY", "DETAILS"]
    y = 130
    d.rounded_rectangle((50, y - 8, 1230, y + 22), 6, fill=PANEL)
    for x, h in zip(cols, hdr):
        d.text((x, y - 1), h, font=F["sb"], fill=MUTED)
    y += 30
    shown = int(min(len(conf), t / 0.25 + 1))
    for dft in conf[:shown][:16]:
        colr = SEV_RGB.get(dft.severity, TXT)
        vals = [str(dft.id), dft.type, f"km {dft.chainage_km:.3f}", dft.rail, dft.severity, dft.detail]
        for i, (x, v) in enumerate(zip(cols, vals)):
            d.text((x, y), v, font=F["s"], fill=colr if i == 4 else TXT)
        y += 24
    # accuracy vs ground truth (only possible in simulation)
    truth_c = len(world.cracks)
    found = 0
    for cr in world.cracks:
        if any(x.type == "CRACK" and x.rail == cr.rail and abs(x.pos_m - cr.pos_m) < 0.3 for x in conf):
            found += 1
    false_alarms = sum(1 for x in conf if x.type == "CRACK" and not any(
        x.rail == cr.rail and abs(x.pos_m - cr.pos_m) < 0.3 for cr in world.cracks))
    gfound = sum(1 for g in world.gauge_faults if any(
        x.type == "GAUGE" and x.pos_m < g.end_m and (x.end_m or x.pos_m) > g.start_m for x in conf))
    ofound = sum(1 for o in world.obstacles if any(x.type == "OBSTACLE" and abs(x.pos_m - o.pos_m) < 3 for x in conf))
    by = 560
    d.rounded_rectangle((50, by, 1230, by + 120), 10, fill=PANEL, outline=EDGE)
    d.text((70, by + 12), "VALIDATION AGAINST GROUND TRUTH (simulation)", font=F["sb"], fill=MUTED)
    stats = [
        (f"{found}/{truth_c}", "cracks detected"),
        (f"{false_alarms}", "false alarms"),
        (f"{gfound}/{len(world.gauge_faults)}", "gauge faults"),
        (f"{ofound}/{len(world.obstacles)}", "obstacles stopped"),
        (f"{gauge_err:.1f} mm", "gauge RMS error"),
    ]
    for i, (v, lab) in enumerate(stats):
        x = 70 + i * 232
        d.text((x, by + 40), v, font=F["big"], fill=GREEN)
        d.text((x, by + 76), lab, font=F["s"], fill=MUTED)
    return img


# ------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--length", type=float, default=80.0)
    ap.add_argument("--random", action="store_true", help="random defects instead of the scripted demo")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=os.path.join(ROOT, "output", "demo_inspection.mp4"))
    ap.add_argument("--max-seconds", type=float, default=600)
    args = ap.parse_args()

    world = TrackWorld.random(args.length, args.seed) if args.random else TrackWorld.demo(args.length, args.seed)
    print("Building track world ...")
    src = SimSource(world)
    eng = InspectionEngine(src)
    hud = Hud(eng, world)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                           "-crf", "21", "-pix_fmt", "yuv420p", "-movflags", "+faststart", args.out],
                          stdin=subprocess.PIPE)

    def put(im):
        ff.stdin.write(np.asarray(im, dtype=np.uint8).tobytes())

    for i in range(int(4.5 * FPS)):
        put(card_intro(i / FPS))

    # first live frames while the robot is still idle
    for i in range(int(1.0 * FPS)):
        s = eng.step(1 / FPS)
        put(hud.frame(s))
    eng.command("start")
    t0 = time.time()
    n = 0
    gauge_err = []
    while eng.status != "COMPLETED" and eng.t < args.max_seconds:
        s = eng.step(1 / FPS)
        if s["gauge_mm"] is not None:
            gauge_err.append(s["gauge_mm"] - (C.NOMINAL_GAUGE_MM + world.gauge_offset_mm(s["pos_m"])))
        hud.on_step(s)
        put(hud.frame(s))
        n += 1
        if n % 150 == 0:
            print(f"  t={eng.t:6.1f}s  pos={s['pos_m']:5.1f} m  status={s['status']:<14} "
                  f"defects={s['summary']['total']}  ({n / (time.time() - t0):.1f} fps render)")
    for i in range(int(1.5 * FPS)):
        s = eng.step(1 / FPS)
        put(hud.frame(s))
    rms = float(np.sqrt(np.mean(np.square(gauge_err)))) if gauge_err else 0.0
    for i in range(int(8 * FPS)):
        put(card_summary(eng, world, i / FPS, rms))
    ff.stdin.close()
    ff.wait()

    paths = write_reports(eng, os.path.join(ROOT, "output"))
    print("Video  :", args.out)
    for p in paths:
        print("Report :", p)


if __name__ == "__main__":
    main()
