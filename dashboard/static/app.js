const $ = (id) => document.getElementById(id);
const COL = { red: "#eb4040", amber: "#f5aa28", orange: "#ff8228", minor: "#ffcd3c", cyan: "#3cbee6",
  violet: "#be78ff", muted: "#8c98a8", edge: "#2d3746", band: "#1c2c26" };
const SEV = { MINOR: COL.minor, MAJOR: COL.orange, CRITICAL: COL.red };

function send(cmd, value) {
  return fetch("/api/cmd", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cmd, value }) });
}

// ------------------------------------------------------------- controls
$("bstart").onclick = () => send("start");
$("bstop").onclick = () => send("stop");
$("breset").onclick = () => { if (confirm("Reset run and clear the defect log?")) send("reset"); };
$("spd").oninput = (e) => { $("spdv").textContent = (+e.target.value).toFixed(1); };
$("spd").onchange = (e) => send("speed", +e.target.value);
$("spdv").textContent = (+$("spd").value).toFixed(1);

function holdButton(btn, speed) {
  const on = (e) => { e.preventDefault(); btn.classList.add("on"); send("manual", speed()); };
  const off = () => { if (btn.classList.contains("on")) { btn.classList.remove("on"); send("manual", 0); } };
  btn.addEventListener("pointerdown", on);
  ["pointerup", "pointerleave", "pointercancel"].forEach((ev) => btn.addEventListener(ev, off));
}
holdButton($("bfwd"), () => +$("spd").value * 0.6);
holdButton($("brev"), () => -+$("spd").value * 0.4);
const keys = {};
document.addEventListener("keydown", (e) => {
  if (keys[e.key]) return;
  keys[e.key] = true;
  if (e.key === "w") { $("bfwd").classList.add("on"); send("manual", +$("spd").value * 0.6); }
  if (e.key === "s") { $("brev").classList.add("on"); send("manual", -+$("spd").value * 0.4); }
  if (e.key === " ") { e.preventDefault(); send("stop"); }
});
document.addEventListener("keyup", (e) => {
  keys[e.key] = false;
  if (e.key === "w" || e.key === "s") { $("bfwd").classList.remove("on"); $("brev").classList.remove("on"); send("manual", 0); }
});

// ---------------------------------------------------------------- render
function drawVib(v) {
  const c = $("vibc"), g = c.getContext("2d");
  g.clearRect(0, 0, c.width, c.height);
  g.strokeStyle = COL.cyan; g.lineWidth = 1.5; g.beginPath();
  v.forEach((y, i) => {
    const px = (i / Math.max(1, v.length - 1)) * c.width, py = c.height - Math.min(1, y / 0.5) * c.height;
    i ? g.lineTo(px, py) : g.moveTo(px, py);
  });
  g.stroke();
}

function drawMap(s) {
  const c = $("mapc");
  const W = (c.width = c.clientWidth * devicePixelRatio), H = (c.height = 190 * devicePixelRatio);
  const g = c.getContext("2d");
  g.scale(devicePixelRatio, devicePixelRatio);
  const w = W / devicePixelRatio, L = s.length_m;
  const x0 = 46, x1 = w - 12, X = (p) => x0 + ((x1 - x0) * p) / L;
  const nom = CFG.nominal_gauge, tol = CFG.tol, R = 30, top = 8, bot = 92;
  const Y = (v) => bot - ((Math.max(nom - R, Math.min(nom + R, v)) - (nom - R)) / (2 * R)) * (bot - top);
  g.font = "10px sans-serif"; g.fillStyle = COL.band;
  g.fillRect(x0, Y(nom + tol), x1 - x0, Y(nom - tol) - Y(nom + tol));
  g.fillStyle = COL.muted;
  [nom - 20, nom, nom + 20].forEach((v) => g.fillText(v, 4, Y(v) + 3));
  g.strokeStyle = COL.cyan; g.lineWidth = 2; g.beginPath();
  s.gauge_profile.forEach(([p, v], i) => (i ? g.lineTo(X(p), Y(v)) : g.moveTo(X(p), Y(v))));
  g.stroke();

  const ry = 130;
  g.fillStyle = "#262e3a"; g.fillRect(x0, ry - 9, x1 - x0, 18);
  g.fillStyle = "#28788f"; g.fillRect(x0, ry - 3, X(s.pos_m) - x0, 6);
  g.fillStyle = COL.muted;
  const step = L > 300 ? 50 : L > 120 ? 20 : 10;
  for (let k = 0; k <= L; k += step) { g.fillRect(X(k), ry + 10, 1, 5); g.fillText(k + "m", X(k) - 8, ry + 27); }
  g.fillText("L/R", 4, ry + 4);
  s.defects.forEach((d) => {
    if (d.type === "GAUGE") { g.fillStyle = COL.amber; g.fillRect(X(d.pos_m), ry - 9, Math.max(2, X(d.end_m || d.pos_m) - X(d.pos_m)), 18); }
  });
  s.defects.forEach((d) => {
    const x = X(d.pos_m);
    if (d.type === "CRACK") {
      const y = d.rail === "L" ? ry - 17 : ry + 17;
      g.fillStyle = SEV[d.severity]; g.beginPath(); g.moveTo(x, ry); g.lineTo(x - 6, y); g.lineTo(x + 6, y); g.fill();
    } else if (d.type === "OBSTACLE") { g.fillStyle = COL.violet; g.fillRect(x - 5, ry - 26, 10, 10); }
  });
  const rx = X(s.pos_m);
  g.fillStyle = COL.cyan; g.beginPath(); g.moveTo(rx, ry - 12); g.lineTo(rx - 7, ry - 27); g.lineTo(rx + 7, ry - 27); g.fill();
}

let lastDefectCount = -1;
function renderDefects(defs) {
  if (defs.length === lastDefectCount) return;
  lastDefectCount = defs.length;
  $("dtab").innerHTML = defs.length ? defs.map((d) => `<tr>
    <td>${d.id}</td><td>${d.type}</td><td class="sev-${d.severity}">${d.severity}</td>
    <td>km ${d.chainage}</td><td>${d.rail}</td><td>${d.detail}</td>
    <td class="muted">${d.lat.toFixed(5)}, ${d.lon.toFixed(5)}</td>
    <td>${d.type !== "GAUGE" ? `<img src="/api/snapshot/${d.id}.jpg?n=${d.id}">` : ""}</td></tr>`).join("")
    : `<tr><td colspan="8" class="muted">No defects yet</td></tr>`;
  const last = [...defs].reverse().find((d) => d.type !== "GAUGE");
  if (last) {
    $("closeimg").src = `/api/snapshot/${last.id}.jpg?n=${last.id}`;
    $("closetxt").innerHTML = `<b class="sev-${last.severity}">${last.type} - ${last.severity}</b><br>km ${last.chainage} &middot; rail ${last.rail}`;
  }
}

let lastAlert = "";
async function tick() {
  try {
    const s = await (await fetch("/api/state")).json();
    $("status").textContent = s.status_text; $("status").className = "pill " + s.status;
    $("src").textContent = "MODE: " + s.source;
    const t = Math.floor(s.t); $("clock").textContent = `RUN ${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
    $("speed").textContent = s.speed_mps.toFixed(2);
    $("speedbar").style.width = Math.min(100, (Math.abs(s.speed_mps) / CFG.max_speed) * 100) + "%";
    $("km").textContent = s.chainage_km.toFixed(3);
    $("posbar").style.width = (s.pos_m / s.length_m) * 100 + "%";
    $("gauge").textContent = s.gauge_mm ? s.gauge_mm.toFixed(0) : "--";
    const bad = s.gauge_dev_mm !== null && Math.abs(s.gauge_dev_mm) > CFG.tol;
    $("gauge").style.color = bad ? COL.red : "#3fc878";
    $("gdev").textContent = s.gauge_dev_mm !== null ? `nominal ${CFG.nominal_gauge} (${s.gauge_dev_mm > 0 ? "+" : ""}${s.gauge_dev_mm.toFixed(0)} mm)` : "";
    const clear = s.range_m >= 3.99;
    $("range").textContent = clear ? "CLEAR" : s.range_m.toFixed(2);
    $("rangeu").textContent = clear ? "" : "m";
    $("range").style.color = s.range_m < 2 ? COL.red : clear ? "#3fc878" : COL.amber;
    $("camd").textContent = s.cam_obstacle_m ? `camera: ${s.cam_obstacle_m} m` : "camera: path clear";
    $("vib").textContent = s.vibration_g.toFixed(2);
    $("bat").textContent = s.battery_pct.toFixed(0);
    $("batbar").style.width = s.battery_pct + "%";
    $("gps").textContent = `GPS ${s.lat.toFixed(6)}, ${s.lon.toFixed(6)}  ·  ${s.pos_m.toFixed(1)} / ${s.length_m} m`;
    $("c_cr").textContent = s.summary.cracks; $("c_crit").textContent = s.summary.critical;
    $("c_g").textContent = s.summary.gauge; $("c_o").textContent = s.summary.obstacles;
    $("log").innerHTML = s.messages.map((m) => {
      const mm = String(Math.floor(m.t / 60)).padStart(2, "0"), ss = String(Math.floor(m.t % 60)).padStart(2, "0");
      return `<li class="${m.level}"><span>${mm}:${ss}</span>${m.text}</li>`;
    }).join("");
    if (s.alerts.length && s.alerts[0].text !== lastAlert) {
      lastAlert = s.alerts[0].text;
      $("alertbar").textContent = "⚠ " + lastAlert; $("alertbar").classList.remove("hidden");
      setTimeout(() => $("alertbar").classList.add("hidden"), 4000);
    }
    drawVib(s.vib_hist);
    drawMap(s);
    renderDefects(s.defects);
  } catch (e) {
    $("status").textContent = "DISCONNECTED"; $("status").className = "pill";
  }
}
setInterval(tick, 250);
tick();
