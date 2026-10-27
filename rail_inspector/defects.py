"""Defect log: turns per-frame detections into unique, geo-tagged defects."""
from dataclasses import dataclass, field, asdict
import math
import time

from . import config as C
from .vision import severity_from_frac

SEV_RANK = {"INFO": 0, "MINOR": 1, "MAJOR": 2, "CRITICAL": 3}


def location(pos_m):
    """Chainage (km) and approximate GPS for a distance along the track."""
    km = C.START_CHAINAGE_KM + pos_m / 1000.0
    h = math.radians(C.HEADING_DEG)
    dlat = pos_m * math.cos(h) / 111_320.0
    dlon = pos_m * math.sin(h) / (111_320.0 * math.cos(math.radians(C.START_LAT)))
    return km, C.START_LAT + dlat, C.START_LON + dlon


@dataclass
class Defect:
    id: int
    type: str                  # CRACK | GAUGE | OBSTACLE
    pos_m: float
    severity: str
    rail: str = "-"
    detail: str = ""
    hits: int = 1
    confirmed: bool = False
    end_m: float | None = None
    value: float | None = None
    chainage_km: float = 0.0
    lat: float = 0.0
    lon: float = 0.0
    t_wall: float = field(default_factory=time.time)
    t_run: float = 0.0
    snapshot: object = None    # small BGR crop (not serialised)
    fracs: list = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        d.pop("snapshot", None)
        d.pop("fracs", None)
        d["chainage"] = f"{self.chainage_km:.3f}"
        return d


class DefectLog:
    def __init__(self):
        self.items: list[Defect] = []
        self._next = 1
        self._gauge_open: Defect | None = None

    def _new(self, **kw):
        km, lat, lon = location(kw["pos_m"])
        d = Defect(id=self._next, chainage_km=km, lat=lat, lon=lon, **kw)
        self._next += 1
        self.items.append(d)
        return d

    def confirmed(self):
        return [d for d in self.items if d.confirmed]

    # ---------------------------------------------------------------- cracks
    def add_crack(self, rail, pos_m, frac, t_run, snapshot=None):
        """Returns the Defect if it just became confirmed (new event), else None."""
        merge = C.DEFECT_MERGE_MM / 1000.0
        for d in self.items:
            if d.type == "CRACK" and d.rail == rail and abs(d.pos_m - pos_m) < merge:
                d.hits += 1
                d.fracs.append(frac)
                # running mean position, severity from the strongest views
                d.pos_m += (pos_m - d.pos_m) / d.hits
                top = sorted(d.fracs)[len(d.fracs) // 2:]
                f = sum(top) / len(top)
                d.severity = severity_from_frac(f)
                d.value = round(f * 100)
                d.detail = f"Transverse crack, {d.value}% of rail head, {'left' if rail == 'L' else 'right'} rail"
                if snapshot is not None and (d.snapshot is None or frac >= max(d.fracs)):
                    d.snapshot = snapshot
                if not d.confirmed and d.hits >= C.CRACK_MIN_FRAMES:
                    d.confirmed = True
                    d.t_run = t_run
                    return d
                return None
        self._new(type="CRACK", rail=rail, pos_m=pos_m, severity=severity_from_frac(frac),
                  fracs=[frac], snapshot=snapshot, t_run=t_run, value=round(frac * 100))
        return None

    # ----------------------------------------------------------------- gauge
    def update_gauge(self, pos_m, gauge_mm, t_run):
        """Track out-of-tolerance stretches. Returns a Defect when one opens."""
        if gauge_mm is None:
            return None
        dev = gauge_mm - C.NOMINAL_GAUGE_MM
        bad = abs(dev) > C.GAUGE_TOLERANCE_MM
        g = self._gauge_open
        if bad:
            if g is None:
                kind = "Wide" if dev > 0 else "Tight"
                g = self._new(type="GAUGE", pos_m=pos_m, severity="MAJOR", value=gauge_mm,
                              detail=f"{kind} gauge", t_run=t_run)
                g.confirmed = True
                g.end_m = pos_m
                self._gauge_open = g
                return g
            g.end_m = pos_m
            if abs(dev) > abs(g.value - C.NOMINAL_GAUGE_MM):
                g.value = gauge_mm
            g.severity = "CRITICAL" if abs(g.value - C.NOMINAL_GAUGE_MM) > 2 * C.GAUGE_TOLERANCE_MM else "MAJOR"
            g.detail = (f"{'Wide' if g.value > C.NOMINAL_GAUGE_MM else 'Tight'} gauge "
                        f"{g.value:.0f} mm ({g.value - C.NOMINAL_GAUGE_MM:+.0f}) over "
                        f"{(g.end_m - g.pos_m):.1f} m")
            return None
        if g is not None and pos_m - g.end_m > 0.5:
            self._gauge_open = None
        return None

    # -------------------------------------------------------------- obstacle
    def add_obstacle(self, pos_m, dist_m, t_run, snapshot=None):
        target = pos_m + dist_m
        for d in self.items:
            if d.type == "OBSTACLE" and abs(d.pos_m - target) < 3.0:
                return None
        d = self._new(type="OBSTACLE", pos_m=target, severity="CRITICAL", detail="Obstruction on track",
                      t_run=t_run, snapshot=snapshot, value=round(dist_m, 1))
        d.confirmed = True
        return d

    def summary(self):
        c = self.confirmed()
        return {
            "cracks": sum(d.type == "CRACK" for d in c),
            "critical": sum(d.severity == "CRITICAL" and d.type == "CRACK" for d in c),
            "gauge": sum(d.type == "GAUGE" for d in c),
            "obstacles": sum(d.type == "OBSTACLE" for d in c),
            "total": len(c),
        }
