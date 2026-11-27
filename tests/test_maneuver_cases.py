"""The orbit-change detector on the stored known cases (Space-Track GP_HISTORY reads in data/state/spacetrack/).

Raw element sets are not republished, so the case files are not in the repository and these tests are skipped
where they are missing (CI included). Where they are present they pin what docs/validation/maneuver-calibration.md
reports, so a change to the detector that moves a calibration result fails here first."""
import gzip
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from orbit import maneuver  # noqa: E402

ST = ROOT / "data" / "state" / "spacetrack"


def run(case: dict) -> dict:
    p = ST / case["file"]
    records = json.loads(gzip.decompress(p.read_bytes()))
    now = datetime.fromisoformat(case["now"].replace("Z", "+00:00"))
    store = maneuver.merge({}, records, now, keep_days=case.get("keep_days", 400))
    return maneuver.report(store, now, case["window_days"])


def out_and_back(events: list) -> int:
    """Pairs of consecutive single-pair changes with the same main term, the first ending where the second begins,
    whose inclination (cross-track) or semi-major-axis (in-track) changes have opposite signs and cancel to within
    half of the larger: the pattern one element set lying off the orbit gives (calibration doc)."""
    n = 0
    for a, b in zip(events, events[1:]):
        key = {"cross-track": "di_deg", "in-track": "da_km"}.get(a["dominant"])
        if not key or a["pairs"] != 1 or b["pairs"] != 1 or a["dominant"] != b["dominant"] or a["to"] != b["from"]:
            continue
        x, y = a[key], b[key]
        if x * y < 0 and abs(x + y) <= 0.5 * max(abs(x), abs(y)):
            n += 1
    return n


def cases():
    """The case table in tools/orbit.py (a script, loaded without running its command line)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("orbit_cli", ROOT / "tools" / "orbit.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    return cli.CASES


class KnownCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = cases()

    def need(self, name):
        if not (ST / self.cases[name]["file"]).exists():
            self.skipTest(f"case file {self.cases[name]['file']} not here (never committed)")
        return self.cases[name]

    def test_iss_every_announced_reboost_and_nothing_else(self):
        case = self.need("iss")
        rep = run(case)
        sc = maneuver.score(rep["events"], case["announced"], case["tolerance_h"], case.get("storm"))
        self.assertEqual((sc["hits"], sc["misses"], len(sc["extra"])), (5, 0, 0))
        self.assertEqual(len(rep["events"]), 10)
        self.assertEqual(rep["objects"][0]["leo_off_track"], 11)

    def test_sj21_tow_and_return_are_listed(self):
        rep = run(self.need("sj21"))
        by = {o["norad"]: o for o in rep["objects"]}
        g2 = [e for e in by[34779]["events"] if e["da_km"] > 1000]
        self.assertEqual(len(g2), 1)  # BeiDou-2 G2 raised to the graveyard, 22-27 Jan 2022
        sj = by[49330]["events"]
        # orbit-2.47: the out-and-back pair of 27-28 Dec 2021 (one set) is not listed (15 to 13); orbit-2.54: two
        # plane changes whose net size across 3 sets either side is under 0.25 m/s are counted, not listed (13 to 11)
        self.assertEqual(len(sj), 11)
        self.assertEqual((by[49330]["episode_below_report"], by[49330]["episode_merged"]), (2, 0))
        self.assertEqual((by[49330]["one_set"], by[49330]["one_set_epochs"]), (1, ["2021-12-27T14:50:09Z"]))
        self.assertEqual(out_and_back(sj), 0)
        self.assertTrue(all(e.get("confirmed_by") for o in rep["objects"] for e in o["events"]))
        self.assertTrue(any(e["da_km"] > 1000 for e in sj) and any(e["da_km"] < -1000 for e in sj))
        self.assertEqual([e["from"] for e in by[34779]["events"] if e["from"] < "2022-01-21"], [])  # dead G2: none

    def test_luch2_counts(self):
        rep = run(self.need("luch2"))
        o = rep["objects"][0]
        terms = {}
        for e in o["events"]:
            terms[e["dominant"]] = terms.get(e["dominant"], 0) + 1
        # orbit-2.47: 176 listed before the confirming set; 49 sets left out as one set off the orbit
        # orbit-2.54: 71 cross-track changes come to 39 listings (24 folded into episodes, 6 episodes netting under
        # 0.25 m/s); in-track (the relocations) and eccentricity unchanged
        self.assertEqual(terms, {"in-track": 40, "cross-track": 39, "eccentricity": 8})
        self.assertEqual((o["episode_merged"], o["episode_below_report"], o["awaiting_settle"]), (24, 6, 0))
        self.assertEqual((o["below_report"], o["one_set"], o["awaiting_next_set"]), (168, 49, 0))
        self.assertEqual(out_and_back(o["events"]), 1)  # 21 before


if __name__ == "__main__":
    unittest.main()
