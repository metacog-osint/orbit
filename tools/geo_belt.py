#!/usr/bin/env python3
"""geo_belt.py: the GEO page's belt board (globe.json "belt"): every active object's class, today's close pairs of
different owners, the last week's orbit changes across the whole belt, and the drifting objects.

Moved from Noisefloor's CelesTrak board (tools/geo.py, d751b4c) in step 5 of doctrine/geo-move-plan.md (Tom, 18 Nov
2026, "Port to Orbit first"), so nothing the board showed is lost when Noisefloor's copy retires. Called by
tools/geo_page.py build; no request to Space-Track or CelesTrak.

Scope: the objects CelesTrak lists in its active GEO group (the day file's `active`, read in the same geo.yml run),
as Noisefloor's board, with Orbit's own Space-Track element sets.
  class     drifting when |drift| is DRIFT_KEPT (0.1 deg a day) or more; otherwise station-kept below INC_KEPT (1 deg)
            of inclination, inclined at or above it. Drift is mean motion x 360 less 360.9856 deg a day.
  close     pairs of different owner codes within CLOSE_KM (100 km) of each other at the build time, each placed by
            SGP4 from its newest set. Pairs of one owner code are counted, not listed (owner codes are often a
            country, and operators co-locate their own satellites on purpose), unless one of the two has a listed role.
  changes   Orbit's rule (orbit/maneuver.py: 8 robust deviations of the object's own noise, 0.25 m/s floor at GEO,
            10 pairs minimum), the rule Tom chose over Noisefloor's C5 on 17 Nov 2026, run on every set held for each
            object; changes ending in the last CHANGE_DAYS (7). Noisefloor's board compared daily CelesTrak snapshots
            with fixed thresholds (drift 0.02 deg a day, inclination 0.02 deg, longitude 0.15 deg). Each change gets
            Noisefloor's kind from the drift and inclination of the sets on either side: routine station-keeping
            when the object holds its longitude before and after (unless the inclination of an inclined orbit moved
            by INC_CHANGE or more), otherwise started drifting, stopped drifting or drift rate changed.
Proximity and orbit changes only, never intent.
"""
import math
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIDEREAL = 360.98564736629        # deg a day, Earth's rotation
DRIFT_KEPT, INC_KEPT = 0.1, 1.0   # deg a day, deg (Noisefloor's board)
INC_CHANGE = 0.02                 # deg: Noisefloor's board's inclination change
CLOSE_KM = 100.0
NEAR_LON = 1.0                    # deg: pairs further apart than this in longitude are not measured (over 700 km)
CHANGE_DAYS = 7
ROUTINE = "station-keeping"
MAX_ROUTINE = 300                 # routine station-keeping kept on the page (the newest), as Noisefloor's board
MAX_CLOSE, MAX_DRIFT = 40, 40


def drift(n):
    return n * 360.0 - SIDEREAL


def classify(d, i):
    if abs(d) >= DRIFT_KEPT:
        return "drifting"
    return "station-kept" if i < INC_KEPT else "inclined"


def pair_kind(ra, rb):
    """What a close pair is, as far as the listed roles say."""
    roles = {ra, rb} - {None, ""}
    if "servicing" in roles:
        return "servicing involved"
    if "inspection" in roles:
        return "inspection-capable involved"
    return "no listed role (often slot-sharing)"


def change_kind(before, after):
    """Noisefloor's words for a change: routine station-keeping, or the rarer kind. `before` and `after` are
    {"drift", "i"} of the sets on either side."""
    kept_b, kept_a = abs(before["drift"]) < DRIFT_KEPT, abs(after["drift"]) < DRIFT_KEPT
    if kept_b and kept_a:
        inclined = before["i"] >= INC_KEPT or after["i"] >= INC_KEPT
        return "inclined orbit changed" if inclined and abs(after["i"] - before["i"]) >= INC_CHANGE else ROUTINE
    if kept_b:
        return "started drifting"
    if kept_a:
        return "stopped drifting"
    return "drift rate changed"


def _epoch(s):
    return datetime.fromisoformat(s.rstrip("Z")[:26]).replace(tzinfo=timezone.utc)


def sgp4_position(o, t):
    """(TEME position km, Earth-fixed longitude deg) of an object's newest set at UTC datetime t, by SGP4 (WGS72, as
    the globe and the tracks); None where SGP4 fails."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from geo_page import satrec
    from sgp4.api import jday
    from sgp4.propagation import gstime
    s = satrec(o)
    jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)
    err, r, _ = s.sgp4(jd, fr)
    if err:
        return None
    g = gstime(jd + fr)
    x, y = r[0] * math.cos(g) + r[1] * math.sin(g), -r[0] * math.sin(g) + r[1] * math.cos(g)
    return tuple(r), math.degrees(math.atan2(y, x))


def close_pairs(objs, roles, t, position=sgp4_position):
    """Pairs within CLOSE_KM at t: (listed, same-owner count). `objs` are dicts with norad, name, owner, epoch and
    elements; `roles` {str(norad): role}."""
    placed = []
    for o in objs:
        p = position(o, t)
        if p:
            placed.append((o, p[0], p[1]))
    placed.sort(key=lambda x: x[2])
    listed, same = [], 0
    for k, (a, ra, la) in enumerate(placed):
        for b, rb, lb in placed[k + 1:] + placed[:k]:
            dlon = (lb - la + 540.0) % 360.0 - 180.0
            if not 0.0 <= dlon <= NEAR_LON or (b is a):
                continue                         # each pair once: b east of a, by at most NEAR_LON
            if dlon == 0.0 and b["norad"] < a["norad"]:
                continue
            km = math.dist(ra, rb)
            if km > CLOSE_KM:
                continue
            role_a, role_b = roles.get(str(a["norad"])), roles.get(str(b["norad"]))
            if a.get("owner") and a.get("owner") == b.get("owner") and not (role_a or role_b):
                same += 1
                continue
            age = max((t - _epoch(x["epoch"])).total_seconds() / 86400.0 for x in (a, b))
            listed.append({"a": [a["norad"], a["name"], a.get("owner"), role_a], "b": [b["norad"], b["name"], b.get("owner"), role_b],
                           "km": round(km), "lon": round(la, 2), "kind": pair_kind(role_a, role_b), "age_days": round(age, 1)})
    listed.sort(key=lambda r: (r["kind"].startswith("no listed"), r["km"]))
    return listed, same


def changes(objs, elsets, roles, now, days=CHANGE_DAYS):
    """Orbit changes by Orbit's rule ending in the last `days` days, every object in `objs`: (changes, counts by kind,
    objects not judged). An object with under MIN_PAIRS pairs of sets is not judged; its last two sets' drift and
    inclination are given as they are."""
    sys.path.insert(0, ROOT)
    from orbit import maneuver as M
    out, unjudged = [], []
    for o in objs:
        held = [r for r in elsets.get(o["norad"], []) if _epoch(r["epoch"]) < now]
        sets = [[M._iso(_epoch(r["epoch"])), float(r["n"]), float(r["e"]), float(r["i"]), float(r["raan"]),
                 float(r["argp"]), float(r["M"]), ""] for r in held]
        det = M.detect({"sets": sets}, now, window_days=days)
        at = {s[0]: s for s in sets}
        if len(sets) - 1 < M.MIN_PAIRS:          # too few public sets for the object's own noise: shown, not judged
            u = {"norad": o["norad"], "name": o["name"], "owner": o.get("owner"), "role": roles.get(str(o["norad"])),
                 "sets": len(sets)}
            if len(sets) >= 2:
                p, q = sets[-2], sets[-1]
                u.update(between=[p[0][:16], q[0][:16]], drift=[round(drift(p[1]), 4), round(drift(q[1]), 4)],
                         inc=[round(p[3], 3), round(q[3], 3)])
            unjudged.append(u)
            continue
        for e in det["events"]:
            p, q = at.get(e["from"]), at.get(e["to"])
            if not (p and q):
                continue
            b, a = {"drift": drift(p[1]), "i": p[3]}, {"drift": drift(q[1]), "i": q[3]}
            c = {"norad": o["norad"], "name": o["name"], "owner": o.get("owner"), "role": roles.get(str(o["norad"])),
                 "between": [e["from"][:16], e["to"][:16]], "dv_ms": e["dv_ms"], "dominant": e["dominant"],
                 "kind": change_kind(b, a), "drift": [round(b["drift"], 4), round(a["drift"], 4)],
                 "inc": [round(b["i"], 3), round(a["i"], 3)]}
            if e.get("geo"):
                c["lon"] = e["geo"]["lon_after"]
            if e.get("gap"):
                c["gap_h"] = e["gap"]["hours"]
            out.append(c)
    rare = [c for c in out if c["kind"] != ROUTINE]
    routine = sorted((c for c in out if c["kind"] == ROUTINE), key=lambda c: c["between"][1])
    counts = {"other": len(rare), ROUTINE: len(routine)}
    keep = sorted(rare + routine[-MAX_ROUTINE:], key=lambda c: (c["between"][1], c["norad"]), reverse=True)
    return keep, counts, unjudged


def build(objs, elsets, roles, now, position=sgp4_position):
    """The belt board for the active objects `objs` (dicts from the day file) at UTC datetime `now`."""
    now = now.replace(second=0, microsecond=0)
    for o in objs:
        o["drift"] = drift(o["n"])
        o["class"] = classify(o["drift"], o["i"])
    counts = {k: sum(1 for o in objs if o["class"] == k) for k in ("station-kept", "inclined", "drifting")}
    close, same = close_pairs(objs, roles, now, position)
    ch, ch_counts, unjudged = changes(objs, elsets, roles, now)
    drifting = sorted((o for o in objs if o["class"] == "drifting"), key=lambda o: -abs(o["drift"]))
    lon_now = {}
    for o in drifting[:MAX_DRIFT]:
        p = position(o, now)
        lon_now[o["norad"]] = round(p[1], 2) if p else None
    return {"at_utc": now.strftime("%Y-%m-%dT%H:%MZ"), "objects": len(objs), "counts": counts,
            "method": {"close_km": CLOSE_KM, "drift_kept": DRIFT_KEPT, "inc_kept": INC_KEPT, "inc_change": INC_CHANGE,
                       "change_days": CHANGE_DAYS, "change_rule": "orbit/maneuver.py"},
            "close_other_owner": close[:MAX_CLOSE], "close_other_owner_count": len(close), "close_same_owner_count": same,
            "changes": ch, "change_counts": ch_counts, "not_judged": unjudged,
            "drifting": [{"norad": o["norad"], "name": o["name"], "owner": o.get("owner"), "lon": lon_now.get(o["norad"]),
                          "drift": round(o["drift"], 4), "role": roles.get(str(o["norad"]))} for o in drifting[:MAX_DRIFT]]}
