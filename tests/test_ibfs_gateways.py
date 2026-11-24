"""Tests for tools/ibfs_gateways.py on synthetic IBFS-shaped tables (no real records)."""
import json
import pathlib
import sys
import tempfile
import unittest
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import ibfs_gateways as g  # noqa: E402

END = "|^|\r\n"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def dt(y, m, d):
    return "%s %2d %d 12:00:00:000AM" % (MONTHS[m - 1], d, y)


def main_row(key, call, fn, status="A/C", grant=None, expire=None, surrender=None, upd=None, cls="FES",
             addr="9", sub="SES", text=""):
    f = [""] * 70
    f[0], f[1], f[2], f[3], f[4], f[5] = str(key), "2", call, fn, sub, status
    f[12] = dt(*grant) if grant else ""
    f[15] = dt(*surrender) if surrender else ""
    f[17] = dt(*expire) if expire else ""
    f[18] = dt(*upd) if upd else ""
    f[25], f[35], f[40], f[41] = "LIC", cls, text, str(addr)
    return "|".join(f) + "|"


def site_row(skey, fkey, lat, lon, nad="NA", city="TESTVILLE"):
    f = [""] * 32
    f[0], f[1], f[2], f[7], f[9] = str(skey), str(fkey), "1", city, "ZZ"
    f[13:17] = [str(lat[0]), str(lat[1]), str(lat[2]), lat[3]]
    f[17:21] = [str(lon[0]), str(lon[1]), str(lon[2]), lon[3]]
    f[21] = nad
    return "|".join(f) + "|"


def write(d, name, rows):
    (d / name).write_bytes("".join(r + END for r in rows).encode("cp1252"))


class Primitives(unittest.TestCase):
    def test_dms_hemispheres(self):
        self.assertAlmostEqual(g.dms(33, 36, 16.0, "N"), 33.604444, 5)
        self.assertAlmostEqual(g.dms(105, 44, 17.0, "W"), -105.738056, 5)
        self.assertAlmostEqual(g.dms(41, 0, 0, "S"), -41.0)
        self.assertIsNone(g.dms(0, 0, 0.0, ""))
        self.assertIsNone(g.dms(10, 0, 0, ""))

    def test_dates(self):
        self.assertEqual(g.parse_dt("Oct 22 1979 12:00:00:000AM"), date(1979, 10, 22))
        self.assertEqual(g.parse_dt("Jun  4 2009  8:30:43:366AM"), date(2009, 6, 4))
        self.assertIsNone(g.parse_dt(""))
        self.assertIsNone(g.parse_dt("garbage"))

    def test_names_and_orbits(self):
        self.assertEqual(g.norm_name("viasat-3 (S2917/3050"), "VIASAT-3")
        self.assertEqual(g.norm_name("SPACEX  (S2983/3018)"), "SPACEX")
        self.assertNotEqual(g.norm_name("VIASAT-2"), g.norm_name("VIASAT 2"))
        self.assertEqual(g.norm_orbit("69.9 W.L.")[0], -69.9)
        self.assertEqual(g.norm_orbit("85.15 W.L")[0], -85.15)
        self.assertEqual(g.norm_orbit("179.6 E.L.")[0], 179.6)
        self.assertIsNone(g.norm_orbit("NGSO")[0])
        self.assertEqual(g.sat_kind("PERMITTED LIST", ""), "permitted_list")
        self.assertEqual(g.sat_kind("ALSAT", ""), "alsat")
        self.assertEqual(g.sat_kind("ALSAT 2", "98 E"), "named")
        self.assertEqual(g.sat_kind("SPACEX", "NGSO"), "ngso")

    def test_bands(self):
        self.assertEqual(g.band_of("00011700.000", "00012200.000"), {"Ku"})
        self.assertEqual(g.band_of("00027500.000", "00030000.000"), {"Ka"})
        self.assertEqual(g.band_of("x", "y"), set())

    def test_classify(self):
        base = dict(date_surrender=None, date_deny=None, date_dismiss=None, date_grant=date(2020, 1, 1),
                    date_expire=date(2030, 1, 1), last_action="GRA", status_code="A/C")
        asof = date(2026, 11, 24)
        self.assertEqual(g.classify(base, asof)[0], "current")
        self.assertEqual(g.classify(dict(base, date_expire=date(2026, 1, 1)), asof)[0], "expired")
        self.assertEqual(g.classify(dict(base, date_surrender=date(2024, 1, 1)), asof)[0], "surrendered")
        self.assertEqual(g.classify(dict(base, date_dismiss=date(2024, 1, 1)), asof)[0], "denied_dismissed")
        self.assertEqual(g.classify(dict(base, date_grant=None), asof)[0], "not_granted")
        self.assertEqual(g.classify(dict(base, date_expire=None), asof)[0], "granted_no_expiry")
        self.assertEqual(g.classify(dict(base, date_expire=None), asof, True)[0], "current")


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.tmp.name)
        self.d = d
        # embedded CR/LF and a stray "|" in a text field must not split the record
        text = "line one\r\nline two | pipe"
        write(d, "main.dat", [
            main_row(1, "E100", "SESLIC2020010100001", grant=(2020, 1, 1), expire=(2030, 1, 1), upd=(2026, 3, 2),
                     text=text),
            main_row(2, "E200", "SESLIC2010010100001", grant=(2010, 1, 1), expire=(2020, 1, 1)),
            main_row(3, "E300", "SESLIC2015010100001", grant=(2015, 1, 1), expire=(2035, 1, 1),
                     surrender=(2022, 5, 5)),
            main_row(4, "E100", "SESMOD2024010100001", grant=(2024, 1, 1), expire=(2034, 1, 1), upd=(2026, 7, 1)),
            main_row(5, "E500", "SESLIC2021010100001", grant=(2021, 1, 1), expire=(2031, 1, 1)),
            main_row(6, "", "SATLIC2021010100001", sub="SAT", grant=(2021, 1, 1), expire=(2031, 1, 1)),
            main_row(7, "E700", "SESLIC2022010100001", grant=(2022, 1, 1), expire=(2032, 1, 1)),
        ])
        write(d, "address.dat", ["9|X1|Test Licensee LLC||1 Main St||Town|ZZ|00000|USA|ATC||0|N"])
        write(d, "status_code.dat", ["A/C  |Action Complete|Y|Dec 31 9999 12:00:00:000AM"])
        write(d, "class.dat", ["FES|Fixed Earth Stations|Dec 31 9999 12:00:00:000AM"])
        write(d, "site.dat", [
            site_row(11, 1, (40, 30, 0.0, "N"), (100, 15, 0.0, "W"), nad="83"),
            site_row(12, 2, (30, 0, 0.0, "N"), (90, 0, 0.0, "W")),
            site_row(13, 3, (30, 0, 0.0, "N"), (91, 0, 0.0, "W")),
            site_row(14, 4, (40, 30, 0.0, "N"), (100, 15, 0.0, "W"), nad="83"),   # same place as site 11
            site_row(15, 5, (33, 30, 0.0, "S"), (151, 0, 0.0, "E")),
            site_row(17, 7, (0, 0, 0.0, ""), (0, 0, 0.0, "")),                     # placeholder coordinates
        ])
        write(d, "space_sta.dat", [
            "100|VIASAT-2 (S2900)|VIASAT-2|69.9 W.L.|v|Dec 31 9999 12:00:00:000AM|W",
            "100|VIASAT-2 (S2900)|VIASAT-2|69.9 W.L.|v|Dec 31 9999 12:00:00:000AM|W",     # table repeats rows
            "101|SPACEX|SPACEX|NGSO|v|Dec 31 9999 12:00:00:000AM|",
            "238|PERMITTED LIST| | |Permitted Space Station List|Dec 31 2099 12:00:00:000AM| ",
        ])
        write(d, "ptcomm.dat", ["1|11|100", "2|12|100", "3|13|100", "4|14|101", "5|15|238", "7|17|238", "8|99|100"])
        write(d, "anten.dat", ["21|1         |11|2.4|0|0|0"])
        write(d, "freq.dat", ["31|21|V|||36MOF3F|00011700.00000000|00012200.00000000"])

    def tearDown(self):
        self.tmp.cleanup()

    def run_build(self, **kw):
        return g.build(self.d, date(2026, 11, 24), date(2026, 7, 15), **kw)

    def test_counts_and_groups(self):
        out = self.run_build()
        h = out["header"]
        self.assertEqual(h["kind"], "published")
        self.assertEqual(h["credit"], "Federal Communications Commission")
        self.assertIn("IBFS.zip", h["source"])
        self.assertEqual(h["file_date"], "2026-07-15")
        self.assertEqual(h["newest_date_last_update_ses"], "2026-07-01")
        c = h["counts"]
        self.assertEqual(c["ses_filings"], 6)               # the SAT row is not an earth station
        self.assertEqual(c["by_status_class"], {"current": 4, "expired": 1, "surrendered": 1})
        self.assertEqual(c["current_sites_merged_duplicates"], 1)   # E100 licence + modification, one place
        self.assertEqual(c["sites_without_coordinates"], 1)
        sats = {s["id"]: s for s in out["satellites"]}
        self.assertEqual(set(sats), {"VIASAT-2@69.9 W.L.", "SPACEX@NGSO", "PERMITTED LIST"})
        self.assertEqual(sats["VIASAT-2@69.9 W.L."]["n_sites"], 1)   # E200 expired, E300 surrendered
        self.assertEqual(sats["VIASAT-2@69.9 W.L."]["orbit_lon_deg_east"], -69.9)
        self.assertEqual(sats["SPACEX@NGSO"]["kind"], "ngso")
        self.assertEqual(sats["PERMITTED LIST"]["kind"], "permitted_list")
        self.assertEqual(sats["PERMITTED LIST"]["n_sites"], 2)

    def test_feature_properties(self):
        out = self.run_build()
        via = [s for s in out["satellites"] if s["id"].startswith("VIASAT")][0]
        self.assertEqual(via["type"], "FeatureCollection")
        f = via["features"][0]
        p = f["properties"]
        self.assertEqual(f["geometry"], {"type": "Point", "coordinates": [-100.25, 40.5]})
        self.assertEqual(p["callsign"], "E100")
        self.assertEqual(p["file_numbers"], ["SESLIC2020010100001", "SESMOD2024010100001"])
        self.assertEqual(p["licensee"], "Test Licensee LLC")
        self.assertEqual(p["datum"], "83")
        self.assertEqual((p["lat_hemi"], p["long_hemi"]), ("N", "W"))
        self.assertEqual(p["antenna_diameters_m"], [2.4])
        self.assertEqual(p["bands"], ["Ku"])
        raws = {s["raw_name"] for s in p["satellites"]}
        self.assertEqual(raws, {"VIASAT-2 (S2900)", "SPACEX"})   # the merged filings name both
        self.assertEqual(p["date_expire"], "2034-01-01")           # newest filing's dates win

    def test_southern_hemisphere_and_no_coords(self):
        out = self.run_build()
        pl = [s for s in out["satellites"] if s["id"] == "PERMITTED LIST"][0]
        geoms = [f["geometry"]["coordinates"] for f in pl["features"] if f["geometry"]]
        self.assertEqual(geoms, [[151.0, -33.5]])
        self.assertEqual(sum(1 for f in pl["features"] if f["geometry"] is None), 1)

    def test_json_roundtrip_and_cli(self):
        out = self.d / "out" / "gateways.json"
        rc = g.main(["build", "--ibfs", str(self.d), "--out", str(out), "--as-of", "2026-11-24",
                     "--zip-date", "2026-07-15"])
        self.assertEqual(rc, 0)
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(data["header"]["kind"], "published")
        self.assertEqual(data["header"]["days_stale_at_reference"], (date(2026, 11, 24) - date(2026, 7, 1)).days)

    def test_record_with_embedded_crlf_is_one_record(self):
        rows = list(g.read_table(self.d / "main.dat", ncols=53))
        self.assertEqual(len(rows), 7)
        self.assertIn("line one\r\nline two", rows[0][40])


if __name__ == "__main__":
    unittest.main()
