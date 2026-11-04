"""Orbit CLI: collect, build, and check.

    python tools/orbit.py collect
    python tools/orbit.py build
    python tools/orbit.py check
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from orbit import feed, gcat, maneuver  # noqa: E402
from tic_doctrine import contract, registers  # noqa: E402

SEED_SNAPSHOT = {
    "generated_at": "2026-11-01T12:00:00Z",
    "raw_gcat": [
        {
            "jcat": "S59773",
            "norad": "59773",
            "name": "Kosmos-2576",
            "celestrak_owner": "CIS",
            "gcat_state": "RU",
            "orbit_class": "LEO",
            "launch_designator": "2024-092A",
            "launch_date": "2024-05-16",
            "status": "O",
            "subpoint_lat": 51.8,
            "subpoint_lon": 39.2,
        },
        {
            "jcat": "S61890",
            "norad": "61890",
            "name": "Kosmos-2576 Subsatellite-A",
            "celestrak_owner": "CIS",
            "gcat_state": "RU",
            "orbit_class": "LEO",
            "launch_designator": "2024-092J",
            "launch_date": "2026-10-30",
            "status": "O",
            "is_subsatellite_deployment": True,
            "parent_object": "Kosmos-2576 (59773)",
            "subpoint_lat": 52.1,
            "subpoint_lon": 39.8,
        },
        {
            "jcat": "S55820",
            "norad": "55820",
            "name": "Luch-5X (Olymp-K No. 2)",
            "celestrak_owner": "CIS",
            "gcat_state": "RU",
            "orbit_class": "GEO",
            "launch_designator": "2023-031A",
            "launch_date": "2023-03-12",
            "status": "O",
            "subpoint_lat": 0.1,
            "subpoint_lon": 16.4,
        },
        {
            "jcat": "S19450",
            "norad": "19450",
            "name": "Kosmos-1966 (Soviet Oko Debris)",
            "celestrak_owner": "CIS",
            "gcat_state": "SU",
            "orbit_class": "HEO",
            "launch_designator": "1988-076A",
            "launch_date": "1988-08-30",
            "status": "O",
            "subpoint_lat": 62.0,
            "subpoint_lon": 88.0,
        },
        {
            "jcat": "A11402",
            "norad": None,
            "name": "Shiyan-28B Unnumbered Inspector",
            "celestrak_owner": "PRC",
            "gcat_state": "CN",
            "orbit_class": "GEO",
            "launch_designator": "2026-144B",
            "launch_date": "2026-10-18",
            "status": "O",
            "subpoint_lat": 0.2,
            "subpoint_lon": 112.5,
        },
        {
            "jcat": "S61901",
            "norad": "61901",
            "name": "Yaogan-43 Group 03A",
            "celestrak_owner": "PRC",
            "gcat_state": "CN",
            "orbit_class": "LEO",
            "launch_designator": "2026-150",
            "launch_date": "2026-10-22",
            "status": "O",
            "subpoint_lat": 28.2,
            "subpoint_lon": 102.0,
        },
        {
            "jcat": "S61902",
            "norad": "61902",
            "name": "Yaogan-43 Group 03B",
            "celestrak_owner": "PRC",
            "gcat_state": "CN",
            "orbit_class": "LEO",
            "launch_designator": "2026-150",
            "launch_date": "2026-10-22",
            "status": "O",
            "subpoint_lat": 28.4,
            "subpoint_lon": 102.3,
        },
    ],
    "raw_tle_histories": [
        {
            "jcat": "S59773",
            "norad": "59773",
            "name": "Kosmos-2576",
            "owner_clean": "RU",
            "country": "RU",
            "orbit_class": "LEO",
            "launch_designator": "2024-092A",
            "days_since_launch": 534,
            "subpoint_lat": 51.8,
            "subpoint_lon": 39.2,
            "epochs": [
                {"epoch": "2026-10-30T18:00:00Z", "mean_motion": 15.3820, "inclination_deg": 97.2500, "eccentricity": 0.00120},
                {"epoch": "2026-10-31T18:00:00Z", "mean_motion": 15.3610, "inclination_deg": 97.2512, "eccentricity": 0.00125},
            ],
        },
        {
            "jcat": "S55820",
            "norad": "55820",
            "name": "Luch-5X (Olymp-K No. 2)",
            "owner_clean": "RU",
            "country": "RU",
            "orbit_class": "GEO",
            "launch_designator": "2023-031A",
            "days_since_launch": 965,
            "subpoint_lat": 0.1,
            "subpoint_lon": 16.4,
            "epochs": [
                {"epoch": "2026-10-29T12:00:00Z", "mean_motion": 1.00270, "inclination_deg": 0.0800, "eccentricity": 0.00015},
                {"epoch": "2026-10-31T12:00:00Z", "mean_motion": 1.00110, "inclination_deg": 0.1450, "eccentricity": 0.00022},
            ],
        },
        {
            "jcat": "S61901",
            "norad": "61901",
            "name": "Yaogan-43 Group 03A",
            "owner_clean": "CN",
            "country": "CN",
            "orbit_class": "LEO",
            "launch_designator": "2026-150",
            "days_since_launch": 10,
            "subpoint_lat": 28.2,
            "subpoint_lon": 102.0,
            "epochs": [
                {"epoch": "2026-10-28T06:00:00Z", "mean_motion": 15.2200, "inclination_deg": 35.0010, "eccentricity": 0.00080},
                {"epoch": "2026-10-31T18:00:00Z", "mean_motion": 15.2140, "inclination_deg": 35.0012, "eccentricity": 0.00082},
            ],
        },
    ],
}


def build_snapshot(raw: dict | None = None) -> dict:
    raw = raw or SEED_SNAPSHOT
    cat = gcat.normalize_gcat_catalog(raw.get("raw_gcat", []))
    siblings_map = cat["hygiene_summary"]["multi_sibling_launches"]
    m_res = maneuver.evaluate_tle_history(raw.get("raw_tle_histories", []), siblings_map=siblings_map)
    return {
        "generated_at": raw.get("generated_at", "2026-11-01T12:00:00Z"),
        "catalog": cat,
        "maneuvers": m_res["detections"],
        "source_health_flags": m_res["source_health_flags"],
    }


def collect() -> dict:
    normalized = build_snapshot(SEED_SNAPSHOT)
    data_dir = ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "snapshot.json").write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return normalized


def build_site(root: Path = ROOT) -> dict[str, str]:
    snap_path = root / "data" / "snapshot.json"
    snap = json.loads(snap_path.read_text(encoding="utf-8")) if snap_path.exists() else build_snapshot()
    feed_doc = feed.build_feed(snap)

    files = {
        "data/snapshot.json": json.dumps(snap, indent=2, ensure_ascii=False) + "\n",
        "data/feed.geojson": json.dumps(feed_doc, indent=2, ensure_ascii=False) + "\n",
    }
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
        build_site(root)
    feed_doc = json.loads(feed_path.read_text(encoding="utf-8"))
    for feat in feed_doc.get("features", []):
        fid = (feat.get("properties") or {}).get("id", "?")
        for std, sev, msg in contract.check(feat, regs):
            if sev == "error":
                errs.append(f"{fid}: {std}: {msg}")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Orbit Space Domain Awareness & Maneuver Compare monitor.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("collect")
    sub.add_parser("build")
    sub.add_parser("check")
    args = ap.parse_args(argv)

    if args.cmd == "collect":
        snap = collect()
        print(
            f"Collected {len(snap['catalog']['objects'])} GCAT objects, "
            f"{len(snap['maneuvers'])} maneuvers, {len(snap['source_health_flags'])} TLE gap flags."
        )
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
