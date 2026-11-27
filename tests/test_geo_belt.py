"""Offline checks for the GEO page's belt board (tools/geo_belt.py; step 5 of doctrine/geo-move-plan.md). Standard
library only: positions are injected, so sgp4 is not needed (the update run's tests run before
tools/requirements-callouts.txt is installed)."""
from __future__ import annotations

import math
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import geo_belt as B  # noqa: E402

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
R_GEO = 42164.0


def obj(norad, owner="US", lon=0.0, n=1.0027379, i=0.05, epoch="2026-11-18T00:00:00"):
    return {"norad": norad, "name": f"OBJ {norad}", "owner": owner, "epoch": epoch, "n": n, "e": 0.0002, "i": i,
            "raan": 80.0, "argp": 10.0, "M": 200.0, "bstar": 0.0, "lon": lon}


def at_lon(o, t):
    """A fake position: on the GEO ring at the object's `lon`."""
    a = math.radians(o["lon"])
    return (R_GEO * math.cos(a), R_GEO * math.sin(a), 0.0), o["lon"]


def km_to_deg(km):
    return math.degrees(km / R_GEO)


def history(norad, days=30, per_day=2, jump_at=None, dn=0.0):
    """Quiet element sets with a little alternating noise; from `jump_at` on, mean motion shifted by `dn`."""
    out = []
    for k in range(days * per_day):
        t = NOW - timedelta(days=days) + timedelta(hours=24 / per_day * k)
        wob = 1e-8 if k % 2 else -1e-8
        n = 1.0027379 + wob + (dn if jump_at is not None and t >= jump_at else 0.0)
        out.append({"norad": norad, "epoch": t.strftime("%Y-%m-%dT%H:%M:%S"), "n": n, "e": 0.0002 + wob,
                    "i": 0.05 + wob * 100, "raan": 80.0, "argp": 10.0, "M": 200.0})
    return out


class Classes(unittest.TestCase):
    def test_class(self):
        self.assertEqual(B.classify(0.05, 0.5), "station-kept")
        self.assertEqual(B.classify(-0.05, 3.0), "inclined")
        self.assertEqual(B.classify(-0.1, 0.0), "drifting")

    def test_change_kind(self):
        kept, drifting = {"drift": 0.01, "i": 0.05}, {"drift": 0.4, "i": 0.05}
        self.assertEqual(B.change_kind(kept, kept), "station-keeping")
        self.assertEqual(B.change_kind(kept, drifting), "started drifting")
        self.assertEqual(B.change_kind(drifting, kept), "stopped drifting")
        self.assertEqual(B.change_kind(drifting, {"drift": 0.9, "i": 0.05}), "drift rate changed")
        self.assertEqual(B.change_kind({"drift": 0.0, "i": 5.0}, {"drift": 0.0, "i": 5.03}), "inclined orbit changed")
        self.assertEqual(B.change_kind({"drift": 0.0, "i": 5.0}, {"drift": 0.0, "i": 5.01}), "station-keeping")
        self.assertEqual(B.change_kind({"drift": 0.0, "i": 0.2}, {"drift": 0.0, "i": 0.25}), "station-keeping")


class ClosePairs(unittest.TestCase):
    def test_owners_roles_and_distance(self):
        objs = [obj(1, "US", 10.0), obj(2, "PRC", 10.0 + km_to_deg(40)), obj(3, "US", 10.0 + km_to_deg(60)),
                obj(4, "CIS", 10.0 + km_to_deg(300)), obj(5, "US", 50.0), obj(6, "US", 50.0 + km_to_deg(20))]
        listed, same = B.close_pairs(objs, {}, NOW, at_lon)
        got = sorted((sorted([p["a"][0], p["b"][0]]), p["km"]) for p in listed)
        self.assertEqual(got, [([1, 2], 40), ([2, 3], 20)])     # 1-3 and 5-6: one owner, counted; 4 too far
        self.assertEqual(same, 2)
        listed, same = B.close_pairs(objs, {"6": "inspection"}, NOW, at_lon)
        roles = [p for p in listed if 6 in (p["a"][0], p["b"][0])]
        self.assertEqual(len(roles), 1)                          # a listed role is always listed
        self.assertEqual(roles[0]["kind"], "inspection-capable involved")
        self.assertEqual(listed[0]["kind"], "inspection-capable involved")   # roles first
        self.assertEqual(same, 1)

    def test_across_the_antimeridian_once(self):
        objs = [obj(1, "US", 179.97), obj(2, "PRC", -179.98)]   # 0.05 deg apart, about 37 km
        listed, _ = B.close_pairs(objs, {}, NOW, at_lon)
        self.assertEqual(len(listed), 1)
        self.assertLess(listed[0]["km"], 100)


class Changes(unittest.TestCase):
    def test_burn_and_baseline(self):
        jump = NOW - timedelta(days=3)
        el = {1: history(1, jump_at=jump, dn=-0.001), 2: history(2), 3: history(3, days=1)}
        objs = [obj(1), obj(2), obj(3)]
        ch, counts, unjudged, _ = B.changes(objs, el, {}, NOW)
        self.assertEqual([c["norad"] for c in ch], [1])
        self.assertEqual(ch[0]["kind"], "started drifting")
        self.assertEqual(ch[0]["dominant"], "in-track")
        self.assertGreater(ch[0]["dv_ms"], 0.25)
        self.assertEqual(counts, {"other": 1, "station-keeping": 0})
        self.assertEqual([u["norad"] for u in unjudged], [3])     # 2 sets: shown with its last two sets, not judged
        self.assertEqual(unjudged[0]["sets"], 2)
        self.assertEqual(len(unjudged[0]["drift"]), 2)

    def test_old_change_left_out(self):
        el = {1: history(1, jump_at=NOW - timedelta(days=12), dn=-0.001)}
        ch, _, _, _ = B.changes([obj(1)], el, {}, NOW)
        self.assertEqual(ch, [])

    def test_build_counts(self):
        objs = [obj(1, lon=10.0), obj(2, "PRC", lon=10.2, n=1.0027379 + 0.001)]
        b = B.build(objs, {1: history(1), 2: history(2)}, {}, NOW, position=at_lon)
        self.assertEqual(b["counts"], {"station-kept": 1, "inclined": 0, "drifting": 1})
        self.assertEqual([d["norad"] for d in b["drifting"]], [2])
        self.assertEqual(b["close_other_owner_count"], 0)       # 0.2 deg is about 147 km
        self.assertEqual(b["at_utc"], "2026-11-18T12:00Z")


if __name__ == "__main__":
    unittest.main()
