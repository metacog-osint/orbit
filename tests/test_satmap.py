"""The satellite map's data (orbit/satmap.py, orbit-2.23, ideas#71). Offline: a 42-row cut of CelesTrak's active group
read 20 Nov 2026 and a small GCAT index."""
import gzip
import json
import shutil
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import importlib.util  # noqa: E402

from orbit import satmap  # noqa: E402

_spec = importlib.util.spec_from_file_location("orbit_cli_satmap", ROOT / "tools" / "orbit.py")
TOOL = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(TOOL)

FIX = ROOT / "tests" / "fixtures" / "celestrak_active_sample_20261120.csv"
INDEX = {"read_at": "2026-11-20T00:00:00Z", "objects": {
    "S00900": ["satcat", "900", "1964-063", "P", "Calsphere 1", "1964 Oct  6", "-", "-", "O", "NRL", "US", "LLEO/P"],
    "S40296": ["satcat", "40296", "2014-086", "P", "Meridian 7", "2014 Dec 25", "-", "-", "O", "MOK", "RU", "HEO"],
}}


class SatMap(unittest.TestCase):
    def setUp(self):
        self.doc = satmap.parse(FIX.read_bytes(), INDEX, "2026-11-20T21:20:00Z")
        self.rows = {r[0]: dict(zip(satmap.FIELDS, r)) for r in self.doc["rows"]}

    def test_every_row_is_kept_sorted_with_the_fields_sgp4_needs(self):
        self.assertEqual((self.doc["schema"], self.doc["count"], self.doc["unusable"]), ("orbit-sats/1", 42, 0))
        norads = [r[0] for r in self.doc["rows"]]
        self.assertEqual(norads, sorted(norads))
        r = self.rows[900]
        self.assertEqual((r["name"], r["cospar"], r["epoch"]), ("CALSPHERE 1", "1964-063C", "2026-11-20T13:37:59.532"))
        self.assertAlmostEqual(r["n"], 13.76772899)
        self.assertEqual(len(self.doc["fields"]), len(self.doc["rows"][0]))

    def test_owner_type_and_launch_join_from_gcat_by_norad(self):
        self.assertEqual(self.doc["gcat_joined"], 2)
        self.assertEqual((self.rows[900]["group"], self.rows[900]["cc"], self.rows[900]["type"], self.rows[900]["launch"]),
                         ("us", "US", "P", "1964-10-06"))
        self.assertEqual((self.rows[40296]["group"], self.rows[40296]["cls"]), ("ru", "heo"))
        unjoined = [r for r in self.rows.values() if r["norad"] not in (900, 40296)]
        self.assertTrue(all(r["group"] == "other" and r["cc"] is None for r in unjoined))

    def test_orbit_classes_and_constellations(self):
        self.assertEqual(satmap.orbit_class(15.5, 0.001), "leo")
        self.assertEqual(satmap.orbit_class(2.0, 0.01), "meo")
        self.assertEqual(satmap.orbit_class(1.0027, 0.0002), "geo")
        self.assertEqual(satmap.orbit_class(2.0, 0.7), "heo")
        self.assertEqual(satmap.orbit_class(0.5, 0.01), "other")
        cons = {r["con"] for r in self.rows.values()}
        self.assertTrue({"starlink", "gps", "beidou", "oneweb"} <= cons)
        self.assertIsNone(satmap.constellation("COSMOS 2433"))  # GLONASS isn't named by name

    def test_a_reply_that_is_not_gp_csv_fails(self):
        with self.assertRaises(ValueError):
            satmap.parse(b"<html>error</html>", INDEX, "t")


class SatsLane(unittest.TestCase):
    def setUp(self):
        self.tool = TOOL
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "raw").mkdir()
        (self.tmp / "state").mkdir()
        (self.tmp / "state" / "catalog_index.json.gz").write_bytes(gzip.compress(json.dumps(INDEX).encode()))
        self.calls = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def getter(self, url, timeout):
        self.calls.append(url)
        return FIX.read_bytes()

    def test_reads_once_a_utc_day_and_writes_the_file(self):
        out, recs, note = self.tool._lane_sats(self.tmp / "raw", {}, self.getter)
        self.assertEqual((out["sats"]["count"], len(recs), note, self.calls), (42, 1, None, [satmap.URL]))
        self.assertIn("GROUP=active&FORMAT=csv", satmap.URL)
        f = self.tmp / "state" / "sats.json"
        self.assertEqual(json.loads(f.read_text(encoding="utf-8"))["count"], 42)
        prev = {"sats": out["sats"]}
        again, _, note = self.tool._lane_sats(self.tmp / "raw", prev, self.getter)
        self.assertIsNone(again)
        self.assertIn("once a UTC day", note)
        self.assertEqual(len(self.calls), 1)

    def test_a_short_reading_or_a_refusal_fails_and_keeps_the_last_file(self):
        out, _, _ = self.tool._lane_sats(self.tmp / "raw", {}, self.getter)
        prev = {"sats": {**out["sats"], "read_at": "2026-11-19T00:00:00Z", "count": 1000}}
        with self.assertRaises(RuntimeError):
            self.tool._lane_sats(self.tmp / "raw", prev, self.getter)

        def refuse(url, timeout):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        prev["sats"]["count"] = 42
        with self.assertRaises(urllib.error.HTTPError):
            self.tool._lane_sats(self.tmp / "raw", prev, refuse)
        self.assertEqual(json.loads((self.tmp / "state" / "sats.json").read_text(encoding="utf-8"))["count"], 42)


if __name__ == "__main__":
    unittest.main()
