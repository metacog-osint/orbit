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
    t.setAttribute("data-tic-fold", "5 10");
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
  // Long tables fold with the hub's tic-fold.js: table() marks every table, which shows its first 5 rows on a phone
  // (each row is a tall block there) and 10 wider, as Orbit's own fold did, then "Show all" (only when 3 or more
  // would hide). fold() sets other counts or adds a find box. A
  // link to a folded row (the map's "Show in table") opens its fold and its section.
  function fold(rows, counts, find) {
    var t = rows.length && rows[0].closest("table");
    if (!t) return;
    if (counts) t.setAttribute("data-tic-fold", counts);
    if (find) t.setAttribute("data-tic-fold-find", "");
  }
  // The sections row (tic-tabs.js): on a phone one group shows at a time, so open the group that holds an element.
  function openGroup(target) {
    var grp = target && target.closest("[data-tab-label]");
    var tabs = grp && window.TicTabs && window.TicTabs.setup(grp.parentElement);
    if (tabs) tabs.show(grp.id);
  }
  /* Pages (orbit-2.22, ideas#71 and ideas#83): each group of cards is its own page. PAGE_OF names the page that
     holds a card id or a row id prefix; a link to an id not on this page goes to that page, and an old /#section
     link on the home page is sent there too. */
  var PAGE = (document.querySelector("main[data-page]") || { getAttribute: function () { return "index"; } }).getAttribute("data-page");
  // Ids of the old single page that no page holds now (its tab panels, and parts of cards retired in orbit-2.32):
  // a link to one goes to the card that took its place.
  var MOVED = {
    "sec-launches": "launches", "sec-history": "ledger", "lg-h": "ledger", "ledger-body": "ledger", "hist-n": "ledger",
    "hist-on": "ledger", "hist-who": "ledger", "hist-year": "ledger", "hz-h": "hazards", "hazard-table": "hazards",
    "upcoming-table": "upcoming", "sec-reentries": "reentries", "sec-baseline": "baseline", "sec-changes": "maneuvers",
    "sec-sources": "sources"
  };
  var PAGE_OF = {
    "sat-map": "index",
    "map-card": "launches", launches: "launches", upcoming: "launches", hazards: "launches", ledger: "launches",
    globe: "launches", "launch-": "launches",
    reentries: "reentries", decay: "reentries", "decay-h": "reentries", "tipcheck-h": "reentries", "re-": "reentries",
    catalog: "catalog", breakups: "catalog", baseline: "catalog", "breakup-": "catalog",
    maneuvers: "changes", rpo: "changes", asat: "changes", "mv-": "changes",
    sources: "sources", "data-files": "sources",
    // the other ids of the single page before the split (orbit-2.22) that are still on a page, so an old /#id link
    // lands (tests/test_orbit.py holds the old page's list)
    "la-h": "launches", map: "launches", "map-h": "launches", "map-info": "launches", "view-flat": "launches",
    "view-globe": "launches", "globe-note": "launches", "up-h": "launches",
    "reentry-table": "reentries", "decay-body": "reentries", "tipcheck-body": "reentries",
    "cat-h": "catalog", "catalog-body": "catalog", "bu-h": "catalog", "base-h": "catalog", "baseline-body": "catalog",
    "archive-body": "catalog",
    "mn-h": "changes", "maneuver-body": "changes", "rpo-h": "changes", "rpo-body": "changes", "asat-h": "changes",
    "asat-body": "changes",
    "src-h": "sources", lanes: "sources"
  };
  function pageOf(id) {
    if (!id) return null;
    if (MOVED[id]) id = MOVED[id];
    if (PAGE_OF[id]) return PAGE_OF[id];
    var m = /^[a-z]+-/.exec(id);
    return m && PAGE_OF[m[0]] || null;
  }
  function pageUrl(pg) { return pg === "index" ? "./" : pg + ".html"; }
  function hrefTo(id) {  // "#id" on this page, else the page that holds it
    var pg = pageOf(id);
    return pg && pg !== PAGE && !document.getElementById(id) ? pageUrl(pg) + "#" + id : "#" + id;
  }
  (function oldLinks() {  // /#maneuvers and the like, from feeds, COP and bookmarks made before the split
    var id = location.hash ? decodeURIComponent(location.hash.slice(1)) : "";
    var pg = pageOf(id);
    if (PAGE === "index" && pg && pg !== "index") location.replace(pageUrl(pg) + "#" + (MOVED[id] || id));
  })();
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest('a[href^="#"]');
    if (!a || e.defaultPrevented) return;
    var id = decodeURIComponent(a.getAttribute("href").slice(1));
    if (!id || document.getElementById(id)) return;
    var pg = pageOf(id);
    if (pg && pg !== PAGE) { e.preventDefault(); location.href = pageUrl(pg) + "#" + id; }
  });
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
  /* A name linked to its object page (orbit-2.20): NORAD number first, else GCAT's JCAT id; plain text without either. */
  function objA(text, norad, jcat) {
    var k = norad != null && norad !== "" ? String(norad).replace(/^0+(?=\d)/, "") : jcat || "";
    var sj = /^S0*(\d+)$/.exec(k);  // GCAT's S-ids are its satcat entries: the NORAD number
    if (sj) k = sj[1];
    if (!k) return document.createTextNode(text == null ? "" : text);
    var a = el("a", "obj-link", text);
    a.href = "object.html?" + (/^\d+$/.test(k) ? "n=" : "j=") + encodeURIComponent(k);
    return a;
  }
  function who(marks, name) {
    var d = el("div", "who");
    marks.forEach(function (m) { d.appendChild(m); });
    if (name) d.appendChild(el("span", "nm", name));
    return d;
  }

  function tiles() {
    var box = document.getElementById("tiles");
    if (!box) return;
    box.textContent = "";
    var since7 = daysAgo(7);
    var launches = (snap.launches || []).filter(function (x) { return x.date >= since7; });
    var reentries = (snap.reentries || []).filter(function (x) { return x.reentry_date >= since7 && x.type === "payload"; });
    var h = snap.hygiene || {};
    [["Orbital launches, 7 days", launches.length, "launches"],
     ["Payload reentries, 7 days", reentries.length, "reentries"],
     ["Orbit changes, watched, 30 days", (snap.maneuvers || {}).read_at ? (snap.maneuvers.events || []).length : "–",
      "maneuvers"],
     ["Objects in orbit (GCAT)", h.in_orbit ? h.in_orbit.toLocaleString() : "–", "catalog"]].forEach(function (t) {
      var d = el("a", "tile");
      d.href = hrefTo(t[2]);
      d.appendChild(el("span", "k", t[0]));
      d.appendChild(el("span", "v", String(t[1])));
      box.appendChild(d);
    });
  }

  function partsInto(node, parts) {  // orbit/lead.py's parts: text, a time, a date, a country, an object's name
    (parts || []).forEach(function (p) {
      if (typeof p === "string") node.appendChild(document.createTextNode(p));
      else if (p.t) node.appendChild(document.createTextNode(fmt(p.t)));
      else if (p.d) node.appendChild(document.createTextNode(dayOnly(p.d)));
      else if (p.cc) node.appendChild(document.createTextNode(countryName(p.cc)));
      else if (p.s != null) node.appendChild(objA(p.s, /^\d+$/.test(String(p.o)) ? p.o : null, /^\d+$/.test(String(p.o)) ? null : p.o));
    });
    return node;
  }

  function leadCard() {  // orbit/lead.py (orbit-2.18): what changed in the last 24 hours, each line to its card
    var ul = document.getElementById("lead-list");
    if (!ul) return;
    ul.textContent = "";
    var L = snap.lead || {};
    var h = document.getElementById("lead-h");
    if (!L.at) {
      ul.appendChild(el("li", "muted", "Not built yet: the lead appears with Orbit's next run."));
      return;
    }
    if (h) h.textContent = "The last 24 hours, to " + fmt(L.at);
    if (L.nothing_new) ul.appendChild(el("li", "", "Nothing new in the last 24 hours from the sources read on this run."));
    (L.lines || []).forEach(function (x) {
      var li = el("li", x.kind === "notable" ? "lead-notable" : "");
      partsInto(li, x.parts);
      li.appendChild(document.createTextNode(" "));
      var a = el("a", "", "Details");
      a.href = x.href && x.href.charAt(0) === "#" ? hrefTo(x.href.slice(1)) : x.href || "#";
      li.appendChild(a);
      if (x.source) li.appendChild(el("span", "src", " · " + x.source));
      ul.appendChild(li);
    });
  }

  function launchTable() {
    var box = document.getElementById("launch-table");
    if (!box) return;
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
        byOwner[k].names.push(p);
      });
      owners.forEach(function (k) {
        var o = byOwner[k], line = el("div", "pl");
        line.appendChild(mark(o.country, o.state));
        var sp = el("span");
        o.names.slice(0, 6).forEach(function (p, i) {
          if (i) sp.appendChild(document.createTextNode(", "));
          sp.appendChild(objA(p.name, p.norad, p.jcat));
        });
        if (o.names.length > 6) sp.appendChild(document.createTextNode(", +" + (o.names.length - 6) + " more"));
        line.appendChild(sp);
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
    if (!box) return;
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
        "as a quiet one). " : "all with a recent element set. ") + countedText(mv.counted_not_listed) +
      "Read " + fmt(mv.read_at) + "."));
    if (!ev.length) return;
    var mvIds = {};
    var rows = ev.map(function (e) {
      var tr = el("tr");
      if (!mvIds[e.norad]) { mvIds[e.norad] = 1; tr.id = "mv-" + e.norad; }  // the globe's satellites open this row
      var who = el("div");
      who.appendChild(mark(e.cc, e.state));
      who.appendChild(objA(e.gcat_name || e.name || ("NORAD " + e.norad), e.norad));
      if (e.names && e.names.length) who.appendChild(el("div", "pl", "also " + e.names.join("; ")));  // orbit-2.26
      who.appendChild(el("div", "pl", "NORAD " + e.norad + (e.object_id ? ", " + e.object_id : "") +
        (e.regime ? ", " + e.regime : "")));
      if (e.notable) who.appendChild(el("div", "pl notable-note", "Notable: listed role on the GEO page (" +
        e.notable.role + "), " + e.notable.kind));
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
        " km" + (e.dv_sma_ms != null ? " (" + (e.dv_sma_ms >= 10 ? Math.round(e.dv_sma_ms) : e.dv_sma_ms.toFixed(2)) +
        " m/s from that change alone)" : "") + ", inclination " + (e.di_deg > 0 ? "+" : "") + e.di_deg + "\u00b0"));
      cell(tr, ch);
      var pos = el("div");
      if (e.geo) {
        pos.appendChild(document.createTextNode(lonText(e.geo.lon_before) + " to " + lonText(e.geo.lon_after)));
        pos.appendChild(el("div", "pl", driftText(e.geo.drift_before) + ", then " + driftText(e.geo.drift_after)));
        if (e.what) partsInto(pos.appendChild(el("div", "pl what-note", "What the sets show: it ")), e.what)
          .appendChild(document.createTextNode("."));
      }
      cell(tr, pos);
      cell(tr, el("span", "muted small", "Space-Track.org (USSPACECOM) element sets; Intelligence Company analysis."));
      return tr;
    });
    box.appendChild(table(["Object", "When", "Change", "Longitude (geostationary)", "Source"], rows));
    fold(rows);
  }

  function countedText(c) {  // marks counted, not listed (orbit-2.8)
    if (!c) return "";
    var parts = [];
    if (c.below_floor) parts.push(c.below_floor + " under the listing floor");
    if (c.low_orbit_off_track) parts.push(c.low_orbit_off_track + " in low orbit, mainly plane change or orbit shape " +
      "and under 1 m/s, where element-set noise is largest");
    return parts.length ? "Counted, not listed: " + parts.join("; ") + ". " : "";
  }

  function baselineCard() {
    var box = document.getElementById("baseline-body");
    if (!box) return;
    var b = (snap && snap.baseline) || {};
    if (!b.recent) return empty(box, "Not read yet: the baseline appears after Orbit's next reading of GCAT.");
    box.textContent = "";
    function ymd(d) {  // a plain date with its year: the windows span two years
      try { return new Date(d + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }); }
      catch (e) { return d; }
    }
    box.appendChild(el("p", "small", "Last 30 days: " + ymd(b.recent[0]) + " to " + ymd(b.recent[1]) + " (UTC dates). Before: " +
      b.prior_windows + " windows of " + b.window_days + " days, " + ymd(b.prior[0]) + " to " + ymd(b.prior[1]) + "."));
    function where(r) {
      if (r.position === "above") return "above all " + r.prior_windows;
      if (r.position === "below") return "below all " + r.prior_windows;
      return r.windows_at_or_above + " of " + r.prior_windows + " as high or higher";
    }
    function spark(series) {  // the 24 windows then the last 30 days, as small bars; the text carries the numbers
      var max = Math.max.apply(null, series.concat([1]));
      var s = el("span", "spark");
      s.setAttribute("aria-hidden", "true");
      series.forEach(function (v, i) {
        var bar = el("i", i === series.length - 1 ? "now" : "");
        bar.style.height = Math.max(1, Math.round(16 * v / max)) + "px";
        s.appendChild(bar);
      });
      return s;
    }
    function block(title, rows, keep, key, who) {
      if (!rows || !rows.length) return;
      box.appendChild(el("h3", "small", title));
      var trs = rows.map(function (r) {
        var tr = el("tr");
        cell(tr, who(r));
        cell(tr, String(r.recent), "num");
        cell(tr, r.prior_median + " (" + r.prior_min + " to " + r.prior_max + ")", "num");
        var w = el("div", r.position === "within" ? "" : "pos-" + r.position, where(r));
        cell(tr, w);
        cell(tr, spark(r.series));
        return tr;
      });
      var wrap = el("div", "tbl-wrap");
      wrap.appendChild(table(["", { label: "Last 30 days", num: true }, { label: "Before: median (range)", num: true },
        "Where it sits", "24 windows, then the last 30 days"], trs));
      box.appendChild(wrap);
      fold(trs, "5 " + keep);
    }
    var all = function (label) { return function () { return document.createTextNode(label); }; };
    var cc = function (r) { var d = el("div"); d.appendChild(mark(r.country, r.state || r.key)); return d; };
    var ag = function (r) {
      var d = el("div"); d.appendChild(mark(r.country, r.state));
      d.appendChild(document.createTextNode(r.name || r.agency));
      d.appendChild(el("div", "pl", "GCAT agency " + r.agency)); return d;
    };
    block("Orbital launches", (b.launches_all || []).map(function (r) { return Object.assign({}, r, { all: true }); })
      .concat(b.launches_by_country || []), 8, "base-lc", function (r) { return r.all ? all("All launches")() : cc(r); });
    block("Orbital launches by launch agency", b.launches_by_agency, 8, "base-la", ag);
    block("Payloads launched, by owner", b.payloads_by_owner, 8, "base-po", cc);
    block("Reentries, by owner", (b.reentries_all || []).map(function (r) { return Object.assign({}, r, { all: true }); })
      .concat(b.reentries_by_owner || []), 8, "base-ro", function (r) { return r.all ? all("All reentries")() : cc(r); });
  }

  function archiveNote() {  // Orbit's own daily archive (orbit/archive.py): what it keeps and when its baselines start
    var box = document.getElementById("archive-body");
    if (!box) return;
    var a = (snap && snap.archive) || {};
    box.textContent = "";
    var ymd = function (d) {
      try { return new Date(d + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }); }
      catch (e) { return d; }
    };
    var p = el("p", "small");
    p.appendChild(document.createTextNode(!a.days ? "Orbit's own daily archive has no days yet. " :
      "Orbit's own daily archive: " + a.days + (a.days === 1 ? " day" : " days") + " since " + ymd(a.first_day) +
      (a.missed_days ? " (" + a.missed_days + " with no run)" : "") + ". "));
    p.appendChild(document.createTextNode("It keeps what no outside source dates for Orbit: the orbit changes listed each day, " +
      "the launch and debris warning areas in force each day, and each GCAT reading's catalog changes, dated by the day " +
      "Orbit read them. " + (a.days ? "Baselines for those from " + ymd(a.baseline_from) + ", after 90 days. " : "")));
    var link = el("a", "", "The archive (JSON)");
    link.href = "data/archive.json";
    p.appendChild(link);
    p.appendChild(document.createTextNode("."));
    box.appendChild(p);
  }

  function counterspaceCard() {
    var box = document.getElementById("asat-body");
    if (!box) return;
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
    fold(rows, "", true);
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


  // SWF's rendezvous and proximity operations: SWF's text, Orbit's reading of its dates, GCAT matches.
  function rpoPart(s) {  // "2014-10" or "2014-10-03" or "2014", as precise as SWF gave it
    if (!s) return "";
    if (s.length === 10) return dayYear(s);
    if (s.length === 7) return MONTH_NAMES[parseInt(s.slice(5), 10) - 1] + " " + s.slice(0, 4);
    return s;
  }
  var MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function rpoWhen(r) {
    var w = r.when;
    if (!w) return r.date_text || "Not given";
    if (w.ongoing) return "Since " + rpoPart(w.start) + ", ongoing";
    if (w.end === w.start) return rpoPart(w.start);
    return rpoPart(w.start) + " to " + rpoPart(w.end);
  }
  function rpoSats(cellText, links) {
    var d = el("div");
    d.appendChild(el("div", "", cellText || "Not given"));
    var on = ((snap && snap.rpo) || {}).matched_on === "catalog" ? "Catalog" : "GCAT";
    (links || []).forEach(function (g) {
      if (g.program) {
        d.appendChild(el("div", "pl", "Program " + g.program + ": " + g.members.length + " objects (" +
          g.members.join(", ") + "), from the alias file"));
        return;
      }
      var ln = el("div", "pl", on + ": ");
      ln.appendChild(objA(g.cat_name || g.gcat_name, g.norad, g.jcat));
      ln.appendChild(document.createTextNode((g.norad ? " (" + g.norad + ")" : " (" + g.jcat + ")") +
        (g.by === "launch date" ? ", the one of that name launched in the year before" :
          g.by === "alias" ? ", from the alias file" : "")));
      d.appendChild(ln);
    });
    return d;
  }
  function rpoCard() {
    var box = document.getElementById("rpo-body");
    if (!box) return;
    var rp = (snap && snap.rpo) || {};
    if (!rp.read_at) return empty(box, "Not read yet: the history appears after Orbit's next collection.");
    box.textContent = "";
    var rows = rp.rows || [], tabs = rp.tabs || {}, roles = rp.roles || {};
    var key = function (r) { return (r.when && r.when.start) || ""; };
    ["military", "commercial", "planned"].forEach(function (tab) {
      var mine = rows.filter(function (r) { return r.tab === tab; })
        .sort(function (a, b) { return key(a) < key(b) ? 1 : key(a) > key(b) ? -1 : 0; });
      if (!mine.length) return;
      var ro = roles[tab] || ["Target", "Chaser"], planned = tab === "planned";
      var trs = mine.map(function (r) {
        var tr = el("tr");
        var when = el("div");
        when.appendChild(el("div", "", rpoWhen(r)));
        if (r.when && r.date_text) when.appendChild(el("div", "pl", "SWF: " + r.date_text));
        cell(tr, when);
        cell(tr, who([mark(r.cc, null)], r.country));
        cell(tr, rpoSats(r.chaser, (r.gcat || {}).chaser));
        cell(tr, rpoSats(r.target, (r.gcat || {}).target));
        cell(tr, r.mission_type || "–");
        if (planned) {
          cell(tr, r.org || "–");
          cell(tr, r.notes || "–", "small");
        } else {
          cell(tr, r.orbit || "–");
          cell(tr, r.site || "–");
          cell(tr, r.debris_released || "–");
        }
        return tr;
      });
      box.appendChild(el("h3", "small", (tabs[tab] || tab) + " (" + trs.length + ")"));
      var head = ["When (SWF's text below)", "Country", ro[1], ro[0], "Mission type"]
        .concat(planned ? ["Organisation", "SWF's notes"] : ["Orbit", "Launch site", "Debris released"]);
      var tw = el("div", "tbl-wrap");
      tw.appendChild(table(head, trs));
      fold(trs, "", true);
      box.appendChild(tw);
    });
    var note = el("div", "muted small asat-note");
    var bits = [];
    if (rp.updated) bits.push("The sheet says it was last updated " + dayYear(rp.updated) + "; Orbit read it " +
      fmt(rp.read_at) + ".");
    var un = rp.unread_dates || [];
    if (un.length) {
      bits.push("Orbit could not read " + (un.length === 1 ? "one row's date" : un.length + " rows' dates") +
        " into a span, so " + (un.length === 1 ? "it shows" : "they show") + " SWF's text as given and " +
        (un.length === 1 ? "sorts" : "sort") + " last: " + un.map(function (u) {
          return u.country + ", " + u.date_text + ", " + (u.chaser || "not given");
        }).join("; ") + ".");
    }
    if (rp.matched_on === "catalog") {
      bits.push("Categories, purposes and spans are SWF's. A catalog match is Orbit's: on every name TIC's " +
        "satellite catalog holds (Space-Track, GCAT, CelesTrak, Wikidata) and launch date, or a reviewed entry " +
        "in Orbit's alias file; where two objects fit, none is shown." +
        (rp.links ? " " + rp.links.linked + " of " + rp.links.names + " names matched." : ""));
    } else {
      bits.push("Categories, purposes and spans are SWF's; a GCAT match is Orbit's, by name and launch date.");
    }
    note.appendChild(el("p", "", bits.join(" ")));
    var cr = el("p", "");
    cr.appendChild(document.createTextNode("Secure World Foundation, Global Counterspace Capabilities (2026), " +
      "CC BY-NC 4.0: "));
    var a1 = el("a", "", "report"); a1.href = rp.report; a1.rel = "noopener"; cr.appendChild(a1);
    cr.appendChild(document.createTextNode(", "));
    var a2 = el("a", "", "sheet"); a2.href = rp.sheet; a2.rel = "noopener"; cr.appendChild(a2);
    cr.appendChild(document.createTextNode("."));
    note.appendChild(cr);
    box.appendChild(note);
  }


  /* The map loads after the tables, from map.js (an ES module with MapLibre); without WebGL it says so. */
  var mapApi = null, mapStarted = false, flatApi = null, globeApi = null, globeStarting = false, view = "flat";
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
    return { launches: launchesFc, tracks: trackList(), payloadTracks: payloadTracks(), reentryTracks: reentryTracks() };
  }
  /* For the globe (orbit-2.15): each object with a TIP prediction and a Space-Track set from the same run's GP
     query, keyed "re-<NORAD>"; its track spans the TIP window (at most 24 h each side). Drawn only while picked. */
  function reentryTracks() {
    var dc = (snap && snap.decay) || {}, sets = ((snap && snap.reentry_sets) || {}).sets || {}, out = {};
    (dc.objects || []).forEach(function (x) {
      var s = sets[String(x.norad)];
      if (!s) return;
      var half = Math.min(x.window_min || 60, 1440) * 60000, t = Date.parse(x.decay_epoch);
      out["re-" + x.norad] = { key: "re-" + x.norad, name: x.name || ("NORAD " + x.norad), group: groupOf(x.cc, x.state),
        elements: Object.assign({ norad: x.norad }, s), from: new Date(t - half).toISOString(),
        to: new Date(t + half).toISOString(), lat: x.lat, lon: x.lon };
    });
    return out;
  }
  /* For the globe: each satellite with a listed orbit change once, with the newest element set Orbit holds. */
  function trackList() {
    var seen = {}, out = [];
    (((snap && snap.maneuvers) || {}).events || []).forEach(function (e) {
      if (seen[e.norad]) return;
      seen[e.norad] = 1;
      out.push({ key: "mv-" + e.norad, name: e.gcat_name || e.name || ("NORAD " + e.norad), group: groupOf(e.cc, e.state),
        elements: e.elements ? Object.assign({ norad: e.norad }, e.elements) : null });
    });
    return out;
  }
  /* For the globe: the payloads of each launch of the last 7 days that CelesTrak's last-30-days group has a set
     for, keyed by the launch's map key. Drawn only while that launch is picked. */
  function payloadTracks() {
    var by = ((snap && snap.payload_sets) || {}).by_launch || {}, out = {}, since7 = daysAgo(7);
    (snap.launches || []).forEach(function (x) {
      if (!(x.date >= since7)) return;  // only launches with a dot on the globe can be picked
      var objs = by[x.launch_tag];
      if (!objs || !objs.length) return;
      var l = (x.launchers || [])[0] || {};
      out["launch-" + x.launch_tag.replace(/ /g, "-")] = objs.map(function (o) {
        return { key: "launch-" + x.launch_tag.replace(/ /g, "-"), name: o.name || o.cospar,
          group: groupOf(l.country, l.state), elements: Object.assign({ norad: o.norad }, o.elements) };
      });
    });
    return out;
  }
  function describe(key) {
    var row = document.getElementById(key);
    if (!row) return null;
    var txt = function (c) { return c ? (c.innerText || c.textContent).replace(/\s+/g, " ").trim() : ""; };
    var main = txt(row.cells[1]).slice(0, 160);
    if (key.indexOf("mv-") === 0) {  // name, when it began, and its size: the text of each cell's own lines, not the notes
      var own = function (c) {
        var out = [];
        (function walk(n) { for (var k = n.firstChild; k; k = k.nextSibling) {
          if (k.nodeType === 3) out.push(k.textContent); else if (!/\bpl\b/.test(k.className || "")) walk(k);
        } })(c);
        return out.join(" ").replace(/\s+/g, " ").trim();
      };
      return own(row.cells[0]) + ": orbit change from " + own(row.cells[1]) + ", " + own(row.cells[2]);
    }
    return main;
  }
  /* A launch dot's card (orbit-2.10): GCAT's payloads with their orbits, grouped where they share one, and a link
     to the same launch in Launch's history. */
  function orbitText(p) {
    if (p.inc == null) return "no orbital elements in GCAT yet";
    return (p.apogee == null ? "perigee " + num(p.perigee) + " km, escape (no apogee)" :
      num(p.perigee) + " x " + num(p.apogee) + " km") + ", " + p.inc.toFixed(1) + "°" +
      (p.orbit_date ? " (elements of " + dayOnly(p.orbit_date) + ")" : "");
  }
  function launchCard(key) {
    var x = (snap.launches || []).filter(function (l) { return "launch-" + l.launch_tag.replace(/ /g, "-") === key; })[0];
    if (!x) return null;
    var box = el("div", "pick");
    var title = [x.flight, x.mission && x.mission !== x.flight ? "(" + x.mission + ")" : ""].join(" ").trim() || x.launch_tag;
    box.appendChild(el("div", "pick-h", title));
    var st = x.site || {};
    box.appendChild(el("div", "pl", [x.vehicle + (x.variant ? " " + x.variant : ""), st.name || x.site_code,
      x.time ? fmt(x.time) : dayOnly(x.date) + " ~", x.outcome].filter(Boolean).join(" · ")));
    var groups = [], seen = {};
    (x.payloads || []).forEach(function (p) {
      var k = p.inc == null ? "none|" + (p.state || "") :
        [p.inc.toFixed(1), Math.round((p.perigee || 0) / 10), p.apogee == null ? "esc" : Math.round(p.apogee / 10),
          p.state || ""].join("|");
      if (!seen[k]) { seen[k] = { p: p, names: [] }; groups.push(seen[k]); }
      seen[k].names.push(p.name);
    });
    if (!groups.length) box.appendChild(el("div", "pl", "Payloads not yet cataloged by GCAT."));
    var ul = el("ul", "plain small");
    groups.slice(0, 8).forEach(function (g) {
      var li = el("li");
      li.appendChild(mark(g.p.country, g.p.state));
      li.appendChild(document.createTextNode(" "));
      li.appendChild(objA(g.names[0], g.p.norad, g.p.jcat));
      li.appendChild(document.createTextNode((g.names.length > 1 ? " and " + (g.names.length - 1) + " more" : "") + ": " + orbitText(g.p)));
      ul.appendChild(li);
    });
    if (groups.length > 8) ul.appendChild(el("li", "muted", "+" + (groups.length - 8) + " more orbits"));
    if (groups.length) box.appendChild(ul);
    var sets = (((snap.payload_sets || {}).by_launch) || {})[x.launch_tag] || [];
    if (sets.length) {
      box.appendChild(el("div", "pl small muted", (view === "globe" ? "Paths on the globe for " :
        "On the globe: paths for ") + sets.length + (sets.length === 1 ? " object" : " objects") +
        " of this launch, from CelesTrak's sets (18th Space Defense Squadron data, epoch " +
        dayOnly(sets[0].elements.epoch.slice(0, 10)) + "). For orientation, not for tracking."));
    }
    if ((x.payloads_cataloged || 0) > (x.payloads || []).length) {
      box.appendChild(el("div", "pl", "Showing " + x.payloads.length + " of " + x.payloads_cataloged + " payloads."));
    }
    var links = el("div", "small");
    var t = el("a", "", "Show in table"); t.href = "#" + key; links.appendChild(t);
    links.appendChild(document.createTextNode(" · "));
    var lh = el("a", "", "Find it in Launch's history");
    lh.href = "https://launch.theintelligence.company/#history?st=launched&q=" + encodeURIComponent(x.launch_tag) +
      "&sel=" + encodeURIComponent("gcat:" + x.launch_tag);
    lh.rel = "noopener"; links.appendChild(lh);
    box.appendChild(links);
    return box;
  }
  var pendingReentry = null;
  function showReentry(key) {  // a decay row's button: the globe, then that object's track over its window
    var card = document.getElementById("map-card");
    if (!card) { location.href = "launches.html?track=" + encodeURIComponent(key) + "#map-card"; return; }
    openGroup(card);
    if (card) card.scrollIntoView({ behavior: "smooth", block: "start" });
    pendingReentry = key;
    setView("globe");
    if (globeApi) applyReentry();
  }
  function applyReentry() {
    if (!pendingReentry || !globeApi || !globeApi.showReentry) return;
    var k = pendingReentry; pendingReentry = null;
    globeApi.showReentry(k);
    onPick(k);
  }
  function reentryInfo(key) {
    var x = (((snap.decay || {}).objects) || []).filter(function (o) { return "re-" + o.norad === key; })[0];
    if (!x) return null;
    var d = el("div");
    d.appendChild(el("strong", "", (x.name || ("NORAD " + x.norad)) + ": predicted reentry " + fmt(x.decay_epoch) +
      (x.window_min != null ? ", window \u00b1" + x.window_min + " min" : "")));
    d.appendChild(el("p", "small", "The line is the ground track the object would follow through the whole window, " +
      "propagated with SGP4 from the newest Space-Track element set, drag kept; it comes down somewhere along it, not " +
      "at the dot. The dot is where TIP puts it at the predicted time. USSPACECOM's prediction (Space-Track.org TIP), " +
      "quoted, not checked; Orbit's drawing. Not for operational use."));
    var link = el("a", "small", "Show in table"); link.href = "#" + key;
    d.appendChild(link);
    return d;
  }
  function onPick(key) {
    var info = document.getElementById("map-info");
    info.textContent = "";
    if (mapApi && mapApi.showReentry && key.indexOf("re-") !== 0) mapApi.showReentry("");
    if (key.indexOf("re-") === 0) {
      var ri = reentryInfo(key);
      if (ri) info.appendChild(ri);
      return;
    }
    var card = key.indexOf("launch-") === 0 ? launchCard(key) : null;
    if (mapApi && mapApi.showPayloads) mapApi.showPayloads(key.indexOf("launch-") === 0 ? key : "");
    if (card) { info.appendChild(card); if (mapApi) mapApi.select(""); return; }
    var text = describe(key);
    if (!text) return;
    info.appendChild(document.createTextNode(text + " "));
    var link = el("a", "", "Show in table"); link.href = "#" + key;
    info.appendChild(link);
    if (mapApi) mapApi.select("");
  }
  /* The globe (globe.js: CesiumJS, loaded only when asked for, about 6 MB once): the flat map's layers and the same
     cards, plus the paths of the satellites with listed orbit changes. "#globe" in the address opens it. */
  function globeText(api) {
    var d = api.drawn || {}, parts = [];
    parts.push(d.tracks ? "Paths drawn for " + d.tracks + (d.tracks === 1 ? " satellite" : " satellites") +
      " with a listed orbit change: each one's place when this page opened and one orbit around it (a day at GEO), " +
      "propagated with SGP4 from the newest Space-Track element set Orbit holds, drag left out. For orientation, " +
      "not for tracking." : "No satellite paths: no listed orbit change has an element set on the page yet.");
    if (d.without) parts.push(d.without + " listed without a usable element set.");
    if (d.launches) parts.push("Pick a launch of the last 7 days to draw its payloads' paths (" + d.launches +
      (d.launches === 1 ? " launch has" : " launches have") + " sets from CelesTrak, from the 18th Space Defense " +
      "Squadron's data).");
    if (d.reentries) parts.push("Predicted reentries: " + d.reentries + (d.reentries === 1 ? " object has" : " objects have") +
      " a track over its TIP window; open it from the Predicted reentries table.");
    parts.push(api.ion ? "Imagery: Cesium ion (Bing Maps)." : "Imagery: Natural Earth II, shipped with CesiumJS.");
    return parts.join(" ");
  }
  function setView(v) {
    var flat = document.getElementById("map"), glob = document.getElementById("globe"), note = document.getElementById("globe-note");
    var bf = document.getElementById("view-flat"), bg = document.getElementById("view-globe");
    if (!flat || !glob) return;
    view = v === "globe" ? "globe" : "flat";
    var g = view === "globe";
    flat.hidden = g; glob.hidden = !g; note.hidden = !g;
    bf.setAttribute("aria-pressed", String(!g)); bg.setAttribute("aria-pressed", String(g));
    if (!g) { mapApi = flatApi; if (flatApi) flatApi.resize(); return; }
    if (globeApi) { mapApi = globeApi; globeApi.resize(); return; }
    if (globeStarting) return;
    globeStarting = true;
    note.textContent = "Loading the globe (about 6 MB, once).";
    import("./globe.js").then(function (m) { return m.createGlobe(glob, mapModel(), { onPick: onPick }); })
      .then(function (api) { globeApi = api; if (view === "globe") mapApi = api; note.textContent = globeText(api); applyReentry(); })
      .catch(function (e) {
        globeStarting = false;
        note.textContent = "The globe could not load (" + e + "); the flat map and the tables list everything.";
      });
  }
  function viewControls() {
    var bf = document.getElementById("view-flat"), bg = document.getElementById("view-globe");
    if (!bf || !bg) return;
    bf.addEventListener("click", function () { setView("flat"); });
    bg.addEventListener("click", function () { setView("globe"); });
    if (location.hash === "#globe") setView("globe");
  }
  function startMap() {
    if (mapStarted) return;
    mapStarted = true;
    var box = document.getElementById("map");
    if (!box) return;
    var test = document.createElement("canvas");
    var gl = null;
    try { gl = test.getContext("webgl2") || test.getContext("webgl"); } catch (e) { gl = null; }
    if (!gl) { box.textContent = "This browser has no WebGL, so the map cannot be drawn; the tables list everything."; return; }
    import("./map.js").then(function (m) {
      return m.createMap(box, mapModel(), { onPick: onPick });
    }).then(function (api) { flatApi = api; if (view === "flat") mapApi = api; }).catch(function (e) {
      box.textContent = "The map could not load (" + e + "); the tables list everything.";
    });
  }

  function reentryTable() {
    var box = document.getElementById("reentry-table");
    if (!box) return;
    var since7 = daysAgo(7);
    var rows = (snap.reentries || []).filter(function (x) { return x.reentry_date >= since7 && x.type === "payload"; });
    if (!rows.length) return empty(box, "No payload reentries dated in the last 7 days.");
    var trs = rows.map(function (x) {
      var tr = el("tr");
      cell(tr, dayOnly(x.reentry_date) + (x.reentry_uncertain ? " ~" : ""));
      cell(tr, objA(x.name, x.norad, x.jcat));
      cell(tr, mark(x.country, x.state));
      cell(tr, x.norad || x.jcat, "muted");
      return tr;
    });
    box.textContent = "";
    box.appendChild(table(["Date", "Payload", "Owner", "Number"], trs));
    var other = (snap.reentries || []).filter(function (x) { return x.reentry_date >= since7 && x.type !== "payload"; }).length;
    if (other) box.appendChild(el("p", "muted small", "Also " + other + " rocket stages, components and debris."));
  }

  var BROKE = { E: "Exploded", C: "Collided" };
  function breakupTable() {  // GCAT statuses E and C, last 30 days (gcat.recent_breakups, orbit-2.14)
    var box = document.getElementById("breakup-table");
    if (!box) return;
    var since30 = daysAgo(30);
    var rows = (snap.breakups || []).filter(function (x) { return x.breakup_date >= since30; });
    if (!rows.length) return empty(box, "No object GCAT marks exploded or collided has a date in the last 30 days.");
    var trs = rows.map(function (x) {
      var tr = el("tr");
      tr.id = "breakup-" + x.jcat;
      cell(tr, dayOnly(x.breakup_date) + (x.breakup_uncertain ? " ~" : ""));
      cell(tr, objA(x.name, x.norad, x.jcat));
      cell(tr, x.type);
      cell(tr, BROKE[x.status] || x.status);
      cell(tr, mark(x.country, x.state));
      cell(tr, x.launch_tag || "", "muted");
      cell(tr, x.norad || x.jcat, "muted");
      return tr;
    });
    box.textContent = "";
    box.appendChild(table(["Date", "Object", "Type", "GCAT status", "Owner", "Launch", "Number"], trs));
  }

  var KIND = { P: "payload", R: "rocket stage", C: "component", D: "debris", S: "suborbital" };
  function decayCard() {  // Space-Track TIP messages (orbit/tip.py, orbit-2.13)
    var box = document.getElementById("decay-body");
    if (!box) return;
    var dc = (snap && snap.decay) || {};
    var lane = (snap.lanes || {}).decay || {};
    if (!dc.read_at) {
      return empty(box, lane.status === "off" ? "Not read: " + (lane.reason || "the lane is off") + "." :
        "Not read yet: predictions appear after Orbit's next reading of Space-Track.");
    }
    var objs = dc.objects || [];
    var ahead = objs.filter(function (x) { return !x.passed; });
    box.textContent = "";
    box.appendChild(el("p", "small", ahead.length + (ahead.length === 1 ? " object" : " objects") +
      " with a prediction window still open" + (objs.length > ahead.length ? ", " + (objs.length - ahead.length) +
      " whose window closed in the last day" : "") + (dc.high_interest ? "; " + dc.high_interest + " flagged high interest by USSPACECOM" : "") +
      ". " + dc.messages + " TIP messages in the last " + dc.window_days + " days. Read " + fmt(dc.read_at) + "."));
    if (!objs.length) return;
    var sets = ((snap.reentry_sets || {}).sets) || {};
    var rows = objs.map(function (x) {
      var tr = el("tr");
      tr.id = "re-" + x.norad;  // the globe's reentry tracks open this row
      if (x.passed) tr.className = "muted";
      var when = el("div", "", fmt(x.decay_epoch));
      when.appendChild(el("div", "pl", (x.window_min != null ? "window ±" + (x.window_min >= 120 ?
        (x.window_min / 60).toFixed(x.window_min % 60 ? 1 : 0) + " h" : x.window_min + " min") : "no window given") +
        (x.passed ? ", closed" : "")));
      cell(tr, when);
      var who = el("div");
      if (x.cc || x.state) who.appendChild(mark(x.cc, x.state));
      who.appendChild(objA(x.name || ("NORAD " + x.norad), x.norad));
      var sub = [x.name ? "NORAD " + x.norad : "", x.launch_tag || "",
        x.type && KIND[x.type.charAt(0)] ? KIND[x.type.charAt(0)] : "", x.high_interest ? "high interest" : ""]
        .filter(Boolean).join(", ");
      if (sub) who.appendChild(el("div", "pl", sub));
      cell(tr, who);
      var at = el("div", "", x.lat == null || x.lon == null ? "" : Math.abs(x.lat).toFixed(1) + "°" +
        (x.lat < 0 ? "S" : "N") + " " + lonText(x.lon));
      at.appendChild(el("div", "pl", [x.direction, x.incl != null ? "inclination " + x.incl + "°" : ""]
        .filter(Boolean).join(", ")));
      cell(tr, at);
      var msg = el("div", "", "issued " + fmt(x.msg_epoch));
      msg.appendChild(el("div", "pl", (x.messages > 1 ? x.messages + " messages in " + dc.window_days + " days" : "1 message") +
        (x.next_report_h ? "; next in about " + x.next_report_h + " h" : "")));
      if (sets[String(x.norad)]) {
        var b = el("button", "linkish small", "Track on the globe");
        b.type = "button";
        b.addEventListener("click", function () { showReentry("re-" + x.norad); });
        msg.appendChild(b);
      }
      cell(tr, msg);
      return tr;
    });
    box.appendChild(table(["Predicted time", "Object", "Place at that time", "Message"], rows));
    fold(rows);
  }

  function mins(m) {  // a signed difference in minutes, in the largest unit that reads well
    var a = Math.abs(m), s = m < 0 ? "−" : "+";
    if (a < 120) return s + a + " min";
    if (a < 2880) return s + (a / 60).toFixed(1).replace(/\.0$/, "") + " h";
    return s + (a / 1440).toFixed(1).replace(/\.0$/, "") + " days";
  }
  function tipCheckCard() {  // tip.check from the daily archive (orbit-2.17)
    var box = document.getElementById("tipcheck-body");
    if (!box) return;
    var c = (snap && snap.tip_check) || {};
    var objs = c.objects || [];
    if (!objs.length) {
      return empty(box, c.kept_since ? "No object with a TIP message has come down in the last " + c.days + " days." :
        "Not built yet: the check starts with the first run that keeps TIP messages in Orbit's archive.");
    }
    box.textContent = "";
    var byNorad = {};
    objs.forEach(function (x) { byNorad[x.norad] = x; });
    var parts = [c.with_after + (c.with_after === 1 ? " object has" : " objects have") + " TIP's message after the reentry; " +
      c.inside + " of them came down inside the last prediction's window"];
    if (c.with_after) parts.push("GCAT gives the same minute as that message for " + c.gcat_same_minute);
    if (c.no_after) parts.push(c.no_after + " without a message after the reentry yet (last prediction shown)");
    if (c.gcat_not_yet) parts.push(c.gcat_not_yet + " not dated by GCAT yet");
    var p = el("p", "small", parts.join("; ") + ". TIP messages kept since " + fmt(c.kept_since) + ".");
    box.appendChild(p);
    if ((c.gcat_day_or_more || []).length) {
      box.appendChild(el("p", "small", "GCAT's time differs from TIP's by a day or more for " + c.gcat_day_or_more.map(function (n) {
        var x = byNorad[n] || {};
        return (x.name || "object") + " (" + n + "): GCAT " + fmt((x.gcat || {}).time) + ", TIP " +
          fmt(((x.after || x.predicted) || {}).decay_epoch);
      }).join("; ") + ". Shown as each gives it; Orbit does not say which is right."));
    }
    var rows = objs.map(function (x) {
      var tr = el("tr"), pr = x.predicted || {}, af = x.after, g = x.gcat;
      cell(tr, af ? fmt(af.decay_epoch) : el("span", "muted", "no message after it yet"));
      var who = el("div");
      who.appendChild(objA(x.name || "Not in GCAT's index", x.norad));
      who.appendChild(el("div", "pl", String(x.norad)));
      cell(tr, who);
      var lp = el("div", "", pr.decay_epoch ? fmt(pr.decay_epoch) + " ±" + mins(pr.window_min || 0).slice(1) : "none kept");
      if (pr.msg_epoch) lp.appendChild(el("div", "pl", "issued " + fmt(pr.msg_epoch) + (x.lead_h != null ? ", " + x.lead_h +
        " h before the reentry" : "")));
      cell(tr, lp);
      cell(tr, x.offset_min == null ? "" : mins(x.offset_min) + (x.inside ? ", inside the window" : ", outside the window"));
      var gc;
      if (!g) gc = el("span", "muted", "not dated yet");
      else {
        gc = el("div", "", g.time ? fmt(g.time) : dayOnly(g.date));
        var d = g.minus_tip_min, note = [];
        if (g.uncertain) note.push("GCAT marks it uncertain");
        if (d != null) note.push(d === 0 ? "same minute as TIP" : mins(d) + " from TIP's " + (af ? "time after the reentry" : "last prediction"));
        if (note.length) gc.appendChild(el("div", "pl", note.join("; ")));
      }
      cell(tr, gc);
      return tr;
    });
    box.appendChild(table(["TIP after the reentry", "Object", "Last prediction", "Offset", "GCAT"], rows));
    fold(rows);
  }

  function catalogBody() {
    var box = document.getElementById("catalog-body");
    if (!box) return;
    box.textContent = "";
    var ch = snap.catalog_changes || {};
    if (ch.previous_reading_at) {
      box.appendChild(el("p", "small", "Since " + fmt(ch.previous_reading_at) + ": " + ch.added + " new entries (" +
        ch.added_late + " from launches over 30 days old), " + ch.removed + " removed, " + ch.changed + " changed."));
      var ul = el("ul", "plain small");
      (ch.late_groups || []).slice(0, 8).forEach(function (g) {
        ul.appendChild(el("li", "", g.count + " new from launch " + g.launch_tag + " (" + g.launch_date + ", " +
          g.states.join(", ") + "): "));
        var gl = ul.lastChild;
        g.objects.slice(0, 3).forEach(function (o, i) {
          if (i) gl.appendChild(document.createTextNode(", "));
          gl.appendChild(objA(o.name, o.norad, o.jcat));
        });
        if (g.count > 3) gl.appendChild(document.createTextNode("…"));
      });
      (ch.owner_changes || []).slice(0, 8).forEach(function (c) {
        var f = c.fields, parts = [];
        ["state", "owner"].forEach(function (k) { if (f[k]) parts.push(k + " " + (f[k][0] || "-") + " → " + (f[k][1] || "-")); });
        var cl = el("li");
        cl.appendChild(objA(c.name, c.norad, c.jcat));
        cl.appendChild(document.createTextNode(": " + parts.join(", ")));
        ul.appendChild(cl);
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
    if (!box) return;
    box.textContent = "";
    var names = { catalog: "GCAT catalog and launch list (J. McDowell)",
      counterspace: "Secure World Foundation, ASAT test history",
      rpo: "Secure World Foundation, RPO history",
      paths: "CelesTrak, last-30-days element sets (paths of new payloads on the globe)",
      sats: "CelesTrak, active group element sets, once a day (the satellite map's data, /data/sats.json)",
      maneuver: "Space-Track.org (USSPACECOM, 18th Space Defense Squadron)",
      decay: "Space-Track.org TIP reentry predictions (USSPACECOM, 18th Space Defense Squadron)" };
    var ul = el("ul", "plain small lanes");
    Object.keys(snap.lanes || {}).forEach(function (k) {
      var s = snap.lanes[k], srcs = sourcesOf(k);
      var li = el("li");
      var multi = srcs.length > 1;
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
        srcs.forEach(function (src) {
          var sh = el("div", "lane-head sub");
          var a2 = el("a", "", src.name); a2.href = src.url; a2.rel = "noopener"; sh.appendChild(a2);
          if (src.grade) {
            sh.appendChild(gradeBadge(src));
            sh.appendChild(el("span", "muted", src.reliability.toLowerCase() + " source; information " +
              src.credibility.toLowerCase()));
          }
          li.appendChild(sh);
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
    var asof = document.getElementById("asof"), meth = document.getElementById("method");
    if (asof) asof.textContent = "Built " + fmt(snap.generated_at) + ".";
    if (meth) meth.textContent = snap.method_version || "";
    tiles(); leadCard(); launchTable(); maneuverCard(); baselineCard(); archiveNote(); counterspaceCard(); rpoCard(); reentryTable(); breakupTable(); decayCard(); tipCheckCard(); catalogBody(); lanes();
    if (document.getElementById("map-card")) {
      startMap();
      viewControls();
      var tr = /[?&]track=(re-\d+)/.exec(location.search);
      if (tr && !render.tracked) { render.tracked = true; showReentry(tr[1]); }
    }
    // A link to a card or row: scroll to it again once tic-fold.js has folded the tables drawn above it.
    var t = location.hash && document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (t) requestAnimationFrame(function () { requestAnimationFrame(function () { t.scrollIntoView(); }); });
  }

  // A map drawn in a hidden group (a phone opened on another section) has no size: redraw it when its group shows.
  document.addEventListener("tic-tabs:show", function (e) {
    if (mapApi && mapApi.resize && e.target.contains(document.getElementById("map-card"))) mapApi.resize();
  });

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
    sources = sd; render();
  }).catch(function (e) {
    var box = document.getElementById("tiles") || document.querySelector("main");
    box.appendChild(el("p", "muted", "Could not load data/snapshot.json: " + e));
  });
})();
