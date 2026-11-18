"""Object pages (orbit-2.20): the catalog's shard archive unpacked into site/data/catalog/, and object keys in the lead.

Offline: archives are built here in the shape catalog build step 6 publishes (`catalog/n25.json`, `catalog/jA4.json`,
`search.json`, `rules.json`), with records cut from the real 18 Nov 2026 shards (ISS 25544, Prowler A04907)."""
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from orbit import lead, objpage  # noqa: E402
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("orbit_cli_objpage", ROOT / "tools" / "orbit.py")
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)

ISS = {"norad": 25544, "jcat": "S25544", "type": "payload", "name": "ISS (ZARYA)",
       "names": [{"value": "ISS (ZARYA)", "source": "space-track", "field": "SATNAME"},
                 {"value": "Zarya", "source": "gcat-mcdowell", "field": "Name"}],
       "orbit": [{"value": {"perigee_km": 413.0, "apogee_km": 423.0, "inc_deg": 51.63, "period_min": 92.94,
                            "orbit_center": "EA", "orbit_type": "ORB"}, "source": "celestrak-satcat"}],
       "disagreements": [{"field": "state", "claims": [{"value": "US", "sources": ["gcat-mcdowell"]},
                                                       {"value": "SU", "sources": ["space-track"], "as_given": ["CIS"]}]}]}
PROWLER = {"norad": None, "jcat": "A04907", "type": "payload", "name": "PROWLER", "no_norad": True,
           "names": [{"value": "PROWLER", "source": "gcat-mcdowell", "field": "Name"}]}


def shard(name, objects):
    return {"schema": objpage.SHARD_SCHEMA, "shard": name, "catalog_schema": "tic-catalog/2", "read": "2026-11-18",
            "sources": {"gcat-mcdowell": {"read": "2026-11-18"}}, "rank": ["space-track", "gcat-mcdowell"],
            "record_defaults": {}, "objects": objects, "swaps": []}


def archive(files: dict, extra: list | None = None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        d = tarfile.TarInfo("catalog")
        d.type = tarfile.DIRTYPE
        tar.addfile(d)
        for name, doc in files.items():
            body = json.dumps(doc).encode()
            ti = tarfile.TarInfo(name)
            ti.size = len(body)
            tar.addfile(ti, io.BytesIO(body))
        for ti, body in extra or []:
            tar.addfile(ti, io.BytesIO(body) if body is not None else None)
    return buf.getvalue()


def good() -> dict:
    return {"catalog/n25.json": shard("n25", {"25544": ISS}), "catalog/jA4.json": shard("jA4", {"A04907": PROWLER}),
            "catalog/search.json": {"schema": objpage.SEARCH_SCHEMA, "columns": ["key", "name", "other_names", "cospar", "type", "gone"],
                                    "objects": [["25544", "ISS (ZARYA)", ["Zarya"], "1998-067A", "p", 0],
                                                ["A04907", "PROWLER", [], "1990-097E", "p", 0]]},
            "catalog/rules.json": {"schema": objpage.RULES_SCHEMA, "catalog_schema": "tic-catalog/2", "read": "2026-11-18",
                                   "stale_after_hours": 36}}


class ShardName(unittest.TestCase):
    def test_rule_from_the_rules_note(self):
        self.assertEqual(objpage.shard_name(25544), "n25.json")
        self.assertEqual(objpage.shard_name("101401"), "n101.json")
        self.assertEqual(objpage.shard_name("5"), "n0.json")
        self.assertEqual(objpage.shard_name("A04907"), "jA4.json")
        self.assertEqual(objpage.shard_name("A12000"), "jA12.json")
        with self.assertRaises(ValueError):
            objpage.shard_name("../x")


class Unpack(unittest.TestCase):
    def test_unpacks_and_writes_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "catalog").mkdir()
            (out / "catalog" / "n999.json").write_text("{}")  # a shard from an older archive is cleared
            man = objpage.unpack(archive(good()), out, fetched={"sha256": "x"})
            self.assertEqual(man["shards"], 2)
            self.assertEqual(man["objects"], 2)
            self.assertEqual(man["catalog_read"], "2026-11-18")
            names = sorted(p.name for p in (out / "catalog").iterdir())
            self.assertEqual(names, ["index.json", "jA4.json", "n25.json", "rules.json", "search.json"])
            doc = json.loads((out / "catalog" / "n25.json").read_text())
            self.assertEqual(doc["objects"]["25544"]["name"], "ISS (ZARYA)")

    def test_refuses_paths_outside_the_folder(self):
        for bad in ("catalog/../../evil.json", "/etc/passwd", "catalog/n25.json.bak", "catalog/sub/n1.json", "other/n1.json"):
            files = good()
            files[bad] = {"schema": objpage.SHARD_SCHEMA}
            with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError, msg=bad):
                objpage.unpack(archive(files), Path(tmp))
                self.assertFalse((Path(tmp) / "catalog").exists())

    def test_refuses_links_and_wrong_schemas(self):
        link = tarfile.TarInfo("catalog/n1.json")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            objpage.unpack(archive(good(), [(link, None)]), Path(tmp))
        files = good()
        files["catalog/n25.json"]["schema"] = "tic-catalog-shard/9"
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            objpage.unpack(archive(files), Path(tmp))
        files = good()
        del files["catalog/search.json"]
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            objpage.unpack(archive(files), Path(tmp))

    def test_a_refused_archive_leaves_the_old_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            objpage.unpack(archive(good()), out)
            files = good()
            files["catalog/evil.sh"] = {}
            with self.assertRaises(ValueError):
                objpage.unpack(archive(files), out)
            self.assertTrue((out / "catalog" / "n25.json").exists())


class Command(unittest.TestCase):
    def test_object_data_never_stops_the_deploy(self):
        def fail(url, timeout):
            raise OSError("404")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cli.object_data(Path(tmp), getter=fail), 0)
            self.assertFalse((Path(tmp) / "data" / "catalog").exists())
            blob = archive(good())
            seen = []
            self.assertEqual(cli.object_data(Path(tmp), getter=lambda url, t: seen.append(url) or blob), 0)
            self.assertEqual(seen, [cli.SHARDS_URL])
            self.assertTrue(cli.SHARDS_URL.endswith("/releases/download/catalog/catalog-shards.tar.gz"))
            self.assertTrue((Path(tmp) / "data" / "catalog" / "jA4.json").exists())


class LeadKeys(unittest.TestCase):
    def test_object_names_carry_their_key(self):
        self.assertEqual(lead._obj("Starlink 4334", 59000), {"s": "Starlink 4334", "o": "59000"})
        self.assertEqual(lead._obj("deb", "001234"), {"s": "deb", "o": "1234"})
        self.assertEqual(lead._obj("PROWLER", None, "A04907"), {"s": "PROWLER", "o": "A04907"})
        self.assertEqual(lead._obj("Unknown"), "Unknown")


if __name__ == "__main__":
    unittest.main()
