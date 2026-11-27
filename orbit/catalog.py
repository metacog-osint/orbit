"""TIC's satellite catalog (schema `tic-catalog/1`): one entry per NORAD number, every value with its source.

Design: the private planning notes (Tom's answers in its section 9). Build step 2: GCAT.
Build step 3 (17 Nov 2026): Space-Track SATCAT and DECAY (orbit/stcat.py). Build step 4 (17 Nov 2026): CelesTrak
SATCAT and Wikidata (orbit/catsources.py). Build step 5 (17 Nov 2026): the hand-kept alias file (orbit/aliases.py)
and a name index for readers (`names_index`). WMO OSCAR/Space comes through a reviewed link file; each source arrives
as more value records on the same entries, ranked by `RANK`.

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

from . import aliases, catsources, gcat, oscar, oscarlinks, stcat

SCHEMA = "tic-catalog/1"

# Name ranking (Tom, 16 Nov 2026): Space-Track, GCAT, CelesTrak, Wikidata, SWF, then cited aliases. WMO OSCAR/Space
# (join step, 20 Nov 2026) sits after Wikidata: its acronyms never replace a name another source gives; only an
# object with no other name shows OSCAR's.
RANK = ("space-track", "gcat-mcdowell", "celestrak-satcat", "wikidata", "wmo-oscar-space", "swf-rpo", "aliases")

# Designations and placeholders: shown, but a better name goes beside them in brackets (Tom, 16 Nov 2026).
# Space-Track's "PAYLOAD A" to "PAYLOAD C" (2013-037: SJ-15 is 39210) are placeholders like "OBJECT A".
DESIGNATION = re.compile(r"^(USA[ -]?\d+|OBJECT [A-Z]{1,3}|PAYLOAD [A-Z]{1,3}|TBA.*|UNKNOWN)$", re.I)

# Fields compared between sources for `disagreements` (names are listed, not flagged: they differ by design).
# `ops_status` is an operational status (CelesTrak's +/-/P/B/S/X), compared only where two sources both give one;
# GCAT's `status` is an orbital status (in orbit, reentered, docked...), not an operational one, so it is not compared.
FLAGGED = ("intldes", "launch_date", "state", "decayed", "ops_status")

GCAT = "gcat-mcdowell"
ST = stcat.SOURCE
CT = catsources.CT
WD = catsources.WD
FIELDS = ("intldes", "launch_tag", "launch_date", "names", "owner", "state", "status", "ops_status", "decayed",
          "decay_date", "orbit")


def _num(text) -> float | None:
    """A number as the source writes it, or None for blanks, '-' and GCAT's 'Inf' (gcat._float)."""
    return gcat._float(str(text or ""))


def gcat_orbit(r: dict) -> dict | None:
    """GCAT's orbit as GCAT states it (build step 6): perigee and apogee (km), inclination (degrees), the date of its
    elements (ODate) and its orbit class (OpOrbit). GCAT's 0 / 0 / 0 before elements exist, and '-' where none
    apply, give no record (gcat.orbit_of's rule); values are kept as written, not rounded."""
    if gcat.orbit_of(r)["inc"] is None:
        return None
    return {"perigee_km": _num(r.get("Perigee")), "apogee_km": _num(r.get("Apogee")), "inc_deg": _num(r.get("Inc")),
            "elements_date": gcat.vague_date(r.get("ODate", ""))["date"],
            "op_orbit": (r.get("OpOrbit") or "").strip() or None}


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
                "orbit": [rec(o, GCAT, read, "attributed", ref=jcat)] if (o := gcat_orbit(r)) else [],
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
            e["state"].append(state_rec(e, country, ST, read, key, "COUNTRY"))
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


def state_rec(e: dict, code: str, source: str, read: str, ref: str, field: str) -> dict:
    """A Space-Track country code (Space-Track COUNTRY; CelesTrak's OWNER uses the same codes) as a state record,
    compared with GCAT's State through stcat.COUNTRY_TO_STATE; operator codes and placeholders are kept, never
    compared."""
    table, operators = stcat.COUNTRY_TO_STATE, stcat.OPERATOR_CODES
    if source == CT:  # CelesTrak adds codes of its own (catsources.CT_OWNER_TO_STATE)
        table, operators = {**table, **catsources.CT_OWNER_TO_STATE}, operators | catsources.CT_PROGRAM_CODES
    gstates = [r["value"] for r in e["state"] if r["source"] == GCAT]
    match = next((g for g in gstates if g in table.get(code, (code,))), None)
    mapped = table.get(code, (code,))[0]
    if code in stcat.PLACEHOLDER_COUNTRY:
        extra = {"placeholder": True, "nocompare": True}
    elif code in operators:
        extra = {"operator_code": True, "nocompare": True}  # an operator, not a state: nothing to compare
    else:
        extra = {"cmp": match or mapped}
    return rec(code, source, read, "attributed", ref=ref, field=field, **extra)


def _entry(numbered: dict, key: str, source: str, type_: str = "other") -> tuple[dict, bool]:
    """The entry for a number; an empty one, marked `only_in`, when no earlier source lists the number."""
    e = numbered.get(key)
    if e is None:
        e = numbered[key] = {"norad": int(key), "jcat": None, "type": type_, **{f: [] for f in FIELDS},
                             "only_in": [source]}
        return e, True
    for f in FIELDS:
        e.setdefault(f, [])
    if e.get("only_in") is not None and source not in e["only_in"]:
        e["only_in"].append(source)
    return e, False


def _norad(cell) -> str | None:
    n = str(cell or "").strip()
    return str(int(n)) if n.isdigit() else None


CT_TYPES = {"PAY": "payload", "R/B": "rocket stage", "DEB": "debris"}


def ct_orbit(row: dict) -> dict | None:
    """CelesTrak SATCAT's orbit as CelesTrak states it (build step 6): perigee and apogee (km), inclination
    (degrees), period (minutes), and CelesTrak's ORBIT_CENTER and ORBIT_TYPE codes, all as written in its file (codes
    kept, not decoded here: celestrak.org/satcat/satcat-format.php); no epoch is given, so the file's time (sources)
    dates it. No numbers, no record."""
    o = {"perigee_km": _num(row.get("PERIGEE")), "apogee_km": _num(row.get("APOGEE")),
         "inc_deg": _num(row.get("INCLINATION")), "period_min": _num(row.get("PERIOD"))}
    if all(v is None for v in o.values()):
        return None
    o["orbit_center"] = (row.get("ORBIT_CENTER") or "").strip() or None
    o["orbit_type"] = (row.get("ORBIT_TYPE") or "").strip() or None
    return o


def add_celestrak(numbered: dict, rows: list[dict], read: str) -> dict:
    """CelesTrak SATCAT rows (CSV; celestrak.org/satcat/satcat-format.php) as records. OBJECT_NAME is kept as given:
    CelesTrak puts alternate names in brackets ("USA 257 (CLIO)") and object kinds in square brackets."""
    counts = {"rows": 0, "added_to_entry": 0, "celestrak_only": 0, "with_ops_status": 0}
    seen = set()
    for row in rows:
        key = _norad(row.get("NORAD_CAT_ID"))
        if not key or key in seen:
            continue
        seen.add(key)
        counts["rows"] += 1
        e, new = _entry(numbered, key, CT, CT_TYPES.get((row.get("OBJECT_TYPE") or "").strip(), "other"))
        counts["celestrak_only" if new else "added_to_entry"] += 1
        intl = (row.get("OBJECT_ID") or "").strip()
        if intl:
            e["intldes"].append(rec(intl, CT, read, "catalog", ref=key))
        ldate = (row.get("LAUNCH_DATE") or "").strip()[:10]
        if ldate:
            e["launch_date"].append(rec(ldate, CT, read, "attributed", ref=key))
        owner = (row.get("OWNER") or "").strip()
        if owner:
            e["state"].append(state_rec(e, owner, CT, read, key, "OWNER"))
        name = (row.get("OBJECT_NAME") or "").strip()
        if name:
            e["names"].append(rec(name, CT, read, name_basis(name), ref=key, field="OBJECT_NAME"))
        ops = (row.get("OPS_STATUS_CODE") or "").strip()
        ddate = (row.get("DECAY_DATE") or "").strip()[:10] or None
        if ops:
            counts["with_ops_status"] += 1
            cls = catsources.CT_OPS.get(ops)
            e["ops_status"].append(rec(ops, CT, read, "attributed", ref=key, field="OPS_STATUS_CODE",
                                       **({"cmp": cls} if cls else {"nocompare": True})))
        e["decayed"].append(rec(bool(ddate) or ops == "D", CT, read, "attributed", ref=key, date=ddate))
        if ddate:
            e["decay_date"].append(rec(ddate, CT, read, "attributed", ref=key, field="DECAY_DATE"))
        o = ct_orbit(row)
        if o:
            e["orbit"].append(rec(o, CT, read, "attributed", ref=key))
    for e in numbered.values():
        finish(e)
    counts["not_in_celestrak"] = sum(1 for k in numbered if k not in seen)
    return counts


def add_wikidata(numbered: dict, rows: list[dict], read: str) -> dict:
    """Wikidata items carrying P377 (rows from catsources.wd_parse): English and multilingual labels and English
    aliases as names, P247 as `intldes`; ref is the Q-id. Wikidata's "unknown value" (no number) is skipped."""
    counts = {"rows": 0, "items": 0, "added_to_entry": 0, "wikidata_only": 0, "unknown_value_skipped": 0,
              "numbers_on_two_items": 0}
    items_by_key: dict[str, set] = {}
    for row in rows:
        key = _norad(row.get("scn"))
        if not key:
            counts["unknown_value_skipped"] += 1
            continue
        counts["rows"] += 1
        qid = row["qid"]
        first = key not in items_by_key
        items_by_key.setdefault(key, set()).add(qid)
        e, new = _entry(numbered, key, WD)
        if first:
            counts["wikidata_only" if new else "added_to_entry"] += 1
        cospar = (row.get("cospar") or "").strip()
        if cospar and not cospar.startswith("http") and not any(
                r["source"] == WD and r["ref"] == qid and r["value"] == cospar for r in e["intldes"]):
            e["intldes"].append(rec(cospar, WD, read, "catalog", ref=qid, field="P247"))
        have = {r["value"].lower() for r in e["names"] if r["source"] == WD and r["ref"] == qid}
        for name, field in ([(row.get("en"), "label:en"), (row.get("mul"), "label:mul")]
                            + [(a, "altLabel:en") for a in row.get("alts") or []]):
            name = (name or "").strip()
            if name and name.lower() not in have:
                have.add(name.lower())
                e["names"].append(rec(name, WD, read, name_basis(name), ref=qid, field=field))
    counts["items"] = len({q for qs in items_by_key.values() for q in qs})
    counts["numbers_on_two_items"] = sum(1 for qs in items_by_key.values() if len(qs) > 1)
    for key, qs in items_by_key.items():
        if len(qs) > 1:  # attached objects (ISS and Zarya, Transit 3B/LOFTI 1): a note, not a disagreement
            numbered[key]["wikidata_items"] = sorted(qs)
    for e in numbered.values():
        finish(e)
    return counts


OS = oscar.SOURCE


def add_oscar(numbered: dict, links: list[dict], satellites: list[dict], read: str) -> dict:
    """WMO OSCAR/Space (build join step, Tom's yes 20 Nov 2026) through the reviewed link file only: `links` are the
    reviewed live entries of oscar-links.yml (oscarlinks.reviewed), `satellites` the last read (oscar.store_load).
    A `same` entry with one number adds OSCAR's operator (`space_agency`, declared through WMO), its status (compared
    with CelesTrak's through oscar.STATUS_CLASS) and its acronym and full name as names. An entry that stands for
    several objects (`members`) adds the operator and the OSCAR entry's name as a `program` to each, no status or
    name: it describes the group, not each member. A `hosted` entry (an instrument on another object) adds only a
    `hosted` record to the host, never a name, operator or status. The link file's evidence and reviewer never
    enter the catalog. A linked number the catalog does not hold, or a slug the read no longer lists, is counted."""
    by_slug = {s["slug"]: s for s in satellites}
    counts = {"links": 0, "names": 0, "operators": 0, "status": 0, "programs": 0, "hosted": 0,
              "slug_not_in_read": [], "not_in_catalog": []}
    for link in links:
        counts["links"] += 1
        sat = by_slug.get(link["slug"])
        if sat is None:
            counts["slug_not_in_read"].append(link["slug"])
            continue
        slug = link["slug"]
        label = (sat.get("acronym") or sat.get("fullname") or slug).strip()
        agency = (sat.get("space_agency") or "").strip()
        for n in oscarlinks.numbers(link):
            e = numbered.get(str(n))
            if e is None:
                counts["not_in_catalog"].append(n)
                continue
            _entry(numbered, str(n), OS)  # makes sure every list field exists
            if link["relation"] == "hosted":
                e.setdefault("hosted", []).append(rec(label, OS, read, "attributed", ref=slug, field="satellite"))
                counts["hosted"] += 1
                continue
            if agency:
                e.setdefault("operator", []).append(rec(agency, OS, read, "declared", ref=slug, field="space_agency"))
                counts["operators"] += 1
            if "members" in link:
                e.setdefault("program", []).append(rec(label, OS, read, "attributed", ref=slug, field="acronym"))
                counts["programs"] += 1
                continue
            have = set()
            for name, field in ((sat.get("acronym"), "acronym"), (sat.get("fullname"), "fullname")):
                name = (name or "").strip()
                if name and name.lower() not in have:
                    have.add(name.lower())
                    e["names"].append(rec(name, OS, read, name_basis(name), ref=slug, field=field))
                    counts["names"] += 1
            status = (sat.get("status") or "").strip()
            if status:
                cls = oscar.STATUS_CLASS.get(status)
                e["ops_status"].append(rec(status, OS, read, "attributed", ref=slug, field="status",
                                           **({"cmp": cls} if cls else {"nocompare": True})))
                counts["status"] += 1
            finish(e)
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


def add_aliases(numbered: dict, unnumbered: dict, entries: list[dict]) -> dict:
    """The alias file's live entries (orbit/aliases.py, build step 5): a name entry adds a name record (source
    `aliases`, the cited source kept as `cited`) to its object; a program entry adds a `program` record to each
    member. An entry naming an object the catalog does not hold is counted in `not_in_catalog`, never invented."""
    counts = {"names": 0, "programs": 0, "swaps": 0, "not_in_catalog": []}
    for e in entries:
        ref = f"aliases.yml:{e['line']}"
        if aliases.is_swap(e):
            counts["swaps"] += 1
            for c in e["claims"]:
                if str(c["norad"]) not in numbered:
                    counts["not_in_catalog"].append(str(c["norad"]))
            continue
        if "program" in e:
            counts["programs"] += 1
            for m in e["members"]:
                obj = numbered.get(str(m))
                if obj is None:
                    counts["not_in_catalog"].append(str(m))
                    continue
                obj.setdefault("program", []).append(
                    rec(e["program"], aliases.SOURCE, e["read"], e["basis"], ref, cited=e["source"]))
            continue
        key = aliases.key_of(e)
        obj = numbered.get(key) or unnumbered.get(key)
        if obj is None:
            counts["not_in_catalog"].append(key)
            continue
        obj["names"].append(aliases.name_record(e))
        counts["names"] += 1
        finish(obj)
    return counts


NAMES_SCHEMA = "tic-catalog-names/1"


def _first(e: dict, field: str):
    recs = sorted(e.get(field) or [], key=lambda r: _rank(r["source"]))
    return recs[0]["value"] if recs else None


def names_index(doc: dict, keys: set[str] | None = None) -> dict:
    """A small index for readers that match names (Orbit's `rpo` lane): every payload, numbered or not, plus any
    object in `keys` (the alias file's), as [key, norad, jcat, type, launch date, gone date, display name, names].
    Gone date: the best-ranked decay date when the best-ranked source says the object has left orbit ("" when it
    gives no date), None while in orbit."""
    rows = []
    keys = keys or set()
    for group in ("objects", "unnumbered"):
        for key, e in doc[group].items():
            if e["type"] != "payload" and key not in keys:
                continue
            gone = (_first(e, "decay_date") or "") if _first(e, "decayed") else None
            seen, ns = set(), []
            for n in sorted(e["names"], key=lambda r: _rank(r["source"])):
                if n["value"] not in seen:
                    seen.add(n["value"])
                    ns.append(n["value"])
            rows.append([key, e.get("norad"), e.get("jcat"), e["type"], _first(e, "launch_date"), gone, e.get("name"),
                         ns])
    return {"schema": NAMES_SCHEMA, "read": doc["read"], "catalog_schema": doc["schema"],
            "sources": {s: v.get("read") for s, v in doc["sources"].items()}, "objects": rows}


def build(tables: dict[str, list[dict]], orgs: dict, read: str, gcat_updated: str | None = None,
          spacetrack: dict | None = None, celestrak: dict | None = None, wikidata: dict | None = None,
          alias_entries: list[dict] | None = None, oscar_join: dict | None = None) -> dict:
    """`spacetrack`: {"satcat": rows, "decay": every DECAY message held, "read": 'YYYY-MM-DD', "read_at": ...}.
    `celestrak`, `wikidata`: {"rows": ..., "read": 'YYYY-MM-DD', "read_at": ...}, as catsources.load gives them.
    `alias_entries`: the alias file's live entries (aliases.load).
    `oscar_join`: {"links": reviewed link entries, "satellites": ..., "read": 'YYYY-MM-DD', "read_at": ...}."""
    numbered, unnumbered = from_gcat(tables, orgs, read)
    sources = {GCAT: {"read": read, "updated": gcat_updated, "citation": gcat.CITATION}}
    st_counts = None
    if spacetrack:
        st_counts = add_spacetrack(numbered, spacetrack["satcat"], spacetrack.get("decay") or [], spacetrack["read"])
        sources[ST] = {"read": spacetrack["read"], "read_at": spacetrack.get("read_at"), "citation": stcat.CITATION}
    more = {}
    if celestrak:
        more[CT] = add_celestrak(numbered, celestrak["rows"], celestrak["read"])
        sources[CT] = {"read": celestrak["read"], "read_at": celestrak.get("read_at"),
                       "file_time": celestrak.get("file_mtime"), "citation": catsources.CT_CITATION}
    if wikidata:
        more[WD] = add_wikidata(numbered, wikidata["rows"], wikidata["read"])
        sources[WD] = {"read": wikidata["read"], "read_at": wikidata.get("read_at"),
                       "citation": catsources.WD_CITATION}
    if oscar_join and oscar_join.get("satellites") and oscar_join.get("links"):
        more[OS] = add_oscar(numbered, oscar_join["links"], oscar_join["satellites"], oscar_join["read"])
        sources[OS] = {"read": oscar_join["read"], "read_at": oscar_join.get("read_at"), "citation": oscar.CITATION}
    if alias_entries:
        more[aliases.SOURCE] = add_aliases(numbered, unnumbered, alias_entries)
        sources[aliases.SOURCE] = {"read": max(aliases.read_of(e) for e in alias_entries), "entries": len(alias_entries),
                                   "file": "orbit/data/catalog/aliases.yml"}
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
                   "disagreements_by_field": flags, **({"space_track": st_counts} if st_counts else {}), **more},
        "objects": numbered,
        "unnumbered": unnumbered,
        "swaps": merge_swaps(swaps(numbered), [e for e in alias_entries or [] if aliases.is_swap(e)]),
    }


def merge_swaps(found: list[dict], entries: list[dict]) -> list[dict]:
    """The swaps the build found plus the alias file's swap entries. An entry on a name the build also found adds
    its claims, spellings and line to that swap; the build's own claims stay as found."""
    out = [dict(s) for s in found]
    by_name = {s["name"]: s for s in out}
    for e in entries:
        r = aliases.swap_record(e)
        s = by_name.get(r["name"])
        if s is None:
            out.append(r)
            by_name[r["name"]] = r
            continue
        claims = {k: list(v) for k, v in s["claims"].items()}
        for src, nums in r["claims"].items():
            claims[src] = sorted(set(claims.get(src, [])) | set(nums), key=int)
        s.update({"claims": claims, "as": {**s.get("as", {}), **r["as"]}, "by": aliases.SOURCE, "ref": r["ref"]})
        for k in ("status", "settled_by", "settled"):
            if k in r:
                s[k] = r[k]
    return sorted(out, key=lambda s: s["name"])
