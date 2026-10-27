"""Computer-vision pipeline (works the same on simulated and real camera frames).

RailAnalyzer      - finds both rails, measures track gauge, detects rail-head cracks
ObstacleDetector  - finds objects inside the track corridor in the front camera
"""
from dataclasses import dataclass

import cv2
import numpy as np

from . import config as C


@dataclass
class RailBand:
    y0: int
    y1: int
    left: tuple | None      # (x_start, x_end) of the left rail head
    right: tuple | None
    gauge_mm: float | None


@dataclass
class CrackDet:
    rail: str
    box: tuple              # x, y, w, h in image pixels
    frac: float             # crack length / rail head width
    severity: str
    row: int                # image row of the crack centre


@dataclass
class ObstacleDet:
    box: tuple
    est_dist_m: float
    area: int


def severity_from_frac(frac):
    if frac >= C.CRACK_CRITICAL_FRAC:
        return "CRITICAL"
    if frac >= C.CRACK_MAJOR_FRAC:
        return "MAJOR"
    return "MINOR"


class RailAnalyzer:
    def __init__(self, n_bands=8):
        self.n_bands = n_bands
        self.rail_w_px = C.RAIL_HEAD_MM / C.MM_PER_PX
        self.k_close = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 11))

    # ---------------------------------------------------------------- rails
    def _runs(self, mask):
        runs, start = [], None
        for x, v in enumerate(mask):
            if v and start is None:
                start = x
            elif not v and start is not None:
                runs.append((start, x))
                start = None
        if start is not None:
            runs.append((start, len(mask)))
        return runs

    def find_rails(self, gray):
        h, w = gray.shape
        bands = []
        bh = h // self.n_bands
        rw = self.rail_w_px
        exp_l = C.LEFT_RAIL_X + rw / 2
        exp_r = exp_l + rw + C.NOMINAL_GAUGE_MM / C.MM_PER_PX
        search = 60 / C.MM_PER_PX * 1.0 + 15     # +/- search window in px
        for i in range(self.n_bands):
            y0, y1 = i * bh, (i + 1) * bh
            prof = gray[y0:y1].mean(axis=0).astype(np.float32)
            base = cv2.blur(prof.reshape(1, -1), (61, 1)).ravel()
            hp = prof - base
            runs = [r for r in self._runs(hp > 12) if 0.6 * rw <= (r[1] - r[0]) <= 1.6 * rw]

            def pick(expected):
                near = [r for r in runs if abs((r[0] + r[1]) / 2 - expected) < search]
                return min(near, key=lambda r: abs((r[0] + r[1]) / 2 - expected)) if near else None

            left, right = pick(exp_l), pick(exp_r)
            bands.append(RailBand(y0, y1, left, right, self._gauge(left, right)))

        # reject bands that disagree with the frame median (bad lighting, debris)
        for side in ("left", "right"):
            cs = [(getattr(b, side)[0] + getattr(b, side)[1]) / 2 for b in bands if getattr(b, side)]
            if cs:
                med = np.median(cs)
                for b in bands:
                    r = getattr(b, side)
                    if r and abs((r[0] + r[1]) / 2 - med) > 8:
                        setattr(b, side, None)
                        b.gauge_mm = None
        for b in bands:
            b.gauge_mm = self._gauge(b.left, b.right)
        return bands

    @staticmethod
    def _gauge(left, right):
        """Inner-face gauge from rail-head centres (robust to edge shading)."""
        if not (left and right):
            return None
        cl, cr = (left[0] + left[1]) / 2, (right[0] + right[1]) / 2
        return (cr - cl) * C.MM_PER_PX - C.RAIL_HEAD_MM

    @staticmethod
    def gauge_from_bands(bands):
        g = [b.gauge_mm for b in bands if b.gauge_mm is not None]
        return float(np.median(g)) if g else None

    # --------------------------------------------------------------- cracks
    def find_cracks(self, gray, bands):
        h, w = gray.shape
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        # black-hat = closing - image  -> bright where thin dark lines are
        bh = cv2.morphologyEx(blur, cv2.MORPH_BLACKHAT, self.k_close)
        _, th = cv2.threshold(bh, 55, 255, cv2.THRESH_BINARY)

        dets = []
        for side in ("L", "R"):
            mask = np.zeros_like(th)
            widths = []
            for b in bands:
                r = b.left if side == "L" else b.right
                if r:
                    # run excludes the 2 px dark chamfer on each side of the head
                    mask[b.y0:b.y1, max(0, r[0] - 2):r[1] + 2] = 255
                    widths.append(r[1] - r[0] + 4)
            if not widths:
                continue
            head_w = float(np.median(widths))
            cand = cv2.bitwise_and(th, mask)
            cand = cv2.morphologyEx(cand, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1)))
            n, lab, stats, cent = cv2.connectedComponentsWithStats(cand, 8)
            for j in range(1, n):
                x, y, bw, bh_, area = stats[j]
                if area < 8:
                    continue
                frac = min(1.0, bw / head_w)
                aspect = bw / max(1, bh_)
                # Cracks run ACROSS the rail: wide and thin.  Rust / grease
                # stains are round blobs -> rejected by the aspect test.
                if frac >= C.CRACK_MINOR_FRAC and aspect >= 1.8 and bh_ <= 10:
                    dets.append(CrackDet(side, (int(x), int(y), int(bw), int(bh_)), frac,
                                         severity_from_frac(frac), int(cent[j][1])))
        return dets

    def analyze(self, frame_bgr):
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        bands = self.find_rails(gray)
        gauge = self.gauge_from_bands(bands)
        cracks = self.find_cracks(gray, bands)
        return bands, gauge, cracks


class ObstacleDetector:
    """Colour/texture anomaly inside the track corridor.

    On the real robot you can swap `detect()` for a YOLO model
    (see README "Upgrading to deep learning").
    """

    def __init__(self):
        W, H, hy, f, ch = C.FRONT_W, C.FRONT_H, C.FRONT_HORIZON_Y, C.FRONT_FOCAL_PX, C.FRONT_CAM_HEIGHT_M
        cx = W // 2

        def proj(d, x):
            return int(cx + f * x / d), int(hy + f * ch / d)

        poly = np.array([proj(40, -1.4), proj(40, 1.4), proj(0.55, 1.4), proj(0.55, -1.4)], np.int32)
        self.corridor = np.zeros((H, W), np.uint8)
        cv2.fillPoly(self.corridor, [poly], 255)
        # allow tall objects (people) whose upper body is above the corridor
        self.corridor_tall = self.corridor.copy()
        for x in range(W):
            col = np.where(self.corridor[:, x] > 0)[0]
            if len(col):
                self.corridor_tall[:col[0], x] = 255
        self.poly = poly

    def detect(self, frame_bgr):
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        sat = hsv[..., 1]
        m = (sat > 85).astype(np.uint8) * 255
        m = cv2.bitwise_and(m, self.corridor_tall)
        hue = hsv[..., 0]
        m[(hue > 90) & (hue < 130)] = 0      # sky
        m[(hue > 35) & (hue < 85)] = 0       # vegetation
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        n, lab, stats, cent = cv2.connectedComponentsWithStats(m, 8)
        best = None
        for j in range(1, n):
            x, y, w, h, area = stats[j]
            if area < 12:
                continue
            bottom = y + h
            if self.corridor[min(bottom - 1, C.FRONT_H - 1), min(x + w // 2, C.FRONT_W - 1)] == 0:
                continue   # foot of the object must be on the track bed
            dy = max(1, bottom - C.FRONT_HORIZON_Y)
            dist = C.FRONT_FOCAL_PX * C.FRONT_CAM_HEIGHT_M / dy
            if best is None or dist < best.est_dist_m:
                best = ObstacleDet((int(x), int(y), int(w), int(h)), float(dist), int(area))
        return best
