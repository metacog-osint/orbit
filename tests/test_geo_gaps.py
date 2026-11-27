"""geo_gaps and the daily lead's GEO line (method orbit-2.40) on Orbit's own public GEO release: the day
files of 22 Oct 2026 (Luch (Olymp) 2's newest set passes 7 days old) and 21 Nov 2026 (its set comes back after
37 days), with 22, 24 and 26 Nov for what follows. Standard library only, offline."""
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import geo_gaps as GG  # noqa: E402
import geo_page  # noqa: E402
from orbit import lead  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "geo_set_gaps_2026.json")
with open(FIX, encoding="utf-8") as _f:
    D = json.load(_f)
ROLES = D["roles"]
ELSETS = {int(k): [dict(zip(D["elset_cols"], r)) for r in v] for k, v in D["elsets"].items()}
DOCS = [{"day": day, "fetched_utc": v["fetched_utc"], "regions": v["regions"]} for day, v in D["days"].items()]
READS = GG.first_reads(reversed(DOCS), ROLES)              # any order in: oldest day first out
OBJS = {int(k): {"name": v[0], "owner": v[1]} for k, v in D["names"].items()}


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def block(day, now):
    """The block as the GEO page's build would have made it from the day file of `day`."""
    rd = {k: [x for x in v if x[0] <= day] for k, v in READS.items()}
    return GG.build(ROLES, GG.held_by(ELSETS, READS, day), rd, OBJS, now, D["days"][day]["fetched_utc"], day)


def text(line):
    return "".join(p if isinstance(p, str) else p["s"] if "s" in p else "[" + str(next(iter(p.values()))) + "]"
                   for p in line["parts"])


def silent(b):
    return [o["name"] for o in b["objects"] if o["silent"]]


class October22(unittest.TestCase):
    """Day file of 22 Oct 2026 (imported from Noisefloor, so no read time): Luch 2's newest set, 15 Oct 15:56Z, passes
    7 days old at 15:56Z; SJ-25's, 15 Oct 18:06Z, at 18:06Z."""

    @classmethod
    def setUpClass(cls):
        cls.b = block("2026-10-22", utc(2026, 10, 22, 23, 0))

    def test_listed_with_set_time_and_age(self):
        self.assertEqual(silent(self.b), ["USA 271", "USA 270", "LUCH (OLYMP) 2", "SJ-25"])   # oldest set first
        luch = next(o for o in self.b["objects"] if o["norad"] == 55841)
        self.assertEqual(luch["newest"]["t"], "2026-10-15T15:56:16Z")
        self.assertEqual(luch["silent_since"], "2026-10-22T15:56:16Z")
        self.assertAlmostEqual(luch["newest"]["age_h"], 175.1, delta=0.1)
        self.assertAlmostEqual(luch["newest"]["lon"], 62.00, delta=0.02)
        self.assertEqual(luch["newest"]["first_read"]["day"], "2026-10-15")
        self.assertIsNone(self.b["read_utc"])

    def test_agrees_with_the_day_files_event(self):
        """The day file's own 'quiet' event (active payloads in the zone) names Luch 2 among the listed objects;
        SJ-25 sits in the crossing region, so only this list carries it."""
        self.assertEqual(D["days"]["2026-10-22"]["quiet"], [55841])
        self.assertEqual(D["days"]["2026-10-22"]["regions"]["62485"][0], "crossing")
        since = {o["norad"]: o["silent_since"][:10] for o in self.b["objects"] if o["silent"]}
        self.assertEqual(since[55841], "2026-10-22")
        self.assertEqual(since[62485], "2026-10-22")

    def test_lead_line(self):
        line = lead.geo_line(self.b, "2026-10-22T23:00:00Z")
        self.assertEqual(line["kind"], "geo_sets")
        t = text(line)
        self.assertIn("Listed GEO satellites now 7 days without a public element set: LUCH (OLYMP) 2 (newest set [2026-10-15T15:56:16Z]); "
                      "SJ-25 (newest set [2026-10-15T18:06:06Z]).", t)
        self.assertNotIn("USA 270", t)                     # its 7 days passed on 19 Oct, not in these 24 hours
        self.assertIn("No public set is not the same as no movement.", t)
        self.assertNotIn("public set again", t)
        self.assertIn("Orbit's GEO day file of [2026-10-22].", t)   # no read time recorded: the day file's day
        self.assertEqual(line["href"], "geo.html#set-gaps")
        self.assertIn({"s": "LUCH (OLYMP) 2", "o": "55841"}, line["parts"])

    def test_before_the_mark(self):
        self.assertIsNone(lead.geo_line(self.b, "2026-10-22T12:00:00Z"))


class November21(unittest.TestCase):
    """Day file of 21 Nov 2026, read 20:57Z: the first public sets since 15 Oct for Luch 2 and SJ-25."""

    @classmethod
    def setUpClass(cls):
        cls.b = block("2026-11-21", utc(2026, 11, 22, 0, 55))

    def test_back_after_37_days(self):
        new = [x for x in self.b["back"] if x["first_read"]["day"] == "2026-11-21"]
        self.assertEqual(sorted(x["name"] for x in new), ["LUCH (OLYMP) 2", "SJ-25"])
        luch = next(x for x in new if x["norad"] == 55841)
        self.assertEqual(luch["before"]["t"], "2026-10-15T15:56:16Z")
        self.assertEqual(luch["after"]["t"], "2026-11-21T15:41:09Z")
        self.assertEqual(luch["gap_days"], 37.0)
        self.assertFalse(luch["late"])
        self.assertEqual(luch["first_read"]["read_utc"], "2026-11-21T20:57:00Z")
        self.assertAlmostEqual(luch["before"]["lon"], 62.00, delta=0.02)
        self.assertAlmostEqual(luch["after"]["lon"], 60.29, delta=0.02)   # it had left 62 E inside the gap
        self.assertAlmostEqual(luch["after"]["drift"], -1.62, delta=0.01)

    def test_no_longer_listed(self):
        self.assertEqual(silent(self.b), ["USA 270", "USA 271"])
        self.assertEqual(self.b["read_utc"], "2026-11-21T20:57:00Z")

    def test_lead_line(self):
        t = text(lead.geo_line(self.b, "2026-11-22T00:55:00Z"))
        self.assertTrue(t.startswith("Listed GEO satellites with a public element set again, after 7 days or more with none newer in Orbit's files:"), t)
        self.assertIn("LUCH (OLYMP) 2 (set of [2026-11-21T15:41:09Z], the first since [2026-10-15T15:56:16Z], 37 days apart; "
                      "62.00° E then, 60.29° E at the new set)", t)
        self.assertIn("SJ-25", t)
        self.assertNotIn("now 7 days", t)
        self.assertIn("Orbit's GEO files read at [2026-11-21T20:57:00Z].", t)

    def test_gone_from_the_lead_a_day_later(self):
        """22 Nov, read 21:06Z: USA 324 and USA 325 pass 7 days (the day file's 'quiet' events agree); the
        returns of 21 Nov 20:57Z are over 24 hours old by 23:00Z."""
        b = block("2026-11-22", utc(2026, 11, 22, 23, 0))
        self.assertEqual(D["days"]["2026-11-22"]["quiet"], [51280, 51281])
        t = text(lead.geo_line(b, "2026-11-22T23:00:00Z"))
        self.assertIn("now 7 days without a public element set: USA 324 (newest set [2026-11-15T09:27:18Z]); USA 325", t)
        self.assertNotIn("public set again", t)


class November26(unittest.TestCase):
    """The build of 27 Nov 2026 03:00Z on the day file of 26 Nov: the count the item started from."""

    def test_three_listed(self):
        b = block("2026-11-26", utc(2026, 11, 27, 3, 0))
        self.assertEqual(silent(b), ["USA 270", "USA 271", "USA 325"])
        self.assertEqual([round(o["newest"]["age_h"] / 24, 1) for o in b["objects"] if o["silent"]], [24.8, 24.6, 11.7])
        usa271 = next(o for o in b["objects"] if o["norad"] == 41745)
        self.assertEqual(usa271["gaps"]["count"], 2)
        self.assertEqual(usa271["gaps"]["longest_days"], 17.3)

    def test_late_set_ends_a_listing(self):
        """MEV-1's set of 22 Nov 23:29Z reached Orbit's files on 24 Nov (23:57Z read), after its set of 16 Nov
        18:43Z had passed 7 days old there: listed as back, marked late, 6.2 days apart."""
        b = block("2026-11-24", utc(2026, 11, 25, 0, 55))
        mev = next(x for x in b["back"] if x["norad"] == 44625 and x["first_read"]["day"] == "2026-11-24")
        self.assertTrue(mev["late"])
        self.assertEqual(mev["gap_days"], 6.2)
        self.assertEqual(mev["none_newer_days"], 8.2)
        t = text(lead.geo_line(b, "2026-11-25T00:55:00Z"))
        self.assertIn("MEV-1 (set of [2026-11-22T23:29:33Z], the first since [2026-11-16T18:43:", t)
        self.assertIn("6.2 days apart; it reached Orbit's files on [2026-11-24]", t)
        self.assertIn("USA 324 (set of [2026-11-24T11:38:00Z]", t)

    def test_imported_files_never_judged_late(self):
        """The imported day files hold no read time, so only sets 7 days or more apart count there."""
        b = block("2026-10-22", utc(2026, 10, 22, 23, 0))
        self.assertTrue(all(not x["late"] for x in b["back"]))


class LeadMerge(unittest.TestCase):
    def snap(self):
        return {"generated_at": "2026-11-22T00:55:00Z",
                "lanes": {"decay": {"status": "ok"}, "maneuver": {"status": "failed", "from_previous": True}},
                "maneuvers": {"read_at": "2026-11-21T00:00:00Z", "events": [
                    {"norad": 55841, "name": "LUCH (OLYMP) 2", "from": "2026-10-15T15:56:16Z", "to": "2026-11-21T15:41:09Z",
                     "dv_ms": 8.5, "notable": {"role": "inspection", "kind": "started drifting"}, "what": ["moved"]}]}}

    def test_pending_until_the_geo_step(self):
        doc = lead.merge_geo(lead.build(self.snap()), dict(lead.GEO_PENDING))
        self.assertEqual([x["kind"] for x in doc["lines"]], ["notable", "gap", "gap"])
        self.assertIn("were not checked on this run", text(doc["lines"][-1]))
        line = lead.geo_line(block("2026-11-21", utc(2026, 11, 22, 0, 55)), doc["at"])
        lead.merge_geo(doc, line)
        self.assertEqual([x["kind"] for x in doc["lines"]], ["notable", "geo_sets", "gap"])   # after the notable line
        once = json.dumps(doc)
        lead.merge_geo(doc, line)
        self.assertEqual(json.dumps(doc), once)                                               # replaces, never adds
        self.assertFalse(doc["nothing_new"])
        lead.merge_geo(doc, None)
        self.assertEqual([x["kind"] for x in doc["lines"]], ["notable", "gap"])

    def test_cap(self):
        doc = {"at": "2026-11-22T00:55:00Z", "lines": [{"kind": "breakup", "parts": []}] * lead.MAX_LINES +
               [{"kind": "gap", "parts": []}]}
        lead.merge_geo(doc, {"kind": "geo_sets", "geo": True, "parts": []})
        self.assertEqual(len(doc["lines"]), lead.MAX_LINES + 1)
        self.assertEqual(doc["lines"][0]["kind"], "geo_sets")
        self.assertEqual(doc["lines"][-1]["kind"], "gap")

    def test_stale_and_failed(self):
        b = block("2026-11-21", utc(2026, 11, 22, 0, 55))
        st = lead.geo_line(b, "2026-11-23T13:00:00Z")      # 40 hours after the read
        self.assertEqual(st["kind"], "stale")
        self.assertIn("Orbit's GEO files were last read at [2026-11-21T20:57:00Z] (about 40 hours ago)", text(st))
        bad = lead.geo_line({"error": "ValueError: x"}, "2026-11-22T00:55:00Z")
        self.assertEqual(bad["kind"], "gap")
        self.assertIn("(ValueError: x)", text(bad))


class Wiring(unittest.TestCase):
    def test_set_gaps_from_release_files(self):
        """geo_page.set_gaps reads the day files next to the newest (none past it) and the roles file."""
        with tempfile.TemporaryDirectory() as d:
            for day in ("2026-11-19", "2026-11-20", "2026-11-21", "2026-11-22"):
                with open(os.path.join(d, f"{day}.geo-region.json"), "w", encoding="utf-8") as f:
                    json.dump({"day": day, "fetched_utc": D["days"][day]["fetched_utc"], "regions": D["days"][day]["regions"]}, f)
            region = {"day": "2026-11-21", "fetched_utc": "2026-11-21T20:57Z", "object_cols": ["norad", "name", "owner", "region"],
                      "objects": [[int(k), v[0], v[1], D["days"]["2026-11-21"]["regions"][k][0]] for k, v in D["names"].items()]}
            b = geo_page.set_gaps(d, region, GG.held_by(ELSETS, READS, "2026-11-21"), datetime(2026, 11, 22, 0, 55))
        self.assertNotIn("error", b)
        self.assertEqual(sorted(x["name"] for x in b["back"]), ["LUCH (OLYMP) 2", "SJ-25"])   # the 20 Nov file is the one before
        self.assertEqual(b["read_utc"], "2026-11-21T20:57:00Z")

    def test_add_lead_to_site_and_archive(self):
        b = block("2026-11-21", utc(2026, 11, 22, 0, 55))
        at = "2026-11-22T00:55:00Z"
        mine = lead.merge_geo({"at": at, "hours": 24, "lines": [], "nothing_new": True}, dict(lead.GEO_PENDING))
        with tempfile.TemporaryDirectory() as d:
            site, data = os.path.join(d, "site"), os.path.join(d, "data")
            os.makedirs(os.path.join(site, "data")); os.makedirs(os.path.join(data, "state"))
            with open(os.path.join(site, "data", "snapshot.json"), "w", encoding="utf-8") as f:
                json.dump({"generated_at": at, "lead": mine}, f)
            arc = {"schema": "orbit-archive/1", "days": {"2026-11-22": {"runs": 1, "lead": mine}}}
            other = {"schema": "orbit-archive/1", "days": {"2026-11-22": {"runs": 2, "lead": dict(mine, at="2026-11-22T06:55:00Z")}}}
            for p, doc in ((os.path.join(data, "state", "daily_archive.json"), arc), (os.path.join(site, "data", "archive.json"), other)):
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(doc, f)
            line = geo_page.add_lead(site, b, data)
            self.assertEqual(line["kind"], "geo_sets")
            with open(os.path.join(site, "data", "snapshot.json"), encoding="utf-8") as f:
                self.assertEqual([x["kind"] for x in json.load(f)["lead"]["lines"]], ["geo_sets"])
            with open(os.path.join(data, "state", "daily_archive.json"), encoding="utf-8") as f:
                self.assertEqual([x["kind"] for x in json.load(f)["days"]["2026-11-22"]["lead"]["lines"]], ["geo_sets"])
            with open(os.path.join(site, "data", "archive.json"), encoding="utf-8") as f:   # another run's lead: untouched
                self.assertEqual([x["kind"] for x in json.load(f)["days"]["2026-11-22"]["lead"]["lines"]], ["gap"])


class Wording(unittest.TestCase):
    """About the source, never the satellite: no 'quiet', 'inactive' or 'dormant', and no likelihood words."""
    BAD = ("quiet", "inactive", "dormant", "silent", "likely", "probab", "expected", "parked")

    def check(self, s, where):
        for w in self.BAD:
            self.assertNotIn(w, s.lower(), f"{w!r} in {where}")

    def test_lead_and_note(self):
        self.check(GG.NOTE, "NOTE")
        for day, at in (("2026-10-22", "2026-10-22T23:00:00Z"), ("2026-11-21", "2026-11-22T00:55:00Z"),
                        ("2026-11-24", "2026-11-25T00:55:00Z")):
            self.check(text(lead.geo_line(block(day, lead._dt(at)), at)), day)

    def test_page_section(self):
        with open(os.path.join(ROOT, "site_src", "geo", "globe.js"), encoding="utf-8") as f:
            js = f.read()
        part = js[js.index("const daysTxt"):js.index('document.addEventListener("click", (e) => {\n    const t = e.target.closest("button.mv-tt")')]
        strings = re.findall(r'"([^"\n]*)"', part) + re.findall(r"'([^'\n]*)'", part)
        self.check(" ".join(strings), "globe.js gapCards")
        self.assertIn("No public set is not the same as no movement.", part)
        with open(os.path.join(ROOT, "site_src", "geo.html"), encoding="utf-8") as f:
            html = f.read()
        sec = html[html.index('<section class="card" id="set-gaps"'):]
        sec = sec[:sec.index("</section>")]
        self.check(sec, "geo.html #set-gaps")
        self.assertIn("no public set is not the same as no movement", sec)
        self.assertIn('href="#set-gaps"', html)


if __name__ == "__main__":
    unittest.main()
