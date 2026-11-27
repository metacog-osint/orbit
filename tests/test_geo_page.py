"""Offline checks for the GEO page (geo.html, tools/geo_page.py; step 4 of doctrine/geo-move-plan.md). No sgp4 or
numpy here: the update run's tests run before tools/requirements-callouts.txt is installed."""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import geo_page as G  # noqa: E402


def objs(*norads):
    return [[k, f"OBJ {k}", "2020-001A", "PAYLOAD", "US", "2020-01-01", "LARGE", "zone", 1, "2026-11-18T00:00:00",
             1.0027, 0.0001, 0.05, 80.0, 10.0, 200.0, 0.0] for k in norads]


class RpoPairs(unittest.TestCase):
    def snap(self, rows):
        return {"rpo": {"sheet": "https://example.invalid/sheet", "report": "https://example.invalid/report",
                        "updated": "2026-02-17", "rows": rows}}

    def row(self, chaser, target, text="Jan 25, 2020", start="2020-01-25"):
        return {"tab": "commercial", "date_text": text, "when": {"start": start, "ongoing": False},
                "chaser": "C", "target": "T", "mission_type": "Servicing", "country": "USA",
                "gcat": {"chaser": [{"norad": str(c)} for c in chaser], "target": [{"norad": str(t)} for t in target]}}

    def test_both_ends_near_geo_only(self):
        rows = [self.row([1], [2]), self.row([1], [99]), self.row([98], [97]), self.row([3], [4, 2], start="2022-01-01")]
        out = G.rpo_pairs(self.snap(rows), objs(1, 2, 3, 4))
        got = [(p["chaser"][0], p["target"][0]) for p in out["pairs"]]
        self.assertEqual(got, [(3, 4), (3, 2), (1, 2)])           # newest first; a two-target row gives two pairs
        self.assertEqual(out["one_end_only"], 1)                 # 1 -> 99: counted, not drawn; 98 -> 97: neither
        self.assertIn("CC BY-NC 4.0", out["source"])

    def test_no_snapshot(self):
        out = G.rpo_pairs(None, objs(1))
        self.assertEqual(out["pairs"], [])


class Files(unittest.TestCase):
    def test_events_and_elements(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            for day, evs in (("2026-10-01", [{"day": "2026-10-01", "norad": 5, "kind": "new"}]),
                             ("2026-11-17", [{"day": "2026-11-17", "norad": 6, "kind": "returned"}]),
                             ("2026-11-18", [])):
                (p / f"{day}.geo-region.json").write_text(json.dumps({"day": day, "events": evs}), encoding="utf-8")
            reg = G.region_events(d, "2026-11-18")
            self.assertEqual([e["norad"] for e in reg["events"]], [6])     # 1 Oct is outside the 30 days
            self.assertEqual(reg["from"], "2026-10-20")
            cols = ["norad", "epoch", "n", "e", "i", "raan", "argp", "M", "bstar", "ndot", "nddot", "elset", "rev"]
            rows = [[7, "2026-11-02T00:00:00", 1.0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1],
                    [7, "2026-11-01T00:00:00", 1.0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1],
                    [7, "2026-11-01T00:00:00", 1.1, 0, 0, 0, 0, 0, 0, 0, 0, 2, 1]]       # a re-issued set: the last wins
            with gzip.open(p / "geo-elements-2026-11.json.gz", "wt", encoding="utf-8") as f:
                json.dump({"cols": cols, "rows": rows}, f)
            from datetime import datetime
            el = G.read_elsets(d, datetime(2026, 11, 18))
            self.assertEqual([r["epoch"] for r in el[7]], ["2026-11-01T00:00:00", "2026-11-02T00:00:00"])
            self.assertEqual(el[7][0]["n"], 1.1)

    def test_encode_round_trip(self):
        samples = [(179.99, 0.1, 5.0), (-179.98, 0.12, 6.0), (-179.5, 0.0, -3.0)]
        start, back = G.decode(G.encode(3, samples))
        self.assertEqual(start, 3)
        for a, b in zip(samples, back):
            self.assertAlmostEqual(a[0], b[0], places=2)


class Page(unittest.TestCase):
    def test_import_map_hash_in_csp(self):
        html = (ROOT / "site_src" / "geo.html").read_text(encoding="utf-8")
        body = re.search(r'<script type="importmap">(.*?)</script>', html, re.S).group(1)
        digest = "'sha256-" + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode() + "'"
        headers = (ROOT / "site_src" / "_headers").read_text(encoding="utf-8")
        script = re.search(r"script-src ([^;]+)", headers).group(1)
        self.assertIn(digest, script)                       # edit the import map, update the hash
        self.assertNotIn("cdn.", html)                      # three.js and satellite.js are self-hosted

    def test_two_set_list_drawn_apart(self):
        # method orbit-2.38: belt.two_set has its own heading inside the changes section, never merged into its tables
        js = (ROOT / "site_src" / "geo" / "globe.js").read_text(encoding="utf-8")
        self.assertIn("twoSet(b.two_set || []", js)
        self.assertIn("Seen between two sets", js)
        html = (ROOT / "site_src" / "geo.html").read_text(encoding="utf-8")
        self.assertIn("a second rule that needs only two sets", html)

    def test_vendored_three_and_no_inline_styles(self):
        three = ROOT / "site_src" / "vendor" / "three"
        for f in ("build/three.module.min.js", "build/three.core.min.js", "examples/jsm/controls/OrbitControls.js", "LICENSE"):
            self.assertTrue((three / f).exists(), f)
        js = (ROOT / "site_src" / "geo" / "globe.js").read_text(encoding="utf-8")
        self.assertNotIn(' style="', js)                    # the CSP blocks style attributes: data-css instead
        for path in re.findall(r'fetch\("([^"]+)', js):
            self.assertFalse(path.startswith("/"), path)    # relative, like the rest of Orbit's site


if __name__ == "__main__":
    unittest.main()
