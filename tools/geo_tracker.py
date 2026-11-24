#!/usr/bin/env python3
"""geo_tracker.py: where a drifting listed-role GEO satellite is, what lies ahead of it at the measured rate, and
where it is stopping once it brakes (ideas#248; method "GEO relocation tracker", orbit-2.27).

Arithmetic on the last public element sets, not a forecast. For every object with a listed role on the GEO page
(`site_src/geo_roles.json`) that the belt board classes as drifting:
  newest set   longitude, drift, height above or below GEO at the set's epoch, and its age at the build time; the
               position "now" is the newest set coasted at its own rate, marked extrapolated.
  departure    the last stop in Orbit's own sets (tools/geo_relocations.py rules) and its last held set; the start
               is estimated two ways, both assuming the object sped up uniformly from rest: from the first moving
               set's distance and rate (t = 2d / v) and, with two moving sets speeding up, from the change in rate
               (t = v / a). Both are clamped to the last held set; each says which sets it rests on.
  cases        "coast": the newest rate held. "speeding up": the rate change between the last two sets held until
               PEAK_CAP (4.5 deg a day, just above the fastest of Luch 2's eight moves, 4.42), then coasting; only
               with MIN_ACCEL_SETS (3) moving sets whose rates rise in turn. Neither includes braking (BRAKING_NOTE).
  passes       station-kept active objects ahead in the drift direction, grouped into slots SLOT_DEG (0.3) wide,
               to PASS_DAYS (45) at the coast rate and under one turn of the belt, at most MAX_PASSES; a date for
               each case. Slots the coast case has already passed by the build time are counted, not listed.
  stale        a newest set older than MAX_AGE_DAYS (3, Orbit's STALE_DAYS) gives no position now, no passes and no
               brake projection: the entry says how old the set is and nothing more.
  brake        from the fastest moving set on, a fall in |drift| of BRAKE_MIN against a set RATE_DT_DAYS earlier
               projects a stop (constant braking); a projection is shown only once steady (within 1 deg of the one
               before it) with the station-kept objects within STOP_NEAR_DEG of it. Luch 2's history: steady
               projections came 7.6-8.6 days before arrival on long moves, off by 0.5-4.6 deg, and later
               ones fell up to 2 deg short in a two-stage brake (2025).
  stops        the object's stop history in Orbit's sets, each with the nearest station-kept objects at the stop's
               departure (or now, for a current stop).
  track        for the page's chart (ideas#321): the sets from TRACK_LEAD_DAYS before the last held set (or the last
               TRACK_DAYS when Orbit holds no stop) to the newest, at most TRACK_MAX (thinned evenly, newest kept);
               none for a stale entry.
Standard library only; low-inclination longitudes (RAAN + argument of perigee + mean anomaly - GMST). Never says
why an object moves, where it is going, or how likely anything is.
"""
import os
import sys
from bisect import bisect_right
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)                               # the orbit package before tools/orbit.py
sys.path.append(os.path.join(ROOT, "tools"))
from orbit import maneuver as M  # noqa: E402
import geo_relocations as GR  # noqa: E402

PEAK_CAP = 4.5
MIN_ACCEL_SETS = 3
SLOT_DEG = 0.3
PASS_DAYS = 45.0
MAX_AGE_DAYS = M.STALE_DAYS
MAX_PASSES = 40
STOP_NEAR_DEG = 2.0
NEIGHBOURS = 3
TRACK_LEAD_DAYS = 7
TRACK_DAYS = 30
TRACK_MAX = 160
BRAKING_NOTE = ("Neither case includes braking. On Luch (Olymp) 2's three long moves (2023-2025) braking took "
                "10.2 to 11.8 days from full speed to the stop, so once an object brakes, dates further "
                "along come later than shown (docs/validation/luch2-relocations.md).")
NOTE = ("Arithmetic on the last public element sets, at the last measured rate: not a forecast, and no statement "
        "of where the object is going or why.")


def _t(s):
    return datetime.fromisoformat(str(s).rstrip("Z")[:19]).replace(tzinfo=timezone.utc)


def _iso(d):
    return d.strftime("%Y-%m-%dT%H:%MZ")


def _days(a, b):
    return (b - a).total_seconds() / 86400.0


def _set(r):
    """An element-file row (dict with epoch, n, e, i, raan, argp, M) as orbit/maneuver.py's set list."""
    return [M._iso(_t(r["epoch"])), float(r["n"]), float(r["e"]), float(r["i"]), float(r["raan"]),
            float(r["argp"]), float(r["M"]), ""]


def rows(elset_rows, now):
    """Positions (geo_relocations.positions' shape) from the GEO element files' rows before `now`. Rows sharing an
    epoch (a re-issued set) keep the later row, as orbit/maneuver.merge keeps the later-created set."""
    by_epoch = {}
    for r in elset_rows:
        s = _set(r)
        if _t(s[0]) < now:
            by_epoch[s[0]] = s
    out = []
    for e in sorted(by_epoch):
        s = by_epoch[e]
        g = M.geo_position(s)
        out.append({"t": s[0], "lon": g["lon"], "drift": g["drift_deg_day"],
                    "dh_km": round(M._a(s[1]) - GR.GEO_KM, 1), "i": s[3]})
    return out


def _ahead(lon0, lon, sign):
    """Degrees from lon0 to lon in the drift direction (0 to 360)."""
    return ((lon - lon0) * sign) % 360.0


def _travel_days(d, v, a, cap=PEAK_CAP):
    """Days to cover d deg starting at speed v (deg/day, > 0), speeding up at a (deg/day per day) to cap."""
    if not a or a <= 0:
        return d / v
    if v >= cap:
        return d / v
    t_cap = (cap - v) / a
    d_cap = v * t_cap + 0.5 * a * t_cap * t_cap
    if d <= d_cap:
        return (-v + (v * v + 2 * a * d) ** 0.5) / a
    return t_cap + (d - d_cap) / cap


def kept_positions(objs, skip=()):
    """[(lon, norad, name, owner)] of station-kept objects at their newest set's epoch, sorted by longitude."""
    out = []
    for o in objs:
        if o.get("class") != "station-kept" or o["norad"] in skip:
            continue
        g = M.geo_position(_set(o))
        out.append((g["lon"], o["norad"], o["name"], o.get("owner")))
    return sorted(out)


def _neighbours_at(lon, when, objs, elsets, skip, n=NEIGHBOURS):
    """The n station-kept objects nearest `lon` at `when`, each placed by its last set before `when`."""
    best = []
    for o in objs:
        if o.get("class") != "station-kept" or o["norad"] in skip:
            continue
        hist = sorted(elsets.get(o["norad"], []), key=lambda r: str(r["epoch"]))
        eps = [str(r["epoch"])[:19] for r in hist]
        k = bisect_right(eps, when.strftime("%Y-%m-%dT%H:%M:%S")) - 1
        if k < 0:
            continue
        s = _set(hist[k])
        if abs(M.geo_position(s)["drift_deg_day"]) >= GR.DRIFT_KEPT:
            continue
        d = abs(M._wrap180(M.geo_position(s)["lon"] - lon))
        best.append((round(d, 2), o["norad"], o["name"]))
    return [{"norad": b[1], "name": b[2], "deg": b[0]} for b in sorted(best)[:n]]


def steady_projection(moving):
    """Brake state of the moving sets: none, seen (not steady) or steady with its projection."""
    if len(moving) < 2:
        return {"state": "none"}
    k0 = max(range(len(moving)), key=lambda k: abs(moving[k]["drift"]))
    prev, seen = None, None
    for k in range(k0 + 1, len(moving)):
        q = moving[k]
        p = next((moving[j] for j in range(k - 1, -1, -1)
                  if _days(_t(moving[j]["t"]), _t(q["t"])) >= GR.RATE_DT_DAYS), None)
        if p is None:
            continue
        fall = abs(p["drift"]) - abs(q["drift"])
        if fall < GR.BRAKE_MIN or p["drift"] * q["drift"] <= 0:
            prev = None
            continue
        b = fall / _days(_t(p["t"]), _t(q["t"]))
        sign = 1 if q["drift"] > 0 else -1
        proj = round(M._wrap180(q["lon"] + sign * q["drift"] ** 2 / (2 * b)), 2)
        seen = {"state": "braking seen", "at": q["t"], "sets": k - k0 + 1}
        if prev is not None and abs(M._wrap180(proj - prev)) <= GR.NEAR_DEG:
            seen = {"state": "steady", "at": q["t"], "projected_lon": proj, "previous_lon": prev,
                    "sets": k - k0 + 1}
        prev = proj
    return seen or {"state": "none"}


def track(o, rws, objs, elsets, role, now):
    """The tracker entry for one drifting object, from its positions `rws`."""
    st = GR.stops(rws)
    last_stop = next((s for s in reversed(st) if _t(s["departure"]) < _t(rws[-1]["t"])), None)
    moving = [r for r in rws if last_stop is None or r["t"] > last_stop["departure"]]
    newest = rws[-1]
    t_new = _t(newest["t"])
    age_d = _days(t_new, now)
    v = newest["drift"]
    sign = 1 if v > 0 else -1
    lon_now = round(M._wrap180(newest["lon"] + v * age_d), 2)
    stale = age_d > MAX_AGE_DAYS
    out = {"norad": o["norad"], "name": o["name"], "owner": o.get("owner"), "role": role, "stale": stale,
           "newest": {"t": newest["t"], "lon": newest["lon"], "drift": v, "dh_km": newest["dh_km"],
                      "age_h": round(age_d * 24, 1)},
           "now": None if stale else {"at": _iso(now), "lon": lon_now, "extrapolated": True, "case": "coast"},
           "moving_sets": len(moving), "direction": "east" if v > 0 else "west", "note": NOTE,
           "braking_note": BRAKING_NOTE}
    seq = ([rws[rws.index(next(r for r in rws if r["t"] == last_stop["departure"]))]] if last_stop else []) + moving
    out["max_gap_h"] = round(max((_days(_t(p["t"]), _t(q["t"])) * 24 for p, q in zip(seq, seq[1:])), default=0), 1)
    if last_stop:
        held = _t(last_stop["departure"])
        dep = {"lon": last_stop["lon"], "last_held_set": last_stop["departure"],
               "gap_to_first_moving_h": round(_days(held, _t(moving[0]["t"])) * 24, 1) if moving else None}
        est = []
        m0 = moving[0] if moving else None
        if m0 and abs(m0["drift"]) > 0:
            d = abs(M._wrap180(m0["lon"] - last_stop["lon"]))
            t0 = max(held, _t(m0["t"]) - timedelta(days=2 * d / abs(m0["drift"])))
            est.append({"basis": "distance and rate of the first moving set", "sets": [m0["t"]], "t": _iso(t0)})
        if len(moving) >= 2 and abs(moving[1]["drift"]) > abs(moving[0]["drift"]):
            m1 = moving[1]
            a = (abs(m1["drift"]) - abs(m0["drift"])) / _days(_t(m0["t"]), _t(m1["t"]))
            t0 = max(held, _t(m0["t"]) - timedelta(days=abs(m0["drift"]) / a))
            est.append({"basis": "rate change between the first two moving sets", "sets": [m0["t"], m1["t"]],
                        "t": _iso(t0)})
        dep["estimated_start"] = est
        out["departure"] = dep
    accel = None
    if len(moving) >= MIN_ACCEL_SETS:
        r3 = [abs(r["drift"]) for r in moving[-MIN_ACCEL_SETS:]]
        if all(b > a for a, b in zip(r3, r3[1:])):
            p, q = moving[-2], moving[-1]
            accel = round((abs(q["drift"]) - abs(p["drift"])) / _days(_t(p["t"]), _t(q["t"])), 3)
    out["cases"] = ["coast"] + (["speeding up"] if accel else [])
    out["speeding_up"] = ({"rate_change": accel, "cap": PEAK_CAP, "sets": [r["t"] for r in moving[-MIN_ACCEL_SETS:]]}
                          if accel else {"shown": False, "why": f"needs {MIN_ACCEL_SETS} moving sets with rising "
                                         f"rates; {len(moving)} moving set(s)"})
    brake = {"state": "stale"} if stale else steady_projection(moving)
    if brake.get("state") == "steady":
        brake["near"] = [{"norad": k[1], "name": k[2], "owner": k[3],
                          "deg": round(abs(M._wrap180(k[0] - brake["projected_lon"])), 2)}
                         for k in kept_positions(objs, {o["norad"]})
                         if abs(M._wrap180(k[0] - brake["projected_lon"])) <= STOP_NEAR_DEG]
        brake["near"].sort(key=lambda x: x["deg"])
    out["brake"] = brake
    passes = []
    out["passes"], out["passes_more"], out["passed_since_newest"] = [], 0, 0
    if brake.get("state") not in ("steady", "stale"):
        for lon, norad, name, owner in kept_positions(objs, {o["norad"]}):
            d = _ahead(newest["lon"], lon, sign)
            if d / abs(v) > PASS_DAYS or d >= 360.0 - SLOT_DEG:
                continue
            passes.append((d, lon, norad, name, owner))
        passes.sort()
        slots = []
        for d, lon, norad, name, owner in passes:
            if slots and d - slots[-1]["d"] <= SLOT_DEG:
                slots[-1]["objects"].append({"norad": norad, "name": name, "owner": owner})
                continue
            slots.append({"d": d, "lon": lon, "objects": [{"norad": norad, "name": name, "owner": owner}]})
        rows_out, passed = [], 0
        for s in slots:
            if t_new + timedelta(days=s["d"] / abs(v)) < now:
                passed += 1
                continue
            if len(rows_out) == MAX_PASSES:
                out["passes_more"] += 1
                continue
            row = {"lon": s["lon"], "deg_ahead": round(s["d"], 2), "objects": s["objects"],
                   "coast": _iso(t_new + timedelta(days=s["d"] / abs(v)))}
            if accel:
                row["speeding_up"] = _iso(t_new + timedelta(days=_travel_days(s["d"], abs(v), accel)))
            rows_out.append(row)
        out["passes"], out["passed_since_newest"] = rows_out, passed
    hist = []
    for s in st:
        when = _t(s["departure"]) if s is not last_stop or moving else now
        hist.append({"lon": s["lon"], "arrival": s["arrival"], "departure": s["departure"], "days": s["days"],
                     "sets": s["sets"], "kind": s["kind"], "current": not moving and s is st[-1],
                     "neighbours": _neighbours_at(s["lon"], when, objs, elsets, {o["norad"]})})
    out["stops"] = hist
    if not stale:
        start = (_t(last_stop["departure"]) - timedelta(days=TRACK_LEAD_DAYS)) if last_stop else t_new - timedelta(days=TRACK_DAYS)
        pts = [[r["t"], round(r["lon"], 3)] for r in rws if _t(r["t"]) >= start]
        if len(pts) > TRACK_MAX:
            step = (len(pts) - 1) / (TRACK_MAX - 1)
            pts = [pts[round(k * step)] for k in range(TRACK_MAX)]
        out["track"] = {"from": _iso(start), "sets": pts}
    return out


def build(objs, elsets, roles, now):
    """Tracker entries for listed-role objects classed drifting. `objs` carry `class` (geo_belt.build sets it),
    `elsets` {norad: [element-file rows]}, `roles` {str(norad): role}."""
    out = []
    for o in objs:
        role = roles.get(str(o["norad"]))
        if not role or o.get("class") != "drifting":
            continue
        rws = rows(elsets.get(o["norad"], []), now)
        if not rws:
            continue
        out.append(track(o, rws, objs, elsets, role, now))
    return {"at_utc": _iso(now), "note": NOTE, "braking_note": BRAKING_NOTE,
            "rules": {"drift_kept": GR.DRIFT_KEPT, "max_age_days": MAX_AGE_DAYS, "peak_cap": PEAK_CAP, "min_accel_sets": MIN_ACCEL_SETS,
                      "slot_deg": SLOT_DEG, "pass_days": PASS_DAYS, "stop_near_deg": STOP_NEAR_DEG,
                      "brake_min": GR.BRAKE_MIN, "rate_dt_days": GR.RATE_DT_DAYS, "steady_deg": GR.NEAR_DEG},
            "movers": out, "attribution": M.ATTRIBUTION}
