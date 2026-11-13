"""Upcoming launches from Launch Library 2 (The Space Devs, ll.thespacedevs.com).

The Space Devs state that the whole database is free to everyone, at up to 15 requests an hour without a
key (thespacedevs.com/llapi, read 13 Nov 2026). Detailed mode (about 450 KB for two weeks) is used because only it
carries the launch provider's country. No licence for the data is stated there; Orbit credits The
Space Devs on every item and uses no images (each image carries its own licence). One request per run.

A scheduled launch is reported, not measured: kind "observation", status_class "reported".
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

API = "https://ll.thespacedevs.com/2.3.0/launches/upcoming/"
HORIZON_DAYS = 14


def url(now: datetime, days: int = HORIZON_DAYS) -> str:
    until = (now + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return API + "?" + urlencode({"limit": 100, "mode": "detailed", "net__lte": until})


def _get(d: dict | None, *path, default=None):
    for k in path:
        if not isinstance(d, dict):
            return default
        d = d.get(k)
    return d if d is not None else default


def parse(body: bytes) -> list[dict]:
    doc = json.loads(body.decode("utf-8"))
    if "results" not in doc:
        raise ValueError(f"Launch Library reply has no results: {str(doc)[:200]}")
    out = []
    for r in doc["results"]:
        pad = r.get("pad") or {}
        try:
            lat, lon = float(pad.get("latitude")), float(pad.get("longitude"))
        except (TypeError, ValueError):
            lat = lon = None
        provider_countries = [c.get("alpha_2_code") for c in _get(r, "launch_service_provider", "country", default=[])
                              if isinstance(c, dict) and c.get("alpha_2_code")]
        out.append({
            "id": r.get("id"),
            "name": r.get("name", ""),
            "net": r.get("net"),
            "net_precision": _get(r, "net_precision", "name", default=""),
            "window_start": r.get("window_start"),
            "window_end": r.get("window_end"),
            "status": _get(r, "status", "abbrev", default=""),
            "status_name": _get(r, "status", "name", default=""),
            "last_updated": r.get("last_updated"),
            "provider": _get(r, "launch_service_provider", "name", default=""),
            "provider_type": _get(r, "launch_service_provider", "type", "name", default=""),
            "provider_countries": provider_countries,
            "vehicle": _get(r, "rocket", "configuration", "full_name", default="") or _get(r, "rocket", "configuration", "name", default=""),
            "mission": _get(r, "mission", "name", default=""),
            "mission_type": _get(r, "mission", "type", default=""),
            "mission_description": (_get(r, "mission", "description", default="") or "").replace("\r\n", "\n")[:600],
            "orbit": _get(r, "mission", "orbit", "abbrev", default=""),
            "orbit_name": _get(r, "mission", "orbit", "name", default=""),
            "pad": pad.get("name", ""),
            "location": _get(pad, "location", "name", default=""),
            "pad_country": _get(pad, "location", "country", "alpha_2_code", default=None)
                           or _get(pad, "country", "alpha_2_code", default=None),
            "lat": lat,
            "lon": lon,
            "ll2_url": r.get("url"),
        })
    out.sort(key=lambda x: (x["net"] or "", x["name"]))
    return out


def within(launches: list[dict], now: datetime, days: int = HORIZON_DAYS) -> list[dict]:
    """Launches whose window has not closed and whose NET is within `days` days of now."""
    until = now + timedelta(days=days)
    keep = []
    for x in launches:
        try:
            net = datetime.fromisoformat((x["net"] or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        end = x.get("window_end") or x["net"]
        try:
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            end_dt = net
        if end_dt >= now and net <= until:
            keep.append(x)
    return keep


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
