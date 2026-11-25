"""Satellite names: a lookup across every source's names, and the longitude a name states (ideas#359, #361;
25 Nov 2026).

Why: on 25 Nov 2026 a session looking for "Eutelsat 12 West G" read the hand-kept alias file (a handful of reviewed
links for SWF's RPO sheet), found nothing and went to the web. The TIC catalog's search index already had the name:
Wikidata's label on NORAD 33459, which Space-Track and CelesTrak still call "EUTELSAT HOTBIRD 13C". The same day
Orbit showed 27508 as "EUTE 12 WEST A" (Space-Track's name) although it had moved to 36° W, and 33459 had moved from
12.5° W to 50.3° W (Eutelsat renamed it 50 West A). Operators put the slot in the name and keep the old name until
they rename the satellite, so a name can state a position the satellite has left.

Lookup (`find`): every name from every source in the catalog's search index (`tic-catalog-search/1`), matched
loosely: case, spacing and punctuation ignored, and "West"/"East" read as "W"/"E", so "12WG" finds "12 West G".

Stated longitude (`stated_lon`): only naming schemes that hold a position, each checked against every name in the
catalog index of 24 Nov 2026 (tests/test_namepos.py):
- "<number> West|East" in any name ("Eutelsat 12 West G", "EUTE 115 WEST B(SATMEX 7");
- Eutelsat's short forms: "Eutelsat|EUTE <number><letter>" is degrees east ("EUTE 36B", "EUTELSAT 7C"), and
  "<number>W" is west ("EUTE 117W B", "EUTE 65W");
- "Hot Bird 13<letter>" (Eutelsat's 13° E names; plain "Hot Bird 9" is a serial, not a position);
- Hispasat's "<number>W-<n>" ("HISPASAT 30W-6").
Nothing else: "Intelsat 37e" (Epic), "Astra 2E", "Fengyun 2E" and the like are series letters, never positions.
A stated position is what the name says, not a claim by Orbit; a name differing from the measured position is
most often a former name. Names give the slot only to the whole degree: Eutelsat's "12 West" slot is at 12.5° W
(12 West A, B, E and G all sat there; Eutelsat URD 2022-23 fleet table) and "7 West A" at 7.3° W. So a stated
position is shown as the name gives it ("named for 12° W"), never as a measured longitude, and a name within
TOLERANCE_DEG of the satellite counts as fitting.
"""
from __future__ import annotations

import re

TOLERANCE_DEG = 1.0   # a stated position this close to the measured one counts as the same slot

_WORD = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d)?)\s*°?\s*(west|east)\b", re.I)
_EUT = re.compile(r"^(?:eutelsat|eute)\s+(\d{1,3})(w)?(?:\s*[a-z]\b|\s*$|\s*[(/])", re.I)
_EUT_LETTER = re.compile(r"^(?:eutelsat|eute)\s+(\d{1,3})([a-vx-z])\b", re.I)
_HOTBIRD = re.compile(r"\bhot\s*-?\s*bird\s*13[a-z]\b", re.I)
_HISPASAT = re.compile(r"^hispasat\s+(\d{1,3})w-\d\b", re.I)


def compact(s: str) -> str:
    """A name or query reduced for loose matching: lower case, "west"/"east" as "w"/"e", letters and digits only."""
    words = re.findall(r"[a-z0-9]+", (s or "").casefold())
    return "".join({"west": "w", "east": "e"}.get(w, w) for w in words)


def _lon(deg: float, west: bool) -> float | None:
    if deg > 180:
        return None
    return -deg if west and deg else deg


def stated_lon(name: str) -> tuple[float, str] | None:
    """(longitude in degrees east, -180..180; the scheme that gave it) or None when the name states no position."""
    n = (name or "").strip()
    m = _WORD.search(n)
    if m:
        lon = _lon(float(m[1]), m[2].lower() == "west")
        return (lon, "number-west-east") if lon is not None else None
    m = _HISPASAT.match(n)
    if m:
        lon = _lon(float(m[1]), True)
        return (lon, "hispasat") if lon is not None else None
    if _HOTBIRD.search(n):
        return (13.0, "hot-bird-13")
    m = _EUT.match(n)
    if m and m[2]:
        lon = _lon(float(m[1]), True)
        return (lon, "eutelsat-short") if lon is not None else None
    m = _EUT_LETTER.match(n)
    if m:
        lon = _lon(float(m[1]), False)
        return (lon, "eutelsat-short") if lon is not None else None
    return None


def apart(a: float, b: float) -> float:
    """Degrees between two longitudes, the short way round."""
    return abs((a - b + 540.0) % 360.0 - 180.0)


def lon_txt(lon: float) -> str:
    return f"{abs(lon):.1f}° {'W' if lon < 0 else 'E'}" if abs(lon) >= 0.05 else "0.0°"


def named_txt(lon: float) -> str:
    """A stated position as the name gives it: "12° W", "7.5° E"; never with a decimal the name does not have."""
    return f"{abs(lon):g}° {'W' if lon < 0 else 'E'}" if lon else "0°"


def positions(names: list[str], lon: float | None) -> list[dict]:
    """Every name that states a position, with how far that is from the measured longitude `lon` (None: not
    measured). Names that differ only by case, spacing or punctuation are listed once."""
    out, seen = [], set()
    for name in names:
        key = compact(name)
        if not key or key in seen:
            continue
        seen.add(key)
        got = stated_lon(name)
        if not got:
            continue
        rec = {"name": name, "stated_lon": got[0], "scheme": got[1]}
        if lon is not None:
            rec["apart_deg"] = round(apart(got[0], lon), 1)
        out.append(rec)
    return out


# ---------------------------------------------------------------------------------------------- lookup

def rows(search_doc: dict) -> list[dict]:
    """The search index's rows as dicts: key, name, other_names, cospar, type, gone."""
    cols = search_doc.get("columns") or ["key", "name", "other_names", "cospar", "type", "gone"]
    return [dict(zip(cols, r)) for r in search_doc.get("objects") or []]


def find(search_doc: dict, query: str, limit: int = 20) -> list[dict]:
    """Objects whose key, COSPAR ID or any name matches `query`, best first: exact key or COSPAR, then a name equal
    to the query, then one starting with it, then one containing it (each loosely, see `compact`). Payloads before
    other objects, objects in orbit before those gone."""
    q = (query or "").strip()
    cq = compact(q)
    if not cq:
        return []
    hits = []
    for r in rows(search_doc):
        key, cospar = str(r.get("key") or ""), (r.get("cospar") or "")
        if q.upper() in (key.upper(), cospar.upper()) or (q.isdigit() and key == str(int(q))):
            hits.append((0, r))
            continue
        best = 9
        for i, name in enumerate([r.get("name") or ""] + list(r.get("other_names") or [])):
            c = compact(name)
            sc = 1 if c == cq else 2 if c.startswith(cq) else 3 if cq in c else 9
            if sc < 9 and i:
                sc += 0.5  # the display name before other names
            best = min(best, sc)
        if best < 9:
            hits.append((best, r))
    hits.sort(key=lambda h: (h[0], h[1].get("type") != "p", bool(h[1].get("gone")), str(h[1].get("name"))))
    return [h[1] for h in hits[:limit]]
