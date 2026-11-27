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
            "argp", "M", "bstar", "lon"]                # lon: degrees east at the build time (ideas#366)
HELD_DAYS = 320                                   # stays read this far back (+45 days, read_elsets), at most
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
    return {str(o["id"]): {"role": o["role"], "basis": o.get("basis", ""), "sources": _sources(o)}
            for o in d.get("objects", []) if o.get("role") and _opened(o)}


NOT_OPENED = "not opened"  # orbit/notable.py NOT_OPENED: a cited source its reviewer could not open


def _not_opened(s):
    return isinstance(s, list) and len(s) == 3 and s[2] == NOT_OPENED


def _opened(o):
    """At least one of the entry's sources was opened (orbit/notable.py check_roles refuses an entry with none)."""
    return any(not _not_opened(s) for s in o.get("sources", []))


def _sources(o):
    """[label, URL] pairs for the page; a source cited but not opened says so in its label."""
    return [[s[0] + " (not opened)", s[1]] if _not_opened(s) else list(s[:2]) for s in o.get("sources", [])]


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
    rmap = {k: v["role"] for k, v in roles().items()}
    try:
        b = geo_belt.build(objs, elsets, rmap, now.replace(tzinfo=timezone.utc))
    except Exception as e:  # noqa: BLE001: reported on the page and in the log
        print(f"geo page: belt board skipped: {e!r}")
        return {"error": f"{type(e).__name__}: {e}"}
    b["movers"] = movers(objs, elsets, rmap, now)
    return b


def movers(objs, elsets, rmap, now):
    """The relocation tracker (tools/geo_tracker.py, method orbit-2.27) for listed-role objects drifting along the
    belt; `objs` carry the belt board's class. {"error": ...} on a failure, so the board still shows."""
    import geo_tracker
    try:
        return geo_tracker.build(objs, elsets, rmap, now.replace(tzinfo=timezone.utc))
    except Exception as e:  # noqa: BLE001
        print(f"geo page: relocation tracker skipped: {e!r}")
        return {"error": f"{type(e).__name__}: {e}"}


def set_gaps(release, region, elsets, now):
    """Listed-role objects with no public set for 7 days or more, and sets back after such a gap (tools/geo_gaps.py,
    method orbit-2.40), from the element sets and the newest day files' `regions`; {"error": ...} on a failure."""
    import geo_gaps
    try:
        paths = sorted(glob.glob(os.path.join(release, "*.geo-region.json")))
        paths = [p for p in paths if os.path.basename(p)[:10] <= region["day"]][-geo_gaps.READ_DAYS:]

        def docs():
            for p in paths:
                try:
                    with open(p, encoding="utf-8") as f:
                        yield json.load(f)
                except (OSError, ValueError):
                    continue
        rmap = {k: v["role"] for k, v in roles().items()}
        cols = region["object_cols"]
        objs = {o["norad"]: o for o in (dict(zip(cols, row)) for row in region["objects"])}
        return geo_gaps.build(rmap, elsets, geo_gaps.first_reads(docs(), rmap), objs, now.replace(tzinfo=timezone.utc),
                              region.get("fetched_utc"), region["day"])
    except Exception as e:  # noqa: BLE001: reported on the page, in the lead and in the log
        print(f"geo page: element-set gaps skipped: {e!r}")
        return {"error": f"{type(e).__name__}: {e}"}


def add_lead(site, block, data_dir=None):
    """Put the GEO element-set line (orbit/lead.py geo_line, orbit-2.40) into the lead the collect wrote: the site's
    snapshot.json, and the day's lead in the daily archive (data/state/daily_archive.json and the site's copy), when
    that lead is this run's. Returns the line, or None."""
    sys.path.insert(0, ROOT)                           # the orbit package before tools/orbit.py
    from orbit import archive, lead
    path = os.path.join(site, "data", "snapshot.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        snap = json.load(f)
    doc = snap.get("lead")
    if not doc or not doc.get("at"):
        return None
    line = lead.geo_line(block, doc["at"])
    lead.merge_geo(doc, line)
    _replace(path, json.dumps(snap, indent=2, ensure_ascii=False) + "\n")
    for p in ([os.path.join(data_dir, "state", "daily_archive.json")] if data_dir else []) + [os.path.join(site, "data", "archive.json")]:
        try:
            with open(p, encoding="utf-8") as f:
                arc = json.load(f)
        except (OSError, ValueError):
            continue
        kept = ((arc.get("days") or {}).get(doc["at"][:10]) or {}).get("lead") or {}
        if kept.get("at") != doc["at"]:
            continue                                   # the archive holds another run's lead: leave it
        archive.keep_lead(arc, doc)
        _replace(p, json.dumps(arc, ensure_ascii=False, separators=(",", ":")) + "\n")
    return line


def _replace(path, text):
    """Write a whole file or nothing: a failed write never leaves the archive or the snapshot cut short."""
    with open(path + ".part", "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(path + ".part", path)


def catalog_names(site, objs):
    """Other names of each object from the TIC catalog's search index, which the update run unpacks into
    site/data/catalog/ in the step before this one (orbit.py object-data; no request here). {norad: [names]}, only
    objects with another name; {} when the index is missing, so the page builds without them (ideas#360)."""
    sys.path.insert(0, ROOT)
    from orbit import names, namepos
    try:
        with open(os.path.join(site, "data", "catalog", "search.json"), encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        print(f"geo page: no catalog search index ({type(e).__name__}); other names left out")
        return {}
    want = {o[0]: o[1] for o in objs}
    out = {}
    for r in namepos.rows(doc):
        k = str(r.get("key") or "")
        if not k.isdigit() or int(k) not in want:
            continue
        also = names.others(want[int(k)], {"display": r.get("name"), "names": list(r.get("other_names") or [])})
        if also:
            out[int(k)] = also
    return out


def catalog_status(site):
    """{norad: {compact name: (status, until)}} for the names the alias file marks current or former, from the same
    search index as catalog_names; {} when the index is missing or marks none."""
    sys.path.insert(0, ROOT)
    from orbit import namepos
    try:
        with open(os.path.join(site, "data", "catalog", "search.json"), encoding="utf-8") as f:
            doc = json.load(f)
        return {int(k): v for k, v in namepos.statuses(doc).items() if k.isdigit()}
    except (OSError, ValueError, TypeError):
        return {}


def catalog_now(site):
    """{norad: declared current name} from the search index's `now_names` (ideas#379); {} when missing."""
    try:
        with open(os.path.join(site, "data", "catalog", "search.json"), encoding="utf-8") as f:
            doc = json.load(f)
        return {int(k): v for k, v in (doc.get("now_names") or {}).items() if k.isdigit() and v}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def lons_now(region, now):
    """{norad: longitude in degrees east at `now`} from each object's newest set (the `lon` column of globe.json,
    ideas#366: slot search reads it, so the CLI needs no SGP4). An object whose set SGP4 refuses is left out."""
    cols = region["object_cols"]
    out = {}
    for row in region["objects"]:
        r = dict(zip(cols, row))
        try:
            p = earth_fixed(satrec(r), now)
        except Exception as e:  # noqa: BLE001: one object's failure leaves its longitude out, not the page
            print(f"geo page: no longitude for {r.get('norad')} ({type(e).__name__})")
            continue
        if p:
            out[r["norad"]] = round(p[0], 2)
    return out


HOLD_DEG, HOLD_MIN_DAYS, HOLD_GAP_DAYS, HOLD_STALE_DAYS = 0.5, 7, 3, 10


def held_stays(elsets, payloads, first, last):
    """Where each payload held a longitude, from every element set held (ideas#366, "who held this slot and when").
    One sample a day at 12:00 UTC from the set in force (skipped when that set is over HOLD_STALE_DAYS old or drifts
    0.1 deg a day or more, the belt board's line). A stay is a run of such days, none more than HOLD_GAP_DAYS apart,
    each within HOLD_DEG of the run's first day; runs shorter than HOLD_MIN_DAYS are dropped. Rows [norad, first day,
    last day, mean lon, min lon, max lon]. Payloads only: debris and rocket bodies hold no slot."""
    import geo_belt
    days = [first + timedelta(days=k) for k in range((last - first).days + 1)]
    rows = []
    for norad in sorted(payloads):
        sets = elsets.get(norad) or []
        at, cur, sr, samples = -1, None, None, []
        for d in days:
            iso = d.strftime("%Y-%m-%dT%H:%M:%S")
            while at + 1 < len(sets) and sets[at + 1]["epoch"][:19] <= iso:
                at += 1
            if at < 0:
                continue
            s = sets[at]
            if (d - datetime.fromisoformat(s["epoch"][:19])).days > HOLD_STALE_DAYS or abs(geo_belt.drift(s["n"])) >= geo_belt.DRIFT_KEPT:
                continue
            if cur != at:
                sr, cur = satrec(s), at
            p = earth_fixed(sr, d)
            if p:
                samples.append((d, p[0]))
        run = []
        for d, lon in samples + [(None, None)]:
            if d is not None and run and (d - run[-1][0]).days <= HOLD_GAP_DAYS and abs((lon - run[0][1] + 540) % 360 - 180) <= HOLD_DEG:
                run.append((d, lon))
                continue
            if run and (run[-1][0] - run[0][0]).days + 1 >= HOLD_MIN_DAYS:
                l0 = run[0][1]
                offs = [(x - l0 + 540) % 360 - 180 for _, x in run]
                wrap = lambda x: round((x + 540) % 360 - 180, 2)  # noqa: E731
                rows.append([norad, run[0][0].strftime("%Y-%m-%d"), run[-1][0].strftime("%Y-%m-%d"),
                             wrap(l0 + sum(offs) / len(offs)), wrap(l0 + min(offs)), wrap(l0 + max(offs))])
            run = [(d, lon)] if d is not None else []
    return rows


def held_block(release, region, elsets_all, now):
    """globe.json "held": the stays from the first day of the element history to today."""
    cols = region["object_cols"]
    payloads = {r[cols.index("norad")] for r in region["objects"] if r[cols.index("type")] == "PAYLOAD"}
    epochs = [s["epoch"] for v in elsets_all.values() for s in v[:1]]
    if not epochs:
        return {"error": "no element history"}
    first = datetime.fromisoformat(min(epochs)[:10]).replace(hour=12)
    last = now.replace(hour=12, minute=0) if now.hour >= 12 else (now - timedelta(days=1)).replace(hour=12, minute=0)
    rows = held_stays(elsets_all, payloads, first, last)
    return {"from": first.strftime("%Y-%m-%d"), "to": last.strftime("%Y-%m-%d"), "hold_deg": HOLD_DEG,
            "min_days": HOLD_MIN_DAYS, "cols": ["norad", "from", "to", "lon", "lo", "hi"], "rows": rows}


def name_positions(region, objs, other, now, lons=None, status=None):
    """Names that state a longitude ("Eutelsat 12 West G", "EUTE 36B"), each with the object's longitude from its
    newest set at the build time (ideas#361; orbit/namepos.py). Rows [norad, name, stated lon, lon now, degrees
    apart, status, until]; lon now None when SGP4 fails, status and until "" unless the alias file marks the name
    current or former (`status`: catalog_status)."""
    sys.path.insert(0, ROOT)
    from orbit import namepos
    if lons is None:
        lons = lons_now(region, now)
    rows = []
    for o in objs:
        every = [o[1]] + list(other.get(o[0]) or [])
        if not any(namepos.stated_lon(n) for n in every):
            continue
        lon = lons.get(o[0])
        for rec in namepos.positions(every, lon):
            st, until = ((status or {}).get(o[0]) or {}).get(namepos.compact(rec["name"]), ("", ""))
            rows.append([o[0], rec["name"], rec["stated_lon"], lon, rec.get("apart_deg"), st, until])
    return {"tolerance_deg": namepos.TOLERANCE_DEG, "at_utc": now.strftime("%Y-%m-%dT%H:%MZ"),
            "cols": ["norad", "name", "stated_lon", "lon", "apart_deg", "status", "until"], "rows": rows}


def build(release, site, now=None, snapshot=None, data_dir=None):
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
                     round(o["raan"], 4), round(o["argp"], 4), round(o["M"], 4), o.get("bstar") or 0.0, None])
    lons = lons_now(region, now)
    for o in objs:
        o[-1] = lons.get(o[0])
    out_dir = os.path.join(site, "data", "geo")
    os.makedirs(out_dir, exist_ok=True)
    meta = {}
    end = now.replace(minute=now.minute - now.minute % 15)
    elsets = read_elsets(release, end - timedelta(days=max(max(WINDOWS), HELD_DAYS)))
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
    other = catalog_names(site, objs)
    try:
        namepos_block = name_positions(region, objs, other, now, lons, catalog_status(site))
    except Exception as e:  # noqa: BLE001: reported on the page and in the log
        print(f"geo page: name positions skipped: {e!r}")
        namepos_block = {"error": f"{type(e).__name__}: {e}"}
    try:
        held = held_block(release, region, elsets, now)
    except Exception as e:  # noqa: BLE001: reported on the page and in the log
        print(f"geo page: held stays skipped: {e!r}")
        held = {"error": f"{type(e).__name__}: {e}"}
    doc = {"built_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "region_day": region["day"], "owners": owners,
           "elements_fetched_utc": region.get("fetched_utc"), "active_from": region.get("day") if active else None,
           "source": CITE, "definitions": region.get("definitions"), "counts": region.get("counts"),
           "cols": OBJ_COLS, "objects": objs, "tracks": meta, "roles": roles(),
           "region": region_events(release, region["day"]), "rpo": rpo_pairs(snapshot, objs),
           "belt": belt(region, active, elsets, now),
           "names": {str(k): v for k, v in sorted(other.items())},
           "now_names": {str(k): v for k, v in sorted(catalog_now(site).items()) if k in {o[0] for o in objs}},
           "name_positions": namepos_block, "held": held, "set_gaps": set_gaps(release, region, elsets, now)}
    with open(os.path.join(out_dir, "globe.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)
    # the relocation tracker alone, small, for the object pages (method orbit-2.27)
    mv = (doc["belt"] or {}).get("movers") if "error" not in (doc["belt"] or {}) else {"error": doc["belt"]["error"]}
    with open(os.path.join(out_dir, "movers.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(mv or {"error": "not built"}, f, separators=(",", ":"), ensure_ascii=False)
    add_relocations(site, mv)
    doc["lead_line"] = add_lead(site, doc["set_gaps"], data_dir)
    return doc


def add_relocations(site, tracker):
    """Put the relocation items (orbit-2.30, ideas#323) into the feed the build wrote; the check step lints it next."""
    path = os.path.join(site, "data", "feed.geojson")
    if not os.path.exists(path):
        return
    sys.path.insert(0, ROOT)                           # the orbit package before tools/orbit.py
    from orbit import feed
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    feed.merge_relocations(doc, tracker or {})
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


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
    d = build(args[1], site, snapshot=snapshot, data_dir=os.path.dirname(os.path.abspath(snap_path)))
    sizes = {k: os.path.getsize(os.path.join(site, "data", "geo", v["file"])) // 1024 for k, v in d["tracks"].items()}
    npb = d.get("name_positions") or {}
    print(f"names: {len(d['names'])} objects with other names; {len(npb.get('rows') or [])} names state a longitude, "
          f"{sum(1 for r in npb.get('rows') or [] if r[4] is not None and r[4] > npb.get('tolerance_deg', 1))} of them "
          f"more than {npb.get('tolerance_deg')}° from the object")
    hb = d.get("held") or {}
    print(f"held stays: {len(hb.get('rows') or [])} stays of {len({r[0] for r in hb.get('rows') or []})} payloads, "
          f"{hb.get('from')} to {hb.get('to')}" if "error" not in hb else f"held stays: {hb['error']}")
    print(f"geo page: {len(d['objects'])} objects; tracks KB by window (days): {sizes}; "
          f"{len(d['region']['events'])} events in {EVENT_DAYS} days; {len(d['rpo']['pairs'])} RPO pairs")
    sg = d.get("set_gaps") or {}
    if "error" in sg:
        print(f"element-set gaps: {sg['error']}")
    else:
        silent = [o["name"] for o in sg["objects"] if o["silent"]]
        print(f"element-set gaps: {len(silent)} of {len(sg['objects'])} listed-role objects with no public set for "
              f"{sg['quiet_days']} days or more ({', '.join(silent) or 'none'}); {len(sg['back'])} sets back after a gap "
              f"in {sg['back_days']} days; lead line: {(d.get('lead_line') or {}).get('kind') or 'none'}")
    b = d.get("belt") or {}
    if "error" not in b:
        print(f"belt board: {b['objects']} active objects {b['counts']}; {b['close_other_owner_count']} close pairs of "
              f"different owners ({b['close_same_owner_count']} of one owner); orbit changes {b['change_counts']} "
              f"({len(b['not_judged'])} objects not judged)")
        mv = b.get("movers") or {}
        if "error" not in mv:
            print(f"relocation tracker: {len(mv['movers'])} listed-role movers "
                  f"({sum(1 for m in mv['movers'] if m['stale'])} with a stale newest set)")


if __name__ == "__main__":
    main()
