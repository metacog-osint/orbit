"""Offline tests for the retention archives (orbit/retention.py): nothing dropped from GCAT's catalog diff, the
releases get unique names and are never clobbered, an upload failure raises, a rerun adds nothing."""
from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from orbit import retention  # noqa: E402


class FakeGh:
    """A tiny stand-in for the gh CLI: releases hold {tag: set(asset names)}."""

    def __init__(self, releases=None, fail_upload=False):
        self.releases = {k: set(v) for k, v in (releases or {}).items()}
        self.calls = []
        self.fail_upload = fail_upload

    def __call__(self, *args):
        self.calls.append(args)
        ok = SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:2] == ("release", "view"):
            tag = args[2]
            if tag not in self.releases:
                return SimpleNamespace(returncode=1, stdout="", stderr="not found")
            out = "\n".join(sorted(self.releases[tag])) if "--json" in args else ""
            return SimpleNamespace(returncode=0, stdout=out, stderr="")
        if args[:2] == ("release", "create"):
            self.releases[args[2]] = set()
            return ok
        if args[:2] == ("release", "upload"):
            if "--clobber" in args:
                raise AssertionError("retention uploads must never clobber")
            if self.fail_upload:
                return SimpleNamespace(returncode=1, stdout="", stderr="boom")
            self.releases[args[2]].add(Path(args[-1]).name)
            return ok
        raise AssertionError(args)


def brief(j):
    return {"jcat": j, "norad": None, "name": j, "type": "payload", "state": "US"}


def full_diff():
    return {"added": 120, "added_fresh": 100, "added_late": 20, "removed": 80, "temporary_entries_closed": 1,
            "changed": 70, "newly_numbered": 0, "status_moves": {"O -> R": 3},
            "added_objects": [brief(f"A{i}") for i in range(120)],
            "removed_objects": [brief(f"R{i}") for i in range(80)],
            "temporary_entries_closed_objects": [brief("T1")],
            "changed_objects": [{"jcat": f"C{i}", "name": "x", "fields": {"owner": ["a", "b"]}} for i in range(70)],
            "owner_changes": [{"jcat": "C0", "fields": {"owner": ["a", "b"]}}],
            "late_groups": [{"launch_tag": "2020-001", "count": 20, "objects": [brief(f"L{i}") for i in range(20)]}]}


class Changes(unittest.TestCase):
    def test_every_object_lands_in_the_file(self):
        lines = retention.changes_lines(full_diff(), "2026-11-18T17:00:00Z", "2026-11-17T17:00:00Z", {"satcat": "s"})
        kinds = [x["kind"] for x in lines]
        self.assertEqual(kinds.count("added"), 120)       # no [:50] cut
        self.assertEqual(kinds.count("removed"), 80)
        self.assertEqual(kinds.count("changed"), 70)
        self.assertEqual(kinds.count("late_group"), 1)
        self.assertEqual(kinds.count("temporary_closed"), 1)
        self.assertEqual(lines[0]["kind"], "reading")
        self.assertIn("CC BY 4.0", lines[0]["credit"])
        self.assertTrue([x for x in lines if x["kind"] == "changed" and x["jcat"] == "C0"][0]["owner_change"])
        self.assertFalse([x for x in lines if x["kind"] == "changed" and x["jcat"] == "C1"][0]["owner_change"])

    def test_upload_unique_names_no_clobber_and_rerun_adds_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            gh = FakeGh()
            for stamp in ("2026-11-18T17:00:00Z", "2026-12-01T05:00:00Z"):
                retention.write_changes(data, retention.changes_lines(full_diff(), stamp, None, {}), stamp)
            self.assertEqual(len(retention.upload_changes(data, "o/r", gh)), 2)
            self.assertEqual(gh.releases["catalog-changes-2026-11"], {"catalog-changes-2026-11-18T17-00-00Z.jsonl.gz"})
            self.assertEqual(gh.releases["catalog-changes-2026-12"], {"catalog-changes-2026-12-01T05-00-00Z.jsonl.gz"})
            self.assertEqual(list((data / retention.OUT).glob("*.jsonl.gz")), [])  # sent files are removed
            # the same reading written again (a rerun): the name is skipped, not replaced
            retention.write_changes(data, retention.changes_lines(full_diff(), "2026-11-18T17:00:00Z", None, {}),
                                    "2026-11-18T17:00:00Z")
            retention.upload_changes(data, "o/r", gh)
            self.assertEqual(len(gh.releases["catalog-changes-2026-11"]), 1)
            self.assertFalse([c for c in gh.calls if c[:2] == ("release", "upload") and "--clobber" in c])

    def test_written_file_is_gzip_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = retention.write_changes(Path(tmp), retention.changes_lines(full_diff(), "2026-11-18T17:00:00Z", None, {}),
                                        "2026-11-18T17:00:00Z")
            rows = [json.loads(x) for x in gzip.decompress(p.read_bytes()).decode().splitlines()]
            self.assertEqual(len(rows), 1 + 120 + 80 + 1 + 70 + 1)

    def test_failed_upload_raises_and_keeps_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            p = retention.write_changes(data, retention.changes_lines(full_diff(), "2026-11-18T17:00:00Z", None, {}),
                                        "2026-11-18T17:00:00Z")
            with self.assertRaises(RuntimeError):
                retention.upload_changes(data, "o/r", FakeGh(fail_upload=True))
            self.assertTrue(p.exists())


class DatedCopies(unittest.TestCase):
    def test_archive_copy_once_a_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "archive.json"
            a.write_text(json.dumps({"schema": "orbit-archive/1", "days": {"2026-11-18": {"runs": 1}}}))
            gh = FakeGh()
            self.assertEqual(retention.upload_archive(a, date(2026, 11, 18), Path(tmp) / "t", "o/r", gh),
                             ["archive-2026-11-18.json.gz"])
            a.write_text("{}")  # a later run the same day: the first copy stays
            self.assertEqual(retention.upload_archive(a, date(2026, 11, 18), Path(tmp) / "t", "o/r", gh), [])
            self.assertEqual(retention.upload_archive(a, date(2026, 11, 19), Path(tmp) / "t", "o/r", gh),
                             ["archive-2026-11-19.json.gz"])
            self.assertEqual(retention.upload_archive(Path(tmp) / "none.json", date(2026, 11, 19), Path(tmp), "o/r", gh), [])

    def test_catalog_copy_once_a_week_named_by_monday(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = Path(tmp) / "catalog.json.gz"
            c.write_bytes(b"x")
            gh = FakeGh()
            self.assertEqual(retention.upload_catalog_week(c, date(2026, 11, 18), "o/r", gh), ["catalog-2026-11-16.json.gz"])
            self.assertEqual(retention.upload_catalog_week(c, date(2026, 11, 20), "o/r", gh), [])
            self.assertEqual(retention.upload_catalog_week(c, date(2026, 11, 23), "o/r", gh), ["catalog-2026-11-23.json.gz"])
            # a week that spans a month end goes to the Monday's month
            self.assertEqual(retention.upload_catalog_week(c, date(2026, 12, 2), "o/r", gh), ["catalog-2026-11-30.json.gz"])
            self.assertIn("catalog-archive-2026-11", gh.releases)


if __name__ == "__main__":
    unittest.main()
