"""Generates docs/block_diagram.png and docs/flowchart.png for the report / PPT."""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FD = "/usr/share/fonts/truetype/dejavu/"


def f(sz, b=False):
    try:
        return ImageFont.truetype(FD + ("DejaVuSans-Bold.ttf" if b else "DejaVuSans.ttf"), sz)
    except OSError:
        return ImageFont.load_default()


INK, MUTED = (30, 38, 50), (100, 110, 125)


def box(d, xy, title, lines=(), fill=(232, 241, 250), edge=(60, 110, 170)):
    d.rounded_rectangle(xy, 10, fill=fill, outline=edge, width=2)
    x0, y0, x1, y1 = xy
    tw = d.textlength(title, font=f(15, True))
    d.text(((x0 + x1 - tw) / 2, y0 + 8), title, font=f(15, True), fill=INK)
    for i, ln in enumerate(lines):
        lw = d.textlength(ln, font=f(12))
        d.text(((x0 + x1 - lw) / 2, y0 + 32 + i * 17), ln, font=f(12), fill=MUTED)


def arrow(d, p0, p1, label=None, both=False):
    d.line([p0, p1], fill=INK, width=2)
    import math
    for a, b in ((p0, p1),) + (((p1, p0),) if both else ()):
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        pts = [b, (b[0] - 11 * math.cos(ang - 0.4), b[1] - 11 * math.sin(ang - 0.4)),
               (b[0] - 11 * math.cos(ang + 0.4), b[1] - 11 * math.sin(ang + 0.4))]
        d.polygon(pts, fill=INK)
    if label:
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        d.text((mx + 6, my - 16), label, font=f(11), fill=(180, 80, 30))


def block_diagram():
    W, H = 1600, 900
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.text((40, 24), "Rail Track Inspection Robot - System Block Diagram", font=f(26, True), fill=INK)

    sens = [
        ("Track Camera", ["down-looking, 720p", "+ LED ring light"]),
        ("Front Camera", ["obstacle view"]),
        ("Ultrasonic x2", ["HC-SR04 front/rear"]),
        ("IR Sensors x2", ["TCRT5000 on rails"]),
        ("MPU6050 IMU", ["vibration + tilt"]),
        ("Wheel Encoder", ["600 PPR, distance"]),
        ("GPS NEO-6M", ["location"]),
    ]
    green = ((232, 248, 236), (60, 150, 90))
    for i, (t, l) in enumerate(sens):
        y = 90 + i * 110
        box(d, (40, y, 300, y + 85), t, l, *green)

    box(d, (470, 180, 790, 420), "Raspberry Pi 5", ["OpenCV vision pipeline", "crack + gauge detection",
                                                     "obstacle detection", "control state machine",
                                                     "defect log + GPS tag", "Flask web dashboard",
                                                     "report generator"])
    box(d, (470, 520, 790, 720), "ESP32 Controller", ["motor PI speed control", "encoder counting",
                                                       "ultrasonic hard-stop", "IMU / IR / battery",
                                                       "watchdog + E-stop"])
    # sensors -> computers
    for i in range(2):
        arrow(d, (300, 132 + i * 110), (470, 250 + i * 60), "USB/CSI" if i == 0 else None)
    for i in range(2, 6):
        arrow(d, (300, 132 + i * 110), (470, 560 + (i - 2) * 40))
    arrow(d, (300, 132 + 6 * 110), (470, 380), "UART")
    arrow(d, (630, 420), (630, 520), "USB serial JSON", both=True)

    orange = ((253, 240, 228), (210, 120, 40))
    box(d, (960, 470, 1250, 560), "Motor Driver", ["BTS7960 / L298N"], *orange)
    box(d, (960, 600, 1250, 690), "2x DC Geared Motors", ["12 V, flanged wheels"], *orange)
    box(d, (960, 730, 1250, 820), "Buzzer / Beacon / Paint", ["marker solenoid relay"], *orange)
    arrow(d, (790, 600), (960, 515), "PWM")
    arrow(d, (1105, 560), (1105, 600))
    arrow(d, (790, 680), (960, 775))

    purple = ((240, 234, 252), (120, 80, 190))
    box(d, (960, 120, 1250, 220), "Wi-Fi / 4G Router", ["telemetry link"], *purple)
    box(d, (1320, 90, 1570, 250), "Control Room", ["live web dashboard", "defect map + alerts",
                                                    "CSV / PDF reports", "manual override"], *purple)
    box(d, (960, 270, 1250, 370), "GSM SIM800L", ["SMS alert (critical)"], *purple)
    arrow(d, (790, 250), (960, 170))
    arrow(d, (1250, 170), (1320, 170), both=True)
    arrow(d, (790, 330), (960, 320))

    grey = ((240, 240, 240), (120, 120, 120))
    box(d, (1320, 470, 1570, 600), "Power", ["3S Li-ion 12 V 10 Ah", "BMS + fuse", "5 V 5 A buck -> Pi"], *grey)
    arrow(d, (1320, 535), (1250, 535))
    img.save(os.path.join(HERE, "block_diagram.png"))


def flowchart():
    W, H = 1000, 1350
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.text((40, 20), "Inspection Algorithm - Flowchart", font=f(24, True), fill=INK)
    cx = 380
    steps = [
        ("START", "oval"),
        ("Initialise cameras, ESP32, GPS", "box"),
        ("Operator presses START AUTO", "box"),
        ("Capture track + front frames,\nread sensors (encoder, ultrasonic, IMU)", "box"),
        ("Locate rails -> measure gauge", "box"),
        ("Black-hat filter on rail head\n-> crack candidates -> shape test", "box"),
        ("Obstacle in front camera\nor range < 2 m ?", "dia"),
        ("Defect found ?", "dia"),
        ("Log defect: chainage + GPS +\nphoto, alert if CRITICAL", "box"),
        ("Drive at cruise speed", "box"),
        ("End of section ?", "dia"),
        ("Generate report, STOP", "oval"),
    ]
    ys = []
    y = 80
    for text, kind in steps:
        h = 70 if kind != "dia" else 96
        ys.append((y, h))
        y += h + 26
    for i, ((text, kind), (y, h)) in enumerate(zip(steps, ys)):
        w = 330
        x0, x1 = cx - w / 2, cx + w / 2
        if kind == "oval":
            d.rounded_rectangle((x0 + 60, y, x1 - 60, y + h), 35, fill=(225, 240, 230), outline=(60, 150, 90), width=2)
        elif kind == "dia":
            d.polygon([(cx, y), (x1 + 20, y + h / 2), (cx, y + h), (x0 - 20, y + h / 2)], fill=(253, 243, 225),
                      outline=(210, 140, 40), width=2)
        else:
            d.rounded_rectangle((x0, y, x1, y + h), 8, fill=(232, 241, 250), outline=(60, 110, 170), width=2)
        lines = text.split("\n")
        for j, ln in enumerate(lines):
            lw = d.textlength(ln, font=f(13))
            d.text((cx - lw / 2, y + h / 2 - 9 * len(lines) + j * 18), ln, font=f(13), fill=INK)
        if i < len(steps) - 1:
            arrow(d, (cx, y + h), (cx, ys[i + 1][0]), {6: "No", 7: "Yes", 10: "Yes"}.get(i))
    # side branches
    oy, oh = ys[6]
    d.rounded_rectangle((640, oy + 10, 960, oy + oh - 10), 8, fill=(252, 232, 232), outline=(200, 60, 60), width=2)
    d.text((655, oy + 22), "far: SLOW DOWN", font=f(13, True), fill=INK)
    d.text((655, oy + 44), "near: EMERGENCY STOP, alert,", font=f(13), fill=INK)
    d.text((655, oy + 62), "wait until clear for 2 s", font=f(13), fill=INK)
    arrow(d, (cx + 185, oy + oh / 2), (640, oy + oh / 2), "Yes")
    dy, dh = ys[7]
    d.line([(cx + 185, dy + dh / 2), (cx + 230, dy + dh / 2)], fill=INK, width=2)
    d.text((cx + 192, dy + dh / 2 - 16), "No", font=f(11), fill=(180, 80, 30))
    d.line([(cx + 230, dy + dh / 2), (cx + 230, ys[9][0] + 35)], fill=INK, width=2)
    arrow(d, (cx + 230, ys[9][0] + 35), (cx + 165, ys[9][0] + 35))
    # loop back
    ey, eh = ys[10]
    d.line([(cx - 185, ey + eh / 2), (60, ey + eh / 2), (60, ys[3][0] + 35)], fill=INK, width=2)
    arrow(d, (60, ys[3][0] + 35), (cx - 165, ys[3][0] + 35))
    d.text((70, ey + eh / 2 - 18), "No (next frame)", font=f(11), fill=(180, 80, 30))
    img.save(os.path.join(HERE, "flowchart.png"))


if __name__ == "__main__":
    block_diagram()
    flowchart()
    print("written block_diagram.png and flowchart.png")
