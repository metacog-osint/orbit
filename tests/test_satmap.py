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
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import importlib.util  # noqa: E402

from orbit import catsources, satmap  # noqa: E402

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
        self.assertIsNone(satmap.constellation("COSMOS 2433"))  # no series in brackets: not counted
        self.assertEqual(satmap.constellation("COSMOS 2433 [GLONASS-M]"), "glonass")
        self.assertEqual(satmap.constellation("COSMOS 2547 [GLONASS-K2]"), "glonass")
        self.assertEqual(satmap.constellation("HULIANWANG DIGUI-17"), "guowang")
        self.assertIsNone(satmap.constellation("HULIANWANG JISHU SHIYAN 4A"))  # a test satellite, not Guowang
        self.assertEqual(satmap.constellation("QIANFAN-12"), "qianfan")
        self.assertEqual(satmap.constellation("QIANFAN 16 OBJECT A"), "qianfan")

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
            raise catsources.Refused("celestrak-gp-active", url, 403)
        prev["sats"]["count"] = 42
        with self.assertRaises(satmap.Stopped):
            self.tool._lane_sats(self.tmp / "raw", prev, refuse)
        self.assertEqual(json.loads((self.tmp / "state" / "sats.json").read_text(encoding="utf-8"))["count"], 42)

    def _stopped(self, code=403):
        def refuse(url, timeout):
            self.calls.append(url)
            raise catsources.Refused("celestrak-gp-active", url, code)
        with self.assertRaises(satmap.Stopped) as ctx:
            self.tool._lane_sats(self.tmp / "raw", {}, refuse)
        self.assertIn(f"HTTP {code}", str(ctx.exception))
        self.assertIn("until a person clears", str(ctx.exception))
        self.calls.clear()
        return json.loads((self.tmp / "state" / "sats_stop.json").read_text(encoding="utf-8"))

    def test_a_non_200_stops_every_later_request_even_a_503_on_a_later_day(self):
        clear = self.tmp / "clear.txt"
        with mock.patch.object(satmap, "CLEAR_FILE", clear):
            self.assertEqual(self._stopped(503)["code"], 503)
            for _ in range(3):
                with self.assertRaises(satmap.Stopped):
                    self.tool._lane_sats(self.tmp / "raw", {"sats": {"read_at": "2020-01-01T00:00:00Z"}}, self.getter)
        self.assertEqual(self.calls, [])

    def test_only_the_stops_own_time_clears_it_and_the_record_is_kept(self):
        clear = self.tmp / "clear.txt"
        with mock.patch.object(satmap, "CLEAR_FILE", clear):
            stop = self._stopped()
            clear.write_text("2020-01-01T00:00:00Z\n", encoding="utf-8")
            with self.assertRaises(satmap.Stopped):
                self.tool._lane_sats(self.tmp / "raw", {}, self.getter)
            self.assertEqual(self.calls, [])
            clear.write_text(stop["at"] + "\n", encoding="utf-8")
            out, _, _ = self.tool._lane_sats(self.tmp / "raw", {}, self.getter)
        self.assertEqual((out["sats"]["count"], len(self.calls)), (42, 1))
        self.assertFalse((self.tmp / "state" / "sats_stop.json").exists())
        kept = json.loads((self.tmp / "state" / "sats_stop_history.jsonl").read_text(encoding="utf-8"))
        self.assertEqual((kept["code"], kept["at"]), (403, stop["at"]))

    def test_an_unreadable_stop_record_still_stops(self):
        (self.tmp / "state" / "sats_stop.json").write_text("{not json", encoding="utf-8")
        with mock.patch.object(satmap, "CLEAR_FILE", self.tmp / "clear.txt"), self.assertRaises(satmap.Stopped):
            self.tool._lane_sats(self.tmp / "raw", {}, self.getter)
        self.assertEqual(self.calls, [])

    def test_a_timeout_is_not_a_stop_and_the_next_run_asks_again(self):
        def slow(url, timeout):
            raise urllib.error.URLError("timed out")
        with self.assertRaises(urllib.error.URLError):
            self.tool._lane_sats(self.tmp / "raw", {}, slow)
        self.assertFalse((self.tmp / "state" / "sats_stop.json").exists())
        out, _, _ = self.tool._lane_sats(self.tmp / "raw", {}, self.getter)
        self.assertEqual(out["sats"]["count"], 42)

    def test_get_refuses_any_status_but_200(self):
        err = urllib.error.HTTPError(satmap.URL, 301, "Moved", {}, None)
        with mock.patch.object(catsources._OPENER, "open", side_effect=err), self.assertRaises(catsources.Refused):
            satmap.get()


if __name__ == "__main__":
    unittest.main()
