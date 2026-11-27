"""The map's rocket bodies and debris (orbit/debrismap.py): one Space-Track GP query a UTC day, the account shared."""
import gzip
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from orbit import debrismap, satmap, spacetrack

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 27, 17, 40, tzinfo=timezone.utc)


def gp(norad, kind="DEBRIS", country="PRC", n="14.2", e="0.0012", **kw):
    row = {"NORAD_CAT_ID": str(norad), "OBJECT_NAME": f"FENGYUN 1C DEB {norad}", "OBJECT_ID": "1999-025ABC",
           "OBJECT_TYPE": kind, "COUNTRY_CODE": country, "LAUNCH_DATE": "1999-05-10", "EPOCH": "2026-11-26T12:00:00.123456",
           "MEAN_MOTION": n, "ECCENTRICITY": e, "INCLINATION": "98.6", "RA_OF_ASC_NODE": "120.5",
           "ARG_OF_PERICENTER": "45.1", "MEAN_ANOMALY": "300.2", "BSTAR": "0.0003", "MEAN_MOTION_DOT": "0.00001"}
    row.update(kw)
    return row


class FakeClient:
    def __init__(self, rows):
        self.rows, self.requests, self.urls = rows, 0, []

    def login(self):
        self.requests += 1

    def logout(self):
        self.requests += 1

    def query_path(self, url, cls="gp"):
        self.requests += 1
        self.urls.append(url)
        return self.rows


class DebrisMap(unittest.TestCase):
    def test_rows_take_the_maps_format_and_owner_groups(self):
        doc = debrismap.parse([gp(30000), gp(25400, "ROCKET BODY", "CIS", n="1.0027"), gp(40000, country="US"),
                               gp(41000, country="ESA"), gp(42000, country="XYZ")], "2026-11-27T17:40:00Z")
        self.assertEqual(doc["fields"], satmap.FIELDS)
        f = {k: i for i, k in enumerate(doc["fields"])}
        got = {r[f["norad"]]: (r[f["group"]], r[f["cc"]], r[f["type"]], r[f["cls"]]) for r in doc["rows"]}
        self.assertEqual(got[30000], ("cn", "CN", "D", "leo"))
        self.assertEqual(got[25400], ("ru", "SU", "R", "geo"))       # CIS: Soviet or Russian, the map's aqua group
        self.assertEqual(got[40000], ("us", "US", "D", "leo"))
        self.assertEqual(got[41000][:2], ("other", "I-ESA"))          # intergovernmental: GCAT's code, no country
        self.assertEqual(got[42000][:2], ("other", "XYZ"))            # a code not mapped is kept as written
        self.assertEqual(doc["by_type"], {"D": 4, "R": 1})
        self.assertIn("Space-Track.org", doc["credit"])
        self.assertIn("blanket approval", doc["credit"])

    def test_a_row_sgp4_cannot_use_is_counted_not_kept(self):
        doc = debrismap.parse([gp(1), gp(2, n=""), gp(3, kind="PAYLOAD"), gp(4, EPOCH="")], "x")
        self.assertEqual((doc["count"], doc["unusable"]), (1, 3))

    def test_the_query_asks_only_for_rocket_bodies_and_debris_on_orbit(self):
        u = debrismap.URL
        self.assertIn("/class/gp/OBJECT_TYPE/ROCKET%20BODY,DEBRIS/", u)
        self.assertIn("/decay_date/null-val/", u)
        self.assertIn("/epoch/%3Enow-30/", u)
        self.assertIn("/predicates/NORAD_CAT_ID,", u)

    def test_one_read_a_utc_day(self):
        self.assertIsNone(debrismap.due(NOW, None))
        self.assertIsNone(debrismap.due(NOW, {"read_at": "2026-11-26T21:30:00Z"}))
        self.assertIn("today", debrismap.due(NOW, {"read_at": "2026-11-27T01:00:00Z"}))

    def test_a_pull_makes_three_requests_and_writes_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = FakeClient([gp(30000), gp(30001, "ROCKET BODY")])
            got = debrismap.pull(Path(tmp), ("u", "p"), NOW, client=c, wait=lambda: 0, busy=lambda t: None)
            self.assertEqual(c.requests, 3)
            self.assertEqual(c.urls, [debrismap.URL])
            held = json.loads(gzip.decompress((Path(tmp) / debrismap.LOCAL).read_bytes()))
            self.assertEqual(held["count"], 2)
            self.assertEqual(got["doc"]["count"], 2)
            # read today: the next run asks nothing
            c2 = FakeClient([])
            with self.assertRaises(spacetrack.NotReady):
                debrismap.pull(Path(tmp), ("u", "p"), datetime.fromisoformat(held["read_at"].replace("Z", "+00:00")),
                               client=c2, wait=lambda: 0, busy=lambda t: None)
            self.assertEqual(c2.requests, 0)

    def test_another_gp_query_within_the_hour_means_no_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = FakeClient([gp(1)])
            with self.assertRaises(spacetrack.NotReady):
                debrismap.pull(Path(tmp), ("u", "p"), NOW, client=c, wait=lambda: 0, busy=lambda t: "GEO run busy")
            self.assertEqual(c.requests, 0)

    def test_an_empty_reply_keeps_the_last_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                debrismap.pull(Path(tmp), ("u", "p"), NOW, client=FakeClient([]), wait=lambda: 0, busy=lambda t: None)
            self.assertFalse((Path(tmp) / debrismap.LOCAL).exists())

    def test_the_three_gp_queries_wait_for_each_other(self):
        self.assertEqual(debrismap.STEP, spacetrack.CATALOG_STEP)
        self.assertIn(f"- name: {debrismap.STEP}", (ROOT / ".github" / "workflows" / "catalog.yml").read_text(encoding="utf-8"))
        self.assertIn(spacetrack.CATALOG, spacetrack.FOR_MANEUVER)
        self.assertIn(spacetrack.CATALOG, spacetrack.FOR_GEO)
        self.assertEqual(set(spacetrack.FOR_DEBRIS), {spacetrack.GEO, spacetrack.UPDATE})

    def test_the_update_run_publishes_the_file_for_the_map(self):
        upd = (ROOT / ".github" / "workflows" / "update.yml").read_text(encoding="utf-8")
        self.assertIn("-p sats-rd.json.gz", upd)
        self.assertIn("site/data/sats-rd.json", upd)
        page = (ROOT / "site_src" / "satmap.js").read_text(encoding="utf-8")
        self.assertIn('getJson("data/sats-rd.json")', page)
        self.assertIn('new Set(["p"])', page)                         # payloads only by default


if __name__ == "__main__":
    unittest.main()
