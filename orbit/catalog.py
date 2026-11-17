"""TIC's satellite catalog (schema `tic-catalog/1`): one entry per NORAD number, every value with its source.

Design: [local path] (Tom's answers in its section 9). Build step 2: GCAT only.
Later steps add Space-Track SATCAT and DECAY, CelesTrak SATCAT, Wikidata, WMO OSCAR/Space and the hand-kept alias
file; each arrives as more value records on the same entries, ranked by `RANK`.

Rules kept here:
- Entries key on the NORAD number. Names are display text and never join anything.
- Every value is a record {value, source, ref, read, basis}; `basis` is `declared` (operator, launching state or UN
  registration), `attributed` (a catalog compiler or analyst), or `catalog` (a designation such as "USA 257" or a
  placeholder such as "OBJECT A"). From GCAT alone nothing is `declared`: GCAT does not say who chose a name.
- No source's name is dropped: `names` holds every name from every source.
- Values that differ between sources are listed in `disagreements`; a disagreement never changes a value.
"""
from __future__ import annotations

import re

from . import gcat

SCHEMA = "tic-catalog/1"

# Name ranking (Tom, 16 Nov 2026): Space-Track, GCAT, CelesTrak, Wikidata, SWF, then cited aliases.
RANK = ("space-track", "gcat-mcdowell", "celestrak-satcat", "wikidata", "swf-rpo", "aliases")

# Designations and placeholders: shown, but a better name goes beside them in brackets (Tom, 16 Nov 2026).
DESIGNATION = re.compile(r"^(USA[ -]?\d+|OBJECT [A-Z]{1,3}|TBA.*|UNKNOWN)$", re.I)

# Fields compared between sources for `disagreements` (names are listed, not flagged: they differ by design).
FLAGGED = ("intldes", "launch_date", "state", "decayed")

GCAT = "gcat-mcdowell"


def rec(value, source: str, read: str, basis: str = "attributed", ref: str | None = None, **extra) -> dict:
    out = {"value": value, "source": source, "ref": ref, "read": read, "basis": basis}
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def name_basis(name: str) -> str:
    return "catalog" if DESIGNATION.match(name.strip()) else "attributed"


def alt_names(cell: str) -> list[tuple[str, str | None]]:
    """GCAT's AltNames cell to (name, qualifier) pairs. Names are comma-separated; a suffix such as ':JP', ':P' or
    ':RA' is kept as the qualifier as written (GCAT's own code; its meaning is not decoded here). A bare ':U' with no
    name before it is a qualifier with no name and is skipped. '-' means none."""
    out = []
    for part in (cell or "").split(","):
        part = part.strip()
        if not part or part == "-":
            continue
        name, qual = part, None
        m = re.match(r"^(.*?):([A-Z]{1,3})$", part)
        if m:
            name, qual = m.group(1).strip(), m.group(2)
        if name:
            out.append((name, qual))
    return out


def _gcat_names(r: dict, read: str, jcat: str) -> list[dict]:
    out, seen = [], set()

    def add(name: str, field: str, qual: str | None = None):
        name = (name or "").strip()
        if not name or name == "-" or (name.lower(), qual) in seen:
            return
        seen.add((name.lower(), qual))
        out.append(rec(name, GCAT, read, name_basis(name), ref=jcat, field=field, qualifier=qual,
                       uncertain=True if name.endswith("?") else None))  # GCAT's own '?', kept as written

    add(r.get("Name", ""), "Name")
    add(r.get("PLName", ""), "PLName")
    for name, qual in alt_names(r.get("AltNames", "")):
        add(name, "AltNames", qual)
    return out


def _owner(code: str, orgs: dict, read: str, jcat: str) -> list[dict]:
    """GCAT owner codes, '/'-separated ('ZZB/CAST'); a trailing '?' is GCAT's own doubt and is kept."""
    out = []
    for part in [p for p in (code or "").split("/") if p and p != "-"]:
        bare = part.rstrip("?")
        org = orgs.get(bare) or {}
        out.append(rec(part, GCAT, read, "attributed", ref=jcat, name=org.get("name"),
                       uncertain=True if part.endswith("?") else None))
    return out


def from_gcat(tables: dict[str, list[dict]], orgs: dict, read: str) -> tuple[dict, dict]:
    """GCAT's four catalogs to (entries by NORAD number, entries with no number by JCAT)."""
    numbered, unnumbered = {}, {}
    for cat in gcat.CATALOGS:
        for r in tables.get(cat) or []:
            jcat = (r.get("JCAT") or "").strip()
            if not jcat:
                continue
            norad = gcat._num(r.get("Satcat", ""))
            ldate = gcat.vague_date(r.get("LDate", ""))["date"]
            ddate = gcat.vague_date(r.get("DDate", ""))["date"]
            status = r.get("Status", "")
            e = {
                "norad": int(norad) if norad else None,
                "jcat": jcat,
                "type": gcat.TYPE_NAMES.get((r.get("Type") or "Z")[:1], "other"),
                "intldes": [rec(r.get("Piece", ""), GCAT, read, "catalog", ref=jcat)],
                "launch_tag": [rec(r.get("Launch_Tag", ""), GCAT, read, "catalog", ref=jcat)],
                "launch_date": [rec(ldate, GCAT, read, "attributed", ref=jcat)],
                "names": _gcat_names(r, read, jcat),
                "owner": _owner(r.get("Owner", ""), orgs, read, jcat),
                "state": [rec(r.get("State", ""), GCAT, read, "attributed", ref=jcat)],
                "status": [rec(status, GCAT, read, "attributed", ref=jcat)],
                "decayed": [rec(status in gcat.GONE, GCAT, read, "attributed", ref=jcat, date=ddate)],
                "gcat_catalog": cat,
            }
            if norad and cat in gcat.US_CATALOGS:
                key = str(int(norad))
                if key in numbered:  # one number twice in the US catalogs (0 on 13 Nov 2026): keep both, flag it
                    numbered[key].setdefault("also_in_gcat", []).append(e)
                else:
                    numbered[key] = e
            else:
                # auxcat and tmpcat: GCAT's own objects. Their Satcat cell, when filled, cites a US number GCAT
                # relates them to (auxcat A00002 cites 00003); it is not a claim to that number, so no NORAD key.
                e["norad"] = None
                e["no_norad"] = True
                if norad:
                    e["gcat_satcat_cell"] = int(norad)
                unnumbered[jcat] = e
    for e in list(numbered.values()) + list(unnumbered.values()):
        finish(e)
    return numbered, unnumbered


def _rank(source: str) -> int:
    return RANK.index(source) if source in RANK else len(RANK)


def display_name(names: list[dict]) -> str | None:
    """The first-ranked name; when it is a designation or placeholder, the best-ranked other name follows it in
    brackets ("USA 257 (CLIO)"). Within one source, names keep the source's own order (GCAT: Name, PLName,
    AltNames)."""
    ordered = sorted(names, key=lambda n: _rank(n["source"]))  # stable: keeps each source's own order
    if not ordered:
        return None
    first = ordered[0]
    if first["basis"] != "catalog":
        return first["value"]
    other = next((n for n in ordered[1:] if n["basis"] != "catalog"
                  and n["value"].lower() != first["value"].lower()), None)
    return f"{first['value']} ({other['value']})" if other else first["value"]


def disagreements(e: dict) -> list[dict]:
    """Fields in FLAGGED where sources give different values. Listed, never resolved."""
    out = []
    for field in FLAGGED:
        by_value: dict = {}
        for r in e.get(field) or []:
            if r["value"] in (None, ""):
                continue
            by_value.setdefault(r["value"], []).append(r["source"])
        if len(by_value) > 1:
            out.append({"field": field, "claims": [{"value": v, "sources": s} for v, s in by_value.items()]})
    if e.get("also_in_gcat"):
        out.append({"field": "gcat_catalog", "claims": [{"value": x["jcat"], "sources": [GCAT]}
                                                        for x in [e] + e["also_in_gcat"]]})
    return out


def finish(e: dict) -> dict:
    e["name"] = display_name(e["names"])
    e["disagreements"] = disagreements(e)
    return e


def swaps(numbered: dict) -> list[dict]:
    """Piece swaps: one payload name that two sources give to different numbers. Flagged, never resolved (names never
    move numbers). With GCAT alone there is one source, so nothing is flagged."""
    claims: dict[str, dict[str, set]] = {}
    for key, e in numbered.items():
        if e["type"] != "payload":
            continue
        for n in e["names"]:
            if n["basis"] == "catalog":
                continue
            claims.setdefault(n["value"].lower(), {}).setdefault(n["source"], set()).add(key)
    out = []
    for name, by_src in sorted(claims.items()):
        numbers = set().union(*by_src.values())
        if len(by_src) > 1 and len(numbers) > 1 and len({frozenset(v) for v in by_src.values()}) > 1:
            out.append({"name": name, "claims": {s: sorted(v, key=int) for s, v in by_src.items()},
                        "status": "open"})
    return out


def build(tables: dict[str, list[dict]], orgs: dict, read: str, gcat_updated: str | None = None) -> dict:
    numbered, unnumbered = from_gcat(tables, orgs, read)
    return {
        "schema": SCHEMA,
        "read": read,
        "sources": {GCAT: {"read": read, "updated": gcat_updated, "citation": gcat.CITATION}},
        "rank": list(RANK),
        "counts": {"numbered": len(numbered), "unnumbered": len(unnumbered),
                   "with_disagreements": sum(1 for e in numbered.values() if e["disagreements"])},
        "objects": numbered,
        "unnumbered": unnumbered,
        "swaps": swaps(numbered),
    }
