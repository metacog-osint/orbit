"""The GEO region (orbit/geo_region.py), offline: regions and edges, events, the day file, the element files, and
the gp query's guard on the shared Space-Track account."""
import contextlib
import gzip
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from orbit import geo_region as G, spacetrack  # noqa: E402

N_GEO = 1.0027   # rev/day: about the GEO radius


def rec(norad, n=N_GEO, e=0.0002, i=0.05, epoch="2026-11-15T12:00:00.000000", kind="PAYLOAD", launch="2015-03-01",
        name=None):
    return {"NORAD_CAT_ID": str(norad), "EPOCH": epoch, "MEAN_MOTION": str(n), "ECCENTRICITY": str(e),
            "INCLINATION": str(i), "RA_OF_ASC_NODE": "80.1", "ARG_OF_PERICENTER": "200.2", "MEAN_ANOMALY": "10.3",
            "BSTAR": "0", "MEAN_MOTION_DOT": "0", "MEAN_MOTION_DDOT": "0", "ELEMENT_SET_NO": "999", "REV_AT_EPOCH": "4000",
            "OBJECT_NAME": name or f"SAT {norad}", "OBJECT_ID": "2015-010A", "OBJECT_TYPE": kind, "COUNTRY_CODE": "US",
            "LAUNCH_DATE": launch, "RCS_SIZE": "LARGE"}


class Regions(unittest.TestCase):
    def test_zone_graveyard_below_inclined(self):
        self.assertEqual(G.region_of(N_GEO, 0.0002, 0.05), "zone")
        self.assertEqual(G.region_of(0.985, 0.0002, 0.05), "graveyard")   # about 300 km above GEO
        self.assertEqual(G.region_of(1.02, 0.0002, 0.05), "below")
        self.assertEqual(G.region_of(N_GEO, 0.0002, 20.0), "inclined")
        self.assertEqual(G.region_of(N_GEO, 0.01, 5.0), "crossing")       # reaches the zone's altitudes, not inside

    def test_edges_hold_an_edge_rider(self):
        i = 14.9  # inside the 15 deg edge, but within 0.25 deg of it
        self.assertEqual(G.region_of(N_GEO, 0.0002, i), "zone")
        self.assertEqual(G.region_of(N_GEO, 0.0002, i, prev="inclined"), "crossing")  # not in the zone until 0.25 deg inside
        self.assertEqual(G.region_of(N_GEO, 0.0002, 15.1, prev="zone"), "zone")       # must go 0.25 deg outside

    def test_near_geo(self):
        self.assertTrue(G.near_geo(1.0, 0.1))
        self.assertFalse(G.near_geo(1.2, 0.1))
        self.assertFalse(G.near_geo(1.0, 0.3))


class Days(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_day_then_events(self):
        day1 = [rec(1), rec(2), rec(3, n=1.02), rec(4)]
        s, paths = G.pull("2026-11-14", self.out, day1, active={1, 2, 4}, fetched="2026-11-14T03:20Z")
        self.assertTrue(s["first_day"])
        self.assertEqual(s["events"], 0)
        self.assertEqual(s["objects"], 4)
        day2 = [rec(1, n=0.985, epoch="2026-11-15T01:00:00"),                            # left up
                rec(2, epoch="2026-11-05T00:00:00"),                                       # quiet (old elements)
                rec(3, epoch="2026-11-15T02:00:00"),                                       # arrived from below
                rec(5, epoch="2026-11-15T03:00:00", launch="2026-10-30")]                  # new, arrived
        # 4 gone; 2's day-1 epoch must be fresh for "quiet" to fire on day 2
        s2, _ = G.pull("2026-11-15", self.out, day2, active=None, fetched="2026-11-15T03:20Z")
        doc = G.load_region(self.out, "2026-11-15")
        kinds = sorted((e["norad"], e["kind"]) for e in doc["events"])
        self.assertIn((1, "left up"), kinds)
        self.assertIn((3, "arrived"), kinds)
        self.assertIn((4, "gone"), kinds)
        self.assertIn((5, "new"), kinds)
        self.assertIn((5, "arrived"), kinds)
        self.assertEqual(doc["active"], [1, 2, 4])  # CelesTrak not read: yesterday's list carried
        self.assertEqual(doc["object_cols"][-2:], ["elset", "rev"])
        self.assertEqual(doc["source"], G.CITE)

    def test_quiet_needs_fresh_elements_the_day_before(self):
        G.pull("2026-11-14", self.out, [rec(2, epoch="2026-11-14T00:00:00")], active={2})
        G.pull("2026-11-15", self.out, [rec(2, epoch="2026-11-07T12:00:00")], active={2})
        kinds = [e["kind"] for e in G.load_region(self.out, "2026-11-15")["events"]]
        self.assertEqual(kinds, ["quiet"])

    def test_quiet_only_for_active_payloads(self):
        G.pull("2026-11-14", self.out, [rec(2, epoch="2026-11-14T00:00:00")], active={9})
        G.pull("2026-11-15", self.out, [rec(2, epoch="2026-11-07T12:00:00")], active={9})
        self.assertEqual(G.load_region(self.out, "2026-11-15")["events"], [])

    def test_element_files_merge_by_month_and_drop_before_history(self):
        G.pull("2026-11-14", self.out, [rec(1, epoch="2026-11-14T00:00:00"), rec(2, epoch="2026-06-30T00:00:00")])
        G.pull("2026-11-15", self.out, [rec(1, epoch="2026-11-15T00:00:00"), rec(1, epoch="2026-11-14T00:00:00")])
        rows = G.read_elements(os.path.join(self.out, G.elements_name("2026-11")))
        self.assertEqual([(r["norad"], r["epoch"][:10]) for r in rows], [(1, "2026-11-14"), (1, "2026-11-15")])
        self.assertFalse(os.path.exists(os.path.join(self.out, G.elements_name("2026-06"))))
        with gzip.open(os.path.join(self.out, G.elements_name("2026-11")), "rt", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["schema"], "orbit-geo-elements/1")

    def test_release_tags_by_year(self):
        self.assertEqual(G.tag_for("2026-11-15.geo-region.json"), "geo-2026")
        self.assertEqual(G.tag_for("geo-elements-2027-01.json.gz"), "geo-2027")

    def test_active_ids(self):
        self.assertEqual(G.active_ids(json.dumps([{"NORAD_CAT_ID": 1}, {"NORAD_CAT_ID": "26038"}]).encode()), {1, 26038})
        with self.assertRaises(ValueError):
            G.active_ids(b"[]")


class SharedAccount(unittest.TestCase):
    """The GEO query waits for Orbit's update run; the update run waits for this one. Noisefloor makes no GP query from
    18 Nov 2026, so neither waits for it (orbit-2.21)."""
    NOW = datetime(2026, 11, 16, 15, 30, tzinfo=timezone.utc)

    def get(self, busy_url):
        def _get(url):
            if url == busy_url:
                return {"workflow_runs": [{"id": 7, "status": "in_progress", "run_started_at": "2026-11-16T15:20:00Z",
                                           "jobs_url": "jobs"}]}
            if url.startswith("https://api.github.com"):
                return {"workflow_runs": []}
            return {"jobs": []}
        return _get

    NF_RUNS = "https://api.github.com/repos/metacog-osint/noise-floor/actions/workflows/daily.yml/runs?per_page=5"

    def test_geo_waits_for_update_only(self):
        self.assertIn("update run", spacetrack.shared_gp_busy(self.NOW, self.get(spacetrack.UPDATE_RUNS), spacetrack.FOR_GEO))
        self.assertIsNone(spacetrack.shared_gp_busy(self.NOW, self.get(spacetrack.GEO_RUNS), spacetrack.FOR_GEO))
        self.assertIsNone(spacetrack.shared_gp_busy(self.NOW, self.get(self.NF_RUNS), spacetrack.FOR_GEO))

    def test_noisefloor_is_not_checked(self):
        for shared in (spacetrack.FOR_GEO, spacetrack.FOR_MANEUVER):
            self.assertFalse([url for url, _, _ in shared if "noise-floor" in url])

    def test_update_waits_for_geo(self):
        self.assertIn("GEO region", spacetrack.shared_gp_busy(self.NOW, self.get(spacetrack.GEO_RUNS)))
        self.assertIsNone(spacetrack.shared_gp_busy(self.NOW, self.get(spacetrack.UPDATE_RUNS)))

    def test_geo_step_names_match_the_workflows(self):
        geo = (ROOT / ".github" / "workflows" / "geo.yml").read_text(encoding="utf-8")
        upd = (ROOT / ".github" / "workflows" / "update.yml").read_text(encoding="utf-8")
        self.assertIn(f"name: {spacetrack.GEO_STEP}\n", geo)
        self.assertIn(f"name: {spacetrack.UPDATE_STEP}\n", upd)


# ---------------------------------------------------------------- the releases, offline
class FakeRelease:
    """Stands in for `gh` against GitHub's releases: a local folder <root>/<tag>/<asset>, no network. Downloads named
    in `fail` exit non-zero, those in `truncate` write half the file and exit 0; `list_fail` makes every listing
    fail with HTTP 500. Every call is logged in `calls` (shared with the archive stand-in, for the order)."""

    def __init__(self, root, calls=None):
        self.root = Path(root)
        self.fail, self.truncate, self.list_fail = set(), set(), False
        self.calls = [] if calls is None else calls

    def __call__(self, *args):
        a = list(args)
        self.calls.append(a)
        ok = lambda out="": subprocess.CompletedProcess(a, 0, out, "")  # noqa: E731
        bad = lambda err: subprocess.CompletedProcess(a, 1, "", err)    # noqa: E731
        if a[0] == "api":
            if self.list_fail:
                return bad("gh: Server Error (HTTP 500)")
            path = next(x for x in a[1:] if x.startswith("repos/"))
            m = re.fullmatch(r"repos/[^/]+/[^/]+/releases/tags/([^/?]+)", path)
            if m:
                return ok(m.group(1) + "\n") if (self.root / m.group(1)).is_dir() else bad("gh: Not Found (HTTP 404)")
            m = re.fullmatch(r"repos/[^/]+/[^/]+/releases/([^/?]+)/assets\?per_page=100", path)
            d = self.root / m.group(1)
            return ok("".join(f"{p.stat().st_size} {p.name}\n" for p in sorted(d.iterdir())))
        tag = a[2]
        if a[1] == "download":
            name, out = a[a.index("-p") + 1], a[a.index("-D") + 1]
            src = self.root / tag / name
            if name in self.fail:
                return bad("HTTP 502: Bad Gateway")
            if not src.exists():
                return bad("no assets match the file pattern")
            data = src.read_bytes()
            Path(out, name).write_bytes(data[: len(data) // 2] if name in self.truncate else data)
            return ok()
        if a[1] == "view":
            return ok() if (self.root / tag).is_dir() else bad("release not found")
        if a[1] == "create":
            (self.root / tag).mkdir(parents=True)
            return ok()
        if a[1] == "upload":
            shutil.copyfile(a[-1], self.root / tag / os.path.basename(a[-1]))
            return ok()
        raise AssertionError(f"unexpected gh call {a}")

    def uploads(self):
        return [os.path.basename(a[-1]) for a in self.calls if a[:2] == ["release", "upload"]]

    def path(self, name):
        return self.root / G.tag_for(name) / name


def month_rows(norads, days, month="2026-10"):
    return [G.elset_row(rec(k, epoch=f"{month}-{d:02d}T06:00:00.000000")) for k in norads for d in days]


_spec = importlib.util.spec_from_file_location("orbit_cli_geo", ROOT / "tools" / "orbit.py")
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)


class GpReply:
    """Space-Track's gp reply for the GEO query, offline: objects 1-55 have a set from today, objects 56-60 still
    have October's as their newest (so October's file is read on every run while they stay in the reply)."""
    day = "2026-11-26"
    queries = 0

    def __init__(self, ident, pw):
        self.requests, self.last_body = 0, b""

    def login(self):
        self.requests += 1

    def logout(self):
        self.requests += 1

    def query_path(self, path):
        GpReply.queries += 1
        self.requests += 1
        recs = [rec(k, epoch=f"{GpReply.day}T01:00:00.000000") for k in range(1, 56)]
        recs += [rec(k, epoch="2026-10-05T06:00:00.000000") for k in range(56, 61)]
        self.last_body = json.dumps(recs).encode()
        return recs


class ReleaseGuard(unittest.TestCase):
    """A GEO upload never loses what the releases hold. Without these guards, a month file whose download failed was
    rebuilt from one reply's sets and uploaded over the release's copy (here: October 300 sets -> 5, November
    180 -> 55, exit 0). Offline: FakeRelease stands in for gh, and the archive is a stand-in that records what it
    was given."""
    NOW = datetime(2026, 11, 26, 3, 20, tzinfo=timezone.utc)
    OCT, NOV = G.elements_name("2026-10"), G.elements_name("2026-11")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.calls, self.archived, self.archive_fails = [], {}, set()
        self.rel = FakeRelease(self.tmp / "release", self.calls)
        (self.tmp / "release" / "geo-2026").mkdir(parents=True)
        G.write_elements(str(self.rel.path(self.OCT)), month_rows(range(1, 61), range(1, 6)))            # 300 sets
        G.write_elements(str(self.rel.path(self.NOV)), month_rows(range(1, 61), range(1, 4), "2026-11"))  # 180 sets
        G.region_file(str(self.tmp / "release" / "geo-2026"), "2026-11-25", {}, [], {})
        self.before = {n: self.rel.path(n).read_bytes() for n in (self.OCT, self.NOV)}
        GpReply.day, GpReply.queries = "2026-11-26", 0
        self.patches = [mock.patch.object(G, "_gh", self.rel), mock.patch.object(cli, "ROOT", self.tmp),
                        mock.patch.object(cli, "GEO_ARCHIVE", self.archive),
                        mock.patch.object(cli, "ST_CLIENT", GpReply), mock.patch.object(cli, "ST_WAIT", lambda: 0.0),
                        mock.patch.object(cli, "ST_NOW", lambda: self.NOW),
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
        self.calls.append(["archive", lane])
        if lane in self.archive_fails:
            raise G.ReleaseError(f"the copy to the private archive (lane {lane}) failed")
        self.archived.setdefault(lane, []).append({p.name: p.read_bytes() for p in Path(folder).iterdir()})

    def run_geo(self, day="2026-11-26"):
        """geo_pull's exit code; its log is kept in self.log (not printed: Actions would read the ::error:: lines of
        these expected failures as annotations on the GEO run)."""
        out = Path(tempfile.mkdtemp(dir=self.tmp))   # each run starts empty, as on GitHub's runners
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli.geo_pull(day, out, True, getter=lambda url, timeout=60: json.dumps(
                [{"NORAD_CAT_ID": k} for k in range(1, 61)]).encode())
        self.log = buf.getvalue()
        if rc:
            self.assertIn("::error::GEO region: ", self.log)
            self.assertIn("Nothing uploaded.", self.log)
        return rc

    def held_sets(self, name):
        return G.element_keys(str(self.rel.path(name)))

    def assert_release_untouched(self):
        self.assertEqual(self.rel.uploads(), [])
        for name, data in self.before.items():
            self.assertEqual(self.rel.path(name).read_bytes(), data, name)

    def test_the_reproduction_a_failed_download_no_longer_rebuilds_a_month_from_one_reply(self):
        # Before the guard: exit 0, October 300 -> 5 sets and November 180 -> 55, both uploaded over the release.
        for fail in ({self.OCT}, {self.NOV}, {self.OCT, self.NOV}):
            with self.subTest(fail=sorted(fail)):
                self.rel.fail = fail
                self.assertEqual(self.run_geo(), 1)
                self.assert_release_untouched()
                self.assertEqual(len(self.held_sets(self.OCT)), 300)
                self.assertEqual(len(self.held_sets(self.NOV)), 180)
                reply, = self.archived["geo-reply"][-1].values()   # the stopped run's sets are kept, privately
                self.assertEqual(len(json.loads(gzip.decompress(reply))), 60)

    def test_a_truncated_download_stops_the_upload(self):
        self.rel.truncate = {self.NOV}
        self.assertEqual(self.run_geo(), 1)
        self.assert_release_untouched()

    def test_a_listing_that_fails_is_never_taken_for_a_missing_file(self):
        self.rel.list_fail = True
        self.assertEqual(self.run_geo(), 1)
        self.assert_release_untouched()
        self.assertEqual(GpReply.queries, 0)

    def test_a_past_month_missing_from_the_release_is_not_rebuilt(self):
        self.rel.path(self.OCT).unlink()
        self.assertEqual(self.run_geo(), 1)
        self.assertEqual(self.rel.uploads(), [])
        self.assertFalse(self.rel.path(self.OCT).exists())

    def test_a_new_month_starts_its_file(self):
        GpReply.day = "2026-12-01"
        self.assertEqual(self.run_geo("2026-12-01"), 0)
        self.assertEqual(len(self.held_sets(G.elements_name("2026-12"))), 55)
        self.assertEqual(self.rel.path(self.OCT).read_bytes(), self.before[self.OCT])

    def test_a_clean_run_archives_each_file_it_replaces_before_uploading(self):
        self.assertEqual(self.run_geo(), 0)
        self.assertEqual(self.rel.uploads(), ["2026-11-26.geo-region.json", self.NOV])
        replaced, uploaded = self.archived["geo-release"]
        self.assertEqual(replaced, {self.NOV: self.before[self.NOV]})  # the copy replaced
        self.assertEqual(uploaded, {n: self.rel.path(n).read_bytes() for n in self.rel.uploads()})  # and the new ones
        order = [c[1] if c[0] == "archive" else "upload" for c in self.calls
                 if c[0] == "archive" or c[:2] == ["release", "upload"]]
        self.assertEqual(order, ["geo-reply", "geo-release", "geo-release", "upload", "upload"])
        old = self.tmp / "old-nov.json.gz"
        old.write_bytes(self.before[self.NOV])
        nov = self.held_sets(self.NOV)
        self.assertEqual(len(nov), 235)
        self.assertTrue(G.element_keys(str(old)) <= nov)
        self.assertEqual(self.rel.path(self.OCT).read_bytes(), self.before[self.OCT])     # no new set: not uploaded

    def test_a_replaced_day_file_is_archived_too(self):
        self.assertEqual(self.run_geo(), 0)
        first = self.rel.path("2026-11-26.geo-region.json").read_bytes()
        self.NOW = datetime(2026, 11, 26, 15, 20, tzinfo=timezone.utc)
        self.assertEqual(self.run_geo(), 0)
        self.assertEqual(self.archived["geo-release"][-2]["2026-11-26.geo-region.json"], first)  # replaced copy

    def test_a_failed_archive_copy_stops_the_replace(self):
        self.archive_fails = {"geo-release"}
        self.assertEqual(self.run_geo(), 1)
        self.assert_release_untouched()
        self.archive_fails = {"geo-reply"}
        self.assertEqual(self.run_geo(), 1)
        self.assert_release_untouched()

    def test_no_archive_token_stops_before_space_track_is_read(self):
        with mock.patch.dict(os.environ, {"TIC_ARCHIVE_TOKEN": ""}):
            self.assertEqual(self.run_geo(), 1)
        self.assertEqual(GpReply.queries, 0)
        self.assert_release_untouched()

    def test_a_day_file_that_fails_to_download_stops_before_space_track_is_read(self):
        self.rel.fail = {"2026-11-25.geo-region.json"}
        self.assertEqual(self.run_geo(), 1)
        self.assertEqual(GpReply.queries, 0)
        self.assert_release_untouched()

    def test_release_put_refuses_an_upload_that_drops_sets(self):
        # The second guard, at the upload itself: a November file of today's sets alone, over the release's 180.
        local = self.tmp / "local"
        local.mkdir()
        G.write_elements(str(local / self.NOV), month_rows(range(1, 56), [26], "2026-11"))
        with self.assertRaisesRegex(G.ReleaseError, "drop 180 of the 180 element sets"):
            G.release_put([str(local / self.NOV)], archive=lambda folder: self.archive("geo-release", folder))
        self.assert_release_untouched()
        self.assertNotIn("geo-release", self.archived)

    def test_release_put_without_an_archive_refuses_any_replace(self):
        # tools/geo_import.py calls release_put without one: a re-run of the import cannot replace Orbit's files.
        local = self.tmp / "local"
        local.mkdir()
        G.write_elements(str(local / self.NOV), month_rows(range(1, 61), range(1, 5), "2026-11"))
        with self.assertRaisesRegex(G.ReleaseError, "no archive copy"):
            G.release_put([str(local / self.NOV)])
        self.assert_release_untouched()


class ArchiveCopy(unittest.TestCase):
    """The copy to the private archive runs tools/tic_archive.py with the archive's own token, never the repo's."""

    def test_tic_archive_put_with_its_own_token(self):
        seen = {}

        def run(args, env):
            seen.update(args=args, env=env)
            return subprocess.CompletedProcess(args, 0)

        with mock.patch.object(cli.subprocess, "run", run), \
                mock.patch.dict(os.environ, {"TIC_ARCHIVE_TOKEN": "archive-token", "GH_TOKEN": "repo-token"}):
            cli._tic_archive("geo-release", "folder")
        self.assertEqual(seen["args"][1:], [str(ROOT / "tools" / "tic_archive.py"), "put", "--program", "orbit",
                                            "--lane", "geo-release", "--src", "folder"])
        self.assertEqual(seen["env"]["GH_TOKEN"], "archive-token")

    def test_a_failed_or_tokenless_copy_raises(self):
        with mock.patch.object(cli.subprocess, "run", lambda args, env: subprocess.CompletedProcess(args, 1)), \
                mock.patch.dict(os.environ, {"TIC_ARCHIVE_TOKEN": "archive-token"}):
            with self.assertRaises(G.ReleaseError):
                cli._tic_archive("geo-reply", "folder")
        with mock.patch.dict(os.environ, {"TIC_ARCHIVE_TOKEN": ""}):
            with self.assertRaises(G.ReleaseError):
                cli._tic_archive("geo-reply", "folder")

    def test_lanes_do_not_share_a_tag_prefix(self):
        # tic_archive finds a lane's releases by the prefix orbit-<lane>-; no lane's prefix may start another's.
        lanes = ["state", "raw", "ledger", "geo-release", "geo-reply"]
        for a in lanes:
            for b in lanes:
                if a != b:
                    self.assertFalse(f"orbit-{b}-".startswith(f"orbit-{a}-"), (a, b))

    def test_the_geo_step_gets_the_archive_token(self):
        geo = (ROOT / ".github" / "workflows" / "geo.yml").read_text(encoding="utf-8")
        step = geo[geo.index(f"- name: {spacetrack.GEO_STEP}\n"):]
        self.assertIn("TIC_ARCHIVE_TOKEN: ${{ secrets.TIC_ARCHIVE_TOKEN }}", step)
        self.assertIn("GH_TOKEN: ${{ github.token }}", step)


if __name__ == "__main__":
    unittest.main()
