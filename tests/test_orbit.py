"""Offline tests for Orbit. Fixtures in tests/fixtures/ are real replies from 13 Nov 2026, cut down:
GCAT tables (CC BY 4.0, J. McDowell, planet4589.org/space/gcat) and four Launch Library 2 records.
swf_asat.csv is Secure World Foundation's whole "History of ASAT Testing in Space" sheet as exported 13 Nov 2026
(Global Counterspace Capabilities (2026), CC BY-NC 4.0), uncut."""
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

from orbit import counterspace, feed, fetch, gcat, launches, navwarn  # noqa: E402
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


def api_doc_from_memos() -> dict:
    """The 13 Nov memoranda recast in the API's broadcast-warn form (navArea code, msgNumber, msgYear, issueDate
    "DDHHMMZ MON YYYY", text), so the API path is tested on the same real warnings as the memo path."""
    codes = {v: k for k, v in navwarn.NGA_AREA_CODES.items()}
    out = []
    for area, url in navwarn.NGA_MEMOS.items():
        lines = (FIX / "navwarn" / url.rsplit("/", 1)[1]).read_bytes().decode("utf-8", "replace").replace(
            "\r", "").split("\n")
        starts = [i for i in range(len(lines) - 1)
                  if navwarn.DTG.match(lines[i].strip()) and navwarn.MSG_ID.match(lines[i + 1].strip())]
        for k, i in enumerate(starts):
            dd, hh, nn, mon, yy = navwarn.DTG.match(lines[i].strip()).groups()
            _, num, _yy = navwarn.MSG_ID.match(lines[i + 1].strip()).groups()
            end = starts[k + 1] if k + 1 < len(starts) else len(lines)
            out.append({"navArea": codes[area], "msgNumber": int(num), "msgYear": 2000 + int(yy),
                        "issueDate": f"{dd}{hh}{nn}Z {mon} 20{yy}", "text": "\n".join(lines[i + 2:end]).strip()})
    return {"broadcast-warn": out}


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
        self.api_doc = None
        self.asat = body("swf_asat.csv")
        by_url = {u: FILES[name] for name, u in gcat.URLS.items()}

        def getter(url, timeout=60):
            self.calls.append(url)
            if self.fail:
                raise OSError("network down")
            if url in by_url:
                return body(by_url[url])
            if url.startswith(launches.API):
                return body("ll2_upcoming.json")
            if url == navwarn.NGA_API:
                if self.api_doc is None:
                    raise OSError("HTTP Error 503: Service Unavailable")
                return json.dumps(self.api_doc).encode("utf-8")
            if url.startswith(navwarn.NGA_BASE):
                return body("navwarn/" + url.rsplit("/", 1)[1])
            if "disp_warnings.cgi" in url:
                return body("navwarn/jcg_" + url.rsplit("TANA=", 1)[1].split("&")[0] + ".html")
            if "/warnings.cgi" in url:
                return body("navwarn/jcg_list.xml")
            if url == counterspace.URL:
                return self.asat
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
        self.assertEqual(snap["navwarn"]["sources"]["jcg"]["status"], "off")  # robots.txt disallows /TUHO/
        self.assertFalse([u for u in self.calls if "kaiho.mlit.go.jp" in u])
        self.assertTrue(snap["navwarn"]["areas"])
        self.assertEqual(snap["catalog_changes"], {})  # first reading only sets the baseline
        cs = snap["counterspace"]
        self.assertEqual(snap["lanes"]["counterspace"]["status"], "ok")
        self.assertEqual(snap["lanes"]["counterspace"]["fetches"][0]["url"], counterspace.URL)
        self.assertEqual((len(cs["tests"]), cs["updated"], cs["first_reading"]), (78, "2026-02-17", True))
        self.assertEqual(cs["new_since_last"], [])  # first reading only sets the baseline
        self.assertEqual(cs["by_country"]["China"], {"cc": "CN", "tests": 11, "debris_created": 3532,
                                                     "debris_on_orbit": 2351})
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
        self.assertEqual(snap["lanes"]["counterspace"]["status"], "failed")
        self.assertEqual(snap["counterspace"], good["counterspace"])

    def test_counterspace_new_tests_and_changed_layout(self):
        self.run_collect()
        rows = self.asat.decode("utf-8").split("\n")
        # A test SWF adds: a new row in the China block, side columns empty.
        i = next(k for k, r in enumerate(rows) if r.startswith("China,4/14/2023"))
        rows.insert(i + 1, "China,9/1/2026,Unknown,DN-9,direct ascent,Korla,\u2013,0,0,0,\u2013,\u2013,,,,")
        self.asat = "\n".join(rows).encode("utf-8")
        cs = self.run_collect()["counterspace"]
        self.assertFalse(cs["first_reading"])
        self.assertEqual(cs["previous_read_at"], "2026-11-13T18:00:00Z")
        self.assertEqual([(t["country"], t["date"], t["interceptor"]) for t in cs["new_since_last"]],
                         [("China", "2026-09-01", "DN-9")])
        self.assertEqual(cs["tests"][0]["date"], "2026-09-01")
        self.assertEqual(self.run_collect()["counterspace"]["new_since_last"], [])  # new once only
        # A sheet that no longer parses fails the lane and keeps the last good copy.
        self.asat = b"<html>Sign in</html>"
        snap = self.run_collect()
        self.assertEqual(snap["lanes"]["counterspace"]["status"], "failed")
        self.assertTrue(snap["lanes"]["counterspace"]["from_previous"])
        self.assertEqual(len(snap["counterspace"]["tests"]), 79)

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

    def test_nga_api_first_then_memoranda(self):
        snap = self.run_collect()  # API answers 503: the memoranda are read
        nga = snap["navwarn"]["sources"]["nga"]
        self.assertEqual((nga["form"], nga["status"]), ("memoranda", "ok"))
        self.assertIn("503", nga["api_error"])
        n_memo = len(snap["navwarn"]["areas"])
        self.api_doc, self.calls[:] = api_doc_from_memos(), []
        snap = self.run_collect()  # API back and fresh: it alone is read
        nga = snap["navwarn"]["sources"]["nga"]
        self.assertEqual((nga["form"], nga["status"]), ("api", "ok"))
        self.assertFalse([u for u in self.calls if u.startswith(navwarn.NGA_BASE)])
        self.assertEqual(len(snap["navwarn"]["areas"]), n_memo)

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

    def test_api_form_matches_memoranda(self):
        api = navwarn.parse_api(api_doc_from_memos(), NOW_NW)
        for area, url in navwarn.NGA_MEMOS.items():
            memo = navwarn.parse_memo((NW / url.rsplit("/", 1)[1]).read_bytes(), area, NOW_NW)
            got = api["memos"][area]
            self.assertEqual(got["in_force"], memo["in_force"], area)
            strip = lambda ws: [(w["id"], w["windows"], w["areas"], w["cancels"]) for w in ws]  # noqa: E731
            self.assertEqual(strip(got["warnings"]), strip(memo["warnings"]), area)

    def test_stale_or_empty_api_is_refused(self):
        doc = api_doc_from_memos()
        for w in doc["broadcast-warn"]:
            w["issueDate"] = w["issueDate"][:-4] + "2024"  # the frozen May 2024 set NGA served before the outage
        with self.assertRaisesRegex(ValueError, "stale"):
            navwarn.parse_api(doc, NOW_NW)
        with self.assertRaisesRegex(ValueError, "no warnings"):
            navwarn.parse_api({"broadcast-warn": []}, NOW_NW)

    def test_current_drops_cancelled_warnings(self):
        later = datetime(2026, 11, 25, 0, 0, tzinfo=timezone.utc)
        left = {w["id"] for w in navwarn.current(self.all_warnings(), later)}
        self.assertNotIn("HYDROPAC 3315/26", left)
        self.assertIn("HYDROPAC 3251/26", left)


class Counterspace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = body("swf_asat.csv")
        cls.doc = counterspace.parse_asat(cls.raw)

    def test_count_and_a_known_row(self):
        tests = self.doc["tests"]
        self.assertEqual(len(tests), 78)
        self.assertEqual(tests[0]["date"], "2023-04-14")  # newest first
        self.assertEqual(tests[-1]["date"], "1959-09-22")
        row = next(t for t in tests if t["target"] == "Cosmos 248")
        self.assertEqual(row, {
            "country": "Russia", "cc": "RU", "date": "1968-10-20", "target": "Cosmos 248",
            "interceptor": "Cosmos 249, Cosmos 252 (IS)", "interceptor_type": "co-orbital", "site": "Baikonur",
            "hit": True, "debris_created": 252, "debris_reentered": 181, "debris_on_orbit": 71,
            "final_reentry": "on orbit", "lifespan_years": 58.1})
        solwind = next(t for t in tests if t["target"] == "Solwind")
        self.assertEqual((solwind["final_reentry"], solwind["debris_on_orbit"]), ("2004-05-09", 0))
        nudol = next(t for t in tests if t["date"] == "2014-08-12")
        self.assertEqual((nudol["hit"], nudol["final_reentry"], nudol["lifespan_years"]), (None, None, None))
        self.assertEqual(next(t for t in tests if t["site"] == "Abdul Kalam island" and t["hit"])["date"],
                         "2019-03-27")
        self.assertEqual(next(t for t in tests if t["interceptor"] == "Naryad-V")["date"], "1994-12-26")  # M/D/YY

    def test_undated_rows_are_skipped_and_counted(self):
        sk = self.doc["skipped"]
        self.assertEqual([(s["country"], s["date_text"]) for s in sk],
                         [("Russia", "Aug - Dec 2019"), ("USA", "June-July 1965")])
        # Parsed tests plus skipped rows give the sheet's own totals: created 6904, still on orbit 2773.
        tests = self.doc["tests"]
        self.assertEqual(sum(t["debris_created"] or 0 for t in tests) + sum(s["debris_created"] for s in sk), 6904)
        self.assertEqual(sum(t["debris_on_orbit"] or 0 for t in tests) + sum(s["debris_on_orbit"] for s in sk), 2773)
        bc = counterspace.by_country(tests)
        self.assertEqual(list(bc), ["Russia", "USA", "China", "India"])
        self.assertEqual(bc["Russia"], {"cc": "RU", "tests": 33, "debris_created": 2734, "debris_on_orbit": 406})

    def test_last_updated(self):
        self.assertEqual(self.doc["updated"], "2026-02-17")
        self.assertEqual(counterspace.parse_updated(["", "Last Updated 3-Sep-2027\n Updated By X"]), "2027-09-03")
        self.assertIsNone(counterspace.parse_updated(["Total Debris Remaining", "2773"]))

    def test_side_columns_are_ignored(self):
        import csv
        import io
        rows = list(csv.reader(io.StringIO(self.raw.decode("utf-8"))))
        self.assertTrue(any(len(r) > counterspace.DATA_COLS and any(c.strip() for c in r[counterspace.DATA_COLS:])
                            for r in rows))  # the fixture does carry side-column text
        out = io.StringIO()
        csv.writer(out).writerows(r[:counterspace.DATA_COLS] for r in rows)
        bare = counterspace.parse_asat(out.getvalue().encode("utf-8"))
        self.assertEqual(bare["tests"], self.doc["tests"])
        self.assertIsNone(bare["updated"])
        side = {c.strip() for r in rows for c in r[counterspace.DATA_COLS:] if c.strip() and not c.strip().isdigit()}
        for t in self.doc["tests"]:
            self.assertFalse(side & {str(v) for v in t.values()}, t)

    def test_new_since_last(self):
        tests = self.doc["tests"]
        self.assertEqual(counterspace.new_since(tests, None), [])
        self.assertEqual(counterspace.new_since(tests, tests), [])
        self.assertEqual(counterspace.new_since(tests, tests[1:]), [tests[0]])

    def test_short_or_changed_sheet_raises(self):
        lines = self.raw.decode("utf-8").split("\n")
        cut = "\n".join(lines[:40])  # the Russian block only: under 50 tests
        with self.assertRaises(ValueError):
            counterspace.parse_asat(cut.encode("utf-8"))
        with self.assertRaises(ValueError):
            counterspace.parse_asat(b"<!DOCTYPE html><html>Sign in</html>")
        with self.assertRaises(ValueError):
            counterspace.parse_asat(self.raw.replace(b"Date of Test", b"When", 1))


class Registers(unittest.TestCase):
    def test_doctrine_registers(self):
        self.assertEqual(registers.check(ROOT / "doctrine"), [])

    def test_page_sources_carry_grades_for_every_lane(self):
        doc = cli.sources_doc(ROOT)
        by_id = {s["id"]: s for s in doc["sources"]}
        # excluded sources (Space-Track, CelesTrak) stay off the page
        self.assertEqual(set(by_id), {"gcat-mcdowell", "ll2-thespacedevs", "nga-msi",
                                      "swf-counterspace"})
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
