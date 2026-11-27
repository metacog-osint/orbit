"""Anomalies against GCAT's history (orbit-2.49): 30-day counts outside every prior window, and breakups."""
from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from orbit import feed, gcat  # noqa: E402
from tic_doctrine import contract, registers  # noqa: E402

REGS = registers.ids(ROOT / "doctrine")
GEN = "2026-11-27T12:00:00Z"
AT = "2026-11-27T03:00:00Z"


def row(recent, prior, high=0.0, low=0.0, key="SPX", **extra):
    """A baseline row as gcat._rows makes it: prior is the 24 windows before the recent one, newest first."""
    counts = [recent, *prior]
    return {"key": key, **gcat._position(recent, prior), "series": counts[::-1],
            "flag_rate": {"high": high, "low": low, "windows": 24}, **extra}


def base(**series):
    return {"window_days": 30, "prior_windows": 24, "recent": ["2026-10-29", "2026-11-27"],
            "prior": ["2024-11-08", "2026-10-28"], **series}


def errors(f):
    return [m for _, sev, m in contract.check(f, REGS) if sev == "error"]


class FlagRate(unittest.TestCase):
    def test_flat_series_never_fires(self):
        self.assertEqual(gcat._flag_rates([5] * 49), {"high": 0.0, "low": 0.0, "windows": 24})

    def test_short_history_has_no_rate(self):
        self.assertIsNone(gcat._flag_rates([5] * 30))

    def test_growing_series_fires_high_every_window(self):
        counts = list(range(49, 0, -1))  # newest first: each window above all before it
        self.assertEqual(gcat._flag_rates(counts)["high"], 1.0)
        self.assertEqual(gcat._flag_rates(counts)["low"], 0.0)

    def test_one_spike_counts_once(self):
        counts = [5] * 49
        counts[10] = 9  # window 10 is above its own 24 before it; the windows after it no longer are
        self.assertEqual(gcat._flag_rates(counts)["high"], round(1 / 24, 4))

    def test_rows_show_25_windows_and_carry_the_rate(self):
        series = {"A": [3] + [4] * 48, "old": [0] * 25 + [7] * 24}
        rows = gcat._rows(series, lambda k: {"key": k})
        self.assertEqual([r["key"] for r in rows], ["A"])  # a key with nothing in the 25 shown windows is left out
        self.assertEqual(len(rows[0]["series"]), 25)
        self.assertEqual((rows[0]["position"], rows[0]["flag_rate"]["low"]), ("below", 0.0))

    def test_baseline_counts_breakups_and_keeps_its_prior_span(self):
        today = date(2026, 11, 27)
        objs = [{"type": "D", "state": "CN", "ldate": "2020 Jan  1", "status": "E",
                 "ddate": (today - timedelta(days=200)).strftime("%Y %b %d")}]
        b = gcat.baseline([], objs, {}, today)
        self.assertEqual(b["prior"], ["2024-11-08", "2026-10-28"])
        (r,) = b["breakups_all"]
        self.assertEqual((r["recent"], sum(r["series"][:-1])), (0, 1))


class Counts(unittest.TestCase):
    PRIOR = [9, 12, 15, 18, 13, 14, 15, 16, 10, 11, 17, 15, 14, 13, 16, 15, 12, 18, 15, 14, 13, 16, 15, 15]

    def test_low_launch_count_is_an_anomaly_with_signal_and_baseline(self):
        b = base(launches_by_agency=[row(7, self.PRIOR, name="SpaceX", state="US", country="US")])
        (f,) = feed.baseline_features(b, GEN, AT)
        p = f["properties"]
        self.assertEqual((p["tier"], p["kind"], p["id"]), ("anomaly", "observation", "orbit:baseline:launches_by_agency:spx"))
        self.assertEqual((p["signal"]["value"], p["signal"]["tail"], p["signal"]["baseline_n"]), (7, "low", 24))
        self.assertEqual(p["baseline_ref"]["flag_rate"], 0.0)
        self.assertEqual(p["countries"], ["US"])
        self.assertIn("fewer than in any of the 24 windows", p["title"])
        self.assertIn("not a warning", p["summary"])
        self.assertIn("one to three days", p["summary"])
        self.assertIsNone(f["geometry"])
        self.assertEqual(errors(f), [])

    def test_series_the_rule_fires_on_too_often_is_not_flagged(self):
        b = base(launches_by_agency=[row(30, self.PRIOR, high=2 / 24)])
        self.assertEqual(feed.baseline_features(b, GEN, AT), [])
        b = base(launches_by_agency=[row(30, self.PRIOR, high=1 / 24)])
        self.assertEqual(len(feed.baseline_features(b, GEN, AT)), 1)

    def test_low_reentries_and_payloads_are_lag_not_anomalies(self):
        b = base(reentries_all=[row(95, [110 + i for i in range(24)], key="all")],
                 payloads_by_owner=[row(5, [9 + i % 3 for i in range(24)], key="US", state="US", country="US")])
        self.assertEqual(feed.baseline_features(b, GEN, AT), [])

    def test_high_reentries_are(self):
        b = base(reentries_all=[row(300, [110 + i for i in range(24)], key="all")])
        (f,) = feed.baseline_features(b, GEN, AT)
        self.assertEqual(f["properties"]["signal"]["tail"], "high")
        self.assertNotIn("one to three days", f["properties"]["summary"])

    def test_small_counts_are_left_out(self):
        b = base(launches_by_agency=[row(2, [0, 1] * 12), row(1, [2, 4] * 12, key="X")])
        self.assertEqual(feed.baseline_features(b, GEN, AT), [])

    def test_within_is_never_flagged(self):
        self.assertEqual(feed.baseline_features(base(launches_all=[row(14, self.PRIOR, key="all")]), GEN, AT), [])

    def test_old_baseline_makes_no_items(self):
        b = base(launches_by_agency=[row(7, self.PRIOR)])
        self.assertEqual(len(feed.baseline_features(b, "2026-11-30T23:00:00Z", AT)), 1)
        self.assertEqual(feed.baseline_features(b, "2026-12-01T01:00:00Z", AT), [])

    def test_build_feed_carries_them(self):
        snap = {"generated_at": GEN, "lanes": {"catalog": {"status": "ok", "fetched_at": AT}},
                "baseline": base(launches_by_agency=[row(7, self.PRIOR)])}
        doc = feed.build_feed(snap)
        self.assertEqual([x["properties"]["tier"] for x in doc["features"]], ["anomaly"])


class Breakups(unittest.TestCase):
    B = {"jcat": "S2", "norad": 99002, "name": "TEST S2", "type": "rocket stage", "launch_tag": "2020-001",
         "launch_date": "2020-01-01", "parent": "", "state": "CN", "country": "CN", "owner": "", "status": "E",
         "op_orbit": "LEO/I", "breakup_date": "2026-11-10", "breakup_time": None, "breakup_uncertain": False}

    def item(self, generated, **b):
        bs = base(breakups_all=[{"key": "all", "recent": 1, "series": [0] * 20 + [1, 0, 0, 0, 1]}])
        return feed._breakup_item({**self.B, **b}, generated, AT, bs)

    def test_anomaly_for_72_hours_from_the_listing(self):
        f = self.item("2026-11-27T12:00:00Z", first_listed="2026-11-26T03:00:00Z")
        p = f["properties"]
        self.assertEqual((p["tier"], p["last_change_at"], p["event_start"]),
                         ("anomaly", "2026-11-26T03:00:00Z", "2026-11-10T00:00:00Z"))
        self.assertEqual(p["measures"]["breakups_in_prior_24_windows"], 1)
        self.assertIn("for 72 hours from the reading that first listed it", p["summary"])
        self.assertEqual(errors(f), [])
        self.assertEqual(self.item("2026-11-29T04:00:00Z", first_listed="2026-11-26T03:00:00Z")["properties"]["tier"],
                         "routine")

    def test_no_listing_stays_routine(self):
        self.assertEqual(self.item(GEN)["properties"]["tier"], "routine")


class FirstListed(unittest.TestCase):
    """tools/orbit.py stamps first_listed: carried from the previous snapshot, the reading's time when new."""

    def stamp(self, prev, index_doc):
        seen = {b["jcat"]: b.get("first_listed") or f"{b['breakup_date'][:10]}T00:00:00Z"
                for b in prev.get("breakups") or [] if b.get("jcat")}
        return lambda b: seen.get(b["jcat"]) or (AT if index_doc else f"{b['breakup_date'][:10]}T00:00:00Z")

    def test_rules_match_the_collector(self):
        src = (ROOT / "tools" / "orbit.py").read_text(encoding="utf-8")
        self.assertIn('b.get("first_listed") or f"{b[\'breakup_date\'][:10]}T00:00:00Z"', src)
        s = self.stamp({"breakups": [{"jcat": "S1", "breakup_date": "2026-11-01"}]}, {"read_at": "x"})
        self.assertEqual(s({"jcat": "S1", "breakup_date": "2026-11-01"}), "2026-11-01T00:00:00Z")  # carried, not new
        self.assertEqual(s({"jcat": "S2", "breakup_date": "2026-11-20"}), AT)  # new since the last reading
        s = self.stamp({}, None)
        self.assertEqual(s({"jcat": "S3", "breakup_date": "2026-11-20"}), "2026-11-20T00:00:00Z")  # first reading


if __name__ == "__main__":
    unittest.main()
