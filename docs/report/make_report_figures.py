"""Module architecture figures for the TrackBot project report (Fig 5.1.1 - 5.1.9)."""
import math
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "figures")
FD = "/usr/share/fonts/truetype/dejavu/"
INK, MUTED, EDGE, FILL = (35, 40, 48), (95, 102, 112), (70, 78, 90), (244, 246, 249)


def f(sz, b=False):
    try:
        return ImageFont.truetype(FD + ("DejaVuSans-Bold.ttf" if b else "DejaVuSans.ttf"), sz)
    except OSError:
        return ImageFont.load_default()


def arrow(d, p0, p1, w=2):
    d.line([p0, p1], fill=INK, width=w)
    a = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    d.polygon([p1, (p1[0] - 11 * math.cos(a - .4), p1[1] - 11 * math.sin(a - .4)),
               (p1[0] - 11 * math.cos(a + .4), p1[1] - 11 * math.sin(a + .4))], fill=INK)


def box(d, xy, title, lines=(), fill=FILL):
    d.rounded_rectangle(xy, 10, fill=fill, outline=EDGE, width=2)
    x0, y0, x1, y1 = xy
    words, rows, cur = title.split(), [], ""
    for wd in words:
        if d.textlength(cur + " " + wd, font=f(19, True)) > x1 - x0 - 16 and cur:
            rows.append(cur)
            cur = wd
        else:
            cur = (cur + " " + wd).strip()
    rows.append(cur)
    y = y0 + 10
    for r in rows:
        d.text(((x0 + x1 - d.textlength(r, font=f(19, True))) / 2, y), r, font=f(19, True), fill=INK)
        y += 24
    y += 4
    for ln in lines:
        d.text((x0 + 10, y), "• " + ln, font=f(16), fill=MUTED)
        y += 21


def pipeline(name, inp, steps, out, feedback=None, h=150):
    """Horizontal pipeline of numbered steps with an input on the left and output on the right."""
    n = len(steps)
    bw, gap = 250, 40
    W = 60 + n * bw + (n - 1) * gap + 60
    H = h + 190
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.text((40, 16), "Input: " + inp, font=f(19, True), fill=INK)
    ow = d.textlength("Output: " + out, font=f(19, True))
    d.text((W - 40 - ow, 16), "Output: " + out, font=f(19, True), fill=INK)
    y0 = 80
    xs = []
    for i, (t, lines) in enumerate(steps):
        x0 = 60 + i * (bw + gap)
        xs.append(x0)
        box(d, (x0, y0, x0 + bw, y0 + h), f"{i + 1}. {t}", lines)
        if i:
            arrow(d, (x0 - gap, y0 + h // 2), (x0, y0 + h // 2))
    arrow(d, (60 + 30, 45), (60 + 30, y0))
    arrow(d, (xs[-1] + bw - 30, y0), (xs[-1] + bw - 30, 45))
    if feedback:
        fy = y0 + h + 45
        d.line([(xs[-1] + bw // 2, y0 + h), (xs[-1] + bw // 2, fy), (xs[0] + bw // 2, fy)], fill=MUTED, width=2)
        arrow(d, (xs[0] + bw // 2, fy), (xs[0] + bw // 2, y0 + h), 2)
        tw = d.textlength(feedback, font=f(17))
        d.rectangle(((W - tw) / 2 - 8, fy - 10, (W + tw) / 2 + 8, fy + 10), fill="white")
        d.text(((W - tw) / 2, fy - 10), feedback, font=f(17), fill=MUTED)
    img.save(os.path.join(OUT, name))


def integration():
    W, H = 1500, 760
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    mods = {
        "m1": ((60, 300, 300, 420), "1. Track Image Acquisition", ["Track cam + LED", "Front cam"]),
        "m2": ((380, 120, 640, 240), "2. Rail Localization & Gauge", ["Band profiles", "Gauge (mm)"]),
        "m3": ((380, 300, 640, 420), "3. Crack Detection", ["Black-hat filter", "Shape test, severity"]),
        "m4": ((380, 480, 640, 600), "4. Obstacle Detection", ["Corridor segmentation", "Range fusion"]),
        "m6": ((740, 210, 1000, 330), "6. Localization & Defect Logging", ["Chainage + GPS", "De-duplication"]),
        "m5": ((740, 450, 1000, 570), "5. Motion Control & Navigation", ["State machine", "PI speed control"]),
        "m7": ((1100, 210, 1440, 330), "7. Alert, Dashboard & Report", ["Live web UI", "CSV / PDF report"]),
        "m8": ((1100, 450, 1440, 570), "8. Safety & Fail-safe", ["ESP32 hard-stop", "Watchdog, E-stop"]),
    }
    for k, (xy, t, l) in mods.items():
        box(d, xy, t, l, (236, 243, 250) if k in ("m2", "m3", "m4") else FILL)
    d.text((60, 250), "Input: track & front", font=f(14, True), fill=INK)
    d.text((60, 268), "camera frames, sensors", font=f(14, True), fill=INK)
    arrow(d, (300, 340), (380, 180))
    arrow(d, (300, 360), (380, 360))
    arrow(d, (300, 380), (380, 540))
    arrow(d, (640, 180), (740, 250))
    arrow(d, (640, 360), (740, 290))
    arrow(d, (640, 540), (740, 510))
    arrow(d, (640, 560), (740, 300))
    arrow(d, (1000, 270), (1100, 270))
    arrow(d, (1000, 510), (1100, 510))
    arrow(d, (1270, 330), (1270, 450))
    d.text((1280, 380), "alerts / stop", font=f(12), fill=MUTED)
    d.line([(1440, 270), (1470, 270), (1470, 680), (870, 680), (870, 570)], fill=MUTED, width=2)
    arrow(d, (870, 600), (870, 570))
    d.text((960, 655), "Operator commands: start / stop / manual drive", font=f(13), fill=MUTED)
    d.text((1150, 160), "Output: control-room dashboard", font=f(14, True), fill=INK)
    d.text((1150, 178), "and inspection report", font=f(14, True), fill=INK)
    img.save(os.path.join(OUT, "fig_5_1_9.png"))


def main():
    os.makedirs(OUT, exist_ok=True)
    pipeline("fig_5_1_1.png", "Track surface & scene ahead",
             [("Illumination", ["LED ring light", "Constant exposure"]),
              ("Down-looking Camera", ["720x480 frames", "Top view of rails"]),
              ("Front Camera", ["480x270 frames", "Track ahead"]),
              ("Frame Pre-processing", ["Resize, grayscale", "Noise smoothing"]),
              ("Frame Buffer", ["Time-stamped", "Encoder position"])],
             "Synchronised frames", feedback="Frame rate adapts to robot speed")
    pipeline("fig_5_1_2.png", "Grayscale track frame",
             [("Band Splitting", ["8 horizontal bands", "per frame"]),
              ("Brightness Profile", ["Column mean", "High-pass filter"]),
              ("Rail Head Runs", ["~72 mm wide runs", "Nearest to expected"]),
              ("Outlier Rejection", ["Median check", "Drop bad bands"]),
              ("Gauge Computation", ["Centre-to-centre", "mm/px calibration"])],
             "Gauge (mm) + rail mask", feedback="Rail positions guide next frame's search")
    pipeline("fig_5_1_3.png", "Frame + rail mask",
             [("Gaussian Blur", ["3x3 kernel", "Sensor noise"]),
              ("Black-hat Filter", ["Closing - image", "3x11 kernel"]),
              ("Threshold & Mask", ["Rail head only", "Binary candidates"]),
              ("Shape Test", ["Length >= 35 %", "Aspect >= 1.8"]),
              ("Severity Grading", ["MINOR / MAJOR", "CRITICAL"])],
             "Crack detections", feedback="Rust and grease stains rejected (round blobs)")
    pipeline("fig_5_1_4.png", "Front frame + range sensor",
             [("Track Corridor", ["Perspective polygon", "Rail bed region"]),
              ("Colour Anomaly", ["HSV saturation", "Sky/vegetation removed"]),
              ("Blob Analysis", ["Morphology", "Connected parts"]),
              ("Distance Estimate", ["d = f.h / (y - y_h)", "Ground contact"]),
              ("Range Fusion", ["Ultrasonic < 4 m", "Stop / slow flag"])],
             "Obstacle distance & state")
    pipeline("fig_5_1_5.png", "Obstacle state, operator command",
             [("State Machine", ["Inspect / Slow / Stop", "Manual / Complete"]),
              ("Target Speed", ["Cruise 1.2 m/s", "Slow 45 %, Stop 0"]),
              ("Serial Command", ["JSON over USB", "to ESP32"]),
              ("PI Speed Control", ["Encoder feedback", "50 Hz loop"]),
              ("Motor Driver", ["BTS7960 PWM", "2x DC motors"])],
             "Controlled robot motion", feedback="Wheel encoder speed feedback")
    pipeline("fig_5_1_6.png", "Per-frame detections",
             [("Position Mapping", ["Encoder + pixel", "offset to metres"]),
              ("Frame Confirmation", ["Seen in >= 2 frames", "Noise rejected"]),
              ("Merging", ["Within 30 cm", "Same rail"]),
              ("Geo-tagging", ["Chainage (km)", "GPS lat/lon"]),
              ("Evidence", ["Photo close-up", "Severity, time"])],
             "Unique defect records")
    pipeline("fig_5_1_7.png", "Defect log, live telemetry",
             [("Alert Engine", ["Critical events", "Control-room alert"]),
              ("Flask Server", ["REST API", "MJPEG streams"]),
              ("Web Dashboard", ["Cameras, tiles", "Map, event log"]),
              ("Operator Control", ["Start / Stop", "Manual drive"]),
              ("Report Generator", ["CSV / JSON", "HTML-PDF + photos"])],
             "Dashboard & inspection report", feedback="Operator commands return to the robot")
    pipeline("fig_5_1_8.png", "Sensors, commands, heartbeat",
             [("Watchdog", ["1 s command timeout", "Auto stop"]),
              ("Ultrasonic Hard-stop", ["Front & rear", "< 1.5 m"]),
              ("E-stop Button", ["NC mushroom", "Cuts drive"]),
              ("Battery Monitor", ["Voltage divider", "Low-battery alarm"]),
              ("Buzzer & Beacon", ["Audible / visual", "Paint marker"])],
             "Safe robot state", feedback="Runs on the ESP32 even if the Pi fails")
    integration()
    print("figures written to", OUT)


if __name__ == "__main__":
    main()
