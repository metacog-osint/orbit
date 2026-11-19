"""Retention archives (18 Nov 2026, Tom's rule: no TIC program loses data; live views may filter, storage keeps all).

Everything here goes to this repository's PUBLIC releases, so only what is already public or open-licensed goes in:
GCAT's catalog changes (CC BY 4.0), the published daily archive (/data/archive.json) and the published TIC catalog
(release `catalog`). Nothing from Space-Track element sets, the watch list or case reads (those need a private store).

Layout: one release per month and kind (`<kind>-YYYY-MM`, GitHub's limit is 1,000 assets a release), assets with
unique names, never clobbered: a name already on the release is skipped, so a rerun or a queued run cannot replace
anything, and an upload that fails raises (the workflow step fails loudly, after the site deploy).

  catalog-changes-YYYY-MM   catalog-changes-<fetch stamp>.jsonl.gz, the whole per-object diff of one GCAT reading
  archive-YYYY-MM           archive-YYYY-MM-DD.json.gz, Orbit's daily archive as published on that day (first run of the day)
  catalog-archive-YYYY-MM   catalog-YYYY-MM-DD.json.gz, the TIC catalog copied weekly (the ISO week's Monday names it)
"""
from __future__ import annotations

import gzip
import json
import re
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path

OUT = Path("archive_out")   # under data/, not in the Actions cache path: files here are uploaded once then removed
GCAT_CREDIT = "Data from GCAT (J. McDowell, planet4589.org/space/gcat), CC BY 4.0"
NOTES = {
    "catalog-changes": "Orbit's archive of GCAT catalog changes: one file per GCAT reading, every added, removed and "
                       "changed object with the field before and after (nothing cut at 50). " + GCAT_CREDIT + ".",
    "archive": "Orbit's daily archive (schema orbit-archive/1) as published at orbit.theintelligence.company/data/"
               "archive.json, one dated copy a day.",
    "catalog-archive": "Weekly dated copies of TIC's satellite catalog (the file on release `catalog`, schema "
                       "tic-catalog/2), so values a source later changes stay on record.",
}


def _gh(*args):
    import subprocess
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def stamp_name(stamp: str) -> str:
    """A fetch stamp as a file-name piece: letters, digits and dashes only."""
    return re.sub(r"[^0-9A-Za-z]+", "-", stamp).strip("-")


def changes_lines(diff: dict, read_at: str, previous_at: str | None, gcat_updated: dict) -> list[dict]:
    """One reading's whole diff (gcat.diff(..., full=True)) as JSON lines: a header, then one line per object."""
    out = [{"kind": "reading", "read_at": read_at, "previous_reading_at": previous_at, "gcat_updated": gcat_updated,
            "credit": GCAT_CREDIT,
            "counts": {k: diff.get(k) for k in ("added", "added_fresh", "added_late", "removed",
                                                "temporary_entries_closed", "changed", "newly_numbered")},
            "status_moves": diff.get("status_moves") or {}}]
    out += [{"kind": "added", **o} for o in diff.get("added_objects") or []]
    out += [{"kind": "removed", **o} for o in diff.get("removed_objects") or []]
    out += [{"kind": "temporary_closed", **o} for o in diff.get("temporary_entries_closed_objects") or []]
    owner = {c["jcat"] for c in diff.get("owner_changes") or []}
    out += [{"kind": "changed", "owner_change": c["jcat"] in owner, **c} for c in diff.get("changed_objects") or []]
    out += [{"kind": "late_group", **g} for g in diff.get("late_groups") or []]
    return out


def write_changes(data_dir: Path, lines: list[dict], read_at: str) -> Path:
    """Write one reading's lines to data/archive_out/catalog-changes-<stamp>.jsonl.gz (a stamp names it once)."""
    p = data_dir / OUT / f"catalog-changes-{stamp_name(read_at)}.jsonl.gz"
    p.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n" for x in lines)
    p.write_bytes(gzip.compress(body.encode("utf-8"), 9))
    return p


def put_new(tag: str, kind: str, files: dict[str, Path], repo: str, gh=_gh) -> list[str]:
    """Upload {asset name: path} to release `tag`, creating it when missing; names already there are skipped, never
    replaced. Returns the names uploaded. Any failure raises."""
    if gh("release", "view", tag, "-R", repo).returncode != 0:
        r = gh("release", "create", tag, "-R", repo, "--title", tag, "--latest=false", "--notes", NOTES[kind])
        if r.returncode and gh("release", "view", tag, "-R", repo).returncode != 0:
            raise RuntimeError(f"release {tag} could not be created: {r.stderr.strip()[:300]}")
    r = gh("release", "view", tag, "-R", repo, "--json", "assets", "-q", ".assets[].name")
    if r.returncode:
        raise RuntimeError(f"release {tag} could not be listed: {r.stderr.strip()[:300]}")
    have = set(r.stdout.split())
    done = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, p in files.items():
            if name in have:
                continue
            q = Path(tmp) / name  # gh names the asset after the file
            shutil.copyfile(p, q)
            r = gh("release", "upload", tag, "-R", repo, str(q))  # no --clobber: a name keeps its first data
            if r.returncode:
                raise RuntimeError(f"upload of {name} to {tag} failed: {r.stderr.strip()[:300]}")
            done.append(name)
    return done


def upload_changes(data_dir: Path, repo: str, gh=_gh) -> list[str]:
    """Upload each pending catalog-changes file (data/archive_out) to its month's release, then remove it."""
    done = []
    for p in sorted((data_dir / OUT).glob("catalog-changes-*.jsonl.gz")):
        m = re.search(r"catalog-changes-(\d{4})-?(\d{2})", p.name)
        if not m:
            continue  # a fetch stamp always starts YYYYMMDD; anything else is left in place
        put_new(f"catalog-changes-{m.group(1)}-{m.group(2)}", "catalog-changes", {p.name: p}, repo, gh)
        done.append(p.name)
        p.unlink()
    return done


def upload_archive(archive_path: Path, today: date, tmp_dir: Path, repo: str, gh=_gh) -> list[str]:
    """Today's dated copy of the daily archive (gzipped), once a day: the first run of the day uploads it."""
    if not archive_path.exists():
        return []
    name = f"archive-{today.isoformat()}.json.gz"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    q = tmp_dir / name
    q.write_bytes(gzip.compress(archive_path.read_bytes(), 9))
    return put_new(f"archive-{today.strftime('%Y-%m')}", "archive", {name: q}, repo, gh)


def week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def upload_catalog_week(catalog_gz: Path, today: date, repo: str, gh=_gh) -> list[str]:
    """A dated copy of the built catalog, once per ISO week (named by that week's Monday; no clobber)."""
    mon = week_monday(today)
    name = f"catalog-{mon.isoformat()}.json.gz"
    return put_new(f"catalog-archive-{mon.strftime('%Y-%m')}", "catalog-archive", {name: catalog_gz}, repo, gh)
