"""Synthetic railway track used for simulation and demo videos.

The world holds the *ground truth* (where the cracks, gauge faults and
obstacles really are).  The vision code never reads this ground truth -
it only sees the rendered camera images, exactly like on the real robot.
"""
from dataclasses import dataclass, field
import math
import random

import cv2
import numpy as np

from . import config as C


@dataclass
class Crack:
    pos_m: float
    rail: str            # "L" or "R"
    frac: float          # fraction of the rail head the crack runs across
    kind: str = "transverse"


@dataclass
class GaugeFault:
    start_m: float
    end_m: float
    offset_mm: float     # + = wide gauge, - = tight gauge


@dataclass
class Obstacle:
    pos_m: float
    kind: str            # "boulder", "log", "worker"
    clears_after_s: float = 6.0   # removed this long after the robot stops at it
    removed: bool = False
    stopped_since: float | None = None


@dataclass
class Stain:
    pos_m: float
    rail: str
    size_px: int


@dataclass
class TrackWorld:
    length_m: float = 80.0
    seed: int = 7
    cracks: list = field(default_factory=list)
    gauge_faults: list = field(default_factory=list)
    obstacles: list = field(default_factory=list)
    stains: list = field(default_factory=list)

    MARGIN_M = 3.0

    @classmethod
    def demo(cls, length_m=80.0, seed=7):
        w = cls(length_m=length_m, seed=seed)
        w.cracks = [
            Crack(8.4, "L", 0.45),
            Crack(17.9, "R", 0.95),
            Crack(29.3, "L", 0.70),
            Crack(43.6, "R", 0.40),
            Crack(52.2, "L", 1.00),
            Crack(66.8, "R", 0.62),
            Crack(73.5, "L", 0.88),
        ]
        w.gauge_faults = [GaugeFault(22.0, 26.5, +22), GaugeFault(57.0, 60.5, -16)]
        w.obstacles = [Obstacle(36.0, "boulder", 5.0), Obstacle(62.0, "worker", 4.0)]
        w.stains = [Stain(12.0, "R", 8), Stain(33.1, "L", 7), Stain(47.0, "L", 9), Stain(70.2, "R", 8)]
        return w

    @classmethod
    def random(cls, length_m=200.0, seed=None):
        rnd = random.Random(seed)
        w = cls(length_m=length_m, seed=seed or 1)
        n = int(length_m / 11)
        for _ in range(n):
            w.cracks.append(Crack(rnd.uniform(4, length_m - 3), rnd.choice("LR"), rnd.uniform(0.35, 1.0)))
        for _ in range(max(1, int(length_m / 60))):
            s = rnd.uniform(5, length_m - 10)
            w.gauge_faults.append(GaugeFault(s, s + rnd.uniform(2, 5), rnd.choice([-1, 1]) * rnd.uniform(13, 25)))
        for _ in range(max(1, int(length_m / 70))):
            w.obstacles.append(Obstacle(rnd.uniform(15, length_m - 5), rnd.choice(["boulder", "log", "worker"]),
                                        rnd.uniform(3, 6)))
        for _ in range(int(length_m / 15)):
            w.stains.append(Stain(rnd.uniform(3, length_m - 3), rnd.choice("LR"), rnd.randint(6, 10)))
        w.cracks.sort(key=lambda c: c.pos_m)
        w.obstacles.sort(key=lambda o: o.pos_m)
        return w

    # ------------------------------------------------------------- ground truth
    def gauge_offset_mm(self, pos_m):
        """Smoothly ramped gauge deviation at a position (ground truth)."""
        off = 0.0
        for g in self.gauge_faults:
            ramp = 0.8
            if g.start_m - ramp <= pos_m <= g.end_m + ramp:
                k = min(1.0, (pos_m - (g.start_m - ramp)) / ramp, ((g.end_m + ramp) - pos_m) / ramp)
                off += g.offset_mm * max(0.0, k)
        return off

    def next_obstacle(self, pos_m):
        for o in self.obstacles:
            if not o.removed and o.pos_m > pos_m - 0.2:
                return o
        return None


class TrackRenderer:
    """Renders the down-looking and front-looking camera images."""

    def __init__(self, world: TrackWorld):
        self.w = world
        self.rng = np.random.default_rng(world.seed)
        self._build_texture()

    # ----------------------------------------------------------- texture build
    def _mm_to_row(self, mm):
        return int(round((mm + TrackWorld.MARGIN_M * 1000) / C.MM_PER_PX))

    def _build_texture(self):
        s = C.MM_PER_PX
        total_mm = (self.w.length_m + 2 * TrackWorld.MARGIN_M) * 1000
        H, W = int(total_mm / s) + 1, C.CAM_W
        rng = self.rng

        # Ballast: layered noise gives a stony look
        small = rng.integers(70, 125, size=(H // 40 + 2, W // 40 + 2)).astype(np.float32)
        ballast = cv2.resize(small, (W, H), interpolation=cv2.INTER_CUBIC)
        tex = np.stack([ballast * 0.92, ballast * 0.98, ballast * 1.04], axis=-1).astype(np.float32)
        # individual stones with a lit top-left and shadowed bottom-right
        n_st = int(H * W / 110)
        xs = rng.integers(0, W, n_st)
        ys = rng.integers(0, H, n_st)
        ax = rng.integers(3, 8, n_st)
        ay = rng.integers(3, 6, n_st)
        ang = rng.integers(0, 180, n_st)
        shade = rng.integers(65, 150, n_st)
        tint = rng.integers(-5, 6, n_st)
        for i in range(n_st):
            c = int(shade[i])
            cv2.ellipse(tex, (int(xs[i]) + 2, int(ys[i]) + 2), (int(ax[i]), int(ay[i])), int(ang[i]), 0, 360,
                        (c * 0.45, c * 0.45, c * 0.45), -1)
            cv2.ellipse(tex, (int(xs[i]), int(ys[i])), (int(ax[i]), int(ay[i])), int(ang[i]), 0, 360,
                        (float(c - tint[i]), float(c), float(c + tint[i])), -1)
        tex += rng.normal(0, 6, size=(H, W, 1)).astype(np.float32)

        # Sleepers (concrete)
        sw = int(C.SLEEPER_WIDTH_MM / s)
        step = C.SLEEPER_SPACING_MM / s
        y = 0.0
        while y < H:
            y0 = int(y)
            tex[y0:y0 + sw, 18:W - 18] = (148, 150, 152)
            tex[y0:y0 + sw, 18:W - 18] += rng.normal(0, 6, size=(min(sw, H - y0), W - 36, 1))
            tex[y0:y0 + 3, 18:W - 18] *= 0.75
            tex[y0 + sw - 3:y0 + sw, 18:W - 18] *= 0.6
            y += step
        self.sleeper_step = step
        self.sleeper_w = sw

        # Rails, row by row (right rail moves with gauge faults)
        rw = int(round(C.RAIL_HEAD_MM / s))
        self.rail_w = rw
        rows = np.arange(H)
        pos_m = (rows * s) / 1000.0 - TrackWorld.MARGIN_M
        offs = np.array([self.w.gauge_offset_mm(p) for p in pos_m[::20]])
        offs = np.repeat(offs, 20)[:H]
        left_x0 = C.LEFT_RAIL_X
        right_x0 = (left_x0 + rw + (C.NOMINAL_GAUGE_MM + offs) / s).round().astype(int)
        self.right_x0 = right_x0

        # Rail profile across the head: darker edges, polished running band
        prof = np.linspace(-1, 1, rw)
        head = 170 + 55 * np.exp(-(prof / 0.45) ** 2)
        head[:2] -= 50
        head[-2:] -= 50
        cols = np.arange(W)
        for y0 in range(0, H, 512):
            y1 = min(H, y0 + 512)
            block = tex[y0:y1]
            # fastening clips on sleepers (dark) are drawn first
            # left rail
            block[:, left_x0:left_x0 + rw] = head[None, :, None]
            # right rail (variable x)
            rx = right_x0[y0:y1]
            idx = cols[None, :] - rx[:, None]
            m = (idx >= 0) & (idx < rw)
            hv = np.zeros_like(idx, dtype=np.float32)
            hv[m] = head[idx[m]]
            for ch in range(3):
                block[..., ch] = np.where(m, hv, block[..., ch])
            # rail foot shadow
            block[:, left_x0 - 4:left_x0] *= 0.55
            block[:, left_x0 + rw:left_x0 + rw + 4] *= 0.55
            for k in range(4):
                xs = rx - 1 - k
                xe = rx + rw + k
                block[np.arange(y1 - y0), xs] *= 0.6
                block[np.arange(y1 - y0), np.clip(xe, 0, W - 1)] *= 0.6

        tex += rng.normal(0, 4, size=tex.shape).astype(np.float32)

        # Elastic rail clips on each sleeper
        y = 0.0
        while y < H:
            yc = int(y + sw / 2)
            if yc < H:
                rx = int(right_x0[yc])
                for cx in (left_x0 - 9, left_x0 + rw + 9, rx - 9, rx + rw + 9):
                    cv2.ellipse(tex, (cx, yc), (5, 12), 0, 0, 360, (55, 55, 60), -1)
                    cv2.ellipse(tex, (cx, yc), (2, 8), 0, 0, 360, (95, 95, 100), -1)
            y += step

        # Rust / grease stains (distractors - round, should NOT be called cracks)
        for st in self.w.stains:
            r = self._mm_to_row(st.pos_m * 1000)
            x0 = left_x0 if st.rail == "L" else int(right_x0[min(r, H - 1)])
            cx = x0 + rw // 2 + int(rng.integers(-3, 4))
            cv2.circle(tex, (cx, r), st.size_px // 2, (70, 95, 120), -1)
            cv2.circle(tex, (cx + 1, r + 1), max(1, st.size_px // 4), (60, 80, 105), -1)

        # Cracks: dark jagged transverse lines across the head
        for cr in self.w.cracks:
            r = self._mm_to_row(cr.pos_m * 1000)
            x0 = left_x0 if cr.rail == "L" else int(right_x0[min(r, H - 1)])
            length = max(4, int(cr.frac * rw))
            start = x0 if rng.random() < 0.5 else x0 + rw - length
            pts, yy = [], r
            for x in range(start, start + length + 1, 3):
                yy += int(rng.integers(-1, 2))
                pts.append((x, yy))
            pts = np.array(pts, np.int32)
            cv2.polylines(tex, [pts], False, (22, 20, 24), 3 + int(cr.frac > 0.7), cv2.LINE_AA)
            cv2.polylines(tex, [pts + [0, 2]], False, (75, 72, 76), 1, cv2.LINE_AA)
            # small branch crack for long cracks
            if cr.frac > 0.6 and len(pts) > 3:
                b = pts[len(pts) // 2]
                cv2.line(tex, (int(b[0]), int(b[1])), (int(b[0]) + 3, int(b[1]) - 5), (35, 33, 37), 1, cv2.LINE_AA)

        self.tex = np.clip(tex, 0, 255).astype(np.uint8)
        self.tex_h = H

    # --------------------------------------------------------------- cameras
    def track_frame(self, pos_m, speed_mps=0.0, t=0.0):
        """Down-looking camera image centred on the robot position.
        Top of the image = ahead of the robot."""
        s = C.MM_PER_PX
        centre = (pos_m * 1000 + TrackWorld.MARGIN_M * 1000) / s
        top = int(centre + C.CAM_H / 2)
        rows = np.clip(np.arange(top, top - C.CAM_H, -1), 0, self.tex_h - 1)
        img = self.tex[rows].astype(np.float32)

        # motion blur proportional to speed
        k = int(1 + speed_mps * 3)
        if k > 1:
            img = cv2.blur(img, (1, k))
        # lighting flicker + sensor noise + vignette
        img *= 0.93 + 0.05 * math.sin(t * 1.7)
        img += self.rng.normal(0, 5, size=img.shape)
        img *= self._vignette(img.shape[:2])[..., None]
        return np.clip(img, 0, 255).astype(np.uint8)

    _vig = None

    def _vignette(self, shape):
        if self._vig is None or self._vig.shape != shape:
            h, w = shape
            yy, xx = np.mgrid[0:h, 0:w]
            d = ((xx - w / 2) / (w / 1.4)) ** 2 + ((yy - h / 2) / (h / 1.2)) ** 2
            self._vig = (1.0 - 0.35 * d).astype(np.float32)
        return self._vig

    def front_frame(self, pos_m, t=0.0):
        """Forward-looking camera (simple perspective scene)."""
        W, H, hy, f, ch = C.FRONT_W, C.FRONT_H, C.FRONT_HORIZON_Y, C.FRONT_FOCAL_PX, C.FRONT_CAM_HEIGHT_M
        img = np.zeros((H, W, 3), np.uint8)
        # sky
        for y in range(hy):
            k = y / hy
            img[y] = (int(235 - 40 * k), int(200 - 20 * k), int(150 + 20 * k))
        # trees on horizon
        rs = np.random.default_rng(3)
        for x in range(0, W, 14):
            hgt = int(rs.integers(8, 26))
            cv2.ellipse(img, (x, hy), (12, hgt), 0, 180, 360, (60, 110 + int(rs.integers(0, 30)), 60), -1)
        # ground
        img[hy:] = (70, 125, 95)
        cx = W // 2
        half_g = C.NOMINAL_GAUGE_MM / 2000.0

        def proj(d, x):
            return int(cx + f * x / d), int(hy + f * ch / d)

        far, near = 60.0, 0.55
        # ballast bed
        poly = np.array([proj(far, -1.7), proj(far, 1.7), proj(near, 1.7), proj(near, -1.7)], np.int32)
        cv2.fillPoly(img, [poly], (118, 122, 128))
        # sleepers move with the robot
        sp = C.SLEEPER_SPACING_MM / 1000.0
        first = math.ceil(pos_m / sp) * sp
        d = first - pos_m
        while d < far:
            if d > near:
                p1, p2 = proj(d, -1.3), proj(d, 1.3)
                th = max(1, int(f * ch / d - f * ch / (d + 0.25)))
                cv2.rectangle(img, (p1[0], p1[1] - th), (p2[0], p2[1]), (150, 152, 155), -1)
            d += sp
        # rails
        for side in (-1, 1):
            for dx, col in ((0.0, (190, 192, 198)), (0.03, (120, 120, 125))):
                pts = np.array([proj(near, side * (half_g + dx)), proj(far, side * (half_g + dx))], np.int32)
                cv2.line(img, tuple(pts[0]), tuple(pts[1]), col, 3 if dx == 0 else 1, cv2.LINE_AA)
        # obstacles
        for o in self.w.obstacles:
            if o.removed:
                continue
            dist = o.pos_m - pos_m
            if 0.4 < dist < far:
                self._draw_obstacle(img, o, dist, proj, f)
        noise = np.random.default_rng(int(t * 1000) % 2**31).normal(0, 3, img.shape)
        return np.clip(img + noise, 0, 255).astype(np.uint8)

    @staticmethod
    def _draw_obstacle(img, o, dist, proj, f):
        bx, by = proj(dist, 0.1)
        scale = f / dist
        if o.kind == "boulder":
            w, h = int(0.7 * scale), int(0.45 * scale)
            cv2.ellipse(img, (bx, by - h // 2), (max(2, w // 2), max(2, h // 2)), 0, 0, 360, (40, 75, 120), -1)
            cv2.ellipse(img, (bx - w // 6, by - h // 2 - h // 6), (max(1, w // 5), max(1, h // 6)), 0, 0, 360,
                        (70, 105, 150), -1)
        elif o.kind == "log":
            w, h = int(1.6 * scale), int(0.22 * scale)
            cv2.rectangle(img, (bx - w // 2, by - h), (bx + w // 2, by), (30, 60, 100), -1)
            cv2.ellipse(img, (bx + w // 2, by - h // 2), (max(1, h // 3), max(1, h // 2)), 0, 0, 360, (80, 140, 190), -1)
        else:  # worker in hi-vis vest
            h = int(1.7 * scale)
            w = int(0.45 * scale)
            cv2.rectangle(img, (bx - w // 3, by - h // 2), (bx + w // 3, by), (30, 70, 140), -1)            # legs (khaki)
            cv2.rectangle(img, (bx - w // 2, by - int(h * 0.85)), (bx + w // 2, by - h // 2), (0, 140, 255), -1)  # vest
            cv2.circle(img, (bx, by - int(h * 0.92)), max(2, w // 4), (90, 130, 180), -1)                # head
            cv2.circle(img, (bx, by - int(h * 0.97)), max(2, w // 4), (0, 220, 255), -1)                 # helmet
