"""Relocation feed items (orbit-2.30, ideas#323): one item per move of a listed-role GEO object, updated in place,
off-map, with the three steps (move began, braking with a steady stop projection, stopped). Luch (Olymp) 2's
November 2026 move (Orbit's GEO release) and its 2025 move from 0.96 W to 62 E (Space-Track history)."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "doctrine", "kit", "python"))
sys.path.append(os.path.join(ROOT, "tools"))
sys.path.append(os.path.join(ROOT, "tests"))
import geo_belt  # noqa: E402
import geo_page  # noqa: E402
import geo_tracker as gt  # noqa: E402
from orbit import feed  # noqa: E402
from tic_doctrine import contract, registers  # noqa: E402
from test_geo_tracker import ROLES, load_2025, load_2026  # noqa: E402

GEN = "2026-11-24T19:00:00Z"
BAD_WORDS = ("likely", "probab", "expected to", "will arrive", "target", "destination is", "heading for")


def tracker_2025(day, hour=0):
    rows = load_2025()
    now = datetime(2025, *day, hour, tzinfo=timezone.utc)
    held = sorted((r for r in rows if r["epoch"][:19] < now.strftime("%Y-%m-%dT%H:%M:%S")), key=lambda r: r["epoch"])
    o = dict(held[-1], norad=55841, name="LUCH (OLYMP) 2", owner="CIS")
    for k in ("n", "e", "i", "raan", "argp", "M"):
        o[k] = float(o[k])
    o["class"] = geo_belt.classify(geo_belt.drift(o["n"]), o["i"])
    return gt.build([o], {55841: rows}, ROLES, now)


def items(doc, generated=GEN):
    return {f["properties"]["id"]: f for f in feed.relocation_features(doc, generated)}


def lint_errors(f):
    regs = registers.ids(Path(ROOT) / "doctrine")
    return [m for _, sev, m in contract.check(f, regs) if sev == "error"]


class Luch2November2026(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        objs, elsets = load_2026()
        cls.doc = gt.build(objs, elsets, ROLES, datetime(2026, 11, 24, 19, 0, tzinfo=timezone.utc))
        cls.items = items(cls.doc)
        cls.f = cls.items["orbit:relocation:55841:2026-11-19"]
        cls.p = cls.f["properties"]

    def test_one_item_dated_by_the_estimated_start(self):
        self.assertEqual(self.p["subject_id"], self.p["id"])
        self.assertEqual(self.p["event_start"], "2026-11-19T00:00:00Z")
        self.assertEqual(self.p["event_time_precision"], "day")
        self.assertNotIn("event_end", self.p)
        self.assertIsNone(self.f["geometry"])
        self.assertEqual((self.p["kind"], self.p["tier"]), ("observation", "routine"))

    def test_move_began_step_names_its_sets(self):
        s = self.p["steps"]
        self.assertEqual(list(s), ["move_began"])
        self.assertEqual(s["move_began"]["sets"][0], "2026-10-15T15:56:16Z")       # the last held set
        self.assertEqual(self.p["last_change"], "new")
        self.assertEqual(self.p["last_change_at"], s["move_began"]["sets"][1])     # the first moving set

    def test_wording(self):
        text = (self.p["title"] + " " + self.p["summary"]).lower()
        self.assertIn("at the last measured rate", text)
        self.assertIn("hours old", text)
        self.assertIn("61.98 e", text)
        for bad in BAD_WORDS:
            self.assertNotIn(bad, text)

    def test_lint(self):
        for f in self.items.values():
            self.assertEqual(lint_errors(f), [], f["properties"]["id"])

    def test_only_listed_roles(self):
        self.assertTrue(all(i.split(":")[2] in ROLES for i in self.items))


class Luch2Move2025(unittest.TestCase):
    ID = "orbit:relocation:55841:2025-02-06"

    def test_braking_with_a_steady_projection(self):
        f = items(tracker_2025((2, 28)), "2025-02-28T00:00:00Z")[self.ID]["properties"]
        self.assertEqual(f["steps"]["braking"]["state"], "steady")
        self.assertEqual(f["last_change"], "changed")
        self.assertIn("held steady", f["summary"])
        self.assertNotIn("61.48", f["summary"])                    # no stop longitude named in the item
        self.assertEqual(lint_errors({"type": "Feature", "geometry": None, "properties": f}), [])

    def test_braking_seen_is_not_a_change(self):
        f = items(tracker_2025((2, 24), 12), "2025-02-24T12:00:00Z")[self.ID]["properties"]
        self.assertEqual(f["steps"]["braking"]["state"], "braking seen")
        self.assertEqual(f["last_change"], "new")

    def test_stopped_is_the_same_item(self):
        doc = tracker_2025((3, 12))
        self.assertEqual(doc["movers"], [])
        f = items(doc, "2025-03-12T00:00:00Z")[self.ID]
        p = f["properties"]
        self.assertEqual(p["steps"]["stopped"]["at"], "2025-03-07T14:14:10Z")
        self.assertEqual((p["last_change"], p["last_change_at"]), ("ended", "2025-03-07T14:14:10Z"))
        self.assertEqual(p["event_end"], "2025-03-07T00:00:00Z")
        self.assertIn("stopped at 6", p["title"])
        self.assertEqual(lint_errors(f), [])

    def test_a_stop_older_than_the_window_drops_out(self):
        self.assertEqual(tracker_2025((3, 20))["arrived"], [])


class IdStableAcrossRuns(unittest.TestCase):
    """The id rests on the last held set and the first moving set; sets added on later runs must not move it
    (ideas#524)."""

    def test_luch2_2025_one_id_every_half_day(self):
        seen = set()
        for day in range(7, 29):
            for hour in (0, 12):
                doc = tracker_2025((2, day), hour)
                seen |= set(items(doc, f"2025-02-{day:02d}T{hour:02d}:00:00Z"))
        seen |= set(items(tracker_2025((3, 12)), "2025-03-12T00:00:00Z"))
        self.assertEqual(seen, {"orbit:relocation:55841:2025-02-06"})

    @staticmethod
    def _id(rws):
        now = gt._t(rws[-1]["t"]) + timedelta(hours=1)
        o = {"norad": 99999, "name": "TEST", "owner": "X", "class": "drifting"}
        m = gt.track(o, rws, [], {}, "test", now)
        doc = {"at_utc": gt._iso(now), "movers": [m], "arrived": []}
        return [f["properties"]["id"] for f in feed.relocation_features(doc, gt._iso(now))]

    def test_a_pause_after_leaving_does_not_move_the_id(self):
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        r = lambda h, lon, drift: {"t": gt._iso(t0 + timedelta(hours=h)), "lon": lon, "drift": drift,
                                   "dh_km": 0.0, "i": 0.05}
        held = [r(12 * k, 10.0, 0.0) for k in range(10)]           # 4.5 days held at 10 E
        first = held + [r(120, 10.05, 0.12)]                        # one set over the line: the item appears
        later = first + [r(132, 10.07, 0.05), r(144, 10.08, 0.05),  # a day back under it, near the stop
                         r(156, 10.3, 0.4), r(168, 10.8, 0.8)]      # then the move
        self.assertEqual(self._id(first), ["orbit:relocation:99999:2026-01-05"])
        self.assertEqual(self._id(later), self._id(first))
        held_again = first + [r(132 + 12 * k, 10.06, 0.02) for k in range(5)] + [r(192, 10.3, 0.4)]
        self.assertEqual(self._id(held_again), ["orbit:relocation:99999:2026-01-08"])  # 2 days held: a new stop


class FeedMerge(unittest.TestCase):
    def test_replaces_earlier_items_and_keeps_the_rest(self):
        objs, elsets = load_2026()
        tracker = gt.build(objs, elsets, ROLES, datetime(2026, 11, 24, 19, 0, tzinfo=timezone.utc))
        old = {"type": "Feature", "geometry": None, "properties": {"id": "orbit:relocation:55841:2026-11-18"}}
        other = {"type": "Feature", "geometry": None, "properties": {"id": "orbit:maneuver:1:2026-11-01"}}
        doc = {"generated_at": GEN, "features": [old, other], "attribution": "Orbit", "licence": "GCAT"}
        with tempfile.TemporaryDirectory() as site:
            os.makedirs(os.path.join(site, "data"))
            path = os.path.join(site, "data", "feed.geojson")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
            geo_page.add_relocations(site, tracker)
            geo_page.add_relocations(site, tracker)                   # twice: still one item per move
            with open(path, encoding="utf-8") as fh:
                out = json.load(fh)
        ids = [f["properties"]["id"] for f in out["features"]]
        self.assertIn("orbit:maneuver:1:2026-11-01", ids)
        self.assertNotIn("orbit:relocation:55841:2026-11-18", ids)
        self.assertEqual(ids.count("orbit:relocation:55841:2026-11-19"), 1)
        self.assertIn("Space-Track", out["attribution"])

    def test_a_failed_tracker_adds_nothing(self):
        self.assertEqual(feed.relocation_features({"error": "x"}, GEN), [])


if __name__ == "__main__":
    unittest.main()
