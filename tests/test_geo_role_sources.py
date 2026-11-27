"""The GEO role list's sources (site_src/geo_roles.json): every entry rests on a source that was opened. A source the
list cites but could not open is marked [label, URL, "not opened"]; an entry with only such sources is refused by
check_roles (orbit/notable.py, also run by `orbit.py check`) and left off the page and the notable rule."""
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
SJ17 = 41838


def _tool(name, file):  # tools/ is not on the path: tools/orbit.py would shadow the orbit package
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def with_sources(norad, sources):
    d = copy.deepcopy(DOC)
    next(o for o in d["objects"] if o["id"] == norad)["sources"] = sources
    return d


UNOPENED = ["Aviation Week", "https://aviationweek.com/x", notable.NOT_OPENED]
OPENED = ["SpaceNews", "https://spacenews.com/x"]


class TestRoleSources(unittest.TestCase):
    def test_the_list_holds(self):
        self.assertEqual(notable.check_roles(DOC), [])

    def test_only_unopened_sources_is_refused(self):
        errs = notable.check_roles(with_sources(SJ17, [UNOPENED]))
        self.assertTrue(any("no opened source" in e and str(SJ17) in e for e in errs), errs)

    def test_an_unopened_source_beside_an_opened_one_holds(self):
        self.assertEqual(notable.check_roles(with_sources(SJ17, [OPENED, UNOPENED])), [])

    def test_a_bad_source_shape_fails(self):
        for bad in (["SpaceNews", "spacenews.com"], ["SpaceNews", "https://spacenews.com/x", "opened"], ["", "https://a.b"]):
            errs = notable.check_roles(with_sources(SJ17, [OPENED, bad]))
            self.assertTrue(any("is not [label, https URL]" in e for e in errs), (bad, errs))
        self.assertTrue(any("no source" in e for e in notable.check_roles(with_sources(SJ17, []))))

    def test_unopened_only_entry_is_not_marked_notable(self):
        idx = notable.roles_index(with_sources(SJ17, [UNOPENED]))
        self.assertNotIn(SJ17, idx)
        self.assertIn(SJ17, notable.roles_index(DOC))

    def test_page_drops_it_and_labels_unopened_sources(self):
        geo_page = _tool("geo_page_role_sources", "geo_page.py")
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "roles.json"
            p.write_text(json.dumps(with_sources(SJ17, [UNOPENED])), encoding="utf-8")
            self.assertNotIn(str(SJ17), geo_page.roles(str(p)))
            p.write_text(json.dumps(with_sources(SJ17, [OPENED, UNOPENED])), encoding="utf-8")
            self.assertEqual(geo_page.roles(str(p))[str(SJ17)]["sources"],
                             [OPENED, ["Aviation Week (not opened)", "https://aviationweek.com/x"]])

    def test_sj17_no_longer_cites_the_page_that_does_not_mention_it(self):
        """SpacePolicyOnline's 5 Feb 2022 article covers SJ-21 only; SJ-17's approaches are SWF's."""
        o = next(x for x in DOC["objects"] if x["id"] == SJ17)
        urls = [s[1] for s in o["sources"]]
        self.assertNotIn("https://spacepolicyonline.com/news/china-demonstrates-space-tug-in-geo-as-it-lays-out-five-year-plan/", urls)
        self.assertTrue(any("swfound.org" in u for u in urls))
        self.assertIn("Attributed by SWF", o["basis"])


if __name__ == "__main__":
    unittest.main()
