"""TIC's satellite catalog, build step 6 (orbit/catshards.py): compact records, shards for the object page, the
search index and the rules note; and the orbit records each source states (orbit/catalog.py).

Fixtures, all already in tests/fixtures and unchanged: GCAT, Space-Track, CelesTrak and Wikidata rows as in
test_catsources.py; GCAT's auxcat and tmpcat rows of 13 Nov 2026 (auxcat.tsv, tmpcat.tsv, as in test_orbit.py); the
real alias file orbit/data/catalog/aliases.yml.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from orbit import aliases, catalog, catshards, gcat  # noqa: E402
import test_catsources as T  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
ENTRIES = aliases.load(source_ids=aliases.source_ids(ROOT))


def build():
    rows = gcat.parse_tsv((FIX / "catalog_satcat.tsv").read_bytes())
    rows += gcat.parse_tsv((FIX / "catalog_satcat_extra.tsv").read_bytes())
    tables = {"satcat": rows, "auxcat": gcat.parse_tsv((FIX / "auxcat.tsv").read_bytes()),
              "tmpcat": gcat.parse_tsv((FIX / "tmpcat.tsv").read_bytes())}
    return catalog.build(tables, T.ORGS, "2026-11-15", gcat_updated="2026 Nov 15 1018:34",
                         spacetrack={"satcat": T.SATCAT, "decay": T.DECAY, "read": "2026-11-17",
                                     "read_at": "2026-11-17T18:09:25Z"},
                         celestrak={"rows": T.CT_ROWS, "read": "2026-11-17", "read_at": "2026-11-17T18:43:19Z",
                                    "file_mtime": "2026-11-16 20:34:45 UTC"},
                         wikidata={"rows": T.WD_ROWS, "read": "2026-11-17", "read_at": "2026-11-17T18:42:54Z"},
                         alias_entries=ENTRIES)


DOC = build()
CDOC = catshards.compact(DOC)
READS = {s: v.get("read") for s, v in DOC["sources"].items()}
ASSETS = catshards.bundle(DOC, CDOC)
SHARDS = catshards.read_shards(ASSETS[catshards.SHARDS_ASSET])


def all_records(doc):
    for group in ("objects", "unnumbered"):
        for key, e in doc[group].items():
            for f in catshards.RECORD_FIELDS:
                for r in e.get(f) or []:
                    yield key, f, r


class OrbitRecords(unittest.TestCase):
    def test_each_source_states_its_own_orbit_never_merged(self):
        # GCAT satcat S40258: ODate 2014 Nov 26, Perigee 35781, Apogee 35795, Inc 0.04, OpOrbit GEO/S; CelesTrak's
        # row for 40258 (file of 16 Nov 2026): PERIOD 1452.87, INCLINATION 2.29, APOGEE 36132, PERIGEE 36097, EA, ORB.
        o = {r["source"]: r["value"] for r in DOC["objects"]["40258"]["orbit"]}
        self.assertEqual(o["gcat-mcdowell"], {"perigee_km": 35781.0, "apogee_km": 35795.0, "inc_deg": 0.04,
                                              "elements_date": "2014-11-26", "op_orbit": "GEO/S"})
        self.assertEqual(o["celestrak-satcat"], {"perigee_km": 36097.0, "apogee_km": 36132.0, "inc_deg": 2.29,
                                                 "period_min": 1452.87, "orbit_center": "EA", "orbit_type": "ORB"})
        self.assertNotIn("orbit", catalog.FLAGGED)  # shown side by side, never compared

    def test_no_elements_no_record(self):
        # tmpcat T00001 (13 Nov 2026) is a row of '-'; auxcat A00001 (1957 ALP 3) has GCAT's 1957 elements
        self.assertEqual(DOC["unnumbered"]["T00001"]["orbit"], [])
        self.assertEqual(DOC["unnumbered"]["A00001"]["orbit"][0]["value"]["elements_date"], "1957-10-04")
        self.assertIsNone(catalog.ct_orbit({"PERIOD": "", "INCLINATION": "", "APOGEE": "", "PERIGEE": ""}))


class Compact(unittest.TestCase):
    def test_round_trip_is_exact(self):
        for group in ("objects", "unnumbered"):
            for key, e in DOC[group].items():
                self.assertEqual(catshards.expand_entry(CDOC[group][key], READS), e, key)

    def test_defaults_left_out_other_values_kept(self):
        self.assertEqual(CDOC["schema"], "tic-catalog/2")
        self.assertEqual(set(CDOC["record_defaults"]), {"read", "ref", "basis"})
        e = CDOC["objects"]["40258"]
        g = next(r for r in e["names"] if r["source"] == "gcat-mcdowell")
        self.assertEqual(set(g) & {"read", "ref", "basis"}, set())
        cat = next(r for r in e["intldes"] if r["source"] == "space-track")
        self.assertEqual(cat["basis"], "catalog")  # only `attributed` is a default
        wd = next(r for r in e["names"] if r["source"] == "wikidata")
        self.assertTrue(wd["ref"].startswith("Q"))  # Q-ids are always given
        al = next(r for r in e["names"] if r["source"] == "aliases")
        self.assertTrue(al["ref"].startswith("aliases.yml:"))

    def test_a_read_date_that_differs_from_the_sources_block_is_kept(self):
        e = json.loads(json.dumps(DOC["objects"]["40258"]))
        e["names"][0]["read"] = "2026-11-01"
        c = catshards.compact_entry(e, READS)
        self.assertEqual(c["names"][0]["read"], "2026-11-01")
        self.assertEqual(catshards.expand_entry(c, READS), e)

    def test_smaller(self):
        full = len(json.dumps(DOC, separators=(",", ":")))
        small = len(json.dumps(CDOC, separators=(",", ":")))
        self.assertLess(small, full * 0.75)


class Shards(unittest.TestCase):
    def test_shard_rule(self):
        for key, sid in (("5", "n0"), ("25544", "n25"), ("40258", "n40"), ("101000", "n101"), ("A00001", "jA0"),
                         ("A04907", "jA4"), ("A12066", "jA12"), ("S100129", "jS100"), ("T00051", "jT0")):
            self.assertEqual(catshards.shard_of(key), sid)

    def test_every_object_once_in_its_shard_with_sources(self):
        seen = {}
        for name, sd in SHARDS.items():
            if name in ("search.json", "rules.json"):
                continue
            self.assertEqual(sd["schema"], "tic-catalog-shard/1")
            self.assertEqual(name, sd["shard"] + ".json")
            self.assertEqual(sd["sources"], DOC["sources"])
            for key, e in sd["objects"].items():
                self.assertNotIn(key, seen)
                seen[key] = e
                self.assertEqual(catshards.shard_of(key), sd["shard"])
                group = "objects" if key.isdigit() else "unnumbered"
                self.assertEqual(catshards.expand_entry(e, READS), DOC[group][key])
        self.assertEqual(set(seen), set(DOC["objects"]) | set(DOC["unnumbered"]))
        self.assertIn("jA12.json", SHARDS)
        self.assertIn("jT0.json", SHARDS)

    def test_swaps_ride_with_the_objects_they_touch(self):
        # SJ-2 / SJ-2B (12842, 12845): Wikidata sides with GCAT against Space-Track and CelesTrak (17 Nov 2026)
        names = {s["name"] for s in SHARDS["n12.json"]["swaps"]}
        self.assertEqual(names, {"sj-2", "sj-2b"})
        self.assertEqual(SHARDS["n40.json"]["swaps"], [])

    def test_bundle_is_the_same_bytes_each_time(self):
        self.assertEqual(catshards.bundle(DOC, CDOC), ASSETS)


class Search(unittest.TestCase):
    def setUp(self):
        self.idx = SHARDS["search.json"]
        self.rows = {r[0]: r for r in self.idx["objects"]}

    def test_every_object_one_row(self):
        self.assertEqual(self.idx["schema"], "tic-catalog-search/1")
        self.assertEqual(len(self.idx["objects"]), len(DOC["objects"]) + len(DOC["unnumbered"]))
        self.assertEqual(self.idx["columns"], ["key", "name", "other_names", "cospar", "type", "gone"])

    def test_rows(self):
        key, name, others, cospar, type_, gone = self.rows["40258"]
        self.assertEqual(name, DOC["objects"]["40258"]["name"])
        self.assertIn("Luch", others)
        self.assertIn("Olimp-K No. 11L", others)  # GCAT's PLName: searchable though never the display name
        self.assertNotIn(name, others)
        self.assertEqual((cospar, type_, gone), ("2014-058A", "p", 0))
        self.assertEqual(self.rows["12842"][5], 1)  # SJ-2 reentered 1981
        self.assertEqual(self.rows["A12066"][4], "r")

    def test_the_separate_asset_is_the_same_index(self):
        import gzip
        self.assertEqual(json.loads(gzip.decompress(ASSETS[catshards.SEARCH_ASSET])), self.idx)


class Rules(unittest.TestCase):
    def setUp(self):
        self.note = SHARDS["rules.json"]

    def test_the_separate_asset_is_the_same_note(self):
        self.assertEqual(json.loads(ASSETS[catshards.RULES_ASSET]), self.note)

    def test_every_value_the_catalog_uses_is_explained(self):
        n = self.note
        for key, field, r in all_records(DOC):
            self.assertIn(r["source"], n["sources"], (key, field))
            self.assertIn(r["basis"], n["basis"], (key, field))
            if field == "names" and r.get("field"):
                self.assertIn(r["field"], n["name_fields"], (key, r["field"]))
            for flag in ("uncertain", "qualifier", "placeholder", "operator_code", "nocompare", "cited"):
                if flag in r:
                    self.assertIn(flag, n["flags"])
        for f in catshards.RECORD_FIELDS + ("name",):
            self.assertIn(f, n["fields"])
        for f in catalog.FLAGGED + ("gcat_catalog",):
            self.assertIn(f, n["disagreements"]["fields"])

    def test_sources_carry_label_citation_and_read(self):
        s = self.note["sources"]
        for src in ("space-track", "gcat-mcdowell", "celestrak-satcat", "wikidata"):
            self.assertTrue(s[src]["label"] and s[src]["citation"] and s[src]["read"], src)
        self.assertEqual(self.note["rank"], list(catalog.RANK))
        self.assertIn("swf-rpo", s)  # ranked though not read by the build; the page can still label alias citations


if __name__ == "__main__":
    unittest.main()
