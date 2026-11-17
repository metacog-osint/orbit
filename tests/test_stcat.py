"""TIC's satellite catalog, build step 3: Space-Track SATCAT and DECAY (orbit/stcat.py, orbit/catalog.py).

Fixtures, rows unchanged:
- spacetrack_satcat_20261117.json: Space-Track's class satcat (CURRENT/Y) reply of 17 Nov 2026 18:09 UTC, cut to the
  design note's test objects (55841, 40258, 43874, 43917, 40208, GSSAP 1-8) and six objects the real reading
  flagged: 24905 and 25105 (Iridium 46 and 24, designations swapped between the two catalogs), 45565 (Starlink-1357,
  decayed 16 Nov, after GCAT's 15 Nov file), 12842 and 12845 (SJ-2 and SJ-2B, names swapped), 23558 (GFZ-1, released
  from Mir: Space-Track gives Mir's launch date, GCAT the release).
- spacetrack_decay_20261117.json: every class decay message for those objects in the same reading.
- catalog_satcat_extra.tsv: GCAT satcat rows of 15 Nov 2026 for the six extra objects (catalog_satcat.tsv holds the
  13 test objects' rows of 13 Nov).
Space-Track data: United States Space Command (USSPACECOM), 18th Space Defense Squadron, redistributed under
USSPACECOM's blanket approval for basic SSA data. GCAT: J. McDowell, planet4589.org/space/gcat, CC BY 4.0.
"""
import gzip
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orbit import catalog, gcat, spacetrack, stcat  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
SATCAT = json.loads((FIX / "spacetrack_satcat_20261117.json").read_text(encoding="utf-8"))
DECAY = json.loads((FIX / "spacetrack_decay_20261117.json").read_text(encoding="utf-8"))
ST_READ = "2026-11-17"
TEST = ["55841", "40258", "43874", "43917", "40208", "40099", "40100", "41744", "41745", "51280", "51281",
        "67759", "67760"]


def gcat_tables(extra=True):
    rows = gcat.parse_tsv((FIX / "catalog_satcat.tsv").read_bytes())
    if extra:
        rows += gcat.parse_tsv((FIX / "catalog_satcat_extra.tsv").read_bytes())
    return {"satcat": rows}


ORGS = gcat.orgs_table(gcat.parse_tsv((FIX / "catalog_orgs.tsv").read_bytes()))


def build(extra=True, satcat=None):
    return catalog.build(gcat_tables(extra), ORGS, "2026-11-15", gcat_updated="2026 Nov 15 1018:34",
                         spacetrack={"satcat": SATCAT if satcat is None else satcat, "decay": DECAY,
                                     "read": ST_READ, "read_at": "2026-11-17T18:09:25Z"})


DOC = build()
OBJ = DOC["objects"]


def st(e, field):
    return [r for r in e[field] if r["source"] == "space-track"]


def values(e, field, source=None):
    return [r["value"] for r in e[field] if source is None or r["source"] == source]


class Schedule(unittest.TestCase):
    def t(self, s):
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)

    def test_only_after_1700_utc(self):
        self.assertIn("after 17:00 UTC", stcat.due(self.t("2026-11-17T16:59:00"), {}))
        self.assertIsNone(stcat.due(self.t("2026-11-17T17:00:00"), {}))

    def test_once_a_day(self):
        state = {"satcat_day": "2026-11-17", "satcat_read_at": "2026-11-17T18:09:25Z"}
        self.assertIn("already read", stcat.due(self.t("2026-11-17T23:30:00"), state))
        self.assertIn("after 17:00 UTC", stcat.due(self.t("2026-11-18T08:00:00"), state))
        self.assertIsNone(stcat.due(self.t("2026-11-18T17:01:00"), state))

    def test_decay_history_once_then_recent_messages(self):
        now = self.t("2026-11-19T18:00:00")
        self.assertEqual(stcat.decay_url({}, now), stcat.DECAY_ALL_URL)
        url = stcat.decay_url({"decay_read_at": "2026-11-17T18:09:25Z"}, now)
        self.assertIn("/decay/MSG_EPOCH/%3E2026-11-16/", url)

    def test_satcat_url_is_one_current_query(self):
        self.assertIn("/class/satcat/CURRENT/Y/", stcat.SATCAT_URL)


class FakeClient:
    def __init__(self, replies):
        self.replies, self.urls, self.requests, self.last_body = list(replies), [], 0, b""

    def login(self):
        self.requests += 1

    def logout(self):
        self.requests += 1

    def query_path(self, url, cls="gp"):
        self.urls.append(url)
        self.requests += 1
        self.last_body = json.dumps(self.replies.pop(0)).encode()
        return json.loads(self.last_body)


class Pull(unittest.TestCase):
    def test_four_requests_raw_kept_store_merged_and_no_second_read_that_day(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            now = datetime(2026, 11, 17, 18, 9, 25, tzinfo=timezone.utc)
            c = FakeClient([SATCAT, DECAY])
            got = stcat.pull(d, ("x", "y"), now=now, client=c, wait=lambda: 0)
            self.assertEqual(c.requests, 4)
            self.assertEqual(c.urls, [stcat.SATCAT_URL, stcat.DECAY_ALL_URL])
            self.assertEqual(got["state"]["decay_held"], len(DECAY))
            self.assertEqual(len(list((d / "raw" / "spacetrack-satcat").glob("*.json.gz"))), 1)
            self.assertEqual(len(list((d / "raw" / "spacetrack-decay").glob("*.json.gz"))), 1)
            with self.assertRaises(spacetrack.NotReady):
                stcat.pull(d, ("x", "y"), now=now.replace(hour=23), client=FakeClient([]), wait=lambda: 0)
            # next day: only recent messages are asked for; the held history is kept and nothing is doubled
            new = dict(DECAY[0], MSG_EPOCH="2026-11-18 18:00:00")
            c2 = FakeClient([SATCAT, [DECAY[1], new]])
            got2 = stcat.pull(d, ("x", "y"), now=now.replace(day=18), client=c2, wait=lambda: 0)
            self.assertIn("MSG_EPOCH/%3E2026-11-16", c2.urls[1])
            self.assertEqual(got2["state"]["decay_added"], 1)
            self.assertEqual(got2["state"]["decay_held"], len(DECAY) + 1)
            self.assertEqual(len(stcat.load_local(d)["decay"]), len(DECAY) + 1)


class Records(unittest.TestCase):
    def test_every_space_track_value_is_a_record(self):
        for key in TEST:
            e = OBJ[key]
            for field in ("intldes", "launch_date", "names", "state", "decayed"):
                recs = st(e, field)
                self.assertTrue(recs, (key, field))
                for r in recs:
                    self.assertEqual((r["read"], r["ref"]), (ST_READ, key))
                    self.assertIn(r["basis"], ("attributed", "catalog"))

    def test_gcat_values_stay_beside_space_tracks(self):
        e = OBJ["40208"]
        self.assertEqual(values(e, "intldes"), ["2014-055A", "2014-055A"])
        self.assertEqual([r["source"] for r in e["intldes"]], ["gcat-mcdowell", "space-track"])
        self.assertIn("NEMESIS 2", values(e, "names"))
        self.assertIn("CLIO", values(e, "names"))

    def test_display_names(self):
        got = {k: OBJ[k]["name"] for k in TEST}
        self.assertEqual(got["40208"], "USA 257 (NEMESIS 2)")
        self.assertEqual(got["40099"], "USA 253 (Hornet 1)")  # GCAT's PLName comes before its AltNames
        self.assertEqual(got["67760"], "USA 583 (Hornet 8)")
        self.assertEqual(got["55841"], "LUCH (OLYMP) 2")  # SWF's "Luch (Olymp) 2" is Space-Track's own name
        self.assertEqual(got["40258"], "LUCH (OLYMP)")
        self.assertEqual(got["43874"], "TJS-3")
        self.assertEqual(got["43917"], "TJS-3 AKM")

    def test_name_basis(self):
        self.assertEqual(st(OBJ["40208"], "names")[0]["basis"], "catalog")      # USA 257
        self.assertEqual(st(OBJ["55841"], "names")[0]["basis"], "attributed")   # LUCH (OLYMP) 2

    def test_country_kept_as_given_and_compared_as_gcat_state(self):
        r = st(OBJ["55841"], "state")[0]
        self.assertEqual((r["value"], r["cmp"]), ("CIS", "RU"))
        self.assertEqual(st(OBJ["43874"], "state")[0]["cmp"], "CN")
        self.assertTrue(stcat.state_matches("CIS", "SU"))
        self.assertFalse(stcat.state_matches("PRC", "US"))

    def test_test_objects_agree(self):
        for key in TEST:
            self.assertEqual(OBJ[key]["disagreements"], [], key)


class Disagreements(unittest.TestCase):
    def test_iridium_designations_swapped_listed_not_resolved(self):
        for key, gc, sp in (("24905", "1997-082B", "1997-043C"), ("25105", "1997-043C", "1997-082B")):
            e = OBJ[key]
            fields = {d["field"]: d for d in e["disagreements"]}
            self.assertEqual(set(fields), {"intldes", "launch_date"})
            self.assertEqual(fields["intldes"]["claims"], [{"value": gc, "sources": ["gcat-mcdowell"]},
                                                           {"value": sp, "sources": ["space-track"]}])
            self.assertEqual(values(e, "intldes"), [gc, sp])  # both kept

    def test_decayed_after_gcats_file(self):
        e = OBJ["45565"]
        self.assertEqual([d["field"] for d in e["disagreements"]], ["decayed"])
        self.assertEqual(st(e, "decayed")[0]["date"], "2026-11-16")
        # SATCAT's DECAY and the DECAY class's Historical message; predictions are not decay dates
        self.assertEqual([(r["value"], r["field"]) for r in e["decay_date"]],
                         [("2026-11-16", "SATCAT DECAY"), ("2026-11-16", "DECAY")])
        self.assertEqual(e["decay_date"][1]["msg_type"], "Historical")

    def test_station_release_date_differs(self):
        e = OBJ["23558"]
        self.assertEqual(e["disagreements"][0]["claims"], [{"value": "1995-04-09", "sources": ["gcat-mcdowell"]},
                                                           {"value": "1986-02-19", "sources": ["space-track"]}])

    def test_name_swap_through_catalog_swaps(self):
        self.assertEqual(DOC["swaps"], [
            {"name": "sj-2", "claims": {"space-track": ["12842"], "gcat-mcdowell": ["12845"]}, "status": "open"},
            {"name": "sj-2b", "claims": {"gcat-mcdowell": ["12842"], "space-track": ["12845"]}, "status": "open"}])
        self.assertEqual(OBJ["12842"]["disagreements"], [])  # same designations: a name swap only

    def test_name_reused_on_another_launch_is_not_a_swap(self):
        a, b = dict(OBJ["40208"]), dict(OBJ["43874"])
        a["names"] = a["names"] + [catalog.rec("Early Bird", "gcat-mcdowell", "2026-11-15")]
        b["names"] = b["names"] + [catalog.rec("Early Bird", "space-track", ST_READ)]
        self.assertEqual(catalog.swaps({"40208": a, "43874": b}), [])

    def test_counts(self):
        c = DOC["counts"]
        self.assertEqual(c["disagreements_by_field"], {"intldes": 2, "launch_date": 3, "decayed": 1})
        self.assertEqual(c["space_track"]["satcat_rows"], 19)
        self.assertEqual(c["space_track"]["with_decay_messages"], 5)


class Placeholders(unittest.TestCase):
    """Rows changed on purpose (marked): Space-Track's FAQ describes analyst objects but none is in the cut."""

    def analyst_doc(self):
        row = dict(next(r for r in SATCAT if r["NORAD_CAT_ID"] == "40208"))
        row.update(INTLDES="2014-000B", OBJECT_ID="2014-000B", LAUNCH="2014-01-01", COUNTRY="UNKN")  # synthetic
        return build(satcat=[row])

    def test_analyst_object_values_are_placeholders_never_compared(self):
        doc = self.analyst_doc()
        e = doc["objects"]["40208"]
        self.assertEqual(e["disagreements"], [])
        self.assertTrue(st(e, "intldes")[0]["placeholder"])
        self.assertEqual(st(e, "launch_date")[0]["basis"], "catalog")
        self.assertTrue(st(e, "state")[0]["placeholder"])
        self.assertEqual(doc["counts"]["space_track"]["analyst_placeholders"], 1)

    def test_operator_code_is_not_compared_with_a_state(self):
        row = dict(next(r for r in SATCAT if r["NORAD_CAT_ID"] == "40208"), COUNTRY="ITSO")  # synthetic
        e = build(satcat=[row])["objects"]["40208"]
        self.assertTrue(st(e, "state")[0]["operator_code"])
        self.assertEqual(e["disagreements"], [])

    def test_greek_letter_pieces_are_not_compared(self):
        self.assertIsNone(stcat.comparable_intldes("1958 ALP 1"))
        self.assertEqual(stcat.comparable_intldes("2014-043A"), "2014-043A")


class Coverage(unittest.TestCase):
    def test_space_track_only_object_gets_its_own_entry(self):
        doc = build(extra=False)
        e = doc["objects"]["45565"]
        self.assertTrue(e["space_track_only"])
        self.assertIsNone(e["jcat"])
        self.assertEqual(e["type"], "payload")
        self.assertEqual(e["name"], "STARLINK-1357")
        self.assertEqual(doc["counts"]["space_track"]["space_track_only"], 6)

    def test_gcat_number_missing_from_satcat_is_counted(self):
        doc = build(satcat=[r for r in SATCAT if r["NORAD_CAT_ID"] != "40208"])
        self.assertEqual(doc["counts"]["space_track"]["gcat_not_in_satcat"], 1)
        self.assertEqual(st(doc["objects"]["40208"], "names"), [])

    def test_sources_carry_the_citation(self):
        self.assertIn("USSPACECOM", DOC["sources"]["space-track"]["citation"])
        self.assertEqual(DOC["rank"][0], "space-track")


if __name__ == "__main__":
    unittest.main()
