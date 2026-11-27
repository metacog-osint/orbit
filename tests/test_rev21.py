"""Feed contract revision 2.1: subjects that hold from day to day, event times, change flags, header and health."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from tic_doctrine import __version__ as KIT, contract  # noqa: E402
from orbit import feed  # noqa: E402

NOW = "2026-11-23T12:00:00Z"
PREV = "2026-11-22T12:00:00Z"


def launch(**over):
    x = {"launch_tag": "2026-262", "time": "2026-11-22T12:23:56Z", "date": "2026-11-22", "time_uncertain": False,
         "flight": "F1", "mission": "M1", "vehicle": "Rocket", "site": {}, "site_code": "X", "pad": "", "kind": "orbital",
         "outcome": "success", "agency": "A", "category": "C", "payloads": [], "payloads_cataloged": 0, "launchers": []}
    x.update(over)
    return x


class Items(unittest.TestCase):
    def props(self, feature):
        return feature["properties"]

    def test_launch(self):
        p = self.props(feed._launch_item(launch(), NOW, NOW))
        self.assertEqual((p["subject_id"], p["event_start"], p["last_change"], p["last_change_at"]),
                         (p["id"], "2026-11-22T12:23:56Z", "new", "2026-11-22T12:23:56Z"))
        self.assertNotIn("event_time_precision", p)

    def test_uncertain_launch_is_a_day(self):
        p = self.props(feed._launch_item(launch(time_uncertain=True), NOW, NOW))
        self.assertEqual((p["event_start"], p["event_time_precision"]), ("2026-11-22T00:00:00Z", "day"))

    def test_reentry_subject_holds_across_days(self):
        rows = [{"type": "payload", "state": "US", "name": "A", "reentry_date": "2026-11-18", "country": "US"},
                {"type": "debris", "state": "CN", "name": "B", "reentry_date": "2026-11-22", "country": "CN"}]
        a = self.props(feed._reentry_item(rows, NOW, NOW, "2026-11-16"))
        b = self.props(feed._reentry_item(rows, "2026-11-24T12:00:00Z", NOW, "2026-11-17"))
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(a["subject_id"], b["subject_id"])
        self.assertEqual((a["event_start"], a["event_end"], a["last_change_at"]),
                         ("2026-11-18T00:00:00Z", "2026-11-22T00:00:00Z", "2026-11-22T00:00:00Z"))

    def test_late_object_subject_has_no_date(self):
        g = {"launch_tag": "2020-001", "launch_date": "2020-01-01", "count": 1, "by_type": {"debris": 1}, "states": ["US"],
             "parents": [], "objects": [{"name": "A", "jcat": "S1"}], "countries": ["US"]}
        p = self.props(feed._late_item(g, NOW, NOW, PREV))
        self.assertEqual((p["subject_id"], p["event_start"], p["event_end"]), ("orbit:late-object:2020-001", PREV, NOW))

    def test_change_is_never_after_the_build(self):
        self.assertEqual(feed._change("new", "2026-11-24T00:00:00Z", NOW)["last_change_at"], NOW)
        self.assertEqual(feed._change("changed", None, NOW), {"last_change": "none"})


class Header(unittest.TestCase):
    def test_header_and_health(self):
        snap = {"generated_at": NOW, "lanes": {
            "catalog": {"status": "ok", "fetched_at": NOW},
            "maneuver": {"status": "failed", "failed_at": NOW, "fetched_at": PREV, "error": "timeout", "failures": 2,
                         "from_previous": True}},
            "launches": [launch()]}
        doc = feed.build_feed(snap)
        self.assertEqual((doc["contract_rev"], doc["kit"]), ("2.1", KIT))
        self.assertEqual(contract.check_health(doc["health"], strict=True), [])
        self.assertEqual(doc["health"]["space-track"]["failures"], 2)
        self.assertEqual(doc["health"]["gcat-mcdowell"]["data_as_of"], "2026-11-22T12:23:56Z")


if __name__ == "__main__":
    unittest.main()
