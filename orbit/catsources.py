"""CelesTrak SATCAT and Wikidata for TIC's satellite catalog (build step 4, 17 Nov 2026).

Design: [local path], sections 1, 2, 4 and 9. Each source's values arrive as more
records on the NORAD-keyed entries of orbit/catalog.py, ranked by catalog.RANK; nothing is replaced and nothing
joins on a name.

CelesTrak (celestrak.org/usage-policy.php, by T.S. Kelso, "Updated 2026 Nov 16", read 17 Nov 2026 18:39 UTC):
  - "Only download the data you need, when you are going to use it, and only download data once per update."
  - "The SATCAT updates manually once or twice a day."
  - Directory queries such as https://celestrak.org/satcat/jsonDir.php: "Please don't query these more than once
    per hour."
  - "We support web compression (gzip & brotli). Please request compressed data whenever possible."
  - "M2M (machine-to-machine) software should immediately stop querying when it receives any non-HTTP 200 responses
    and report the results to a human for investigation." 500 or 503: "All requests should stop for at least 15
    minutes".
  No licence, redistribution or credit terms are stated; ingested with credit (Tom, 16 Nov 2026), as for Launch
  Library 2. So a run asks the directory once (FILE_MTIME of satcat.csv), downloads /pub/satcat.csv (gzip) only when
  that time differs from the last read and no read was made that UTC day, and never follows a redirect. Any answer
  but 200 is a hold: a 500 or 503 holds until the next UTC day; anything else holds until a person clears it
  (`clear_hold`), and the run prints the code for a human.

Wikidata (CC0, wikidata.org/wiki/Wikidata:Licensing, read 17 Nov 2026: structured data "is released into the public
domain under Creative Commons Zero"). Query service limits (mediawiki.org/wiki/Wikidata_Query_Service/User_Manual,
read 17 Nov 2026): "hard query deadline configured which is set to 60 seconds"; "One client (user agent + IP) is
allowed 60 seconds of processing time each 60 seconds"; 429 when over; "access to the service is limited to 5
parallel queries per IP". The Wikimedia User-Agent policy (foundation.wikimedia.org/wiki/Policy:User-Agent_policy,
read 17 Nov 2026) asks for "an informative User-Agent string with contact information" (an email address, a website
or a wiki user) and the word "bot": UA below names the repository, no person. One query a week: every item with a
truthy P377 (Satellite Catalog Number), its English and multilingual ('mul') labels, English aliases and P247
(COSPAR ID). 7,518 items carried P377 on 17 Nov 2026.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

UA = "TIC-Orbit-catalog-bot/1.0 (https://github.com/metacog-osint/orbit; satellite catalog build)"
STATE = Path("state") / "catalog-sources.json"

CT = "celestrak-satcat"
WD = "wikidata"

CT_DIR_URL = "https://celestrak.org/satcat/jsonDir.php"
CT_CSV_URL = "https://celestrak.org/pub/satcat.csv"
CT_FILE = "satcat.csv"
CT_CITATION = "CelesTrak SATCAT (T.S. Kelso, celestrak.org)"
CT_STORE = Path("state") / "celestrak-satcat.csv.gz"   # the last reply, kept between runs (Actions cache)
CT_MIN_ROWS = 50000  # 71,323 rows on 17 Nov 2026; a shorter reply is refused and the last read kept

WD_URL = "https://query.wikidata.org/sparql"
WD_CITATION = "Wikidata (CC0), each value with its item's Q-id"
WD_STORE = Path("state") / "wikidata-p377.json.gz"  # the last reply, parsed (Actions cache)
WD_DAYS = 7
WD_MIN_ROWS = 5000  # 7,518 items on 17 Nov 2026
WD_QUERY = """SELECT ?item ?scn ?cospar ?en ?mul (GROUP_CONCAT(DISTINCT ?alt; separator="\\u001f") AS ?alts) WHERE {
  ?item wdt:P377 ?scn .
  OPTIONAL { ?item wdt:P247 ?cospar }
  OPTIONAL { ?item rdfs:label ?en FILTER(LANG(?en) = "en") }
  OPTIONAL { ?item rdfs:label ?mul FILTER(LANG(?mul) = "mul") }
  OPTIONAL { ?item skos:altLabel ?alt FILTER(LANG(?alt) = "en") }
} GROUP BY ?item ?scn ?cospar ?en ?mul"""

# CelesTrak's operational status codes (celestrak.org/satcat/status.php, read 17 Nov 2026): "+" Operational,
# "-" Nonoperational, "P" Partially Operational, "B" Backup/Standby, "S" Spare, "X" Extended Mission, "D"
# Decayed/Deorbited, "?" Unknown; "Active is any satellite with an operational status of +, P, B, S, or X." Compared
# with another source's operational status by that split; "D" goes to `decayed`, "?" is not compared.
CT_OPS = {"+": "active", "P": "active", "B": "active", "S": "active", "X": "active", "-": "inactive"}

# CelesTrak's OWNER uses Space-Track's COUNTRY codes (stcat.COUNTRY_TO_STATE) plus some of its own. These are the
# GCAT State that most of each code's objects carry (cross-tab of CelesTrak's 17 Nov 2026 file with GCAT of 15 Nov):
# ROC 50 of 51 TW; BUL 8 of 10 BGN; PERU 3 of 4 PE; ANG 2 of 2 AO; one object each for the rest. SGJP is joint
# (Singapore-Japan) and GRSA joint (Greece-Saudi Arabia, Hellas Sat 4/SaudiGeoSat 1), as Space-Track's joint codes.
CT_OWNER_TO_STATE = {
    "ROC": ("TW",), "BUL": ("BGN", "BG"), "PERU": ("PE",), "ANG": ("AO",), "BHUT": ("BT",), "GUAT": ("GT",),
    "VAT": ("VA",), "ARM": ("AM",), "IRL": ("IE",), "SEN": ("SN",), "MNE": ("ME",), "ETH": ("ET",),
    "SGJP": ("SG", "J"), "GRSA": ("GR", "SA"),
}
# "ISS": CelesTrak's owner for station modules and objects released from the station (135 objects; GCAT gives the
# module's own state: RU 80, US 44, J 7, I-ESA 3). A programme, not a state: kept, never compared.
CT_PROGRAM_CODES = {"ISS"}


class Refused(Exception):
    """A source answered with something other than 200: stop, record it, tell a human."""

    def __init__(self, source: str, url: str, code, why: str = ""):
        super().__init__(f"{source}: HTTP {code} from {url}{(' (' + why + ')') if why else ''}")
        self.source, self.url, self.code = source, url, code


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # a 301 is CelesTrak telling us the URL is wrong: never follow it
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def get(source: str, url: str, accept: str = "*/*", timeout: int = 120) -> bytes:
    """One GET with gzip asked for, no redirects followed. Any status but 200 raises Refused."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Encoding": "gzip"})
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            if resp.status != 200:
                raise Refused(source, url, resp.status)
            body = resp.read()
            if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                body = gzip.decompress(body)
            return body
    except urllib.error.HTTPError as exc:
        raise Refused(source, url, exc.code, (exc.reason or "") if isinstance(exc.reason, str) else "") from None


def read_json(path: Path, default):
    if not path.exists():
        return default
    body = path.read_bytes()
    return json.loads(gzip.decompress(body) if path.name.endswith(".gz") else body)


def write_json(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(doc, ensure_ascii=False, separators=(",", ":"), indent=None).encode("utf-8")
    path.write_bytes(gzip.compress(raw, 6) if path.name.endswith(".gz") else raw)


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _t(s: str | None) -> datetime | None:
    try:
        return datetime.strptime((s or "")[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def held(st: dict, now: datetime) -> str | None:
    """Why a source is on hold (None when it is not)."""
    h = st.get("hold")
    if not h:
        return None
    if h.get("until") and _t(h["until"]) and now >= _t(h["until"]):
        return None
    return (f"held since {h.get('at')} after HTTP {h.get('code')} from {h.get('url')}"
            + (f", until {h['until']}" if h.get("until") else "; a person must clear it (--clear-hold)"))


def hold(st: dict, exc: Refused, now: datetime) -> None:
    """Record a refusal. A 500 or 503 (CelesTrak: stop at least 15 minutes) holds until the next UTC day, the next
    daily slot; a 429 the same; anything else holds until a person clears it."""
    until = None
    if exc.code in (429, 500, 502, 503, 504):
        until = _iso(datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))
    st["hold"] = {"code": exc.code, "url": exc.url, "at": _iso(now), "until": until}


# --- CelesTrak SATCAT ----------------------------------------------------------------------------------------------

def ct_due(now: datetime, st: dict) -> str | None:
    """Why CelesTrak must not be asked now (None when the directory may be asked): one read per UTC date at most."""
    why = held(st, now)
    if why:
        return why
    if st.get("day") == now.date().isoformat():
        return f"already read today ({st.get('read_at')}); at most once a day"
    return None


def ct_mtime(dir_body: bytes) -> str | None:
    """satcat.csv's FILE_MTIME from CelesTrak's SATCAT directory reply."""
    for f in json.loads(dir_body):
        if f.get("FILE_NAME") == CT_FILE:
            return f.get("FILE_MTIME")
    return None


def ct_parse(body: bytes) -> list[dict]:
    text = body.decode("utf-8-sig")
    return [dict(r) for r in csv.DictReader(io.StringIO(text))]


def ct_pull(data_dir: Path, now: datetime, state: dict, get=get) -> dict:
    """One directory request; one CSV request when the file changed since the last read. Returns a note."""
    st = state.setdefault(CT, {})
    why = ct_due(now, st)
    if why:
        return {"read": False, "why": why}
    try:
        mtime = ct_mtime(get(CT, CT_DIR_URL, "application/json"))
        if not mtime:
            return {"read": False, "why": f"{CT_FILE} not listed in {CT_DIR_URL}"}
        if mtime == st.get("file_mtime") and (data_dir / CT_STORE).exists():
            st["checked_at"] = _iso(now)
            return {"read": False, "why": f"unchanged since the last read (file time {mtime})", "requests": 1}
        body = get(CT, CT_CSV_URL)  # "*/*": "text/csv" drew a 406 on 17 Nov 2026
    except Refused as exc:
        hold(st, exc, now)
        return {"read": False, "why": str(exc), "refused": exc.code}
    rows = ct_parse(body)
    if len(rows) < CT_MIN_ROWS or "NORAD_CAT_ID" not in (rows[0] if rows else {}):
        return {"read": False, "why": f"reply has {len(rows)} rows or lacks NORAD_CAT_ID; kept the last read",
                "requests": 2}
    stamp = now.strftime("%Y%m%dT%H%MZ")
    raw = data_dir / "raw" / CT / f"{stamp}.csv.gz"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(gzip.compress(body, 6))
    (data_dir / CT_STORE).parent.mkdir(parents=True, exist_ok=True)
    (data_dir / CT_STORE).write_bytes(gzip.compress(body, 6))
    st.update({"day": now.date().isoformat(), "read_at": _iso(now), "file_mtime": mtime, "rows": len(rows)})
    st.pop("hold", None)
    return {"read": True, "rows": len(rows), "file_mtime": mtime, "requests": 2}


def ct_load(data_dir: Path, state: dict) -> dict | None:
    p = data_dir / CT_STORE
    st = state.get(CT) or {}
    if not p.exists() or not st.get("read_at"):
        return None
    return {"rows": ct_parse(gzip.decompress(p.read_bytes())), "read": st["read_at"][:10],
            "read_at": st["read_at"], "file_mtime": st.get("file_mtime")}


# --- Wikidata ------------------------------------------------------------------------------------------------------

def wd_due(now: datetime, st: dict) -> str | None:
    why = held(st, now)
    if why:
        return why
    last = _t(st.get("read_at"))
    if last and now - last < timedelta(days=WD_DAYS) - timedelta(hours=6):
        return f"read {st['read_at']}; once a week"
    return None


def wd_url() -> str:
    return WD_URL + "?" + urllib.parse.urlencode({"query": WD_QUERY, "format": "json"})


def wd_parse(body: bytes) -> list[dict]:
    """SPARQL JSON results to rows {qid, scn, cospar, en, mul, alts[]}. One item may give several rows (several
    P377 or P247 values); each is kept."""
    out = []
    for b in json.loads(body)["results"]["bindings"]:
        def v(k):
            return (b.get(k) or {}).get("value")
        alts = [a for a in (v("alts") or "").split("\u001f") if a]
        out.append({"qid": v("item").rsplit("/", 1)[-1], "scn": v("scn"), "cospar": v("cospar"),
                    "en": v("en"), "mul": v("mul"), "alts": alts})
    return out


def wd_pull(data_dir: Path, now: datetime, state: dict, get=get) -> dict:
    st = state.setdefault(WD, {})
    # With the last reply gone (the Actions cache can be evicted), read again rather than build without Wikidata.
    why = wd_due(now, st) if (data_dir / WD_STORE).exists() else held(st, now)
    if why:
        return {"read": False, "why": why}
    try:
        body = get(WD, wd_url(), "application/sparql-results+json", timeout=90)
    except Refused as exc:
        hold(st, exc, now)
        return {"read": False, "why": str(exc), "refused": exc.code}
    rows = wd_parse(body)
    if len(rows) < WD_MIN_ROWS:
        return {"read": False, "why": f"reply has {len(rows)} rows (7,518 items on 17 Nov 2026); kept the last read",
                "requests": 1}
    stamp = now.strftime("%Y%m%dT%H%MZ")
    raw = data_dir / "raw" / WD / f"{stamp}.json.gz"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(gzip.compress(body, 6))
    write_json(data_dir / WD_STORE, rows)
    st.update({"read_at": _iso(now), "rows": len(rows), "items": len({r["qid"] for r in rows})})
    st.pop("hold", None)
    return {"read": True, "rows": len(rows), "items": st["items"], "requests": 1}


def wd_load(data_dir: Path, state: dict) -> dict | None:
    st = state.get(WD) or {}
    rows = read_json(data_dir / WD_STORE, None)
    if rows is None or not st.get("read_at"):
        return None
    return {"rows": rows, "read": st["read_at"][:10], "read_at": st["read_at"]}


# --- both ----------------------------------------------------------------------------------------------------------

def pull(data_dir: Path, now: datetime | None = None, get=get, only: tuple = (CT, WD)) -> dict:
    """Read each source that is due; the state file records reads and holds. Returns {source: note}."""
    now = now or datetime.now(timezone.utc)
    state = read_json(data_dir / STATE, {})
    notes = {}
    if CT in only:
        notes[CT] = ct_pull(data_dir, now, state, get)
    if WD in only:
        notes[WD] = wd_pull(data_dir, now, state, get)
    write_json(data_dir / STATE, state)
    return notes


def clear_hold(data_dir: Path, source: str) -> bool:
    state = read_json(data_dir / STATE, {})
    had = bool((state.get(source) or {}).pop("hold", None))
    write_json(data_dir / STATE, state)
    return had


def load(data_dir: Path) -> dict:
    """What is held locally for each source (no request): {source: {...} or None}."""
    state = read_json(data_dir / STATE, {})
    return {CT: ct_load(data_dir, state), WD: wd_load(data_dir, state)}
