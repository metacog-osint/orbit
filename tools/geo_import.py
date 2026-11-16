#!/usr/bin/env python3
"""One-time import of Noisefloor's GEO region history into Orbit's files (step 2 of doctrine/geo-move-plan.md).

  python tools/geo_import.py --out data/geo [--src DIR] [--upload]

Reads Noisefloor's public releases pnt-data-YYYY-MM (2026-07 on): every geo-elements-YYYY-MM.parquet and every
<day>.geo-region.json. Writes Orbit's geo-elements-YYYY-MM.json.gz (the same element sets) and copies the day files
(schema noted as Noisefloor's), so Orbit's daily pull has yesterday's file and step 3's callouts have the history.
No Space-Track request: Space-Track asks that gp_history be fetched once per object and stored, and Noisefloor
already holds it. Needs pyarrow (pinned in .github/workflows/geo-import.yml); Orbit's live lanes stay standard
library. --upload puts the files on Orbit's public releases geo-YYYY (a day file already there is not replaced).
"""
import argparse
import glob
import json
import os
import subprocess
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from orbit import geo_region as G  # noqa: E402

NF_REPO = "metacog-osint/noise-floor"
FIRST_MONTH = G.HISTORY_START[:7]


def months(until: date):
    y, m = map(int, FIRST_MONTH.split("-"))
    while (y, m) <= (until.year, until.month):
        yield f"{y:04d}-{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def download(src):
    """Every GEO file of Noisefloor's monthly releases into `src`. A month's element file can sit in two releases (the
    month before holds an early copy); the month's own release wins, so it is fetched last."""
    os.makedirs(src, exist_ok=True)
    for m in months(date.today()):
        r = gh("release", "download", f"pnt-data-{m}", "-R", NF_REPO, "-p", "*.geo-region.json", "-D", src, "--skip-existing")
        print(f"pnt-data-{m}: day files {'ok' if not r.returncode else r.stderr.strip()[:120]}")
    for m in months(date.today()):
        name = f"geo-elements-{m}.parquet"
        for tag in (f"pnt-data-{m}",):
            r = gh("release", "download", tag, "-R", NF_REPO, "-p", name, "-D", src, "--clobber")
            print(f"{tag}: {name} {'ok' if not r.returncode else 'not there'}")


def convert(src, out):
    import pyarrow.parquet as pq
    os.makedirs(out, exist_ok=True)
    total = {}
    for p in sorted(glob.glob(os.path.join(src, "geo-elements-*.parquet"))):
        t = pq.read_table(p).to_pydict()
        rows = [dict(zip(G.COLS, vals)) for vals in zip(*(t[c] for c in G.COLS))]
        m = os.path.basename(p)[len("geo-elements-"):-len(".parquet")]
        total[m] = G.write_elements(os.path.join(out, G.elements_name(m)), rows)
    days = 0
    for p in sorted(glob.glob(os.path.join(src, "*.geo-region.json"))):
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        doc["schema"] = "orbit-geo-region/1"
        doc["imported_from"] = f"Noisefloor ({NF_REPO}), tools/geo_region.py"
        with open(os.path.join(out, os.path.basename(p)), "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)
        days += 1
    print(f"element sets by month: {total}; day files: {days}")
    return total, days


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "geo"))
    ap.add_argument("--src", default=os.path.join(ROOT, "data", "geo-import"))
    ap.add_argument("--upload", action="store_true")
    a = ap.parse_args()
    download(a.src)
    convert(a.src, a.out)
    if a.upload:
        held = {}
        for tag in sorted({G.tag_for(os.path.basename(p)) for p in glob.glob(os.path.join(a.out, "*"))}):
            r = gh("release", "view", tag, "-R", G.REPO, "--json", "assets", "-q", ".assets[].name")
            held[tag] = set(r.stdout.split()) if not r.returncode else set()
        paths = [p for p in sorted(glob.glob(os.path.join(a.out, "*")))
                 if p.endswith(".json.gz") or os.path.basename(p) not in held.get(G.tag_for(os.path.basename(p)), set())]
        G.release_put(paths)
        print(f"uploaded {len(paths)} file(s)")


if __name__ == "__main__":
    main()
