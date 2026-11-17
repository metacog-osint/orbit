"""TIC's satellite catalog (schema `tic-catalog/1`): one entry per NORAD number, every value with its source.

Design: [local path] (Tom's answers in its section 9). Build step 2: GCAT.
Build step 3 (17 Nov 2026): Space-Track SATCAT and DECAY (orbit/stcat.py). Later steps add CelesTrak SATCAT,
Wikidata, WMO OSCAR/Space and the hand-kept alias file; each arrives as more value records on the same entries,
ranked by `RANK`.

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

from . import gcat, stcat

SCHEMA = "tic-catalog/1"

# Name ranking (Tom, 16 Nov 2026): Space-Track, GCAT, CelesTrak, Wikidata, SWF, then cited aliases.
RANK = ("space-track", "gcat-mcdowell", "celestrak-satcat", "wikidata", "swf-rpo", "aliases")

# Designations and placeholders: shown, but a better name goes beside them in brackets (Tom, 16 Nov 2026).
DESIGNATION = re.compile(r"^(USA[ -]?\d+|OBJECT [A-Z]{1,3}|TBA.*|UNKNOWN)$", re.I)

# Fields compared between sources for `disagreements` (names are listed, not flagged: they differ by design).
FLAGGED = ("intldes", "launch_date", "state", "decayed")

GCAT = "gcat-mcdowell"
ST = stcat.SOURCE


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
                "decay_date": [rec(ddate, GCAT, read, "attributed", ref=jcat)] if ddate else [],
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


def add_spacetrack(numbered: dict, satcat: list[dict], decay_store: list[dict], read: str) -> dict:
    """Space-Track's SATCAT rows (and every DECAY message held) as records on the NORAD-keyed entries. An object
    GCAT does not list gets an entry of its own. Returns counts. Space-Track's values never replace GCAT's: both
    are kept, ranked by RANK, and differences are listed by `disagreements`."""
    by_decay = stcat.decay_messages(decay_store)
    counts = {"satcat_rows": 0, "added_to_gcat_entry": 0, "space_track_only": 0, "analyst_placeholders": 0,
              "with_decay_messages": 0}
    seen = set()
    for row in satcat:
        n = str(row.get("NORAD_CAT_ID") or "").strip()
        if not n.isdigit():
            continue
        key = str(int(n))
        if key in seen:  # CURRENT/Y gives one row per number; a repeat would be Space-Track's, kept once
            continue
        seen.add(key)
        counts["satcat_rows"] += 1
        e = numbered.get(key)
        if e is None:
            e = numbered[key] = {"norad": int(key), "jcat": None,
                                 "type": stcat.TYPES.get((row.get("OBJECT_TYPE") or "").upper(), "other"),
                                 "intldes": [], "launch_tag": [], "launch_date": [], "names": [], "owner": [],
                                 "state": [], "status": [], "decayed": [], "decay_date": [], "space_track_only": True}
            counts["space_track_only"] += 1
        else:
            counts["added_to_gcat_entry"] += 1
        e.setdefault("decay_date", [])
        analyst = stcat.placeholder_analyst(row)
        counts["analyst_placeholders"] += analyst
        ph = {"placeholder": True, "nocompare": True} if analyst else {}
        intl = (row.get("INTLDES") or row.get("OBJECT_ID") or "").strip()
        if intl:
            e["intldes"].append(rec(intl, ST, read, "catalog", ref=key, **ph))
        ldate = stcat._date(row.get("LAUNCH"))
        if ldate:
            e["launch_date"].append(rec(ldate, ST, read, "catalog" if analyst else "attributed", ref=key, **ph))
        country = (row.get("COUNTRY") or "").strip()
        if country:
            gstates = [r["value"] for r in e["state"] if r["source"] == GCAT]
            match = next((g for g in gstates if stcat.state_matches(country, g)), None)
            mapped = stcat.COUNTRY_TO_STATE.get(country, (country,))[0]
            if country in stcat.PLACEHOLDER_COUNTRY:
                extra = {"placeholder": True, "nocompare": True}
            elif country in stcat.OPERATOR_CODES:
                extra = {"operator_code": True, "nocompare": True}  # an operator, not a state: nothing to compare
            else:
                extra = {"cmp": match or mapped}
            e["state"].append(rec(country, ST, read, "attributed", ref=key, field="COUNTRY", **extra))
        name = (row.get("SATNAME") or row.get("OBJECT_NAME") or "").strip()
        if name:
            e["names"].insert(sum(1 for r in e["names"] if r["source"] == ST),
                              rec(name, ST, read, name_basis(name), ref=key, field="SATNAME"))
        ddate = stcat._date(row.get("DECAY"))
        e["decayed"].append(rec(bool(ddate), ST, read, "attributed", ref=key, date=ddate))
        if ddate:
            e["decay_date"].append(rec(ddate, ST, read, "attributed", ref=key, field="SATCAT DECAY"))
        msgs = by_decay.get(key) or []
        if msgs:
            counts["with_decay_messages"] += 1
            # Space-Track's glossary: "In the Decay class, lower PRECEDENCE values indicate more recent data." Only
            # "Historical" messages are decay dates; "Prediction" messages (60-day decay) stay in the store only.
            # One record per date: the first by precedence.
            dates = {r["value"] for r in e["decay_date"] if r["source"] == ST and r.get("field") == "DECAY"}
            for m in sorted(msgs, key=lambda m: (int(m.get("PRECEDENCE") or 99), m.get("MSG_EPOCH") or "")):
                d = stcat._date(m.get("DECAY_EPOCH"))
                if d and m.get("MSG_TYPE") == "Historical" and d not in dates:
                    dates.add(d)
                    e["decay_date"].append(rec(d, ST, read, "attributed", ref=key, field="DECAY",
                                               msg_type=m.get("MSG_TYPE"), msg_epoch=m.get("MSG_EPOCH"),
                                               precedence=m.get("PRECEDENCE"), st_source=m.get("SOURCE")))
        e["decay_date"].sort(key=lambda r: _rank(r["source"]))
    for e in numbered.values():
        finish(e)
    counts["gcat_not_in_satcat"] = sum(1 for k, e in numbered.items()
                                       if k not in seen and not e.get("space_track_only"))
    return counts


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
        given: dict = {}
        for r in e.get(field) or []:
            if r["value"] in (None, "") or r.get("nocompare"):
                continue
            v = r.get("cmp", r["value"])
            if field == "intldes":
                v = stcat.comparable_intldes(r["value"])
                if v is None:  # GCAT's pre-1963 Greek-letter pieces: no table maps them, so not compared
                    continue
            by_value.setdefault(v, []).append(r["source"])
            given.setdefault(v, []).append(r["value"])
        if len(by_value) > 1:
            claims = []
            for v, s in by_value.items():
                c = {"value": v, "sources": s}
                if any(g != v for g in given[v]):
                    c["as_given"] = given[v]  # e.g. Space-Track's COUNTRY "PRC", compared as GCAT's "CN"
                claims.append(c)
            out.append({"field": field, "claims": claims})
    if e.get("also_in_gcat"):
        out.append({"field": "gcat_catalog", "claims": [{"value": x["jcat"], "sources": [GCAT]}
                                                        for x in [e] + e["also_in_gcat"]]})
    return out


def finish(e: dict) -> dict:
    e["name"] = display_name(e["names"])
    e["disagreements"] = disagreements(e)
    return e


def _launch(e: dict) -> str | None:
    """The launch part of the best-ranked comparable designation ('2014-043' from '2014-043A')."""
    for r in sorted(e.get("intldes") or [], key=lambda r: _rank(r["source"])):
        v = stcat.comparable_intldes(r["value"])
        if v:
            return v[:8]
    return None


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
        # A swap needs each of two sources to give the name to a number the other does not, and every number to
        # come from one launch. A source that gives one name to more numbers than another does is not a swap, nor
        # is one name used again on a later launch ("Early Bird", 1965 and 1997: 17 Nov 2026 reading).
        sets = list(by_src.values())
        if not any(a - b and b - a for i, a in enumerate(sets) for b in sets[i + 1:]):
            continue
        launches = {_launch(numbered[k]) for k in set().union(*sets)}
        if len(launches) == 1 and None not in launches:
            out.append({"name": name, "claims": {s: sorted(v, key=int) for s, v in by_src.items()},
                        "status": "open"})
    return out


def build(tables: dict[str, list[dict]], orgs: dict, read: str, gcat_updated: str | None = None,
          spacetrack: dict | None = None) -> dict:
    """`spacetrack`: {"satcat": rows, "decay": every DECAY message held, "read": 'YYYY-MM-DD', "read_at": ...}."""
    numbered, unnumbered = from_gcat(tables, orgs, read)
    sources = {GCAT: {"read": read, "updated": gcat_updated, "citation": gcat.CITATION}}
    st_counts = None
    if spacetrack:
        st_counts = add_spacetrack(numbered, spacetrack["satcat"], spacetrack.get("decay") or [], spacetrack["read"])
        sources[ST] = {"read": spacetrack["read"], "read_at": spacetrack.get("read_at"), "citation": stcat.CITATION}
    flags: dict = {}
    for e in numbered.values():
        for d in e["disagreements"]:
            flags[d["field"]] = flags.get(d["field"], 0) + 1
    return {
        "schema": SCHEMA,
        "read": read,
        "sources": sources,
        "rank": list(RANK),
        "counts": {"numbered": len(numbered), "unnumbered": len(unnumbered),
                   "with_disagreements": sum(1 for e in numbered.values() if e["disagreements"]),
                   "disagreements_by_field": flags, **({"space_track": st_counts} if st_counts else {})},
        "objects": numbered,
        "unnumbered": unnumbered,
        "swaps": swaps(numbered),
    }
