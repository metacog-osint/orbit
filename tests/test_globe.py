"""Offline checks for the globe (orbit-2.11): the vendored CesiumJS patch and the CSP it runs under.

Cesium.js bundles Knockout, which looks up the global object with (0,eval)("this") as it loads; under the site's
CSP (no 'unsafe-eval') that throws and Cesium never loads. Orbit patches that one expression to globalThis (see
site_src/vendor/cesium/PATCHED.md). A Cesium upgrade that drops the patch, or a CSP change that opens eval or
blob: scripts, fails here."""
from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CESIUM = ROOT / "site_src" / "vendor" / "cesium"


class CesiumPatch(unittest.TestCase):
    def test_patched_and_recorded(self):
        body = (CESIUM / "Cesium.js").read_bytes().replace(b"\r\n", b"\n")  # git on Windows checks out CRLF
        self.assertNotIn(b'(0,eval)("this")', body)
        self.assertEqual(body.count(b"var t=this||globalThis,n=t.document"), 1)
        note = (CESIUM / "PATCHED.md").read_text(encoding="utf-8")
        self.assertIn(hashlib.sha256(body).hexdigest(), note)  # the note names the patched file it describes

    def test_licences_present(self):
        self.assertTrue((CESIUM / "LICENSE.md").exists())
        self.assertTrue((ROOT / "site_src" / "vendor" / "satellite.js" / "LICENSE.md").exists())


class Csp(unittest.TestCase):
    def csp(self) -> dict[str, str]:
        text = (ROOT / "site_src" / "_headers").read_text(encoding="utf-8")
        line = re.search(r"Content-Security-Policy: (.+)", text).group(1)
        return {p.split()[0]: p for p in (x.strip() for x in line.split(";")) if p}

    def test_scripts_stay_strict(self):
        script = self.csp()["script-src"]
        self.assertNotIn("'unsafe-eval'", script)
        self.assertNotIn("'unsafe-inline'", script)
        self.assertNotIn("blob:", script)  # globe.js unsets CESIUM_WORKERS so workers load from Workers/ instead
        self.assertIn("'wasm-unsafe-eval'", script)

    def test_globe_hosts(self):
        c = self.csp()
        for host in ("https://api.cesium.com", "https://assets.ion.cesium.com", "https://*.virtualearth.net"):
            self.assertIn(host, c["connect-src"])
        self.assertNotIn("'unsafe-inline'", c["style-src"])

    def test_globe_unsets_blob_workers(self):
        self.assertIn("globalThis.CESIUM_WORKERS = undefined", (ROOT / "site_src" / "globe.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
