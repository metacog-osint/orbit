"""The daily lead (orbit/lead.py, orbit-2.18): each kind of line, stale and unread sources, the archive copy."""
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from orbit import archive, lead, tip  # noqa: E402
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("orbit_cli_lead", ROOT / "tools" / "orbit.py")
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)

AT = "2026-11-18T16:17:52Z"
NOW = datetime(2026, 11, 18, 16, 17, 52, tzinfo=timezone.utc)


def text(line):
    return "".join(p if isinstance(p, str) else "[" + str(next(iter(p.values()))) + "]" for p in line["parts"])


def kinds(doc):
    return [x["kind"] for x in doc["lines"]]


def snap(**over):
    s = {
        "generated_at": AT,
        "lanes": {"decay": {"status": "ok"}, "maneuver": {"status": "ok"}, "catalog": {"status": "unchanged"}},
        "decay": {"objects": [
            {"norad": 59000, "name": "Starlink 4334", "decay_epoch": "2026-11-18T19:27:00Z", "window_min": 60, "passed": False},
            {"norad": 59001, "name": "CZ-3B R/B", "decay_epoch": "2026-11-19T10:00:00Z", "window_min": 300, "passed": False,
             "high_interest": True},
            {"norad": 59002, "name": "Later one", "decay_epoch": "2026-11-20T10:00:00Z", "window_min": 900, "passed": False},
            {"norad": 59003, "name": "Gone", "decay_epoch": "2026-11-18T07:16:00Z", "window_min": 1, "passed": True}]},
        "tip_check": {"objects": [
            {"norad": 53201, "name": "Starlink 4405", "offset_min": -21, "inside": True,
             "after": {"msg_epoch": "2026-11-18T10:02:00Z", "decay_epoch": "2026-11-18T07:16:00Z", "window_min": 1}},
            {"norad": 45555, "name": "Old", "offset_min": -39, "inside": True,
             "after": {"msg_epoch": "2026-11-03T16:41:00Z", "decay_epoch": "2026-11-03T11:02:00Z", "window_min": 1}}]},
        "maneuvers": {"read_at": AT, "events": [
            {"norad": 41745, "name": "USA 271", "gcat_name": "USA 271", "cc": "US", "regime": "GEO",
             "from": "2026-10-12T10:19:20Z", "to": "2026-10-29T17:29:30Z", "dv_ms": 12.903}]},
        "gcat_updated": {"satcat": "2026 Nov 18 0144:40"},
        "catalog_changes": {"previous_reading_at": "2026-11-15T22:17:04Z", "added": 10, "added_late": 10, "changed": 40,
                            "owner_changes": [{}] * 9, "late_groups": [
                                {"launch_tag": "2026-051", "launch_date": "2026-03-15", "count": 5, "by_type": {"debris": 5}},
                                {"launch_tag": "2026-257", "launch_date": "2026-11-14", "count": 3, "by_type": {"payload": 3}}]},
        "breakups": [{"name": "Fregat tank", "breakup_date": "2026-11-15"}, {"name": "Old breakup", "breakup_date": "2026-11-01"}],
        "launches": [{"kind": "orbital", "time": "2026-11-18T05:30:00Z", "vehicle": "Electron", "mission": "QPS-SAR-20",
                      "site": {"name": "Mahia"}, "outcome": "success"},
                     {"kind": "orbital", "time": "2026-11-14T05:30:00Z", "vehicle": "Electron", "mission": "QPS-SAR-19",
                      "site": {"name": "Mahia"}, "outcome": "success"}],
        "baseline": {"reentries_all": [{"recent": 87, "prior_median": 143.5, "prior_min": 103, "prior_max": 272,
                                        "position": "below"}],
                     "launches_all": [{"recent": 23, "prior_median": 27.0, "prior_min": 18, "prior_max": 39,
                                       "position": "within"}]},
    }
    s.update(over)
    return s


class Lines(unittest.TestCase):
    def setUp(self):
        self.doc = lead.build(snap())
        self.by = {x["kind"]: x for x in self.doc["lines"]}

    def test_order_and_kinds(self):
        self.assertEqual(kinds(self.doc), ["reentry_ahead", "reentry_done", "orbit_change", "breakup", "catalog",
                                           "launch", "baseline"])
        self.assertFalse(self.doc["nothing_new"])
        self.assertEqual(self.doc["at"], AT)

    def test_reentry_ahead_next_24_hours_high_interest_first(self):
        t = text(self.by["reentry_ahead"])
        self.assertTrue(t.startswith("2 objects are predicted to reenter in the next 24 hours: CZ-3B R/B at"), t)
        self.assertIn("±5 h", t)
        self.assertIn("Starlink 4334 at [2026-11-18T19:27:00Z] ±60 min", t)
        self.assertNotIn("Later one", t)
        self.assertIn("USSPACECOM flags 1 of them as high interest, listed first.", t)

    def test_reentry_done_only_messages_of_the_last_day(self):
        t = text(self.by["reentry_done"])
        self.assertIn("1 object came down, by the TIP messages USSPACECOM issued after the reentry in the last 24 hours: Starlink 4405 at [2026-11-18T07:16:00Z] (21 min earlier than the last "
                      "prediction, inside its window).", t)
        self.assertNotIn("Old", t)

    def test_orbit_change_new_without_archive_but_not_after_its_first_day(self):
        self.assertIn("USA 271 ([US], GEO), 12.9 m/s", text(self.by["orbit_change"]))
        arc = {"days": {"2026-11-16": {"maneuver": {"listed": {"41745:2026-10-12": {}}}}}}
        self.assertNotIn("orbit_change", kinds(lead.build(snap(), arc)))
        arc = {"days": {"2026-11-18": {"maneuver": {"listed": {"41745:2026-10-12": {}}}}}}
        self.assertIn("orbit_change", kinds(lead.build(snap(), arc)))

    def test_catalog_new_copy(self):
        t = text(self.by["catalog"])
        self.assertEqual(t, "GCAT published a new copy at [2026-11-18T01:44:40Z]: 10 new entries (all from launches "
                            "over 30 days old), 40 changed, 9 owner changes; the largest group is 5 pieces of debris "
                            "from launch 2026-051 ([2026-03-15]).")

    def test_catalog_stale_after_36_hours_and_silent_between(self):
        later = lead.build(snap(generated_at="2026-11-19T16:00:00Z"))  # 38 h after GCAT's stamp
        self.assertIn("stale", kinds(later))
        self.assertIn("GCAT has not published a new copy since [2026-11-18T01:44:40Z] (about 38 hours)",
                      text([x for x in later["lines"] if x["kind"] == "stale"][0]))
        mid = lead.build(snap(generated_at="2026-11-19T08:00:00Z"))  # 30 h: neither
        self.assertNotIn("catalog", kinds(mid))
        self.assertNotIn("stale", kinds(mid))

    def test_breakups_last_7_days(self):
        t = text(self.by["breakup"])
        self.assertIn("1 breakup in the last 7 days: Fregat tank ([2026-11-15]).", t)

    def test_launch_last_24_hours(self):
        t = text(self.by["launch"])
        self.assertIn("Electron (QPS-SAR-20) from Mahia at [2026-11-18T05:30:00Z], success", t)
        self.assertNotIn("QPS-SAR-19", t)

    def test_baseline_only_outside_every_prior_window(self):
        t = text(self.by["baseline"])
        self.assertIn("87 reentries, fewer than in any 30-day stretch of the two years before (103-272, median 143.5)", t)
        self.assertNotIn("launches", t)

    def test_parts_are_text_times_dates_or_countries(self):
        for x in self.doc["lines"]:
            for p in x["parts"]:
                self.assertTrue(isinstance(p, str) or set(p) <= {"t", "d", "cc"}, p)
            self.assertTrue(x["href"].startswith("#"))
            self.assertTrue(x["source"])


class Gaps(unittest.TestCase):
    def test_unread_lanes_named(self):
        s = snap(lanes={"decay": {"status": "failed", "from_previous": True}, "maneuver": {"status": "ok"},
                        "catalog": {"status": "failed"}})
        g = [x for x in lead.build(s)["lines"] if x["kind"] == "gap"][0]
        self.assertEqual(text(g), "Not read on this run: TIP predictions (kept copy), GCAT (not read). Their lines use "
                                  "the last copy Orbit holds.")

    def test_nothing_new(self):
        s = snap(decay={}, tip_check={}, maneuvers={}, catalog_changes={}, breakups=[], launches=[],
                 gcat_updated={"satcat": "2026 Nov 17 2000:00"})
        doc = lead.build(s)
        self.assertTrue(doc["nothing_new"])
        self.assertEqual(kinds(doc), ["baseline"])

    def test_gcat_stamp(self):
        self.assertEqual(lead.gcat_stamp("2026 Nov 18 0144:40"), datetime(2026, 11, 18, 1, 44, 40, tzinfo=timezone.utc))
        self.assertIsNone(lead.gcat_stamp("not a stamp"))


class Archive(unittest.TestCase):
    def test_archive_run_sets_lead_and_keeps_the_days_last(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            offline = lambda *_: (_ for _ in ()).throw(OSError("offline"))  # noqa: E731
            s1 = snap(generated_at="2026-11-18T10:00:00Z")
            cli._archive_run(tmp, s1, getter=offline)
            s2 = snap()
            cli._archive_run(tmp, s2, getter=offline)
            self.assertEqual(s2["lead"]["at"], AT)
            doc = json.loads((tmp / cli.ARCHIVE).read_text(encoding="utf-8"))
            self.assertEqual(doc["days"]["2026-11-18"]["lead"]["at"], AT)
            self.assertEqual(doc["days"]["2026-11-18"]["runs"], 2)
        finally:
            shutil.rmtree(tmp)

    def test_keep_lead_needs_its_day(self):
        doc = archive.keep_lead(archive.empty(), {"at": AT, "lines": []})
        self.assertEqual(doc["days"], {})


if __name__ == "__main__":
    unittest.main()
