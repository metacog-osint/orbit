"""RPO names to GCAT (orbit/rpo.py `link`): the launch-date tiebreak of orbit-2.13 on GCAT's two payloads named
Luch (rows copied from GCAT's index of 13 Nov 2026)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orbit import rpo  # noqa: E402

OBJECTS = {
    "S23426": ["S23426", "23426", "1994-082", "P", "Luch", "1994 Dec 16", "", "", "O", "", "RU", "GEO/S"],
    "S40258": ["S40258", "40258", "2014-058", "P", "Luch", "2014 Sep 27", "", "", "O", "", "RU", "GEO/S"],
}
INDEX = rpo.gcat_names(OBJECTS)


class LaunchDateTiebreak(unittest.TestCase):
    def test_the_luch_launched_the_month_before_is_taken(self):
        got = rpo.link("Luch (Olymp)", rpo.parse_when("Oct 2014 - Present"), INDEX)
        self.assertEqual([(g["jcat"], g["by"]) for g in got], [("S40258", "launch date")])

    def test_no_link_when_neither_was_launched_in_the_year_before(self):
        self.assertEqual(rpo.link("Luch", rpo.parse_when("February 2019"), INDEX), [])

    def test_no_link_without_a_date(self):
        self.assertEqual(rpo.link("Luch", None, INDEX), [])

    def test_a_single_fit_is_still_by_name(self):
        got = rpo.link("Luch", rpo.parse_when("2000"), {"luch": INDEX["luch"][:1]})
        self.assertEqual([(g["jcat"], g["by"]) for g in got], [("S23426", "name")])


if __name__ == "__main__":
    unittest.main()
