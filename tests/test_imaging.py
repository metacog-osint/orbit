"""The imaging lane (orbit-2.52): real catalogue answers for Kennedy Space Center, read 27 Nov 2026, and the last
48 days of USGS's Landsat calendar file. Offline."""
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orbit import imaging  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "imaging"
NOW = datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc)


def _getter(calls=None):
    def get(url, timeout=60):
        if calls is not None:
            calls.append(url)
        if url == imaging.CALENDAR_URL:
            return (FIX / "cycles_tail.json").read_bytes()
        for coll in ("landsat-c2l1", "sentinel-2-l1c", "sentinel-1-grd"):
            if f"collections={coll}" in url:
                return (FIX / f"kennedy_{coll}.json").read_bytes()
        raise AssertionError(url)
    return get


KSC = {"id": "kennedy", "name": "Kennedy", "lat": 28.6083, "lon": -80.6041, "kind": "launch site", "country": "US",
       "source": "GCAT"}


class Calendar(unittest.TestCase):
    def setUp(self):
        self.cal = imaging.parse_calendar((FIX / "cycles_tail.json").read_bytes())

    def test_template_carries_the_repeat_forward(self):
        c = self.cal["landsat_9"]
        self.assertEqual(c["through"], date(2025, 12, 31))
        d = date(2025, 12, 20)
        self.assertEqual(imaging.paths_on(self.cal, "landsat_9", d + timedelta(days=16 * 21)),
                         imaging.paths_on(self.cal, "landsat_9", d))

    def test_scenes_of_2026_fall_on_the_carried_calendar(self):
        # LC09 path 16 on 18 Nov 2026, LC09 path 15 on 11 Nov, LC08 path 16 on 10 Nov (fixture scenes)
        self.assertIn(16, imaging.paths_on(self.cal, "landsat_9", date(2026, 11, 18)))
        self.assertIn(15, imaging.paths_on(self.cal, "landsat_9", date(2026, 11, 11)))
        self.assertIn(16, imaging.paths_on(self.cal, "landsat_8", date(2026, 11, 10)))

    def test_a_file_that_does_not_repeat_is_refused(self):
        doc = json.loads((FIX / "cycles_tail.json").read_text())
        k = sorted(doc["landsat_8"], key=lambda s: datetime.strptime(s, "%m/%d/%Y"))[0]
        doc["landsat_8"][k] = {"path": "1,2,3", "cycle": "1"}
        with self.assertRaises(ValueError):
            imaging.parse_calendar(json.dumps(doc).encode())


class Read(unittest.TestCase):
    def setUp(self):
        self.cal = imaging.parse_calendar((FIX / "cycles_tail.json").read_bytes())
        self.calls = []
        self.doc, self.recs = imaging.read([KSC], _getter(self.calls), self.cal, NOW, pause=lambda s: None)
        self.row = self.doc["places"][0]

    def test_three_searches_per_place(self):
        self.assertEqual(len(self.calls), 3)
        self.assertTrue(all("intersects" in u and "sortby=-properties.datetime" in u for u in self.calls))

    def test_last_acquired_is_the_newest_scene(self):
        self.assertEqual(self.row["landsat"]["last_acquired"]["id"], "LC09_L1GT_016040_20261118_20261119_02_T2")
        self.assertTrue(self.row["sentinel2"]["last_acquired"]["id"].startswith("S2C_MSIL1C_20261125"))
        self.assertEqual(self.row["sentinel1"]["last_acquired"]["mode"], "IW")

    def test_landsat_due_from_daylight_paths_only(self):
        nxt = self.row["landsat"]["next"]
        self.assertEqual(nxt["status"], "on calendar")
        paths = {(p["platform"], p["wrs_path"]) for p in nxt["paths"]}
        self.assertNotIn(116, {p for _, p in paths})  # the night scene's path is not a daylight path
        self.assertIn(("Landsat 9", 16), paths)
        self.assertTrue(all(d["date"] > "2026-11-27" and d["date"] <= "2026-12-13" for d in nxt["due"]))
        # LC09 imaged path 16 on 18 Nov, so it is due again 16 days later, on 4 Dec
        self.assertIn({"date": "2026-12-04", "platform": "Landsat 9", "wrs_path": 16}, nxt["due"])

    def test_sentinel_plans_are_never_given(self):
        self.assertEqual(self.row["sentinel2"]["planned"], imaging.SENTINEL_PLAN)
        self.assertEqual(self.row["sentinel1"]["planned"], imaging.SENTINEL_PLAN)
        self.assertNotIn("due", self.row["sentinel2"])

    def test_credit_names_the_year(self):
        self.assertIn("Copernicus Sentinel data 2026", self.doc["credit"]["sentinel"])

    def test_off_calendar_scene_makes_landsat_unknown(self):
        scenes = [{"id": "x", "platform": "LANDSAT_9", "datetime": "2026-11-18T15:55:33Z", "sun_elevation": 40,
                   "wrs_path": "200"}]
        nxt = imaging.landsat_due(scenes, self.cal, NOW.date())
        self.assertEqual(nxt["status"], "unknown")
        self.assertEqual(nxt["off_calendar"], ["x"])

    def test_failed_search_raises(self):
        def bad(url, timeout=60):
            return b'{"message": "Internal server error"}'
        with self.assertRaises(ValueError):
            imaging.read([KSC], bad, self.cal, NOW, pause=lambda s: None)


class Places(unittest.TestCase):
    def test_reviewed_list_loads(self):
        places = imaging.load_places()
        self.assertGreaterEqual(len(places), 10)
        self.assertTrue(all(p["source"].startswith("GCAT sites.tsv") for p in places))


class Lane(unittest.TestCase):
    def test_lane_writes_the_file_and_reads_once_a_day(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("orbit_tool", ROOT / "tools" / "orbit.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        orig_now, orig_pause = imaging.utc_now, imaging.PAUSE
        imaging.utc_now = lambda: NOW
        imaging.PAUSE = 0
        try:
            with tempfile.TemporaryDirectory() as tmp:
                raw = Path(tmp) / "data" / "raw"
                calls = []
                res, recs, note = tool._lane_imaging(raw, {}, _getter(calls))
                self.assertEqual(res["imaging"]["places"], len(imaging.load_places()))
                self.assertTrue((Path(tmp) / "data" / tool.IMAGING).exists())
                self.assertEqual(calls[0], imaging.CALENDAR_URL)
                again = tool._lane_imaging(raw, {"imaging": res["imaging"]}, _getter())
                self.assertIsNone(again[0])
        finally:
            imaging.utc_now, imaging.PAUSE = orig_now, orig_pause


if __name__ == "__main__":
    unittest.main()
