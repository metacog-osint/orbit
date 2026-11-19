"""Offline tests for Orbit's own daily archive (orbit/archive.py) and its place in `collect` and `build`."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from orbit import archive  # noqa: E402
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("orbit_cli_archive", ROOT / "tools" / "orbit.py")
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)


def snap(at: str, mv_status="ok", nw_status="ok", cat_status="unchanged", events=None, areas=None, changes=None,
         memo="2026-11-16T17:05:00Z", satcat="2026 Nov 16 1018:34") -> dict:
    return {
        "generated_at": at,
        "lanes": {"maneuver": {"status": mv_status}, "navwarn": {"status": nw_status},
                  "catalog": {"status": cat_status}, "upcoming": {"status": "ok"}},
        "maneuvers": {"read_at": at, "watched": 12, "counted_not_listed": {"below_floor": 3},
                      "events": events if events is not None else [
                          {"norad": 41744, "name": "USA 270", "gcat_name": "USA 270", "regime": "GEO",
                           "from": "2026-10-12T18:06:12Z", "to": "2026-11-02T06:44:40Z", "dv_ms": 0.887,
                           "dominant": "in-track", "cc": "US"}]},
        "navwarn": {"sources": {"nga": {"form": "memoranda", "memos": {"HYDROPAC": {"as_of": memo}}}},
                    "areas": areas if areas is not None else [
                        {"key": "hydropac-3246-26", "hazard": "rocket launching", "regions": ["SOUTH CHINA SEA"],
                         "broadcasts": [{"id": "HYDROPAC 3246/26"}]}]},
        "gcat_updated": {"satcat": satcat},
        "catalog_changes": changes if changes is not None else {},
    }


class Record(unittest.TestCase):
    def test_one_day_two_runs(self):
        doc = archive.record(None, snap("2026-11-16T00:55:00Z"))
        doc = archive.record(doc, snap("2026-11-16T06:55:00Z", areas=[
            {"key": "hydropac-3246-26", "hazard": "rocket launching", "regions": [],
             "broadcasts": [{"id": "HYDROPAC 3246/26"}, {"id": "NAVAREA XI 0520/26"}]},
            {"key": "navarea-iv-1080-26", "hazard": "space debris", "regions": ["NORTH ATLANTIC"],
             "broadcasts": [{"id": "NAVAREA IV 1080/26"}]}]))
        d = doc["days"]["2026-11-16"]
        self.assertEqual(d["runs"], 2)
        self.assertEqual(list(d["maneuver"]["listed"]), ["41744:2026-10-12"])
        self.assertEqual(sorted(d["navwarn"]["areas"]), ["hydropac-3246-26", "navarea-iv-1080-26"])
        self.assertEqual(d["navwarn"]["areas"]["hydropac-3246-26"]["broadcasts"],
                         ["HYDROPAC 3246/26", "NAVAREA XI 0520/26"])
        self.assertEqual(d["navwarn"]["memo_as_of"], "2026-11-16T17:05:00Z")
        self.assertNotIn("catalog", d)  # GCAT unchanged: no reading that day

    def test_same_run_twice_counts_once(self):
        s = snap("2026-11-16T00:55:00Z")
        doc = archive.record(archive.record(None, s), s)
        self.assertEqual(doc["days"]["2026-11-16"]["runs"], 1)

    def test_lane_not_read_is_not_zero(self):
        doc = archive.record(None, snap("2026-11-16T00:55:00Z", mv_status="failed", nw_status="off"))
        d = doc["days"]["2026-11-16"]
        self.assertNotIn("maneuver", d)  # a failed lane leaves no count at all, not an empty one
        self.assertNotIn("navwarn", d)
        self.assertEqual(d["lanes"]["maneuver"], ["failed"])
        self.assertEqual(d["lanes"]["navwarn"], ["off"])

    def test_carried_copy_is_not_read(self):
        s = snap("2026-11-16T00:55:00Z")
        s["lanes"]["maneuver"]["from_previous"] = True
        d = archive.record(None, s)["days"]["2026-11-16"]
        self.assertNotIn("maneuver", d)
        self.assertEqual(d["lanes"]["maneuver"], ["carried"])

    def test_gcat_reading_once_by_stamp(self):
        ch = {"added": 12, "added_fresh": 10, "added_late": 2, "removed": 0, "temporary_entries_closed": 1,
              "changed": 30, "newly_numbered": 4, "owner_changes": [{"jcat": "S1"}], "late_groups": [{"count": 2}]}
        doc = archive.record(None, snap("2026-11-16T12:55:00Z", cat_status="ok", changes=ch))
        doc = archive.record(doc, snap("2026-11-16T18:55:00Z", cat_status="ok", changes=ch))  # same GCAT copy
        cat = doc["days"]["2026-11-16"]["catalog"]
        self.assertEqual(list(cat), ["2026 Nov 16 1018:34"])
        self.assertEqual(cat["2026 Nov 16 1018:34"]["added_late"], 2)
        self.assertEqual(cat["2026 Nov 16 1018:34"]["owner_changes"], 1)

    def test_watch_list_stays_out(self):
        doc = archive.record(None, snap("2026-11-16T00:55:00Z"))
        text = json.dumps(doc)
        self.assertNotIn("quiet_or_untracked", text)
        self.assertEqual(doc["days"]["2026-11-16"]["maneuver"]["watched"], 12)  # the count the page shows

    def test_keeps_every_day(self):  # retention rule, 18 Nov 2026: the old 800-day cap is gone
        doc = archive.empty()
        for i in range(900):
            doc["days"][str(date(2024, 1, 1).fromordinal(date(2024, 1, 1).toordinal() + i))] = {"runs": 1}
        doc = archive.record(doc, snap("2030-01-01T00:55:00Z"))
        self.assertEqual(len(doc["days"]), 901)
        self.assertIn("2024-01-01", doc["days"])
        self.assertIn("2030-01-01", doc["days"])
        self.assertFalse(hasattr(archive, "MAX_DAYS"))


class MergeAndSummary(unittest.TestCase):
    def test_merge_keeps_fuller_day(self):
        a = archive.record(None, snap("2026-11-16T00:55:00Z"))
        b = archive.record(archive.record(None, snap("2026-11-15T18:55:00Z")), snap("2026-11-16T00:55:00Z"))
        b = archive.record(b, snap("2026-11-16T06:55:00Z"))
        m = archive.merge(a, b)
        self.assertEqual(sorted(m["days"]), ["2026-11-15", "2026-11-16"])
        self.assertEqual(m["days"]["2026-11-16"]["runs"], 2)
        self.assertEqual(archive.merge(None, {"schema": "something-else", "days": {"x": {}}})["days"], {})

    def test_summary(self):
        doc = archive.record(None, snap("2026-11-16T00:55:00Z", memo="2026-11-13T17:05:00Z"))
        doc = archive.record(doc, snap("2026-11-18T00:55:00Z", memo="2026-11-17T17:05:00Z"))
        s = archive.summary(doc, date(2026, 11, 18))
        self.assertEqual((s["days"], s["span_days"], s["missed_days"]), (2, 3, 1))
        self.assertEqual(s["baseline_from"], "2027-02-14")
        self.assertEqual(s["navwarn_stale_memo_days"], 1)  # 16 Nov read memoranda dated 13 Nov
        self.assertEqual((s["listed_changes"], s["warning_areas"]), (1, 1))
        self.assertEqual(archive.summary(None, date(2026, 11, 18)), {"days": 0})


class CollectAndBuild(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(ROOT / "doctrine", self.tmp / "doctrine")
        shutil.copytree(ROOT / "site_src", self.tmp / "site_src", ignore=shutil.ignore_patterns("cesium"))  # 14 MB, not needed
        (self.tmp / "data").mkdir()
        self.published = None
        self.calls = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def get(self, url, timeout=60):
        self.calls.append(url)
        if url == archive.PUBLIC_URL and self.published is not None:
            return json.dumps(self.published).encode("utf-8")
        raise OSError("offline")

    def test_restores_published_copy_when_local_missing(self):
        self.published = archive.record(None, snap("2026-11-15T18:55:00Z"))
        out = cli._archive_run(self.tmp / "data", snap("2026-11-16T00:55:00Z"), self.get)
        self.assertEqual(out["days"], 2)
        self.assertEqual(out["note"], "restored from the published copy")
        out = cli._archive_run(self.tmp / "data", snap("2026-11-16T06:55:00Z"), self.get)
        self.assertEqual(self.calls, [archive.PUBLIC_URL])  # read only while the local copy is missing
        self.assertNotIn("note", out)

    def test_starts_locally_when_nothing_reads(self):
        out = cli._archive_run(self.tmp / "data", snap("2026-11-16T00:55:00Z"), self.get)
        self.assertEqual(out["days"], 1)
        self.assertIn("started here", out["note"])

    def test_build_publishes_archive(self):
        cli._archive_run(self.tmp / "data", snap("2026-11-16T00:55:00Z"), self.get)
        s = snap("2026-11-16T00:55:00Z")
        files = cli.build_site(self.tmp, {"generated_at": s["generated_at"], "lanes": {}, "archive": {"days": 1}})
        self.assertEqual(json.loads(files["data/archive.json"])["schema"], archive.SCHEMA)
        self.assertTrue((self.tmp / "site" / "data" / "archive.json").exists())

    def test_build_globe_token_and_binary_files(self):
        """The globe (orbit-2.11): the ion token from the environment, and vendor images copied byte for byte."""
        png = bytes(range(256)) * 4  # not UTF-8
        (self.tmp / "site_src" / "vendor" / "x").mkdir(parents=True)
        (self.tmp / "site_src" / "vendor" / "x" / "t.png").write_bytes(png)
        doc = {"generated_at": "2026-11-16T00:55:00Z", "lanes": {}}
        with mock.patch.dict(os.environ, {"CESIUM_ION_TOKEN": "test-token"}):
            files = cli.build_site(self.tmp, doc)
        self.assertEqual(json.loads(files["data/cesium.json"]), {"token": "test-token"})
        self.assertEqual((self.tmp / "site" / "vendor" / "x" / "t.png").read_bytes(), png)
        self.assertNotIn("vendor/x/t.png", files)
        with mock.patch.dict(os.environ, {"CESIUM_ION_TOKEN": ""}):
            files = cli.build_site(self.tmp, doc)
        self.assertEqual(json.loads(files["data/cesium.json"]), {"token": None})
        self.assertTrue((self.tmp / "site" / "globe.js").exists())


if __name__ == "__main__":
    unittest.main()
