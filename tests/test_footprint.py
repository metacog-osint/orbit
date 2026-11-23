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


if __name__ == "__main__":
    unittest.main()
