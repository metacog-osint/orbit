/* Object search (orbit-2.20): name from any source, NORAD number, COSPAR ID or GCAT's JCAT id. Reads the TIC
   satellite catalog's search index (data/catalog/search.json, about 84,000 objects, about 1.1 MB compressed) on the
   first keystroke, never with the page. Each result links to that object's page. No inline scripts (CSP). */
(function () {
  "use strict";
  var index = null, loading = null;

  function norm(s) { return String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim(); }
  /* As orbit/namepos.py's compact(): no spaces, "west"/"east" as "w"/"e", so "12WG" finds "Eutelsat 12 West G"
     (ideas#359). Used only when the plain match finds nothing better. */
  function compact(s) {
    return norm(s).split(" ").map(function (w) { return w === "west" ? "w" : w === "east" ? "e" : w; }).join("");
  }
  function load() {
    if (index) return Promise.resolve(index);
    if (loading) return loading;
    loading = fetch("data/catalog/search.json", { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (d) {
      var c = d.columns || [], at = {};
      c.forEach(function (k, i) { at[k] = i; });
      var now = d.now_names || {};
      index = { types: d.types || {}, read: d.read, rows: (d.objects || []).map(function (r) {
        var others = r[at.other_names] || [];
        return { key: String(r[at.key]), name: r[at.name] || "", now: now[String(r[at.key])] || "", others: others, cospar: r[at.cospar] || "",
          type: r[at.type], gone: !!r[at.gone], n: norm(r[at.name]), o: others.map(norm),
          c: [compact(r[at.name])].concat(others.map(compact)) };
      }) };
      return index;
    });
    loading.catch(function () { loading = null; });
    return loading;
  }
  function href(key) { return "object.html?" + (/^\d+$/.test(key) ? "n=" : "j=") + encodeURIComponent(key); }
  /* A GEO slot ("12.5W", "12.5° W", "12 West", "36E", "-12.5"), as orbit/namepos.py's parse_slot (ideas#366). Slot
     queries go to the GEO page: positions and the "held it" record live in its data, with its time control, and the
     name rules stay in one place (the build), so this page loads nothing for them. */
  function slotOf(q) {
    var m = /^\s*(\d{1,3}(?:\.\d+)?)\s*(?:°|º|deg(?:rees?)?)?\s*(w|west|e|east)\s*$/i.exec(q || ""), lon;
    if (m) lon = (m[2].charAt(0).toLowerCase() === "w" ? -1 : 1) * Number(m[1]);
    else { m = /^\s*([+-]\s*\d{1,3}(?:\.\d+)?)\s*(?:°|º)?\s*$/.exec(q || ""); if (!m) return null; lon = Number(m[1].replace(/\s/g, "")); }
    if (Math.abs(lon) > 180) return null;
    return lon === -180 ? 180 : lon + 0;
  }
  function geoHref(q) { return "geo.html#g=" + encodeURIComponent("q:" + q.trim().replace(/;/g, " ")); }

  /* Ranked matches: exact number or JCAT id, then COSPAR ID (a whole launch for "1998-067"), then names: exact,
     starting with, a word starting with, containing; payloads before other objects, in orbit before reentered. */
  function find(q, limit) {
    var rows = index.rows, out = [], s = q.trim();
    if (!s) return { hits: [], total: 0 };
    var up = s.toUpperCase();
    if (/^\d{1,6}$/.test(s)) {
      var k = String(parseInt(s, 10));
      rows.forEach(function (r) { if (r.key === k) out.push([0, r]); });
    }
    if (/^[A-Z]\d{1,6}$/.test(up)) rows.forEach(function (r) { if (r.key.toUpperCase() === up) out.push([0, r]); });
    if (/^\d{4}-\d{3}/.test(s)) {
      var launch = /^\d{4}-\d{3}$/.test(up);  // a whole launch: its pieces in letter order, numbered ones first
      rows.forEach(function (r) {
        var c = r.cospar.toUpperCase();
        if (c === up && !launch) out.push([1, r]); else if (c.indexOf(up) === 0) out.push([2, r]);
      });
    }
    var n = norm(s), cn = compact(s);
    if (n.length >= 2 && !/^\d+$/.test(n)) {
      rows.forEach(function (r) {
        var best = 9;
        [r.n].concat(r.o).forEach(function (x, i) {
          var sc = x === n ? 3 : x.indexOf(n) === 0 ? 4 : (" " + x).indexOf(" " + n) >= 0 ? 5 : x.indexOf(n) >= 0 ? 6 :
            cn.length >= 3 && r.c[i].indexOf(cn) >= 0 ? 7 : 9;
          if (i && sc < 9) sc += 0.5;  // the display name before other names
          if (sc < best) best = sc;
        });
        if (best < 9) out.push([best, r]);
      });
    }
    var seen = {};
    out = out.filter(function (h) { if (seen[h[1].key]) return false; seen[h[1].key] = 1; return true; });
    var num = function (r) { return /^\d+$/.test(r.key) ? 0 : 1; };
    out.sort(function (a, b) {
      if (a[0] === b[0] && a[0] <= 2) {
        return num(a[1]) - num(b[1]) || a[1].cospar.length - b[1].cospar.length || (a[1].cospar < b[1].cospar ? -1 : a[1].cospar > b[1].cospar ? 1 : 0);
      }
      return a[0] - b[0] || (a[1].type === "p" ? 0 : 1) - (b[1].type === "p" ? 0 : 1) ||
        (a[1].gone ? 1 : 0) - (b[1].gone ? 1 : 0) || a[1].name.localeCompare(b[1].name);
    });
    return { hits: out.slice(0, limit || 20).map(function (h) { return h[1]; }), total: out.length };
  }

  function attach(form) {
    var input = form.querySelector("input"), list = form.querySelector(".search-results"), timer = null, last = "";
    if (!input || !list) return;
    function el(tag, cls, text) {
      var e = document.createElement(tag);
      if (cls) e.className = cls;
      if (text != null) e.textContent = text;
      return e;
    }
    function show(q) {
      list.textContent = "";
      if (!q.trim()) { list.hidden = true; return; }
      list.hidden = false;
      var slot = slotOf(q);
      if (slot != null) {
        var li = el("li"), a = el("a", "", "See who is at " + Math.abs(slot) + "° " + (slot < 0 ? "W" : "E") + " on the GEO page");
        a.href = geoHref(q);
        li.appendChild(a);
        li.appendChild(el("span", "pl", "“" + q.trim() + "” reads as a GEO slot: the GEO page lists the objects there now, those named for it and those that held it."));
        list.appendChild(li);
        return;
      }
      if (!index) { list.appendChild(el("li", "muted", "Loading the catalog's search index (about 1 MB, once)…")); }
      load().then(function () {
        if (input.value !== q) return;
        list.textContent = "";
        var r = find(q, 20);
        if (!r.total) { list.appendChild(el("li", "muted", "No object in the TIC catalog matches “" + q.trim() + "”.")); return; }
        r.hits.forEach(function (o) {
          var li = el("li"), a = el("a", "", o.name || o.key);
          a.href = href(o.key);
          li.appendChild(a);
          if (o.now) li.appendChild(el("span", "muted", " now " + o.now));  // declared current name (ideas#379)
          var qn = norm(q), qc = compact(q);
          var hit = function (x) { return norm(x).indexOf(qn) >= 0 || (qc.length >= 3 && compact(x).indexOf(qc) >= 0); };
          var others = o.others.filter(function (x) { return norm(x) !== o.n; });
          others = others.filter(hit).concat(others.filter(function (x) { return !hit(x); }));  // the name that matched first
          var bits = [(/^\d+$/.test(o.key) ? "NORAD " : "GCAT ") + o.key, o.cospar, index.types[o.type] || "",
            o.gone ? "reentered" : ""].filter(Boolean);
          li.appendChild(el("span", "pl", bits.join(" · ") + (others.length ? " · also " + others.slice(0, 2).join(", ") : "")));
          list.appendChild(li);
        });
        if (r.total > r.hits.length) list.appendChild(el("li", "muted small", r.total.toLocaleString() + " matches; the first " +
          r.hits.length + " shown. Add to the search to narrow it."));
      }).catch(function (e) {
        list.textContent = "";
        list.appendChild(el("li", "muted", "The catalog's search index is not on the site yet (" + e.message + ")."));
      });
    }
    input.addEventListener("input", function () {
      clearTimeout(timer);
      var q = input.value;
      timer = setTimeout(function () { if (q !== last) { last = q; show(q); } }, 150);
    });
    input.addEventListener("focus", function () { load().catch(function () {}); });
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var q = input.value;
      if (slotOf(q) != null) { location.href = geoHref(q); return; }
      load().then(function () {
        var r = find(q, 1);
        if (r.hits.length) location.href = href(r.hits[0].key); else show(q);
      }).catch(function () { show(q); });
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") { list.hidden = true; }
    });
    // ?q= opens the page with that search run, so other programs can link to it: Launch links a launch's COSPAR
    // launch id ("2026-266"), which lists every piece of that launch.
    var asked = queryOf(location.search);
    if (asked) { input.value = asked; last = asked; show(asked); }
  }
  function queryOf(search) {
    var m = /[?&]q=([^&]*)/.exec(search || "");
    if (!m) return "";
    var q;
    try { q = decodeURIComponent(m[1].replace(/\+/g, " ")); } catch (e) { return ""; }
    return q.trim().slice(0, 80);
  }

  window.OrbitSearch = { attach: attach, load: load, find: find, href: href, slotOf: slotOf, queryOf: queryOf };
  document.querySelectorAll("form.obj-search").forEach(attach);
})();
