"""When a watched place was last imaged by Landsat and Sentinel, and when Landsat is next due over it (orbit-2.52).

Three answers per place, each from what a public source lists, never from a pass prediction:
- **Last acquired**: the newest scene a public catalogue lists over the place: USGS LandsatLook STAC (Landsat
  Collection 2 Level-1) and Copernicus Data Space STAC (Sentinel-2 L1C, Sentinel-1 GRD).
- **Landsat next due**: the days in the next 16 on which Landsat 8 or 9 flies a WRS-2 path that has imaged the place
  in daylight in the last 32 days, on USGS's nominal acquisition calendar (`cycles_full.json`, the file USGS's
  "Landsat Acquisition Tool" reads). The calendar repeats every 16 days, so its last 16 published days are carried
  forward; every daylight scene read is checked against it, and a place with any scene off the calendar gets
  "unknown", not a date.
- **Sentinel planned**: always "not published here". ESA's acquisition-plan files are not used until it is settled
  which ESA terms cover them.

It never says a place was or was not imaged outside these catalogues, who asked for a scene, or that a due date will
be kept. Standard library only.
"""
from __future__ import annotations

import json
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PLACES = Path(__file__).resolve().parent / "data" / "imaging-places.json"
CALENDAR_URL = "https://landsat.usgs.gov/sites/default/files/landsat_acq/assets/json/cycles_full.json"
LANDSAT_STAC = "https://landsatlook.usgs.gov/stac-server/search"
CDSE_STAC = "https://stac.dataspace.copernicus.eu/v1/search"
SEARCHES = (  # (key, source id, search URL, collection)
    ("landsat", "usgs-landsatlook-stac", LANDSAT_STAC, "landsat-c2l1"),
    ("sentinel2", "cdse-stac", CDSE_STAC, "sentinel-2-l1c"),
    ("sentinel1", "cdse-stac", CDSE_STAC, "sentinel-1-grd"),
)
LOOKBACK_DAYS = 32      # two Landsat cycles: the paths that imaged a place in daylight
AHEAD_DAYS = 16         # one Landsat cycle ahead, as USGS's own calendar shows
CALENDAR_MAX_AGE = 7    # days before the calendar file is read again
PAUSE = 1.0             # seconds between catalogue searches, in series
PLATFORMS = {"LANDSAT_8": "landsat_8", "LANDSAT_9": "landsat_9"}
CREDIT = {
    "landsat": "U.S. Geological Survey (Landsat, public domain)",
    "sentinel": "Copernicus Sentinel data {year} (catalogue: Copernicus Data Space Ecosystem, ESA)",
}
SENTINEL_PLAN = "not published here"
SENTINEL_PLAN_WHY = ("ESA publishes Sentinel-1 and -2 acquisition plans, but which of ESA's terms cover those files "
                     "is not settled, so Orbit shows no planned Sentinel dates.")


def load_places(path: Path = PLACES) -> list[dict]:
    """The reviewed place list. Each place has id, name, lat, lon and the source of its position."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    places = doc["places"]
    seen = set()
    for p in places:
        if p["id"] in seen:
            raise ValueError(f"place id {p['id']} twice in {path.name}")
        seen.add(p["id"])
        if not (-90 <= p["lat"] <= 90 and -180 <= p["lon"] <= 180):
            raise ValueError(f"place {p['id']}: position out of range")
        if not p.get("source"):
            raise ValueError(f"place {p['id']}: no source for its position")
    return places


def search_url(base: str, collection: str, lat: float, lon: float, since: str, limit: int = 20) -> str:
    point = json.dumps({"type": "Point", "coordinates": [lon, lat]}, separators=(",", ":"))
    q = {"collections": collection, "intersects": point, "limit": limit,
         "sortby": "-properties.datetime", "datetime": f"{since}/.."}
    return base + "?" + urllib.parse.urlencode(q)


def _day(s: str) -> date:
    return datetime.strptime(s, "%m/%d/%Y").date()


def parse_calendar(body: bytes) -> dict:
    """USGS's calendar to {platform: {"through": date, "template": {offset 0-15: set of paths}, "anchor": date}}.

    The last 16 published days are the template; any later day d uses template[(d - anchor) % 16]. Refuses a file
    whose 16-day repeat does not hold over its own published days."""
    doc = json.loads(body)
    out = {}
    for plat in PLATFORMS.values():
        rows = doc.get(plat)
        if not rows:
            raise ValueError(f"calendar has no {plat}")
        days = {_day(k): frozenset(int(x) for x in str(v.get("path", "")).split(",") if x.strip())
                for k, v in rows.items()}
        for d, paths in days.items():
            nxt = d + timedelta(days=16)
            if nxt in days and days[nxt] != paths:
                raise ValueError(f"{plat} calendar does not repeat every 16 days at {d.isoformat()}")
        through = max(days)
        anchor = through - timedelta(days=15)
        template = {}
        for i in range(16):
            d = anchor + timedelta(days=i)
            if d not in days:
                raise ValueError(f"{plat} calendar is missing {d.isoformat()}")
            template[i] = days[d]
        out[plat] = {"through": through, "anchor": anchor, "template": template}
    return out


def paths_on(cal: dict, plat: str, d: date) -> frozenset:
    c = cal[plat]
    return c["template"][(d - c["anchor"]).days % 16]


def _scene(f: dict) -> dict:
    p = f.get("properties") or {}
    out = {"id": f.get("id"), "datetime": p.get("datetime"), "platform": p.get("platform")}
    for src, dst in (("eo:cloud_cover", "cloud_cover"), ("view:sun_elevation", "sun_elevation"),
                     ("sar:instrument_mode", "mode"), ("sat:orbit_state", "orbit_state"),
                     ("landsat:wrs_path", "wrs_path"), ("landsat:wrs_row", "wrs_row")):
        if p.get(src) is not None:
            out[dst] = round(p[src], 1) if isinstance(p[src], float) else p[src]
    return out


def _daylight(s: dict) -> bool:
    sun = s.get("sun_elevation")
    return sun is not None and sun > 0


def landsat_due(scenes: list[dict], cal: dict, today: date) -> dict:
    """Landsat's next due days over a place from its daylight scenes of the last 32 days and the calendar."""
    since = today - timedelta(days=LOOKBACK_DAYS)
    seen, off = set(), []
    for s in scenes:
        plat = PLATFORMS.get((s.get("platform") or "").upper())
        if not plat or not _daylight(s) or not s.get("datetime") or s.get("wrs_path") is None:
            continue
        d = datetime.fromisoformat(s["datetime"].replace("Z", "+00:00")).date()
        if d < since:
            continue
        path = int(s["wrs_path"])
        if path in paths_on(cal, plat, d):
            seen.add((plat, path))
        else:
            off.append(s["id"])
    through = min(c["through"] for c in cal.values()).isoformat()
    if off:
        return {"status": "unknown", "why": "a scene read does not match the calendar", "off_calendar": off,
                "calendar_through": through}
    if not seen:
        return {"status": "unknown", "why": f"no daylight Landsat scene listed in the last {LOOKBACK_DAYS} days",
                "calendar_through": through}
    due = []
    for i in range(1, AHEAD_DAYS + 1):
        d = today + timedelta(days=i)
        for plat, path in sorted(seen):
            if path in paths_on(cal, plat, d):
                due.append({"date": d.isoformat(), "platform": plat.replace("_", " ").title(), "wrs_path": path})
    return {"status": "on calendar" if due else "not on calendar", "due": due,
            "paths": [{"platform": p.replace("_", " ").title(), "wrs_path": n} for p, n in sorted(seen)],
            "calendar_through": through}


def read(places: list[dict], getter, cal: dict, now: datetime, pause=time.sleep) -> tuple[dict, list[dict]]:
    """Search each catalogue once per place, in series. Any failed search raises: the lane keeps its last copy."""
    today = now.date()
    since = (today - timedelta(days=LOOKBACK_DAYS)).isoformat() + "T00:00:00Z"
    out, calls = [], []
    first = True
    for place in places:
        row = {k: place[k] for k in ("id", "name", "lat", "lon", "kind", "country") if k in place}
        for key, source_id, base, coll in SEARCHES:
            if not first:
                pause(PAUSE)
            first = False
            url = search_url(base, coll, place["lat"], place["lon"], since)
            body = getter(url, 60)
            calls.append({"source_id": source_id, "url": url, "bytes": len(body)})
            feats = json.loads(body).get("features")
            if feats is None:
                raise ValueError(f"{coll} search for {place['id']} returned no feature list")
            scenes = sorted((_scene(f) for f in feats), key=lambda s: s.get("datetime") or "", reverse=True)
            entry = {"last_acquired": scenes[0] if scenes else None,
                     "scenes_listed": len(scenes), "since": since}
            if key == "landsat":
                entry["next"] = landsat_due(scenes, cal, today)
            else:
                entry["planned"] = SENTINEL_PLAN
            row[key] = entry
        out.append(row)
    doc = {"read_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "method": "orbit-2.52", "places": out,
           "credit": {k: v.format(year=now.year) for k, v in CREDIT.items()}, "sentinel_plan": SENTINEL_PLAN_WHY,
           "lookback_days": LOOKBACK_DAYS, "ahead_days": AHEAD_DAYS}
    return doc, calls


def summary(doc: dict) -> dict:
    places = doc.get("places") or []
    return {"read_at": doc.get("read_at"), "places": len(places),
            "landsat_due": sum(1 for p in places if ((p.get("landsat") or {}).get("next") or {}).get("due")),
            "landsat_unknown": sum(1 for p in places
                                   if ((p.get("landsat") or {}).get("next") or {}).get("status") == "unknown")}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
