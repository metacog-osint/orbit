"""Build Orbit's contract-v2 feed (tic-feed/2, GeoJSON) from the snapshot.

Every item is an observation (measured or reported, no judgment) at tier "routine": Orbit has no baseline
of its own readings yet, so nothing is called an anomaly, and the manoeuvre lane is not live (see
doctrine/method.md). Items:
  - orbital launches GCAT dates in the last 7 days (one item each, at the launch site);
  - launches scheduled in the next 14 days (Launch Library 2, one item each, at the pad);
  - reentries GCAT dates in the last 7 days (one summary item, off-map);
  - catalog changes since Orbit's previous reading: new objects from launches more than 30 days old (one item
    per launch), and owner or state changes (one item).
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))
from tic_doctrine import CONTRACT, geo  # noqa: E402

SITE = "https://orbit.theintelligence.company"
METHOD = "orbit-2.4"
LANGUAGE_KEY = "https://github.com/metacog-osint/tic-doctrine/blob/main/docs/language-key.md"
LAUNCH_DAYS = 7
REENTRY_DAYS = 7

SRC_GCAT = {
    "id": "gcat-mcdowell",
    "publisher": "Jonathan McDowell (GCAT)",
    "title": "General Catalog of Artificial Space Objects",
    "url": "https://planet4589.org/space/gcat/",
    "licence": "CC BY 4.0. Data from GCAT (J. McDowell, planet4589.org/space/gcat)",
    "grade": "A2",
    "independence_group": "gcat",
    "source_type": "registry",
}
SRC_LL2 = {
    "id": "ll2-thespacedevs",
    "publisher": "The Space Devs (Launch Library 2)",
    "title": "Launch Library 2: upcoming launches",
    "url": "https://thespacedevs.com/llapi",
    "licence": "Free access stated by The Space Devs; no data licence stated (read 13 Nov 2026)",
    "grade": "B2",
    "independence_group": "thespacedevs",
    "source_type": "aggregator",
}


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _base(generated: str, valid_hours: int = 48) -> dict:
    return {
        "contract": CONTRACT,
        "program": "orbit",
        "kind": "observation",
        "tier": "routine",
        "status": "actual",
        "msg_type": "new",
        "human_review": "none",
        "us_person_data": "organizations",
        "status_class": "reported",
        "product_category": "current",
        "published_at": generated,
        "valid_until": _iso(_dt(generated) + timedelta(hours=valid_hours)),
        "pmesii_pt": ["military", "infrastructure"],
        "ascope": ["capabilities"],
        "ie_aspect": ["physical"],
        "ncf": ["provide_satellite_access"],
        "method_version": METHOD,
    }


def _countries(*codes) -> list[str]:
    return sorted({c for c in codes if c and geo.name(c)})


def _launch_item(x: dict, generated: str, accessed: str) -> dict:
    site = x.get("site") or {}
    site_cc = geo.country_at(site["lat"], site["lon"]) if site else None
    payload_ccs = [p.get("country") for p in x.get("payloads") or []]
    when = x["time"] or f"{x['date']}T00:00:00Z"
    label = x["flight"] or x["mission"] or x["launch_tag"]
    if x["flight"] and x["mission"] and x["mission"] != x["flight"]:
        label = f"{x['flight']} ({x['mission']})"
    pls = x.get("payloads") or []
    if pls:
        names = ", ".join(f"{p['name']} ({p['state']})" for p in pls[:8]) + (f" and {len(pls) - 8} more" if len(pls) > 8 else "")
        pl_text = f"GCAT has cataloged {x['payloads_cataloged']} payload(s): {names}."
    else:
        pl_text = "GCAT has not yet cataloged its payloads."
    outcome = "" if x["outcome"] == "success" else f" Outcome per GCAT: {x['outcome']}."
    props = {
        **_base(generated),
        "id": f"orbit:launch:{x['launch_tag'].lower().replace(' ', '-')}",
        "title": f"{x['kind'].capitalize()} launch: {x['vehicle']}, {label}, from {site.get('name') or x['site_code']}"
                 + ("" if x["outcome"] == "success" else f" ({x['outcome']})"),
        "summary": (f"{x['vehicle']} launched {label} from {site.get('full_name') or x['site_code']}"
                    f"{' pad ' + x['pad'] if x['pad'] else ''} at {when[:16].replace('T', ' ')} UTC"
                    f"{' (time approximate)' if x['time_uncertain'] else ''}; GCAT launch {x['launch_tag']}, "
                    f"agency {x['agency']}, category {x['category']}.{outcome} {pl_text}"),
        "data_as_of": when,
        "countries": _countries(site_cc, *(l.get("country") for l in x.get("launchers") or []), *payload_ccs),
        "requirement_ids": ["OR-PIR-2"],
        "coverage_fraction": 1.0,
        "precision_class": "approximate",
        "measures": {"payloads_cataloged": x["payloads_cataloged"]},
        "visual": {"type": "table", "url": f"{SITE}/#launch-{x['launch_tag'].replace(' ', '-')}"},
        "sources": [{**SRC_GCAT, "accessed_at": accessed}],
    }
    geom = {"type": "Point", "coordinates": [site["lon"], site["lat"]]} if site else None
    if not geom:
        props["precision_class"] = "none"
    return {"type": "Feature", "geometry": geom, "properties": props}


def _upcoming_item(x: dict, generated: str, accessed: str) -> dict:
    net = x["net"]
    end = x.get("window_end") or net
    valid = max(_dt(end) + timedelta(hours=6), _dt(generated) + timedelta(hours=6))
    mission_bits = [b for b in (x["mission_type"], x["orbit_name"]) if b]
    props = {
        **_base(generated),
        "id": f"orbit:upcoming:{x['id']}",
        "title": f"Scheduled launch: {x['name']} ({x['status']}), {net[:16].replace('T', ' ')} UTC",
        "summary": (f"Launch Library 2 lists {x['name']} for {net[:16].replace('T', ' ')} UTC "
                    f"(status {x['status_name'] or x['status']}; NET precision {x['net_precision'] or 'not given'}) "
                    f"from {x['pad']}, {x['location']}. Provider {x['provider']}."
                    + (f" Mission: {', '.join(mission_bits)}." if mission_bits else "")
                    + " A scheduled time is the provider's or press's, not Orbit's, and often moves."),
        "data_as_of": x.get("last_updated") or accessed,
        "valid_until": _iso(valid),
        "countries": _countries(x.get("pad_country"), *(x.get("provider_countries") or []),
                                geo.country_at(x["lat"], x["lon"]) if x.get("lat") is not None else None),
        "requirement_ids": ["OR-PIR-3"],
        "coverage_fraction": 1.0,
        "precision_class": "point",
        "visual": {"type": "table", "url": f"{SITE}/#upcoming"},
        "sources": [{**SRC_LL2, "url": x.get("ll2_url") or SRC_LL2["url"], "accessed_at": accessed}],
    }
    geom = {"type": "Point", "coordinates": [x["lon"], x["lat"]]} if x.get("lat") is not None else None
    if not geom:
        props["precision_class"] = "none"
    return {"type": "Feature", "geometry": geom, "properties": props}


def _reentry_item(rows: list[dict], generated: str, accessed: str, since: str) -> dict:
    by_type = Counter(r["type"] for r in rows)
    by_state = Counter(r["state"] for r in rows)
    payloads = [r for r in rows if r["type"] == "payload"]
    named = ", ".join(f"{r['name']} ({r['state']}, {r['reentry_date']})" for r in payloads[:12])
    more = f" and {len(payloads) - 12} more" if len(payloads) > 12 else ""
    props = {
        **_base(generated, 24),
        "id": f"orbit:reentries:{generated[:10]}",
        "title": f"Reentries dated by GCAT since {since}: {len(rows)} objects, {len(payloads)} payloads",
        "summary": (f"GCAT dates {len(rows)} reentries since {since} ("
                    + ", ".join(f"{n} {t}" for t, n in by_type.most_common()) + "; by owner state "
                    + ", ".join(f"{s} {n}" for s, n in by_state.most_common(6)) + ")."
                    + (f" Payloads: {named}{more}." if payloads else "")
                    + " GCAT's dates are often approximate and are revised as reports arrive."),
        "data_as_of": accessed,
        "countries": _countries(*(r.get("country") for r in rows)),
        "requirement_ids": ["OR-EEI-4"],
        "coverage_fraction": 1.0,
        "precision_class": "none",
        "measures": {"reentries": len(rows), "payloads": len(payloads)},
        "visual": {"type": "table", "url": f"{SITE}/#reentries"},
        "sources": [{**SRC_GCAT, "accessed_at": accessed}],
    }
    return {"type": "Feature", "geometry": None, "properties": props}


def _late_item(g: dict, generated: str, accessed: str, prev_at: str) -> dict:
    types = ", ".join(f"{n} {t}" for t, n in sorted(g["by_type"].items(), key=lambda kv: -kv[1]))
    names = ", ".join(f"{o['name']} ({o['jcat']})" for o in g["objects"][:10])
    props = {
        **_base(generated),
        "id": f"orbit:late-object:{g['launch_tag'].lower().replace(' ', '-')}:{accessed[:10]}",
        "title": f"New catalog entries from launch {g['launch_tag']} ({g['launch_date']}): {g['count']} ({types})",
        "summary": (f"Between Orbit's readings of {prev_at[:16].replace('T', ' ')} UTC and "
                    f"{accessed[:16].replace('T', ' ')} UTC, GCAT added {g['count']} objects ({types}) from launch "
                    f"{g['launch_tag']} of {g['launch_date']}, owner state {', '.join(g['states'])}"
                    + (f", parent object {', '.join(g['parents'])}" if g["parents"] else "") + f": {names}"
                    + (" and more" if g["count"] > 10 else "") + ". "
                    "A new entry from an old launch can be a release from a host, a breakup, or an object only now "
                    "identified; Orbit reports which objects, not why."),
        "data_as_of": accessed,
        "countries": _countries(*g["countries"]),
        "requirement_ids": ["OR-EEI-3"],
        "coverage_fraction": 1.0,
        "precision_class": "none",
        "measures": {"new_entries": g["count"]},
        "visual": {"type": "table", "url": f"{SITE}/#catalog"},
        "sources": [{**SRC_GCAT, "accessed_at": accessed}],
    }
    return {"type": "Feature", "geometry": None, "properties": props}


def _owner_item(changes: list[dict], generated: str, accessed: str, prev_at: str) -> dict:
    def fmt(c):
        f = c["fields"]
        parts = [f"{k} {f[k][0] or '-'} to {f[k][1] or '-'}" for k in ("state", "owner") if k in f]
        return f"{c['name']} ({c['jcat']}): {', '.join(parts)}"
    props = {
        **_base(generated),
        "id": f"orbit:owner-change:{accessed[:10]}",
        "title": f"Owner or owner-state changes in GCAT: {len(changes)} objects",
        "summary": (f"Between Orbit's readings of {prev_at[:16].replace('T', ' ')} UTC and "
                    f"{accessed[:16].replace('T', ' ')} UTC, GCAT changed the owner or owner state of "
                    f"{len(changes)} objects: " + "; ".join(fmt(c) for c in changes[:10])
                    + (" and more" if len(changes) > 10 else "") + ". Most are corrections, not transfers."),
        "data_as_of": accessed,
        "countries": _countries(*(c.get("country") for c in changes)),
        "requirement_ids": ["OR-EEI-3"],
        "coverage_fraction": 1.0,
        "precision_class": "none",
        "measures": {"objects": len(changes)},
        "visual": {"type": "table", "url": f"{SITE}/#catalog"},
        "sources": [{**SRC_GCAT, "accessed_at": accessed}],
    }
    return {"type": "Feature", "geometry": None, "properties": props}


def build_feed(snap: dict) -> dict:
    generated = snap["generated_at"]
    now = _dt(generated)
    cat_at = ((snap.get("lanes") or {}).get("catalog") or {}).get("fetched_at") or generated
    up_at = ((snap.get("lanes") or {}).get("upcoming") or {}).get("fetched_at") or generated
    features = []

    launch_since = (now - timedelta(days=LAUNCH_DAYS)).date().isoformat()
    for x in snap.get("launches") or []:
        if x["date"] >= launch_since:
            features.append(_launch_item(x, generated, cat_at))

    for x in snap.get("upcoming") or []:
        try:
            if _dt(x.get("window_end") or x["net"]) >= now:
                features.append(_upcoming_item(x, generated, up_at))
        except (TypeError, ValueError):
            continue

    re_since = (now - timedelta(days=REENTRY_DAYS)).date().isoformat()
    rows = [r for r in snap.get("reentries") or [] if r["reentry_date"] >= re_since]
    if rows:
        features.append(_reentry_item(rows, generated, cat_at, re_since))

    changes = snap.get("catalog_changes") or {}
    # Change items stay in the feed for two days after the reading that found them.
    if changes.get("previous_reading_at") and now - _dt(cat_at) <= timedelta(days=2):
        for g in (changes.get("late_groups") or [])[:10]:
            features.append(_late_item(g, generated, cat_at, changes["previous_reading_at"]))
        if changes.get("owner_changes"):
            features.append(_owner_item(changes["owner_changes"], generated, cat_at, changes["previous_reading_at"]))

    return {
        "type": "FeatureCollection",
        "contract": CONTRACT,
        "program": "orbit",
        "generated_at": generated,
        "method_version": METHOD,
        "licence": "GCAT data CC BY 4.0 (J. McDowell, planet4589.org/space/gcat); Launch Library 2 data from "
                   "The Space Devs (free access, no licence stated)",
        "attribution": "Orbit, The Intelligence Company. Data from GCAT (J. McDowell, planet4589.org/space/gcat) "
                       "and Launch Library 2 (The Space Devs)",
        "language_key": LANGUAGE_KEY,
        "features": features,
    }
