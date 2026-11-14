"""Offline tests for Orbit. Fixtures in tests/fixtures/ are real replies from 13 Nov 2026, cut down:
GCAT tables (CC BY 4.0, J. McDowell, planet4589.org/space/gcat) and four Launch Library 2 records."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from orbit import feed, fetch, gcat, launches, navwarn  # noqa: E402
from tic_doctrine import contract, registers  # noqa: E402
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("orbit_cli", ROOT / "tools" / "orbit.py")
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)

FIX = ROOT / "tests" / "fixtures"
TODAY = date(2026, 11, 13)
NOW = datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc)
FILES = {"satcat": "satcat.tsv", "satcat100k": "satcat100k.tsv", "auxcat": "auxcat.tsv", "tmpcat": "tmpcat.tsv",
         "launch": "launch.tsv", "sites": "sites.tsv", "orgs": "orgs.tsv"}


def body(name: str) -> bytes:
    return (FIX / name).read_bytes()


def tables() -> dict:
    return {c: gcat.parse_tsv(body(FILES[c])) for c in gcat.CATALOGS}


class Dates(unittest.TestCase):
    def test_vague_dates(self):
        self.assertEqual(gcat.vague_date("2026 Nov 12 0436:30"),
                         {"date": "2026-11-12", "time": "2026-11-12T04:36:30Z", "uncertain": False})
        self.assertEqual(gcat.vague_date("2026 Nov  7 1325?"),
                         {"date": "2026-11-07", "time": "2026-11-07T13:25:00Z", "uncertain": True})
        self.assertEqual(gcat.vague_date("2026 Nov  4?")["date"], "2026-11-04")
        self.assertIsNone(gcat.vague_date("1957 Nov?")["date"])
        self.assertIsNone(gcat.vague_date("-")["date"])

    def test_state_codes(self):
        self.assertEqual(gcat.iso_country("F"), "FR")
        self.assertEqual(gcat.iso_country("SU"), "RU")
        self.assertEqual(gcat.iso_country("UK"), "GB")
        self.assertEqual(gcat.iso_country("UAE"), "AE")
        self.assertEqual(gcat.iso_country("CN"), "CN")
        self.assertIsNone(gcat.iso_country("I-ESA"))
        self.assertIsNone(gcat.iso_country("X"))


class Catalog(unittest.TestCase):
    def setUp(self):
        self.objs = gcat.objects(tables())
        self.sites = gcat.sites_table(gcat.parse_tsv(body("sites.tsv")))
        self.orgs = gcat.orgs_table(gcat.parse_tsv(body("orgs.tsv")))

    def test_every_catalog_is_read(self):
        cats = {o["cat"] for o in self.objs}
        self.assertEqual(cats, set(gcat.CATALOGS))
        self.assertEqual(gcat.updated_stamp(body("satcat.tsv")), "2026 Nov 13 0021:52")

    def test_recent_launches_find_payloads_in_new_and_temporary_catalogs(self):
        got = {x["launch_tag"]: x for x in gcat.recent_launches(gcat.parse_tsv(body("launch.tsv")), self.objs,
                                                                self.sites, TODAY)}
        tl = got["2026-254"]  # Chang Zheng 2D, Tanluzhe, 11 Nov: one numbered object, three temporary ones
        self.assertEqual(tl["site"]["name"], "Jiuquan")
        self.assertEqual(sorted(p["name"] for p in tl["payloads"]),
                         ["Tanluzhe A", "Tanluzhe B", "Tanluzhe C", "Tanluzhe D"])
        self.assertEqual(got["2026-255"]["time"], "2026-11-12T04:36:30Z")
        self.assertNotIn("2026-S267", got)  # a suborbital test is not an orbital launch
        newest = list(got)[0]
        self.assertEqual(newest, "2026-255")

    def test_launchers_and_site_countries(self):
        got = {x["launch_tag"]: x for x in gcat.recent_launches(gcat.parse_tsv(body("launch.tsv")), self.objs,
                                                                self.sites, TODAY, orgs=self.orgs)}
        f9 = got["2026-255"]
        self.assertEqual([(l["code"], l["country"]) for l in f9["launchers"]], [("SPX", "US")])
        self.assertEqual(f9["site"]["country"], "US")
        self.assertEqual(f9["payloads"][0]["country"], "US")
        self.assertEqual({l["country"] for l in got["2026-254"]["launchers"]}, {"CN"})
        joint = next(x for x in got.values() if "/" in x["agency"])
        self.assertEqual(len(joint["launchers"]), 2)  # 'ZHSH/CALT' names two agencies
        self.assertEqual(gcat.launchers("NOSUCH", self.orgs), [{"code": "NOSUCH", "name": "NOSUCH", "state": "",
                                                                "country": None}])

    def test_hygiene_counts_only_us_catalog_numbers_for_duplicates(self):
        h = gcat.hygiene(self.objs)
        # auxcat A00002 carries 00003, the number of the object it is associated with: not a duplicate claim
        self.assertNotIn("00003", h["duplicate_catalog_numbers"])
        self.assertIn("satcat100k", h["objects_by_catalog"])
        owners = h["in_orbit_owners"]
        self.assertTrue(owners)
        self.assertTrue(all(o["payloads"] <= o["total"] for o in owners))
        self.assertEqual([o["total"] for o in owners], sorted((o["total"] for o in owners), reverse=True))
        su = [o for o in owners if o["state"] == "SU"]
        self.assertTrue(all(o["country"] == "RU" for o in su))  # SU kept as its own row, placed in Russia

    def test_diff_reports_late_objects_owner_changes_and_ignores_temporary_graduations(self):
        idx = gcat.build_index(self.objs)
        prev = dict(idx)
        satcat_old = next(j for j in idx if j == "S00005")
        prev[satcat_old] = list(prev[satcat_old])
        prev[satcat_old][gcat.INDEX_FIELDS.index("state")] = "UK"   # owner state changed since last reading
        prev["T99999"] = ["tmpcat", None, "2026-254", "P", "Gone temp", "2026 Nov 11", "-", "-", "AO", "CAS", "CN", "-"]
        prev["S99998"] = ["satcat", "99998", "1990-001", "D", "Deleted deb", "1990 Jan 1", "-", "-", "O", "X", "US", "-"]
        old_piece = next(o for o in self.objs if o["jcat"] == "S00002")
        prev.pop(old_piece["jcat"])  # an object from 1957 that is new to this reading
        fresh = next(o for o in self.objs if o["launch_tag"] == "2026-255")
        prev.pop(fresh["jcat"])
        d = gcat.diff(prev, self.objs, TODAY)
        self.assertEqual(d["added"], 2)
        self.assertEqual(d["added_late"], 1)
        self.assertEqual(d["added_fresh"], 1)
        self.assertEqual(d["late_groups"][0]["launch_tag"], old_piece["launch_tag"])
        self.assertEqual(d["removed"], 1)
        self.assertEqual(d["temporary_entries_closed"], 1)
        self.assertEqual(d["owner_changes"][0]["fields"]["state"], ["UK", "US"])

    def test_reentries_window(self):
        rows = gcat.recent_reentries(self.objs, TODAY, days=7)
        self.assertTrue(rows)
        self.assertTrue(all(r["reentry_date"] >= "2026-11-06" for r in rows))
        self.assertTrue(all(r["status"] in gcat.GONE for r in rows))

    def test_not_a_gcat_table(self):
        with self.assertRaises(ValueError):
            gcat.parse_tsv(b"<html>maintenance</html>")


class Upcoming(unittest.TestCase):
    def test_parse_and_window(self):
        rows = launches.parse(body("ll2_upcoming.json"))
        self.assertEqual(len(rows), 4)
        soyuz = next(r for r in rows if r["name"].startswith("Soyuz 2.1b/Fregat-M"))
        self.assertEqual(soyuz["pad_country"], "RU")
        self.assertEqual(soyuz["provider_countries"], ["RU"])
        electron = next(r for r in rows if r["name"].startswith("Electron"))
        self.assertEqual((electron["provider_countries"], electron["pad_country"]), (["US"], "NZ"))
        self.assertIsNotNone(soyuz["lat"])
        self.assertTrue(all(r["net"] for r in rows))
        later = launches.within(rows, datetime(2026, 11, 30, tzinfo=timezone.utc))
        self.assertEqual(later, [])
        self.assertIn("net__lte=2026-11-27", launches.url(NOW))
        self.assertIn("mode=detailed", launches.url(NOW))

    def test_bad_reply(self):
        with self.assertRaises(ValueError):
            launches.parse(b'{"detail": "Request was throttled."}')


class EndToEnd(unittest.TestCase):
    """collect -> build -> check on a temporary copy, with every network call answered from fixtures."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(ROOT / "doctrine", self.tmp / "doctrine")
        shutil.copytree(ROOT / "site_src", self.tmp / "site_src")
        self.calls = []
        self.stamp = "Fri, 13 Nov 2026 00:23:02 GMT"
        self.fail = False
        by_url = {u: FILES[name] for name, u in gcat.URLS.items()}

        def getter(url, timeout=60):
            self.calls.append(url)
            if self.fail:
                raise OSError("network down")
            if url in by_url:
                return body(by_url[url])
            if url.startswith(launches.API):
                return body("ll2_upcoming.json")
            if url.startswith(navwarn.NGA_BASE):
                return body("navwarn/" + url.rsplit("/", 1)[1])
            if "disp_warnings.cgi" in url:
                return body("navwarn/jcg_" + url.rsplit("TANA=", 1)[1].split("&")[0] + ".html")
            if "/warnings.cgi" in url:
                return body("navwarn/jcg_list.xml")
            raise AssertionError(url)

        self.getter = getter
        self.header = lambda url: self.stamp
        self.patches = [mock.patch.object(gcat, "today_utc", return_value=TODAY),
                        mock.patch.object(launches, "now_utc", return_value=NOW),
                        mock.patch.object(fetch, "now_utc", return_value="2026-11-13T18:00:00Z")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_collect(self, **kw):
        return cli.collect(self.tmp, getter=self.getter, header=self.header, **kw)

    def test_full_cycle(self):
        snap = self.run_collect()
        self.assertEqual(snap["lanes"]["catalog"]["status"], "ok")
        self.assertEqual(snap["lanes"]["upcoming"]["status"], "ok")
        self.assertEqual(snap["lanes"]["navwarn"]["status"], "ok")
        self.assertEqual(snap["navwarn"]["sources"]["jcg"]["status"], "ok")
        self.assertTrue(snap["navwarn"]["areas"])
        self.assertEqual(snap["catalog_changes"], {})  # first reading only sets the baseline
        self.assertTrue((self.tmp / "data" / "state" / "catalog_index.json.gz").exists())

        # Same Last-Modified dates: GCAT is not downloaded again.
        self.calls.clear()
        snap2 = self.run_collect()
        self.assertEqual(snap2["lanes"]["catalog"]["status"], "unchanged")
        self.assertFalse([c for c in self.calls if "planet4589" in c])
        self.assertEqual(snap2["launches"], snap["launches"])

        # New dates: GCAT is read and compared with the stored index.
        self.stamp = "Sat, 14 Nov 2026 00:23:02 GMT"
        snap3 = self.run_collect()
        self.assertEqual(snap3["catalog_changes"]["added"], 0)
        self.assertIn("previous_reading_at", snap3["catalog_changes"])

        cli.build_site(self.tmp)
        self.assertEqual(cli.check_all(self.tmp), [])
        doc = json.loads((self.tmp / "site" / "data" / "feed.geojson").read_text(encoding="utf-8"))
        ids = [f["properties"]["id"] for f in doc["features"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(any(i.startswith("orbit:launch:") for i in ids))
        self.assertTrue(any(i.startswith("orbit:upcoming:") for i in ids))
        for f in doc["features"]:
            p = f["properties"]
            self.assertEqual(p["kind"], "observation")
            self.assertEqual(p["tier"], "routine")
            self.assertNotIn("probability", p)
        ariane = next(f for f in doc["features"] if "Ariane" in f["properties"]["title"])
        self.assertEqual(ariane["properties"]["countries"], ["FR"])  # Kourou: French Guiana, drawn as France

    def test_failed_lane_keeps_last_good_copy(self):
        good = self.run_collect()
        self.fail = True
        self.stamp = "Sat, 14 Nov 2026 00:23:02 GMT"
        snap = self.run_collect()
        self.assertEqual(snap["lanes"]["catalog"]["status"], "failed")
        self.assertTrue(snap["lanes"]["catalog"]["from_previous"])
        self.assertEqual(snap["launches"], good["launches"])
        self.assertEqual(snap["lanes"]["upcoming"]["status"], "failed")

    def test_short_reading_is_refused(self):
        self.run_collect()
        idx_path = self.tmp / "data" / "state" / "catalog_index.json.gz"
        import gzip
        doc = json.loads(gzip.decompress(idx_path.read_bytes()))
        for i in range(5000):  # pretend the last reading had far more objects
            doc["objects"][f"S9{i:05d}"] = ["satcat", None, "1990-001", "D", "x", "1990 Jan 1", "-", "-", "O", "X", "US", "-"]
        idx_path.write_bytes(gzip.compress(json.dumps(doc).encode()))
        self.stamp = "Sat, 14 Nov 2026 00:23:02 GMT"
        snap = self.run_collect()
        self.assertEqual(snap["lanes"]["catalog"]["status"], "failed")
        self.assertIn("short reading", snap["lanes"]["catalog"]["error"])

    def test_build_refuses_without_snapshot(self):
        with self.assertRaises(SystemExit):
            cli.build_site(self.tmp)


NW = FIX / "navwarn"
NOW_NW = datetime(2026, 11, 13, 23, 0, tzinfo=timezone.utc)


class NavWarnings(unittest.TestCase):
    """Real NGA memoranda and NAVAREA XI messages, 13 Nov 2026."""

    def all_warnings(self):
        out = []
        for area, url in navwarn.NGA_MEMOS.items():
            out += navwarn.parse_memo((NW / url.rsplit("/", 1)[1]).read_bytes(), area, NOW_NW)["warnings"]
        for it in navwarn.jcg_wanted(navwarn.parse_jcg_list((NW / "jcg_list.xml").read_bytes())):
            w = navwarn.parse_jcg_message((NW / f"jcg_{it['tana']}.html").read_bytes(), it)
            if w:
                out.append(w)
        return out

    def test_memo_header_and_launch_filter(self):
        memo = navwarn.parse_memo((NW / "DailyMemPAC.txt").read_bytes(), "HYDROPAC", NOW_NW)
        self.assertEqual(memo["as_of"], "2026-11-13T17:05:00Z")
        ids = {w["id"] for w in memo["warnings"]}
        self.assertIn("HYDROPAC 3315/26", ids)  # India, rocket launching
        self.assertNotIn("HYDROPAC 3316/26", ids)  # the India hazardous-operations box with no launch words
        for w in memo["warnings"]:
            self.assertRegex(w["hazard"], "rocket|space|reentry")

    def test_explicit_single_window_and_expiry(self):
        w = next(x for x in self.all_warnings() if x["id"] == "HYDROPAC 3315/26")
        self.assertEqual(w["windows"], [{"start": "2026-11-18T05:30:00Z", "end": "2026-11-18T07:00:00Z"}])
        self.assertEqual(w["window_mode"], "single")
        self.assertEqual(w["expires"], "2026-11-18T08:00:00Z")
        self.assertEqual(w["regions"], ["EASTERN INDIAN OCEAN", "INDIA"])
        self.assertEqual(len(w["areas"][0]["coords"]), 8)
        self.assertAlmostEqual(w["areas"][0]["coords"][0][1], 8 + 31.98 / 60, places=3)

    def test_daily_windows_cross_midnight(self):
        w = next(x for x in self.all_warnings() if x["id"] == "HYDROPAC 3251/26")  # 2215Z TO 0700Z DAILY 13 THRU 26
        self.assertEqual(w["window_mode"], "daily")
        self.assertEqual(len(w["windows"]), 14)
        self.assertEqual(w["windows"][0], {"start": "2026-11-13T22:15:00Z", "end": "2026-11-14T07:00:00Z"})

    def test_alternates_and_lettered_areas(self):
        w = next(x for x in self.all_warnings() if x["id"] == "NAVAREA IV 1078/26")
        self.assertEqual(w["window_mode"], "alternates")
        self.assertEqual(w["windows"][0]["start"], "2026-11-13T17:54:00Z")
        self.assertEqual(len(w["windows"]), 7)
        self.assertEqual([a["label"] for a in w["areas"]], ["A", "B", "C"])
        x = next(x for x in self.all_warnings() if x["id"] == "NAVAREA XII 801/26")  # windows per area
        self.assertEqual(len(x["windows"]), 7)  # areas opening together are one window
        self.assertEqual(x["windows"][0], {"start": "2026-11-18T03:14:00Z", "end": "2026-11-18T07:57:00Z"})
        self.assertEqual(x["cancels"], ["NAVAREA XII 785/26"])

    def test_navarea_xi_message_jst_and_cancellation(self):
        ws = {w["id"]: w for w in self.all_warnings()}
        w = ws["NAVAREA XI 0504/26"]
        self.assertEqual(w["issued"], "2026-11-09T12:00:00Z")  # 21:00 JST
        self.assertEqual(w["windows"][0], {"start": "2026-11-14T01:30:00Z", "end": "2026-11-14T05:01:00Z"})
        self.assertEqual(ws["NAVAREA XI 0511/26"]["hazard"], "rocket launching suspended")
        self.assertEqual(ws["NAVAREA XI 0511/26"]["cancels"], ["NAVAREA XI 0508/26"])

    def test_area_across_the_antimeridian_stays_one_shape(self):
        w = next(x for x in self.all_warnings() if x["id"] == "NAVAREA XI 0504/26")
        lons = [c[0] for c in w["areas"][0]["coords"]]
        self.assertTrue(all(abs(a - b) < 180 for a, b in zip(lons, lons[1:])))
        self.assertGreater(max(lons), 180)

    def test_rebroadcasts_group_and_vertex_differences_are_counted(self):
        groups = navwarn.group(navwarn.current(self.all_warnings(), NOW_NW))
        ids = [[b["id"] for b in g["broadcasts"]] for g in groups]
        self.assertIn(["NAVAREA XI 0504/26", "NAVAREA XII 788/26", "HYDROPAC 3257/26"], ids)
        micronesia = next(g for g in groups if g["broadcasts"][0]["id"] == "NAVAREA XI 0507/26")
        self.assertEqual(micronesia["vertex_differences"], 1)  # 178-12E in NAVAREA XI, 178-21E in NGA's copies
        self.assertEqual(len(ids), len({i for g in ids for i in g}) - 5)  # 25 warnings, 20 areas

    def test_current_drops_cancelled_warnings(self):
        later = datetime(2026, 11, 25, 0, 0, tzinfo=timezone.utc)
        left = {w["id"] for w in navwarn.current(self.all_warnings(), later)}
        self.assertNotIn("HYDROPAC 3315/26", left)
        self.assertIn("HYDROPAC 3251/26", left)


class Registers(unittest.TestCase):
    def test_doctrine_registers(self):
        self.assertEqual(registers.check(ROOT / "doctrine"), [])

    def test_page_sources_carry_grades_for_every_lane(self):
        doc = cli.sources_doc(ROOT)
        by_id = {s["id"]: s for s in doc["sources"]}
        # excluded sources (Space-Track, CelesTrak) stay off the page
        self.assertEqual(set(by_id), {"gcat-mcdowell", "ll2-thespacedevs", "nga-msi", "jcg-navarea11"})
        self.assertEqual(by_id["gcat-mcdowell"]["grade"], "A2")
        self.assertEqual(by_id["gcat-mcdowell"]["reliability"], "Completely reliable")
        self.assertEqual(by_id["ll2-thespacedevs"]["grade"], "B2")
        self.assertEqual(by_id["ll2-thespacedevs"]["credibility"], "Probably true")
        self.assertEqual({lane for s in doc["sources"] for lane in s["lanes"]}, set(cli.LANE_FIELDS))
        self.assertTrue(all(s["grade"] for s in doc["sources"]))

    def test_feed_items_lint(self):
        snap = json.loads((FIX / "ll2_upcoming.json").read_text(encoding="utf-8"))
        rows = launches.parse(json.dumps(snap).encode())
        doc = feed.build_feed({"generated_at": "2026-11-13T18:00:00Z", "upcoming": rows, "lanes": {}})
        regs = registers.ids(ROOT / "doctrine")
        for f in doc["features"]:
            errs = [m for _, sev, m in contract.check(f, regs) if sev == "error"]
            self.assertEqual(errs, [], f["properties"]["id"])


if __name__ == "__main__":
    unittest.main()
