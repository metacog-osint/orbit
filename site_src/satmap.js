// Orbit's home map (orbit-2.24, ideas#71, the design Tom approved 20 Nov 2026): every object in CelesTrak's GP "active"
// group (data/sats.json, read once a UTC day) as one point on the Cesium globe, placed with SGP4 from its newest public
// element set, drag left out. A drawing for orientation, not a tracking product. Points are a PointPrimitiveCollection
// (entities do not hold 17,000 objects) and are propagated a slice per frame, so the page keeps responding. Objects
// Orbit has a finding on (orbit changes, RPO history, breakups, new in the last 30 days, TIP in window) are larger and
// ringed. Filters and display options live in the URL, so a filtered view is a link. No inline styles or scripts (CSP).
import { json2satrec } from "./vendor/satellite.js/io.js";
import { propagate, gstime } from "./vendor/satellite.js/propagation.js";
import { eciToEcf } from "./vendor/satellite.js/transforms.js";
import { loadCesium, token, baseLayer, path } from "./globe.js";

const REFRESH_MS = 2000, SLICE_MS = 7, LIST_MAX = 200, DAY_MS = 86400000;
const OWNERS = ["us", "cn", "ru", "other"], CLASSES = ["leo", "meo", "geo", "heo"];
// ideas#264: an owner's name in place of its bare code. SU is the Soviet Union; other non-country codes stay as GCAT prints them.
let REGION = null;
try { REGION = new Intl.DisplayNames(["en"], { type: "region" }); } catch (e) { REGION = null; }
function ownerName(cc) {
  if (cc === "SU") return "Soviet Union";
  if (REGION && /^[A-Z]{2}$/.test(cc || "")) {
    try { const n = REGION.of(cc); if (n && n !== cc && n !== "Unknown Region") return n; } catch (e) { /* keep the code */ }
  }
  return cc;
}
const CLASS_NAME = { leo: "LEO", meo: "MEO", geo: "GEO", heo: "HEO", other: "Other" };
const CON_NAME = { starlink: "Starlink", oneweb: "OneWeb", kuiper: "Kuiper", iridium: "Iridium", gps: "GPS",
  galileo: "Galileo", beidou: "BeiDou" };
const MARK_NAME = { change: "Orbit change", rpo: "RPO history", breakup: "Breakup", new: "New in 30 days", tip: "TIP in window" };
const MARK_LINK = { change: "changes.html#maneuvers", rpo: "changes.html#rpo", breakup: "catalog.html#breakups",
  new: "catalog.html#catalog", tip: "reentries.html#decay" };

const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const make = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};
const when = (iso) => {
  if (!iso) return "";
  const z = /Z$/.test(iso) ? iso : iso + "Z";
  return window.TicTime ? window.TicTime.format(z, {}) : z;
};

// Marks: NORAD number -> the kinds of finding Orbit holds on it. Exported for reading in a console; pure.
export function marksFrom(snap) {
  const out = new Map();
  const add = (n, kind) => {
    const k = Number(n);
    if (!k) return;
    if (!out.has(k)) out.set(k, new Set());
    out.get(k).add(kind);
  };
  for (const e of (snap.maneuvers && snap.maneuvers.events) || []) add(e.norad, "change");
  for (const r of (snap.rpo && snap.rpo.rows) || []) {
    for (const side of ["target", "chaser"]) for (const g of (r.gcat && r.gcat[side]) || []) add(g.norad, "rpo");
  }
  for (const b of snap.breakups || []) add(b.norad, "breakup");
  for (const list of Object.values((snap.payload_sets && snap.payload_sets.by_launch) || {})) {
    for (const p of list) add(p.norad, "new");
  }
  for (const o of (snap.decay && snap.decay.objects) || []) if (!o.passed) add(o.norad, "tip");
  return out;
}

function readState() {
  const q = new URLSearchParams(location.search);
  const list = (name, all) => {
    if (!q.has(name)) return new Set(all);
    return new Set(q.get(name).split(",").filter((x) => all.includes(x)));
  };
  return {
    own: list("own", OWNERS), cls: list("cls", CLASSES), con: q.get("con") || "",
    nostar: q.get("nostar") === "1", recent: q.get("new") === "1", marked: q.get("marked") === "1",
    view: q.get("view") === "2d" ? "2d" : "3d", lines: q.get("lines") !== "0", track: q.get("track") !== "0",
    labels: q.get("labels") !== "0", n: Number(q.get("n")) || null,
  };
}

function writeState(s) {
  const q = new URLSearchParams(location.search);
  const put = (k, v) => { if (v == null) q.delete(k); else q.set(k, v); };
  put("own", s.own.size === OWNERS.length ? null : [...s.own].join(","));
  put("cls", s.cls.size === CLASSES.length ? null : [...s.cls].join(","));
  put("con", s.con || null);
  put("nostar", s.nostar ? "1" : null);
  put("new", s.recent ? "1" : null);
  put("marked", s.marked ? "1" : null);
  put("view", s.view === "2d" ? "2d" : null);
  put("lines", s.lines ? null : "0");
  put("track", s.track ? null : "0");
  put("labels", s.labels ? null : "0");
  put("n", s.n || null);
  const t = q.toString();
  history.replaceState(null, "", location.pathname + (t ? "?" + t : "") + location.hash);
}

async function getJson(url) {
  const r = await fetch(url, { cache: "no-cache" });
  // Pages answers a missing file with index.html and a 200, so the content type is the real test.
  if (!r.ok || !/json/i.test(r.headers.get("content-type") || "")) return null;
  return r.json();
}

async function start() {
  const note = $("sm-note");
  const say = (t) => { note.textContent = t; note.hidden = !t; };
  let doc, snap;
  try {
    [doc, snap] = await Promise.all([getJson("data/sats.json"), getJson("data/snapshot.json")]);
  } catch (e) {
    say("The satellite file could not be read: " + e.message);
    return;
  }
  if (!doc || !Array.isArray(doc.rows)) {
    say("The satellite file is not on the site yet. It is read from CelesTrak once a day.");
    return;
  }
  const f = Object.fromEntries(doc.fields.map((k, i) => [k, i]));
  const rows = doc.rows, N = rows.length;
  const marks = marksFrom(snap || {});
  const state = readState();
  const cutoff = new Date(Date.now() - 30 * DAY_MS).toISOString().slice(0, 10);
  const vis = new Uint8Array(N), bad = new Uint8Array(N);
  const byNorad = new Map(rows.map((r, i) => [r[f.norad], i]));
  const markOf = (i) => marks.get(rows[i][f.norad]);
  const elementsOf = (i) => {
    const r = rows[i];
    return { norad: r[f.norad], epoch: r[f.epoch], n: r[f.n], e: r[f.e], i: r[f.i], raan: r[f.raan], argp: r[f.argp], ma: r[f.ma] };
  };

  function passes(i) {
    const r = rows[i], m = markOf(i), con = r[f.con];
    if (!state.own.has(r[f.group]) || !state.cls.has(r[f.cls])) return false;
    if (state.nostar && con === "starlink") return false;
    if (state.con === "none" ? con : state.con && con !== state.con) return false;
    if (state.marked && !m) return false;
    if (state.recent && !((r[f.launch] && r[f.launch] >= cutoff) || (m && m.has("new")))) return false;
    return true;
  }

  // Controls ---------------------------------------------------------------------------------------------------
  const boxes = (name, set) => document.querySelectorAll(`input[data-sm="${name}"]`).forEach((b) => {
    b.checked = set.has(b.value);
  });
  const flag = (id, key, after) => {
    const b = $(id);
    b.checked = state[key];
    b.addEventListener("change", () => { state[key] = b.checked; (after || changed)(); });
  };
  boxes("own", state.own);
  boxes("cls", state.cls);
  flag("sm-nostar", "nostar");
  flag("sm-recent", "recent");
  flag("sm-marked", "marked");
  flag("sm-lines", "lines", () => { writeState(state); drawSelected(); });
  flag("sm-track", "track", () => { writeState(state); drawSelected(); });
  flag("sm-labels", "labels", () => { writeState(state); applyVisible(); });
  const conSel = $("sm-con");
  conSel.value = state.con;
  conSel.addEventListener("change", () => {
    state.con = conSel.value;
    if (state.con === "starlink") { state.nostar = false; $("sm-nostar").checked = false; }
    changed();
  });
  $("sm-reset").addEventListener("click", () => {
    state.own = new Set(OWNERS); state.cls = new Set(CLASSES); state.con = ""; conSel.value = "";
    state.nostar = state.recent = state.marked = false;
    document.querySelectorAll('input[data-sm="own"],input[data-sm="cls"]').forEach((b) => { b.checked = true; });
    ["sm-nostar", "sm-recent", "sm-marked"].forEach((id) => { $(id).checked = false; });
    rebind();
    changed();
  });
  function rebind() {  // the reset gives new Sets; the checkboxes read them through state from here on
    document.querySelectorAll('input[data-sm="own"],input[data-sm="cls"]').forEach((b) => {
      b.onchange = () => {
        const set = state[b.dataset.sm];
        if (b.checked) set.add(b.value); else set.delete(b.value);
        changed();
      };
    });
  }

  // The list: the accessible view of what the map shows ---------------------------------------------------------
  const tbody = $("sm-rows");
  function drawList(shown) {
    const order = shown.slice().sort((a, b) => (markOf(a) ? 0 : 1) - (markOf(b) ? 0 : 1)
      || String(rows[a][f.name]).localeCompare(String(rows[b][f.name])));
    const frag = document.createDocumentFragment();
    for (const i of order.slice(0, LIST_MAX)) {
      const r = rows[i], tr = make("tr"), m = markOf(i);
      const name = make("td"), btn = make("button", "sm-pick", r[f.name]);
      btn.type = "button";
      btn.addEventListener("click", () => select(i, true));
      name.append(btn);
      const owner = make("td");
      owner.append(make("span", "sw g-" + r[f.group]), document.createTextNode(r[f.cc] ? ownerName(r[f.cc]) : "not in GCAT"));
      tr.append(name, make("td", "num", r[f.norad]), owner, make("td", null, CLASS_NAME[r[f.cls]] || r[f.cls]),
        make("td", null, r[f.launch] || ""), make("td", null, m ? [...m].map((k) => MARK_NAME[k]).join(", ") : ""));
      frag.append(tr);
    }
    tbody.replaceChildren(frag);
    $("sm-list-note").textContent = shown.length > LIST_MAX
      ? `The first ${LIST_MAX} of ${shown.length.toLocaleString()}, objects with a finding first, then by name.`
      : `All ${shown.length.toLocaleString()}, objects with a finding first, then by name.`;
  }

  // The globe ---------------------------------------------------------------------------------------------------
  let C = null, widget = null, points = null, labels = null, recs = null, ptOf = null, lblOf = new Map(), selected = null;
  const selEntities = [];

  function colours() {
    if (!C) return null;
    const g = (k) => C.Color.fromCssColorString(css("--g-" + k) || "#888");
    return { us: g("us"), cn: g("cn"), ru: g("ru"), other: g("other"), ink: C.Color.fromCssColorString(css("--text") || "#222") };
  }
  function paint() {
    if (!points) return;
    const c = colours();
    for (let i = 0; i < N; i++) {
      const p = ptOf[i], m = markOf(i), base = c[rows[i][f.group]] || c.other;
      p.color = m ? base : base.withAlpha(0.85);
      p.pixelSize = i === selected ? 11 : m ? 7 : 2.5;
      p.outlineWidth = i === selected ? 2.5 : m ? 1.5 : 0;
      p.outlineColor = c.ink;
    }
    labels && lblOf.forEach((l) => { l.fillColor = c.ink; l.backgroundColor = C.Color.fromCssColorString(css("--panel") || "#fff").withAlpha(0.85); });
    widget.scene.requestRender();
  }

  function applyVisible() {
    if (points) {
      for (let i = 0; i < N; i++) ptOf[i].show = !!vis[i] && !bad[i] && placed[i] === 1;
      lblOf.forEach((l, i) => { l.show = state.labels && !!vis[i] && !bad[i] && placed[i] === 1; });
      widget.scene.requestRender();
    }
  }

  // One refresh runs across frames: every shown object gets the same clock reading, then the frame is drawn once.
  const placed = new Uint8Array(N);
  const scratch = { x: 0, y: 0, z: 0 };
  let cycle = null;
  const stats = { objects: N, lastRefreshMs: null, busyMs: null, failed: 0 };
  function beginCycle() {
    const now = new Date();
    cycle = { now, g: gstime(now), at: 0, t0: performance.now(), busy: 0 };
    requestAnimationFrame(step);
  }
  function step() {
    if (!cycle) return;
    const c = cycle, t0 = performance.now();
    let i = c.at;
    for (; i < N; i++) {
      if (vis[i] && !bad[i]) {
        if (!recs[i]) recs[i] = makeRec(i);
        const pv = recs[i] ? propagate(recs[i], c.now) : null;
        if (!pv || !pv.position || typeof pv.position === "boolean") {
          bad[i] = 1; stats.failed++;
          ptOf[i].show = false;
        } else {
          const e = eciToEcf(pv.position, c.g);
          scratch.x = e.x * 1000; scratch.y = e.y * 1000; scratch.z = e.z * 1000;
          ptOf[i].position = scratch;
          const l = lblOf.get(i);
          if (l) l.position = scratch;
          if (!placed[i]) { placed[i] = 1; ptOf[i].show = true; if (l) l.show = state.labels; }
        }
      }
      if ((i & 127) === 127 && performance.now() - t0 > SLICE_MS) { i++; break; }
    }
    c.at = i;
    c.busy += performance.now() - t0;
    if (i < N) { requestAnimationFrame(step); return; }
    stats.lastRefreshMs = Math.round(performance.now() - c.t0);
    stats.busyMs = Math.round(c.busy);
    cycle = null;
    widget.scene.requestRender();
    setTimeout(beginCycle, Math.max(0, REFRESH_MS - stats.lastRefreshMs));
  }
  function makeRec(i) {
    const r = rows[i];
    try {
      return json2satrec({ NORAD_CAT_ID: r[f.norad], EPOCH: r[f.epoch], MEAN_MOTION: r[f.n], ECCENTRICITY: r[f.e],
        INCLINATION: r[f.i], RA_OF_ASC_NODE: r[f.raan], ARG_OF_PERICENTER: r[f.argp], MEAN_ANOMALY: r[f.ma],
        BSTAR: 0, MEAN_MOTION_DOT: 0, MEAN_MOTION_DDOT: 0 });
    } catch {
      return null;
    }
  }

  function drawSelected() {
    if (!widget) return;
    selEntities.splice(0).forEach((e) => widget.entities.remove(e));
    if (selected != null) {
      const p = path(elementsOf(selected), new Date());
      const col = (colours()[rows[selected][f.group]] || colours().other);
      if (p && state.lines && state.view === "3d") {
        selEntities.push(widget.entities.add({ polyline: { positions: p.orbit.map((x) => new C.Cartesian3(x[0], x[1], x[2])),
          width: 1.8, arcType: C.ArcType.NONE, material: col.withAlpha(0.9) } }));
      }
      if (p && state.track) {
        selEntities.push(widget.entities.add({ polyline: { positions: p.ground.map((c) => C.Cartesian3.fromDegrees(c[0], c[1])),
          width: 1.2, arcType: C.ArcType.GEODESIC, material: new C.PolylineDashMaterialProperty({ color: col.withAlpha(0.7), dashLength: 8 }) } }));
      }
    }
    widget.scene.requestRender();
  }

  function sideCard(i) {
    const box = $("sm-card");
    box.replaceChildren();
    if (i == null) { box.hidden = true; return; }
    const r = rows[i], m = markOf(i);
    const close = make("button", "sm-close", "Close");
    close.type = "button";
    close.addEventListener("click", () => select(null));
    box.append(close, make("h3", null, r[f.name]));
    const dl = make("dl");
    const row = (k, v) => { if (v) dl.append(make("dt", null, k), make("dd", null, v)); };
    row("NORAD", String(r[f.norad]));
    row("COSPAR", r[f.cospar]);
    row("Owner", r[f.cc] ? (ownerName(r[f.cc]) === r[f.cc] ? r[f.cc] : ownerName(r[f.cc]) + " (" + r[f.cc] + ")") : "Not in GCAT");
    row("Orbit", CLASS_NAME[r[f.cls]] || r[f.cls]);
    row("Constellation", CON_NAME[r[f.con]]);
    row("Launched", r[f.launch]);
    row("Element set", when(r[f.epoch]));
    box.append(dl);
    if (m) {
      const ul = make("ul", "sm-marks");
      for (const k of m) {
        const li = make("li"), a = make("a", null, MARK_NAME[k]);
        a.href = MARK_LINK[k];
        li.append(a);
        ul.append(li);
      }
      box.append(ul);
    }
    const a = make("a", "sm-object", "Open this object's page");
    a.href = "object.html?n=" + encodeURIComponent(r[f.norad]);
    box.append(a);
    box.hidden = false;
  }

  function select(i, fly) {
    const prev = selected;
    selected = i;
    state.n = i == null ? null : rows[i][f.norad];
    writeState(state);
    sideCard(i);
    if (points) {
      const c = colours();
      for (const k of [prev, i]) {
        if (k == null) continue;
        const p = ptOf[k], m = markOf(k);
        p.pixelSize = k === selected ? 11 : m ? 7 : 2.5;
        p.outlineWidth = k === selected ? 2.5 : m ? 1.5 : 0;
        p.outlineColor = c.ink;
      }
      drawSelected();
      if (fly && i != null && placed[i]) {
        const pos = ptOf[i].position, h = C.Cartographic.fromCartesian(pos);
        widget.camera.flyTo({ destination: C.Cartesian3.fromRadians(h.longitude, h.latitude, Math.max(h.height * 2.2, 9e6)), duration: 0.8 });
      }
    }
  }

  function refilter() {
    const shown = [];
    for (let i = 0; i < N; i++) {
      vis[i] = passes(i) ? 1 : 0;
      if (vis[i]) shown.push(i);
    }
    $("sm-count").textContent = `${shown.length.toLocaleString()} of ${N.toLocaleString()} objects shown.`;
    drawList(shown);
    applyVisible();
    return shown;
  }
  let timer = null;
  function changed() {
    writeState(state);
    clearTimeout(timer);
    timer = setTimeout(() => {
      refilter();
      if (points && !cycle) beginCycle();  // newly shown objects get a position now, not at the next tick
    }, 60);
  }

  rebind();
  refilter();
  if (state.n != null && byNorad.has(state.n)) { selected = byNorad.get(state.n); sideCard(selected); }
  $("sm-read").textContent = "Read " + when(doc.read_at) + ".";

  // Cesium last: the filters and the list work without WebGL.
  try {
    C = await loadCesium();
    globalThis.CESIUM_WORKERS = undefined;
    const base = await baseLayer(C, await token());
    const box = $("sm-globe");
    widget = new C.CesiumWidget(box, {
      baseLayer: base.layer, terrainProvider: new C.EllipsoidTerrainProvider(), sceneModePicker: false,
      skyAtmosphere: new C.SkyAtmosphere(), requestRenderMode: true, maximumRenderTimeChange: Infinity,
    });
    widget.scene.globe.enableLighting = false;
    widget.camera.setView({ destination: C.Cartesian3.fromDegrees(-30, 20, 3.2e7) });
    widget.canvas.setAttribute("aria-label", "Globe of the satellites listed in the table under it, at their computed places now.");
    if (!base.ion) box.parentElement.append(make("p", "fallback-note small muted", "Imagery: Natural Earth II (Cesium ion not reached)."));
    points = widget.scene.primitives.add(new C.PointPrimitiveCollection());
    labels = widget.scene.primitives.add(new C.LabelCollection());
    recs = new Array(N);
    ptOf = new Array(N);
    for (let i = 0; i < N; i++) ptOf[i] = points.add({ id: i, show: false, position: C.Cartesian3.ZERO, pixelSize: 2.5 });
    const near = new C.DistanceDisplayCondition(0, 1.4e7);
    for (const n of marks.keys()) {
      const i = byNorad.get(n);
      if (i == null) continue;
      lblOf.set(i, labels.add({ show: false, position: C.Cartesian3.ZERO, text: String(rows[i][f.name]),
        font: "12px system-ui, sans-serif", showBackground: true, pixelOffset: new C.Cartesian2(0, -14), distanceDisplayCondition: near }));
    }
    paint();
    if (state.view === "2d") widget.scene.morphTo2D(0);
    const viewBtns = { "3d": $("sm-view-3d"), "2d": $("sm-view-2d") };
    const showView = () => {
      for (const k of Object.keys(viewBtns)) viewBtns[k].setAttribute("aria-pressed", String(state.view === k));
    };
    showView();
    for (const k of Object.keys(viewBtns)) {
      viewBtns[k].addEventListener("click", () => {
        if (state.view === k) return;
        state.view = k;
        writeState(state);
        showView();
        if (k === "2d") widget.scene.morphTo2D(0.6); else widget.scene.morphTo3D(0.6);
        drawSelected();
      });
    }
    widget.scene.morphComplete.addEventListener(() => widget.scene.requestRender());

    const handler = new C.ScreenSpaceEventHandler(widget.canvas);
    const hitAt = (pos) => {  // prefers an object with a finding among what is under the pointer
      const hits = widget.scene.drillPick(pos, 6).filter((h) => h && h.primitive && h.collection !== labels && typeof h.id === "number");
      return (hits.find((h) => markOf(h.id)) || hits[0] || { id: null }).id;
    };
    handler.setInputAction((ev) => { const i = hitAt(ev.position); if (i != null) select(i); }, C.ScreenSpaceEventType.LEFT_CLICK);
    handler.setInputAction((ev) => {
      const h = widget.scene.pick(ev.endPosition);
      widget.canvas.style.cursor = h && typeof h.id === "number" ? "pointer" : "";
    }, C.ScreenSpaceEventType.MOUSE_MOVE);

    if (selected != null) drawSelected();
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { paint(); drawSelected(); });
    new MutationObserver(() => { paint(); drawSelected(); }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    window.__orbitSatMap = stats;
    beginCycle();
  } catch (e) {
    say("The globe could not start in this browser (" + e.message + "). The filters and the list below still work.");
  }
}

start();
