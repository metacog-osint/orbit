"""TIC's satellite catalog, build step 4: CelesTrak SATCAT and Wikidata (orbit/catsources.py, orbit/catalog.py).

Fixtures, rows unchanged:
- celestrak_satcat_20261117.csv: CelesTrak's /pub/satcat.csv (file time 2026-11-16 20:34:45 UTC, read 17 Nov 2026
  18:43 UTC), header and the rows of the 19 objects in test_stcat.py's fixtures. CelesTrak SATCAT (T.S. Kelso,
  celestrak.org).
- wikidata_p377_20261117.json: the reply to catsources.WD_QUERY of 17 Nov 2026 18:42 UTC, bindings cut to the same
  objects plus 25544 (two items: the ISS and Zarya) and one item whose P377 is Wikidata's "unknown value". Wikidata,
  CC0.
- CT_DIR below: CelesTrak's https://celestrak.org/satcat/jsonDir.php reply of 17 Nov 2026 18:39 UTC, as printed.
Space-Track and GCAT fixtures as in test_stcat.py.
"""
import gzip
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orbit import catalog, catsources, gcat  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
CT_BODY = (FIX / "celestrak_satcat_20261117.csv").read_bytes()
CT_ROWS = catsources.ct_parse(CT_BODY)
WD_BODY = (FIX / "wikidata_p377_20261117.json").read_bytes()
WD_ROWS = catsources.wd_parse(WD_BODY)
CT_DIR = b'[{\n    "FILE_NAME": "satcat.csv",\n    "FILE_SIZE": 6798479,\n    "FILE_MTIME": "2026-11-16 20:34:45 UTC"\n}]'
SATCAT = json.loads((FIX / "spacetrack_satcat_20261117.json").read_text(encoding="utf-8"))
DECAY = json.loads((FIX / "spacetrack_decay_20261117.json").read_text(encoding="utf-8"))
ORGS = gcat.orgs_table(gcat.parse_tsv((FIX / "catalog_orgs.tsv").read_bytes()))
TEST = ["55841", "40258", "43874", "43917", "40208", "40099", "40100", "41744", "41745", "51280", "51281",
        "67759", "67760"]
CT, WD = catsources.CT, catsources.WD


def build(ct=True, wd=True):
    rows = gcat.parse_tsv((FIX / "catalog_satcat.tsv").read_bytes())
    rows += gcat.parse_tsv((FIX / "catalog_satcat_extra.tsv").read_bytes())
    return catalog.build({"satcat": rows}, ORGS, "2026-11-15", gcat_updated="2026 Nov 15 1018:34",
                         spacetrack={"satcat": SATCAT, "decay": DECAY, "read": "2026-11-17",
                                     "read_at": "2026-11-17T18:09:25Z"},
                         celestrak={"rows": CT_ROWS, "read": "2026-11-17", "read_at": "2026-11-17T18:43:19Z",
                                    "file_mtime": "2026-11-16 20:34:45 UTC"} if ct else None,
                         wikidata={"rows": WD_ROWS, "read": "2026-11-17",
                                   "read_at": "2026-11-17T18:42:54Z"} if wd else None)


DOC = build()
OBJ = DOC["objects"]


def recs(e, field, source):
    return [r for r in e[field] if r["source"] == source]


def t(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


class Fetching(unittest.TestCase):
    def setUp(self):
        self._floors = catsources.CT_MIN_ROWS, catsources.WD_MIN_ROWS
        catsources.CT_MIN_ROWS = catsources.WD_MIN_ROWS = 10  # the fixtures are cut to a few rows

    def tearDown(self):
        catsources.CT_MIN_ROWS, catsources.WD_MIN_ROWS = self._floors

    def fake(self, answers):
        calls = []

        def get(source, url, accept="*/*", timeout=120):
            calls.append(url)
            a = answers.pop(0)
            if isinstance(a, Exception):
                raise a
            return a
        return get, calls

    def test_user_agent_names_the_repository_and_no_person(self):
        self.assertIn("bot", catsources.UA.lower())
        self.assertIn("github.com/metacog-osint/orbit", catsources.UA)
        self.assertNotIn("@", catsources.UA)

    def test_redirects_are_not_followed(self):
        self.assertIsNone(catsources._NoRedirect().redirect_request())

    def test_celestrak_directory_then_file_then_not_again_that_day(self):
        with tempfile.TemporaryDirectory() as d:
            get, calls = self.fake([CT_DIR, CT_BODY])
            n = catsources.pull(Path(d), t("2026-11-17T18:43:00"), get, only=(CT,))[CT]
            self.assertTrue(n["read"])
            self.assertEqual(calls, [catsources.CT_DIR_URL, catsources.CT_CSV_URL])
            got = catsources.load(Path(d))[CT]
            self.assertEqual(len(got["rows"]), 19)
            self.assertEqual(got["file_mtime"], "2026-11-16 20:34:45 UTC")
            self.assertEqual(len(list((Path(d) / "raw" / CT).glob("*.csv.gz"))), 1)
            n = catsources.pull(Path(d), t("2026-11-17T21:23:00"), get, only=(CT,))[CT]
            self.assertIn("already read today", n["why"])
            self.assertEqual(len(calls), 2)

    def test_celestrak_unchanged_file_is_not_downloaded_again(self):
        with tempfile.TemporaryDirectory() as d:
            get, calls = self.fake([CT_DIR, CT_BODY, CT_DIR])
            catsources.pull(Path(d), t("2026-11-17T18:43:00"), get, only=(CT,))
            n = catsources.pull(Path(d), t("2026-11-18T17:30:00"), get, only=(CT,))[CT]
            self.assertFalse(n["read"])
            self.assertIn("unchanged", n["why"])
            self.assertEqual(calls[-1], catsources.CT_DIR_URL)
            self.assertEqual(len(calls), 3)

    def test_short_reply_keeps_the_last_read(self):
        catsources.CT_MIN_ROWS = 50000  # the real floor: the fixture's 19 rows stand for a cut-short reply
        with tempfile.TemporaryDirectory() as d:
            get, _ = self.fake([CT_DIR, CT_BODY])
            n = catsources.ct_pull(Path(d), t("2026-11-17T18:43:00"), {}, get)
            self.assertFalse(n["read"])
            self.assertIn("19 rows", n["why"])
            self.assertFalse((Path(d) / catsources.CT_STORE).exists())

    def test_a_refusal_holds_until_a_person_clears_it(self):
        with tempfile.TemporaryDirectory() as d:
            refused = catsources.Refused(CT, catsources.CT_CSV_URL, 406, "Not Acceptable")
            get, calls = self.fake([CT_DIR, refused])
            n = catsources.pull(Path(d), t("2026-11-17T18:42:00"), get, only=(CT,))[CT]
            self.assertEqual(n["refused"], 406)
            n = catsources.pull(Path(d), t("2026-11-20T18:00:00"), get, only=(CT,))[CT]
            self.assertIn("a person must clear it", n["why"])
            self.assertEqual(len(calls), 2)
            self.assertTrue(catsources.clear_hold(Path(d), CT))
            self.assertIsNone(catsources.held(catsources.read_json(Path(d) / catsources.STATE, {})[CT],
                                              t("2026-11-20T18:00:00")))

    def test_a_server_error_holds_until_the_next_utc_day(self):
        st = {}
        catsources.hold(st, catsources.Refused(CT, catsources.CT_DIR_URL, 503), t("2026-11-17T18:00:00"))
        self.assertIn("until 2026-11-18T00:00:00Z", catsources.held(st, t("2026-11-17T23:00:00")))
        self.assertIsNone(catsources.held(st, t("2026-11-18T00:00:00")))

    def test_wikidata_weekly_and_again_when_its_store_is_gone(self):
        with tempfile.TemporaryDirectory() as d:
            body = WD_BODY
            get, calls = self.fake([body, body])
            self.assertTrue(catsources.pull(Path(d), t("2026-11-17T18:42:00"), get, only=(WD,))[WD]["read"])
            self.assertIn("once a week",
                          catsources.pull(Path(d), t("2026-11-23T18:00:00"), get, only=(WD,))[WD]["why"])
            (Path(d) / catsources.WD_STORE).unlink()
            self.assertTrue(catsources.pull(Path(d), t("2026-11-18T18:00:00"), get, only=(WD,))[WD]["read"])
            self.assertEqual(len(calls), 2)
            self.assertTrue(calls[0].startswith(catsources.WD_URL + "?query="))

    def test_wikidata_unknown_value_is_parsed_and_skipped(self):
        unk = [r for r in WD_ROWS if not r["scn"].isdigit()]
        self.assertEqual(len(unk), 1)
        self.assertEqual(DOC["counts"][WD]["unknown_value_skipped"], 1)


class Release(unittest.TestCase):
    def test_existing_release_gets_current_notes_with_every_source(self):
        calls = []

        class R:
            returncode, stderr = 0, ""

        def gh(*args):
            calls.append(args)
            return R()

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "state.json"
            p.write_text("{}")
            from orbit import stcat
            stcat.release_put({stcat.SOURCES_STATE_ASSET: p}, "o/r", gh=gh)
        self.assertEqual(calls[1][:3], ("release", "edit", "catalog"))
        notes = calls[1][-1]
        for credit in ("CC BY 4.0", "USSPACECOM", "CelesTrak SATCAT (T.S. Kelso, celestrak.org)", "Wikidata (CC0)"):
            self.assertIn(credit, notes)
        self.assertTrue(calls[2][-1].endswith("catalog-sources.json"))


class Records(unittest.TestCase):
    def test_celestrak_name_kept_as_given(self):
        self.assertEqual([r["value"] for r in recs(OBJ["40208"], "names", CT)], ["USA 257 (CLIO)"])
        self.assertEqual([r["value"] for r in recs(OBJ["55841"], "names", CT)], ["LUCH-5X (OLYMP-K 2)"])
        self.assertEqual([r["value"] for r in recs(OBJ["40258"], "names", CT)], ["LUCH (OLYMP-K 1)"])

    def test_wikidata_names_carry_the_q_id(self):
        wd = recs(OBJ["40258"], "names", WD)
        self.assertEqual(wd[0], {"value": "Olymp-K 1", "source": WD, "ref": "Q18550141", "read": "2026-11-17",
                                 "basis": "attributed", "field": "label:en"})
        self.assertIn("Olimp-K No. 11L", [r["value"] for r in wd])
        self.assertEqual({r["field"] for r in wd[1:]}, {"altLabel:en"})
        usa = recs(OBJ["40208"], "names", WD)
        self.assertEqual([(r["value"], r["basis"]) for r in usa], [("USA 257", "catalog")])

    def test_every_name_is_kept(self):
        for key in TEST:
            before = build(ct=False, wd=False)["objects"][key]["names"]
            after = OBJ[key]["names"]
            self.assertTrue(all(n in after for n in before), key)
        self.assertEqual({r["source"] for r in OBJ["40099"]["names"]},
                         {"space-track", "gcat-mcdowell", CT, WD})

    def test_display_names_unchanged_by_lower_ranked_sources(self):
        before = build(ct=False, wd=False)["objects"]
        for key in TEST:
            self.assertEqual(OBJ[key]["name"], before[key]["name"], key)
        self.assertEqual(OBJ["40208"]["name"], "USA 257 (NEMESIS 2)")

    def test_rank_order(self):
        r = catalog.RANK
        self.assertLess(r.index("gcat-mcdowell"), r.index(CT))
        self.assertLess(r.index(CT), r.index(WD))
        self.assertLess(r.index(WD), r.index("swf-rpo"))

    def test_state_from_owner_compared_as_gcat_state(self):
        s = recs(OBJ["55841"], "state", CT)[0]
        self.assertEqual((s["value"], s["field"], s["cmp"]), ("CIS", "OWNER", "RU"))

    def test_operational_status_kept_and_classed(self):
        self.assertEqual([(r["value"], r.get("cmp")) for r in OBJ["40258"]["ops_status"]], [("-", "inactive")])
        self.assertEqual([(r["value"], r.get("cmp")) for r in OBJ["55841"]["ops_status"]], [("+", "active")])
        d = recs(OBJ["12842"], "ops_status", CT)[0]
        self.assertTrue(d["nocompare"])  # "D" is decayed, compared under `decayed`

    def test_test_objects_agree(self):
        # 40258: CelesTrak alone gives an operational status ("-"); GCAT's Status is an orbital status, Space-Track
        # and Wikidata give none, so there is nothing to compare it with and no status disagreement.
        for key in TEST:
            self.assertEqual(OBJ[key]["disagreements"], [], key)

    def test_operational_status_differences_are_listed(self):
        e = {"ops_status": [catalog.rec("-", CT, "2026-11-17", cmp="inactive"),
                            catalog.rec("Operational", "wmo-oscar-space", "2026-11-17", cmp="active")]}
        self.assertEqual(catalog.disagreements(e), [{"field": "ops_status", "claims": [
            {"value": "inactive", "sources": [CT], "as_given": ["-"]},
            {"value": "active", "sources": ["wmo-oscar-space"], "as_given": ["Operational"]}]}])


class Disagreements(unittest.TestCase):
    def test_iridium_designations_four_sources(self):
        # Space-Track and CelesTrak against GCAT and Wikidata: listed, never resolved.
        for key, gc, sp in (("24905", "1997-082B", "1997-043C"), ("25105", "1997-043C", "1997-082B")):
            d = {x["field"]: x for x in OBJ[key]["disagreements"]}["intldes"]
            self.assertEqual(d["claims"], [{"value": gc, "sources": ["gcat-mcdowell", WD]},
                                           {"value": sp, "sources": ["space-track", CT]}])

    def test_decayed_celestrak_with_space_track(self):
        d = {x["field"]: x for x in OBJ["45565"]["disagreements"]}["decayed"]
        self.assertEqual(d["claims"], [{"value": False, "sources": ["gcat-mcdowell"]},
                                       {"value": True, "sources": ["space-track", CT]}])
        self.assertEqual(recs(OBJ["45565"], "decay_date", CT)[0]["value"], "2026-11-15")

    def test_name_swap_through_catalog_swaps(self):
        self.assertEqual(DOC["swaps"], [
            {"name": "sj-2", "claims": {"space-track": ["12842"], "gcat-mcdowell": ["12845"], CT: ["12842"],
                                        WD: ["12845"]}, "status": "open"},
            {"name": "sj-2b", "claims": {"gcat-mcdowell": ["12842"], "space-track": ["12845"], CT: ["12845"],
                                         WD: ["12842"]}, "status": "open"}])

    def test_two_wikidata_items_on_one_number_are_a_note(self):
        # 25544 has no GCAT or Space-Track row in these fixtures, so it is a Wikidata-only entry here.
        e = OBJ["25544"]
        self.assertEqual(e["wikidata_items"], ["Q25271", "Q331785"])
        self.assertEqual(e["only_in"], [WD])
        self.assertEqual(e["disagreements"], [])

    def test_counts_and_sources(self):
        c = DOC["counts"]
        self.assertEqual(c[CT]["rows"], 19)
        self.assertEqual(c[CT]["celestrak_only"], 0)
        self.assertEqual(c[WD]["numbers_on_two_items"], 1)
        self.assertEqual(DOC["sources"][CT]["citation"], "CelesTrak SATCAT (T.S. Kelso, celestrak.org)")
        self.assertIn("CC0", DOC["sources"][WD]["citation"])
        self.assertEqual(DOC["sources"][CT]["file_time"], "2026-11-16 20:34:45 UTC")


if __name__ == "__main__":
    unittest.main()
