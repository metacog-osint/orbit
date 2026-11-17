"""Rendezvous and proximity operations (RPO) in space, from Secure World Foundation's sheet (orbit-2.7).

Source: Secure World Foundation, Global Counterspace Capabilities (2026), "History of Robotic Rendezvous and
Proximity Operations in Space", linked from the report's page under "Additional Information"; the report is
CC BY-NC 4.0 (so not for commercial use). Read as the sheet's own CSV export, no key, one request per tab:
https://docs.google.com/spreadsheets/d/1pHzvC-zGjF34Jrd6TdmM4odTL_MinBBoS_ld9X3jsW4/

Tabs (read 15 Nov 2026): an About tab (title, authors, "Last Updated 17 February 2026", categories), and three data
tabs, each a header row then one row per activity: Commercial/Civil (Country, Date of Activity, Client Satellite,
Servicer Satellite, Mission Type, Orbit, Launch Site, Debris Released, debris counts), Military/Intelligence (the
same with Date of Test, Target Satellite, Chaser Satellite) and Planned (Country, Date of Test, Org, Client,
Servicer, Mission Type, Launch Site, Notes, Source).

Orbit keeps SWF's own text for every field. Dates are free text ("Apr 14, 2005", "Mar - Apr 2017", "Oct 2014 -
Present", "1990-1998"); Orbit reads them into a start, an end, a precision (day, month or year) and whether the
activity is ongoing, and lists the rows it cannot read apart, with SWF's text, rather than guessing. Satellite
names are matched to TIC's satellite catalog (every source's names, orbit-2.16) or, failing that, GCAT, only where
exactly one payload fits, or by a reviewed alias-file entry (see `link`). History, not events: nothing goes
into the feed.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date

from .gcat import GONE  # GCAT statuses for an object no longer in orbit; only then is its DDate a reentry

SHEET = "https://docs.google.com/spreadsheets/d/1pHzvC-zGjF34Jrd6TdmM4odTL_MinBBoS_ld9X3jsW4/"
REPORT = "https://www.swfound.org/publications-and-reports/2026-global-counterspace-capabilities-report"
EXPORT = SHEET + "export?format=csv&gid={gid}"
ABOUT_GID = "1782604784"
# tab id -> gid, SWF's tab name, the two satellite columns' names, and the fewest rows a good reading has
TABS = {
    "commercial": {"gid": "0", "name": "Commercial/Civil", "roles": ("Client", "Servicer"), "min": 10},
    "military": {"gid": "1789904048", "name": "Military/Intelligence", "roles": ("Target", "Chaser"), "min": 35},
    "planned": {"gid": "1403218889", "name": "Planned", "roles": ("Client", "Servicer"), "min": 1},
}
COUNTRY_ISO = {"USA": "US", "United States": "US", "Russia": "RU", "China": "CN", "Japan": "JP", "India": "IN",
               "Sweden": "SE", "Italy": "IT", "UK": "GB", "United Kingdom": "GB", "Switzerland": "CH",
               "France": "FR", "Germany": "DE", "Israel": "IL", "Canada": "CA"}
DASHES = {"", "-", "--", "–", "—", "––", "n/a", "N/A", "tbc", "tbd"}
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_M = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
_UPDATED = re.compile(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})")


def _text(s: str) -> str:
    t = re.sub(r"\s+", " ", (s or "")).strip()
    return "" if t in DASHES else t


def _int(s: str) -> int | None:
    t = (s or "").strip().replace(",", "")
    return int(t) if t.isdigit() else None


def _mon(s: str) -> int:
    return MONTHS[s[:3].lower()]


def _ymd(y, m=None, d=None) -> str:
    if m is None:
        return f"{int(y):04d}"
    if d is None:
        return f"{int(y):04d}-{int(m):02d}"
    return date(int(y), int(m), int(d)).isoformat()


def _when(start: str, end: str | None, precision: str, ongoing: bool = False) -> dict:
    return {"start": start, "end": end, "precision": precision, "ongoing": ongoing}


def parse_when(text: str) -> dict | None:
    """SWF's free-text date to {"start", "end", "precision", "ongoing"} (ISO dates cut to the precision), or None
    when the text does not fit one of the forms the sheet uses. A note in brackets ("April 27, 2021 (launch)") is
    left out of the reading and kept in SWF's text."""
    t = re.sub(r"\([^)]*\)", " ", text or "")
    t = re.sub(r"[–—]", "-", t).replace(".", " ").replace(",", " ")
    t = re.sub(r"\s*-\s*", " - ", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    if not t:
        return None
    try:
        if " & " in t:  # "Dec 23, 2008 & Jan 1, 2009": two dates, read as the span from the first to the last
            parts = [parse_when(p) for p in t.split(" & ")]
            if all(p and p["precision"] == "day" for p in parts):
                return _when(parts[0]["start"], parts[-1]["end"], "day")
            return None
        m = re.fullmatch(rf"{_M} (\d{{1,2}}) (\d{{4}})", t)
        if m:
            d = _ymd(m.group(3), _mon(m.group(1)), m.group(2))
            return _when(d, d, "day")
        m = re.fullmatch(rf"{_M} (\d{{4}})", t)
        if m:
            d = _ymd(m.group(2), _mon(m.group(1)))
            return _when(d, d, "month")
        m = re.fullmatch(r"(\d{4})", t)
        if m:
            return _when(m.group(1), m.group(1), "year")
        m = re.fullmatch(rf"{_M} (\d{{1,2}}) - (\d{{1,2}}) (\d{{4}})", t)  # Jun 15-29 2020
        if m:
            mo = _mon(m.group(1))
            return _when(_ymd(m.group(4), mo, m.group(2)), _ymd(m.group(4), mo, m.group(3)), "day")
        m = re.fullmatch(rf"{_M} (\d{{1,2}}) - {_M} (\d{{1,2}}) (\d{{4}})", t)  # Sept 3-Oct 28 2020
        if m:
            y = m.group(5)
            return _when(_ymd(y, _mon(m.group(1)), m.group(2)), _ymd(y, _mon(m.group(3)), m.group(4)), "day")
        m = re.fullmatch(rf"{_M}(?: (\d{{4}}))? - {_M} (\d{{4}})", t)  # Mar - Apr 2017, Aug 2010 - July 2011
        if m:
            y1 = m.group(2) or m.group(4)
            return _when(_ymd(y1, _mon(m.group(1))), _ymd(m.group(4), _mon(m.group(3))), "month")
        m = re.fullmatch(rf"(?:{_M} )?(\d{{4}}) - present", t)  # Oct 2014 - Present, 2014 - Present
        if m:
            if m.group(1):
                return _when(_ymd(m.group(2), _mon(m.group(1))), None, "month", True)
            return _when(m.group(2), None, "year", True)
        m = re.fullmatch(r"(\d{4}) - (\d{4})", t)  # 1990-1998
        if m:
            return _when(m.group(1), m.group(2), "year")
    except (ValueError, KeyError):
        return None
    return None


def parse_updated(body: bytes | str) -> str | None:
    """The About tab's "Last Updated" date, e.g. "17 February 2026" -> 2026-02-17."""
    text = body.decode("utf-8-sig") if isinstance(body, bytes) else body
    for r in csv.reader(io.StringIO(text)):
        if r and r[0].strip().lower() == "last updated":
            m = _UPDATED.search(" ".join(r[1:]))
            if m:
                try:
                    return date(int(m.group(3)), _mon(m.group(2)), int(m.group(1))).isoformat()
                except (ValueError, KeyError):
                    return None
    return None


def parse_tab(body: bytes | str, tab: str) -> list[dict]:
    """One data tab to rows. Raises ValueError if the header is not SWF's or fewer than the tab's minimum rows
    carry a country (a changed layout keeps the last good copy)."""
    spec = TABS[tab]
    text = body.decode("utf-8-sig") if isinstance(body, bytes) else body
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ValueError(f"SWF RPO sheet, {spec['name']}: empty")
    head = [re.sub(r"\s+", " ", h).strip().lower() for h in rows[0]]
    planned = tab == "planned"
    want = (["country", "date of test", "org", "client", "servicer", "mission type"] if planned else
            ["country", "date of", spec["roles"][0].lower(), spec["roles"][1].lower(), "mission type", "orbit"])
    if len(head) < len(want) or not all(head[i].startswith(w) for i, w in enumerate(want)):
        raise ValueError(f"SWF RPO sheet, {spec['name']}: layout changed, header {head[:6]}")
    out = []
    for r in rows[1:]:
        r = r + [""] * 12
        country = _text(r[0])
        if not country:
            continue
        row = {"tab": tab, "country": country, "cc": COUNTRY_ISO.get(country), "date_text": _text(r[1]),
               "when": parse_when(r[1])}
        if planned:
            row.update({"org": _text(r[2]), "target": _text(r[3]), "chaser": _text(r[4]),
                        "mission_type": _text(r[5]), "site": _text(r[6]), "notes": _text(r[7]),
                        "source_text": _text(r[8])})
        else:
            row.update({"target": _text(r[2]), "chaser": _text(r[3]), "mission_type": _text(r[4]),
                        "orbit": _text(r[5]), "site": _text(r[6]), "debris_released": _text(r[7]),
                        "debris_created": _int(r[8]), "debris_on_orbit": _int(r[10])})
        out.append(row)
    if len(out) < spec["min"]:
        raise ValueError(f"SWF RPO sheet, {spec['name']}: {len(out)} rows (under {spec['min']}); layout changed?")
    return out


# --- names to GCAT ----------------------------------------------------------------------------------------------

def _norm(s: str) -> str:
    s = (s or "").lower()
    # matching only; SWF's text is kept as written. GCAT spells out the Chinese series SWF abbreviates.
    s = re.sub(r"\bcomos\b|\bcosmos\b", "kosmos", s)
    s = re.sub(r"\btongxin jishu shiyan\b", "tjs", s)
    s = re.sub(r"\bshi ?jian\b", "sj", s)
    s = re.sub(r"\bshiyan\b", "sy", s)
    return re.sub(r"[^a-z0-9]", "", s)


def names(cell: str) -> list[list[str]]:
    """A satellite cell to its names, each with the forms to try in order: the whole name, then the name outside
    brackets, then each name inside ("MiTEx (USA 187, USA 188)" gives MiTEx, USA 187 and USA 188)."""
    out = []
    for part in re.split(r",(?![^()]*\))|\s&\s|\sand\s", cell or ""):
        part = part.strip()
        if not part or _norm(part) in ("multiple", "unknown", "various", "variousobjects", "others", "othersunknown"):
            continue
        outer = re.sub(r"\([^)]*\)", "", part).strip()
        inner = [x.strip() for m in re.findall(r"\(([^)]*)\)", part) for x in m.split(",") if x.strip()]
        out.append([part] + ([outer] if outer and outer != part else []))
        out += [[x] for x in inner]
    return out


def _cand(jcat: str, norad, name: str, launched: date | None, launch_year: int | None,
          gone_year: int | None) -> dict:
    """One object a name can mean: its keys, the catalog's name for it, launch day (or year) and, when it is no
    longer in orbit, the year it left."""
    return {"jcat": jcat, "norad": norad if norad not in ("", "-", None) else None, "cat_name": name,
            "ld": launched, "ly": launch_year, "gy": gone_year}


def gcat_names(objects: dict) -> dict[str, list]:
    """GCAT's catalog index (JCAT -> fields as in gcat.INDEX_FIELDS) to normalized payload name -> [candidate]. The
    fallback when the TIC catalog's name index cannot be read (orbit-2.7 to 2.15 matched on this alone)."""
    out: dict[str, list] = {}
    for jcat, row in objects.items():
        if not (row[3] or "").startswith("P"):
            continue
        gone = _gcat_year(row[7]) if row[8] in GONE else None
        out.setdefault(_norm(row[4]), []).append(
            _cand(jcat, row[1], row[4], _gcat_date(row[5]), _gcat_year(row[5]), gone))
    return out


def _iso_day(s) -> date | None:
    try:
        return date.fromisoformat(s) if s and len(s) == 10 else None
    except ValueError:
        return None


def catalog_names(names_doc: dict) -> dict[str, list]:
    """The TIC catalog's name index (`tic-catalog-names/1`, catalog.names_index) to normalized name -> [candidate]:
    every name every source gives a payload (Space-Track, GCAT, CelesTrak, Wikidata, the alias file), so SWF's
    "Luch (Olymp) 2" meets Space-Track's "LUCH (OLYMP) 2". Rows: [key, norad, jcat, type, launch date, gone date
    (or "" when gone with no date, None when in orbit), display name, names]."""
    out: dict[str, list] = {}
    for key, norad, jcat, type_, launched, gone, display, names_ in names_doc.get("objects") or []:
        if type_ != "payload":
            continue
        ld = _iso_day(launched)
        ly = int(launched[:4]) if launched and launched[:4].isdigit() else None
        gy = int(gone[:4]) if gone and gone[:4].isdigit() else None
        c = _cand(jcat or key, norad, display, ld, ly, gy)
        for n in {_norm(x) for x in names_}:
            if n:
                out.setdefault(n, []).append(c)
    return out


def alias_pins(entries: list[dict], names_doc: dict | None = None) -> dict:
    """Reviewed links from the alias file (orbit/aliases.py) for SWF's text: (normalized swf_key, swf_date or None)
    -> link. A pin is a person's reviewed claim with its evidence, so no date rule applies to it."""
    rows = {r[0]: r for r in (names_doc or {}).get("objects") or []}
    pins = {}
    for e in entries:
        if not e.get("swf_key"):
            continue
        k = (_norm(e["swf_key"]), e.get("swf_date"))
        ref = f"aliases.yml:{e['line']}"
        if "program" in e:
            pins[k] = {"program": e["program"], "members": list(e["members"]), "by": "alias", "alias_ref": ref,
                       "cited": e["source"]}
        else:
            key = str(e["norad"]) if "norad" in e else e["jcat"]
            r = rows.get(key)
            pins[k] = {"jcat": (r[2] if r else None) or (key if not key.isdigit() else None),
                       "norad": e.get("norad"), "cat_name": (r[6] if r else None) or e["name"], "by": "alias",
                       "alias_ref": ref, "cited": e["source"]}
    return pins


def _gcat_year(s: str) -> int | None:
    m = re.match(r"\s*(\d{4})", s or "")
    return int(m.group(1)) if m else None


def _gcat_date(s: str) -> date | None:
    """GCAT's launch date ("2014 Sep 27"); None when it is vaguer than a day."""
    m = re.match(r"\s*(\d{4})\s+([A-Za-z]{3})\s+(\d{1,2})\b", s or "")
    try:
        return date(int(m.group(1)), _mon(m.group(2)), int(m.group(3))) if m else None
    except (ValueError, KeyError):
        return None


def _start_span(when: dict | None) -> tuple[date, date] | None:
    """The first and last day the activity's start can mean, at the precision SWF gave it."""
    st = (when or {}).get("start")
    if not st:
        return None
    y = int(st[:4])
    if len(st) == 4:
        return date(y, 1, 1), date(y, 12, 31)
    m = int(st[5:7])
    if len(st) == 7:
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        return date(y, m, 1), date.fromordinal(nxt.toordinal() - 1)
    d = date.fromisoformat(st)
    return d, d


def _launched_just_before(fits: list, when: dict | None) -> list:
    """Of several GCAT payloads with the same name, those launched in the year up to the activity's start
    (orbit-2.13): SWF's "Luch (Olymp)", Oct 2014 - Present, is the Luch of 27 Sep 2014, not the Luch of 1994."""
    span = _start_span(when)
    if not span:
        return []
    lo = date.fromordinal(span[0].toordinal() - 366)
    return [c for c in fits if c["ld"] and lo <= c["ld"] <= span[1]]


def _same(a: dict, b: dict) -> bool:
    return a.get("jcat") == b.get("jcat") if a.get("jcat") and b.get("jcat") else \
        a.get("norad") is not None and str(a.get("norad")) == str(b.get("norad"))


def link(cell: str, when: dict | None, index: dict[str, list], pins: dict | None = None,
         date_text: str | None = None) -> list[dict]:
    """Catalog objects for a satellite cell. A reviewed alias-file entry for SWF's text (and, where given, this
    row's date text) links first (`by` "alias"). Otherwise a name links only when exactly one payload of that name
    was launched by the activity's last year (or this year if ongoing or undated) and had not left orbit before its
    first year; names that fit none are left unlinked. Of several, the one launched in the year up to the activity's
    start is taken when it is the only one (`by` "launch date"); otherwise none, rather than a guess."""
    end = (when or {}).get("end")
    last = int(end[:4]) if end else date.today().year
    first = int(when["start"][:4]) if when and when.get("start") else None
    out: list[dict] = []
    for forms in names(cell):
        for form in forms:
            n = _norm(form)
            pin = (pins or {}).get((n, date_text)) or (pins or {}).get((n, None))
            if pin:
                if not any(_same(o, pin) for o in out if "program" not in o):
                    out.append({"name": form, **pin})
                break
            fits, seen = [], set()
            for c in index.get(n, []):
                k = c["jcat"] or c["norad"]
                if k in seen:
                    continue  # one object under two of its names
                seen.add(k)
                if (c["ly"] or 0) <= last and not (first and c["gy"] is not None and c["gy"] < first):
                    fits.append(c)
            by = "name"
            if len(fits) > 1:
                near = _launched_just_before(fits, when)
                if len(near) == 1:
                    fits, by = near, "launch date"
            if len(fits) == 1:
                c = fits[0]
                if any(_same(o, c) for o in out):
                    break  # "ShiJian-21 (SJ-21)": one object, named twice
                out.append({"name": form, "jcat": c["jcat"], "norad": c["norad"], "cat_name": c["cat_name"],
                            "by": by})
                break
            if len(fits) > 1:
                break  # several fit: no link rather than a guess
    return out


def read(bodies: dict[str, bytes], objects: dict | None, names_doc: dict | None = None,
         alias_entries: list[dict] | None = None) -> dict:
    """Every tab's rows, the About tab's date, the rows whose date Orbit could not read, and catalog links: on the
    TIC catalog's name index and the alias file when `names_doc` is given (`matched_on` "catalog"), else on GCAT's
    names alone ("gcat")."""
    if names_doc:
        index, on = catalog_names(names_doc), "catalog"
    else:
        index, on = gcat_names(objects or {}), "gcat"
    pins = alias_pins(alias_entries or [], names_doc)
    rows = []
    for tab in TABS:
        rows += parse_tab(bodies[tab], tab)
    for r in rows:
        r["gcat"] = {role: link(r[role], r["when"], index, pins, r["date_text"]) for role in ("target", "chaser")}
    unread = [{"tab": r["tab"], "country": r["country"], "date_text": r["date_text"], "chaser": r["chaser"]}
              for r in rows if not r["when"]]
    counts = {t: sum(1 for r in rows if r["tab"] == t) for t in TABS}
    names_n = sum(len(names(r[role])) for r in rows for role in ("target", "chaser"))
    linked_n = sum(1 for r in rows for role in ("target", "chaser") for forms in names(r[role])
                   if any(g["name"] in forms for g in r["gcat"][role]))
    return {"updated": parse_updated(bodies.get("about") or b""), "rows": rows, "unread_dates": unread,
            "counts": counts, "matched_on": on, "names_read": (names_doc or {}).get("read"),
            "links": {"names": names_n, "linked": linked_n, "by_alias": sum(
                1 for r in rows for role in ("target", "chaser") for g in r["gcat"][role] if g["by"] == "alias")}}
