"""TIC satellite catalog, build step 6: a smaller catalog file, shards for Orbit's object page, a search index and a
rules note for the page's "Names and sources" section.

Design: [local path] (build order step 6); the page: [local path]
orbit-object-page-2026-11-18.md. Split agreed 18 Nov 2026: the catalog supplies the data and the rules, Orbit's page
draws them; no page code here.

- **Compact records (schema tic-catalog/2).** Every value is still a record {value, source, ref, read, basis}; a
  record leaves out `read` when it equals its source's read date in `sources`, `ref` when it is the object's own
  key in that source (GCAT: the JCAT id; Space-Track and CelesTrak: the NORAD number), and `basis` when it is
  `attributed`. `expand_entry` puts all three back exactly. Nothing else changes: the 18 Nov 2026 file was 210 MB of JSON, most of it `read` and `ref` repeated.
- **Shards.** Numbered objects by NORAD number // 1000 (`n25` holds 25000-25999); objects with no NORAD number by
  JCAT letter and number // 1000 (`jA4` holds A04000-A04999). Each shard carries the sources block, so a page that
  loads one shard can expand and credit every record, and the name swaps that touch its objects.
- **Search index.** Every object: key, display name, other names, COSPAR ID, type and whether it has left orbit.
- **Rules note.** What each source, field, basis and flag means, in the words the page shows.
"""
from __future__ import annotations

import gzip
import io
import json
import tarfile

from . import aliases, catalog

SCHEMA = "tic-catalog/2"
SHARD_SCHEMA = "tic-catalog-shard/1"
SEARCH_SCHEMA = "tic-catalog-search/1"
RULES_SCHEMA = "tic-catalog-rules/1"

SHARDS_ASSET = "catalog-shards.tar.gz"
SEARCH_ASSET = "catalog-search.json.gz"
RULES_ASSET = "catalog-rules.json"
SHARD_DIR = "catalog"  # inside the tar: catalog/n25.json, catalog/jA4.json, catalog/search.json, catalog/rules.json

# Fields holding lists of value records ({value, source, ref, read, basis}).
RECORD_FIELDS = catalog.FIELDS + ("program",)

# The source whose own key for an object is the default `ref` of its records.
REF_BY_SOURCE = {catalog.GCAT: "jcat", catalog.ST: "norad", catalog.CT: "norad"}

RECORD_DEFAULTS = {
    "read": "Left out when it equals the source's read date in `sources`.",
    "basis": "Left out when it is `attributed`.",
    "ref": "Left out when it is the object's own key in that source: GCAT's JCAT id (`jcat`) for gcat-mcdowell, the "
           "NORAD number for space-track and celestrak-satcat. Wikidata's Q-id and the alias file's line are always "
           "given.",
}


DEFAULT_BASIS = "attributed"


def default_ref(source: str, e: dict) -> str | None:
    field = REF_BY_SOURCE.get(source)
    if field is None or e.get(field) is None:
        return None
    return str(e[field])


def _reads(sources: dict) -> dict:
    return {s: v.get("read") for s, v in sources.items()}


def compact_entry(e: dict, reads: dict) -> dict:
    """An entry with `read`, `ref` and `basis` left out wherever they are the default (RECORD_DEFAULTS)."""
    out = {}
    for k, v in e.items():
        if k in RECORD_FIELDS and isinstance(v, list):
            recs = []
            for r in v:
                r = dict(r)
                if r.get("read") is not None and r["read"] == reads.get(r["source"]):
                    del r["read"]
                if "ref" in r and r["ref"] is not None and r["ref"] == default_ref(r["source"], e):
                    del r["ref"]
                if r.get("basis") == DEFAULT_BASIS:
                    del r["basis"]
                recs.append(r)
            out[k] = recs
        elif k == "also_in_gcat":
            out[k] = [compact_entry(x, reads) for x in v]
        else:
            out[k] = v
    return out


def expand_entry(e: dict, reads: dict) -> dict:
    """The inverse of compact_entry: every record with its `read`, `ref` and `basis`, keys in the build's order."""
    out = {}
    for k, v in e.items():
        if k in RECORD_FIELDS and isinstance(v, list):
            recs = []
            for r in v:
                full = {"value": r["value"], "source": r["source"],
                        "ref": r["ref"] if "ref" in r else default_ref(r["source"], e),
                        "read": r["read"] if "read" in r else reads.get(r["source"]),
                        "basis": r.get("basis", DEFAULT_BASIS)}
                full.update({x: y for x, y in r.items() if x not in full})
                recs.append(full)
            out[k] = recs
        elif k == "also_in_gcat":
            out[k] = [expand_entry(x, reads) for x in v]
        else:
            out[k] = v
    return out


def compact(doc: dict) -> dict:
    """The built catalog (catalog.build) in schema tic-catalog/2: the same entries with default `read`, `ref` and
    `basis` left out."""
    reads = _reads(doc["sources"])
    out = {k: v for k, v in doc.items() if k not in ("objects", "unnumbered")}
    out["schema"] = SCHEMA
    out["record_defaults"] = RECORD_DEFAULTS
    out["objects"] = {k: compact_entry(e, reads) for k, e in doc["objects"].items()}
    out["unnumbered"] = {k: compact_entry(e, reads) for k, e in doc["unnumbered"].items()}
    return out


def shard_of(key: str) -> str:
    """`n<NORAD // 1000>` for a numbered object, `j<JCAT letter><JCAT number // 1000>` for one with no NORAD
    number ('25544' -> 'n25', 'A04907' -> 'jA4', 'S100129' -> 'jS100')."""
    if key.isdigit():
        return f"n{int(key) // 1000}"
    return f"j{key[0]}{int(key[1:]) // 1000}"


def shards(cdoc: dict) -> dict[str, dict]:
    """The compact catalog cut into shards {shard id: shard doc}."""
    groups: dict[str, dict] = {}
    where: dict[str, str] = {}
    for group in ("objects", "unnumbered"):
        for key, e in cdoc[group].items():
            sid = shard_of(key)
            groups.setdefault(sid, {})[key] = e
            where[key] = sid
    touching: dict[str, list] = {}
    for sw in cdoc.get("swaps") or []:
        for sid in sorted({where[k] for ks in sw["claims"].values() for k in ks if k in where}):
            touching.setdefault(sid, []).append(sw)
    head = {"catalog_schema": cdoc["schema"], "read": cdoc["read"], "sources": cdoc["sources"],
            "rank": cdoc["rank"], "record_defaults": cdoc["record_defaults"]}
    return {sid: {"schema": SHARD_SCHEMA, "shard": sid, **head, "objects": objs, "swaps": touching.get(sid, [])}
            for sid, objs in sorted(groups.items())}


TYPE_CODES = {"payload": "p", "rocket stage": "r", "debris": "d", "component": "c", "other": "o"}


def _gone(e: dict) -> int:
    return 1 if catalog._first(e, "decayed") else 0


def search_index(doc: dict) -> dict:
    """Every object, numbered or not, as [key, display name, other names, COSPAR ID, type, gone]. Other names:
    every source's names not equal (ignoring case) to the display name, best-ranked source first. COSPAR ID: the
    best-ranked one. Type: TYPE_CODES. Gone: 1 when the best-ranked source says the object has left orbit."""
    rows = []
    for group in ("objects", "unnumbered"):
        for key, e in doc[group].items():
            shown = e.get("name") or ""
            seen, others = {shown.lower()}, []
            for n in sorted(e.get("names") or [], key=lambda r: catalog._rank(r["source"])):
                if n["value"].lower() not in seen:
                    seen.add(n["value"].lower())
                    others.append(n["value"])
            rows.append([key, shown, others, catalog._first(e, "intldes") or "", TYPE_CODES.get(e["type"], "o"),
                         _gone(e)])
    return {"schema": SEARCH_SCHEMA, "read": doc["read"], "catalog_schema": SCHEMA,
            "columns": ["key", "name", "other_names", "cospar", "type", "gone"],
            "types": {v: k for k, v in TYPE_CODES.items()}, "shard_rule": SHARD_RULE, "objects": rows}


SHARD_RULE = ("A numbered object is in n<NORAD number // 1000>.json (25544 in n25.json); an object with no NORAD "
              "number is in j<first letter of its JCAT id><rest of the id as a number // 1000>.json (A04907 in "
              "jA4.json). Keys: the NORAD number as written without leading zeros, or the JCAT id.")

# The rules note. Wording is the page's: precise, with terms explained in place (mixed readers, Tom 18 Nov 2026).
SOURCE_LABELS = {
    catalog.ST: {"label": "Space-Track", "about": "The US Space Force's public catalog (18th Space Defense "
                 "Squadron). It assigns NORAD numbers and COSPAR IDs.", "url": "https://www.space-track.org"},
    catalog.GCAT: {"label": "GCAT", "about": "Jonathan McDowell's General Catalog of Artificial Space Objects, "
                   "compiled from many sources.", "url": "https://planet4589.org/space/gcat/"},
    catalog.CT: {"label": "CelesTrak SATCAT", "about": "T.S. Kelso's catalog, drawn from the same US data as "
                 "Space-Track, with names and status codes of its own.", "url": "https://celestrak.org/satcat/"},
    catalog.WD: {"label": "Wikidata", "about": "The open knowledge base; an item names the object and carries its "
                 "NORAD number. Each value links to its item.", "url": "https://www.wikidata.org"},
    "swf-rpo": {"label": "Secure World Foundation", "about": "SWF's public sheet of rendezvous and proximity "
                "operations.", "url": None},
    aliases.SOURCE: {"label": "TIC alias file", "about": "Names TIC added by hand, one claim per entry, each with "
                     "its evidence and the source it cites.",
                     "url": "https://github.com/metacog-osint/orbit/blob/main/orbit/data/catalog/aliases.yml"},
}

BASIS = {
    "declared": {"label": "declared", "means": "The operator, the launching state or a UN registration states it.",
                 "phrase": "named {value} by {source}"},
    "attributed": {"label": "attributed", "means": "A catalog compiler or analyst gives it; the operator has not "
                   "been shown to state it.", "phrase": "identified as {value} by {source}"},
    "catalog": {"label": "catalog designation", "means": "A catalog's own designation or placeholder, such as USA "
                "257 or OBJECT A, not a name the owner chose.", "phrase": "catalogued as {value} by {source}"},
}

NAME_FIELDS = {
    "Name": "GCAT's name for the object.",
    "PLName": "GCAT's payload name: often the maker's or programme's name for the spacecraft.",
    "AltNames": "GCAT's other names. A code after a colon (such as :JP or :RA) is GCAT's own and is kept as written.",
    "SATNAME": "Space-Track's name.",
    "OBJECT_NAME": "CelesTrak's name; CelesTrak puts another name in brackets, as in USA 257 (CLIO).",
    "label:en": "Wikidata's English label.",
    "label:mul": "Wikidata's label for all languages.",
    "altLabel:en": "Wikidata's English alias.",
}

FIELD_NOTES = {
    "name": "The display name. The best-ranked source's name (Space-Track, then GCAT, CelesTrak, Wikidata, SWF, the "
            "alias file); when that is a catalog designation such as USA 257, the best-ranked other name follows in "
            "brackets: USA 257 (CLIO). Names are text to read and search; they never link or move a number.",
    "names": "Every name every source gives, none dropped.",
    "intldes": "COSPAR ID (international designator): launch year, launch number in that year, and a letter for "
               "each piece, as 1998-067A.",
    "launch_tag": "GCAT's launch identifier, the key Launch and Orbit share for a launch.",
    "launch_date": "Launch date as each source gives it.",
    "owner": "GCAT's owner or operator code, with its name from GCAT's organisation list. A trailing ? is GCAT's "
             "own doubt.",
    "state": "The state each source gives. Space-Track and CelesTrak use country codes, GCAT its own; they are "
             "compared through a table. Some Space-Track and CelesTrak codes are operators or programmes (SES, "
             "ISS), kept and not compared.",
    "status": "GCAT's orbital status code (in orbit, reentered, docked, attached, deep space and others).",
    "ops_status": "CelesTrak's operational status code: + operational, - nonoperational, P partially operational, "
                  "B backup or standby, S spare, X extended mission, D decayed or deorbited, ? unknown "
                  "(celestrak.org/satcat/status.php, read 17 Nov 2026).",
    "decayed": "Whether each source says the object has left orbit.",
    "decay_date": "Reentry or decay date as each source gives it; Space-Track's come from its SATCAT and its "
                  "Historical decay messages.",
    "orbit": "Each source's orbit as it states it, never merged. Perigee and apogee are the lowest and highest "
             "points above the Earth's surface (km); inclination is the tilt of the orbit to the equator (degrees). "
             "GCAT's comes with the date of the elements it is from, which can be years old (GCAT's orbit for the "
             "ISS's first module is dated 20 Dec 1998), and its orbit class (OpOrbit). CelesTrak's adds the period "
             "(minutes) and its orbit centre and type codes; it gives no date, so its file's time dates it.",
    "program": "A programme the object belongs to, from the alias file (for example GSSAP).",
}

FLAGS = {
    "uncertain": "The source marks the value with a question mark: its own doubt, kept as written.",
    "qualifier": "A code the source attaches to the name, kept as written and not decoded.",
    "placeholder": "A placeholder the source uses until it has a value (an analyst object's date, TBD, UNKN).",
    "operator_code": "An operator's code where a state is expected: kept, not compared.",
    "nocompare": "Kept and shown, but not compared with other sources.",
    "cited": "For alias-file names: the source the entry cites.",
}

DISAGREEMENTS = {
    "about": "Sources differ: the values each source gives for a field, side by side. TIC lists them and never picks "
             "one.",
    "fields": {
        "intldes": "Sources give different COSPAR IDs: often two pieces of one launch swapped between catalogs.",
        "launch_date": "Sources give different launch dates. For objects released from the ISS, Space-Track gives "
                       "the station's launch date and GCAT the release date.",
        "state": "Sources give different states, often for multinational owners or companies that moved.",
        "decayed": "One source says the object has left orbit and another does not. Often GCAT holds it as docked, "
                   "attached or in deep space while Space-Track gives a decay date.",
        "ops_status": "Two sources give different operational status.",
        "gcat_catalog": "GCAT lists the number twice.",
    },
}

# Shown once on every satellite card, above "Names and sources" (Tom, 18 Nov 2026: a general note, no reviewer named).
CARD_NOTE = ("Names, owners, dates, orbits and status on this card come from several public catalogs and are shown as "
             "each source gives them. The sources sometimes disagree, and some details are attributed to the satellite "
             "by a catalog compiler or analyst rather than stated by its operator. Where they differ, TIC lists each "
             "source's value instead of choosing one. If something looks wrong, ask us.")

SWAPS = ("Name swap: two sources give one payload name to different numbers from the same launch. Both claims show "
         "on both objects and nothing is reassigned; the numbers stay as each source gives them.")


def rules(doc: dict) -> dict:
    """The rules note for the page's "Names and sources" section, with the sources as this build read them."""
    srcs = {}
    for s, v in doc["sources"].items():
        srcs[s] = {**SOURCE_LABELS.get(s, {"label": s, "about": None, "url": None}),
                   **{k: v.get(k) for k in ("read", "read_at", "updated", "file_time", "citation") if v.get(k)}}
    for s in doc["rank"]:
        srcs.setdefault(s, {**SOURCE_LABELS.get(s, {"label": s, "about": None, "url": None}), "read": None})
    return {"schema": RULES_SCHEMA, "catalog_schema": SCHEMA, "read": doc["read"], "rank": doc["rank"],
            "sources": srcs, "basis": BASIS, "name_fields": NAME_FIELDS, "fields": FIELD_NOTES, "flags": FLAGS,
            "card_note": CARD_NOTE, "disagreements": DISAGREEMENTS, "swaps": SWAPS, "record_defaults": RECORD_DEFAULTS,
            "shard_rule": SHARD_RULE,
            "stale_after_hours": 36}


def _json(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def bundle(doc: dict, cdoc: dict | None = None) -> dict[str, bytes]:
    """{asset name: bytes} for the release: the shards, search index and rules note in one tar (Orbit's update run
    unpacks it into site/data/; one download), plus the search index and the rules note on their own. `doc` is the
    built catalog (full records), `cdoc` its compact form if already made."""
    cdoc = cdoc or compact(doc)
    idx = _json(search_index(doc))
    note = json.dumps(rules(doc), ensure_ascii=False, indent=1).encode("utf-8")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:  # gzipped below with mtime 0: the same bytes for the same catalog
        def add(name: str, body: bytes):
            ti = tarfile.TarInfo(f"{SHARD_DIR}/{name}")
            ti.size, ti.mtime, ti.mode = len(body), 0, 0o644
            tar.addfile(ti, io.BytesIO(body))
        for sid, sd in shards(cdoc).items():
            add(f"{sid}.json", _json(sd))
        add("search.json", idx)
        add("rules.json", note)
    return {SHARDS_ASSET: gzip.compress(buf.getvalue(), 9, mtime=0), SEARCH_ASSET: gzip.compress(idx, 9, mtime=0),
            RULES_ASSET: note}


def read_shards(body: bytes) -> dict[str, dict]:
    """The tar back into {file name: doc} (tests and readers in Python)."""
    out = {}
    with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as tar:
        for m in tar.getmembers():
            if m.isfile() and m.name.startswith(SHARD_DIR + "/") and m.name.endswith(".json"):
                out[m.name[len(SHARD_DIR) + 1:]] = json.loads(tar.extractfile(m).read())
    return out
