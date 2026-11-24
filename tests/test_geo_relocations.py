"""geo_relocations: Luch (Olymp) 2's stops and relocations, on real excerpts of its Space-Track history (ideas#256).
The stops are checked against Marco Langbroek's published table (SatTrackCam Leiden, 14 Mar 2025)."""
import json
import os
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
import geo_relocations as gr  # noqa: E402

with open(os.path.join(ROOT, "tests", "fixtures", "spacetrack_gp_history_55841_excerpt.json"), encoding="utf-8") as f:
    FIX = json.load(f)["windows"]
NOW = datetime(2026, 11, 25, tzinfo=timezone.utc)


def doc(window):
    return gr.build(FIX[window], NOW)


class Checkout2023(unittest.TestCase):
    def setUp(self):
        self.d = doc("checkout_2023")

    def test_turnaround_at_78e(self):
        """Langbroek: 78.00 E, 21-24 Mar 2023, checkout. Never held under 0.1 deg a day for two days, so a turnaround."""
        t = self.d["stops"][0]
        self.assertEqual(t["kind"], "turnaround")
        self.assertAlmostEqual(t["lon"], 78.0, delta=0.7)
        self.assertEqual(t["arrival"][:10], "2023-03-22")

    def test_held_at_58e(self):
        """Langbroek: 58.00 E from 7 Apr 2023. Orbit's rule (under 0.1 deg a day) gives 9 Apr."""
        s = self.d["stops"][1]
        self.assertEqual(s["kind"], "held")
        self.assertAlmostEqual(s["lon"], 58.0, delta=0.05)
        self.assertEqual(s["arrival"][:10], "2023-04-09")

    def test_relocation_west(self):
        r = self.d["relocations"][0]
        self.assertEqual(r["direction"], "west")
        self.assertAlmostEqual(r["peak_drift"], -2.783, delta=0.001)
        self.assertGreater(r["peak_dh_km"], 0)   # above GEO drifts west


class Move2025(unittest.TestCase):
    def setUp(self):
        self.d = doc("move_2025")

    def test_stops(self):
        """Langbroek: 0.92 W to 7 Feb 2025, 62.02 E from 7 Mar 2025. The excerpt holds only the stop's last 12 days
        (median 0.96 W; 0.90 W over the whole 140-day stop)."""
        lons = [s["lon"] for s in self.d["stops"]]
        self.assertAlmostEqual(lons[0], -0.92, delta=0.05)
        self.assertEqual(self.d["stops"][0]["departure"][:10], "2025-02-06")
        self.assertAlmostEqual(lons[-1], 62.0, delta=0.05)
        self.assertEqual(self.d["stops"][-1]["arrival"][:10], "2025-03-07")

    def test_profile(self):
        r = self.d["relocations"][-1]
        self.assertEqual(r["direction"], "east")
        self.assertAlmostEqual(r["moved_deg"], 62.96, delta=0.05)
        self.assertAlmostEqual(r["peak_drift"], 3.382, delta=0.001)
        self.assertEqual(r["peak_at"][:10], "2025-02-23")

    def test_brake_projection(self):
        """The first fall in drift overshoots (braking was not constant); the steady projection lands within 1 deg,
        7.6 days before arrival."""
        b = self.d["relocations"][-1]["brake"]
        self.assertGreater(abs(b["first"]["error_deg"]), 10)
        self.assertLessEqual(abs(b["steady"]["error_deg"]), 1.0)
        self.assertAlmostEqual(b["steady"]["lead_days"], 7.6, delta=0.05)
        self.assertAlmostEqual(b["within_1deg"]["lead_days"], 9.4, delta=0.05)


class Move2026(unittest.TestCase):
    def test_still_moving(self):
        """From 62 E since Mar 2025 to drifting west by 21 Nov 2026: one held stop, no arrival yet, so no relocation."""
        d = doc("move_2026")
        self.assertEqual(len(d["stops"]), 1)
        self.assertAlmostEqual(d["stops"][0]["lon"], 62.0, delta=0.05)
        self.assertEqual(d["stops"][0]["departure"][:10], "2026-10-15")
        self.assertEqual(d["relocations"], [])
        rows = gr.positions(FIX["move_2026"], NOW)
        self.assertAlmostEqual(rows[-1]["lon"], 58.19, delta=0.01)
        self.assertAlmostEqual(rows[-1]["drift"], -2.467, delta=0.001)


if __name__ == "__main__":
    unittest.main()
