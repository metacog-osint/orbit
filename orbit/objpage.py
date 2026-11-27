"""Data for Orbit's object pages (orbit-2.20, 18 Nov 2026).

The TIC satellite catalog (build step 6) publishes `catalog-shards.tar.gz` on the public release `catalog`: one file per
thousand numbered objects (`n<NORAD // 1000>.json`), one per thousand unnumbered GCAT entries (`j<letter><n // 1000>.json`),
the search index `search.json` and the rules note `rules.json`, all under `catalog/`. The update run downloads it once
(one GitHub request) and unpacks it into `site/data/catalog/`, so the page reads them from Orbit's own host.

Only regular files with those exact names are written; anything else in the archive is refused, so a bad or altered
archive cannot write outside the folder. A manifest (`index.json`) says what was unpacked and when, and the page says
when the catalog is missing or older than the rules note's `stale_after_hours`.
"""
from __future__ import annotations

import io
import json
import re
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ASSET = "catalog-shards.tar.gz"
SHARD_SCHEMA = "tic-catalog-shard/1"
SEARCH_SCHEMA = "tic-catalog-search/1"
RULES_SCHEMA = "tic-catalog-rules/1"
MANIFEST_SCHEMA = "orbit-object-data/1"
NAME = re.compile(r"^catalog/(n\d{1,4}|j[A-Z]\d{1,4}|search|rules)\.json$")
MAX_FILE = 25 * 1024 * 1024  # Cloudflare Pages refuses files over 25 MiB


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def shard_name(key: str | int) -> str:
    """The shard file for a key: NORAD number as written (25544 -> n25.json) or JCAT id (A04907 -> jA4.json)."""
    k = str(key).strip()
    if k.isdigit():
        return f"n{int(k) // 1000}.json"
    m = re.fullmatch(r"([A-Z])0*(\d+)", k)
    if not m:
        raise ValueError(f"not a NORAD number or JCAT id: {key!r}")
    return f"j{m.group(1)}{int(m.group(2)) // 1000}.json"


def unpack(blob: bytes, out_dir: Path, fetched: dict | None = None) -> dict:
    """Unpack the catalog's shard archive into out_dir/catalog/ and write its manifest. Returns the manifest.

    Raises ValueError (and writes nothing) when the archive holds an unexpected name, a non-file entry, a file over
    25 MiB, a schema other than the expected ones, or lacks search.json or rules.json."""
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for m in tar.getmembers():
            if m.isdir() and m.name.rstrip("/") == "catalog":
                continue
            if not m.isfile() or not NAME.match(m.name):
                raise ValueError(f"unexpected entry in {ASSET}: {m.name!r}")
            if m.size > MAX_FILE:
                raise ValueError(f"{m.name} is {m.size} bytes, over Cloudflare Pages' 25 MiB")
            files[m.name.split("/", 1)[1]] = tar.extractfile(m).read()
    for need in ("search.json", "rules.json"):
        if need not in files:
            raise ValueError(f"{ASSET} has no {need}")
    rules = json.loads(files["rules.json"])
    search = json.loads(files["search.json"])
    if rules.get("schema") != RULES_SCHEMA or search.get("schema") != SEARCH_SCHEMA:
        raise ValueError(f"schemas {rules.get('schema')!r} / {search.get('schema')!r}, "
                         f"not {RULES_SCHEMA} / {SEARCH_SCHEMA}")
    shards = sorted(n for n in files if n not in ("search.json", "rules.json"))
    for n in shards:
        if json.loads(files[n]).get("schema") != SHARD_SCHEMA:
            raise ValueError(f"{n} is not {SHARD_SCHEMA}")
    dest = Path(out_dir) / "catalog"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for n, body in files.items():
        (dest / n).write_bytes(body)
    manifest = {"schema": MANIFEST_SCHEMA, "unpacked_at": _now(), "asset": ASSET, "catalog_read": rules.get("read"),
                "catalog_schema": rules.get("catalog_schema"), "shards": len(shards),
                "objects": len(search.get("objects") or []), "bytes": sum(len(b) for b in files.values()),
                "stale_after_hours": rules.get("stale_after_hours"), "fetched": fetched}
    (dest / "index.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    return manifest
