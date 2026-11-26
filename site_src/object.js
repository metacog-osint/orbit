/* Orbit's object page (orbit-2.20, 18 Nov 2026; design in the private planning notes).
   object.html?n=<NORAD number> or ?j=<GCAT JCAT id>. Reads the TIC satellite catalog's shard for the object
   (data/catalog/, unpacked by the update run from release `catalog`) and its rules note, plus Orbit's own snapshot
   and daily archive. Every value names its source; sources that disagree are shown side by side and never merged.
   Times are stored UTC and shown in the viewer's zone (tic-time.js). No inline scripts (CSP). */
(function () {
  "use strict";
  var T = window.TicTime;
  var q = new URLSearchParams(location.search);
  var KEY = (q.get("n") || q.get("j") || "").trim().toUpperCase().replace(/^S0*(?=\d)/, "").replace(/^0+(?=\d)/, "");
  var NUMBERED = /^\d+$/.test(KEY);
  var shard = null, rules = null, man = null, snap = null, arc = null, obj = null, movers = null;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }
  function fmt(iso) { return !iso ? "" : T ? T.format(iso, {}) : iso.replace("T", " "); }
  /* A date as the source gives it (a day, no time): written with its year and never moved to another time zone. */
  var DATE = null;
  try { DATE = new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" }); } catch (e) { DATE = null; }
  function day(d) {
    if (!d) return "";
    var s = String(d).slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return String(d);
    return DATE ? DATE.format(new Date(s + "T12:00:00Z")) : s;
  }
  function num(x, dp) { return x == null ? "–" : Number(x).toLocaleString(undefined, { maximumFractionDigits: dp == null ? 0 : dp }); }
  var REGION = null;
  try { REGION = new Intl.DisplayNames(["en"], { type: "region" }); } catch (e) { REGION = null; }
  function country(cc) { try { return (cc && cc.length === 2 && REGION && REGION.of(cc)) || cc; } catch (e) { return cc; } }
  function link(text, href, ext) { var a = el("a", "", text); a.href = href; if (ext) a.rel = "noopener"; return a; }
  function objHref(key) { return "object.html?" + (/^\d+$/.test(String(key)) ? "n=" : "j=") + encodeURIComponent(key); }
  function table(head, rows) {
    var t = el("table"), th = el("thead"), tr = el("tr");
    head.forEach(function (h) { tr.appendChild(el("th", "", h)); });
    th.appendChild(tr); t.appendChild(th);
    var tb = el("tbody");
    rows.forEach(function (r) {
      var row = el("tr");
      r.forEach(function (c, i) {
        var td = el("td");
        td.setAttribute("data-label", head[i]);
        if (c instanceof Node) td.appendChild(c); else td.textContent = c == null ? "" : c;
        row.appendChild(td);
      });
      tb.appendChild(row);
    });
    t.appendChild(tb);
    var w = el("div", "tbl-wrap");
    w.appendChild(t);
    return w;
  }
  function sub(box, title, intro) {
    var s = el("div", "obj-sub");
    s.appendChild(el("h3", "", title));
    if (intro) s.appendChild(el("p", "small muted", intro));
    box.appendChild(s);
    return s;
  }
  function shardName(key) {
    if (/^\d+$/.test(key)) return "n" + Math.floor(parseInt(key, 10) / 1000) + ".json";
    var m = /^([A-Z])0*(\d+)$/.exec(key);
    return m ? "j" + m[1] + Math.floor(parseInt(m[2], 10) / 1000) + ".json" : null;
  }
  function getJson(url) {
    return fetch(url, { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
  }

  /* Compact records (tic-catalog/2): `read` left out when it is the source's read date, `ref` when it is the object's
     own key in that source, `basis` when "attributed" (the shard's record_defaults). Put them back. */
  function full(rec) {
    var r = Object.assign({}, rec), src = (shard.sources || {})[r.source] || {};
    if (!r.read) r.read = src.read || null;
    if (!r.basis) r.basis = "attributed";
    if (!r.ref) r.ref = r.source === "gcat-mcdowell" ? obj.jcat : (r.source === "space-track" || r.source === "celestrak-satcat") ? obj.norad : null;
    return r;
  }
  function recs(field) {
    var r = ((obj && obj[field]) || []).map(full);
    if (field !== "decay_date") return r;
    var gone = {};
    ((obj && obj.decayed) || []).forEach(function (x) { if (x.value) gone[x.source] = 1; });
    return r.filter(function (x) { return gone[x.source]; });  // GCAT gives a date for docked or grouped objects too
  }
  function label(src) { var s = (rules && rules.sources || {})[src] || {}; return s.label || src; }
  function rankOf(src) { var i = ((rules && rules.rank) || []).indexOf(src); return i < 0 ? 99 : i; }

  var GCAT_STATUS = { O: "in orbit", R: "reentered", D: "deorbited", L: "landed", E: "exploded", C: "collided" };
  var OPS = { "+": "operational", "-": "nonoperational", P: "partially operational", B: "backup or standby", S: "spare",
    X: "extended mission", D: "decayed or deorbited", "?": "unknown" };
  var TYPES = { payload: "payload", rocket: "rocket stage", debris: "debris", component: "component" };

  // ---------------------------------------------------------------- header
  function head() {
    var name = obj ? obj.name : holdingsName() || (NUMBERED ? "NORAD " + KEY : KEY);
    document.title = name + " · Orbit · The Intelligence Company";
    document.getElementById("obj-name").textContent = name;
    var subl = document.getElementById("obj-sub"), facts = document.getElementById("obj-facts");
    subl.textContent = ""; facts.textContent = "";
    var bits = [NUMBERED ? "NORAD " + KEY : "GCAT " + KEY + " (no NORAD number)"];
    if (obj) {
      var ids = uniq(recs("intldes").map(function (r) { return r.value; }));
      if (ids.length) bits.push("COSPAR " + ids.join(" or "));
      if (obj.type) bits.push(TYPES[obj.type] || obj.type);
      if (NUMBERED && obj.jcat) bits.push("GCAT " + obj.jcat);
    }
    subl.textContent = bits.join(" · ");
    if (!obj) return;
    function fact(dt, dd) { facts.appendChild(el("dt", "", dt)); var d = el("dd"); if (dd instanceof Node) d.appendChild(dd); else d.textContent = dd; facts.appendChild(d); }
    function each(field, show) {
      var r = recs(field).sort(function (a, b) { return rankOf(a.source) - rankOf(b.source); });
      if (!r.length) return null;
      var d = el("span");
      r.forEach(function (x, i) {
        if (i) d.appendChild(document.createTextNode("; "));
        d.appendChild(document.createTextNode(show(x) + " "));
        d.appendChild(el("span", "src", "(" + label(x.source) + ")"));
      });
      return d;
    }
    var st = each("status", function (x) { return (GCAT_STATUS[x.value] ? GCAT_STATUS[x.value] + ", " : "") + "status " + x.value; });
    if (st) fact("Status", st);
    var gone = recs("decayed").filter(function (x) { return x.value; });
    if (gone.length) {
      fact("Left orbit", each("decay_date", function (x) { return day(x.value); }) || "yes, by " + gone.map(function (x) { return label(x.source); }).join(", "));
    }
    var ops = each("ops_status", function (x) { return OPS[x.value] ? OPS[x.value] + " (" + x.value + ")" : x.value; });
    if (ops) fact("Operational status", ops);
    var ow = each("owner", function (x) { return (x.name && x.name !== x.value ? x.name + " (" + x.value + ")" : x.value); });
    if (ow) fact("Owner", ow);
    var stt = each("state", function (x) { return (x.value.length === 2 ? country(x.value) + " (" + x.value + ")" : x.value) +
      (x.cmp && x.cmp !== x.value ? ", compared as " + x.cmp : "") + (x.nocompare ? ", not compared" : ""); });
    if (stt) fact("State", stt);
    var ld = each("launch_date", function (x) { return day(x.value); });
    if (ld) {
      var tag = (recs("launch_tag")[0] || {}).value;
      if (tag) {
        ld.appendChild(document.createTextNode(" · launch " + tag + " "));
        ld.appendChild(link("in Launch's history", "https://launch.theintelligence.company/#history?st=launched&q=" +
          encodeURIComponent(tag) + "&sel=" + encodeURIComponent("gcat:" + tag), true));
      }
      fact("Launched", ld);
    }
    if (obj.program) fact("Programme", [].concat(obj.program).map(function (p) { return p.value || p; }).join(", ") + " (TIC alias file)");
    stale();
  }
  function uniq(a) { var s = {}; return a.filter(function (x) { if (x == null || s[x]) return false; s[x] = 1; return true; }); }
  function stale() {
    var box = document.getElementById("obj-stale");
    if (!man) return;
    var h = rules && rules.stale_after_hours || 36;
    var read = Date.parse((man.catalog_read || "") + "T23:59:59Z");
    var age = (Date.now() - read) / 3600000;
    var g = ((shard.sources || {})["gcat-mcdowell"] || {}).updated;
    box.textContent = "TIC satellite catalog built " + day(man.catalog_read) + (g ? " from GCAT's copy of " + g + " UTC" : "") +
      "; on this site since " + fmt(man.unpacked_at) + "." + (age > h ? " That is over " + h + " hours old: values may have changed since." : "");
  }

  // ---------------------------------------------------------------- orbit
  function regime(p, a, inc) {
    if (p == null) return "";
    if (a == null) return "an escape or deep-space path (no apogee given)";
    if (a < 2000) return "low Earth orbit (LEO, below about 2,000 km)";
    if (p > 35286 && a < 36286) return "geostationary or near it (GEO, about 35,786 km)" + (inc > 1 ? ", inclined " + num(inc, 1) + "°" : "");
    if (p >= 2000 && a < 35286) return "medium Earth orbit (MEO, between LEO and GEO)";
    if (p < 2000) return "an elliptical orbit with its perigee in LEO and its apogee higher (often called HEO)";
    return "above geostationary";
  }
  function orbitRecs() {
    return recs("orbit").filter(function (r) { return r.value && r.value.perigee_km != null; })
      .sort(function (a, b) { return rankOf(a.source) - rankOf(b.source); });
  }
  function orbitCard() {
    var box = document.getElementById("obj-orbit");
    box.textContent = "";
    var r = orbitRecs();
    if (!obj) return box.appendChild(el("p", "muted small", "The TIC catalog's record is not on the site, so no orbit is shown."));
    if (!r.length) return box.appendChild(el("p", "muted small", "No source in the catalog gives an orbit for this object."));
    box.appendChild(table(["Source", "Perigee × apogee", "Inclination", "Period", "Dated", "Reads as"], r.map(function (x) {
      var v = x.value, src = (shard.sources || {})[x.source] || {};
      var dated = x.source === "gcat-mcdowell" ? (v.elements_date ? "elements of " + day(v.elements_date) : "") :
        x.source === "celestrak-satcat" ? (src.file_time ? "file of " + src.file_time : "read " + day(x.read)) : day(x.read);
      return [label(x.source) + (v.op_orbit ? " (class " + v.op_orbit + ")" : "") + (v.orbit_type && v.orbit_type !== "ORB" ? " (" + v.orbit_type + ")" : ""),
        num(v.perigee_km) + " × " + (v.apogee_km == null ? "–" : num(v.apogee_km)) + " km", v.inc_deg == null ? "–" : num(v.inc_deg, 2) + "°",
        v.period_min ? num(v.period_min, 1) + " min" : "", dated, regime(v.perigee_km, v.apogee_km, v.inc_deg)];
    })));
    var g = r.filter(function (x) { return x.source === "gcat-mcdowell"; })[0];
    if (g && g.value.elements_date && Date.now() - Date.parse(g.value.elements_date) > 365 * 86400000) {
      box.appendChild(el("p", "small muted", "GCAT's elements here are from " + day(g.value.elements_date) +
        ": GCAT keeps an orbit from a set date, which can be years old for objects that have since moved or decayed."));
    }
  }

  // ---------------------------------------------------------------- globe (option A: sets Orbit already holds)
  function sets() {
    var n = NUMBERED ? KEY : obj && obj.norad != null ? String(obj.norad) : null, out = [];
    if (!n || !snap) return out;
    var rs = ((snap.reentry_sets || {}).sets || {})[n];
    var tip = ((snap.decay || {}).objects || []).filter(function (x) { return String(x.norad) === n; })[0];
    if (rs) out.push({ el: Object.assign({ norad: +n }, rs), src: "Space-Track.org (USSPACECOM) element set, fetched with the TIP lane",
      window: tip && !tip.passed ? { from: new Date(Date.parse(tip.decay_epoch) - Math.min(tip.window_min || 60, 1440) * 60000).toISOString(),
        to: new Date(Date.parse(tip.decay_epoch) + Math.min(tip.window_min || 60, 1440) * 60000).toISOString(), lat: tip.lat, lon: tip.lon } : null });
    ((snap.maneuvers || {}).events || []).forEach(function (e) {
      if (String(e.norad) === n && e.elements) out.push({ el: Object.assign({ norad: +n }, e.elements), src: "Space-Track.org (USSPACECOM) element set, the newest Orbit holds for a listed orbit change" });
    });
    var by = (snap.payload_sets || {}).by_launch || {};
    Object.keys(by).forEach(function (k) {
      by[k].forEach(function (o) { if (String(o.norad) === n && o.elements) out.push({ el: Object.assign({ norad: +n }, o.elements), src: "CelesTrak's last-30-days group (18th Space Defense Squadron data)" }); });
    });
    out.sort(function (a, b) { return Date.parse(b.el.epoch + (/Z$/.test(b.el.epoch) ? "" : "Z")) - Date.parse(a.el.epoch + (/Z$/.test(a.el.epoch) ? "" : "Z")); });
    return out;
  }
  function globeCard() {
    var box = document.getElementById("obj-globe-body");
    box.textContent = "";
    var s = sets()[0];
    if (s) {
      var ep = s.el.epoch + (/Z$/.test(s.el.epoch) ? "" : "Z");
      box.appendChild(el("p", "small", (s.window ? "Its ground track over TIP's window, drag kept, with TIP's point at the predicted time. " :
        "Its path over one orbit centred on when you open the globe (a day at GEO), its place then, and its ground track (dashed). ") +
        "Propagated with SGP4 from the " + s.src + ", epoch " + fmt(ep) + ". A drawing for orientation, not a tracking product; " +
        "not for operational use."));
      var b = el("button", "linkish", "Show on the globe (about 6 MB, once)");
      b.type = "button";
      b.addEventListener("click", function () {
        var g = document.getElementById("obj-globe");
        g.hidden = false; b.disabled = true; b.textContent = "Loading the globe…";
        import("./globe.js").then(function (m) {
          return m.createObjectGlobe(g, { elements: s.el, name: obj ? obj.name : document.getElementById("obj-name").textContent, window: s.window });
        }).then(function (api) {
          b.remove();
          if (!api.drawn.orbit && !api.drawn.window) box.appendChild(el("p", "small muted", "SGP4 could not use this element set, so nothing is drawn."));
          box.appendChild(el("p", "small muted", api.ion ? "Imagery: Cesium ion (Bing Maps)." : "Imagery: Natural Earth II, shipped with CesiumJS."));
        }).catch(function (e) { b.textContent = "The globe could not load (" + e + ")."; g.hidden = true; });
      });
      box.appendChild(b);
      return;
    }
    box.appendChild(el("p", "small", "Orbit holds no element set for this object: it keeps sets only for new launches' payloads " +
      "(CelesTrak's last-30-days group), objects with an open TIP window and satellites with a listed orbit change. " +
      "The drawing shows the orbit's size, shape and tilt from the stated numbers; where the orbit's plane points and " +
      "where the object is along it are not known from these."));
    var r = orbitRecs()[0];
    if (r) box.appendChild(drawing(r));
  }
  /* Side view to scale: the Earth, the orbit's ellipse with the Earth's centre at one focus, and a second panel with the
     equator and the orbit's plane at its inclination. */
  function drawing(r) {
    var v = r.value, R = 6371, NS = "http://www.w3.org/2000/svg";
    var wrap = el("figure", "orb-fig");
    if (v.apogee_km == null) { wrap.appendChild(el("p", "small muted", "No apogee given (an escape or deep-space path), so no drawing.")); return wrap; }
    var rp = R + v.perigee_km, ra = R + v.apogee_km, a = (rp + ra) / 2, e = (ra - rp) / (ra + rp), b = a * Math.sqrt(1 - e * e);
    var W = 320, H = 300, cy = 150, scale = 140 / Math.max(a, 1.2 * R), earthX = 160 + a * e * scale;
    function svg(w, h) { var s = document.createElementNS(NS, "svg"); s.setAttribute("viewBox", "0 0 " + w + " " + h); s.setAttribute("role", "img"); return s; }
    function add(s, tag, at) { var x = document.createElementNS(NS, tag); Object.keys(at).forEach(function (k) { x.setAttribute(k, at[k]); }); s.appendChild(x); return x; }
    var s1 = svg(W, H);
    s1.setAttribute("aria-label", "The orbit's shape to scale: perigee " + num(v.perigee_km) + " km, apogee " + num(v.apogee_km) + " km.");
    // the ellipse centred in the panel, the Earth's centre at its right focus, so perigee is at the right end
    add(s1, "ellipse", { cx: 160, cy: cy, rx: a * scale, ry: b * scale, "class": "orb-path" });
    add(s1, "circle", { cx: earthX, cy: cy, r: R * scale, "class": "orb-earth" });
    var tp = add(s1, "text", { x: Math.min(W - 2, 160 + a * scale), y: cy - b * scale * 0.2 - 8, "class": "orb-txt", "text-anchor": "end" });
    tp.textContent = "perigee " + num(v.perigee_km) + " km";
    var ta = add(s1, "text", { x: Math.max(2, 160 - a * scale), y: cy + b * scale * 0.2 + 18, "class": "orb-txt" });
    ta.textContent = "apogee " + num(v.apogee_km) + " km";
    var s2 = svg(W, 160);
    s2.setAttribute("aria-label", "The orbit's tilt against the equator: " + num(v.inc_deg, 1) + " degrees.");
    add(s2, "circle", { cx: 160, cy: 80, r: 46, "class": "orb-earth" });
    add(s2, "line", { x1: 40, y1: 80, x2: 280, y2: 80, "class": "orb-eq" });
    var t = (v.inc_deg || 0) * Math.PI / 180;
    add(s2, "line", { x1: 160 - 120 * Math.cos(t), y1: 80 + 120 * Math.sin(t) * 0.6, x2: 160 + 120 * Math.cos(t), y2: 80 - 120 * Math.sin(t) * 0.6, "class": "orb-plane" });
    var te = add(s2, "text", { x: 282, y: 76, "class": "orb-txt", "text-anchor": "end" }); te.textContent = "equator";
    var ti = add(s2, "text", { x: 160, y: 150, "class": "orb-txt", "text-anchor": "middle" }); ti.textContent = "inclination " + num(v.inc_deg, 1) + "°";
    wrap.appendChild(s1); wrap.appendChild(s2);
    wrap.appendChild(el("figcaption", "small muted", "To scale, from " + label(r.source) + "'s perigee, apogee and inclination. The tilt panel " +
      "is drawn edge-on and foreshortened."));
    return wrap;
  }

  // ---------------------------------------------------------------- what Orbit holds
  function mine(x) {
    var n = NUMBERED ? KEY : obj && obj.norad != null ? String(obj.norad) : null;
    var j = obj ? obj.jcat : NUMBERED ? null : KEY;
    return (n && x.norad != null && String(x.norad) === n) || (j && x.jcat && x.jcat === j);
  }
  function holdingsName() {
    if (!snap) return null;
    var lists = [(snap.decay || {}).objects, (snap.maneuvers || {}).events, snap.reentries, snap.breakups];
    for (var i = 0; i < lists.length; i++) {
      var h = (lists[i] || []).filter(mine)[0];
      if (h) return h.gcat_name || h.name;
    }
    return null;
  }
  function holds() {
    var box = document.getElementById("obj-holds");
    box.textContent = "";
    if (!snap) return box.appendChild(el("p", "muted small", "Orbit's snapshot did not load, so its records are not shown."));
    var n = NUMBERED ? KEY : obj && obj.norad != null ? String(obj.norad) : null, any = false;
    // TIP: every message Orbit kept (daily archive since tip_check.kept_since) and this run's reply
    if (n) {
      var msgs = {}, list = [];
      Object.keys((arc && arc.days) || {}).forEach(function (d) { (arc.days[d].tip || []).forEach(function (m) { msgs[m[4]] = m; }); });
      (((snap.decay || {}).all_messages) || []).forEach(function (m) { msgs[m[4]] = m; });
      Object.keys(msgs).forEach(function (k) { if (String(msgs[k][0]) === n) list.push(msgs[k]); });
      var tip = ((snap.decay || {}).objects || []).filter(mine)[0];
      var chk = ((snap.tip_check || {}).objects || []).filter(mine)[0];
      if (list.length || tip || chk) {
        any = true;
        var s = sub(box, "Reentry predictions (TIP)", "United States Space Command's Tracking and Impact Prediction messages on Space-Track.org, " +
          "quoted, not checked. Orbit keeps every message it has read since " + fmt((snap.tip_check || {}).kept_since) + ".");
        if (tip) {
          s.appendChild(el("p", "small", (tip.passed ? "Window closed. " : "Window open. ") + "Newest message " + fmt(tip.msg_epoch) + ": predicted " +
            fmt(tip.decay_epoch) + " ±" + tip.window_min + " min" + (tip.lat != null ? ", at " + Math.abs(tip.lat).toFixed(1) + "°" + (tip.lat < 0 ? "S " : "N ") +
            Math.abs(tip.lon).toFixed(1) + "°" + (tip.lon < 0 ? "W" : "E") : "") + (tip.direction ? ", " + tip.direction : "") +
            (tip.high_interest ? "; USSPACECOM flags it high interest" : "") + "."));
        }
        if (chk && chk.after) {
          s.appendChild(el("p", "small", "TIP's message after the reentry (" + fmt(chk.after.msg_epoch) + ") puts it down at " + fmt(chk.after.decay_epoch) +
            (chk.offset_min != null ? ", " + Math.abs(chk.offset_min) + " min " + (chk.offset_min > 0 ? "later" : "earlier") + " than the last prediction, " +
              (chk.inside ? "inside" : "outside") + " its window" : "") + (chk.gcat && (chk.gcat.time || chk.gcat.date) ? "; GCAT gives " +
              (chk.gcat.time ? fmt(chk.gcat.time) : day(chk.gcat.date)) + (chk.gcat.uncertain ? " (marked uncertain)" : "") : "") + "."));
        }
        list.sort(function (a, b) { return a[1] < b[1] ? 1 : -1; });
        if (list.length) s.appendChild(table(["Issued", "Predicted reentry", "Window"], list.map(function (m) {
          return [fmt(m[1]), fmt(m[2]), m[3] >= 120 ? "±" + (m[3] / 60).toFixed(1).replace(/\.0$/, "") + " h" : "±" + m[3] + " min"];
        })));
      }
    }
    var re = (snap.reentries || []).filter(mine)[0];
    if (re) {
      any = true;
      sub(box, "Reentry in GCAT", "GCAT dates it " + (re.reentry_time ? fmt(re.reentry_time) : day(re.reentry_date)) +
        (re.reentry_uncertain ? " (GCAT marks the time uncertain)" : "") + ".");
    }
    var mv = ((snap.maneuvers || {}).events || []).filter(mine);
    if (mv.length) {
      any = true;
      var first = {};
      Object.keys((arc && arc.days) || {}).sort().forEach(function (d) {
        Object.keys(((arc.days[d].maneuver || {}).listed) || {}).forEach(function (k) { if (!first[k]) first[k] = d; });
      });
      var sm = sub(box, "Orbit changes", "Space-Track.org (USSPACECOM) element sets; Intelligence Company analysis. A listed change means the " +
        "published orbit moved by more than its element sets usually move: not a confirmed manoeuvre, a statement of intent or a warning. " +
        "Not reviewed or endorsed by USSPACECOM; not for operational use.");
      sm.appendChild(table(["Between", "Change", "First listed"], mv.map(function (e) {
        return [fmt(e.from) + " and " + fmt(e.to), "about " + (e.dv_ms >= 10 ? Math.round(e.dv_ms) : e.dv_ms.toFixed(2)) + " m/s, mostly " + e.dominant +
          "; semi-major axis " + (e.da_km > 0 ? "+" : "") + e.da_km.toFixed(1) + " km, inclination " + (e.di_deg > 0 ? "+" : "") + e.di_deg + "°",
          day(first[e.norad + ":" + (e.from || "").slice(0, 10)])];
      })));
      var to = link("On Orbit's page", "./#mv-" + n);
      sm.appendChild(to);
    }
    // relocation tracker (method orbit-2.27): the GEO page's section for this object, in short
    var mover = n && movers && !movers.error ? (movers.movers || []).filter(function (m) { return String(m.norad) === n; })[0] : null;
    if (mover) {
      any = true;
      var nw = mover.newest, lonT = function (x) { return Math.abs(x).toFixed(2) + "°" + (x < 0 ? "W" : "E"); };
      var age = nw.age_h < 48 ? Math.round(nw.age_h) + " hours" : Math.round(nw.age_h / 24) + " days";
      var sg = sub(box, "On the move along the GEO belt", mover.note);
      var lines = ["Newest element set " + fmt(nw.t) + ", " + age + " old: " + lonT(nw.lon) + ", drifting " + Math.abs(nw.drift).toFixed(2) + "° a day " +
        mover.direction + "."];
      if (mover.stale) lines.push("No public set for over 3 days, so Orbit shows no position now and no dates.");
      else lines.push("Now about " + lonT(mover.now.lon) + " at " + fmt(mover.now.at) + ", extrapolated at that rate.");
      var dep = mover.departure;
      if (dep) {
        var est = (dep.estimated_start || []).map(function (e) { return e.t; }).sort();
        lines.push("Left " + lonT(dep.lon) + " after its set of " + fmt(dep.last_held_set) + (est.length ? "; the move began about " + fmt(est[0]) +
          (est.length > 1 && est[est.length - 1] !== est[0] ? " to " + fmt(est[est.length - 1]) : "") + " (estimated from the drift rates, assuming it sped up evenly from rest)" : "") + ".");
      }
      if (mover.brake && mover.brake.state === "steady") lines.push("Braking: at a constant rate of braking it would stop at about " + lonT(mover.brake.projected_lon) + ".");
      lines.forEach(function (t) { sg.appendChild(el("p", "", t)); });
      sg.appendChild(link("Pass-by dates and stops on the GEO page", "geo.html#movers"));
    }
    var rpo = (((snap.rpo || {}).rows) || []).filter(function (r) {
      var g = r.gcat || {};
      return (g.target || []).concat(g.chaser || []).some(mine);
    });
    if (rpo.length) {
      any = true;
      var sr = sub(box, "Rendezvous and proximity operations", "From Secure World Foundation's public RPO sheet (CC BY-NC 4.0), sheet updated " +
        day((snap.rpo || {}).updated) + ". SWF's names matched to catalog numbers by Orbit (" + ((snap.rpo || {}).matched_on === "catalog" ?
        "the TIC catalog's names" : "GCAT's names") + " and the alias file).");
      sr.appendChild(table(["When", "Role", "Other object", "Type", "Orbit"], rpo.map(function (r) {
        var g = r.gcat || {}, isT = (g.target || []).some(mine), other = isT ? (g.chaser || []) : (g.target || []);
        var o = el("span");
        if (other.length) other.forEach(function (x, i) {
          if (i) o.appendChild(document.createTextNode(", "));
          o.appendChild(link(x.cat_name || x.name, objHref(x.norad || x.jcat)));
        });
        else o.textContent = (isT ? r.chaser : r.target) || "not given";
        var w = r.when || {};
        return [(w.start || r.date_text || "") + (w.end && w.end !== w.start ? " to " + w.end : "") + (w.ongoing ? ", ongoing" : ""),
          isT ? "target or client" : "chaser or servicer", o, r.mission_type || "", r.orbit || ""];
      })));
    }
    var cc = snap.catalog_changes || {}, cat = [];
    (cc.late_groups || []).forEach(function (g) { (g.objects || []).forEach(function (o) { if (mine(o)) cat.push("New entry in GCAT, from launch " + g.launch_tag + " (" + day(g.launch_date) + "), over 30 days after it."); }); });
    (cc.owner_changes || []).forEach(function (c) {
      if (!mine(c)) return;
      cat.push("Changed in GCAT: " + Object.keys(c.fields || {}).map(function (k) { return k + " " + (c.fields[k][0] || "–") + " → " + (c.fields[k][1] || "–"); }).join(", ") + ".");
    });
    (cc.removed_objects || []).forEach(function (o) { if (mine(o)) cat.push("Removed from GCAT's catalog."); });
    (cc.newly_numbered_objects || []).forEach(function (o) { if (mine(o)) cat.push("Given a NORAD number."); });
    if (cat.length) {
      any = true;
      var sc = sub(box, "Catalog changes", "Between Orbit's readings of GCAT of " + fmt(cc.previous_reading_at) + " and its latest.");
      var ul = el("ul", "plain small"); cat.forEach(function (t) { ul.appendChild(el("li", "", t)); }); sc.appendChild(ul);
    }
    var br = (snap.breakups || []).filter(mine)[0];
    if (br) { any = true; sub(box, "Breakup", "GCAT marks it " + ({ E: "exploded", C: "collided" }[br.status] || br.status) + " on " + day(br.breakup_date) + "."); }
    var tag = obj ? (recs("launch_tag")[0] || {}).value : null;
    var la = tag && (snap.launches || []).filter(function (l) { return l.launch_tag === tag; })[0];
    if (la) {
      any = true;
      var st = la.site || {};
      sub(box, "Launch", [la.vehicle + (la.variant ? " " + la.variant : ""), la.flight || la.mission, st.name || la.site_code,
        la.time ? fmt(la.time) : day(la.date), la.outcome].filter(Boolean).join(" · ") + ". From GCAT; Orbit lists launches of the last 30 days.");
    }
    box.appendChild(el("p", "small muted", (any ? "" : "Orbit holds nothing on this object beyond its catalog record. ") +
      "What Orbit keeps: TIP messages since " + fmt((snap.tip_check || {}).kept_since) + "; orbit changes in the satellites it watches over the last " +
      ((snap.maneuvers || {}).window_days || 30) + " days; GCAT's changes between its last two readings; launches and reentries of the last 30 days; " +
      "SWF's RPO sheet. Snapshot of " + fmt(snap.generated_at) + "."));
  }

  // ---------------------------------------------------------------- names and sources (the catalog's rules note)
  function names() {
    var box = document.getElementById("obj-names");
    box.textContent = "";
    if (!obj) {
      box.appendChild(el("p", "muted small", shard && shard.missing ? "This key is not in the TIC satellite catalog's copy on this site." :
        "The TIC satellite catalog is not on this site yet, so names and sources cannot be shown."));
      return;
    }
    var R = rules || {}, B = R.basis || {}, NF = R.name_fields || {};
    if ((R.fields || {}).name) box.appendChild(el("p", "small muted", R.fields.name));
    var rows = recs("names").sort(function (a, b) { return rankOf(a.source) - rankOf(b.source); }).map(function (x) {
      var nm = el("span", "", x.value + (x.uncertain ? " ?" : ""));
      if (x.status) nm.appendChild(el("div", "pl", x.status + " name" + (x.until ? ", until " + day(x.until) : "")));
      if (x.qualifier) nm.appendChild(el("div", "pl", "qualifier " + x.qualifier + " (the source's own, kept as written)"));
      var src = el("span", "", label(x.source));
      if (x.field) { var f = el("div", "pl", x.field); f.title = NF[x.field] || ""; src.appendChild(f); }
      if (x.cited) src.appendChild(el("div", "pl", "cites " + label(x.cited)));
      var ref = el("span");
      if (x.source === "wikidata" && x.ref) ref.appendChild(link(x.ref, "https://www.wikidata.org/wiki/" + encodeURIComponent(x.ref), true));
      else if (x.source === "aliases" && x.ref) ref.textContent = "line " + x.ref;
      else ref.textContent = x.ref || "";
      var b = B[x.basis] || {};
      var bs = el("span", "", b.label || x.basis); bs.title = b.means || "";
      return [nm, src, bs, day(x.read), ref];
    });
    box.appendChild(table(["Name", "Source", "Basis", "Read", "Ref"], rows));
    var bl = el("ul", "plain small muted");
    Object.keys(B).forEach(function (k) { bl.appendChild(el("li", "", (B[k].label || k) + ": " + (B[k].means || ""))); });
    box.appendChild(bl);
    // Each source's record, side by side
    var FIELDS = [["intldes", "COSPAR ID"], ["launch_date", "Launch date"], ["state", "State"], ["owner", "Owner"], ["status", "GCAT status"],
      ["ops_status", "Operational status"], ["decayed", "Left orbit"], ["decay_date", "Decay date"]];
    var srcs = uniq(FIELDS.reduce(function (acc, f) { return acc.concat(recs(f[0]).map(function (x) { return x.source; })); }, []))
      .sort(function (a, b) { return rankOf(a) - rankOf(b); });
    if (srcs.length) {
      var rws = FIELDS.filter(function (f) { return recs(f[0]).length; }).map(function (f) {
        var cells = [f[1]];
        srcs.forEach(function (s) {
          var v = recs(f[0]).filter(function (x) { return x.source === s; }).map(function (x) {
            var t = typeof x.value === "boolean" ? (x.value ? "yes" : "no") : String(x.value);
            return t + (x.uncertain ? " ?" : "") + (x.placeholder ? " (placeholder)" : "") + (x.nocompare ? " (not compared)" : "");
          });
          cells.push(uniq(v).join("; "));
        });
        return cells;
      });
      var h = sub(box, "Each source's record", "Values as each source gives them. " + (((R.fields || {}).state) || ""));
      h.appendChild(table(["Field"].concat(srcs.map(label)), rws));
    }
    var dis = obj.disagreements || [];
    if (dis.length) {
      var D = R.disagreements || {}, sd = sub(box, "Sources differ", D.about || "");
      var ul = el("ul", "plain small");
      dis.forEach(function (d) {
        var li = el("li");
        li.appendChild(el("strong", "", (FIELDS.filter(function (f) { return f[0] === d.field; })[0] || [0, d.field])[1] + ": "));
        li.appendChild(document.createTextNode((d.claims || []).map(function (c) {
          return (typeof c.value === "boolean" ? (c.value ? "yes" : "no") : c.value) + (c.as_given && c.as_given.join("") !== String(c.value) ? " (as given: " + c.as_given.join(", ") + ")" : "") +
            " by " + (c.sources || []).map(label).join(", ");
        }).join("; ") + ". "));
        if ((D.fields || {})[d.field]) li.appendChild(el("span", "muted", D.fields[d.field]));
        ul.appendChild(li);
      });
      sd.appendChild(ul);
    }
    var key = NUMBERED ? KEY : obj.jcat;
    var sw = (shard.swaps || []).filter(function (w) {
      return Object.keys(w.claims || {}).some(function (s) { return (w.claims[s] || []).map(String).indexOf(String(key)) >= 0; });
    });
    if (sw.length) {
      var ss = sub(box, "Name swaps", typeof R.swaps === "string" ? R.swaps : "");
      var ul2 = el("ul", "plain small");
      sw.forEach(function (w) {
        var li = el("li", "", "“" + w.name + "”: ");
        Object.keys(w.claims).forEach(function (s, i) {
          if (i) li.appendChild(document.createTextNode("; "));
          li.appendChild(document.createTextNode(label(s) + " gives it to "));
          w.claims[s].forEach(function (k, j) { if (j) li.appendChild(document.createTextNode(", ")); li.appendChild(link(String(k), objHref(k))); });
        });
        li.appendChild(document.createTextNode(" (" + (w.status || "open") + ")."));
        ul2.appendChild(li);
      });
      ss.appendChild(ul2);
    }
  }

  // ---------------------------------------------------------------- sources and citations
  function cite() {
    var box = document.getElementById("obj-cite");
    box.textContent = "";
    var ul = el("ul", "plain small");
    if (obj) {
      var used = uniq(Object.keys(obj).reduce(function (acc, k) {
        return Array.isArray(obj[k]) ? acc.concat(obj[k].map(function (x) { return x && x.source; })) : acc;
      }, [])).sort(function (a, b) { return rankOf(a) - rankOf(b); });
      used.forEach(function (s) {
        var r = (rules.sources || {})[s] || {}, sh = (shard.sources || {})[s] || {};
        var li = el("li");
        li.appendChild(el("strong", "", r.label || s));
        li.appendChild(document.createTextNode(": " + (r.about || "") + " " + (sh.citation || r.citation || "") +
          (sh.read || r.read ? " Read " + day(sh.read || r.read) + "." : "") + " "));
        if (r.url) li.appendChild(link(r.url.replace(/^https?:\/\//, ""), r.url, true));
        ul.appendChild(li);
      });
      if (NUMBERED) {
        var li2 = el("li", "", "Elsewhere: ");
        li2.appendChild(link("CelesTrak's SATCAT record", "https://celestrak.org/satcat/table-satcat.php?CATNR=" + encodeURIComponent(KEY), true));
        uniq(recs("names").concat(recs("intldes")).filter(function (x) { return x.source === "wikidata" && x.ref; }).map(function (x) { return x.ref; }))
          .forEach(function (qid) { li2.appendChild(document.createTextNode(" · ")); li2.appendChild(link("Wikidata " + qid, "https://www.wikidata.org/wiki/" + qid, true)); });
        ul.appendChild(li2);
      }
    }
    ul.appendChild(el("li", "", "Orbit's own records: Space-Track.org TIP messages and element sets (USSPACECOM, 18th Space Defense Squadron), " +
      "redistributed under USSPACECOM's blanket approval for basic SSA data; orbit-change analysis by The Intelligence Company, not reviewed or " +
      "endorsed by USSPACECOM. GCAT (CC BY 4.0). Secure World Foundation (CC BY-NC 4.0). Not for operational use."));
    box.appendChild(ul);
  }

  function render() {
    head(); orbitCard(); globeCard(); holds(); names(); cite();
  }
  if (T && T.mountSettings) T.mountSettings(document.getElementById("time-settings"));
  if (T && T.onChange) T.onChange(render);

  if (!KEY || !shardName(KEY)) {
    document.getElementById("obj-name").textContent = "Find an object";
    document.getElementById("obj-sub").textContent = "Search by any source's name, a NORAD number (25544), a COSPAR ID (1998-067A) or GCAT's id for an object without a NORAD number (A04907).";
    ["obj-orbit-card", "obj-globe-card", "obj-holds-card", "obj-names-card", "obj-cite-card"].forEach(function (id) { document.getElementById(id).hidden = true; });
    var inp = document.getElementById("obj-q"); if (inp) inp.focus();
    return;
  }
  Promise.all([getJson("data/catalog/" + shardName(KEY)), getJson("data/catalog/rules.json"), getJson("data/catalog/index.json"),
    getJson("data/snapshot.json"), getJson("data/archive.json"), getJson("data/geo/movers.json")]).then(function (r) {
    rules = r[1]; man = r[2]; snap = r[3]; arc = r[4]; movers = r[5];
    shard = r[0] && rules ? r[0] : r[0] === null && rules && man ? { missing: true, sources: {}, swaps: [] } : null;
    obj = shard && !shard.missing ? (shard.objects || {})[KEY] || null : null;
    if (shard && !obj) shard.missing = true;  // the shard is here but this key is not in it
    render();
    if (shard && shard.missing) {
      document.getElementById("obj-sub").textContent += " · not in the TIC satellite catalog's copy on this site";
    }
  });
})();
