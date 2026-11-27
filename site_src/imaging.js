/* Orbit imaging page (orbit-2.52): reads data/imaging.json and draws two tables. Times are stored UTC and shown in
   the viewer's zone through tic-time.js; Landsat due days are UTC days. No inline scripts (CSP). */
(function () {
  "use strict";
  var T = window.TicTime;
  var doc = null;

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }
  function when(iso) {
    if (!iso) return "";
    return T ? T.format(iso, { year: true }) : iso.slice(0, 16).replace("T", " ") + "Z";
  }
  function day(isoDate) {
    var p = isoDate.split("-"), m = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return Number(p[2]) + " " + m[Number(p[1]) - 1] + " " + p[0];
  }
  function table(head, rows) {
    var t = el("table"), th = el("thead"), tr = el("tr");
    head.forEach(function (h) { tr.appendChild(el("th", "", h)); });
    th.appendChild(tr); t.appendChild(th);
    t.setAttribute("data-tic-fold", "10 20");
    var tb = el("tbody");
    rows.forEach(function (cells) {
      var r = el("tr");
      cells.forEach(function (c, i) {
        var td = el("td");
        td.setAttribute("data-label", head[i]);
        if (c && c.nodeType) td.appendChild(c); else td.textContent = c === null || c === undefined ? "" : c;
        r.appendChild(td);
      });
      tb.appendChild(r);
    });
    t.appendChild(tb);
    return t;
  }
  function scene(entry, kind) {
    var s = entry && entry.last_acquired;
    var box = el("span");
    if (!s) { box.textContent = "none listed in " + doc.lookback_days + " days"; return box; }
    box.appendChild(el("span", "", when(s.datetime)));
    var bits = [String(s.platform || "").replace(/^sentinel-(\d)([a-z])$/, function (m, n, l) { return "Sentinel-" + n + l.toUpperCase(); }).replace(/^LANDSAT_/, "Landsat ")];
    if (kind === "sar") {
      if (s.mode) bits.push(s.mode);
      if (s.orbit_state) bits.push(s.orbit_state);
    } else {
      if (typeof s.cloud_cover === "number") bits.push("cloud " + Math.round(s.cloud_cover) + "%");
      if (typeof s.sun_elevation === "number" && s.sun_elevation <= 0) bits.push("night");
    }
    box.appendChild(el("br"));
    box.appendChild(el("span", "muted small", bits.join(", ")));
    return box;
  }
  function place(p) {
    var b = el("span");
    b.appendChild(el("span", "", p.name));
    b.appendChild(el("br"));
    b.appendChild(el("span", "muted small", (p.country || "") + " " + p.lat.toFixed(2) + ", " + p.lon.toFixed(2)));
    return b;
  }
  function due(n) {
    if (!n) return "unknown";
    if (n.status === "unknown") return "unknown (" + n.why + ")";
    if (!n.due || !n.due.length) return "not on the calendar in the next " + doc.ahead_days + " days";
    return n.due.map(function (d) { return day(d.date) + ", " + d.platform + " path " + d.wrs_path; }).join("; ");
  }
  function draw() {
    if (!doc) return;
    $("im-asof").textContent = "Read " + when(doc.read_at) + ".";
    $("im-cal").textContent = doc.calendar ? day(doc.calendar.published_through) : "an unknown date";
    $("im-s-plan").textContent = doc.sentinel_plan || "";
    $("im-year").textContent = (doc.read_at || "").slice(0, 4);
    var ps = doc.places || [];
    var last = $("im-last"), next = $("im-next");
    last.textContent = ""; next.textContent = "";
    last.appendChild(table(["Place", "Landsat 8/9", "Sentinel-2", "Sentinel-1"], ps.map(function (p) {
      return [place(p), scene(p.landsat, "optical"), scene(p.sentinel2, "optical"), scene(p.sentinel1, "sar")];
    })));
    next.appendChild(table(["Place", "Landsat due (UTC days)"], ps.map(function (p) {
      return [place(p), due(p.landsat && p.landsat.next)];
    })));
  }
  if (T && T.mountSettings) T.mountSettings($("time-settings"));
  if (T && T.onChange) T.onChange(draw);
  fetch("data/imaging.json", { cache: "no-cache" }).then(function (r) {
    if (!r.ok || (r.headers.get("content-type") || "").indexOf("json") < 0) throw new Error("not on the site yet");
    return r.json();
  }).then(function (d) { doc = d; draw(); }).catch(function () {
    $("im-last").textContent = "The imaging file is not on the site yet. It is written once a UTC day by Orbit's update run.";
  });
})();
