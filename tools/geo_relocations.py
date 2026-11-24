#!/usr/bin/env python3
"""geo_relocations.py: a GEO object's stops and relocations along the belt from its element sets, and how early a
brake detector would have given each stop longitude. The calibration for the relocation tracker (ideas#248), first
run on Luch (Olymp) 2's full history (ideas#256, the `luch2` case of `tools/orbit.py maneuver-case`).

  stop        a run of sets with |drift| under DRIFT_KEPT (0.1 deg a day, the belt board's line) lasting MIN_STOP_DAYS
              (2) or more. Two runs whose median longitudes differ by under MERGE_LON (0.2 deg) with a break of under
              MERGE_GAP_DAYS (7) are one stop (a short trim, not a move). Longitude: the median of the run.
              Arrival: its first set; departure: its last set (the move began between it and the next set).
              A turnaround is a stop too: the drift changes direction between two sets both under TURN_DRIFT
              (0.5 deg a day), outside any stop; the stop spans the sets under TURN_DRIFT around it, longitude at the
              set of least drift (Luch 2's checkout at 78 deg E, 21-24 Mar 2023 in Marco Langbroek's table).
  relocation  the sets between two stops: longitude moved, peak drift and when, days speeding up (departure to
              peak) and braking (peak to arrival), the largest gap between sets.
  brake       from the peak on, at each set the drift is compared with a set at least RATE_DT_DAYS (0.5) earlier; when
              the drift fell by BRAKE_MIN (0.05 deg a day) or more, constant braking at that measured rate gives a
              projected stop longitude (lon + v * v / 2b, in the direction of drift). Reported: the first projection
              and the first one within NEAR_DEG (1 deg) of the stop, each with its lead before arrival. A live
              detector cannot know the stop, so `steady` is the first projection within NEAR_DEG of the one before
              it: the one a tracker could publish.
Arithmetic on public element sets: not a forecast, and no statement of why an object moved. Low-inclination orbits
only (longitude = RAAN + argument of perigee + mean anomaly - GMST, orbit/maneuver.py). Standard library only.

  python tools/geo_relocations.py [CASE_FILE] [--json OUT]   # default: data/state/spacetrack/case_luch2_2023.json.gz
"""
import argparse
import gzip
import json
import os
import sys
from datetime import datetime, timezone
from statistics import median

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from orbit import maneuver  # noqa: E402

GEO_KM = 42164.17
DRIFT_KEPT = 0.1
MIN_STOP_DAYS = 2.0
TURN_DRIFT = 0.5
MERGE_LON, MERGE_GAP_DAYS = 0.2, 7.0
RATE_DT_DAYS = 0.5
BRAKE_MIN = 0.05
NEAR_DEG = 1.0
DEFAULT_CASE = os.path.join(ROOT, "data", "state", "spacetrack", "case_luch2_2023.json.gz")


def _t(s):
    return datetime.fromisoformat(s.rstrip("Z")[:19]).replace(tzinfo=timezone.utc)


def _days(a, b):
    return (_t(b) - _t(a)).total_seconds() / 86400.0


def positions(records, now=None):
    """One row per distinct epoch (Space-Track's re-issues merged as orbit/maneuver.py does): epoch, longitude
    (east +), drift (deg a day, east +), height above GEO (km), inclination."""
    now = now or datetime.now(timezone.utc)
    store = maneuver.merge({}, records, now, keep_days=100000)
    out = []
    for obj in store.values():
        for s in obj["sets"]:
            g = maneuver.geo_position(s)
            out.append({"t": s[0], "lon": g["lon"], "drift": g["drift_deg_day"],
                        "dh_km": round(maneuver._a(s[1]) - GEO_KM, 1), "i": s[3]})
    return sorted(out, key=lambda r: r["t"])


def _runs(rows):
    runs, cur = [], []
    for r in rows:
        if abs(r["drift"]) < DRIFT_KEPT:
            cur.append(r)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return runs


def turnarounds(rows, held):
    out = []
    inside = lambda t: any(h["arrival"] <= t <= h["departure"] for h in held)
    for k in range(1, len(rows)):
        p, q = rows[k - 1], rows[k]
        if p["drift"] * q["drift"] >= 0 or abs(p["drift"]) >= TURN_DRIFT or abs(q["drift"]) >= TURN_DRIFT:
            continue
        if inside(p["t"]) or inside(q["t"]):
            continue
        lo, hi = k - 1, k
        while lo > 0 and abs(rows[lo - 1]["drift"]) < TURN_DRIFT:
            lo -= 1
        while hi < len(rows) - 1 and abs(rows[hi + 1]["drift"]) < TURN_DRIFT:
            hi += 1
        run = rows[lo:hi + 1]
        if out and out[-1]["arrival"] == run[0]["t"]:
            continue
        calm = min(run, key=lambda r: abs(r["drift"]))
        out.append({"lon": calm["lon"], "arrival": run[0]["t"], "departure": run[-1]["t"], "rows": list(run),
                    "kind": "turnaround"})
    return out


def stops(rows):
    out = []
    for run in _runs(rows):
        lon = median(r["lon"] for r in run)
        if out:
            last = out[-1]
            if abs(lon - last["lon"]) < MERGE_LON and _days(last["departure"], run[0]["t"]) < MERGE_GAP_DAYS:
                last["rows"].extend(run)
                last["departure"] = run[-1]["t"]
                last["lon"] = round(median(r["lon"] for r in last["rows"]), 2)
                continue
        out.append({"lon": round(lon, 2), "arrival": run[0]["t"], "departure": run[-1]["t"], "rows": list(run)})
    out = [s for s in out if _days(s["arrival"], s["departure"]) >= MIN_STOP_DAYS]
    for s in out:
        s["kind"] = "held"
    out = sorted(out + turnarounds(rows, out), key=lambda s: s["arrival"])
    for s in out:
        s["days"] = round(_days(s["arrival"], s["departure"]), 1)
        s["sets"] = len(s.pop("rows"))
    return out


def _brake(moving, stop_lon, arrival):
    """First brake projection, and first within NEAR_DEG of the stop, from the peak on."""
    if not moving:
        return None
    k0 = max(range(len(moving)), key=lambda k: abs(moving[k]["drift"]))
    first = near = steady = prev = None
    for k in range(k0 + 1, len(moving)):
        q = moving[k]
        p = next((moving[j] for j in range(k - 1, -1, -1) if _days(moving[j]["t"], q["t"]) >= RATE_DT_DAYS), None)
        if p is None:
            continue
        fall = abs(p["drift"]) - abs(q["drift"])
        if fall < BRAKE_MIN or p["drift"] * q["drift"] <= 0:
            continue
        b = fall / _days(p["t"], q["t"])              # deg a day, per day
        v = abs(q["drift"])
        sign = 1 if q["drift"] > 0 else -1
        proj = round(maneuver._wrap180(q["lon"] + sign * v * v / (2 * b)), 2)
        rec = {"at": q["t"], "lead_days": round(_days(q["t"], arrival), 1), "projected_lon": proj,
               "error_deg": round(maneuver._wrap180(proj - stop_lon), 2), "drift": q["drift"]}
        if first is None:
            first = rec
        if near is None and abs(rec["error_deg"]) <= NEAR_DEG:
            near = rec
        if steady is None and prev is not None and abs(maneuver._wrap180(proj - prev["projected_lon"])) <= NEAR_DEG:
            steady = rec
        prev = rec
        if near and steady:
            break
    return {"first": first, "steady": steady, "within_1deg": near}


def relocations(rows, st):
    out = []
    for a, b in zip(st, st[1:]):
        moving = [r for r in rows if a["departure"] < r["t"] < b["arrival"]]
        seq = [r for r in rows if a["departure"] <= r["t"] <= b["arrival"]]
        gap = max((_days(p["t"], q["t"]) for p, q in zip(seq, seq[1:])), default=None)
        moved = round(maneuver._wrap180(b["lon"] - a["lon"]), 2)
        rec = {"from_lon": a["lon"], "to_lon": b["lon"], "moved_deg": moved,
               "direction": "east" if moved > 0 else "west", "departure": a["departure"], "arrival": b["arrival"],
               "days": round(_days(a["departure"], b["arrival"]), 1), "sets": len(moving),
               "max_gap_days": round(gap, 1) if gap is not None else None}
        if moving:
            pk = max(moving, key=lambda r: abs(r["drift"]))
            rec.update({"peak_drift": pk["drift"], "peak_at": pk["t"], "peak_dh_km": pk["dh_km"],
                        "speeding_up_days": round(_days(a["departure"], pk["t"]), 1),
                        "braking_days": round(_days(pk["t"], b["arrival"]), 1),
                        "brake": _brake(moving, b["lon"], b["arrival"])})
        out.append(rec)
    return out


def build(records, now=None):
    rows = positions(records, now)
    st = stops(rows)
    return {"schema": "orbit-relocations/1", "sets": len(rows), "first": rows[0]["t"] if rows else None,
            "last": rows[-1]["t"] if rows else None, "stops": st, "relocations": relocations(rows, st),
            "rules": {"drift_kept": DRIFT_KEPT, "min_stop_days": MIN_STOP_DAYS, "turn_drift": TURN_DRIFT, "merge_lon": MERGE_LON,
                      "merge_gap_days": MERGE_GAP_DAYS, "rate_dt_days": RATE_DT_DAYS, "brake_min": BRAKE_MIN,
                      "near_deg": NEAR_DEG},
            "attribution": maneuver.ATTRIBUTION}


def _lon(x):
    return f"{abs(x):.2f}{'E' if x >= 0 else 'W'}"


def print_report(doc):
    print(f"{doc['sets']} element sets, {doc['first']} to {doc['last']}. {doc['attribution']}")
    print("Stops:")
    for s in doc["stops"]:
        print(f"  {_lon(s['lon']):>7}  {s['arrival'][:10]} to {s['departure'][:10]}  {s['days']:6.1f} d  {s['sets']} sets"
              + ("  (turnaround)" if s["kind"] == "turnaround" else ""))
    print("Relocations:")
    for r in doc["relocations"]:
        line = (f"  {_lon(r['from_lon']):>7} -> {_lon(r['to_lon']):>7}  {r['moved_deg']:+7.2f} deg  {r['departure'][:10]}"
                f" to {r['arrival'][:10]} ({r['days']} d, {r['sets']} sets, gap max {r['max_gap_days']} d)")
        if "peak_drift" in r:
            line += (f"  peak {r['peak_drift']:+.3f}/d at {r['peak_at'][:10]} ({r['peak_dh_km']:+.0f} km)"
                     f"  up {r['speeding_up_days']} d, braking {r['braking_days']} d")
            br = r.get("brake") or {}
            for key, label in (("first", "first brake"), ("steady", "steady"), ("within_1deg", "within 1 deg")):
                b = br.get(key)
                line += (f"\n{'':10}{label}: {b['at'][:16]}, {b['lead_days']} d before arrival, projected "
                         f"{_lon(b['projected_lon'])} (off {b['error_deg']:+.2f})" if b else f"\n{'':10}{label}: none")
        print(line)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("case", nargs="?", default=DEFAULT_CASE)
    ap.add_argument("--json", help="write the table here")
    a = ap.parse_args(argv)
    with gzip.open(a.case) if a.case.endswith(".gz") else open(a.case, "rb") as f:
        records = json.load(f)
    doc = build(records)
    print_report(doc)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
