"""WMO OSCAR/Space: the reader, the link proposer and the reviewed link file (orbit/oscar.py, orbit/oscarlinks.py).

Fixtures, rows unchanged:
- oscar_satellites_20261118.json: 14 satellites cut unchanged from WMO OSCAR/Space's API
  (space.oscar.wmo.int/api/v1/satellites?page=N&sort=id&order=asc, read 18 Nov 2026), in page 1's wrapper
  (`_links` and `page` of page 1 as received). Credit: WMO OSCAR/Space, courtesy of the World Meteorological
  Organization ("may be used and redistributed freely", space.oscar.wmo.int/pages/disclaimer).
- celestrak_satcat_oscar_20261116.csv: header and every payload row launched within a day of those satellites'
  launch dates, plus ISS (25544) and Intelsat 40e's neighbour rows if present, cut unchanged from CelesTrak's
  SATCAT file of 16 Nov 2026 20:34 UTC (read 17 Nov 2026). CelesTrak SATCAT (T.S. Kelso, celestrak.org).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from orbit import aliases, catsources, oscar, oscarlinks  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
DOC = json.loads((FIX / "oscar_satellites_20261118.json").read_text(encoding="utf-8"))
SATS = DOC["_embedded"]["satellites"]
BY = {s["slug"]: s for s in SATS}
ROWS = catsources.ct_parse((FIX / "celestrak_satcat_oscar_20261116.csv").read_bytes())


def proposals():
    return {p["slug"]: p for p in oscar.propose(SATS, ROWS, statuses=("Operational", "Mission concept"))}


class Values(unittest.TestCase):
    def test_launch_dates(self):
        self.assertEqual(oscar.launch_day(BY["noaa_20"]), ("2017-11-18", "day"))
        self.assertEqual(oscar.launch_day(BY["ews_g2_formerly_goes_15"]), ("2023-12", "month"))
        self.assertEqual(oscar.launch_day(BY["3d_winds"]), (None, "none"))      # "TBD"
        self.assertEqual(oscar.launch_day(BY["umbra"])[1], "none")              # "≥2021"

    def test_heights_and_longitudes(self):
        self.assertEqual(oscar.altitude_km(BY["goes_18"]), 35786.0)
        self.assertEqual(oscar.altitude_km(BY["ace"]), 1.5e6)                   # "1.5e+06"
        self.assertIsNone(oscar.altitude_km(BY["3d_winds"]))                    # "TBD"
        self.assertEqual(oscar.longitude_deg(BY["goes_18"]), -137.0)
        self.assertIsNone(oscar.longitude_deg(BY["ace"]))

    def test_orbit_classes(self):
        self.assertEqual(oscar.orbit_class(BY["goes_18"]), "geo")
        self.assertEqual(oscar.orbit_class(BY["noaa_20"]), "sso")
        self.assertEqual(oscar.orbit_class(BY["ace"]), "l1")
        self.assertEqual(oscar.orbit_class(BY["iss_gedi"]), "drift")

    def test_names_normalise_spellings_not_meaning(self):
        self.assertEqual(oscar.name_agrees(BY["electro_l_n2"], ["ELEKTRO-L 2"]), "ELEKTRO-L 2")
        self.assertEqual(oscar.name_agrees(BY["noaa_20"], ["NOAA 20 (JPSS-1)"]), "NOAA 20 (JPSS-1)")
        self.assertIsNone(oscar.name_agrees(BY["noaa_20"], ["NOAA 21 (JPSS-2)"]))
        self.assertIsNone(oscar.name_agrees(BY["skysat_19"], ["SKYSAT-C19"]))   # stays for a person


class Propose(unittest.TestCase):
    def test_date_and_orbit_leave_two(self):
        p = proposals()["noaa_20"]
        # six payloads on 2017-073; four cubesats ruled out by orbit; RadFxSat (421 x 621 km) still fits 824 km
        self.assertEqual((p["payloads_in_window"], p["dropped_by_orbit"], p["outcome"]), (6, 4, "several"))
        c = p["candidates"][0]  # the candidate whose name equals OSCAR's sorts first
        self.assertEqual((c["norad"], c["intldes"], c["days_off"]), (43013, "2017-073A", 0))
        self.assertTrue(c["orbit_checked"])
        self.assertEqual(c["name_agrees"], "NOAA 20 (JPSS-1)")
        self.assertEqual([x["norad"] for x in p["candidates"][1:]], [43017])

    def test_geo_and_deep_space(self):
        P = proposals()
        self.assertEqual([c["norad"] for c in P["goes_18"]["candidates"]], [51850])
        self.assertEqual([c["norad"] for c in P["electro_l_n2"]["candidates"]], [41105])
        self.assertEqual([c["norad"] for c in P["ace"]["candidates"]], [24912])
        # IMAP, SWFO-L1 and Carruthers share a launch and CelesTrak gives each orbit centre SU: three fit
        self.assertEqual(P["carruthers"]["outcome"], "several")
        self.assertEqual([c["norad"] for c in P["carruthers"]["candidates"] if c["name_agrees"]], [65727])

    def test_names_never_choose(self):
        """A hosted instrument fits the cargo ship that carried it: the proposer says so, a person decides."""
        p = proposals()["iss_gedi"]
        self.assertTrue(all(c["name_agrees"] is None for c in p["candidates"]))
        self.assertIn("DRAGON CRS-16", [c["name"] for c in p["candidates"]])
        self.assertNotIn(25544, [c["norad"] for c in p["candidates"]])  # ISS launched 1998: not in the window

    def test_constellation_member_and_month_dates(self):
        P = proposals()
        self.assertEqual(P["rcm_2"]["outcome"], "several")  # three RCM satellites on one launch
        self.assertEqual([c["norad"] for c in P["rcm_2"]["candidates"] if c["name_agrees"]], [44324])
        self.assertEqual(P["ews_g2_formerly_goes_15"]["launch_precision"], "month")  # "Dec 2023": not its launch
        self.assertEqual(P["3d_winds"]["outcome"], "none")

    def test_evidence_lines(self):
        p = proposals()["noaa_20"]
        ev = oscar.evidence(p, p["candidates"][0])
        self.assertTrue(ev[0].startswith("OSCAR launch date 18 Nov 2017; CelesTrak launches 2017-073A on 2017-11-18"))
        self.assertIn("824 km", ev[1])
        self.assertIn("equal after normalising: 'NOAA 20 (JPSS-1)'", ev[3])


class Read(unittest.TestCase):
    def pages(self):
        a = dict(DOC, page={"elementsPerPage": 30, "totalElements": 14, "totalPages": 2, "number": 1},
                 _embedded={"satellites": SATS[:7]})
        b = dict(DOC, page={"elementsPerPage": 30, "totalElements": 14, "totalPages": 2, "number": 2},
                 _embedded={"satellites": SATS[7:]})
        return {oscar.PAGE_URL.format(n=1): json.dumps(a).encode(), oscar.PAGE_URL.format(n=2): json.dumps(b).encode()}

    def test_reads_every_page_once_and_resumes(self):
        bodies, asked, slept = self.pages(), [], []

        def get(source, url, accept="*/*"):
            self.assertEqual(source, oscar.SOURCE)
            asked.append(url)
            return bodies[url]
        with tempfile.TemporaryDirectory() as tmp:
            out = oscar.read(Path(tmp), "t", get=get, sleep=slept.append)
            self.assertEqual(len(asked), 2)
            self.assertEqual(slept, [oscar.PAUSE])  # a pause between pages, none before the first
            self.assertEqual(oscar.load(out)["total"], 14)
            oscar.read(Path(tmp), "t", get=get, sleep=slept.append)
            self.assertEqual(len(asked), 2)  # nothing asked again

    def test_refusal_stops_the_read(self):
        def get(source, url, accept="*/*"):
            raise catsources.Refused(source, url, 503)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(catsources.Refused):
                oscar.read(Path(tmp), "t", get=get, sleep=lambda s: None)

    def test_load_refuses_a_short_read(self):
        bodies = self.pages()
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "page-01.json").write_bytes(bodies[oscar.PAGE_URL.format(n=1)])
            with self.assertRaises(ValueError):
                oscar.load(d)


ENTRY = """- slug: noaa_20
  norad: 43013
  relation: same
  proposal: single-fit
  oscar_id: 1
  read: 2026-11-18
  evidence:
    - "one line"
  proposed_by: oscar-propose
  proposed: 2026-11-18
"""


class Links(unittest.TestCase):
    def load(self, text):
        return oscarlinks.validate(aliases.parse(text))

    def test_real_file_reads_and_nothing_is_reviewed_yet(self):
        live = oscarlinks.load()
        self.assertGreater(len(live), 200)
        self.assertEqual(oscarlinks.reviewed(live), [])  # 18 Nov 2026: every entry waits for a person
        self.assertTrue(all(e["proposed_by"] == "oscar-propose" for e in live))

    def test_only_reviewed_entries_join(self):
        a = self.load(ENTRY)
        self.assertEqual(oscarlinks.reviewed(a), [])
        b = self.load(ENTRY + "  reviewed_by: Tom\n  reviewed: 2026-11-19\n")
        self.assertEqual(len(oscarlinks.reviewed(b)), 1)
        with self.assertRaises(oscarlinks.LinkError):
            self.load(ENTRY + "  reviewed_by: Tom\n")  # a review needs its date

    def test_refusals(self):
        for bad in (ENTRY.replace("relation: same", "relation: guess"),
                    ENTRY.replace("  norad: 43013\n", ""),
                    ENTRY.replace("  norad: 43013\n", "  norad: 43013\n  members: [1, 2]\n"),
                    ENTRY.replace("proposal: single-fit", "proposal: name"),
                    ENTRY + "\n" + ENTRY,                                       # slug twice
                    ENTRY + "\n" + ENTRY.replace("slug: noaa_20", "slug: other"),  # one number, two satellites
                    ENTRY.replace('    - "one line"\n', "")):
            with self.assertRaises(aliases.AliasError, msg=bad):
                self.load(bad)

    def test_members_hosted_and_withdrawn(self):
        text = (ENTRY.replace("  norad: 43013\n", "  members: [43013, 54234]\n") + "\n"
                + ENTRY.replace("slug: noaa_20", "slug: iss_gedi").replace("norad: 43013", "norad: 25544")
                .replace("relation: same", "relation: hosted") + "\n"
                + ENTRY.replace("slug: noaa_20", "slug: iss_ecostress").replace("norad: 43013", "norad: 25544")
                .replace("relation: same", "relation: hosted") + "\n"
                + ENTRY.replace("slug: noaa_20", "slug: old").replace("norad: 43013", "norad: 54234")
                + "  withdrawn: 2026-11-19\n  reason: \"wrong number\"\n")
        live = self.load(text)
        self.assertEqual([e["slug"] for e in live], ["noaa_20", "iss_gedi", "iss_ecostress"])
        self.assertEqual(oscarlinks.numbers(live[0]), [43013, 54234])

    def test_written_entries_read_back(self):
        t = oscarlinks.entry_text("noaa_20", [43013], "same", "single-fit", 1, 'NOAA-20 "x"', "2026-11-18",
                                  ['a "quoted" line'], "2026-11-18")
        e = self.load(t)[0]
        self.assertEqual((e["acronym"], e["evidence"]), ('NOAA-20 "x"', ['a "quoted" line']))


if __name__ == "__main__":
    unittest.main()
