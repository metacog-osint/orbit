"""The satellite map's data (orbit-2.23, ideas#71, Tom's yes to the design 20 Nov 2026): CelesTrak's GP "active" group
(working satellites, the 18th Space Defense Squadron's GP data) once a UTC day, joined to GCAT by NORAD number for the
owner, type and launch date, written as one compact file the home page's map draws with SGP4.

CelesTrak's usage policy (read 20 Nov 2026, updated 16 Nov 2026): request compressed data, use FORMAT=csv (JSON is
about three times the size), download once per update (GP data update every 2 hours), and stop at any non-200 reply
and leave it for a person. It states no redistribution or credit terms; the sets are credited as CelesTrak, from 18 SDS
data, as the `paths` lane does. Orbit asks once a UTC day. Any reply but 200 (redirects are not followed) is recorded
in data/state/sats_stop.json: the last file stays and the lane asks nothing more until a person clears the stop by
committing the stop's time to orbit/sats_stop_clear.txt. A timeout gets no reply, so it is not a stop and the next run
asks again. Standard library only."""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from orbit import catsources

URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=csv"
SCHEMA = "orbit-sats/1"
CREDIT = "Element sets: CelesTrak (celestrak.org), GP group 'active', from the 18th Space Defense Squadron's GP data"
FIELDS = ["norad", "name", "cospar", "group", "cc", "type", "launch", "cls", "con",
          "epoch", "n", "e", "i", "raan", "argp", "ma", "bstar", "ndot"]
# Constellations named by CelesTrak's object name. Only families whose names say so: GLONASS satellites are named
# COSMOS nnnn with the series in brackets ("COSMOS 2433 [GLONASS-M]"); Guowang's are HULIANWANG DIGUI-nn (China SatNet's
# test satellites, HULIANWANG JISHU SHIYAN, are not counted); Qianfan's are QIANFAN-n or "QIANFAN 16 OBJECT A".
CONSTELLATIONS = [("glonass", re.compile(r"\[GLONASS\b")), ("guowang", re.compile(r"^HULIANWANG DIGUI\b")),
                  ("qianfan", re.compile(r"^QIANFAN\b")),
                  ("starlink", re.compile(r"^STARLINK\b")), ("oneweb", re.compile(r"^ONEWEB\b")),
                  ("kuiper", re.compile(r"^KUIPER\b")), ("iridium", re.compile(r"^IRIDIUM\b")),
                  ("gps", re.compile(r"^NAVSTAR\b")), ("beidou", re.compile(r"^BEIDOU\b")),
                  ("galileo", re.compile(r"^GSAT0\d|GALILEO"))]
BIG = {"US": "us", "CN": "cn", "RU": "ru"}
CLEAR_FILE = Path(__file__).with_name("sats_stop_clear.txt")  # a person commits the stop's time here to clear it


class Stopped(RuntimeError):
    """CelesTrak answered with something other than 200: the lane asks nothing until a person clears it."""


def stop_message(stop: dict) -> str:
    return (f"CelesTrak answered HTTP {stop.get('code')} at {stop.get('at')}; "
            "Orbit asks nothing more until a person clears the stop")


def record_stop(path: Path, code, url: str, at: str) -> dict:
    stop = {"code": code, "url": url, "at": at}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stop) + "\n", encoding="utf-8", newline="\n")
    return stop


def check_stop(path: Path, now: str) -> None:
    """Raise Stopped while a stop stands. CLEAR_FILE holding that stop's exact time clears it, so an old clear can never
    lift a later stop; the cleared record moves to sats_stop_history.jsonl. An unreadable record still stops the lane."""
    if not path.exists():
        return
    try:
        stop = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        stop = {"code": "unknown", "at": "unknown"}
    cleared = CLEAR_FILE.read_text(encoding="utf-8").strip() if CLEAR_FILE.exists() else ""
    if cleared != stop.get("at"):
        raise Stopped(stop_message(stop))
    with path.with_name("sats_stop_history.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({**stop, "cleared_at": now}) + "\n")
    path.unlink()


def get(url: str = URL, timeout: int = 240) -> bytes:
    """One compressed request, as CelesTrak asks, no redirects followed. Any status but 200 raises catsources.Refused,
    which the lane records as a stop."""
    return catsources.get("celestrak-gp-active", url, "text/csv", timeout)


def orbit_class(n: float, e: float) -> str:
    """From mean motion n (revolutions a day) and eccentricity e (rules in doctrine/method.md, "The satellite map"):
    HEO from e 0.25; LEO under 128 min a revolution (n above 11.25); GEO-like at n 0.9-1.1 (a period of about a
    sidereal day, inclined orbits included); MEO between; 'other' beyond (n under 0.9)."""
    if e >= 0.25:
        return "heo"
    if n > 11.25:
        return "leo"
    if 0.9 <= n <= 1.1:
        return "geo"
    if n > 1.1:
        return "meo"
    return "other"


def constellation(name: str) -> str | None:
    for key, rx in CONSTELLATIONS:
        if rx.search(name):
            return key
    return None


def gcat_by_norad(index_doc: dict | None) -> dict[str, dict]:
    """GCAT's index (tools/orbit.py writes it each catalog reading) by NORAD number: owner state, type, launch date."""
    from orbit import gcat
    out = {}
    for row in ((index_doc or {}).get("objects") or {}).values():
        o = dict(zip(gcat.INDEX_FIELDS, row))
        if o.get("norad"):
            out[str(o["norad"])] = o
    return out


def _f(v: str, nd: int) -> float:
    return round(float(v), nd)


def parse(body: bytes, index_doc: dict | None, read_at: str) -> dict:
    """CelesTrak's CSV to Orbit's compact file. A row SGP4 cannot use (a missing number) is counted, not kept."""
    from orbit import gcat
    text = body.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    need = {"OBJECT_NAME", "OBJECT_ID", "EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE",
            "ARG_OF_PERICENTER", "MEAN_ANOMALY", "NORAD_CAT_ID"}
    if not reader.fieldnames or not need <= set(reader.fieldnames):
        raise ValueError(f"CelesTrak CSV header is not GP's: {text[:200]!r}")
    by_norad = gcat_by_norad(index_doc)
    rows, unusable, joined = [], 0, 0
    for r in reader:
        try:
            norad = str(int(r["NORAD_CAT_ID"]))
            n, e = float(r["MEAN_MOTION"]), float(r["ECCENTRICITY"])
            nums = [_f(r["INCLINATION"], 4), _f(r["RA_OF_ASC_NODE"], 4), _f(r["ARG_OF_PERICENTER"], 4),
                    _f(r["MEAN_ANOMALY"], 4), float(r.get("BSTAR") or 0), float(r.get("MEAN_MOTION_DOT") or 0)]
            if not r["EPOCH"] or n <= 0:
                raise ValueError("no epoch or mean motion")
        except (TypeError, ValueError, KeyError):
            unusable += 1
            continue
        g = by_norad.get(norad)
        state = (g or {}).get("state") or ""
        cc = gcat.iso_country(state) if g else None
        group = "ru" if state == "SU" else BIG.get(cc or "", "other")
        launch = gcat.vague_date(g["ldate"])["date"] if g and g.get("ldate") else None
        joined += 1 if g else 0
        name = (r["OBJECT_NAME"] or "").strip()
        rows.append([int(norad), name, r["OBJECT_ID"], group, cc or (state or None), (g or {}).get("type"), launch,
                     orbit_class(n, e), constellation(name), r["EPOCH"][:23], round(n, 8), round(e, 7), *nums])
    rows.sort(key=lambda x: x[0])
    counts = {}
    for x in rows:
        counts[x[7]] = counts.get(x[7], 0) + 1
    return {"schema": SCHEMA, "read_at": read_at, "source": "celestrak-gp-active", "url": URL, "credit": CREDIT,
            "count": len(rows), "unusable": unusable, "gcat_joined": joined, "by_class": dict(sorted(counts.items())),
            "fields": FIELDS, "rows": rows}


def summary(doc: dict) -> dict:
    """What the snapshot keeps: the file's size and counts, not its rows."""
    return {k: doc[k] for k in ("read_at", "source", "url", "credit", "count", "unusable", "gcat_joined", "by_class")}
