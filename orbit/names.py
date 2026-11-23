"""The other names an object goes by, beside the one a lane shows (orbit-2.26, 23 Nov 2026).

On 23 Nov 2026 catalog number 55841 was "Luch-5Kh No. 3" in the feed (GCAT's name), "LUCH (OLYMP) 2" on the GEO page
(Space-Track's) and "LUCH-5X (OLYMP-K 2)" in the role list (CelesTrak's), so a search for "Olymp" missed the feed
item. A lane keeps the name it already shows; this module adds the others from the TIC catalog's name index
(`tic-catalog-names/1`, release `catalog`, the file the `rpo` lane already reads: no new request).

Rules: the catalog's display name comes first, then the index's own order; a name that differs from one already
shown only by case, spacing or punctuation is left out; so is a name the source marks as uncertain (ending "?"), a
bare catalog number, and a joined form "A (B)" whose A is already shown and whose B is a name of its own in the
index ("USA 270 (Hornet 3)" beside "USA 270": "Hornet 3" follows by itself). Nothing is merged or corrected: where
sources differ, the names stand side by side, and the object's page ("Names and sources") says which source gives
which.
"""
from __future__ import annotations

import re

TITLE_NAMES = 2   # other names in a title or a lead line; the summary and the page give all of them


def loose(s: str) -> str:
    """A name reduced to letters and digits, lower case: "LUCH (OLYMP) 2" and "Luch-Olymp 2" are the same."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").casefold())


def index(names_doc: dict | None) -> dict[int, dict]:
    """The name index by catalog number: {norad: {"display", "names"}}. Rows: [key, norad, jcat, type, launch
    date, gone date, display name, names]."""
    out: dict[int, dict] = {}
    for row in (names_doc or {}).get("objects") or []:
        norad = row[1]
        if isinstance(norad, int):
            out[norad] = {"display": row[6], "names": list(row[7] or [])}
    return out


def others(primary: str | None, rec: dict | None) -> list[str]:
    """Every other name the index gives the object, the catalog's display name first."""
    if not rec:
        return []
    seen = {loose(primary)} if primary else set()
    every = {loose(n) for n in rec.get("names") or []}
    out = []
    for name in [rec.get("display")] + list(rec.get("names") or []):
        name = (name or "").strip()
        key = loose(name)
        if not key or key in seen or name.endswith("?") or name.isdigit():
            continue
        joined = re.fullmatch(r"(.+?)\s*\((.+)\)", name)
        if joined and loose(joined[1]) in seen and loose(joined[2]) in every:
            continue
        seen.add(key)
        out.append(name)
    return out


def label(primary: str, also: list[str] | None, limit: int = TITLE_NAMES) -> str:
    """"A, also B and C": the shown name with up to `limit` others, for a title."""
    also = list(also or [])[:limit]
    if not also:
        return primary
    return f"{primary}, also {' and '.join(also)}"
