"""The GEO role list (site_src/geo_roles.json): every entry cites a source, says whether its role is declared or
attributed, and carries a status with its date (orbit/notable.py check_roles, also run by `orbit.py check`)."""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orbit import notable  # noqa: E402

DOC = json.loads((ROOT / "site_src" / "geo_roles.json").read_text(encoding="utf-8"))


def _tool(name, file):  # tools/ is not on the path: tools/orbit.py would shadow the orbit package
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def broken(i, **change):
    """A copy of the list with object i changed: a key set to None is removed."""
    d = copy.deepcopy(DOC)
    for k, v in change.items():
        if v is None:
            d["objects"][i].pop(k, None)
        else:
            d["objects"][i][k] = v
    return d


class TestRoleList(unittest.TestCase):
    def test_the_list_holds(self):
        self.assertEqual(notable.check_roles(DOC), [])
        self.assertEqual(len(DOC["objects"]), 20)

    def test_every_entry_has_source_status_and_date(self):
        for o in DOC["objects"]:
            self.assertTrue(o["sources"], o["id"])
            self.assertIn(o["status"], notable.ROLE_STATUSES, o["id"])
            self.assertRegex(o["status_date"], r"^\d{4}-\d{2}(-\d{2})?$", o["id"])
            self.assertIn(o["claim"], notable.ROLE_CLAIMS, o["id"])

    def test_a_missing_source_fails(self):
        self.assertTrue(any("no source" in e for e in notable.check_roles(broken(3, sources=None))))
        self.assertTrue(any("no source" in e for e in notable.check_roles(broken(3, sources=[]))))
        self.assertTrue(any("not [label, https URL]" in e
                            for e in notable.check_roles(broken(3, sources=[["SpaceNews", "spacenews.com"]]))))

    def test_a_missing_status_fails(self):
        self.assertTrue(any("status None" in e for e in notable.check_roles(broken(5, status=None))))
        self.assertTrue(any("status 'operating'" in e for e in notable.check_roles(broken(5, status="operating"))))
        self.assertTrue(any("no status_note" in e for e in notable.check_roles(broken(5, status_note=None))))

    def test_a_missing_or_bad_status_date_fails(self):
        self.assertTrue(any("status_date None" in e for e in notable.check_roles(broken(7, status_date=None))))
        self.assertTrue(any("is not YYYY-MM" in e for e in notable.check_roles(broken(7, status_date="Aug 2023"))))
        self.assertTrue(any("is after" in e for e in notable.check_roles(broken(7, status_date="2026-12"),
                                                                           today="2026-11-27")))

    def test_a_missing_claim_and_a_duplicate_fail(self):
        self.assertTrue(any("claim None" in e for e in notable.check_roles(broken(0, claim=None))))
        d = copy.deepcopy(DOC)
        d["objects"].append(copy.deepcopy(d["objects"][0]))
        self.assertTrue(any("listed twice" in e for e in notable.check_roles(d)))

    def test_usa_254_is_retired(self):
        """GSSAP 2: out of service 2 Aug 2023, passivated and in a graveyard orbit by 14 Aug 2023."""
        o = next(x for x in DOC["objects"] if x["id"] == 40100)
        self.assertEqual((o["status"], o["status_date"]), ("retired", "2023-08-14"))

    def test_page_data_carries_the_status(self):
        geo_page = _tool("geo_page_roles", "geo_page.py")
        r = geo_page.roles()["40100"]
        self.assertEqual((r["claim"], r["status"], r["status_date"]), ("declared", "retired", "2023-08-14"))
        self.assertTrue(r["status_note"] and r["sources"])


if __name__ == "__main__":
    unittest.main()
