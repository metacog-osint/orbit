# Orbit changes: what the known cases measure (orbit-2.43)

How often the orbit-change detector (`orbit/maneuver.py`, method in `doctrine/method.md`, "Orbit changes in watched
objects") finds a known manoeuvre, and how often it lists a change that is probably not one. Built 27 Nov 2026 on
the three stored known cases of `python tools/orbit.py maneuver-case`, with the rules of `orbit-2.43`. Tests:
`tests/test_maneuver_cases.py` pins these results where the case files are present (they are Space-Track reads,
never committed, so CI skips them); `tests/test_orbit.py` covers the logic on synthetic series.

> Element sets: Space-Track.org, United States Space Command (USSPACECOM), 18th Space Defense Squadron, redistributed
> under USSPACECOM's blanket approval for basic SSA data. Orbit-change analysis: The Intelligence Company, not
> reviewed or endorsed by USSPACECOM. Not for operational use. Velocities are differences between published orbits,
> not burn records.

## The cases

| Case | Object | Regime | Sets read | Span | Truth used |
|---|---|---|---|---|---|
| `iss` | ISS (25544) | LEO, 51.6 deg | 965 (884 epochs) | 15 Jan to 1 Jun 2024 | NASA ISS Daily Summary Reports: 5 reboosts (US public domain; links in `tools/orbit.py`) |
| `sj21` | Shijian-21 (49330), BeiDou-2 G2 (34779) | GEO | 423 (213 and 138 epochs) | 1 Dec 2021 to 1 Mar 2022 | J. McDowell's account of the tow to a graveyard orbit (about 290 x 3,100 km above GEO) |
| `luch2` | Luch (Olymp) 2 (55841) | GEO | 2,570 (2,225 epochs) | 13 Mar 2023 to 22 Nov 2026 | none for manoeuvres; its stops match M. Langbroek's optical table (`luch2-relocations.md`) |

## Detection

- **Low orbit (ISS):** all 5 announced reboosts are listed within 12 hours of NASA's stated time or span, each as an
  in-track change raising the orbit 1.0-3.1 km (0.8-2.3 m/s). The semi-major-axis velocity alone is within
  0.07-0.33 m/s of NASA's figures where NASA gave one (1.79 against 1.725, 1.71 against 1.59, 1.30 + 1.29 for the two
  burns of 24 May against 2.26).
- **GEO (SJ-21 and G2):** the tow is found on both objects: G2 raised 1,716 km (69.4 m/s, between sets of 21 and
  27 Jan 2022) and SJ-21 1,721 km (69.6 m/s, 21-25 Jan), and SJ-21's return 1,765 km down (70.7 m/s) on 26 Jan.
- **Not measured:** a detection rate for small GEO station-keeping burns (no public burn list exists for these
  objects), and anything in medium or highly elliptical orbit (no case).

## Changes listed that are probably not manoeuvres

- **Low orbit (ISS):** 10 listed changes over 137 days. All lie within 12 hours of an announced reboost (the burn
  itself and the fit settling after it); **none is outside NASA's list**. 11 cross-track or eccentricity marks are
  counted and not listed by the low-orbit 1 m/s rule. One object over 4.5 months is a thin base: zero in 4.5
  object-months bounds the rate of listed changes outside a known burn at about 0.7 per object-month (95%, Poisson).
- **GEO, a dead object (G2 before the tow):** nothing listed from 1 Dec 2021 to 21 Jan 2022; 7 marks under the 0.25 m/s
  floor are counted across the case. That floor was set on this same object, so this is not an independent check.
- **GEO, Luch 2 (independent of that floor):** 176 listed changes over 1,349 days (120 mainly cross-track, 46
  in-track, 10 eccentricity); 151 more counted under 0.25 m/s. **42 of the 176 come in out-and-back pairs**: two
  consecutive single-pair changes with the same main term, the first ending where the second begins, whose
  inclination (17 pairs) or semi-major-axis (4 pairs) changes have opposite signs and cancel to within half of the
  larger one. That is the pattern one element set lying off the orbit gives, not a burn, though a real burn and its
  correction a day apart cannot be told from it here. On SJ-21, 1 such pair (27-28 Dec 2021, 0.40 m/s each) of 15.
  So on Luch 2 about a quarter of listed changes (42 of 176) show the pattern of a single off set. A second
  check, comparing the settled orbit over the 24 hours before and after each listing, finds 31 of 136 testable
  listings (23%) leave it moved by under 0.25 m/s. Two of the 21 pairs do not return to the old orbit. This is
  one object: on SJ-21 the settled-orbit check finds 1 of 12.

## One set off the orbit (the orbit-2.47 change)

From `orbit-2.47` a GEO change is listed only once the set after it confirms it (method: "GEO changes wait for a
confirming set"). On the cases above: Luch 2 lists 119 changes, not 176, with 49 sets left out as lying off the
orbit; its out-and-back pairs fall from 21 to 1, and every relocation departure and arrival that had a listed
in-track change still has one. SJ-21 lists 13, not 15: the 27-28 Dec 2021 pair goes, the tow and return stay. The
ISS is unchanged (the step applies at GEO only). A listed change waits for its confirming set: on Luch 2 a median
12.8 hours, 90% within 28.4 hours, longest 82.9 hours. The figures above this section are those of `orbit-2.43`,
before the step; `tests/test_maneuver_cases.py` pins the new ones.

## Station-kept GEO satellites held near zero inclination

Seven commercial station-kept satellites, from Orbit's public `geo-elements-2026-07..11` sets (1 Jul to 26 Nov 2026,
about 148 days each), run through the detector over their whole stored series. The north-south need is the object's
own steady inclination-vector drift between listings (lunar and solar pull, 0.63-0.99 deg a year here) times orbital
speed over the span: the plane change station keeping has to undo. An episode is a run of listed cross-track changes
less than 2 days apart; its net change compares the median orbit of the 3 sets before it with the 3 sets after it,
with the steady drift removed.

| Satellite | Median i (deg) | Listed (cross-track) | Listed total (m/s) | Episodes | Net over episodes (m/s) | North-south need (m/s) |
|---|---|---|---|---|---|---|
| Eutelsat 70B | 0.065 | 11 | 23.7 | 11 | 22.8 | 20.7 |
| Astra 2G | 0.053 | 22 | 44.2 | 13 | 28.0 | 19.1 |
| SES-11 | 0.027 | 35 | 80.5 | 11 | 25.4 | 18.3 |
| Turksat 4B | 0.019 | 42 | 80.2 | 20 | 32.6 | 21.6 |
| IS-15 | 0.019 | 33 | 40.1 | 19 | 17.9 | 13.7 |
| IS-22 | 0.017 | 38 | 67.0 | 19 | 26.7 | 17.0 |
| Galaxy 35 | 0.015 | 34 | 47.8 | 19 | 20.0 | 19.1 |

- **Why the listed totals run 2-4 times the need:** one north-south burn is often listed as several plane changes.
  In the days after a burn the published sets jump back and forth in plane, by 0.02-0.03 deg between sets 3-6 hours
  apart, which no burn explains, before they settle. Each jump is listed. Away from listings the sets are smooth: a
  set more than 0.25 m/s off the line through its two neighbours occurs in 0-7% of sets elsewhere, against 5-31% in
  the 8 days after an episode starts (SES-11 31%, Eutelsat 70B 5%). Counted by episode, with the net change across
  each, the totals come to 1.0-1.6 times the need, as station keeping with some fit scatter would.
- **The clean one:** Eutelsat 70B, held at about 0.065 deg, has the smallest set scatter (0.008 m/s against
  0.014-0.033) and the fewest off sets after a burn (5%), and lists one change per episode. Why its sets settle
  faster is not measured. The six that list more are held at 0.015-0.053 deg, where a 0.02 deg jump also swings the
  node through tens of degrees.
- **Cross-tagged neighbours are not the cause here:** no catalogued object within 0.3 deg of longitude sits on the
  alternate track of SES-11's sets (checked 28-29 Aug 2026), though many station-kept satellites share that
  inclination vector, so a match would not prove a swap either.
- **`orbit-2.47` (one off set confirmed by the next set) removes few of these:** 38 to 34 on IS-22, 35 to 31 on
  SES-11, 42 to 36 on Turksat 4B, since the off sets come several in a row.
- No operator publishes these burns, so which individual listings are real is not known. The page states the limit.

## Long gaps (the orbit-2.43 change)

Before `orbit-2.43` the detector removed nodal precession at one median rate per object. A decaying low orbit
precesses faster as it falls, so a long pair late in the stored history kept a false cross-track term. Synthetic,
no burn, 450 km and 51.6 deg decaying about 36 m a day, 4.5-day gap near the end: 1.2 m/s listed from a 60-day
history, 2.5 m/s from 120 days; 506.6 km and 97.45 deg, 93-hour gap: 0.27 and
0.55 m/s. From `orbit-2.43` each pair's J2 precession is removed at its own orbit's rate, and the synthetic cases
list nothing. On the three known cases the change keeps every listed change (the same 203, at the same spans) and moves totals by
0.29 m/s at most (median 0); ISS still 5 of 5 with none outside NASA's list.

**Scaling noise by pair length was tried and not adopted.** Quiet pairs' terms do grow with pair length at GEO
(Luch 2, in-track: 0.0030 m/s at 0.5-1 day, 0.0132 m/s at 2-4 days; cross-track 0.084 to 0.108 m/s), but scaling each
pair's noise by its length relative to the object's median pair lowered the shared noise figure, which added one
change outside NASA's list on the ISS (24 Mar 2024, 1.2 m/s cross-track) and dropped two that sit beside reboosts. The 0.25 m/s GEO floor is about 20 times the 2-4 day in-track term.

## Not covered
- Medium orbit and highly elliptical orbits: no known case.
- GEO station-keeping detection: no public burn list for the case objects.
- The live watch list: its store is held privately, so the effect of `orbit-2.43` on live listings is not measured
  here; the first update run after the change lists with the new rule.
