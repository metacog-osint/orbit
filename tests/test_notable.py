"""What a GEO change did in words, the notable rule and the other names (orbit-2.26), on a real case: LUCH (OLYMP) 2
(55841) leaving 62 E in November 2026. The fixture is every element set of it in Orbit's public GEO release."""
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from orbit import archive, feed, lead, maneuver, names, notable  # noqa: E402
from tic_doctrine import contract, registers  # noqa: E402
import importlib.util  # noqa: E402


def _tool(name, file):  # tools/ is not on the path: tools/orbit.py would shadow the orbit package
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cli = _tool("orbit_cli_notable", "orbit.py")
geo_belt = _tool("geo_belt_notable", "geo_belt.py")

FIX = ROOT / "tests" / "fixtures"
NOW = datetime(2026, 11, 23, 22, 40, 4, tzinfo=timezone.utc)
AT = "2026-11-23T22:40:04Z"
GCAT_NAME = "Luch-5Kh No. 3"


def load():
    recs = json.loads((FIX / "luch2_sets_2026.json").read_text(encoding="utf-8"))["records"]
    store = maneuver.merge({}, recs, NOW)
    rep = maneuver.report(store, NOW)
    for e in rep["events"]:
        e.update({"gcat_name": GCAT_NAME, "state": "RU", "cc": "RU"})
    return store, rep["events"]


def roles():
    return notable.roles_index(json.loads((ROOT / "site_src" / "geo_roles.json").read_text(encoding="utf-8")))


def name_index():
    return names.index(json.loads((FIX / "catalog_names_20261117.json").read_text(encoding="utf-8")))


def text(line):
    return "".join(p if isinstance(p, str) else p["s"] if "s" in p else "[" + str(next(iter(p.values()))) + "]"
                   for p in line["parts"])


class Names(unittest.TestCase):
    def test_the_three_names_of_55841_stand_side_by_side(self):
        also = names.others(GCAT_NAME, name_index()[55841])
        self.assertEqual(also[0], "LUCH (OLYMP) 2")            # the catalog's display name first
        self.assertIn("LUCH-5X (OLYMP-K 2)", also)
        self.assertNotIn(GCAT_NAME, also)                      # the shown name is not repeated
        self.assertEqual(names.label(GCAT_NAME, also), "Luch-5Kh No. 3, also LUCH (OLYMP) 2 and LUCH-5X (OLYMP-K 2)")

    def test_case_and_punctuation_variants_uncertain_names_and_bare_numbers_are_left_out(self):
        also = names.others(GCAT_NAME, name_index()[55841])
        self.assertNotIn("Luch (Olymp) 2", also)               # "LUCH (OLYMP) 2" is already there
        self.assertNotIn("Luch-Olymp 2", also)
        self.assertFalse([n for n in also if n.endswith("?")])  # GCAT's "Yenisey-2 No. 13L?"
        rec = {"display": "COMPASS G2", "names": ["COMPASS G2", "34779", "Beidou-2 G2", "BEIDOU-2 G2"]}
        self.assertEqual(names.others("Beidou DW 2", rec), ["COMPASS G2", "Beidou-2 G2"])

    def test_a_joined_display_name_adds_nothing(self):
        rec = {"display": "USA 270 (Hornet 3)", "names": ["USA 270", "Hornet 3", "AFSPC-6 F1", "GSSAP 3"]}
        self.assertEqual(names.others("USA 270", rec), ["Hornet 3", "AFSPC-6 F1", "GSSAP 3"])
        self.assertEqual(names.label("USA 270", names.others("USA 270", rec)), "USA 270, also Hornet 3 and AFSPC-6 F1")
        kept = {"display": "LUCH-5X (OLYMP-K 2)", "names": ["LUCH-5X (OLYMP-K 2)", "Olymp-K 2"]}
        self.assertEqual(names.others("Luch-5Kh No. 3", kept)[0], "LUCH-5X (OLYMP-K 2)")   # its A is not shown: kept

    def test_no_index_row_gives_no_names(self):
        self.assertEqual(names.others("X", None), [])
        self.assertEqual(names.label("X", []), "X")


class WhatHappened(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store, cls.events = load()
        notable.enrich(cls.events, cls.store, roles(), name_index())
        cls.e = cls.events[0]

    def test_one_listed_change_across_the_gap(self):
        self.assertEqual(len(self.events), 1)
        self.assertEqual((self.e["from"], self.e["to"]), ("2026-10-15T15:56:16Z", "2026-11-22T15:37:18Z"))
        self.assertEqual(self.e["gap"]["hours"], 887.7)        # no public set from 15 Oct to 21 Nov

    def test_the_kind_uses_the_geo_boards_line_and_words(self):
        self.assertEqual(notable.DRIFT_KEPT, geo_belt.DRIFT_KEPT)
        self.assertEqual(notable.KEPT, geo_belt.ROUTINE)
        for b, a in ((0.0, 0.0), (0.0, -2.5), (-2.5, 0.0), (-2.5, -1.0)):
            self.assertEqual(notable.kind(b, a), geo_belt.change_kind({"drift": b, "i": 0.0}, {"drift": a, "i": 0.0}))
        self.assertEqual(self.e["geo"]["kind"], "started drifting")

    def test_longitude_drift_and_height(self):
        g = self.e["geo"]
        self.assertEqual((g["lon_before"], g["lon_after"]), (62.0, 58.19))
        self.assertEqual(g["drift_after"], -2.467)
        self.assertAlmostEqual(g["alt_km_after"], 193.2, delta=0.5)   # from the mean motion, 0.99588508 rev a day
        self.assertAlmostEqual(g["alt_km_before"], 0.6, delta=0.5)
        self.assertGreater(notable.alt_km(-1.0), 0)             # westward drift is a higher orbit
        self.assertLess(notable.alt_km(1.0), 0)

    def test_held_reaches_only_as_far_as_the_sets_orbit_holds(self):
        h = self.e["geo"]["held"]
        self.assertEqual(h["since"], "2026-07-01T18:01:36Z")   # the first set in the store, so the start is unknown
        self.assertTrue(h["first_held"])
        later = {"55841": {**self.store["55841"], "sets": self.store["55841"]["sets"][40:]}}
        _, ev = load()
        notable.enrich(ev, later, roles(), None)
        self.assertEqual(ev[0]["geo"]["held"]["since"], later["55841"]["sets"][0][0])

    def test_the_sentence(self):
        self.assertEqual(
            GCAT_NAME + " " + notable.text(self.e["what"]),
            "Luch-5Kh No. 3 left 62.00°E, where it had held position in every element set Orbit holds since "
            "2026-07-01, and is drifting west at 2.47° a day, about 193 km above geostationary altitude; at 58.19°E "
            "by the element set of 2026-11-22 15:37 UTC")
        for p in self.e["what"]:
            self.assertTrue(isinstance(p, str) or set(p) <= {"t", "d"}, p)

    def test_the_sentence_never_says_why_or_where_to(self):
        s = notable.text(self.e["what"]).lower()
        for word in ("toward", "target", "heading", "because", "likely", "will ", "warning"):
            self.assertNotIn(word, s)

    def test_other_kinds(self):
        def ev(b, a, lb=10.0, la=9.02):
            return {"from": "2026-12-01T00:00:00Z", "to": "2026-12-04T00:00:00Z",
                    "geo": {"lon_before": lb, "lon_after": la, "drift_before": b, "drift_after": a}}
        edge = notable.text(notable.describe(ev(-0.07, 0.12, 125.47, 125.46))["parts"])   # USA 270, live 23 Nov 2026
        self.assertTrue(edge.startswith("began to drift from 125.47°E east at 0.12° a day, about 9 km below"), edge)
        stop = notable.describe(ev(-2.47, -0.02))
        self.assertEqual(stop["kind"], "stopped drifting")
        self.assertIn("was drifting west at 2.47° a day and now holds 9.02°E", notable.text(stop["parts"]))
        slow = notable.describe(ev(-2.47, -1.2))
        self.assertEqual(slow["kind"], "drift rate changed")
        self.assertIn("slowed its drift west from 2.47° to 1.20° a day", notable.text(slow["parts"]))
        self.assertIn("sped up its drift west from 1.20° to 2.47°", notable.text(notable.describe(ev(-1.2, -2.47))["parts"]))
        self.assertIn("reversed its drift, from west at 0.50° a day to east at 0.40° a day",
                      notable.text(notable.describe(ev(-0.5, 0.4))["parts"]))
        kept = notable.describe(ev(0.01, -0.02, 62.0, 62.01))
        self.assertEqual(kept["kind"], "station-keeping")
        self.assertTrue(notable.text(kept["parts"]).startswith("holds 62.01°E"))
        self.assertIsNone(notable.describe({"from": "x", "to": "y"}))   # not geostationary: nothing added

    def test_a_carried_change_keeps_its_description_when_the_store_is_not_there(self):
        _, ev = load()
        notable.enrich(ev, self.store, roles(), name_index())
        before = json.dumps(ev[0], sort_keys=True)
        notable.enrich(ev, {}, roles(), None)                   # a run with no store and no name index
        self.assertEqual(json.dumps(ev[0], sort_keys=True), before)


class Notable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store, cls.events = load()
        notable.enrich(cls.events, cls.store, roles(), name_index())
        cls.e = cls.events[0]
        cls.snap = {"generated_at": AT, "lanes": {"maneuver": {"status": "ok"}},
                    "maneuvers": {"read_at": AT, "attribution": maneuver.ATTRIBUTION, "window_days": 30,
                                  "watched": 1, "events": cls.events}}

    def test_a_listed_role_and_more_than_station_keeping(self):
        self.assertEqual(self.e["notable"]["kind"], "started drifting")
        self.assertEqual(self.e["notable"]["role"], "inspection")
        self.assertIsNone(notable.mark(self.e, {}))             # no listed role: not notable
        kept = {"norad": 55841, "geo": {"kind": "station-keeping"}}
        self.assertIsNone(notable.mark(kept, roles()))
        edge = {"norad": 41744, "geo": {"kind": "started drifting", "drift_before": 0.03, "drift_after": 0.12}}
        self.assertIsNone(notable.mark(edge, roles()))          # USA 270, live 23 Nov 2026: across the line by a hair
        real = {"norad": 41745, "geo": {"kind": "drift rate changed", "drift_before": -4.37, "drift_after": -8.86}}
        self.assertEqual(notable.mark(real, roles())["kind"], "drift rate changed")
        self.assertIsNone(notable.mark({"norad": 55841}, roles()))   # not a geostationary change

    def test_every_listed_role_cites_a_source(self):
        for n, r in roles().items():
            self.assertTrue(r["sources"], n)

    def test_first_line_of_the_lead(self):
        doc = lead.build(self.snap)
        self.assertEqual(doc["lines"][0]["kind"], "notable")
        s = text(doc["lines"][0])
        self.assertTrue(s.startswith("Notable: Luch-5Kh No. 3, also LUCH (OLYMP) 2 and LUCH-5X (OLYMP-K 2) ([RU]; "
                                     "listed role on Orbit's GEO page: inspection) left 62.00°E"), s)
        self.assertIn("drifting west at 2.47° a day", s)
        self.assertIn("measured across a 37-day gap between element sets", s)
        self.assertNotIn("orbit_change", [x["kind"] for x in doc["lines"]])   # said once, not twice
        self.assertFalse(doc["nothing_new"])

    def test_the_line_goes_when_it_is_neither_new_nor_fresh(self):
        days = {"2026-11-20": {"maneuver": {"listed": {"55841:2026-10-15": {}}}}}   # first listed three days ago
        old = {**self.snap, "generated_at": "2026-11-25T22:40:04Z"}                 # and its newest set is 3 days old
        self.assertEqual(lead.notable_changes(old, {"days": days}, datetime(2026, 11, 25, 22, 40, tzinfo=timezone.utc)), [])
        fresh = lead.notable_changes(self.snap, {"days": days}, datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(len(fresh), 1)                         # a new set inside 24 hours brings it back

    def test_a_change_that_is_not_notable_says_what_happened_in_the_ordinary_line(self):
        _, ev = load()
        notable.enrich(ev, self.store, {}, name_index())        # no role list: nothing is notable
        doc = lead.build({**self.snap, "maneuvers": {**self.snap["maneuvers"], "events": ev}})
        self.assertEqual([x["kind"] for x in doc["lines"]], ["orbit_change"])
        s = text(doc["lines"][0])
        self.assertIn("([RU], GEO) left 62.00°E", s)
        self.assertIn(", 8.2 m/s between [2026-10-15T15:56:16Z] and [2026-11-22T15:37:18Z].", s)

    def test_the_feed_item(self):
        item = feed._maneuver_item(self.e, AT, AT, maneuver.ATTRIBUTION)["properties"]
        self.assertEqual(item["id"], "orbit:maneuver:55841:2026-10-15")   # the id does not change
        self.assertEqual(item["tier"], "routine")               # a higher tier is Tom's call
        self.assertTrue(item["title"].startswith(
            "Notable orbit change: Luch-5Kh No. 3, also LUCH (OLYMP) 2 and LUCH-5X (OLYMP-K 2) (GEO, RU): started "
            "drifting west at 2.47 deg/day from 62.00 E; "), item["title"])
        for name in ("Luch-5Kh No. 3", "LUCH (OLYMP) 2", "LUCH-5X (OLYMP-K 2)", "Olymp"):
            self.assertIn(name.lower(), item["title"].lower())  # any of the three names finds it (COP ignores case)
        self.assertTrue(item["summary"].startswith("Luch-5Kh No. 3 left 62.00°E"))
        self.assertIn("Also known as LUCH (OLYMP) 2; LUCH-5X (OLYMP-K 2); Olymp-K 2", item["summary"])
        self.assertIn("Notable is not a tier, a warning or a judgment of why", item["summary"])
        self.assertIn("not a confirmed manoeuvre", item["summary"])       # the approved wording stays
        self.assertEqual(item["measures"]["lon_before_deg"], 62.0)
        self.assertEqual(item["measures"]["drift_after_deg_day"], -2.467)

    def test_a_change_without_the_new_fields_reads_as_before(self):
        plain = {k: v for k, v in self.e.items() if k not in ("names", "what", "notable")}
        plain["geo"] = {k: self.e["geo"][k] for k in ("lon_before", "lon_after", "drift_before", "drift_after")}
        item = feed._maneuver_item(plain, AT, AT, maneuver.ATTRIBUTION)["properties"]
        self.assertEqual(item["title"], f"Orbit change: Luch-5Kh No. 3 (GEO, RU), {plain['dv_ms']:g} m/s in-track")
        self.assertTrue(item["summary"].startswith("Luch-5Kh No. 3 (catalog 55841"))

    def test_the_feed_lints_with_a_notable_item(self):
        doc = feed.build_feed({**self.snap, "launches": [], "upcoming": [], "reentries": []})
        regs = registers.ids(ROOT / "doctrine")
        mine = [f for f in doc["features"] if f["properties"]["id"].startswith("orbit:maneuver:")]
        self.assertEqual(len(mine), 1)
        for f in mine:
            self.assertEqual([m for _, sev, m in contract.check(f, regs) if sev == "error"], [])

    def test_the_archive_marks_it(self):
        doc = archive.record(None, self.snap)
        row = doc["days"]["2026-11-23"]["maneuver"]["listed"]["55841:2026-10-15"]
        self.assertEqual(row["notable"], "started drifting")

    def test_the_public_file(self):
        doc = notable.public(self.snap, roles(), feed.SITE)
        self.assertEqual(doc["schema"], "orbit-notable/1")
        self.assertEqual(len(doc["items"]), 1)
        it = doc["items"][0]
        self.assertEqual(it["id"], "orbit:maneuver:55841:2026-10-15")
        self.assertTrue(it["what"].startswith("Luch-5Kh No. 3 left 62.00°E"))
        self.assertTrue(it["what"].endswith("UTC."))
        self.assertEqual(it["names"][0], "LUCH (OLYMP) 2")
        self.assertTrue(it["role_sources"])
        self.assertEqual(it["link"], "https://orbit.theintelligence.company/object?n=55841")
        self.assertIn("not a warning", doc["rule"])
        self.assertEqual(notable.public({"generated_at": AT})["items"], [])   # no lane: an empty list, not an error


class EndOfCollect(unittest.TestCase):
    def test_describe_changes_reads_only_listed_objects_and_the_runs_name_index(self):
        store, events = load()
        store["99999"] = {"sets": [], "name": "never listed"}
        with tempfile.TemporaryDirectory() as d:
            data = Path(d) / "data"
            cli._st_write(data, "sets.json.gz", store)
            snap = {"maneuvers": {"events": events}}
            cli._RUN.clear()
            cli._describe_changes(ROOT, data, snap)             # the rpo lane did not read the index on this run
            self.assertNotIn("names", events[0])
            self.assertEqual(events[0]["notable"]["kind"], "started drifting")
            cli._RUN["names_doc"] = json.loads((FIX / "catalog_names_20261117.json").read_text(encoding="utf-8"))
            cli._describe_changes(ROOT, data, snap)
            self.assertEqual(events[0]["names"][0], "LUCH (OLYMP) 2")
            cli._RUN.clear()
            cli._describe_changes(ROOT, data, snap)             # a later run without the index keeps the names
            self.assertEqual(events[0]["names"][0], "LUCH (OLYMP) 2")
        self.assertIsNone(cli._describe_changes(ROOT, Path("nowhere"), {}))   # no changes: nothing to do

    def test_the_build_writes_the_public_file(self):
        store, events = load()
        notable.enrich(events, store, roles(), name_index())
        snap = {"generated_at": AT, "method_version": feed.METHOD, "lanes": {"maneuver": {"status": "ok"}},
                "maneuvers": {"read_at": AT, "attribution": maneuver.ATTRIBUTION, "window_days": 30, "watched": 1,
                              "events": events}, "launches": [], "upcoming": [], "reentries": []}
        tmp = Path(tempfile.mkdtemp())     # a copy, as the other build tests use: the build writes site/
        try:
            shutil.copytree(ROOT / "doctrine", tmp / "doctrine")
            shutil.copytree(ROOT / "site_src", tmp / "site_src", ignore=shutil.ignore_patterns("cesium"))
            (tmp / "data").mkdir()
            files = cli.build_site(tmp, snap)
            doc = json.loads((tmp / "site" / "data" / "notable.json").read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertIn("data/notable.json", files)
        self.assertEqual([i["norad"] for i in doc["items"]], [55841])


if __name__ == "__main__":
    unittest.main()
