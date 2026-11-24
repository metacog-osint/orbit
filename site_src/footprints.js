// Footprints prototype (ideas#232): draws data/footprints.json, written by tools/footprints.py. Every outline keeps
// its kind (published, computed, estimated), source, date and uncertainty beside it; kinds differ by line pattern,
// not colour. No inline styles or scripts (CSP).
import * as ml from "./vendor/maplibre-gl/maplibre-gl.mjs";

const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const dark = () => matchMedia("(prefers-color-scheme: dark)").matches;
const BASE = { light: { land: "#F2F3F0", water: "#C2C8CA", border: "#B9BEC2" }, dark: { land: "#1A1D22", water: "#0C0F14", border: "#3A3F46" } };
const DASH = { published: null, computed: [4, 3], estimated: [0.6, 2.2] };
const WIDTH = { published: 2.6, computed: 1.6, estimated: 2.2 };
const el = (tag, attrs = {}, text) => {
  const n = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => (k === "class" ? (n.className = v) : n.setAttribute(k, v)));
  if (text != null) n.textContent = text;
  return n;
};
const pct = (x) => (x == null ? "" : Math.round(x * 100) + "%");
const km = (x) => (x == null ? "" : Number(x).toLocaleString("en-US") + " km");

let map = null, doc = null, current = null, drawn = null, loaded = false, shown = new Set();

function style() {
  const b = BASE[dark() ? "dark" : "light"];
  return { version: 8, sources: { world: { type: "geojson", data: new URL("data/world.geojson", location.href).href, maxzoom: 5, tolerance: 1 } },
    layers: [{ id: "bg", type: "background", paint: { "background-color": b.water } },
             { id: "land", type: "fill", source: "world", paint: { "fill-color": b.land } },
             { id: "borders", type: "line", source: "world", paint: { "line-color": b.border, "line-width": 0.6 } }] };
}

function clearCase() {
  if (!drawn) return;
  drawn.layers.forEach((l) => {
    ["fp-fill-", "fp-line-", "fp-pt-"].forEach((p) => { if (map.getLayer(p + l.id)) map.removeLayer(p + l.id); });
    if (map.getSource("fp-" + l.id)) map.removeSource("fp-" + l.id);
  });
}

// The table is the page's content and never waits for the map: a map in a hidden tab does not finish loading.
function select(c) {
  current = c;
  shown = new Set(c.layers.filter((l) => l.on !== false).map((l) => l.id));
  table(c);
  if (loaded) drawCase(c);
}

function drawCase(c) {
  clearCase();
  drawn = c;
  const ink = css("--text") || "#14202e";
  c.layers.forEach((l) => {
    map.addSource("fp-" + l.id, { type: "geojson", data: l.geojson });
    const vis = { visibility: shown.has(l.id) ? "visible" : "none" };
    if (l.fill) {
      map.addLayer({ id: "fp-fill-" + l.id, type: "fill", source: "fp-" + l.id, filter: ["==", ["geometry-type"], "Polygon"], layout: vis,
        paint: { "fill-color": ink, "fill-antialias": !l.fill_by, "fill-opacity": l.fill_by ? ["interpolate", ["linear"], ["get", l.fill_by], 0, 0.02, l.fill_max || 1, 0.55] : 0.08 } });
    }
    const paint = { "line-color": ink, "line-width": l.thin ? 0.8 : WIDTH[l.kind] || 1.5, "line-opacity": l.thin ? 0.45 : 0.95 };
    if (DASH[l.kind]) paint["line-dasharray"] = DASH[l.kind];
    if (!l.no_line) map.addLayer({ id: "fp-line-" + l.id, type: "line", source: "fp-" + l.id, filter: ["!=", ["geometry-type"], "Point"], layout: { ...vis, "line-cap": "round" }, paint });
    map.addLayer({ id: "fp-pt-" + l.id, type: "circle", source: "fp-" + l.id, filter: ["==", ["geometry-type"], "Point"], layout: vis,
      paint: { "circle-radius": l.point_radius || 3, "circle-color": ink, "circle-opacity": l.point_opacity || 0.8, "circle-stroke-color": css("--panel") || "#fff", "circle-stroke-width": l.point_radius && l.point_radius < 2 ? 0 : 1 } });
  });
  if (c.bounds) map.fitBounds(c.bounds, { padding: 30, duration: 0 });
}

function toggle(id, on) {
  on ? shown.add(id) : shown.delete(id);
  if (!loaded) return;
  ["fp-fill-", "fp-line-", "fp-pt-"].forEach((p) => { if (map.getLayer(p + id)) map.setLayoutProperty(p + id, "visibility", on ? "visible" : "none"); });
}

function table(c) {
  $("fp-summary").textContent = c.summary || "";
  const body = $("fp-layers").tBodies[0];
  body.replaceChildren();
  c.layers.forEach((l) => {
    const tr = el("tr");
    const box = el("input", { type: "checkbox", "aria-label": "Show " + l.label });
    box.checked = shown.has(l.id);
    box.addEventListener("change", () => toggle(l.id, box.checked));
    const td0 = el("td"); td0.append(box);
    const td1 = el("td"); td1.append(el("span", { class: "fp-kind", "data-kind": l.kind }, l.kind));
    const td3 = el("td");
    if (l.source_url) { const a = el("a", { href: l.source_url, rel: "noopener" }, l.source); td3.append(a); } else td3.append(l.source || "");
    if (l.date) td3.append(" (" + l.date + ")");
    tr.append(td0, td1, el("td", {}, l.label), td3, el("td", {}, l.uncertainty || ""));
    body.append(tr);
  });
  const sb = $("fp-scores").tBodies[0];
  sb.replaceChildren();
  (c.scores || []).forEach((s) => {
    const tr = el("tr");
    tr.append(el("td", {}, s.estimate), el("td", {}, s.published), el("td", { class: "num" }, pct(s.iou)), el("td", { class: "num" }, pct(s.covered)),
      el("td", { class: "num" }, pct(s.excess)), el("td", { class: "num" }, km(s.median_km)), el("td", { class: "num" }, km(s.p95_km)));
    sb.append(tr);
  });
  $("fp-scores-box").hidden = !(c.scores || []).length;
  const extra = $("fp-extra");
  extra.replaceChildren();
  (c.tables || []).forEach((t) => {
    extra.append(el("h3", {}, t.title));
    if (t.note) extra.append(el("p", { class: "small muted" }, t.note));
    const wrap = el("div", { class: "table-wrap" }), tb = el("table", { class: "fp-table" }), head = el("tr");
    t.columns.forEach((h) => head.append(el("th", { scope: "col" }, h)));
    const th = el("thead"); th.append(head);
    const bd = el("tbody");
    t.rows.forEach((r) => { const tr = el("tr"); r.forEach((v, i) => tr.append(el("td", i ? { class: "num" } : {}, String(v)))); bd.append(tr); });
    tb.append(th, bd); wrap.append(tb); extra.append(wrap);
  });
  const notes = $("fp-notes");
  notes.replaceChildren();
  (c.notes || []).forEach((n) => notes.append(el("li", {}, n)));
}

function tabs() {
  const box = $("fp-cases");
  doc.cases.forEach((c, i) => {
    const b = el("button", { type: "button", role: "tab", "aria-selected": i === 0 ? "true" : "false" }, c.title);
    b.addEventListener("click", () => {
      box.querySelectorAll("button").forEach((x) => x.setAttribute("aria-selected", x === b ? "true" : "false"));
      select(c);
      history.replaceState(null, "", "#" + c.id);
    });
    b.dataset.case = c.id;
    box.append(b);
  });
}

async function main() {
  try {
    const r = await fetch("data/footprints.json", { cache: "no-cache" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    doc = await r.json();
  } catch (e) {
    $("fp-fallback").hidden = false;
    $("fp-fallback").textContent = "The footprint file is not on this site yet (" + e.message + "). Build it with tools/footprints.py.";
    return;
  }
  // A <time> element, so tic-time.js re-renders it in the viewer's zone when the time settings change.
  const t = el("time", { datetime: doc.generated_at, "data-tic": "datetime" }, doc.generated_at.slice(0, 16).replace("T", " ") + " UTC");
  $("fp-asof").replaceChildren("Built ", t, ".");
  if (window.TicTime) { window.TicTime.renderAll($("fp-asof")); window.TicTime.onChange(() => window.TicTime.renderAll($("fp-asof"))); }
  map = new ml.Map({ container: "fp-map", style: style(), center: [0, 20], zoom: 1, dragRotate: false, pitchWithRotate: false,
    cooperativeGestures: true, renderWorldCopies: true, attributionControl: { compact: true, customAttribution: "Land: Natural Earth" } });
  map.touchZoomRotate.disableRotation();
  map.addControl(new ml.NavigationControl({ showCompass: false }), "top-right");
  tabs();
  const want = location.hash.slice(1);
  const first = doc.cases.find((c) => c.id === want) || doc.cases[0];
  document.querySelectorAll("#fp-cases button").forEach((x) => x.setAttribute("aria-selected", x.dataset.case === first.id ? "true" : "false"));
  select(first);
  map.on("load", () => {
    loaded = true;
    drawCase(current);
    document.documentElement.dataset.fpReady = "1";
  });
}

main();
