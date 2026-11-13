/* Orbit page: reads data/snapshot.json and draws it. Times are stored UTC and shown in the viewer's zone
   through tic-time.js. No inline scripts (the site's CSP allows scripts from this origin only). */
(function () {
  "use strict";
  var T = window.TicTime;
  var snap = null;

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
    rows.forEach(function (r) { tb.appendChild(r); });
    t.appendChild(tb);
    return t;
  }
  function cell(tr, content, cls) {
    var td = el("td", cls || "");
    if (content instanceof Node) td.appendChild(content); else td.textContent = content == null ? "" : content;
    tr.appendChild(td);
    return td;
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
    [["Orbital launches, 7 days", launches.length],
     ["Scheduled, next 14 days", (snap.upcoming || []).length],
     ["Payload reentries, 7 days", reentries.length],
     ["Objects in orbit (GCAT)", h.in_orbit ? h.in_orbit.toLocaleString() : "–"]].forEach(function (t) {
      var d = el("div", "tile");
      d.appendChild(el("span", "k", t[0]));
      d.appendChild(el("span", "v", String(t[1])));
      box.appendChild(d);
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
      cell(tr, fmt(x.net) + (x.net_precision && x.net_precision !== "Minute" && x.net_precision !== "Second" ? " (" + x.net_precision.toLowerCase() + ")" : ""));
      cell(tr, x.name);
      cell(tr, who((x.provider_countries || []).map(function (c) { return mark(c, null); }), x.provider || ""));
      cell(tr, x.orbit || "");
      cell(tr, who(x.pad_country ? [mark(x.pad_country, null)] : [], x.location || x.pad));
      cell(tr, el("span", "badge", x.status));
      return tr;
    });
    if (!rows.length) return empty(box, "No launches listed for the next 14 days.");
    box.textContent = "";
    box.appendChild(table(["No earlier than", "Launch", "Provider", "Orbit", "Site", "Status"], rows));
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

  function lanes() {
    var box = document.getElementById("lanes");
    box.textContent = "";
    var names = { catalog: "GCAT catalog and launch list (J. McDowell)", upcoming: "Launch Library 2 (The Space Devs)" };
    var ul = el("ul", "plain small");
    Object.keys(snap.lanes || {}).forEach(function (k) {
      var s = snap.lanes[k];
      var when = s.fetched_at ? "read " + fmt(s.fetched_at) : "never read";
      var txt = (names[k] || k) + ": " + s.status + (s.from_previous ? " (showing the last good copy)" : "") +
        "; " + when + (s.checked_at ? ", checked " + fmt(s.checked_at) : "");
      if (s.status === "failed" && s.error) txt += ". Error: " + s.error;
      ul.appendChild(el("li", s.status === "failed" ? "" : "", txt));
    });
    var g = snap.gcat_updated || {};
    if (g.satcat) ul.appendChild(el("li", "muted", "GCAT tables stamped " + g.satcat + " UTC (GCAT's own update time)."));
    box.appendChild(ul);
  }

  function render() {
    if (!snap) return;
    tiles(); launchTable(); upcomingTable(); reentryTable(); catalogBody(); lanes();
    if (location.hash) { var t = document.getElementById(location.hash.slice(1)); if (t) t.scrollIntoView(); }
  }

  if (T && T.mountSettings) T.mountSettings(document.getElementById("time-settings"));
  if (T && T.onChange) T.onChange(render);
  fetch("data/snapshot.json", { cache: "no-cache" }).then(function (r) { return r.json(); }).then(function (d) {
    snap = d; render();
  }).catch(function (e) {
    document.getElementById("tiles").textContent = "Could not load data/snapshot.json: " + e;
  });
})();
