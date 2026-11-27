"""Build Orbit's contract-v2 feed (tic-feed/2, GeoJSON) from the snapshot.

Every item is an observation (measured or reported, no judgment). Most are tier "routine"; from orbit-2.49 two kinds
can be tier "anomaly", each against a baseline from GCAT's own history (doctrine/method.md, "Anomalies against
GCAT's history"): a 30-day count outside every one of its 24 prior windows, and a breakup or collision for 72 hours
from the reading that first listed it. Items:
  - orbital launches GCAT dates in the last 7 days (one item each, at the launch site);
  - reentries GCAT dates in the last 7 days (one summary item, off-map);
  - catalog changes since Orbit's previous reading: new objects from launches more than 30 days old (one item
    per launch), and owner or state changes (one item);
  - orbit changes in watched objects listed on the page (Space-Track element sets, last 30 days; one item each,
    off-map), kind "maneuver" (Tom, 14 Nov 2026). COP's gate holds this kind as military context;
  - 30-day counts outside every prior window (orbit-2.49; one item per series, off-map, tier anomaly);
  - GEO relocations of listed-role objects (orbit-2.30, ideas#323): one item per move, updated in place, off-map,
    from the GEO page's tracker (tools/geo_tracker.py). tools/geo_page.py adds them to site/data/feed.geojson after
    the tracker runs, since the tracker is built after the feed in the same run (relocation_features below).
Scheduled launches (orbit:upcoming:*, Launch Library 2) left the feed in orbit-2.32: Launch's feed carries them as
launch:upcoming:* (ideas#69).
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))
from tic_doctrine import CONTRACT, __version__ as KIT_VERSION, geo  # noqa: E402

from orbit import names, notable  # noqa: E402

SITE = "https://orbit.theintelligence.company"
METHOD = "orbit-2.32"
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


SRC_ST = {
    "id": "space-track",
    "publisher": "Space-Track.org (United States Space Command, USSPACECOM, 18th Space Defense Squadron)",
    "title": "GP and GP_HISTORY element sets for a watch list",
    "url": "https://www.space-track.org/",
    "grade": "A2",
    "independence_group": "usspacecom",
    "source_type": "registry",
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


def _floor(iso: str, precision: str | None) -> str:
    """A time at the start of its period, as the contract's event_time_precision reads it."""
    if precision == "month":
        return f"{iso[:7]}-01T00:00:00Z"
    if precision == "day":
        return f"{iso[:10]}T00:00:00Z"
    if precision == "hour":
        return f"{iso[:13]}:00:00Z"
    return iso


def _day(value) -> str | None:
    text = str(value or "")[:10]
    return f"{text}T00:00:00Z" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else None


def _change(kind: str, at: str | None, generated: str) -> dict:
    """last_change from the source's own date, never after this build. Orbit keeps no log of its feed items, so an
    item says what its source dates: a launch, a breakup or an orbit change is new at its own time, a catalog change
    at the reading that found it, and the rolling reentry count changed when last added to."""
    return {"last_change": kind, "last_change_at": min(at, generated)} if at else {"last_change": "none"}


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
        "subject_id": f"orbit:launch:{x['launch_tag'].lower().replace(' ', '-')}",
        "event_start": _floor(when, "day") if not x["time"] or x["time_uncertain"] else when,
        **({"event_time_precision": "day"} if not x["time"] or x["time_uncertain"] else {}),
        **_change("new", when, generated),
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
        "visual": {"type": "table", "url": f"{SITE}/launches#launch-{x['launch_tag'].replace(' ', '-')}"},
        "sources": [{**SRC_GCAT, "accessed_at": accessed}],
    }
    geom = {"type": "Point", "coordinates": [site["lon"], site["lat"]]} if site else None
    if not geom:
        props["precision_class"] = "none"
    return {"type": "Feature", "geometry": geom, "properties": props}


def _reentry_item(rows: list[dict], generated: str, accessed: str, since: str) -> dict:
    by_type = Counter(r["type"] for r in rows)
    by_state = Counter(r["state"] for r in rows)
    payloads = [r for r in rows if r["type"] == "payload"]
    named = ", ".join(f"{r['name']} ({r['state']}, {r['reentry_date']})" for r in payloads[:12])
    more = f" and {len(payloads) - 12} more" if len(payloads) > 12 else ""
    days = sorted(d for d in (_day(r["reentry_date"]) for r in rows) if d)
    first = days[0] if days else _day(since)
    props = {
        **_base(generated, 24),
        "id": f"orbit:reentries:{generated[:10]}",
        "subject_id": "orbit:reentries:last-7-days",     # the id carries the day; the rolling count is one subject
        "event_start": first,
        **({"event_end": days[-1]} if days and days[-1] > first else {}),
        "event_time_precision": "day",
        **_change("changed", days[-1] if days else None, generated),
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
        "visual": {"type": "table", "url": f"{SITE}/reentries#reentries"},
        "sources": [{**SRC_GCAT, "accessed_at": accessed}],
    }
    return {"type": "Feature", "geometry": None, "properties": props}


BREAKUP_WORD = {"E": "exploded (broke up in orbit)", "C": "collided"}


ANOMALY_METHOD = "orbit-2.49"
ANOMALY_HOLD_HOURS = 72   # the kit's hold for an event (feed contract revision 2.1, D5)
FLAG_RATE_CAP = 0.05      # the kit's cap: a series the rule flagged on more than 5% of its baseline windows is not flagged
SMALL_COUNT = 3           # high tail: at least 3 in the recent window; low tail: at least 3 in every prior window
# (series key in gcat.baseline, tails Orbit flags). Payloads and reentries only on the high side: GCAT adds payloads
# and dates reentries as it learns of them, so a low recent window there can be lag (method "Baselines" item 3).
ANOMALY_SERIES = (("launches_all", ("high", "low")), ("launches_by_country", ("high", "low")),
                  ("launches_by_agency", ("high", "low")), ("payloads_by_owner", ("high",)),
                  ("reentries_all", ("high",)), ("reentries_by_owner", ("high",)))


def _series_label(series: str, r: dict) -> tuple[str, str]:
    """(what is counted, its unit) for one baseline row."""
    cc = r.get("country")
    place = geo.name(cc) if cc else None
    if series == "launches_all":
        return "Orbital launch attempts, all launchers", "launches"
    if series == "launches_by_country":
        return f"Orbital launch attempts with a launching agency of {place or r['key']}", "launches"
    if series == "launches_by_agency":
        return f"Orbital launch attempts by {r.get('name') or r['key']} (GCAT agency {r['key']})", "launches"
    if series == "payloads_by_owner":
        return f"Payloads launched for owner {place or r['key']} (GCAT state {r['key']})", "payloads"
    if series == "reentries_all":
        return "Reentries, all owners", "reentries"
    return f"Reentries of objects owned by {place or r['key']} (GCAT state {r['key']})", "reentries"


def _baseline_tail(r: dict, tails: tuple) -> str | None:
    """The tail this row departs on under the orbit-2.49 rule, or None."""
    fr = r.get("flag_rate")
    if not fr or r.get("prior_windows") != 24:
        return None
    if "high" in tails and r["position"] == "above" and r["recent"] >= SMALL_COUNT and fr["high"] <= FLAG_RATE_CAP:
        return "high"
    if "low" in tails and r["position"] == "below" and r["prior_min"] >= SMALL_COUNT and fr["low"] <= FLAG_RATE_CAP:
        return "low"
    return None


def _baseline_item(series: str, r: dict, tail: str, base: dict, generated: str, accessed: str) -> dict:
    """A 30-day count outside every one of its 24 prior windows (orbit-2.49): tier anomaly, against GCAT's history."""
    what, unit = _series_label(series, r)
    start, end = base["recent"]
    n = r["prior_windows"]
    fr = r["flag_rate"][tail]
    word = "more" if tail == "high" else "fewer"
    fired = round(fr * r["flag_rate"]["windows"])
    lag = (" GCAT lists a launch about one to three days after it, so the last days of the window can still fill in."
           if series.startswith("launches") and tail == "low" else "")
    each = (" A launch counts once for each country among its GCAT agencies." if series == "launches_by_country" else "")
    key = re.sub(r"[^a-z0-9-]+", "-", str(r["key"]).lower()).strip("-") or "x"
    countries = _countries(r.get("country"))
    prior = base.get("prior") or ["", ""]
    props = {
        **_base(generated, 48),
        "tier": "anomaly",
        "method_version": ANOMALY_METHOD,
        "id": f"orbit:baseline:{series}:{key}",
        "subject_id": f"orbit:baseline:{series}:{key}",
        "event_start": f"{start}T00:00:00Z",
        "event_end": f"{end}T00:00:00Z",
        "event_time_precision": "day",
        **_change("changed", accessed, generated),
        "title": (f"{what}: {r['recent']} in the last 30 days, {word} than in any of the {n} windows of 30 days "
                  "before (GCAT)"),
        "summary": (f"{what}, from GCAT's own history: {r['recent']} in the 30 days {start} to {end}, against "
                    f"{r['prior_min']} to {r['prior_max']} (median {r['prior_median']:g}) in each of the {n} windows "
                    f"of 30 days before ({prior[0]} to {prior[1]}).{each} Outside every prior window is Orbit's "
                    f"rule, a count, not a warning or a judgment of why. Over the {n} windows before those, the same "
                    f"rule fired on this series {fired} time(s) on this side.{lag}"),
        "data_as_of": accessed,
        "countries": countries,
        **({"place_basis": "subject" if series == "launches_by_country" else "named"} if countries else {}),
        "requirement_ids": ["OR-REQ-1"],
        "coverage_fraction": 1.0,
        "precision_class": "none",
        "signal": {"name": f"{what}, 30 days", "value": r["recent"], "expected": r["prior_median"], "unit": unit,
                   "tail": tail, "baseline_n": n, "exceedance": round(1 / (n + 1), 4)},
        "baseline_ref": {"id": f"gcat-30d:{series}", "type": "rolling", "version": ANOMALY_METHOD,
                         "window": f"the last 30 days against each of the {n} windows of 30 days before them",
                         "flag_rate": fr},
        "measures": {"recent": r["recent"], "prior_median": r["prior_median"], "prior_min": r["prior_min"],
                     "prior_max": r["prior_max"], "series_oldest_first": r["series"]},
        "visual": {"type": "table", "url": f"{SITE}/catalog#baseline"},
        "sources": [{**SRC_GCAT, "accessed_at": accessed}],
    }
    return {"type": "Feature", "geometry": None, "properties": props}


def baseline_features(base: dict, generated: str, accessed: str) -> list[dict]:
    """Every baseline row outside all of its prior windows under the orbit-2.49 rule. None when the baseline's
    recent window ended more than the hold before this build (GCAT unchanged for days): the count is then old."""
    if not base or not base.get("recent"):
        return []
    end = _dt(f"{base['recent'][1]}T00:00:00Z") + timedelta(days=1)
    if _dt(generated) - end > timedelta(hours=ANOMALY_HOLD_HOURS):
        return []
    out = []
    for series, tails in ANOMALY_SERIES:
        for r in base.get(series) or []:
            tail = _baseline_tail(r, tails)
            if tail:
                out.append(_baseline_item(series, r, tail, base, generated, accessed))
    return out


def _breakup_item(b: dict, generated: str, accessed: str, base: dict | None = None) -> dict:
    """One object GCAT marks as broken up (E) or collided (C) in the last 30 days (OR-EEI-5, Tom's yes 16 Nov 2026).
    Kept apart from reentries since orbit-2.12: the object did not come down; its fragments are catalogued anew."""
    word = BREAKUP_WORD.get(b.get("status"), "ended in orbit")
    when = b["breakup_date"] + (" (GCAT marks the date uncertain)" if b.get("breakup_uncertain") else "")
    parent = f", from {b['parent']}" if b.get("parent") else ""
    launched = f" Launched {b['launch_date']} ({b['launch_tag']})." if b.get("launch_date") else ""
    props = {
        **_base(generated, 48),
        "id": f"orbit:breakup:{b['jcat']}",
        "subject_id": f"orbit:breakup:{b['jcat']}",
        **({"event_start": _day(b["breakup_date"]), "event_time_precision": "day"} if _day(b["breakup_date"])
           else {"event_start": accessed}),
        **_change("new", b.get("first_listed") or _day(b["breakup_date"]) or accessed, generated),
        "title": f"{b['name']} ({b['type']}, {b['state']}) {word}, {b['breakup_date']} (GCAT)",
        "summary": (f"GCAT gives {b['name']} ({b['jcat']}{', NORAD ' + str(b['norad']) if b.get('norad') else ''}"
                    f"{parent}) status {b.get('status')}: {word}, on {when}.{launched} Orbit class "
                    f"{b.get('op_orbit') or 'not given'}. This is GCAT's record, not a reentry; any fragments get "
                    "their own catalog entries, which Orbit's catalog-change items count. GCAT's dates are often "
                    "approximate and are revised as reports arrive."),
        "data_as_of": accessed,
        "countries": _countries(b.get("country")),
        "requirement_ids": ["OR-EEI-5"],
        "coverage_fraction": 1.0,
        "precision_class": "none",
        "measures": {"status": b.get("status"), "breakup_date": b["breakup_date"],
                     "uncertain": bool(b.get("breakup_uncertain"))},
        "visual": {"type": "table", "url": f"{SITE}/catalog#breakups"},
        "sources": [{**SRC_GCAT, "accessed_at": accessed}],
    }
    listed = b.get("first_listed")
    if listed and timedelta(0) <= _dt(generated) - _dt(listed) <= timedelta(hours=ANOMALY_HOLD_HOURS):
        # orbit-2.49: a breakup or collision is rare in GCAT's record; tier anomaly for 72 hours from the reading
        # that first listed it, then routine. The record it is set against is stated in the item.
        row = next(iter((base or {}).get("breakups_all") or []), None)
        before = sum(row["series"][:-1]) if row else 0
        span = (base or {}).get("prior")
        within = f" ({span[0]} to {span[1]})" if span else ""
        props["tier"] = "anomaly"
        props["method_version"] = ANOMALY_METHOD
        props["baseline_ref"] = {"id": "gcat-breakups", "type": "rolling", "version": ANOMALY_METHOD,
                                 "window": "GCAT's breakups and collisions (status E or C) in the 24 windows of 30 "
                                           "days before the last 30 days"}
        props["measures"]["breakups_in_prior_24_windows"] = before
        props["summary"] += (f" GCAT dates {before} breakup(s) or collision(s) in the 24 windows of 30 days before "
                             f"the last 30{within}. Orbit calls a breakup an anomaly for {ANOMALY_HOLD_HOURS} hours "
                             f"from the reading that first listed it ({listed}).")
    return {"type": "Feature", "geometry": None, "properties": props}


def _late_item(g: dict, generated: str, accessed: str, prev_at: str) -> dict:
    types = ", ".join(f"{n} {t}" for t, n in sorted(g["by_type"].items(), key=lambda kv: -kv[1]))
    names = ", ".join(f"{o['name']} ({o['jcat']})" for o in g["objects"][:10])
    props = {
        **_base(generated),
        "id": f"orbit:late-object:{g['launch_tag'].lower().replace(' ', '-')}:{accessed[:10]}",
        "subject_id": f"orbit:late-object:{g['launch_tag'].lower().replace(' ', '-')}",
        "event_start": prev_at,                          # the two readings between which GCAT added the entries
        "event_end": accessed,
        **_change("new", accessed, generated),
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
        "visual": {"type": "table", "url": f"{SITE}/catalog#catalog"},
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
        "subject_id": "orbit:owner-change:gcat",
        "event_start": prev_at,
        "event_end": accessed,
        **_change("new", accessed, generated),
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
        "visual": {"type": "table", "url": f"{SITE}/catalog#catalog"},
        "sources": [{**SRC_GCAT, "accessed_at": accessed}],
    }
    return {"type": "Feature", "geometry": None, "properties": props}


def _lon(x: float) -> str:
    x = ((x + 180) % 360) - 180
    return f"{abs(x):.2f} {'E' if x >= 0 else 'W'}"


def _maneuver_item(e: dict, generated: str, read_at: str, attribution: str) -> dict:
    """Off the map (geometry null): where to draw a satellite on COP's map is Tom's open decision (ground tracks)."""
    name = e.get("gcat_name") or e["name"]
    also = e.get("names") or []          # the other names the object goes by (orbit/names.py, orbit-2.26)
    shown = names.label(name, also)
    note = e.get("notable")              # orbit/notable.py: a listed-role GEO object, not station-keeping
    owner = e.get("state") or e.get("country") or "unknown owner"
    t = lambda s: s[:16].replace("T", " ")
    gap = e.get("gap")
    if gap:
        when = f"somewhere inside a {gap['hours']:g}-hour gap between element sets ({t(gap['from'])} to {t(gap['to'])} UTC)"
        if (gap["from"], gap["to"]) != (e["from"], e["to"]):
            when += f"; the change as measured spans {t(e['from'])} to {t(e['to'])} UTC"
    else:
        when = f"between {t(e['from'])} and {t(e['to'])} UTC"
    g = e.get("geo")
    geo_text = (f" Geostationary longitude {_lon(g['lon_before'])} before and {_lon(g['lon_after'])} after, drift "
                f"{g['drift_before']:+.3f} to {g['drift_after']:+.3f} deg/day." if g else "")
    what = notable.text(e.get("what"))   # what happened, in words, for a geostationary change
    moved = bool(what) and (g or {}).get("kind") not in (None, notable.KEPT)
    lead_in = f"{name} {what}. " if what else ""
    if moved:
        lead_in += ("Drift is how far along the belt the satellite moves each day; an orbit above geostationary "
                    "altitude circles slower than the Earth turns, so the satellite falls back to the west, and one "
                    "below it runs ahead to the east. ")
    if also:
        lead_in += (f"Also known as {'; '.join(also)} (names from the TIC catalog; the object's page on Orbit says "
                    "which source gives which). ")
    if note:
        lead_in += (f"Orbit marks this change as notable: the object has a listed role on Orbit's GEO page "
                    f"({note.get('role_text') or note['role']}"
                    + (f"; basis: {note['basis']}" if note.get("basis") else "") + ") and the change is not "
                    "station-keeping. Notable is not a tier, a warning or a judgment of why. ")
    title_what = (f": {g['kind']} {'east' if g['drift_after'] > 0 else 'west'} at {abs(g['drift_after']):.2f} deg/day "
                  f"from {_lon(g['lon_before'])};" if moved and g["kind"] == notable.STARTED else
                  f": {g['kind']} at {_lon(g['lon_after'])};" if moved and g["kind"] == notable.STOPPED else
                  f": {g['kind']}, {g['drift_before']:+.2f} to {g['drift_after']:+.2f} deg/day;" if moved else ",")
    props = {
        **_base(generated),
        "id": f"orbit:maneuver:{e['norad']}:{e['from'][:10]}",
        "subject_id": f"orbit:maneuver:{e['norad']}:{e['from'][:10]}",   # one change of one object; its date is its identity
        "event_start": e["from"],
        "event_end": e["to"],
        **_change("new", e["to"], generated),
        "title": (f"{'Notable orbit change' if note else 'Orbit change'}: {shown} ({e['regime'] or 'orbit unknown'}, "
                  f"{owner}){title_what} {e['dv_ms']:g} m/s {e['dominant']}"),
        "summary": (f"{lead_in}{name} (catalog {e['norad']}, {e['object_id']}, owner {owner}): its published orbit changed by "
                    f"about {e['dv_ms']:g} m/s, mostly {e['dominant']}, semi-major axis {e['da_km']:+g} km"
                    + (f" (about {e['dv_sma_ms']:g} m/s from that change alone)" if e.get("dv_sma_ms") is not None else "")
                    + ", "
                    f"inclination {e['di_deg']:+g} deg, {when}.{geo_text} A listed change means the object's "
                    "published orbit moved more than its element sets usually move; it is not a confirmed manoeuvre, "
                    "a statement of intent or a warning. Velocities are differences between published orbits, not "
                    "burn records. " + attribution),
        "data_as_of": e["to"],
        "countries": _countries(e.get("cc")),
        "requirement_ids": ["OR-PIR-1", "OR-EEI-1"] + (["OR-EEI-2"] if gap else []),
        "coverage_fraction": 1.0,
        "precision_class": "none",
        "measures": {"dv_ms": e["dv_ms"], "da_km": e["da_km"], "di_deg": e["di_deg"],
                     **({"dv_sma_ms": e["dv_sma_ms"]} if e.get("dv_sma_ms") is not None else {}),
                     **({"gap_hours": gap["hours"]} if gap else {}),
                     **({"lon_before_deg": g["lon_before"], "lon_after_deg": g["lon_after"],
                         "drift_before_deg_day": g["drift_before"], "drift_after_deg_day": g["drift_after"]} if g else {}),
                     **({"alt_after_km": g["alt_km_after"]} if g and "alt_km_after" in g else {})},
        "visual": {"type": "table", "url": f"{SITE}/changes#maneuvers"},
        "sources": [{**SRC_ST, "licence": attribution, "accessed_at": read_at}],
    }
    return {"type": "Feature", "geometry": None, "properties": props}


RELOCATION_METHOD = "orbit-2.30"
RELOCATION_PREFIX = "orbit:relocation:"
RELOCATION_NOTE = ("Arithmetic on the last public element sets, at the last measured rate: not a forecast, and no "
                   "statement of why the satellite moves or where it is going.")


def _start(m: dict) -> dict | None:
    """The estimate a move's identity rests on: the first moving set's distance and rate, fixed once that set
    exists (the rate-change estimate needs a second set and would move the id)."""
    est = ((m.get("departure") or {}).get("estimated_start")) or []
    return est[0] if est else None


def _relocation_item(m: dict, generated: str, read_at: str, attribution: str, stopped: bool) -> dict | None:
    dep = m.get("departure") or {}
    start = _start(m)
    if not start:
        return None                          # no held stop in Orbit's sets: not a move this item can date
    new = m["newest"]
    t = lambda x: x[:16].replace("T", " ")
    role = m.get("role") or "listed"
    owner = m.get("owner") or "unknown owner"
    steps = {"move_began": {"estimated": start["t"], "basis": start["basis"],
                            "sets": [dep["last_held_set"], *start["sets"]]}}
    change = ("new", start["sets"][0])
    title_what = f"moving {m['direction']} at {abs(new['drift']):.2f} deg/day from {_lon(dep['lon'])}"
    parts = [f"{m['name']} (catalog {m['norad']}, owner {owner}, listed role on Orbit's GEO page: {role}) left its "
             f"stop at {_lon(dep['lon'])}. The move began about {start['t'][:10]} (estimated from the "
             f"{start['basis']}, assuming it sped up evenly from rest); its last held set is dated "
             f"{t(dep['last_held_set'])} UTC and its first moving set {t(start['sets'][0])} UTC."]
    brake = m.get("brake") or {}
    if stopped:
        stop = m["stop"]
        steps["stopped"] = {"at": stop["arrival"], "sets": stop["sets"]}
        change = ("ended", stop["arrival"])
        title_what = f"stopped at {_lon(stop['lon'])} after moving {m['direction']} from {_lon(dep['lon'])}"
        parts.append(f"It stopped at {_lon(stop['lon'])}: drift under 0.1 deg/day for 2 days or more, from the set "
                     f"dated {t(stop['arrival'])} UTC ({stop['sets']} sets so far).")
    elif m.get("stale"):
        pass                                 # said after the newest set, below
    elif brake.get("state") in ("braking seen", "steady"):
        steps["braking"] = {"state": brake["state"], "at": brake["at"], "sets": brake.get("sets")}
        if brake["state"] == "steady":
            change = ("changed", brake["at"])
            title_what = f"braking while moving {m['direction']} from {_lon(dep['lon'])}"
        parts.append("Braking is seen: its drift fell between sets"
                     + ("; the stop projection from constant braking at the measured rate has held steady "
                        "(the GEO page shows it)." if brake["state"] == "steady"
                        else "; no steady stop projection yet."))
    if not stopped:
        parts.append(f"Newest set: {t(new['t'])} UTC, {new['age_h']:g} hours old at this build, at "
                     f"{_lon(new['lon'])} drifting {new['drift']:+.3f} deg/day."
                     + (" That set is too old to give a position now." if m.get("stale") else ""))
    parts.append(RELOCATION_NOTE + " " + attribution)
    ident = f"{RELOCATION_PREFIX}{m['norad']}:{start['t'][:10]}"
    props = {
        **_base(generated),
        "method_version": RELOCATION_METHOD,
        "id": ident,
        "subject_id": ident,                  # one move of one object, updated in place
        "event_start": _floor(start["t"], "day"),
        "event_time_precision": "day",
        **({"event_end": _floor(m["stop"]["arrival"], "day")} if stopped else {}),
        **_change(change[0], change[1], generated),
        "title": f"GEO relocation: {m['name']} ({role}, {owner}): {title_what}",
        "summary": " ".join(parts),
        "data_as_of": new["t"],
        "countries": [],
        "requirement_ids": ["OR-PIR-1", "OR-EEI-1"],
        "coverage_fraction": 1.0,
        "precision_class": "none",
        "steps": steps,
        "measures": {"from_lon_deg": dep["lon"], "drift_deg_day": new["drift"], "newest_set_age_h": new["age_h"],
                     "moving_sets": m.get("moving_sets"),
                     **({"stop_lon_deg": m["stop"]["lon"]} if stopped else {})},
        "visual": {"type": "table", "url": f"{SITE}/geo#movers"},
        "sources": [{**SRC_ST, "licence": attribution, "accessed_at": read_at}],
    }
    return {"type": "Feature", "geometry": None, "properties": props}


def relocation_features(tracker: dict, generated: str) -> list[dict]:
    """Relocation items from the GEO tracker's output (movers and arrivals); none when it failed."""
    if not tracker or "error" in tracker:
        return []
    read_at, attribution = tracker.get("at_utc") or generated, tracker.get("attribution") or ""
    out = [_relocation_item(m, generated, read_at, attribution, False) for m in tracker.get("movers") or []]
    out += [_relocation_item(m, generated, read_at, attribution, True) for m in tracker.get("arrived") or []]
    return [f for f in out if f]


def merge_relocations(feed_doc: dict, tracker: dict) -> dict:
    """The feed with this run's relocation items in place of any earlier ones."""
    keep = [f for f in feed_doc.get("features") or []
            if not str((f.get("properties") or {}).get("id", "")).startswith(RELOCATION_PREFIX)]
    items = relocation_features(tracker, feed_doc["generated_at"])
    feed_doc["features"] = keep + items
    if items and "Space-Track" not in feed_doc.get("attribution", ""):
        feed_doc["attribution"] += (". Satellite element sets from Space-Track.org, United States Space Command "
                                    "(USSPACECOM), 18th Space Defense Squadron; relocation arithmetic is Orbit's own")
        feed_doc["licence"] += ("; Space-Track element sets redistributed under USSPACECOM's blanket approval for "
                                "basic SSA data, with citation")
    return feed_doc


# Each item's first source id and the collect lane that reads it. A lane that fails keeps its last good copy in the
# feed (from_previous), so readers need to know which source was really read on this run.
SOURCE_LANES = {"gcat-mcdowell": "catalog", "space-track": "maneuver"}


def source_health(snap: dict, features: list | None = None) -> dict:
    """The feed's per-source `health` block (the doctrine kit's form, as Headwind's and Blackout's): one entry per
    source id the items carry, from the snapshot's lane records. A source counts as read when last_ok equals
    checked_at and the state is up: its lane was fetched, or GCAT said its files had not changed (as
    archive._fresh). A failed lane (its items are the last good copy), an unconfigured one (off), one not run this
    time, or one carried from an earlier run (--only) is not read, so COP's ledger neither ends its items nor counts
    the kept copies as sightings (15 Nov 2026). States are the kit's health_state words (vocab/enums.json, feed
    contract revision 2.1): up, failing, never (off or never fetched), stale (fetched on an earlier run only)."""
    lanes = snap.get("lanes") or {}
    newest: dict[str, str] = {}
    for f in features or []:
        p = f["properties"]
        sid = p["sources"][0]["id"]
        newest[sid] = max(newest.get(sid, ""), min(p["data_as_of"], p["published_at"]))
    out = {}
    for src, lane in SOURCE_LANES.items():
        rec = lanes.get(lane)
        if not isinstance(rec, dict):
            continue  # a held or absent lane carries no items
        status = rec.get("status")
        read = status in ("ok", "unchanged") and not rec.get("from_previous")
        checked = ({"ok": rec.get("fetched_at"), "unchanged": rec.get("checked_at")}.get(status) if read else
                   {"off": rec.get("checked_at"), "failed": rec.get("failed_at")}.get(status)) or snap["generated_at"]
        if read:
            state = "up"
        elif status == "failed":
            state = "failing"
        else:
            state = "stale" if rec.get("fetched_at") and status != "off" else "never"
        detail = status or "unknown"
        if rec.get("from_previous"):
            detail += ", last good copy kept"
        if rec.get("error") or rec.get("reason"):
            detail += f": {(rec.get('error') or rec.get('reason'))[:200]}"
        out[src] = {"state": state, "last_ok": checked if read else rec.get("fetched_at"), "checked_at": checked,
                    "last_error": (rec.get("error") or "")[:200] or None if status == "failed" else None,
                    "failures": int(rec.get("failures") or 0) if status == "failed" else 0,
                    "data_as_of": newest.get(src), "lane": lane, "detail": detail}
    return out


def build_feed(snap: dict) -> dict:
    generated = snap["generated_at"]
    now = _dt(generated)
    cat_at = ((snap.get("lanes") or {}).get("catalog") or {}).get("fetched_at") or generated
    features = []

    launch_since = (now - timedelta(days=LAUNCH_DAYS)).date().isoformat()
    for x in snap.get("launches") or []:
        if x["date"] >= launch_since:
            features.append(_launch_item(x, generated, cat_at))

    re_since = (now - timedelta(days=REENTRY_DAYS)).date().isoformat()
    rows = [r for r in snap.get("reentries") or [] if r["reentry_date"] >= re_since]
    if rows:
        features.append(_reentry_item(rows, generated, cat_at, re_since))
    for b in (snap.get("breakups") or [])[:10]:   # GCAT E and C, last 30 days (gcat.recent_breakups)
        features.append(_breakup_item(b, generated, cat_at, snap.get("baseline")))
    features += baseline_features(snap.get("baseline") or {}, generated, cat_at)

    changes = snap.get("catalog_changes") or {}
    # Change items stay in the feed for two days after the reading that found them.
    if changes.get("previous_reading_at") and now - _dt(cat_at) <= timedelta(days=2):
        for g in (changes.get("late_groups") or [])[:10]:
            features.append(_late_item(g, generated, cat_at, changes["previous_reading_at"]))
        if changes.get("owner_changes"):
            features.append(_owner_item(changes["owner_changes"], generated, cat_at, changes["previous_reading_at"]))

    man = snap.get("maneuvers") or {}
    for e in man.get("events") or []:  # the card's own list: 30 days, above the reporting floor
        features.append(_maneuver_item(e, generated, man.get("read_at") or generated, man["attribution"]))
    credit = (". Satellite element sets from Space-Track.org, United States Space Command (USSPACECOM), 18th Space "
              "Defense Squadron; orbit-change analysis is Orbit's own" if man.get("events") else "")  # disclaimer section 4

    return {
        "type": "FeatureCollection",
        "contract": CONTRACT,
        "contract_rev": "2.1",
        "kit": KIT_VERSION,
        "program": "orbit",
        "generated_at": generated,
        "method_version": METHOD,
        "licence": "GCAT data CC BY 4.0 (J. McDowell, planet4589.org/space/gcat)" + (
                       "; Space-Track element sets redistributed under USSPACECOM's blanket approval for basic SSA "
                       "data, with citation" if man.get("events") else ""),
        "attribution": "Orbit, The Intelligence Company. Data from GCAT (J. McDowell, planet4589.org/space/gcat)" + credit,
        "language_key": LANGUAGE_KEY,
        "health": source_health(snap, features),
        "features": features,
    }
