"""Offline tests for Orbit's launch ledger (orbit/ledger.py and `orbit.py ledger`). Launch Library 2 replies are
built here in LL2's detailed shape, cut to the fields Orbit reads."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from orbit import ledger  # noqa: E402
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("orbit_cli_ledger", ROOT / "tools" / "orbit.py")
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)


def rec(i: int, net: str, status: str = "Success", name: str | None = None) -> dict:
    return {"id": f"id-{i:03d}", "name": name or f"Rocket | Mission {i}", "net": net,
            "net_precision": {"name": "Second"}, "window_start": net, "window_end": net,
            "status": {"abbrev": status, "name": status}, "last_updated": net,
            "launch_service_provider": {"name": "Provider", "type": {"name": "Commercial"},
                                        "country": [{"alpha_2_code": "US"}]},
            "rocket": {"configuration": {"full_name": "Rocket"}},
            "mission": {"name": f"Mission {i}", "type": "Communications", "description": "x" * 900,
                        "orbit": {"abbrev": "LEO", "name": "Low Earth Orbit"}},
            "pad": {"name": "Pad 1", "latitude": "28.5", "longitude": "-80.6",
                    "location": {"name": "Cape", "country": {"alpha_2_code": "US"}}},
            "url": f"https://ll.thespacedevs.com/2.3.0/launches/id-{i:03d}/", "image": {"image_url": "x.jpg"}}


def page(*rows) -> bytes:
    return json.dumps({"count": len(rows), "results": list(rows)}).encode()


def day(n: int, h: int = 0) -> str:
    return f"2024-01-{n:02d}T{h:02d}:00:00Z"


class LedgerTest(unittest.TestCase):
    def test_urls(self):
        q = parse_qs(urlparse(ledger.next_url(ledger.empty())).query)
        self.assertEqual(q, {"net__gte": [ledger.START], "ordering": ["net"], "limit": ["14"], "mode": ["detailed"]})
        doc = ledger.empty()
        ledger.step(doc, page(rec(1, day(1)), rec(2, day(3))), "t0")
        self.assertEqual(parse_qs(urlparse(ledger.next_url(doc)).query)["net__gte"], [day(3)])  # the newest saved
        self.assertTrue(ledger.id_url("abc").startswith("https://ll.thespacedevs.com/2.3.0/launches/abc/?"))

    def test_first_page_then_verify_and_add(self):
        doc = ledger.empty()
        r = ledger.step(doc, page(*[rec(i, day(i)) for i in range(1, 15)]), "t0")
        self.assertEqual((r["added"], r["verified"], doc["caught_up"]), (14, None, False))
        self.assertNotIn("mission_description", doc["launches"][0])     # the long text isn't kept
        self.assertNotIn("image", json.dumps(doc))                         # nor images
        # the next pull starts at launch 14: it comes back first (now renamed), then three new ones
        r = ledger.step(doc, page(rec(14, day(14), name="Renamed"), rec(15, day(15)), rec(16, day(16)),
                                  rec(17, day(17))), "t1")
        self.assertEqual((r["verified"], r["added"], r["requests"]), ("ok", 3, 1))
        self.assertEqual(r["changed"], {"id-014": {"name": ["Rocket | Mission 14", "Renamed"]}})
        self.assertEqual(doc["changes"][-1]["id"], "id-014")
        self.assertTrue(doc["caught_up"])
        self.assertEqual([x["id"] for x in doc["launches"]][-3:], ["id-015", "id-016", "id-017"])
        # caught up: the pull holds only the last saved launch; nothing changes, nothing is added
        r = ledger.step(doc, page(rec(17, day(17))), "t2")
        self.assertEqual((r["verified"], r["added"], r["changed"]), ("ok", 0, {}))
        self.assertEqual(len(doc["launches"]), 17)

    def test_same_net_twice_is_kept_once_each(self):
        doc = ledger.empty()
        ledger.step(doc, page(rec(1, day(1)), rec(2, day(1))), "t0")
        r = ledger.step(doc, page(rec(1, day(1)), rec(2, day(1)), rec(3, day(2))), "t1")
        self.assertEqual((r["added"], len(doc["launches"])), (1, 3))

    def test_last_saved_missing_from_pull(self):
        doc = ledger.empty()
        ledger.step(doc, page(rec(1, day(1)), rec(2, day(5))), "t0")
        calls = []

        def moved(i):  # its NET was corrected to before the pull's start
            calls.append(i)
            return json.dumps(rec(2, day(4))).encode()
        r = ledger.step(doc, page(rec(3, day(6))), "t1", moved)
        self.assertEqual((calls, r["verified"], r["requests"]), (["id-002"], "moved", 2))
        self.assertEqual(r["changed"]["id-002"]["net"], [day(5), day(4)])
        r = ledger.step(doc, page(rec(4, day(7))), "t2", lambda i: None)    # LL2 no longer has launch 3
        self.assertEqual(r["verified"], "missing")
        self.assertEqual(next(x for x in doc["launches"] if x["id"] == "id-003")["ll2_missing_since"], "t2")
        r = ledger.step(doc, page(rec(5, day(8))), "t3")                    # no lookup given: said, not guessed
        self.assertEqual(r["verified"], "not in pull")

    def test_open_launch_is_looked_up_until_final(self):
        doc = ledger.empty()
        ledger.step(doc, page(rec(1, day(1)), rec(2, day(2), "Go"), rec(3, day(3))), "t0")
        self.assertEqual(ledger.open_launch(doc)["id"], "id-002")
        calls = []

        def lookup(i):
            calls.append(i)
            return json.dumps(rec(2, day(2), "Failure")).encode()
        r = ledger.step(doc, page(rec(3, day(3)), rec(4, day(4))), "t1", lookup)
        self.assertEqual((calls, r["open_checked"], r["requests"]), (["id-002"], {"id": "id-002", "status": "Failure"}, 2))
        self.assertEqual(r["changed"]["id-002"]["status"], ["Go", "Failure"])
        self.assertIsNone(ledger.open_launch(doc))
        # an open launch more than OPEN_DAYS before the newest is left as it is
        doc = ledger.empty()
        ledger.step(doc, page(rec(1, "2024-01-01T00:00:00Z", "TBC"), rec(2, "2024-01-20T00:00:00Z")), "t0")
        self.assertIsNone(ledger.open_launch(doc))
        # the newest itself still "Go" is verified by the pull, not looked up
        doc = ledger.empty()
        ledger.step(doc, page(rec(1, day(1)), rec(2, day(2), "Go")), "t0")
        self.assertIsNone(ledger.open_launch(doc))

    def test_one_lookup_at_most(self):
        doc = ledger.empty()
        ledger.step(doc, page(rec(1, day(1), "Go"), rec(2, day(2))), "t0")
        calls = []
        r = ledger.step(doc, page(rec(3, day(3))), "t1", lambda i: calls.append(i) or json.dumps(rec(2, day(2))).encode())
        self.assertEqual((calls, r["requests"], r["open_checked"]), (["id-002"], 2, None))   # the newest took it

    def test_bad_reply_changes_nothing(self):
        doc = ledger.empty()
        ledger.step(doc, page(rec(1, day(1))), "t0")
        before = json.dumps(doc)
        with self.assertRaises(ValueError):
            ledger.step(doc, b'{"detail": "Request was throttled."}', "t1")
        self.assertEqual(json.dumps(doc), before)

    def test_summary_lists_what_gcat_has_not(self):
        doc = ledger.empty()
        ledger.step(doc, page(rec(1, day(1)), rec(2, day(2)), rec(3, day(3))), "t0")
        s = ledger.summary(doc, "2024-01-01")
        self.assertEqual((s["held"], s["url"]), (3, ledger.PUBLIC_URL))
        self.assertEqual([x["id"] for x in s["since_gcat"]], ["id-003", "id-002"])
        self.assertNotIn("since_gcat", ledger.summary(doc))


class LedgerCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / "state" / ledger.ASSET
        # the command's own lines (a ::warning:: among them) would read as real annotations in the workflow log
        out = contextlib.redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def test_pull_writes_and_repeats(self):
        urls = []

        def getter(url, timeout=120):
            urls.append(url)
            return page(*[rec(i, day(i)) for i in range(1, 4)])
        self.assertEqual(cli.ledger_pull(self.path, getter, raw_dir=None), 0)
        doc = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual((len(doc["launches"]), doc["schema"], len(urls)), (3, ledger.SCHEMA, 1))
        self.assertEqual(cli.ledger_pull(self.path, getter, raw_dir=None), 0)
        self.assertIn("net__gte=" + day(3).replace(":", "%3A"), urls[1])
        self.assertEqual(len(json.loads(self.path.read_text(encoding="utf-8"))["launches"]), 3)

    def test_throttled_changes_nothing_and_does_not_retry(self):
        calls = []

        def ok(url, timeout=120):
            return page(rec(1, day(1)))
        cli.ledger_pull(self.path, ok, raw_dir=None)
        before = self.path.read_bytes()

        def throttled(url, timeout=120):
            calls.append(url)
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, io.BytesIO(b""))
        self.assertEqual(cli.ledger_pull(self.path, throttled, raw_dir=None), 0)
        self.assertEqual((len(calls), self.path.read_bytes()), (1, before))

    def test_lane_off_before_first_publish(self):
        def getter(url, timeout=120):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b""))
        with self.assertRaises(cli.spacetrack.NotReady):
            cli._lane_ledger(None, {}, getter)

    def test_lane_reads_the_release(self):
        doc = ledger.empty()
        ledger.step(doc, page(rec(1, day(1)), rec(2, day(9))), "t0")

        def getter(url, timeout=120):
            self.assertEqual(url, ledger.PUBLIC_URL)
            return json.dumps(doc).encode()
        out, recs, _ = cli._lane_ledger(None, {}, getter, launches_30d=[{"date": "2024-01-05"}])
        self.assertEqual([x["id"] for x in out["ledger"]["since_gcat"]], ["id-002"])


if __name__ == "__main__":
    unittest.main()
