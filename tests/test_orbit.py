"""Offline tests for Orbit. Fixtures in tests/fixtures/ are real replies from 13 Nov 2026, cut down:
GCAT tables (CC BY 4.0, J. McDowell, planet4589.org/space/gcat) and four Launch Library 2 records.
swf_asat.csv is Secure World Foundation's whole "History of ASAT Testing in Space" sheet as exported 13 Nov 2026
(Global Counterspace Capabilities (2026), CC BY-NC 4.0), uncut."""
from __future__ import annotations

import json
import math
import os
import random
import shutil
import sys
import tempfile
import unittest
import urllib.error
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from orbit import celestrak, counterspace, feed, fetch, gcat, launches, launchpairs, maneuver, navwarn, news, rpo, spacetrack  # noqa: E402
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

    def test_payload_orbits_and_none_before_elements(self):
        got = {x["launch_tag"]: x for x in gcat.recent_launches(gcat.parse_tsv(body("launch.tsv")), self.objs,
                                                                self.sites, TODAY)}
        sl = got["2026-246"]["payloads"][0]  # Starlink 38432: elements dated 1 Nov
        self.assertEqual((sl["inc"], sl["perigee"], sl["apogee"], sl["orbit_date"]), (70.0, 245, 256, "2026-11-01"))
        nvs = got["2026-245"]["payloads"][0]  # NVS-03, still in its transfer orbit
        self.assertEqual((nvs["inc"], nvs["perigee"], nvs["apogee"]), (20.71, 178, 37895))
        usa = got["2026-255"]["payloads"][0]  # GCAT writes 0 / 0 / 0.00 before elements: no orbit, not zero
        self.assertEqual((usa["inc"], usa["perigee"], usa["apogee"], usa["orbit_date"]), (None, None, None, None))
        self.assertEqual(gcat.orbit_of({"Perigee": "-", "Apogee": "-", "Inc": "-"})["inc"], None)
        self.assertEqual(gcat.orbit_of({"Perigee": "35780", "Apogee": "35792", "Inc": "0.00", "ODate": "2026 Nov 1"}),
                         {"perigee": 35780, "apogee": 35792, "inc": 0.0, "orbit_date": "2026-11-01"})  # GEO at 0.00
        esc = gcat.orbit_of({"Perigee": "185", "Apogee": "Inf", "Inc": "28.50", "ODate": "-"})  # GCAT's escape form
        self.assertEqual((esc["perigee"], esc["apogee"], esc["inc"], esc["orbit_date"]), (185, None, 28.5, None))

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

    def test_breakup_and_collision_are_not_reentries(self):
        def obj(jcat, status):
            return {"jcat": jcat, "norad": 99000 + int(jcat[1:]), "name": f"TEST {jcat}", "type": "R",
                    "launch_tag": "2020-001", "ldate": "2020 Jan  1", "parent": "", "state": "CN", "owner": "",
                    "status": status, "op_orbit": "LEO/I", "ddate": "2026 Nov 10"}
        objs = [obj("S1", "R"), obj("S2", "E"), obj("S3", "C")]
        self.assertEqual([r["jcat"] for r in gcat.recent_reentries(objs, TODAY)], ["S1"])
        self.assertEqual({(r["jcat"], r["status"], r["breakup_date"]) for r in gcat.recent_breakups(objs, TODAY)},
                         {("S2", "E", "2026-11-10"), ("S3", "C", "2026-11-10")})

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
        shutil.copytree(ROOT / "site_src", self.tmp / "site_src", ignore=shutil.ignore_patterns("cesium"))  # 14 MB, not needed
        self.calls = []
        self.stamp = "Fri, 13 Nov 2026 00:23:02 GMT"
        self.fail = False
        self.api_doc = None
        self.celestrak_403 = False
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
            if url.startswith(news.API):
                return body("snapi_articles.json")
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
            if url == launchpairs.URL:
                return body("launch_snapshot.json")
            if url == celestrak.URL:
                if self.celestrak_403:
                    raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
                return body("celestrak_last30.json")
            if url.startswith(rpo.SHEET):
                gid = url.rsplit("gid=", 1)[1]
                tab = {s["gid"]: t for t, s in rpo.TABS.items()}.get(gid, "about")
                return body(f"swf_rpo_{tab}.csv")
            raise AssertionError(url)

        self.getter = getter
        self.header = lambda url: self.stamp
        self.patches = [mock.patch.object(gcat, "today_utc", return_value=TODAY),
                        mock.patch.object(launches, "now_utc", return_value=NOW),
                        mock.patch.object(fetch, "now_utc", return_value="2026-11-13T18:00:00Z"),
                        mock.patch.object(cli.spacetrack, "credentials", return_value=None)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_collect(self, **kw):
        return cli.collect(self.tmp, getter=self.getter, header=self.header, **kw)

    def test_paths_kept_on_celestrak_403(self):
        """A repeat download inside one of CelesTrak's 2-hour updates gets 403: sets kept, one request, no retry."""
        snap = self.run_collect()
        self.celestrak_403 = True
        n = len(self.calls)
        again = self.run_collect(only=["paths"])
        self.assertEqual(again["lanes"]["paths"]["status"], "unchanged")
        self.assertIn("403", again["lanes"]["paths"]["note"])
        self.assertEqual(again["payload_sets"], snap["payload_sets"])
        self.assertEqual([u for u in self.calls[n:] if "celestrak" in u], [celestrak.URL])

    def test_full_cycle(self):
        snap = self.run_collect()
        self.assertEqual(snap["lanes"]["catalog"]["status"], "ok")
        self.assertEqual(snap["lanes"]["upcoming"]["status"], "ok")
        self.assertEqual(snap["lanes"]["navwarn"]["status"], "ok")
        self.assertEqual(snap["lanes"]["rpo"]["status"], "ok")
        self.assertEqual(snap["lanes"]["pairs"]["status"], "ok")
        self.assertEqual(snap["lanes"]["paths"]["status"], "ok")
        self.assertEqual(snap["payload_sets"]["objects_in_group"], 5)
        self.assertEqual(len(snap["launch_pairs"]["matches"]), 11)  # 14 rows, 11 launch-area pairs
        self.assertEqual(snap["rpo"]["counts"], {"commercial": 14, "military": 44, "planned": 4})
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


class PayloadSets(unittest.TestCase):
    """orbit-2.12: CelesTrak's last-30-days group, cut to five rows of its 16 Nov 2026 reply (2026-257 and -258)."""
    LAUNCHES = [{"launch_tag": "2026-258", "payloads": [{"norad": "101385", "name": "QPS-SAR-19"}]},
                {"launch_tag": "2026-257", "payloads": []}]

    def test_keeps_payloads_and_unnamed_objects_not_rocket_bodies(self):
        got = celestrak.parse(body("celestrak_last30.json"), self.LAUNCHES)
        self.assertEqual(got["objects_in_group"], 5)
        self.assertEqual([o["cospar"] for o in got["by_launch"]["2026-258"]], ["2026-258A"])  # both R/B dropped
        self.assertTrue(got["by_launch"]["2026-258"][0]["gcat_payload"])
        self.assertEqual([o["cospar"] for o in got["by_launch"]["2026-257"]], ["2026-257A", "2026-257B"])
        self.assertFalse(got["by_launch"]["2026-257"][0]["gcat_payload"])
        el = got["by_launch"]["2026-258"][0]["elements"]
        self.assertEqual(sorted(el), ["argp", "e", "epoch", "i", "ma", "n", "raan"])
        self.assertGreater(el["n"], 10)  # LEO
        self.assertEqual(got["sets"], 3)

    def test_other_launches_and_bad_rows_left_out(self):
        rows = json.loads(body("celestrak_last30.json"))
        rows[0] = {**rows[0], "MEAN_MOTION": None}
        got = celestrak.parse(json.dumps(rows).encode(), self.LAUNCHES[1:])
        self.assertNotIn("2026-258", got["by_launch"])
        got = celestrak.parse(json.dumps(rows).encode(), self.LAUNCHES)
        self.assertEqual((got["unusable"], got["sets"]), (1, 2))
        with self.assertRaises(ValueError):
            celestrak.parse(b'{"error": "maintenance"}', self.LAUNCHES)


class LaunchPairs(unittest.TestCase):
    """Launch's place check on Orbit's areas: its snapshot as published 16 Nov 2026 03:58 UTC (matches only)."""

    def test_best_row_per_pair_and_only_orbit_areas(self):
        doc = json.loads(body("launch_snapshot.json"))
        got = launchpairs.parse(body("launch_snapshot.json"))
        self.assertEqual(got["generated_at"], "2026-11-16T03:58:13Z")
        pairs = {(m["launch"], m["area"]) for m in doc["matches"]}
        self.assertEqual({(m["launch"], m["area"]) for m in got["matches"]}, pairs)
        two = [m for m in doc["matches"] if (m["launch"], m["area"]) == (got["matches"][0]["launch"], got["matches"][0]["area"])]
        if len(two) > 1:  # several polygons: the nearest is kept when the levels agree
            self.assertEqual(got["matches"][0]["distance_nm"], min(m["distance_nm"] for m in two))
        # Synthetic, built here: a place match outranks a time-only row; an FAA TFR row is not Orbit's.
        extra = dict(doc["matches"][0], level="time and place", distance_nm=900)
        tfr = dict(doc["matches"][0], area_source="faa-tfr", area="FDC 6/1234")
        doc["matches"] += [extra, tfr]
        got = launchpairs.parse(json.dumps(doc).encode())
        row = next(m for m in got["matches"] if (m["launch"], m["area"]) == (extra["launch"], extra["area"]))
        self.assertEqual((row["level"], row["distance_nm"]), ("time and place", 900))
        self.assertFalse([m for m in got["matches"] if m["area"] == "FDC 6/1234"])

    def test_not_launchs_snapshot(self):
        with self.assertRaises(ValueError):
            launchpairs.parse(b'{"html": "maintenance"}')


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


class RPO(unittest.TestCase):
    """SWF's RPO sheet as read 15 Nov 2026 (tests/fixtures/swf_rpo_*.csv, CC BY-NC 4.0, Secure World Foundation)."""

    @classmethod
    def setUpClass(cls):
        cls.bodies = {t: (FIX / f"swf_rpo_{t}.csv").read_bytes() for t in list(rpo.TABS) + ["about"]}
        cls.doc = rpo.read(cls.bodies, None)

    def test_counts_and_date(self):
        self.assertEqual(self.doc["counts"], {"commercial": 14, "military": 44, "planned": 4})
        self.assertEqual(self.doc["updated"], "2026-02-17")

    def test_dates_read_or_listed_apart(self):
        W = rpo.parse_when
        self.assertEqual(W("Apr 14, 2005"), {"start": "2005-04-14", "end": "2005-04-14", "precision": "day", "ongoing": False})
        self.assertEqual((W("Aug - Oct. 2017")["start"], W("Aug - Oct. 2017")["end"]), ("2017-08", "2017-10"))
        self.assertEqual((W("Aug 2010 - July 2011")["start"], W("Aug 2010 - July 2011")["end"]), ("2010-08", "2011-07"))
        self.assertEqual((W("Sept 3-Oct 28 2020")["start"], W("Sept 3-Oct 28 2020")["end"]), ("2020-09-03", "2020-10-28"))
        self.assertEqual((W("Jun 15-29 2020")["start"], W("Jun 15-29 2020")["end"]), ("2020-06-15", "2020-06-29"))
        self.assertEqual(W("Oct 2014 - Present"), {"start": "2014-10", "end": None, "precision": "month", "ongoing": True})
        self.assertEqual(W("2014 - Present")["precision"], "year")
        self.assertEqual((W("1990-1998")["start"], W("1990-1998")["end"]), ("1990", "1998"))
        self.assertEqual((W("Dec 23, 2008 & Jan 1, 2009")["start"], W("Dec 23, 2008 & Jan 1, 2009")["end"]),
                         ("2008-12-23", "2009-01-01"))
        self.assertEqual(W("April 27, 2021 (launch)")["start"], "2021-04-27")
        for t in ("Mar - Apr, Sep, Dec 2024", "Fall 2025", "", "Feb 30, 2020"):
            self.assertIsNone(W(t), t)
        self.assertEqual([u["date_text"] for u in self.doc["unread_dates"]], ["Mar - Apr, Sep, Dec 2024", "Fall 2025"])

    def test_swf_text_kept(self):
        row = next(r for r in self.doc["rows"] if r["chaser"] == "Comos 2521")  # SWF's spelling, kept
        self.assertEqual((row["tab"], row["target"], row["mission_type"]), ("military", "Cosmos 2519", "Intelligence"))
        planned = [r for r in self.doc["rows"] if r["tab"] == "planned"]
        self.assertTrue(all("notes" in r and "orbit" not in r for r in planned))

    def test_names_link_to_gcat_only_when_one_fits(self):
        objs = {"S49330": ["satcat", "49330", "2021-063", "P", "Shi Jian 21", "2021 Oct 24", "-", "-", "O", "", "CN", ""],
                "S23426": ["satcat", "23426", "1994-082", "P", "Luch", "1994 Dec 16", "-", "-", "O", "", "RU", ""],
                "S40258": ["satcat", "40258", "2014-058", "P", "Luch", "2014 Sep 27", "-", "-", "O", "", "RU", ""],
                "S99999": ["satcat", "99999", "2030-001", "P", "SJ-99", "2030 Jan  1", "-", "-", "O", "", "CN", ""],
                "S11111": ["satcat", "11111", "2001-001", "P", "Old 1", "2001 Jan  1", "-", "2005 Jan  1", "R", "", "US", ""]}
        ix = rpo.gcat_names(objs)
        when = rpo.parse_when("Dec 2021 - Jan 2022")
        self.assertEqual([o["norad"] for o in rpo.link("ShiJian-21 (SJ-21)", when, ix)], ["49330"])  # once
        self.assertEqual(rpo.link("Luch (Olymp)", when, ix), [])  # two GCAT payloads named Luch: no guess
        self.assertEqual(rpo.link("SJ-99", when, ix), [])  # launched after the activity
        self.assertEqual(rpo.link("Old 1", rpo.parse_when("2010"), ix), [])  # reentered before it
        self.assertEqual(rpo.link("Multiple", when, ix), [])

    def test_changed_layout_fails(self):
        with self.assertRaises(ValueError):
            rpo.parse_tab(self.bodies["military"].replace(b"Chaser", b"Other", 1), "military")
        with self.assertRaises(ValueError):
            rpo.parse_tab(b"<!DOCTYPE html><html>Sign in</html>", "commercial")
        with self.assertRaises(ValueError):
            rpo.parse_tab(self.bodies["military"].split(b"\n", 5)[0] + b"\n", "military")  # header only


class Registers(unittest.TestCase):
    def test_doctrine_registers(self):
        self.assertEqual(registers.check(ROOT / "doctrine"), [])

    def test_page_sources_carry_grades_for_every_lane(self):
        doc = cli.sources_doc(ROOT)
        by_id = {s["id"]: s for s in doc["sources"]}
        # excluded sources stay out; the catalog's CelesTrak SATCAT and Wikidata (build step 4) are ingested but
        # feed no page lane yet, so the page, which lists sources by lane, does not show them
        self.assertEqual(set(by_id), {"gcat-mcdowell", "ll2-thespacedevs", "snapi-thespacedevs", "nga-msi",
                                      "swf-counterspace", "swf-rpo", "space-track", "tic-launch", "celestrak-gp",
                                      "celestrak-satcat", "wikidata"})
        self.assertEqual(by_id["wikidata"]["lanes"], [])
        self.assertEqual(by_id["gcat-mcdowell"]["grade"], "A2")
        self.assertEqual(by_id["gcat-mcdowell"]["reliability"], "Completely reliable")
        self.assertEqual(by_id["ll2-thespacedevs"]["grade"], "B2")
        self.assertEqual(by_id["ll2-thespacedevs"]["credibility"], "Probably true")
        held = set() if maneuver.PUBLISH else {"maneuver"}  # held until Tom approves the Space-Track disclaimer
        self.assertEqual({lane for s in doc["sources"] for lane in s["lanes"]}, set(cli.LANE_FIELDS) - held)
        self.assertTrue(all(s["grade"] for s in doc["sources"]))

    def test_feed_items_lint(self):
        snap = json.loads((FIX / "ll2_upcoming.json").read_text(encoding="utf-8"))
        rows = launches.parse(json.dumps(snap).encode())
        doc = feed.build_feed({"generated_at": "2026-11-13T18:00:00Z", "upcoming": rows, "lanes": {}})
        regs = registers.ids(ROOT / "doctrine")
        for f in doc["features"]:
            errs = [m for _, sev, m in contract.check(f, regs) if sev == "error"]
            self.assertEqual(errs, [], f["properties"]["id"])

    def test_breakups_are_feed_items_under_or_eei_5(self):
        b = {"jcat": "S2", "norad": 99002, "name": "TEST S2", "type": "rocket stage", "launch_tag": "2020-001",
             "launch_date": "2020-01-01", "parent": "", "state": "CN", "country": "CN", "owner": "", "status": "E",
             "op_orbit": "LEO/I", "breakup_date": "2026-11-10", "breakup_time": None, "breakup_uncertain": False}
        doc = feed.build_feed({"generated_at": "2026-11-16T18:00:00Z", "lanes": {}, "breakups": [b]})
        (f,) = [x for x in doc["features"] if x["properties"]["id"].startswith("orbit:breakup:")]
        p = f["properties"]
        self.assertEqual((p["id"], p["requirement_ids"], p["tier"], p["countries"]),
                         ("orbit:breakup:S2", ["OR-EEI-5"], "routine", ["CN"]))
        self.assertIsNone(f["geometry"])
        self.assertIn("exploded (broke up in orbit)", p["title"])
        self.assertIn("not a reentry", p["summary"])
        self.assertTrue(p["visual"]["url"].endswith("/#breakups"))
        regs = registers.ids(ROOT / "doctrine")
        self.assertEqual([m for _, sev, m in contract.check(f, regs) if sev == "error"], [])

    def test_the_page_has_the_breakups_card_the_feed_links_to(self):
        html = (ROOT / "site_src" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "site_src" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="breakups"', html)
        self.assertIn('href="#breakups"', html)
        self.assertIn('id="breakup-table"', html)
        self.assertIn("breakupTable();", js)

    def test_maneuver_items_carry_the_approved_citation_and_stay_off_the_map(self):
        ev = {"norad": 41744, "name": "USA 270", "object_id": "2016-052A", "country": "US", "regime": "GEO",
              "from": "2026-10-12T18:06:12Z", "to": "2026-11-02T06:44:40Z", "dv_ms": 0.887, "dominant": "in-track",
              "da_km": -14.63, "di_deg": 0.053, "z": 2916.6, "pairs": 2, "longest_gap_h": 408.8,
              "gap": {"from": "2026-10-12T18:06:12Z", "to": "2026-10-29T18:55:44Z", "hours": 408.8},
              "geo": {"lon_before": 125.47, "lon_after": -72.13, "drift_before": -0.065, "drift_after": 0.123},
              "gcat_name": "USA 270", "state": "US", "cc": "US"}
        snap = {"generated_at": "2026-11-15T00:56:02Z", "lanes": {},
                "maneuvers": {"attribution": maneuver.ATTRIBUTION, "read_at": "2026-11-15T00:56:26Z", "events": [ev]}}
        doc = feed.build_feed(snap)
        (f,) = doc["features"]
        p = f["properties"]
        self.assertEqual(p["id"], "orbit:maneuver:41744:2026-10-12")  # kind "maneuver": COP's gate holds it
        self.assertIsNone(f["geometry"])
        self.assertEqual(p["sources"][0]["licence"], maneuver.ATTRIBUTION)
        self.assertTrue(p["summary"].endswith(maneuver.ATTRIBUTION))
        self.assertIn("not a confirmed manoeuvre", p["summary"])
        self.assertIn("408.8-hour gap", p["summary"])
        self.assertIn("72.13 W", p["summary"])
        self.assertIn("OR-EEI-2", p["requirement_ids"])
        self.assertIn("18th Space Defense Squadron; orbit-change analysis is Orbit's own", doc["attribution"])
        regs = registers.ids(ROOT / "doctrine")
        self.assertEqual([m for _, sev, m in contract.check(f, regs) if sev == "error"], [])
        self.assertNotIn("Space-Track", feed.build_feed({**snap, "maneuvers": {}})["attribution"])


class News(unittest.TestCase):
    """Spaceflight News API headlines (orbit-2.5): links only, filtered to the scheduled launches."""
    IDS = [r["id"] for r in json.loads(body("ll2_upcoming.json"))["results"]]

    def test_fixture_keeps_headline_outlet_time_and_link_only(self):
        doc = news.parse(body("snapi_articles.json"), self.IDS)
        self.assertEqual(len(doc["articles"]), 4)  # 6 results; one link listed twice is kept once; 3 newest a launch
        for a in doc["articles"]:
            self.assertEqual(set(a), {"title", "site", "url", "published_at", "launches"})
            self.assertTrue(a["url"].startswith("https://"))
            self.assertTrue(set(a["launches"]) <= set(self.IDS))
        self.assertEqual(sorted(i[:8] for i in doc["by_launch"]), ["0f867f0c", "7bdc412b", "db3500ac"])
        dates = [a["published_at"] for a in doc["articles"]]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_bad_links_duplicates_and_other_launches_are_dropped_and_each_launch_keeps_three(self):
        mine, other = "0f867f0c-0000-0000-0000-000000000000", "ffffffff-0000-0000-0000-000000000000"
        rows = [{"title": f"Story {n}", "url": f"https://example.org/{n}", "news_site": "Outlet",
                 "published_at": f"2026-11-{10 + n:02d}T12:00:00Z", "launches": [{"launch_id": mine}]} for n in range(7)]
        rows += [{"title": "Dup", "url": "https://example.org/3", "news_site": "X", "published_at": "2026-11-20T00:00:00Z",
                  "launches": [{"launch_id": mine}]},
                 {"title": "Script", "url": "javascript:alert(1)", "news_site": "X", "published_at": "2026-11-20T00:00:00Z",
                  "launches": [{"launch_id": mine}]},
                 {"title": "Not ours", "url": "https://example.org/x", "news_site": "X",
                  "published_at": "2026-11-20T00:00:00Z", "launches": [{"launch_id": other}]}]
        doc = news.parse(json.dumps({"count": len(rows), "results": rows}).encode(), [mine])
        titles = [a["title"] for a in doc["articles"]]
        self.assertEqual(titles, ["Story 6", "Story 5", "Story 4"])  # newest three; Dup lost to Story 3, Script dropped
        self.assertEqual(doc["by_launch"][mine], [0, 1, 2])

    def test_one_request_for_all_scheduled_launches_and_none_when_nothing_is_scheduled(self):
        calls = []

        def getter(url, timeout=60):
            calls.append(url)
            return body("snapi_articles.json")
        out, recs, _ = cli._lane_news(None, {}, getter, upcoming=[{"id": i} for i in self.IDS])
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(i in calls[0] for i in self.IDS))
        self.assertEqual(len(out["news"]["articles"]), 4)
        calls.clear()
        out, recs, _ = cli._lane_news(None, {}, getter, upcoming=[])
        self.assertEqual((calls, recs, out["news"]["articles"]), ([], [], []))

    def test_a_response_without_results_fails_the_lane(self):
        with self.assertRaises(ValueError):
            news.parse(b'{"detail": "throttled"}', self.IDS)


NOW_M = datetime(2026, 11, 14, 6, 0, tzinfo=timezone.utc)
SIDEREAL = maneuver.SIDEREAL_REV_DAY


def synth(norad, days=40, per_day=2, n0=1.0027379, e0=0.0002, i0=0.05, node0=80.0, n_rate=0.0, node_rate=0.0,
          noise_n=2e-7, noise_i=2e-5, noise_node=0.0, burns=(), lon0=100.0, seed=1, end=NOW_M):
    """SYNTHETIC element sets in Space-Track's GP form, for testing the detector's logic only: a steady orbit with
    Gaussian set-to-set noise and step changes ("burns") at given days. Not real data."""
    rng = random.Random(seed)
    out, n, i, step, lon = [], n0, i0, 1.0 / per_day, lon0
    t0 = end - timedelta(days=days)
    for k in range(int(days * per_day)):
        d = k * step
        t = t0 + timedelta(days=d)
        for bd, dn, di in burns:
            if abs(d - bd) < step / 2:
                n, i = n + dn, i + di
        n_now = n + n_rate * d
        node = node0 + node_rate * d + rng.gauss(0, noise_node)
        argp = 10.0
        lon = lon + (n_now - SIDEREAL) * 360.0 * step if k else lon0
        ma = (lon + maneuver._gmst_deg(t) - node - argp) % 360.0
        out.append({"NORAD_CAT_ID": str(norad), "OBJECT_NAME": f"TEST {norad}", "OBJECT_ID": "2000-001A",
                    "COUNTRY_CODE": "TEST", "DECAY_DATE": None, "EPOCH": t.strftime("%Y-%m-%dT%H:%M:%S.%f"),
                    "MEAN_MOTION": f"{n_now + rng.gauss(0, noise_n):.8f}", "ECCENTRICITY": f"{e0:.7f}",
                    "INCLINATION": f"{i + rng.gauss(0, noise_i):.6f}", "RA_OF_ASC_NODE": f"{node % 360:.6f}",
                    "ARG_OF_PERICENTER": f"{argp:.4f}", "MEAN_ANOMALY": f"{ma:.4f}",
                    "CREATION_DATE": (t + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")})
    return out


def dn_for(dv_ms):  # mean-motion step for an along-track change of dv_ms at GEO (dv = v/3 * dn/n)
    return 3 * dv_ms * SIDEREAL / 3074.7


class Maneuver(unittest.TestCase):
    """The detector on SYNTHETIC series (logic only; the real-data check is `orbit.py maneuver-case`)."""

    def detect(self, recs, **kw):
        store = maneuver.merge({}, recs, NOW_M)
        return maneuver.detect(next(iter(store.values())), NOW_M, **kw)

    def test_quiet_geo_has_no_change(self):
        d = self.detect(synth(1))
        self.assertEqual((d["regime"], d["events"], d["note"]), ("GEO", [], None))
        self.assertAlmostEqual(d["geo"]["lon"], 100.0, delta=0.5)

    def test_geo_in_track_burn_is_one_change(self):
        d = self.detect(synth(2, burns=[(30.0, dn_for(0.5), 0.0)]))
        self.assertEqual(len(d["events"]), 1, d["events"])
        ev = d["events"][0]
        self.assertEqual(ev["dominant"], "in-track")
        self.assertAlmostEqual(ev["dv_ms"], 0.5, delta=0.05)
        self.assertAlmostEqual(ev["da_km"], -13.7, delta=1.0)  # 2a*dv/v: faster mean motion, lower orbit
        self.assertAlmostEqual(ev["geo"]["drift_after"] - ev["geo"]["drift_before"], dn_for(0.5) * 360, delta=0.01)

    def test_geo_change_under_quarter_metre_a_second_is_counted_not_listed(self):
        d = self.detect(synth(9, burns=[(30.0, dn_for(0.15), 0.0)]))
        self.assertEqual((d["events"], d["below_report"]), ([], 1))

    def test_change_across_a_tracking_gap_is_labelled(self):
        recs = [r for r in synth(10, burns=[(30.0, dn_for(0.5), 0.0)])
                if not "2026-11-01" <= r["EPOCH"][:10] <= "2026-11-05"]  # no sets for five days around the change
        d = self.detect(recs)
        self.assertEqual(len(d["events"]), 1, d["events"])
        ev = d["events"][0]
        self.assertGreaterEqual(ev["gap"]["hours"], 5 * 24)
        self.assertLess(ev["gap"]["from"], "2026-11-01")
        self.assertGreater(ev["gap"]["to"], "2026-11-05")
        self.assertNotIn("gap", self.detect(synth(11, burns=[(30.0, dn_for(0.5), 0.0)]))["events"][0])

    def test_marks_under_a_day_apart_join_only_when_they_agree(self):
        # orbit-2.6: a lowering then a raising half a day later are two changes; two raisings are one
        d = self.detect(synth(12, burns=[(30.0, dn_for(0.5), 0.0), (30.5, -dn_for(0.5), 0.0)]))
        self.assertEqual([e["da_km"] < 0 for e in d["events"]], [True, False], d["events"])
        d = self.detect(synth(13, burns=[(30.0, dn_for(0.5), 0.0), (30.5, dn_for(0.5), 0.0)]))
        self.assertEqual(len(d["events"]), 1, d["events"])
        self.assertAlmostEqual(d["events"][0]["dv_ms"], 1.0, delta=0.1)
        # an in-track change then a plane change half a day later are two changes
        d = self.detect(synth(14, i0=1.0, burns=[(30.0, dn_for(0.5), 0.0), (30.5, 0.0, 0.01)]))
        self.assertEqual([e["dominant"] for e in d["events"]], ["in-track", "cross-track"], d["events"])

    def test_score_counts_hits_misses_and_storm_marks(self):
        ev = lambda f, t: {"from": f, "to": t, "dv_ms": 1.0, "dominant": "in-track", "da_km": 1.0}
        hit, late, storm, other = (ev("2024-01-27T05:00:00Z", "2024-01-27T17:00:00Z"),
                                   ev("2024-03-15T02:00:00Z", "2024-03-15T03:00:00Z"),
                                   ev("2024-05-11T08:00:00Z", "2024-05-11T11:00:00Z"),
                                   ev("2024-04-15T12:00:00Z", "2024-04-15T13:00:00Z"))
        ann = [{"label": "a", "from": "2024-01-27T11:39:00Z", "to": "2024-01-27T11:39:00Z"},
               {"label": "b", "from": "2024-03-14T13:11:00Z", "to": "2024-03-14T13:11:00Z"},  # 12 h 49 m before "late": outside 12 h
               {"label": "c", "from": "2024-02-23T06:00:00Z", "to": "2024-02-24T06:00:00Z"}]
        sc = maneuver.score([hit, late, storm, other], ann, 12,
                            {"from": "2024-05-10T12:00:00Z", "to": "2024-05-13T00:00:00Z"})
        self.assertEqual((sc["hits"], sc["misses"]), (1, 2))
        self.assertEqual(sc["extra"], [late, other, storm])
        self.assertEqual(sc["in_storm"], [storm])
        self.assertEqual(maneuver.score([late], ann[1:2], 14)["hits"], 1)  # 12 h 49 m apart: inside 14 h

    def test_geo_plane_change_is_cross_track(self):
        d = self.detect(synth(3, i0=1.0, burns=[(25.0, 0.0, 0.01)]))  # 0.01 deg: about 0.54 m/s
        self.assertEqual([e["dominant"] for e in d["events"]], ["cross-track"])
        self.assertAlmostEqual(d["events"][0]["dv_ms"], 0.54, delta=0.06)

    def test_leo_drag_decay_and_precession_are_not_changes(self):
        d = self.detect(synth(4, per_day=4, n0=15.2, i0=51.6, n_rate=0.002, node_rate=-5.0, noise_n=2e-5,
                              noise_i=1e-4, noise_node=1e-3))
        self.assertEqual((d["regime"], d["events"]), ("LEO", []))

    def test_precession_across_a_long_gap_is_not_a_change(self):
        # 15 Nov review: 28.5 deg, 30-day gap, no burn listed 22,902 m/s cross-track (node residual off by 360 deg)
        leo = dict(days=70, per_day=4, n0=15.2, i0=28.5, node_rate=-7.0, noise_n=2e-5, noise_i=1e-4, noise_node=1e-3)
        recs = [r for r in synth(18, **leo) if not "2026-09-25" <= r["EPOCH"][:10] <= "2026-10-24"]
        d = self.detect(recs)
        self.assertGreaterEqual(d["max_gap_h"], 30 * 24)
        self.assertEqual((d["events"], d["implausible"]), ([], 0))

    def test_a_change_beyond_orbital_speed_is_counted_never_listed(self):
        leo = dict(per_day=4, n0=15.2, i0=51.6, node_rate=-5.0, noise_n=2e-5, noise_i=1e-4, noise_node=1e-3)
        d = self.detect(synth(19, burns=[(30.0, 0.0, 70.0)], **leo))  # a 70 deg plane jump: a bad set, not a burn
        self.assertEqual((d["events"], d["implausible"]), ([], 1))

    def test_leo_small_cross_track_change_is_counted_not_listed(self):
        # orbit-2.8: in low orbit a change mainly cross-track or eccentricity is listed only at 1 m/s or more
        leo = dict(per_day=4, n0=15.2, i0=51.6, n_rate=0.002, node_rate=-5.0, noise_n=2e-5, noise_i=1e-4, noise_node=1e-4)
        d = self.detect(synth(15, burns=[(30.0, 0.0, 0.0037)], **leo))  # about 0.5 m/s plane change
        self.assertEqual((d["regime"], d["events"], d["leo_off_track"]), ("LEO", [], 1))
        d = self.detect(synth(16, burns=[(30.0, 0.0, 0.0112)], **leo))  # about 1.5 m/s: listed
        self.assertEqual([e["dominant"] for e in d["events"]], ["cross-track"])
        self.assertEqual(d["leo_off_track"], 0)

    def test_leo_in_track_change_is_listed_with_its_semi_major_axis_velocity(self):
        leo = dict(per_day=4, n0=15.2, i0=51.6, n_rate=0.002, node_rate=-5.0, noise_n=2e-5, noise_i=1e-4, noise_node=1e-3)
        dn = 3 * 0.3 * 15.2 / 7680.0  # about 0.3 m/s along-track at 400 km
        d = self.detect(synth(17, burns=[(30.0, -dn, 0.0)], **leo))
        self.assertEqual([e["dominant"] for e in d["events"]], ["in-track"], d["events"])
        ev = d["events"][0]
        self.assertAlmostEqual(ev["dv_sma_ms"], 0.3, delta=0.05)
        self.assertLessEqual(ev["dv_sma_ms"], ev["dv_ms"] + 1e-9)
        self.assertGreater(ev["da_km"], 0)  # slower mean motion: higher orbit

    def test_short_baseline_marks_nothing(self):
        d = self.detect(synth(5, days=5, burns=[(3.0, dn_for(2.0), 0.0)]))
        self.assertEqual(d["events"], [])
        self.assertIn("baseline too short", d["note"])

    def test_old_changes_fall_outside_the_window(self):
        self.assertEqual(self.detect(synth(6, days=60, burns=[(10.0, dn_for(0.5), 0.0)]))["events"], [])

    def test_stale_object_is_named(self):
        d = self.detect(synth(7, end=NOW_M - timedelta(days=5)))
        self.assertTrue(d["note"].startswith("no new element set for 5."), d["note"])

    def test_reissued_epoch_keeps_the_later_set(self):
        a = synth(8, days=1)[0]
        b = {**a, "MEAN_MOTION": "1.1", "CREATION_DATE": "2099-01-01T00:00:00"}
        store = maneuver.merge({}, [b, a], NOW_M)
        self.assertEqual(store["8"]["sets"][0][1], 1.1)
        self.assertEqual(len(store["8"]["sets"]), 1)


class SpaceTrack(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for k in ("SPACETRACK_IDENTITY", "SPACETRACK_PASSWORD", "ORBIT_WATCH"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_credentials_and_watch_list_from_private_files(self):
        self.assertIsNone(spacetrack.credentials(self.tmp))
        self.assertEqual(spacetrack.watch_list(self.tmp), [])
        (self.tmp / ".env").write_text("﻿SPACETRACK_IDENTITY=me@example.test\n# local\nSPACETRACK_PASSWORD='x y'\n",
                                       encoding="utf-8")  # with the byte-order mark Notepad can add
        (self.tmp / "private").mkdir()
        (self.tmp / "private" / "watch.txt").write_text("49330  # SJ-21, note 40258\n34779,49330\nfoo\n")
        self.assertEqual(spacetrack.credentials(self.tmp), ("me@example.test", "x y"))
        self.assertEqual(spacetrack.watch_list(self.tmp), [49330, 34779])
        os.environ["ORBIT_WATCH"] = "41838"
        self.assertEqual(spacetrack.watch_list(self.tmp), [41838])

    def test_top_and_bottom_of_the_hour_are_waited_out(self):
        def at(m, s=0):
            return datetime(2026, 11, 14, 6, m, s, tzinfo=timezone.utc)
        self.assertEqual(spacetrack.wait_for_clear_minute(at(58), lambda s: None, lambda: 0.0), 360)  # to 07:04
        self.assertEqual(spacetrack.wait_for_clear_minute(at(30, 30), lambda s: None, lambda: 0.0), 210)  # to :34
        self.assertEqual(spacetrack.wait_for_clear_minute(at(10), lambda s: None, lambda: 0.5), 30)
        for m in range(60):
            t = at(m) + timedelta(seconds=spacetrack.wait_for_clear_minute(at(m), lambda s: None, lambda: 0.0))
            self.assertNotIn(t.minute, spacetrack.BLOCKED_MINUTES, m)

    def test_requests_are_spaced(self):
        waits = []

        class Resp:
            def __init__(self, b):
                self.b = b

            def read(self):
                return self.b

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        class Opener:
            def open(self, req, timeout=0):
                return Resp(b"[]")

        c = spacetrack.Client("u", "p", opener=Opener(), sleep=waits.append)
        c.login()
        c.query("gp", [2, 1])
        c.logout()
        self.assertEqual(c.requests, 3)
        self.assertEqual(len(waits), 2)
        self.assertTrue(all(2.0 < w <= spacetrack.GAP_S for w in waits))

    def test_failed_login_is_refused(self):
        class Opener:
            def open(self, req, timeout=0):
                class R:
                    def read(self):
                        return b'{"Login":"Failed"}'

                    def __enter__(self):
                        return self

                    def __exit__(self, *a):
                        return False
                return R()
        with self.assertRaises(PermissionError):
            spacetrack.Client("u", "p", opener=Opener(), sleep=lambda s: None).login()


class FakeClient:
    """Stands in for Space-Track: answers GP (the newest set) and GP_HISTORY (the rest) from SYNTHETIC series."""
    log: list = []
    series: dict = {}

    def __init__(self, ident, pw):
        self.requests, self.last_body = 0, b""

    def login(self):
        self.requests += 1
        FakeClient.log.append("login")

    def logout(self):
        self.requests += 1
        FakeClient.log.append("logout")

    def query(self, cls, ids, extra=""):
        self.requests += 1
        FakeClient.log.append((cls, tuple(ids), extra))
        recs = [r for i in ids for r in (FakeClient.series[i][-1:] if cls == "gp" else FakeClient.series[i][:-1])]
        self.last_body = json.dumps(recs).encode()
        return recs


def _offline(url, timeout=60):
    raise OSError("offline")


class ManeuverLane(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(ROOT / "doctrine", self.tmp / "doctrine")
        FakeClient.log = []
        FakeClient.series = {49330: synth(49330, burns=[(30.0, dn_for(0.5), 0.0)]), 34779: synth(34779)}
        self.now = [NOW_M]
        self.patches = [mock.patch.object(cli, "ST_CLIENT", FakeClient),
                        mock.patch.object(cli, "ST_WAIT", lambda: 0.0),
                        mock.patch.object(cli, "ST_NOW", lambda: self.now[0]),
                        mock.patch.object(cli, "ST_SHARED", lambda now: None),
                        mock.patch.object(cli.spacetrack, "credentials", return_value=("u", "p")),
                        mock.patch.dict(os.environ, {"ORBIT_WATCH": "49330,34779"})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_lane(self):
        return cli.collect(self.tmp, getter=_offline, header=lambda u: None, only=["maneuver"])

    def held(self):
        return json.loads((self.tmp / "data" / "state" / "spacetrack" / "held_lane.json").read_text(encoding="utf-8"))

    def test_held_lane_stays_off_the_snapshot(self):
        with mock.patch.object(maneuver, "PUBLISH", False):
            snap = self.run_lane()
        self.assertNotIn("maneuver", snap["lanes"])
        self.assertNotIn("maneuvers", snap)
        self.assertNotIn("49330", (self.tmp / "data" / "snapshot.json").read_text(encoding="utf-8"))
        held = self.held()
        self.assertEqual(held["lane"]["status"], "ok")
        self.assertEqual([e["norad"] for e in held["maneuvers"]["events"]], [49330])
        self.assertEqual(FakeClient.log, ["login", ("gp", (49330, 34779), ""),
                                          ("gp_history", (49330, 34779), "/EPOCH/>now-60"), "logout"])

    def test_history_once_and_gp_once_an_hour(self):
        self.run_lane()
        FakeClient.log.clear()
        self.now[0] = NOW_M + timedelta(minutes=30)
        self.run_lane()
        self.assertEqual(FakeClient.log, [])  # under an hour: no request at all
        self.now[0] = NOW_M + timedelta(minutes=61)
        self.run_lane()
        self.assertEqual(FakeClient.log, ["login", ("gp", (49330, 34779), ""), "logout"])  # no history again

    def test_waits_while_noisefloor_holds_the_shared_gp_hour(self):
        self.run_lane()
        FakeClient.log.clear()
        self.now[0] = NOW_M + timedelta(minutes=90)
        with mock.patch.object(cli, "ST_SHARED", lambda now: "Noisefloor's GP query was under an hour ago"):
            snap = self.run_lane()
        self.assertEqual(FakeClient.log, [])  # no request at all
        lane = snap["lanes"]["maneuver"]
        self.assertEqual(lane["status"], "unchanged")
        self.assertIn("Noisefloor", lane["note"])
        self.assertEqual(len(snap["maneuvers"]["events"]), 1)  # the last reading is kept
        snap = self.run_lane()  # clear again: asks, and the note goes
        self.assertEqual(FakeClient.log, ["login", ("gp", (49330, 34779), ""), "logout"])
        self.assertNotIn("note", snap["lanes"]["maneuver"])

    def test_off_without_credentials(self):
        with mock.patch.object(cli.spacetrack, "credentials", return_value=None):
            snap = self.run_lane()
        self.assertEqual(snap["lanes"]["maneuver"]["status"], "off")
        self.assertIn("no Space-Track credentials", snap["lanes"]["maneuver"]["reason"])
        self.assertEqual(snap["maneuvers"], {})
        self.assertEqual(FakeClient.log, [])

    def test_published_snapshot_never_names_the_watch_list_in_urls(self):
        with mock.patch.object(maneuver, "PUBLISH", True):
            snap = self.run_lane()
        lane = snap["lanes"]["maneuver"]
        self.assertEqual(lane["status"], "ok")
        self.assertTrue(all("withheld" in f["url"] and "49330" not in f["url"] for f in lane["fetches"]))
        self.assertEqual(snap["maneuvers"]["watched"], 2)
        self.assertIn("USSPACECOM", snap["maneuvers"]["attribution"])
        self.assertEqual(len(snap["maneuvers"]["events"]), 1)
        self.assertNotIn("objects", snap["maneuvers"])  # quiet watched objects are counted, not named
        el = snap["maneuvers"]["events"][0]["elements"]  # the newest set of a listed object, for the globe
        self.assertEqual(sorted(el), ["argp", "e", "epoch", "i", "ma", "n", "raan"])
        self.assertGreater(el["n"], 0.9)
        for f in ("snapshot.json", "state/daily_archive.json"):  # the quiet watched object stays unnamed
            self.assertNotIn("34779", (self.tmp / "data" / f).read_text(encoding="utf-8"))


class Baseline(unittest.TestCase):
    """gcat.baseline on small synthetic rows: windows, counts and positions."""
    TODAY = date(2026, 11, 15)

    def test_windows_counts_and_position(self):
        orgs = {"SPX": {"name": "SpaceX", "state": "US"}, "CALT": {"name": "CALT", "state": "CN"}}
        prior = [(self.TODAY - timedelta(days=30 * k + 3)).isoformat() for k in range(1, 25)]  # one a window
        rows = [{"Launch_Tag": d, "Launch_Date": gcat_date(d), "Agency": "SPX", "LaunchCode": "OS"} for d in prior]
        recent = [(self.TODAY - timedelta(days=k)).isoformat() for k in (1, 2, 3)]
        rows += [{"Launch_Tag": d, "Launch_Date": gcat_date(d), "Agency": "SPX", "LaunchCode": "OS"} for d in recent]
        rows.append({"Launch_Tag": "x", "Launch_Date": gcat_date(recent[0]), "Agency": "CALT", "LaunchCode": "OF"})
        rows.append({"Launch_Tag": "y", "Launch_Date": gcat_date(recent[0]), "Agency": "SPX", "LaunchCode": "SS"})  # suborbital
        b = gcat.baseline(rows, [], orgs, self.TODAY)
        self.assertEqual(b["recent"], ["2026-10-17", "2026-11-15"])
        us = next(r for r in b["launches_by_country"] if r["key"] == "US")
        self.assertEqual((us["recent"], us["prior_median"], us["prior_min"], us["prior_max"], us["position"]),
                         (3, 1, 1, 1, "above"))
        self.assertEqual(len(us["series"]), 25)
        cn = next(r for r in b["launches_by_country"] if r["key"] == "CN")  # a failed orbital attempt still counts
        self.assertEqual((cn["recent"], cn["position"], cn["windows_at_or_above"]), (1, "above", 0))
        self.assertEqual(b["launches_all"][0]["recent"], 4)
        self.assertEqual(next(r for r in b["launches_by_agency"] if r["key"] == "SPX")["name"], "SpaceX")

    def test_reentries_and_payloads_by_owner(self):
        d = (self.TODAY - timedelta(days=40)).isoformat()
        objs = [{"type": "P", "state": "CN", "ldate": gcat_date(d), "status": "O", "ddate": ""},
                {"type": "R", "state": "US", "ldate": "2020 Jan  1", "status": "R", "ddate": gcat_date(d)}]
        b = gcat.baseline([], objs, {}, self.TODAY)
        self.assertEqual(b["payloads_by_owner"][0]["key"], "CN")
        self.assertEqual(b["payloads_by_owner"][0]["series"][-2:], [1, 0])
        self.assertEqual((b["reentries_by_owner"][0]["key"], b["reentries_by_owner"][0]["position"]), ("US", "within"))


def gcat_date(iso):  # GCAT's own form: "2026 Nov 12"
    y, m, d = iso.split("-")
    return f"{y} {['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][int(m) - 1]} {int(d):2d}"


class SharedAccount(unittest.TestCase):
    """spacetrack.shared_gp_busy against canned GitHub API answers (offline)."""
    NOW = datetime(2026, 11, 15, 13, 5, tzinfo=timezone.utc)

    def get(self, runs, steps):
        def _get(url):
            if url == spacetrack.SHARED_RUNS:
                return {"workflow_runs": runs}
            return {"jobs": [{"steps": steps}]}
        return _get

    def run_(self, status="completed", started="2026-11-15T12:40:00Z"):
        return {"id": 1, "status": status, "run_started_at": started, "jobs_url": "jobs"}

    def step(self, done, conclusion="success"):
        return {"name": spacetrack.SHARED_STEP, "conclusion": conclusion, "completed_at": done}

    def test_recent_noisefloor_gp_query_is_busy(self):
        busy = spacetrack.shared_gp_busy(self.NOW, self.get([self.run_()], [self.step("2026-11-15T12:52:00Z")]))
        self.assertIn("under an hour", busy)

    def test_an_hour_after_it_is_clear(self):
        self.assertIsNone(spacetrack.shared_gp_busy(self.NOW, self.get([self.run_(started="2026-11-15T11:30:00Z")],
                                                                     [self.step("2026-11-15T12:00:00Z")])))

    def test_skipped_step_and_old_runs_are_clear(self):
        self.assertIsNone(spacetrack.shared_gp_busy(self.NOW, self.get([self.run_()], [self.step(None, "skipped")])))
        self.assertIsNone(spacetrack.shared_gp_busy(self.NOW, self.get([self.run_(started="2026-11-15T05:40:00Z")],
                                                                     [self.step("2026-11-15T12:59:00Z")])))

    def test_running_noisefloor_job_is_busy(self):
        self.assertIn("in_progress", spacetrack.shared_gp_busy(self.NOW, self.get([self.run_("in_progress")], [])))

    def test_github_unreadable_is_busy(self):
        def fail(url):
            raise OSError("offline")
        self.assertIn("could not read", spacetrack.shared_gp_busy(self.NOW, fail))


if __name__ == "__main__":
    unittest.main()
