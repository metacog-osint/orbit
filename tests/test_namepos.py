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

    def test_named_slot_text_keeps_the_name_s_precision(self):
        self.assertEqual(N.named_txt(-12.0), "12° W")
        self.assertEqual(N.named_txt(7.5), "7.5° E")
        self.assertEqual(N.named_txt(0.0), "0°")

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
            status = {33459: {N.compact("Eutelsat 12 West G"): ("former", "2025-12-19")}}
            block = G.name_positions(region, self.objs(), other, datetime(2026, 11, 25, 18, 0), status=status)
        finally:
            G.satrec, G.earth_fixed = old
        rows = {(r[0], r[1]): r for r in block["rows"]}
        self.assertEqual(rows[(33459, "Eutelsat 12 West G")],
                         [33459, "Eutelsat 12 West G", -12.0, -50.32, 38.3, "former", "2025-12-19"])
        self.assertEqual(rows[(27508, "EUTELSAT 36 WEST A")][5:], ["", ""])
        self.assertEqual(rows[(27508, "EUTELSAT 36 WEST A")][4], 4.9)
        self.assertNotIn(99999, {r[0] for r in block["rows"]})
        self.assertEqual(block["at_utc"], "2026-11-25T18:00Z")
        self.assertEqual(block["tolerance_deg"], N.TOLERANCE_DEG)


class SlotQuery(unittest.TestCase):
    """ideas#366: a GEO slot typed as a query."""

    def test_every_slot_form(self):
        cases = {"12.5W": -12.5, "12.5° W": -12.5, "12.5 W": -12.5, "12.5°W": -12.5, "12.5º W": -12.5,
                 "12.5 deg W": -12.5, "-12.5": -12.5, "12 West": -12.0, "12 west": -12.0, "36E": 36.0, "36 East": 36.0,
                 "+36": 36.0, "36.0° E": 36.0, " 7.3W ": -7.3, "179.5E": 179.5, "179.5W": -179.5, "180W": 180.0,
                 "180E": 180.0, "-180": 180.0, "0E": 0.0, "-0": 0.0}
        for q, lon in cases.items():
            with self.subTest(q=q):
                self.assertEqual(N.parse_slot(q), lon)
        self.assertEqual(str(N.parse_slot("-0")), "0.0")   # never "-0.0"

    def test_names_numbers_and_nonsense_are_not_slots(self):
        for q in ("Intelsat 37e", "Astra 2E", "INTELSAT 37E (IS-37E)", "Eutelsat 12 West G", "12WG", "33459", "12.5",
                  "36", "1998-067A", "181W", "-181", "12.5 N", "W12.5", "", None):
            with self.subTest(q=q):
                self.assertIsNone(N.parse_slot(q))

    def test_the_page_scripts_read_slots_as_python_does(self):
        # globe.js and search.js carry the same two patterns; run them here as Python patterns
        import re
        pats = None
        for f in ("site_src/geo/globe.js", "site_src/search.js"):
            src = (ROOT / f).read_text(encoding="utf-8")
            got = re.findall(r"/(\^\\s\*\((?:\\d|\[\+-\]).*?\$)/(i?)\.exec", src)
            self.assertEqual(len(got), 2, f)
            if pats is None:
                pats = got
            self.assertEqual(got, pats, f)

        def js(q):
            m = re.match(pats[0][0], q, re.I)
            if m:
                lon = (-1 if m[2][0].lower() == "w" else 1) * float(m[1])
            else:
                m = re.match(pats[1][0], q)
                if not m:
                    return None
                lon = float(re.sub(r"\s", "", m[1]))
            return None if abs(lon) > 180 else 180.0 if lon == -180 else lon + 0.0
        for q in ("12.5W", "12.5° W", "12.5 W", "-12.5", "12 West", "36E", "179.5E", "179.5W", "180W", "Intelsat 37e",
                  "Astra 2E", "33459", "12.5", "+ 36", "181E"):
            with self.subTest(q=q):
                self.assertEqual(js(q), N.parse_slot(q))


def obj(norad, name, lon, names=(), region="zone", drift=0.0, active=True, gone=False):
    return {"norad": norad, "name": name, "names": list(names), "lon": lon, "region": region, "drift": drift,
            "active": active, "gone": gone}


class AtSlot(unittest.TestCase):
    OBJS = [obj(42075, "WGS 9 (USA 275)", -12.02),
            obj(61994, "INTELSAT 33E DEB", -12.49, region="zone", drift=0.78, active=False),
            obj(33459, "EUTE HOT BIRD 13C (HB 9)", -50.30, ["Eutelsat 12 West G", "Eutelsat 50 West A", "Hot Bird 13C"]),
            obj(26927, "EUTE 12 WEST B", -40.4, ["EUTELSAT 12 WEST B"], region="graveyard", drift=-3.9, active=False),
            obj(11111, "EUTELSAT 12 WEST Z", None, gone=True, active=False),
            obj(41748, "INTELSAT 37E (IS-37E)", 37.0, ["IS-37E"]),
            obj(39613, "EXPRESS AT2", 55.99, ["EUTELSAT 140A"]),
            obj(50001, "EAST SIDE", 179.8), obj(50002, "WEST SIDE", -179.9), obj(50003, "FAR WEST", -179.0),
            obj(50004, "AT 179.5 W", -179.5)]

    def test_there_named_and_former(self):
        r = N.at_slot(self.OBJS, -12.5)
        self.assertEqual([o["norad"] for o in r["there"]], [61994, 42075])   # nearest first
        self.assertEqual(r["there"][1]["apart_deg"], 0.48)
        named = {o["norad"]: o for o in r["named"]}
        self.assertEqual(sorted(named), [11111, 26927, 33459])
        self.assertEqual(named[33459]["slot_names"], ["Eutelsat 12 West G"])     # not "50 West A", not "Hot Bird 13C"
        self.assertFalse(named[33459]["there_now"])
        self.assertIsNone(named[11111]["lon"])
        self.assertEqual(r["window"], N.WINDOW_DEG)
        self.assertEqual(r["named_tol"], N.TOLERANCE_DEG)

    def test_named_slots_match_within_a_degree(self):
        # "12 West" names a 12.5 W satellite: half a degree, inside the 1 degree tolerance; 2 degrees is not
        self.assertIn(33459, [o["norad"] for o in N.at_slot(self.OBJS, -11.5)["named"]])
        self.assertNotIn(33459, [o["norad"] for o in N.at_slot(self.OBJS, -14.0)["named"]])

    def test_series_letters_are_not_named_for_a_slot(self):
        r = N.at_slot(self.OBJS, 37.0)
        self.assertEqual([o["norad"] for o in r["there"]], [41748])
        self.assertEqual(r["named"], [])                                     # "Intelsat 37E" is a series name

    def test_across_the_antimeridian(self):
        # 179.5 E and 179.5 W are 1 degree apart, the short way across 180
        east = N.at_slot(self.OBJS, N.parse_slot("179.5E"))
        self.assertEqual([(o["norad"], o["apart_deg"]) for o in east["there"]], [(50001, 0.3)])
        self.assertIn(50004, [o["norad"] for o in N.at_slot(self.OBJS, N.parse_slot("179.5E"), window=1.0)["there"]])
        west = N.at_slot(self.OBJS, N.parse_slot("179.5W"))
        self.assertEqual([o["norad"] for o in west["there"]], [50004, 50002, 50003])   # 0.0, 0.4, 0.5
        across = N.at_slot(self.OBJS, N.parse_slot("179.9E"))
        self.assertEqual([o["norad"] for o in across["there"]], [50001, 50002])        # 0.1 east, 0.2 across

    def test_window(self):
        self.assertEqual([o["norad"] for o in N.at_slot(self.OBJS, 56.5, window=0.6)["there"]], [39613])
        self.assertEqual(N.at_slot(self.OBJS, 56.5)["there"], [])

    def test_held_stays(self):
        held = [[42075, "2026-07-01", "2026-11-25", -12.01, -12.06, -11.95],
                [33459, "2026-07-01", "2026-11-25", -50.35, -50.4, -50.3],
                [26927, "2026-07-01", "2026-08-02", -12.52, -12.6, -12.45]]
        r = N.at_slot(self.OBJS, -12.5, held=held)
        self.assertEqual([(s["norad"], s["to"]) for s in r["held"]], [(42075, "2026-11-25"), (26927, "2026-08-02")])
        self.assertEqual(r["held"][1]["name"], "EUTE 12 WEST B")


KEPT_N = 360.98564736629 / 360.0      # no drift


def sets(norad, first_day, days, lon, n=KEPT_N):
    from datetime import timedelta
    d0 = datetime.fromisoformat(first_day + "T06:00:00")
    return [{"norad": norad, "epoch": (d0 + timedelta(days=k)).strftime("%Y-%m-%dT%H:%M:%S"), "n": n, "lon": lon}
            for k in range(days)]


class HeldStays(unittest.TestCase):
    """geo_page.held_stays: who held a longitude, from the element history (SGP4 stubbed: each set's lon)."""

    def run_stays(self, elsets, payloads, first="2026-07-01", last="2026-08-20"):
        old = (G.satrec, G.earth_fixed)
        G.satrec = lambda s: s
        G.earth_fixed = lambda s, t: (s["lon"], 0.0, 0.0)
        try:
            return G.held_stays(elsets, payloads, datetime.fromisoformat(first + "T12:00"), datetime.fromisoformat(last + "T12:00"))
        finally:
            G.satrec, G.earth_fixed = old

    def test_a_move_ends_one_stay_and_starts_another(self):
        el = {1: sets(1, "2026-07-01", 20, -12.5) + sets(1, "2026-07-21", 5, -30.0, n=1.01) + sets(1, "2026-07-26", 16, -50.3)}
        got = self.run_stays(el, {1})
        self.assertEqual(got, [[1, "2026-07-01", "2026-07-20", -12.5, -12.5, -12.5],
                               [1, "2026-07-26", "2026-08-20", -50.3, -50.3, -50.3]])   # the last set stays in force 10 days

    def test_stale_sets_short_stays_and_other_objects(self):
        el = {2: sets(2, "2026-07-01", 1, 36.0),                 # one set: in force for 10 days, then stale
              3: sets(3, "2026-07-01", 5, 7.0),                  # 5 days + 10: kept
              4: sets(4, "2026-07-01", 30, 100.0)}               # not a payload
        got = self.run_stays(el, {2, 3}, last="2026-07-31")
        self.assertEqual([r[:3] for r in got], [[2, "2026-07-01", "2026-07-11"], [3, "2026-07-01", "2026-07-15"]])

    def test_a_slow_wander_splits_at_half_a_degree(self):
        el = {5: [dict(s, lon=10.0 + 0.04 * k) for k, s in enumerate(sets(5, "2026-07-01", 40, 0))]}
        got = self.run_stays(el, {5}, last="2026-08-09")
        self.assertEqual([r[1] for r in got][:2], ["2026-07-01", "2026-07-14"])
        self.assertTrue(all(r[5] - r[4] <= G.HOLD_DEG + 1e-9 for r in got))

    def test_across_the_antimeridian(self):
        el = {6: [dict(s, lon=(179.9 if k % 2 else -179.9)) for k, s in enumerate(sets(6, "2026-07-01", 10, 0))]}
        got = self.run_stays(el, {6}, last="2026-07-10")
        self.assertEqual(len(got), 1)
        self.assertAlmostEqual(abs(got[0][3]), 180.0, places=1)


class FindSlotCli(unittest.TestCase):
    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("orbit_cli_slot", ROOT / "tools" / "orbit.py")
        self.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cli)
        cols = ["norad", "name", "cospar", "type", "owner", "launch", "rcs", "region", "active", "epoch", "n", "e", "i",
                "raan", "argp", "M", "bstar", "lon"]
        row = lambda k, name, region, act, n, lon: [k, name, "", "PAYLOAD", "", "", "", region, act, "", n, 0, 0, 0, 0, 0, 0, lon]  # noqa: E731
        self.globe = {"built_utc": "2026-11-25T20:15Z", "cols": cols,
                      "objects": [row(42075, "WGS 9 (USA 275)", "zone", 1, KEPT_N, -12.02),
                                  row(33459, "EUTE HOT BIRD 13C (HB 9)", "zone", 1, KEPT_N, -50.3),
                                  row(27508, "EUTE 12 WEST A (AB 1)", "graveyard", 0, 0.99, -41.2)],
                      "names": {}, "held": {"from": "2026-07-01", "to": "2026-11-25", "hold_deg": 0.5, "min_days": 7,
                                            "rows": [[42075, "2026-07-01", "2026-11-25", -12.01, -12.06, -11.95]]}}

    def run_find(self, q, **kw):
        import contextlib
        import io
        urls = {self.cli.SEARCH_URL: json.dumps(SEARCH).encode(), self.cli.GEO_URL: json.dumps(self.globe).encode()}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = self.cli.find_name(q, getter=lambda u: urls[u], **kw)
        return code, buf.getvalue()

    def test_slot_lists_there_named_and_held(self):
        code, out = self.run_find("12.5W")
        self.assertEqual(code, 0)
        there, named, held = out.split("There now")[1].split("Named for it")[0], out.split("Named for it")[1].split("Held it")[0], out.split("Held it")[1]
        self.assertIn("42075", there)
        self.assertNotIn("33459", there)
        self.assertIn("33459", named)
        self.assertIn("Eutelsat 12 West G -> now at 50.3° W", named)
        self.assertIn("27508", named)
        self.assertIn("graveyard", named)
        self.assertIn("2026-07-01 to now, at 12.0° W", held)
        self.assertNotIn("whole degree", out)               # a decimal query needs no rounding note

    def test_whole_degree_query_says_names_round(self):
        code, out = self.run_find("12 West")
        self.assertIn("widen with --window 1", out)

    def test_window_and_names_still_work(self):
        _, out = self.run_find("50 West", window=1.0)
        self.assertIn("33459", out.split("There now")[1].split("Named for it")[0])
        code, out = self.run_find("12 West G")             # a name, not a slot
        self.assertEqual(code, 0)
        self.assertIn("33459", out)
        self.assertNotIn("There now", out)


if __name__ == "__main__":
    unittest.main()
