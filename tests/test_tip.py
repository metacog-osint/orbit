"""Predicted reentries from Space-Track TIP messages (orbit/tip.py, lane `decay`).

The fixture is Space-Track's real TIP reply of 17 Nov 2026 (191 messages over 14 days; USSPACECOM, 18th Space
Defense Squadron; basic SSA data redistributed under USSPACECOM's blanket approval with this citation)."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from orbit import tip  # noqa: E402
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("orbit_cli_tip", ROOT / "tools" / "orbit.py")
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)

FIX = ROOT / "tests" / "fixtures" / "spacetrack_tip_20261117.json"
NOW = datetime(2026, 11, 17, 3, 30, tzinfo=timezone.utc)


def rows():
    return json.loads(FIX.read_text(encoding="utf-8"))


class Parse(unittest.TestCase):
    def test_newest_message_per_object_soonest_first(self):
        d = tip.parse(rows(), NOW)
        self.assertEqual(d["messages"], 191)
        got = [(o["norad"], o["decay_epoch"], o["window_min"]) for o in d["objects"]]
        self.assertEqual(got[2], (53892, "2026-11-17T08:59:00Z", 60))  # 02:39 message, not the 14:38 one before it
        self.assertEqual([o["decay_epoch"] for o in d["objects"]], sorted(o["decay_epoch"] for o in d["objects"]))
        self.assertEqual(len({o["norad"] for o in d["objects"]}), len(d["objects"]))
        o = d["objects"][2]
        self.assertEqual((o["messages"], o["next_report_h"], o["direction"]), (6, 2, "descending"))

    def test_open_window_is_not_passed_and_closed_windows_go_after_a_day(self):
        d = tip.parse(rows(), NOW)
        first = d["objects"][0]  # 16 Nov 20:22 plus or minus 18 h: centre behind, window still open
        self.assertEqual((first["norad"], first["passed"]), (47746, False))
        later = tip.parse(rows(), datetime(2026, 11, 17, 15, 0, tzinfo=timezone.utc))
        closed = next(o for o in later["objects"] if o["norad"] == 47746)
        self.assertTrue(closed["passed"])  # window closed at 14:22 on 17 Nov
        gone = tip.parse(rows(), datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc))
        self.assertNotIn(47746, [o["norad"] for o in gone["objects"]])  # over a day after the window closed

    def test_longitude_to_east_west_and_gcat_names(self):
        objects = {"S45710": ["S45710", "45710", "2020-035", "P", "Starlink-1490", "2020 Jun 4", "", "", "O",
                              "SPX", "US", "LLEO/I"]}
        d = tip.parse(rows(), NOW, objects)
        o = next(x for x in d["objects"] if x["norad"] == 45710)
        self.assertEqual(o["lon"], -167.3)  # TIP's 192.7 east
        self.assertEqual((o["name"], o["type"], o["cc"]), ("Starlink-1490", "P", "US"))
        self.assertNotIn("name", next(x for x in d["objects"] if x["norad"] == 53892))

    def test_bad_rows_are_skipped_and_a_non_list_fails(self):
        d = tip.parse([{"NORAD_CAT_ID": "x"}, {"NORAD_CAT_ID": "1", "MSG_EPOCH": "", "DECAY_EPOCH": ""}], NOW)
        self.assertEqual(d["objects"], [])
        with self.assertRaises(ValueError):
            tip.parse({"error": "x"}, NOW)


class FakeTip:
    log: list = []

    def __init__(self, ident, pw):
        self.requests, self.last_body = 0, b""

    def login(self):
        FakeTip.log.append("login")

    def logout(self):
        FakeTip.log.append("logout")

    def query_path(self, url, cls="gp"):
        FakeTip.log.append((cls, url))
        self.last_body = FIX.read_bytes()
        return json.loads(self.last_body)


def _offline(url, timeout=60):
    raise OSError("offline")


class Lane(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(ROOT / "doctrine", self.tmp / "doctrine")
        FakeTip.log = []
        self.patches = [mock.patch.object(cli, "ST_CLIENT", FakeTip),
                        mock.patch.object(cli, "ST_NOW", lambda: NOW)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_lane(self):
        return cli.collect(self.tmp, getter=_offline, header=lambda u: None, only=["decay"])

    def test_one_query_cited_and_url_kept(self):
        with mock.patch.object(cli.spacetrack, "credentials", return_value=("u", "p")):
            snap = self.run_lane()
        self.assertEqual(FakeTip.log, ["login", ("tip", tip.URL), "logout"])
        self.assertEqual(snap["lanes"]["decay"]["status"], "ok")
        self.assertEqual(snap["lanes"]["decay"]["fetches"][0]["url"], tip.URL)
        self.assertEqual(snap["decay"]["attribution"], tip.ATTRIBUTION)
        self.assertIn("18th Space Defense Squadron", tip.ATTRIBUTION)
        self.assertEqual(len(snap["decay"]["objects"]), 7)

    def test_off_without_credentials(self):
        with mock.patch.object(cli.spacetrack, "credentials", return_value=None), \
                mock.patch.dict(os.environ, {}, clear=False):
            snap = self.run_lane()
        self.assertEqual(snap["lanes"]["decay"]["status"], "off")
        self.assertEqual(snap["decay"], {})
        self.assertEqual(FakeTip.log, [])

    def test_lane_is_graded_from_space_track(self):
        self.assertEqual(cli.LANE_SOURCE["decay"], ["space-track"])


if __name__ == "__main__":
    unittest.main()
