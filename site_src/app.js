/* Orbit UI — renders snapshot.json */
(function () {
  "use strict";

  function render(snap) {
    var ms = snap.maneuvers || [];
    var cat = (snap.catalog && snap.catalog.objects) || [];
    var hyg = (snap.catalog && snap.catalog.hygiene_summary) || {};
    var gaps = snap.source_health_flags || [];

    var tiles = document.getElementById("tiles");
    if (tiles) {
      tiles.innerHTML = [
        '<div class="tile"><span class="k">Watched Objects</span><span class="v">' + cat.length + "</span></div>",
        '<div class="tile"><span class="k">Detected Maneuvers</span><span class="v">' + ms.length + "</span></div>",
        '<div class="tile"><span class="k">Unnumbered Active (GCAT)</span><span class="v">' + (hyg.unnumbered_active_count || 0) + "</span></div>",
        '<div class="tile"><span class="k">TLE Gaps (&ge;48 h)</span><span class="v">' + gaps.length + "</span></div>"
      ].join("");
    }

    var manEl = document.getElementById("maneuvers");
    if (manEl) {
      manEl.innerHTML = ms.map(function (m) {
        var isWarn = m.tier === "warning";
        return '<div class="row">' +
          '<div class="row-title"><strong>' + m.name + ' (NORAD ' + m.norad + ', ' + m.owner + ')</strong> ' +
            '<span class="badge ' + (isWarn ? "badge-warn" : "") + '">' + m.maneuver_type + ' · Δv ' + m.delta_v_ms + ' m/s (' + Math.round(m.calibrated_confidence * 100) + '% conf)</span>' +
          '</div>' +
          '<div class="small">' + m.summary + '</div>' +
        '</div>';
      }).join("");
    }

    var catEl = document.getElementById("catalog");
    if (catEl) {
      catEl.innerHTML = cat.map(function (o) {
        var sibNote = o.siblings && o.siblings.length ? " · Siblings: " + o.siblings.join(", ") : "";
        var subNote = o.is_subsatellite_deployment ? ' <span class="badge badge-warn">Subsatellite Release</span>' : "";
        return '<div class="row">' +
          '<div class="row-title"><strong>' + o.name + ' (' + o.jcat + ')</strong>' + subNote + '</div>' +
          '<div class="small muted">NORAD: ' + (o.norad || "Unnumbered") + ' · CelesTrak: ' + o.celestrak_owner + ' &rarr; GCAT: <strong>' + o.owner_clean + '</strong> · ' + o.orbit_class + sibNote + '</div>' +
        '</div>';
      }).join("");
    }

    var gapEl = document.getElementById("gaps");
    if (gapEl) {
      gapEl.innerHTML = gaps.length ? gaps.map(function (g) {
        return '<div class="row">' +
          '<div class="row-title"><strong>' + g.name + ' (NORAD ' + g.norad + ')</strong> <span class="badge badge-warn">' + g.max_tle_gap_hours + ' h gap</span></div>' +
          '<div class="small">' + g.summary + '</div>' +
        '</div>';
      }).join("") : '<p class="muted small">No watched satellites have TLE gaps &ge;48 h.</p>';
    }
  }

  fetch("data/snapshot.json")
    .then(function (r) { return r.json(); })
    .then(render)
    .catch(function () {});
})();
