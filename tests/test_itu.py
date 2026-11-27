"""ITU filings as GEO slot evidence (orbit-2.42, doctrine/itu-filings.md).

The fixtures are made up in the format of ITU Space Explorer's replies (field names as ITU gives them, values
invented: "TEST-..." networks, administration "XX"), so the repository holds no ITU table."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from orbit import itu  # noqa: E402
from orbit.aliases import parse  # noqa: E402


def row(ntc_id, name, lon, prov, rcv, adm="XX", org=None, plan=False, plan_txt="Non-Plan"):
    return {"ntc_id": ntc_id, "adm": adm, "ntwk_org": org, "sat_name": name, "sat_name_latest": name,
            "long_nom": lon, "ntc_type": "G", "prov": prov, "f_plan": plan, "plan_txt": plan_txt, "d_rcv": rcv}


ROWS = [row(1001, "TEST-SAT-12.5W", -12.5, "RS49", "20.12.1999", org="TST"),
        row(1002, "TEST-SAT-12.5W", -12.5, "11.2", "12.05.2026", org="TST"),
        row(1003, "TEST-B-12.5W", -12.5, "9.6", "07.07.2025"),
        row(1004, "TEST-PLAN-12.5W", -12.5, "A30B#8.1", "02.05.2013", plan=True, plan_txt="Plan (AP30B)"),
        row(1005, "TEST-OLD-12.4W", -12.4, None, "02.06.2000", plan=True, plan_txt="Plan (AP30B)")]

RES40 = [{"sat_name": "TEST-B-12.5W", "adm": "XX", "ntwk_org": None, "long_nom": -12.5, "d_in_pos": "15.02.2016",
          "prov": "11.2", "sat_relocation": "YES", "prev_long_nom": -8, "sat_name_prev": "TEST-B-8W",
          "d_out_prev_pos": "01.10.2015"},
         {"sat_name": "TEST-C-50W", "adm": "YY", "ntwk_org": None, "long_nom": -50, "d_in_pos": "16.12.2025",
          "prov": "11.2", "sat_relocation": "YES", "prev_long_nom": -12.5, "sat_name_prev": "TEST-SAT-12.5W",
          "d_out_prev_pos": "29.10.2025"},
         {"sat_name": "TEST-D-70E", "adm": "XX", "ntwk_org": None, "long_nom": 70, "d_in_pos": "01.01.2020",
          "prov": "11.2", "sat_relocation": "NO", "prev_long_nom": None, "sat_name_prev": None, "d_out_prev_pos": None}]


class NoWait:
    def wait(self):
        pass


def poster_for(rows, page=200):
    calls = []

    def post(url, body):
        calls.append(body)
        lo, hi = body["satNetworkTypes"]["geoFrom"], body["satNetworkTypes"]["geoTo"]
        got = [r for r in rows if lo <= r["long_nom"] <= hi]
        part = got[body["skip"]: body["skip"] + min(page, body["take"])]
        return json.dumps({"table": part, "total": len(got), "sql": "--no sql included--"}).encode()
    return post, calls


class Words(unittest.TestCase):
    def test_dates_and_provisions(self):
        self.assertEqual(itu.iso("20.12.1999"), "1999-12-20")
        self.assertIsNone(itu.iso(None))
        self.assertEqual(itu.provision("11.2"), "notification for the Master Register (11.2)")
        self.assertEqual(itu.provision("9.6"), "coordination request (9.6)")
        self.assertEqual(itu.provision("RS49"), "Resolution 49 due diligence (RS49)")
        self.assertEqual(itu.provision("9.1/IA"), "advance publication (9.1/IA)")
        self.assertEqual(itu.provision("A30B#6.17"), "Appendix 30B, Article 6.17")
        self.assertEqual(itu.provision("5.2.10"), "Appendix 30/30A plan notification, Article 5.2.10")
        self.assertEqual(itu.provision("30/30A#5"), "30/30A#5")          # unknown forms are kept as ITU gives them
        self.assertEqual(itu.provision(None, "Plan (AP30B)"), "Plan (AP30B) entry")
        self.assertEqual(itu.provision(None), "provision not given")

    def test_notes_say_what_a_filing_is_not(self):
        self.assertIn("not a satellite's name", itu.NETWORK_NOTE)
        self.assertIn("not evidence that a satellite is or was there", itu.NETWORK_NOTE)
        self.assertIn("no NORAD number", itu.RES40_NOTE)

    def test_links_to_itu_pages(self):
        n = itu.notice(ROWS[0])
        self.assertEqual(n["link"], itu.APP + "/networks-explorer/space-stations/dashboard/non-plans/TEST-SAT-12.5W/1001")
        p = itu.notice(ROWS[3])
        self.assertTrue(p["link"].startswith(itu.APP + "/list-redirect?entity=ss&src=sns&adm=XX&sat_name=TEST-PLAN-12.5W"))
        self.assertIn("nonplan=0", p["link"])
        self.assertEqual(n["filer"], "XX/TST")


class Query(unittest.TestCase):
    def test_body_is_the_orbital_arc_filter(self):
        b = itu.query_body(-12.6, -12.4, 200)
        self.assertEqual(b["satNetworkTypes"], {"geo": True, "geoFrom": -12.6, "geoTo": -12.4})
        self.assertEqual(b["general"], {"network": "active", "serviceType": "all"})
        self.assertEqual((b["take"], b["skip"]), (200, 200))

    def test_arcs_across_180(self):
        self.assertEqual(itu.arcs(-12.5, 0.1), [(-12.6, -12.4)])
        a = itu.arcs(179.95, 0.1)
        self.assertEqual(len(a), 2)
        self.assertAlmostEqual(a[0][0], 179.85)
        self.assertAlmostEqual(a[1][1], -179.95)
        self.assertEqual(len(itu.arcs(-180.0, 0.5)), 2)

    def test_pages_cache_and_refresh(self):
        many = [row(2000 + k, f"TEST-{k}", -12.5, "9.6", "01.01.2020") for k in range(5)]
        post, calls = poster_for(many, page=2)
        old_take = itu.TAKE
        with tempfile.TemporaryDirectory() as d:
            now = datetime(2026, 11, 27, 5, 0, tzinfo=timezone.utc)
            got = itu.slot_notices(-12.5, 0.1, Path(d), poster=post, pacer=NoWait(), now=now)
            self.assertEqual((len(got["rows"]), got["total"], got["cached"]), (5, 5, False))
            self.assertEqual([c["skip"] for c in calls], [0, 2, 4])
            again = itu.slot_notices(-12.5, 0.1, Path(d), poster=post, pacer=NoWait(), now=now + timedelta(days=6))
            self.assertTrue(again["cached"])
            self.assertEqual(len(calls), 3)                                 # nothing asked within the week
            itu.slot_notices(-12.5, 0.1, Path(d), poster=post, pacer=NoWait(), now=now + timedelta(days=8))
            self.assertEqual(len(calls), 6)                                 # older than a week: asked again
            itu.slot_notices(-12.5, 0.1, Path(d), refresh=True, poster=post, pacer=NoWait(), now=now + timedelta(days=8))
            self.assertEqual(len(calls), 9)
        self.assertEqual(itu.TAKE, old_take)

    def test_a_changed_reply_is_an_error(self):
        with self.assertRaises(ValueError):
            itu.slot_notices(-12.5, 0.1, None, poster=lambda u, b: b'{"rows": []}', pacer=NoWait())

    def test_pacer_spaces_requests(self):
        slept, t = [], [0.0]
        p = itu._Pacer(3.0, sleep=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)), clock=lambda: t[0])
        p.wait()
        t[0] += 1.0
        p.wait()
        self.assertEqual(slept, [2.0])

    def test_networks_group_notices(self):
        nets = itu.networks(ROWS)
        by = {g["network"]: g for g in nets}
        self.assertEqual([n["prov"] for n in by["TEST-SAT-12.5W"]["notices"]], ["RS49", "11.2"])
        self.assertEqual(by["TEST-OLD-12.4W"]["notices"][0]["what"], "Plan (AP30B) entry")

    def test_res40_in_and_out(self):
        at = itu.res40_at(RES40, -12.5, 0.1)
        self.assertEqual([x["network"] for x in at["in"]], ["TEST-B-12.5W"])
        self.assertEqual(at["in"][0]["in_position"], "2016-02-15")
        self.assertEqual(at["in"][0]["prev_lon"], -8.0)
        self.assertEqual([(x["prev_network"], x["left_prev"], x["network"]) for x in at["out"]],
                         [("TEST-SAT-12.5W", "2025-10-29", "TEST-C-50W")])


LINK = """- norad: 99001
  network: "TEST-SAT-12.5W"
  adm: XX
  org: TST
  slot: -12.5
  ntc_id: 1002
  from: 2016-02-15
  to: 2025-10-29
  basis: res40-dates
  evidence:
    - "Resolution 40 (ITU table read 2026-11-27): TEST-B-12.5W in position from 15.02.2016"
  proposed_by: test
  proposed: 2026-11-27
"""


class Links(unittest.TestCase):
    def test_the_repository_file_reads(self):
        entries = itu.load_links()
        self.assertIsInstance(entries, list)
        for e in itu.reviewed(entries):
            self.assertIn(e["basis"], itu.BASES)

    def test_only_reviewed_entries_are_public(self):
        e = itu.validate_links(parse(LINK))
        self.assertEqual(e[0]["slot"], -12.5)
        self.assertEqual(itu.public_links(e, "2026-11-27T05:00Z")["objects"], {})
        rev = itu.validate_links(parse(LINK + "  reviewed_by: tic-analyst\n  reviewed: 2026-11-28\n"))
        doc = itu.public_links(rev, "2026-11-27T05:00Z")
        self.assertEqual(doc["schema"], "orbit-itu-links/1")
        got = doc["objects"]["99001"][0]
        self.assertEqual((got["network"], got["slot"], got["from"], got["to"]), ("TEST-SAT-12.5W", -12.5, "2016-02-15", "2025-10-29"))
        self.assertTrue(got["link"].endswith("/dashboard/non-plans/TEST-SAT-12.5W/1002"))
        self.assertIn("TIC's attribution", doc["link_note"])
        self.assertNotIn("reviewed_by", got)                                # the reviewer is not published

    def test_bad_entries_are_refused(self):
        bad = {
            "slot: -12.5": "slot: 200",
            "basis: res40-dates": "basis: hunch",
            "norad: 99001": "norad: OBJECT",
            "from: 2016-02-15": "from: 2026-02-15",                         # after `to`
        }
        for old, new in bad.items():
            with self.assertRaises(itu.LinkError, msg=new):
                itu.validate_links(parse(LINK.replace(old, new)))
        with self.assertRaises(itu.LinkError):
            itu.validate_links(parse(LINK + "  reviewed_by: tic-analyst\n"))   # reviewed_by without reviewed
        with self.assertRaises(itu.LinkError):
            itu.validate_links(parse(LINK + "  satellite_name: X\n"))          # names never come from a filing
        with self.assertRaises(itu.LinkError):
            itu.validate_links(parse(LINK + LINK))
        withdrawn = itu.validate_links(parse(LINK + "  withdrawn: 2026-11-28\n  reason: wrong object\n"))
        self.assertEqual(withdrawn, [])


class FindCli(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("orbit_cli_itu", ROOT / "tools" / "orbit.py")
        self.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cli)
        self.search = {"schema": "tic-catalog-search/1", "read": "2026-11-26", "columns": ["key", "name", "other_names", "cospar", "type", "gone"],
                       "objects": [["99001", "TEST SAT", [], "2009-001A", "p", False]]}
        self.globe = {"built_utc": "2026-11-27T04:46Z", "cols": ["norad", "name", "region", "active", "n", "lon"],
                      "objects": [[99001, "TEST SAT", "zone", 1, 1.0027, -12.48]], "names": {}}

    def run_find(self, q, poster=None, getter=None, **kw):
        urls = {self.cli.SEARCH_URL: json.dumps(self.search).encode(), self.cli.GEO_URL: json.dumps(self.globe).encode()}
        post, _ = poster_for(ROWS)
        io_ = {"poster": poster or post, "getter": getter or (lambda u: json.dumps(RES40).encode()),
               "pacer": NoWait(), "cache_dir": False}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = self.cli.find_name(q, getter=lambda u: urls[u], itu_io=io_, **kw)
        return code, buf.getvalue()

    def test_slot_lists_filings_and_res40(self):
        code, out = self.run_find("12.5W", itu=True)
        self.assertEqual(code, 0)
        filed = out.split("Filed for 12.5° W at the ITU")[1].split("Resolution 40 statements")[0]
        self.assertIn("4 networks", filed)                                  # 12.4 W is inside the 0.1° default
        self.assertIn("TEST-SAT-12.5W", filed)
        self.assertIn("Resolution 49 due diligence (RS49) received 1999-12-20; notification for the Master Register (11.2) received 2026-05-12", filed)
        self.assertIn(itu.NETWORK_NOTE, filed)
        r40 = out.split("Resolution 40 statements")[1]
        self.assertIn("in position  TEST-B-12.5W", r40)
        self.assertIn("came from 8.0° W (TEST-B-8W), left 2015-10-01", r40)
        self.assertIn("left it      TEST-SAT-12.5W at 12.5° W, left 2025-10-29", r40)
        self.assertIn("TIC's inference, never the ITU's", r40)
        self.assertIn("Not published by Orbit", r40)

    def test_window_narrows_filings(self):
        _, out = self.run_find("12.5W", itu=True, window=0.05)
        self.assertIn("3 networks", out)

    def test_without_itu_nothing_is_asked(self):
        def boom(u, b):
            raise AssertionError("ITU asked without --itu")
        code, out = self.run_find("12.5W", poster=boom)
        self.assertNotIn("Filed for", out)
        self.assertIn("add --itu", out)

    def test_itu_down_is_said_not_guessed(self):
        def down(u, b):
            raise OSError("timed out")
        code, out = self.run_find("12.5W", itu=True, poster=down)
        self.assertIn("Space Explorer did not answer (OSError: timed out); nothing shown, nothing assumed.", out)
        self.assertEqual(code, 0)                                           # the GEO record still found the object


class Page(unittest.TestCase):
    def test_object_page_reads_reviewed_links_only(self):
        js = (ROOT / "site_src" / "object.js").read_text(encoding="utf-8")
        self.assertIn('getJson("data/itu-links.json")', js)
        self.assertIn("ITU filings linked by review", js)
        self.assertIn("itu.link_note", js)


if __name__ == "__main__":
    unittest.main()
