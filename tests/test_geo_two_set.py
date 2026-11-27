"""Offline checks for the GEO two-set rule (tools/geo_belt.py two_set_mark; method orbit-2.38, ideas#252), on real
element sets from Orbit's GEO release. Standard library only."""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import geo_belt as B  # noqa: E402

FIX = json.loads((ROOT / "tests" / "fixtures" / "geo_two_set_20261126.json").read_text(encoding="utf-8"))["objects"]
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)


def marks(norad):
    s = FIX[str(norad)]
    return [(p["epoch"][:10], q["epoch"][:10], B.two_set_mark(p, q)) for p, q in zip(s, s[1:])]


class KnownCases(unittest.TestCase):
    def test_usa324_stop_across_24_day_gap(self):
        got = [(a, b, m["kind"]) for a, b, m in marks(51280) if m]
        self.assertEqual(got, [("2026-10-22", "2026-11-15", "stopped drifting")])
        m = [m for _, _, m in marks(51280) if m][0]
        self.assertEqual(sorted(m["tests"]), ["class", "drift", "longitude"])
        self.assertGreater(m["gap_h"], 24 * 24)
        self.assertAlmostEqual(m["drift"][0], 0.683, places=2)

    def test_usa325_steady_drift_not_marked(self):
        self.assertEqual([m for _, _, m in marks(51281) if m], [])

    def test_luch2_start_across_37_day_gap(self):
        got = {(a, b): m for a, b, m in marks(55841) if m}
        m = got[("2026-10-15", "2026-11-21")]
        self.assertEqual(m["kind"], "started drifting")
        self.assertAlmostEqual(m["lon"][0], 62.0, delta=0.05)
        self.assertAlmostEqual(m["drift"][1], -1.618, places=2)
        self.assertEqual(got[("2026-11-21", "2026-11-22")]["kind"], "drift rate changed")
        self.assertEqual(len(got), 2, "the parked sets before 15 Oct are not marked")


class Rule(unittest.TestCase):
    base = {"epoch": "2026-11-01T00:00:00", "n": 1.0027379093, "e": 0.0002, "i": 0.05, "raan": 80.0, "argp": 10.0,
            "M": 200.0}

    def later(self, days, dn=0.0, dlon=0.0):
        from datetime import timedelta
        t = datetime.fromisoformat(self.base["epoch"]) + timedelta(days=days)
        # Same mean longitude after `days`: the mean anomaly turns with the Earth (360.98564736629 deg a day).
        m = (self.base["M"] + 360.98564736629 * days + dlon) % 360.0
        return dict(self.base, epoch=t.isoformat(), n=self.base["n"] + dn, M=m)

    def test_quiet_pair_not_marked(self):
        self.assertIsNone(B.two_set_mark(self.base, self.later(20)))

    def test_allowance_grows_with_gap(self):
        # 0.9 deg off the held slot: marked over 5 days (allowance 0.52), not over 30 (1.27).
        self.assertEqual(B.two_set_mark(self.base, self.later(5, dlon=0.9))["kind"], "moved inside the gap")
        self.assertIsNone(B.two_set_mark(self.base, self.later(30, dlon=0.9)))

    def test_drift_floor(self):
        dn = 0.05 / 360.0  # 0.05 deg a day: under the 0.25 m/s floor, no class change
        self.assertIsNone(B.two_set_mark(self.base, self.later(1, dn=dn, dlon=0.025)))

    def test_window_and_scope(self):
        s = FIX["51280"]
        self.assertEqual(len(B.two_set(s, NOW)), 1)
        self.assertEqual(B.two_set(s, datetime(2026, 12, 20, tzinfo=timezone.utc)), [])


    def test_board_lists_marks_apart_for_unjudged_only(self):
        o = {"norad": 51280, "name": "USA 324", "owner": "US"}
        ch, _, unjudged, two = B.changes([o], {51280: FIX["51280"]}, {}, NOW)
        self.assertEqual(ch, [])
        self.assertEqual([u["norad"] for u in unjudged], [51280])
        self.assertEqual([(m["norad"], m["kind"], m["sets"]) for m in two], [(51280, "stopped drifting", 4)])
        # The Luch 2 excerpt holds 5 sets, too few for Orbit's rule, so it is marked apart here too.
        _, _, _, two = B.changes([dict(o, norad=55841)], {55841: FIX["55841"]}, {}, NOW)
        self.assertEqual(len(two), 2)


if __name__ == "__main__":
    unittest.main()
