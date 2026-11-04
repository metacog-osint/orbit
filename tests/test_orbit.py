"""Offline tests for Orbit (GCAT owner-code hygiene, Maneuver Compare, TLE gap health, Doctrine Registers, Contract v2 Feed)."""
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from orbit import feed, gcat, maneuver  # noqa: E402
from tic_doctrine import contract, registers  # noqa: E402

_spec = importlib.util.spec_from_file_location("orbit_cli", ROOT / "tools" / "orbit.py")
orbit_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(orbit_cli)


class TestOrbit(unittest.TestCase):
    def test_doctrine_registers_pass(self):
        self.assertEqual(registers.check(ROOT / "doctrine"), [])

    def test_gcat_owner_hygiene_and_siblings(self):
        snap = orbit_cli.build_snapshot()
        hyg = snap["catalog"]["hygiene_summary"]
        self.assertEqual(hyg["soviet_su_separated"], 1)
        self.assertEqual(hyg["russian_ru_separated"], 3)
        self.assertEqual(hyg["unnumbered_active_count"], 1)
        self.assertIn("2026-150", hyg["multi_sibling_launches"])

    def test_maneuver_compare_and_tle_gap_flag(self):
        snap = orbit_cli.build_snapshot()
        ms = {m["jcat"]: m for m in snap["maneuvers"]}
        self.assertIn("S59773", ms)
        self.assertEqual(ms["S59773"]["tier"], "warning")
        self.assertIn("Hypothesis:", ms["S59773"]["meaning_sentence"])
        # Yaogan-43 sibling within 30 days of launch + 84h TLE gap stays routine and triggers a TLE gap flag
        self.assertEqual(ms["S61901"]["tier"], "routine")
        gaps = [g["jcat"] for g in snap["source_health_flags"]]
        self.assertIn("S61901", gaps)

    def test_feed_contract_v2_passes_linter(self):
        snap = orbit_cli.build_snapshot()
        fc = feed.build_feed(snap)
        regs = registers.ids(ROOT / "doctrine")
        self.assertGreaterEqual(len(fc["features"]), 4)
        for feat in fc["features"]:
            errs = [m for _, sev, m in contract.check(feat, regs) if sev == "error"]
            self.assertEqual(errs, [], f"Linter errors on {feat['properties'].get('id')}: {errs}")

    def test_site_build_and_check_all(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(ROOT / "doctrine", tmp / "doctrine")
            shutil.copytree(ROOT / "site_src", tmp / "site_src")
            files = orbit_cli.build_site(tmp)
            self.assertIn("data/feed.geojson", files)
            self.assertIn("index.html", files)
            self.assertEqual(orbit_cli.check_all(tmp), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
