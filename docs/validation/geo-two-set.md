# GEO two-set rule: checks on Orbit's element history (26 Nov 2026, method `orbit-2.38`)

The rule (`tools/geo_belt.py`, `two_set_mark`) and its thresholds are in `doctrine/method.md`, "GEO two-set rule".
Data: every element set in Orbit's release `geo-2026` (`geo-elements-2026-07` to `-11`, sets from 1 Jul to
26 Nov 2026), for the 554 objects in CelesTrak's active GEO group on the day file of 26 Nov 2026. Orbital data:
USSPACECOM (space-track.org).

## What quiet pairs look like
Pairs of consecutive sets where both drifts are under 0.1 deg a day, by gap, as quantiles 50/90/99/99.9%:

| Gap (days) | Pairs | Drift change (deg a day) | Mean longitude off the mean-of-drifts path (deg) |
|---|---|---|---|
| 0.5-1 | 36,234 | 0.001 / 0.008 / 0.031 / 0.074 | 0.005 / 0.011 / 0.034 / 0.113 |
| 1-2 | 7,773 | 0.002 / 0.014 / 0.045 / 0.079 | 0.010 / 0.025 / 0.061 / 0.124 |
| 2-4 | 1,500 | 0.004 / 0.018 / 0.054 / 0.098 | 0.023 / 0.051 / 0.125 / 0.472 |
| 4-8 | 207 | 0.006 / 0.019 / 0.117 / 0.169 | 0.042 / 0.098 / 0.285 / 2.732 |
| 8-16 | 26 | 0.016 / 0.056 / 0.186 / 0.186 | 0.080 / 0.377 / 1.404 / 1.404 |
| 16 and more | 6 | 0.056 / 0.165 / 0.165 / 0.165 | 0.449 / 2.851 / 2.851 / 2.851 |

The tails over 4 days include real station-keeping and small slot moves. (These quantiles used SGP4's mean
longitude over the day centred on each epoch.) The mean longitude from the elements (RAAN + argument of perigee +
mean anomaly - GMST), which the rule uses, was within 0.022 / 0.040 / 0.057 / 0.126 deg of that day mean, so the
rule needs no SGP4.

## Every pair, 1 Jul to 26 Nov 2026
- 208,793 pairs; 291 marked, on 102 objects: started drifting 90, stopped drifting 84, drift rate changed 68,
  drift changed but held either side 43, moved inside the gap 6. 69 marks span a gap of 48 h or more.
- 280 marks fall on objects with 10 or more pairs at the time, which Orbit's rule judges. Orbit's rule
  (`orbit/maneuver.py`, run on every set held) lists a change covering every one of the 280, so the two-set rule
  adds nothing for those objects. That is why the board lists two-set marks only for objects Orbit's rule does not
  judge, and lists them apart.
- 11 marks fall on objects with under 10 pairs at the time. 10 of them are in the first 8 days of the history
  (YAMAL 300K, INMARSAT 5-F1, EXPRESS AM-8, BEIDOU IGSO-7, COSMOS 2539, HG-02): every object had few sets then
  because the release starts on 1 Jul 2026. Eight of the ten come in pairs that start and stop within 1.5 days with
  the longitude unchanged (one set off in mean motion, or a short east-west burn and its return). Today these
  objects hold 30 or more sets and Orbit's rule judges them.
- The eleventh is USA 324 (below).

## Known cases
| Object | Pair | Gap | Drift (deg a day) | Mean longitude | Tests | Two-set rule | Orbit's rule |
|---|---|---|---|---|---|---|---|
| USA 324 (51280) | 22 Oct 07:14Z to 15 Nov 09:27Z | 24.1 days | +0.683 to +0.024 | 108.54 to 121.36 E (natural path 117.07 E) | drift, class, longitude | stopped drifting | not judged (3 sets) |
| USA 325 (51281) | 21 Oct 19:29Z to 15 Nov 09:42Z | 24.6 days | -0.651 to -0.675 | 154.73 to 138.65 E | none | not marked: the same drift either side | not judged (2 sets) |
| LUCH (OLYMP) 2 (55841) | 15 Oct 15:56Z to 21 Nov 15:41Z | 37.0 days | -0.008 to -1.618 | 62.00 to 60.29 E | drift, class, longitude | started drifting | listed (8.5 m/s, gap) |
| LUCH (OLYMP) 2 | 21 Nov 15:41Z to 22 Nov 15:37Z | 1.0 day | -1.618 to -2.467 | 60.29 to 58.19 E | drift | drift rate changed | listed |

- USA 324: with the rule live, the board would have marked the stop from the first build after the 15 Nov set
  reached the release. Where in the 24 days it stopped, the two sets cannot say.
- USA 325 drifted west at the same rate in both sets, and its position matches that drift, so no change between
  them is visible. It stays in the board's drifting list.
- Luch 2: Orbit's rule judges it (91 sets), so its change is in the main list and not repeated in the two-set
  list. The two-set rule finds the same pair, from the same 21 Nov set: neither rule can mark a move earlier than
  the first public set after it.

Fixture: `tests/fixtures/geo_two_set_20261126.json`; tests: `tests/test_geo_two_set.py`.
