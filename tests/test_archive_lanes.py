"""Private archive lanes: every file Orbit's workflows replace or remove, on its public releases and its site, also
lands in the private tic-archive and restores from it byte for byte.

  update.yml   lane site (site/data as built and checked; each deploy replaces it) and lane catalog-changes (the
               GCAT change files, removed from the runner once on their public release)
  catalog.yml  lane catalog-release (release `catalog` keeps only its newest files) and lane catalog-raw (the run's
               raw replies, which live only on the runner)
  geo.yml      lane geo-release (releases geo-YYYY keep only the newest version of each file)

Offline: tic_archive's DirStore stands in for the private repository, the releases are local folders, and any
subprocess call fails the test. The workflow lanes run the workflow's own tic_archive.py commands, read from the YAML.
"""
from __future__ import annotations

import contextlib
import gzip
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT / "tools"))   # after ROOT: tools/orbit.py must not shadow the orbit package
sys.path.insert(0, str(ROOT / "tests"))

import tic_archive as ta  # noqa: E402
from orbit import geo_region as G, retention, stcat  # noqa: E402
from test_geo_region import FakeRelease, GpReply, cli, month_rows  # noqa: E402  (cli: tools/orbit.py)

WF = ROOT / ".github" / "workflows"
T0 = datetime(2026, 11, 27, 17, 23, tzinfo=timezone.utc)


class Clock:
    """tic_archive's clock, a second further on at each reading, so every snapshot has its own stamp."""

    def __init__(self, start=T0):
        self.t = start

    def __call__(self):
        self.t += timedelta(seconds=1)
        return self.t


def no_subprocess(*a, **k):
    raise AssertionError(f"no subprocess in these tests: {a[:1]}")


def step_block(workflow: str, name: str) -> str:
    text = (WF / workflow).read_text(encoding="utf-8")
    block = text[text.index(f"- name: {name}\n"):]
    end = block.find("\n      - ", 10)
    return block if end < 0 else block[:end]


def put_commands(workflow: str, name: str) -> list[list[str]]:
    """The tic_archive.py put commands of one workflow step, as argument lists."""
    joined = step_block(workflow, name).replace("\\\n", " ")
    out = []
    for line in joined.splitlines():
        if "tools/tic_archive.py put" in line:
            args = shlex.split(line.split("||")[0])
            out.append(args[args.index("tools/tic_archive.py") + 1:])
    return out


def run_puts(cmds, cwd: Path, store, clock) -> None:
    """Runs the commands with cwd as the run's checkout, against `store`; any failure fails the test."""
    here = os.getcwd()
    fake_dt = type("FakeDT", (datetime,), {"now": classmethod(lambda cls, tz=None: clock())})
    try:
        os.chdir(cwd)
        with mock.patch.object(ta, "GhStore", lambda *a, **k: store), mock.patch.object(ta, "datetime", fake_dt), \
                mock.patch.object(subprocess, "run", no_subprocess), contextlib.redirect_stdout(io.StringIO()):
            for c in cmds:
                assert ta.main(c) == 0, c
    finally:
        os.chdir(here)


def restore_all(store, lane: str, dest: Path) -> list[dict]:
    """Every snapshot of the lane restored under dest/<index name>/; returns the snapshot documents in order."""
    arc = ta.Archive(store, "orbit", lane)
    docs = []
    for tag in store.tags(arc.prefix):
        for name in sorted(n for n in store.assets(tag) if n.endswith(".files.json")):
            with contextlib.redirect_stdout(io.StringIO()):
                docs.append(arc.restore(dest / name, snapshot=name))
            docs[-1]["_dir"] = dest / name
    return docs


def versions(docs, name: str) -> set[bytes]:
    """Every version of file `name` the lane's snapshots hold."""
    return {(d["_dir"] / name).read_bytes() for d in docs if (d["_dir"] / name).exists()}


def tree(root: Path, skip=()) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and not any(p.relative_to(root).as_posix().startswith(s) for s in skip)}


# ---------------------------------------------------------------- update.yml: site and catalog-changes
class UpdateLanes(unittest.TestCase):
    STEP = "Private archive (published data and GCAT catalog changes, to tic-archive)"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.run_dir = self.tmp / "run"
        shutil.copytree(ROOT / "doctrine", self.run_dir / "doctrine")
        (self.run_dir / "data").mkdir()
        self.store = ta.DirStore(self.tmp / "store")
        self.clock = Clock()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, at: str, change: bool = True) -> None:
        """One update run's output as the deploy and the public archive step see it: site/data from build_site, the
        GEO page's files, the catalog shards object-data unpacks, and a GCAT change file."""
        snap = {"generated_at": at, "lanes": {"catalog": {"status": "ok"}}, "catalog_changes": {"added": 1}}
        (self.run_dir / "data" / "snapshot.json").write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n",
                                                             encoding="utf-8", newline="\n")
        cli.build_site(self.run_dir, snap)
        geo = self.run_dir / "site" / "data" / "geo"
        geo.mkdir(parents=True, exist_ok=True)
        (geo / "globe.json").write_text(json.dumps({"at": at}), encoding="utf-8")
        (geo / "movers.json").write_text(json.dumps({"movers": [], "at": at}), encoding="utf-8")
        cat = self.run_dir / "site" / "data" / "catalog"
        cat.mkdir(parents=True, exist_ok=True)
        (cat / "n41.json").write_text("{}", encoding="utf-8")
        (cat / "search.json").write_text("{}", encoding="utf-8")
        if change:
            retention.write_changes(self.run_dir / "data", [{"kind": "reading", "read_at": at}], at)

    def test_the_step_comes_after_the_deploy_and_before_the_public_upload(self):
        text = (WF / "update.yml").read_text(encoding="utf-8")
        deploy = text.index("- name: Deploy site/ to Cloudflare Pages")
        mine = text.index(f"- name: {self.STEP}")
        public = text.index("- name: Archive to monthly releases")
        self.assertLess(deploy, mine)
        self.assertLess(mine, public)   # the public step removes the change files from the runner
        block = step_block("update.yml", self.STEP)
        self.assertIn("if: ${{ !cancelled() }}", block)
        self.assertIn("GH_TOKEN: ${{ secrets.TIC_ARCHIVE_TOKEN }}", block)
        self.assertNotIn("github.token", block)
        self.assertIn("CHECKED: ${{ steps.check.outcome }}", block)
        self.assertIn("id: check", text[text.index("- name: Feed check"):][:80])

    def test_every_published_data_file_restores(self):
        self.build("2026-11-27T00:55:00Z")
        run_puts(put_commands("update.yml", self.STEP), self.run_dir, self.store, self.clock)
        site = restore_all(self.store, "site", self.tmp / "restored")
        self.assertEqual(len(site), 1)
        want = tree(self.run_dir / "site" / "data", skip=("catalog/",))
        self.assertIn("snapshot.json", want)
        self.assertIn("feed.geojson", want)
        self.assertIn("geo/globe.json", want)
        self.assertEqual(tree(site[0]["_dir"]), want)
        # the shards are release `catalog`'s, archived by catalog.yml (lane catalog-release), not here
        self.assertFalse(any(f["path"].startswith("catalog/") for f in site[0]["files"]))

    def test_a_replaced_site_file_and_a_removed_change_file_stay_restorable(self):
        firsts = {}
        for at in ("2026-11-27T00:55:00Z", "2026-11-27T06:55:00Z"):
            self.build(at)
            firsts.setdefault("snapshot", (self.run_dir / "site" / "data" / "snapshot.json").read_bytes())
            changes = sorted((self.run_dir / "data" / retention.OUT).glob("catalog-changes-*.jsonl.gz"))
            sent = {p.name: p.read_bytes() for p in changes}
            run_puts(put_commands("update.yml", self.STEP), self.run_dir, self.store, self.clock)
            gh = mock.Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
            retention.upload_changes(self.run_dir / "data", "o/r", gh=gh)   # the public step: upload, then remove
            self.assertEqual(list((self.run_dir / "data" / retention.OUT).glob("catalog-changes-*")), [])
            got = restore_all(self.store, "catalog-changes", self.tmp / f"changes-{at[11:13]}")
            for name, body in sent.items():
                self.assertIn(body, versions(got, name))
        site = restore_all(self.store, "site", self.tmp / "site")
        self.assertEqual(len(site), 2)
        self.assertIn(firsts["snapshot"], versions(site, "snapshot.json"))       # replaced by the second deploy
        self.assertEqual(len(versions(site, "snapshot.json")), 2)

    def test_a_run_without_a_gcat_reading_archives_the_site_only(self):
        self.build("2026-11-27T00:55:00Z", change=False)
        cmds = [c for c in put_commands("update.yml", self.STEP) if "catalog-changes" not in c]
        run_puts(cmds, self.run_dir, self.store, self.clock)
        self.assertIn("ls data/archive_out/catalog-changes-*.jsonl.gz", step_block("update.yml", self.STEP))
        self.assertEqual(self.store.tags("orbit-catalog-changes-"), [])

    def test_the_cache_paths_are_in_the_archive(self):
        """The Actions cache (evicted after 7 days unused) holds data/snapshot.json and data/state: data/state goes to
        lane state, and the snapshot as site/data/snapshot.json, the same bytes as collect writes."""
        text = (WF / "update.yml").read_text(encoding="utf-8")
        cache = text[text.index("- name: Keep this run's state for the next run"):][:300]
        self.assertIn("data/snapshot.json", cache)
        self.assertIn("data/state", cache)
        self.assertIn("--lane state --src data/state", text)
        self.build("2026-11-27T00:55:00Z")
        self.assertEqual((self.run_dir / "site" / "data" / "snapshot.json").read_bytes(),
                         (self.run_dir / "data" / "snapshot.json").read_bytes())


# ---------------------------------------------------------------- catalog.yml: catalog-release and catalog-raw
class FakeGh:
    """gh against release `catalog` (and the weekly copy's release), in local folders <root>/<tag>/<asset>."""

    def __init__(self, root: Path):
        self.root = root
        self.calls = []
        self.truncate = set()

    def uploads(self):
        return [a for a in self.calls if a[:2] == ["release", "upload"]]

    def __call__(self, *args):
        a = list(args)
        self.calls.append(a)
        ok = lambda out="": subprocess.CompletedProcess(a, 0, out, "")  # noqa: E731
        bad = lambda err: subprocess.CompletedProcess(a, 1, "", err)    # noqa: E731
        if a[0] == "api":
            tag = re.fullmatch(r"repos/[^/]+/[^/]+/releases/tags/(.+)", a[1]).group(1)
            d = self.root / tag
            if not d.is_dir():
                return bad("HTTP 404")
            return ok("".join(f"{p.stat().st_size} {p.name}\n" for p in sorted(d.iterdir())))
        verb, tag = a[1], a[2]
        d = self.root / tag
        if verb == "view":
            if not d.is_dir():
                return bad("release not found")
            return ok("".join(f"{p.name}\n" for p in sorted(d.iterdir())) if "--json" in a else "")
        if verb == "create":
            d.mkdir(parents=True)
            return ok()
        if verb == "edit":
            return ok()
        if verb == "upload":
            shutil.copyfile(a[-1], d / Path(a[-1]).name)
            return ok()
        if verb == "download":
            name = a[a.index("-p") + 1]
            if not (d / name).exists():
                return bad("no assets match")
            dest = Path(a[a.index("-O") + 1]) if "-O" in a else Path(a[a.index("-D") + 1]) / name
            data = (d / name).read_bytes()
            dest.write_bytes(data[: len(data) // 2] if name in self.truncate else data)
            return ok()
        raise AssertionError(f"unexpected gh call {a}")


class CatalogLanes(unittest.TestCase):
    """catalog_release over four starts: the release's files before each due read and each day's uploads land in
    lane catalog-release, so every version that was ever on the release restores from the archive."""
    ASSETS = (stcat.CATALOG_ASSET, stcat.NAMES_ASSET, "catalog-shards.tar.gz", "catalog-search.json.gz",
              "catalog-rules.json")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.gh = FakeGh(self.tmp / "release")
        self.store = ta.DirStore(self.tmp / "store")
        self.aclock = Clock()
        self.archive_calls, self.fail_after_upload, self.fail_all, self.reads = [], False, False, 0
        self.now = T0
        rel = self.tmp / "release" / stcat.RELEASE
        rel.mkdir(parents=True)
        for name in self.ASSETS:
            (rel / name).write_bytes(f"{name} v0".encode())
        (rel / stcat.DECAY_ASSET).write_bytes(gzip.compress(b"[]", mtime=0))
        (rel / stcat.STATE_ASSET).write_text(json.dumps({"satcat_day": "2026-11-26"}), encoding="utf-8")
        (rel / stcat.SOURCES_STATE_ASSET).write_text("{}", encoding="utf-8")
        self.ever = {n: {(rel / n).read_bytes()} for n in os.listdir(rel)}   # every version the release held
        fake_dt = type("FakeDT", (datetime,), {"now": classmethod(lambda cls, tz=None: self.now)})
        exists, get, copy, put, week = (stcat.release_exists, stcat.release_get, stcat.release_copy,
                                        stcat.release_put, retention.upload_catalog_week)
        self.patches = [
            mock.patch.object(cli, "datetime", fake_dt),
            mock.patch.object(stcat, "release_exists", lambda repo, gh=None: exists(repo, self.gh)),
            mock.patch.object(stcat, "release_get", lambda d, repo, gh=None: get(d, repo, self.gh)),
            mock.patch.object(stcat, "release_copy", lambda d, repo, gh=None: copy(d, repo, self.gh)),
            mock.patch.object(stcat, "release_put", lambda paths, repo, gh=None: put(paths, repo, self.gh)),
            mock.patch.object(retention, "upload_catalog_week", lambda c, day, repo, gh=None: week(c, day, repo, self.gh)),
            mock.patch.object(stcat, "pull", self.pull),
            mock.patch.object(cli.spacetrack, "credentials", return_value=("u", "p")),
            mock.patch.object(cli, "catalog_sources", lambda data_dir, *a: 0),
            mock.patch.object(cli.fetch, "get", lambda url, *a, **k: b"gcat table"),
            mock.patch.object(cli, "catalog_local", self.build),
            mock.patch.object(cli, "CATALOG_ARCHIVE", self.archive),
            mock.patch.object(subprocess, "run", no_subprocess),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def pull(self, data_dir, cred, now=None, history_held=False, **k):
        state = stcat.read_json(data_dir / stcat.STATE, {})
        why = stcat.due(now, state)
        if why:
            raise cli.spacetrack.NotReady(why)
        self.reads += 1
        state.update({"satcat_day": stcat.satcat_day(now), "satcat_read_at": f"{now:%Y-%m-%dT%H:%M:%SZ}",
                      "satcat_rows": 1, "decay_query": "since", "decay_rows_read": 0, "decay_added": 0,
                      "decay_held": 0})
        stcat.write_json(data_dir / stcat.STATE, state)
        (data_dir / "state").mkdir(parents=True, exist_ok=True)
        (data_dir / "state" / stcat.SOURCES_STATE_ASSET).write_text("{}", encoding="utf-8")
        return {"state": state, "requests": 4}

    def build(self, raw, out, data_dir):
        out.parent.mkdir(parents=True, exist_ok=True)
        for name in self.ASSETS:
            (out.parent / name).write_bytes(f"{name} built {self.now:%Y-%m-%d}".encode())
        return 0

    def archive(self, lane, folder):
        self.archive_calls.append(lane)
        uploaded = any(a for a in self.gh.uploads() if a[2] == stcat.RELEASE and a not in self.before_run)
        if self.fail_all or (self.fail_after_upload and uploaded):
            raise G.ReleaseError(f"the copy to the private archive (lane {lane}) failed")
        with contextlib.redirect_stdout(io.StringIO()):
            ta.Archive(self.store, "orbit", lane).put(Path(folder), now=self.aclock())

    def start(self, when: datetime) -> int:
        self.now, self.before_run, self.reads, self.archive_calls = when, list(self.gh.uploads()), 0, []
        data = self.tmp / f"data-{when:%d%H}"
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = cli.catalog_release(data)
        self.log = buf.getvalue()
        rel = self.tmp / "release" / stcat.RELEASE
        for p in rel.iterdir():
            self.ever.setdefault(p.name, set()).add(p.read_bytes())
        return rc

    def test_every_version_the_release_held_restores(self):
        self.assertEqual(self.start(T0), 0)                                   # day 1: v0 kept, then v1
        self.assertEqual(self.archive_calls, ["catalog-release", "catalog-release"])
        self.assertEqual(self.start(T0 + timedelta(hours=2)), 0)              # same day: not due
        self.assertEqual((self.reads, self.archive_calls), (0, []))
        self.fail_after_upload = True
        self.assertEqual(self.start(T0 + timedelta(days=1)), 1)               # day 2: v2 public, its copy failed
        self.assertIn("::error::", self.log)
        self.fail_after_upload = False
        self.assertEqual(self.start(T0 + timedelta(days=2)), 0)               # day 3: v2 kept first, then v3
        docs = restore_all(self.store, "catalog-release", self.tmp / "restored")
        for name, held in self.ever.items():
            self.assertEqual(versions(docs, name), held, name)
        self.assertEqual(len(self.ever[stcat.CATALOG_ASSET]), 4)
        self.assertEqual(len(docs), 4)   # the day-3 copy of the release before the read held only day 2's new bytes

    def test_a_failed_copy_before_the_read_stops_the_run_before_space_track(self):
        self.fail_all = True
        before = {p.name: p.read_bytes() for p in (self.tmp / "release" / stcat.RELEASE).iterdir()}
        self.assertEqual(self.start(T0), 1)
        self.assertEqual(self.reads, 0)
        self.assertEqual(self.gh.uploads(), [])
        self.assertEqual({p.name: p.read_bytes() for p in (self.tmp / "release" / stcat.RELEASE).iterdir()}, before)

    def test_no_archive_token_stops_the_due_run_before_space_track(self):
        self.patches[11].stop()   # the real copy: no token, so it raises before running anything
        try:
            with mock.patch.dict(os.environ, {"TIC_ARCHIVE_TOKEN": ""}):
                self.assertEqual(self.start(T0), 1)
        finally:
            self.patches[11].start()
        self.assertEqual((self.reads, self.gh.uploads()), (0, []))

    def test_a_file_that_does_not_download_whole_stops_the_run(self):
        self.gh.truncate = {stcat.CATALOG_ASSET}
        self.assertEqual(self.start(T0), 1)
        self.assertEqual((self.reads, self.archive_calls), (0, []))
        self.assertIn("did not download whole", self.log)

    def test_the_catalog_step_gets_the_archive_token(self):
        block = step_block("catalog.yml", "Catalog (Space-Track SATCAT and DECAY, CelesTrak SATCAT, Wikidata, "
                                          "WMO OSCAR/Space, GCAT)")
        self.assertIn("TIC_ARCHIVE_TOKEN: ${{ secrets.TIC_ARCHIVE_TOKEN }}", block)
        self.assertIn("GH_TOKEN: ${{ github.token }}", block)


class CatalogRawLane(unittest.TestCase):
    STEP = "Private archive (the catalog run's raw replies, to tic-archive)"

    def test_every_reply_but_gcat_restores(self):
        block = step_block("catalog.yml", self.STEP)
        self.assertIn("if: ${{ !cancelled() }}", block)       # also when the catalog step failed
        self.assertIn("GH_TOKEN: ${{ secrets.TIC_ARCHIVE_TOKEN }}", block)
        self.assertNotIn("github.token", block)
        with tempfile.TemporaryDirectory() as td:
            run = Path(td) / "run"
            raw = run / "data" / "raw"
            for rel in ("spacetrack-satcat/20261127T1723Z.json.gz", "spacetrack-decay/20261127T1723Z.json.gz",
                        "celestrak-satcat/20261127T1724Z.csv.gz", "wikidata-p377/20261127T1724Z.json.gz",
                        "wmo-oscar/20261127/page-01.json", "gcat-satcat/20261127T1725Z.tsv.gz"):
                (raw / rel).parent.mkdir(parents=True, exist_ok=True)
                (raw / rel).write_bytes(rel.encode())
            store = ta.DirStore(Path(td) / "store")
            run_puts(put_commands("catalog.yml", self.STEP), run, store, Clock())
            doc, = restore_all(store, "catalog-raw", Path(td) / "restored")
            want = {k: v for k, v in tree(raw).items() if not k.startswith("gcat-")}
            self.assertEqual(len(want), 5)
            self.assertEqual(tree(doc["_dir"]), want)


# ---------------------------------------------------------------- geo.yml: geo-release
class GeoLane(unittest.TestCase):
    """Three GEO runs: every version of every file the releases geo-YYYY held restores from lane geo-release."""
    NOV = G.elements_name("2026-11")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.rel = FakeRelease(self.tmp / "release")
        rel = self.tmp / "release" / "geo-2026"
        rel.mkdir(parents=True)
        G.write_elements(str(self.rel.path(G.elements_name("2026-10"))), month_rows(range(1, 61), range(1, 6)))
        G.write_elements(str(self.rel.path(self.NOV)), month_rows(range(1, 61), range(1, 4), "2026-11"))
        G.region_file(str(rel), "2026-11-25", {}, [], {})
        self.ever = {p.name: {p.read_bytes()} for p in rel.iterdir()}
        self.store = ta.DirStore(self.tmp / "store")
        self.aclock = Clock()
        self.now = datetime(2026, 11, 26, 3, 20, tzinfo=timezone.utc)
        GpReply.day, GpReply.queries = "2026-11-26", 0
        self.patches = [mock.patch.object(G, "_gh", self.rel), mock.patch.object(cli, "ROOT", self.tmp),
                        mock.patch.object(cli, "GEO_ARCHIVE", self.archive),
                        mock.patch.object(cli, "ST_CLIENT", GpReply), mock.patch.object(cli, "ST_WAIT", lambda: 0.0),
                        mock.patch.object(cli, "ST_NOW", lambda: self.now),
                        mock.patch.object(cli, "ST_SHARED", lambda now, shared=None: None),
                        mock.patch.object(cli.spacetrack, "credentials", return_value=("u", "p")),
                        mock.patch.dict(os.environ, {"TIC_ARCHIVE_TOKEN": "test-archive-token"})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def archive(self, lane, folder):
        with contextlib.redirect_stdout(io.StringIO()):
            ta.Archive(self.store, "orbit", lane).put(Path(folder), now=self.aclock())

    def test_every_version_the_releases_held_restores(self):
        for day, now in (("2026-11-26", datetime(2026, 11, 26, 3, 20, tzinfo=timezone.utc)),
                         ("2026-11-26", datetime(2026, 11, 26, 15, 20, tzinfo=timezone.utc)),
                         ("2026-11-27", datetime(2026, 11, 27, 3, 20, tzinfo=timezone.utc))):
            self.now, GpReply.day = now, day
            out = Path(tempfile.mkdtemp(dir=self.tmp))
            with contextlib.redirect_stdout(io.StringIO()):
                rc = cli.geo_pull(day, out, True, getter=lambda url, timeout=60: json.dumps(
                    [{"NORAD_CAT_ID": k} for k in range(1, 61)]).encode())
            self.assertEqual(rc, 0)
            for p in (self.tmp / "release" / "geo-2026").iterdir():
                self.ever.setdefault(p.name, set()).add(p.read_bytes())
        self.assertGreaterEqual(len(self.ever["2026-11-26.geo-region.json"]), 2)   # replaced the same day
        self.assertGreaterEqual(len(self.ever[self.NOV]), 3)
        docs = restore_all(self.store, "geo-release", self.tmp / "restored")
        for name, held in self.ever.items():
            if name == "2026-11-25.geo-region.json" or name == G.elements_name("2026-10"):
                continue   # never replaced in these runs: the release holds them, no run touched them
            self.assertEqual(versions(docs, name), held, name)


# ---------------------------------------------------------------- lane names
class LaneNames(unittest.TestCase):
    def test_no_lane_prefix_starts_another(self):
        """tic_archive finds a lane's releases by the prefix orbit-<lane>-, so no lane's prefix may start another's.
        The lanes are read from the workflows and tools/orbit.py, plus the retired ledger lane still in the archive."""
        lanes = {"ledger"}
        for wf in WF.glob("*.yml"):
            lanes |= set(re.findall(r"--program orbit --lane ([a-z0-9-]+)", wf.read_text(encoding="utf-8")))
        code = (ROOT / "tools" / "orbit.py").read_text(encoding="utf-8")
        lanes |= set(re.findall(r'ARCHIVE\("([a-z0-9-]+)"', code))
        lanes |= set(re.findall(r'_archive_files\(\w+, "([a-z0-9-]+)"', code))
        self.assertTrue({"state", "raw", "site", "catalog-changes", "catalog-release", "catalog-raw", "geo-reply",
                         "geo-release"} <= lanes, lanes)
        for a in lanes:
            for b in lanes:
                if a != b:
                    self.assertFalse(f"orbit-{b}-".startswith(f"orbit-{a}-"), (a, b))


if __name__ == "__main__":
    unittest.main()
