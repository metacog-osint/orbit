"""FCC earth stations grouped by the satellite they are licensed to work (ideas#232, exploration).

    python tools/ibfs_gateways.py build --ibfs DIR --out data/footprints/gateways.json [--as-of YYYY-MM-DD]
                                        [--zip-date YYYY-MM-DD] [--include-no-expiry]

Reads the FCC IBFS bulk database (ftp.fcc.gov/pub/Bureaus/International/databases/IBFS.zip), already downloaded and
unpacked by the caller; no request is made. Tables used (file, table, fields):
  main.dat      MAIN            filing_key, callsign, file_number, subsystem_code (SES = earth station), status_code,
                                status_date, last_action, date_grant, date_deny, date_dismiss, date_surrender,
                                date_begin, date_expire, date_last_update, app_type_code, class_of_station_code,
                                address_key
  address.dat   ADDRESS         address_key, address_name (the licensee)
  site.dat      SITE            site_key, filing_key, site_id, city, county, state, lat/long deg min sec hemi, nad_ind
  anten.dat     ANTENNA         antenna_key, site_key, diameter
  freq.dat      FREQUENCY       antenna_key, frequency_lower, frequency_upper (MHz)
  ptcomm.dat    PTCOMM          site_key, space_station_key   (the points of communication)
  space_sta.dat SPACE_STATION   space_station_key, us_name, itu_name, orbit_location
  status_code.dat, class.dat    code text
Record format: fields split on "|", records end with "|^|" CR LF, and text fields may hold CR/LF or "|" inside a
record, so records are split on the terminator, not on lines. MAIN has more columns than the published schema;
only the first 53 (which match it) are used.

What the output is and is not: a site licensed to work a satellite is not necessarily a gateway (the class is
recorded), blanket licences for user terminals have no site, and a licence on file is not proof of use. Nothing is
dropped silently: every status is counted in the header.
"""
import argparse
import json
import pathlib
import re
import sys
from datetime import date, datetime, timezone

SOURCE = "FCC IBFS bulk database (ftp.fcc.gov/pub/Bureaus/International/databases/IBFS.zip)"
CREDIT = "Federal Communications Commission"
TERMINATOR = "|^|\r\n"

MAIN_COLS = ["filing_key", "filing_state", "callsign", "file_number", "subsystem_code", "status_code", "status_date",
             "last_action", "last_action_date", "mts_number", "date_filed", "mellon_date", "date_grant", "date_deny",
             "date_dismiss", "date_surrender", "date_begin", "date_expire", "date_last_update"]
MAIN_FIELDS = 70      # fields per record in the July 2026 file
MAIN_EXTRA = {"app_type_code": 25, "class_of_station_code": 35, "address_key": 41}
SITE_COLS = ["site_key", "filing_key", "site_id", "site_description", "contact_person", "site_street1", "site_street2",
             "site_city", "site_county", "site_state", "site_zipcode", "site_telephone", "site_elevation", "lat_deg",
             "lat_min", "lat_sec", "lat_hemi", "long_deg", "long_min", "long_sec", "long_hemi", "nad_ind"]
ANTENNA_COLS = ["antenna_key", "antenna_id", "site_key", "diameter"]
FREQ_COLS = ["frequency_key", "antenna_key", "polarization_code", "eirp", "eirp_density", "emission",
             "frequency_lower", "frequency_upper"]
SPACE_COLS = ["space_station_key", "us_name", "itu_name", "orbit_location", "verbose", "inactive_date", "hemi"]
ADDRESS_COLS = ["address_key", "address_id", "address_name"]

# Frequency bands by MHz, the usual satellite plan. A range is tagged by every band it touches.
BANDS = [("L", 1000, 2000), ("S", 2000, 4000), ("C", 3400, 7075), ("X", 7250, 8400), ("Ku", 10700, 14500),
         ("Ka", 17300, 31000), ("V", 37500, 51400)]
# Overlaps matter little at this precision (S and C share 3400-4000): the lowest match wins per frequency point.


def read_table(path, cols=None, ncols=None):
    """Yield one list of fields per record. Splits on the record terminator; a record whose text holds extra "|"
    keeps its first `ncols` fields intact (they are before any free text) and the rest are left as they fall."""
    data = pathlib.Path(path).read_bytes().decode("cp1252", errors="replace")
    for rec in data.split(TERMINATOR):
        if not rec:
            continue
        if rec.endswith("|"):
            rec = rec[:-1]
        f = rec.split("|")
        if ncols is not None and len(f) < ncols:
            f += [""] * (ncols - len(f))
        yield f


def parse_dt(s):
    """IBFS dates read 'Oct 22 1979 12:00:00:000AM'. Returns a date or None. Placeholder years 9999 and 2099 stay."""
    toks = (s or "").split()
    if len(toks) < 3:
        return None
    try:
        return datetime.strptime(" ".join(toks[:3]), "%b %d %Y").date()
    except ValueError:
        return None


def dms(deg, mn, sec, hemi):
    """Degrees/minutes/seconds and a hemisphere letter to signed decimal degrees (N and E positive). None when the
    hemisphere is missing or the coordinate is the all-zero placeholder."""
    try:
        d, m, s = float(deg or 0), float(mn or 0), float(sec or 0)
    except ValueError:
        return None
    h = (hemi or "").strip().upper()
    if h not in ("N", "S", "E", "W") or (d == 0 and m == 0 and s == 0):
        return None
    v = d + m / 60.0 + s / 3600.0
    return round(-v if h in ("S", "W") else v, 6)


def band_of(lo, hi):
    """Band letters for a frequency range in MHz given as the file's fixed-width strings; empty when unparseable."""
    try:
        a, b = float(lo), float(hi)
    except (TypeError, ValueError):
        return set()
    if a <= 0 and b <= 0:
        return set()
    out = set()
    for f in (a, b):
        for name, low, high in BANDS:
            if low <= f <= high:
                out.add(name)
                break
    return out


def norm_name(raw):
    """Conservative: upper case, the filing's '(S1234)' ITU suffix and surrounding blanks removed. Hyphens, numbers
    and spelling are left as filed ('VIASAT-2' and 'VIASAT 2' stay two names)."""
    s = re.sub(r"\(\s*S\d+[^)]*\)?", "", raw or "")
    return re.sub(r"\s+", " ", s).strip().upper()


def norm_orbit(raw):
    """Orbit location text to (east-positive degrees or None, tidy text). '69.9 W.L.' -> -69.9; 'NGSO' and blanks None."""
    s = (raw or "").strip()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*°?\s*([EW])", s.upper())
    if not m:
        return None, s
    v = float(m.group(1))
    return (-v if m.group(2) == "W" else v), s


def sat_kind(name_norm, orbit_raw):
    n = name_norm
    if n in ("ALSAT", "ALL SAT", "ALL SATELLITES"):   # 'ALSAT 2' is a named satellite and stays named
        return "alsat"
    if "PERMITTED" in n:
        return "permitted_list"
    if (orbit_raw or "").strip().upper().startswith("NGSO"):
        return "ngso"
    return "named"


def classify(m, as_of, include_no_expiry=False):
    """Status class of one MAIN row. Returns (class, reason). Only 'current' goes in the main output."""
    if m["date_surrender"]:
        return "surrendered", "date_surrender set"
    if m["last_action"] == "SUR":
        return "surrendered", "last_action SUR"
    if m["date_deny"] or m["date_dismiss"]:
        return "denied_dismissed", "date_deny or date_dismiss set"
    if not m["date_grant"]:
        return "not_granted", "no grant date"
    if m["date_grant"] > as_of:
        return "not_granted", "grant date after reference date"
    if not m["date_expire"]:
        return ("current" if include_no_expiry else "granted_no_expiry"), "granted, no expiry date on file"
    if m["date_expire"] < as_of:
        return "expired", "expired before the reference date"
    return "current", "granted and unexpired"


def load_tables(ibfs):
    d = pathlib.Path(ibfs)
    t = {}
    t["status"] = {f[0].strip(): f[1].strip() for f in read_table(d / "status_code.dat") if len(f) > 1}
    t["class"] = {f[0].strip(): f[1].strip() for f in read_table(d / "class.dat") if len(f) > 1}
    t["address"] = {}
    for f in read_table(d / "address.dat", ncols=3):
        t["address"][f[0].strip()] = f[2].strip()
    ses = {}
    n_main = 0
    newest = None
    n_cols = max(MAIN_EXTRA.values()) + 1
    for f in read_table(d / "main.dat", ncols=n_cols):
        n_main += 1
        dt = parse_dt(f[18])
        if dt and (newest is None or dt > newest):
            newest = dt
        if f[4].strip() != "SES":
            continue
        m = {c: f[i].strip() for i, c in enumerate(MAIN_COLS)}
        for c, i in MAIN_EXTRA.items():
            m[c] = f[i].strip()
        if len(f) > MAIN_FIELDS:
            # a "|" inside free text shifts what follows it: take address_key from where it falls if the
            # usual place does not hold a known key
            for off in (0, len(f) - MAIN_FIELDS):
                cand = f[MAIN_EXTRA["address_key"] + off].strip()
                if cand in t["address"]:
                    m["address_key"] = cand
                    break
            else:
                m["address_key"] = ""
        for c in ("status_date", "date_filed", "date_grant", "date_deny", "date_dismiss", "date_surrender", "date_begin",
                  "date_expire", "date_last_update"):
            m[c] = parse_dt(m[c])
        ses[m["filing_key"]] = m
    t["ses"], t["n_main"], t["newest_main_update"] = ses, n_main, newest
    sites, by_filing = {}, {}
    for f in read_table(d / "site.dat", ncols=len(SITE_COLS)):
        s = {c: f[i].strip() for i, c in enumerate(SITE_COLS)}
        if s["filing_key"] in ses:
            sites[s["site_key"]] = s
            by_filing.setdefault(s["filing_key"], []).append(s["site_key"])
    t["sites"], t["sites_by_filing"] = sites, by_filing
    ptc = {}
    for f in read_table(d / "ptcomm.dat", ncols=3):
        if f[1].strip() in sites and f[2].strip():
            ptc.setdefault(f[1].strip(), []).append(f[2].strip())
    t["ptcomm"] = ptc
    sp = {}
    for f in read_table(d / "space_sta.dat", ncols=len(SPACE_COLS)):
        sp[f[0].strip()] = {c: f[i].strip() for i, c in enumerate(SPACE_COLS)}
    t["space"] = sp
    ant, ant_by_site = {}, {}
    for f in read_table(d / "anten.dat", ncols=len(ANTENNA_COLS)):
        if f[2].strip() in sites:
            ant[f[0].strip()] = f[2].strip()
            try:
                dia = float(f[3])
            except ValueError:
                dia = None
            ant_by_site.setdefault(f[2].strip(), []).append((f[0].strip(), dia))
    t["ant_by_site"] = ant_by_site
    bands = {}
    for f in read_table(d / "freq.dat", ncols=len(FREQ_COLS)):
        site = ant.get(f[1].strip())
        if site:
            bands.setdefault(site, set()).update(band_of(f[6], f[7]))
    t["bands"] = bands
    return t


def build(ibfs, as_of, zip_date=None, include_no_expiry=False):
    t = load_tables(ibfs)
    counts = {"filings_total": t["n_main"], "ses_filings": len(t["ses"]), "ses_sites": len(t["sites"]),
              "ses_filings_without_site": 0, "sites_without_coordinates": 0, "sites_without_space_station": 0,
              "by_status_class": {}, "by_status_code": {}, "by_class_of_station": {}, "current_by_kind": {},
              "current_sites_merged_duplicates": 0}
    newest_ses_update = newest_status = newest_filed = newest_grant = None
    stations = {}          # merge key -> station dict (current only)
    non_current = {}
    for fk, m in t["ses"].items():
        cls, reason = classify(m, as_of, include_no_expiry)
        sk = t["sites_by_filing"].get(fk, [])
        if not sk:
            counts["ses_filings_without_site"] += 1
        for key in ("date_filed", "date_grant"):
            v = m[key]
            if v and v.year < 2100:
                if key == "date_filed" and (newest_filed is None or v > newest_filed):
                    newest_filed = v
                if key == "date_grant" and (newest_grant is None or v > newest_grant):
                    newest_grant = v
        counts["by_status_code"][m["status_code"] or "(blank)"] = counts["by_status_code"].get(m["status_code"] or "(blank)", 0) + 1
        for key, val in (("date_last_update", "u"), ("status_date", "s")):
            v = m[key]
            if v and v.year < 2100:
                if val == "u" and (newest_ses_update is None or v > newest_ses_update):
                    newest_ses_update = v
                if val == "s" and (newest_status is None or v > newest_status):
                    newest_status = v
        # the count is of sites (one per filing site), with filings without a site counted as one unplaced row
        for s in (sk or [None]):
            counts["by_status_class"][cls] = counts["by_status_class"].get(cls, 0) + 1
            cos = m["class_of_station_code"] or "(blank)"
            counts["by_class_of_station"][cos] = counts["by_class_of_station"].get(cos, 0) + 1
            if cls != "current":
                non_current[reason] = non_current.get(reason, 0) + 1
                continue
            if s is None:
                continue
            site = t["sites"][s]
            lat = dms(site["lat_deg"], site["lat_min"], site["lat_sec"], site["lat_hemi"])
            lon = dms(site["long_deg"], site["long_min"], site["long_sec"], site["long_hemi"])
            if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
                counts["sites_without_coordinates"] += 1
                lat = lon = None
            sats = []
            for sk2 in t["ptcomm"].get(s, []):
                sp = t["space"].get(sk2)
                if sp:
                    sats.append(sp)
            if not sats:
                counts["sites_without_space_station"] += 1
            dias = sorted({dia for _, dia in t["ant_by_site"].get(s, []) if dia})
            props = {
                "callsign": m["callsign"] or None, "file_numbers": [m["file_number"]],
                "licensee": t["address"].get(m["address_key"]) or None,
                "status_code": m["status_code"], "status_text": t["status"].get(m["status_code"]),
                "status_date": m["status_date"].isoformat() if m["status_date"] else None,
                "date_grant": m["date_grant"].isoformat() if m["date_grant"] else None,
                "date_expire": m["date_expire"].isoformat() if m["date_expire"] else None,
                "date_last_update": m["date_last_update"].isoformat() if m["date_last_update"] else None,
                "app_type": m["app_type_code"] or None,
                "station_class": m["class_of_station_code"] or None,
                "station_class_text": t["class"].get(m["class_of_station_code"]),
                "site_id": site["site_id"], "city": site["site_city"] or None, "state": site["site_state"] or None,
                "lat_hemi": site["lat_hemi"] or None, "long_hemi": site["long_hemi"] or None,
                "datum": site["nad_ind"] or None,
                "antenna_diameters_m": dias, "bands": sorted(t["bands"].get(s, set())),
                "satellites": [{"raw_name": x["us_name"], "itu_name": x["itu_name"] or None,
                                "orbit_location_raw": x["orbit_location"] or None} for x in sats],
            }
            mk = ((m["callsign"], round(lat, 4), round(lon, 4)) if m["callsign"] and lat is not None
                  else ("filing", m["file_number"], s))
            old = stations.get(mk)
            if old is None:
                stations[mk] = {"props": props, "lat": lat, "lon": lon, "sats": {x["space_station_key"]: x for x in sats}}
                continue
            counts["current_sites_merged_duplicates"] += 1
            op = old["props"]
            op["file_numbers"] = sorted(set(op["file_numbers"] + props["file_numbers"]))
            if (props["date_last_update"] or "") > (op["date_last_update"] or ""):
                for k in ("status_code", "status_text", "status_date", "date_grant", "date_expire",
                          "date_last_update", "app_type"):
                    op[k] = props[k]
            for x in sats:
                old["sats"][x["space_station_key"]] = x
            op["antenna_diameters_m"] = sorted(set(op["antenna_diameters_m"]) | set(dias))
            op["bands"] = sorted(set(op["bands"]) | set(props["bands"]))
    groups = {}
    for st in stations.values():
        p = st["props"]
        p["satellites"] = [{"raw_name": x["us_name"], "itu_name": x["itu_name"] or None,
                            "orbit_location_raw": x["orbit_location"] or None}
                           for x in st["sats"].values()]
        feat = {"type": "Feature", "properties": p,
                "geometry": ({"type": "Point", "coordinates": [st["lon"], st["lat"]]} if st["lat"] is not None else None)}
        seen = set()
        for x in st["sats"].values():
            nn = norm_name(x["us_name"])
            lon_e, otxt = norm_orbit(x["orbit_location"])
            gid = nn + ("@" + otxt.upper() if otxt else "")
            if gid in seen:
                continue
            seen.add(gid)
            g = groups.get(gid)
            if g is None:
                g = groups[gid] = {"id": gid, "name_normalised": nn, "raw_names": [], "itu_names": [],
                                   "orbit_location_raw": otxt or None, "orbit_lon_deg_east": lon_e,
                                   "kind": sat_kind(nn, x["orbit_location"]), "space_station_keys": [],
                                   "type": "FeatureCollection", "features": []}
            for k, v in (("raw_names", x["us_name"]), ("itu_names", x["itu_name"])):
                if v and v not in g[k]:
                    g[k].append(v)
            if x["space_station_key"] not in g["space_station_keys"]:
                g["space_station_keys"].append(x["space_station_key"])
            g["features"].append(feat)
        if not st["sats"]:
            g = groups.setdefault("(no space station on file)", {
                "id": "(no space station on file)", "name_normalised": "", "raw_names": [], "itu_names": [],
                "orbit_location_raw": None, "orbit_lon_deg_east": None, "kind": "none",
                "space_station_keys": [], "type": "FeatureCollection", "features": []})
            g["features"].append(feat)
    for g in groups.values():
        g["n_sites"] = len(g["features"])
        counts["current_by_kind"][g["kind"]] = counts["current_by_kind"].get(g["kind"], 0) + g["n_sites"]
    counts["current_stations"] = len(stations)
    counts["not_current_reasons"] = dict(sorted(non_current.items(), key=lambda kv: -kv[1]))
    counts["satellite_groups"] = len(groups)
    ordered = sorted(groups.values(), key=lambda g: (-g["n_sites"], g["id"]))
    stale = (as_of - newest_ses_update).days if newest_ses_update else None
    header = {
        "kind": "published", "source": SOURCE, "credit": CREDIT,
        "file_date": zip_date.isoformat() if zip_date else None,
        "reference_date": as_of.isoformat(),
        "newest_date_last_update_ses": newest_ses_update.isoformat() if newest_ses_update else None,
        "newest_date_last_update_all": t["newest_main_update"].isoformat() if t["newest_main_update"] else None,
        "newest_status_date_ses": newest_status.isoformat() if newest_status else None,
        "newest_date_filed_ses": newest_filed.isoformat() if newest_filed else None,
        "newest_date_grant_ses": newest_grant.isoformat() if newest_grant else None,
        "days_stale_at_reference": stale,
        "current_rule": "granted, not expired, no surrender/denial/dismissal; grants with no expiry date are counted apart"
                        + (" and included" if include_no_expiry else " and left out"),
        "caveats": ["A licence naming a satellite is not proof the site is a gateway; see station_class.",
                    "Blanket licences (user terminals) have no site and are not here.",
                    "The bulk file is a snapshot; filings since it was cut are not in it."],
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counts": counts,
    }
    return {"header": header, "satellites": ordered}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--ibfs", required=True, help="folder holding the unpacked *.dat tables")
    b.add_argument("--out", required=True)
    b.add_argument("--as-of", help="reference date for expiry (default today, UTC)")
    b.add_argument("--zip-date", help="date of the IBFS.zip file, recorded in the header")
    b.add_argument("--include-no-expiry", action="store_true")
    a = ap.parse_args(argv)
    as_of = date.fromisoformat(a.as_of) if a.as_of else datetime.now(timezone.utc).date()
    zd = date.fromisoformat(a.zip_date) if a.zip_date else None
    out = build(a.ibfs, as_of, zd, a.include_no_expiry)
    p = pathlib.Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    c = out["header"]["counts"]
    print("wrote %s: %d current stations, %d satellite groups; status classes %s"
          % (p, c["current_stations"], c["satellite_groups"], c["by_status_class"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
