"""Launch's place check on Orbit's own hazard areas (orbit-2.10, Tom's "do all four", 16 Nov 2026).

Orbit's warnings table pairs a scheduled launch with a hazard area on time alone: its NET inside a window of four
hours or less, or up to an hour before one opens. Time is not place: on 13 Nov it paired a Vostochny Soyuz with
a North Atlantic debris box. The suite's Launch program (launch.theintelligence.company) already reads Orbit's
areas and scheduled launches each hour and checks place as well, so Orbit reads Launch's result rather than
keeping a second method:

  time and place  the area's centre lies inside an azimuth band (+-5 degrees) and a downrange distance seen in
                  the closure history for that pad (x0.5 - 50 NM to x1.25 + 100 NM); with no history for the pad,
                  within 1,500 NM of it
  grouped         time and place, and a GCAT launch from the same pad (within 30 NM) falls in the window
  time            the window only

Each row keeps Launch's azimuth and distance from the pad to the area's centre and the inclination that azimuth
implies. A coincidence, never a finding that an area is for a launch. One request a run, to Launch's published
snapshot; no request to any outside source.
"""
from __future__ import annotations

import json

URL = "https://launch.theintelligence.company/data/snapshot.json"
SOURCE = "orbit-navwarn"   # Launch's name for the areas it read from Orbit
LEVELS = ("grouped", "time and place", "time")   # best first
KEEP = ("launch", "launch_name", "net", "area", "window", "level", "azimuth", "distance_nm", "inclination_est",
        "place_basis", "grouped_with")


def parse(body: bytes) -> dict:
    """Launch's snapshot -> {generated_at, method_version, matches}: only its rows on Orbit's areas, the best row
    for each (launch, area) pair (an area can have several polygons), in Launch's own words."""
    doc = json.loads(body.decode("utf-8"))
    if not isinstance(doc, dict) or "matches" not in doc or not doc.get("generated_at"):
        raise ValueError("not Launch's snapshot: no matches or generated_at")
    best: dict[tuple, dict] = {}
    for m in doc.get("matches") or []:
        if m.get("area_source") != SOURCE or m.get("level") not in LEVELS or not m.get("launch") or not m.get("area"):
            continue
        row = {k: m.get(k) for k in KEEP}
        key = (row["launch"], row["area"])
        old = best.get(key)
        if old is None or _rank(row) < _rank(old):
            best[key] = row
    rows = sorted(best.values(), key=lambda r: (r["net"] or "", r["launch"], r["area"]))
    return {"generated_at": doc["generated_at"], "method_version": doc.get("method_version"), "url": URL,
            "matches": rows}


def _rank(r: dict) -> tuple:
    return (LEVELS.index(r["level"]), r.get("distance_nm") if r.get("distance_nm") is not None else 1e9)
