"""Object search opened from a link (site_src/search.js `?q=`): the query is read from the address, decoded and
capped, and a COSPAR launch id finds every piece of that launch. Run in Node with a bare page stub."""
import json
import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
NODE = shutil.which("node")

SCRIPT = r"""
globalThis.window = globalThis;
globalThis.location = { search: "" };
globalThis.document = { querySelectorAll: () => [], addEventListener: () => {} };
require(%s);
const S = window.OrbitSearch;
const out = {
  plain: S.queryOf("?q=2026-266"),
  spaced: S.queryOf("?x=1&q=Hornet+1"),
  encoded: S.queryOf("?q=Eutelsat%%2012%%20West"),
  none: S.queryOf("?track=re-123"),
  empty: S.queryOf(""),
  bad: S.queryOf("?q=%%E0%%A4%%A"),
  long: S.queryOf("?q=" + "a".repeat(200)).length,
};
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(NODE, "node not installed")
class SearchLink(unittest.TestCase):
    def test_query_from_the_address(self):
        src = json.dumps(str(ROOT / "site_src" / "search.js"))
        got = json.loads(subprocess.run([NODE, "-e", SCRIPT % src], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(got["plain"], "2026-266")
        self.assertEqual(got["spaced"], "Hornet 1")
        self.assertEqual(got["encoded"], "Eutelsat 12 West")
        self.assertEqual((got["none"], got["empty"], got["bad"]), ("", "", ""))
        self.assertEqual(got["long"], 80)

    def test_form_has_the_id_links_land_on(self):
        html = (ROOT / "site_src" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="obj-search"', html)


if __name__ == "__main__":
    unittest.main()
