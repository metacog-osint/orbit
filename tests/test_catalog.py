"""TIC's satellite catalog, build step 2 (GCAT only): the test objects of the design note's section 7
(the private planning notes). Rows copied unchanged from GCAT's satcat and orgs of 13 Nov 2026."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orbit import catalog, gcat  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
READ = "2026-11-13"


def load():
    tables = {"satcat": gcat.parse_tsv((FIX / "catalog_satcat.tsv").read_bytes())}
    orgs = gcat.orgs_table(gcat.parse_tsv((FIX / "catalog_orgs.tsv").read_bytes()))
    return catalog.build(tables, orgs, READ, gcat_updated="2026 Nov 13 0021:52")


DOC = load()
OBJ = DOC["objects"]


def values(e, field="names"):
    return [r["value"] for r in e[field]]


class Shape(unittest.TestCase):
    def test_schema_and_keys(self):
        self.assertEqual(DOC["schema"], "tic-catalog/1")
        self.assertEqual(DOC["counts"]["numbered"], 13)
        self.assertEqual(set(OBJ), {"55841", "40258", "43874", "43917", "40208", "40099", "40100", "41744", "41745",
                                    "51280", "51281", "67759", "67760"})

    def test_every_value_carries_source_read_and_basis(self):
        for e in OBJ.values():
            for field in ("intldes", "launch_tag", "launch_date", "names", "owner", "state", "status", "decayed"):
                for r in e[field]:
                    self.assertEqual(r["source"], "gcat-mcdowell")
                    self.assertEqual(r["read"], READ)
                    self.assertIn(r["basis"], ("declared", "attributed", "catalog"))
                    self.assertEqual(r["ref"], e["jcat"])

    def test_gcat_alone_declares_nothing(self):
        self.assertFalse([r for e in OBJ.values() for r in e["names"] if r["basis"] == "declared"])

    def test_one_source_has_no_disagreements_or_swaps(self):
        self.assertEqual(DOC["counts"]["with_disagreements"], 0)
        self.assertEqual(DOC["swaps"], [])


class TestObjects(unittest.TestCase):
    def test_luch_5kh_no_3(self):
        e = OBJ["55841"]
        self.assertEqual(e["name"], "Luch-5Kh No. 3")
        # no Olymp alias in GCAT for this one: CelesTrak and Wikidata add it (step 4)
        self.assertEqual(values(e), ["Luch-5Kh No. 3", "Yenisey-2 No. 13L?"])
        self.assertTrue(e["names"][1]["uncertain"])
        self.assertEqual(values(e, "intldes"), ["2023-031A"])
        self.assertEqual(values(e, "launch_date"), ["2023-03-12"])
        self.assertEqual([(o["value"], o.get("name")) for o in e["owner"]][0][0], "FSB")

    def test_luch_40258_keeps_its_qualified_alt_name(self):
        e = OBJ["40258"]
        self.assertEqual(e["name"], "Luch")
        self.assertIn("Olimp-K No. 11L", values(e))  # GCAT's PLName: links SWF's "Luch (Olymp)" once spellings fold
        alt =[r for r in e["names"] if r["field"] == "AltNames"]
        self.assertEqual([(r["value"], r.get("qualifier")) for r in alt], [("Luch No. 794-48-211", "RA")])

    def test_tjs_3_and_its_subsatellite(self):
        self.assertEqual(OBJ["43874"]["name"], "Tongxin Jishu Shiyan 3")
        self.assertIn(("TJS-X1A", "JP"), [(r["value"], r.get("qualifier")) for r in OBJ["43874"]["names"]])
        self.assertEqual(OBJ["43917"]["name"], "TJS-3 subsatellite")
        self.assertEqual(values(OBJ["43874"], "launch_tag"), values(OBJ["43917"], "launch_tag"))

    def test_clio_keeps_every_name_and_gcat_doubt_on_owner(self):
        e = OBJ["40208"]
        self.assertEqual(e["name"], "NEMESIS 2")
        self.assertEqual(values(e), ["NEMESIS 2", "USA-257", "CLIO"])
        basis = {r["value"]: r["basis"] for r in e["names"]}
        self.assertEqual(basis["USA-257"], "catalog")
        self.assertEqual(basis["CLIO"], "attributed")
        self.assertEqual(e["owner"][0]["value"], "NROC?")
        self.assertTrue(e["owner"][0]["uncertain"])

    def test_gssap_1_to_8_by_alt_name(self):
        got = {r["value"]: key for key, e in OBJ.items() for r in e["names"] if r["value"].startswith("GSSAP")}
        self.assertEqual(got, {"GSSAP 1": "40099", "GSSAP 2": "40100", "GSSAP 3": "41744", "GSSAP 4": "41745",
                               "GSSAP 5": "51280", "GSSAP 6": "51281", "GSSAP 7": "67759", "GSSAP 8": "67760"})

    def test_designation_first_gets_its_best_name_in_brackets(self):
        # GCAT gives USA 253 as Name, so the display adds its next name in GCAT's order (PLName).
        self.assertEqual(OBJ["40099"]["name"], "USA 253 (Hornet 1)")
        self.assertEqual(values(OBJ["40099"]), ["USA 253", "Hornet 1", "AFSPC-4 F1", "GSSAP 1"])

    def test_a_bare_qualifier_is_not_a_name(self):
        # 51280's AltNames is ':U,GSSAP 5'
        self.assertEqual(values(OBJ["51280"]), ["USA 324", "Hornet 5", "GSSAP 5"])

    def test_same_name_twice_in_one_source_is_kept_once(self):
        # 40208: Name and PLName are both NEMESIS 2
        self.assertEqual([r["field"] for r in OBJ["40208"]["names"]], ["Name", "AltNames", "AltNames"])


class Ranking(unittest.TestCase):
    def test_space_track_outranks_gcat_and_brackets_the_programme_name(self):
        names = list(OBJ["40208"]["names"]) + [catalog.rec("USA 257", "space-track", "2026-11-17", "catalog")]
        self.assertEqual(catalog.display_name(names), "USA 257 (NEMESIS 2)")

    def test_disagreement_is_listed_not_resolved(self):
        e = dict(OBJ["55841"])
        e["intldes"] = e["intldes"] + [catalog.rec("2023-031B", "space-track", "2026-11-17", "catalog")]
        e = catalog.finish(e)
        self.assertEqual(e["disagreements"][0]["field"], "intldes")
        self.assertEqual(values(e, "intldes"), ["2023-031A", "2023-031B"])

    def test_swap_flagged_when_two_sources_give_one_name_to_different_numbers(self):
        a, b = dict(OBJ["40099"]), dict(OBJ["40100"])
        a["names"] = a["names"] + [catalog.rec("GSSAP 2", "celestrak-satcat", "2026-11-17")]
        b["names"] = b["names"] + [catalog.rec("GSSAP 1", "celestrak-satcat", "2026-11-17")]
        got = catalog.swaps({"40099": a, "40100": b})
        self.assertEqual([s["name"] for s in got], ["gssap 1", "gssap 2"])
        self.assertEqual(got[0]["claims"], {"gcat-mcdowell": ["40099"], "celestrak-satcat": ["40100"]})
        self.assertEqual(got[0]["status"], "open")


class GcatOwnCatalogs(unittest.TestCase):
    def test_auxcat_number_cell_is_not_a_norad_claim(self):
        # auxcat A00002 (13 Nov 2026) carries 00003 in its Satcat cell; satcat's S00003 holds the number.
        hdr = "#JCAT\tSatcat\tLaunch_Tag\tPiece\tType\tName\tPLName\tLDate\tParent\tSDate\tPrimary\tDDate\tStatus\tOwner\tState\tAltNames\n"
        s = "S00003\t00003\t1958 ALP\t1958 ALP\tP\tExplorer 1\t-\t1958 Feb  1\t-\t-\tEarth\t1970 Mar 31\tR\tABMA\tUS\t-\n"
        a = "A00002\t00003\t1957 BET\t1957 BET 1\tR2\t8K71PS No. M1-11 Stage 2\t-\t1957 Nov  3\t-\t-\tEarth\t1958 Apr 14\tR\tOKB1\tSU\t-\n"
        doc = catalog.build({"satcat": gcat.parse_tsv(hdr.encode() + s.encode()),
                             "auxcat": gcat.parse_tsv(hdr.encode() + a.encode())}, {}, READ)
        self.assertEqual(doc["objects"]["3"]["jcat"], "S00003")
        self.assertEqual(doc["unnumbered"]["A00002"]["gcat_satcat_cell"], 3)
        self.assertIsNone(doc["unnumbered"]["A00002"]["norad"])
        self.assertEqual(doc["counts"]["with_disagreements"], 0)


class AltNames(unittest.TestCase):
    def test_split(self):
        self.assertEqual(catalog.alt_names("USA 251,Navstar 70,Rigel"),
                         [("USA 251", None), ("Navstar 70", None), ("Rigel", None)])
        self.assertEqual(catalog.alt_names("NROL-33,SDS C-7 GEO:JP"), [("NROL-33", None), ("SDS C-7 GEO", "JP")])
        self.assertEqual(catalog.alt_names("-"), [])


if __name__ == "__main__":
    unittest.main()
