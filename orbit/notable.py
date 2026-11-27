"""What a geostationary orbit change did, in words, and which changes lead the page (orbit-2.26, 23 Nov 2026).

Tom, 23 Nov 2026, after Luch (Olymp) 2 left 62 E: Orbit listed "8.5 m/s between 15 Oct and 22 Nov" as one routine
row, and he heard of the move elsewhere. Two additions to a listed GEO change (orbit/maneuver.py), both from the
element sets already held, no request:

1. **What happened.** From the set before and the set after: the longitude and drift on each side, the kind of
   change in the GEO board's words (DRIFT_KEPT, 0.1 deg a day: under it an object holds its longitude), the
   direction, and the height above or below geostationary altitude that the drift rate implies (from the mean
   motion: a higher orbit circles slower than the Earth turns, so the satellite falls back to the west). How long
   it had held the earlier longitude is counted back through the sets Orbit holds for it, while each is under
   DRIFT_KEPT and within HELD_LON of that longitude; when the count reaches the first set held, the line says
   "in every element set Orbit holds since", because Orbit's sets start 60 days before it first read the object.
2. **Notable.** A change is notable when the object has a listed role on the GEO page (site_src/geo_roles.json,
   each entry with its published source), the change is not station-keeping (it started drifting, stopped, or
   changed its drift rate) and the drift rate changed by NOTABLE_RATE (0.25 deg a day, about 0.7 m/s along track)
   or more. Without that floor a roaming inspector that edges across the 0.1 line reads as notable: on the live
   snapshot of 23 Nov 2026 USA 270 "started drifting" at 0.12 deg a day on a 0.9 m/s change. A notable change is the first line of the daily lead, is marked in the archive, and
   goes into the public file /data/notable.json. Its feed item keeps tier "routine": a higher tier is Tom's call.

A line says which object, where and how fast, from which sets. It never says why, never names a destination and
is not a warning. The simple longitude (node + perigee argument + mean anomaly - sidereal time) holds for the low
inclinations of station-kept objects; an inclined object swings either side of it daily.

Sentences are lead `parts` (orbit/lead.py): text, {"t": time}, {"d": date}, so the page writes times in the
viewer's zone; text() gives the same sentence with UTC times for the feed.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from orbit import maneuver

SCHEMA = "orbit-notable/1"
DRIFT_KEPT = 0.1    # deg a day: the GEO board's line between station-kept and drifting (tools/geo_belt.py)
HELD_LON = 0.5      # deg: earlier sets within this of the longitude before the change count as the same place
NOTABLE_RATE = 0.25  # deg a day: the smallest change in drift rate that makes a listed-role change notable
KEPT, STARTED, STOPPED, RATE = "station-keeping", "started drifting", "stopped drifting", "drift rate changed"
NOTABLE_KINDS = (STARTED, STOPPED, RATE)
RULE = ("An object with a listed role on Orbit's GEO page whose listed orbit change is not station-keeping: it "
        "started drifting along the belt, stopped, or changed its drift rate (0.1 deg a day is the line between "
        "holding a longitude and drifting), by 0.25 deg a day or more. An observation from published element sets: "
        "not a warning, and no statement of why.")
GEO_A = maneuver._a(maneuver.SIDEREAL_REV_DAY)  # km from the Earth's centre


def kind(drift_before: float, drift_after: float) -> str:
    kept_b, kept_a = abs(drift_before) < DRIFT_KEPT, abs(drift_after) < DRIFT_KEPT
    if kept_b and kept_a:
        return KEPT
    if kept_b:
        return STARTED
    if kept_a:
        return STOPPED
    return RATE


def alt_km(drift_deg_day: float) -> float:
    """Height above (+) or below (-) geostationary altitude that a drift rate implies (east +)."""
    return round(maneuver._a(maneuver.SIDEREAL_REV_DAY + drift_deg_day / 360.0) - GEO_A, 1)


def held(sets: list, before_epoch: str, lon: float) -> dict | None:
    """How far back the object held `lon`: the earliest of the consecutive sets, ending with the one at
    before_epoch, that are under DRIFT_KEPT and within HELD_LON of it. `first_held` is true when that run reaches
    the first set Orbit holds, so the true start is unknown."""
    idx = next((i for i, s in enumerate(sets) if s[0] == before_epoch), None)
    if idx is None:
        return None
    first = idx
    for i in range(idx, -1, -1):
        p = maneuver.geo_position(sets[i])
        if abs(p["drift_deg_day"]) >= DRIFT_KEPT or abs(maneuver._wrap180(p["lon"] - lon)) > HELD_LON:
            break
        first = i
    return {"since": sets[first][0], "sets": idx - first + 1, "first_held": first == 0}


def _lon(x: float) -> str:
    x = maneuver._wrap180(x)
    return f"{abs(x):.2f}°{'E' if x >= 0 else 'W'}"


def _dir(x: float) -> str:
    return "east" if x > 0 else "west"


def _rate(x: float) -> str:
    return f"{_dir(x)} at {abs(x):.2f}° a day"


def _height(x: float) -> str:
    return f"about {abs(x):.0f} km {'above' if x > 0 else 'below'} geostationary altitude"


def describe(ev: dict, sets: list | None = None) -> dict | None:
    """The block added to a listed GEO change: {"kind", "alt_km_before", "alt_km_after", "held"?, "parts"}. `parts`
    is a predicate with no subject ("left 62.00°E ... and is drifting west ..."), so a line can put the name first."""
    g = ev.get("geo")
    if not g:
        return None
    b, a = g["drift_before"], g["drift_after"]
    k = kind(b, a)
    out = {"kind": k, "alt_km_before": alt_km(b), "alt_km_after": alt_km(a)}
    h = held(sets, ev["from"], g["lon_before"]) if sets and abs(b) < DRIFT_KEPT else None
    if h and h["sets"] > 1:
        out["held"] = h
    at = [_lon(g["lon_after"]), " by the element set of ", {"t": ev["to"]}]
    if k == STARTED:
        # "left" only when the sets show it somewhere else: USA 270, live 23 Nov 2026, crossed the line at 0.12 deg
        # a day with its longitude unchanged, and had left nothing.
        gone = abs(maneuver._wrap180(g["lon_after"] - g["lon_before"])) >= HELD_LON
        parts = ["left " if gone else "began to drift from ", _lon(g["lon_before"])]
        if out.get("held"):
            parts += [", where it had held position " + ("in every element set Orbit holds since " if h["first_held"]
                                                         else "since "), {"d": h["since"][:10]}, ","]
        parts += [(" and is drifting " if gone else " ") + f"{_rate(a)}, {_height(out['alt_km_after'])}; at "] + at
    elif k == STOPPED:
        parts = [f"was drifting {_rate(b)} and now holds "] + at + [f" (drift under {DRIFT_KEPT:g}° a day)"]
    elif k == RATE:
        if (a > 0) != (b > 0):
            change = f"reversed its drift, from {_rate(b)} to {_rate(a)}"
        else:
            change = (f"{'slowed' if abs(a) < abs(b) else 'sped up'} its drift {_dir(a)} from {abs(b):.2f}° to "
                      f"{abs(a):.2f}° a day")
        parts = [f"{change}, {_height(out['alt_km_after'])}; at "] + at
    else:
        moved = abs(maneuver._wrap180(g["lon_after"] - g["lon_before"])) >= DRIFT_KEPT
        parts = ([f"moved from {_lon(g['lon_before'])} to "] if moved else ["holds "]) + at + \
                [f" (station-keeping: drift under {DRIFT_KEPT:g}° a day before and after)"]
    out["parts"] = parts
    return out


def text(parts: list) -> str:
    """Parts as one plain string, times in UTC (for the feed and the public file)."""
    out = []
    for p in parts or []:
        if isinstance(p, str):
            out.append(p)
        elif "t" in p:
            out.append(p["t"][:16].replace("T", " ") + " UTC")
        elif "d" in p:
            out.append(p["d"])
        elif "s" in p:
            out.append(str(p["s"]))
    return "".join(out)


def roles_index(roles_doc: dict | None) -> dict[int, dict]:
    """site_src/geo_roles.json by catalog number: {norad: {"role", "role_text", "basis", "sources"}}."""
    words = (roles_doc or {}).get("roles") or {}
    return {int(o["id"]): {"role": o["role"], "role_text": words.get(o["role"]) or o["role"],
                           "basis": o.get("basis"), "sources": o.get("sources") or []}
            for o in (roles_doc or {}).get("objects") or []}


ROLE_CLAIMS = ("declared", "attributed")
ROLE_STATUSES = ("active", "retired", "uncertain")
_ROLE_DATE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?$")


def check_roles(roles_doc: dict | None, today: str | None = None) -> list[str]:
    """Problems in site_src/geo_roles.json, one line each; [] when every entry holds. Each object needs a unique
    catalog number, a name, a listed role, a basis, whether the role is declared or attributed, at least one
    source as [label, https URL], a status (active, retired or uncertain), the status date (YYYY-MM or YYYY-MM-DD,
    not after `today`) and a note saying who reports the status."""
    doc = roles_doc or {}
    words = doc.get("roles") or {}
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    objs = doc.get("objects")
    if not isinstance(objs, list) or not objs:
        return ["geo_roles: no objects"]
    errs, seen = [], set()
    for i, o in enumerate(objs):
        if not isinstance(o, dict):
            errs.append(f"geo_roles[{i}]: not an object")
            continue
        n = o.get("id")
        at = f"geo_roles[{i}] {n}"
        if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
            errs.append(f"{at}: id is not a catalog number")
        elif n in seen:
            errs.append(f"{at}: listed twice")
        seen.add(n)
        for k in ("name", "basis", "status_note"):
            if not str(o.get(k) or "").strip():
                errs.append(f"{at}: no {k}")
        if o.get("role") not in words:
            errs.append(f"{at}: role {o.get('role')!r} is not one of {sorted(words)}")
        if o.get("claim") not in ROLE_CLAIMS:
            errs.append(f"{at}: claim {o.get('claim')!r} is not declared or attributed")
        if o.get("status") not in ROLE_STATUSES:
            errs.append(f"{at}: status {o.get('status')!r} is not one of {list(ROLE_STATUSES)}")
        d = o.get("status_date")
        if not isinstance(d, str) or not _ROLE_DATE.match(d):
            errs.append(f"{at}: status_date {d!r} is not YYYY-MM or YYYY-MM-DD")
        elif d > today:
            errs.append(f"{at}: status_date {d} is after {today}")
        src = o.get("sources")
        if not isinstance(src, list) or not src:
            errs.append(f"{at}: no source")
        else:
            for s in src:
                if not (isinstance(s, list) and len(s) == 2 and str(s[0]).strip()
                        and str(s[1]).startswith("https://")):
                    errs.append(f"{at}: source {s!r} is not [label, https URL]")
    return errs


def mark(ev: dict, roles: dict[int, dict]) -> dict | None:
    """The notable block for a change, or None: a listed role and a change that is not station-keeping."""
    r = roles.get(ev.get("norad"))
    g = ev.get("geo") or {}
    k = g.get("kind")
    if not r or k not in NOTABLE_KINDS:
        return None
    if abs((g.get("drift_after") or 0.0) - (g.get("drift_before") or 0.0)) < NOTABLE_RATE:
        return None
    return {"rule": "listed-role-geo", "kind": k, "role": r["role"], "role_text": r["role_text"],
            "basis": r.get("basis")}


def enrich(events: list[dict], store: dict | None = None, roles: dict[int, dict] | None = None,
           names_idx: dict[int, dict] | None = None) -> None:
    """Add to each listed change, in place: `names` (the other names, when the name index was read this run; names
    set on an earlier run are kept otherwise), and for a GEO change `geo.kind`, the heights, `geo.held`, `what`
    (the sentence) and `notable`. Runs at the end of every collect, on new and carried changes alike."""
    from orbit import names as names_
    for ev in events or []:
        if names_idx is not None:
            also = names_.others(ev.get("gcat_name") or ev.get("name"), names_idx.get(ev.get("norad")))
            if also:
                ev["names"] = also
        sets = ((store or {}).get(str(ev.get("norad"))) or {}).get("sets")
        if not ev.get("geo"):
            continue
        if sets or not (ev.get("what") and ev["geo"].get("kind")):
            # Without the object's sets (no store on this run) a change described on an earlier run keeps that
            # description: only the sets can say how long it had held the longitude.
            d = describe(ev, sets)
            ev["what"] = d.pop("parts")
            ev["geo"].pop("held", None)
            ev["geo"].update(d)
        n = mark(ev, roles or {})
        if n:
            ev["notable"] = n
        else:
            ev.pop("notable", None)


def public(snap: dict, roles: dict[int, dict] | None = None, site: str = "") -> dict:
    """/data/notable.json: the notable changes in the snapshot, each readable alone."""
    m = snap.get("maneuvers") or {}
    items = []
    for e in m.get("events") or []:
        if not e.get("notable"):
            continue
        r = (roles or {}).get(e["norad"]) or {}
        name = e.get("gcat_name") or e.get("name")
        items.append({
            "id": f"orbit:maneuver:{e['norad']}:{e['from'][:10]}", "norad": e["norad"], "object_id": e.get("object_id"),
            "name": name, "names": e.get("names") or [], "country": e.get("cc") or e.get("country"),
            "kind": e["notable"]["kind"], "role": e["notable"]["role"],
            "role_text": e["notable"].get("role_text"), "role_basis": e["notable"].get("basis"),
            "role_sources": r.get("sources") or [],
            "what": f"{name} {text(e.get('what'))}.", "from": e["from"], "to": e["to"],
            "gap": e.get("gap"), "dv_ms": e.get("dv_ms"), "dominant": e.get("dominant"), "geo": e.get("geo"),
            "link": f"{site}/object?n={e['norad']}"})
    return {"schema": SCHEMA, "at": snap.get("generated_at"), "read_at": m.get("read_at"), "rule": RULE,
            "window_days": m.get("window_days"), "attribution": m.get("attribution"), "items": items}
