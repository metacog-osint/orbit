"""Catalog build step 5: the alias file (orbit/aliases.py), alias names in the catalog, the name index, and the rpo
lane matching on it (orbit/rpo.py). Fixtures: the real alias file, SWF's RPO tabs of 15 Nov 2026, and 22 real rows of
the name index built 17 Nov 2026 from the step-4 catalog (Space-Track, GCAT of 15 Nov, CelesTrak, Wikidata) with the
alias file applied, cut unchanged into tests/fixtures/catalog_names_20261117.json."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orbit import aliases, catalog, gcat, rpo  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
IDS = aliases.source_ids(ROOT)
ENTRIES = aliases.load(source_ids=IDS)
NAMES = json.loads((FIX / "catalog_names_20261117.json").read_text(encoding="utf-8"))
BODIES = {t: (FIX / f"swf_rpo_{t}.csv").read_bytes() for t in (*rpo.TABS, "about")}
GOOD = """- norad: 40258
  name: "Luch (Olymp)"
  basis: attributed
  source: swf-rpo
  read: 2026-11-17
  evidence:
    - "Space-Track SATNAME of 40258 is 'LUCH (OLYMP)'"
"""


class AliasFile(unittest.TestCase):
    def test_the_real_file_reads_with_the_five_test_objects(self):
        got = {e.get("norad") or e.get("program") for e in ENTRIES}
        self.assertEqual(got, {55841, 40258, 43917, 40208, "GSSAP"})
        gssap = next(e for e in ENTRIES if e.get("program") == "GSSAP")
        self.assertEqual(gssap["members"], [40099, 40100, 41744, 41745, 51280, 51281, 67759, 67760])
        self.assertTrue(all(e["evidence"] for e in ENTRIES))

    def test_subset_values(self):
        e = aliases.parse(GOOD + '  note: "a # inside quotes stays"  # a comment goes\n')[0]
        self.assertEqual(e["norad"], 40258)
        self.assertEqual(e["read"], "2026-11-17")
        self.assertEqual(e["note"], "a # inside quotes stays")
        self.assertEqual(e["evidence"], ["Space-Track SATNAME of 40258 is 'LUCH (OLYMP)'"])
        self.assertEqual(aliases.parse("- members: [1, 2, \"x, y\"]\n")[0]["members"], [1, 2, "x, y"])

    def test_outside_the_subset_is_an_error_with_its_line(self):
        for text, line in (("- a: {b: 1}\n", 1), ("- a: 1\n  b:\n    - [1, [2]]\n", 3), ("- a: 1\n   b: 2\n", 2),
                           ("a: 1\n", 1), ("- a: 1\n  a: 2\n", 2)):
            with self.assertRaises(aliases.AliasError) as cm:
                aliases.parse(text)
            self.assertIn(f"line {line}", str(cm.exception))

    def test_rules(self):
        def check(text):
            return aliases.validate(aliases.parse(text), IDS)
        self.assertEqual(len(check(GOOD)), 1)
        bad = {
            "no evidence": GOOD.split("  evidence:")[0],
            "unknown source": GOOD.replace("swf-rpo", "someone"),
            "both keys": GOOD.replace("- norad: 40258\n", "- norad: 40258\n  jcat: S40258\n"),
            "bad basis": GOOD.replace("attributed", "guessed"),
            "bad date": GOOD.replace("2026-11-17", "17 Nov 2026"),
            "withdrawn without reason": GOOD + "  withdrawn: 2026-11-18\n",
            "date without key": GOOD + '  swf_date: "Oct 2014 - Present"\n',
            "twice": GOOD + GOOD,
            "swap": "- swap: [1, 2]\n",
        }
        for why, text in bad.items():
            with self.assertRaises(aliases.AliasError, msg=why):
                check(text)

    def test_a_withdrawn_entry_stays_in_the_file_and_is_skipped(self):
        text = GOOD + "  withdrawn: 2026-11-18\n  reason: \"wrong object\"\n"
        self.assertEqual(check_live(text), [])


def check_live(text):
    return aliases.validate(aliases.parse(text), IDS)


class CatalogAliases(unittest.TestCase):
    def test_alias_names_and_programs_join_the_catalog(self):
        tables = {"satcat": gcat.parse_tsv((FIX / "catalog_satcat.tsv").read_bytes())}
        orgs = gcat.orgs_table(gcat.parse_tsv((FIX / "catalog_orgs.tsv").read_bytes()))
        doc = catalog.build(tables, orgs, "2026-11-17", alias_entries=ENTRIES)
        c = doc["counts"][aliases.SOURCE]
        o = doc["objects"]
        held = [k for k in ("40258", "55841", "40208", "43917") if k in o]
        self.assertEqual(c["names"], len(held))
        for k in held:
            recs = [n for n in o[k]["names"] if n["source"] == aliases.SOURCE]
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0]["cited"], "swf-rpo")
            self.assertTrue(recs[0]["ref"].startswith("aliases.yml:"))
        if "40099" in o:
            self.assertEqual(o["40099"]["program"][0]["value"], "GSSAP")
        self.assertEqual(sorted(c["not_in_catalog"]),
                         sorted(k for k in ("40258", "55841", "40208", "43917", "40099", "40100", "41744", "41745",
                                            "51280", "51281", "67759", "67760") if k not in o))

    def test_name_index_rows(self):
        row = next(r for r in NAMES["objects"] if r[0] == "55841")
        key, norad, jcat, type_, launched, gone, display, names_ = row
        self.assertEqual((norad, jcat, type_, launched, gone, display), (55841, "S55841", "payload", "2023-03-12",
                                                                          None, "LUCH (OLYMP) 2"))
        self.assertEqual(names_[0], "LUCH (OLYMP) 2")  # Space-Track first; one copy of each name
        self.assertIn("Luch (Olymp) 2", names_)  # the alias file's spelling
        self.assertEqual(len(names_), len(set(names_)))
        gone = next(r for r in NAMES["objects"] if r[0] == "44422")[5]  # Space-Track: decayed
        self.assertTrue(gone is not None and gone[:4].isdigit(), gone)


class RpoOnCatalogNames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = rpo.read(BODIES, None, NAMES, ENTRIES)
        cls.rows = cls.doc["rows"]

    def links(self, date_text, role, tab="military"):
        r = next(r for r in self.rows if r["tab"] == tab and r["date_text"] == date_text)
        return r["gcat"][role]

    def test_matched_on_the_catalog(self):
        self.assertEqual(self.doc["matched_on"], "catalog")
        self.assertGreater(self.doc["links"]["by_alias"], 0)

    def test_luch_olymp_rows(self):
        for d in ("Oct 2014 - Present", "February 2019"):
            g = self.links(d, "chaser")
            self.assertEqual([(x["norad"], x["by"]) for x in g], [(40258, "alias")], d)
        g = self.links("Mar 2023 - Present", "chaser")
        self.assertEqual([(x["norad"], x["by"]) for x in g], [(55841, "alias")])

    def test_clio_tjs3_akm_and_gssap(self):
        self.assertEqual([x["norad"] for x in self.links("2014 - Present", "chaser")], [40208])
        self.assertEqual([x["norad"] for x in self.links("Jan - Apr 2019", "chaser")], [43917])
        self.assertEqual([x["norad"] for x in self.links("Jan - Apr 2019", "target")], [43874])
        g = self.links("Jul 2014 - Present", "chaser")
        self.assertEqual(len(g), 1)
        self.assertEqual((g[0]["program"], len(g[0]["members"])), ("GSSAP", 8))

    def test_names_from_other_sources_link(self):
        g = self.links("Dec 2021 - Jan 2022", "target")  # SWF's "Compass G2" is Space-Track's name for 34779
        self.assertEqual([(x["norad"], x["by"]) for x in g], [(34779, "name")])
        g = self.links("2009 - 2016", "chaser")  # "PAN (USA-207)": GCAT's AltNames give USA-207
        self.assertEqual([x["norad"] for x in g], [35815])

    def test_two_objects_fit_so_no_link(self):
        # Cosmos 2536: Space-Track gives the name to 44422, GCAT to 44424 (a piece swap): no link, not a guess.
        self.assertEqual(self.links("Aug - Dec 2019", "chaser"), [])
        # Prowler: Wikidata's item carries USA 67's number (20963); GCAT lists Prowler apart as A04907.
        self.assertEqual(self.links("1990-1998", "chaser"), [])

    def test_gcat_fallback_without_the_index(self):
        doc = rpo.read(BODIES, {}, None, ENTRIES)
        self.assertEqual(doc["matched_on"], "gcat")
        self.assertEqual(doc["links"]["linked"], doc["links"]["by_alias"])  # no GCAT names given: aliases only
        self.assertGreater(doc["links"]["by_alias"], 0)


if __name__ == "__main__":
    unittest.main()
