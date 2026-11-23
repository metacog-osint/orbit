"""The daily lead: what changed in the last 24 hours and what is due in the next 24 (orbit-2.18, 18 Nov 2026).

Tom, 18 Nov 2026: "begin with the daily lead first"; plan in the private planning notes.
Readers are mostly informed, some new to the topic, so each line is exact (source, time, number) and the page
defines its terms beside it.

Built from the snapshot alone (and the daily archive, for orbit changes first listed today): no request. Each line
says where it comes from and links to its card. A source that was not read this run, or has not published in a
while, gets its own line: no line ever reads as "nothing happened" for lack of data. Observations only: no
probability, warning or judgment of why.

A line is {"kind", "href", "source", "parts"}. `parts` mixes text with {"t": ISO time}, {"d": ISO date},
{"cc": ISO country code} and, from orbit-2.20, {"s": an object's name, "o": its NORAD number or JCAT id} so the
page writes times in the viewer's zone and countries by name, and links each object to its page.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from orbit import names

HOURS = 24
GCAT_STALE_H = 36      # GCAT usually publishes daily; past this the lead says how old its copy is
BREAKUP_DAYS = 7       # GCAT dates breakups late, so a week, said as such
SHOW = 3               # names per line before "and N more"
MAX_LINES = 7

SOURCES = {"tip": "Space-Track.org TIP (USSPACECOM)", "tipcheck": "Space-Track.org TIP and GCAT",
           "maneuver": "Space-Track.org element sets; Orbit's analysis", "gcat": "GCAT (Jonathan McDowell)",
           "baseline": "GCAT's history"}


def _dt(iso: str | None) -> datetime | None:
    try:
        return datetime.strptime((iso or "")[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def gcat_stamp(s: str | None) -> datetime | None:
    """GCAT's file stamp, e.g. '2026 Nov 18 0144:40' (UTC), to a datetime."""
    try:
        return datetime.strptime((s or "").strip(), "%Y %b %d %H%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _obj(name: str, norad=None, jcat=None):
    """An object's name, with its key for the page's link (orbit-2.20); plain text when it has neither."""
    key = str(norad).lstrip("0") or None if norad not in (None, "") else jcat
    return {"s": name, "o": key} if key else name


def _names(parts: list, items: list, render) -> None:
    """Append up to SHOW rendered items, then 'and N more'."""
    for i, x in enumerate(items[:SHOW]):
        parts.append("; " if i else ": ")
        parts.extend(render(x))
    if len(items) > SHOW:
        parts.append(f"; and {len(items) - SHOW} more")
    parts.append(".")


def _lane(snap: dict, name: str) -> dict:
    return (snap.get("lanes") or {}).get(name) or {}


def _fresh(snap: dict, name: str) -> bool:
    rec = _lane(snap, name)
    return rec.get("status") in ("ok", "unchanged") and not rec.get("from_previous")


def _win(m) -> str:
    m = m or 0
    return f"±{m} min" if m < 120 else f"±{m / 60:.1f}".rstrip("0").rstrip(".") + " h"


def _kind(k: str, n: int) -> str:
    if k == "debris":
        return f"{n} {'piece' if n == 1 else 'pieces'} of debris"
    return f"{n} {k}" + ("" if n == 1 else "s")


def _dv(x) -> str:
    x = x or 0
    return f"{x:.1f}" if x >= 1 else f"{x:.2f}"


def reentries_ahead(snap: dict, now: datetime) -> dict | None:
    dc = snap.get("decay") or {}
    soon = [o for o in dc.get("objects") or [] if not o.get("passed")
            and (t := _dt(o.get("decay_epoch"))) and now <= t <= now + timedelta(hours=HOURS)]
    if not soon:
        return None
    soon.sort(key=lambda o: (not o.get("high_interest"), o["decay_epoch"]))
    parts = [_plural(len(soon), "object") + (" is" if len(soon) == 1 else " are") +
             " predicted to reenter in the next 24 hours"]
    _names(parts, soon, lambda o: [_obj(o.get('name') or 'NORAD ' + str(o['norad']), o['norad']), " at ", {"t": o["decay_epoch"]},
                                    f" {_win(o.get('window_min'))}"])
    hi = sum(1 for o in soon if o.get("high_interest"))
    if hi:
        parts.append(f" USSPACECOM flags {hi} of them as high interest" + (", listed first." if hi < len(soon) else "."))
    return {"kind": "reentry_ahead", "href": "#decay", "source": SOURCES["tip"], "parts": parts}


def reentries_done(snap: dict, now: datetime) -> dict | None:
    c = snap.get("tip_check") or {}
    done = [o for o in c.get("objects") or [] if (a := o.get("after"))
            and (t := _dt(a.get("msg_epoch"))) and t >= now - timedelta(hours=HOURS)]
    if not done:
        return None
    done.sort(key=lambda o: o["after"]["decay_epoch"], reverse=True)

    def render(o):
        out = [_obj(o.get('name') or 'NORAD ' + str(o['norad']), o['norad']), " at ", {"t": o["after"]["decay_epoch"]}]
        if "offset_min" in o:
            m = o["offset_min"]
            how = f"{abs(m)} min {'later' if m > 0 else 'earlier'} than" if m else "at the time of"
            out.append(f" ({how} the last prediction, {'inside' if o['inside'] else 'outside'} its window)")
        return out
    parts = [_plural(len(done), "object") + " came down, by the TIP messages USSPACECOM issued after the reentry "
             "in the last 24 hours"]
    _names(parts, done, render)
    return {"kind": "reentry_done", "href": "#tipcheck-h", "source": SOURCES["tipcheck"], "parts": parts}


def _who(e: dict) -> list:
    """The object as the lane names it, linked, with up to two of the other names it goes by (orbit-2.26)."""
    also = (e.get("names") or [])[:names.TITLE_NAMES]
    return [_obj(e.get('gcat_name') or e.get('name'), e.get('norad'))] + ([", also " + " and ".join(also)] if also else [])


def _new_changes(snap: dict, archive_doc: dict | None, now: datetime) -> list[dict]:
    """Listed changes first listed since the start of yesterday (UTC), by the archive's days."""
    m = snap.get("maneuvers") or {}
    if not m.get("read_at"):
        return []
    first: dict[str, str] = {}
    for day in sorted(((archive_doc or {}).get("days") or {})):
        for k in (((archive_doc["days"][day].get("maneuver") or {}).get("listed")) or {}):
            first.setdefault(k, day)
    since = (now - timedelta(hours=HOURS)).date().isoformat()
    return [e for e in m.get("events") or []
            if first.get(f"{e.get('norad')}:{(e.get('from') or '')[:10]}", now.date().isoformat()) >= since]


def _gap(e: dict) -> list:
    g = e.get("gap")
    if not g:
        return []
    days = g["hours"] / 24
    return [f", measured across a {round(days) if days >= 10 else round(days, 1):g}-day gap between element sets (",
            {"t": g["from"]}, " to ", {"t": g["to"]}, ")"]


def notable_changes(snap: dict, archive_doc: dict | None, now: datetime) -> list[dict]:
    """One line for each notable change (orbit/notable.py: a listed-role GEO object that started drifting, stopped
    or changed its drift rate), while it is new or its newest element set is under 24 hours old. First in the
    lead (Tom, 23 Nov 2026). What moved and how, from which sets; never why."""
    m = snap.get("maneuvers") or {}
    new = {id(e) for e in _new_changes(snap, archive_doc, now)}
    out = []
    for e in m.get("events") or []:
        t = _dt(e.get("to"))
        if not e.get("notable") or not (id(e) in new or (t and t >= now - timedelta(hours=HOURS))):
            continue
        parts = ["Notable: "] + _who(e) + [" (", {"cc": e.get("cc") or e.get("country")},
                                          f"; listed role on Orbit's GEO page: {e['notable']['role']}) "]
        parts += list(e.get("what") or []) + [f"; {_dv(e.get('dv_ms'))} m/s"] + _gap(e) + ["."]
        out.append({"kind": "notable", "href": "#maneuvers", "source": SOURCES["maneuver"], "parts": parts})
    return out


def orbit_changes(snap: dict, archive_doc: dict | None, now: datetime) -> dict | None:
    new = [e for e in _new_changes(snap, archive_doc, now) if not e.get("notable")]  # notable ones have their own line
    if not new:
        return None
    new.sort(key=lambda e: -(e.get("dv_ms") or 0))
    parts = ["Orbit lists " + _plural(len(new), "new orbit change") + " among the satellites it watches"]

    def render(e):
        out = _who(e) + [" (", {"cc": e.get("cc") or e.get("country")}, f", {e.get('regime')})"]
        if e.get("what"):  # a geostationary change: where it was and how it drifts now (orbit-2.26)
            out += [" "] + list(e["what"])
        return out + [f", {_dv(e.get('dv_ms'))} m/s between ", {"t": e.get("from")}, " and ", {"t": e.get("to")}]
    _names(parts, new, render)
    return {"kind": "orbit_change", "href": "#maneuvers", "source": SOURCES["maneuver"], "parts": parts}


def catalog(snap: dict, now: datetime) -> dict | None:
    stamp = gcat_stamp((snap.get("gcat_updated") or {}).get("satcat"))
    if stamp is None:
        return None
    age_h = (now - stamp).total_seconds() / 3600
    cc = snap.get("catalog_changes") or {}
    if age_h <= HOURS and cc.get("previous_reading_at"):
        parts = ["GCAT published a new copy at ", {"t": _iso(stamp)}, ": " + _plural(cc.get("added") or 0, "new entry", "new entries")]
        late, added = cc.get("added_late") or 0, cc.get("added") or 0
        if late:
            parts.append(" (all from launches over 30 days old)" if late == added else f" ({late} from launches over 30 days old)")
        owners = cc.get("owner_changes") or 0
        owners = len(owners) if isinstance(owners, list) else owners
        parts.append(f", {cc.get('changed') or 0} changed, {_plural(owners, 'owner change')}")
        groups = sorted(cc.get("late_groups") or [], key=lambda g: -(g.get("count") or 0))
        if groups:
            g = groups[0]
            kinds = ", ".join(_kind(k, n) for k, n in sorted((g.get("by_type") or {}).items(), key=lambda kv: -kv[1]))
            parts += ["; the largest group is ", kinds, " from launch ", g.get("launch_tag") or "", " (", {"d": g.get("launch_date")}, ")"]
        parts.append(".")
        return {"kind": "catalog", "href": "#catalog", "source": SOURCES["gcat"], "parts": parts}
    if age_h > GCAT_STALE_H:
        return {"kind": "stale", "href": "#catalog", "source": SOURCES["gcat"],
                "parts": ["GCAT has not published a new copy since ", {"t": _iso(stamp)}, f" (about {round(age_h)} hours): "
                          "the catalog, reentries, breakups and baseline cards carry that copy."]}
    return None


def breakups(snap: dict, now: datetime) -> dict | None:
    since = (now - timedelta(days=BREAKUP_DAYS)).date().isoformat()
    rows = [b for b in snap.get("breakups") or [] if (b.get("date") or b.get("breakup_date") or "") >= since]
    if not rows:
        return None
    parts = ["GCAT records " + _plural(len(rows), "breakup") + " in the last 7 days"]
    _names(parts, rows, lambda b: [_obj(b.get('name'), b.get('norad'), b.get('jcat')), " (", {"d": (b.get('date') or b.get('breakup_date'))[:10]}, ")"])
    return {"kind": "breakup", "href": "#breakups", "source": SOURCES["gcat"], "parts": parts}


def launches(snap: dict, now: datetime) -> dict | None:
    rows = [x for x in snap.get("launches") or [] if x.get("kind") == "orbital"
            and (t := _dt(x.get("time"))) and t >= now - timedelta(hours=HOURS)]
    if not rows:
        return None
    parts = ["Launched in the last 24 hours"]
    _names(parts, rows, lambda x: [f"{x.get('vehicle')} ({x.get('mission') or x.get('flight') or x.get('launch_tag')}) from "
                                   f"{(x.get('site') or {}).get('name') or x.get('site_code')} at ", {"t": x["time"]},
                                   f", {x.get('outcome') or 'outcome not yet given'}"])
    return {"kind": "launch", "href": "#launches", "source": SOURCES["gcat"], "parts": parts}


def baseline(snap: dict) -> dict | None:
    b = snap.get("baseline") or {}
    out = []
    for key, noun in (("reentries_all", "reentries"), ("launches_all", "orbital launches")):
        rows = b.get(key) or []
        if rows and rows[0].get("position") in ("above", "below"):
            r = rows[0]
            word = "fewer" if r["position"] == "below" else "more"
            out.append(f"{r['recent']} {noun}, {word} than in any 30-day stretch of the two years before "
                       f"({r['prior_min']}-{r['prior_max']}, median {r['prior_median']:g})")
    if not out:
        return None
    return {"kind": "baseline", "href": "#baseline", "source": SOURCES["baseline"],
            "parts": ["The last 30 days: " + "; ".join(out) + "."]}


def gaps(snap: dict) -> dict | None:
    names = {"decay": "TIP predictions", "maneuver": "orbit changes", "catalog": "GCAT"}
    out = []
    for lane, label in names.items():
        rec = _lane(snap, lane)
        if not rec or rec.get("status") == "off":
            continue
        if not _fresh(snap, lane):
            out.append(label + (" (kept copy)" if rec.get("from_previous") else " (not read)"))
    if not out:
        return None
    return {"kind": "gap", "href": "#sources", "source": "Orbit's run record",
            "parts": ["Not read on this run: " + ", ".join(out) + ". Their lines use the last copy Orbit holds."]}


def build(snap: dict, archive_doc: dict | None = None) -> dict:
    now = _dt(snap.get("generated_at")) or datetime.now(timezone.utc)
    lines = notable_changes(snap, archive_doc, now)
    lines += [x for x in (reentries_ahead(snap, now), reentries_done(snap, now), orbit_changes(snap, archive_doc, now),
                          breakups(snap, now), catalog(snap, now), launches(snap, now), baseline(snap)) if x]
    lines = lines[:MAX_LINES]
    g = gaps(snap)
    if g:
        lines.append(g)
    return {"at": _iso(now), "hours": HOURS, "lines": lines,
            "nothing_new": not any(x["kind"] not in ("baseline", "gap", "stale") for x in lines)}
