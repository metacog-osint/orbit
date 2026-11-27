"""Names a state registered in the UN Register of Objects Launched into Outer Space (method orbit-2.50).

UNOOSA's Online Index answers one object at a time, filtered on its COSPAR id. It marks what a state communicated to
the United Nations apart from what the Index took from other sources: `nameOfSpaceObjectO_s1` is the name as
registered, `nameOfSpaceObjectIno_s1` a name the Index did not receive that way (shown in square brackets there).
Only the first is a declared name, and only with a registration document. The designator's own `@official` flag says
nothing about the name.

The UN's terms bar redistributing or compiling the Index, so Orbit publishes no register table. `lookup` asks on a
person's request only, at most MAX_IDS ids a call, GAP_S apart, and keeps replies in git-ignored `data/raw/unoosa/`.
Object pages show only entries a person reviewed in `orbit/data/catalog/un-register.yml`, one object at a time, as
declared by that state, with the document symbol and a link.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime
from pathlib import Path

from .aliases import AliasError, _check_date, parse
from .itu import _fresh, _now, _Pacer, get_bytes

SEARCH_URL = "https://www.unoosa.org/unoosa/osoindex/search/objects.search"
SITE = "https://www.unoosa.org/unoosa"
INDEX_URL = f"{SITE}/en/osoindex/search/search-objects.html"
GAP_S = 3.0          # seconds between two requests to UNOOSA
MAX_AGE_DAYS = 7     # a cached reply is reused this long
MAX_IDS = 10         # ids asked in one call
LINKS_PATH = Path(__file__).resolve().parent / "data" / "catalog" / "un-register.yml"
COSPAR = re.compile(r"^(19|20)\d{2}-\d{3}[A-Z]{1,3}$")
CREDIT = ("United Nations Register of Objects Launched into Outer Space (UNOOSA Online Index), (c) United Nations, "
          "one object at a time with the registration document cited")
ABOUT = ("The name a state gave when it registered the object with the United Nations. It may differ from the name "
         "in use today.")


class RegisterError(ValueError):
    pass


def cospar_id(text: str) -> str:
    c = (text or "").strip().upper()
    if not COSPAR.match(c):
        raise RegisterError(f"not a COSPAR id (like 2008-065A): {text!r}")
    return c


def search_url(cospar: str) -> str:
    criteria = {"filters": [{"fieldName": "object.internationalDesignator_s1", "value": cospar_id(cospar)}],
                "startAt": 0}
    return f"{SEARCH_URL}?{urllib.parse.urlencode({'criteria': json.dumps(criteria, separators=(',', ':'))})}"


def _text(v) -> str:
    """One field of a reply as text: the Index sends a string or a list of strings, and dashes for nothing."""
    if isinstance(v, list):
        v = v[0] if v else ""
    s = str(v or "").strip()
    return "" if set(s) <= {"-"} else s


def record(values: dict) -> dict:
    """One result's fields. `name` is set only for a name as registered: given in the registered-name field, without
    square brackets, with a registration document. A name from the other field is kept as `other_name` and is never
    a declared name. The GSO location is kept only when the Index marks it official."""
    def get(k):
        return _text(values.get(k))

    registered = get("en#object.unRegistration.unRegistered_s1").lower() == "yes"
    symbol = get("object.unRegistration.registrationDocuments.document..document.symbol_s")
    uri = get("object.unRegistration.registrationDocuments.document@uri_s")
    name = get("object.nameOfSpaceObjectO_s1")
    declared = bool(name and "[" not in name and "]" not in name and registered and symbol)
    gso = get("object.status.gsoLocation_s1")
    return {"cospar": get("object.internationalDesignator_s1"),
            "name": name if declared else None,
            "other_name": get("object.nameOfSpaceObjectIno_s1") or (None if declared else name) or None,
            "state": get("object.launch.stateOfRegistry_s1") or None,
            "state_official": get("object.launch.stateOfRegistry@official_s1").lower() == "true",
            "gso": gso if gso and get("object.status.gsoLocation@official_s1").lower() == "true" else None,
            "registered": registered,
            "symbol": symbol or None,
            "link": SITE + uri if uri.startswith("/osoindex/") else None,
            "remark": get("object.remark_s1") or None}


def records(doc: dict, cospar: str) -> list[dict]:
    """The reply's records for exactly this id. A reply without a result list is an error, never "not registered"."""
    results = doc.get("results") if isinstance(doc, dict) else None
    if not isinstance(results, list):
        raise RegisterError("the Online Index's reply has no result list")
    got = [record(r.get("values") or {}) for r in results]
    return [r for r in got if r["cospar"] == cospar]


def lookup(ids: list[str], cache_dir: Path | None, refresh: bool = False, getter=None, pacer: _Pacer | None = None,
           now: datetime | None = None) -> list[dict]:
    """Each id's register records: [{"cospar", "read", "records", "cached"}]. A reply cached under `cache_dir` within
    MAX_AGE_DAYS is reused unless `refresh`. More than MAX_IDS ids is refused before anything is asked."""
    ids = list(dict.fromkeys(cospar_id(i) for i in ids))
    if len(ids) > MAX_IDS:
        raise RegisterError(f"at most {MAX_IDS} ids in one call, got {len(ids)}")
    now = now or _now()
    getter, pacer = getter or get_bytes, pacer or _Pacer(GAP_S)
    out = []
    for c in ids:
        path = Path(cache_dir) / f"{c}.json" if cache_dir else None
        doc = _fresh(path, now, MAX_AGE_DAYS) if path and not refresh else None
        cached = doc is not None
        if not cached:
            pacer.wait()
            reply = json.loads(getter(search_url(c)).decode("utf-8"))
            records(reply, c)  # a reply of the wrong shape is not cached
            doc = {"read": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "reply": reply}
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(doc), encoding="utf-8")
        out.append({"cospar": c, "read": doc["read"], "records": records(doc["reply"], c), "cached": cached})
    return out


# --------------------------------------------------------------------------------------------- the reviewed file

KEYS = {"cospar", "name", "state", "symbol", "link", "gso", "read", "proposed_by", "proposed", "reviewed_by",
        "reviewed", "withdrawn", "reason", "note"}
NEED = ("cospar", "name", "state", "symbol", "link", "read", "proposed_by", "proposed")


class EntryError(AliasError):
    pass


def validate_entries(entries: list[dict]) -> list[dict]:
    """Checks every entry of un-register.yml and returns the live ones (withdrawn left out), reviewed or not."""
    live, seen = [], {}
    for e in entries:
        where = f"un-register.yml line {e.get('line')}"
        extra = set(e) - KEYS - {"line"}
        if extra:
            raise EntryError(f"{where}: unknown keys {sorted(extra)}")
        missing = [k for k in NEED if k not in e]
        if missing:
            raise EntryError(f"{where}: missing {missing}")
        if not (isinstance(e["cospar"], str) and COSPAR.match(e["cospar"])):
            raise EntryError(f"{where}: cospar must be a COSPAR id, like 2008-065A")
        for k in ("name", "state", "symbol", "proposed_by"):
            if not (isinstance(e[k], str) and e[k].strip()):
                raise EntryError(f"{where}: {k} must be text")
        if "[" in e["name"] or "]" in e["name"]:
            raise EntryError(f"{where}: a name in square brackets was not registered, so it is not a declared name")
        if not str(e["link"]).startswith(f"{SITE}/osoindex/"):
            raise EntryError(f"{where}: link must be the registration document under {SITE}/osoindex/")
        for k in ("read", "proposed", "reviewed", "withdrawn"):
            try:
                _check_date(e, k, where)
            except AliasError as exc:
                raise EntryError(str(exc)) from None
        if ("reviewed" in e) != ("reviewed_by" in e):
            raise EntryError(f"{where}: reviewed and reviewed_by go together")
        if "reviewed_by" in e and not (isinstance(e["reviewed_by"], str) and e["reviewed_by"].strip()):
            raise EntryError(f"{where}: reviewed_by must name the reviewer")
        if "withdrawn" in e:
            if not e.get("reason"):
                raise EntryError(f"{where}: a withdrawn entry needs a reason")
            continue
        k = (e["cospar"], e["symbol"])
        if k in seen:
            raise EntryError(f"{where}: the same registration is at line {seen[k]}")
        seen[k] = e.get("line")
        live.append(e)
    return live


def load_entries(path: Path | str | None = None) -> list[dict]:
    p = Path(path) if path else LINKS_PATH
    if not p.exists():
        return []
    return validate_entries(parse(p.read_text(encoding="utf-8")))


def public_names(entries: list[dict], built: str) -> dict:
    """`site/data/un-register.json` (`orbit-un-register/1`): reviewed entries only, by COSPAR id."""
    by: dict[str, list] = {}
    for e in entries:
        if not e.get("reviewed_by"):
            continue
        row = {k: e[k] for k in ("name", "state", "symbol", "link", "read", "reviewed")}
        for k in ("gso", "note"):
            if e.get(k) is not None:
                row[k] = e[k]
        by.setdefault(e["cospar"], []).append(row)
    for v in by.values():
        v.sort(key=lambda r: r["symbol"])
    return {"schema": "orbit-un-register/1", "built": built, "about": ABOUT, "credit": CREDIT, "index": INDEX_URL,
            "objects": by}
