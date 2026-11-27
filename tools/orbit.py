"""Orbit CLI: collect, build, and check.

    python tools/orbit.py collect            # fetch every live lane, write data/snapshot.json
    python tools/orbit.py collect --only catalog
    python tools/orbit.py collect --force    # read GCAT even if its files have not changed
    python tools/orbit.py build              # build site/ from data/snapshot.json
    python tools/orbit.py check              # validate the registers and lint the feed

collect never falls back to made-up data. A lane that fails keeps its last good copy (marked
from_previous) or stays empty, and the snapshot's "lanes" block says which.

Lanes (method orbit-2.7; launch lanes retired in orbit-2.32):
  catalog   GCAT: satcat, satcat100k, auxcat, tmpcat, launch list and launch sites. GCAT republishes once a
            day (about 00:20 UTC), so a run first asks each file's Last-Modified date and downloads nothing
            if none has changed. About 37 MB when it does.
  (The upcoming, news, ledger, navwarn and pairs lanes retired in orbit-2.32: scheduled launches, launch news,
  the launch ledger and launch closures are the suite's Launch program's, launch.theintelligence.company.)
  counterspace  Secure World Foundation's "History of ASAT Testing in Space" sheet (CSV export, CC BY-NC 4.0):
            every test with its debris counts, totals by country, and tests new since the last reading.
  rpo       Secure World Foundation's "History of Robotic Rendezvous and Proximity Operations in Space" sheet
            (CSV export of three data tabs and the About tab, CC BY-NC 4.0): SWF's rows with dates read into
            start, end, precision and ongoing, rows whose dates do not read listed apart, names matched to GCAT.
  maneuver  Space-Track.org (USSPACECOM) element sets for a private watch list: GP once an hour at most, each
            object's history (GP_HISTORY) once only, stored in data/state/spacetrack/. Orbit changes larger than
            each object's own element-set noise (orbit/maneuver.py). Published since Tom approved the disclaimer
            (14 Nov 2026); maneuver.PUBLISH = False holds it off the page again. Off without credentials.
    python tools/orbit.py maneuver-case      # the January 2022 Shijian-21 / BeiDou-2 G2 case, local only
    python tools/orbit.py maneuver-report    # the held report, printed locally
    python tools/orbit.py spacetrack-catalog # Space-Track SATCAT and DECAY, once a day after 17:00 UTC (local)
    python tools/orbit.py catalog            # TIC's satellite catalog from GCAT and Space-Track copies (local)
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from orbit import (aliases, archive, catalog, catshards, catsources, celestrak, satmap, counterspace, feed, fetch, gcat, geo_region, lead, maneuver, names, notable, objpage,  # noqa: E402
                   oscar, oscarlinks, retention, rpo, spacetrack, stcat, tip)
from tic_doctrine import contract, registers  # noqa: E402

LANE_FIELDS = {
    "catalog": ["gcat_updated", "launches", "reentries", "breakups", "hygiene", "catalog_changes", "baseline"],
    "paths": ["payload_sets"],
    "counterspace": ["counterspace"],
    "rpo": ["rpo"],
    "maneuver": ["maneuvers", "reentry_sets"],
    "decay": ["decay"],
    "sats": ["sats"],
}
EMPTY = {"baseline": {}, "gcat_updated": {}, "launches": [], "reentries": [], "breakups": [], "hygiene": {}, "catalog_changes": {},
         "payload_sets": {}, "counterspace": {}, "rpo": {}, "maneuvers": {}, "reentry_sets": {}, "decay": {}, "sats": {}}
ST_DIR = Path("state") / "spacetrack"  # Space-Track sets, kept in the private Actions cache, never published
ST_CLIENT = spacetrack.Client            # replaceable in tests
ST_WAIT = spacetrack.wait_for_clear_minute
ST_SHARED = spacetrack.shared_gp_busy       # geo.yml's GP query on the same account (replaceable in tests)
ST_NOW = lambda: datetime.now(timezone.utc)  # noqa: E731
INDEX = Path("state") / "catalog_index.json.gz"
SATS = Path("state") / "sats.json"  # the satellite map's file (orbit/satmap.py), published at /data/sats.json
SATS_STOP = Path("state") / "sats_stop.json"  # CelesTrak's last non-200, until a person clears it (orbit/satmap.py)
TEXT_SUFFIXES = {".html", ".css", ".js", ".mjs", ".json", ".geojson", ".svg", ".txt", ".md", ".glsl", ".xml"}
ARCHIVE = Path("state") / "daily_archive.json"  # Orbit's own daily counts (orbit/archive.py), published at /data/archive.json
MIN_KEEP = 0.9  # a reading with under 90% of the previous reading's objects fails the lane
# Which register source feeds each lane (doctrine/sources.json), so the page can show each lane's grade.
LANE_SOURCE = {"catalog": ["gcat-mcdowell"], "paths": ["celestrak-gp"], "counterspace": ["swf-counterspace"], "rpo": ["swf-rpo"],
               "maneuver": ["space-track"], "decay": ["space-track"], "sats": ["celestrak-gp-active"]}


def _read_index(data_dir: Path) -> dict | None:
    p = data_dir / INDEX
    if not p.exists():
        return None
    return json.loads(gzip.decompress(p.read_bytes()).decode("utf-8"))


def _write_index(data_dir: Path, doc: dict) -> None:
    p = data_dir / INDEX
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(gzip.compress(json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), 6))


def _lane_catalog(raw_dir: Path, prev: dict, getter, force: bool = False, header=None):
    data_dir = raw_dir.parent
    stamps = {name: (header or fetch.last_modified)(url) for name, url in gcat.URLS.items()}
    prev_lane = (prev.get("lanes") or {}).get("catalog") or {}
    index_doc = _read_index(data_dir)
    if (not force and index_doc and prev_lane.get("last_modified") == stamps
            and prev_lane.get("status") in ("ok", "unchanged")):
        return None, [], stamps  # nothing new: the caller keeps the last reading

    bodies, recs = {}, []
    for name, url in gcat.URLS.items():
        body, rec = fetch.fetch(f"gcat-{name}", url, raw_dir, "tsv", getter=getter, gz=True)
        bodies[name] = body
        recs.append(rec)
    tables = {name: gcat.parse_tsv(bodies[name]) for name in gcat.CATALOGS}
    objs = gcat.objects(tables)
    if index_doc and len(objs) < MIN_KEEP * len(index_doc["objects"]):
        raise RuntimeError(f"GCAT read {len(objs)} objects against {len(index_doc['objects'])} last time; "
                           "refusing a short reading")
    today = gcat.today_utc()
    sites = gcat.sites_table(gcat.parse_tsv(bodies["sites"]))
    orgs = gcat.orgs_table(gcat.parse_tsv(bodies["orgs"]))
    launch_rows = gcat.parse_tsv(bodies["launch"])
    result = {
        "gcat_updated": {name: gcat.updated_stamp(bodies[name]) for name in gcat.URLS},
        "launches": gcat.recent_launches(launch_rows, objs, sites, today, orgs=orgs),
        "baseline": gcat.baseline(launch_rows, objs, orgs, today),
        "reentries": gcat.recent_reentries(objs, today),
        "breakups": gcat.recent_breakups(objs, today),
        "hygiene": gcat.hygiene(objs),
        "catalog_changes": {},
    }
    # When Orbit's reading first listed each breakup (orbit-2.49): GCAT dates breakups late, so the feed's anomaly
    # hold runs from the listing. Carried from the previous snapshot; a first reading has no "before", so it
    # dates each one by GCAT's own breakup date rather than calling the whole record new.
    seen = {b["jcat"]: b.get("first_listed") or f"{b['breakup_date'][:10]}T00:00:00Z"
            for b in prev.get("breakups") or [] if b.get("jcat")}
    for b in result["breakups"]:
        b["first_listed"] = seen.get(b["jcat"]) or (
            recs[0]["fetched_at"] if index_doc else f"{b['breakup_date'][:10]}T00:00:00Z")
    if index_doc:
        result["catalog_changes"] = {"previous_reading_at": index_doc["read_at"],
                                     **gcat.diff(index_doc["objects"], objs, today)}
        # retention (18 Nov 2026): the whole per-object diff, uncut, for the release archive (orbit/retention.py);
        # the published view above keeps its lists at 50
        retention.write_changes(data_dir, retention.changes_lines(
            gcat.diff(index_doc["objects"], objs, today, full=True), recs[0]["fetched_at"], index_doc["read_at"],
            result["gcat_updated"]), recs[0]["fetched_at"])
    _write_index(data_dir, {"read_at": recs[0]["fetched_at"], "gcat_updated": result["gcat_updated"],
                            "objects": gcat.build_index(objs)})
    return result, recs, stamps


def _lane_counterspace(raw_dir: Path, prev: dict, getter, **_):
    """Secure World Foundation's ASAT test history. A test is new when its (country, date, interceptor) was not in
    the previous reading; with no previous reading the list is empty and first_reading says so."""
    body, rec = fetch.fetch("swf-asat", counterspace.URL, raw_dir, "csv", getter=getter)
    doc = counterspace.parse_asat(body)
    prev_cs = prev.get("counterspace") or {}
    previous = prev_cs.get("tests") if prev_cs.get("read_at") else None
    return {"counterspace": {
        "read_at": rec["fetched_at"],
        "updated": doc["updated"],
        "sheet": counterspace.SHEET,
        "report": counterspace.REPORT,
        "tests": doc["tests"],
        "skipped": doc["skipped"],
        "by_country": counterspace.by_country(doc["tests"]),
        "first_reading": previous is None,
        "previous_read_at": prev_cs.get("read_at"),
        "new_since_last": counterspace.new_since(doc["tests"], previous),
    }}, [rec], None


NAMES_URL = f"https://github.com/{geo_region.REPO}/releases/download/{stcat.RELEASE}/{stcat.NAMES_ASSET}"
_RUN: dict = {}  # what one collect run hands from a lane to its end-of-run steps; cleared when collect starts


def _catalog_names(raw_dir: Path, getter) -> tuple[dict | None, dict | None, str | None]:
    """The TIC catalog's name index from the public release `catalog` (one GitHub request): (doc, record, None),
    or (None, None, why) when it cannot be read, so the rpo lane falls back to GCAT's names."""
    try:
        body, rec = fetch.fetch("tic-catalog-names", NAMES_URL, raw_dir, "json", getter=getter, gz=True)
        if body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        doc = json.loads(body.decode("utf-8"))
        if doc.get("schema") != catalog.NAMES_SCHEMA:
            return None, None, f"name index schema {doc.get('schema')!r}, not {catalog.NAMES_SCHEMA}"
        return doc, rec, None
    except Exception as exc:  # noqa: BLE001 - GCAT's names are the fallback
        return None, None, f"TIC catalog name index not read ({type(exc).__name__}: {exc})"


def _lane_rpo(raw_dir: Path, prev: dict, getter, **_):
    """Secure World Foundation's RPO history: one request per data tab, and one for the About tab's date (that
    one may fail alone). Names are matched on the TIC catalog's name index (one request to Orbit's release
    `catalog`) and the alias file (catalog build step 5); if the index cannot be read, on the GCAT index Orbit
    keeps (data/state), with a note."""
    bodies, recs = {}, []
    for tab, spec in rpo.TABS.items():
        bodies[tab], rec = fetch.fetch(f"swf-rpo-{tab}", rpo.EXPORT.format(gid=spec["gid"]), raw_dir, "csv",
                                       getter=getter)
        recs.append(rec)
    try:
        bodies["about"], rec = fetch.fetch("swf-rpo-about", rpo.EXPORT.format(gid=rpo.ABOUT_GID), raw_dir, "csv",
                                           getter=getter)
        recs.append(rec)
    except Exception:  # noqa: BLE001 - the date is shown as unknown
        bodies["about"] = b""
    names_doc, nrec, why = _catalog_names(raw_dir, getter)
    _RUN["names_doc"] = names_doc  # read once a run; the end of collect names the listed orbit changes from it
    if nrec:
        recs.append(nrec)
    entries = aliases.load(source_ids=aliases.source_ids(ROOT))
    doc = rpo.read(bodies, (_read_index(Path(raw_dir).parent) or {}).get("objects"), names_doc, entries)
    return {"rpo": {"read_at": recs[0]["fetched_at"], "sheet": rpo.SHEET, "report": rpo.REPORT,
                    "tabs": {t: s["name"] for t, s in rpo.TABS.items()},
                    "roles": {t: list(s["roles"]) for t, s in rpo.TABS.items()},
                    **({"names_note": why} if why else {}), **doc}}, recs, None


def _st_read(data_dir: Path, name: str, default):
    p = data_dir / ST_DIR / name
    if not p.exists():
        return default
    raw = p.read_bytes()
    return json.loads(gzip.decompress(raw) if name.endswith(".gz") else raw)


def _st_write(data_dir: Path, name: str, doc) -> None:
    p = data_dir / ST_DIR / name
    p.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(doc, separators=(",", ":") if name.endswith(".gz") else None, indent=None if name.endswith(
        ".gz") else 1, ensure_ascii=False).encode("utf-8")
    p.write_bytes(gzip.compress(raw, 6) if name.endswith(".gz") else raw)


def _st_raw(raw_dir: Path, source_id: str, cls: str, body: bytes) -> dict:
    """Hash and keep Space-Track's bytes before anything is derived (git-ignored data/raw). The record names the
    class only: the URL lists the watch list, so it never reaches the snapshot."""
    sha = hashlib.sha256(body).hexdigest()
    dest = raw_dir / source_id
    dest.mkdir(parents=True, exist_ok=True)
    f = dest / f"{sha[:12]}.json.gz"
    if not f.exists():
        f.write_bytes(gzip.compress(body, 6))
    return {"source_id": source_id, "url": spacetrack.REDACTED.format(cls=cls), "sha256": sha, "bytes": len(body),
            "fetched_at": fetch.now_utc()}


REENTRY_MAX = 30  # TIP objects added to the watch list's GP query, soonest first


def _reentry_set(row: dict) -> dict | None:
    """A GP row to the globe's element set for a reentry track (orbit-2.15): the mean elements plus BSTAR and the
    mean-motion rate, since drag shapes a decaying object's track inside its window."""
    try:
        return {"epoch": row["EPOCH"], "n": float(row["MEAN_MOTION"]), "e": float(row["ECCENTRICITY"]),
                "i": float(row["INCLINATION"]), "raan": float(row["RA_OF_ASC_NODE"]),
                "argp": float(row["ARG_OF_PERICENTER"]), "ma": float(row["MEAN_ANOMALY"]),
                "bstar": float(row.get("BSTAR") or 0), "ndot": float(row.get("MEAN_MOTION_DOT") or 0)}
    except (KeyError, TypeError, ValueError):
        return None


def _lane_maneuver(raw_dir: Path, prev: dict, getter, reentry_norads=None, **_):
    """Orbit changes in watched objects (Space-Track GP and GP_HISTORY). Off without credentials or a watch list;
    unchanged (no request) within an hour of the last GP query. From orbit-2.15 the same GP query also asks for
    the objects with an open TIP window (lane `decay`, run first), for the globe's reentry tracks: no extra request.
    Their sets go to snapshot block `reentry_sets` only, never into the watch list's store, history or report."""
    data_dir = raw_dir.parent
    root = data_dir.parent
    cred = spacetrack.credentials(root)
    if not cred:
        raise spacetrack.NotReady("no Space-Track credentials (SPACETRACK_IDENTITY, SPACETRACK_PASSWORD)")
    ids = spacetrack.watch_list(root)
    if not ids:
        raise spacetrack.NotReady("no watch list (ORBIT_WATCH or private/watch.txt)")
    meta = _st_read(data_dir, "meta.json", {})
    store = _st_read(data_dir, "sets.json.gz", {})
    now = ST_NOW()
    if meta.get("last_gp_at"):
        since = (now - datetime.fromisoformat(meta["last_gp_at"].replace("Z", "+00:00"))).total_seconds()
        if since < spacetrack.MIN_GP_GAP_S:
            return None, [], None  # GP once an hour: keep the last reading
    ST_WAIT()
    busy = ST_SHARED(ST_NOW())  # checked after the wait, just before the query
    if busy:
        return None, [], busy  # the account's hourly GP limit: keep the last reading, say why
    client = ST_CLIENT(*cred)
    recs = []
    try:
        extra = [n for n in (reentry_norads or []) if n not in ids][:REENTRY_MAX]
        client.login()
        gp_all = client.query("gp", ids + extra)
        watched_ids = set(ids)
        gp = [r for r in gp_all if int(r.get("NORAD_CAT_ID") or 0) in watched_ids]
        recs.append(_st_raw(raw_dir, "spacetrack-gp", "gp", client.last_body))
        fresh = [i for i in ids if not (store.get(str(i)) or {}).get("history_at")]
        hist = []
        if fresh:  # each object's history once only: Space-Track asks that it be stored, never fetched again
            hist = client.query("gp_history", fresh, spacetrack.history_extra())
            recs.append(_st_raw(raw_dir, "spacetrack-gp-history", "gp_history", client.last_body))
    finally:
        client.logout()
    read_at = maneuver._iso(ST_NOW())
    meta.update({"last_gp_at": read_at, "requests_last_run": client.requests})
    maneuver.merge(store, hist + gp, now)
    for i in fresh:
        store.setdefault(str(i), {"sets": []})["history_at"] = read_at
    _st_write(data_dir, "sets.json.gz", store)
    _st_write(data_dir, "meta.json", meta)
    watched = {str(i): store[str(i)] for i in ids if str(i) in store}
    rep = maneuver.report(watched, now)
    objs = (_read_index(data_dir) or {}).get("objects") or {}
    for ev in rep["events"]:  # GCAT's name and owner beside Space-Track's, as the rest of the page uses
        g = objs.get(f"S{ev['norad']:05d}")
        if g:
            ev.update({"gcat_name": g[4], "state": g[10], "cc": gcat.iso_country(g[10])})
        sets = (store.get(str(ev["norad"])) or {}).get("sets") or []
        if sets:  # the newest set, for the globe's path (orbit-2.11): basic SSA data, cited with the rest of the lane
            s = sets[-1]
            ev["elements"] = {"epoch": s[0], "n": s[1], "e": s[2], "i": s[3], "raan": s[4], "argp": s[5], "ma": s[6]}
    rep.update({"read_at": read_at, "watched": len(ids), "missing": [i for i in ids if str(i) not in store]})
    _st_write(data_dir, "report.json", rep)  # the full report, private
    out = {"attribution": maneuver.ATTRIBUTION, "read_at": read_at, "watched": len(ids), "window_days": rep["window_days"],
           "thresholds": rep["thresholds"], "events": rep["events"],
           "counted_not_listed": {"below_floor": sum(o.get("below_report") or 0 for o in rep["objects"]),
                                  "low_orbit_off_track": sum(o.get("leo_off_track") or 0 for o in rep["objects"])},
           "quiet_or_untracked": sum(1 for o in rep["objects"] if not o["events"]),
           "stale": sum(1 for o in rep["objects"] if (o.get("note") or "").startswith("no new"))}
    want = set(reentry_norads or [])
    sets: dict[str, dict] = {}
    for r in gp_all:  # the newest set of each TIP object (watched ones included: the set says nothing of the list)
        n = int(r.get("NORAD_CAT_ID") or 0)
        el = _reentry_set(r) if n in want else None
        if el and (str(n) not in sets or el["epoch"] > sets[str(n)]["epoch"]):
            sets[str(n)] = el
    resets = {"attribution": maneuver.ATTRIBUTION, "read_at": read_at, "sets": sets,
              "asked": len(want), "missing": sorted(want - {int(k) for k in sets})}
    return {"maneuvers": out, "reentry_sets": resets}, recs, None


def _lane_paths(raw_dir: Path, prev: dict, getter, launches_30d=None, **_):
    """CelesTrak's last-30-days GP group (orbit/celestrak.py): element sets for the payloads of GCAT's recent
    launches, for their paths on the globe. One request a run; CelesTrak's 403 for a repeat download inside one
    of its 2-hour updates keeps the previous sets and is not retried."""
    try:
        body, rec = fetch.fetch("celestrak-gp", celestrak.URL, raw_dir, "json", getter=getter, gz=True)
    except urllib.error.HTTPError as exc:
        if exc.code == 403 and prev.get("payload_sets"):
            return None, [], "CelesTrak: no new GP data since this address's last download (HTTP 403); sets kept"
        raise
    return {"payload_sets": {"read_at": rec["fetched_at"], **celestrak.parse(body, launches_30d or [])}}, [rec], None


def _lane_decay(raw_dir: Path, prev: dict, getter, **_):
    """Space-Track's reentry predictions (TIP, orbit/tip.py): log in, one TIP query, log out. Off without
    credentials. Not GP, so no wait for the shared account's hourly GP query."""
    data_dir = raw_dir.parent
    cred = spacetrack.credentials(data_dir.parent)
    if not cred:
        raise spacetrack.NotReady("no Space-Track credentials (SPACETRACK_IDENTITY, SPACETRACK_PASSWORD)")
    client = ST_CLIENT(*cred)
    try:
        client.login()
        rows = client.query_path(tip.URL, "tip")
        body = client.last_body
    finally:
        client.logout()
    rec = _st_raw(raw_dir, "spacetrack-tip", "tip", body)
    rec["url"] = tip.URL  # no watch list in this query, so the real URL is kept
    objs = (_read_index(data_dir) or {}).get("objects") or {}
    doc = tip.parse(rows, ST_NOW(), objs)
    return {"decay": {"attribution": tip.ATTRIBUTION, "read_at": rec["fetched_at"], **doc}}, [rec], None


def _lane_sats(raw_dir: Path, prev: dict, getter, **_):
    """The satellite map (orbit/satmap.py, orbit-2.23): CelesTrak's active group once a UTC day, joined to this run's
    GCAT index. Any non-200 fails the lane, keeps the last file and stops all requests until a person clears the stop,
    as CelesTrak's policy says; a timeout is not a stop. Under 90% of the last reading's objects fails the lane too."""
    data_dir = raw_dir.parent
    path = data_dir / SATS
    last = (prev.get("sats") or {}).get("read_at") or ""
    now = fetch.now_utc()
    satmap.check_stop(data_dir / SATS_STOP, now)
    if path.exists() and last[:10] == now[:10]:
        return None, [], "CelesTrak's active group was read today already (once a UTC day)"
    try:
        body, rec = fetch.fetch("celestrak-gp-active", satmap.URL, None, "csv", timeout=240, getter=getter or satmap.get)
    except catsources.Refused as exc:
        raise satmap.Stopped(satmap.stop_message(satmap.record_stop(data_dir / SATS_STOP, exc.code, satmap.URL, now))) from exc
    doc = satmap.parse(body, _read_index(data_dir), rec["fetched_at"])
    before = (prev.get("sats") or {}).get("count") or 0
    if path.exists() and doc["count"] < MIN_KEEP * before:
        raise RuntimeError(f"CelesTrak active group read {doc['count']} objects against {before} last time; "
                           "refusing a short reading")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return {"sats": {**satmap.summary(doc), "bytes": path.stat().st_size}}, [rec], None


LANES = {"catalog": _lane_catalog, "paths": _lane_paths,
         "counterspace": _lane_counterspace, "rpo": _lane_rpo, "decay": _lane_decay,
         "maneuver": _lane_maneuver, "sats": _lane_sats}


def collect(root: Path = ROOT, getter=None, header=None, only: list[str] | None = None, force: bool = False) -> dict:
    data_dir = root / "data"
    raw_dir = data_dir / "raw"
    snap_path = data_dir / "snapshot.json"
    prev = json.loads(snap_path.read_text(encoding="utf-8")) if snap_path.exists() else {}
    now = fetch.now_utc()
    snap = {"generated_at": now, "method_version": feed.METHOD, "lanes": {}}
    _RUN.clear()
    for lane, fn in LANES.items():
        fields = LANE_FIELDS[lane]
        prev_lane = (prev.get("lanes") or {}).get(lane) or {}

        def keep_previous():
            for k in fields:
                snap[k] = prev.get(k, EMPTY[k])

        if only and lane not in only:
            keep_previous()
            snap["lanes"][lane] = {**prev_lane, "from_previous": True} if prev_lane else {"status": "not run"}
            continue
        try:
            kwargs = {"force": force, "header": header} if lane == "catalog" else {}
            if lane == "paths":  # read this run's GCAT launches (catalog runs first)
                kwargs = {"launches_30d": snap.get("launches")}
            if lane == "maneuver":  # this run's open TIP windows (decay runs first), soonest first
                kwargs = {"reentry_norads": [o["norad"] for o in (snap.get("decay") or {}).get("objects") or []
                                             if not o.get("passed")]}
            result, recs, stamps = fn(raw_dir, prev, getter, **kwargs)
            if result is None:
                keep_previous()
                snap["lanes"][lane] = {**prev_lane, "status": "unchanged", "checked_at": now, "from_previous": False}
                snap["lanes"][lane].pop("note", None)
                if isinstance(stamps, str):
                    snap["lanes"][lane]["note"] = stamps
                continue
            snap.update(result)
            snap["lanes"][lane] = {"status": "ok", "fetched_at": now, "from_previous": False,
                                   "fetches": [{k: r[k] for k in ("url", "sha256", "bytes")} for r in recs]}
            if stamps:
                snap["lanes"][lane]["last_modified"] = stamps
        except spacetrack.NotReady as exc:
            for k in fields:
                snap[k] = EMPTY[k]
            snap["lanes"][lane] = {"status": "off", "reason": str(exc), "checked_at": now}
        except Exception as exc:
            had = bool(prev_lane.get("fetched_at"))
            for k in fields:
                snap[k] = prev.get(k, EMPTY[k]) if had else EMPTY[k]
            snap["lanes"][lane] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300],
                                   "failed_at": now, "from_previous": had, "fetched_at": prev_lane.get("fetched_at"),
                                   "last_modified": prev_lane.get("last_modified")}
    if not maneuver.PUBLISH:  # held: the lane's record and output stay in the private state, off the snapshot
        held = {"lane": snap["lanes"].pop("maneuver", None), "maneuvers": snap.pop("maneuvers", None)}
        if prev.get("maneuvers") or (prev.get("lanes") or {}).get("maneuver"):
            held["note"] = "dropped from a snapshot written while PUBLISH was on"
        _st_write(data_dir, "held_lane.json", held)
    _describe_changes(root, data_dir, snap)
    data_dir.mkdir(parents=True, exist_ok=True)
    snap["archive"] = _archive_run(data_dir, snap, getter)
    snap_path.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return snap


def _roles(root: Path) -> dict[int, dict]:
    """The GEO page's role list (site_src/geo_roles.json: each entry cites published reporting), by catalog number."""
    path = root / "site_src" / "geo_roles.json"
    return notable.roles_index(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else {}


def _describe_changes(root: Path, data_dir: Path, snap: dict) -> None:
    """End of every collect (orbit-2.26): each listed orbit change gets the other names its object goes by (the
    name index the rpo lane read on this run; none read, names from an earlier run stay), and a GEO change gets
    what happened in words and the notable mark (orbit/notable.py). New and carried changes alike; no request.
    Only objects with a listed change are looked up in the private store."""
    events = (snap.get("maneuvers") or {}).get("events") or []
    if not events:
        return
    store = _st_read(data_dir, "sets.json.gz", {})
    wanted = {str(e.get("norad")) for e in events}
    names_doc = _RUN.get("names_doc")
    notable.enrich(events, {k: v for k, v in store.items() if k in wanted}, _roles(root),
                   names.index(names_doc) if names_doc else None)


def _archive_run(data_dir: Path, snap: dict, getter=None) -> dict:
    """Add this run to Orbit's daily archive (orbit/archive.py) and return its summary for the page.

    The archive lives in data/state/ (the Actions cache). When that copy is missing, the published copy is read
    back from Orbit's own site (one request) and merged, so a lost cache entry does not start the archive over.
    A failed read of the published copy starts from what is local and says so. From orbit-2.17 it also sets
    snap['tip_check']: the archive's TIP messages against TIP's and GCAT's reentry times (tip.check). From
    orbit-2.18 it sets snap['lead'] (orbit/lead.py) and keeps the day's last lead in the archive."""
    path = data_dir / ARCHIVE
    local = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    note = None
    if local is None:
        try:
            local = archive.merge(None, json.loads((getter or fetch.get)(archive.PUBLIC_URL, 30).decode("utf-8")))
            note = "restored from the published copy"
        except Exception as exc:  # noqa: BLE001 - a first run, or the site unreachable: start locally
            note = f"no local or published copy read ({type(exc).__name__}); started here"
    doc = archive.record(local, snap)
    at = datetime.fromisoformat(snap["generated_at"].replace("Z", "+00:00"))
    msgs = archive.tip_messages(doc)
    snap["tip_check"] = tip.check(msgs, snap.get("reentries") or [], at,
                                  (_read_index(data_dir) or {}).get("objects") or {}) if msgs else {}
    # the GEO element-set line comes later in the run (tools/geo_page.py, orbit-2.40); until then the lead says so
    snap["lead"] = lead.merge_geo(lead.build(snap, doc), dict(lead.GEO_PENDING))
    archive.keep_lead(doc, snap["lead"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    out = archive.summary(doc, at.date())
    if note:
        out["note"] = note
    return out


def world_shapes(countries: dict, step: float = 0.1) -> dict:
    """Every country outline from the kit's Natural Earth admin-0 file (public domain), snapped to `step` degrees:
    the map's land at world zoom, and its whole base map when OpenFreeMap can't be reached (Blackout's)."""
    feats = []
    for c in countries["countries"]:
        polys = []
        for ring in c["rings"]:
            out = []
            for x, y in ring:
                pt = [round(round(x / step) * step, 2), round(round(y / step) * step, 2)]
                if not out or out[-1] != pt:
                    out.append(pt)
            if len(out) >= 4:
                if out[0] != out[-1]:
                    out.append(out[0])
                polys.append([out])
        if polys:
            feats.append({"type": "Feature", "properties": {"cc": c["cc"]},
                          "geometry": {"type": "MultiPolygon", "coordinates": polys}})
    return {"type": "FeatureCollection", "source": countries["source"] + f"; snapped to {step} degrees for world zoom",
            "features": feats}


def sources_doc(root: Path = ROOT) -> dict:
    """The ingested sources from the register, each with its Admiralty grade spelled out, for the page."""
    reg = json.loads((root / "doctrine" / "sources.json").read_text(encoding="utf-8"))
    vocab = json.loads((root / "doctrine" / "kit" / "vocab" / "grading.json").read_text(encoding="utf-8"))
    adm = vocab["admiralty"]
    lanes_of: dict[str, list[str]] = {}
    for lane, sids in LANE_SOURCE.items():
        for sid in sids:
            lanes_of.setdefault(sid, []).append(lane)
    out = []
    for src in reg["sources"]:
        if src.get("use") != "ingest":
            continue
        grade = src.get("grade") or ""
        rel, cred = (grade[:1], grade[1:]) if len(grade) == 2 else ("", "")
        out.append({"id": src["id"], "name": src["name"], "url": src["url"], "licence": src.get("licence", ""),
                    "grade": grade, "reliability": adm["reliability"].get(rel, ""),
                    "credibility": adm["credibility"].get(cred, ""), "lanes": lanes_of.get(src["id"], [])})
    return {"basis": adm["basis"], "sources": out}


def build_site(root: Path = ROOT, snapshot: dict | None = None) -> dict[str, str]:
    snap_path = root / "data" / "snapshot.json"
    if snapshot is None:
        if not snap_path.exists():
            raise SystemExit("No data/snapshot.json. Run `python tools/orbit.py collect` first; "
                             "Orbit does not build from made-up data.")
        snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
    feed_doc = feed.build_feed(snapshot)

    def dump(obj) -> str:
        return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"

    countries = json.loads((root / "doctrine" / "kit" / "geo" / "countries.json").read_text(encoding="utf-8"))
    files = {"data/snapshot.json": dump(snapshot), "data/feed.geojson": dump(feed_doc),
             "data/sources.json": dump(sources_doc(root)),
             "data/archive.json": (root / "data" / ARCHIVE).read_text(encoding="utf-8")
             if (root / "data" / ARCHIVE).exists() else dump(archive.empty()),
             "data/world.geojson": json.dumps(world_shapes(countries), separators=(",", ":")) + "\n"}
    # The globe's Cesium ion token (orbit-2.11): a public, read-only token restricted to Orbit's hosts, from the
    # repository variable CESIUM_ION_TOKEN; without it the globe uses Cesium's own Natural Earth imagery.
    files["data/cesium.json"] = dump({"token": os.environ.get("CESIUM_ION_TOKEN") or None})
    # Notable orbit changes (orbit-2.26), for readers and tools that want only those: orbit/notable.py.
    files["data/notable.json"] = dump(notable.public(snapshot, _roles(root), feed.SITE))
    # ITU filings linked to objects by review (orbit-2.42, doctrine/itu-filings.md): reviewed entries of
    # orbit/data/catalog/itu-links.yml only, per object; no ITU table is published. A bad entry stops the build.
    from orbit import itu
    files["data/itu-links.json"] = dump(itu.public_links(itu.load_links(root / "orbit" / "data" / "catalog" / "itu-links.yml"),
                                                         snapshot.get("generated_at") or ""))
    # Names registered with the United Nations (orbit-2.50): reviewed entries of orbit/data/catalog/un-register.yml
    # only, by COSPAR id; no register table is published. A bad entry stops the build.
    from orbit import unregister
    files["data/un-register.json"] = dump(unregister.public_names(
        unregister.load_entries(root / "orbit" / "data" / "catalog" / "un-register.yml"),
        snapshot.get("generated_at") or ""))
    # The satellite map's file (orbit-2.23), as the sats lane last wrote it; without one the map says so.
    if (root / "data" / SATS).exists():
        files["data/sats.json"] = (root / "data" / SATS).read_text(encoding="utf-8")
    src_dir = root / "site_src"
    binary = {}
    if src_dir.exists():
        for p in sorted(src_dir.rglob("*")):
            if p.is_file():
                rel = p.relative_to(src_dir).as_posix()
                if p.suffix.lower() in TEXT_SUFFIXES or p.name == "_headers":
                    files[rel] = p.read_text(encoding="utf-8")
                else:  # images, wasm and the like in vendor/ (CesiumJS): copied byte for byte
                    binary[rel] = p
    out_dir = root / "site"
    out_dir.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8", newline="\n")
    for rel, src in binary.items():
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        if not dest.exists() or dest.read_bytes() != data:
            dest.write_bytes(data)
    return files


SHARDS_URL = f"https://github.com/{geo_region.REPO}/releases/download/{stcat.RELEASE}/{objpage.ASSET}"


SEARCH_URL = "https://orbit.theintelligence.company/data/catalog/search.json"


GEO_URL = "https://orbit.theintelligence.company/data/geo/globe.json"


def _slot_objects(globe: dict, search: dict) -> list[dict]:
    """The GEO page's objects (longitude now, region, drift) with every catalog name, plus every other catalog object
    (no longitude: not near GEO, or gone) so names that state a slot are found wherever their object is."""
    from orbit import namepos
    cols = globe.get("cols") or []
    idx = {str(r.get("key")): r for r in namepos.rows(search)}
    out, near = [], set()
    for row in globe.get("objects") or []:
        o = dict(zip(cols, row))
        r = idx.get(str(o["norad"])) or {}
        extra = list((globe.get("names") or {}).get(str(o["norad"])) or [])
        names = [n for n in [r.get("name")] + list(r.get("other_names") or []) + extra if n and n != o["name"]]
        out.append({"norad": o["norad"], "name": o["name"], "names": names, "lon": o.get("lon"), "region": o.get("region"),
                    "drift": namepos.drift_of(o["n"]), "active": bool(o.get("active")), "gone": False})
        near.add(str(o["norad"]))
    for k, r in idx.items():
        if k in near or not k.isdigit():
            continue
        out.append({"norad": int(k), "name": r.get("name") or k, "names": list(r.get("other_names") or []), "lon": None,
                    "region": None, "drift": None, "active": False, "gone": bool(r.get("gone"))})
    return out


def find_slot(slot: float, query: str, search: dict, geo: str | None = None, window: float | None = None,
              getter=None, itu: bool = False, refresh: bool = False, itu_io: dict | None = None) -> int:
    """`orbit.py find 12.5W`: who is within `window` of a GEO slot now (the GEO page's longitudes at its build time),
    who carries a name that states the slot, and who held it since the GEO element history starts (ideas#366)."""
    from orbit import namepos
    from orbit import itu as _itu
    itu_window = _itu.WINDOW_DEG if window is None else window
    window = namepos.WINDOW_DEG if window is None else window
    if geo:
        raw, gwhere = Path(geo).read_bytes(), geo
    else:
        raw, gwhere = (getter or fetch.get)(GEO_URL), GEO_URL
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    globe = json.loads(raw.decode("utf-8"))
    if "lon" not in (globe.get("cols") or []):
        print(f"{gwhere} has no longitudes yet (built before ideas#366): names only.")
    held = globe.get("held") or {}
    res = namepos.at_slot(_slot_objects(globe, search), slot, window, held=held.get("rows"))
    known = namepos.statuses(search)
    lt, rw = namepos.lon_txt, namepos.REGION_WORD
    print(f"Slot {lt(slot)} (read from {query!r}); GEO page {gwhere} built {globe.get('built_utc')}, catalog read {search.get('read')}.")
    print(f"There now, within {window:g}° ({len(res['there'])}):")
    for o in res["there"]:
        mv = ("holding its longitude" if abs(o["drift"]) < 0.1 else
              f"drifting {abs(o['drift']):.2f}° a day {'west' if o['drift'] < 0 else 'east'}")
        act = ", active (CelesTrak)" if o["active"] else ""
        print(f"  {o['norad']:>7}  {o['name']:<34} {lt(o['lon']):>8}  {rw.get(o['region'], o['region'] or '')}, {mv}{act}")
    if not res["there"]:
        print("  none")
    print(f"Named for it, within {res['named_tol']:g}° ({len(res['named'])}); a name is not a position, and most such "
          "names are former names:")
    for o in res["named"]:
        if o["lon"] is not None:
            now = (f"now at {lt(o['lon'])}, " + ("there now" if o["there_now"] else f"{namepos.apart(o['lon'], slot):.1f}° away") +
                   f" ({rw.get(o['region'], o['region'] or '')})")
        else:
            now = "left orbit" if o["gone"] else "not near GEO on the GEO page"
        said = "; ".join(namepos.marked(n, known.get(str(o["norad"]))) for n in o["slot_names"])
        print(f"  {o['norad']:>7}  {o['name']:<34} {said} -> {now}")
    if not res["named"]:
        print("  none")
    if "rows" in held:
        print(f"Held it since {held['from']} ({len(res['held'])}): payloads holding a longitude within {held['hold_deg']:g}° "
              f"for {held['min_days']} days or more, mean longitude within {window:g}° of the slot; the record ends {held['to']}:")
        for s in res["held"]:
            to = "now" if s["to"] == held["to"] else s["to"]
            print(f"  {s['norad']:>7}  {s['name']:<34} {s['from']} to {to}, at {lt(s['lon'])}")
        if not res["held"]:
            print("  none")
    else:
        print("Held it: not on the GEO page yet" + (f" ({held['error']})" if held.get("error") else "") + ".")
    if "." not in query:
        print("Names round a slot to the whole degree (Eutelsat's \"12 West\" is 12.5° W), so a whole-degree query may "
              "mean the half degree beside it: widen with --window 1.")
    filed = find_itu(slot, itu_window, refresh, **(itu_io or {})) if itu else 0
    if not itu:
        print("ITU filings for the slot: add --itu (asks ITU Space Explorer; method orbit-2.42).")
    print("Object pages: https://orbit.theintelligence.company/object.html?n=<NORAD>; the GEO page's search takes the same "
          "slot forms.")
    return 0 if res["there"] or res["named"] or res["held"] or filed else 1


def find_itu(slot: float, window: float, refresh: bool = False, poster=None, getter=None, pacer=None,
             cache_dir: Path | None = None) -> int:
    """`orbit.py find 12.5W --itu` (orbit-2.42, doctrine/itu-filings.md): the ITU's active GEO notices filed for
    the slot and its Resolution 40 statements, asked of ITU Space Explorer on this request only (cached a week in
    git-ignored data/raw/itu/). Local use: nothing here is published. Returns how many networks and statements
    it printed."""
    from orbit import itu, namepos
    lt = namepos.lon_txt
    cache = ROOT / "data" / "raw" / "itu" if cache_dir is None else (cache_dir or None)  # False: no cache (tests)
    pacer = pacer or itu._Pacer()
    try:
        got = itu.slot_notices(slot, window, cache, refresh, poster=poster, pacer=pacer)
    except (OSError, ValueError) as exc:
        print(f"ITU filings: Space Explorer did not answer ({type(exc).__name__}: {exc}); nothing shown, nothing assumed.")
        return 0
    nets = itu.networks(got["rows"])
    nets.sort(key=lambda g: (namepos.apart(g["lon"], slot) if g["lon"] is not None else 999, g["network"]))
    how = "cached copy of " if got["cached"] else ""
    print(f"Filed for {lt(slot)} at the ITU ({len(nets)} networks, {got['total']} active GEO notices with a nominal "
          f"longitude within {window:g}°; Space Explorer, {how}read {got['read']}):")
    print("  " + itu.NETWORK_NOTE)
    for g in nets:
        steps = "; ".join(dict.fromkeys(f"{n['what']} received {n['received'] or '?'}" for n in g["notices"]))
        where = lt(g["lon"]) if g["lon"] is not None else "longitude not given"
        print(f"  {g['network']:<24} {g['filer']:<8} {where:>8}  {steps}")
        print(f"  {'':<24} {g['notices'][-1]['link']}")
    if not nets:
        print("  none")
    if len(got["rows"]) < got["total"]:
        print(f"  Only {len(got['rows'])} of {got['total']} notices were read (page limit); narrow --window.")
    try:
        r40 = itu.res40_table(cache, refresh, getter=getter, pacer=pacer)
    except (OSError, ValueError) as exc:
        print(f"Resolution 40: the table did not load ({type(exc).__name__}: {exc}).")
        return len(nets)
    at = itu.res40_at(r40["rows"], slot, window)
    how = "cached copy of " if r40["cached"] else ""
    print(f"Resolution 40 statements for {lt(slot)} ({how}the ITU table read {r40['read']}):")
    print("  " + itu.RES40_NOTE)
    for x in at["in"]:
        frm = (f"; the station came from {lt(x['prev_lon'])} ({x['prev_network']}), left {x['left_prev'] or '?'}"
               if x["moved"] and x["prev_lon"] is not None else "; not moved from another filing's slot")
        print(f"  in position  {x['network']:<24} {x['adm']:<5} at {lt(x['lon'])} from {x['in_position'] or '?'} "
              f"({itu.provision(x['prov'])}){frm}")
    for x in at["out"]:
        print(f"  left it      {x['prev_network'] or '?'} at {lt(x['prev_lon'])}, left {x['left_prev'] or '?'}: the "
              f"station went to {x['network']} ({x['adm']}) at {lt(x['lon'])}, in position {x['in_position'] or '?'}")
    if not at["in"] and not at["out"]:
        print("  none")
    print("  Matching a filing or a statement to a satellite is TIC's inference, never the ITU's: compare the dates "
          "with the GEO record above, and record a link only by review in orbit/data/catalog/itu-links.yml.")
    print(f"  Source: {itu.CREDIT}. Not published by Orbit.")
    return len(nets) + len(at["in"]) + len(at["out"])


def find_name(query: str, index: str | None = None, limit: int = 10, getter=None, geo: str | None = None,
              window: float | None = None, itu: bool = False, refresh: bool = False, itu_io: dict | None = None) -> int:
    """`orbit.py find`: every name from every source in the catalog's search index, matched loosely
    (orbit/namepos.py), so a session looks here before the web. The hand-kept alias file is only the reviewed links;
    the index holds Space-Track's, GCAT's, CelesTrak's, Wikidata's, WMO OSCAR's and the aliases' names."""
    from orbit import namepos
    try:
        sys.stdout.reconfigure(errors="replace")  # a Windows console cannot print every name
    except AttributeError:
        pass
    if index:
        raw = Path(index).read_bytes()
        where = index
    else:
        raw = (getter or fetch.get)(SEARCH_URL)
        where = SEARCH_URL
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    doc = json.loads(raw.decode("utf-8"))
    slot = namepos.parse_slot(query)
    if slot is not None:
        return find_slot(slot, query, doc, geo, window, getter, itu, refresh, itu_io)
    hits = namepos.find(doc, query, limit)
    print(f"{len(hits)} match{'es' if len(hits) != 1 else ''} for {query!r} in {where} (catalog read {doc.get('read')}):")
    known = namepos.statuses(doc)
    for h in hits:
        others = list(h.get("other_names") or [])
        gone = " (left orbit)" if h.get("gone") else ""
        mine = known.get(str(h["key"]))
        print(f"  {h['key']:>7}  {h.get('cospar') or '':<10}  {namepos.marked(h.get('name') or '', mine)}{gone}")
        if others:
            print(f"           also: {'; '.join(namepos.marked(n, mine) for n in others)}")
        stated = [p for p in namepos.positions([h.get("name") or ""] + others, None)]
        if stated:
            print("           names that state a slot: " + "; ".join(f"{p['name']} = named for {namepos.named_txt(p['stated_lon'])}" for p in stated))
    if any(namepos.positions([h.get("name") or ""] + list(h.get("other_names") or []), None) for h in hits):
        print("Names give a slot to the whole degree (Eutelsat's \"12 West\" is 12.5° W); a slot name is often a former name.")
    if hits:
        print("Each object's page lists which source gives which name: https://orbit.theintelligence.company/object.html?n=<NORAD>")
    return 0 if hits else 1


def object_data(site_dir: Path, getter=None) -> int:
    """Object pages (orbit-2.20): the catalog's shards, search index and rules note from the public release
    `catalog` (one GitHub request) into site/data/catalog/. A missing or refused archive leaves the folder as it
    was and returns 0, so the deploy goes ahead; the page then says the catalog is not on the site yet."""
    try:
        body, rec = fetch.fetch("tic-catalog-shards", SHARDS_URL, None, "tar.gz", timeout=180, getter=getter)
        man = objpage.unpack(body, Path(site_dir) / "data", fetched={k: rec[k] for k in ("url", "sha256", "bytes", "fetched_at")})
    except Exception as exc:  # noqa: BLE001 - the page works without it and says so
        print(f"::warning::object pages: catalog shards not unpacked ({type(exc).__name__}: {exc})")
        return 0
    print(f"Object pages: {man['shards']} shards, {man['objects']:,} objects in the search index, catalog read {man['catalog_read']}, "
          f"{man['bytes'] / 1e6:.1f} MB unpacked.")
    return 0


def check_all(root: Path = ROOT) -> list[str]:
    errs = registers.check(root / "doctrine")
    regs = registers.ids(root / "doctrine")
    roles_path = root / "site_src" / "geo_roles.json"
    if roles_path.exists():
        errs += notable.check_roles(json.loads(roles_path.read_text(encoding="utf-8")))
    feed_path = root / "site" / "data" / "feed.geojson"
    if not feed_path.exists():
        return errs + ["site/data/feed.geojson is missing: run collect and build first"]
    feed_doc = json.loads(feed_path.read_text(encoding="utf-8"))
    for feat in feed_doc.get("features", []):
        fid = (feat.get("properties") or {}).get("id", "?")
        for std, sev, msg in contract.check(feat, regs):
            if sev == "error":
                errs.append(f"{fid}: {std}: {msg}")
    return errs


CASE = {"ids": [49330, 34779], "from": "2021-12-01", "to": "2022-03-01", "file": "case_sj21_2022.json.gz",
        "now": "2022-03-01T00:00:00Z", "window_days": 90}
_NASA = "https://www.nasa.gov/blogs/stationreport/2024/"
# The ISS (25544), 15 Jan to 1 Jun 2024: the reboosts NASA's ISS Daily Summary Reports announced (US public domain),
# each as the span NASA's words allow, in UTC (the reports keep US Central time). Read 15 Nov 2026; the reports
# found may not list every manoeuvre, so an extra mark is "not in this list", not a false mark.
CASE_ISS = {"ids": [25544], "from": "2024-01-15", "to": "2024-06-01", "file": "case_iss_2024.json.gz",
            "now": "2024-06-01T00:00:00Z", "window_days": 138, "tolerance_h": 12,
            "announced": [
                {"label": "27 Jan, Progress 85P", "from": "2024-01-27T11:39:00Z", "to": "2024-01-27T11:39:00Z",
                 "dv_ms": None, "said": "27 Jan, 5:39 AM CST", "url": _NASA + "01/29/"},
                {"label": "23 Feb, Progress 87P", "from": "2024-02-23T06:00:00Z", "to": "2024-02-24T06:00:00Z",
                 "dv_ms": 1.725, "said": "Friday 23 Feb, no time",
                 "url": _NASA + "02/26/iss-daily-summary-report-2-26-2024/"},
                {"label": "14 Mar, Progress 87P", "from": "2024-03-14T13:11:00Z", "to": "2024-03-14T13:11:00Z",
                 "dv_ms": 1.59, "said": "8:11 AM CDT", "url": _NASA + "03/14/iss-daily-summary-report-3-14-2024/"},
                {"label": "25-26 Apr, Progress 87P", "from": "2024-04-25T23:00:00Z", "to": "2024-04-26T13:00:00Z",
                 "dv_ms": None, "said": "overnight, report of 26 Apr",
                 "url": _NASA + "04/26/iss-daily-summary-report-4-26-2024/"},
                {"label": "24 May, Cygnus NG-20 (two burns)", "from": "2024-05-24T05:00:00Z",
                 "to": "2024-05-25T05:00:00Z", "dv_ms": 2.26, "said": "today, report of 24 May",
                 "url": _NASA + "05/24/iss-daily-summary-report-5-24-2024/"}],
            # the G5 geomagnetic storm (NOAA SWPC): from about 17 UTC on 10 May; drag, not a manoeuvre
            "storm": {"label": "G5 storm, 10-12 May 2024", "from": "2024-05-10T12:00:00Z", "to": "2024-05-13T00:00:00Z"}}
# Luch (Olymp) 2 (55841, 2023-031A), from launch to the read: its relocations along the GEO belt, the calibration
# for the relocation tracker (ideas#248, #256). Read once on 24 Nov 2026 on Tom's word; Orbit's own GEO sets start
# 1 Jul 2026. Stop table and profiles: tools/geo_relocations.py, docs/validation/luch2-relocations.md.
CASE_LUCH2 = {"ids": [55841], "from": "2023-03-01", "to": "2026-11-25", "file": "case_luch2_2023.json.gz",
              "now": "2026-11-25T00:00:00Z", "window_days": 1365, "keep_days": 1400}
CASES = {"sj21": CASE, "iss": CASE_ISS, "luch2": CASE_LUCH2}


def print_report(rep: dict) -> None:
    for o in rep["objects"]:
        g = o.get("geo") or {}
        print(f"{o['norad']:>6} {str(o.get('name'))[:24]:24s} {str(o.get('regime')):4s} sets {o['sets']:4d}  "
              f"last {o.get('last_epoch')}  gap max {o.get('max_gap_h')} h  noise {o.get('noise_ms')}"
              + (f"  lon {g['lon']} drift {g['drift_deg_day']}/day" if g else "") + (f"  [{o['note']}]" if o.get("note") else ""))
        for e in o["events"]:
            gg = e.get("geo") or {}
            print(f"         {e['from']} -> {e['to']}  {e['dv_ms']:8.3f} m/s (sma {e.get('dv_sma_ms')}) {e['dominant']:12s} da {e['da_km']} km "
                  f"di {e['di_deg']} deg z {e['z']} ({e['pairs']} pairs)"
                  + (f"  lon {gg['lon_before']} -> {gg['lon_after']}, drift {gg['drift_before']} -> {gg['drift_after']}"
                     if gg else ""))


def print_score(sc: dict, case: dict) -> None:
    print(f"Scored against {len(case['announced'])} announced reboosts, within {case['tolerance_h']} h:")
    for h in sc["announced"]:
        got = "; ".join(f"{e['from']} -> {e['to']} {e['dv_ms']} m/s (sma {e.get('dv_sma_ms')}) {e['dominant']} da {e['da_km']} km"
                        for e in h["events"]) or "MISSED"
        print(f"  {h['label']:34s} NASA {h['dv_ms'] if h['dv_ms'] is not None else 'n/a':>5} m/s  {got}")
    st = case.get("storm")
    print(f"  hits {sc['hits']} of {len(sc['announced'])}, misses {sc['misses']}, marks not in the list "
          f"{len(sc['extra'])}" + (f" ({len(sc['in_storm'])} inside the {st['label']})" if st else ""))
    for e in sc["extra"]:
        tag = "  [storm]" if e in sc["in_storm"] else ""
        print(f"    extra {e['from']} -> {e['to']} {e['dv_ms']} m/s {e['dominant']} da {e['da_km']} km{tag}")


def maneuver_case(root: Path = ROOT, name: str = "sj21") -> int:
    """A known case from Space-Track GP_HISTORY: one request the first time, stored in data/state/spacetrack/ and
    never asked for again. sj21: Shijian-21 (49330) and BeiDou-2 G2 (34779), 1 Dec 2021 to 1 Mar 2022. iss: the ISS
    (25544), 15 Jan to 1 Jun 2024, scored against NASA's announced reboosts and the 10-12 May 2024 storm."""
    CASE = CASES[name]
    data_dir = root / "data"
    records = _st_read(data_dir, CASE["file"], None)
    if records is None:
        cred = spacetrack.credentials(root)
        if not cred:
            print("No Space-Track credentials: set SPACETRACK_IDENTITY and SPACETRACK_PASSWORD in .env first.")
            return 1
        ST_WAIT()
        client = ST_CLIENT(*cred)
        try:
            client.login()
            records = client.query("gp_history", CASE["ids"], f"/EPOCH/{CASE['from']}--{CASE['to']}")
        finally:
            client.logout()
        _st_write(data_dir, CASE["file"], records)
    store = maneuver.merge({}, records, datetime.fromisoformat(CASE["now"].replace("Z", "+00:00")),
                           keep_days=CASE.get("keep_days", 400))
    rep = maneuver.report(store, datetime.fromisoformat(CASE["now"].replace("Z", "+00:00")), CASE["window_days"])
    print(f"{len(records)} element sets, Space-Track (USSPACECOM). Thresholds {rep['thresholds']}.")
    print_report(rep)
    if CASE.get("announced"):
        print_score(maneuver.score(rep["events"], CASE["announced"], CASE["tolerance_h"], CASE.get("storm")), CASE)
    return 0


def _tic_archive(lane: str, src) -> None:
    """A dated copy of the files in folder `src` in the private archive (tools/tic_archive.py: release
    orbit-<lane>-YYYY-MM of metacog-osint/tic-archive, nothing replaced there), with the archive's own token
    TIC_ARCHIVE_TOKEN. Raises ReleaseError when the copy fails."""
    token = os.environ.get("TIC_ARCHIVE_TOKEN", "")
    if not token:
        raise geo_region.ReleaseError("secret TIC_ARCHIVE_TOKEN is not set, so nothing can go to the private archive")
    r = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "tic_archive.py"), "put",
                        "--program", "orbit", "--lane", lane, "--src", str(src)], env={**os.environ, "GH_TOKEN": token})
    if r.returncode:
        raise geo_region.ReleaseError(f"the copy to the private archive (lane {lane}) failed")


GEO_ARCHIVE = _tic_archive  # (lane, folder) -> None, raises on failure; replaceable in tests
CATALOG_ARCHIVE = _tic_archive  # the same, for catalog.yml's copies (lane catalog-release)


def _archive_files(archive, lane: str, files: dict) -> None:
    """{asset name: local path} into a fresh folder, then `archive(lane, folder)`: the folder holds exactly those
    files under their release names, so a later copy of the same release files shares their bytes."""
    with tempfile.TemporaryDirectory(prefix=f"{lane}-") as tmp:
        for name, p in files.items():
            shutil.copyfile(p, Path(tmp) / name)
        archive(lane, tmp)


def geo_pull(day: str, out: Path, upload: bool, getter=None) -> int:
    """The GEO region (orbit/geo_region.py; workflow geo.yml): one Space-Track gp query for every object near GEO,
    one CelesTrak request for its active GEO list, today's region file and the monthly element files, uploaded to
    the public release geo-YYYY. Skips, with a note and exit 0, when the shared account's hourly gp limit could be
    broken (Orbit's update run) or today's file was pulled under an hour ago.

    An upload never loses what the releases hold. Exit 1, with nothing uploaded, when a file a release holds does
    not download whole, a past month's file is missing from its release, an upload would drop an element set the
    release holds, or a copy to the private tic-archive fails: each gp reply goes there (lane geo-reply) before
    anything else, and every release file before it is replaced and as it is uploaded (lane geo-release)."""
    out.mkdir(parents=True, exist_ok=True)
    try:
        return _geo_pull(day, out, upload, getter)
    except geo_region.ReleaseError as exc:
        print(f"::error::GEO region: {exc}. Nothing uploaded.")
        return 1


def _geo_pull(day: str, out: Path, upload: bool, getter) -> int:
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if upload:
        geo_region.release_get([f"{day}.geo-region.json", f"{geo_region.yesterday(day)}.geo-region.json"], str(out))
    held = geo_region.load_region(str(out), day)
    if held and held.get("fetched_utc"):
        since = ST_NOW() - datetime.strptime(held["fetched_utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
        if since.total_seconds() < spacetrack.MIN_GP_GAP_S:
            print(f"{day}: pulled {int(since.total_seconds() // 60)} minutes ago; gp once an hour: skipped")
            return 0
    cred = spacetrack.credentials(ROOT)
    if not cred:
        print("::warning::GEO region: no Space-Track credentials (SPACETRACK_IDENTITY, SPACETRACK_PASSWORD); skipped")
        return 0
    if upload and not os.environ.get("TIC_ARCHIVE_TOKEN"):
        raise geo_region.ReleaseError("secret TIC_ARCHIVE_TOKEN is not set, so no release file could be archived "
                                      "before it is replaced; Space-Track not read")
    ST_WAIT()
    busy = ST_SHARED(ST_NOW(), shared=spacetrack.FOR_GEO)  # after the wait, just before the query
    if busy:
        print(f"::notice::GEO region skipped: {busy}")
        return 0
    client = ST_CLIENT(*cred)
    try:
        client.login()
        records = client.query_path(geo_region.GP_URL)
    finally:
        client.logout()
    fetched = ST_NOW().strftime("%Y-%m-%dT%H:%MZ")
    raw = _st_raw(ROOT / "data" / "raw", "spacetrack-gp-geo", "gp", client.last_body)
    if upload:  # the reply first, so a run stopped below still keeps its sets (private, as the update run's replies)
        kept = ROOT / "data" / "raw" / "spacetrack-gp-geo" / f"{raw['sha256'][:12]}.json.gz"
        with tempfile.TemporaryDirectory(prefix="geo-reply-") as tmp:
            shutil.copyfile(kept, Path(tmp) / f"{ST_NOW():%Y%m%dT%H%MZ}-{kept.name}")
            GEO_ARCHIVE("geo-reply", tmp)
    try:
        active = geo_region.active_ids((getter or fetch.get)(geo_region.ACTIVE_URL, 60))
    except Exception as exc:  # yesterday's list is used instead (geo_region.pull)
        print(f"::warning::CelesTrak's GEO group not read ({type(exc).__name__}); yesterday's active list is used")
        active = None
    months = sorted({r["EPOCH"][:7] for r in records if (r.get("EPOCH") or "") >= geo_region.HISTORY_START})
    if upload:
        held = geo_region.release_assets({geo_region.tag_for(geo_region.elements_name(m)) for m in months})
        geo_region.check_new_months(months, held, day)
        geo_region.release_get([geo_region.elements_name(m) for m in months], str(out), held=held)
    summary, paths = geo_region.pull(day, str(out), records, active, fetched)
    print(f"{day}: {summary['objects']} objects near GEO; zone {summary['zone']}, graveyard {summary['graveyard']}; "
          f"{summary['events']} events{' (first day: none)' if summary['first_day'] else ''}; "
          f"active list {summary['active_listed']}; element sets by month {summary['element_months']}; "
          f"{client.requests} Space-Track request(s)")
    if upload:
        geo_region.release_put(paths, archive=lambda folder: GEO_ARCHIVE("geo-release", folder))
        print(f"uploaded {len(paths)} file(s)")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as fh:
            fh.write("changed=true\n")
    return 0


def catalog_local(raw_dir: Path, out: Path, st_dir: Path | None = None, src_dir: Path | None = None) -> int:
    """Build the catalog from the newest GCAT copy of each table in data/raw (gzipped, as `collect` keeps them) and,
    when `spacetrack-catalog` has run, the newest Space-Track SATCAT and the DECAY store under `st_dir`, and the last
    CelesTrak SATCAT and Wikidata reads under `src_dir` (orbit/catsources.py; no request)."""
    def newest(name: str) -> bytes | None:
        files = sorted((raw_dir / f"gcat-{name}").glob("*"), key=lambda p: p.stat().st_mtime)
        if not files:
            return None
        body = files[-1].read_bytes()
        return gzip.decompress(body) if files[-1].name.endswith(".gz") else body
    bodies = {n: newest(n) for n in (*gcat.CATALOGS, "orgs")}
    missing = [n for n, b in bodies.items() if b is None]
    if missing:
        print(f"No GCAT copy in {raw_dir} for: {', '.join(missing)}. Run collect first.")
        return 1
    tables = {n: gcat.parse_tsv(bodies[n]) for n in gcat.CATALOGS}
    orgs = gcat.orgs_table(gcat.parse_tsv(bodies["orgs"]))
    stamp = gcat.updated_stamp(bodies["satcat"])
    st = stcat.load_local(st_dir or raw_dir.parent)
    if st:
        st = {"satcat": st["satcat"], "decay": st["decay"], "read": st["state"]["satcat_read_at"][:10],
              "read_at": st["state"]["satcat_read_at"]}
    more = catsources.load(src_dir or raw_dir.parent)
    entries = aliases.load(source_ids=aliases.source_ids(ROOT))
    os_read = oscar.store_load(src_dir or raw_dir.parent, catsources.read_json(
        (src_dir or raw_dir.parent) / catsources.STATE, {}))
    os_join = ({**os_read, "links": oscarlinks.reviewed(oscarlinks.load())} if os_read else None)
    doc = catalog.build(tables, orgs, gcat.today_utc().isoformat(), gcat_updated=stamp, spacetrack=st,
                        celestrak=more[catsources.CT], wikidata=more[catsources.WD], alias_entries=entries,
                        oscar_join=os_join)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Written in compact form (catshards, schema tic-catalog/2: default read, ref and basis left out; build step 6),
    # with the object page's shards, search index and rules note beside it.
    full_mb = len(json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) / 1e6
    cdoc = catshards.compact(doc)
    raw = json.dumps(cdoc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    out.write_bytes(gzip.compress(raw, 6) if out.name.endswith(".gz") else raw)
    assets = catshards.bundle(doc, cdoc)
    for name, body in assets.items():
        (out.parent / name).write_bytes(body)
    idx = catalog.names_index(doc, {aliases.key_of(e) for e in entries
                                     if "program" not in e and not aliases.is_swap(e)})
    idx_raw = json.dumps(idx, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    (out.parent / stcat.NAMES_ASSET).write_bytes(gzip.compress(idx_raw, 9))
    c = doc["counts"]
    held = ", ".join(f"{s} ({v['read_at']})" for s, v in more.items() if v) or "no CelesTrak or Wikidata copy"
    print(f"Catalog from GCAT ({stamp})" + (f", Space-Track ({st['read_at']})" if st else ", no Space-Track copy")
          + f", {held}: {c['numbered']} numbered, {c['unnumbered']} without a number, "
          f"{c['with_disagreements']} with disagreements {c['disagreements_by_field']}, {len(doc['swaps'])} name "
          f"swaps; {len(raw) / 1e6:.1f} MB JSON ({full_mb:.1f} MB with every record in full) -> {out}; name index "
          f"{len(idx['objects'])} objects, {len(idx_raw) / 1e6:.1f} MB JSON -> {out.parent / stcat.NAMES_ASSET}; "
          + ", ".join(f"{n} {len(b) / 1e6:.2f} MB" for n, b in assets.items()))
    for k in ("space_track", catsources.CT, catsources.WD, oscar.SOURCE, aliases.SOURCE):
        if c.get(k):
            print(f"{k}: {c[k]}")
    return 0


def catalog_sources(data_dir: Path, clear: str | None = None) -> int:
    """CelesTrak SATCAT (at most daily, once per file update), Wikidata (weekly) and WMO OSCAR/Space (weekly, 36
    pages 3 s apart), each only when due (orbit/catsources.py, orbit/oscar.py). A refusal (any answer but 200) puts
    the source on hold and is printed for a person."""
    if clear:
        print(f"Hold on {clear} cleared." if catsources.clear_hold(data_dir, clear) else f"No hold on {clear}.")
    notes = catsources.pull(data_dir)
    state = catsources.read_json(data_dir / catsources.STATE, {})
    notes[oscar.SOURCE] = oscar.pull(data_dir, datetime.now(timezone.utc), state)
    catsources.write_json(data_dir / catsources.STATE, state)
    bad = False
    for src, n in notes.items():
        if n.get("refused"):
            bad = True
            print(f"::error::{src} refused: {n['why']}. On hold (catsources.held); a person looks before clearing.")
        else:
            print(f"{src}: " + (f"read, {n.get('rows')} rows" if n.get("read") else f"not read: {n['why']}"))
    return 1 if bad else 0


def oscar_read(data_dir: Path, stamp: str | None) -> int:
    """WMO OSCAR/Space's satellite list, every page once into data/raw/wmo-oscar/<stamp>/ (local only; a stopped
    read resumes with the same stamp). Not scheduled: OSCAR joins only through the reviewed link file."""
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%d")
    try:
        out = oscar.read(data_dir, stamp)
    except catsources.Refused as exc:
        print(f"::error::{exc}. Stopped; a person looks before reading again.")
        return 1
    r = oscar.load(out)
    print(f"{out}: {r['total']} satellites")
    return 0


def oscar_propose(data_dir: Path, stamp: str, satcat: Path, names: Path | None, draft: bool) -> int:
    """NORAD candidates for OSCAR's operational satellites from launch date and orbit (orbit/oscar.py propose),
    into data/catalog/oscar-proposals.json. With --draft, appends an unreviewed entry to oscar-links.yml for each
    slug not yet in it whose proposal is single-fit with a name equal after normalising, or one-of-n with exactly
    one such name. Nothing joins until a person reviews an entry (reviewed_by, reviewed)."""
    r = oscar.load(data_dir / oscar.RAW / stamp)
    rows = catsources.ct_parse(gzip.decompress(satcat.read_bytes()) if satcat.name.endswith(".gz")
                               else satcat.read_bytes())
    idx = catsources.read_json(names, None) if names and names.exists() else None
    props = oscar.propose(r["satellites"], rows, idx)
    out = data_dir / "catalog" / "oscar-proposals.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"read": r["read"], "satcat": satcat.name, "names_index": idx and idx.get("read"),
                               "proposals": props}, ensure_ascii=False, indent=1), encoding="utf-8")
    counts = {}
    for p in props:
        counts[p["outcome"]] = counts.get(p["outcome"], 0) + 1
    print(f"{out}: {len(props)} proposals {counts}")
    if not draft:
        return 0
    have = {e["slug"] for e in (oscarlinks.parse(oscarlinks.PATH.read_text(encoding="utf-8"))
                                if oscarlinks.PATH.exists() else [])}
    today = datetime.now(timezone.utc).date().isoformat()
    added = []
    for p in props:
        if p["slug"] in have:
            continue
        agree = [c for c in p["candidates"] if c["name_agrees"]]
        if p["outcome"] == "one" and agree:
            c, kind = agree[0], "single-fit"
        elif p["outcome"] == "several" and len(agree) == 1:
            c, kind = agree[0], "one-of-n"
        else:
            continue
        added.append(oscarlinks.entry_text(p["slug"], [c["norad"]], "same", kind, p["oscar_id"], p["acronym"],
                                           r["read"], oscar.evidence(p, c), today))
    if added:
        with oscarlinks.PATH.open("a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(added))
    oscarlinks.load()  # the file must still read
    print(f"{oscarlinks.PATH.name}: {len(added)} unreviewed entries added")
    return 0


def spacetrack_catalog(data_dir: Path) -> int:
    """Space-Track SATCAT and DECAY, once a day after 17:00 UTC (orbit/stcat.py). Local for now: no workflow
    reads it until Tom says so."""
    cred = spacetrack.credentials(ROOT)
    if not cred:
        print("No Space-Track credentials (.env or the environment).")
        return 1
    try:
        got = stcat.pull(data_dir, cred)
    except spacetrack.NotReady as exc:
        print(f"Not read: {exc}")
        return 0
    s = got["state"]
    print(f"Space-Track: {s['satcat_rows']} SATCAT rows; DECAY ({s['decay_query']}) {s['decay_rows_read']} messages "
          f"read, {s['decay_added']} new, {s['decay_held']} held; {got['requests']} requests.")
    return 0


def archive_upload(data_dir: Path) -> int:
    """Workflow update.yml, after the deploy: this run's GCAT catalog-change files and the day's copy of the daily
    archive to monthly public releases (orbit/retention.py). No clobber; a failed upload exits 1."""
    repo = os.environ.get("GITHUB_REPOSITORY", geo_region.REPO)
    try:
        ch = retention.upload_changes(data_dir, repo)
        ar = retention.upload_archive(data_dir / ARCHIVE, datetime.now(timezone.utc).date(),
                                      data_dir / retention.OUT / "tmp", repo)
    except RuntimeError as exc:
        print(f"::error::{exc}")
        return 1
    print(f"Uploaded {len(ch)} catalog-change file(s) and {len(ar)} archive copy.")
    return 0


def catalog_release(data_dir: Path, clear_hold: str | None = None) -> int:
    """Workflow catalog.yml: the decay store and state from the public release `catalog`, one Space-Track read when
    due, GCAT's catalogs (one request each), the catalog built and uploaded with the store and state. Not due: exit 0
    with a note. The release exists but its decay store will not download: exit 1, nothing read. Every version of
    the release's files goes to the private tic-archive (lane catalog-release): the files as the release holds them
    before a due read (a failure stops the run, nothing read), and the files uploaded."""
    repo = os.environ.get("GITHUB_REPOSITORY", geo_region.REPO)
    held = stcat.release_exists(repo)
    if held and stcat.DECAY_ASSET not in stcat.release_get(data_dir, repo):
        print(f"::error::release {stcat.RELEASE} exists but {stcat.DECAY_ASSET} did not download; not reading")
        return 1
    if clear_hold:  # a person cleared it (workflow_dispatch input): saved now, read at the next Space-Track read
        print(f"Hold on {clear_hold} cleared." if catsources.clear_hold(data_dir, clear_hold)
              else f"No hold on {clear_hold}.")
    cred = spacetrack.credentials(ROOT)
    if not cred:
        print("No Space-Track credentials.")
        return 1
    now = datetime.now(timezone.utc)
    if held and stcat.due(now, stcat.read_json(data_dir / stcat.STATE, {})) is None:
        # Private archive (lane catalog-release): a read is due, so this run replaces the release's files. First a
        # copy of them as the release holds them now; normally the last run's copy of its uploads, so no new bytes.
        # A failure stops the run before Space-Track is read, so the once-a-day read is never spent on a run that
        # cannot keep what it replaces.
        try:
            with tempfile.TemporaryDirectory(prefix="catalog-held-") as tmp:
                stcat.release_copy(Path(tmp), repo)
                CATALOG_ARCHIVE("catalog-release", tmp)
        except RuntimeError as exc:
            print(f"::error::{exc}; Space-Track not read, nothing replaced")
            return 1
    try:
        got = stcat.pull(data_dir, cred, now=now, history_held=held)
    except spacetrack.NotReady as exc:
        print(f"::notice::Not read: {exc}")
        if clear_hold:
            stcat.release_put({stcat.SOURCES_STATE_ASSET: data_dir / catsources.STATE}, repo)
        return 0
    s = got["state"]
    print(f"Space-Track: {s['satcat_rows']} SATCAT rows; DECAY ({s['decay_query']}) {s['decay_rows_read']} messages "
          f"read, {s['decay_added']} new, {s['decay_held']} held; {got['requests']} requests.")
    # CelesTrak SATCAT (at most daily, once per file update) and Wikidata (weekly) are read only in the run that read
    # Space-Track: the build needs that day's SATCAT reply, which is not kept between runs, so one build a day and
    # GCAT's tables are fetched once. Their last replies ride the Actions cache (catalog.yml); the read dates and
    # any hold ride the release. A refusal holds that source and fails the run after the upload, for a person.
    refused = catalog_sources(data_dir) != 0
    raw = data_dir / "raw"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    for name in (*gcat.CATALOGS, "orgs"):
        p = raw / f"gcat-{name}" / f"{stamp}.tsv.gz"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(gzip.compress(fetch.get(gcat.URLS[name]), 6))
    out = data_dir / "catalog" / stcat.CATALOG_ASSET
    if catalog_local(raw, out, data_dir):
        return 1
    files = {stcat.CATALOG_ASSET: out, stcat.NAMES_ASSET: out.parent / stcat.NAMES_ASSET,
             **{n: out.parent / n for n in (catshards.SHARDS_ASSET, catshards.SEARCH_ASSET, catshards.RULES_ASSET)},
             stcat.DECAY_ASSET: data_dir / stcat.DECAY_STORE,
             stcat.STATE_ASSET: data_dir / stcat.STATE,
             stcat.SOURCES_STATE_ASSET: data_dir / catsources.STATE}
    stcat.release_put(files, repo)
    print(f"Uploaded {stcat.CATALOG_ASSET}, {stcat.NAMES_ASSET}, {catshards.SHARDS_ASSET}, {catshards.SEARCH_ASSET}, "
          f"{catshards.RULES_ASSET}, {stcat.DECAY_ASSET}, {stcat.STATE_ASSET} and "
          f"{stcat.SOURCES_STATE_ASSET} to release {stcat.RELEASE}.")
    # Private archive: the files just uploaded, so the archive holds every day's catalog (the release keeps only the
    # newest, the weekly copy below one a week). A failure fails the run after the live files are up; the next due
    # run's copy of the release, before it replaces anything, then keeps them.
    failed = False
    try:
        _archive_files(CATALOG_ARCHIVE, "catalog-release", files)
    except RuntimeError as exc:
        print(f"::error::{exc}")
        failed = True
    # retention (18 Nov 2026): the catalog is replaced every build, so keep one dated copy a week (already public on
    # release `catalog`); a failure fails the run, after the live files are up
    try:
        wk = retention.upload_catalog_week(out, datetime.now(timezone.utc).date(), repo)
    except RuntimeError as exc:
        print(f"::error::{exc}")
        return 1
    if wk:
        print(f"Kept the weekly copy {wk[0]}.")
    return 1 if refused or failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Orbit: launches, reentries and catalog changes from public sources.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--only", nargs="*", choices=sorted(LANES), help="run only these lanes; keep the rest as they were")
    c.add_argument("--force", action="store_true", help="read GCAT even if its files have not changed")
    sub.add_parser("build")
    od = sub.add_parser("object-data", help="object pages: the catalog's shards and search index from release "
                                           "`catalog` into site/data/catalog/ (one request; update.yml)")
    od.add_argument("--site", default=str(ROOT / "site"))
    fd = sub.add_parser("find", help="look a satellite up by any name from any source, NORAD number, COSPAR ID or GEO slot (12.5W) in "
                                     "TIC's catalog search index (one request to the live site; ideas#359)")
    fd.add_argument("query", nargs="+")
    fd.add_argument("--index", help="a search.json (or .json.gz) to read instead of the live site's")
    fd.add_argument("--limit", type=int, default=10)
    fd.add_argument("--geo", help="a globe.json to read instead of the live GEO page's (slot queries)")
    fd.add_argument("--window", type=float, default=None, help="degrees either side of a slot query (default 0.5; "
                                                               "0.1 for ITU filings' nominal longitudes)")
    fd.add_argument("--itu", action="store_true", help="slot queries: also the ITU's GEO filings and Resolution 40 "
                                                       "statements for the slot (asks ITU Space Explorer; local only)")
    fd.add_argument("--refresh", action="store_true", help="with --itu: ask ITU again, not the week-old cache")
    sub.add_parser("check")
    mc = sub.add_parser("maneuver-case", help="a known case from Space-Track, local only: sj21 (Jan 2022 Shijian-21 / "
                                              "BeiDou-2 G2), iss (2024 reboosts and the May storm) or luch2 (Luch (Olymp) 2, 2023-2026)")
    mc.add_argument("case", nargs="?", default="sj21", choices=sorted(CASES))
    sub.add_parser("maneuver-report", help="print the held manoeuvre report (data/state/spacetrack/report.json)")
    sub.add_parser("archive-upload", help="this run's catalog-change files and daily archive to monthly releases "
                                          "(update.yml, after the deploy)")
    gp = sub.add_parser("geo", help="the GEO region: one Space-Track gp query, day file and element files (geo.yml)")
    gp.add_argument("--day", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    gp.add_argument("--out", default=str(ROOT / "data" / "geo"))
    gp.add_argument("--upload", action="store_true", help="read and write the public release geo-YYYY (GitHub only)")
    cg = sub.add_parser("catalog", help="TIC's satellite catalog (tic-catalog/1) from the GCAT copies already in "
                                        "data/raw; local only, no request (build step 2)")
    cg.add_argument("--raw", default=str(ROOT / "data" / "raw"))
    cg.add_argument("--out", default=str(ROOT / "data" / "catalog" / "catalog.json.gz"))
    cg.add_argument("--spacetrack", default=str(ROOT / "data"),
                    help="data folder holding spacetrack-catalog's state and raw replies")
    sc = sub.add_parser("spacetrack-catalog", help="Space-Track SATCAT and DECAY for the catalog: once a day after "
                                                   "17:00 UTC, 4 requests; raw replies in data/raw (build step 3)")
    sc.add_argument("--data", default=str(ROOT / "data"))
    sc.add_argument("--release", action="store_true", help="workflow catalog.yml: store and state from the public "
                                                           "release `catalog`, build, upload (GitHub only)")
    sc.add_argument("--clear-hold", choices=(catsources.CT, catsources.WD),
                    help="with --release: clear a source's hold after a person has looked at the refusal")
    cs = sub.add_parser("catalog-sources", help="CelesTrak SATCAT (daily at most) and Wikidata (weekly) for the "
                                                "catalog, each only when due; local (build step 4)")
    cs.add_argument("--data", default=str(ROOT / "data"))
    cs.add_argument("--clear-hold", choices=(catsources.CT, catsources.WD))
    cg.add_argument("--sources", default=str(ROOT / "data"),
                    help="data folder holding catalog-sources' state and last replies")
    orr = sub.add_parser("oscar-read", help="WMO OSCAR/Space's satellite list, once, into data/raw (local only)")
    orr.add_argument("--data", default=str(ROOT / "data"))
    orr.add_argument("--stamp", help="folder under data/raw/wmo-oscar (default: today, UTC); reuse it to resume")
    op = sub.add_parser("oscar-propose", help="NORAD candidates for OSCAR satellites from launch date and orbit; "
                                             "--draft adds unreviewed entries to oscar-links.yml (local only)")
    op.add_argument("--data", default=str(ROOT / "data"))
    op.add_argument("--stamp", required=True, help="the OSCAR read under data/raw/wmo-oscar")
    op.add_argument("--satcat", default=str(ROOT / "data" / catsources.CT_STORE),
                    help="CelesTrak SATCAT CSV (catalog-sources' last reply)")
    op.add_argument("--names", default=str(ROOT / "data" / "catalog" / "catalog-names.json.gz"),
                    help="TIC name index (release `catalog`), for every source's names beside each candidate")
    op.add_argument("--draft", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "oscar-read":
        return oscar_read(Path(args.data), args.stamp)
    if args.cmd == "oscar-propose":
        return oscar_propose(Path(args.data), args.stamp, Path(args.satcat), Path(args.names), args.draft)
    if args.cmd == "spacetrack-catalog":
        return (catalog_release(Path(args.data), args.clear_hold) if args.release
                else spacetrack_catalog(Path(args.data)))
    if args.cmd == "catalog-sources":
        return catalog_sources(Path(args.data), args.clear_hold)
    if args.cmd == "catalog":
        return catalog_local(Path(args.raw), Path(args.out), Path(args.spacetrack), Path(args.sources))
    if args.cmd == "geo":
        return geo_pull(args.day, Path(args.out), args.upload)

    if args.cmd == "collect":
        snap = collect(only=args.only, force=args.force)
        for lane, st in snap["lanes"].items():
            extra = f" ({st.get('error')})" if st.get("status") == "failed" else ""
            print(f"  {lane:12s} {st.get('status')}{' [last good copy]' if st.get('from_previous') else ''}{extra}")
        ch = snap.get("catalog_changes") or {}
        h = snap.get("hygiene") or {}
        print(f"Collected {len(snap['launches'])} launches (30 days), {len(snap['reentries'])} reentries (30 days); "
              f"{len((snap.get('counterspace') or {}).get('tests') or [])} ASAT tests in SWF's sheet "
              f"({len((snap.get('counterspace') or {}).get('new_since_last') or [])} new since the last reading); "
              f"{h.get('in_orbit', 0)} objects in orbit. "
              + (f"Catalog changes since {ch['previous_reading_at']}: {ch['added']} added, {ch['removed']} removed, "
                 f"{ch['changed']} changed." if ch.get("previous_reading_at") else "No previous catalog reading."))
        return 0 if any(s.get("status") in ("ok", "unchanged") for s in snap["lanes"].values()) else 1
    if args.cmd == "archive-upload":
        return archive_upload(ROOT / "data")
    if args.cmd == "maneuver-case":
        return maneuver_case(ROOT, args.case)
    if args.cmd == "maneuver-report":
        rep = _st_read(ROOT / "data", "report.json", None)
        if not rep:
            print("No report yet: run collect with Space-Track credentials and a watch list.")
            return 1
        print_report(rep)
        return 0
    if args.cmd == "object-data":
        return object_data(Path(args.site))
    if args.cmd == "find":
        return find_name(" ".join(args.query), args.index, args.limit, geo=args.geo, window=args.window,
                         itu=args.itu, refresh=args.refresh)
    if args.cmd == "build":
        files = build_site(ROOT)
        print(f"Built site/ ({len(files)} files).")
        return 0
    if args.cmd == "check":
        errs = check_all(ROOT)
        for e in errs:
            print("  -", e)
        print(f"Orbit check: {'PASS' if not errs else f'FAIL ({len(errs)} problems)'}")
        return 1 if errs else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
