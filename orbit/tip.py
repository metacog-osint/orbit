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
            "high_interest": sum(1 for x in out if x["high_interest"])}
