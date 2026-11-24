"""Offline tests of orbit/footprint.py (prototype, ideas#232). The GXT text here is made up in the published
format; no filed file is in the repository."""
import math
import unittest

from orbit import footprint as fp

SAT = fp.geo_position(-75.0)

GXT = """[FormatInfo]
format_ver=1
[GeoMain]
adm=XXX
sat_name=TEST-1   # made up
long_nom=-75.000
n_diag=2
[COHeader]
beam_id=KUDN
emi_rcp=E
polar_disc=C
n_bore=1
n_cont=2
[B1]
gain=0.00
p=-100.0000;40.0000
[C1]
gain=-2.00
n_point=5
p1=-104.0000;38.0000
p2=-96.0000;38.0000
p3=-96.0000;42.0000
p4=-104.0000;42.0000
p5=-104.0000;38.0000
[C2]
gain=-4.00
n_point=3
p1=-110.0000;35.0000
p2=-100.0000;33.0000
p3=-90.0000;35.0000
[COHeader]
beam_id=KUUP
emi_rcp=R
polar_disc=X
n_bore=0
n_cont=0
"""


class Geometry(unittest.TestCase):
    def test_line_of_sight_matches_the_textbook_edges(self):
        for elev, north in ((0, 81.3), (5, 76.3), (10, 71.4)):
            ring = fp.los_contour(SAT, elev, n=72)
            self.assertAlmostEqual(max(lat for _, lat in ring), north, delta=0.1)
            for lon, lat in ring[::9]:
                self.assertAlmostEqual(fp.elevation(lat, lon, SAT), elev, delta=0.01)

    def test_elevation_under_and_away_from_the_satellite(self):
        self.assertAlmostEqual(fp.elevation(0, -75, SAT), 90.0, delta=0.001)
        self.assertAlmostEqual(fp.elevation(40, -75, SAT), 43.7, delta=0.1)
        self.assertLess(fp.elevation(0, 105, SAT), 0)

    def test_geodetic_round_trip(self):
        lat, lon, h = fp.geodetic(fp.ecef(47.3, 8.5, 0.4))
        self.assertAlmostEqual(lat, 47.3, places=6)
        self.assertAlmostEqual(lon, 8.5, places=6)
        self.assertAlmostEqual(h, 0.4, places=5)

    def test_beam_is_a_cone_from_the_satellite(self):
        ring = fp.beam_contour(SAT, 40, -100, 1.0, n=90)
        frame = fp._frame(SAT, 40, -100)
        for lon, lat in ring[:-1]:
            east, north = fp.view_angles(SAT, frame, lat, lon)
            self.assertAlmostEqual(math.hypot(east, north), 1.0, delta=0.002)

    def test_beam_past_the_edge_follows_the_edge(self):
        ring = fp.beam_contour(SAT, 60, -150, 3.0, n=90)
        low = min(fp.elevation(lat, lon, SAT) for lon, lat in ring)
        self.assertGreater(low, -0.01)
        self.assertLess(low, 0.01)

    def test_elliptical_beam_axes(self):
        ring = fp.beam_contour(SAT, 20, -80, 2.0, minor_half_deg=1.0, tilt_deg=0.0, n=360)
        frame = fp._frame(SAT, 20, -80)
        offs = [fp.view_angles(SAT, frame, lat, lon) for lon, lat in ring[:-1]]
        self.assertAlmostEqual(max(abs(e) for e, _ in offs), 2.0, delta=0.01)
        self.assertAlmostEqual(max(abs(n) for _, n in offs), 1.0, delta=0.01)

    def test_width_rules(self):
        self.assertAlmostEqual(fp.beamwidth(12, 2), 0.874, places=3)
        self.assertAlmostEqual(fp.half_angle_at(2.0, 3), 1.0)
        self.assertAlmostEqual(fp.half_angle_at(2.0, 12), 2.0)
        self.assertGreater(fp.beamwidth_from_gain(40), fp.beamwidth_from_gain(50))
        # a 2.4 m dish at 20 GHz, 60% efficient, has about 51.8 dBi, and that gain gives back its width
        gain = 10 * math.log10(0.6 * (math.pi * 2.4 / (0.299792458 / 20)) ** 2)
        self.assertAlmostEqual(fp.beamwidth_from_gain(gain), fp.beamwidth(20, 2.4), places=6)


class Fit(unittest.TestCase):
    def test_enclosing_ellipse_recovers_a_known_ellipse(self):
        t0 = 0.5
        pts = [(3 * math.cos(a) * math.cos(t0) - math.sin(a) * math.sin(t0) + 2,
                3 * math.cos(a) * math.sin(t0) + math.sin(a) * math.cos(t0) - 1) for a in [i * 0.1 for i in range(63)]]
        cx, cy, a, b, tilt = fp.enclosing_ellipse(pts + [(2.0, -1.0), (2.2, -0.9)])
        self.assertAlmostEqual(cx, 2.0, delta=0.02)
        self.assertAlmostEqual(cy, -1.0, delta=0.02)
        self.assertAlmostEqual(a, 3.0, delta=0.03)
        self.assertAlmostEqual(b, 1.0, delta=0.03)
        self.assertAlmostEqual(tilt, math.degrees(t0), delta=1.0)

    def test_beam_for_area_holds_every_point_it_was_fitted_to(self):
        box = [[-105.0, 30.0], [-85.0, 30.0], [-85.0, 48.0], [-105.0, 48.0], [-105.0, 30.0]]
        ring, params = fp.beam_for_area(SAT, [box], margin_deg=0.05)
        got = fp.overlap(box, ring, samples=6000)
        self.assertGreaterEqual(got["excess"], 0.0)
        self.assertLess(got["excess"], 0.01)             # nothing of the area lies outside the fitted beam
        self.assertEqual(params["points_fitted"], 5)

    def test_area_the_satellite_cannot_see_is_refused(self):
        far = [[100.0, 0.0], [110.0, 0.0], [110.0, 10.0], [100.0, 0.0]]
        with self.assertRaises(ValueError):
            fp.beam_for_area(SAT, [far])


class Scores(unittest.TestCase):
    def test_same_ring_scores_full_agreement(self):
        ring = fp.beam_contour(SAT, 40, -100, 1.0, n=120)
        got = fp.overlap(ring, ring, samples=6000)
        self.assertEqual((got["iou"], got["covered"], got["excess"]), (1.0, 1.0, 0.0))
        self.assertEqual(fp.contour_distance(ring, ring, points=90)["max_km"], 0)

    def test_small_inside_large(self):
        small, large = fp.beam_contour(SAT, 40, -100, 1.0, n=120), fp.beam_contour(SAT, 40, -100, 1.2, n=120)
        got = fp.overlap(small, large, samples=8000)
        self.assertEqual(got["excess"], 0.0)
        self.assertAlmostEqual(got["iou"], got["estimate_km2"] / got["published_km2"], delta=0.02)
        self.assertTrue(0.6 < got["iou"] < 0.75)
        d = fp.contour_distance(small, large, points=90)
        self.assertTrue(100 < d["median_km"] < 250)

    def test_area_of_a_known_cap(self):
        sat = fp.geo_position(0.0)
        ring = fp.los_contour(sat, 0.0, n=180)
        got = fp.overlap(ring, ring, samples=20000)
        # a geostationary satellite sees about 42.4% of the Earth's surface (216 million km2)
        self.assertAlmostEqual(got["published_km2"] / 510.07e6, 0.424, delta=0.006)

    def test_a_small_offset_ring_does_not_cut_the_line_of_sight(self):
        # before 24 Nov 2026 the cap was centred between the two rings and stopped at 90 degrees, so a contour far
        # from the sub-satellite point cut a fifth off the line of sight it was scored against (Galaxy 34)
        sat = fp.geo_position(-129.0)
        los = fp.los_contour(sat, 0.0, n=180)
        spot = fp.beam_contour(sat, 45, -100, 2.0, n=90)
        got = fp.overlap(los, spot, samples=20000)
        self.assertAlmostEqual(got["estimate_km2"] / 510.07e6, 0.424, delta=0.008)
        self.assertGreater(got["covered"], 0.98)

    def test_rings_across_the_antimeridian(self):
        sat = fp.geo_position(180.0)
        a, b = fp.beam_contour(sat, 10, 178, 1.0, n=120), fp.beam_contour(sat, 10, -178, 1.0, n=120)
        got = fp.overlap(a, b, samples=6000)
        self.assertTrue(0.2 < got["iou"] < 0.8)
        lons = [p[0] for p in fp.unwrap(b)]
        self.assertLess(max(lons) - min(lons), 30)


class Gxt(unittest.TestCase):
    def test_reads_beams_contours_and_points(self):
        doc = fp.parse_gxt(GXT)
        self.assertEqual((doc["sat_name"], doc["long_nom"], len(doc["beams"])), ("TEST-1", -75.0, 2))
        down, up = doc["beams"]
        self.assertEqual((down["beam_id"], down["emi_rcp"], down["polar"]), ("KUDN", "E", "C"))
        self.assertEqual(down["boresights"], [{"gain_db": 0.0, "point": [-100.0, 40.0]}])
        self.assertEqual([(c["gain_db"], c["closed"], len(c["ring"])) for c in down["contours"]], [(-2.0, True, 5), (-4.0, False, 3)])
        self.assertEqual((up["emi_rcp"], up["contours"]), ("R", []))

    def test_empty_text_gives_no_beams(self):
        self.assertEqual(fp.parse_gxt("")["beams"], [])

    def test_quirks_of_filed_files(self):
        # Made up, in the shape of real FCC attachments read 24 Nov 2026: upper-case point keys, an ntc_id,
        # format 2, the absolute peak gain on the boresight, CR LF line ends.
        text = ("[FormatInfo]\r\nformat_ver=2\r\n[GeoMain]\r\nntc_id=1\r\nadm=G  \r\nsat_name=TEST-2\r\nlong_nom=-95.20 \r\n"
                "n_diag=1\r\n[COHeader]\r\nbeam_id=U1   \r\nemi_rcp=E\r\npolar_disc=C\r\nreason=C\r\nn_bore=1\r\nn_cont=1\r\n"
                "[B1]\r\ngain=59.63\r\np=-86.0;36.5\r\n[C1]\r\ngain=-2\r\nn_point=4\r\n"
                "P1=-86.5;36.0\r\nP2=-85.5;36.0\r\nP3=-86.0;37.0\r\nP4=-86.5;36.0\r\n")
        doc = fp.parse_gxt(text)
        self.assertEqual((doc["format_ver"], doc["ntc_id"], doc["adm"], doc["long_nom"]), (2, "1", "G", -95.2))
        beam = doc["beams"][0]
        self.assertEqual((beam["beam_id"], beam["reason"], beam["peak_dbi"]), ("U1", "C", 59.63))
        self.assertEqual([(c["gain_db"], c["closed"], len(c["ring"])) for c in beam["contours"]], [(-2.0, True, 4)])

    def test_relative_boresight_has_no_peak(self):
        self.assertIsNone(fp.parse_gxt(GXT)["beams"][0]["peak_dbi"])


def gims_block(bores, conts, extra=b""):
    """A GIMS database data_block in the layout parse_gims_block reads: radians, latitude before longitude."""
    import struct
    out = struct.pack("<i", len(bores))
    for g, lon, lat in bores:
        out += struct.pack("<3f", g, math.radians(lat), math.radians(lon))
    out += struct.pack("<i", len(conts))
    for g, pts in conts:
        out += struct.pack("<fi", g, len(pts))
        for lon, lat in pts:
            out += struct.pack("<2f", math.radians(lat), math.radians(lon))
    return out + extra


class GimsBlock(unittest.TestCase):
    def test_reads_boresight_and_contours(self):
        ring = [[-100.0, 30.0], [-90.0, 30.0], [-95.0, 40.0], [-100.0, 30.0]]
        beam = fp.parse_gims_block(gims_block([(0.0, -95.0, 35.0)], [(-2.0, ring), (-4.0, ring[:3])]), "CAHD", "E", "C")
        self.assertEqual((beam["beam_id"], beam["emi_rcp"], beam["peak_dbi"]), ("CAHD", "E", None))
        self.assertEqual(beam["boresights"][0]["gain_db"], 0.0)
        self.assertAlmostEqual(beam["boresights"][0]["point"][0], -95.0, places=3)
        self.assertAlmostEqual(beam["boresights"][0]["point"][1], 35.0, places=3)
        self.assertEqual([(c["gain_db"], c["closed"], len(c["ring"])) for c in beam["contours"]], [(-2.0, True, 4), (-4.0, False, 3)])

    def test_left_over_or_short_bytes_are_refused(self):
        good = gims_block([(0.0, -95.0, 35.0)], [(-2.0, [[-100.0, 30.0], [-90.0, 30.0]])])
        with self.assertRaises(ValueError):
            fp.parse_gims_block(good + b"\x00\x00\x00\x00")
        with self.assertRaises(ValueError):
            fp.parse_gims_block(good[:-3])

    def test_carves_blocks_from_a_whole_file_once_each(self):
        # made up: two blocks among filler bytes, the first stored twice, as a locked database keeps copies
        ring = [[-40.0, -5.0], [-38.0, -5.0], [-39.0, -3.0], [-40.0, -5.0]]
        a = gims_block([(0.0, -39.3, -5.2)], [(-2.0, ring), (-4.0, ring)])
        b = gims_block([(0.0, -74.3, 4.8)], [(-2.0, [[-75.0, 4.0], [-73.0, 4.0], [-74.0, 6.0]])])
        filler = bytes(range(7, 250, 3)) * 4
        data = filler + a + filler + b + filler + a + filler
        got = fp.carve_gims_blocks(data)
        self.assertEqual([blk for _, blk in got], [a, b])
        self.assertEqual(got[0][0], len(filler))
        beam = fp.parse_gims_block(got[1][1])
        self.assertAlmostEqual(beam["boresights"][0]["point"][0], -74.3, places=3)

    def test_carve_refuses_latitudes_past_the_pole(self):
        bad = gims_block([(0.0, -39.3, -5.2)], [(-2.0, [[-40.0, 100.0], [-38.0, -5.0], [-39.0, -3.0]])])
        self.assertEqual(fp.carve_gims_blocks(bytes(64) + bad + bytes(64)), [])

    def test_carve_finds_nothing_in_noise(self):
        self.assertEqual(fp.carve_gims_blocks(bytes(range(256)) * 64), [])


class EirpKml(unittest.TestCase):
    def test_reads_levels_and_polygons(self):
        # made up, in the shape of an operator's footprint KML: a label point, a polygon, a multi-polygon
        kml = """<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>
        <name>TEST_DL EIRP.kml</name>
        <Placemark><name>43 dBW</name><Point><coordinates>10,20,0</coordinates></Point></Placemark>
        <Placemark><name>Contour 43 dBW</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
          0,10,0 20,10,0 20,30,0 0,30,0 0,10,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
        <Placemark><name>Contour 48 dBW</name><MultiGeometry>
          <Polygon><outerBoundaryIs><LinearRing><coordinates>5,15,0 10,15,0 10,20,0</coordinates></LinearRing></outerBoundaryIs></Polygon>
          <Polygon><outerBoundaryIs><LinearRing><coordinates>12,22,0 14,22,0 14,24,0 12,22,0</coordinates></LinearRing></outerBoundaryIs></Polygon>
        </MultiGeometry></Placemark></Document></kml>"""
        beam = fp.parse_eirp_kml(kml)
        self.assertEqual((beam["beam_id"], beam["unit"], beam["emi_rcp"]), ("TEST_DL EIRP.kml", "dBW", "E"))
        self.assertEqual([(c["gain_db"], len(c["ring"]), c["closed"]) for c in beam["contours"]], [(43.0, 5, True), (48.0, 4, True), (48.0, 4, True)])
        self.assertEqual(beam["contours"][1]["ring"][0], beam["contours"][1]["ring"][-1])   # closed when the file left it open


class Horizon(unittest.TestCase):
    def setUp(self):
        self.sat = fp.geo_position(0.0)
        edge = fp.los_contour(self.sat, 0.0, n=360)
        north, south = edge[0], edge[180]           # bearings 0 and 180 from the sub-satellite point
        self.line = [north, [40.0, 40.0], [40.0, 0.0], [40.0, -40.0], south]

    def _holds(self, ring, p):
        v = fp._vec(*p)
        e1, e2 = fp._plane(v)
        return fp._inside([fp._project(fp._vec(*q), v, e1, e2) for q in ring], 0.0, 0.0)

    def test_closes_on_the_side_of_the_boresight(self):
        east = fp.close_on_horizon(self.sat, [self.line], [60.0, 0.0])
        west = fp.close_on_horizon(self.sat, [self.line], [-40.0, 0.0])
        self.assertTrue(self._holds(east, [60.0, 0.0]) and not self._holds(east, [-40.0, 0.0]))
        self.assertTrue(self._holds(west, [-40.0, 0.0]) and not self._holds(west, [60.0, 0.0]))
        a, b = fp.overlap(east, east, 6000)["published_km2"], fp.overlap(west, west, 6000)["published_km2"]
        self.assertLess(a, b)                       # the eastern slice is the smaller one

    def test_two_pieces_of_one_level(self):
        # a band between two open lines: the region holding the point lies between them
        edge = fp.los_contour(self.sat, 0.0, n=360)
        a = [edge[60], [20.0, 20.0], [-20.0, 20.0], edge[300]]
        b = [edge[240], [-20.0, -20.0], [20.0, -20.0], edge[120]]
        ring = fp.close_on_horizon(self.sat, [a, b], [0.0, 0.0])
        self.assertTrue(self._holds(ring, [0.0, 0.0]))
        self.assertFalse(self._holds(ring, [0.0, 45.0]))
        self.assertFalse(self._holds(ring, [0.0, -45.0]))


class ContourGeojson(unittest.TestCase):
    def test_reads_levels_units_and_collections(self):
        # made up, in the shape of an operator's coverage GeoJSON: a label point, a polygon, a geometry collection
        ring = [[100.0, 0.0], [104.0, 0.0], [102.0, 3.0], [100.0, 0.0]]
        doc = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [101, 1, 0]}, "properties": {"name": "46"}},
            {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": {"name": "Contour 46 dBW"}},
            {"type": "Feature", "geometry": {"type": "GeometryCollection", "geometries": [
                {"type": "Polygon", "coordinates": [ring[:3]]}, {"type": "Point", "coordinates": [0, 0]}]},
             "properties": {"name": "Outer 43"}}]}
        import json
        beam = fp.parse_contour_geojson(json.dumps(doc).encode(), "dBW")
        self.assertEqual((beam["unit"], beam["emi_rcp"]), ("dBW", "E"))
        self.assertEqual([(c["gain_db"], len(c["ring"])) for c in beam["contours"]], [(46.0, 4), (43.0, 4)])
        gt = fp.parse_contour_geojson(json.dumps({"features": [{"geometry": {"type": "Polygon", "coordinates": [ring]},
                                                               "properties": {"name": "Contour -2 dB/K"}},
                                                              {"geometry": {"type": "Polygon", "coordinates": [ring]},
                                                               "properties": {"name": "Contour 11 dB/K S2"}}]}), "dB/K")
        self.assertEqual((gt["emi_rcp"], [c["gain_db"] for c in gt["contours"]]), ("R", [-2.0, 11.0]))
        with self.assertRaises(ValueError):
            fp.parse_contour_geojson(json.dumps(doc), "dB/K")


class PublishedData(unittest.TestCase):
    """site_src/footprints-data.json is built outside CI and committed (Tom, 24 Nov 2026: publish). No local path
    may reach it, and every layer says what kind it is and where it came from."""
    def test_committed_data_is_clean_and_labelled(self):
        import json
        import pathlib
        import re
        p = pathlib.Path(__file__).resolve().parent.parent / "site_src" / "footprints-data.json"
        text = p.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\b[a-z]:[\\/]", text.lower()))          # no Windows drive path of any kind
        doc = json.loads(text)
        self.assertEqual(set(doc["kinds"]), {"published", "computed", "estimated", "measured"})
        for case in doc["cases"]:
            for layer in case["layers"]:
                self.assertIn(layer["kind"], doc["kinds"])
                self.assertTrue(layer.get("source"), layer["id"])


if __name__ == "__main__":
    unittest.main()
