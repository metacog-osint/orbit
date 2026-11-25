"""Orbit's own daily archive: the counts no outside source keeps for Orbit (decision 8, Tom, 15 Nov 2026).

GCAT's history gives the launch, payload and reentry baselines at once (gcat.baseline). Three series exist only
in Orbit's own readings, so Orbit keeps them day by day and gives them baselines after 90 days:

  maneuver  the listed orbit changes in the watch list, each keyed by NORAD number and start, on the days a run
            read Space-Track (lane ok, or waiting out the hour with its last read);
  navwarn   the launch, debris and reentry warning areas in force, each by Orbit's area key, with the newest
            memorandum date, so a day read from stale memoranda says so. Days to 25 Nov 2026 only: the lane
            retired in orbit-2.32 (ideas#69); those days stay as they are and nothing new is added;
  catalog   each new GCAT reading's changes (objects added, late additions, removals, owner changes, newly
            numbered), keyed by GCAT's own file stamp: GCAT keeps no date of cataloging, so a reading's
            changes are dated by the day Orbit read them;
  tip       from orbit-2.17, Space-Track's TIP messages (USSPACECOM's reentry predictions), each once, on the day
            a run first saw it: Space-Track's reply covers only 5 days and GCAT dates a reentry days later, so the
            check of a prediction against the reentry (tip.check) reads them from here;
  lead      from orbit-2.18, the day's last daily lead (orbit/lead.py), so each day's lead can be cited.

Every day also records how many runs it had and each lane's statuses, so a missed day or a failed lane is never
read as a count of zero. Only what the page already publishes goes in: listed changes, never the private watch
list. One entry per UTC day, every day kept (retention rule, 18 Nov 2026: no cap).

Kept in data/state/ (the Actions cache) and published with the site at /data/archive.json. A run whose cache
entry is missing or older merges the published copy back in (one request to Orbit's own site), so losing the
cache does not start the archive over.
"""
from __future__ import annotations

from datetime import date, timedelta

SCHEMA = "orbit-archive/1"
PUBLIC_URL = "https://orbit.theintelligence.company/data/archive.json"
TIP_DEDUP_DAYS = 10  # a TIP message already kept in the last 10 days is not kept again (the reply covers 5)
BASELINE_DAYS = 90  # decision 8: baselines from Orbit's own counts after 90 days


def empty() -> dict:
    return {"schema": SCHEMA, "days": {}}


def _lane_status(snap: dict, lane: str) -> str:
    """The lane's status this run; 'carried' when the run kept an earlier run's copy (a failed lane or --only)."""
    rec = (snap.get("lanes") or {}).get(lane) or {}
    if rec.get("from_previous") and rec.get("status") in ("ok", "unchanged"):
        return "carried"
    return rec.get("status") or "missing"


def _fresh(snap: dict, lane: str) -> bool:
    """True when this run's copy of a lane is its own read: ok, or 'unchanged' with nothing failed since."""
    rec = (snap.get("lanes") or {}).get(lane) or {}
    return rec.get("status") in ("ok", "unchanged") and not rec.get("from_previous")


def record(doc: dict | None, snap: dict) -> dict:
    """Add one run's snapshot to the archive and return it. The run is dated by snap['generated_at'] (UTC)."""
    doc = doc if doc and doc.get("schema") == SCHEMA else empty()
    stamp = snap.get("generated_at") or ""
    day = stamp[:10]
    if len(day) != 10:
        return doc
    d = doc["days"].setdefault(day, {"runs": 0, "first_run": stamp, "lanes": {}})
    if stamp and stamp <= d.get("last_run", ""):  # the same run recorded twice
        return doc
    d["runs"] += 1
    d["last_run"] = stamp
    for lane in sorted((snap.get("lanes") or {}).keys()):
        seen = d["lanes"].setdefault(lane, [])
        st = _lane_status(snap, lane)
        if st not in seen:
            seen.append(st)

    m = snap.get("maneuvers") or {}
    if _fresh(snap, "maneuver") and m:
        mv = d.setdefault("maneuver", {"listed": {}})
        mv["watched"] = m.get("watched")
        mv["read_at"] = m.get("read_at")
        mv["counted_not_listed"] = m.get("counted_not_listed") or {}
        for e in m.get("events") or []:
            key = f"{e.get('norad')}:{(e.get('from') or '')[:10]}"
            mv["listed"].setdefault(key, {"norad": e.get("norad"), "name": e.get("gcat_name") or e.get("name"),
                                          "regime": e.get("regime"), "from": e.get("from"), "to": e.get("to"),
                                          "dv_ms": e.get("dv_ms"), "dominant": e.get("dominant"),
                                          "country": e.get("cc") or e.get("country")})
            if e.get("notable"):  # orbit-2.26 (orbit/notable.py): kept from the run that first marks it
                mv["listed"][key].setdefault("notable", e["notable"].get("kind"))

    nw = snap.get("navwarn") or {}
    if _fresh(snap, "navwarn") and nw:
        w = d.setdefault("navwarn", {"areas": {}})
        nga = (nw.get("sources") or {}).get("nga") or {}
        w["form"] = nga.get("form")
        memo_dates = [v.get("as_of") for v in (nga.get("memos") or {}).values() if v.get("as_of")]
        if memo_dates:
            w["memo_as_of"] = max(memo_dates)
        for a in nw.get("areas") or []:
            row = w["areas"].setdefault(a.get("key"), {"hazard": a.get("hazard"), "regions": a.get("regions") or [],
                                                       "broadcasts": []})
            for b in a.get("broadcasts") or []:
                if b.get("id") and b["id"] not in row["broadcasts"]:
                    row["broadcasts"].append(b["id"])

    cc = snap.get("catalog_changes") or {}
    cat_lane = (snap.get("lanes") or {}).get("catalog") or {}
    if cat_lane.get("status") == "ok" and not cat_lane.get("from_previous") and cc:
        key = (snap.get("gcat_updated") or {}).get("satcat") or stamp
        readings = d.setdefault("catalog", {})
        readings.setdefault(key, {k: cc.get(k) for k in ("added", "added_fresh", "added_late", "removed",
                                                          "temporary_entries_closed", "changed", "newly_numbered")}
                            | {"owner_changes": len(cc.get("owner_changes") or []),
                               "late_launches": len(cc.get("late_groups") or []), "read_at": stamp})

    dc = snap.get("decay") or {}
    if _fresh(snap, "decay") and dc.get("all_messages"):
        since = str(date.fromisoformat(day) - timedelta(days=TIP_DEDUP_DAYS))
        kept = {tuple(m[:5]) for k, v in doc["days"].items() if since <= k <= day for m in v.get("tip") or []}
        new = [list(m[:5]) for m in dc["all_messages"] if tuple(m[:5]) not in kept]
        if new:
            d.setdefault("tip", []).extend(new)
            doc["tip_attribution"] = dc.get("attribution")

    doc["updated_at"] = stamp
    return doc


def keep_lead(doc: dict, lead: dict) -> dict:
    """Keep the run's daily lead (orbit/lead.py) on its UTC day; the day's last run's lead stands (orbit-2.18)."""
    day = (lead.get("at") or "")[:10]
    if len(day) == 10 and day in doc.get("days", {}):
        doc["days"][day]["lead"] = lead
    return doc


def tip_messages(doc: dict | None) -> list[list]:
    """Every TIP message kept, oldest day first: [norad, msg_epoch, decay_epoch, window_min, id]."""
    days = (doc or {}).get("days") or {}
    return [m for k in sorted(days) for m in days[k].get("tip") or []]


def merge(local: dict | None, published: dict | None) -> dict:
    """Join two copies day by day; where both hold a day, keep the one with more runs (then the later last run).

    A run whose Actions cache entry is lost or older than the published copy loses nothing that was deployed."""
    out = empty()
    for src in (published, local):
        if not src or src.get("schema") != SCHEMA:
            continue
        for day, entry in (src.get("days") or {}).items():
            have = out["days"].get(day)
            if have is None or (entry.get("runs", 0), entry.get("last_run", "")) > (have.get("runs", 0),
                                                                                      have.get("last_run", "")):
                out["days"][day] = entry
    stamps = [x.get("updated_at") for x in (local, published) if x and x.get("updated_at")]
    if stamps:
        out["updated_at"] = max(stamps)
    for src in (published, local):
        if src and src.get("tip_attribution"):
            out["tip_attribution"] = src["tip_attribution"]
    return out


def summary(doc: dict | None, today: date) -> dict:
    """What the page shows: the span kept, days with a run, days each series was read, and when baselines start."""
    days = sorted(((doc or {}).get("days") or {}).keys())
    if not days:
        return {"days": 0}
    first = date.fromisoformat(days[0])
    span = (today - first).days + 1
    count = lambda k: sum(1 for d in days if k in doc["days"][d])  # noqa: E731
    stale_memo = sum(1 for d in days if (doc["days"][d].get("navwarn") or {}).get("memo_as_of", "9")[:10] < str(
        date.fromisoformat(d) - timedelta(days=1)))
    return {
        "days": len(days), "first_day": days[0], "last_day": days[-1], "span_days": span,
        "missed_days": max(0, span - len(days)),
        "maneuver_days": count("maneuver"), "navwarn_days": count("navwarn"), "catalog_readings": sum(
            len(doc["days"][d].get("catalog") or {}) for d in days),
        "navwarn_stale_memo_days": stale_memo,
        "tip_messages": sum(len(doc["days"][d].get("tip") or []) for d in days),
        "listed_changes": len({k for d in days for k in ((doc["days"][d].get("maneuver") or {}).get("listed") or {})}),
        "warning_areas": len({k for d in days for k in ((doc["days"][d].get("navwarn") or {}).get("areas") or {})}),
        "baseline_from": str(first + timedelta(days=BASELINE_DAYS)),
    }
