"""CelesTrak's last-30-days GP group: element sets for the payloads of recent launches (orbit-2.12, 16 Nov
2026), so the globe can draw their paths in the days before Orbit holds a Space-Track set for them. Space-Track stays
the source for the satellites Orbit watches; this is for new payloads' paths only, never for orbit changes.

One request a run (Orbit runs about every six hours). CelesTrak's usage policy (read 16 Nov 2026, updated that day):
"only download data once per update"; GP data updates every 2 hours; a repeat download inside an update gets HTTP 403,
and repeating a 403 or 404 doesn't change it. The policy states no redistribution or credit terms. CelesTrak's GP
data are the 18th Space Defense Squadron's GP sets, so they are credited as both, as Orbit credits Space-Track's.
Standard library only."""
from __future__ import annotations

import json
import re

URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=json"
SITE = "https://celestrak.org"
CREDIT = "Element sets: CelesTrak (celestrak.org), from the 18th Space Defense Squadron's GP data"
_TAG = re.compile(r"^(\d{4}-\d{3})[A-Z]{1,3}$")
# Not payloads: rocket bodies, debris, and named platforms or adapters left in orbit.
_NOT_PAYLOAD = re.compile(r"\bR/B\b|\bDEB\b|\bROCKET\b|\bPLATFORM\b|\bAKM\b|\bPAM\b", re.I)


def _num(row: dict, key: str) -> float:
    v = row.get(key)
    if v is None or v == "":
        raise ValueError(f"no {key}")
    return float(v)


def elements(row: dict) -> dict:
    """The fields globe.js needs from one CelesTrak GP row (OMM JSON), as the maneuver lane writes Space-Track's."""
    return {"epoch": row["EPOCH"], "n": _num(row, "MEAN_MOTION"), "e": _num(row, "ECCENTRICITY"),
            "i": _num(row, "INCLINATION"), "raan": _num(row, "RA_OF_ASC_NODE"),
            "argp": _num(row, "ARG_OF_PERICENTER"), "ma": _num(row, "MEAN_ANOMALY")}


def parse(body: bytes, launches: list[dict]) -> dict:
    """Keep the sets for objects of the launches in `launches` (GCAT's recent launches, by launch tag): every object
    GCAT lists as a payload of that launch, and, while GCAT hasn't listed them, any other object of the launch whose
    name doesn't mark it as a rocket body or debris (CelesTrak's "OBJECT A" names included)."""
    rows = json.loads(body.decode("utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"CelesTrak reply is not a list: {str(rows)[:200]}")
    tags = {x["launch_tag"] for x in launches if x.get("launch_tag")}
    payload_norads = {str(p["norad"]) for x in launches for p in x.get("payloads") or [] if p.get("norad")}
    by_launch: dict[str, list[dict]] = {}
    skipped = 0
    for r in rows:
        m = _TAG.match(str(r.get("OBJECT_ID") or ""))
        if not m or m.group(1) not in tags:
            continue
        norad = str(r.get("NORAD_CAT_ID") or "")
        name = str(r.get("OBJECT_NAME") or "").strip()
        listed = norad in payload_norads
        if not listed and _NOT_PAYLOAD.search(name):
            continue
        try:
            el = elements(r)
        except (KeyError, ValueError):
            skipped += 1
            continue
        by_launch.setdefault(m.group(1), []).append(
            {"norad": norad, "name": name, "cospar": r["OBJECT_ID"], "gcat_payload": listed, "elements": el})
    for v in by_launch.values():
        v.sort(key=lambda o: o["cospar"])
    return {"source": "celestrak-gp", "url": URL, "credit": CREDIT, "objects_in_group": len(rows),
            "sets": sum(len(v) for v in by_launch.values()), "unusable": skipped,
            "by_launch": dict(sorted(by_launch.items()))}
