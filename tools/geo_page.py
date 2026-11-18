#!/usr/bin/env python3
"""geo_page.py: the data files behind Orbit's GEO page (geo.html): every object near GEO with its latest elements,
the observed tracks of the last 1, 7, 30 and 90 days, the listed roles, the region's arrivals and departures, and
Secure World Foundation's RPO pairs whose chaser and target are both near GEO.

  python tools/geo_page.py build RELEASE_DIR [SITE] [--snapshot data/snapshot.json]
      # -> SITE/data/geo/globe.json and SITE/data/geo/tracks-<N>d.json

Moved from Noisefloor's tools/geo_globe.py (35328c0) in step 4 of doctrine/geo-move-plan.md; the tracks are made the
same way. Inputs: the geo-YYYY release (orbit/geo_region.py): the newest <day>.geo-region.json that carries objects
(its `active` list is CelesTrak's active GEO group, read in the same run), every day file's events, and the monthly
geo-elements-YYYY-MM.json.gz files (every element set held). RPO pairs come from the snapshot's `rpo` block (SWF's
sheet, lane `rpo`); no request is made here.

Tracks: each element set is propagated with SGP4 (the sgp4 library, MIT; WGS72, as satellite.js in the browser) only
until the next one is published, so a track is what the published elements said at each time, manoeuvres included.
Positions are Earth-fixed (TEME rotated by Greenwich mean sidereal time; polar motion ignored) and good to tens of
kilometres at GEO. Each track is [first sample, lon, lat, dalt, then the change from the sample before for each of
the three]; lon and lat in hundredths of a degree, dalt in km from the GEO altitude (35,786 km).
"""
import glob
import gzip
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOWS = {1: 15, 7: 60, 30: 240, 90: 720}       # days shown: minutes between samples
EVENT_DAYS = 30                                   # arrivals and departures listed on the page
GEO_ALT, RE = 35786.0, 6378.137
OBJ_COLS = ["norad", "name", "cospar", "type", "owner", "launch", "rcs", "region", "active", "epoch", "n", "e", "i", "raan",
            "argp", "M", "bstar"]
CITE = "Orbital data: USSPACECOM (space-track.org); basic SSA data, redistributed with citation"
RPO_CITE = ("Secure World Foundation, Global Counterspace Capabilities (2026), \"History of Robotic Rendezvous and "
            "Proximity Operations in Space\" (CC BY-NC 4.0)")


def newest(paths, test=lambda d: True):
    for p in sorted(paths, reverse=True):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        if test(d):
            return d
    return None


def satrec(r):
    from sgp4.api import WGS72, Satrec
    s = Satrec()
    ep = datetime.fromisoformat(r["epoch"][:26])
    days = (ep - datetime(1949, 12, 31)).total_seconds() / 86400.0
    s.sgp4init(WGS72, "i", 0, days, r.get("bstar") or 0.0, 0.0, 0.0, r["e"], math.radians(r["argp"]), math.radians(r["i"]),
               math.radians(r["M"]), r["n"] * 2 * math.pi / 1440.0, math.radians(r["raan"]))
    return s


def earth_fixed(s, t):
    """(lon deg, lat deg, km from GEO altitude) of a Satrec at a UTC datetime, or None if SGP4 fails."""
    from sgp4.api import jday
    from sgp4.propagation import gstime
    jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)
    err, r, _ = s.sgp4(jd, fr)
    if err:
        return None
    g = gstime(jd + fr)
    x, y = r[0] * math.cos(g) + r[1] * math.sin(g), -r[0] * math.sin(g) + r[1] * math.cos(g)
    return (math.degrees(math.atan2(y, x)), math.degrees(math.atan2(r[2], math.hypot(x, y))),
            math.sqrt(x * x + y * y + r[2] * r[2]) - RE - GEO_ALT)


def encode(start, samples):
    """[start, lon, lat, dalt, then deltas]: integers (0.01 deg, km); longitude steps wrapped to the short way round."""
    out, prev = [start], None
    for lon, lat, dalt in samples:
        q = (round(lon * 100), round(lat * 100), round(dalt))
        if prev is None:
            out += list(q)
        else:
            dl = (q[0] - prev[0] + 18000) % 36000 - 18000
            out += [dl, q[1] - prev[1], q[2] - prev[2]]
        prev = q
    return out


def decode(track):
    """The inverse of encode (for tests): (start, [(lon, lat, dalt), ...])."""
    start, vals, out = track[0], track[1:], []
    lon = lat = dalt = None
    for k in range(0, len(vals), 3):
        if lon is None:
            lon, lat, dalt = vals[k:k + 3]
        else:
            lon, lat, dalt = (lon + vals[k] + 18000) % 36000 - 18000, lat + vals[k + 1], dalt + vals[k + 2]
        out.append((lon / 100, lat / 100, dalt))
    return start, out


def read_elsets(release, since):
    """{norad: [element sets sorted by epoch]} from Orbit's monthly geo-elements-YYYY-MM.json.gz files ("cols" and
    "rows") that can hold sets newer than `since` - 45 days. A repeated epoch keeps the last set read."""
    first = (since - timedelta(days=45)).strftime("%Y-%m")
    keep = ("norad", "epoch", "n", "e", "i", "raan", "argp", "M", "bstar")
    by = {}
    for p in sorted(glob.glob(os.path.join(release, "geo-elements-*.json.gz"))):
        if os.path.basename(p)[13:20] < first:
            continue
        with gzip.open(p, "rt", encoding="utf-8") as f:
            doc = json.load(f)
        idx = {c: doc["cols"].index(c) for c in keep}
        for row in doc["rows"]:
            r = {c: row[i] for c, i in idx.items()}
            r["norad"] = int(r["norad"])
            by.setdefault(r["norad"], {})[r["epoch"]] = r
    return {k: [v[e] for e in sorted(v)] for k, v in by.items()}


def tracks(elsets, norads, end, days, step):
    """Observed tracks over `days` ending at `end`, one sample every `step` minutes."""
    n = days * 1440 // step
    times = [end - timedelta(minutes=step * (n - k)) for k in range(n + 1)]
    iso = [t.strftime("%Y-%m-%dT%H:%M:%S") for t in times]
    out = {}
    for norad in norads:
        sets = elsets.get(norad)
        if not sets:
            continue
        at, cache, start, samples = -1, {}, None, []
        for k, t in enumerate(times):
            while at + 1 < len(sets) and sets[at + 1]["epoch"][:19] <= iso[k]:
                at += 1
            if at < 0:
                continue                           # no element set yet at this time
            if at not in cache:
                cache = {at: satrec(sets[at])}     # one at a time: the sets only move forward
            p = earth_fixed(cache[at], t)
            if p is None:
                if start is not None:
                    break                          # stop the track at a failure rather than leave a gap
                continue
            if start is None:
                start = k
            samples.append(p)
        if samples:
            out[str(norad)] = encode(start, samples)
    return {"start_utc": times[0].strftime("%Y-%m-%dT%H:%MZ"), "step_min": step, "samples": n + 1, "tracks": out}


def roles(path=os.path.join(ROOT, "site_src", "geo_roles.json")):
    """{str(norad): {role, basis, sources}} for the objects whose role published reporting supports."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    return {str(o["id"]): {"role": o["role"], "basis": o.get("basis", ""), "sources": o.get("sources", [])}
            for o in d.get("objects", []) if o.get("role")}


def region_events(release, last_day, days=EVENT_DAYS):
    """Every day file's events from the `days` days up to `last_day`, newest first."""
    first = (datetime.strptime(last_day, "%Y-%m-%d") - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    out = []
    for p in sorted(glob.glob(os.path.join(release, "*.geo-region.json"))):
        day = os.path.basename(p)[:10]
        if first <= day <= last_day:
            try:
                with open(p, encoding="utf-8") as f:
                    out += json.load(f).get("events", [])
            except (OSError, ValueError):
                continue
    out.sort(key=lambda e: (e.get("day", ""), e.get("norad", 0)), reverse=True)
    return {"from": first, "to": last_day, "events": out}


def rpo_pairs(snapshot, objs):
    """SWF's RPO rows whose chaser and target were both matched to objects near GEO today: one entry per row and
    chaser-target pair, with SWF's own text for the date and mission. Rows with one end near GEO are counted only."""
    rpo = (snapshot or {}).get("rpo") or {}
    near = {o[0]: o[1] for o in objs}
    pairs, one_end = [], 0
    for row in rpo.get("rows", []):
        g = row.get("gcat") or {}
        ch = [int(x["norad"]) for x in g.get("chaser", []) if str(x.get("norad") or "").isdigit()]
        tg = [int(x["norad"]) for x in g.get("target", []) if str(x.get("norad") or "").isdigit()]
        both = [(c, t) for c in ch for t in tg if c in near and t in near and c != t]
        if not both:
            one_end += any(k in near for k in ch + tg)
            continue
        for c, t in both:
            when = row.get("when") or {}
            pairs.append({"chaser": [c, near[c], row.get("chaser", "")], "target": [t, near[t], row.get("target", "")],
                          "when": row.get("date_text", ""), "start": when.get("start"), "ongoing": bool(when.get("ongoing")),
                          "mission": row.get("mission_type", ""), "tab": row.get("tab", ""), "country": row.get("country", "")})
    pairs.sort(key=lambda p: p.get("start") or "", reverse=True)
    return {"source": RPO_CITE, "sheet": rpo.get("sheet"), "report": rpo.get("report"), "updated": rpo.get("updated"),
            "read_at": rpo.get("read_at"), "pairs": pairs, "one_end_only": one_end}


def belt(region, active, elsets, now):
    """The belt board (tools/geo_belt.py) for CelesTrak's active objects, or {"error": ...} so a failure there never
    takes the globe down."""
    if not active:
        return {"error": "no active list in the day file (CelesTrak not read)"}
    import geo_belt
    cols = region["object_cols"]
    objs = [o for o in (dict(zip(cols, row)) for row in region["objects"]) if o["norad"] in active]
    try:
        return geo_belt.build(objs, elsets, {k: v["role"] for k, v in roles().items()}, now.replace(tzinfo=timezone.utc))
    except Exception as e:  # noqa: BLE001: reported on the page and in the log
        print(f"geo page: belt board skipped: {e!r}")
        return {"error": f"{type(e).__name__}: {e}"}


def build(release, site, now=None, snapshot=None):
    now = (now or datetime.now(timezone.utc)).replace(tzinfo=None, second=0, microsecond=0)
    region = newest(glob.glob(os.path.join(release, "*.geo-region.json")), lambda d: "objects" in d)
    if not region:
        raise SystemExit("no geo-region file with objects (python tools/orbit.py geo runs first)")
    active = set(region.get("active") or [])
    cols = region["object_cols"]
    objs = []
    for row in region["objects"]:
        o = dict(zip(cols, row))
        objs.append([o["norad"], o["name"], o["cospar"], o["type"], o["owner"], o["launch"], o["rcs"], o["region"],
                     1 if o["norad"] in active else 0, o["epoch"][:19], round(o["n"], 8), round(o["e"], 7), round(o["i"], 4),
                     round(o["raan"], 4), round(o["argp"], 4), round(o["M"], 4), o.get("bstar") or 0.0])
    out_dir = os.path.join(site, "data", "geo")
    os.makedirs(out_dir, exist_ok=True)
    meta = {}
    end = now.replace(minute=now.minute - now.minute % 15)
    elsets = read_elsets(release, end - timedelta(days=max(WINDOWS)))
    norads = [o[0] for o in objs]
    for days, step in WINDOWS.items():
        e = end.replace(minute=0) - timedelta(hours=end.hour % (step // 60)) if step >= 60 else end
        tr = tracks(elsets, norads, e, days, step)
        name = f"tracks-{days}d.json"
        with open(os.path.join(out_dir, name), "w", encoding="utf-8", newline="\n") as f:
            json.dump(tr, f, separators=(",", ":"))
        meta[str(days)] = {"file": name, "start_utc": tr["start_utc"], "step_min": step, "samples": tr["samples"],
                           "objects": len(tr["tracks"])}
    owners = {}
    try:
        with open(os.path.join(ROOT, "site_src", "geo", "satcat_owners.json"), encoding="utf-8") as f:
            names = json.load(f)["codes"]
        owners = {o[4]: names[o[4]] for o in objs if o[4] in names}
    except (OSError, ValueError, KeyError):
        pass
    doc = {"built_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "region_day": region["day"], "owners": owners,
           "elements_fetched_utc": region.get("fetched_utc"), "active_from": region.get("day") if active else None,
           "source": CITE, "definitions": region.get("definitions"), "counts": region.get("counts"),
           "cols": OBJ_COLS, "objects": objs, "tracks": meta, "roles": roles(),
           "region": region_events(release, region["day"]), "rpo": rpo_pairs(snapshot, objs),
           "belt": belt(region, active, elsets, now)}
    with open(os.path.join(out_dir, "globe.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)
    return doc


def main():
    args = sys.argv[1:]
    snap_path = os.path.join(ROOT, "data", "snapshot.json")
    if "--snapshot" in args:
        k = args.index("--snapshot")
        snap_path = args[k + 1]
        del args[k:k + 2]
    if len(args) < 2 or args[0] != "build":
        raise SystemExit(__doc__)
    site = args[2] if len(args) > 2 else os.path.join(ROOT, "site")
    snapshot = None
    try:
        with open(snap_path, encoding="utf-8") as f:
            snapshot = json.load(f)
    except (OSError, ValueError):
        print(f"geo page: no snapshot at {snap_path}; RPO pairs left out")
    d = build(args[1], site, snapshot=snapshot)
    sizes = {k: os.path.getsize(os.path.join(site, "data", "geo", v["file"])) // 1024 for k, v in d["tracks"].items()}
    print(f"geo page: {len(d['objects'])} objects; tracks KB by window (days): {sizes}; "
          f"{len(d['region']['events'])} events in {EVENT_DAYS} days; {len(d['rpo']['pairs'])} RPO pairs")
    b = d.get("belt") or {}
    if "error" not in b:
        print(f"belt board: {b['objects']} active objects {b['counts']}; {b['close_other_owner_count']} close pairs of "
              f"different owners ({b['close_same_owner_count']} of one owner); orbit changes {b['change_counts']} "
              f"({len(b['not_judged'])} objects not judged)")


if __name__ == "__main__":
    main()
