"""TIP predictions against TIP's own and GCAT's reentry times (tip.check, archive `tip`; orbit-2.17).

Fixtures: Space-Track's real TIP reply of 17 Nov 2026 (USSPACECOM, 18th Space Defense Squadron; basic SSA data under
USSPACECOM's blanket approval, with this citation) and GCAT's reentries for the same objects from Orbit's live
snapshot of 18 Nov 2026 (Jonathan McDowell, CC BY 4.0)."""
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

from orbit import archive, tip  # noqa: E402
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("orbit_cli_tipcheck", ROOT / "tools" / "orbit.py")
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)

FIX = ROOT / "tests" / "fixtures"
NOW = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)


def tip_rows():
    return json.loads((FIX / "spacetrack_tip_20261117.json").read_text(encoding="utf-8"))


def gcat_rows():
    return json.loads((FIX / "gcat_reentries_20261118.json").read_text(encoding="utf-8"))["reentries"]


def by(c):
    return {o["norad"]: o for o in c["objects"]}


class Compact(unittest.TestCase):
    def test_every_message_oldest_first(self):
        m = tip.compact(tip_rows())
        self.assertEqual(len(m), 191)
        self.assertEqual([x[1] for x in m], sorted(x[1] for x in m))
        self.assertIn([53892, "2026-11-17T02:39:00Z", "2026-11-17T08:59:00Z", 60, 67698], m)

    def test_parse_carries_them(self):
        self.assertEqual(len(tip.parse(tip_rows(), NOW)["all_messages"]), 191)


class Check(unittest.TestCase):
    def setUp(self):
        self.c = tip.check(tip.compact(tip_rows()), gcat_rows(), NOW)
        self.o = by(self.c)

    def test_counts(self):
        c = self.c
        self.assertEqual((c["with_after"], c["inside"], c["gcat_same_minute"]), (20, 17, 18))  # 18 of the 19 GCAT dates; 28485 not dated, 57418 7 days off
        self.assertEqual(c["gcat_day_or_more"], [57418])
        self.assertEqual(c["kept_since"][:10], "2026-11-03")

    def test_last_prediction_against_tip_after(self):
        x = self.o[51775]  # Starlink 3620: predicted 00:19 +-44, TIP after the reentry 00:18
        self.assertEqual(x["predicted"]["decay_epoch"], "2026-11-13T00:19:00Z")
        self.assertEqual(x["after"]["decay_epoch"], "2026-11-13T00:18:00Z")
        self.assertEqual((x["offset_min"], x["inside"]), (-1, True))
        self.assertEqual(x["gcat"]["minus_tip_min"], 0)

    def test_outside_the_window(self):
        x = self.o[58706]  # Starlink 11075: last prediction 17 Nov 23:31 +-900, down 15 Nov 17:14
        self.assertFalse(x["inside"])
        self.assertEqual(x["offset_min"], -3257)
        self.assertEqual(x["lead_h"], 12.1)

    def test_gcat_seven_days_from_tip(self):
        x = self.o[57418]  # Starlink 30221: TIP after the reentry 10 Nov 17:37; GCAT 17 Nov 17:37
        self.assertEqual(x["after"]["decay_epoch"], "2026-11-10T17:37:00Z")
        self.assertEqual(x["gcat"]["minus_tip_min"], 7 * 1440)

    def test_late_wide_message_stays_a_prediction(self):
        x = self.o[45755]  # issued after its time with a 39-minute window: no TIP time after the reentry
        self.assertNotIn("after", x)
        self.assertEqual(x["predicted"]["window_min"], 39)
        self.assertTrue(x["gcat"]["uncertain"])
        self.assertEqual(x["gcat"]["minus_tip_min"], 12)

    def test_open_windows_and_old_reentries_left_out(self):
        self.assertNotIn(53665, self.o)  # predicted 19 Nov
        later = tip.check(tip.compact(tip_rows()), gcat_rows(), datetime(2026, 12, 4, tzinfo=timezone.utc))
        self.assertNotIn(45555, by(later))  # 3 Nov, over 30 days before 4 Dec
        self.assertIn(53892, by(later))

    def test_duplicates_count_once(self):
        m = tip.compact(tip_rows())
        self.assertEqual(tip.check(m + m, gcat_rows(), NOW)["objects"], self.c["objects"])

    def test_no_gcat_row(self):
        self.assertNotIn("gcat", self.o[28485])
        self.assertEqual(self.c["gcat_not_yet"], sum(1 for o in self.c["objects"] if "gcat" not in o))


def snap(at, status="ok", msgs=None, from_previous=False):
    lane = {"status": status}
    if from_previous:
        lane["from_previous"] = True
    return {"generated_at": at, "lanes": {"decay": lane},
            "decay": {"attribution": tip.ATTRIBUTION, "all_messages": msgs if msgs is not None else tip.compact(tip_rows())}}


class Archive(unittest.TestCase):
    def test_each_message_kept_once(self):
        doc = archive.record(None, snap("2026-11-17T04:00:00Z"))
        doc = archive.record(doc, snap("2026-11-17T10:00:00Z"))
        doc = archive.record(doc, snap("2026-11-18T04:00:00Z"))
        self.assertEqual(len(doc["days"]["2026-11-17"]["tip"]), 191)
        self.assertNotIn("tip", doc["days"]["2026-11-18"])
        self.assertEqual(len(archive.tip_messages(doc)), 191)
        self.assertEqual(doc["tip_attribution"], tip.ATTRIBUTION)
        self.assertEqual(archive.summary(doc, NOW.date())["tip_messages"], 191)

    def test_new_message_added_on_its_day(self):
        doc = archive.record(None, snap("2026-11-17T04:00:00Z"))
        extra = [53668, "2026-11-17T18:01:00Z", "2026-11-17T16:30:00Z", 1, 99999]
        doc = archive.record(doc, snap("2026-11-18T04:00:00Z", msgs=tip.compact(tip_rows()) + [extra]))
        self.assertEqual(doc["days"]["2026-11-18"]["tip"], [extra])

    def test_carried_lane_not_kept(self):
        doc = archive.record(None, snap("2026-11-17T04:00:00Z", from_previous=True))
        self.assertNotIn("tip", doc["days"]["2026-11-17"])
        doc = archive.record(None, snap("2026-11-17T04:00:00Z", status="failed"))
        self.assertEqual(archive.tip_messages(doc), [])

    def test_merge_keeps_attribution(self):
        doc = archive.record(None, snap("2026-11-17T04:00:00Z"))
        self.assertEqual(archive.merge(None, doc)["tip_attribution"], tip.ATTRIBUTION)


class Collect(unittest.TestCase):
    def test_archive_run_sets_tip_check(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            s = snap("2026-11-18T15:00:00Z")
            s["reentries"] = gcat_rows()
            out = cli._archive_run(tmp, s, getter=lambda *_: (_ for _ in ()).throw(OSError("offline")))
            self.assertEqual(out["tip_messages"], 191)
            self.assertEqual(s["tip_check"]["with_after"], 20)
            self.assertEqual(s["tip_check"]["attribution"], tip.CHECK_ATTRIBUTION)
        finally:
            shutil.rmtree(tmp)

    def test_no_messages_no_block(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            s = {"generated_at": "2026-11-18T15:00:00Z", "lanes": {}}
            cli._archive_run(tmp, s, getter=lambda *_: (_ for _ in ()).throw(OSError("offline")))
            self.assertEqual(s["tip_check"], {})
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
