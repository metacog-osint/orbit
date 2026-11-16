"""Warning times that once stopped the parser: 2400Z, a month carried across a list of windows, and a typo.

The time phrases are those of three HYDROPAC warnings of 2023 (1257, 2751, 3798, read from Internet Archive copies of
NGA's broadcast-warn API by Launch); the areas are made up.
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orbit import navwarn  # noqa: E402

AREA = "IN AREA BOUND BY 10-00N 120-00E, 10-00N 121-00E, 11-00N 121-00E, 11-00N 120-00E."


def body(times: str, cancel: str) -> str:
    return f"SOUTH CHINA SEA.\n1. HAZARDOUS OPERATIONS, SPACE DEBRIS\n   {times}\n   {AREA}\n2. {cancel}\n"


class WarningTimes(unittest.TestCase):

    def test_2400z_is_midnight_at_the_end_of_the_day(self):
        w = navwarn.parse_body(body("051800Z TO 052400Z DEC, ALTERNATE 061800Z TO 062400Z DEC",
                                    "CANCEL THIS MSG 070100Z DEC 23."),
                               datetime(2023, 12, 1, 13, 48, tzinfo=timezone.utc))
        self.assertEqual(w["windows"], [{"start": "2023-12-05T18:00:00Z", "end": "2023-12-06T00:00:00Z"},
                                        {"start": "2023-12-06T18:00:00Z", "end": "2023-12-07T00:00:00Z"}])
        self.assertEqual(w["window_mode"], "alternates")
        self.assertEqual(w["expires"], "2023-12-07T01:00:00Z")

    def test_2400z_at_the_end_of_a_month_and_a_year(self):
        w, _ = navwarn.parse_windows("311800Z TO 312400Z DEC", datetime(2023, 12, 20, tzinfo=timezone.utc))
        self.assertEqual(w, [{"start": "2023-12-31T18:00:00Z", "end": "2024-01-01T00:00:00Z"}])
        w, _ = navwarn.parse_windows("2000Z TO 2400Z DAILY 30 NOV THRU 01 DEC",
                                     datetime(2023, 11, 28, tzinfo=timezone.utc))
        self.assertEqual(w, [{"start": "2023-11-30T20:00:00Z", "end": "2023-12-01T00:00:00Z"},
                             {"start": "2023-12-01T20:00:00Z", "end": "2023-12-02T00:00:00Z"}])
        self.assertEqual(navwarn.parse_body(body("051800Z TO 052000Z DEC", "CANCEL THIS MSG 052400Z DEC 23."),
                                            datetime(2023, 12, 1, tzinfo=timezone.utc))["expires"],
                         "2023-12-06T00:00:00Z")

    def test_month_carried_across_a_list_of_windows(self):
        w = navwarn.parse_body(body("270245Z TO 270532Z AUG ALTERNATE\n   280220Z TO 280507Z, 290155Z TO 290442Z,\n"
                                    "   300130Z TO 300415Z, 310104Z TO 310351Z,\n   010039Z TO 010326Z SEP AND\n"
                                    "   020014Z TO 020253Z SEP",
                                    "CANCEL THIS MSG 020353Z SEP 23."),
                               datetime(2023, 8, 27, 0, 20, tzinfo=timezone.utc))
        self.assertEqual([x["start"][:10] for x in w["windows"]],
                         ["2023-08-27", "2023-08-28", "2023-08-29", "2023-08-30", "2023-08-31",
                          "2023-09-01", "2023-09-02"])
        self.assertEqual(w["windows"][4], {"start": "2023-08-31T01:04:00Z", "end": "2023-08-31T03:51:00Z"})
        self.assertEqual(w["window_mode"], "alternates")

    def test_windows_before_the_first_named_month_count_back(self):
        w, _ = navwarn.parse_windows("302300Z TO 310100Z, 010100Z TO 010300Z SEP",
                                     datetime(2023, 8, 25, tzinfo=timezone.utc))
        self.assertEqual(w, [{"start": "2023-08-30T23:00:00Z", "end": "2023-08-31T01:00:00Z"},
                             {"start": "2023-09-01T01:00:00Z", "end": "2023-09-01T03:00:00Z"}])
        w, _ = navwarn.parse_windows("051800Z TO 052000Z AND 061800Z TO 062000Z, BOTH DEC",
                                     datetime(2023, 12, 1, tzinfo=timezone.utc))
        self.assertEqual([x["start"] for x in w], ["2023-12-05T18:00:00Z", "2023-12-06T18:00:00Z"])

    def test_alternates_out_of_order_stay_in_the_month(self):  # HYDROPAC 2283/22
        w, mode = navwarn.parse_windows("252100Z TO 261100Z AUG, ALTERNATE 241200Z TO 251100Z AND 261200Z TO "
                                        "271100Z AUG", datetime(2022, 8, 20, 7, 57, tzinfo=timezone.utc))
        self.assertEqual(w, [{"start": "2022-08-24T12:00:00Z", "end": "2022-08-25T11:00:00Z"},
                             {"start": "2022-08-25T21:00:00Z", "end": "2022-08-26T11:00:00Z"},
                             {"start": "2022-08-26T12:00:00Z", "end": "2022-08-27T11:00:00Z"}])
        self.assertEqual(mode, "alternates")
        w, _ = navwarn.parse_windows("252100Z TO 261100Z AUG, ALTERNATE 241200Z TO 251100Z",
                                     datetime(2022, 8, 20, tzinfo=timezone.utc))
        self.assertEqual([x["start"][:10] for x in w], ["2022-08-24", "2022-08-25"])

    def test_a_window_ending_before_it_starts_is_left_out(self):  # HYDROPAC 832/23: 172359Z TO 170036Z
        w, _ = navwarn.parse_windows("150109Z TO 150146Z, ALTERNATE 160047Z TO 160124Z AND 172359Z TO 170036Z MAR.",
                                     datetime(2023, 3, 12, 9, 41, tzinfo=timezone.utc))
        self.assertEqual(w, [{"start": "2023-03-15T01:09:00Z", "end": "2023-03-15T01:46:00Z"},
                             {"start": "2023-03-16T00:47:00Z", "end": "2023-03-16T01:24:00Z"}])

    def test_a_window_across_a_month_end_keeps_the_end_month_named(self):
        w, _ = navwarn.parse_windows("312300Z TO 010100Z JAN", datetime(2023, 12, 28, tzinfo=timezone.utc))
        self.assertEqual(w, [{"start": "2023-12-31T23:00:00Z", "end": "2024-01-01T01:00:00Z"}])

    def test_a_typo_drops_that_window_not_the_warning(self):
        w = navwarn.parse_body(body("171300Z TO 171190Z, ALTERNATE 1300Z TO 1900Z",
                                    "CANCEL THIS MSG 212000Z APR 23."),
                               datetime(2023, 4, 15, 17, 48, tzinfo=timezone.utc))
        self.assertIsNotNone(w)
        self.assertEqual(w["windows"], [])
        self.assertEqual(len(w["areas"]), 1)
        self.assertEqual(w["expires"], "2023-04-21T20:00:00Z")
        w, _ = navwarn.parse_windows("171300Z TO 171190Z APR, ALTERNATE 181300Z TO 181500Z APR",
                                     datetime(2023, 4, 15, tzinfo=timezone.utc))
        self.assertEqual(w, [{"start": "2023-04-18T13:00:00Z", "end": "2023-04-18T15:00:00Z"}])
        self.assertIsNone(navwarn.parse_body(body("051800Z TO 052000Z DEC", "CANCEL THIS MSG 312000Z NOV 23."),
                                             datetime(2023, 11, 20, tzinfo=timezone.utc))["expires"])

    def test_no_such_day_drops_the_window(self):
        w, _ = navwarn.parse_windows("311800Z TO 312000Z SEP", datetime(2023, 9, 1, tzinfo=timezone.utc))
        self.assertEqual(w, [])
        w, _ = navwarn.parse_windows("0100Z TO 0300Z DAILY 29, 30 AND 31 SEP", datetime(2023, 9, 1, tzinfo=timezone.utc))
        self.assertEqual([x["start"][:10] for x in w], ["2023-09-29", "2023-09-30"])


if __name__ == "__main__":
    unittest.main()
