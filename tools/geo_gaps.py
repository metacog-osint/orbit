#!/usr/bin/env python3
"""geo_gaps.py: listed-role GEO satellites whose newest public element set is 7 days old or more, and the sets that
came back after such a gap (method "Gaps in public element sets", orbit-2.40).

About the source, never the satellite. Space-Track publishes sets for some objects days or weeks apart, and an
object can manoeuvre while none is published: Luch (Olymp) 2 had no public set from 15 Oct to 21 Nov 2026 and had
left 62 E when its sets came back. So an entry says how old the newest set in Orbit's files is, and never that the
object is quiet, inactive or holding its slot.

Inputs, all from Orbit's public GEO release (no request): every element set held (geo-elements-YYYY-MM.json.gz),
and the day files (<day>.geo-region.json), whose `regions` give each object's newest epoch as of that day's GEO run
and whose `fetched_utc` gives the run's time, so they date when a set first reached Orbit's files. Listed roles:
site_src/geo_roles.json. Standard library only.
  objects   every listed-role object: its newest set (epoch, age at the build time, longitude and drift at that set,
            the day file that first carried it), `silent` when that set is QUIET_DAYS (7) days old or more, the
            time it passed 7 days, and its earlier gaps of 7 days or more in Orbit's sets (how many, the longest).
  back      a set again after 7 days or more with none newer in Orbit's files, by the day file that first carried
            it, in the last BACK_DAYS (30): the widest pair of consecutive sets across it, with longitude and drift
            at each, the time between their epochs, and the day file (see `backs`).
The daily lead's line is orbit/lead.py's geo_line, from this block.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)                               # the orbit package before tools/orbit.py
from orbit import geo_region as G  # noqa: E402
from orbit import maneuver as M  # noqa: E402

QUIET_DAYS = G.QUIET_DAYS          # 7: the day files' "quiet" event uses the same age
BACK_DAYS = 30                     # sets back after a gap, by the day file that first carried them
READ_DAYS = BACK_DAYS + 15         # day files read for first reads (the release's newest first)
NOTE = ("A satellite can manoeuvre while no set is published, and the next set can show it somewhere else. Orbit "
        "cannot tell from the public data why no set was published.")


def _t(s):
    return datetime.fromisoformat(str(s).rstrip("Z")[:19]).replace(tzinfo=timezone.utc)


def _iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _days(a, b):
    return (b - a).total_seconds() / 86400.0


def read_time(day, fetched):
    """When a day file was read: its `fetched_utc`, or the end of its day for the files imported from Noisefloor,
    which hold none."""
    if fetched:
        return _t(str(fetched).replace("Z", ""))
    return _t(day) + timedelta(days=1)


def first_reads(day_docs, ids):
    """{norad: [[day, fetched_utc or None, epoch], ...]}, oldest day first, from day files' `regions` (each
    object's newest epoch as of that day's GEO run). `day_docs` are parsed day files in any order."""
    want = {str(k) for k in ids}
    out = {int(k): [] for k in want}
    for d in day_docs:                                 # one at a time: a day file is about 430 KB
        for k in want:
            v = (d.get("regions") or {}).get(k)
            if v and len(v) > 1:
                out[int(k)].append([d["day"], d.get("fetched_utc"), str(v[1])[:19]])
    for v in out.values():
        v.sort(key=lambda x: x[0])
    return out


def held_by(elsets, reads, day):
    """The sets Orbit's files held as of a day file: each object's sets no newer than its epoch in that day file
    (for tests on a past day; on the build day the element files and the newest day file agree)."""
    out = {}
    for k, sets in elsets.items():
        r = [x for x in reads.get(k, []) if x[0] <= day]
        if r:
            out[k] = [s for s in sets if str(s["epoch"])[:19] <= r[-1][2]]
    return out


def _pos(s):
    g = M.geo_position([M._iso(_t(s["epoch"])), float(s["n"]), float(s["e"]), float(s["i"]), float(s["raan"]),
                        float(s["argp"]), float(s["M"]), ""])
    return g["lon"], g["drift_deg_day"]


def _first_read(reads, epoch):
    """The first day file whose newest epoch for the object is this set's or later: {day, read_utc}."""
    for day, fetched, e in reads:
        if e >= epoch:
            return {"day": day, "read_utc": fetched and _iso(read_time(day, fetched))}
    return None


def _set_at(s):
    lon, drift = _pos(s)
    return {"t": _iso(_t(s["epoch"])), "lon": lon, "drift": drift}


def backs(sets, rd, now):
    """Each day file that first carried a newer set for the object while the newest set in Orbit's files before it
    (the epoch in the day file before) was QUIET_DAYS old or more at that file's read time, within BACK_DAYS of
    `now`. That always includes a gap of 7 days or more between two sets' epochs, and also a set that reached
    Orbit's files late (MEV-1's set of 22 Nov 2026 23:29Z, first read 24 Nov 23:57Z, after the set of 16 Nov
    18:43Z had passed 7 days old). The pair shown is the widest between consecutive sets from that newest set to
    the file's: `late` when it is under 7 days."""
    by = {str(s["epoch"])[:19]: s for s in sets}
    eps = sorted(by)
    out = []
    for prev, cur in zip(rd, rd[1:]):
        p, c = prev[2], cur[2]
        if c <= p:
            continue
        r = read_time(cur[0], cur[1])
        if _days(_t(p), r) < QUIET_DAYS or _days(r, now) > BACK_DAYS or r > now:
            continue
        lo = [e for e in eps if e <= p]
        chain = lo[-1:] + [e for e in eps if p < e <= c]
        if len(chain) < 2:
            continue
        a, b = max(zip(chain, chain[1:]), key=lambda ab: _days(_t(ab[0]), _t(ab[1])))
        gap = _days(_t(a), _t(b))
        if gap < QUIET_DAYS and not cur[1]:
            continue                                   # an imported day file holds no read time to judge "late" by
        out.append({"before": _set_at(by[a]), "after": _set_at(by[b]), "gap_days": round(gap, 1),
                    "late": gap < QUIET_DAYS, "none_newer_days": round(_days(_t(p), r), 1),
                    "first_read": {"day": cur[0], "read_utc": cur[1] and _iso(r)}})
    return out


def build(roles, elsets, reads, objs, now, read_utc=None, region_day=None):
    """`roles` {str(norad): role}; `elsets` {norad: [element-file rows sorted by epoch]}; `reads` first_reads();
    `objs` {norad: {name, owner, region}} from the newest day file; `now` the build time (UTC)."""
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    quiet = timedelta(days=QUIET_DAYS)
    objects, back = [], []
    for key, role in sorted(roles.items(), key=lambda kv: int(kv[0])):
        k = int(key)
        o = objs.get(k) or {}
        by_epoch = {}
        for s in elsets.get(k) or []:
            if _t(s["epoch"]) <= now:
                by_epoch[str(s["epoch"])[:19]] = s
        sets = [by_epoch[e] for e in sorted(by_epoch)]
        rd = reads.get(k) or []
        entry = {"norad": k, "name": o.get("name") or f"NORAD {k}", "owner": o.get("owner"), "role": role,
                 "region": o.get("region"), "sets": len(sets)}
        if not sets:
            entry.update({"newest": None, "silent": True, "silent_since": None, "gaps": {"count": 0}})
            objects.append(entry)
            continue
        new = sets[-1]
        tn = _t(new["epoch"])
        nw = _set_at(new)
        nw["age_h"] = round((now - tn).total_seconds() / 3600, 1)
        nw["first_read"] = _first_read(rd, str(new["epoch"])[:19])
        gaps = []
        for a, b in zip(sets, sets[1:]):
            d = _days(_t(a["epoch"]), _t(b["epoch"]))
            if d >= QUIET_DAYS:
                gaps.append((d, a, b))
        longest = max(gaps, key=lambda g: g[0]) if gaps else None
        entry.update({"newest": nw, "first_set": _iso(_t(sets[0]["epoch"])),
                      "silent": now - tn >= quiet, "silent_since": _iso(tn + quiet),
                      "gaps": {"count": len(gaps), "longest_days": round(longest[0], 1) if longest else None,
                               "longest": [_iso(_t(longest[1]["epoch"])), _iso(_t(longest[2]["epoch"]))] if longest else None}})
        objects.append(entry)
        for b in backs(sets, rd, now):
            back.append(dict(b, norad=k, name=entry["name"], owner=entry["owner"], role=role))
    objects.sort(key=lambda e: (not e["silent"], -(e["newest"] or {}).get("age_h", 1e9)))
    back.sort(key=lambda b: (b["first_read"]["day"], b["after"]["t"]), reverse=True)
    return {"at_utc": _iso(now), "read_utc": read_utc and _iso(read_time(region_day, read_utc)), "region_day": region_day,
            "quiet_days": QUIET_DAYS, "back_days": BACK_DAYS, "note": NOTE, "objects": objects, "back": back,
            "attribution": M.ATTRIBUTION}
