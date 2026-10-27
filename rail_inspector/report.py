"""Inspection report generation: CSV (for maintenance software), JSON and a
printable HTML report with defect photos (open in a browser -> Print -> PDF)."""
import base64
import csv
import datetime as dt
import html
import json
import os

import cv2

from . import config as C

FIELDS = ["id", "type", "severity", "chainage", "rail", "pos_m", "end_m", "value", "detail", "lat", "lon", "t_run"]


def _img_b64(img, scale=3):
    if img is None or img.size == 0:
        return ""
    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode() if ok else ""


def rows(engine):
    out = []
    for d in engine.log.confirmed():
        r = d.to_dict()
        r["pos_m"] = round(r["pos_m"], 2)
        r["end_m"] = round(r["end_m"], 2) if r["end_m"] is not None else ""
        r["lat"], r["lon"], r["t_run"] = round(r["lat"], 6), round(r["lon"], 6), round(r["t_run"], 1)
        out.append({k: r.get(k, "") for k in FIELDS})
    return out


def csv_text(engine):
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(rows(engine))
    return buf.getvalue()


def html_report(engine):
    s = engine.last or {}
    now = dt.datetime.now().strftime("%d %b %Y, %H:%M")
    sev_col = {"MINOR": "#c99a00", "MAJOR": "#d9661f", "CRITICAL": "#c62828"}
    trs = []
    for d in engine.log.confirmed():
        img = _img_b64(d.snapshot)
        trs.append(
            f"<tr><td>{d.id}</td><td>{d.type}</td>"
            f"<td><b style='color:{sev_col.get(d.severity, '#333')}'>{d.severity}</b></td>"
            f"<td>km {d.chainage_km:.3f}</td><td>{d.rail}</td><td>{html.escape(d.detail)}</td>"
            f"<td>{d.lat:.6f}, {d.lon:.6f}</td>"
            f"<td>{f'<img src={chr(34)}{img}{chr(34)}>' if img else ''}</td></tr>")
    sm = engine.log.summary()
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Track Inspection Report</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:32px;color:#1d2530}}
h1{{margin:0 0 4px}} .muted{{color:#667}} table{{border-collapse:collapse;width:100%;margin-top:16px}}
th,td{{border:1px solid #d5dae1;padding:6px 8px;font-size:13px;text-align:left;vertical-align:middle}}
th{{background:#eef2f6}} img{{max-height:90px;border-radius:4px}}
.cards{{display:flex;gap:12px;margin-top:16px}} .card{{border:1px solid #d5dae1;border-radius:8px;padding:10px 16px}}
.card b{{font-size:24px;display:block}}
</style></head><body>
<h1>Rail Track Inspection Report</h1>
<div class="muted">Generated {now} &middot; Source: {s.get('source', '-')} &middot;
Section km {C.START_CHAINAGE_KM:.3f} &ndash; {s.get('chainage_km', 0):.3f} &middot;
{s.get('pos_m', 0):.1f} m inspected in {s.get('t', 0):.0f} s</div>
<div class="cards">
<div class="card"><b>{sm['cracks']}</b>Cracks</div>
<div class="card"><b style="color:#c62828">{sm['critical']}</b>Critical cracks</div>
<div class="card"><b>{sm['gauge']}</b>Gauge faults</div>
<div class="card"><b>{sm['obstacles']}</b>Obstructions</div>
</div>
<p class="muted">Gauge standard: {C.NOMINAL_GAUGE_MM} mm &plusmn; {C.GAUGE_TOLERANCE_MM} mm.
Crack severity by length across rail head: MINOR &ge; {int(C.CRACK_MINOR_FRAC * 100)}%,
MAJOR &ge; {int(C.CRACK_MAJOR_FRAC * 100)}%, CRITICAL &ge; {int(C.CRACK_CRITICAL_FRAC * 100)}%.</p>
<table><tr><th>#</th><th>Type</th><th>Severity</th><th>Chainage</th><th>Rail</th><th>Details</th><th>GPS</th><th>Photo</th></tr>
{''.join(trs) or '<tr><td colspan=8>No defects found</td></tr>'}
</table></body></html>"""


def write_reports(engine, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    stamp = "inspection_report"
    p_csv = os.path.join(out_dir, stamp + ".csv")
    p_json = os.path.join(out_dir, stamp + ".json")
    p_html = os.path.join(out_dir, stamp + ".html")
    with open(p_csv, "w", newline="") as f:
        f.write(csv_text(engine))
    with open(p_json, "w") as f:
        json.dump({"summary": engine.log.summary(), "run": engine.last, "defects": rows(engine)}, f, indent=2)
    with open(p_html, "w") as f:
        f.write(html_report(engine))
    return [p_csv, p_json, p_html]
