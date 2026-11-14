"""Anti-satellite (ASAT) tests in space, from Secure World Foundation's sheet.

Source: Secure World Foundation, Global Counterspace Capabilities (2026), "History of ASAT Testing in Space",
CC BY-NC 4.0 (so not for commercial use). Read as the sheet's own CSV export, no key:
https://docs.google.com/spreadsheets/d/1e5GtZEzdo6xk41i2_ei3c8jRZDjvP4Xwz3BVsUHwi48/export?format=csv&gid=0

Layout (read 13 Nov 2026): a header row (one cell with an embedded newline), then one block of test rows per
country, each block closed by a "Total" row and a blank row, and a grand-total row at the end. Columns 0-11 are
the data: country, date of test (M/D/YYYY, sometimes M/D/YY), target, interceptor, interceptor type, launch site,
object hit ("Yes" or a dash), cataloged debris created, re-entered and still on orbit, date of final re-entry
("Still On Orbit", a dash or a date) and lifespan of the debris in years. Columns 12 and later hold SWF's totals,
footnotes and "Last Updated 17-Feb-26 Updated By ..."; only the "Last Updated" date is taken from them, and nothing
there is ever read as a test.

Debris counts are U.S. military catalog counts (generally 10 cm and larger), as SWF compiled them. SWF lists
Soviet-era tests under Russia; Orbit keeps the sheet's country names.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date

URL = ("https://docs.google.com/spreadsheets/d/1e5GtZEzdo6xk41i2_ei3c8jRZDjvP4Xwz3BVsUHwi48/"
       "export?format=csv&gid=0")
SHEET = "https://docs.google.com/spreadsheets/d/1e5GtZEzdo6xk41i2_ei3c8jRZDjvP4Xwz3BVsUHwi48/"
REPORT = "https://www.swfound.org/publications-and-reports/2026-global-counterspace-capabilities-report"
MIN_TESTS = 50  # a reading with fewer fails the lane, so a changed layout keeps the last good copy
DATA_COLS = 12
# The sheet's country names, mapped to ISO 3166-1 alpha-2 for the page's flags.
COUNTRY_ISO = {"Russia": "RU", "USA": "US", "United States": "US", "China": "CN", "India": "IN"}
DASHES = {"", "-", "--", "–", "—", "––", "n/a", "N/A"}
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MDY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})$")
_UPDATED = re.compile(r"Last\s+Updated\s+(\d{1,2})[-\s]([A-Za-z]{3})[A-Za-z]*[-\s](\d{4}|\d{2})\b", re.I)


def _year(y: str) -> int:
    """Two-digit years in the sheet run 1990s (90, 91, 94) and 2010s (14 to 23); anything past this year's two
    digits is read as the 1900s."""
    n = int(y)
    if len(y) == 4:
        return n
    return 2000 + n if n <= date.today().year % 100 else 1900 + n


def parse_date(text: str) -> str | None:
    """M/D/YYYY or M/D/YY to an ISO date; None for anything else (a span such as "Aug - Dec 2019")."""
    m = _MDY.match((text or "").replace(" ", ""))
    if not m:
        return None
    mo, d, y = m.groups()
    try:
        return date(_year(y), int(mo), int(d)).isoformat()
    except ValueError:
        return None


def _int(text: str) -> int | None:
    t = (text or "").strip().replace(",", "")
    return int(t) if t.isdigit() else None


def _float(text: str) -> float | None:
    t = (text or "").strip()
    try:
        return float(t)
    except ValueError:
        return None


def _hit(text: str) -> bool | None:
    t = (text or "").strip().lower()
    if t == "yes":
        return True
    if t == "no":
        return False
    return None  # a dash or blank: the sheet does not say


def _final(text: str) -> str | None:
    t = (text or "").strip()
    if t.lower().replace(" ", "") == "stillonorbit":
        return "on orbit"
    return parse_date(t)


def _text(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "")).strip()
    return "" if t in DASHES else t


def parse_updated(cells) -> str | None:
    for c in cells:
        m = _UPDATED.search(c or "")
        if m:
            d, mon, y = m.groups()
            mo = MONTHS.get(mon[:3].lower())
            if mo:
                try:
                    return date(_year(y), mo, int(d)).isoformat()
                except ValueError:
                    return None
    return None


def parse_asat(body: bytes | str) -> dict:
    """Return {"updated", "tests", "skipped"}. Each test row with a parsable date becomes one test; a row with a
    country but no single date (a span such as "Aug - Dec 2019") is skipped and listed in "skipped". Raises
    ValueError if the header is not where it was or fewer than MIN_TESTS tests parse."""
    text = body.decode("utf-8-sig") if isinstance(body, bytes) else body
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or len(rows[0]) < DATA_COLS:
        raise ValueError("not the SWF ASAT sheet: no header row")
    head = [re.sub(r"\s+", " ", h).strip().lower() for h in rows[0][:DATA_COLS]]
    if not (head[0] == "country" and head[1].startswith("date of test") and "interceptor" in head[3]
            and "debris" in head[7] and "still on orbit" in head[9]):
        raise ValueError(f"SWF ASAT sheet layout changed: header {head[:4]}...")
    updated = parse_updated(c for r in rows for c in r[DATA_COLS:])
    tests, skipped = [], []
    for r in rows[1:]:
        r = (r + [""] * DATA_COLS)[:DATA_COLS]  # side columns dropped here, before anything else
        country = _text(r[0])
        if not country:
            continue  # totals, blank rows and the grand total carry no country
        when = parse_date(r[1])
        interceptor = _text(r[3])
        if not when:
            skipped.append({"country": country, "date_text": _text(r[1]), "target": _text(r[2]),
                            "interceptor": interceptor, "debris_created": _int(r[7]),
                            "debris_on_orbit": _int(r[9])})
            continue
        tests.append({
            "country": country,
            "cc": COUNTRY_ISO.get(country),
            "date": when,
            "target": _text(r[2]),
            "interceptor": interceptor,
            "interceptor_type": _text(r[4]),
            "site": _text(r[5]),
            "hit": _hit(r[6]),
            "debris_created": _int(r[7]),
            "debris_reentered": _int(r[8]),
            "debris_on_orbit": _int(r[9]),
            "final_reentry": _final(r[10]),
            "lifespan_years": _float(r[11]),
        })
    if len(tests) < MIN_TESTS:
        raise ValueError(f"SWF ASAT sheet gave {len(tests)} tests (under {MIN_TESTS}); layout changed?")
    tests.sort(key=lambda t: t["date"], reverse=True)
    return {"updated": updated, "tests": tests, "skipped": skipped}


def key(t: dict) -> str:
    return f"{t['country']}|{t['date']}|{t['interceptor']}"


def by_country(tests: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for t in tests:
        c = out.setdefault(t["country"], {"cc": t.get("cc"), "tests": 0, "debris_created": 0, "debris_on_orbit": 0})
        c["tests"] += 1
        c["debris_created"] += t["debris_created"] or 0
        c["debris_on_orbit"] += t["debris_on_orbit"] or 0
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["tests"]))


def new_since(tests: list[dict], previous: list[dict] | None) -> list[dict]:
    """Tests whose (country, date, interceptor) was not in the previous reading. None (no previous reading)
    gives an empty list: the first reading only sets the baseline."""
    if previous is None:
        return []
    seen = {key(t) for t in previous}
    return [t for t in tests if key(t) not in seen]
