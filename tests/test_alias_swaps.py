"""The alias file's swap entries and Space-Track's "PAYLOAD x" placeholders. Fixtures: the real alias file, and real
rows of Orbit's catalog and name index built 26 Nov 2026 17:35 UTC (release `catalog`), cut unchanged into
tests/fixtures/catalog_objects_20261126.json and catalog_names_20261126.json."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orbit import aliases, catalog, catshards  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
IDS = aliases.source_ids(ROOT)
ENTRIES = aliases.load(source_ids=IDS)
CAT = json.loads((FIX / "catalog_objects_20261126.json").read_text(encoding="utf-8"))
NAMES = json.loads((FIX / "catalog_names_20261126.json").read_text(encoding="utf-8"))
SWAP = """- swap: "Cosmos 2536"
  claims:
    - {source: space-track, read: 2026-11-26, norad: 44422, as: "COSMOS 2536"}
    - {source: gcat-mcdowell, read: 2026-11-26, norad: 44424, as: "Kosmos-2536"}
  status: open
  evidence:
    - "All three numbers are 2019-039"
"""


def names(key: str) -> list[dict]:
    """The object's name records in full: the compact file leaves basis out where it is `attributed`, so the
    designation rule is applied again to each value."""
    return [{**n, "basis": catalog.name_basis(n["value"])} for n in CAT["objects"][key]["names"]]


class SwapEntries(unittest.TestCase):
    def check(self, text):
        return aliases.validate(aliases.parse(text), IDS)

    def test_a_swap_reads(self):
        e = self.check(SWAP)[0]
        self.assertEqual(e["claims"][0], {"source": "space-track", "read": "2026-11-26", "norad": 44422,
                                          "as": "COSMOS 2536"})
        self.assertEqual(aliases.read_of(e), "2026-11-26")
        self.assertEqual(aliases.swap_record(e), {
            "name": "cosmos 2536", "claims": {"space-track": ["44422"], "gcat-mcdowell": ["44424"]},
            "as": {"space-track": "COSMOS 2536", "gcat-mcdowell": "Kosmos-2536"}, "status": "open",
            "by": "aliases", "ref": "aliases.yml:1"})

    def test_swap_rules(self):
        bad = {
            "one claim": SWAP.replace('    - {source: gcat-mcdowell, read: 2026-11-26, norad: 44424, as: "Kosmos-2536"}\n',
                                      ""),
            "one number": SWAP.replace("norad: 44424", "norad: 44422"),
            "one source twice": SWAP.replace("source: gcat-mcdowell", "source: space-track"),
            "unknown source": SWAP.replace("source: gcat-mcdowell", "source: someone"),
            "claim without as": SWAP.replace(', as: "Kosmos-2536"', ""),
            "claim extra key": SWAP.replace('as: "Kosmos-2536"', 'as: "Kosmos-2536", basis: catalog'),
            "bad read": SWAP.replace("read: 2026-11-26, norad: 44424", "read: 26 Nov, norad: 44424"),
            "bad status": SWAP.replace("status: open", "status: maybe"),
            "settled without source": SWAP.replace("status: open", "status: settled"),
            "open with settled_by": SWAP.replace("status: open", "status: open\n  settled_by: space-track\n"
                                                                 "  settled: 2026-11-26"),
            "no evidence": SWAP.split("  evidence:")[0],
            "unknown key": SWAP + "  norad: 44422\n",
            "twice": SWAP + SWAP,
        }
        for why, text in bad.items():
            with self.assertRaises(aliases.AliasError, msg=why):
                self.check(text)
        ok = SWAP.replace("status: open", "status: settled\n  settled_by: space-track\n  settled: 2026-11-26")
        self.assertEqual(aliases.swap_record(self.check(ok)[0])["settled_by"], "space-track")
        self.assertEqual(self.check(SWAP + "  withdrawn: 2026-11-26\n  reason: \"test\"\n"), [])

    def test_the_real_cosmos_rotation(self):
        swaps = {e["swap"]: aliases.swap_record(e) for e in ENTRIES if aliases.is_swap(e)}
        self.assertEqual(sorted(swaps), ["Cosmos 2536", "Cosmos 2537", "Cosmos 2538"])
        st = {s["claims"]["space-track"][0]: n for n, s in swaps.items()}
        gc = {s["claims"]["gcat-mcdowell"][0]: n for n, s in swaps.items()}
        # Each claim is the source's own name for that number in the 26 Nov catalog.
        for key in ("44422", "44423", "44424"):
            by = {(n["source"], n["value"]) for n in CAT["objects"][key]["names"]}
            self.assertIn(("space-track", st[key].upper()), by)
            self.assertIn(("gcat-mcdowell", gc[key].replace("Cosmos ", "Kosmos-")), by)
        self.assertEqual(st, {"44422": "Cosmos 2536", "44423": "Cosmos 2537", "44424": "Cosmos 2538"})
        self.assertEqual(gc, {"44422": "Cosmos 2537", "44423": "Cosmos 2538", "44424": "Cosmos 2536"})

    def test_merged_into_the_catalog_swaps(self):
        live = [e for e in ENTRIES if aliases.is_swap(e)]
        found = [{"name": "cosmos 2537", "claims": {"wikidata": ["44423"]}, "status": "open"}]
        got = {s["name"]: s for s in catalog.merge_swaps(found, live)}
        self.assertEqual(sorted(got), ["cosmos 2536", "cosmos 2537", "cosmos 2538"])
        self.assertEqual(got["cosmos 2537"]["claims"],
                         {"wikidata": ["44423"], "space-track": ["44423"], "celestrak-satcat": ["44423"],
                          "gcat-mcdowell": ["44422"]})
        self.assertEqual(got["cosmos 2536"]["by"], "aliases")
        self.assertEqual(found[0]["claims"], {"wikidata": ["44423"]})  # the build's own list is left as found

    def test_alias_counts_and_shards(self):
        numbered = {k: {**v, "names": names(k)} for k, v in CAT["objects"].items()}
        counts = catalog.add_aliases(numbered, {}, [e for e in ENTRIES if aliases.is_swap(e)])
        self.assertEqual((counts["swaps"], counts["names"], counts["not_in_catalog"]), (3, 0, []))
        cdoc = {"schema": "tic-catalog/2", "read": CAT["read"], "sources": {}, "rank": [], "record_defaults": {},
                "objects": CAT["objects"], "unnumbered": CAT["unnumbered"],
                "swaps": catalog.merge_swaps([], ENTRIES and [e for e in ENTRIES if aliases.is_swap(e)])}
        sh = catshards.shards(cdoc)
        self.assertEqual(sorted(s["name"] for s in sh["n44"]["swaps"]), ["cosmos 2536", "cosmos 2537", "cosmos 2538"])
        self.assertEqual(sh["n39"]["swaps"], [])


class PayloadPlaceholders(unittest.TestCase):
    def test_payload_x_is_a_designation(self):
        for v in ("PAYLOAD A", "PAYLOAD B", "PAYLOAD C", "OBJECT A"):
            self.assertEqual(catalog.name_basis(v), "catalog", v)
        for v in ("PAYLOAD SIM (CYGNUS)", "PAYLOAD A DEB", "Payload Truss", "Shi Jian 15"):
            self.assertEqual(catalog.name_basis(v), "attributed", v)

    def test_sj15_shows_its_name_beside_the_placeholder(self):
        self.assertEqual(CAT["objects"]["39210"]["name"], "PAYLOAD C")  # the 26 Nov build, before this rule
        self.assertEqual(catalog.display_name(names("39210")), "PAYLOAD C (Shi Jian 15)")
        self.assertEqual(catalog.display_name(names("39208")), "PAYLOAD A (Shiyan Weixing 7)")
        self.assertEqual(catalog.display_name(names("39209")), "PAYLOAD B (Chuangxin-3)")
        self.assertEqual(catalog.display_name(names("49113")), "PAYLOAD B (Test satellite)")
        self.assertEqual(catalog.display_name(names("44422")), "COSMOS 2536")  # a real name is left alone


class ProwlerEvidence(unittest.TestCase):
    def test_the_entry_matches_the_catalog(self):
        e = next(e for e in ENTRIES if e.get("jcat") == "A04907")
        self.assertEqual((e["swf_key"], e["basis"], e["source"]), ("Prowler", "attributed", "swf-rpo"))
        a = CAT["unnumbered"]["A04907"]
        self.assertEqual((a["name"], a["intldes"][0]["value"], a["launch_date"][0]["value"]),
                         ("PROWLER", "1990-097E", "1990-11-15"))
        u = CAT["objects"]["20963"]
        wd = {r["field"]: r["value"] for r in u["intldes"] if r["source"] == "wikidata"}
        self.assertEqual(wd, {"P247": "1990-097E"})  # Wikidata's own COSPAR ID is GCAT's Prowler piece
        self.assertEqual({r["value"] for r in u["intldes"] if r["source"] != "wikidata"}, {"1990-097B"})
        row = next(r for r in NAMES["objects"] if r[0] == "A04907")
        self.assertEqual(row[2], "A04907")


if __name__ == "__main__":
    unittest.main()
