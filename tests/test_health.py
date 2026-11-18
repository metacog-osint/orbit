"""The feed's per-source health block (15 Nov 2026): which source was really read on this run.

A lane that fails keeps its last good copy in the feed. COP's suite ledger reads this block so that a kept copy
neither ends an item nor counts as a fresh sighting of it. Run with: python -m unittest tests.test_health
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import test_orbit as T  # noqa: E402  (its fixtures and its offline collect)
from orbit import feed  # noqa: E402


class history:  # noqa: N801  Orbit's vendored kit predates tic_doctrine.history; this is its lanes_ok rule
    READ_STATES = ("fresh", "late", "up")

    @staticmethod
    def lanes_ok(health):
        return {k for k, v in (health or {}).items()
                if isinstance(v, dict) and v.get("last_ok") and v.get("last_ok") == v.get("checked_at")
                and (v.get("state") is None or v.get("state") in history.READ_STATES)}


NOW = "2026-11-15T18:00:00Z"


def snap(**lanes):
    return {"generated_at": NOW, "lanes": lanes}


class Block(unittest.TestCase):
    def test_a_fetched_lane_is_read(self):
        h = feed.source_health(snap(catalog={"status": "ok", "fetched_at": NOW, "from_previous": False}))
        self.assertEqual(h["gcat-mcdowell"], {"state": "up", "last_ok": NOW, "checked_at": NOW, "lane": "catalog",
                                              "detail": "ok"})
        self.assertEqual(history.lanes_ok(h), {"gcat-mcdowell"})

    def test_gcat_unchanged_is_read(self):
        h = feed.source_health(snap(catalog={"status": "unchanged", "fetched_at": "2026-11-15T00:30:00Z",
                                             "checked_at": NOW, "from_previous": False}))
        self.assertEqual(history.lanes_ok(h), {"gcat-mcdowell"})

    def test_a_failed_lane_keeping_its_last_good_copy_is_not_read(self):
        h = feed.source_health(snap(
            catalog={"status": "ok", "fetched_at": NOW},
            upcoming={"status": "failed", "error": "OSError: network down", "failed_at": NOW, "from_previous": True,
                      "fetched_at": "2026-11-15T12:00:00Z"}))
        up = h["ll2-thespacedevs"]
        self.assertEqual((up["state"], up["last_ok"], up["checked_at"]), ("failing", "2026-11-15T12:00:00Z", NOW))
        self.assertIn("last good copy kept", up["detail"])
        self.assertEqual(history.lanes_ok(h), {"gcat-mcdowell"})

    def test_a_failed_lane_is_not_read_even_when_its_times_match(self):
        # The state decides when a fetch time and a failure time happen to be equal.
        h = feed.source_health(snap(upcoming={"status": "failed", "failed_at": NOW, "fetched_at": NOW}))
        self.assertEqual(history.lanes_ok(h), set())

    def test_off_not_run_and_absent_lanes(self):
        h = feed.source_health(snap(maneuver={"status": "off", "reason": "no credentials", "checked_at": NOW},
                                    upcoming={"status": "not run"}))
        self.assertEqual((h["space-track"]["state"], h["ll2-thespacedevs"]["state"]), ("never", "never"))
        self.assertEqual((h["space-track"]["detail"], h["ll2-thespacedevs"]["detail"]),
                         ("off: no credentials", "not run"))
        self.assertNotIn("gcat-mcdowell", h, "a lane with no record carries no items, so it has no entry")
        self.assertEqual(history.lanes_ok(h), set())

    def test_a_lane_carried_from_an_earlier_run_is_not_read(self):
        # collect --only keeps the other lanes' records with from_previous: an old ok must not read as this run's.
        h = feed.source_health(snap(upcoming={"status": "ok", "fetched_at": "2026-11-15T12:00:00Z",
                                              "from_previous": True}))
        up = h["ll2-thespacedevs"]
        self.assertEqual((up["state"], up["last_ok"], up["checked_at"]), ("stale", "2026-11-15T12:00:00Z", NOW))
        self.assertEqual(history.lanes_ok(h), set())

    def test_every_state_is_a_kit_health_state(self):
        # vocab/enums.json health_state (feed contract revision 2.1, 18 Nov 2026)
        kit = {"fresh", "late", "stale", "failing", "never", "up"}
        h = feed.source_health(snap(
            catalog={"status": "unchanged", "checked_at": NOW},
            upcoming={"status": "failed", "failed_at": NOW, "fetched_at": "2026-11-15T12:00:00Z", "from_previous": True},
            maneuver={"status": "off", "reason": "no credentials", "checked_at": NOW}))
        self.assertTrue({v["state"] for v in h.values()} <= kit, h)
        for status in ("not run", None, "something new"):
            h = feed.source_health(snap(catalog={"status": status}))
            self.assertIn(h["gcat-mcdowell"]["state"], kit, status)


class Collected(unittest.TestCase):
    """Through the real collect and build, with the network answered from fixtures."""

    def setUp(self):
        self.e = T.EndToEnd("run_collect")
        self.e.setUp()

    def tearDown(self):
        self.e.tearDown()

    def test_a_failed_run_marks_the_kept_sources_unread(self):
        good = feed.build_feed(self.e.run_collect())
        self.assertEqual(history.lanes_ok(good["health"]), {"gcat-mcdowell", "ll2-thespacedevs"})
        self.e.fail = True
        self.e.stamp = "Sat, 14 Nov 2026 00:23:02 GMT"
        kept = feed.build_feed(self.e.run_collect())
        self.assertTrue(kept["features"], "the last good copy is still in the feed")
        self.assertEqual(history.lanes_ok(kept["health"]), set())
        firsts = {f["properties"]["sources"][0]["id"] for f in kept["features"]}
        self.assertTrue(firsts <= set(kept["health"]))


if __name__ == "__main__":
    unittest.main()
