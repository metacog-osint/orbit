"""Names: the loose lookup and the longitude a name states (orbit/namepos.py; ideas#359, #360, #361). Cases are real
names from the TIC catalog's search index of 24 Nov 2026. No sgp4 here: geo_page's longitude is stubbed."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))                   # the orbit package before tools/orbit.py
from orbit import namepos as N  # noqa: E402
import geo_page as G  # noqa: E402

SEARCH = {"schema": "tic-catalog-search/1", "read": "2026-11-24",
          "columns": ["key", "name", "other_names", "cospar", "type", "gone"],
          "objects": [
              ["33459", "EUTE HOT BIRD 13C (HB 9)", ["Hot Bird 9", "EUTELSAT HOTBIRD 13C", "Eutelsat 12 West G", "Hot Bird 13C"], "2008-065A", "p", 0],
              ["27508", "EUTE 12 WEST A (AB 1)", ["Atlantic Bird 1", "EUTELSAT 36 WEST A", "Eutelsat 59A", "Eutelsat 12 West A"], "2002-040A", "p", 0],
              ["26927", "EUTE 12 WEST B", ["Atlantic Bird 2", "EUTELSAT 12 WEST B", "Eutelsat 8 West A"], "2001-042A", "p", 0],
              ["41748", "INTELSAT 33E (IS-33E)", ["IS-33E"], "2016-053B", "p", 0],
              ["25544", "ISS (ZARYA)", ["International Space Station"], "1998-067A", "p", 0],
          ]}


class StatedLongitude(unittest.TestCase):
    def test_positions_from_the_naming_schemes(self):
        cases = {
            "Eutelsat 12 West G": -12.0, "EUTE 115 WEST B(SATMEX 7": -115.0, "EUTELSAT 5 West B": -5.0,
            "EUTE 36B (EUTE W7)": 36.0, "EUTELSAT 7C": 7.0, "EUTE 33E": 33.0, "Eute 36X": 36.0,
            "EUTELSAT 172B": 172.0, "EUTELSAT 9B/EDRS-A": 9.0, "Eutelsat 25B/Es'hail 1": 25.0,
            "EUTE 117W B": -117.0, "EUTE 65W": -65.0, "EUTELSAT 5WB": -5.0, "Eutelsat 65WA": -65.0,
            "EUTE HOT BIRD 13C (HB 9)": 13.0, "Hotbird 13E": 13.0, "EUTELSAT HOTBIRD 13G": 13.0,
            "HISPASAT 30W-6": -30.0, "Hispasat 143W-1": -143.0,
        }
        for name, lon in cases.items():
            with self.subTest(name=name):
                self.assertEqual(N.stated_lon(name)[0], lon)

    def test_series_letters_and_serials_are_not_positions(self):
        for name in ("INTELSAT 37E (IS-37E)", "IS-32E", "ASTRA 2E", "FENGYUN 2E", "Hot Bird 9", "HOT BIRD 1",
                     "Eutelsat W3C", "EUTE W7", "TRANSIT 5E-3", "RADIATION SAT (5E-1)", "Intelsat 1W", "GSAT-19E",
                     "Galileo 10E", "FLOCK 2E 1", "Hispasat 1E", "YAOGAN-30 W", "ISS (ZARYA)", "", None):
            with self.subTest(name=name):
                self.assertIsNone(N.stated_lon(name))

    def test_apart_goes_the_short_way(self):
        self.assertAlmostEqual(N.apart(-12.0, -50.32), 38.32)
        self.assertAlmostEqual(N.apart(179.0, -179.0), 2.0)

    def test_positions_once_per_name_with_distance(self):
        got = N.positions(["EUTELSAT HOTBIRD 13C", "Eutelsat Hotbird 13C", "Eutelsat 12 West G", "Hot Bird 9"], -50.32)
        self.assertEqual([(p["name"], p["stated_lon"], p["apart_deg"]) for p in got],
                         [("EUTELSAT HOTBIRD 13C", 13.0, 63.3), ("Eutelsat 12 West G", -12.0, 38.3)])
        self.assertNotIn("apart_deg", N.positions(["EUTE 36B"], None)[0])


class Lookup(unittest.TestCase):
    def keys(self, q):
        return [h["key"] for h in N.find(SEARCH, q)]

    def test_any_source_name_and_short_forms(self):
        for q in ("Eutelsat 12 West G", "12 west g", "12WG", "12-West-G", "Hotbird 13C"):
            with self.subTest(q=q):
                self.assertEqual(self.keys(q), ["33459"])

    def test_number_and_cospar(self):
        self.assertEqual(self.keys("33459"), ["33459"])
        self.assertEqual(self.keys("2002-040A"), ["27508"])

    def test_display_name_ranks_before_other_names(self):
        # "12 West A" is 27508's display name; 26927 has only "12 West B"
        self.assertEqual(self.keys("12 West A"), ["27508"])
        self.assertEqual(self.keys("12 west")[:2], ["27508", "26927"])

    def test_nothing_for_an_empty_query(self):
        self.assertEqual(N.find(SEARCH, "  "), [])


class GeoPageNames(unittest.TestCase):
    def site(self, doc=SEARCH):
        d = tempfile.mkdtemp()
        (Path(d) / "data" / "catalog").mkdir(parents=True)
        if doc is not None:
            (Path(d) / "data" / "catalog" / "search.json").write_text(json.dumps(doc), encoding="utf-8")
        return d

    def objs(self):
        return [[33459, "EUTE HOT BIRD 13C (HB 9)"], [27508, "EUTE 12 WEST A (AB 1)"], [99999, "OBJ 99999"]]

    def test_other_names_from_the_search_index(self):
        got = G.catalog_names(self.site(), self.objs())
        self.assertEqual(sorted(got), [27508, 33459])
        self.assertIn("Eutelsat 12 West G", got[33459])
        self.assertNotIn("EUTE HOT BIRD 13C (HB 9)", got[33459])

    def test_no_index_no_names(self):
        self.assertEqual(G.catalog_names(self.site(None), self.objs()), {})

    def test_name_positions_against_the_measured_longitude(self):
        region = {"object_cols": ["norad", "name"], "objects": [[33459, "x"], [27508, "y"], [99999, "z"]]}
        lons = {33459: -50.32, 27508: -40.85}
        old = (G.satrec, G.earth_fixed)
        G.satrec = lambda r: r["norad"]
        G.earth_fixed = lambda s, t: (lons[s], 0.0, 0.0) if s in lons else None
        try:
            other = G.catalog_names(self.site(), self.objs())
            block = G.name_positions(region, self.objs(), other, datetime(2026, 11, 25, 18, 0))
        finally:
            G.satrec, G.earth_fixed = old
        rows = {(r[0], r[1]): r for r in block["rows"]}
        self.assertEqual(rows[(33459, "Eutelsat 12 West G")], [33459, "Eutelsat 12 West G", -12.0, -50.32, 38.3])
        self.assertEqual(rows[(27508, "EUTELSAT 36 WEST A")][4], 4.9)
        self.assertNotIn(99999, {r[0] for r in block["rows"]})
        self.assertEqual(block["at_utc"], "2026-11-25T18:00Z")
        self.assertEqual(block["tolerance_deg"], N.TOLERANCE_DEG)


if __name__ == "__main__":
    unittest.main()
