"""The GEO region: every object in and near the geostationary region from Space-Track, where each one is, and which
arrived or left. Behaviour only, never intent.

Moved from Noisefloor (`tools/geo_region.py`, built 27 Oct 2026) as step 2 of `doctrine/geo-move-plan.md` (
15-16 Nov 2026: the GEO belt is Orbit's subject; one Space-Track collector for the shared account). The region,
the edges and the event rules are Noisefloor's, unchanged, so the two programs' day files can be compared day by day
before Noisefloor's own query is switched off. What changed: standard library only (Orbit's live lanes), Orbit's
Space-Track client and shared-account checks, element sets in monthly JSON files (gzipped, columnar) instead of
parquet, and Orbit's public releases `geo-YYYY` instead of Noisefloor's `pnt-data-YYYY-MM`.

Data: Space-Track, USSPACECOM basic SSA data (blanket approval to redistribute and to publish analysis, with
citation). The "quiet" event's list of active payloads is CelesTrak's GEO group (GROUP=geo), one request a run, as
Noisefloor's GEO board reads it.

Region (as stated on Noisefloor's GEO page):
  near GEO    mean motion 0.9-1.1 rev/day and eccentricity under 0.3: what the daily query takes (not decayed)
  zone        perigee and apogee within GEO +-200 km (35,586-35,986 km altitude) and inclination 15 deg or less:
              the IADC geosynchronous protected region
  graveyard   perigee above the zone
  below       apogee below the zone
  crossing    inclination 15 deg or less, reaching into the zone's altitudes without staying inside them
  inclined    reaching the zone's altitudes with inclination over 15 deg
  edges       an object enters the zone only when 25 km (0.25 deg) inside its edges and leaves only when that far
              outside, so an orbit riding an edge doesn't flicker in and out
Events between consecutive days (each day's inventory is every object's latest element set by the end of that day):
  new, returned, arrived, left up, left down, left, quiet, gone (see `events`).
Files: `geo-elements-YYYY-MM.json.gz` (every element set held from HISTORY_START, by epoch month) and
`<day>.geo-region.json` (the day's regions, counts and events; a pull also carries the objects with their latest
elements, and the active list it used).
"""
from __future__ import annotations

import gzip
import json
import math
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta

from orbit import spacetrack

REPO = "metacog-osint/orbit"
CITE = "Orbital data: USSPACECOM (space-track.org)"
MU, RE = 398600.4418, 6378.137               # km^3/s^2, km
GEO_ALT, BAND, ZONE_INC = 35786.0, 200.0, 15.0
N_MIN, N_MAX, E_MAX = 0.9, 1.1, 0.3
QUIET_DAYS, NEW_LAUNCH_DAYS = 7, 365
EDGE_KM, EDGE_DEG = 25.0, 0.25               # hysteresis at the zone's edges
HISTORY_START = "2026-07-01"                 # the first epoch the monthly element files hold (Noisefloor's)
COLS = ["norad", "epoch", "n", "e", "i", "raan", "argp", "M", "bstar", "ndot", "nddot", "elset", "rev"]
OBJ_COLS = ["norad", "name", "cospar", "type", "owner", "launch", "rcs", "region", "epoch", "n", "e", "i", "raan", "argp",
            "M", "bstar", "ndot", "nddot", "elset", "rev"]   # Noisefloor's columns, plus elset and rev at the end
REGIONS = ["zone", "graveyard", "crossing", "inclined", "below"]
GP_URL = (spacetrack.BASE + "/basicspacedata/query/class/gp/decay_date/null-val/MEAN_MOTION/{}--{}/ECCENTRICITY/%3C{}"
          "/orderby/NORAD_CAT_ID%20asc/format/json").format(N_MIN, N_MAX, E_MAX)
ACTIVE_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=geo&FORMAT=json"


# ---------------------------------------------------------------- geometry and regions
def altitudes(n, e):
    """Perigee and apogee altitude (km) from mean motion (rev/day) and eccentricity."""
    a = (MU / (n * 2 * math.pi / 86400.0) ** 2) ** (1 / 3)
    return a * (1 - e) - RE, a * (1 + e) - RE


def near_geo(n, e):
    return n is not None and e is not None and N_MIN <= n <= N_MAX and e < E_MAX


def region_of(n, e, i, prev=None):
    """The region of an orbit. `prev`, the object's region the day before, moves the zone's edges: inward by
    EDGE_KM/EDGE_DEG for an object outside, outward for one inside, so edge-riders don't flicker."""
    perigee, apogee = altitudes(n, e)
    m, md = (0.0, 0.0) if prev is None else (-EDGE_KM, -EDGE_DEG) if prev == "zone" else (EDGE_KM, EDGE_DEG)
    if perigee >= GEO_ALT - BAND + m and apogee <= GEO_ALT + BAND - m and i <= ZONE_INC - md:
        return "zone"
    if perigee > GEO_ALT + BAND:
        return "graveyard"
    if apogee < GEO_ALT - BAND:
        return "below"
    if i > ZONE_INC:
        return "inclined"
    return "crossing"


# ---------------------------------------------------------------- records
def num(x, kind=float):
    if x is None or x == "":
        return None
    try:
        return kind(x)
    except (TypeError, ValueError):
        return None


def elset_row(g):
    """A Space-Track GP/GP_history record (all strings) -> the stored element set."""
    return {"norad": num(g.get("NORAD_CAT_ID"), int), "epoch": g.get("EPOCH"), "n": num(g.get("MEAN_MOTION")),
            "e": num(g.get("ECCENTRICITY")), "i": num(g.get("INCLINATION")), "raan": num(g.get("RA_OF_ASC_NODE")),
            "argp": num(g.get("ARG_OF_PERICENTER")), "M": num(g.get("MEAN_ANOMALY")), "bstar": num(g.get("BSTAR")),
            "ndot": num(g.get("MEAN_MOTION_DOT")), "nddot": num(g.get("MEAN_MOTION_DDOT")),
            "elset": num(g.get("ELEMENT_SET_NO"), int), "rev": num(g.get("REV_AT_EPOCH"), int)}


def static_row(g):
    return {"norad": num(g.get("NORAD_CAT_ID"), int), "name": g.get("OBJECT_NAME"), "cospar": g.get("OBJECT_ID"),
            "type": g.get("OBJECT_TYPE"), "owner": g.get("COUNTRY_CODE"), "launch": g.get("LAUNCH_DATE"),
            "rcs": g.get("RCS_SIZE")}


def end_of(day):
    return (datetime.strptime(day, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")


def age_days(epoch, at):
    """Days from an element epoch to a time (ISO strings, UTC)."""
    e = datetime.fromisoformat(epoch[:19])
    t = datetime.fromisoformat(at[:19]) if "T" in at else datetime.strptime(at[:10], "%Y-%m-%d")
    return (t - e).total_seconds() / 86400.0


# ---------------------------------------------------------------- inventories and events
def from_latest(latest, prev=None):
    """{norad: {region, epoch}} from each object's latest element set, near-GEO sets only; `prev` sets the edges."""
    prev = prev or {}
    return {k: {"region": region_of(r["n"], r["e"], r["i"], (prev.get(k) or {}).get("region")), "epoch": r["epoch"][:19]}
            for k, r in latest.items() if near_geo(r["n"], r["e"])}


def events(prev, cur, day, static, seen=None, active=None):
    """Membership events between two inventories. `seen`: norads ever near GEO before (defaults to prev's).
    `active`: catalogue numbers listed as active (None: every payload counts for "quiet").
      new       first seen near GEO, launched within the last year
      returned  first seen near GEO in our data, launched earlier (back after a gap in public elements)
      arrived   in the zone, and wasn't the day before
      left up   zone -> graveyard; left down: zone -> below; left: zone -> crossing or inclined
      quiet     an active payload in the zone whose latest elements passed 7 days old that day
      gone      near GEO the day before, not any more (decayed, moved away, or dropped from the public catalogue)"""
    seen = set(prev) if seen is None else seen
    end, out = end_of(day), []

    def ev(k, kind, rec, frm=None):
        s = static.get(k) or {}
        out.append({"day": day, "norad": k, "kind": kind, "name": s.get("name"), "owner": s.get("owner"), "type": s.get("type"),
                    "region": rec["region"], "from": frm, "epoch": rec["epoch"][:16]})
    for k, c in cur.items():
        p = prev.get(k)
        if p is None:
            if k not in seen:
                launch = (static.get(k) or {}).get("launch")
                recent = bool(launch) and age_days(launch + "T00:00:00", day) <= NEW_LAUNCH_DAYS
                ev(k, "new" if recent else "returned", c)
            if c["region"] == "zone":
                ev(k, "arrived", c, p and p["region"])
            continue
        if p["region"] != "zone" and c["region"] == "zone":
            ev(k, "arrived", c, p["region"])
        elif p["region"] == "zone" and c["region"] != "zone":
            ev(k, {"graveyard": "left up", "below": "left down"}.get(c["region"], "left"), c, p["region"])
        if (c["region"] == "zone" and (static.get(k) or {}).get("type") == "PAYLOAD" and (active is None or k in active)
                and age_days(c["epoch"], end) > QUIET_DAYS
                and age_days(p["epoch"], day) <= QUIET_DAYS):
            ev(k, "quiet", c, p["region"])
    for k, p in prev.items():
        if k not in cur:
            ev(k, "gone", p, p["region"])
    return out


def counts(inv, static):
    c = {r: {} for r in REGIONS}
    for k, v in inv.items():
        t = (static.get(k) or {}).get("type") or "UNKNOWN"
        c[v["region"]][t] = c[v["region"]].get(t, 0) + 1
    return c


def active_ids(body: bytes) -> set[int]:
    """CelesTrak's GEO group (OMM JSON) -> the catalogue numbers it lists as active."""
    doc = json.loads(body)
    if not isinstance(doc, list) or not doc:
        raise ValueError("CelesTrak's GEO group was empty or not a list")
    return {int(o["NORAD_CAT_ID"]) for o in doc if str(o.get("NORAD_CAT_ID", "")).isdigit()}


# ---------------------------------------------------------------- files
def month_of(epoch):
    return epoch[:7]


def elements_name(month):
    return f"geo-elements-{month}.json.gz"


def read_elements(path):
    if not os.path.exists(path):
        return []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        doc = json.load(f)
    cols = doc["cols"]
    return [dict(zip(cols, row)) for row in doc["rows"]]


def write_elements(path, rows):
    rows = sorted({(r["norad"], r["epoch"]): r for r in rows}.values(), key=lambda r: (r["norad"], r["epoch"]))
    doc = {"schema": "orbit-geo-elements/1", "source": CITE, "cols": COLS, "rows": [[r.get(c) for c in COLS] for r in rows]}
    with gzip.open(path + ".part", "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(doc, f, separators=(",", ":"))
    os.replace(path + ".part", path)
    return len(rows)


def merge_elements(out, rows):
    """Add element sets to the monthly files in `out`; returns {month: rows in the file} for the months that gained
    a set (an object whose latest set is months old touches that month's file without adding to it)."""
    by = {}
    for r in rows:
        if r["epoch"] >= HISTORY_START:
            by.setdefault(month_of(r["epoch"]), []).append(r)
    done = {}
    for m, new in sorted(by.items()):
        p = os.path.join(out, elements_name(m))
        held = read_elements(p)
        keys = {(r["norad"], r["epoch"]) for r in held}
        if os.path.exists(p) and all((r["norad"], r["epoch"]) in keys for r in new):
            continue
        done[m] = write_elements(p, held + new)
    return done


def region_file(out, day, inv, evs, static, objects=None, fetched=None, active=None):
    doc = {"schema": "orbit-geo-region/1", "day": day, "source": CITE, "fetched_utc": fetched,
           "definitions": {"geo_alt_km": GEO_ALT, "band_km": BAND, "zone_inclination_deg": ZONE_INC,
                           "near_geo": {"mean_motion": [N_MIN, N_MAX], "eccentricity_below": E_MAX}, "quiet_days": QUIET_DAYS},
           "counts": counts(inv, static), "events": evs,
           "regions": {str(k): [v["region"], v["epoch"][:19]] for k, v in sorted(inv.items())}}
    if objects is not None:
        doc["object_cols"] = OBJ_COLS
        doc["objects"] = objects
    if active is not None:
        doc["active"] = sorted(active)
    p = os.path.join(out, f"{day}.geo-region.json")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)
    return p


def load_region(out, day):
    p = os.path.join(out, f"{day}.geo-region.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


def yesterday(day):
    return (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- the day
def pull(day, out, records, active=None, fetched=None):
    """One gp reply -> today's region file and the element sets merged into the monthly files in `out`.
    Yesterday's region file (when in `out`) gives the edges and the events; a first day lists none.
    `active`: CelesTrak's active GEO list, or None to use yesterday's (and every payload when there is none).
    Returns (summary, paths written)."""
    os.makedirs(out, exist_ok=True)
    static = {s["norad"]: s for s in map(static_row, records) if s["norad"] is not None}
    rows = [r for r in map(elset_row, records) if r["norad"] is not None and r["epoch"]]
    merged = merge_elements(out, rows)
    latest = {}
    for r in rows:
        if r["norad"] not in latest or r["epoch"] > latest[r["norad"]]["epoch"]:
            latest[r["norad"]] = r
    prev_doc = load_region(out, yesterday(day))
    prev = {int(k): {"region": v[0], "epoch": v[1]} for k, v in prev_doc["regions"].items()} if prev_doc else None
    if active is None and prev_doc and prev_doc.get("active"):
        active = set(prev_doc["active"])           # CelesTrak not read this run: yesterday's list
    inv = from_latest(latest, prev)
    evs = events(prev, inv, day, static, active=active) if prev is not None else []
    objects = []
    for k in sorted(inv):
        s, r = static.get(k, {}), latest[k]
        objects.append([k, s.get("name"), s.get("cospar"), s.get("type"), s.get("owner"), s.get("launch"), s.get("rcs"),
                        inv[k]["region"], r["epoch"], r["n"], r["e"], r["i"], r["raan"], r["argp"], r["M"], r["bstar"],
                        r["ndot"], r["nddot"], r["elset"], r["rev"]])
    path = region_file(out, day, inv, evs, static, objects, fetched, active)
    c = counts(inv, static)
    summary = {"day": day, "objects": len(inv), "zone": sum(c["zone"].values()), "graveyard": sum(c["graveyard"].values()),
               "events": len(evs), "first_day": prev is None, "active_listed": None if active is None else len(active),
               "element_months": merged}
    return summary, [path] + [os.path.join(out, elements_name(m)) for m in merged]


# ---------------------------------------------------------------- releases (gh, on GitHub's runners)
def tag_for(name):
    """The public release for a file: `geo-YYYY` by the year in its name (day files and element months)."""
    stem = name[len("geo-elements-"):] if name.startswith("geo-elements-") else name
    return "geo-" + stem[:4]


class ReleaseError(RuntimeError):
    """A file the release holds could not be read whole, or an upload would lose element sets the release holds, or
    the copy of a file about to be replaced could not be archived. Nothing is uploaded; the run fails."""


def _gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def _repo(repo):
    return repo or os.environ.get("GITHUB_REPOSITORY", REPO)


PART = ".part"   # an upload in progress: release_put uploads each file under <name>.part, then swaps it in


def _release_files(repo, tag):
    """{asset name: (id, bytes, state)} for release `tag`, or None when the release does not exist (HTTP 404). Any
    other failure to read or list raises ReleaseError. `state` is GitHub's: "uploaded" for a whole file."""
    r = _gh("api", f"repos/{repo}/releases/tags/{tag}", "--jq", ".id")
    if r.returncode and "HTTP 404" in r.stderr:
        return None
    if r.returncode or not r.stdout.strip():
        raise ReleaseError(f"release {tag} could not be read: {r.stderr.strip()[:300]}")
    r = _gh("api", "--paginate", f"repos/{repo}/releases/{r.stdout.strip()}/assets?per_page=100",
            "--jq", '.[] | "\\(.id) \\(.size) \\(.state) \\(.name)"')
    if r.returncode:
        raise ReleaseError(f"the files on release {tag} could not be listed: {r.stderr.strip()[:300]}")
    files = {}
    for line in r.stdout.splitlines():
        parts = line.strip().split(" ", 3)
        if len(parts) == 4:
            files[parts[3]] = (parts[0], int(parts[1]), parts[2])
    return files


def _asset_call(repo, method, asset_id, *fields):
    return _gh("api", "-X", method, f"repos/{repo}/releases/assets/{asset_id}", *fields)


def _rename(repo, asset_id, name):
    return _asset_call(repo, "PATCH", asset_id, "-f", f"name={name}")


def release_assets(tags, repo=None):
    """{asset name: bytes} for the files on the releases `tags`. A release that does not exist (HTTP 404) holds
    nothing; any other failure to list raises ReleaseError, so a file is never taken as absent because a listing
    failed. Uploads in progress (`<name>.part`) are not listed. One that is whole while `<name>` is missing is an
    upload stopped between removing the old copy and renaming the new one (release_put): the rename is finished
    here, and logged, before anything reads the list."""
    repo = _repo(repo)
    held = {}
    for tag in sorted(set(tags)):
        files = _release_files(repo, tag)
        for name, (asset_id, size, state) in (files or {}).items():
            if not name.endswith(PART):
                held[name] = size
                continue
            final = name[: -len(PART)]
            if final in files or state != "uploaded":
                continue   # the old copy is still there, or the upload did not finish: release_put replaces it
            r = _rename(repo, asset_id, final)
            if r.returncode:
                raise ReleaseError(f"{final} is not on release {tag}, but its whole upload {name} is, and could not "
                                   f"be renamed: {r.stderr.strip()[:300]}; the next run tries again")
            print(f"{final}: finished the upload a run left as {name} on release {tag} ({size} bytes)")
            held[final] = size
    return held


def release_get(names, out, repo=None, held=None):
    """Download into `out` the files in `names` that the releases hold (`held`, from release_assets; listed here
    when not given). A file the release holds that does not download whole (an error, or a size other than the
    listed one) raises ReleaseError. Files the release does not hold are skipped. Returns the names downloaded."""
    repo = _repo(repo)
    if held is None:
        held = release_assets({tag_for(n) for n in names}, repo)
    got = []
    for name in names:
        if name not in held:
            continue
        r = _gh("release", "download", tag_for(name), "-R", repo, "-p", name, "-D", out, "--clobber")
        p = os.path.join(out, name)
        size = os.path.getsize(p) if os.path.exists(p) else None
        if r.returncode or size != held[name]:
            why = r.stderr.strip()[:300] if r.returncode else f"{size} of {held[name]} bytes"
            raise ReleaseError(f"{name} is on release {tag_for(name)} but did not download whole ({why})")
        got.append(name)
    return got


def element_keys(path):
    """The (norad, epoch) of every element set in a month file."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        doc = json.load(f)
    k, e = doc["cols"].index("norad"), doc["cols"].index("epoch")
    return {(row[k], row[e]) for row in doc["rows"]}


def check_new_months(months, held, day):
    """A month file the release does not hold is started only for `day`'s month or a later one, and only while the
    release holds no day file of that month. A past month that is not on the release is a lost file or a wrong
    listing, never a month to rebuild from one reply's sets. So is a current month whose day files are on the
    release: a run that wrote a day file of the month also wrote the month's element sets, so the file was there
    and has gone (a replace that failed after the old file was removed, or a removal by hand)."""
    missing = [m for m in sorted(months) if elements_name(m) not in held]
    gone = [m for m in missing if m < month_of(day)]
    if gone:
        raise ReleaseError(f"{', '.join(map(elements_name, gone))} not on the release, though the month has passed; "
                           "a past month is never rebuilt from one reply")
    started = {m: sorted(n for n in held if n.startswith(m + "-") and n.endswith(".geo-region.json"))
               for m in missing}
    lost = [m for m in missing if started[m]]
    if lost:
        days = "; ".join(f"{elements_name(m)}: {len(started[m])} day file(s) of the month, the last "
                         f"{started[m][-1][:10]}" for m in lost)
        raise ReleaseError(f"{', '.join(map(elements_name, lost))} not on the release, though it holds day files of "
                           f"that month ({days}), so the month file was there and has gone; a month is never rebuilt "
                           "from one reply. Since orbit-2.36 each copy replaced is kept in the private archive "
                           "(lane geo-release) and each run's reply in lane geo-reply: restore the file to the "
                           "release from there, then run again")


def _swap_in(repo, tag, path):
    """Upload `path` to release `tag` under a temporary name and swap it in for the file of the same name, so a
    failure at any point leaves the release with its old copy or a whole `<name>.part` that release_assets finishes
    on the next run, never without the file for the length of an upload (`gh release upload --clobber` removes the
    old copy first). The release is without `<name>` only between the two short calls that remove the old copy
    and rename the new one."""
    name = os.path.basename(path)
    part = name + PART
    stale = (_release_files(repo, tag) or {}).get(part)
    if stale and _asset_call(repo, "DELETE", stale[0]).returncode:
        raise RuntimeError(f"upload of {name} not started: an earlier {part} on release {tag} could not be removed")
    with tempfile.TemporaryDirectory(prefix="geo-upload-") as tmp:
        staged = os.path.join(tmp, part)
        shutil.copyfile(path, staged)
        r = _gh("release", "upload", tag, "-R", repo, staged)
    if r.returncode:
        raise RuntimeError(f"upload of {name} failed: {r.stderr.strip()[:300]}; the release keeps its copy")
    files = _release_files(repo, tag) or {}
    up, want = files.get(part), os.path.getsize(path)
    if not up or up[1] != want or up[2] != "uploaded":
        if up:
            _asset_call(repo, "DELETE", up[0])   # a bad copy of the local file; the release keeps its own
        got = f"{up[1]} bytes, {up[2]}" if up else "not listed"
        raise RuntimeError(f"upload of {name} did not arrive whole ({got}, of {want} bytes); the release keeps its copy")
    old = files.get(name)
    if old and _asset_call(repo, "DELETE", old[0]).returncode:
        raise RuntimeError(f"{name}: the old copy on release {tag} could not be removed, so the new one stays as "
                           f"{part}; the release keeps its copy")
    r = _rename(repo, up[0], name)
    if r.returncode:
        raise RuntimeError(f"{name}: uploaded whole as {part} on release {tag} but not renamed "
                           f"({r.stderr.strip()[:300]}); the next run finishes the rename")


def release_put(paths, repo=None, archive=None):
    """Upload `paths` to their releases geo-YYYY, replacing the files of the same name. First every file the
    releases already hold under those names is downloaded again and checked: a month file that would lose any
    element set (norad, epoch) the release holds is refused, and the release copies about to be replaced go to
    `archive(folder)`, which must succeed (geo_pull: a dated copy in the private tic-archive). With an archive, the
    files about to go up are copied there too, so the archive alone holds every version the releases have held.
    Any failure raises ReleaseError before the first upload. Each file is then swapped in (_swap_in), never
    uploaded over the old copy."""
    repo = _repo(repo)
    names = [os.path.basename(p) for p in paths]
    held = release_assets({tag_for(n) for n in names}, repo)
    with tempfile.TemporaryDirectory(prefix="geo-replaced-") as tmp:
        replaced = release_get([n for n in names if n in held], tmp, repo, held)
        for p in paths:
            name = os.path.basename(p)
            if name in replaced and name.startswith("geo-elements-"):
                old = element_keys(os.path.join(tmp, name))
                lost = old - element_keys(p)
                if lost:
                    raise ReleaseError(f"{name}: the upload would drop {len(lost):,} of the {len(old):,} element sets "
                                       f"on release {tag_for(name)}; refused, nothing uploaded")
        if replaced:
            if archive is None:
                raise ReleaseError(f"{', '.join(replaced)} would be replaced with no archive copy; refused")
            archive(tmp)
    if archive is not None:  # the new copies, in the same lane: the next run's replaced copies then add no bytes
        with tempfile.TemporaryDirectory(prefix="geo-upload-") as up:
            for p in paths:
                shutil.copyfile(p, os.path.join(up, os.path.basename(p)))
            archive(up)
    for p in paths:
        tag = tag_for(os.path.basename(p))
        if _gh("release", "view", tag, "-R", repo).returncode:
            r = _gh("release", "create", tag, "-R", repo, "--title", f"GEO region {tag[4:]}", "--latest=false", "--notes",
                    "Orbit's GEO region: every object near the geostationary region from Space-Track, daily "
                    "(<day>.geo-region.json, schema orbit-geo-region/1) and the element sets held, by epoch month "
                    "(geo-elements-YYYY-MM.json.gz, schema orbit-geo-elements/1). Orbital data: USSPACECOM "
                    "(space-track.org). Method: orbit/geo_region.py.")
            if r.returncode:
                raise RuntimeError(f"release {tag} could not be created: {r.stderr.strip()[:300]}")
        _swap_in(repo, tag, p)
