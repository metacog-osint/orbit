"""Orbit CLI: collect, build, and check.

    python tools/orbit.py collect            # fetch every live lane, write data/snapshot.json
    python tools/orbit.py collect --only upcoming
    python tools/orbit.py collect --force    # read GCAT even if its files have not changed
    python tools/orbit.py build              # build site/ from data/snapshot.json
    python tools/orbit.py check              # validate the registers and lint the feed

collect never falls back to made-up data. A lane that fails keeps its last good copy (marked
from_previous) or stays empty, and the snapshot's "lanes" block says which.

Lanes (method orbit-2.4):
  catalog   GCAT: satcat, satcat100k, auxcat, tmpcat, launch list and launch sites. GCAT republishes once a
            day (about 00:20 UTC), so a run first asks each file's Last-Modified date and downloads nothing
            if none has changed. About 37 MB when it does.
  upcoming  Launch Library 2: launches scheduled in the next 14 days. One request.
  navwarn   Launch hazard and space-debris navigational warnings in force: NGA's five daily memoranda and
            NAVAREA XI (Japan Coast Guard), a list and one request per launch-related warning.
  counterspace  Secure World Foundation's "History of ASAT Testing in Space" sheet (CSV export, CC BY-NC 4.0):
            every test with its debris counts, totals by country, and tests new since the last reading.
  maneuver  Space-Track.org (USSPACECOM) element sets for a private watch list: GP once an hour at most, each
            object's history (GP_HISTORY) once only, stored in data/state/spacetrack/. Orbit changes larger than
            each object's own element-set noise (orbit/maneuver.py). Published since Tom approved the disclaimer
            (14 Nov 2026); maneuver.PUBLISH = False holds it off the page again. Off without credentials.
    python tools/orbit.py maneuver-case      # the January 2022 Shijian-21 / BeiDou-2 G2 case, local only
    python tools/orbit.py maneuver-report    # the held report, printed locally
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from orbit import counterspace, feed, fetch, gcat, launches, maneuver, navwarn, news, spacetrack  # noqa: E402
from tic_doctrine import contract, registers  # noqa: E402

LANE_FIELDS = {
    "catalog": ["gcat_updated", "launches", "reentries", "hygiene", "catalog_changes"],
    "upcoming": ["upcoming"],
    "news": ["news"],
    "navwarn": ["navwarn"],
    "counterspace": ["counterspace"],
    "maneuver": ["maneuvers"],
}
EMPTY = {"gcat_updated": {}, "launches": [], "reentries": [], "hygiene": {}, "catalog_changes": {}, "upcoming": [],
         "news": {}, "navwarn": {}, "counterspace": {}, "maneuvers": {}}
ST_DIR = Path("state") / "spacetrack"  # Space-Track sets, kept in the private Actions cache, never published
ST_CLIENT = spacetrack.Client            # replaceable in tests
ST_WAIT = spacetrack.wait_for_clear_minute
ST_NOW = lambda: datetime.now(timezone.utc)  # noqa: E731
INDEX = Path("state") / "catalog_index.json.gz"
MIN_KEEP = 0.9  # a reading with under 90% of the previous reading's objects fails the lane
# Which register source feeds each lane (doctrine/sources.json), so the page can show each lane's grade.
LANE_SOURCE = {"catalog": ["gcat-mcdowell"], "upcoming": ["ll2-thespacedevs"], "news": ["snapi-thespacedevs"],
               "navwarn": ["nga-msi"], "counterspace": ["swf-counterspace"], "maneuver": ["space-track"]}


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
    result = {
        "gcat_updated": {name: gcat.updated_stamp(bodies[name]) for name in gcat.URLS},
        "launches": gcat.recent_launches(gcat.parse_tsv(bodies["launch"]), objs, sites, today, orgs=orgs),
        "reentries": gcat.recent_reentries(objs, today),
        "hygiene": gcat.hygiene(objs),
        "catalog_changes": {},
    }
    if index_doc:
        result["catalog_changes"] = {"previous_reading_at": index_doc["read_at"],
                                     **gcat.diff(index_doc["objects"], objs, today)}
    _write_index(data_dir, {"read_at": recs[0]["fetched_at"], "gcat_updated": result["gcat_updated"],
                            "objects": gcat.build_index(objs)})
    return result, recs, stamps


def _lane_upcoming(raw_dir: Path, prev: dict, getter, **_):
    now = launches.now_utc()
    body, rec = fetch.fetch("ll2-upcoming", launches.url(now), raw_dir, "json", getter=getter)
    return {"upcoming": launches.within(launches.parse(body), now)}, [rec], None


def _lane_news(raw_dir: Path, prev: dict, getter, upcoming=None, **_):
    """Spaceflight News API headlines for this run's scheduled launches (links only): one request, none when
    nothing is scheduled."""
    ids = [u["id"] for u in upcoming or [] if u.get("id")]
    if not ids:
        return {"news": {"read_at": fetch.now_utc(), "articles": [], "by_launch": {}, "note": "no scheduled launches"}}, [], None
    body, rec = fetch.fetch("snapi-articles", news.url(ids), raw_dir, "json", getter=getter)
    doc = news.parse(body, ids)
    return {"news": {"read_at": rec["fetched_at"], "source": news.SITE, **doc}}, [rec], None


def _lane_navwarn(raw_dir: Path, prev: dict, getter, **_):
    """Launch hazard and space-debris warnings in force: NGA's daily memoranda and NAVAREA XI (Japan Coast
    Guard). Each source is read on its own; the lane fails only if both do, and says which one failed."""
    now = launches.now_utc()
    warnings, recs, sources = [], [], {}
    nga = {"status": "ok", "memos": {}}
    try:  # NGA's API first; down (503) since at least 6 Nov 2026, frozen at May 2024 before that
        body, rec = fetch.fetch("nga-api", navwarn.NGA_API, raw_dir, "json", getter=getter)
        recs.append(rec)
        api = navwarn.parse_api(json.loads(body), now)
        nga.update({"form": "api", "newest": api["newest"]})
        for area, memo in api["memos"].items():
            warnings += memo["warnings"]
            nga["memos"][area] = {"as_of": navwarn._iso(now), "in_force": memo["in_force"], "launch_related": len(memo["warnings"])}
    except Exception as exc:  # then the daily in-force memoranda, each read on its own
        nga.update({"form": "memoranda", "api_error": f"{type(exc).__name__}: {exc}"[:200]})
        for area, url in navwarn.NGA_MEMOS.items():
            slug = area.lower().replace(" ", "")
            try:
                body, rec = fetch.fetch(f"nga-{slug}", url, raw_dir, "txt", getter=getter)
                recs.append(rec)
                memo = navwarn.parse_memo(body, area, now)
                warnings += memo["warnings"]
                nga["memos"][area] = {"as_of": memo["as_of"], "in_force": memo["in_force"],
                                      "launch_related": len(memo["warnings"])}
            except Exception as exc2:  # one memo failing leaves the others
                nga["memos"][area] = {"error": f"{type(exc2).__name__}: {exc2}"[:200]}
    bad = [a for a, m in nga["memos"].items() if "error" in m]
    if bad:
        nga["status"] = "failed" if len(bad) == len(navwarn.NGA_MEMOS) else "partial"
    sources["nga"] = nga
    jcg = {"status": "ok"}
    try:
        if not navwarn.JCG_READ:
            raise navwarn.SourceOff(navwarn.JCG_OFF)
        items = []
        for year in sorted({now.year, (now - timedelta(days=45)).year}):
            body, rec = fetch.fetch("jcg-navarea11-list", navwarn.JCG_LIST.format(year=year), raw_dir, "xml",
                                    getter=getter)
            recs.append(rec)
            items += navwarn.parse_jcg_list(body)
        wanted = navwarn.jcg_wanted(items)
        jcg.update({"listed": len(items), "launch_titles": len(wanted)})
        bad = []
        for it in wanted:  # one unreadable message is skipped and named, not the whole source
            try:
                body, rec = fetch.fetch("jcg-navarea11-msg", navwarn.JCG_MSG.format(tana=it["tana"]), raw_dir,
                                        "html", getter=getter)
                recs.append(rec)
                w = navwarn.parse_jcg_message(body, it)
            except Exception as exc:
                bad.append(f"{it['tana']}: {type(exc).__name__}: {exc}"[:160])
                continue
            if w:
                warnings.append(w)
        if bad:
            jcg.update({"status": "partial" if len(bad) < len(wanted) else "failed", "errors": bad})
    except navwarn.SourceOff as exc:
        jcg = {"status": "off", "reason": str(exc)}
    except Exception as exc:
        jcg = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:200]}
    sources["jcg"] = jcg
    if nga["status"] == "failed" and jcg["status"] in ("failed", "off"):
        raise RuntimeError("NGA failed and NAVAREA XI gave nothing: " + (jcg.get("error") or jcg.get("reason")
                                                                         or "; ".join(jcg.get("errors", []))))
    areas = navwarn.group(navwarn.current(warnings, now))
    return {"navwarn": {"read_at": fetch.now_utc(), "sources": sources, "areas": areas}}, recs, None


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


def _lane_maneuver(raw_dir: Path, prev: dict, getter, **_):
    """Orbit changes in watched objects (Space-Track GP and GP_HISTORY). Off without credentials or a watch list;
    unchanged (no request) within an hour of the last GP query."""
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
    client = ST_CLIENT(*cred)
    recs = []
    try:
        client.login()
        gp = client.query("gp", ids)
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
    rep.update({"read_at": read_at, "watched": len(ids), "missing": [i for i in ids if str(i) not in store]})
    _st_write(data_dir, "report.json", rep)  # the full report, private
    out = {"attribution": maneuver.ATTRIBUTION, "read_at": read_at, "watched": len(ids), "window_days": rep["window_days"],
           "thresholds": rep["thresholds"], "events": rep["events"],
           "quiet_or_untracked": sum(1 for o in rep["objects"] if not o["events"]),
           "stale": sum(1 for o in rep["objects"] if (o.get("note") or "").startswith("no new"))}
    return {"maneuvers": out}, recs, None


LANES = {"catalog": _lane_catalog, "upcoming": _lane_upcoming, "news": _lane_news, "navwarn": _lane_navwarn,
         "counterspace": _lane_counterspace, "maneuver": _lane_maneuver}


def collect(root: Path = ROOT, getter=None, header=None, only: list[str] | None = None, force: bool = False) -> dict:
    data_dir = root / "data"
    raw_dir = data_dir / "raw"
    snap_path = data_dir / "snapshot.json"
    prev = json.loads(snap_path.read_text(encoding="utf-8")) if snap_path.exists() else {}
    now = fetch.now_utc()
    snap = {"generated_at": now, "method_version": feed.METHOD, "lanes": {}}
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
            if lane == "news":  # reads this run's scheduled launches (upcoming runs first)
                kwargs = {"upcoming": snap.get("upcoming")}
            result, recs, stamps = fn(raw_dir, prev, getter, **kwargs)
            if result is None:
                keep_previous()
                snap["lanes"][lane] = {**prev_lane, "status": "unchanged", "checked_at": now, "from_previous": False}
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
    data_dir.mkdir(parents=True, exist_ok=True)
    snap_path.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return snap


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
             "data/world.geojson": json.dumps(world_shapes(countries), separators=(",", ":")) + "\n"}
    src_dir = root / "site_src"
    if src_dir.exists():
        for p in sorted(src_dir.rglob("*")):
            if p.is_file():
                files[p.relative_to(src_dir).as_posix()] = p.read_text(encoding="utf-8")
    out_dir = root / "site"
    out_dir.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8", newline="\n")
    return files


def check_all(root: Path = ROOT) -> list[str]:
    errs = registers.check(root / "doctrine")
    regs = registers.ids(root / "doctrine")
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
CASES = {"sj21": CASE, "iss": CASE_ISS}


def print_report(rep: dict) -> None:
    for o in rep["objects"]:
        g = o.get("geo") or {}
        print(f"{o['norad']:>6} {str(o.get('name'))[:24]:24s} {str(o.get('regime')):4s} sets {o['sets']:4d}  "
              f"last {o.get('last_epoch')}  gap max {o.get('max_gap_h')} h  noise {o.get('noise_ms')}"
              + (f"  lon {g['lon']} drift {g['drift_deg_day']}/day" if g else "") + (f"  [{o['note']}]" if o.get("note") else ""))
        for e in o["events"]:
            gg = e.get("geo") or {}
            print(f"         {e['from']} -> {e['to']}  {e['dv_ms']:8.3f} m/s {e['dominant']:12s} da {e['da_km']} km "
                  f"di {e['di_deg']} deg z {e['z']} ({e['pairs']} pairs)"
                  + (f"  lon {gg['lon_before']} -> {gg['lon_after']}, drift {gg['drift_before']} -> {gg['drift_after']}"
                     if gg else ""))


def print_score(sc: dict, case: dict) -> None:
    print(f"Scored against {len(case['announced'])} announced reboosts, within {case['tolerance_h']} h:")
    for h in sc["announced"]:
        got = "; ".join(f"{e['from']} -> {e['to']} {e['dv_ms']} m/s {e['dominant']} da {e['da_km']} km"
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
    store = maneuver.merge({}, records, datetime.fromisoformat(CASE["now"].replace("Z", "+00:00")), keep_days=400)
    rep = maneuver.report(store, datetime.fromisoformat(CASE["now"].replace("Z", "+00:00")), CASE["window_days"])
    print(f"{len(records)} element sets, Space-Track (USSPACECOM). Thresholds {rep['thresholds']}.")
    print_report(rep)
    if CASE.get("announced"):
        print_score(maneuver.score(rep["events"], CASE["announced"], CASE["tolerance_h"], CASE.get("storm")), CASE)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Orbit: launches, reentries and catalog changes from public sources.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--only", nargs="*", choices=sorted(LANES), help="run only these lanes; keep the rest as they were")
    c.add_argument("--force", action="store_true", help="read GCAT even if its files have not changed")
    sub.add_parser("build")
    sub.add_parser("check")
    mc = sub.add_parser("maneuver-case", help="a known case from Space-Track, local only: sj21 (Jan 2022 Shijian-21 / "
                                              "BeiDou-2 G2) or iss (2024 reboosts and the May storm)")
    mc.add_argument("case", nargs="?", default="sj21", choices=sorted(CASES))
    sub.add_parser("maneuver-report", help="print the held manoeuvre report (data/state/spacetrack/report.json)")
    args = ap.parse_args(argv)

    if args.cmd == "collect":
        snap = collect(only=args.only, force=args.force)
        for lane, st in snap["lanes"].items():
            extra = f" ({st.get('error')})" if st.get("status") == "failed" else ""
            print(f"  {lane:12s} {st.get('status')}{' [last good copy]' if st.get('from_previous') else ''}{extra}")
        ch = snap.get("catalog_changes") or {}
        h = snap.get("hygiene") or {}
        print(f"Collected {len(snap['launches'])} launches (30 days), {len(snap['reentries'])} reentries (30 days), "
              f"{len(snap['upcoming'])} scheduled launches (14 days); "
              f"{len((snap.get('navwarn') or {}).get('areas') or [])} launch hazard areas in force; "
              f"{len((snap.get('counterspace') or {}).get('tests') or [])} ASAT tests in SWF's sheet "
              f"({len((snap.get('counterspace') or {}).get('new_since_last') or [])} new since the last reading); "
              f"{h.get('in_orbit', 0)} objects in orbit. "
              + (f"Catalog changes since {ch['previous_reading_at']}: {ch['added']} added, {ch['removed']} removed, "
                 f"{ch['changed']} changed." if ch.get("previous_reading_at") else "No previous catalog reading."))
        return 0 if any(s.get("status") in ("ok", "unchanged") for s in snap["lanes"].values()) else 1
    if args.cmd == "maneuver-case":
        return maneuver_case(ROOT, args.case)
    if args.cmd == "maneuver-report":
        rep = _st_read(ROOT / "data", "report.json", None)
        if not rep:
            print("No report yet: run collect with Space-Track credentials and a watch list.")
            return 1
        print_report(rep)
        return 0
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
