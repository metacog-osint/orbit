"""Footprints page (ideas#232): builds the data for site_src/footprints.html. Published as
site_src/footprints-data.json (24 Nov 2026: publish), built here from the research folder and committed.

    python tools/footprints.py build --day-file DAY.geo-region.json --tle-dir DIR [--published DIR] --out FILE
    python tools/footprints.py preview --json FILE --dir FOLDER      a small standalone copy of the page to serve
    python tools/footprints.py gateways --gateways FILE [--data FILE]  add or refresh only the FCC earth-station layer

Earth stations (decision 5): with --gateways (the file tools/ibfs_gateways.py writes from the FCC's IBFS bulk
database), each case that names its satellite's IBFS entries under "fcc_earth_stations" gets a published layer of
the sites licensed to work that satellite, a table of every licence, and the bulk file's age at build time. Names
are matched exactly, never guessed: a case with no entry gets a note saying none was matched.

Three cases, each outline labelled published, computed or estimated (orbit/footprint.py says what those mean):
a wide-beam GEO satellite, a high-throughput GEO satellite and a LEO constellation. The cases and every assumption
are in doctrine/footprint-cases.json. A fourth kind, measured, marks terminals seen in use (the LEO case).
Published contours are read from --published and are NOT committed (24 Nov 2026: filed contours may be
redrawn on the page with credit; the files stay out of the repository until the page is approved). Without
--published the estimates are still drawn, with no score, and a case note says which files were missing.

Build-time only, like the GEO callouts: numpy and sgp4 (tools/requirements-callouts.txt). No request to
Space-Track, CelesTrak or any operator: positions come from files the caller already holds.
"""
import argparse
import json
import math
import pathlib
import shutil
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from orbit import footprint as fp  # noqa: E402

CASES = ROOT / "doctrine" / "footprint-cases.json"
KINDS = {"published": "A contour the operator filed or published, drawn as given.",
         "computed": "Exact geometry from the satellite's position.",
         "estimated": "A beam drawn from stated assumptions; error unknown unless scored against a published contour.",
         "measured": "Places where a terminal on the network was seen in use: a lower bound; no point shows nothing."}
MU = 398600.4418            # km3/s2
R_SPHERE = 6371.0088        # km: the LEO view test uses a spherical Earth (error under 0.2 deg of arc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def feature(geometry, **props):
    return {"type": "Feature", "properties": props, "geometry": geometry}


def polygon(ring):
    return {"type": "Polygon", "coordinates": [fp.unwrap(ring)]}


def bounds(rings, pad=3.0):
    pts = [p for r in rings for p in fp.unwrap(r)]
    lons, lats = [p[0] for p in pts], [p[1] for p in pts]
    return [[max(min(lons) - pad, -360), max(min(lats) - pad, -85)], [min(max(lons) + pad, 360), min(max(lats) + pad, 85)]]


# ---------------------------------------------------------------- satellite positions from files already held
def gmst(jd_ut1):
    t = (jd_ut1 - 2451545.0) / 36525.0
    sec = 67310.54841 + (876600 * 3600 + 8640184.812866) * t + 0.093104 * t * t - 6.2e-6 * t ** 3
    return math.radians((sec % 86400) / 240.0) % (2 * math.pi)


def jday(t):
    y, m = t.year, t.month
    jd = (367 * y - int(7 * (y + int((m + 9) / 12)) / 4) + int(275 * m / 9) + t.day + 1721013.5)
    return jd, (t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1e6) / 86400.0


def geo_object(day_file, norad, when):
    """Earth-fixed position (km) of an object in an Orbit GEO day file at a time, by SGP4 from its latest set."""
    from sgp4.api import WGS72, Satrec
    doc = json.loads(pathlib.Path(day_file).read_text(encoding="utf-8"))
    cols = doc["object_cols"]
    row = next((dict(zip(cols, r)) for r in doc["objects"] if r[0] == norad), None)
    if row is None:
        raise SystemExit(f"NORAD {norad} is not in {day_file}")
    epoch = datetime.fromisoformat(row["epoch"]).replace(tzinfo=timezone.utc)
    sat = Satrec()
    sat.sgp4init(WGS72, "i", norad, (epoch - datetime(1949, 12, 31, tzinfo=timezone.utc)).total_seconds() / 86400.0,
                 row["bstar"], 0.0, 0.0, row["e"], math.radians(row["argp"]), math.radians(row["i"]),
                 math.radians(row["M"]), row["n"] * 2 * math.pi / 1440.0, math.radians(row["raan"]))
    jd, fr = jday(when)
    err, r, _ = sat.sgp4(jd, fr)
    if err:
        raise SystemExit(f"SGP4 error {err} for {norad}")
    g = gmst(jd + fr)
    pos = (r[0] * math.cos(g) + r[1] * math.sin(g), -r[0] * math.sin(g) + r[1] * math.cos(g), r[2])
    lat, lon, h = fp.geodetic(pos)
    return pos, {"norad": norad, "name": row["name"], "owner": row["owner"], "lon": round(lon, 3), "lat": round(lat, 3),
                 "height_km": round(h), "inclination_deg": row["i"], "elements_epoch": row["epoch"][:19] + "Z",
                 "position_at": iso(when), "position_source": doc.get("source", "")}


# ---------------------------------------------------------------- a LEO constellation from its element sets
def read_tles(path):
    from sgp4.api import Satrec
    lines = [l.rstrip() for l in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    out = []
    for i in range(0, len(lines) - 2, 3):
        if lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            out.append((lines[i].strip(), Satrec.twoline2rv(lines[i + 1], lines[i + 2])))
    return out


def leo_case(case, tle_dir, when):
    """Computed only: from each satellite's orbit, how many stand above the service elevation angle at each
    latitude through a day, and where they are at one instant."""
    import numpy as np
    from sgp4.api import SatrecArray
    sats = read_tles(pathlib.Path(tle_dir) / case["tle_file"])
    alt = np.array([(MU / (s.no_kozai / 60.0) ** 2) ** (1 / 3) - R_SPHERE for _, s in sats])
    inc = np.degrees(np.array([s.inclo for _, s in sats]))
    ecc = np.array([s.ecco for _, s in sats])
    serving = (alt >= case["min_alt_km"]) & (alt <= case["max_alt_km"]) & (ecc < 0.005)
    recs = [s for (_, s), ok in zip(sats, serving) if ok]
    step, hours = case.get("step_s", 300), case.get("hours", 24)
    times = [when + timedelta(seconds=step * k) for k in range(int(hours * 3600 / step))]
    jd = np.array([jday(t)[0] for t in times])
    fr = np.array([jday(t)[1] for t in times])
    err, r, _ = SatrecArray(recs).sgp4(jd, fr)                 # (satellites, times, 3), km, TEME
    good = (err == 0).all(axis=1)
    r = r[good]
    elev = math.radians(case["min_elevation_deg"])
    band = case.get("band_deg", 2.0)
    lats = np.arange(-90 + band / 2, 90, band)
    lons = np.arange(-180 + 3, 180, 6.0)
    la, lo = np.meshgrid(np.radians(lats), np.radians(lons), indexing="ij")
    ground = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], axis=-1).reshape(-1, 3).astype(np.float32)
    far = case.get("min_elevation_north")            # a lower filed angle at high northern latitudes
    elev_n = math.radians(far["deg"]) if far else elev
    north = (np.degrees(la).reshape(-1) >= (far["from_lat"] if far else 91))
    angle = f"{case['min_elevation_deg']:g} degrees" + (f" ({far['deg']:g} degrees from {far['from_lat']:g} north)" if far else "")
    total = np.zeros(len(lats)); covered = np.zeros(len(lats)); least = np.full(len(lats), 1e9)
    snapshot = None
    for k in range(len(times)):
        g = gmst(jd[k] + fr[k])
        x = r[:, k, 0] * math.cos(g) + r[:, k, 1] * math.sin(g)
        y = -r[:, k, 0] * math.sin(g) + r[:, k, 1] * math.cos(g)
        z = r[:, k, 2]
        dist = np.sqrt(x * x + y * y + z * z)
        unit = np.stack([x / dist, y / dist, z / dist], axis=-1).astype(np.float32)
        # a satellite at radius d is above elevation e within central angle acos(R cos e / d) - e of its sub-point
        reach = np.cos(np.arccos(np.clip(R_SPHERE * math.cos(elev) / dist, -1, 1)) - elev).astype(np.float32)
        reach_n = np.cos(np.arccos(np.clip(R_SPHERE * math.cos(elev_n) / dist, -1, 1)) - elev_n).astype(np.float32)
        counts = np.zeros(len(ground))
        for a in range(0, len(ground), 1500):
            dots = ground[a:a + 1500] @ unit.T
            lim = np.where(north[a:a + 1500, None], reach_n[None, :], reach[None, :])
            counts[a:a + 1500] = (dots >= lim).sum(axis=1)
        counts = counts.reshape(len(lats), len(lons))
        total += counts.mean(axis=1)
        covered += (counts > 0).mean(axis=1)
        least = np.minimum(least, counts.min(axis=1))
        if k == 0:
            snapshot = [[round(float(math.degrees(math.atan2(yy, xx))), 2), round(float(math.degrees(math.asin(zz / dd))), 2)]
                        for xx, yy, zz, dd in zip(x, y, z, dist)]
    n = len(times)
    feats = []
    for i, lat in enumerate(lats):
        s, nn = float(lat - band / 2), float(lat + band / 2)
        feats.append(feature({"type": "Polygon", "coordinates": [[[-180, s], [180, s], [180, nn], [-180, nn], [-180, s]]]},
                             lat=float(lat), mean_in_view=round(float(total[i] / n), 2),
                             share_time=round(float(covered[i] / n), 4), least_in_view=int(least[i])))
    full = [float(l) for l, c in zip(lats, covered / n) if c >= 0.999]
    groups = {}
    for a, i, ok in zip(alt, inc, serving):
        key = round(float(i) * 2) / 2
        g_ = groups.setdefault(key, {"serving": 0, "other": 0, "alts": []})
        g_["serving" if ok else "other"] += 1
        if ok:
            g_["alts"].append(float(a))
    rows = [[f"{k:g}", v["serving"], v["other"], (f"{sorted(v['alts'])[len(v['alts']) // 2]:.0f}" if v["alts"] else "")]
            for k, v in sorted(groups.items()) if v["serving"] + v["other"] >= 5]
    mean_max = max(f["properties"]["mean_in_view"] for f in feats)
    peak = max(feats, key=lambda f: f["properties"]["mean_in_view"])["properties"]["lat"]
    src, date = case["tle_source"], case["tle_date"]
    layers = [
        {"id": "inview", "kind": "computed", "fill": True, "fill_by": "mean_in_view", "fill_max": mean_max, "no_line": True,
         "label": f"Satellites above the service angle of {angle}, mean over {hours:g} hours, by {band:g}-degree latitude band (heavier shading is more)",
         "source": src, "source_url": case.get("tle_url"), "date": date,
         "uncertainty": "Geometry only: no gateways, licences, capacity or terminals. Spherical Earth; a few km at band edges.",
         "geojson": {"type": "FeatureCollection", "features": feats}},
        {"id": "sats", "kind": "computed", "point_radius": 1.3, "point_opacity": 0.5, "on": False,
         "label": f"Where the {int(good.sum()):,} serving satellites were at {iso(when)[:16].replace('T', ' ')} UTC",
         "source": src, "source_url": case.get("tle_url"), "date": date,
         "uncertainty": "SGP4 from public element sets: about 1 km at the set's epoch, growing by a few km a day.",
         "geojson": {"type": "FeatureCollection", "features": [feature({"type": "MultiPoint", "coordinates": snapshot})]}},
    ]
    if case.get("measured_file") and (pathlib.Path(tle_dir) / case["measured_file"]).exists():
        m = case["measured"]
        rows_m = json.loads((pathlib.Path(tle_dir) / case["measured_file"]).read_text(encoding="utf-8"))["results"]
        pts = [x["geometry"]["coordinates"] for x in rows_m if x.get("geometry")]
        layers.append({"id": "measured", "kind": "measured", "point_radius": 3.5, "on": True,
                       "label": f"{m['label']} ({len(pts)} points, {len({x['country_code'] for x in rows_m if x.get('geometry')})} countries)",
                       "source": m["source"], "source_url": m.get("source_url"), "date": m.get("date"), "uncertainty": m["uncertainty"],
                       "geojson": {"type": "FeatureCollection", "features": [feature({"type": "MultiPoint", "coordinates": pts})]}})
    notes = list(case.get("notes", []))
    if full:
        span = ("at every latitude, pole to pole" if len(full) == len(lats) else
                f"between {abs(min(full)) + band / 2:g} degrees south and {max(full) + band / 2:g} degrees north")
        notes.insert(0, f"At least one serving satellite stood above the service angle of {angle} for all of the "
                        f"{hours:g} hours {span}. The most were in view near {abs(peak):g} degrees latitude "
                        f"({mean_max:.0f} on average); the fewest at any moment anywhere was {int(least.min())}.")
    return {"id": case["id"], "title": case["title"], "class": case["class"], "summary": case["summary"], "layers": layers,
            "bounds": [[-170, -70], [170, 78]], "notes": notes,
            "tables": [{"title": "Orbits in the element sets", "note": f"Grouped by inclination to the nearest half degree. Serving: {case['min_alt_km']:g} to {case['max_alt_km']:g} km and near-circular; the rest are raising, lowering or spare.",
                        "columns": ["Inclination, degrees", "Serving", "Other", "Median altitude of serving, km"], "rows": rows}],
            "counts": {"in_file": len(sats), "serving": int(serving.sum()), "propagated": int(good.sum())}}


# ---------------------------------------------------------------- GEO cases
def area_rings(countries_file, codes, box=None):
    """Outlines of the named countries. `box` [west, south, east, north] keeps only the parts wholly inside it, so
    an overseas territory (French Guiana, Svalbard, the Canaries) does not stretch a beam fitted to the mainland."""
    doc = json.loads(pathlib.Path(countries_file).read_text(encoding="utf-8"))
    rings = [r for c in doc["countries"] if c["cc"] in codes for r in c["rings"]]
    if box:
        w, s_, e, n = box
        rings = [r for r in rings if all(w <= lon <= e and s_ <= lat <= n for lon, lat in r)]
    if not rings:
        raise SystemExit(f"no country outlines for {codes}")
    return rings


def read_published(path, b):
    """One filed beam from a GXT text file or a GIMS database block saved as .bin (see orbit.footprint)."""
    if b.get("format") == "kml" or path.suffix.lower() == ".kml":
        return fp.parse_eirp_kml(path.read_bytes(), b.get("beam_id"))
    if b.get("format") == "geojson_contours":
        return fp.parse_contour_geojson(path.read_bytes(), b.get("unit", "dBW"), b.get("beam_id"))
    if b.get("format") == "gims_block" or path.suffix.lower() == ".bin":
        return fp.parse_gims_block(path.read_bytes(), b.get("beam_id"), b.get("emi_rcp"), b.get("polar"))
    doc = fp.parse_gxt(path.read_bytes().decode("cp1252"))
    want = [x for x in doc["beams"] if not b.get("beam_id") or (x["beam_id"] or "").strip() == b["beam_id"]]
    if not want:
        raise SystemExit(f"{path}: no beam {b.get('beam_id')}")
    return want[0]


def contour_words(beam, level, short=False):
    """How a published contour is named on the page, by its unit."""
    unit = beam.get("unit")
    if unit == "dBW":
        return f"operator's contour, {level:g} dBW downlink EIRP" if short else f"operator's contour at {level:g} dBW downlink EIRP, redrawn"
    if unit == "dB/K":
        return f"operator's contour, {level:g} dB/K uplink G/T" if short else f"operator's contour at {level:g} dB/K uplink G/T, redrawn"
    return f"filed contour, {level:g} dB" if short else f"filed contour at {level:g} dB from the beam's peak"


def level_rings(sat, beam, level, bore):
    """The contours of one level: the main ring (the one holding the boresight, with open parts joined along the
    Earth's edge), every ring to draw, and whether any part was joined."""
    got = [c for c in beam["contours"] if c["gain_db"] is not None and abs(c["gain_db"] - level) < 0.01]
    closed = [c["ring"] for c in got if c["closed"]]
    open_ = [c["ring"] for c in got if not c["closed"] and len(c["ring"]) >= 2]
    joined = fp.close_on_horizon(sat, open_, bore) if open_ and bore else None
    rings = closed + ([joined] if joined else [])
    if not rings:
        return None, [], False
    main = joined
    if main is None and not bore:              # no boresight (an operator's KML): the largest ring by area
        main = max(rings, key=lambda r: fp.overlap(r, r, 2000)["published_km2"])
    if main is None and bore:
        for r in closed:
            v = fp._vec(*bore)
            e1, e2 = fp._plane(v)
            if fp._inside([fp._project(fp._vec(*p), v, e1, e2) for p in r], 0.0, 0.0):
                main = r
                break
    return main or max(rings, key=len), rings, joined is not None


def geo_case(case, day_file, published_dir, when):
    sat, info = geo_object(day_file, case["norad"], when)
    pos_src = "Orbit's GEO day file (element sets: Space-Track.org, USSPACECOM)"
    layers, rings_all, scores, est_rings = [], [], [], []
    for e in case.get("line_of_sight_deg", [5]):
        ring = fp.los_contour(sat, e)
        rings_all.append(ring)
        layers.append({"id": f"los{e}", "kind": "computed", "label": f"Line of sight: the satellite is {e:g} degrees or more above the horizon",
                       "source": pos_src, "date": info["elements_epoch"][:10], "on": e == case.get("line_of_sight_deg", [5])[0],
                       "uncertainty": "Position to a few km; the outline to well under 0.1 degree. Terrain and buildings not included.",
                       "geojson": {"type": "FeatureCollection", "features": [feature(polygon(ring), elevation_deg=e)]}})
    published, beams, left_out = {}, {}, []
    for b in case.get("published", []):
        path = pathlib.Path(published_dir or "") / b["file"] if published_dir else None
        if not path or not path.exists():
            if published_dir:                          # named but not found: say so on the page, never drop it quietly
                left_out.append(f"The published contour file for {b['label']} ({b['file']}) was not found for this build, "
                                "so it is not drawn and nothing is scored against it.")
            continue
        beam = read_published(path, b)
        beams[b["id"]] = beam
        bore = beam["boresights"][0]["point"] if beam["boresights"] else b.get("near")
        for level in b.get("levels_db", []):
            main, rings, joined = level_rings(sat, beam, level, bore)
            if not main:
                continue
            lid = f"pub-{b['id']}-{abs(level):g}"
            published[(b["id"], level)] = main
            rings_all += rings
            note = " Parts that reach the Earth's edge as the satellite sees it are closed along that edge." if joined else ""
            what = contour_words(beam, level)
            layers.append({"id": lid, "kind": "published", "label": f"{b['label']}: {what}", "on": b.get("on", True),
                           "source": b["source"], "source_url": b.get("source_url"), "date": b.get("date"),
                           "uncertainty": b.get("uncertainty", "As filed. A filing shows the design, not a measurement, and may predate launch.") + note,
                           "geojson": {"type": "FeatureCollection", "features": [feature(polygon(r), gain_db=level, beam=beam.get("beam_id"),
                                                                                         emi_rcp=beam.get("emi_rcp")) for r in rings]}})
    for est in case.get("estimates", []):
        if est["method"] == "gain":
            aim = est.get("aim")
            if est.get("aim_from"):                    # the filed boresight of a published beam
                src = beams.get(est["aim_from"])
                if not src or not src["boresights"]:
                    if published_dir:
                        left_out.append(f"The estimate '{est['label']}' is not drawn: it is aimed at a published beam's "
                                        "boresight, and that beam was not read.")
                    continue
                aim = src["boresights"][0]["point"]
            peak = est.get("peak_gain_dbi") or (beams.get(est.get("aim_from")) or {}).get("peak_dbi")
            if peak is None:
                left_out.append(f"The estimate '{est['label']}' is not drawn: no peak gain was filed or given for it.")
                continue
            width = fp.beamwidth_from_gain(peak, est.get("efficiency", 0.6))
            ring = fp.beam_contour(sat, aim[1], aim[0], fp.half_angle_at(width, abs(est["level_db"])))
            how = (f"circular beam of {width:.2f} degrees at -3 dB, from the filed peak gain of {peak:g} dBi "
                   f"at {est.get('efficiency', 0.6):g} efficiency, aimed at {aim[1]:.2f}, {aim[0]:.2f}, drawn at {est['level_db']:g} dB")
            unc = "Assumes an unshaped circular beam. The width is good to about 10% for the efficiency alone."
        elif est["method"] == "spot_km":
            aim = fp.ecef(est["aim"][1], est["aim"][0])
            slant = math.dist(sat, aim)
            half = math.degrees(math.atan(est["diameter_km"] / 2 / slant))
            ring = fp.beam_contour(sat, est["aim"][1], est["aim"][0], half)
            how = (f"one spot as a cone {2 * half:.2f} degrees wide at the satellite, which is {est['diameter_km']:g} km across "
                   f"where it is aimed ({est['aim_words']})")
            unc = est.get("uncertainty", "The stated spot size is a round figure with no gain level, and the aim point is an example, not a real beam centre.")
        elif est["method"] == "area":
            ring, params = fp.beam_for_area(sat, area_rings(ROOT / "doctrine" / "kit" / "geo" / "countries.json", est["countries"], est.get("box")), est.get("margin_deg", 0.0))
            how = (f"smallest ellipse, as the satellite sees it, around {est['area_words']} "
                   f"({params['half_axes_deg'][0]:g} by {params['half_axes_deg'][1]:g} degrees half-axes)")
            unc = est.get("uncertainty", "A service area named in words has no gain level, and a shaped beam is not an ellipse. Expect hundreds of km.")
        else:
            raise SystemExit(f"unknown estimate method {est['method']}")
        rings_all.append(ring)
        est_rings.append(ring)
        layers.append({"id": est["id"], "kind": "estimated", "label": f"{est['label']}: {how}", "source": est["source"],
                       "source_url": est.get("source_url"), "date": est.get("date"), "uncertainty": unc,
                       "geojson": {"type": "FeatureCollection", "features": [feature(polygon(ring), method=est["method"])]}})
        for key in ([est["check"]] if est.get("check") else []) + est.get("checks", []):
            if (key[0], key[1]) in published:
                pub = published[(key[0], key[1])]
                scores.append({"estimate": est["label"], "published": contour_words(beams[key[0]], key[1], short=True),
                               **fp.overlap(ring, pub), **fp.contour_distance(ring, pub)})
    for e, lid in ((x, f"los{x}") for x in case.get("line_of_sight_deg", [])[:1]):
        for (bid, level), pub in published.items():
            if case.get("score_line_of_sight") and (bid, level) == tuple(case["score_line_of_sight"]):
                los = fp.los_contour(sat, e)
                scores.append({"estimate": f"Line of sight, {e:g} degrees (computed, shown for scale)",
                               "published": contour_words(beams[bid], level, short=True),
                               **fp.overlap(los, pub), **fp.contour_distance(los, pub)})
    # one published contour against another: a filing against the operator's map, uplink against downlink
    for x in case.get("cross_checks", []):
        a, b2 = tuple(x["contour"]), tuple(x["against"])
        if a in published and b2 in published:
            scores.append({"estimate": x["label"], "published": contour_words(beams[b2[0]], b2[1], short=True),
                           **fp.overlap(published[a], published[b2]), **fp.contour_distance(published[a], published[b2])})
    notes = left_out + list(case.get("notes", []))
    if not published and case.get("published"):
        notes.insert(0, "No published contour was supplied to this build, so the estimates carry no score.")
    elif not published:
        notes.insert(0, "No published contour exists here to check the estimates against, so they carry no score.")
    return {"id": case["id"], "title": case["title"], "class": case["class"], "summary": case["summary"], "satellite": info,
            "layers": layers, "scores": scores, "notes": notes, "bounds": bounds(rings_all[:1] if case.get("fit") == "los" or not est_rings else est_rings, pad=6.0)}


GATEWAY_SOURCE = "FCC IBFS bulk database, earth station licences (credit: Federal Communications Commission)"


def gateway_parts(case, gw, built):
    """The FCC earth-station layer, table and notes for one case. `gw` is the file ibfs_gateways.py writes;
    `built` the build date. Returns (layer or None, table or None, notes)."""
    want = case.get("fcc_earth_stations")
    if want is None:
        return None, None, []
    h = gw["header"]
    by_id = {x["id"]: x for x in gw["satellites"]}
    missing = [w for w in want if w not in by_id]
    if missing:                                    # a renamed entry must fail the build, not vanish from the page
        raise SystemExit(f"{case['id']}: fcc_earth_stations not in the gateways file: {missing}")
    feats = [f for w in want for f in by_id[w]["features"]]
    file_day = datetime.fromisoformat(h["file_date"]).date()
    age = (built - file_day).days
    when = f"the FCC's bulk file of {file_day.day} {file_day:%b %Y}, {age} days old when this page was built"
    if not feats:
        return None, None, [f"No current FCC earth-station licence names this satellite in {when}. Earth stations "
                            "licensed in other countries are not in the FCC's records."]
    rows, points = [], []
    for f in feats:
        q = f["properties"]
        rows.append([q["callsign"], q.get("licensee") or "", q.get("station_class_text") or q.get("station_class") or "",
                     q.get("date_grant") or "", q.get("date_expire") or "", "yes" if f["geometry"] else "no coordinates"])
        if f["geometry"]:
            points.append({"type": "Feature", "geometry": f["geometry"],
                           "properties": {k: q.get(k) for k in ("callsign", "licensee", "station_class", "date_expire")}})
    rows.sort(key=lambda r: (r[1].lower(), r[0]))
    n, drawn = len(feats), len(points)
    names = ", ".join(w.split("@")[0].strip() for w in want)
    layer = {"id": "fcc-es", "kind": "published", "label": f"Earth stations the FCC has licensed to work {names}: "
             f"{drawn} sites drawn" + (f", {n - drawn} more with no coordinates on file" if n > drawn else ""),
             "source": GATEWAY_SOURCE, "date": h["file_date"], "on": True, "point_radius": 3,
             "uncertainty": f"As of {when}: licences granted since are missing, and some shown may since have lapsed or been "
                            "surrendered. A licence naming the satellite is not proof the site uses it, and not every site is "
                            "a gateway (the class is in the table). US licences only.",
             "geojson": {"type": "FeatureCollection", "features": points}}
    table = {"title": f"FCC earth-station licences for {names} ({n})", "text_cols": [1, 2, 5],
             "note": f"Current licences only (granted, not expired, surrendered, denied or dismissed), from {when}. "
                     "Blanket licences for user terminals have no site and are not listed. Sites on the FCC's "
                     "Permitted List may also work this satellite without naming it, and are not counted here.",
             "columns": ["Call sign", "Licensee", "Station class", "Granted", "Expires", "On the map"], "rows": rows}
    return layer, table, []


def add_gateways(case, out, gw, built):
    """Put the earth-station parts into one built case, replacing any from an earlier build."""
    layer, table, notes = gateway_parts(case, gw, built)
    out["layers"] = [l for l in out.get("layers", []) if l["id"] != "fcc-es"] + ([layer] if layer else [])
    title = "FCC earth-station licences for "
    tables = [t for t in out.get("tables", []) if not t["title"].startswith(title)] + ([table] if table else [])
    if tables or "tables" in out:
        out["tables"] = tables
    old = [x for x in out.get("notes", []) if not x.startswith("No current FCC earth-station licence")]
    out["notes"] = old + notes


def cmd_gateways(a):
    cases = {c["id"]: c for c in json.loads(CASES.read_text(encoding="utf-8"))["cases"]}
    gw = json.loads(pathlib.Path(a.gateways).read_text(encoding="utf-8"))
    path = pathlib.Path(a.data)
    doc = json.loads(path.read_text(encoding="utf-8"))
    built = datetime.fromisoformat(doc["generated_at"].replace("Z", "+00:00")).date()
    for out in doc["cases"]:
        add_gateways(cases[out["id"]], out, gw, built)
        print(out["id"], "earth stations:", next((len(l["geojson"]["features"]) for l in out["layers"] if l["id"] == "fcc-es"), 0))
    path.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print("wrote", path, path.stat().st_size, "bytes")


def cmd_build(a):
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    when = datetime.fromisoformat(a.when.replace("Z", "+00:00")) if a.when else datetime.now(timezone.utc).replace(microsecond=0)
    out = []
    gw = json.loads(pathlib.Path(a.gateways).read_text(encoding="utf-8")) if a.gateways else None
    only = set(a.only or [])
    if only - {c["id"] for c in cases["cases"]}:
        raise SystemExit(f"--only names no such case: {sorted(only - {c['id'] for c in cases['cases']})}")
    kept = {}
    if only:                                           # rebuild these cases, keep every other one as last built
        prev = json.loads(pathlib.Path(a.out).read_text(encoding="utf-8"))
        if prev["positions_at"] != iso(when):
            raise SystemExit(f"--only needs --when {prev['positions_at']} (the time the kept cases were built at)")
        kept = {c["id"]: c for c in prev["cases"]}
    for case in cases["cases"]:
        if only and case["id"] not in only:
            if case["id"] not in kept:
                raise SystemExit(f"{case['id']} is not in {a.out}; build it too with --only")
            out.append(kept[case["id"]])
            continue
        if case["class"] == "LEO constellation":
            out.append(leo_case(case, a.tle_dir, when))
        else:
            out.append(geo_case(case, a.day_file, a.published, when))
        if gw:
            add_gateways(case, out[-1], gw, datetime.now(timezone.utc).date())
        print(case["id"], "layers:", [l["id"] for l in out[-1]["layers"]], "scores:", len(out[-1].get("scores", [])))
    doc = {"schema": "orbit-footprints/0", "generated_at": iso(datetime.now(timezone.utc)), "positions_at": iso(when),
           "kinds": KINDS, "cases": out}
    path = pathlib.Path(a.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print("wrote", path, path.stat().st_size, "bytes")


def cmd_preview(a):
    """A standalone folder with only what footprints.html needs, so the page can be served without a full build."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("orbit_cli", ROOT / "tools" / "orbit.py")
    orbit_cli = importlib.util.module_from_spec(spec)   # tools/orbit.py: world_shapes makes the land file the site ships
    spec.loader.exec_module(orbit_cli)
    dst = pathlib.Path(a.dir)
    (dst / "data").mkdir(parents=True, exist_ok=True)
    src = ROOT / "site_src"
    for name in ("footprints.html", "footprints.js", "footprints.css", "style.css", "tic-time.css", "tic-time.js", "tic-nav.css",
                 "tic-nav.js", "tic-shell.css", "tic-fold.css", "tic-fold.js", "_headers"):
        shutil.copy2(src / name, dst / name)
    shutil.copytree(src / "vendor" / "maplibre-gl", dst / "vendor" / "maplibre-gl", dirs_exist_ok=True)
    countries = json.loads((ROOT / "doctrine" / "kit" / "geo" / "countries.json").read_text(encoding="utf-8"))
    (dst / "data" / "world.geojson").write_text(json.dumps(orbit_cli.world_shapes(countries), separators=(",", ":")), encoding="utf-8")
    shutil.copy2(a.json, dst / "footprints-data.json")
    print("preview folder:", dst)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("build")
    s.add_argument("--day-file", required=True)
    s.add_argument("--tle-dir", required=True)
    s.add_argument("--published")
    s.add_argument("--when", help="UTC time for positions, ISO 8601 (default now)")
    s.add_argument("--gateways", help="earth stations by satellite, from tools/ibfs_gateways.py")
    s.add_argument("--out", default=str(ROOT / "data" / "footprints" / "footprints.json"))
    s.add_argument("--only", nargs="+", metavar="CASE", help="rebuild only these case ids; the rest are kept from --out")
    s.set_defaults(fn=cmd_build)
    s = sub.add_parser("gateways")
    s.add_argument("--gateways", required=True)
    s.add_argument("--data", default=str(ROOT / "site_src" / "footprints-data.json"))
    s.set_defaults(fn=cmd_gateways)
    s = sub.add_parser("preview")
    s.add_argument("--json", required=True)
    s.add_argument("--dir", required=True)
    s.set_defaults(fn=cmd_preview)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
