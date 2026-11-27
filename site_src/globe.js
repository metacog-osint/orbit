// Orbit's globe (orbit-2.11, decisions 4 and 7, 15 Nov 2026: Cesium ion; ground tracks only here, pads stay
// COP's mark). CesiumJS 1.146.0 and satellite.js 7.1.0 are self-hosted in vendor/ like MapLibre (licences there).
// It draws the flat map's launches of the last 7 days on a globe (the scheduled launches, ledger history, hazard
// areas and Launch's lines it drew until orbit-2.32 are Launch's now, ideas#69), plus the satellites whose orbit
// changes Orbit lists: each one's place now and its path over one orbit (a day at GEO), propagated with SGP4 from the newest
// Space-Track element set Orbit holds, drag left out. A drawing for orientation, not a tracking product.
// Imagery: Cesium ion (Bing Maps aerial, asset 2) with the site's public token (data/cesium.json, written by the
// build from the repository variable CESIUM_ION_TOKEN, restricted to Orbit's hosts); without a token, or if ion
// refuses it, Natural Earth II from Cesium's own assets. Only CesiumWidget is used: the Viewer's widgets need
// eval (knockout), which the site's CSP forbids. Same interface as map.js, so the page's cards work with either.
import { json2satrec } from "./vendor/satellite.js/io.js";
import { propagate, gstime } from "./vendor/satellite.js/propagation.js";
import { eciToEcf, eciToGeodetic } from "./vendor/satellite.js/transforms.js";

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
export function loadCesium() {
  if (window.Cesium) return Promise.resolve(window.Cesium);
  const BASE = new URL("vendor/cesium/", location.href).href;
  window.CESIUM_BASE_URL = BASE;
  return new Promise((resolve, reject) => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = BASE + "Widgets/widgets.css";
    document.head.append(link);
    const s = document.createElement("script");
    s.src = BASE + "Cesium.js";
    s.onload = () => (window.Cesium ? resolve(window.Cesium) : reject(new Error("Cesium did not load")));
    s.onerror = () => reject(new Error("Cesium.js could not be fetched"));
    document.head.append(s);
  });
}

export async function token() {
  try {
    const r = await fetch("data/cesium.json", { cache: "no-cache" });
    return r.ok ? ((await r.json()).token || null) : null;
  } catch {
    return null;
  }
}

export async function baseLayer(C, tok) {
  if (tok) {
    try {
      C.Ion.defaultAccessToken = tok;
      return { layer: new C.ImageryLayer(await C.IonImageryProvider.fromAssetId(2)), ion: true };
    } catch { /* refused (wrong host, revoked, offline): fall through to the local imagery */ }
  }
  const p = await C.TileMapServiceImageryProvider.fromUrl(C.buildModuleUrl("Assets/Textures/NaturalEarthII"));
  return { layer: new C.ImageryLayer(p), ion: false };
}

// One satellite's path from its element set: positions (Earth-fixed, metres) and the ground track, over one orbit
// (or a day, whichever is shorter), centred on now. Returns null when SGP4 cannot use the set.
export function path(el, now = new Date(), steps = 120) {
  if (!el || !el.n) return null;
  let rec;
  try {
    rec = json2satrec({ NORAD_CAT_ID: el.norad || 0, EPOCH: el.epoch, MEAN_MOTION: el.n, ECCENTRICITY: el.e,
      INCLINATION: el.i, RA_OF_ASC_NODE: el.raan, ARG_OF_PERICENTER: el.argp, MEAN_ANOMALY: el.ma,
      BSTAR: 0, MEAN_MOTION_DOT: 0, MEAN_MOTION_DDOT: 0 });
  } catch {
    return null;
  }
  const periodMin = Math.min(1440, 1440 / el.n);
  const out = { orbit: [], ground: [], now: null };
  for (let k = 0; k <= steps; k++) {
    const t = new Date(now.getTime() + (k / steps - 0.5) * periodMin * 60000);
    const pv = propagate(rec, t);
    if (!pv || !pv.position || typeof pv.position === "boolean") continue;
    const g = gstime(t), ecf = eciToEcf(pv.position, g), geo = eciToGeodetic(pv.position, g);
    out.orbit.push([ecf.x * 1000, ecf.y * 1000, ecf.z * 1000]);
    out.ground.push([geo.longitude * 180 / Math.PI, geo.latitude * 180 / Math.PI]);
  }
  const pv = propagate(rec, now);
  if (pv && pv.position && typeof pv.position !== "boolean") {
    const ecf = eciToEcf(pv.position, gstime(now));
    out.now = [ecf.x * 1000, ecf.y * 1000, ecf.z * 1000];
  }
  return out.orbit.length > 1 ? out : null;
}

// A reentry track (orbit-2.15): the ground track from t0 to t1 (ms), one point a minute at most 2,880, with drag
// kept (BSTAR and the mean-motion rate from the set), since drag shapes a decaying object's track. Points SGP4
// refuses (the orbit has decayed in the model) are left out. Returns [[lon, lat], ...] or null.
export function span(el, t0, t1) {
  if (!el || !el.n || !(t1 > t0)) return null;
  let rec;
  try {
    rec = json2satrec({ NORAD_CAT_ID: el.norad || 0, EPOCH: el.epoch, MEAN_MOTION: el.n, ECCENTRICITY: el.e,
      INCLINATION: el.i, RA_OF_ASC_NODE: el.raan, ARG_OF_PERICENTER: el.argp, MEAN_ANOMALY: el.ma,
      BSTAR: el.bstar || 0, MEAN_MOTION_DOT: el.ndot || 0, MEAN_MOTION_DDOT: 0 });
  } catch {
    return null;
  }
  const steps = Math.min(2880, Math.max(2, Math.round((t1 - t0) / 60000)));
  const out = [];
  for (let k = 0; k <= steps; k++) {
    const t = new Date(t0 + (k / steps) * (t1 - t0));
    const pv = propagate(rec, t);
    if (!pv || !pv.position || typeof pv.position === "boolean") continue;
    const geo = eciToGeodetic(pv.position, gstime(t));
    out.push([geo.longitude * 180 / Math.PI, geo.latitude * 180 / Math.PI]);
  }
  return out.length > 1 ? out : null;
}

export async function createGlobe(container, model, { onPick }) {
  const C = await loadCesium();
  // Cesium.js carries its workers as one string and starts them from blob: URLs, which script-src 'self' refuses.
  // Without that string it starts the same workers as ES modules from vendor/cesium/Workers/ on this origin.
  globalThis.CESIUM_WORKERS = undefined;
  const base = await baseLayer(C, await token());
  const widget = new C.CesiumWidget(container, {
    baseLayer: base.layer, terrainProvider: new C.EllipsoidTerrainProvider(), sceneModePicker: false,
    skyAtmosphere: new C.SkyAtmosphere(), requestRenderMode: true, maximumRenderTimeChange: Infinity,
  });
  widget.scene.globe.enableLighting = false;
  widget.camera.setView({ destination: C.Cartesian3.fromDegrees(150, 20, 2.4e7) });
  widget.canvas.setAttribute("aria-label",
    "Globe of the launch sites of the last 7 days and the paths of satellites with listed orbit changes. " +
    "Every item on it is also listed in the tables on this page.");
  if (!base.ion) {
    const p = document.createElement("p");
    p.className = "fallback-note small muted";
    p.textContent = "Imagery: Natural Earth II (Cesium ion not reached).";
    container.parentElement.querySelectorAll(".fallback-note").forEach((e) => e.remove());
    container.parentElement.append(p);
  }

  const col = (name, a = 1) => C.Color.fromCssColorString(css(name) || "#888").withAlpha(a);
  const G = { us: "--g-us", cn: "--g-cn", ru: "--g-ru", other: "--g-other" };
  const actor = (g, a) => col(G[g] || G.other, a);
  const ink = () => col("--text");
  const E = widget.entities;
  const keyOf = new Map(); // entity id -> page key
  let selected = null;

  const add = (key, spec) => { const e = E.add(spec); keyOf.set(e.id, key); return e; };
  const lonlat = (c) => C.Cartesian3.fromDegrees(c[0], c[1]);

  function points() {
    for (const f of model.launches.features) {
      add(f.properties.key, { position: lonlat(f.geometry.coordinates), point: { pixelSize: 11,
        color: actor(f.properties.group), outlineColor: ink(), outlineWidth: 1 } });
    }
  }
  const drawn = { tracks: 0, without: 0, launches: Object.keys(model.payloadTracks || {}).length,
    reentries: Object.keys(model.reentryTracks || {}).length };
  let payloadKey = null, reentryKey = null;
  function reentry() {  // the picked object's track over its TIP window, and TIP's point at the predicted time
    const r = reentryKey && (model.reentryTracks || {})[reentryKey];
    if (!r) return;
    const g = span(r.elements, Date.parse(r.from), Date.parse(r.to));
    const c = actor(r.group);
    if (g) {
      add(r.key, { polyline: { positions: g.map(lonlat), width: 2, arcType: C.ArcType.GEODESIC, material: c.withAlpha(0.8) } });
    }
    if (r.lat != null && r.lon != null) {
      add(r.key, { position: C.Cartesian3.fromDegrees(r.lon, r.lat), point: { pixelSize: 10, color: c, outlineColor: ink(),
        outlineWidth: 1.5 }, label: { text: r.name + ": TIP point at the predicted time", font: "12px system-ui, sans-serif",
        fillColor: ink(), showBackground: true, backgroundColor: col("--panel", 0.85), pixelOffset: new C.Cartesian2(0, -16) } });
    }
    drawn.reentryPoints = g ? g.length : 0;
  }
  function tracks() {
    const now = new Date();
    drawn.tracks = 0; drawn.without = 0;
    const list = [...(model.tracks || []), ...((payloadKey && (model.payloadTracks || {})[payloadKey]) || [])
      .map((t, _, all) => ({ ...t, payload: true, quiet: all.length > 6 }))];  // a big batch: no labels
    for (const t of list) {
      const p = path(t.elements, now);
      if (!p) { if (!t.payload) drawn.without++; continue; }
      if (!t.payload) drawn.tracks++;
      const c = actor(t.group);
      add(t.key, { polyline: { positions: p.orbit.map((x) => new C.Cartesian3(x[0], x[1], x[2])), width: 1.6,
        arcType: C.ArcType.NONE, material: c.withAlpha(0.85) } });
      add(t.key, { polyline: { positions: p.ground.map(lonlat), width: 1, arcType: C.ArcType.GEODESIC,
        material: new C.PolylineDashMaterialProperty({ color: c.withAlpha(0.6), dashLength: 8 }) } });
      if (p.now) {
        add(t.key, { position: new C.Cartesian3(p.now[0], p.now[1], p.now[2]),
          point: { pixelSize: t.payload ? 7 : 9, color: c, outlineColor: ink(), outlineWidth: 1 },
          label: t.quiet ? undefined : { text: t.name, font: "12px system-ui, sans-serif", fillColor: ink(), showBackground: true,
            backgroundColor: col("--panel", 0.85), pixelOffset: new C.Cartesian2(0, -16),
            distanceDisplayCondition: new C.DistanceDisplayCondition(0, 1.2e8) } });
      }
    }
  }
  function draw() {
    E.removeAll();
    keyOf.clear();
    points(); tracks(); reentry();
    highlight();
    widget.scene.requestRender();
  }
  function highlight() {
    for (const e of E.values) {
      if (!e.properties || !e.properties.outline) continue;
      const on = selected && keyOf.get(e.id) === selected;
      e.polyline.width = on ? 3.4 : 1.6;
    }
    widget.scene.requestRender();
  }
  draw();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", draw);

  const handler = new C.ScreenSpaceEventHandler(widget.canvas);
  const pickKey = (pos) => {
    const hit = widget.scene.pick(pos);
    return hit && hit.id ? keyOf.get(hit.id.id) || null : null;
  };
  // A click takes everything under the pointer and prefers a recent launch, then a listed change or reentry.
  const RANK = [["launch-", 0], ["re-", 1], ["mv-", 1]];
  const rank = (k) => (RANK.find(([p]) => k.startsWith(p)) || [null, 4])[1];
  const clickKey = (pos) => {
    const keys = widget.scene.drillPick(pos, 10).map((h) => (h && h.id ? keyOf.get(h.id.id) : null)).filter(Boolean);
    return keys.sort((a, b) => rank(a) - rank(b))[0] || null;
  };
  handler.setInputAction((ev) => { const k = clickKey(ev.position); if (k) onPick(k); }, C.ScreenSpaceEventType.LEFT_CLICK);
  handler.setInputAction((ev) => { widget.canvas.style.cursor = pickKey(ev.endPosition) ? "pointer" : ""; },
    C.ScreenSpaceEventType.MOUSE_MOVE);

  return {
    drawn,
    ion: base.ion,
    resize: () => { widget.resize(); widget.scene.requestRender(); },
    select(key) { selected = key || null; highlight(); },
    showReentry(key) {
      const k = key && (model.reentryTracks || {})[key] ? key : null;
      if (k === reentryKey) return;
      reentryKey = k; draw();
      const r = k && model.reentryTracks[k];
      if (r && r.lat != null) widget.camera.flyTo({ destination: C.Cartesian3.fromDegrees(r.lon, r.lat, 2.2e7), duration: 0.8 });
    },
    showPayloads(key) {
      const k = key && (model.payloadTracks || {})[key] ? key : null;
      if (k === payloadKey) return;
      payloadKey = k; draw();
    },
    flyTo(key) {
      const p = model.launches.features.find((x) => x.properties.key === key);
      if (p) widget.camera.flyTo({ destination: C.Cartesian3.fromDegrees(p.geometry.coordinates[0], p.geometry.coordinates[1], 3.5e6), duration: 0.8 });
    },
    destroy() { handler.destroy(); widget.destroy(); },
  };
}

// One object's globe (orbit-2.20, object pages): its path over one orbit centred on now (or a day at GEO), its place
// now and its ground track, from the one element set Orbit holds for it, drag left out; or, for an object with an
// open TIP window, its ground track over that window with drag kept and TIP's point. `spec`: { elements, name,
// window: {from, to, lat, lon} | null }. Returns { ion, resize, destroy } or throws when the set cannot be used.
export async function createObjectGlobe(container, spec) {
  const C = await loadCesium();
  globalThis.CESIUM_WORKERS = undefined;
  const base = await baseLayer(C, await token());
  const widget = new C.CesiumWidget(container, {
    baseLayer: base.layer, terrainProvider: new C.EllipsoidTerrainProvider(), sceneModePicker: false,
    skyAtmosphere: new C.SkyAtmosphere(), requestRenderMode: true, maximumRenderTimeChange: Infinity,
  });
  widget.scene.globe.enableLighting = false;
  widget.canvas.setAttribute("aria-label", "Globe with " + spec.name + "'s path from the element set named under it.");
  const col = (name, a = 1) => C.Color.fromCssColorString(css(name) || "#888").withAlpha(a);
  const E = widget.entities, lonlat = (c) => C.Cartesian3.fromDegrees(c[0], c[1]);
  const drawn = { orbit: false, window: false };
  function draw() {
    E.removeAll();
    const c = col("--accent"), ink = col("--text");
    const w = spec.window;
    if (w) {
      const g = span(spec.elements, Date.parse(w.from), Date.parse(w.to));
      if (g) {
        drawn.window = true;
        E.add({ polyline: { positions: g.map(lonlat), width: 2, arcType: C.ArcType.GEODESIC, material: c.withAlpha(0.85) } });
      }
      if (w.lat != null && w.lon != null) {
        E.add({ position: C.Cartesian3.fromDegrees(w.lon, w.lat), point: { pixelSize: 10, color: c, outlineColor: ink, outlineWidth: 1.5 },
          label: { text: "TIP point at the predicted time", font: "12px system-ui, sans-serif", fillColor: ink, showBackground: true,
            backgroundColor: col("--panel", 0.85), pixelOffset: new C.Cartesian2(0, -16) } });
      }
      if (g || w.lat != null) return;
    }
    const p = path(spec.elements, new Date());
    if (!p) return;
    drawn.orbit = true;
    drawn.center = p.ground[Math.floor(p.ground.length / 2)];
    E.add({ polyline: { positions: p.orbit.map((x) => new C.Cartesian3(x[0], x[1], x[2])), width: 1.8, arcType: C.ArcType.NONE,
      material: c.withAlpha(0.9) } });
    E.add({ polyline: { positions: p.ground.map(lonlat), width: 1, arcType: C.ArcType.GEODESIC,
      material: new C.PolylineDashMaterialProperty({ color: c.withAlpha(0.6), dashLength: 8 }) } });
    if (p.now) {
      E.add({ position: new C.Cartesian3(p.now[0], p.now[1], p.now[2]), point: { pixelSize: 9, color: c, outlineColor: ink, outlineWidth: 1 },
        label: { text: spec.name, font: "12px system-ui, sans-serif", fillColor: ink, showBackground: true,
          backgroundColor: col("--panel", 0.85), pixelOffset: new C.Cartesian2(0, -16) } });
    }
  }
  draw();
  const w = spec.window;
  const far = spec.elements && spec.elements.n && spec.elements.n < 2 ? 7.5e7 : 2.4e7;  // GEO and high orbits: further out
  widget.camera.setView({ destination: w && w.lat != null ? C.Cartesian3.fromDegrees(w.lon, w.lat, 2.2e7)
    : C.Cartesian3.fromDegrees(drawn.center ? drawn.center[0] : 0, drawn.center ? drawn.center[1] : 20, far) });
  widget.scene.requestRender();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { draw(); widget.scene.requestRender(); });
  return { ion: base.ion, drawn, resize: () => { widget.resize(); widget.scene.requestRender(); }, destroy: () => widget.destroy() };
}
