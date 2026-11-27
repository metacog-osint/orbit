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
  So at GEO roughly a quarter of listed changes, at the least, show the pattern of a single off set.

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
