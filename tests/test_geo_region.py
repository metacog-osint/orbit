"""The GEO region (orbit/geo_region.py), offline: regions and edges, events, the day file, the element files, and
the gp query's guard on the shared Space-Track account."""
import gzip
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from orbit import geo_region as G, spacetrack  # noqa: E402

N_GEO = 1.0027   # rev/day: about the GEO radius


def rec(norad, n=N_GEO, e=0.0002, i=0.05, epoch="2026-11-15T12:00:00.000000", kind="PAYLOAD", launch="2015-03-01",
        name=None):
    return {"NORAD_CAT_ID": str(norad), "EPOCH": epoch, "MEAN_MOTION": str(n), "ECCENTRICITY": str(e),
            "INCLINATION": str(i), "RA_OF_ASC_NODE": "80.1", "ARG_OF_PERICENTER": "200.2", "MEAN_ANOMALY": "10.3",
            "BSTAR": "0", "MEAN_MOTION_DOT": "0", "MEAN_MOTION_DDOT": "0", "ELEMENT_SET_NO": "999", "REV_AT_EPOCH": "4000",
            "OBJECT_NAME": name or f"SAT {norad}", "OBJECT_ID": "2015-010A", "OBJECT_TYPE": kind, "COUNTRY_CODE": "US",
            "LAUNCH_DATE": launch, "RCS_SIZE": "LARGE"}


class Regions(unittest.TestCase):
    def test_zone_graveyard_below_inclined(self):
        self.assertEqual(G.region_of(N_GEO, 0.0002, 0.05), "zone")
        self.assertEqual(G.region_of(0.985, 0.0002, 0.05), "graveyard")   # about 300 km above GEO
        self.assertEqual(G.region_of(1.02, 0.0002, 0.05), "below")
        self.assertEqual(G.region_of(N_GEO, 0.0002, 20.0), "inclined")
        self.assertEqual(G.region_of(N_GEO, 0.01, 5.0), "crossing")       # reaches the zone's altitudes, not inside

    def test_edges_hold_an_edge_rider(self):
        i = 14.9  # inside the 15 deg edge, but within 0.25 deg of it
        self.assertEqual(G.region_of(N_GEO, 0.0002, i), "zone")
        self.assertEqual(G.region_of(N_GEO, 0.0002, i, prev="inclined"), "crossing")  # not in the zone until 0.25 deg inside
        self.assertEqual(G.region_of(N_GEO, 0.0002, 15.1, prev="zone"), "zone")       # must go 0.25 deg outside

    def test_near_geo(self):
        self.assertTrue(G.near_geo(1.0, 0.1))
        self.assertFalse(G.near_geo(1.2, 0.1))
        self.assertFalse(G.near_geo(1.0, 0.3))


class Days(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_day_then_events(self):
        day1 = [rec(1), rec(2), rec(3, n=1.02), rec(4)]
        s, paths = G.pull("2026-11-14", self.out, day1, active={1, 2, 4}, fetched="2026-11-14T03:20Z")
        self.assertTrue(s["first_day"])
        self.assertEqual(s["events"], 0)
        self.assertEqual(s["objects"], 4)
        day2 = [rec(1, n=0.985, epoch="2026-11-15T01:00:00"),                            # left up
                rec(2, epoch="2026-11-05T00:00:00"),                                       # quiet (old elements)
                rec(3, epoch="2026-11-15T02:00:00"),                                       # arrived from below
                rec(5, epoch="2026-11-15T03:00:00", launch="2026-10-30")]                  # new, arrived
        # 4 gone; 2's day-1 epoch must be fresh for "quiet" to fire on day 2
        s2, _ = G.pull("2026-11-15", self.out, day2, active=None, fetched="2026-11-15T03:20Z")
        doc = G.load_region(self.out, "2026-11-15")
        kinds = sorted((e["norad"], e["kind"]) for e in doc["events"])
        self.assertIn((1, "left up"), kinds)
        self.assertIn((3, "arrived"), kinds)
        self.assertIn((4, "gone"), kinds)
        self.assertIn((5, "new"), kinds)
        self.assertIn((5, "arrived"), kinds)
        self.assertEqual(doc["active"], [1, 2, 4])  # CelesTrak not read: yesterday's list carried
        self.assertEqual(doc["object_cols"][-2:], ["elset", "rev"])
        self.assertEqual(doc["source"], G.CITE)

    def test_quiet_needs_fresh_elements_the_day_before(self):
        G.pull("2026-11-14", self.out, [rec(2, epoch="2026-11-14T00:00:00")], active={2})
        G.pull("2026-11-15", self.out, [rec(2, epoch="2026-11-07T12:00:00")], active={2})
        kinds = [e["kind"] for e in G.load_region(self.out, "2026-11-15")["events"]]
        self.assertEqual(kinds, ["quiet"])

    def test_quiet_only_for_active_payloads(self):
        G.pull("2026-11-14", self.out, [rec(2, epoch="2026-11-14T00:00:00")], active={9})
        G.pull("2026-11-15", self.out, [rec(2, epoch="2026-11-07T12:00:00")], active={9})
        self.assertEqual(G.load_region(self.out, "2026-11-15")["events"], [])

    def test_element_files_merge_by_month_and_drop_before_history(self):
        G.pull("2026-11-14", self.out, [rec(1, epoch="2026-11-14T00:00:00"), rec(2, epoch="2026-06-30T00:00:00")])
        G.pull("2026-11-15", self.out, [rec(1, epoch="2026-11-15T00:00:00"), rec(1, epoch="2026-11-14T00:00:00")])
        rows = G.read_elements(os.path.join(self.out, G.elements_name("2026-11")))
        self.assertEqual([(r["norad"], r["epoch"][:10]) for r in rows], [(1, "2026-11-14"), (1, "2026-11-15")])
        self.assertFalse(os.path.exists(os.path.join(self.out, G.elements_name("2026-06"))))
        with gzip.open(os.path.join(self.out, G.elements_name("2026-11")), "rt", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["schema"], "orbit-geo-elements/1")

    def test_release_tags_by_year(self):
        self.assertEqual(G.tag_for("2026-11-15.geo-region.json"), "geo-2026")
        self.assertEqual(G.tag_for("geo-elements-2027-01.json.gz"), "geo-2027")

    def test_active_ids(self):
        self.assertEqual(G.active_ids(json.dumps([{"NORAD_CAT_ID": 1}, {"NORAD_CAT_ID": "26038"}]).encode()), {1, 26038})
        with self.assertRaises(ValueError):
            G.active_ids(b"[]")


class SharedAccount(unittest.TestCase):
    """The GEO query waits for Noisefloor's and Orbit's update runs; the update run waits for Noisefloor's and this one."""
    NOW = datetime(2026, 11, 16, 15, 30, tzinfo=timezone.utc)

    def get(self, busy_url):
        def _get(url):
            if url == busy_url:
                return {"workflow_runs": [{"id": 7, "status": "in_progress", "run_started_at": "2026-11-16T15:20:00Z",
                                           "jobs_url": "jobs"}]}
            if url.startswith("https://api.github.com"):
                return {"workflow_runs": []}
            return {"jobs": []}
        return _get

    def test_geo_waits_for_update_and_noisefloor(self):
        self.assertIn("update run", spacetrack.shared_gp_busy(self.NOW, self.get(spacetrack.UPDATE_RUNS), spacetrack.FOR_GEO))
        self.assertIn("Noisefloor", spacetrack.shared_gp_busy(self.NOW, self.get(spacetrack.SHARED_RUNS), spacetrack.FOR_GEO))
        self.assertIsNone(spacetrack.shared_gp_busy(self.NOW, self.get(spacetrack.GEO_RUNS), spacetrack.FOR_GEO))

    def test_update_waits_for_geo(self):
        self.assertIn("GEO region", spacetrack.shared_gp_busy(self.NOW, self.get(spacetrack.GEO_RUNS)))
        self.assertIsNone(spacetrack.shared_gp_busy(self.NOW, self.get(spacetrack.UPDATE_RUNS)))

    def test_geo_step_names_match_the_workflows(self):
        geo = (ROOT / ".github" / "workflows" / "geo.yml").read_text(encoding="utf-8")
        upd = (ROOT / ".github" / "workflows" / "update.yml").read_text(encoding="utf-8")
        self.assertIn(f"name: {spacetrack.GEO_STEP}\n", geo)
        self.assertIn(f"name: {spacetrack.UPDATE_STEP}\n", upd)


if __name__ == "__main__":
    unittest.main()
