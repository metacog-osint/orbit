"""Predicted reentries: Space-Track's Tracking and Impact Prediction (TIP) messages (orbit-2.13, 17 Nov 2026).

Source: Space-Track.org class `tip` (USSPACECOM, 18th Space Defense Squadron). Reentry and decay data are basic SSA
data under USSPACECOM's blanket approval for redistribution, conditioned on citation (doctrine/spacetrack-disclaimer.md).
One request a run, on the account shared with Noisefloor; TIP is not GP, so the hourly GP rule does not apply, and
3 requests a run (log in, TIP, log out) four times a day is far under 30 a minute and 300 an hour.

Fields (Space-Track's model definition, read 17 Nov 2026): NORAD_CAT_ID, MSG_EPOCH, INSERT_EPOCH, DECAY_EPOCH,
WINDOW, REV, DIRECTION, LAT, LON, INCL, NEXT_REPORT, ID, HIGH_INTEREST, OBJECT_NUMBER. The reply of 17 Nov 2026
03:3x UTC held 191 messages over 14 days. WINDOW is in minutes and NEXT_REPORT in hours; Orbit reads WINDOW as plus or
minus that many minutes around DECAY_EPOCH (it runs at about a fifth of the time left to the predicted reentry,
the usual rule of thumb for decay predictions); Space-Track's own text on the field was not found, so the page
says "window". LAT and LON are where the object would be at the predicted time, not where debris falls: with a
window of hours the object goes round the Earth several times inside it, so Orbit does not map them.

USSPACECOM's predictions, quoted, not Orbit's: Orbit keeps the newest message for each object and says so.

From orbit-2.17 every message of the reply also goes out compactly (`all_messages`), so Orbit's daily archive keeps
them after the 5 days (orbit/archive.py), and `check` sets each object's last prediction against the time TIP itself
gives after the reentry, and against GCAT's reentry time (doctrine/method.md, "Predicted reentries" item 7).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import gcat

DAYS = 5  # early messages promise the next one in 72 h (seen 13 Nov 2026), so 5 days holds every live prediction
URL = ("https://www.space-track.org/basicspacedata/query/class/tip/MSG_EPOCH/%3Enow-" + str(DAYS) +
       "/orderby/MSG_EPOCH%20desc/format/json")
KEEP_PAST_H = 24  # a prediction whose whole window has closed stays listed for a day, marked closed
ATTRIBUTION = ("Reentry predictions: Space-Track.org TIP messages, United States Space Command (USSPACECOM), 18th Space "
               "Defense Squadron, redistributed under USSPACECOM's blanket approval for basic SSA data. Quoted as "
               "issued, not checked by The Intelligence Company. Not for operational use.")


def _t(s: str | None) -> datetime | None:
    """Space-Track's 'YYYY-MM-DD HH:MM:SS' (UTC) to an aware datetime; None for anything else."""
    try:
        return datetime.strptime((s or "").strip()[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _iso(t: datetime | None) -> str | None:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


def _num(s, cast=float):
    try:
        return cast(s)
    except (TypeError, ValueError):
        return None


def _lon(x: float | None) -> float | None:
    return None if x is None else round(((x + 180.0) % 360.0) - 180.0, 1)  # TIP gives 0-360 east


def parse(rows: list[dict], now: datetime, objects: dict | None = None) -> dict:
    """TIP rows to the newest prediction per object, with GCAT's name and owner where GCAT lists it. Keeps
    predictions whose window is still open or closed under KEEP_PAST_H hours ago, soonest first. `passed`: the
    whole window (predicted time plus WINDOW minutes) is behind `now`."""
    if not isinstance(rows, list):
        raise ValueError("Space-Track TIP: reply is not a list")
    newest: dict[int, dict] = {}
    count: dict[int, int] = {}
    for r in rows:
        norad = _num(r.get("NORAD_CAT_ID") or r.get("OBJECT_NUMBER"), int)
        msg, decay = _t(r.get("MSG_EPOCH")), _t(r.get("DECAY_EPOCH"))
        if norad is None or msg is None or decay is None:
            continue
        count[norad] = count.get(norad, 0) + 1
        key = (msg, _num(r.get("ID"), int) or 0)
        if norad not in newest or key > newest[norad]["_key"]:
            newest[norad] = {"_key": key, "row": r, "msg": msg, "decay": decay}
    objs = objects or {}
    out = []
    for norad, n in newest.items():
        r, decay = n["row"], n["decay"]
        win = _num(r.get("WINDOW"), int)
        closes = decay + timedelta(minutes=win or 0)
        if closes < now - timedelta(hours=KEEP_PAST_H):
            continue
        rec = {"norad": norad, "msg_epoch": _iso(n["msg"]), "decay_epoch": _iso(decay), "window_min": win,
               "passed": closes < now, "direction": (r.get("DIRECTION") or "").strip().lower() or None,
               "lat": _num(r.get("LAT")), "lon": _lon(_num(r.get("LON"))), "incl": _num(r.get("INCL")),
               "rev": _num(r.get("REV"), int), "next_report_h": _num(r.get("NEXT_REPORT"), int),
               "high_interest": (r.get("HIGH_INTEREST") or "").strip().upper() == "Y", "messages": count[norad]}
        g = objs.get(f"S{norad:05d}")
        if g:  # gcat.INDEX_FIELDS: cat, norad, launch_tag, type, name, ldate, parent, ddate, status, owner, state
            rec.update({"name": g[4], "type": g[3], "launch_tag": g[2], "state": g[10],
                        "cc": gcat.iso_country(g[10])})
        out.append(rec)
    out.sort(key=lambda x: x["decay_epoch"])
    return {"objects": out, "messages": len(rows), "window_days": DAYS,
            "high_interest": sum(1 for x in out if x["high_interest"]), "all_messages": compact(rows)}


def compact(rows: list[dict]) -> list[list]:
    """Every usable message as [norad, msg_epoch, decay_epoch, window_min, id], oldest first: what the archive keeps."""
    out = []
    for r in rows if isinstance(rows, list) else []:
        norad = _num(r.get("NORAD_CAT_ID") or r.get("OBJECT_NUMBER"), int)
        msg, decay = _t(r.get("MSG_EPOCH")), _t(r.get("DECAY_EPOCH"))
        if norad is None or msg is None or decay is None:
            continue
        out.append([norad, _iso(msg), _iso(decay), _num(r.get("WINDOW"), int), _num(r.get("ID"), int)])
    out.sort(key=lambda m: (m[1], m[4] or 0))
    return out


CHECK_DAYS = 30  # GCAT's reentries card keeps 30 days, so the check does too
CHECK_ATTRIBUTION = ("Reentry times: Space-Track.org TIP messages (USSPACECOM, 18th Space Defense Squadron) and GCAT "
                     "(Jonathan McDowell, CC BY 4.0). Comparison: The Intelligence Company, not reviewed or endorsed by "
                     "USSPACECOM or by GCAT. Not for operational use.")


def _dt(iso: str | None) -> datetime | None:
    try:
        return datetime.strptime((iso or "")[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _min(a: datetime, b: datetime) -> int:
    return round((a - b).total_seconds() / 60)


AFTER_MAX_WINDOW = 1  # minutes: TIP's message after the reentry; wider ones issued late (10-60 min seen) stay predictions


def _after(m: list) -> bool:
    """A message issued after the time it gives, with a window of at most AFTER_MAX_WINDOW minutes."""
    return m[1] > m[2] and (m[3] if m[3] is not None else 99) <= AFTER_MAX_WINDOW


def check(messages: list[list], reentries: list[dict], now: datetime, objects: dict | None = None) -> dict:
    """Each object's last TIP prediction against the time TIP gives after the reentry, and GCAT's time beside both.

    `messages`: compact rows (see `compact`), from the archive and this run, duplicates allowed. TIP's message after
    the reentry is the newest one issued after the time it gives with a 1-minute window (`_after`). The last
    prediction is the newest message issued before that time. `offset_min` is TIP's time after the reentry minus
    the last prediction (positive: it came down later than predicted); `inside` is whether that time falls within
    the prediction's window. GCAT's time is set against TIP's time after the reentry, or, without one, against the
    last prediction; GCAT often takes its time from that same TIP message, so a match is not an independent check.
    Objects whose reentry (or last predicted time) is more than CHECK_DAYS old are left out."""
    seen, by = set(), {}
    for m in messages or []:
        if not isinstance(m, (list, tuple)) or len(m) < 5:
            continue
        key = (m[0], m[1], m[2], m[4])
        if key in seen:
            continue
        seen.add(key)
        by.setdefault(int(m[0]), []).append(m)
    gcat_by = {}
    for r in reentries or []:
        try:
            gcat_by[int(r.get("norad"))] = r
        except (TypeError, ValueError):
            continue
    objs = objects or {}
    rows = []
    for norad, ms in by.items():
        ms.sort(key=lambda m: (m[1], m[4] or 0))
        after = [m for m in ms if _after(m)]
        assessed = after[-1] if after else None
        ref = _dt(assessed[2]) if assessed else None
        before = [m for m in ms if ref is None or _dt(m[1]) < ref]
        before = [m for m in before if not _after(m)]
        last = before[-1] if before else None
        when = ref or (_dt(last[2]) if last else None)
        if when is None or when < now - timedelta(days=CHECK_DAYS) or when > now:
            continue  # too old, or a prediction still ahead (the table above lists it)
        if ref is None and last is not None:
            win = last[3] or 0
            if _dt(last[2]) + timedelta(minutes=win) > now:
                continue  # its window is still open
        rec = {"norad": norad, "messages": len(ms)}
        if last:
            rec["predicted"] = {"msg_epoch": last[1], "decay_epoch": last[2], "window_min": last[3]}
            if ref:
                rec["offset_min"] = _min(ref, _dt(last[2]))
                rec["inside"] = abs(rec["offset_min"]) <= (last[3] or 0)
                rec["lead_h"] = round((ref - _dt(last[1])).total_seconds() / 3600, 1)
        if assessed:
            rec["after"] = {"msg_epoch": assessed[1], "decay_epoch": assessed[2], "window_min": assessed[3]}
        g = gcat_by.get(norad)
        if g:
            rec["name"] = g.get("name")
            rec["gcat"] = {"date": g.get("reentry_date"), "time": g.get("reentry_time"),
                           "uncertain": bool(g.get("reentry_uncertain"))}
            gt = _dt(g.get("reentry_time"))
            base = ref or (_dt(last[2]) if last else None)
            if gt and base:
                rec["gcat"]["minus_tip_min"] = _min(gt, base)
        else:
            gi = objs.get(f"S{norad:05d}")
            if gi:  # gcat.INDEX_FIELDS: name is field 4
                rec["name"] = gi[4]
        rec["_when"] = _iso(when)
        rows.append(rec)
    rows.sort(key=lambda r: r.pop("_when"), reverse=True)
    with_after = [r for r in rows if "offset_min" in r]
    gc = [r for r in rows if "minus_tip_min" in (r.get("gcat") or {})]
    kept = [m[1] for m in messages or [] if isinstance(m, (list, tuple)) and len(m) >= 5]
    return {"attribution": CHECK_ATTRIBUTION, "days": CHECK_DAYS, "objects": rows, "kept_since": min(kept, default=None),
            "with_after": len(with_after), "inside": sum(1 for r in with_after if r["inside"]),
            "no_after": sum(1 for r in rows if "after" not in r),
            "gcat_dated": len(gc), "gcat_same_minute": sum(1 for r in gc if r["gcat"]["minus_tip_min"] == 0
                                                           and "after" in r),
            "gcat_day_or_more": [r["norad"] for r in gc if abs(r["gcat"]["minus_tip_min"]) >= 1440],
            "gcat_not_yet": sum(1 for r in rows if "gcat" not in r)}
