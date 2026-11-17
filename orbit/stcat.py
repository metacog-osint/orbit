"""Space-Track SATCAT and DECAY for TIC's satellite catalog (build step 3, 17 Nov 2026).

Design: [local path], sections 2 and 4. Space-Track ranks first for identity
keys (`intldes`), decay and names (catalog.RANK); GCAT ranks first for launch date and state.

Space-Track's limits (space-track.org/documentation, "Use Policy" table, read 17 Nov 2026 18:00 UTC):
  - "SATCAT  1 / day  Once per day after 1700 (UTC) for SATCAT data."
  - "DECAY  1 / day  Once you download an object's decay history, you need to store it on your own servers; do not
    download it again. If checking once per day, add "/MSG_EPOCH/%3Enow-1/" to retrieve current messages only."
  - "GP (aka TLEs)  1 / hour ... randomly choose a minute that is not at the top or bottom of the hour". That row is
    GP's alone: SATCAT and DECAY have their own daily rows, so the hourly GP spacing (spacetrack.shared_gp_busy) does
    not apply. Neither Noisefloor nor any other TIC program queries satcat or decay (checked 17 Nov 2026), so the
    daily limit is Orbit's to keep: `due()` allows one read per SATCAT day (17:00 UTC to 17:00 UTC next day),
    recorded in the state file, and the run still keeps off :57-:03 and :27-:33 (spacetrack.wait_for_clear_minute).
  - The account-wide 30 a minute and 300 an hour: a run makes 4 requests (log in, satcat, decay, log out), 2.5 s
    apart (spacetrack.Client).

DECAY: the first read takes the whole history once (one request); later reads ask only for messages since the
last read less a day (MSG_EPOCH), and the store keeps every message ever read. The history is never asked for again.

Redistribution: SATCAT and decay data are basic SSA data under USSPACECOM's blanket approval, conditioned on
citation (doctrine/spacetrack-disclaimer.md; CITATION below). Raw replies stay in git-ignored data/raw.

Well-tracked analyst objects (Space-Track FAQ, read 17 Nov 2026): COUNTRY and SITE "UNKN", international designator
"YYYY-000A" (year cataloged) and launch date "1 January of the year that the object is cataloged". Those values are
Space-Track placeholders: kept, basis `catalog`, marked `placeholder`, and never compared with another source.
"""
from __future__ import annotations

import gzip
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import spacetrack

SOURCE = "space-track"
BASE = spacetrack.BASE + "/basicspacedata/query/class/"
SATCAT_URL = BASE + "satcat/CURRENT/Y/orderby/NORAD_CAT_ID%20asc/format/json"
DECAY_ALL_URL = BASE + "decay/orderby/NORAD_CAT_ID%20asc/format/json"
DECAY_SINCE_URL = BASE + "decay/MSG_EPOCH/%3E{since}/orderby/NORAD_CAT_ID%20asc/format/json"
OPEN_HOUR = 17  # "Once per day after 1700 (UTC)"
STATE = Path("state") / "spacetrack-catalog.json"
DECAY_STORE = Path("state") / "spacetrack-decay.json.gz"
RAW = Path("raw")
# doctrine/spacetrack-disclaimer.md section 3 (approved by Tom 14 Nov 2026), with "Element sets" read as catalog and
# decay data, as tip.py reads it for reentry predictions.
CITATION = ("Catalog and decay data: Space-Track.org, United States Space Command (USSPACECOM), 18th Space Defense "
            "Squadron, redistributed under USSPACECOM's blanket approval for basic SSA data. Comparisons with other "
            "catalogs: The Intelligence Company, not reviewed or endorsed by USSPACECOM. Not for operational use.")

INTLDES_RE = re.compile(r"^(\d{4})-(\d{3})([A-Z]{1,3})$")
OLD_PIECE_RE = re.compile(r"^\d{4} [A-Z]{3}")  # GCAT's pre-1963 Greek-letter pieces ("1958 ALP 1")

# Space-Track COUNTRY codes -> GCAT State codes, for comparison only (the record keeps Space-Track's own code).
# Space-Track's COUNTRY is "the nation or group that has responsibility for an object" (its glossary); GCAT's State
# is the responsible state. Built 17 Nov 2026 from a cross-tabulation of the two on the 70,000 numbers both list
# (Space-Track SATCAT of 17 Nov 18:09 UTC, GCAT of 15 Nov): each code below is the one GCAT gives most of that
# code's objects. Joint codes map to each partner. A code not listed is compared as written.
COUNTRY_TO_STATE = {
    "US": ("US",), "CIS": ("SU", "RU"), "PRC": ("CN",), "FR": ("F",), "JPN": ("J",), "IND": ("IN",), "UK": ("UK",),
    "ESA": ("I-ESA",), "GER": ("D",), "IT": ("I",), "CA": ("CA",), "SPN": ("E",), "SKOR": ("KR",), "ARGN": ("AR",),
    "AUS": ("AU",), "ISRA": ("IL",), "TURK": ("TR",), "TWN": ("TW",), "FIN": ("FI",), "BRAZ": ("BR",),
    "UAE": ("UAE",), "SING": ("SG",), "POL": ("PL",), "NOR": ("N",), "IRAN": ("IR",), "LUXE": ("L",), "NZ": ("NZ",),
    "GREC": ("GR",), "INDO": ("ID",), "NETH": ("NL",), "SWTZ": ("CH",), "BEL": ("B",), "DEN": ("DK",),
    "EUME": ("I-EUM",), "SWED": ("S",), "AB": ("I-ARAB",), "THAI": ("T",), "SAUD": ("SA",), "LTU": ("LT",),
    "POR": ("P",), "EGYP": ("EG",), "MEX": ("MX",), "RWA": ("RW",), "UKR": ("UA",), "SAFR": ("ZA",), "HUN": ("HU",),
    "BGR": ("BGN", "BG"), "ESRO": ("I-ESRO",), "PAKI": ("PK",), "CZE": ("CZ",), "MALA": ("MY",), "NATO": ("I-NATO",),
    "RP": ("PH",), "CHLE": ("CL",), "KAZ": ("KZ",), "NKOR": ("KP",), "ALG": ("DZ",), "NIG": ("NG",), "VTNM": ("VN",),
    "ASRA": ("AT",), "CZCH": ("CSSR", "CSFR", "CZ"), "PER": ("PE",), "MA": ("MA",), "SVN": ("SI",), "COL": ("CO",),
    "VENZ": ("VE",), "AZER": ("AZ",), "RASC": ("I-RASC",), "ROM": ("RO",), "BELA": ("BY",), "ECU": ("EC",),
    "EST": ("EE",), "QAT": ("QA",), "SVK": ("SK",), "BGD": ("BD",), "AGO": ("AO",), "KEN": ("KE",), "KWT": ("KW",),
    "DJI": ("DJ",), "BOL": ("BO",), "URY": ("UY",), "IRAQ": ("IQ",), "LAOS": ("LA",), "GHA": ("GH",), "MNG": ("MN",),
    "CRI": ("CR",), "JOR": ("JO",), "LKA": ("LK",), "NPL": ("NP",), "SDN": ("SD",), "PRY": ("PY",), "TUN": ("TN",),
    "MMR": ("MYM",), "MUS": ("MU",), "PRI": ("PR",), "MDA": ("MD",), "UGA": ("UG",), "ZWE": ("ZW",), "MCO": ("MC",),
    "HRV": ("HR",), "BWA": ("BW",), "BHR": ("BH",), "SLB": ("SB",),
    # joint: CBERS (China-Brazil), Symphonie (France-Germany), Athena-Fidus and Sicral 2 (France-Italy),
    # Estrela do Sul (US-Brazil), ST 1 and 2 (Singapore-Taiwan), TurkmenAlem/MonacoSat (Turkmenistan-Monaco)
    "CHBZ": ("CN", "BR"), "FGER": ("F", "D"), "FRIT": ("F", "I"), "USBZ": ("US", "BR"), "STCT": ("SG", "TW"),
    "TMMC": ("TM", "MC"),
}
# Codes naming an operator, not a state (their objects on 17 Nov 2026: ORBCOMM, Globalstar, SES/Astra, O3b, Sea
# Launch, Intelsat, Eutelsat, Inmarsat, ABS, AsiaSat). Kept as Space-Track gives them, never compared with a state.
OPERATOR_CODES = {"ORB", "GLOB", "SES", "O3B", "SEAL", "ITSO", "EUTE", "IM", "ABS", "AC"}
# "TBD" (490 objects on 17 Nov 2026, named OBJECT C and the like) and "UNKN" (analyst objects, Space-Track FAQ).
PLACEHOLDER_COUNTRY = {"TBD", "UNKN"}


def _t(s: str | None) -> datetime | None:
    s = (s or "").strip()
    for fmt, n in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(s[:n], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _date(s: str | None) -> str | None:
    t = _t(s)
    return t.date().isoformat() if t else None


def satcat_day(now: datetime) -> str:
    """The UTC date of a read (reads happen only from 17:00 UTC, so one date is one SATCAT day)."""
    return now.date().isoformat()


def due(now: datetime, state: dict) -> str | None:
    """Why a SATCAT read must not run now (None when it may): only from 17:00 UTC, once per UTC date."""
    if now.hour < OPEN_HOUR:
        return f"Space-Track asks for SATCAT once a day after 17:00 UTC; it is {now:%H:%M} UTC"
    if state.get("satcat_day") == satcat_day(now):
        return f"SATCAT already read today ({state.get('satcat_read_at')}); next after 17:00 UTC tomorrow"
    return None


def decay_url(state: dict, now: datetime) -> str:
    """The whole decay history on the first read; afterwards messages since the last read less a day."""
    last = _t(state.get("decay_read_at"))
    if last is None:
        return DECAY_ALL_URL
    since = (min(last, now) - timedelta(days=1)).strftime("%Y-%m-%d")
    return DECAY_SINCE_URL.format(since=since)


def _msg_key(r: dict) -> tuple:
    return (str(r.get("NORAD_CAT_ID") or ""), r.get("MSG_EPOCH") or "", r.get("MSG_TYPE") or "",
            r.get("SOURCE") or "", r.get("DECAY_EPOCH") or "")


def merge_decay(store: list[dict], new: list[dict]) -> tuple[list[dict], int]:
    """Adds messages not yet held. Returns (store, number added). Nothing held is ever dropped."""
    seen = {_msg_key(r) for r in store}
    added = 0
    for r in new:
        k = _msg_key(r)
        if k not in seen:
            seen.add(k)
            store.append(r)
            added += 1
    return store, added


def read_json(path: Path, default):
    if not path.exists():
        return default
    body = path.read_bytes()
    return json.loads(gzip.decompress(body) if path.name.endswith(".gz") else body)


def write_json(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path.write_bytes(gzip.compress(raw, 6) if path.name.endswith(".gz") else raw)


def pull(data_dir: Path, cred: tuple[str, str], now: datetime | None = None, client=None, wait=None) -> dict:
    """One SATCAT and one DECAY read (4 requests). Raw replies into data/raw/spacetrack-{satcat,decay}/, gzipped;
    the decay store and state under data/state/. Raises spacetrack.NotReady when not due."""
    now = now or datetime.now(timezone.utc)
    state_path = data_dir / STATE
    state = read_json(state_path, {})
    why = due(now, state)
    if why:
        raise spacetrack.NotReady(why)
    (wait or spacetrack.wait_for_clear_minute)()
    c = client or spacetrack.Client(*cred)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    c.login()
    try:
        satcat = c.query_path(SATCAT_URL, "satcat")
        sat_body = c.last_body
        durl = decay_url(state, now)
        decay = c.query_path(durl, "decay")
        dec_body = c.last_body
    finally:
        c.logout()
    for name, body in (("satcat", sat_body), ("decay", dec_body)):
        p = data_dir / RAW / f"spacetrack-{name}" / f"{stamp}.json.gz"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(gzip.compress(body, 6))
    store_path = data_dir / DECAY_STORE
    store, added = merge_decay(read_json(store_path, []), decay)
    write_json(store_path, store)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    state.update({"satcat_day": satcat_day(now), "satcat_read_at": read_at, "satcat_rows": len(satcat),
                  "decay_read_at": read_at, "decay_query": "all" if durl == DECAY_ALL_URL else "since",
                  "decay_rows_read": len(decay), "decay_added": added, "decay_held": len(store),
                  "satcat_file": f"spacetrack-satcat/{stamp}.json.gz"})
    write_json(state_path, state)
    return {"satcat": satcat, "decay": store, "state": state, "requests": c.requests}


def load_local(data_dir: Path) -> dict | None:
    """The newest SATCAT reply and the decay store already on disk (no request), or None."""
    state = read_json(data_dir / STATE, {})
    f = state.get("satcat_file")
    if not f or not (data_dir / RAW / f).exists():
        return None
    return {"satcat": json.loads(gzip.decompress((data_dir / RAW / f).read_bytes())),
            "decay": read_json(data_dir / DECAY_STORE, []), "state": state}


# --- catalog records -------------------------------------------------------------------------------------------

TYPES = {"PAYLOAD": "payload", "ROCKET BODY": "rocket stage", "DEBRIS": "debris"}


def placeholder_analyst(row: dict) -> bool:
    m = INTLDES_RE.match((row.get("INTLDES") or row.get("OBJECT_ID") or "").strip())
    return bool(m and m.group(2) == "000")


def comparable_intldes(value: str) -> str | None:
    """A designation in YYYY-NNNP form, for comparison; GCAT's pre-1963 Greek-letter pieces and anything else are
    not compared (no table maps them)."""
    v = (value or "").strip().upper().replace(" ", "")
    return v if INTLDES_RE.match(v) and not v[5:8] == "000" else None


def state_matches(country: str, gcat_state: str) -> bool:
    return gcat_state in COUNTRY_TO_STATE.get(country, (country,))


def decay_messages(store: list[dict]) -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = {}
    for r in store:
        n = str(r.get("NORAD_CAT_ID") or r.get("OBJECT_NUMBER") or "").strip()
        if n.isdigit():
            by.setdefault(str(int(n)), []).append(r)
    return by
