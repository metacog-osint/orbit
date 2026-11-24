# Luch (Olymp) 2: stops and relocations, 2023-2026

Calibration for the GEO relocation tracker (ideas#248), from one read of the object's full element history
(ideas#256). Built 24 Nov 2026 with `tools/geo_relocations.py` on the `luch2` case of `tools/orbit.py
maneuver-case`; tests: `tests/test_geo_relocations.py` on real excerpts.

**Object:** NORAD 55841, 2023-031A, Luch-5Kh No. 3, also LUCH (OLYMP) 2, LUCH-5X (OLYMP-K 2) (Russia). Listed role
on Orbit's GEO page: inspection.
**Data:** Space-Track GP_HISTORY, read once on 24 Nov 2026 (one request; stored, never fetched again): 2,570 element
sets, 2,225 distinct epochs, 13 Mar 2023 to 22 Nov 2026.

> Element sets: Space-Track.org, United States Space Command (USSPACECOM), 18th Space Defense Squadron, redistributed
> under USSPACECOM's blanket approval for basic SSA data. Stop and relocation analysis: The Intelligence Company, not
> reviewed or endorsed by USSPACECOM. Not for operational use. Arithmetic on public element sets: not a forecast,
> and no statement of why the object moved.

## Rules
- **Stop:** |drift| under 0.1° a day (the belt board's line) for 2 days or more. Runs within 0.2° of each other with a
  break of under 7 days merge. Longitude: the median of the stop's sets. Arrival: its first set. Departure: its last
  set (the move began between that set and the next one).
- **Turnaround:** the drift changes direction between two sets that are both under 0.5° a day, outside a stop.
  This is how the 78°E checkout appears: the satellite never held under 0.1° a day for two days there.
- **Brake projection:** from the peak drift on, each set's drift is compared with a set at least 0.5 days earlier.
  When the drift has fallen by 0.05° a day or more, constant braking at that measured rate gives a stop longitude.
  *Steady* is the first projection within 1° of the one before it. A live tracker could publish that one, because
  it does not need the answer.

## Stops, checked against Marco Langbroek's table
His table: [SatTrackCam Leiden, 14 Mar 2025](https://sattrackcam.blogspot.com/2025/03/the-russian-eavesdropping-satellite.html),
from his own optical observations. That makes it an independent check on the element sets. The neighbours are his.
Orbit's own GEO sets start on 1 Jul 2026, so Orbit can measure neighbours only at 62°E.

| Orbit (element sets) | Arrival to departure | Sets | Langbroek | Neighbour (Langbroek) |
|---|---|---|---|---|
| 78.60°E (turnaround) | 22 Mar to 24 Mar 2023 | 5 | 78.00°E, 21-24 Mar 2023 | checkout |
| 58.00°E | 9 Apr to 2 May 2023 | 50 | 58.00°E, 7 Apr to 2 May 2023 | checkout |
| 8.93°E | 22 May to 25 Sep 2023 | 197 | 9.00°E, 22 May to 25 Sep 2023 | Eutelsat 9A (KA-SAT), 9B |
| 3.20°E | 4 Oct to 3 Dec 2023 | 131 | 3.20°E, 4 Oct to 4 Dec 2023 | Eutelsat 3B |
| 2.65°E | 6 Dec 2023 to 26 Mar 2024 | 251 | 2.60°E, 5 Dec 2023 to 26 Mar 2024 | Eutelsat Konnect VHTS |
| 4.73°E | 30 Mar to 22 Jun 2024 | 195 | 4.75°E, 1 Apr to 22 Jun 2024 | Astra 4A |
| 0.59°W | 1 Jul to 16 Sep 2024 | 156 | 0.54°W, 1 Jul to 16 Sep 2024 | Thor 7 |
| 0.90°W | 19 Sep 2024 to 6 Feb 2025 | 305 | 0.92°W, 18 Sep 2024 to 7 Feb 2025 | Intelsat 1002 |
| 61.99°E | 7 Mar 2025 to 15 Oct 2026 | 724 | 62.02°E, from 7 Mar 2025 | Intelsat 39 |

All nine stops agree. The held stops agree within 0.07° of longitude, and arrivals and departures within 2 days.
Orbit's dates for the 58°E and 4.73°E arrivals fall 1-2 days after Langbroek's, because the 0.1° a day line is
crossed after the satellite is in practice at the stop. The 61.99°E stop ran 587 days, by far the longest. It
ended somewhere inside a 37-day gap with no public sets (15 Oct to 21 Nov 2026), which is how the 2026 move
started unseen.

## Relocations
| From to | Moved | Departure to arrival | Peak drift (height vs GEO) | Speeding up / braking | Steady stop projection | Within 1° |
|---|---|---|---|---|---|---|
| 78.60°E to 58.00°E | 20.6° W | 24 Mar to 9 Apr 2023, 16.4 d | 2.78°/d (+218 km) | 5.7 d / 10.7 d | 7.9 d ahead, off 0.55° | 8.0 d |
| 58.00°E to 8.93°E | 49.1° W | 2 to 22 May 2023, 20.3 d | 4.42°/d (+348 km) | 6.5 d / 13.8 d | 8.6 d ahead, off 4.62° | 6.1 d |
| 8.93°E to 3.20°E | 5.7° W | 25 Sep to 4 Oct 2023, 9.1 d | 1.04°/d (+82 km) | 2.6 d / 6.5 d | 3.4 d ahead, off 0.53° | 3.6 d |
| 3.20°E to 2.65°E | 0.6° W | 3 to 6 Dec 2023, 3.5 d | 0.39°/d (+31 km) | 1.9 d / 1.6 d | none (one projection) | 1.1 d |
| 2.65°E to 4.73°E | 2.1° E | 26 to 30 Mar 2024, 4.6 d | 0.90°/d (-70 km) | 2.3 d / 2.2 d | none (one projection) | 1.3 d |
| 4.73°E to 0.59°W | 5.3° W | 22 Jun to 1 Jul 2024, 8.9 d | 0.94°/d (+73 km) | 2.4 d / 6.5 d | 2.5 d ahead, off 0.65° | 3.5 d |
| 0.59°W to 0.90°W | 0.3° W | 16 to 19 Sep 2024, 2.6 d | 0.24°/d (+18 km) | 0.7 d / 2.0 d | none (one projection) | 0.6 d |
| 0.90°W to 61.99°E | 62.9° E | 6 Feb to 7 Mar 2025, 28.8 d | 3.38°/d (-261 km) | 16.8 d / 12.0 d | 7.6 d ahead, off 0.30° | 9.4 d |

Departure and arrival are the last set of one stop and the first set of the next. Speeding up runs from departure to
the set with the peak drift, and braking from that set to arrival. During moves the largest gap between sets was
3.5 days (0.7-1.7 days on the rest).

## What this means for the tracker (ideas#248)
1. **Braking on the long moves took 11-14 days, not 1.5-2.** On the three moves of 20° or more, the drift fell from
   its peak to the stop over 10.7, 13.8 and 12.0 days. The one-off pass-by windows written on 23 Nov 2026 (in
   ideas#248) allowed 1.5-2 days of braking, so their later dates are likely too early. The tracker's braking
   allowance should come from this table, not from a fixed figure.
2. **Peak drift on the long moves was 2.8-4.4° a day.** The 2025 move coasted at about 3.38° a day for about 6 days
   (18-23 Feb) before braking. The 2026 move was at 2.47° a day in its last public set and still speeding up.
3. **A brake projection gives roughly a week's notice on the long moves, and 1-4 days on the short ones.** The first
   fall in drift is not enough on its own: on the 2025 move it projected 121°E, 59° too far, because the braking
   started gently. Waiting for two projections that agree within 1° gave 61.7°E, 7.6 days before arrival. On the
   2023 move to 9°E, two agreeing projections were still 4.6° off at 8.6 days out, and came within 1° from 6.1 days.
   The page should show a projection only once it is steady, and say how far off steady projections have been on
   this object.
4. **Height tracks drift as orbital mechanics says,** about 0.013° a day of westward drift per km above GEO
   (2.47°/d at +193 km in Nov 2026; 4.42°/d at +348 km in May 2023). A set's height is a check on its drift.
5. **Turnarounds count as stops.** Without the turnaround rule, the 78°E checkout is lost, so the stop table would
   miss one of Langbroek's nine stops.
6. **The start of the 2026 move:** at 1.62° a day on 21 Nov, 1.71° west of 62°E, uniform speeding up from rest puts
   the start about 2 days earlier (about 19 Nov). Past moves took 0.7-16.8 days to reach their peak, so this
   estimate rests on the assumption of uniform speeding up and should be shown with that caveat.
