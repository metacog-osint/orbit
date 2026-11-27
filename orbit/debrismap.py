"""Rocket bodies and debris for the satellite map (orbit-2.51): one Space-Track GP query a UTC day, in the catalog
workflow's run (catalog.yml), written as sats-rd.json.gz on the public release `catalog` in the map's own row format.
The update run copies it to /data/sats-rd.json; the home map loads it only when its "Object type" filter asks for
rocket bodies or debris (off by default).

Why Space-Track: CelesTrak publishes no whole-catalog, rocket-body or debris GP group (its Current Data page, read
27 Nov 2026: only the FENGYUN 1C, IRIDIUM 33 and COSMOS 2251 debris clouds), so the active group (orbit/satmap.py)
holds payloads only.

Space-Track's rules (space-track.org/documentation, read 14 and 17 Nov 2026; orbit/spacetrack.py):
  - GP once an hour on the account, at a minute that is not the top or bottom of the hour. This query is the
    account's third GP query (with the update run's watch list and geo.yml's GEO region), so each of the three waits
    for the other two (spacetrack.FOR_DEBRIS, FOR_MANEUVER, FOR_GEO) and this one skips the run when either is under
    an hour old. catalog.yml starts three times a day, so a skipped run is read at the next.
  - Basic SSA data may be redistributed under USSPACECOM's blanket approval, conditioned on citation: CITATION,
    the disclaimer's wording (doctrine/spacetrack-disclaimer.md section 3).
A run makes three requests (log in, the GP query, log out), 2.5 s apart. Only objects on orbit (no decay date) with an
element set from the last 30 days, and only the columns the map draws (predicates), so the reply stays small.
Standard library only."""
from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

from . import gcat, satmap, spacetrack, stcat

SCHEMA = "orbit-sats/1"   # the same row format as sats.json, so the map reads both the same way
ASSET = "sats-rd.json.gz"
LOCAL = Path("state") / ASSET
COLUMNS = ["NORAD_CAT_ID", "OBJECT_NAME", "OBJECT_ID", "OBJECT_TYPE", "COUNTRY_CODE", "LAUNCH_DATE", "EPOCH",
           "MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY",
           "BSTAR", "MEAN_MOTION_DOT"]
URL = (stcat.BASE + "gp/OBJECT_TYPE/ROCKET%20BODY,DEBRIS/decay_date/null-val/epoch/%3Enow-30"
       "/orderby/NORAD_CAT_ID%20asc/predicates/" + ",".join(COLUMNS) + "/format/json")
TYPE = {"ROCKET BODY": "R", "DEBRIS": "D"}
CITATION = ("Element sets for rocket bodies and debris: Space-Track.org, United States Space Command (USSPACECOM), 18th "
            "Space Defense Squadron, redistributed under USSPACECOM's blanket approval for basic SSA data. Not reviewed "
            "or endorsed by USSPACECOM. Not for operational use.")
STEP = "Rocket bodies and debris (Space-Track GP, once a day)"   # catalog.yml's step name; spacetrack.CATALOG reads it


def due(now: datetime, held: dict | None) -> str | None:
    """Why not to read now (None when due): one read a UTC day, the held file's own read time being the state."""
    at = (held or {}).get("read_at") or ""
    if at[:10] == now.strftime("%Y-%m-%d"):
        return f"read already today ({at})"
    return None


def owner(code: str | None) -> tuple[str, str | None]:
    """Space-Track's COUNTRY_CODE to the map's colour group and owner code (GCAT's state, as ISO where it has one),
    so the owner filter and search treat these rows as they treat the active group's."""
    states = stcat.COUNTRY_TO_STATE.get((code or "").strip().upper())
    if not states:
        return "other", (code or None)
    state = "SU" if states == ("SU", "RU") else states[0]
    if state == "SU":
        return "ru", "SU"
    cc = gcat.iso_country(state)
    return satmap.BIG.get(cc or "", "other"), cc or state


def parse(rows: list[dict], read_at: str) -> dict:
    """Space-Track GP rows to the map's compact file. A row SGP4 cannot use (a missing number) is counted, not kept."""
    out, unusable = [], 0
    for r in rows:
        t = TYPE.get((r.get("OBJECT_TYPE") or "").upper())
        try:
            norad = int(r["NORAD_CAT_ID"])
            n, e = float(r["MEAN_MOTION"]), float(r["ECCENTRICITY"])
            nums = [round(float(r["INCLINATION"]), 4), round(float(r["RA_OF_ASC_NODE"]), 4),
                    round(float(r["ARG_OF_PERICENTER"]), 4), round(float(r["MEAN_ANOMALY"]), 4),
                    float(r.get("BSTAR") or 0), float(r.get("MEAN_MOTION_DOT") or 0)]
            if not t or not r.get("EPOCH") or n <= 0:
                raise ValueError("no type, epoch or mean motion")
        except (TypeError, ValueError, KeyError):
            unusable += 1
            continue
        group, cc = owner(r.get("COUNTRY_CODE"))
        name = (r.get("OBJECT_NAME") or "").strip()
        out.append([norad, name, r.get("OBJECT_ID"), group, cc, t, (r.get("LAUNCH_DATE") or None),
                    satmap.orbit_class(n, e), None, r["EPOCH"][:23], round(n, 8), round(e, 7), *nums])
    out.sort(key=lambda x: x[0])
    by_type, by_class = {}, {}
    for x in out:
        by_type[x[5]] = by_type.get(x[5], 0) + 1
        by_class[x[7]] = by_class.get(x[7], 0) + 1
    return {"schema": SCHEMA, "read_at": read_at, "source": "space-track-gp", "credit": CITATION,
            "query": "class gp: OBJECT_TYPE ROCKET BODY or DEBRIS, no decay date, epoch in the last 30 days",
            "count": len(out), "unusable": unusable, "by_type": dict(sorted(by_type.items())),
            "by_class": dict(sorted(by_class.items())), "fields": satmap.FIELDS, "rows": out}


def read_held(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(gzip.decompress(path.read_bytes()))
    except (OSError, ValueError):
        return None


def pull(data_dir: Path, cred: tuple[str, str], now: datetime | None = None, client=None, wait=None,
         busy=None) -> dict:
    """One GP query when due and the account is clear; writes data/state/sats-rd.json.gz. Raises
    spacetrack.NotReady when it must not ask (read today, or another GP query under an hour old)."""
    now = now or datetime.now(timezone.utc)
    path = data_dir / LOCAL
    why = due(now, read_held(path))
    if why:
        raise spacetrack.NotReady(why)
    (wait or spacetrack.wait_for_clear_minute)()
    why = (busy or (lambda t: spacetrack.shared_gp_busy(t, shared=spacetrack.FOR_DEBRIS)))(datetime.now(timezone.utc))
    if why:  # after the wait, just before the query, as the GEO region checks
        raise spacetrack.NotReady(why)
    c = client or spacetrack.Client(*cred)
    c.login()
    try:
        rows = c.query_path(URL, "gp")
    finally:
        c.logout()
    doc = parse(rows, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    if not doc["count"]:
        raise RuntimeError("Space-Track's GP reply held no usable rocket body or debris; the last file is kept")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(doc, separators=(",", ":")).encode("utf-8"), 9))
    return {"doc": doc, "requests": c.requests}
