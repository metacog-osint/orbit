/* Orbit page: reads data/snapshot.json and draws it. Times are stored UTC and shown in the viewer's zone
   through tic-time.js. No inline scripts (the site's CSP allows scripts from this origin only). */
(function () {
  "use strict";
  var T = window.TicTime;
  var snap = null;
  var sources = null; // data/sources.json: the register's ingested sources with their Admiralty grades

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }
  function fmt(iso, opts) {
    if (!iso) return "";
    return T ? T.format(iso, opts || {}) : iso.replace("T", " ").replace(":00Z", "Z");
  }
  function dayOnly(isoDate) {
    return T ? T.format(isoDate + "T12:00:00Z", { time: false, zoneName: false }) : isoDate;
  }
  function daysAgo(n) {
    var d = new Date(Date.parse(snap.generated_at) - n * 86400000);
    return d.toISOString().slice(0, 10);
  }
  function table(head, rows) {
    var t = el("table"), th = el("thead"), tr = el("tr");
    head.forEach(function (h) { var c = el("th", h.num ? "num" : "", h.label || h); tr.appendChild(c); });
    th.appendChild(tr); t.appendChild(th);
    var tb = el("tbody");
    var names = head.map(function (h) { return h.label || h || ""; });
    rows.forEach(function (r) {
      [].forEach.call(r.cells, function (c, i) { if (names[i]) c.setAttribute("data-label", names[i]); });
      tb.appendChild(r);
    });
    t.appendChild(tb);
    return t;
  }
  function cell(tr, content, cls) {
    var td = el("td", cls || "");
    if (content instanceof Node) td.appendChild(content); else td.textContent = content == null ? "" : content;
    tr.appendChild(td);
    return td;
  }
  var opened = {}; // folds the viewer has opened; kept when the page redraws (time settings)
  function fold(box, rows, keep, noun, key) {
    if (rows.length <= keep + 2) return;
    var rest = rows.slice(keep);
    var p = el("p", "more"), b = el("button");
    b.type = "button";
    function set(open) {
      opened[key] = open;
      rest.forEach(function (r) { r.classList.toggle("folded", !open); });
      b.setAttribute("aria-expanded", String(open));
      b.textContent = open ? "Show the first " + keep : "Show all " + rows.length + " " + noun;
    }
    b.addEventListener("click", function () { set(!opened[key]); });
    b.foldOpen = function () { set(true); };
    set(!!opened[key]);
    p.appendChild(b);
    box.appendChild(p);
  }
  // A link to a folded row (the map's "Show in table", a hazard's scheduled launch) opens its table first.
  function reveal(id) {
    var r = id && document.getElementById(id);
    if (!r) return null;
    if (r.classList.contains("folded")) {
      var b = r.closest(".tbl-wrap").querySelector(".more button");
      if (b && b.foldOpen) b.foldOpen();
    }
    return r;
  }
  function empty(box, text) { box.textContent = ""; box.appendChild(el("p", "muted small", text)); }

  /* Country marks. Colour is kept for the three largest actors (US, China, Russia with the USSR); every mark also
     carries its code and, where flag-icons has one, the flag, so colour never carries identity alone. */
  var BIG = { US: "us", CN: "cn", RU: "ru" };
  var REGION = null;
  try { REGION = new Intl.DisplayNames(["en"], { type: "region" }); } catch (e) { REGION = null; }
  function countryName(cc) {
    try { return (REGION && REGION.of(cc)) || cc; } catch (e) { return cc; }
  }
  function mark(country, state) {
    var label, title, group = "other", flag = null;
    if (state === "SU") {
      label = "SU"; group = "ru";
      title = "Soviet Union (GCAT keeps Soviet objects apart from the Russian Federation's)";
    } else if (state && state.indexOf("I-") === 0) {
      label = state.slice(2); title = label + " (intergovernmental)";
    } else if (country) {
      label = country; title = countryName(country); group = BIG[country] || "other"; flag = country.toLowerCase();
    } else {
      label = state || "?"; title = state ? "GCAT owner code " + state : "Unknown";
    }
    var s = el("span", "cc g-" + group);
    s.title = title;
    if (flag) {
      var img = document.createElement("img");
      img.src = "flags/" + flag + ".svg"; img.alt = ""; img.loading = "lazy"; img.width = 16; img.height = 12;
      img.onerror = function () { if (img.parentNode) img.parentNode.removeChild(img); };
      s.appendChild(img);
    }
    s.appendChild(document.createTextNode(label));
    return s;
  }
  function who(marks, name) {
    var d = el("div", "who");
    marks.forEach(function (m) { d.appendChild(m); });
    if (name) d.appendChild(el("span", "nm", name));
    return d;
  }

  function tiles() {
    var box = document.getElementById("tiles");
    box.textContent = "";
    var since7 = daysAgo(7);
    var launches = (snap.launches || []).filter(function (x) { return x.date >= since7; });
    var reentries = (snap.reentries || []).filter(function (x) { return x.reentry_date >= since7 && x.type === "payload"; });
    var h = snap.hygiene || {};
    [["Orbital launches, 7 days", launches.length, "launches"],
     ["Scheduled, next 14 days", (snap.upcoming || []).length, "upcoming"],
     ["Launch hazard areas in force", hazardAreas().length, "hazards"],
     ["Payload reentries, 7 days", reentries.length, "reentries"],
     ["Orbit changes, watched, 30 days", (snap.maneuvers || {}).read_at ? (snap.maneuvers.events || []).length : "–",
      "maneuvers"],
     ["Objects in orbit (GCAT)", h.in_orbit ? h.in_orbit.toLocaleString() : "–", "catalog"]].forEach(function (t) {
      var d = el("a", "tile");
      d.href = "#" + t[2];
      d.appendChild(el("span", "k", t[0]));
      d.appendChild(el("span", "v", String(t[1])));
      box.appendChild(d);
      var n = document.querySelector('.secbar b[data-n="' + t[2] + '"]');
      if (n) n.textContent = String(t[1]);
    });
    document.getElementById("asof").textContent = "Built " + fmt(snap.generated_at) + ".";
    document.getElementById("method").textContent = snap.method_version || "";
  }

  function launchTable() {
    var box = document.getElementById("launch-table");
    var since7 = daysAgo(7);
    var rows = (snap.launches || []).filter(function (x) { return x.date >= since7; }).map(function (x) {
      var tr = el("tr");
      tr.id = "launch-" + x.launch_tag.replace(/ /g, "-");
      cell(tr, x.time ? fmt(x.time) + (x.time_uncertain ? " ~" : "") : dayOnly(x.date) + " ~");
      var what = el("div");
      what.appendChild(el("div", "", [x.flight, x.mission && x.mission !== x.flight ? "(" + x.mission + ")" : ""].join(" ").trim() || x.launch_tag));
      var pls = x.payloads || [];
      if (!pls.length) what.appendChild(el("div", "pl", "Payloads not yet cataloged"));
      var owners = [], byOwner = {};
      pls.forEach(function (p) {
        var k = p.state || "?";
        if (!byOwner[k]) { byOwner[k] = { country: p.country, state: p.state, names: [] }; owners.push(k); }
        byOwner[k].names.push(p.name);
      });
      owners.forEach(function (k) {
        var o = byOwner[k], line = el("div", "pl");
        line.appendChild(mark(o.country, o.state));
        line.appendChild(el("span", "", o.names.slice(0, 6).join(", ") +
          (o.names.length > 6 ? ", +" + (o.names.length - 6) + " more" : "")));
        what.appendChild(line);
      });
      cell(tr, what);
      var veh = el("div");
      veh.appendChild(el("div", "", x.vehicle));
      var ls = x.launchers || [];
      var seen = {};
      var lm = ls.filter(function (l) { var k = l.state + "|" + l.country; if (seen[k]) return false; seen[k] = 1; return true; })
        .map(function (l) { return mark(l.country, l.state); });
      if (ls.length) veh.appendChild(who(lm,
        ls.map(function (l) { return l.name; }).join(" / ")));
      cell(tr, veh);
      var st = x.site || {};
      cell(tr, who(st.country || st.state ? [mark(st.country, st.state)] : [], st.name || x.site_code));
      var out = el("span", x.outcome === "success" ? "badge" : "badge badge-warn", x.outcome);
      cell(tr, out);
      cell(tr, x.launch_tag, "muted");
      return tr;
    });
    if (!rows.length) return empty(box, "No orbital launches in GCAT's list for the last 7 days.");
    box.textContent = "";
    box.appendChild(table(["When", "Flight and payloads (by owner)", "Vehicle and launcher", "Site", "Outcome", "GCAT"], rows));
  }

  function upcomingTable() {
    var box = document.getElementById("upcoming-table");
    var rows = (snap.upcoming || []).map(function (x) {
      var tr = el("tr");
      tr.id = "up-" + x.id;
      var when = el("div");
      when.appendChild(el("div", "", fmt(x.net)));
      var cd = el("div", "cd small");
      cd.setAttribute("data-net", x.net || "");
      cd.setAttribute("data-prec", x.net_precision || "");
      when.appendChild(cd);
      cell(tr, when);
      cell(tr, x.name);
      cell(tr, who((x.provider_countries || []).map(function (c) { return mark(c, null); }), x.provider || ""));
      cell(tr, x.orbit || "");
      cell(tr, who(x.pad_country ? [mark(x.pad_country, null)] : [], x.location || x.pad));
      cell(tr, el("span", "badge", x.status));
      return tr;
    });
    if (!rows.length) return empty(box, "No launches listed for the next 14 days.");
    box.textContent = "";
    box.appendChild(table(["No earlier than (NET)", "Launch", "Provider", "Orbit", "Site", "Status"], rows));
    tick();
  }

  /* Navigational warnings: launch hazard and space-debris areas in force (NGA memoranda, NAVAREA XI). A scheduled
     launch is shown against a warning only as a time coincidence: its NET inside a window of four hours or less, or
     up to an hour before one opens. Longer windows (some debris areas stand for most of a day, two weeks running)
     would match nearly everything. Orbit does not say which launch a warning is for. */
  var HOUR = 3600000, MAX_WINDOW = 4 * HOUR;
  function hazardAreas() { return ((snap && snap.navwarn) || {}).areas || []; }
  function netInWindow(netIso, a) {
    var t = Date.parse(netIso);
    if (isNaN(t)) return false;
    return (a.windows || []).some(function (w) {
      var s = Date.parse(w.start), e = Date.parse(w.end);
      return e - s <= MAX_WINDOW && t >= s - HOUR && t <= e;
    });
  }
  function nextWindow(a, now) {
    var ws = a.windows || [];
    for (var i = 0; i < ws.length; i++) if (Date.parse(ws[i].end) > now) return { w: ws[i], left: ws.length - i - 1 };
    return null;
  }
  var MODE = { alternates: "alternates", daily: "daily repeats", list: "more windows", single: "" };
  function hazardTable() {
    var box = document.getElementById("hazard-table");
    var nw = (snap && snap.navwarn) || {};
    var areas = hazardAreas();
    if (!nw.read_at) return empty(box, "Not read yet: navigational warnings appear after Orbit's next collection.");
    if (!areas.length) return empty(box, "No launch hazard or space-debris warnings in force in the sources read.");
    var now = Date.now();
    var rows = areas.map(function (a) {
      var tr = el("tr");
      tr.id = "nw-" + a.key;
      var when = el("div");
      var nx = nextWindow(a, now);
      if (nx) {
        var open = Date.parse(nx.w.start) <= now;
        when.appendChild(el("div", "", fmt(nx.w.start) + " to " + fmt(nx.w.end, { date: false })));
        when.appendChild(el("div", "pl", (open ? "Open now" : "") + (open && nx.left ? "; " : "") +
          (nx.left ? "then " + nx.left + " " + (MODE[a.window_mode] || "more windows") : "")));
      } else if (a.window_text) {
        when.appendChild(el("div", "", a.window_text));
      } else {
        when.appendChild(el("div", "muted", "Notice, no window"));
      }
      cell(tr, when);
      var what = el("div");
      what.appendChild(el("div", "", a.hazard.charAt(0).toUpperCase() + a.hazard.slice(1)));
      what.appendChild(el("div", "pl", (a.regions || []).join(", ").toLowerCase().replace(/\b\w/g, function (c) { return c.toUpperCase(); })));
      if (!(a.areas || []).length && a.cancels && a.cancels.length) {
        what.appendChild(el("div", "pl", "Cancels " + a.cancels.join(", ")));
      }
      cell(tr, what);
      var by = el("div");
      a.broadcasts.forEach(function (b) {
        var d = el("div");
        var link = el("a", "", b.id); link.href = b.url; link.rel = "noopener";
        d.appendChild(link);
        d.appendChild(el("span", "muted", " issued " + fmt(b.issued, { date: true })));
        by.appendChild(d);
      });
      if (a.vertex_differences) {
        by.appendChild(el("div", "pl", "Copies differ at " + a.vertex_differences +
          (a.vertex_differences === 1 ? " vertex" : " vertices") + "; the first is drawn"));
      }
      cell(tr, by);
      var match = (snap.upcoming || []).filter(function (u) { return netInWindow(u.net, a); });
      var mc = el("div");
      if (match.length) {
        match.forEach(function (u) {
          var link = el("a", "", u.name); link.href = "#up-" + u.id;
          var d = el("div"); d.appendChild(link); mc.appendChild(d);
        });
      } else mc.appendChild(el("span", "muted", "None listed"));
      cell(tr, mc);
      var act = el("div");
      if ((a.areas || []).length) {
        var btn = el("button", "linkish small", "Show on map");
        btn.type = "button";
        btn.addEventListener("click", function () { showOnMap(a.key); });
        act.appendChild(btn);
      }
      if (a.expires) act.appendChild(el("div", "pl", "Cancelled " + fmt(a.expires)));
      cell(tr, act);
      return tr;
    });
    box.textContent = "";
    box.appendChild(table(["Next window", "Hazard and area", "Broadcast as",
      "Scheduled launches with NET in a window (time only)", "Map and cancellation"], rows));
    fold(box, rows, 8, "warnings", "hazards");
  }

  /* Anti-satellite tests in space: Secure World Foundation's sheet as it stands (CC BY-NC 4.0). History, not new
     events: every row is SWF's, shown as SWF gives it, newest first. */
  function num(n) { return n == null ? "–" : n.toLocaleString(); }
  // A calendar date with its year ("20 Oct 1968"): history needs the year that dayOnly leaves out.
  function dayYear(isoDate) {
    return T ? T.format(isoDate + "T12:00:00Z", { year: true, time: false }) : isoDate;
  }
  // Orbit changes in watched objects (Space-Track element sets, Orbit's analysis). Wording approved by Tom, 14 Nov 2026.
  var DOMINANT = { "in-track": "along track", "cross-track": "plane change", "eccentricity": "orbit shape" };
  function lonText(x) { return x == null ? "" : Math.abs(x).toFixed(1) + "\u00b0" + (x < 0 ? "W" : "E"); }
  function driftText(x) {
    if (x == null) return "";
    if (Math.abs(x) < 0.005) return "holding station";
    return "drifting " + Math.abs(x).toFixed(2) + "\u00b0/day " + (x < 0 ? "west" : "east");
  }
  function maneuverCard() {
    var box = document.getElementById("maneuver-body");
    var mv = (snap && snap.maneuvers) || {};
    var lane = (snap.lanes || {}).maneuver || {};
    if (!mv.read_at) {
      return empty(box, lane.status === "off" ? "Not read: " + (lane.reason || "the lane is off") + "." :
        "Not read yet: changes appear after Orbit's next reading of Space-Track.");
    }
    box.textContent = "";
    var ev = mv.events || [];
    box.appendChild(el("p", "small", mv.watched + " watched " + (mv.watched === 1 ? "object" : "objects") + "; " +
      ev.length + (ev.length === 1 ? " change" : " changes") + " listed in the last " + mv.window_days + " days; " +
      (mv.stale ? mv.stale + " without a new element set for 3 days or more (an untracked object looks the same " +
        "as a quiet one). " : "all with a recent element set. ") + "Read " + fmt(mv.read_at) + "."));
    if (!ev.length) return;
    var rows = ev.map(function (e) {
      var tr = el("tr");
      var who = el("div");
      who.appendChild(mark(e.cc, e.state));
      who.appendChild(document.createTextNode(e.gcat_name || e.name || ("NORAD " + e.norad)));
      who.appendChild(el("div", "pl", "NORAD " + e.norad + (e.object_id ? ", " + e.object_id : "") +
        (e.regime ? ", " + e.regime : "")));
      cell(tr, who);
      var when = el("div", "", fmt(e.from));
      when.appendChild(el("div", "pl", "to " + fmt(e.to) + (e.pairs > 1 ? " (" + e.pairs + " set pairs)" : "")));
      if (e.gap) {  // no element set between these two: the change happened somewhere inside the gap
        var days = e.gap.hours / 24;
        when.appendChild(el("div", "pl gap-note", "Measured across a " + (days >= 10 ? Math.round(days) : days.toFixed(1)) +
          "-day gap between element sets (" + fmt(e.gap.from) + " to " + fmt(e.gap.to) + "): the change happened " +
          "somewhere in that gap, not necessarily at either end."));
      }
      cell(tr, when);
      var ch = el("div", "", "about " + (e.dv_ms >= 10 ? Math.round(e.dv_ms) : e.dv_ms.toFixed(2)) + " m/s, mostly " +
        (DOMINANT[e.dominant] || e.dominant));
      ch.appendChild(el("div", "pl", "semi-major axis " + (e.da_km > 0 ? "+" : "") + (Math.abs(e.da_km) >= 100 ? Math.round(e.da_km).toLocaleString() : e.da_km.toFixed(1)) +
        " km, inclination " + (e.di_deg > 0 ? "+" : "") + e.di_deg + "\u00b0"));
      cell(tr, ch);
      var pos = el("div");
      if (e.geo) {
        pos.appendChild(document.createTextNode(lonText(e.geo.lon_before) + " to " + lonText(e.geo.lon_after)));
        pos.appendChild(el("div", "pl", driftText(e.geo.drift_before) + ", then " + driftText(e.geo.drift_after)));
      }
      cell(tr, pos);
      cell(tr, el("span", "muted small", "Space-Track.org (USSPACECOM) element sets; Intelligence Company analysis."));
      return tr;
    });
    box.appendChild(table(["Object", "When", "Change", "Longitude (geostationary)", "Source"], rows));
    fold(box, rows, 10, "changes", "maneuvers");
  }

  function counterspaceCard() {
    var box = document.getElementById("asat-body");
    var cs = (snap && snap.counterspace) || {};
    var tests = cs.tests || [];
    if (!cs.read_at) return empty(box, "Not read yet: the test history appears after Orbit's next collection.");
    box.textContent = "";
    if (tests.length) {
      document.getElementById("asat-h").textContent = "Anti-satellite tests in space, " +
        tests[tests.length - 1].date.slice(0, 4) + " to date";
    }
    // New since Orbit's last reading of the sheet.
    var fresh = cs.new_since_last || [];
    if (cs.first_reading) {
      box.appendChild(el("p", "muted small", "First reading of the sheet: tests SWF adds are listed here from " +
        "Orbit's next reading."));
    } else if (fresh.length) {
      box.appendChild(el("p", "small", fresh.length + (fresh.length === 1 ? " test" : " tests") +
        " new in the sheet since Orbit's reading of " + fmt(cs.previous_read_at) + ":"));
      var ul = el("ul", "plain small");
      fresh.forEach(function (t) {
        var li = el("li");
        li.appendChild(mark(t.cc, null));
        li.appendChild(document.createTextNode(dayYear(t.date) + ": " + (t.interceptor || "interceptor not given") +
          (t.target ? ", target " + t.target : "")));
        ul.appendChild(li);
      });
      box.appendChild(ul);
    } else {
      box.appendChild(el("p", "muted small", "No tests added to the sheet since Orbit's reading of " +
        fmt(cs.previous_read_at) + "."));
    }
    // By country.
    var bc = cs.by_country || {}, tot = { tests: 0, debris_created: 0, debris_on_orbit: 0 };
    var srows = Object.keys(bc).map(function (k) {
      var c = bc[k], tr = el("tr");
      tot.tests += c.tests; tot.debris_created += c.debris_created; tot.debris_on_orbit += c.debris_on_orbit;
      cell(tr, who([mark(c.cc, null)], k));
      cell(tr, num(c.tests), "num");
      cell(tr, num(c.debris_created), "num");
      cell(tr, num(c.debris_on_orbit), "num");
      return tr;
    });
    if (srows.length) {
      var tt = el("tr");
      cell(tt, "All in the table", "muted");
      cell(tt, num(tot.tests), "num"); cell(tt, num(tot.debris_created), "num"); cell(tt, num(tot.debris_on_orbit), "num");
      srows.push(tt);
      box.appendChild(el("h3", "small", "By country"));
      var sw = el("div", "tbl-wrap");
      sw.appendChild(table(["Country", { label: "Tests", num: true }, { label: "Debris created", num: true },
        { label: "Debris still on orbit", num: true }], srows));
      box.appendChild(sw);
    }
    // Every test, newest first.
    var rows = tests.map(function (t) {
      var tr = el("tr");
      cell(tr, dayYear(t.date));
      cell(tr, mark(t.cc, null));
      var what = el("div");
      what.appendChild(el("div", "", t.interceptor || "Not given"));
      what.appendChild(el("div", "pl", [t.interceptor_type, t.target ? "target: " + t.target : ""]
        .filter(Boolean).join(" · ")));
      cell(tr, what);
      cell(tr, t.site || "–");
      var hit = cell(tr, t.hit === true ? "Yes" : t.hit === false ? "No" : "–");
      if (t.hit == null) hit.title = "The sheet gives a dash or nothing here";
      cell(tr, num(t.debris_created), "num");
      cell(tr, num(t.debris_reentered), "num");
      cell(tr, num(t.debris_on_orbit), "num");
      var fin = el("div");
      fin.appendChild(el("div", "", t.final_reentry === "on orbit" ? "Still on orbit" :
        t.final_reentry ? dayYear(t.final_reentry) : "–"));
      if (t.lifespan_years != null) fin.appendChild(el("div", "pl", t.lifespan_years.toFixed(2) + " years"));
      cell(tr, fin);
      return tr;
    });
    box.appendChild(el("h3", "small", "Every test, newest first (" + rows.length + ")"));
    var tw = el("div", "tbl-wrap");
    tw.appendChild(table(["Date", "Country", "Interceptor, type and target", "Launch site", "Object hit",
      { label: "Debris created", num: true }, { label: "Re-entered", num: true }, { label: "Still on orbit", num: true },
      "Last piece re-entered (debris lifespan)"], rows));
    fold(tw, rows, 10, "tests", "asat");
    box.appendChild(tw);
    // Notes and credit.
    var note = el("div", "muted small asat-note");
    var bits = [];
    if (cs.updated) bits.push("The sheet says it was last updated " + dayYear(cs.updated) + "; Orbit read it " +
      fmt(cs.read_at) + ".");
    bits.push("Debris counts are U.S. military catalog counts (generally 10 cm and larger), as SWF compiled them.");
    bits.push("SWF lists Soviet-era tests under Russia.");
    var sk = cs.skipped || [];
    if (sk.length) {
      bits.push((sk.length === 1 ? "One row is" : sk.length + " rows are") + " dated as a span, not a day, so " +
        (sk.length === 1 ? "it is" : "they are") + " in neither table: " + sk.map(function (s) {
          return s.country + ", " + s.date_text + ", " + (s.interceptor || "interceptor not given") +
            (s.target && s.target !== "None" ? ", target " + s.target : "") + " (" + num(s.debris_created) +
            " debris created, " + num(s.debris_on_orbit) + " still on orbit)";
        }).join("; ") + ".");
    }
    note.appendChild(el("p", "", bits.join(" ")));
    var cr = el("p", "");
    cr.appendChild(document.createTextNode("Secure World Foundation, Global Counterspace Capabilities (2026), " +
      "CC BY-NC 4.0: "));
    var a1 = el("a", "", "report"); a1.href = cs.report; a1.rel = "noopener"; cr.appendChild(a1);
    cr.appendChild(document.createTextNode(", "));
    var a2 = el("a", "", "sheet"); a2.href = cs.sheet; a2.rel = "noopener"; cr.appendChild(a2);
    cr.appendChild(document.createTextNode("."));
    note.appendChild(cr);
    box.appendChild(note);
  }


  /* The map loads after the tables, from map.js (an ES module with MapLibre); without WebGL it says so. */
  var mapApi = null, mapStarted = false;
  function groupOf(country, state) {
    if (state === "SU") return "ru";
    return BIG[country] || "other";
  }
  function mapModel() {
    var launchesFc = { type: "FeatureCollection", features: [] };
    var since7 = daysAgo(7);
    (snap.launches || []).filter(function (x) { return x.date >= since7 && x.site && x.site.lat != null; }).forEach(function (x) {
      var l = (x.launchers || [])[0] || {};
      launchesFc.features.push({ type: "Feature", geometry: { type: "Point", coordinates: [x.site.lon, x.site.lat] },
        properties: { key: "launch-" + x.launch_tag.replace(/ /g, "-"), group: groupOf(l.country, l.state) } });
    });
    var pads = { type: "FeatureCollection", features: [] };
    (snap.upcoming || []).filter(function (x) { return x.lat != null; }).forEach(function (x) {
      pads.features.push({ type: "Feature", geometry: { type: "Point", coordinates: [x.lon, x.lat] },
        properties: { key: "up-" + x.id, group: groupOf((x.provider_countries || [])[0], null) } });
    });
    var areas = { type: "FeatureCollection", features: [] };
    hazardAreas().forEach(function (a) {
      (a.areas || []).forEach(function (ar) {
        if (ar.coords.length < 3) return;
        var ring = ar.coords.slice();
        var f0 = ring[0], fl = ring[ring.length - 1];
        if (f0[0] !== fl[0] || f0[1] !== fl[1]) ring.push(f0);
        areas.features.push({ type: "Feature", geometry: { type: "Polygon", coordinates: [ring] },
          properties: { key: "nw-" + a.key, debris: a.hazard.indexOf("debris") >= 0 } });
      });
    });
    return { launches: launchesFc, pads: pads, areas: areas };
  }
  function describe(key) {
    var row = document.getElementById(key);
    if (!row) return null;
    var txt = function (c) { return c ? (c.innerText || c.textContent).replace(/\s+/g, " ").trim() : ""; };
    var main = txt(row.cells[1]).slice(0, 160);
    if (key.indexOf("nw-") === 0) {
      var first = row.cells[2] && row.cells[2].querySelector("a");
      return (first ? first.textContent + ": " : "") + main;
    }
    return main;
  }
  function onPick(key) {
    var info = document.getElementById("map-info");
    info.textContent = "";
    var text = describe(key);
    if (!text) return;
    info.appendChild(document.createTextNode(text + " "));
    var link = el("a", "", "Show in table"); link.href = "#" + key;
    info.appendChild(link);
    if (mapApi) mapApi.select(key.indexOf("nw-") === 0 ? key : "");
  }
  function showOnMap(key) {
    var card = document.getElementById("map-card");
    if (card) card.scrollIntoView({ behavior: "smooth", block: "start" });
    if (mapApi) { mapApi.select("nw-" + key); mapApi.flyTo("nw-" + key); onPick("nw-" + key); }
  }
  function startMap() {
    if (mapStarted) return;
    mapStarted = true;
    var box = document.getElementById("map");
    var test = document.createElement("canvas");
    var gl = null;
    try { gl = test.getContext("webgl2") || test.getContext("webgl"); } catch (e) { gl = null; }
    if (!gl) { box.textContent = "This browser has no WebGL, so the map cannot be drawn; the tables list everything."; return; }
    import("./map.js").then(function (m) {
      return m.createMap(box, mapModel(), { onPick: onPick });
    }).then(function (api) { mapApi = api; }).catch(function (e) {
      box.textContent = "The map could not load (" + e + "); the tables list everything.";
    });
  }

  /* Countdown to each NET, on the viewer's clock, refreshed each minute. It is never finer than the NET itself:
     Launch Library 2 gives each NET a precision (Second, Minute, Hour, Day, Week, Month and coarser). */
  var PREC = { Second: "exact", Minute: "exact", Hour: "hour", "Morning (local)": "hour", "Afternoon (local)": "hour",
    Day: "day" };
  function precWords(p) {
    if (!p) return "precision not given";
    if (p === "Second" || p === "Minute") return "to the " + p.toLowerCase();
    if (p === "Hour") return "to the hour";
    if (p === "Day") return "to the day";
    return p.toLowerCase().replace(" (local)", ", local time") + " only";
  }
  function pad2(n) { return (n < 10 ? "0" : "") + n; }
  function span(ms, unit) {
    if (unit === "day") {
      var dd = Math.round(ms / 86400000);
      return dd < 1 ? "under 1 day" : "about " + dd + (dd === 1 ? " day" : " days");
    }
    if (unit === "hour") {
      var hh = Math.round(ms / 3600000);
      if (hh < 1) return "under 1 h";
      return "about " + (hh >= 24 ? Math.floor(hh / 24) + " d " + (hh % 24) + " h" : hh + " h");
    }
    var m = Math.floor(ms / 60000), d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), mm = m % 60;
    if (m < 1) return "under 1 m";
    if (d) return d + " d " + pad2(h) + " h " + pad2(mm) + " m";
    if (h) return h + " h " + pad2(mm) + " m";
    return mm + " m";
  }
  function countdown(netIso, prec, now) {
    var t = Date.parse(netIso);
    if (isNaN(t)) return "";
    var unit = PREC[prec];
    if (!unit) return "No countdown: NET " + precWords(prec);
    var ms = t - now;
    if (ms > 0) return "T\u2212 " + span(ms, unit) + " \u00b7 NET " + precWords(prec);
    return (unit === "exact" ? "NET passed " + span(-ms, unit) + " ago" : "NET passed") +
      " \u00b7 status as last read";
  }
  function tick() {
    var now = Date.now();
    var cds = document.querySelectorAll("#upcoming-table .cd");
    for (var i = 0; i < cds.length; i++) {
      cds[i].textContent = countdown(cds[i].getAttribute("data-net"), cds[i].getAttribute("data-prec"), now);
    }
  }
  function startTicking() {
    // Align to the top of each minute so every countdown steps together.
    setTimeout(function () { tick(); setInterval(tick, 60000); }, 60000 - (Date.now() % 60000) + 50);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) tick(); });
  }

  function reentryTable() {
    var box = document.getElementById("reentry-table");
    var since7 = daysAgo(7);
    var rows = (snap.reentries || []).filter(function (x) { return x.reentry_date >= since7 && x.type === "payload"; });
    if (!rows.length) return empty(box, "No payload reentries dated in the last 7 days.");
    var trs = rows.map(function (x) {
      var tr = el("tr");
      cell(tr, dayOnly(x.reentry_date) + (x.reentry_uncertain ? " ~" : ""));
      cell(tr, x.name);
      cell(tr, mark(x.country, x.state));
      cell(tr, x.norad || x.jcat, "muted");
      return tr;
    });
    box.textContent = "";
    box.appendChild(table(["Date", "Payload", "Owner", "Number"], trs));
    var other = (snap.reentries || []).filter(function (x) { return x.reentry_date >= since7 && x.type !== "payload"; }).length;
    if (other) box.appendChild(el("p", "muted small", "Also " + other + " rocket stages, components and debris."));
  }

  function catalogBody() {
    var box = document.getElementById("catalog-body");
    box.textContent = "";
    var ch = snap.catalog_changes || {};
    if (ch.previous_reading_at) {
      box.appendChild(el("p", "small", "Since " + fmt(ch.previous_reading_at) + ": " + ch.added + " new entries (" +
        ch.added_late + " from launches over 30 days old), " + ch.removed + " removed, " + ch.changed + " changed."));
      var ul = el("ul", "plain small");
      (ch.late_groups || []).slice(0, 8).forEach(function (g) {
        ul.appendChild(el("li", "", g.count + " new from launch " + g.launch_tag + " (" + g.launch_date + ", " +
          g.states.join(", ") + "): " + g.objects.slice(0, 3).map(function (o) { return o.name; }).join(", ") +
          (g.count > 3 ? "…" : "")));
      });
      (ch.owner_changes || []).slice(0, 8).forEach(function (c) {
        var f = c.fields, parts = [];
        ["state", "owner"].forEach(function (k) { if (f[k]) parts.push(k + " " + (f[k][0] || "-") + " → " + (f[k][1] || "-")); });
        ul.appendChild(el("li", "", c.name + ": " + parts.join(", ")));
      });
      if (ul.children.length) box.appendChild(ul);
    } else {
      box.appendChild(el("p", "muted small", "First reading: changes appear from Orbit's next reading of GCAT."));
    }
    var h = snap.hygiene || {};
    if (h.in_orbit) {
      var dl = el("ul", "plain small");
      dl.appendChild(el("li", "", "In orbit: " + h.in_orbit.toLocaleString() + " objects. Russian Federation (RU) " +
        (h.in_orbit_russian_ru || 0).toLocaleString() + ", Soviet (SU) " + (h.in_orbit_soviet_su || 0).toLocaleString() +
        ": CelesTrak's owner code CIS would count these together."));
      dl.appendChild(el("li", "", "In orbit with no catalog number: " + (h.unnumbered_in_orbit || 0).toLocaleString() +
        " (" + Object.keys(h.unnumbered_in_orbit_by_state || {}).slice(0, 4).map(function (k) {
          return k + " " + h.unnumbered_in_orbit_by_state[k]; }).join(", ") + ")."));
      var dupes = Object.keys(h.duplicate_catalog_numbers || {});
      dl.appendChild(el("li", "", "Catalog numbers claimed by two GCAT entries: " + dupes.length +
        (dupes.length ? " (" + dupes.slice(0, 5).join(", ") + ")" : "") + "."));
      box.appendChild(el("h3", "small", "Owner codes"));
      box.appendChild(dl);
      ownerChart(box, h);
    }
  }

  function ownerChart(box, h) {
    var rows = h.in_orbit_owners;
    if (!rows || !rows.length) return;
    rows = rows.slice(0, 15);
    var max = rows[0].total || 1;
    box.appendChild(el("h3", "small", "Objects in orbit by owner (GCAT, top " + rows.length + ")"));
    var g = el("div", "owners");
    g.setAttribute("role", "table");
    g.setAttribute("aria-label", "Objects in orbit by owner: total and payloads");
    rows.forEach(function (o) {
      var group = o.state === "SU" ? "ru" : (BIG[o.country] || "other");
      var r = el("div", "row");
      r.setAttribute("role", "row");
      var rest = o.total - o.payloads;
      var label = mark(o.country, o.state);
      var tip = (label.title || o.state) + ": " + o.total.toLocaleString() + " objects in orbit, " +
        o.payloads.toLocaleString() + " payloads and " + rest.toLocaleString() + " rocket stages, components and debris";
      r.title = tip;
      var c1 = el("div"); c1.setAttribute("role", "cell"); c1.appendChild(label);
      var bar = el("div", "bar"); bar.setAttribute("role", "cell"); bar.setAttribute("aria-label", tip);
      if (o.payloads) { var p = el("div", "seg pay g-" + group); p.style.width = (100 * o.payloads / max) + "%"; bar.appendChild(p); }
      if (rest) { var q = el("div", "seg rest g-" + group); q.style.width = (100 * rest / max) + "%"; bar.appendChild(q); }
      var n = el("div", "n", o.total.toLocaleString() + " (" + o.payloads.toLocaleString() + " payloads)");
      n.setAttribute("role", "cell");
      r.appendChild(c1); r.appendChild(bar); r.appendChild(n);
      g.appendChild(r);
    });
    box.appendChild(g);
    box.appendChild(el("p", "muted small", "Solid: payloads. Pale: rocket stages, components and debris. GCAT owner " +
      "codes; SU is the Soviet Union, kept apart from the Russian Federation (RU)."));
  }

  function sourcesOf(lane) {
    return ((sources && sources.sources) || []).filter(function (s) { return (s.lanes || []).indexOf(lane) >= 0; });
  }
  function gradeBadge(src) {
    var gb = el("span", "badge grade", "Grade " + src.grade);
    gb.title = "Admiralty grade: source reliability " + src.grade.charAt(0) + " (" + src.reliability +
      "), information credibility " + src.grade.slice(1) + " (" + src.credibility + ")";
    return gb;
  }
  function lanes() {
    var box = document.getElementById("lanes");
    box.textContent = "";
    var names = { catalog: "GCAT catalog and launch list (J. McDowell)", upcoming: "Launch Library 2 (The Space Devs)",
      navwarn: "Navigational warnings", counterspace: "Secure World Foundation, ASAT test history",
      maneuver: "Space-Track.org (USSPACECOM, 18th Space Defense Squadron)" };
    var srcNames = { "nga-msi": "NGA Maritime Safety Information",
      "jcg-navarea11": "Japan Coast Guard, NAVAREA XI" };
    var ul = el("ul", "plain small lanes");
    Object.keys(snap.lanes || {}).forEach(function (k) {
      var s = snap.lanes[k], srcs = sourcesOf(k);
      var li = el("li");
      var multi = srcs.length > 1 || k === "navwarn";  // navwarn always shows NGA's per-memo status
      var head = el("div", "lane-head");
      if (!multi && srcs[0] && srcs[0].url) {
        var a = el("a", "", names[k] || k); a.href = srcs[0].url; a.rel = "noopener"; head.appendChild(a);
      } else head.appendChild(el("strong", "", names[k] || k));
      if (!multi && srcs[0] && srcs[0].grade) {
        head.appendChild(gradeBadge(srcs[0]));
        head.appendChild(el("span", "muted", srcs[0].reliability.toLowerCase() + " source; information " +
          srcs[0].credibility.toLowerCase()));
      }
      li.appendChild(head);
      if (multi) {
        var nwSrc = ((snap.navwarn || {}).sources) || {};
        srcs.forEach(function (src) {
          var sh = el("div", "lane-head sub");
          var a2 = el("a", "", srcNames[src.id] || src.name); a2.href = src.url; a2.rel = "noopener"; sh.appendChild(a2);
          if (src.grade) {
            sh.appendChild(gradeBadge(src));
            sh.appendChild(el("span", "muted", src.reliability.toLowerCase() + " source; information " +
              src.credibility.toLowerCase()));
          }
          li.appendChild(sh);
          var st = nwSrc[src.id === "nga-msi" ? "nga" : "jcg"];
          if (st) {
            var parts = ["Status " + st.status];
            if (st.form === "api") parts.push("read from NGA's broadcast-warn API");
            else if (st.form === "memoranda") parts.push("read from the daily in-force memoranda (API: " +
              (st.api_error || "not used") + ")");
            if (st.memos) {
              Object.keys(st.memos).forEach(function (m) {
                var mm = st.memos[m];
                parts.push(m + (mm.error ? " failed (" + mm.error + ")" : " as of " + fmt(mm.as_of) + ", " +
                  mm.launch_related + " of " + mm.in_force + " launch-related"));
              });
            }
            if (st.listed != null) parts.push(st.launch_titles + " of " + st.listed + " in-force warnings launch-related");
            if (st.error) parts.push("Error: " + st.error);
            if (st.reason) parts.push(st.reason);
            (st.errors || []).forEach(function (e) { parts.push("Skipped " + e); });
            li.appendChild(el("div", "sub", parts.join("; ")));
          }
          if (src.licence) li.appendChild(el("div", "muted sub", "Terms: " + src.licence));
        });
      }
      var when = s.fetched_at ? "read " + fmt(s.fetched_at) : "never read";
      var txt = "Status " + s.status + (s.from_previous ? " (showing the last good copy)" : "") +
        "; " + when + (s.checked_at ? ", checked " + fmt(s.checked_at) : "");
      if (s.status === "failed" && s.error) txt += ". Error: " + s.error;
      if (s.status === "off" && s.reason) txt += ". Not read: " + s.reason;
      li.appendChild(el("div", "", txt));
      if (!multi && srcs[0] && srcs[0].licence) li.appendChild(el("div", "muted", "Terms: " + srcs[0].licence));
      ul.appendChild(li);
    });
    var g = snap.gcat_updated || {};
    if (g.satcat) ul.appendChild(el("li", "muted", "GCAT tables stamped " + g.satcat + " UTC (GCAT's own update time)."));
    box.appendChild(ul);
    if (sources && sources.sources && sources.sources.length) {
      box.appendChild(el("p", "muted small", "Grades are Orbit's, on the NATO Admiralty system: source reliability " +
        "A (completely reliable) to F (cannot be judged) and information credibility 1 (confirmed by other sources) " +
        "to 6 (cannot be judged), graded separately."));
    }
  }

  function render() {
    if (!snap) return;
    tiles(); launchTable(); upcomingTable(); hazardTable(); maneuverCard(); counterspaceCard(); reentryTable(); catalogBody(); lanes();
    startMap();
    if (location.hash) { var t = reveal(location.hash.slice(1)); if (t) t.scrollIntoView(); }
    markSection();
  }

  window.addEventListener("hashchange", function () {
    var r = reveal(location.hash.slice(1));
    if (r) r.scrollIntoView();
    markSection();
  });

  // The section bar marks the section in view.
  var barLinks = [].slice.call(document.querySelectorAll(".secbar a"));
  function markSection() {
    var cur = 0, curTop = -Infinity;
    barLinks.forEach(function (link, i) {
      var s = document.getElementById(link.getAttribute("href").slice(1));
      var top = s ? s.getBoundingClientRect().top : Infinity;
      // Side-by-side cards (reentries and catalog) share a top: the first one keeps the mark.
      if (top <= 120 && top > curTop + 1) { cur = i; curTop = top; }
    });
    barLinks.forEach(function (link, i) {
      if (i === cur) link.setAttribute("aria-current", "location"); else link.removeAttribute("aria-current");
    });
  }
  window.addEventListener("scroll", markSection, { passive: true });

  // On a phone, a long card note shows three lines; selecting it shows the rest.
  var notes = [].slice.call(document.querySelectorAll(".card-head p"));
  function clampNotes() {
    var phone = window.matchMedia("(max-width: 600px)").matches;
    notes.forEach(function (p) {
      var long = phone && !p.classList.contains("open") && p.scrollHeight > p.clientHeight + 2;
      if (long || (phone && p.classList.contains("open"))) {
        p.tabIndex = 0; p.setAttribute("role", "button");
        p.setAttribute("aria-expanded", String(p.classList.contains("open")));
      } else if (!phone) {
        p.removeAttribute("tabindex"); p.removeAttribute("role"); p.removeAttribute("aria-expanded");
      }
    });
  }
  notes.forEach(function (p) {
    function toggle() {
      if (!p.hasAttribute("role")) return;
      p.classList.toggle("open");
      p.setAttribute("aria-expanded", String(p.classList.contains("open")));
    }
    p.addEventListener("click", toggle);
    p.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
    });
  });
  clampNotes();
  window.addEventListener("resize", clampNotes);

  if (T && T.mountSettings) T.mountSettings(document.getElementById("time-settings"));
  if (T && T.onChange) T.onChange(render);
  // The grades are an extra: the page draws without them if data/sources.json does not load.
  var gotSources = fetch("data/sources.json", { cache: "no-cache" })
    .then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
  fetch("data/snapshot.json", { cache: "no-cache" }).then(function (r) { return r.json(); }).then(function (d) {
    snap = d;
    return gotSources;
  }).then(function (sd) {
    sources = sd; render(); startTicking();
  }).catch(function (e) {
    document.getElementById("tiles").textContent = "Could not load data/snapshot.json: " + e;
  });
})();
