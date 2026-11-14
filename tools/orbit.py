"""Orbit CLI: collect, build, and check.

    python tools/orbit.py collect            # fetch every live lane, write data/snapshot.json
    python tools/orbit.py collect --only upcoming
    python tools/orbit.py collect --force    # read GCAT even if its files have not changed
    python tools/orbit.py build              # build site/ from data/snapshot.json
    python tools/orbit.py check              # validate the registers and lint the feed

collect never falls back to made-up data. A lane that fails keeps its last good copy (marked
from_previous) or stays empty, and the snapshot's "lanes" block says which.

Lanes (method orbit-2.2):
  catalog   GCAT: satcat, satcat100k, auxcat, tmpcat, launch list and launch sites. GCAT republishes once a
            day (about 00:20 UTC), so a run first asks each file's Last-Modified date and downloads nothing
            if none has changed. About 37 MB when it does.
  upcoming  Launch Library 2: launches scheduled in the next 14 days. One request.
  navwarn   Launch hazard and space-debris navigational warnings in force: NGA's five daily memoranda and
            NAVAREA XI (Japan Coast Guard), a list and one request per launch-related warning.
The manoeuvre lane (orbit/maneuver.py) is not run: see doctrine/method.md.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from orbit import feed, fetch, gcat, launches, navwarn  # noqa: E402
from tic_doctrine import contract, registers  # noqa: E402

LANE_FIELDS = {
    "catalog": ["gcat_updated", "launches", "reentries", "hygiene", "catalog_changes"],
    "upcoming": ["upcoming"],
    "navwarn": ["navwarn"],
}
EMPTY = {"gcat_updated": {}, "launches": [], "reentries": [], "hygiene": {}, "catalog_changes": {}, "upcoming": [],
         "navwarn": {}}
INDEX = Path("state") / "catalog_index.json.gz"
MIN_KEEP = 0.9  # a reading with under 90% of the previous reading's objects fails the lane
# Which register source feeds each lane (doctrine/sources.json), so the page can show each lane's grade.
LANE_SOURCE = {"catalog": ["gcat-mcdowell"], "upcoming": ["ll2-thespacedevs"],
               "navwarn": ["nga-msi"]}


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


LANES = {"catalog": _lane_catalog, "upcoming": _lane_upcoming, "navwarn": _lane_navwarn}


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
        except Exception as exc:
            had = bool(prev_lane.get("fetched_at"))
            for k in fields:
                snap[k] = prev.get(k, EMPTY[k]) if had else EMPTY[k]
            snap["lanes"][lane] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300],
                                   "failed_at": now, "from_previous": had, "fetched_at": prev_lane.get("fetched_at"),
                                   "last_modified": prev_lane.get("last_modified")}
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Orbit: launches, reentries and catalog changes from public sources.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--only", nargs="*", choices=sorted(LANES), help="run only these lanes; keep the rest as they were")
    c.add_argument("--force", action="store_true", help="read GCAT even if its files have not changed")
    sub.add_parser("build")
    sub.add_parser("check")
    args = ap.parse_args(argv)

    if args.cmd == "collect":
        snap = collect(only=args.only, force=args.force)
        for lane, st in snap["lanes"].items():
            extra = f" ({st.get('error')})" if st.get("status") == "failed" else ""
            print(f"  {lane:9s} {st.get('status')}{' [last good copy]' if st.get('from_previous') else ''}{extra}")
        ch = snap.get("catalog_changes") or {}
        h = snap.get("hygiene") or {}
        print(f"Collected {len(snap['launches'])} launches (30 days), {len(snap['reentries'])} reentries (30 days), "
              f"{len(snap['upcoming'])} scheduled launches (14 days); "
              f"{len((snap.get('navwarn') or {}).get('areas') or [])} launch hazard areas in force; "
              f"{h.get('in_orbit', 0)} objects in orbit. "
              + (f"Catalog changes since {ch['previous_reading_at']}: {ch['added']} added, {ch['removed']} removed, "
                 f"{ch['changed']} changed." if ch.get("previous_reading_at") else "No previous catalog reading."))
        return 0 if any(s.get("status") in ("ok", "unchanged") for s in snap["lanes"].values()) else 1
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
