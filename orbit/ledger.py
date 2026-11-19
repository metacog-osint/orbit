"""Orbit's launch ledger: every launch since START from Launch Library 2 (The Space Devs), kept and checked hourly.

Tom's plan (15 Nov 2026, from his earlier launch mapper): each hour one request pulls 14 launches in NET order,
starting at the last saved launch's NET. The first of them is the last saved launch, which verifies it (its
status, time and other fields are refreshed, and any change is logged); the rest are new and are added. When the
ledger has caught up, a pull returns the last saved launch and only the launches since. 887 launches from 1 Jan 2024
to 15 Nov 2026 took the first 64 hours.

A launch saved before LL2 posted its outcome (status Go, TBC, In Flight) would keep that status once newer launches
pass it, so the earliest such launch from the last OPEN_DAYS is looked up by id each hour until it has a final one.

Load: one request an hour, and at most one more (a by-id lookup: the last saved launch when the pull doesn't hold
it, or else the open launch above), far inside the 15 an hour The Space Devs give everyone without a key ("the entire database is accessible to
everyone, for free", thespacedevs.com/llapi, read 16 Nov 2026). On a 429 or any other error nothing is changed and
the next hour tries again: no retries.

Use (Tom, 15 Nov 2026: freely available, published so the suite's programs can read it): the ledger is published on
Orbit's public release `ledger` as launch-ledger.json, credited to The Space Devs. Images are not kept: each image
carries its photographer's or agency's own licence.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlencode

from orbit import launches

API = "https://ll.thespacedevs.com/2.3.0/launches/"
PREVIOUS = API + "previous/"
START = "2024-01-01T00:00:00Z"
PAGE = 14
SCHEMA = "orbit-ledger/1"
ATTRIBUTION = "Launch data: Launch Library 2, The Space Devs (thespacedevs.com)"
RELEASE_TAG = "ledger"
ASSET = "launch-ledger.json"
PUBLIC_URL = f"https://github.com/metacog-osint/orbit/releases/download/{RELEASE_TAG}/{ASSET}"
FINAL = ("Success", "Failure", "Partial Failure")   # LL2 status abbreviations that end a launch's story
OPEN_DAYS = 14          # a launch without a final status this close to the newest is pulled again
COMPARED = ("name", "net", "net_precision", "window_start", "window_end", "status", "status_name", "provider",
            "vehicle", "mission", "mission_type", "orbit", "pad", "location", "pad_country")


def page_url(since: str, page: int = PAGE) -> str:
    return PREVIOUS + "?" + urlencode({"net__gte": since, "ordering": "net", "limit": page, "mode": "detailed"})


def id_url(launch_id: str) -> str:
    return API + f"{launch_id}/?" + urlencode({"mode": "detailed"})


def empty() -> dict:
    return {"schema": SCHEMA, "attribution": ATTRIBUTION, "start": START, "page": PAGE, "updated_at": None,
            "caught_up": False, "launches": [], "changes": [], "last_check": None}  # changes: every field change, never cut (18 Nov 2026)


def _key(r: dict) -> tuple:
    return (r.get("net") or "", r.get("id") or "")


def _clean(r: dict) -> dict:
    """The fields the ledger keeps: launches.parse's, without the long mission text."""
    out = {k: v for k, v in r.items() if k != "mission_description"}
    return out


def parse_one(body: bytes) -> dict | None:
    """One launch from the by-id endpoint (a bare record, not a page)."""
    doc = json.loads(body.decode("utf-8"))
    if not isinstance(doc, dict) or not doc.get("id"):
        return None
    return _clean(launches.parse(json.dumps({"results": [doc]}).encode("utf-8"))[0])


def _net(r: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(r["net"].replace("Z", "+00:00"))
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def open_launch(ledger: dict) -> dict | None:
    """The earliest launch within OPEN_DAYS of the newest, other than the newest, with no final status yet: one
    saved as "Go" or "TBC" before LL2 posted its outcome. It is looked up by id (a second request that hour)."""
    rows = ledger["launches"]
    if len(rows) < 2:
        return None
    last = max(rows, key=_key)
    newest = _net(last)
    if newest is None:
        return None
    open_ = [r for r in rows if r is not last and r.get("status") not in FINAL and _net(r) is not None
             and (newest - _net(r)).total_seconds() <= OPEN_DAYS * 86400]
    return min(open_, key=_key) if open_ else None


def _diff(old: dict, new: dict) -> dict:
    return {k: [old.get(k), new.get(k)] for k in COMPARED if old.get(k) != new.get(k)}


def step(ledger: dict, body: bytes, read_at: str, lookup=None) -> dict:
    """Apply one pull to `ledger` in place and return what it found.

    body: the reply to next_url(ledger), the PAGE launches from the newest saved launch's NET on (from START for an
    empty ledger). lookup(launch_id) -> bytes | None is the by-id reply (None: LL2 no longer has it). It is called at
    most once a step: for the newest saved launch when the pull doesn't hold it, otherwise for open_launch().
    launches.parse raises ValueError on a reply with no results, before anything changes.
    """
    rows = [_clean(r) for r in launches.parse(body)]
    held = {r["id"]: i for i, r in enumerate(ledger["launches"])}
    last = max(ledger["launches"], key=_key) if ledger["launches"] else None
    report = {"read_at": read_at, "pulled": len(rows), "added": 0, "verified": None, "changed": {},
              "open_checked": None, "requests": 1}
    looked = False

    def refresh(old: dict, new: dict):
        d = _diff(old, new)
        if d:
            report["changed"][new["id"]] = d
        ledger["launches"][held[old["id"]]] = new

    if last is not None:
        here = next((r for r in rows if r["id"] == last["id"]), None)
        if here is not None:
            report["verified"] = "ok"
        elif lookup is not None:
            looked = True
            report["requests"] += 1
            raw = lookup(last["id"])
            here = parse_one(raw) if raw else None
            report["verified"] = "moved" if here is not None else "missing"
            if here is None:                                # LL2 no longer lists it: kept, and marked
                ledger["launches"][held[last["id"]]]["ll2_missing_since"] = read_at
        else:
            report["verified"] = "not in pull"
        if here is not None:
            refresh(last, here)
    for r in rows:
        if r["id"] in held:
            if last is None or r["id"] != last["id"]:
                refresh(ledger["launches"][held[r["id"]]], r)
            continue
        ledger["launches"].append(r)
        held[r["id"]] = len(ledger["launches"]) - 1
        report["added"] += 1
    pulled = {r["id"] for r in rows}
    op = open_launch(ledger)
    if op is not None and op["id"] not in pulled and lookup is not None and not looked:
        report["requests"] += 1
        raw = lookup(op["id"])
        new = parse_one(raw) if raw else None
        if new is None:
            ledger["launches"][held[op["id"]]]["ll2_missing_since"] = read_at
        else:
            refresh(op, new)
        report["open_checked"] = {"id": op["id"], "status": new.get("status") if new else None}
    ledger["launches"].sort(key=_key)
    for lid, d in report["changed"].items():
        ledger["changes"].append({"at": read_at, "id": lid, "fields": d})
    ledger["caught_up"] = len(rows) < PAGE
    ledger["updated_at"] = read_at
    ledger["last_check"] = report
    return report


def next_url(ledger: dict) -> str:
    if not ledger["launches"]:
        return page_url(ledger.get("start") or START)
    return page_url(max(ledger["launches"], key=_key)["net"])


def after(ledger: dict, since_date: str) -> list[dict]:
    """Launches in the ledger dated after `since_date` (YYYY-MM-DD), newest first: what GCAT hasn't listed yet."""
    return sorted((r for r in ledger.get("launches") or [] if (r.get("net") or "")[:10] > since_date),
                  key=_key, reverse=True)


def history(ledger: dict) -> dict:
    """The ledger compacted for Orbit's map (orbit-2.10): each pad once, then one short row per launch,
    [net, pad index, status, provider country, name], oldest first. Pads without coordinates are left out and
    counted. About 160 bytes a launch (measured on the first 14), so about 140 KB once the ledger has caught up."""
    pads, index, rows, no_place = [], {}, [], 0
    for r in sorted(ledger.get("launches") or [], key=_key):
        if r.get("lat") is None or r.get("lon") is None:
            no_place += 1
            continue
        key = (r.get("pad") or "", r.get("location") or "", round(r["lat"], 3), round(r["lon"], 3))
        if key not in index:
            index[key] = len(pads)
            pads.append([key[0], key[1], key[2], key[3], r.get("pad_country")])
        pc = r.get("provider_countries") or []
        rows.append([r.get("net"), index[key], r.get("status") or "", pc[0] if pc else None, r.get("name") or ""])
    return {"fields": {"pads": ["pad", "location", "lat", "lon", "country"],
                       "launches": ["net", "pad", "status", "provider_country", "name"]},
            "pads": pads, "launches": rows, "no_place": no_place}


def summary(ledger: dict, gcat_last_date: str | None = None) -> dict:
    """The snapshot's `ledger` block: counts, the last check, and the launches GCAT hasn't listed yet."""
    rows = ledger.get("launches") or []
    out = {"attribution": ATTRIBUTION, "url": PUBLIC_URL, "start": ledger.get("start"), "held": len(rows),
           "first_net": rows[0]["net"] if rows else None, "last_net": rows[-1]["net"] if rows else None,
           "caught_up": ledger.get("caught_up"), "updated_at": ledger.get("updated_at"),
           "last_check": ledger.get("last_check"), "changes_logged": len(ledger.get("changes") or []),
           "history": history(ledger)}
    if gcat_last_date:
        out["gcat_last_date"] = gcat_last_date
        out["since_gcat"] = [{k: r.get(k) for k in ("id", "name", "net", "status", "status_name", "provider",
                                                    "provider_countries", "vehicle", "mission", "orbit", "pad",
                                                    "location", "pad_country", "ll2_url")}
                             for r in after(ledger, gcat_last_date)]
    return out


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
