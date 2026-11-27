"""Private archive (19 Nov 2026): the Space-Track set store keeps every set while the analysis reads the same
120 days as before, and update.yml sends state and raw replies to the PRIVATE tic-archive repo after the deploy."""
from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT / "tools"))   # after ROOT: tools/orbit.py must not shadow the orbit package
sys.path.insert(0, str(ROOT / "tests"))

from orbit import maneuver  # noqa: E402
import tic_archive as ta  # noqa: E402
from test_orbit import NOW_M, synth  # noqa: E402


def old_merge(store, records, now, keep_days=maneuver.KEEP_DAYS):
    """merge() as it was until 19 Nov 2026 (sets older than keep_days dropped), for comparison."""
    cutoff = maneuver._iso(now - timedelta(days=keep_days))
    for rec in records:
        key = str(int(rec["NORAD_CAT_ID"]))
        obj = store.setdefault(key, {"sets": []})
        obj.update({"name": rec.get("OBJECT_NAME"), "object_id": rec.get("OBJECT_ID"),
                    "country": rec.get("COUNTRY_CODE"), "decay": rec.get("DECAY_DATE")})
        row = maneuver.norm(rec)
        by_epoch = {s[0]: s for s in obj["sets"]}
        old = by_epoch.get(row[0])
        if old is None or row[7] >= old[7]:
            by_epoch[row[0]] = row
        obj["sets"] = sorted((s for s in by_epoch.values() if s[0] >= cutoff), key=lambda s: s[0])
    return store


class SetStore(unittest.TestCase):
    def runs(self):
        """200 days of sets, merged in three runs as the lane does (history first, then GP top-ups)."""
        recs = synth(7, days=200, per_day=2, burns=[(150, 2e-5, 0.0), (190, 3e-5, 0.0)])
        return [(recs[:250], NOW_M - timedelta(days=60)), (recs[250:340], NOW_M - timedelta(days=15)),
                (recs[340:], NOW_M)]

    def test_store_keeps_every_set(self):
        store = {}
        for recs, now in self.runs():
            maneuver.merge(store, recs, now)
        self.assertEqual(len(store["7"]["sets"]), 400)

    def test_analysis_reads_exactly_what_it_read_before(self):
        new, old = {}, {}
        for recs, now in self.runs():
            maneuver.merge(new, copy.deepcopy(recs), now)
            old_merge(old, copy.deepcopy(recs), now)
        self.assertEqual(maneuver.view(new["7"]), old["7"]["sets"])
        self.assertLess(len(old["7"]["sets"]), len(new["7"]["sets"]))
        d_new = maneuver.detect(new["7"], NOW_M)
        d_old = maneuver.detect(old["7"], NOW_M)
        self.assertEqual(d_new, d_old)
        self.assertEqual(maneuver.report(new, NOW_M), maneuver.report(old, NOW_M))

    def test_store_written_before_the_change_reads_as_is(self):
        old = old_merge({}, synth(9, days=60), NOW_M)
        self.assertNotIn("view_from", old["9"])
        self.assertEqual(maneuver.view(old["9"]), old["9"]["sets"])

    def test_object_without_new_records_keeps_its_old_view(self):
        new, old = {}, {}
        maneuver.merge(new, synth(5, days=40, end=NOW_M - timedelta(days=200)), NOW_M - timedelta(days=200))
        old_merge(old, synth(5, days=40, end=NOW_M - timedelta(days=200)), NOW_M - timedelta(days=200))
        maneuver.merge(new, synth(6, days=40), NOW_M)       # a run that touched another object only
        old_merge(old, synth(6, days=40), NOW_M)
        self.assertEqual(maneuver.view(new["5"]), old["5"]["sets"])


class LedgerWorkflow(unittest.TestCase):
    def test_retired_ledger_workflow_is_gone(self):
        """orbit-2.32: the launch ledger is Launch's. The do-nothing stub went once the hub's dispatcher stopped
        starting it."""
        self.assertFalse((ROOT / ".github" / "workflows" / "ledger.yml").exists())

    def test_one_snapshot_a_day_and_nothing_replaced(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "state"
            src.mkdir()
            ledger = src / "launch-ledger.json"
            (src / "other.json").write_text("{}", encoding="utf-8")
            arc = ta.Archive(ta.DirStore(Path(td) / "store"), "orbit", "ledger")
            t0 = NOW_M
            ledger.write_text('{"v":1}', encoding="utf-8")
            first = arc.put(src, include=["launch-ledger.json"], min_interval_hours=23, now=t0)
            self.assertEqual(first["status"], "uploaded")
            self.assertEqual([f["path"] for f in first["doc"]["files"]], ["launch-ledger.json"])
            ledger.write_text('{"v":2}', encoding="utf-8")
            soon = arc.put(src, include=["launch-ledger.json"], min_interval_hours=23, now=t0 + timedelta(hours=1))
            self.assertEqual(soon["status"], "too-soon")
            next_day = arc.put(src, include=["launch-ledger.json"], min_interval_hours=23, now=t0 + timedelta(hours=24))
            self.assertEqual(next_day["status"], "uploaded")
            self.assertEqual(next_day["doc"]["previous"], ta.utc_stamp(t0))


class Workflow(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / ".github" / "workflows" / "update.yml").read_text(encoding="utf-8")

    def test_private_step_after_deploy_with_its_own_token(self):
        deploy = self.text.index("- name: Deploy site/ to Cloudflare Pages")
        step = self.text.index("- name: Private archive (Space-Track state and raw replies, to tic-archive)")
        self.assertLess(deploy, step)
        block = self.text[step:]
        self.assertIn("GH_TOKEN: ${{ secrets.TIC_ARCHIVE_TOKEN }}", block)
        self.assertNotIn("github.token", block)
        self.assertIn("--lane state --src data/state", block)
        self.assertIn("--lane raw --src data/raw", block)
        self.assertIn("exit 1", block)          # a missing token fails loudly

    def test_private_data_never_in_artifacts(self):
        for chunk in self.text.split("uses: actions/upload-artifact")[1:]:
            path = chunk.split("path:", 1)[1].split("\n", 1)[0]
            self.assertNotIn("data/state", path)
            self.assertNotIn("data/raw", path)

    def test_excludes_keep_spacetrack_and_drop_gcat(self):
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "raw"
            for rel in ("spacetrack-gp/a.json", "spacetrack-tip/b.json", "celestrak-gp/c.json.gz",
                        "nga-api/d.json", "swf-rpo-x/e.csv", "gcat-satcat/f.tsv.gz", "tic-catalog-names/g.json.gz",
                        "orbit-ledger/h.json.gz", "index.jsonl"):
                (raw / rel).parent.mkdir(parents=True, exist_ok=True)
                (raw / rel).write_text(rel, encoding="utf-8")
            store = ta.DirStore(Path(td) / "store")
            r = ta.Archive(store, "orbit", "raw").put(raw, exclude=["gcat-*", "tic-*", "orbit-ledger/*"], now=NOW_M)
            got = sorted(f["path"] for f in r["doc"]["files"])
            self.assertEqual(got, ["celestrak-gp/c.json.gz", "index.jsonl", "nga-api/d.json",
                                   "spacetrack-gp/a.json", "spacetrack-tip/b.json", "swf-rpo-x/e.csv"])


if __name__ == "__main__":
    unittest.main()
