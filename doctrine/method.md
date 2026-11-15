# Orbit method (`orbit-2.5`, 15 Nov 2026)

## Purpose
The space layer of the suite: what changed in Earth orbit. Planned scope (`_ideas/new-programs.md`, program row
and roadmap step 14): catalog changes, launches, manoeuvres and counterspace events. `orbit-2.0` was the first
live slice: launches, scheduled launches, reentries and catalog changes. Launch hazard warnings (`orbit-2.2`), ASAT
test history (`orbit-2.3`), orbit changes in watched objects (`orbit-2.4`) and news headlines for scheduled
launches (`orbit-2.5`) followed.

Every item is an **observation** (measured or reported, no judgment) at tier **routine**. Orbit has no
baseline of its own readings yet, so nothing is called an anomaly, and it makes no warnings.

## Lanes

| Lane | Source | What Orbit takes |
|---|---|---|
| `catalog` | GCAT (J. McDowell, planet4589.org/space/gcat), CC BY 4.0: `satcat`, `satcat100k`, `auxcat`, `tmpcat`, `launch`, `sites`, `orgs` | Orbital launches in the last 30 days (feed: 7), reentries dated in the last 30 days (feed: 7), catalog changes between two readings, owner-code counts |
| `upcoming` | Launch Library 2 (The Space Devs), detailed mode | Launches scheduled in the next 14 days, with the provider's country |
| `navwarn` (`orbit-2.2`) | NGA Maritime Safety Information, in-force daily memoranda (HYDROPAC, HYDROLANT, HYDROARC, NAVAREA IV, NAVAREA XII). Japan Coast Guard NAVAREA XI not read since 14 Nov 2026 (robots.txt) | Navigational warnings in force that name rocket launching, space debris or reentry: areas, windows, cancel times |
| `counterspace` (`orbit-2.3`) | Secure World Foundation, "History of ASAT Testing in Space" sheet (Global Counterspace Capabilities 2026, CC BY-NC 4.0), CSV export | Every anti-satellite test in space SWF lists since 1959, with debris created, re-entered and still on orbit; tests new since Orbit's last reading |

GCAT republishes once a day, about 00:20 UTC. A run asks each file's Last-Modified date first and downloads
nothing (about 37 MB) unless one has changed.

## Rules
1. **Owners come from GCAT's State column**, which keeps Soviet (SU) objects apart from Russian Federation (RU)
   objects; CelesTrak's owner code CIS merges them. GCAT state codes are mapped to ISO 3166-1 alpha-2 in
   `gcat.STATE_ISO` (F France, J Japan, UK Britain, D Germany, SU Russia for map placement, and so on);
   intergovernmental owners (I-ESA, I-INT and the rest) get no country.
2. **New objects land in `satcat100k`** (catalog numbers 100000 and up) and, before they are numbered, in
   `tmpcat`. Reading only `satcat` misses every recent payload.
3. **A catalog change is the difference between two of Orbit's own readings.** Each reading reduces GCAT to
   `JCAT -> [catalog, number, launch, type, name, launch date, parent, decay date, status, owner, state, orbit]`
   in `data/state/catalog_index.json.gz` and compares it with the reading before. The first reading only sets
   the baseline. A reading with under 90% of the previous reading's objects fails the lane.
4. **A new entry from a launch more than 30 days old** is reported by launch, type and parent (indicator
   OR-IND-2). It can be a release from a host, a breakup, or an object only now identified. Orbit reports which
   objects, not why.
5. **A temporary (`tmpcat`) entry that disappears** is counted as closed, not removed: GCAT moves it to a
   numbered catalog under a new id.
6. **Reentry dates are GCAT's** and are often approximate (`?` in GCAT, `~` on the page).
7. **Who launched and who owns (`orbit-2.1`).** A launch's launching country is its GCAT agency's state code
   from `orgs.tsv` (`ZHSH/CALT` names two agencies); its site's country is the site's state code; each payload's
   owner is its own GCAT state. A scheduled launch's provider country is Launch Library 2's, and its site country
   is the pad's. The two sources can differ: GCAT files Rocket Lab's launches under its New Zealand company
   (RLABN, NZ), Launch Library 2 under the US. Each is shown as its source gives it. Launch items in the feed
   now list the launching country with the site and payload owners.
8. **A scheduled launch is the provider's or press's schedule**, as Launch Library 2 lists it. It moves, and
   some military launches are listed late or not at all.

## Launch hazard warnings (`orbit-2.2`)
1. **Kept:** a warning whose text names rocket launching (including a suspension), space debris, a space vehicle
   or spacecraft, or reentry. Missile firings and every other hazard are left out.
2. **As written:** areas (lettered sub-areas kept apart), windows and cancel time are the issuer's. Windows are
   expanded to UTC pairs: explicit `DDHHMMZ TO DDHHMMZ` lists, `ALTERNATE` lists (the first is the primary), and
   `HHMMZ TO HHMMZ DAILY d THRU d` repeats (an end before the start runs past midnight). Areas that each carry
   their own windows are joined: windows opening together are one, ending when the last area closes.
3. **NAVAREA XI is not read directly** (since 14 Nov 2026): the Japan Coast Guard's robots.txt disallows `/TUHO/`,
   where its list and messages sit, for every crawler but the National Diet Library's. NAVAREA XI appears only where
   NGA rebroadcasts it (HYDROPAC, NAVAREA XII). Kept for a source that permits reading: **issue times are JST.** The Japan Coast Guard stamps each warning `発表日時` in Japan time; its own
   in-force list (0499/26, stamped 21:00 on 7 Nov) says "IN FORCE 071200Z", which fixes the offset at nine hours.
4. **One area, many broadcasts.** HYDROPAC rebroadcasts NAVAREA XI and XII warnings. Warnings with the same windows
   and the same vertices (within 0.05 degrees; up to one in five may differ) are one row, NAVAREA XI listed first,
   then NAVAREA IV/XII, then the HYDRO series. Vertices that differ between copies are counted and shown, not
   corrected: on 13 Nov NAVAREA XI 0507/26 gives 19-21N 178-12E where NAVAREA XII 787/26 and HYDROPAC 3256/26 give
   178-21E.
5. **No attribution.** Orbit never says which launch a warning is for. The page shows, as a time coincidence only,
   scheduled launches whose NET falls inside a window of four hours or less, or up to an hour before one opens;
   longer windows (some debris areas stand for most of a day for two weeks) would match nearly everything. A
   coincidence crosses oceans: it is time, not place.
6. **Not for navigation.** The memoranda supplement, and do not replace, the IMO/SOLAS broadcasts; the page says so.
7. **Sources fail apart.** One memo or one NAVAREA XI message that cannot be read is named and skipped; the lane
   fails only when both sources fail, and then keeps its last good copy.
8. **NGA's MSI API** (`msi.nga.mil/api/publications/broadcast-warn`) has answered 503 "under maintenance" since at
   least 6 Nov 2026, and before that served a set frozen at May 2024. Orbit reads the API first and keeps it only
   when its newest warning is under seven days old (NGA issues warnings daily, so an older list is a frozen copy,
   never a quiet sea); otherwise it reads the memoranda, served from the maintenance page (`apology_objects/`).
   The page names the form read and why the API was passed over. Cordon reads NGA the same way.

Not in Orbit's feed: warnings appear on the page and in `snapshot.json` only. COP shows NGA's launch, debris and
reentry warnings from Cordon's copies (14 Nov 2026).

## Anti-satellite test history (`orbit-2.3`)
1. **As SWF compiled it.** Country (SWF lists Soviet tests under Russia), date, target, interceptor and type,
   launch site, whether the target was hit, and SWF's debris counts (U.S. military catalog, generally 10 cm and
   larger). The sheet's own "Last Updated" date is shown; Orbit adds nothing and judges nothing.
2. **Rows dated as a span** ("Aug - Dec 2019", "June-July 1965") are not placed on a day: they are listed apart
   and named on the page, and the parsed tests plus those rows equal SWF's own totals (6,904 pieces created, 2,773
   still on orbit, sheet of 17 Feb 2026).
3. **New tests** are those whose country, date and interceptor were not in Orbit's previous reading. The first
   reading lists none and says so. History, not events: nothing goes into the feed.
4. **Licence:** CC BY-NC 4.0, credited with links to the report and the sheet. Orbit is non-commercial; this
   source may not be reused commercially.

## Headlines for scheduled launches (`orbit-2.5`)
Source: the Spaceflight News API (Spaceflight News API and The Space Devs), which ties articles to Launch Library 2
launches. No licence or terms stated (read 15 Nov 2026); asked of The Space Devs in writing.
1. **Links only** (Tom, 15 Nov 2026): headline, outlet, publication time and the link to the outlet's own page.
   Summaries are the publishers' text and images are theirs; neither is kept.
2. **One request a run**, filtered to the Launch Library 2 ids of the launches scheduled in the next 14 days; no
   request when none are. Each launch shows its three newest headlines; a link listed twice is kept once; links
   other than http(s) are dropped.
3. **Not checked.** A headline is the outlet's reporting, shown beside the launch the API ties it to; Orbit does
   not judge it. Graded B3 (Orbit's call). Not in the feed.

## Orbit changes in watched objects (`orbit-2.4`)
Source: Space-Track.org (USSPACECOM, 18th Space Defense Squadron) GP and GP_HISTORY element sets for a private
watch list. Space-Track's documentation gives USSPACECOM's blanket approval to redistribute basic SSA data
"conditioned on appropriate citation". The citation and disclaimer are in `spacetrack-disclaimer.md`, approved by
Tom on 14 Nov 2026, and appear on the card, in `snapshot.json` (`maneuvers.attribution`) and in the footer. Raw
element sets are not republished. In the feed from 15 Nov 2026 (Tom's yes): one item per listed change (kind
`maneuver`, off the map), carrying the citation; COP's gate holds the kind from joins as military context.
1. **Space-Track's limits kept:** at most four requests a run, 2.5 s apart; GP at most once an hour, never at
   :57-:03 or :27-:33; each object's history (60 days) read once and stored, never asked for again.
2. **One set per epoch**, the later-created where Space-Track re-issued one.
3. **Change against the object's own noise.** For each pair of consecutive sets: the change in semi-major axis,
   inclination, node and eccentricity, less the object's median drift over that interval (drag decay, nodal
   precession), as along-track (v da / 2a), cross-track (v times the plane angle) and eccentricity (v de / 2)
   velocities. A pair is marked when one term is at least 8 robust deviations (1.4826 x MAD) above the object's
   own median and the total is at least 0.05 m/s; at least 10 pairs are needed first; marks under a day apart are
   one change. A change is listed only at 0.25 m/s or more in geostationary orbit (0.05 m/s elsewhere); smaller ones
   are counted, not listed. Geostationary objects also show longitude and drift before and after.
4. **What a mark is:** the published orbit moved more than this object's sets usually move. Usually a manoeuvre;
   a re-fit after a tracking gap, a mislabelled set or storm-driven drag in low orbit can give the same. Orbit says
   which object, when and how much, never why; no warnings.
5. **Silence is not quiet.** An object with no new set for 3 days is counted as untracked, and the longest gap
   between sets is kept. A change measured across a gap of 48 hours or more between consecutive sets is labelled
   with that gap on the page (`gap`): it happened somewhere inside it, not at either end (Tom, 14 Nov 2026, after
   the first live reading timed USA 270's change across three weeks).
6. **The known case** (Shijian-21 towing BeiDou-2 G2, `tools/orbit.py maneuver-case`, run 14 Nov 2026 on 423
   Space-Track sets, 1 Dec 2021 to 1 Mar 2022): G2 raised 1,720 km and SJ-21 1,694 km from 21-25 Jan, SJ-21 back
   down 1,732 km on 26-27 Jan; J. McDowell gave the stack 290 x 3,100 km above GEO (about 1,695 km mean). At
   0.05 m/s the dead G2 also drew four marks of 0.06-0.19 m/s, which cannot be manoeuvres; hence the 0.25 m/s
   geostationary floor, which leaves G2 one change and SJ-21 six. Changes under a day apart are joined, so SJ-21's
   approach, docking and tow show as one change (17-25 Jan). Velocities are differences between published orbits,
   not burn records. Low, medium and high orbits are not yet checked against a known case.

## Not built
SWF's rendezvous and proximity operations sheet, ITU Space Explorer filings,
an optional 3D page (Cesium ion decision).
