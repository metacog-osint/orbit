"""geo_tracker: the GEO relocation tracker (ideas#248) on real element sets. Luch (Olymp) 2 leaving 62 E in November
2026 (Orbit's public GEO release), USA 325 with a 9-day-old set, and Luch 2's 2025 move from 0.9 W to 62 E (its
Space-Track history, ideas#256) for the speeding-up case and brake detection."""
import json
import os
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.append(os.path.join(ROOT, "tools"))
import geo_belt  # noqa: E402
import geo_tracker as gt  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
ROLES = {"55841": "inspection", "51281": "inspection"}


def load_2026():
    with open(os.path.join(FIX, "geo_tracker_20261124.json"), encoding="utf-8") as f:
        d = json.load(f)
    objs = [dict(zip(d["object_cols"], r)) for r in d["objects"]]
    for o in objs:
        o["class"] = geo_belt.classify(geo_belt.drift(o["n"]), o["i"])
    elsets = {int(k): [dict(zip(d["elset_cols"], r)) for r in v] for k, v in d["elsets"].items()}
    return objs, elsets


def load_2025():
    """Luch 2's sets from 25 Jan to 20 Mar 2025 as element-file rows, and the object as the day file has it."""
    with open(os.path.join(FIX, "spacetrack_gp_history_55841_excerpt.json"), encoding="utf-8") as f:
        recs = sorted(json.load(f)["windows"]["move_2025"], key=lambda r: r["CREATION_DATE"])  # re-issues last
    rows = [{"epoch": r["EPOCH"], "n": r["MEAN_MOTION"], "e": r["ECCENTRICITY"], "i": r["INCLINATION"],
             "raan": r["RA_OF_ASC_NODE"], "argp": r["ARG_OF_PERICENTER"], "M": r["MEAN_ANOMALY"]} for r in recs]
    return rows


def at_2025(rows, now):
    held = sorted((r for r in rows if r["epoch"][:19] < now.strftime("%Y-%m-%dT%H:%M:%S")), key=lambda r: r["epoch"])
    o = dict(held[-1], norad=55841, name="LUCH (OLYMP) 2", owner="CIS")
    for k in ("n", "e", "i", "raan", "argp", "M"):
        o[k] = float(o[k])
    o["class"] = geo_belt.classify(geo_belt.drift(o["n"]), o["i"])
    return gt.build([o], {55841: rows}, ROLES, now)["movers"][0]


class Luch2November2026(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        objs, elsets = load_2026()
        cls.doc = gt.build(objs, elsets, ROLES, datetime(2026, 11, 24, 19, 0, tzinfo=timezone.utc))
        cls.m = next(m for m in cls.doc["movers"] if m["norad"] == 55841)

    def test_newest_set_and_now(self):
        n = self.m["newest"]
        self.assertEqual(n["t"], "2026-11-22T15:37:18Z")
        self.assertAlmostEqual(n["lon"], 58.19, delta=0.01)
        self.assertAlmostEqual(n["drift"], -2.467, delta=0.001)
        self.assertAlmostEqual(n["age_h"], 51.4, delta=0.1)
        self.assertTrue(self.m["now"]["extrapolated"])
        self.assertAlmostEqual(self.m["now"]["lon"], 52.91, delta=0.02)
        self.assertFalse(self.m["stale"])
        self.assertAlmostEqual(self.m["max_gap_h"], 887.7, delta=0.1)

    def test_departure(self):
        """It held 61.98 E to 15 Oct; the start estimates fall on 19 Nov, inside the 37-day gap (ideas#248: 'about
        19-20 Nov')."""
        d = self.m["departure"]
        self.assertAlmostEqual(d["lon"], 61.98, delta=0.02)
        self.assertEqual(d["last_held_set"], "2026-10-15T15:56:16Z")
        self.assertEqual([e["t"][:10] for e in d["estimated_start"]], ["2026-11-19", "2026-11-19"])
        self.assertEqual(len(d["estimated_start"][1]["sets"]), 2)

    def test_coast_only_on_two_sets(self):
        self.assertEqual(self.m["cases"], ["coast"])
        self.assertFalse(self.m["speeding_up"]["shown"])
        self.assertEqual(self.m["brake"]["state"], "none")

    def test_passes(self):
        """Slots already passed at the coast rate are counted; the first listed is Yahsat 1A at 52.5 E."""
        first = self.m["passes"][0]
        self.assertEqual(first["objects"][0]["name"], "YAHSAT 1A")
        self.assertEqual(first["coast"], "2026-11-24T23:10Z")
        self.assertNotIn("speeding_up", first)
        self.assertEqual(self.m["passed_since_newest"], 1)          # Express AM-6 / Skynet 5D at 53.0 E (fixture)
        lons = [p["lon"] for p in self.m["passes"]]
        self.assertEqual(lons, sorted(lons, reverse=True))          # westward, in order

    def test_stop_history_neighbour(self):
        s = self.m["stops"][-1]
        self.assertEqual(s["kind"], "held")
        self.assertEqual(s["neighbours"][0]["name"], "INTELSAT 39")
        self.assertLessEqual(s["neighbours"][0]["deg"], 0.05)

    def test_track_for_the_chart(self):
        """ideas#321: the chart's sets run from 7 days before the last held set (15 Oct) to the newest; a stale
        entry carries none."""
        tr = self.m["track"]
        self.assertEqual(tr["from"], "2026-10-08T15:56Z")
        self.assertEqual(tr["sets"][-1], ["2026-11-22T15:37:18Z", 58.19])
        self.assertTrue(all(s[0] >= "2026-10-08T15:56" for s in tr["sets"]))
        self.assertEqual([s[0][:10] for s in tr["sets"]], ["2026-10-09", "2026-10-10", "2026-10-11", "2026-10-14",
                                                         "2026-10-15", "2026-11-21", "2026-11-22"])
        stale = next(m for m in self.doc["movers"] if m["norad"] == 51281)
        self.assertNotIn("track", stale)

    def test_last_day(self):
        """ideas#322: nothing new in the 24 hours to 24 Nov 19:00Z; the day of 22 Nov brought one set, faster than
        the one before it."""
        self.assertEqual(self.m["last_day"]["new_sets"], 0)
        objs, elsets = load_2026()
        doc = gt.build(objs, elsets, ROLES, datetime(2026, 11, 22, 20, 0, tzinfo=timezone.utc))
        d = next(m for m in doc["movers"] if m["norad"] == 55841)["last_day"]
        self.assertEqual(d["new_sets"], 1)
        self.assertEqual(d["set_before"], "2026-11-21T15:41:09Z")
        self.assertAlmostEqual(d["drift_before"], -1.62, delta=0.01)
        self.assertEqual(d["brake_before"], "none")

    def test_wording(self):
        self.assertIn("not a forecast", self.doc["note"])
        self.assertIn("braking", self.doc["braking_note"])


class StaleSet(unittest.TestCase):
    def test_usa_325(self):
        """USA 325's newest set is 9 days old at the build time: no position now, no passes, no projection."""
        objs, elsets = load_2026()
        doc = gt.build(objs, elsets, ROLES, datetime(2026, 11, 24, 19, 0, tzinfo=timezone.utc))
        m = next(m for m in doc["movers"] if m["norad"] == 51281)
        self.assertTrue(m["stale"])
        self.assertIsNone(m["now"])
        self.assertEqual(m["passes"], [])
        self.assertEqual(m["brake"]["state"], "stale")


class Luch2Move2025(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = load_2025()

    def test_speeding_up_case(self):
        """At 23:00Z on 12 Feb 2025 the rate was still rising set after set (2.82, 3.00, 3.21 deg a day): both
        cases, the speeding-up date earlier. By 15 Feb it coasted at 3.37 and only the coast case is left."""
        m = at_2025(self.rows, datetime(2025, 2, 12, 23, 0, tzinfo=timezone.utc))
        self.assertEqual(m["cases"], ["coast", "speeding up"])
        self.assertGreater(m["speeding_up"]["rate_change"], 0)
        self.assertEqual(at_2025(self.rows, datetime(2025, 2, 15, tzinfo=timezone.utc))["cases"], ["coast"])

    def test_travel_days(self):
        self.assertAlmostEqual(gt._travel_days(10.0, 2.0, 0), 5.0)
        self.assertLess(gt._travel_days(10.0, 2.0, 0.5), 5.0)
        self.assertAlmostEqual(gt._travel_days(100.0, 4.5, 1.0), 100.0 / 4.5)   # at the cap: coast

    def test_brake_steady(self):
        """At 00:00Z on 28 Feb 2025 the steady projection is 61.48 E (it stopped at 61.99 E on 7 Mar); passes are not
        listed once a stop is projected. The projection is redone on every set: a day later it reads 60.02 E (the
        braking came in two stages)."""
        m = at_2025(self.rows, datetime(2025, 2, 28, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(m["brake"]["state"], "steady")
        self.assertAlmostEqual(m["brake"]["projected_lon"], 61.48, delta=0.05)
        self.assertEqual(m["passes"], [])
        later = at_2025(self.rows, datetime(2025, 3, 1, 0, 0, tzinfo=timezone.utc))["brake"]
        self.assertAlmostEqual(later["projected_lon"], 60.02, delta=0.05)

    def test_brake_seen_not_steady(self):
        """On 24 Feb 2025 one fall in drift is measured (it would project 121 E); nothing is projected yet."""
        m = at_2025(self.rows, datetime(2025, 2, 24, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(m["brake"]["state"], "braking seen")
        self.assertNotIn("projected_lon", m["brake"])


class PageWiring(unittest.TestCase):
    def test_movers_in_belt(self):
        """geo_page.movers gives the tracker; a failure becomes {"error": ...} so the belt board still shows."""
        import geo_page
        objs, elsets = load_2026()
        now = datetime(2026, 11, 24, 19, 0)
        doc = geo_page.movers(objs, elsets, ROLES, now)
        self.assertEqual(sorted(m["norad"] for m in doc["movers"]), [51281, 55841])
        self.assertIn("error", geo_page.movers([{"norad": 55841, "class": "drifting"}], {55841: [{}]}, ROLES, now))

    def test_page_wording(self):
        """The approved wording (24 Nov 2026): the table heading, both cases named, the braking note, the extrapolated mark;
        no likelihood words in the section."""
        html = open(os.path.join(ROOT, "site_src", "geo.html"), encoding="utf-8").read()
        js = open(os.path.join(ROOT, "site_src", "geo", "globe.js"), encoding="utf-8").read()
        self.assertIn('id="geo-movers"', html)
        self.assertIn('src="tic-fold.js"', html)
        start = js.index("relocation tracker (tools/geo_tracker.py")
        part = js[start:js.index('document.addEventListener("click"', start)]
        for words in ("At the last measured rate", "Still speeding up", "extrapolated", "braking_note", "note",
                      "How to read this section", "moverSummary", "moverChart", "mv-chartbox", "movers-",
                      "Last 24 hours", "From now", "An element set is", "slips west"):
            self.assertIn(words, part)
        self.assertEqual(part.count("braking_note"), 1)             # the braking note once, at the top (ideas#321)
        for bad in ("likely", "probab", "expected to", "will arrive", "target"):
            self.assertNotIn(bad, part.lower())


if __name__ == "__main__":
    unittest.main()
