// Orbit's map, on the suite's stack (COP, Blackout): vendored MapLibre GL JS 6.14.0, Natural Earth land served from
// this site at world zoom, OpenFreeMap's vector map once zoomed in past DETAIL_ZOOM, and Natural Earth alone at every
// zoom if OpenFreeMap can't be reached. Colours come from style.css (the validated actor tokens) through MapLibre
// paint, so there are no inline styles (CSP).
// What it draws: launches of the last 7 days at their GCAT site (filled dots), scheduled launches at their pad
// (rings), and launch hazard and space-debris areas from navigational warnings in force (outlines; dashed for
// debris). Dot colour is the launching country (GCAT) or the provider's country (Launch Library 2).
import * as ml from "./vendor/maplibre-gl/maplibre-gl.mjs";

const dark = matchMedia("(prefers-color-scheme: dark)");
const DETAIL_ZOOM = 3.5;
const BASE = {
  light: { style: "https://tiles.openfreemap.org/styles/positron", land: "#F2F3F0", water: "#C2C8CA", border: "#B9BEC2" },
  dark: { style: "https://tiles.openfreemap.org/styles/dark", land: "#1A1D22", water: "#0C0F14", border: "#3A3F46" },
};
const CLICK = ["or-launch", "or-pad", "or-area-fill"];

const theme = () => (dark.matches ? "dark" : "light");
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const worldSource = () => ({ type: "geojson", data: new URL("data/world.geojson", location.href).href, maxzoom: 5, tolerance: 1 });
const worldLayers = (b, maxzoom) => [
  { id: "or-land", type: "fill", source: "or_world", ...(maxzoom ? { maxzoom } : {}), paint: { "fill-color": b.land } },
  { id: "or-borders", type: "line", source: "or_world", ...(maxzoom ? { maxzoom } : {}), paint: { "line-color": b.border, "line-width": 0.6 } },
];
function fallbackStyle() {
  const b = BASE[theme()];
  return { version: 8, sources: { or_world: worldSource() },
    layers: [{ id: "bg", type: "background", paint: { "background-color": b.water } }, ...worldLayers(b)] };
}
async function buildStyle() {
  const b = BASE[theme()];
  let s;
  try {
    const r = await fetch(b.style);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    s = await r.json();
  } catch {
    return { style: fallbackStyle(), fellBack: true };
  }
  s.layers = s.layers.filter((l) => l.source !== "ne2_shaded");
  delete s.sources.ne2_shaded;
  for (const l of s.layers) {
    if (l.type === "background") {
      l.paint = { ...l.paint, "background-color": ["step", ["zoom"], b.water, DETAIL_ZOOM, (l.paint && l.paint["background-color"]) || b.land] };
    } else if (l.source) {
      l.minzoom = Math.max(l.minzoom || 0, DETAIL_ZOOM);
    }
  }
  s.sources.or_world = worldSource();
  s.layers.splice(s.layers.findIndex((l) => l.type === "background") + 1, 0, ...worldLayers(b, DETAIL_ZOOM));
  return { style: s, fellBack: false };
}

export async function createMap(container, model, { onPick }) {
  const first = await buildStyle();
  const fitZoom = Math.max(0, Math.log2(container.clientWidth / 512));
  const map = new ml.Map({
    container, style: first.style, center: [150, 20], zoom: fitZoom,
    dragRotate: false, pitchWithRotate: false, cooperativeGestures: true, renderWorldCopies: true,
    attributionControl: { compact: true, customAttribution: "Land: Natural Earth · Warnings: NGA, Japan Coast Guard" },
  });
  map.touchZoomRotate.disableRotation();
  map.addControl(new ml.NavigationControl({ showCompass: false }), "top-right");
  map.getCanvas().setAttribute("aria-label",
    "Map of launch sites, pads and hazard areas. Every item on it is also listed in the tables on this page.");
  setFallbackNote(first.fellBack);

  function setFallbackNote(on) {
    const stage = container.parentElement;
    stage.querySelectorAll(".fallback-note").forEach((e) => e.remove());
    if (on) {
      const p = document.createElement("p");
      p.className = "fallback-note small muted";
      p.textContent = "Detailed base map unavailable: showing outline land.";
      stage.append(p);
    }
  }

  function addLayers() {
    const g = { us: css("--g-us"), cn: css("--g-cn"), ru: css("--g-ru"), other: css("--g-other") };
    const ink = css("--text"), ring = css("--panel");
    const actor = ["match", ["get", "group"], "us", g.us, "cn", g.cn, "ru", g.ru, g.other];
    map.addSource("or_areas", { type: "geojson", data: model.areas, maxzoom: 8 });
    map.addSource("or_launches", { type: "geojson", data: model.launches, maxzoom: 10 });
    map.addSource("or_pads", { type: "geojson", data: model.pads, maxzoom: 10 });
    map.addLayer({ id: "or-area-fill", type: "fill", source: "or_areas", paint: { "fill-color": ink, "fill-opacity": 0.07 } });
    map.addLayer({ id: "or-area-line", type: "line", source: "or_areas", filter: ["!=", ["get", "debris"], true],
      paint: { "line-color": ink, "line-width": 1.4, "line-opacity": 0.8 } });
    map.addLayer({ id: "or-area-debris", type: "line", source: "or_areas", filter: ["==", ["get", "debris"], true],
      paint: { "line-color": ink, "line-width": 1.2, "line-opacity": 0.7, "line-dasharray": [3, 2] } });
    map.addLayer({ id: "or-sel", type: "line", source: "or_areas", filter: ["==", ["get", "key"], ""],
      paint: { "line-color": ink, "line-width": 3 } });
    map.addLayer({ id: "or-pad", type: "circle", source: "or_pads",
      paint: { "circle-radius": 5.5, "circle-color": ring, "circle-stroke-color": actor, "circle-stroke-width": 2.6 } });
    map.addLayer({ id: "or-launch", type: "circle", source: "or_launches",
      paint: { "circle-radius": 5.5, "circle-color": actor, "circle-stroke-color": ink, "circle-stroke-width": 1 } });
  }
  map.on("style.load", addLayers);
  dark.addEventListener("change", async () => {
    const next = await buildStyle();
    setFallbackNote(next.fellBack);
    map.setStyle(next.style, { diff: false });
  });

  const box = (pt, pad) => [[pt.x - pad, pt.y - pad], [pt.x + pad, pt.y + pad]];
  function pick(pt) {
    const live = CLICK.filter((id) => map.getLayer(id));
    const pts = map.queryRenderedFeatures(box(pt, 7), { layers: live.filter((id) => id !== "or-area-fill") });
    if (pts.length) return pts[0].properties.key;
    const areas = map.queryRenderedFeatures(pt, { layers: live.filter((id) => id === "or-area-fill") });
    return areas.length ? areas[0].properties.key : null;
  }
  map.on("click", (e) => { const key = pick(e.point); if (key) onPick(key); });
  map.on("mousemove", (e) => { map.getCanvas().style.cursor = pick(e.point) ? "pointer" : ""; });

  return {
    resize: () => map.resize(),
    select(key) {
      if (map.getLayer("or-sel")) map.setFilter("or-sel", ["==", ["get", "key"], key || ""]);
    },
    flyTo(key) {
      const f = model.areas.features.filter((x) => x.properties.key === key);
      if (f.length) {
        const b = new ml.LngLatBounds();
        f.forEach((x) => x.geometry.coordinates[0].forEach((c) => b.extend(c)));
        map.fitBounds(b, { padding: 30, maxZoom: 6, duration: 800 });
        return;
      }
      const p = [...model.launches.features, ...model.pads.features].find((x) => x.properties.key === key);
      if (p) map.flyTo({ center: p.geometry.coordinates, zoom: Math.max(map.getZoom(), 5) });
    },
  };
}
