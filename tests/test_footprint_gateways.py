"""Tests for the FCC earth-station layer in tools/footprints.py (ideas#232, decision 5). Made-up records only."""
import json
import pathlib
import sys
import unittest
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import footprints as fpt  # noqa: E402


def site(call, licensee, lon=None, lat=None):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]} if lon is not None else None,
            "properties": {"callsign": call, "licensee": licensee, "station_class": "FES",
                           "station_class_text": "Fixed Earth Stations", "date_grant": "2025-01-02", "date_expire": "2040-01-02"}}


GW = {"header": {"file_date": "2026-07-15"},
      "satellites": [{"id": "TEST-1@10 W.L.", "features": [site("E1", "Zeta Co", -100, 40), site("E2", "Alpha Co")]},
                     {"id": "EMPTY@20 W.L.", "features": []}]}


class GatewayLayer(unittest.TestCase):
    def test_points_table_and_age(self):
        layer, table, notes = fpt.gateway_parts({"id": "c", "fcc_earth_stations": ["TEST-1@10 W.L."]}, GW, date(2026, 11, 24))
        self.assertEqual(layer["kind"], "published")
        self.assertEqual(len(layer["geojson"]["features"]), 1)          # the site without coordinates is not drawn
        self.assertIn("1 more with no coordinates", layer["label"])
        self.assertIn("132 days old", layer["uncertainty"])
        self.assertEqual([r[0] for r in table["rows"]], ["E2", "E1"])  # by licensee
        self.assertEqual(table["rows"][0][5], "no coordinates")
        self.assertEqual(notes, [])

    def test_no_licence_says_so(self):
        layer, table, notes = fpt.gateway_parts({"id": "c", "fcc_earth_stations": []}, GW, date(2026, 11, 24))
        self.assertIsNone(layer)
        self.assertIsNone(table)
        self.assertTrue(notes[0].startswith("No current FCC earth-station licence"))

    def test_unlisted_case_untouched(self):
        self.assertEqual(fpt.gateway_parts({"id": "c"}, GW, date(2026, 11, 24)), (None, None, []))

    def test_unknown_name_fails(self):
        with self.assertRaises(SystemExit):
            fpt.gateway_parts({"id": "c", "fcc_earth_stations": ["RENAMED@10 W.L."]}, GW, date(2026, 11, 24))

    def test_rerun_replaces(self):
        case = {"id": "c", "fcc_earth_stations": ["TEST-1@10 W.L."]}
        out = {"layers": [{"id": "los5"}], "notes": ["kept"]}
        for _ in range(2):
            fpt.add_gateways(case, out, GW, date(2026, 11, 24))
        self.assertEqual([l["id"] for l in out["layers"]], ["los5", "fcc-es"])
        self.assertEqual(len(out["tables"]), 1)
        self.assertEqual(out["notes"], ["kept"])

    def test_every_case_names_its_entries(self):
        cases = json.loads((ROOT / "doctrine" / "footprint-cases.json").read_text(encoding="utf-8"))["cases"]
        for c in cases:
            self.assertIn("fcc_earth_stations", c, c["id"])


if __name__ == "__main__":
    unittest.main()


class BuildOnly(unittest.TestCase):
    """--only rebuilds named cases and keeps the rest from the last build, at the same positions time."""

    def args(self, out, only, when="2026-11-24T16:00:00Z"):
        import argparse
        return argparse.Namespace(only=only, when=when, out=str(out), gateways=None, day_file="unused",
                                  tle_dir="unused", published=None)

    def test_unknown_case_is_refused(self):
        with self.assertRaises(SystemExit):
            fpt.cmd_build(self.args(ROOT / "site_src" / "footprints-data.json", ["no-such-case"]))

    def test_a_different_positions_time_is_refused(self):
        with self.assertRaises(SystemExit) as e:
            fpt.cmd_build(self.args(ROOT / "site_src" / "footprints-data.json", ["geo-wide-galaxy31"], when="2020-01-01T00:00:00Z"))
        self.assertIn("--when", str(e.exception))
