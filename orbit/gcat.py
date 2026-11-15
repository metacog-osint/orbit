"""GCAT (Jonathan McDowell, planet4589.org/space/gcat, CC BY 4.0): parse, diff, launches, reentries, hygiene.

Orbit reads six GCAT tables:
  cat/satcat.tsv     objects from the US catalog, numbers 1-69999
  cat/satcat100k.tsv objects from the US catalog, numbers 100000-269999 (where new objects land now)
  cat/auxcat.tsv     objects GCAT tracks that the US catalog does not
  cat/tmpcat.tsv     objects GCAT tracks under a temporary id until they are cataloged
  launch/launch.tsv every launch, orbital and not
  tables/sites.tsv  launch sites with coordinates

What Orbit reports from them is measured, never judged:
  - orbital launches in the last 30 days (kept; the feed shows the last 7);
  - reentries GCAT has dated in the last 30 days;
  - catalog changes between two of Orbit's own readings (new, removed and changed entries);
  - owner-code hygiene counts (Soviet SU kept apart from Russian RU; objects with no catalog number;
    catalog numbers claimed by two entries).
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

BASE = "https://planet4589.org/space/gcat/tsv"
URLS = {
    "satcat": f"{BASE}/cat/satcat.tsv",
    "satcat100k": f"{BASE}/cat/satcat100k.tsv",
    "auxcat": f"{BASE}/cat/auxcat.tsv",
    "tmpcat": f"{BASE}/cat/tmpcat.tsv",
    "launch": f"{BASE}/launch/launch.tsv",
    "sites": f"{BASE}/tables/sites.tsv",
    "orgs": f"{BASE}/tables/orgs.tsv",
}
CITATION = "Data from GCAT (J. McDowell, planet4589.org/space/gcat), CC BY 4.0"

# GCAT state codes that are not ISO 3166-1 alpha-2 (read against GCAT's orgs.tsv on 13 Nov 2026).
# Intergovernmental owners (I-ESA, I-INT, I-NATO and the rest) and X (unknown) have no country.
STATE_ISO = {
    "F": "FR", "J": "JP", "UK": "GB", "D": "DE", "I": "IT", "L": "LU", "E": "ES", "N": "NO", "S": "SE",
    "T": "TH", "B": "BE", "P": "PT", "UAE": "AE", "SU": "RU", "BGN": "BG", "HKUK": "HK", "CSSR": "CZ",
    "CSFR": "CZ", "CYM": "KY", "MYM": "MM", "ESIB": "ES",
}
NO_COUNTRY = {"X", "-", ""}

TYPE_NAMES = {"P": "payload", "R": "rocket stage", "C": "component", "D": "debris", "Z": "other"}
# GCAT Status codes for an object no longer in orbit around Earth (GCAT object catalog column notes).
GONE = {"R", "D", "L", "AR", "E", "R?", "L?"}
ORBITAL_CODES = ("O", "D", "N")  # LaunchCode first letter: orbital, deep space, near-orbital
MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}
VAGUE_RE = re.compile(r"^(\d{4})(?:\s+([A-Z][a-z]{2}))?(?:\s+(\d{1,2}))?(?:\s+(\d{2})(\d{2})(?::(\d{2}))?)?")


def iso_country(state: str) -> str | None:
    """GCAT state code to ISO 3166-1 alpha-2, or None for intergovernmental and unknown owners."""
    s = (state or "").strip()
    if s in NO_COUNTRY or s.startswith("I-"):
        return None
    if s in STATE_ISO:
        return STATE_ISO[s]
    return s if len(s) == 2 and s.isalpha() else None


def vague_date(text: str) -> dict:
    """GCAT 'vague date' ('2026 Nov 12 0436:30', '2026 Nov  4?', '1957 Nov?') to parts.

    Returns {"date": 'YYYY-MM-DD' or None, "time": 'YYYY-MM-DDTHH:MM:SSZ' or None, "uncertain": bool}."""
    t = (text or "").strip()
    out = {"date": None, "time": None, "uncertain": "?" in t}
    m = VAGUE_RE.match(t.replace("?", ""))
    if not m or not m.group(2) or not m.group(3):
        return out
    y, mon, d = int(m.group(1)), MONTHS.get(m.group(2)), int(m.group(3))
    if not mon:
        return out
    try:
        day = date(y, mon, d)
    except ValueError:
        return out
    out["date"] = day.isoformat()
    if m.group(4):
        hh, mm, ss = int(m.group(4)), int(m.group(5)), int(m.group(6) or 0)
        if hh < 24 and mm < 60 and ss < 60:
            out["time"] = f"{day.isoformat()}T{hh:02d}:{mm:02d}:{ss:02d}Z"
    return out


def parse_tsv(body: bytes) -> list[dict]:
    """A GCAT TSV table: the header is the first line, starting '#'; other '#' lines are comments."""
    text = body.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if not lines or not lines[0].startswith("#"):
        raise ValueError("not a GCAT table: no '#' header line")
    hdr = lines[0].lstrip("#").split("\t")
    rows = []
    for line in lines[1:]:
        if not line or line.startswith("#"):
            continue
        cells = [c.strip() for c in line.split("\t")]
        rows.append(dict(zip(hdr, cells)))
    return rows


def updated_stamp(body: bytes) -> str | None:
    """The '# Updated 2026 Nov 13 0021:52' line GCAT writes under the header."""
    for line in body[:2000].decode("utf-8", errors="replace").splitlines()[1:3]:
        if line.startswith("# Updated"):
            return line[len("# Updated"):].strip()
    return None


def _num(text: str) -> str | None:
    t = (text or "").strip()
    return t if t.isdigit() else None


CATALOGS = ("satcat", "satcat100k", "auxcat", "tmpcat")
US_CATALOGS = ("satcat", "satcat100k")


def objects(tables: dict[str, list[dict]]) -> list[dict]:
    """One compact record per GCAT object, from every catalog in CATALOGS."""
    out = []
    for cat in CATALOGS:
        rows = tables.get(cat) or []
        for r in rows:
            jcat = r.get("JCAT", "").strip()
            if not jcat:
                continue
            out.append({
                "jcat": jcat,
                "cat": cat,
                "norad": _num(r.get("Satcat", "")),
                "launch_tag": r.get("Launch_Tag", ""),
                "type": (r.get("Type") or "Z")[:1],
                "name": r.get("Name", ""),
                "ldate": r.get("LDate", ""),
                "parent": r.get("Parent", ""),
                "ddate": r.get("DDate", ""),
                "status": r.get("Status", ""),
                "owner": r.get("Owner", ""),
                "state": r.get("State", ""),
                "op_orbit": r.get("OpOrbit", ""),
            })
    return out


# --- the catalog index Orbit keeps between runs -------------------------------------------------------------

INDEX_FIELDS = ("cat", "norad", "launch_tag", "type", "name", "ldate", "parent", "ddate", "status", "owner",
                "state", "op_orbit")


def build_index(objs: list[dict]) -> dict[str, list]:
    return {o["jcat"]: [o[k] for k in INDEX_FIELDS] for o in objs}


def _from_index(jcat: str, row: list) -> dict:
    return {"jcat": jcat, **dict(zip(INDEX_FIELDS, row))}


def _brief(o: dict) -> dict:
    return {"jcat": o["jcat"], "norad": o["norad"], "name": o["name"], "type": TYPE_NAMES.get(o["type"], o["type"]),
            "launch_tag": o["launch_tag"], "launch_date": vague_date(o["ldate"])["date"], "parent": o["parent"],
            "state": o["state"], "country": iso_country(o["state"]), "owner": o["owner"], "status": o["status"],
            "op_orbit": o["op_orbit"]}


def diff(prev_index: dict[str, list], objs: list[dict], today: date, late_days: int = 30) -> dict:
    """Changes between Orbit's previous reading and this one.

    'Late' new objects come from a launch more than late_days old: a payload released from a host, a
    fragmentation, or an object GCAT has only now identified. Orbit reports which, by type and parent,
    and does not say why."""
    cur = {o["jcat"]: o for o in objs}
    added = [cur[j] for j in cur.keys() - prev_index.keys()]
    removed = [_from_index(j, prev_index[j]) for j in prev_index.keys() - cur.keys()]
    # A temporary (tmpcat) entry leaves when the object is cataloged under a new id: not a deletion.
    graduated = [o for o in removed if o["cat"] == "tmpcat"]
    removed = [o for o in removed if o["cat"] != "tmpcat"]
    changed = []
    for j in cur.keys() & prev_index.keys():
        old = _from_index(j, prev_index[j])
        new = cur[j]
        fields = [k for k in ("norad", "status", "state", "owner", "ddate", "name") if (old.get(k) or "") != (new.get(k) or "")]
        if fields:
            changed.append({"jcat": j, "name": new["name"], "fields": {k: [old.get(k), new.get(k)] for k in fields},
                            "type": TYPE_NAMES.get(new["type"], new["type"]), "state": new["state"],
                            "country": iso_country(new["state"]), "launch_tag": new["launch_tag"]})

    cutoff = today - timedelta(days=late_days)
    late, fresh = [], []
    for o in added:
        ld = vague_date(o["ldate"])["date"]
        (late if ld and date.fromisoformat(ld) < cutoff else fresh).append(o)

    late_groups = defaultdict(list)
    for o in late:
        late_groups[o["launch_tag"]].append(o)
    late_out = []
    for tag, group in sorted(late_groups.items()):
        types = Counter(TYPE_NAMES.get(o["type"], o["type"]) for o in group)
        parents = Counter(o["parent"] for o in group if o["parent"] and o["parent"] != "-")
        late_out.append({
            "launch_tag": tag,
            "launch_date": vague_date(group[0]["ldate"])["date"],
            "count": len(group),
            "by_type": dict(types),
            "parents": dict(parents.most_common(5)),
            "states": sorted({o["state"] for o in group}),
            "countries": sorted({c for c in (iso_country(o["state"]) for o in group) if c}),
            "objects": [_brief(o) for o in sorted(group, key=lambda o: o["jcat"])][:50],
        })
    late_out.sort(key=lambda g: (-g["count"], g["launch_tag"]))

    owner_changes = [c for c in changed if "state" in c["fields"] or "owner" in c["fields"]]
    numbered = [c for c in changed if "norad" in c["fields"] and not c["fields"]["norad"][0] and c["fields"]["norad"][1]]
    status_moves = Counter(f"{c['fields']['status'][0]} -> {c['fields']['status'][1]}" for c in changed
                           if "status" in c["fields"])
    return {
        "added": len(added),
        "added_fresh": len(fresh),
        "added_late": len(late),
        "late_groups": late_out,
        "removed": len(removed),
        "temporary_entries_closed": len(graduated),
        "removed_objects": [_brief(o) for o in sorted(removed, key=lambda o: o["jcat"])][:50],
        "changed": len(changed),
        "status_moves": dict(status_moves.most_common()),
        "owner_changes": owner_changes[:50],
        "newly_numbered": len(numbered),
        "newly_numbered_objects": numbered[:50],
    }


# --- launches and reentries ---------------------------------------------------------------------------------

def sites_table(rows: list[dict]) -> dict[str, dict]:
    """Launch site code -> {name, lat, lon, state}. Where a code has several rows, the current one wins."""
    out = {}
    for r in rows:
        code = r.get("Site", "")
        try:
            lon, lat = float(r.get("Longitude", "")), float(r.get("Latitude", ""))
        except ValueError:
            continue
        current = r.get("TStop", "") in ("*", "-", "")
        if code not in out or current:
            out[code] = {"name": r.get("ShortName") or r.get("Name") or code, "full_name": r.get("Name", ""),
                         "lat": lat, "lon": lon, "state": r.get("StateCode", ""),
                         "country": iso_country(r.get("StateCode", ""))}
    return out


def orgs_table(rows: list[dict]) -> dict[str, dict]:
    """GCAT organisation code -> {name, state}. Where a code has several rows, the current one wins."""
    out = {}
    for r in rows:
        code = (r.get("Code") or "").strip()
        if not code:
            continue
        current = r.get("TStop", "") in ("*", "-", "")
        if code not in out or current:
            out[code] = {"name": r.get("ShortName") or r.get("Name") or code, "state": r.get("StateCode", "")}
    return out


def launchers(agency: str, orgs: dict) -> list[dict]:
    """The launch agencies GCAT names for a launch ('ZHSH/CALT' is two), each with its GCAT state and ISO country."""
    out = []
    for code in (agency or "").split("/"):
        code = code.strip()
        if not code or code == "-":
            continue
        org = orgs.get(code) or {}
        state = org.get("state", "")
        out.append({"code": code, "name": org.get("name", code), "state": state, "country": iso_country(state)})
    return out


def recent_launches(launch_rows: list[dict], objs: list[dict], sites: dict, today: date, days: int = 30,
                    orgs: dict | None = None) -> list[dict]:
    """Orbital, deep-space and near-orbital launches GCAT dates within the last `days` days, newest first."""
    payloads = defaultdict(list)
    for o in objs:
        if o["type"] == "P":
            payloads[o["launch_tag"]].append(o)
    since = today - timedelta(days=days)
    out = []
    for r in launch_rows:
        code = r.get("LaunchCode", "")
        if not code or code[0] not in ORBITAL_CODES:
            continue
        when = vague_date(r.get("Launch_Date", ""))
        if not when["date"] or not (since <= date.fromisoformat(when["date"]) <= today):
            continue
        tag = r.get("Launch_Tag", "")
        site = sites.get(r.get("Launch_Site", ""))
        pls = sorted(payloads.get(tag, []), key=lambda o: o["jcat"])
        outcome = {"S": "success", "F": "failure", "U": "unknown", "E": "pad explosion"}.get(code[1:2], code[1:])
        out.append({
            "launch_tag": tag,
            "date": when["date"],
            "time": when["time"],
            "time_uncertain": when["uncertain"],
            "vehicle": r.get("LV_Type", ""),
            "variant": r.get("Variant", "") if r.get("Variant", "") != "-" else "",
            "flight": r.get("Flight", "") if r.get("Flight", "") != "-" else "",
            "mission": r.get("Mission", "") if r.get("Mission", "") != "-" else "",
            "agency": r.get("Agency", ""),
            "launchers": launchers(r.get("Agency", ""), orgs or {}),
            "category": r.get("Category", ""),
            "kind": {"O": "orbital", "D": "deep space", "N": "near-orbital"}[code[0]],
            "outcome": outcome,
            "site_code": r.get("Launch_Site", ""),
            "pad": r.get("Launch_Pad", "") if r.get("Launch_Pad", "") != "-" else "",
            "site": site,
            "payloads_cataloged": len(pls),
            "payloads": [{"jcat": o["jcat"], "norad": o["norad"], "name": o["name"], "state": o["state"],
                          "country": iso_country(o["state"]), "owner": o["owner"], "op_orbit": o["op_orbit"]}
                         for o in pls][:40],
            "payload_states": sorted({o["state"] for o in pls}),
        })
    out.sort(key=lambda x: (x["time"] or x["date"], x["launch_tag"]), reverse=True)
    return out


def recent_reentries(objs: list[dict], today: date, days: int = 30) -> list[dict]:
    """Objects whose GCAT decay date (DDate) falls within the last `days` days and that are no longer in orbit."""
    since = today - timedelta(days=days)
    out = []
    for o in objs:
        if o["status"] not in GONE:
            continue
        d = vague_date(o["ddate"])
        if d["date"] and since <= date.fromisoformat(d["date"]) <= today:
            out.append({**_brief(o), "reentry_date": d["date"], "reentry_time": d["time"],
                        "reentry_uncertain": d["uncertain"]})
    out.sort(key=lambda x: (x["reentry_date"], x["jcat"]), reverse=True)
    return out


def hygiene(objs: list[dict]) -> dict:
    """Owner-code hygiene and catalog-number counts across satcat and auxcat."""
    sat = [o for o in objs if o["cat"] in US_CATALOGS]
    in_orbit = [o for o in objs if o["status"] in ("O", "OX", "AO")]
    by_state_all = Counter(o["state"] for o in sat)
    by_state_orbit = Counter(o["state"] for o in in_orbit)
    payloads_orbit = Counter(o["state"] for o in in_orbit if o["type"] == "P")
    unnumbered_in_orbit = [o for o in in_orbit if not o["norad"]]
    norad_claims = defaultdict(list)
    for o in sat:  # auxcat repeats the number of the object a piece is associated with, so it is left out
        if o["norad"]:
            norad_claims[o["norad"]].append(o["jcat"])
    dupes = {n: j for n, j in sorted(norad_claims.items()) if len(j) > 1}
    return {
        "objects_by_catalog": dict(Counter(o["cat"] for o in objs)),
        "soviet_su": by_state_all.get("SU", 0),
        "russian_ru": by_state_all.get("RU", 0),
        "in_orbit": len(in_orbit),
        "in_orbit_by_state": dict(by_state_orbit.most_common(15)),
        "in_orbit_owners": [{"state": st, "country": iso_country(st), "total": n, "payloads": payloads_orbit.get(st, 0)}
                            for st, n in by_state_orbit.most_common(20)],
        "in_orbit_soviet_su": by_state_orbit.get("SU", 0),
        "in_orbit_russian_ru": by_state_orbit.get("RU", 0),
        "unnumbered_in_orbit": len(unnumbered_in_orbit),
        "unnumbered_in_orbit_by_state": dict(Counter(o["state"] for o in unnumbered_in_orbit).most_common(10)),
        "duplicate_catalog_numbers": dupes,
    }


# --- baselines from GCAT's own history (orbit-2.8; Tom, 15 Nov 2026, decision 8) ----------------------------

BASE_WINDOW_DAYS = 30   # the recent window
BASE_PRIOR_WINDOWS = 24  # the 24 windows of 30 days before it: about two years
BASE_TOP_OPERATORS = 25


def _windows(today: date, window: int = BASE_WINDOW_DAYS, prior: int = BASE_PRIOR_WINDOWS) -> list[tuple[date, date]]:
    """[(start, end)], both ends included: index 0 is the recent window ending today, 1..prior the ones before."""
    return [(today - timedelta(days=window * (k + 1) - 1), today - timedelta(days=window * k)) for k in range(prior + 1)]


def _series(dated: list[tuple[str, str]], wins: list[tuple[date, date]]) -> dict[str, list[int]]:
    """Counts per key and window from (key, ISO date) pairs."""
    first, last = wins[-1][0], wins[0][1]
    out: dict[str, list[int]] = defaultdict(lambda: [0] * len(wins))
    span = BASE_WINDOW_DAYS
    for key, d in dated:
        day = date.fromisoformat(d)
        if not (first <= day <= last):
            continue
        out[key][(last - day).days // span] += 1
    return out


def _position(recent: int, prior: list[int]) -> dict:
    """The recent window against the prior windows: their median and range, and where the recent count sits.
    'above' and 'below' mean outside every prior window, not a threshold of Orbit's choosing."""
    srt = sorted(prior)
    mid = len(srt) // 2
    med = srt[mid] if len(srt) % 2 else (srt[mid - 1] + srt[mid]) / 2
    pos = "above" if recent > srt[-1] else "below" if recent < srt[0] else "within"
    return {"recent": recent, "prior_median": med, "prior_min": srt[0], "prior_max": srt[-1],
            "prior_windows": len(prior), "windows_at_or_above": sum(1 for x in prior if x >= recent), "position": pos}


def _rows(series: dict[str, list[int]], label) -> list[dict]:
    rows = []
    for key, counts in series.items():
        rows.append({**label(key), **_position(counts[0], counts[1:]), "series": counts[::-1]})  # oldest first
    rows.sort(key=lambda r: (-(r["recent"] + sum(r["series"][:-1]) / max(len(r["series"]) - 1, 1)), str(r.get("key"))))
    return rows


def baseline(launch_rows: list[dict], objs: list[dict], orgs: dict, today: date) -> dict:
    """Launch cadence per launching country and per launch agency, payloads launched per owner and reentries per
    owner: the last 30 days against each of the 24 windows of 30 days before them, from GCAT's own history.
    GCAT dates the last few days as it learns of them, so the newest window can grow after a reading."""
    wins = _windows(today)
    by_country, by_agency, all_launches = [], [], []
    for r in launch_rows:
        code = r.get("LaunchCode", "")
        if not code or code[0] not in ORBITAL_CODES:
            continue
        d = vague_date(r.get("Launch_Date", ""))["date"]
        if not d:
            continue
        all_launches.append(("all", d))
        ls = launchers(r.get("Agency", ""), orgs)
        for c in sorted({l["country"] or l["state"] or "?" for l in ls} or {"?"}):
            by_country.append((c, d))
        for l in ls:
            by_agency.append((l["code"], d))
    names = {l: (orgs.get(l) or {}) for l, _ in by_agency}
    payloads, reentries = [], []
    for o in objs:
        st = o["state"] or "?"
        if o["type"] == "P":
            d = vague_date(o["ldate"])["date"]
            if d:
                payloads.append((st, d))
        if o["status"] in GONE:
            d = vague_date(o["ddate"])["date"]
            if d:
                reentries.append((st, d))
    country = lambda c: {"key": c, "country": c if len(c) == 2 and c.isalpha() and c.isupper() else None}
    owner = lambda st: {"key": st, "state": st, "country": iso_country(st)}
    agency = lambda a: {"key": a, "agency": a, "name": names.get(a, {}).get("name", a),
                        "state": names.get(a, {}).get("state", ""), "country": iso_country(names.get(a, {}).get("state", ""))}
    ag = _rows(_series(by_agency, wins), agency)
    ag = [r for i, r in enumerate(ag) if i < BASE_TOP_OPERATORS or r["recent"]]
    total = lambda pairs: _rows(_series([("all", d) for _, d in pairs], wins), lambda k: {"key": k})
    return {
        "window_days": BASE_WINDOW_DAYS, "prior_windows": BASE_PRIOR_WINDOWS,
        "recent": [wins[0][0].isoformat(), wins[0][1].isoformat()],
        "prior": [wins[-1][0].isoformat(), wins[1][1].isoformat()],
        "launches_all": total(all_launches),
        "launches_by_country": _rows(_series(by_country, wins), country),
        "launches_by_agency": ag,
        "payloads_by_owner": _rows(_series(payloads, wins), owner)[:30],
        "reentries_all": total(reentries),
        "reentries_by_owner": _rows(_series(reentries, wins), owner)[:20],
    }


def today_utc() -> date:
    return datetime.now(timezone.utc).date()
