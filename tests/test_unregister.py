"""Names registered with the United Nations (orbit/unregister.py, method orbit-2.50). Offline. The replies here are
written by hand in the Online Index's shape, with only the fields Orbit reads; no register reply is stored."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from orbit import unregister as un

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
DOC = "/osoindex/data/documents/fr/st/stsgser.e563.html"


def values(**over):
    v = {"object.internationalDesignator_s1": "2008-065A",
         "object.internationalDesignator@official_s1": "true",
         "object.nameOfSpaceObjectO_s1": "HOT BIRD 9",
         "object.nameOfSpaceObjectIno_s1": "",
         "object.launch.stateOfRegistry_s1": "France (for Eutelsat)",
         "object.launch.stateOfRegistry@official_s1": "true",
         "object.status.gsoLocation_s1": "+009 degrees East",
         "object.status.gsoLocation@official_s1": "true",
         "en#object.unRegistration.unRegistered_s1": "Yes",
         "object.unRegistration.registrationDocuments.document@uri_s": [DOC],
         "object.unRegistration.registrationDocuments.document..document.symbol_s": ["ST/SG/SER.E/563"],
         "object.remark_s1": "------"}
    v.update(over)
    return v


def reply(*rows):
    return json.dumps({"found": len(rows), "results": [{"values": r} for r in rows]}).encode("utf-8")


def entry(**over):
    e = {"line": 1, "cospar": "2008-065A", "name": "HOT BIRD 9", "state": "France (for Eutelsat)",
         "symbol": "ST/SG/SER.E/563", "link": un.SITE + DOC, "read": "2026-11-27", "proposed_by": "tic",
         "proposed": "2026-11-27", "reviewed_by": "tic-analyst", "reviewed": "2026-11-27"}
    e.update(over)
    return {k: v for k, v in e.items() if v is not None}


class Record(unittest.TestCase):
    def test_registered_name_document_and_gso(self):
        r = un.record(values())
        self.assertEqual((r["name"], r["symbol"], r["gso"]), ("HOT BIRD 9", "ST/SG/SER.E/563", "+009 degrees East"))
        self.assertEqual(r["link"], "https://www.unoosa.org/unoosa" + DOC)
        self.assertIsNone(r["remark"])

    def test_name_stays_declared_when_only_the_designator_is_unofficial(self):
        r = un.record(values(**{"object.internationalDesignator@official_s1": "false"}))
        self.assertEqual(r["name"], "HOT BIRD 9")

    def test_other_name_field_is_never_declared(self):
        r = un.record(values(**{"object.nameOfSpaceObjectO_s1": "",
                                "object.nameOfSpaceObjectIno_s1": "[EXAMPLE 1]"}))
        self.assertIsNone(r["name"])
        self.assertEqual(r["other_name"], "[EXAMPLE 1]")

    def test_bracketed_unregistered_or_undocumented_name_is_not_declared(self):
        for over in ({"object.nameOfSpaceObjectO_s1": "[EXAMPLE 1]"},
                     {"en#object.unRegistration.unRegistered_s1": "No"},
                     {"object.unRegistration.registrationDocuments.document..document.symbol_s": []}):
            with self.subTest(over=over):
                self.assertIsNone(un.record(values(**over))["name"])

    def test_unofficial_gso_location_is_left_out(self):
        self.assertIsNone(un.record(values(**{"object.status.gsoLocation@official_s1": "false"}))["gso"])


class Lookup(unittest.TestCase):
    def test_one_request_per_id_then_the_cache(self):
        asked = []

        def get(url):
            asked.append(url)
            return reply(values())

        with tempfile.TemporaryDirectory() as d:
            first = un.lookup(["2008-065a", "2008-065A"], Path(d), getter=get, now=NOW)
            again = un.lookup(["2008-065A"], Path(d), getter=get, now=NOW + timedelta(days=6))
            self.assertEqual(len(asked), 1)
            self.assertIn("2008-065A", asked[0])
            self.assertEqual((first[0]["cached"], again[0]["cached"]), (False, True))
            un.lookup(["2008-065A"], Path(d), getter=get, now=NOW + timedelta(days=8))
            self.assertEqual(len(asked), 2)

    def test_too_many_ids_or_a_bad_id_asks_nothing(self):
        def boom(url):
            raise AssertionError("asked")

        for ids in ([f"2008-{n:03d}A" for n in range(1, 12)], ["HOT BIRD 9"]):
            with self.assertRaises(un.RegisterError):
                un.lookup(ids, None, getter=boom, now=NOW)

    def test_wrong_shape_is_an_error_and_not_cached(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(un.RegisterError):
                un.lookup(["2008-065A"], Path(d), getter=lambda u: b'{"error": "x"}', now=NOW)
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_another_objects_record_is_not_taken(self):
        got = un.lookup(["2014-058A"], None, getter=lambda u: reply(values()), now=NOW)
        self.assertEqual(got[0]["records"], [])


class Entries(unittest.TestCase):
    def test_only_reviewed_entries_are_published(self):
        rows = un.validate_entries([entry(), entry(line=2, cospar="2014-058A", reviewed=None, reviewed_by=None)])
        doc = un.public_names(rows, "2026-11-27T12:00:00Z")
        self.assertEqual(list(doc["objects"]), ["2008-065A"])
        self.assertEqual(doc["objects"]["2008-065A"][0]["symbol"], "ST/SG/SER.E/563")
        self.assertNotIn("proposed_by", doc["objects"]["2008-065A"][0])

    def test_bad_entries_stop(self):
        for bad in (entry(name="[EXAMPLE 1]"), entry(link="https://example.org/x"), entry(cospar="65A"),
                    entry(reviewed=None), entry(symbol=None), entry(withdrawn="2026-11-28")):
            with self.subTest(bad=bad):
                with self.assertRaises(un.EntryError):
                    un.validate_entries([bad])

    def test_repo_file_loads(self):
        un.load_entries()

    def test_page_and_build_use_the_reviewed_file(self):
        js = (ROOT / "site_src" / "object.js").read_text(encoding="utf-8")
        self.assertIn('getJson("data/un-register.json")', js)
        self.assertIn("to the UN Register", js)
        self.assertIn('files["data/un-register.json"]', (ROOT / "tools" / "orbit.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
