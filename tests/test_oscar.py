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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from orbit import aliases, catalog, catsources, oscar, oscarlinks  # noqa: E402

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

    def test_real_file_reads_and_the_first_review_is_in(self):
        # Reviewed 18 Nov 2026: all 285 accepted, none withdrawn. The public file names a role, not a person.
        live = oscarlinks.load()
        self.assertEqual(len(live), 285)
        self.assertEqual(len(oscarlinks.reviewed(live)), 285)
        self.assertTrue(all(e["reviewed_by"] == "tic-analyst" and e["reviewed"] == "2026-11-18" for e in live))
        self.assertTrue(all(e["proposed_by"] == "oscar-propose" for e in live))

    def test_only_reviewed_entries_join(self):
        a = self.load(ENTRY)
        self.assertEqual(oscarlinks.reviewed(a), [])
        b = self.load(ENTRY + "  reviewed_by: tic-analyst\n  reviewed: 2026-11-19\n")
        self.assertEqual(len(oscarlinks.reviewed(b)), 1)
        with self.assertRaises(oscarlinks.LinkError):
            self.load(ENTRY + "  reviewed_by: tic-analyst\n")  # a review needs its date

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




LINK = """- slug: {slug}
  {num}
  relation: {rel}
  proposal: single-fit
  oscar_id: 1
  read: 2026-11-18
  evidence:
    - "one line"
  proposed_by: oscar-propose
  proposed: 2026-11-18
  reviewed_by: "tic-analyst"
  reviewed: 2026-11-18
"""


class Join(unittest.TestCase):
    """The join (catalog.add_oscar) and the weekly read (oscar.pull), on the 14 real satellites of the fixture."""

    def numbered(self):
        out = {}
        for k, name, ops in (("43013", "NOAA 20", "+"), ("25544", "ISS (ZARYA)", "+"), ("54234", "CYGNSS 1", "-"),
                             ("99999", "OTHER", "+")):
            e = {"norad": int(k), "jcat": None, "type": "payload", **{f: [] for f in catalog.FIELDS},
                 "only_in": ["celestrak-satcat"]}
            e["names"].append(catalog.rec(name, "celestrak-satcat", "2026-11-20", "attributed", ref=k))
            e["ops_status"].append(catalog.rec(ops, "celestrak-satcat", "2026-11-20", cmp="active" if ops == "+"
                                               else "inactive", ref=k))
            catalog.finish(e)
            out[k] = e
        return out

    def links(self, *entries):
        return oscarlinks.reviewed(oscarlinks.validate(aliases.parse("\n".join(entries))))

    def test_a_reviewed_same_entry_adds_operator_names_and_status(self):
        n = self.numbered()
        links = self.links(LINK.format(slug="noaa_20", num="norad: 43013", rel="same"))
        c = catalog.add_oscar(n, links, SATS, "2026-11-20")
        self.assertEqual((c["names"], c["operators"], c["status"]), (2, 1, 1))
        e = n["43013"]
        op = e["operator"][0]
        self.assertEqual((op["value"], op["basis"], op["ref"], op["source"]), ("NOAA,NASA", "declared", "noaa_20",
                                                                              oscar.SOURCE))
        self.assertEqual([r["value"] for r in e["names"] if r["source"] == oscar.SOURCE],
                         ["NOAA-20", "National Oceanic and Atmospheric Administration - 20"])
        st = [r for r in e["ops_status"] if r["source"] == oscar.SOURCE][0]
        self.assertEqual((st["value"], st["cmp"]), ("Operational", "active"))
        self.assertEqual(e["name"], "NOAA 20")           # OSCAR ranks after CelesTrak: no name is replaced
        self.assertEqual(e["disagreements"], [])         # active and active

    def test_status_disagreement_is_listed_not_resolved(self):
        n = self.numbered()
        n["43013"]["ops_status"][0] = catalog.rec("-", "celestrak-satcat", "2026-11-20", cmp="inactive", ref="43013")
        catalog.add_oscar(n, self.links(LINK.format(slug="noaa_20", num="norad: 43013", rel="same")), SATS,
                          "2026-11-20")
        d = n["43013"]["disagreements"]
        self.assertEqual([x["field"] for x in d], ["ops_status"])
        self.assertEqual(n["43013"]["ops_status"][0]["value"], "-")

    def test_unreviewed_entries_do_not_join(self):
        text = LINK.format(slug="noaa_20", num="norad: 43013", rel="same").replace(
            "  reviewed_by: \"tic-analyst\"\n  reviewed: 2026-11-18\n", "")
        self.assertEqual(self.links(text), [])

    def test_members_get_operator_and_programme_only(self):
        n = self.numbered()
        links = self.links(LINK.format(slug="noaa_20", num="members: [54234, 43013]", rel="same"))
        c = catalog.add_oscar(n, links, SATS, "2026-11-20")
        self.assertEqual((c["programs"], c["operators"], c["names"], c["status"]), (2, 2, 0, 0))
        self.assertEqual(n["54234"]["program"][0]["value"], "NOAA-20")
        self.assertEqual(len(n["54234"]["names"]), 1)
        self.assertEqual(len(n["54234"]["ops_status"]), 1)

    def test_hosted_adds_a_note_to_the_host_and_nothing_else(self):
        n = self.numbered()
        links = self.links(LINK.format(slug="iss_gedi", num="norad: 25544", rel="hosted"))
        c = catalog.add_oscar(n, links, SATS, "2026-11-20")
        self.assertEqual(c["hosted"], 1)
        e = n["25544"]
        self.assertEqual(e["hosted"][0]["value"], "ISS GEDI")
        self.assertEqual((len(e["names"]), len(e["ops_status"]), "operator" in e), (1, 1, False))

    def test_missing_number_or_slug_is_counted_never_invented(self):
        n = self.numbered()
        links = self.links(LINK.format(slug="noaa_20", num="norad: 11111", rel="same"),
                           LINK.format(slug="gone_sat", num="norad: 99999", rel="same"))
        c = catalog.add_oscar(n, links, SATS, "2026-11-20")
        self.assertEqual((c["not_in_catalog"], c["slug_not_in_read"]), ([11111], ["gone_sat"]))
        self.assertNotIn("11111", n)

    def test_nothing_of_the_review_reaches_the_catalog(self):
        n = self.numbered()
        catalog.add_oscar(n, self.links(LINK.format(slug="noaa_20", num="norad: 43013", rel="same")), SATS, "x")
        blob = json.dumps(n)
        for word in ("tic-analyst", "evidence", "reviewed", "oscar-propose"):
            self.assertNotIn(word, blob)

    def test_build_ranks_oscar_after_wikidata_and_lists_it_as_a_source(self):
        self.assertLess(catalog.RANK.index("wikidata"), catalog.RANK.index(oscar.SOURCE))
        self.assertLess(catalog.RANK.index(oscar.SOURCE), catalog.RANK.index("swf-rpo"))

    # --- the weekly read ---

    def fake(self, pages):
        calls = []

        def get(source, url, accept="*/*", timeout=120):
            calls.append(url)
            n = int(url.split("page=")[1].split("&")[0])
            a = pages[n - 1]
            if isinstance(a, Exception):
                raise a
            return a
        return get, calls

    def two_pages(self):
        a = {**DOC, "page": {"elementsPerPage": 7, "totalElements": 14, "totalPages": 2, "number": 1},
             "_embedded": {"satellites": SATS[:7]}}
        b = {**a, "page": {**a["page"], "number": 2}, "_embedded": {"satellites": SATS[7:]}}
        return [json.dumps(a).encode(), json.dumps(b).encode()]

    def test_pull_reads_every_page_stores_the_slim_list_and_waits_a_week(self):
        floor, oscar.MIN_SATS = oscar.MIN_SATS, 10
        try:
            with tempfile.TemporaryDirectory() as d:
                get, calls = self.fake(self.two_pages())
                state = {}
                now = datetime(2026, 11, 20, 23, 0, tzinfo=timezone.utc)
                n = oscar.pull(Path(d), now, state, get=get, pause=0, sleep=lambda s: None)
                self.assertEqual((n["read"], n["rows"], len(calls)), (True, 14, 2))
                got = oscar.store_load(Path(d), state)
                self.assertEqual(len(got["satellites"]), 14)
                self.assertEqual(got["read"], "2026-11-20")
                self.assertNotIn("satellite-instruments", got["satellites"][0])
                self.assertEqual(set(got["satellites"][0]), set(oscar.KEEP))
                again = oscar.pull(Path(d), now.replace(day=22), state, get=get, pause=0, sleep=lambda s: None)
                self.assertFalse(again["read"])
                self.assertEqual(len(calls), 2)
                later = oscar.pull(Path(d), now.replace(day=27, hour=18), {oscar.SOURCE: state[oscar.SOURCE]},
                                   get=self.fake(self.two_pages())[0], pause=0, sleep=lambda s: None)
                self.assertTrue(later["read"])
        finally:
            oscar.MIN_SATS = floor

    def test_a_refusal_holds_the_source_and_keeps_the_last_read(self):
        with tempfile.TemporaryDirectory() as d:
            get, calls = self.fake([catsources.Refused(oscar.SOURCE, "u", 403)])
            state = {}
            now = datetime(2026, 11, 20, 23, 0, tzinfo=timezone.utc)
            n = oscar.pull(Path(d), now, state, get=get, pause=0, sleep=lambda s: None)
            self.assertEqual(n["refused"], 403)
            self.assertIn("hold", state[oscar.SOURCE])
            n2 = oscar.pull(Path(d), now.replace(day=21), state, get=get, pause=0, sleep=lambda s: None)
            self.assertFalse(n2["read"])
            self.assertEqual(len(calls), 1)             # held until a person clears it: no second request
            self.assertIsNone(oscar.store_load(Path(d), state))

    def test_a_short_list_is_not_stored(self):
        with tempfile.TemporaryDirectory() as d:
            get, _ = self.fake(self.two_pages())
            state = {}
            n = oscar.pull(Path(d), datetime(2026, 11, 20, tzinfo=timezone.utc), state, get=get, pause=0,
                           sleep=lambda s: None)
            self.assertFalse(n["read"])
            self.assertIsNone(oscar.store_load(Path(d), state))


if __name__ == "__main__":
    unittest.main()
