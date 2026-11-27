"""ITU filings as GEO slot evidence (method `orbit-2.42`, doctrine/itu-filings.md).

What an ITU filing is, and is not:
- A satellite network filing is an administration's request to the ITU for orbit position and spectrum. Its name
  (`sat_name` in ITU's tables, "EUTELSAT 3-12.5W", "F-SAT-N3-12.5W") is the administration's label for the
  filing, not the name of a satellite, and one satellite may serve several filings, at different slots over time.
- A filing for a slot is not evidence that a satellite is, or ever was, at that slot. Brought-into-use dates in the
  Master Register and Resolution 40 statements are the administration's own declarations to the ITU that a space
  station was in position; Orbit quotes them as such.
- No ITU table gives a NORAD number. A filing reaches an object page only through a hand-reviewed entry in
  `orbit/data/catalog/itu-links.yml`, and that link is TIC's attribution, never the ITU's.

Sources (ITU Space Explorer's public calls, no login; read by hand 27 Nov 2026):
- notices by nominal longitude: POST {BASE}/queries with the "orbital arc" filter Space Explorer's own list sends;
- the Resolution 40 table: GET RES40_URL.
Terms (itu.int terms of use): download, copy and use "for personal, educational, or non-commercial purposes" with
the source acknowledged; no reproduction or distribution without ITU's written permission. So these calls run
only on a person's request (`orbit.py find <slot> --itu`), never in a schedule; replies stay in git-ignored
`data/raw/itu/`; Orbit publishes no ITU table, only reviewed per-object links with a link to ITU's own page.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .aliases import AliasError, _check_date, parse

BASE = "https://www.itu.int/itu-r/space/apps/ep/spaceexplorer/v1"
QUERIES_URL = f"{BASE}/queries"
RES40_URL = "https://www.itu.int/net/ITU-R/space/res40/res40_webtable.json"
APP = "https://www.itu.int/itu-r/space/apps/public/spaceexplorer"
UA = "Mozilla/5.0 (compatible; TIC-Orbit/1.0; +https://github.com/metacog-osint/orbit)"
GAP_S = 3.0          # seconds between two requests to ITU
MAX_AGE_DAYS = 7     # a cached reply is reused this long
TAKE = 200           # Space Explorer's page size
WINDOW_DEG = 0.1     # default: filings whose nominal longitude is within this of the slot (station-keeping is
                     # usually +/-0.1 deg, and filings give the slot to 0.1 deg or better)
MAX_PAGES = 10
CREDIT = ("ITU Space Explorer and the ITU-R Resolution 40 table, (c) ITU, used for non-commercial research with "
          "the source acknowledged (itu.int terms of use)")
LINKS_PATH = Path(__file__).resolve().parent / "data" / "catalog" / "itu-links.yml"

NETWORK_NOTE = ("A network name is the administration's label for a filing, not a satellite's name; a filing for "
                "a slot is a claim to orbit position and spectrum, not evidence that a satellite is or was there.")
RES40_NOTE = ("Resolution 40: the administration's statement to the ITU that a space station was in position for "
              "the filing from that date, and whether the station came from another filing's slot. ITU names no "
              "satellite and no NORAD number.")


def iso(d: str | None) -> str | None:
    """ITU's dd.mm.yyyy as yyyy-mm-dd; anything else as given (None stays None)."""
    if not d:
        return None
    m = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", d.strip())
    return f"{m[3]}-{m[2]}-{m[1]}" if m else d.strip()


def provision(prov: str | None, plan: str | None = None) -> str:
    """A short gloss of the Radio Regulations provision a notice was filed under, with ITU's code kept. A notice
    with no provision is an entry of a plan (`plan`, ITU's "Plan (AP30B)" text) when one is given."""
    p = (prov or "").strip()
    u = p.upper()
    if not p:
        return f"{plan} entry" if plan and plan != "Non-Plan" else "provision not given"
    if u in ("9.1A", "9.1", "9.2B", "9.2", "9.1A/9.2B", "9.1/IA"):
        g = "advance publication"
    elif u.startswith("9.6") or u.startswith("9.7") or u == "9.11":
        g = "coordination request"
    elif u == "11.2" or u.startswith("11."):
        g = "notification for the Master Register"
    elif u == "RR1488":
        g = "notification under RR1488 (the former number of 11.2)"
    elif u == "RS49":
        g = "Resolution 49 due diligence"
    elif u.startswith("RS"):
        g = "Resolution " + u[2:] + " notice"
    elif u.startswith("A30B#") or u.startswith("30B#"):
        return "Appendix 30B, Article " + u.split("#", 1)[1]
    elif re.match(r"^(30/30A#|30#)?4\.", u):
        return "Appendix 30/30A plan modification, Article " + u.split("#")[-1]
    elif re.match(r"^(30/30A#|30#)?5\.", u):
        return "Appendix 30/30A plan notification, Article " + u.split("#")[-1]
    else:
        return p
    return f"{g} ({p})"


def dashboard_url(row: dict) -> str:
    """ITU's own page for a notice: the non-plan dashboard by name and notice id; for a plan notice, Space
    Explorer's list of that network."""
    name = row.get("sat_name") or ""
    if not row.get("f_plan") and row.get("ntc_id"):
        return (f"{APP}/networks-explorer/space-stations/dashboard/non-plans/"
                f"{urllib.parse.quote(name, safe='')}/{int(row['ntc_id'])}")
    q = {"entity": "ss", "src": "sns", "adm": row.get("adm") or "", "sat_name": name, "plan": 1,
         "nonplan": 0 if row.get("f_plan") else 1, "geo": 1, "nongeo": 0}
    if row.get("ntwk_org"):
        q["ntwk_org"] = row["ntwk_org"]
    return f"{APP}/list-redirect?" + urllib.parse.urlencode(q)  # the form Space Explorer's link generator gives


def notice(row: dict) -> dict:
    """One row of Space Explorer's list, reduced to what Orbit shows."""
    adm = row.get("adm") or ""
    return {"network": row.get("sat_name") or "", "adm": adm, "org": row.get("ntwk_org"),
            "filer": adm + ("/" + row["ntwk_org"] if row.get("ntwk_org") else ""),
            "lon": row.get("long_nom"), "ntc_id": row.get("ntc_id"), "prov": row.get("prov"),
            "what": provision(row.get("prov"), row.get("plan_txt")), "received": iso(row.get("d_rcv")),
            "plan": row.get("plan_txt") or ("Plan" if row.get("f_plan") else "Non-Plan"),
            "link": dashboard_url(row)}


def networks(rows: list[dict]) -> list[dict]:
    """Notices grouped by network name and filer, nearest the slot first, then by name; each network's notices
    oldest first."""
    by: dict[tuple, dict] = {}
    for r in rows:
        n = notice(r)
        k = (n["network"], n["filer"])
        g = by.setdefault(k, {"network": n["network"], "filer": n["filer"], "adm": n["adm"], "org": n["org"],
                              "lon": n["lon"], "notices": []})
        g["notices"].append(n)
    out = list(by.values())
    for g in out:
        g["notices"].sort(key=lambda n: (n["received"] or "", n["ntc_id"] or 0))
    return out


def arcs(slot: float, window: float) -> list[tuple[float, float]]:
    """The orbital arc(s) Space Explorer is asked for: one, or two where the window crosses 180°."""
    lo, hi = slot - window, slot + window
    if lo < -180:
        return [(-180.0, hi), (lo + 360.0, 180.0)]
    if hi > 180:
        return [(lo, 180.0), (-180.0, hi - 360.0)]
    return [(lo, hi)]


def query_body(lo: float, hi: float, skip: int = 0) -> dict:
    """The body Space Explorer's Space Stations list sends with its GEO "orbital arc" filter (active notices)."""
    return {"general": {"network": "active", "serviceType": "all"},
            "satNetworkTypes": {"geo": True, "geoFrom": round(lo, 3), "geoTo": round(hi, 3)}, "take": TAKE, "skip": skip}


def post_json(url: str, body: dict, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"User-Agent": UA, "Accept": "application/json",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https URL
        return r.read()


def get_bytes(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https URL
        return r.read()


class _Pacer:
    """At most one request every GAP_S seconds."""

    def __init__(self, gap: float = GAP_S, sleep=time.sleep, clock=time.monotonic):
        self.gap, self.sleep, self.clock, self.last = gap, sleep, clock, None

    def wait(self):
        if self.last is not None:
            left = self.gap - (self.clock() - self.last)
            if left > 0:
                self.sleep(left)
        self.last = self.clock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fresh(path: Path, now: datetime, max_age_days: float) -> dict | None:
    if not path.exists():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        read = datetime.fromisoformat(doc["read"].replace("Z", "+00:00"))
    except (ValueError, KeyError, TypeError):
        return None
    return doc if (now - read).total_seconds() < max_age_days * 86400 else None


def slot_notices(slot: float, window: float, cache_dir: Path | None, refresh: bool = False, poster=None,
                 pacer: _Pacer | None = None, now: datetime | None = None) -> dict:
    """Active GEO notices with a nominal longitude within `window` of `slot`: {"read", "arcs", "total", "rows",
    "cached"}. A reply cached under `cache_dir` within MAX_AGE_DAYS is reused unless `refresh`."""
    now = now or _now()
    key = f"slot_{slot:+.2f}_w{window:.2f}.json".replace("+", "p").replace("-", "m")
    path = Path(cache_dir) / key if cache_dir else None
    if path and not refresh:
        doc = _fresh(path, now, MAX_AGE_DAYS)
        if doc:
            return {**doc, "cached": True}
    poster, pacer = poster or post_json, pacer or _Pacer()
    rows, total, got_arcs = [], 0, arcs(slot, window)
    for lo, hi in got_arcs:
        skip = 0
        for _ in range(MAX_PAGES):
            pacer.wait()
            doc = json.loads(poster(QUERIES_URL, query_body(lo, hi, skip)).decode("utf-8"))
            if not isinstance(doc, dict) or not isinstance(doc.get("table"), list):
                raise ValueError("Space Explorer's reply has no table: the call may have changed")
            page = doc["table"]
            rows += page
            arc_total = int(doc.get("total") or 0)
            skip += len(page)
            if not page or skip >= arc_total:
                break
        total += arc_total
    out = {"read": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "slot": slot, "window": window,
           "arcs": [list(a) for a in got_arcs], "total": total, "rows": rows}
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return {**out, "cached": False}


def res40_table(cache_dir: Path | None, refresh: bool = False, getter=None, pacer: _Pacer | None = None,
                now: datetime | None = None) -> dict:
    """ITU's Resolution 40 table: {"read", "rows", "cached"}, cached like `slot_notices`."""
    now = now or _now()
    path = Path(cache_dir) / "res40.json" if cache_dir else None
    if path and not refresh:
        doc = _fresh(path, now, MAX_AGE_DAYS)
        if doc:
            return {**doc, "cached": True}
    (pacer or _Pacer()).wait()
    raw = (getter or get_bytes)(RES40_URL)
    rows = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(rows, list):
        raise ValueError("the Resolution 40 table is not a list: the file may have changed")
    out = {"read": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "rows": rows}
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return {**out, "cached": False}


def _apart(a: float, b: float) -> float:
    return abs((a - b + 540.0) % 360.0 - 180.0)


def res40_at(rows: list[dict], slot: float, window: float) -> dict:
    """Resolution 40 rows for a slot: "in": a station in position for a filing at the slot; "out": a station that
    left the slot for a filing elsewhere. Newest first."""
    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    def rec(r):
        return {"network": r.get("sat_name") or "", "adm": r.get("adm") or "", "org": r.get("ntwk_org"),
                "lon": num(r.get("long_nom")), "in_position": iso(r.get("d_in_pos")), "prov": r.get("prov"),
                "moved": (r.get("sat_relocation") or "").upper() == "YES", "prev_lon": num(r.get("prev_long_nom")),
                "prev_network": r.get("sat_name_prev"), "left_prev": iso(r.get("d_out_prev_pos"))}

    came, left = [], []
    for r in rows:
        x = rec(r)
        if x["lon"] is not None and _apart(x["lon"], slot) <= window:
            came.append(x)
        if x["moved"] and x["prev_lon"] is not None and _apart(x["prev_lon"], slot) <= window:
            left.append(x)
    came.sort(key=lambda x: x["in_position"] or "", reverse=True)
    left.sort(key=lambda x: x["left_prev"] or x["in_position"] or "", reverse=True)
    return {"in": came, "out": left}


# --------------------------------------------------------------------------------------------- the link file

KEYS = {"norad", "network", "adm", "org", "slot", "ntc_id", "from", "to", "basis", "evidence", "proposed_by",
        "proposed", "reviewed_by", "reviewed", "withdrawn", "reason", "note"}
NEED = ("norad", "network", "adm", "slot", "basis", "evidence", "proposed_by", "proposed")
BASES = {
    "declared": "an operator's or administration's own document names both the satellite and the filing",
    "res40-dates": "the Resolution 40 in-position or departure dates match this object's own move in public "
                   "element sets",
    "by-hand": "matched by a TIC analyst from the evidence listed",
}


class LinkError(AliasError):
    pass


def validate_links(entries: list[dict]) -> list[dict]:
    """Checks every entry of itu-links.yml and returns the live ones (withdrawn left out), reviewed or not."""
    live, seen = [], {}
    for e in entries:
        where = f"itu-links.yml line {e.get('line')}"
        extra = set(e) - KEYS - {"line"}
        if extra:
            raise LinkError(f"{where}: unknown keys {sorted(extra)}")
        missing = [k for k in NEED if k not in e]
        if missing:
            raise LinkError(f"{where}: missing {missing}")
        if not (isinstance(e["norad"], int) and e["norad"] > 0):
            raise LinkError(f"{where}: norad must be a NORAD number")
        for k in ("network", "adm"):
            if not (isinstance(e[k], str) and e[k].strip()):
                raise LinkError(f"{where}: {k} must be ITU's text, as ITU gives it")
        try:
            slot = float(e["slot"])
        except (TypeError, ValueError):
            raise LinkError(f"{where}: slot must be degrees east, -180 to 180 (west negative)") from None
        if not -180 <= slot <= 180:
            raise LinkError(f"{where}: slot must be degrees east, -180 to 180 (west negative)")
        e["slot"] = slot
        if "ntc_id" in e and not (isinstance(e["ntc_id"], int) and e["ntc_id"] > 0):
            raise LinkError(f"{where}: ntc_id must be ITU's notice id")
        if e["basis"] not in BASES:
            raise LinkError(f"{where}: basis must be one of {sorted(BASES)}")
        ev = e["evidence"]
        if not (isinstance(ev, list) and ev and all(isinstance(x, str) and x.strip() for x in ev)):
            raise LinkError(f"{where}: evidence must be a list of at least one statement")
        for k in ("from", "to", "proposed", "reviewed", "withdrawn"):
            try:
                _check_date(e, k, where)
            except AliasError as exc:
                raise LinkError(str(exc)) from None
        if e.get("from") and e.get("to") and e["to"] < e["from"]:
            raise LinkError(f"{where}: to is before from")
        if ("reviewed" in e) != ("reviewed_by" in e):
            raise LinkError(f"{where}: reviewed and reviewed_by go together")
        if "reviewed_by" in e and not (isinstance(e["reviewed_by"], str) and e["reviewed_by"].strip()):
            raise LinkError(f"{where}: reviewed_by must name the reviewer")
        if "withdrawn" in e:
            if not e.get("reason"):
                raise LinkError(f"{where}: a withdrawn entry needs a reason")
            continue
        k = (e["norad"], e["network"], e["adm"], e.get("from"))
        if k in seen:
            raise LinkError(f"{where}: the same link is at line {seen[k]}")
        seen[k] = e.get("line")
        live.append(e)
    return live


def load_links(path: Path | str | None = None) -> list[dict]:
    p = Path(path) if path else LINKS_PATH
    if not p.exists():
        return []
    return validate_links(parse(p.read_text(encoding="utf-8")))


def reviewed(entries: list[dict]) -> list[dict]:
    """The entries that may reach a page: reviewed by a person."""
    return [e for e in entries if e.get("reviewed_by")]


def public_links(entries: list[dict], built: str) -> dict:
    """`site/data/itu-links.json` (`orbit-itu-links/1`): reviewed links only, by NORAD number."""
    by: dict[str, list] = {}
    for e in reviewed(entries):
        row = {"network": e["network"], "adm": e["adm"], "slot": e["slot"], "basis": e["basis"],
               "evidence": list(e["evidence"]), "reviewed": e["reviewed"]}
        for k in ("org", "ntc_id", "from", "to", "note"):
            if e.get(k) is not None:
                row[k] = e[k]
        row["link"] = dashboard_url({"sat_name": e["network"], "adm": e["adm"], "ntwk_org": e.get("org"),
                                     "ntc_id": e.get("ntc_id"), "f_plan": False})
        by.setdefault(str(e["norad"]), []).append(row)
    for v in by.values():
        v.sort(key=lambda r: (r.get("from") or "", r["network"]))
    return {"schema": "orbit-itu-links/1", "built": built, "about": NETWORK_NOTE,
            "link_note": "Each link from a filing to this object is TIC's attribution, reviewed by a TIC analyst; "
                         "the ITU gives no satellite or NORAD number for a filing.",
            "bases": BASES, "credit": CREDIT, "objects": by}
