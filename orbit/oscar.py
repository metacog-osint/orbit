"""WMO OSCAR/Space for TIC's satellite catalog: the reader and the slug-to-NORAD link proposer (18 Nov 2026).

Design: D:/Projects/_ideas/sat-catalog-design-2026-11.md, sections 1, 2 and 9 (Tom's answer 8, 17 Nov 2026).

Terms (space.oscar.wmo.int/pages/disclaimer, read 16 and 17 Nov 2026): "All information available on these pages
may be used and redistributed freely", and "any publication using this information should acknowledge WMO";
"(c) World Meteorological Organization 2011-2026"; no warranty. Credit: CITATION.

The API (space.oscar.wmo.int/swagger/swagger.json, read 17 and 18 Nov 2026) has three list endpoints
(satellites, instruments, variables), 30 a page, with `page`, `sort`, `order`, `filterOn`, `filterValue`. A
satellite carries id, slug, acronym, fullname, WIGOS_Station_Identifier, space_agency, status, orbit,
launch_date, EoL, longitude, Altitude, ECT, description, link, data_access_link and its instruments. It carries no
NORAD number and no COSPAR ID, and no Wikidata item carries a WIGOS id, so OSCAR cannot be joined on an id.

Tom, 17 Nov 2026: a hand-reviewed slug-to-NORAD link file, each entry with its evidence, reviewed by diff; a script
may propose candidates (launch date and orbit); nothing joins until a person has reviewed the entry. The 414
operational satellites first, the inactive ones later. So this module:
  - reads the satellite list once (`read`), one page every few seconds, raw replies kept unchanged in
    data/raw/wmo-oscar/<stamp>/ (git-ignored);
  - proposes NORAD candidates for each OSCAR satellite from launch date and orbit only (`propose`); names are shown
    beside each candidate for the reviewer and never pick one;
  - the reviewed links live in orbit/data/catalog/oscar-links.yml (orbit/oscarlinks.py), not here.
"""
from __future__ import annotations

import gzip
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import catsources

SOURCE = "wmo-oscar-space"
API = "https://space.oscar.wmo.int/api/v1/satellites"
PAGE_URL = API + "?page={n}&sort=id&order=asc"
PAGE_URL_SITE = "https://space.oscar.wmo.int/satellites/view/{slug}"
CITATION = "WMO OSCAR/Space (space.oscar.wmo.int), courtesy of the World Meteorological Organization"
RAW = Path("raw") / "wmo-oscar"
PAUSE = 3.0  # seconds between page requests: 36 pages in about two minutes


# --- reading ---------------------------------------------------------------------------------------------------

def read(data_dir: Path, stamp: str, get=catsources.get, pause: float = PAUSE, sleep=time.sleep) -> Path:
    """Reads every page of the satellite list into data/raw/wmo-oscar/<stamp>/page-NN.json (the bytes as received).
    A page already in that folder is not asked again, so a stopped read resumes. Any answer but 200 raises
    catsources.Refused: stop and tell a person."""
    out = Path(data_dir) / RAW / stamp
    out.mkdir(parents=True, exist_ok=True)
    total, n, asked = None, 1, 0
    while total is None or n <= total:
        path = out / f"page-{n:02d}.json"
        if path.exists():
            body = path.read_bytes()
        else:
            if asked:
                sleep(pause)
            body = get(SOURCE, PAGE_URL.format(n=n), "application/json")
            asked += 1
            path.write_bytes(body)
        doc = json.loads(body)
        total = int(doc["page"]["totalPages"])
        n += 1
    return out


def load(raw_dir: Path) -> dict:
    """The satellites of one read, with the read's own counts checked: {read, satellites, total}. Raises ValueError
    when the pages do not add up to the total the API states (a list that changed while it was read)."""
    raw_dir = Path(raw_dir)
    pages = sorted(raw_dir.glob("page-*.json*"))
    if not pages:
        raise ValueError(f"no pages in {raw_dir}")
    sats, total, npages = [], None, None
    for p in pages:
        body = p.read_bytes()
        doc = json.loads(gzip.decompress(body) if p.name.endswith(".gz") else body)
        total = int(doc["page"]["totalElements"])
        npages = int(doc["page"]["totalPages"])
        sats.extend(doc["_embedded"]["satellites"])
    if len(pages) != npages:
        raise ValueError(f"{raw_dir}: {len(pages)} pages, the API states {npages}")
    slugs = [s["slug"] for s in sats]
    if len(set(slugs)) != total or len(slugs) != total:
        raise ValueError(f"{raw_dir}: {len(set(slugs))} distinct slugs in {len(slugs)} rows, the API states {total}")
    mtime = max(p.stat().st_mtime for p in pages)
    read_day = datetime.fromtimestamp(mtime, timezone.utc).date().isoformat()
    return {"read": read_day, "satellites": sats, "total": total}


# --- OSCAR's values ----------------------------------------------------------------------------------------------

def launch_day(s: dict) -> tuple[str | None, str]:
    """OSCAR's launch_date as (ISO date or None, precision): 'day', 'month', 'year' or 'none'."""
    t = (s.get("launch_date") or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return t, "day"
    for fmt, prec in (("%d %b %Y", "day"), ("%d %B %Y", "day"), ("%b %Y", "month"), ("%B %Y", "month"),
                      ("%Y-%m", "month"), ("%Y", "year")):
        try:
            d = datetime.strptime(t, fmt).date()
        except ValueError:
            continue
        return (d.isoformat() if prec == "day" else d.isoformat()[: 7 if prec == "month" else 4]), prec
    return None, "none"


def altitude_km(s: dict) -> float | None:
    """OSCAR's Altitude as km when it is one number ('817', '35786', '1.5e+06'); None for 'N/A', ranges and TBD."""
    t = str(s.get("Altitude") or "").replace(",", "").strip()
    m = re.fullmatch(r"(\d+(?:\.\d+)?(?:e\+?\d+)?)\s*(?:km)?", t, re.I)
    return float(m.group(1)) if m else None


def longitude_deg(s: dict) -> float | None:
    """OSCAR's longitude (GEO satellites) as signed degrees east, when given as a number or 'nn.n E/W'."""
    v = s.get("longitude")
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("\u00b0", "")
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*([EW])?", t, re.I)
    if not m:
        return None
    x = float(m.group(1))
    return -x if (m.group(2) or "").upper() == "W" else x


# OSCAR's orbit texts (all 1,062 satellites, 18 Nov 2026 read) and what each must look like in CelesTrak's SATCAT
# (APOGEE and PERIGEE are heights in km, INCLINATION degrees, ORBIT_CENTER EA = Earth, EL1 = Sun-Earth L1, SU = Sun,
# MO = Moon). The bounds are Orbit's, wide on purpose: they drop impossible candidates, they do not pick one.
ORBITS = {
    "Geostationary orbit": "geo",
    "Geosynchronous orbit": "gso",
    "Sunsynchronous orbit": "sso",
    "Drifting orbit": "drift",   # any Earth orbit that is not sun-synchronous: LAGEOS 5,900 km, Galileo 23,222 km
    "Molniya orbit": "heo",
    "Highly elliptical orbit": "heo",
    "Cross-magnetosphere orbit": "magneto",
    "Lagrange libration point 1": "l1",
    "Lagrange libration point 2": "l2",
    "Lunar orbit": "moon",
    "Solar orbit": "sun",
    "Ecliptic orbit": "sun",
}
# OSCAR gives one nominal height. Below 2,000 km a candidate fits when that height lies between its perigee less
# ALT_BELOW_KM and its apogee plus ALT_ABOVE_KM (payloads decay or are lowered after launch: SkySat 19-21, launched
# for 500 km, sit near 400 km); higher up, within ALT_SHARE of the height either side of perigee and apogee.
ALT_BELOW_KM, ALT_ABOVE_KM, ALT_SHARE = 200, 300, 0.10
DEEP_SPACE = {"l1": ("EL1", "SU"), "l2": ("EL2", "SU"), "moon": ("MO",), "sun": ("SU",)}  # CelesTrak gives SU
# for objects still on their way to L1 (IMAP, SWFO-L1, Carruthers on 16 Nov 2026)


def orbit_class(s: dict) -> str:
    """OSCAR's orbit text as a class of ORBITS ('other' for a text not seen in the 18 Nov 2026 read)."""
    return ORBITS.get((s.get("orbit") or "").strip(), "other")


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def orbit_fits(cls: str, alt: float | None, row: dict) -> tuple[bool | None, str]:
    """Whether a CelesTrak SATCAT row's orbit can be OSCAR's: (True, why), (False, why), or (None, why) when the
    row gives no orbit to compare."""
    centre = (row.get("ORBIT_CENTER") or "").strip()
    per, apo, inc = _f(row.get("PERIGEE")), _f(row.get("APOGEE")), _f(row.get("INCLINATION"))
    if cls in DEEP_SPACE:
        want = DEEP_SPACE[cls]
        return centre in want, f"CelesTrak orbit centre {centre or 'not given'} (OSCAR {cls}: {' or '.join(want)})"
    if centre and centre != "EA":
        return False, f"CelesTrak orbit centre {centre}, not Earth"
    if per is None or apo is None:
        return None, "CelesTrak gives no orbit for it"
    shape = f"{per:.0f} x {apo:.0f} km" + (f", {inc:.2f} deg" if inc is not None else "")
    if cls in ("geo", "gso"):
        ok = 34500 <= per <= 37000 and 34500 <= apo <= 37000 and (cls == "gso" or inc is None or inc <= 20)
        return ok, shape
    if cls == "heo":
        return apo > 20000 and per < 20000, shape
    if cls == "magneto":
        return apo > 10000, shape
    if cls in ("sso", "drift"):
        if cls == "sso" and (apo > 2500 or (inc is not None and not 95 <= inc <= 105)):
            return False, shape + " (not sun-synchronous)"
        if alt is not None:
            lo, hi = (per - ALT_BELOW_KM, apo + ALT_ABOVE_KM) if alt < 2000 else \
                (per - ALT_SHARE * alt, apo + ALT_SHARE * alt)
            if not lo <= alt <= hi:
                return False, shape + f" (OSCAR height {alt:.0f} km)"
        return True, shape
    return None, shape + f" (OSCAR orbit '{cls}' has no test)"


# Spellings that differ only by transliteration or abbreviation (design note section 4 names the same kind of
# pairs). Used for the evidence line "equal after normalising", never to choose a candidate.
SPELLINGS = (("elektro", "electro"), ("arktika", "arctica"), ("gaofen", "gf"), ("haiyang", "hy"),
             ("fengyun", "fy"), ("ziyuan", "zy"), ("kosmos", "cosmos"), ("shijian", "sj"))


def _norm(t: str) -> str:
    t = t.lower()
    t = re.sub(r"\bno\.?\s*(?=\d)", "", t)       # "KONDOR-FKA NO. 2" -> "kondor-fka 2"
    t = re.sub(r"\bn(?=\d)", "", t)              # "Electro-L N2" -> "electro-l 2"
    for a, b in SPELLINGS:
        t = re.sub(rf"\b{a}", b, t)
    t = re.sub(r"[^a-z0-9]", " ", t)
    t = re.sub(r"(?<![0-9])0+(?=[0-9])", "", t)  # "EOS-04" -> "eos 4"
    return t.replace(" ", "")


def name_parts(name: str) -> set[str]:
    """A catalog name and its bracketed parts, normalised: 'NOAA 20 (JPSS-1)' -> {'noaa20jpss1', 'noaa20', 'jpss1'}."""
    out = {_norm(name)}
    for part in re.split(r"[()\[\]]", name):
        if part.strip():
            out.add(_norm(part))
    return {p for p in out if p}


def name_agrees(s: dict, names: list[str]) -> str | None:
    """The first catalog name whose normalised form equals OSCAR's acronym or full name (shown to the reviewer as
    evidence; never used to choose)."""
    want = {_norm(s.get("acronym") or ""), _norm(s.get("fullname") or "")} - {""}
    for n in names:
        if name_parts(n) & want:
            return n
    return None


# --- proposing links ---------------------------------------------------------------------------------------------

def _day(t: str) -> date | None:
    try:
        return date.fromisoformat((t or "")[:10])
    except ValueError:
        return None


def propose(sats: list[dict], satcat: list[dict], names_index: dict | None = None,
            statuses: tuple[str, ...] = ("Operational",)) -> list[dict]:
    """NORAD candidates for each OSCAR satellite with one of `statuses`, from launch date and orbit only.

    Candidates are CelesTrak SATCAT payloads launched within a day of OSCAR's launch date (in the same month when
    OSCAR gives only a month) whose orbit fits OSCAR's (orbit_fits). Every candidate carries its names (CelesTrak's
    and, given the TIC name index, every source's) and whether one equals OSCAR's acronym or full name. Outcome:
    'one' (a single candidate fits), 'several', or 'none'. Nothing here joins anything: each proposal is for a
    person to review into orbit/data/catalog/oscar-links.yml."""
    by_day: dict[date, list[dict]] = {}
    for r in satcat:
        if (r.get("OBJECT_TYPE") or "").strip() != "PAY":
            continue
        d = _day(r.get("LAUNCH_DATE"))
        if d:
            by_day.setdefault(d, []).append(r)
    idx = {}
    if names_index:
        for row in names_index["objects"]:
            if row[1] is not None:
                idx[str(row[1])] = row
    out = []
    for s in sats:
        if s.get("status") not in statuses:
            continue
        ld, prec = launch_day(s)
        cls, alt = orbit_class(s), altitude_km(s)
        pool: list[tuple[dict, int | None]] = []
        if prec == "day":
            d0 = date.fromisoformat(ld)
            for off in (-1, 0, 1):
                pool += [(r, off) for r in by_day.get(d0.fromordinal(d0.toordinal() + off), [])]
        elif prec == "month":
            pool = [(r, None) for d, rows in by_day.items() if d.isoformat()[:7] == ld for r in rows]
        cands, dropped, ruled_out = [], 0, []
        for r, off in pool:
            fits, shape = orbit_fits(cls, alt, r)
            if fits is False:
                dropped += 1
                if len(ruled_out) < 12:
                    ruled_out.append({"norad": int(r["NORAD_CAT_ID"]), "name": r["OBJECT_NAME"].strip(),
                                      "orbit": shape})
                continue
            norad = str(int(r["NORAD_CAT_ID"]))
            names = [r["OBJECT_NAME"].strip()]
            ix = idx.get(norad)
            if ix:
                names += [n for n in ix[7] if n not in names]
            cands.append({
                "norad": int(norad), "intldes": r.get("OBJECT_ID"), "name": r["OBJECT_NAME"].strip(),
                "names": names, "launch_date": r.get("LAUNCH_DATE"), "days_off": off,
                "index_launch_date": ix[4] if ix else None, "decayed": bool((r.get("DECAY_DATE") or "").strip()),
                "ops_status": (r.get("OPS_STATUS_CODE") or "").strip(), "owner": (r.get("OWNER") or "").strip(),
                "orbit": shape, "orbit_checked": fits is True, "name_agrees": name_agrees(s, names),
            })
        cands.sort(key=lambda c: (c["name_agrees"] is None, abs(c["days_off"] or 0), c["norad"]))
        out.append({
            "slug": s["slug"], "oscar_id": s.get("id"), "acronym": s.get("acronym"), "fullname": s.get("fullname"),
            "status": s.get("status"), "agency": s.get("space_agency"), "orbit": s.get("orbit"),
            "orbit_class": cls, "altitude_km": alt, "longitude": longitude_deg(s),
            "launch_date": s.get("launch_date"), "launch": ld, "launch_precision": prec,
            "payloads_in_window": len(pool), "dropped_by_orbit": dropped, "candidates": cands,
            "ruled_out": ruled_out,
            "outcome": "none" if not cands else "one" if len(cands) == 1 else "several",
        })
    return out


def evidence(p: dict, c: dict) -> list[str]:
    """The evidence lines for a link entry from one proposal and its chosen candidate."""
    lines = []
    when = {0: "the same day", -1: "a day earlier", 1: "a day later", None: "in the same month"}[c["days_off"]]
    lines.append(f"OSCAR launch date {p['launch_date']}; CelesTrak launches {c['intldes']} on {c['launch_date']}, "
                 f"{when}" + (f" (TIC name index: {c['index_launch_date']})"
                              if c.get("index_launch_date") and c["index_launch_date"] != c["launch_date"] else ""))
    alt = f", {p['altitude_km']:.0f} km" if p.get("altitude_km") and p["altitude_km"] < 1e5 else ""
    lon = f", {p['longitude']:g} deg E" if p.get("longitude") is not None else ""
    shape = c["orbit"].replace("CelesTrak orbit centre", "orbit centre")
    lines.append(f"OSCAR orbit {p['orbit']}{alt}{lon}; CelesTrak {shape}"
                 + ("" if c["orbit_checked"] else " (orbit not compared)"))
    n = len(p["candidates"])
    agree = sum(1 for x in p["candidates"] if x["name_agrees"])
    lines.append(f"Payloads launched in the date window: {p['payloads_in_window']}; ruled out by orbit: "
                 f"{p['dropped_by_orbit']}; left: {n}"
                 + ("" if n == 1 else f"; names equal to OSCAR's: {agree}"))
    lines.append(f"Names: OSCAR '{p['acronym']}' ({p['fullname']}); catalog " +
                 ", ".join(f"'{x}'" for x in c["names"][:4]) +
                 (f"; equal after normalising: '{c['name_agrees']}'" if c["name_agrees"] else "; none equal"))
    return lines


# --- the weekly read for the catalog build (join step, 20 Nov 2026) -----------------------------------------------

STORE = Path("state") / "wmo-oscar-satellites.json.gz"  # the last read, slimmed (Actions cache, own cache entry)
DAYS = 7           # one full read (36 pages, 3 s apart, about two minutes) a week
MIN_SATS = 900     # 1,062 satellites on 18 Nov 2026; a shorter list is refused and the last read kept
KEEP = ("id", "slug", "acronym", "fullname", "space_agency", "status", "orbit", "launch_date")


def due(now: datetime, st: dict) -> str | None:
    """Why OSCAR must not be asked now (None when it may be): on hold, or read within the week."""
    why = catsources.held(st, now)
    if why:
        return why
    last = catsources._t(st.get("read_at"))
    if last and now - last < timedelta(days=DAYS) - timedelta(hours=6):
        return f"read {st['read_at']}; once a week"
    return None


def pull(data_dir: Path, now: datetime, state: dict, get=catsources.get, pause: float = PAUSE,
         sleep=time.sleep) -> dict:
    """The weekly read: every page once into data/raw/wmo-oscar/<stamp>/, the satellites (fields in KEEP, no
    instruments) into the store. Any answer but 200 puts the source on hold and is returned as `refused`. With the
    store gone (the Actions cache can be evicted) it reads again rather than build without OSCAR."""
    data_dir = Path(data_dir)
    st = state.setdefault(SOURCE, {})
    why = due(now, st) if (data_dir / STORE).exists() else catsources.held(st, now)
    if why:
        return {"read": False, "why": why}
    stamp = now.strftime("%Y%m%dT%H%MZ")
    try:
        out = read(data_dir, stamp, get=get, pause=pause, sleep=sleep)
    except catsources.Refused as exc:
        catsources.hold(st, exc, now)
        return {"read": False, "why": str(exc), "refused": exc.code}
    try:
        r = load(out)
    except ValueError as exc:
        return {"read": False, "why": f"{exc}; kept the last read"}
    if r["total"] < MIN_SATS:
        return {"read": False, "why": f"list has {r['total']} satellites (1,062 on 18 Nov 2026); kept the last read"}
    sats = [{k: s.get(k) for k in KEEP} for s in r["satellites"]]
    catsources.write_json(data_dir / STORE, {"satellites": sats})
    st.update({"read_at": catsources._iso(now), "satellites": r["total"]})
    st.pop("hold", None)
    return {"read": True, "rows": r["total"], "requests": len(list(out.glob("page-*.json")))}


def store_load(data_dir: Path, state: dict) -> dict | None:
    """The last read as {satellites, read, read_at}, or None (no request)."""
    st = state.get(SOURCE) or {}
    doc = catsources.read_json(Path(data_dir) / STORE, None)
    if doc is None or not st.get("read_at"):
        return None
    return {"satellites": doc["satellites"], "read": st["read_at"][:10], "read_at": st["read_at"]}


# OSCAR's status texts as the active / inactive split catalog.disagreements compares; the rest are kept, not compared.
STATUS_CLASS = {"Operational": "active", "Inactive": "inactive", "Presumably inactive": "inactive"}
