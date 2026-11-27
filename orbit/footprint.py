"""Satellite footprints (exploration, ideas#232): where a satellite's line of sight and its beams meet the Earth,
contours read from GIMS GXT files in public filings, and scores of an estimate against a published contour.

Every ring this module returns is labelled by the caller as one of three kinds, never mixed:
  published  a contour the operator filed or published, drawn as given;
  computed   exact geometry from the satellite's position (line of sight above an elevation angle);
  estimated  a beam drawn from stated assumptions (a gain, a beamwidth, a service area), with its error unknown
             unless a published contour of the same beam is there to score it against.

Geometry is on the WGS84 ellipsoid at sea level. Rings are lists of [lon, lat] in degrees, closed (first point
repeated). Standard library only.
"""
import math
import struct

A = 6378.137                      # WGS84 semi-major axis, km
F = 1 / 298.257223563
B = A * (1 - F)
E2 = F * (2 - F)
R_MEAN = 6371.0088                # mean radius, km: distances and areas on the sphere
GEO_R = 42164.17                  # geostationary radius, km
RAD, DEG = math.pi / 180, 180 / math.pi


# ---------------------------------------------------------------- vectors and frames
def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n)


def ecef(lat, lon, h=0.0):
    """Earth-fixed position, km, of a geodetic point (degrees, km above the ellipsoid)."""
    f, l = lat * RAD, lon * RAD
    n = A / math.sqrt(1 - E2 * math.sin(f) ** 2)
    return ((n + h) * math.cos(f) * math.cos(l), (n + h) * math.cos(f) * math.sin(l), (n * (1 - E2) + h) * math.sin(f))


def geodetic(p):
    """Geodetic (lat, lon, height km) of an Earth-fixed position."""
    x, y, z = p
    lon = math.atan2(y, x)
    r = math.hypot(x, y)
    lat = math.atan2(z, r * (1 - E2))
    for _ in range(8):
        n = A / math.sqrt(1 - E2 * math.sin(lat) ** 2)
        lat = math.atan2(z + E2 * n * math.sin(lat), r)
    n = A / math.sqrt(1 - E2 * math.sin(lat) ** 2)
    h = r / math.cos(lat) - n if abs(lat) < 1.2 else z / math.sin(lat) - n * (1 - E2)
    return lat * DEG, lon * DEG, h


def geo_position(lon, lat=0.0, r=GEO_R):
    """Earth-fixed position of a satellite at a geocentric longitude and latitude (degrees) and radius (km)."""
    f, l = lat * RAD, lon * RAD
    return (r * math.cos(f) * math.cos(l), r * math.cos(f) * math.sin(l), r * math.sin(f))


def _up(lat, lon):
    f, l = lat * RAD, lon * RAD
    return (math.cos(f) * math.cos(l), math.cos(f) * math.sin(l), math.sin(f))


def elevation(lat, lon, sat):
    """Angle of the satellite above the local horizon at a sea-level point, degrees."""
    d = _unit(_sub(sat, ecef(lat, lon)))
    return math.asin(max(-1.0, min(1.0, _dot(d, _up(lat, lon))))) * DEG


def _step(lat, lon, bearing, angle):
    """The point `angle` degrees along a bearing on the sphere: only a way to walk outward, never a result."""
    f1, l1, t, a = lat * RAD, lon * RAD, bearing * RAD, angle * RAD
    f2 = math.asin(math.sin(f1) * math.cos(a) + math.cos(f1) * math.sin(a) * math.cos(t))
    l2 = l1 + math.atan2(math.sin(t) * math.sin(a) * math.cos(f1), math.cos(a) - math.sin(f1) * math.sin(f2))
    return f2 * DEG, l2 * DEG


def _wrap(lon):
    return (lon + 180) % 360 - 180


def unwrap(ring):
    """The same ring with longitudes made continuous, so a map draws it across the antimeridian in one piece."""
    out, prev = [], None
    for lon, lat in ring:
        if prev is not None:
            while lon - prev > 180:
                lon -= 360
            while lon - prev < -180:
                lon += 360
        out.append([round(lon, 4), round(lat, 4)])
        prev = lon
    return out


# ---------------------------------------------------------------- computed: line of sight
def los_contour(sat, min_elev=0.0, n=360):
    """Ring where the satellite stands exactly `min_elev` degrees above the horizon (inside: higher)."""
    lat0, lon0, _ = geodetic(sat)
    ring = []
    for k in range(n):
        bearing = 360.0 * k / n
        lo, hi = 0.0, 90.0
        for _ in range(40):
            mid = (lo + hi) / 2
            if elevation(*_step(lat0, lon0, bearing, mid), sat) > min_elev:
                lo = mid
            else:
                hi = mid
        lat, lon = _step(lat0, lon0, bearing, (lo + hi) / 2)
        ring.append([_wrap(lon), lat])
    ring.append(ring[0])
    return ring


# ---------------------------------------------------------------- estimated: a beam as a cone from the satellite
def _hit(sat, d):
    """First point where a ray from the satellite meets the ellipsoid, or None when it passes the Earth."""
    k = A / B
    s, v = (sat[0], sat[1], sat[2] * k), (d[0], d[1], d[2] * k)
    a, b, c = _dot(v, v), 2 * _dot(s, v), _dot(s, s) - A * A
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    t = (-b - math.sqrt(disc)) / (2 * a)
    return None if t <= 0 else _add(sat, _mul(d, t))


def _frame(sat, aim_lat, aim_lon):
    b = _unit(_sub(ecef(aim_lat, aim_lon), sat))
    north = (0.0, 0.0, 1.0) if abs(b[2]) < 0.95 else (1.0, 0.0, 0.0)
    u = _unit(_cross(north, b))               # across the boresight, towards the east as seen looking down
    return b, u, _cross(b, u)                 # the third axis points north in the satellite's view


def _ray(frame, psi, phi):
    b, u, w = frame
    side = _add(_mul(u, math.cos(phi)), _mul(w, math.sin(phi)))
    return _add(_mul(b, math.cos(psi)), _mul(side, math.sin(psi)))


def beam_contour(sat, aim_lat, aim_lon, half_deg, minor_half_deg=None, tilt_deg=0.0, n=360):
    """Ring where a cone around the boresight meets the Earth. `half_deg` is the half-angle at the satellite; give
    `minor_half_deg` and `tilt_deg` (major axis, degrees anticlockwise from east in the satellite's view) for an
    elliptical beam. Where the cone passes the Earth's edge the ring follows the edge (0 degrees elevation)."""
    frame = _frame(sat, aim_lat, aim_lon)
    a, bb, tilt = half_deg * RAD, (minor_half_deg if minor_half_deg is not None else half_deg) * RAD, tilt_deg * RAD
    ring = []
    for k in range(n):
        phi = 2 * math.pi * k / n
        t = phi - tilt
        psi = a * bb / math.hypot(bb * math.cos(t), a * math.sin(t))
        p = _hit(sat, _ray(frame, psi, phi))
        if p is None:                          # walk back along this direction to the Earth's edge
            lo, hi = 0.0, psi
            for _ in range(40):
                mid = (lo + hi) / 2
                if _hit(sat, _ray(frame, mid, phi)) is None:
                    hi = mid
                else:
                    lo = mid
            p = _hit(sat, _ray(frame, lo, phi))
        lat, lon, _ = geodetic(p)
        ring.append([lon, lat])
    ring.append(ring[0])
    return ring


def view_angles(sat, frame, lat, lon):
    """A ground point as the satellite sees it: (east, north) offsets from the boresight in degrees."""
    d = _unit(_sub(ecef(lat, lon), sat))
    b, u, w = frame
    return math.atan2(_dot(d, u), _dot(d, b)) * DEG, math.atan2(_dot(d, w), _dot(d, b)) * DEG


def beamwidth(ghz, dish_m):
    """-3 dB full width in degrees: about 70 wavelengths over the dish diameter (the rule Orbit's GEO page uses)."""
    return 70 * (0.299792458 / ghz) / dish_m


def beamwidth_from_gain(gain_dbi, efficiency=0.6):
    """-3 dB full width in degrees of a circular beam with this peak gain. From G = efficiency (pi D / lambda)^2 and
    width = 70 lambda / D. The efficiency is an assumption (0.5 to 0.7 is usual), so the width is good to about 10%."""
    return 70 * math.pi * math.sqrt(efficiency / 10 ** (gain_dbi / 10))


def half_angle_at(width_3db, drop_db):
    """Half-angle where a main lobe of this -3 dB full width is `drop_db` below its peak: -12 (angle/width)^2 dB.
    Good inside the main lobe (to about -10 dB) for an unshaped beam; a shaped beam does not follow it."""
    return width_3db / 2 * math.sqrt(drop_db / 3)


def enclosing_ellipse(points):
    """Smallest-area ellipse around 2-D points, by Khachiyan's algorithm: (centre x, centre y, major half-axis,
    minor half-axis, tilt degrees of the major axis from x). Used to fit a beam to a named service area."""
    pts = [(float(x), float(y)) for x, y in points]
    n = len(pts)
    if n < 3:
        raise ValueError("an ellipse needs at least 3 points")
    u = [1.0 / n] * n
    for _ in range(2000):
        # X = sum u_i q_i q_i^T with q = (x, y, 1); M_i = q_i^T X^-1 q_i
        sxx = sum(w * x * x for w, (x, y) in zip(u, pts))
        sxy = sum(w * x * y for w, (x, y) in zip(u, pts))
        syy = sum(w * y * y for w, (x, y) in zip(u, pts))
        sx = sum(w * x for w, (x, y) in zip(u, pts))
        sy = sum(w * y for w, (x, y) in zip(u, pts))
        m = [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, 1.0]]
        inv = _inv3(m)
        best, jbest = -1.0, 0
        for j, (x, y) in enumerate(pts):
            q = (x, y, 1.0)
            v = sum(q[r] * sum(inv[r][c] * q[c] for c in range(3)) for r in range(3))
            if v > best:
                best, jbest = v, j
        step = (best - 3.0) / (3.0 * (best - 1.0))
        if step < 1e-7:
            break
        u = [w * (1 - step) for w in u]
        u[jbest] += step
    cx = sum(w * x for w, (x, y) in zip(u, pts))
    cy = sum(w * y for w, (x, y) in zip(u, pts))
    cxx = sum(w * (x - cx) ** 2 for w, (x, y) in zip(u, pts))
    cxy = sum(w * (x - cx) * (y - cy) for w, (x, y) in zip(u, pts))
    cyy = sum(w * (y - cy) ** 2 for w, (x, y) in zip(u, pts))
    # the ellipse is (p-c)^T (2 C)^-1 (p-c) = 1, so its half-axes are sqrt(2 * eigenvalue of C)
    tr, det = cxx + cyy, cxx * cyy - cxy * cxy
    root = math.sqrt(max(tr * tr / 4 - det, 0.0))
    l1, l2 = tr / 2 + root, tr / 2 - root
    tilt = 0.5 * math.atan2(2 * cxy, cxx - cyy) * DEG
    return cx, cy, math.sqrt(2 * l1), math.sqrt(max(2 * l2, 0.0)), tilt


def _inv3(m):
    (a, b, c), (d, e, f), (g, h, i) = m
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]


def beam_for_area(sat, rings, margin_deg=0.0, n=360):
    """Estimated beam for a named service area: the smallest ellipse, in the satellite's own view, around every
    point of the area the satellite can see, drawn back onto the Earth. Returns (ring, parameters). The contour
    level this stands for is not known: operators draw service areas at different gain levels."""
    seen = [(lon, lat) for ring in rings for lon, lat in ring if elevation(lat, lon, sat) > 0]
    if len(seen) < 3:
        raise ValueError("the satellite sees too little of this area to fit a beam")
    lat0, lon0, _ = geodetic(sat)
    frame = _frame(sat, lat0, lon0)                     # view angles measured from the sub-satellite direction
    cx, cy, a, b, tilt = enclosing_ellipse([view_angles(sat, frame, lat, lon) for lon, lat in seen])
    a, b = a + margin_deg, b + margin_deg
    ring = []
    for k in range(n):
        t = 2 * math.pi * k / n
        ex = cx + a * math.cos(t) * math.cos(tilt * RAD) - b * math.sin(t) * math.sin(tilt * RAD)
        ey = cy + a * math.cos(t) * math.sin(tilt * RAD) + b * math.sin(t) * math.cos(tilt * RAD)
        d = _unit(_add(frame[0], _add(_mul(frame[1], math.tan(ex * RAD)), _mul(frame[2], math.tan(ey * RAD)))))
        p = _hit(sat, d)
        if p is None:                                   # past the Earth's edge: pull towards the ellipse centre
            lo, hi = 0.0, 1.0
            for _ in range(40):
                mid = (lo + hi) / 2
                dx, dy = cx + (ex - cx) * mid, cy + (ey - cy) * mid
                dm = _unit(_add(frame[0], _add(_mul(frame[1], math.tan(dx * RAD)), _mul(frame[2], math.tan(dy * RAD)))))
                if _hit(sat, dm) is None:
                    hi = mid
                else:
                    lo = mid
            dx, dy = cx + (ex - cx) * lo, cy + (ey - cy) * lo
            p = _hit(sat, _unit(_add(frame[0], _add(_mul(frame[1], math.tan(dx * RAD)), _mul(frame[2], math.tan(dy * RAD))))))
        lat, lon, _ = geodetic(p)
        ring.append([lon, lat])
    ring.append(ring[0])
    return ring, {"centre_deg": [round(cx, 3), round(cy, 3)], "half_axes_deg": [round(a, 3), round(b, 3)],
                  "tilt_deg": round(tilt, 1), "points_fitted": len(seen)}


# ---------------------------------------------------------------- published: GIMS GXT contours
def parse_gxt(text):
    """Gain contours from a GIMS GXT text file, the format filings use for antenna gain contours (ITU Radio
    Regulations Preface, section III chapter 2: INI-style sections, points as `longitude;latitude` in degrees east
    and north, contour gains in dB relative to the beam's peak, so negative).

    Returns {"sat_name", "long_nom", "adm", "format_ver", "ntc_id", "beams": [{"beam_id", "emi_rcp" (E transmit,
    R receive), "polar", "reason", "peak_dbi", "boresights": [{"gain_db", "point": [lon, lat]}],
    "contours": [{"gain_db", "closed", "ring": [[lon, lat], ...]}]}]}.
    An open contour starts and ends on the Earth's edge as the satellite sees it and is kept as a line
    (`close_on_horizon` closes it).

    Checked on 24 Nov 2026 against 258 filed files (FCC SAT-LOI-20130319-00040 ViaSat-2, SAT-LOA-20170621-00092
    EchoStar XXIV): declared n_cont, n_point and n_bore matched every file. What real files do that the
    description does not say: keys may be upper case (`P1=`); `[GeoMain]` may carry an `ntc_id`; `n_bore` may be 0
    (a service-area outline at 0 dB); and some filers put the absolute peak gain in dBi on the boresight instead
    of 0 dB, while the contours stay relative. A positive boresight gain is kept as `peak_dbi`."""
    doc = {"sat_name": None, "long_nom": None, "adm": None, "format_ver": None, "ntc_id": None, "beams": []}
    section, beam, item = None, None, None

    def point(value):
        lon, lat = value.split(";")[:2]
        return [float(lon), float(lat)]

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            name = section.lower()
            if name == "coheader":
                beam = {"beam_id": None, "emi_rcp": None, "polar": None, "reason": None, "peak_dbi": None,
                        "boresights": [], "contours": []}
                doc["beams"].append(beam)
                item = None
            elif beam is not None and name[:1] == "b" and name[1:].isdigit():
                item = {"gain_db": None, "point": None}
                beam["boresights"].append(item)
            elif beam is not None and name[:1] == "c" and name[1:].isdigit():
                item = {"gain_db": None, "closed": False, "ring": []}
                beam["contours"].append(item)
            else:
                item = None
            continue
        if "=" not in line or section is None:
            continue
        key, value = (x.strip() for x in line.split("=", 1))
        key, name = key.lower(), section.lower()
        if name == "formatinfo" and key == "format_ver" and value:
            doc["format_ver"] = int(float(value))
        elif name == "geomain":
            if key in ("sat_name", "adm", "ntc_id"):
                doc[key] = value
            elif key == "long_nom" and value:
                doc["long_nom"] = float(value)
        elif name == "coheader" and beam is not None:
            if key in ("beam_id", "emi_rcp", "reason"):
                beam[key] = value
            elif key == "polar_disc":
                beam["polar"] = value
        elif item is not None and value:
            if key == "gain":
                item["gain_db"] = float(value)
            elif key == "p" and "point" in item:
                item["point"] = point(value)
            elif key[:1] == "p" and key[1:].isdigit() and "ring" in item:
                item["ring"].append(point(value))
    for b in doc["beams"]:
        _finish_beam(b)
    return doc


def _finish_beam(b):
    for c in b["contours"]:
        r = c["ring"]
        c["closed"] = len(r) >= 4 and abs(r[0][0] - r[-1][0]) < 1e-6 and abs(r[0][1] - r[-1][1]) < 1e-6
    peaks = [x["gain_db"] for x in b["boresights"] if x["gain_db"] is not None and x["gain_db"] > 0]
    b["peak_dbi"] = max(peaks) if peaks else b.get("peak_dbi")


def parse_gims_block(data, beam_id=None, emi_rcp=None, polar=None):
    """Gain contours from one diagram's `data_block` in a GIMS database (.mdb, table `diagram`), the form a
    filing takes when the ITU database itself is attached instead of GXT text. Same beam dict as `parse_gxt`;
    the beam's name, direction and polarisation come from the same table row, so the caller passes them.

    Layout (little-endian), not documented by the ITU and inferred on 24 Nov 2026 from Galaxy 34's filing
    (FCC SAT-RPL-20210325-00039): int32 boresight count; per boresight float32 gain, latitude, longitude; int32
    contour count; per contour float32 gain, int32 point count, then float32 latitude, longitude pairs. Angles are
    in radians. All four of that filing's diagrams were consumed to the last byte, and the outlines fall where
    the satellite serves (the continental US, Alaska and a separate Hawaii contour). A block that does not
    decode exactly raises ValueError."""
    o = 0

    def take(fmt):
        nonlocal o
        try:
            v = struct.unpack_from(fmt, data, o)
        except struct.error as e:
            raise ValueError(f"GIMS block ends early at byte {o}") from e
        o += struct.calcsize(fmt)
        return v

    beam = {"beam_id": beam_id, "emi_rcp": emi_rcp, "polar": polar, "reason": None, "peak_dbi": None,
            "boresights": [], "contours": []}
    (nb,) = take("<i")
    if not 0 <= nb <= 99:
        raise ValueError(f"implausible boresight count {nb}")
    for _ in range(nb):
        g, lat, lon = take("<3f")
        beam["boresights"].append({"gain_db": round(g, 2), "point": [round(lon * DEG, 4), round(lat * DEG, 4)]})
    (nc,) = take("<i")
    if not 0 <= nc <= 999:
        raise ValueError(f"implausible contour count {nc}")
    for _ in range(nc):
        g, n = take("<fi")
        if not 0 < n <= 8000:
            raise ValueError(f"implausible point count {n}")
        pts = take(f"<{2 * n}f")
        ring = [[round(pts[i + 1] * DEG, 4), round(pts[i] * DEG, 4)] for i in range(0, 2 * n, 2)]
        beam["contours"].append({"gain_db": round(g, 2), "closed": False, "ring": ring})
    if o != len(data):
        raise ValueError(f"GIMS block has {len(data) - o} bytes left over")
    _finish_beam(beam)
    return beam


def carve_gims_blocks(data, max_bores=20, max_conts=60):
    """Diagram data blocks found by scanning a whole GIMS database file, for a filing whose .mdb the Access engine
    will not open (user-level security; for example FCC SAT-PPL-20160225-00020, Telstar 19 VANTAGE, read 24 Nov
    2026). Such files are locked, not encrypted. Only a block that fits in one database page (4,096 bytes, so a
    few hundred contour points) is stored in one piece and can be found: Access splits a longer one across pages
    (Galaxy 34's 20 KB blocks, SAT-RPL-20210325-00039, are not found), so a filing's larger, shaped beams can be
    missing from the result. A candidate must decode in
    `parse_gims_block`'s layout with plausible values: boresight gains -10 to 70 dB, every angle within the
    Earth's range in radians, and at least one contour. Returns [(offset, bytes)], each block once (copies of a
    block, which Access keeps, are dropped). The beam's name, direction and polarisation sit in other table rows
    that this does not read, so a caller matches blocks to beams by boresight, for example against the filing's
    service-area files."""
    def plausible_end(o):
        try:
            (nb,) = struct.unpack_from("<i", data, o)
            if not 1 <= nb <= max_bores:
                return None
            p = o + 4
            for _ in range(nb):
                g, la, lo = struct.unpack_from("<3f", data, p)
                if not (-10.0 <= g <= 70.0 and abs(la) <= 1.6 and abs(lo) <= 3.2):
                    return None
                p += 12
            (nc,) = struct.unpack_from("<i", data, p)
            if not 1 <= nc <= max_conts:
                return None
            p += 4
            for _ in range(nc):
                g, n = struct.unpack_from("<fi", data, p)
                if not (-60.0 <= g <= 70.0 and 1 <= n <= 8000):
                    return None
                pts = struct.unpack_from(f"<{2 * n}f", data, p + 8)
                # latitude then longitude, in radians; `not <=` also refuses NaN
                if any(not abs(v) <= (1.6 if i % 2 == 0 else 3.2) for i, v in enumerate(pts)):
                    return None
                p += 8 + 8 * n
            return p
        except struct.error:
            return None

    out, seen, o = [], set(), 0
    while o < len(data) - 16:
        end = plausible_end(o)
        if end is None:
            o += 1
            continue
        block = bytes(data[o:end])
        if block not in seen:
            seen.add(block)
            out.append((o, block))
        o = end
    return out


JET_PAGE = 4096


def _jet_rows(data, page=JET_PAGE):
    """{(page, row): bytes} for every live row on every data page of an Access (Jet 4) file, read straight from
    the bytes: page type 0x01, row count at byte 12, a two-byte offset per row from byte 14 (low 13 bits the
    start, 0x8000 deleted), rows stored from the page's end backwards, so each row ends where the one before it
    starts."""
    rows = {}
    for pg in range(1, len(data) // page):
        p = data[pg * page:(pg + 1) * page]
        if p[0] != 1 or p[1] != 1:
            continue
        (n,) = struct.unpack_from("<H", p, 12)
        if not 0 < n <= (page - 14) // 2:
            continue
        end = page
        for i in range(n):
            (o,) = struct.unpack_from("<H", p, 14 + 2 * i)
            start = o & 0x1FFF
            if not o & 0x8000 and 14 + 2 * n <= start < end:
                rows[(pg, i)] = bytes(p[start:end])
            if 0 < start < end:
                end = start
    return rows


def _jet_text(b):
    """Jet 4 text: 0xFF 0xFE starts compressed text, one byte a character; a zero byte switches between that and
    two-byte UTF-16 characters."""
    out, compressed, i = [], True, 0
    while i < len(b):
        if b[i] == 0:
            compressed, i = not compressed, i + 1
        elif compressed:
            out.append(chr(b[i]))
            i += 1
        elif i + 1 < len(b):
            out.append(b[i:i + 2].decode("utf-16-le", "replace"))
            i += 2
        else:
            break
    return "".join(out)


def gims_long_blocks(data, page=JET_PAGE):
    """Every diagram data block in a GIMS database (.mdb) that the Access engine will not open, including blocks
    longer than one page, which `carve_gims_blocks` cannot find. Returns [{beam_id, emi_rcp, polar, block}] in
    file order, each block once per beam.

    Access stores a long value outside its row: the row holds a 12-byte descriptor (3-byte length, a flag byte, 0
    for a value spread over pages, then a 4-byte pointer, row number in the low byte and page above it) and each
    page's piece starts with a 4-byte pointer to the next piece, 0 on the last. This reads the rows from the raw
    pages, finds descriptors whose chain decodes exactly in `parse_gims_block`'s layout, and takes the beam's
    name, direction and polarisation from the text just before the descriptor in the same row. That text,
    inferred on 25 Nov 2026 from Intelsat's filings (Galaxy 31, SAT-RPL-20201109-00130; Galaxy 34's, which the
    Access engine opens, matched in length and content), reads beam name, then E or R, then the polarisation
    code, then "COCO"; when it does not end that way the names are None. The format is not documented by the
    ITU."""
    rows = _jet_rows(data, page)

    def chain(key, need):
        out, seen = b"", set()
        while key and len(out) < need:
            if key in seen or key not in rows or len(rows[key]) < 4:
                return None
            seen.add(key)
            row = rows[key]
            out += row[4:]
            (nxt,) = struct.unpack_from("<I", row, 0)
            key = (nxt >> 8, nxt & 0xFF) if nxt else None
        return out if len(out) >= need else None

    found, seen = [], set()
    for here in sorted(rows):
        b = rows[here]
        i = 0
        while i <= len(b) - 12:
            length = b[i] | b[i + 1] << 8 | b[i + 2] << 16
            (ptr,) = struct.unpack_from("<I", b, i + 4)
            key = (ptr >> 8, ptr & 0xFF)
            if b[i + 3] == 0 and length >= 40 and key != here and key in rows:
                payload = chain(key, length)
                beam = None
                if payload is not None:
                    try:
                        beam = parse_gims_block(payload[:length])
                    except ValueError:
                        beam = None
                if beam is not None:
                    mark = b.rfind(b"\xff\xfe", 0, i)
                    text = _jet_text(b[mark + 2:i]) if mark >= 0 else ""
                    names = (None, None, None)
                    if len(text) >= 7 and text.endswith("COCO") and text[-6] in "ER":
                        names = (text[:-6], text[-6], text[-5])
                    item = (names, payload[:length])
                    if item not in seen:
                        seen.add(item)
                        found.append({"beam_id": names[0], "emi_rcp": names[1], "polar": names[2],
                                      "block": payload[:length]})
                    i += 12
                    continue
            i += 1
    return found


def parse_eirp_kml(text, beam_id=None):
    """Contours from an operator's KML footprint file, where each Placemark named like "Contour 43 dBW" holds one
    or more polygons (read 24 Nov 2026 from Arabsat's Badr-8 files: downlink EIRP in dBW, Polygon or
    MultiGeometry, coordinates `lon,lat,alt`). Returns the beam dict `parse_gxt` gives, with `unit` "dBW" and
    each contour's level in `gain_db`, so callers treat both alike. Placemarks without a level (the labels)
    are skipped. Inner rings (holes) are not used."""
    import re
    import xml.etree.ElementTree as ET
    root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    tag = lambda e: e.tag.rsplit("}", 1)[-1]
    doc_name = next((e.text for e in root.iter() if tag(e) == "name"), None)
    beam = {"beam_id": beam_id or doc_name, "emi_rcp": "E", "polar": None, "reason": None, "peak_dbi": None,
            "unit": "dBW", "boresights": [], "contours": []}
    for pm in (e for e in root.iter() if tag(e) == "Placemark"):
        name = next((c.text or "" for c in pm if tag(c) == "name"), "")
        m = re.search(r"(-?\d+(?:\.\d+)?)\s*dBW", name)
        polys = [e for e in pm.iter() if tag(e) == "Polygon"]
        if not m or not polys:
            continue
        for poly in polys:
            outer = next((e for e in poly.iter() if tag(e) == "outerBoundaryIs"), poly)
            coords = next((e.text for e in outer.iter() if tag(e) == "coordinates"), "") or ""
            ring = [[float(x.split(",")[0]), float(x.split(",")[1])] for x in coords.split()]
            if len(ring) >= 3:
                if ring[0] != ring[-1]:
                    ring.append(list(ring[0]))
                beam["contours"].append({"gain_db": float(m.group(1)), "closed": True, "ring": ring})
    return beam


def parse_contour_geojson(data, unit="dBW", beam_id=None):
    """Contours from an operator's GeoJSON coverage file, where each polygon feature is named like "Contour 46 dBW",
    "Outer 59 dBW", "Contour 5 dB/K" or "Contour 11 dB/K S2" (read 24 Nov 2026 from Telesat's fleet map: downlink EIRP in dBW and uplink
    G/T in dB/K, Polygon or GeometryCollection, label points beside them). A name with no unit takes `unit`.
    Returns the beam dict `parse_eirp_kml` gives, with `unit` "dBW" (downlink, emi_rcp E) or "dB/K" (uplink, R).
    Inner rings (holes) are not used."""
    import json
    import re
    doc = json.loads(data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data)
    beam = {"beam_id": beam_id, "emi_rcp": "R" if unit == "dB/K" else "E", "polar": None, "reason": None,
            "peak_dbi": None, "unit": unit, "boresights": [], "contours": []}
    for f in doc.get("features", []):
        g = f.get("geometry") or {}
        # a spot's name may follow the unit ("Contour 11 dB/K S2")
        m = re.match(r"\s*(?:Contour|Outer)\s+(-?\d+(?:\.\d+)?)\s*(dBW|dB/K)?(?:\s|$)", (f.get("properties") or {}).get("name") or "")
        if not m:
            continue
        if (m.group(2) or unit) != unit:
            raise ValueError(f"contour unit {m.group(2)} in a {unit} file")
        polys = [g["coordinates"]] if g.get("type") == "Polygon" else \
                [x["coordinates"] for x in g.get("geometries", []) if x.get("type") == "Polygon"]
        for p in polys:
            ring = [[float(c[0]), float(c[1])] for c in p[0]]
            if len(ring) >= 3:
                if ring[0] != ring[-1]:
                    ring.append(list(ring[0]))
                beam["contours"].append({"gain_db": float(m.group(1)), "closed": True, "ring": ring})
    return beam


def close_on_horizon(sat, lines, inside, n=1440):
    """Open filed contours of one level (each starts and ends on the Earth's edge as the satellite sees it) joined
    along that edge into the ring that holds `inside` ([lon, lat], normally the beam's boresight). One level can
    be bounded by several open pieces, so all of them are passed. Worked in the satellite's view, where the
    visible Earth is a disc, so the antimeridian does not matter. Tries both ways round the edge and both piece
    orientations; returns None when no joined ring holds `inside`."""
    lat0, lon0, _ = geodetic(sat)
    frame = _frame(sat, lat0, lon0)
    edge = los_contour(sat, 0.0, n)[:-1]

    def view(p):
        return view_angles(sat, frame, p[1], p[0])

    def theta(p):
        e, nn = view(p)
        return math.atan2(nn, e)

    t_edge = [theta(p) for p in edge]
    target = view(inside)

    def arc(t_from, t_to, sign):
        span = (sign * (t_to - t_from)) % (2 * math.pi)
        picks = [((sign * (t - t_from)) % (2 * math.pi), p) for p, t in zip(edge, t_edge)]
        return [list(p) for d, p in sorted(picks) if 0 < d < span]

    for pieces in (lines, [list(reversed(x)) for x in lines]):
        for sign in (1, -1):
            todo = list(range(1, len(pieces)))
            ring, cur = [list(p) for p in pieces[0]], 0
            for _ in range(len(pieces)):
                t_end = theta(ring[-1])
                # the next piece to start going round the edge this way, or back to the first piece
                cands = [(sign * (theta(pieces[k][0]) - t_end)) % (2 * math.pi) for k in todo] + \
                        [(sign * (theta(pieces[0][0]) - t_end)) % (2 * math.pi)]
                pick = min(range(len(cands)), key=cands.__getitem__)
                nxt = todo[pick] if pick < len(todo) else 0
                ring += arc(t_end, theta(pieces[nxt][0]), sign)
                if nxt == 0:
                    break
                todo.remove(nxt)
                ring += [list(p) for p in pieces[nxt]]
            ring.append(list(ring[0]))
            if _inside([view(p) for p in ring], *target):
                return ring
    return None


# ---------------------------------------------------------------- scoring an estimate against a published contour
def _vec(lon, lat):
    return _up(lat, lon)


def distance_km(p, q):
    """Great-circle distance between two [lon, lat] points on the mean sphere."""
    c = max(-1.0, min(1.0, _dot(_vec(*p), _vec(*q))))
    return math.acos(c) * R_MEAN


def densify(ring, max_deg=0.5):
    """The ring with points added so no side is longer than `max_deg` of arc."""
    out = []
    for p, q in zip(ring, ring[1:]):
        a, b = _vec(*p), _vec(*q)
        ang = math.acos(max(-1.0, min(1.0, _dot(a, b)))) * DEG
        steps = max(1, int(math.ceil(ang / max_deg)))
        for k in range(steps):
            t = k / steps
            v = _unit(_add(_mul(a, 1 - t), _mul(b, t)))
            out.append([math.atan2(v[1], v[0]) * DEG, math.asin(v[2]) * DEG])
    out.append(out[0])
    return out


def _plane(centre):
    north = (0.0, 0.0, 1.0) if abs(centre[2]) < 0.95 else (1.0, 0.0, 0.0)
    e1 = _unit(_cross(north, centre))
    return e1, _cross(centre, e1)


def _project(v, centre, e1, e2):
    """Azimuthal equidistant: true distance and bearing from the centre, so one hemisphere maps without folds."""
    x, y, z = _dot(v, e1), _dot(v, e2), _dot(v, centre)
    r = math.hypot(x, y)
    if r < 1e-15:
        return 0.0, 0.0
    k = math.atan2(r, z) / r
    return x * k, y * k


def _inside(poly, x, y):
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def overlap(estimate, published, samples=40000):
    """How well two rings agree in area, by equal-area sampling of the cap around both. Returns the shares:
    `iou` (shared area over combined area), `covered` (share of the published area inside the estimate) and
    `excess` (share of the estimate outside the published area), with both areas in km2. The sampled cap is
    centred where it is smallest of three tries (each ring's own centre and the joint one), so a small contour
    does not pull the cap off a large ring such as a line of sight; before 24 Nov 2026 the joint centre and a
    90-degree cap cut up to a fifth off a line-of-sight ring. Valid for rings within 170 degrees of that centre
    (the azimuthal-equidistant view has no folds short of the antipode). Sampling error is about
    1/sqrt(points inside)."""
    a, b = densify(estimate), densify(published)
    va, vb = [_vec(*p) for p in a], [_vec(*p) for p in b]
    vecs = va + vb

    def mean(vs):
        return _unit((sum(v[0] for v in vs), sum(v[1] for v in vs), sum(v[2] for v in vs)))

    def reach(c):
        return max(math.acos(max(-1.0, min(1.0, _dot(c, v)))) for v in vecs)
    centre = min((mean(va), mean(vb), mean(vecs)), key=reach)
    rho = min(reach(centre) + 0.01, math.radians(170))
    e1, e2 = _plane(centre)
    pa = [_project(_vec(*p), centre, e1, e2) for p in a]
    pb = [_project(_vec(*p), centre, e1, e2) for p in b]
    golden, zmin = math.pi * (3 - math.sqrt(5)), math.cos(rho)
    both = only_a = only_b = 0
    for i in range(samples):
        z = 1 - (1 - zmin) * (i + 0.5) / samples          # equal area in the cap
        r, t = math.acos(z), golden * i
        x, y = r * math.cos(t), r * math.sin(t)
        ia, ib = _inside(pa, x, y), _inside(pb, x, y)
        both += ia and ib
        only_a += ia and not ib
        only_b += ib and not ia
    cell = 2 * math.pi * R_MEAN ** 2 * (1 - zmin) / samples
    union = both + only_a + only_b
    return {"iou": round(both / union, 3) if union else 0.0,
            "covered": round(both / (both + only_b), 3) if both + only_b else 0.0,
            "excess": round(only_a / (both + only_a), 3) if both + only_a else 0.0,
            "estimate_km2": round((both + only_a) * cell), "published_km2": round((both + only_b) * cell),
            "samples_inside": union}


def contour_distance(estimate, published, points=720):
    """How far apart two rings run, in km: each of `points` evenly spaced points on one ring to the nearest point
    of the other (densified to 0.1 degree), both ways. Returns the median, the 95th percentile and the largest."""
    def spaced(ring, n):
        d = densify(ring, 0.1)
        return [d[int(i * (len(d) - 1) / n)] for i in range(n)]

    def one_way(src, dst):
        dv = [_vec(*p) for p in dst]
        out = []
        for p in src:
            v = _vec(*p)
            out.append(math.acos(max(-1.0, min(1.0, max(_dot(v, w) for w in dv)))) * R_MEAN)
        return out

    a, b = densify(estimate, 0.1), densify(published, 0.1)
    step_a, step_b = max(1, len(a) // 1500), max(1, len(b) // 1500)
    a2, b2 = a[::step_a], b[::step_b]
    d = sorted(one_way(spaced(estimate, points), b2) + one_way(spaced(published, points), a2))
    return {"median_km": round(d[len(d) // 2]), "p95_km": round(d[int(len(d) * 0.95)]), "max_km": round(d[-1])}
