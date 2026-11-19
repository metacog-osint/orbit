"""Orbit changes in watched objects' element sets (orbit-2.4, 14 Nov 2026). Replaces the 1 Nov seed engine, which
called any 0.35 m/s difference a manoeuvre (drag and fit noise exceed that in low orbit) and gave its confidence
from a formula.

The method, for each watched object, over its stored Space-Track element sets (GP and GP_HISTORY):
  1. One set per epoch: where Space-Track has re-issued an epoch, the later-created set is kept.
  2. For each pair of consecutive sets, the changes in semi-major axis (from mean motion), inclination, right
     ascension of the ascending node and eccentricity, less what the object's own steady drift would give over
     that interval (the median rate across its pairs: drag decay, nodal precession).
  3. Each change as a velocity: in-track from semi-major axis (v * da / 2a), cross-track from inclination and node
     (v * angle), eccentricity (v * de / 2).
  4. The object's own noise: for each of the three, the median and 1.4826 * median absolute deviation across all
     its pairs. A pair is marked when one of them is at least Z (8) of those deviations above the median AND the
     total is at least FLOOR_MS (0.05 m/s). At least MIN_PAIRS (10) pairs are needed before anything is marked.
     A change is reported only when its total is at least REPORT_MS for its regime: 0.25 m/s at GEO (Tom, 14 Nov
     2026, after the known case gave four 0.06-0.19 m/s marks on the dead BeiDou-2 G2), FLOOR_MS elsewhere.
  5. Marked pairs less than a day apart are one change, but only when they agree: the same dominant term
     (in-track, cross-track or eccentricity) and the same sign of semi-major-axis change as the change so far
     (orbit-2.6, Tom, 15 Nov 2026; before, SJ-21's lowering, raising, tow and return of 17-26 Jan 2022 read as one).
  6. In low orbit a change is listed only when it is mainly in-track, or when its cross-track or eccentricity
     total is LEO_OFF_TRACK_MS (1 m/s) or more; the rest are counted, not listed (orbit-2.8, Tom, 15 Nov 2026). On
     the ISS known case low-orbit cross-track noise is 0.32 m/s against 0.006 m/s in-track, and all nine marks
     NASA did not list were cross-track or eccentricity at 0.28-0.84 m/s.
  7. Each listed change also carries dv_sma_ms, the velocity the net semi-major-axis change alone gives
     (v * |da| / 2a, steady drift removed), beside the total, which adds the noisier cross-track and eccentricity
     terms.

What a mark means: the published orbit moved by more than this object's element sets usually move. Most such
marks are manoeuvres; a re-fit after a tracking gap, a mis-tagged set, or (in low orbit) a geomagnetic storm's
drag can give the same. Orbit says which object, when and how much; never why, and never a warning. The
thresholds are not yet calibrated against announced manoeuvres; `python tools/orbit.py maneuver-case` runs the
known case (Shijian-21 towing BeiDou-2 G2 to a graveyard orbit, January 2022).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from statistics import median

PUBLISH = True  # Tom approved the disclaimer, 14 Nov 2026 (doctrine/spacetrack-disclaimer.md); False holds the lane
ATTRIBUTION = ("Element sets: Space-Track.org, United States Space Command (USSPACECOM), 18th Space Defense Squadron, "
               "redistributed under USSPACECOM's blanket approval for basic SSA data. Orbit-change analysis: The "
               "Intelligence Company, not reviewed or endorsed by USSPACECOM. Not for operational use.")  # section 3

MU = 398600.4418  # km^3/s^2
RE = 6378.137     # km
SIDEREAL_REV_DAY = 1.0027379093
Z = 8.0
FLOOR_MS = 0.05
REPORT_MS = {"GEO": 0.25}  # smallest reported change by regime; FLOOR_MS where a regime is not listed
LEO_OFF_TRACK_MS = {"cross-track": 1.0, "eccentricity": 1.0}  # LEO: smallest listed change by dominant term (orbit-2.8)
IMPLAUSIBLE_FRAC = 1.0  # a pair needing more than the orbital speed itself is a fitting error, never published
MIN_PAIRS = 10
MERGE_DAYS = 1.0
MIN_RATE_DT = 0.1   # days: pairs closer than this do not set the steady-drift rate
WINDOW_DAYS = 30    # changes reported from the last 30 days
KEEP_DAYS = 120     # the analysis reads the sets of the last 120 days (view()); the store keeps every set
STALE_DAYS = 3      # no new set for this long is named: an untracked object looks exactly like a quiet one
GAP_LABEL_H = 48    # a change measured across a gap this long or longer is labelled: it happened somewhere inside it
J2000 = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
COMPONENTS = ("in-track", "cross-track", "eccentricity")


def _dt(s: str) -> datetime:
    s = s.strip().replace(" ", "T").rstrip("Z")
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm(rec: dict) -> list:
    """A Space-Track GP / GP_HISTORY record reduced to [epoch, mean motion, e, i, node, perigee arg, mean anomaly,
    created]."""
    return [_iso(_dt(rec["EPOCH"])), float(rec["MEAN_MOTION"]), float(rec["ECCENTRICITY"]), float(rec["INCLINATION"]),
            float(rec["RA_OF_ASC_NODE"]), float(rec["ARG_OF_PERICENTER"]), float(rec["MEAN_ANOMALY"]),
            str(rec.get("CREATION_DATE") or "")]


def merge(store: dict, records: list[dict], now: datetime, keep_days: int = KEEP_DAYS) -> dict:
    """Add Space-Track records to the store {norad: {name, object_id, country, decay, sets, view_from}}; one set
    per epoch (the later-created one). Every set is kept (retention rule, 18 Nov 2026: the store is copied to the
    private archive, tic-archive release orbit-state-YYYY-MM). Until 19 Nov 2026 sets older than keep_days were
    dropped here; now `view_from` records that cutoff and view() applies it, so the analysis reads exactly what
    it read before."""
    cutoff = _iso(now - timedelta(days=keep_days))
    for rec in records:
        key = str(int(rec["NORAD_CAT_ID"]))
        obj = store.setdefault(key, {"sets": []})
        obj.update({"name": rec.get("OBJECT_NAME"), "object_id": rec.get("OBJECT_ID"),
                    "country": rec.get("COUNTRY_CODE"), "decay": rec.get("DECAY_DATE")})
        row = norm(rec)
        by_epoch = {s[0]: s for s in obj["sets"]}
        old = by_epoch.get(row[0])
        if old is None or row[7] >= old[7]:
            by_epoch[row[0]] = row
        obj["sets"] = sorted(by_epoch.values(), key=lambda s: s[0])
        obj["view_from"] = cutoff
    return store


def view(obj: dict) -> list:
    """The sets the analysis reads: those from `view_from` (keep_days before the last merge that touched the
    object), as the store held them when merge() still dropped older sets. A store written before 19 Nov 2026 has
    no view_from and was already cut, so all its sets are read."""
    sets = obj.get("sets") or []
    cut = obj.get("view_from")
    return [s for s in sets if s[0] >= cut] if cut else sets


def _a(n_rev_day: float) -> float:
    n = n_rev_day * 2 * math.pi / 86400.0
    return (MU / n ** 2) ** (1 / 3)


def _gmst_deg(t: datetime) -> float:
    d = (t - J2000).total_seconds() / 86400.0
    return (280.46061837 + 360.98564736629 * d) % 360.0


def _wrap180(x: float) -> float:
    return (x + 180.0) % 360.0 - 180.0


def regime(n: float, e: float) -> str:
    a = _a(n)
    if e > 0.25:
        return "HEO"
    if a * (1 + e) - RE < 2000:
        return "LEO"
    if 0.9 < n < 1.1 and e < 0.05:
        return "GEO"
    return "MEO"


def geo_position(s: list) -> dict:
    """Sub-satellite longitude (east +) at the set's epoch and drift in degrees a day (east +), near-circular
    geosynchronous orbits only."""
    t = _dt(s[0])
    lon = _wrap180(s[4] + s[5] + s[6] - _gmst_deg(t))
    return {"lon": round(lon, 2), "drift_deg_day": round((s[1] - SIDEREAL_REV_DAY) * 360.0, 3)}


def _pairs(sets: list) -> list[dict]:
    out = []
    for p, q in zip(sets, sets[1:]):
        dt = (_dt(q[0]) - _dt(p[0])).total_seconds() / 86400.0
        if dt <= 0:
            continue
        a0, a1 = _a(p[1]), _a(q[1])
        out.append({"from": p[0], "to": q[0], "dt": dt, "a": (a0 + a1) / 2, "i": (p[3] + q[3]) / 2,
                    "da": a1 - a0, "di": q[3] - p[3], "dnode": _wrap180(q[4] - p[4]), "de": q[2] - p[2],
                    "p": p, "q": q})
    return out


def _robust(xs: list[float]) -> tuple[float, float]:
    m = median(xs)
    return m, 1.4826 * median(abs(x - m) for x in xs)


def _dominant(g: list[dict]) -> str:
    dv = {c: sum(p["dv"][c] for p in g) for c in COMPONENTS}
    return max(dv, key=dv.get)


def _agrees(g: list[dict], p: dict) -> bool:
    """A marked pair joins the change before it only with the same dominant term and the same sign of
    semi-major-axis change (a zero change agrees with either sign)."""
    da_g, da_p = sum(q["da"] for q in g), p["da"]
    return _dominant(g) == _dominant([p]) and da_g * da_p >= 0


def detect(obj: dict, now: datetime, window_days: int = WINDOW_DAYS) -> dict:
    sets = view(obj)
    out = {"sets": len(sets), "events": [], "regime": None, "last_epoch": sets[-1][0] if sets else None,
           "max_gap_h": None, "note": None}
    if not sets:
        out["note"] = "no element sets"
        return out
    last = sets[-1]
    out["regime"] = reg = regime(last[1], last[2])
    if reg == "GEO":
        out["geo"] = geo_position(last)
    age = (now - _dt(last[0])).total_seconds() / 86400.0
    if age > STALE_DAYS:
        out["note"] = f"no new element set for {age:.1f} days"
    pairs = _pairs(sets)
    if pairs:
        out["max_gap_h"] = round(max(p["dt"] for p in pairs) * 24, 1)
    if len(pairs) < MIN_PAIRS:
        out["note"] = out["note"] or f"baseline too short ({len(pairs)} pairs of {MIN_PAIRS})"
        return out
    rated = [p for p in pairs if p["dt"] >= MIN_RATE_DT] or pairs
    rate = {k: median(p[k] / p["dt"] for p in rated) for k in ("da", "di", "dnode", "de")}
    for p in pairs:
        v = math.sqrt(MU / p["a"]) * 1000.0  # m/s
        ja = p["da"] - rate["da"] * p["dt"]
        ji = math.radians(p["di"] - rate["di"] * p["dt"])
        # Wrap the residual, not only the raw change: over a long gap the expected precession passes 180 degrees
        # and an unwrapped residual is off by 360 (a 28.5 deg orbit, 30-day gap, gave 22,902 m/s cross-track).
        jn = math.radians(_wrap180(p["dnode"] - rate["dnode"] * p["dt"])) * math.sin(math.radians(p["i"]))
        je = p["de"] - rate["de"] * p["dt"]
        p["ja"], p["v"] = ja, v
        p["dv"] = {"in-track": abs(v * ja / (2 * p["a"])), "cross-track": v * math.hypot(ji, jn),
                   "eccentricity": abs(v * je / 2)}
        p["total"] = math.sqrt(sum(x * x for x in p["dv"].values()))
    base = {c: _robust([p["dv"][c] for p in pairs]) for c in COMPONENTS}
    out["noise_ms"] = {c: round(base[c][1], 4) for c in COMPONENTS}
    cutoff = _iso(now - timedelta(days=window_days))
    out["implausible"] = 0
    marked = []
    for p in pairs:
        z = {c: (p["dv"][c] - base[c][0]) / max(base[c][1], 1e-6) for c in COMPONENTS}
        p["z"] = z
        if p["total"] > p["v"] * IMPLAUSIBLE_FRAC:
            if p["to"] >= cutoff:
                out["implausible"] += 1  # counted, never listed: no burn changes velocity by the orbital speed
            continue
        if max(z.values()) >= Z and p["total"] >= FLOOR_MS and p["to"] >= cutoff:
            marked.append(p)
    groups: list[list[dict]] = []
    for p in marked:
        if groups and (_dt(p["from"]) - _dt(groups[-1][-1]["to"])).total_seconds() / 86400.0 < MERGE_DAYS                 and _agrees(groups[-1], p):
            groups[-1].append(p)
        else:
            groups.append([p])
    out["below_report"] = 0
    out["leo_off_track"] = 0
    for g in groups:
        total = sum(p["total"] for p in g)
        if total < REPORT_MS.get(reg, FLOOR_MS):
            out["below_report"] += 1  # counted, not listed
            continue
        dv = {c: sum(p["dv"][c] for p in g) for c in COMPONENTS}
        dominant = max(dv, key=dv.get)
        if reg == "LEO" and total < LEO_OFF_TRACK_MS.get(dominant, 0.0):
            out["leo_off_track"] += 1  # counted, not listed: low-orbit cross-track and eccentricity noise
            continue
        a = sum(p["a"] for p in g) / len(g)
        ev = {"from": g[0]["from"], "to": g[-1]["to"], "dv_ms": round(total, 3),
              "dv_sma_ms": round(g[0]["v"] * abs(sum(p["ja"] for p in g)) / (2 * a), 3),
              "dominant": dominant, "da_km": round(sum(p["da"] for p in g), 2),
              "di_deg": round(sum(p["di"] for p in g), 4), "z": round(max(max(p["z"].values()) for p in g), 1),
              "pairs": len(g)}
        gap = max(g, key=lambda p: p["dt"])  # the widest pair: the change can sit anywhere inside it
        ev["longest_gap_h"] = round(gap["dt"] * 24, 1)
        if ev["longest_gap_h"] >= GAP_LABEL_H:
            ev["gap"] = {"from": gap["from"], "to": gap["to"], "hours": ev["longest_gap_h"]}
        if reg == "GEO":
            b, a = geo_position(g[0]["p"]), geo_position(g[-1]["q"])
            ev["geo"] = {"lon_before": b["lon"], "lon_after": a["lon"], "drift_before": b["drift_deg_day"],
                         "drift_after": a["drift_deg_day"]}
        out["events"].append(ev)
    return out


def score(events: list[dict], announced: list[dict], tolerance_h: float = 12.0, storm: dict | None = None) -> dict:
    """Listed changes against announced manoeuvres. A change (somewhere between its first and last element set)
    hits an announced one when the two spans come within tolerance_h hours. Changes that hit nothing are extra;
    those inside the storm span are named apart (drag, not a manoeuvre)."""
    tol = timedelta(hours=tolerance_h)

    def near(e, a):
        return _dt(e["from"]) - tol <= _dt(a["to"]) and _dt(e["to"]) + tol >= _dt(a["from"])

    out = [{**a, "events": [e for e in events if near(e, a)]} for a in announced]
    used = {id(e) for h in out for e in h["events"]}
    extra = sorted((e for e in events if id(e) not in used), key=lambda e: e["from"])
    in_storm = [e for e in extra if storm and _dt(e["from"]) <= _dt(storm["to"]) and _dt(e["to"]) >= _dt(storm["from"])]
    hits = sum(1 for h in out if h["events"])
    return {"announced": out, "hits": hits, "misses": len(out) - hits, "extra": extra, "in_storm": in_storm}


def report(store: dict, now: datetime, window_days: int = WINDOW_DAYS) -> dict:
    objs = []
    for key, obj in sorted(store.items(), key=lambda kv: int(kv[0])):
        d = detect(obj, now, window_days)
        objs.append({"norad": int(key), "name": obj.get("name"), "object_id": obj.get("object_id"),
                     "country": obj.get("country"), "decay": obj.get("decay"), **d})
    events = sorted(({"norad": o["norad"], "name": o["name"], "object_id": o["object_id"], "country": o["country"],
                      "regime": o["regime"], **e} for o in objs for e in o["events"]),
                    key=lambda e: e["to"], reverse=True)
    return {"objects": objs, "events": events, "window_days": window_days,
            "thresholds": {"z": Z, "floor_ms": FLOOR_MS, "report_ms": REPORT_MS, "leo_off_track_ms": LEO_OFF_TRACK_MS,
                           "min_pairs": MIN_PAIRS, "merge_days": MERGE_DAYS}}
