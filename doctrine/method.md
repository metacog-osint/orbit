# Orbit method (`orbit-2.11`, 16 Nov 2026)

## Purpose
The space layer of the suite: what changed in Earth orbit. Planned scope (the private planning notes, program row
and roadmap step 14): catalog changes, launches, manoeuvres and counterspace events. `orbit-2.0` was the first
live slice: launches, scheduled launches, reentries and catalog changes. Launch hazard warnings (`orbit-2.2`), ASAT
test history (`orbit-2.3`), orbit changes in watched objects (`orbit-2.4`) and news headlines for scheduled
launches (`orbit-2.5`) followed; `orbit-2.6` splits orbit changes that disagree, and `orbit-2.7` adds SWF's
rendezvous and proximity operations history. `orbit-2.8` lists low-orbit plane and shape changes only from 1 m/s,
waits for Noisefloor's share of the Space-Track account, and adds baselines from GCAT's history. `orbit-2.9` adds
the launch ledger; `orbit-2.10` adds each payload's orbit from GCAT, Launch's place check on Orbit's hazard areas,
and the ledger's history and GCAT gap on the page; `orbit-2.11` starts Orbit's own daily archive and adds the globe.

Every item is an **observation** (measured or reported, no judgment). Most are tier **routine**; from `orbit-2.49`
two kinds can be tier **anomaly**, each against a baseline from GCAT's own history (see "Anomalies against GCAT's
history" below). Orbit makes no warnings.

## Lanes

| Lane | Source | What Orbit takes |
|---|---|---|
| `catalog` | GCAT (J. McDowell, planet4589.org/space/gcat), CC BY 4.0: `satcat`, `satcat100k`, `auxcat`, `tmpcat`, `launch`, `sites`, `orgs` | Orbital launches in the last 30 days (feed: 7), reentries dated in the last 30 days (feed: 7), catalog changes between two readings, owner-code counts |
| `upcoming` (retired `orbit-2.32`) | Launch Library 2 (The Space Devs), detailed mode | Launches scheduled in the next 14 days, with the provider's country |
| `ledger` (`orbit-2.9`) (retired `orbit-2.32`) | Orbit's launch ledger from Launch Library 2, on Orbit's public release | Every launch since 1 Jan 2024, checked hourly; the launches GCAT hasn't listed yet |
| `pairs` (`orbit-2.10`) (retired `orbit-2.32`) | The suite's Launch program (launch.theintelligence.company), its published snapshot | Launch's place check on Orbit's own hazard areas and scheduled launches: time and place, grouped, or time only, with azimuth, distance and implied inclination |
| `navwarn` (`orbit-2.2`) (retired `orbit-2.32`) | NGA Maritime Safety Information, in-force daily memoranda (HYDROPAC, HYDROLANT, HYDROARC, NAVAREA IV, NAVAREA XII). Japan Coast Guard NAVAREA XI not read since 14 Nov 2026 (robots.txt) | Navigational warnings in force that name rocket launching, space debris or reentry: areas, windows, cancel times |
| `counterspace` (`orbit-2.3`) | Secure World Foundation, "History of ASAT Testing in Space" sheet (Global Counterspace Capabilities 2026, CC BY-NC 4.0), CSV export | Every anti-satellite test in space SWF lists since 1959, with debris created, re-entered and still on orbit; tests new since Orbit's last reading |
| `decay` (`orbit-2.13`) | Space-Track.org TIP messages (USSPACECOM, 18th Space Defense Squadron), class `tip` | The newest reentry prediction for each object messaged in the last 5 days: predicted time, window, the object's place at that time, next report |
| `rpo` (`orbit-2.7`, matching `orbit-2.16`) | Secure World Foundation, "History of Robotic Rendezvous and Proximity Operations in Space" sheet (same report, CC BY-NC 4.0), CSV export of three data tabs and the About tab | Every rendezvous and proximity operation SWF lists (Commercial/Civil, Military/Intelligence, Planned), in SWF's words, with Orbit's reading of each date and GCAT matches |

GCAT republishes about once a day, at no fixed time (file headers seen 13 Nov 2026 00:21 UTC and 15 Nov 10:18
UTC), so a run reads it within six hours of an update. A run asks each file's Last-Modified date first and downloads
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
   **Times as written** (16 Nov 2026, a parser fix, method unchanged): 2400Z is midnight at the end of that day. A
   window followed by a month takes it as its end's month; one without takes the month of the window listed after
   it (or, after the last named month, before it), a month back (or on) only where the day number jumps by more than
   15 (`310104Z TO 310351Z, 010039Z TO 010326Z SEP`: the first is 31 Aug), so alternates listed out of order a few
   days apart stay in their month. A window or cancel time that does not exist (a typo such as `171190Z`, or the 31st
   of a 30-day month), or a window that ends before it starts, is left out, and the rest of the warning is read.
   Until this fix such a warning raised and was not read, a list like the one above put 28-31 Aug in September, and
   a window ending before it started was read as a month long.
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

## Rendezvous and proximity operations (`orbit-2.7`)
Source: SWF's RPO sheet, linked from the 2026 report's page under "Additional Information"; the report is CC BY-NC
4.0 (checked 15 Nov 2026). Graded B2, as the ASAT sheet (Tom, 15 Nov 2026: "I trust SWF"; Orbit had proposed
B3). Many rows are SWF's reading of public tracking (a purpose, an "Intelligence" category, a span of months), and
the card says so.
1. **SWF's text kept.** Every field as SWF wrote it, its spellings included ("Comos 2521"); the three tabs are
   shown apart, with SWF's column names (client and servicer, target and chaser).
2. **Dates read, not guessed.** SWF's free-text date becomes a start, an end, a precision (day, month or year)
   and whether it is ongoing ("Oct 2014 - Present"). Forms read: "Apr 14, 2005", "Jan 2016", "2026", "Jun 15-29
   2020", "Sept 3-Oct 28 2020", "Mar - Apr 2017", "Aug 2010 - July 2011", "1990-1998", "Oct 2014 - Present",
   "Dec 23, 2008 & Jan 1, 2009" (first to last); a bracketed note such as "(launch)" stays in SWF's text. Any other
   form is listed apart with SWF's text (15 Nov 2026: "Mar - Apr, Sep, Dec 2024" and "Fall 2025").
3. **GCAT matches by name and date only.** A satellite name links to a GCAT payload only when exactly one payload
   of that name (spaces and punctuation ignored; Cosmos read as Kosmos, Shi Jian as SJ, Shiyan as SY, Tongxin Jishu
   Shiyan as TJS) was launched by the operation's last year and had not reentered before its first. Several or
   none: no link. 15 Nov 2026: 78 of 143 names linked; "Luch (Olymp)" is not, since GCAT has more than one Luch.
   **From orbit-2.13 (17 Nov 2026):** of several, the one launched in the 366 days up to the activity's start (its
   start read at SWF's precision) is taken when it is the only one, marked `by` "launch date" and labelled on the
   card. On the 16 Nov rows it changes one link: "Luch (Olymp)", Oct 2014 - Present, to GCAT's Luch of 27 Sep 2014
   (40258), not the Luch of 16 Dec 1994. "Luch", Feb 2019, stays unlinked. Names GCAT spells differently stay
   unlinked (SWF's "SDX01"/"SDX02" are GCAT's SPADEX-A/B; "Luch (Olymp) 2" has no GCAT name match); GSSAP names a
   program, not one satellite.
   **From orbit-2.16 (17 Nov 2026, catalog build step 5):** names are matched on TIC's satellite catalog instead of
   GCAT alone: every name any source gives a payload (Space-Track, GCAT, CelesTrak, Wikidata, the alias file), read
   from the name index `catalog-names.json.gz` on Orbit's public release `catalog` (one request a run; written by
   `catalog.yml`). The same rules apply: one fitting object or none, launch-date tiebreak, and an object two
   sources disagree on fits twice, so it is not linked. A reviewed entry in the alias file
   (`orbit/data/catalog/aliases.yml`: SWF's text, optionally SWF's date text, the object or program, the evidence)
   links first, marked `by` "alias"; a program entry links the program and its members (GSSAP, 8). If the index
   cannot be read, the lane matches on GCAT's names and the alias file, with a note (`names_note`). On the 15 Nov
   rows and the 17 Nov catalog: 99 of 143 names linked (78 before), 6 by the alias file; no link moved to another
   object; two links dropped because sources disagree: "Cosmos 2536" (Space-Track gives it to 44422, GCAT to 44424)
   and "Prowler" (Wikidata's item carries USA 67's number 20963; GCAT lists Prowler apart as A04907). Either can be
   linked only by a reviewed alias entry.
4. **History, not events.** Nothing goes into the feed or onto the map. A changed layout, or a tab with fewer rows
   than a good reading has, fails the lane, which keeps its last good copy.

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
   :57-:03 or :27-:33; each object's history (60 days) read once and stored, never asked for again. **The account
   is shared** with Noisefloor, whose daily workflow makes one GP query in its step "GEO region (Space-Track)"
   (Tom, 15 Nov 2026). The hourly limit is the account's, so from `orbit-2.8` Orbit reads that workflow's recent
   runs from GitHub's API just before asking: while a run is going, or within an hour of that step, it keeps its
   last reading and says why on the lane; if GitHub cannot be read it waits too. Noisefloor checks Orbit's
   snapshot the other way (16 Nov 2026). From the GEO region lane (below), the update run also waits for
   Orbit's own workflow `geo.yml`, and that workflow waits for the update run and Noisefloor's. **From
   `orbit-2.21` (18 Nov 2026) neither waits for Noisefloor:** its GEO page moved here and its GP step went with it
   (Noisefloor PR #50), so the update run waits for `geo.yml` only and `geo.yml` for the update run only. Before
   that, any Noisefloor daily run still in progress made Orbit skip, though it no longer queried.
2. **One set per epoch**, the later-created where Space-Track re-issued one.
3. **Change against the object's own noise.** For each pair of consecutive sets: the change in semi-major axis,
   inclination, node and eccentricity, less the object's median drift over that interval (drag decay, nodal
   precession), as along-track (v da / 2a), cross-track (v times the plane angle) and eccentricity (v de / 2)
   velocities. A pair is marked when one term is at least 8 robust deviations (1.4826 x MAD) above the object's
   own median and the total is at least 0.05 m/s; at least 10 pairs are needed first; marks under a day apart are
   one change only when they agree, with the same dominant term and the same sign of semi-major-axis change
   (`orbit-2.6`, Tom, 15 Nov 2026). A change is listed only at 0.25 m/s or more in geostationary orbit (0.05 m/s
   elsewhere); smaller ones are counted, not listed. **In low orbit** a change whose largest term is cross-track or
   eccentricity is listed only at 1 m/s or more (`orbit-2.8`, Tom, 15 Nov 2026, from the ISS case below); the rest
   are counted, not listed. Every listed change also gives the velocity its net semi-major-axis change alone
   implies (v |da| / 2a, steady drift removed) beside the total, which adds the noisier terms. Geostationary
   objects also show longitude and drift before and after.
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
   geostationary floor, which left G2 one change and SJ-21 six. Joining every change under a day apart made
   SJ-21's approach, docking and tow one change (17-25 Jan); from `orbit-2.6`, joining only changes that agree
   gives SJ-21 fifteen: 17-19 Jan 5.7 m/s lowering, 20-21 Jan 4.3 m/s raising, 21-25 Jan 69.6 m/s (the tow, G2
   69.4 m/s), 26 Jan 70.7 m/s back down. It also splits small corrections, e.g. two 0.4 m/s cross-track marks on
   27 Dec with opposite tiny semi-major-axis changes. Velocities are differences between published orbits,
   not burn records.
7. **The low-orbit known case** (the ISS, `tools/orbit.py maneuver-case iss`, run 15 Nov 2026 on 965 Space-Track
   sets, 15 Jan to 1 Jun 2024, one GP_HISTORY read): scored against the five reboosts NASA's ISS Daily Summary
   Reports announced (27 Jan, 23 Feb, 14 Mar, 25-26 Apr, 24 May; US public domain), a change counting as a hit
   when it comes within 12 hours of NASA's stated time or span. **All five hit**, each as an in-track change
   raising the orbit 1.0-3.1 km. The semi-major-axis change alone gives 1.76 m/s on 23 Feb (NASA 1.725), 1.68 on
   14 Mar (NASA 1.59) and 2.56 for 24 May's two burns (NASA 2.26); the listed totals run higher (2.23-2.25 m/s)
   because they add the noisy cross-track term. **Nine marks are not in NASA's list**, all cross-track or
   eccentricity at 0.28-0.84 m/s with semi-major-axis changes under 0.2 km, near the threshold (z 8-15); in low
   orbit the cross-track noise is 0.32 m/s against 0.006 m/s in-track. Reboosts also drew cross-track marks beside
   them (fit settling after the burn). **The G5 storm of 10-12 May 2024** drew no in-track (drag) mark and one
   0.32 m/s cross-track mark. NASA's reports found may not list every manoeuvre, so an extra mark is "not in this
   list", not proven false. Medium and high orbits are not yet checked against a known case.
   **With the low-orbit rule (`orbit-2.8`)**: still 5 of 5 hits, 0 marks not in NASA's list; 11 cross-track or
   eccentricity marks counted, not listed, over the whole span (the 9 extras plus 2 beside reboosts). The
   semi-major-axis velocity alone: 1.79 m/s on 23 Feb (NASA 1.725), 1.71 on 14 Mar (NASA 1.59). The rule as first
   worded to Tom ("mainly along-track or eccentricity, or cross-track above about 1 m/s") would have kept the
   0.53 m/s eccentricity mark of 28 Apr 2024; the 1 m/s floor applies to eccentricity too, which is what gave the
   "drops all 9" result Tom approved.
8. **Precession at each pair's own rate (`orbit-2.43`, 27 Nov 2026).** The node's J2 precession is removed first at
   the rate each pair's own orbit gives (-1.5 n J2 (Re/p)^2 cos i, the mean of its two sets' rates), and the
   object's median rate then takes only what is left (lunar and solar pull, higher zonal terms). One median rate
   left a decaying low orbit's faster precession in long pairs: synthetic, no burn, 450 km and 51.6 deg decaying
   36 m a day, a 4.5-day gap late in a 120-day history listed 2.5 m/s cross-track. With the change it lists nothing;
   on the three known cases every listed change stays at the same span, totals move by 0.29 m/s at most, and the
   ISS stays 5 of 5 with none outside NASA's list. Scaling noise by pair length was measured and not adopted (it
   added a change outside NASA's list). What the known cases measure, detection and probable false listings
   included: `docs/validation/maneuver-calibration.md`.
9. **How soon a change is listed (measured 19-27 Nov 2026).** The lane reads Space-Track when an update run starts
   and the account's hour allows: the hub's dispatch at :55 past 00, 06, 12 and 18 UTC, and every push to main (the
   run's own cron is a late fallback). A change is listed in the run that first reads its set and goes live with
   that run's deploy, about 3 minutes later. Of 84 new element sets of watched objects published in that span, the
   first read came a median 1.6 hours after Space-Track created the set (its `CREATION_DATE`), 90% within 3.8
   hours, longest 5.7 hours. Expect up to about 6 hours when nothing is pushed, and longer when a GEO run's query
   takes the account's hour just before a dispatch: 9 of 112 update runs were held that way, two of them dispatch
   runs (25 Nov 00:55 and 26 Nov 12:55 UTC; the second left 10 hours between reads). Luch (Olymp) 2's set of 21 Nov
   15:41 UTC was created at 19:16 UTC. The run at 19:47 was held by the hour after the 18:56 read, and the run at
   21:06 by the GEO run of 20:56. The change was listed at 00:57 UTC on 22 Nov. Its next set (22 Nov 15:37 UTC,
   created 19:16) was listed at 20:05 UTC the same day.

## Baselines from GCAT's history (`orbit-2.8`)
Tom, 15 Nov 2026 (decision 8, "GCAT history now, rest later"). Computed in the catalog lane at each new GCAT reading
(`gcat.baseline`), shown in the card `#baseline`; not in the feed.
1. **Windows:** the last 30 days (UTC dates, today included) against each of the 24 windows of 30 days before
   them (about two years). For each row: the recent count, the prior windows' median, lowest and highest, how many
   prior windows were as high or higher, and all 25 counts. "Above" or "below" means outside every prior window,
   not a threshold of Orbit's choosing. A count, never a warning.
2. **Series:** orbital, deep-space and near-orbital launch attempts (GCAT LaunchCode O, D or N, failures included)
   in total, by launching country (each country among the launch's GCAT agencies, once) and by GCAT agency (the 25
   busiest over the span plus any active in the last 30 days); payloads by launch date and owner state (top 30);
   reentries by GCAT decay date and owner state, in total and by owner (top 20).
3. **The newest window fills in late** for payloads and reentries: GCAT adds payloads and dates reentries as it
   learns of them, so a "below" there can be lag. Launches are dated promptly. First measured on the 13 Nov GCAT
   copy: 21 launches in the last 30 days against a prior median of 26 (20 to 41); 83 reentries against 143 (114 to
   274), below every prior window, which is likely lag. Checked 15-16 Nov 2026: the lag isn't seen yet. Between the
   13 and 15 Nov copies GCAT added no reentry dated 17 Oct-12 Nov (80 then, 76 now); the 82 recent ones are spread
   at 2-3 a day across the window rather than thinning toward today; and the four windows before it (139, 123, 119,
   137) are not low. A lag of weeks or more is not ruled out.
4. **Not from GCAT:** catalog additions by date of cataloging (GCAT keeps no such date) and Orbit's own counts
   (listed orbit changes per object, warnings per area). Those come from Orbit's own daily archive (below, from
   `orbit-2.11`), with baselines after 90 days of it.

## Anomalies against GCAT's history (`orbit-2.49`, 27 Nov 2026)
Tier anomaly means unusual against Orbit's own baseline, under the feed contract's revision 2.1 rule. It is a count
or a record, never a warning, a prediction or a judgment of why. Two kinds:
1. **A 30-day count outside every prior window.** A row of the GCAT baselines (above) whose last 30 days are above
   or below all 24 windows of 30 days before them becomes one feed item, `orbit:baseline:<series>:<key>`, off-map,
   linking `/catalog#baseline`. Its `signal` is the recent count against the prior median, with `baseline_n` 24 and
   `exceedance` 1 in 25 (the smallest 24 windows can show).
   - **Which side.** Launch attempts (all, by launching country, by GCAT agency) on either side. Payloads and
     reentries only above: GCAT adds payloads and dates reentries as it learns of them, so a low recent window
     there can be lag (item 3 above). A low launch count says GCAT lists launches one to three days late.
   - **Small counts.** Above needs at least 3 in the recent window; below needs at least 3 in every prior window.
   - **The rule's own flag rate.** `gcat.baseline` counts 24 more windows (four years in all). Each of the 24 prior
     windows is tested against its own 24 before it, per side; the share that would have been flagged is the
     row's `flag_rate` and the item's `baseline_ref.flag_rate`. A series the rule flagged on more than 5% of those
     windows (more than 1 of 24) is not called an anomaly: the kit's cap for a series. A series that grows steadily
     (most launchers' cadence) is above its past often, so this keeps it out.
   - **Freshness.** Items are only made while the baseline's recent window ended within 72 hours of the build. GCAT
     unchanged for longer leaves an old count, so the items drop out until GCAT's next copy.
   - First measured on GCAT's 27 Nov 2026 copy: 90 rows; the rule fired on 3% of past windows above and 0.4% below,
     and 11 rows above and 2 below are over the 5% cap. Three rows qualified: the US and SpaceX launch counts below
     every prior window (8 against 9 to 18, and 7 against 9 to 18; Launch Library 2 also lists 7 SpaceX launches
     for 29 Oct-27 Nov), and Roskosmos (GCAT agency FKA) above (3 against 0 to 2). Reentries (95 against 109 to
     277) were below every window but are not flagged on that side.
2. **A breakup or collision.** A GCAT object with status E (exploded) or C (collided) is rare in GCAT's record:
   one dated in the 24 windows before 27 Nov 2026. Its feed item (`orbit:breakup:<jcat>`) is tier anomaly for 72
   hours from the reading that first listed it, the kit's hold for an event, then routine. GCAT dates breakups late,
   so the hold runs from Orbit's listing (`first_listed` in the snapshot, carried from run to run; `last_change_at`
   is that listing), not from GCAT's breakup date, which stays the item's `event_start`. The item states how many
   breakups GCAT dates in the 24 windows before. A first reading with no earlier one dates each by GCAT's breakup
   date, so the whole record is not called new.

COP reads the tier as it does every program's: an anomaly is unusual against that program's own baseline.

## Orbit's own daily archive (`orbit-2.11`, 16 Nov 2026)
Decision 8's second half (Tom, 15 Nov 2026). Each run adds itself to one entry per UTC day (`orbit/archive.py`,
schema `orbit-archive/1`), every day kept (no cap since 18 Nov 2026):
1. **Listed orbit changes**, each keyed by NORAD number and start date, with name, regime, size and dominant term,
   on days the lane read Space-Track itself (`ok`, or `unchanged` while it waits out the hour). Only what the page
   lists goes in, with the watched count it already shows; the private watch list does not.
2. **Warning areas in force**, by Orbit's area key, with hazard, regions and every broadcast seen that day, and the
   newest NGA memorandum date and form, so a day read from stale memoranda (the API has answered 503 since at least
   6 Nov) is marked as such rather than read as a quiet day.
3. **Catalog changes by GCAT reading**, keyed by GCAT's own satcat stamp so two runs on one copy count once: added
   (fresh and late), removed, temporary entries closed, changed, owner changes, newly numbered, late launches. GCAT
   keeps no date of cataloging, so a reading's changes are dated by the day Orbit read them.
4. **Coverage:** runs that day and each lane's statuses. A day with no run, or with a lane that failed or was off,
   has no count for that series, never a zero. Baselines start 90 days after the first day and will skip those days.
5. **Where it lives:** `data/state/daily_archive.json` in the Actions cache, published at `/data/archive.json` with
   the site. A run with no local copy reads the published one back (one request to Orbit's own site) and merges it
   day by day, so a lost cache entry does not start the archive over. The page notes the archive under the GCAT
   baselines (days kept, days with no run, the date baselines start).

## Launch ledger (`orbit-2.9`, 16 Nov 2026)
Hourly, one Launch Library 2 request takes the 14 launches from the newest saved launch's NET on, in NET order. The
first is that launch, which verifies it; the rest are new. A by-id lookup (at most one an hour) covers the newest
saved launch when the pull doesn't hold it and, otherwise, the earliest launch in the last 14 days with no final
status (Success, Failure, Partial Failure). Every field change is logged (newest 200 kept). A launch LL2 drops is
kept and marked. A launch Launch Library 2 reports is reported, not measured, like a scheduled launch: kind
observation, status_class reported. The ledger is the suite's shared launch record from 1 Jan 2024; GCAT stays
the record for objects, reentries and the baselines, and `since_gcat` lists what LL2 has and GCAT doesn't yet.

## Payload orbits (`orbit-2.10`, 16 Nov 2026)
Each launch's payloads carry GCAT's own perigee and apogee (km), inclination (degrees) and the date of those
elements (`inc`, `perigee`, `apogee`, `orbit_date`). GCAT writes 0 / 0 / 0.00 before an object has elements and
`-` where none apply: both are null, never an orbit at zero. An escape trajectory's apogee (`Inf`, 95 objects on
13 Nov 2026) is null with its perigee and inclination kept. Negative perigees and apogees (suborbital and
hyperbolic paths) are GCAT's figures, kept as given. Launch reads `inc` from Orbit's snapshot for its joins and
trajectory checks.

## Launch's place check (`orbit-2.10`, 16 Nov 2026)
Orbit's warnings table pairs a scheduled launch and a hazard area on time alone (NET in a window of four hours or
less, or up to an hour before). Launch reads Orbit's areas and scheduled launches each hour and checks place too:
the area's centre inside an azimuth band (+-5 degrees) and a downrange distance seen in that pad's closure history
(x0.5 - 50 NM to x1.25 + 100 NM), or within 1,500 NM where the pad has no history. Orbit reads Launch's rows (lane
`pairs`, one request), keeps the best row for each launch and area, and shows Launch's level, distance, azimuth and
implied inclination under each pairing; a time-and-place pairing still in its window is drawn as a dotted great
circle from the pad to the nearest polygon's centre. Launch's rows can be a run behind Orbit's; a pairing Launch has
not checked says so. Every level is a coincidence, never a finding that an area is for a launch. Source
`tic-launch`, graded B2 (Orbit's call).

## The globe (`orbit-2.11`, 16 Nov 2026)
Tom's decisions 4 (Cesium ion) and 7 (ground tracks only on the 3D view; COP keeps pads). A "Globe (3D)" switch on
the map card loads CesiumJS 1.146.0 (Apache-2.0) and satellite.js 7.1.0 (MIT), both self-hosted in `vendor/`, and
draws the flat map's layers on a globe with the same cards. It adds the satellites whose orbit changes Orbit lists:
each one's place when the page opened and its path over one orbit (a day at GEO), propagated with SGP4 from the
newest Space-Track element set Orbit holds for that object (`elements` on each listed change), with drag, B* and the
mean-motion derivatives set to zero. It is a drawing for orientation, not a tracking product: the set can be days
old and the path drifts from the truth with time. Only listed objects' sets are published; the watch list is not.
Imagery: Cesium ion's world imagery (Bing Maps aerial) with the site's public, read-only token restricted to
Orbit's hosts (repository variable `CESIUM_ION_TOKEN`, written to `data/cesium.json` at build); without it, or if
ion refuses it, Natural Earth II from Cesium's own assets. CesiumWidget only: the Viewer's widgets need eval,
which the CSP forbids.

## Paths of new payloads (`orbit-2.12`, 16 Nov 2026)
Tom's yes, 16 Nov 2026. Lane `paths` makes one request a run for CelesTrak's last-30-days GP group (JSON, about
200 objects) and keeps the sets of objects of GCAT's recent launches, by launch tag: every object GCAT lists as a
payload of that launch, and, while GCAT hasn't listed them, any other object of the launch whose name doesn't
mark it as a rocket body, debris or a platform (CelesTrak's "OBJECT A" names stay). Snapshot block
`payload_sets` (`by_launch`, each with NORAD number, name, COSPAR id, `gcat_payload` and `elements`). The globe
draws a launch's payload paths only while that launch is picked, the same way as listed changes' paths (SGP4,
drag left out, for orientation, not for tracking). CelesTrak's policy: one download per 2-hour update; its 403
for a repeat inside an update keeps the previous sets and is not retried. Space-Track stays the source for watched
objects and orbit changes; these sets are never used to find orbit changes. Not in the feed.

## The GEO region (16 Nov 2026; step 2 of `geo-move-plan.md`, Tom's "Start step 2")
Moved from Noisefloor, where it ran from 27 Oct 2026 (`tools/geo_region.py` there). The GEO belt is Orbit's subject
under the boundary Tom accepted on 16 Nov 2026 (Orbit: what is in orbit, who owns it, what it is doing; Noisefloor:
signals, not objects). Module `orbit/geo_region.py`, command `python tools/orbit.py geo`, workflow `geo.yml`.
1. **Source:** one Space-Track gp query a run for every object near GEO (mean motion 0.9-1.1 rev/day, eccentricity
   under 0.3, not decayed), through Orbit's client and limits (item 1 of the orbit changes above): at most an hour
   after any other gp query on the shared account, checked from GitHub's record of Orbit's update runs (and of
   Noisefloor's daily runs until `orbit-2.21`, 18 Nov 2026); a run inside the hour skips and says so. Plus one CelesTrak request for its GEO group, the
   list of active payloads that the "quiet" event uses (yesterday's list when CelesTrak is not read).
2. **Rules unchanged from Noisefloor:** the zone (IADC protected region, GEO +-200 km, inclination 15 deg or less),
   graveyard, below, crossing and inclined regions; 25 km and 0.25 deg edges against flicker; events new,
   returned, arrived, left up, left down, left, quiet and gone between each day's inventory and the day before.
   Checked 16 Nov 2026 on Noisefloor's own day files for 15 and 16 Nov 2026: the same 1,836 objects, regions,
   counts and events (one "quiet", TIANTONG-1 1), from the same gp replies.
3. **Files, public, release `geo-YYYY` of this repository:** `<day>.geo-region.json` (schema `orbit-geo-region/1`:
   regions, counts, events, the objects with their latest elements, the active list used) and
   `geo-elements-YYYY-MM.json.gz` (schema `orbit-geo-elements/1`, every element set held by epoch month from
   1 Jul 2026, the columns Noisefloor's parquet files had). Basic SSA data, redistributed with Space-Track's
   citation as Noisefloor did (Tom, 15 Nov 2026). Orbit's private watch list is not in them: they hold every
   object near GEO, and the watch-list query stays separate.
4. **History:** imported once from Noisefloor's public releases (`tools/geo_import.py`, workflow `geo-import.yml`;
   no Space-Track request): 508,742 element sets July-November 2026 and 111 day files, measured 16 Nov 2026.
5. **Not yet:** the page (step 4), feed items. Nothing from this lane is on the site or in the feed.

## GEO callouts (17 Nov 2026; step 3 of `geo-move-plan.md`)
`tools/geo_callouts.py`, moved from Noisefloor (`35328c0`) with its pre-registered rules C1-C8, thresholds, cases
and scoring unchanged (`docs/validation/geo-callouts.md`, `geo-callouts-cases.json`, `site_src/geo_roles.json`
copied unchanged). Run at build time only, with numpy and sgp4 pinned in `tools/requirements-callouts.txt`; the
collector and live lanes stay standard library. Published on the GEO page from step 4 (below).
1. **Same results:** on the same input (Noisefloor's parquet of 27 Oct) Noisefloor's script and the port write
   byte-identical files (11,009 callouts). On Orbit's own element history the port matches Noisefloor's held run of
   31 Oct (8 Jul-30 Oct): 11,022 of 11,023 callouts identical, none missing either side; one C2 distance differs
   (SESAT 2 / LDPE-1, 30 Oct, 152.9 vs 152.5 km; both objects' sets are the same in both histories, so probably a
   set published after the held run's pull, unverified). `score` gives Noisefloor's `score-v1.json` exactly (40
   expectations, every case run, every rule's decision).
2. **One input change:** the catalogue (name, owner, type) is the newest entry per object across every day file.
   Noisefloor read the newest file only, so LDPE-2 (54219), gone from the public catalogue on 10 Nov 2026, lost its
   type in any later rerun and with it 14 callouts.
3. **GEO orbit changes: Orbit's rule, not C5 (Tom, 17 Nov 2026).** Compared on the same element history
   (8 Jul-16 Nov 2026) for the 10 listed-role objects and the GEO objects Orbit watches: C5 marked 53 days, Orbit's
   rule ("Orbit changes in watched objects", item 3: 8 robust deviations of the object's own noise, 0.25 m/s floor at GEO) 29
   changes; 27 agree. C5's 26 others: Luch (Olymp) 2 drifting along the belt (15, 0.06-0.55 m/s, within 2-9 of its
   own noisy baseline), SJ-21 station-keeping (4, 0.20-0.25 m/s), 0.02 deg inclination changes over 7-9 day gaps
   that natural drift explains (3; C5 takes no rate off), USA 324/325 with 2-3 sets (2), and two burns just under
   0.25 m/s. Orbit's 6 others: MEV-1 12-19 Aug (0.77 m/s, the A6 undocking C5 missed) and five MEV-2 cross-track
   changes of 0.32-0.75 m/s. On C5's own published cases Orbit's rule hits 6 of 6 (C5 5 of 6). Known gap: an
   object with under 10 set pairs is not judged (USA 324 moved +0.66 deg/day over a 24-day gap and was not
   marked; from `orbit-2.38` the two-set rule covers such objects). C5 stays in the script as the scored v1 record; the page (step 4) uses Orbit's rule for listed-role
   orbit changes.

## The GEO page (18 Nov 2026; step 4 of `geo-move-plan.md`)
`geo.html`, moved from Noisefloor's /geo page (globe, belt strip, look angles, sun and shadow, relative motion,
closest objects, beams, footprint files, callouts). Page only: nothing new in the feed (callout feed items wait on
Tom's yes).
1. **Data** (`tools/geo_page.py`, at build time in the update run): the newest `<day>.geo-region.json` on the
   `geo-YYYY` releases for the objects and the "Active" colour (CelesTrak's active GEO group from the same
   `geo.yml` run, where Noisefloor read its own CelesTrak snapshot), the monthly element files for the tracks
   (SGP4 per element set until the next, as Noisefloor's `geo_globe.py`), 30 days of the day files' events, and
   `site_src/geo_roles.json`. No request to Space-Track or CelesTrak.
2. **RPO pairs (Tom, 17 Nov 2026, "Add RPO pairs"):** every row of SWF's RPO sheet (lane `rpo`, the snapshot's
   names matched to catalogue numbers) whose chaser and target are both near GEO in today's list, one line per
   chaser-target pair between today's positions. Rows with one end near GEO are counted, not drawn. SWF's date and
   mission text are shown as SWF gives them; today's positions say nothing about how close the two were then.
3. **Callouts:** `geo_callouts.py publish`, the last 14 days of C1-C8 by the frozen v1 rules, except C5 (Tom, 17
   Nov 2026): listed-role orbit changes are Orbit's rule (`orbit/maneuver.detect` on every set held, 8 robust
   deviations, 0.25 m/s floor at GEO, 10 pairs minimum), listed under C5's id with the change in m/s, its main
   term and, for a pair 48 h or more apart, the gap. Objects with under 10 pairs are listed as not judged.
   First local run (18 Nov 2026, release of 18 Nov 11:55Z): 1,395 callouts 4-17 Nov (C1 378, C2 1,001, C3 2, C4 2,
   C5 6, C6 1, C8 5); C5's six are MEV-1 (inclination 0.03 to 0.54 deg between 5 and 15 Nov; 10.4 and 26.3 m/s
   across gaps) and MEV-2 (0.34-0.75 m/s); USA 324 and 325 not judged. Noisefloor's live file of the same span had
   709 (no C3, C4 or C5); not investigated, since that page retires at step 5 and the port matched the held run.
4. **Self-hosted libraries:** three.js 0.185.0 (`vendor/three/`, `three.module.min.js`, `three.core.min.js`,
   `OrbitControls.js`, MIT; npm tarball sha256 5f52a93f...433d) and Orbit's satellite.js 7.1.0 through
   `geo/satellite.js`. geo.html's import map is the one inline script; its sha256 is in `_headers`' script-src
   (`tests/test_geo_page.py` holds it). The CSP has no `'unsafe-inline'` for styles, so the globe's markup carries
   `data-css` and one MutationObserver applies it through the CSSOM.
5. **Belt board (18 Nov 2026; step 5, Tom: "Port to Orbit first"):** `tools/geo_belt.py`, called by `geo_page.py
   build` into `globe.json`'s `belt`, drawn in the page's "Belt board" section. It carries what Noisefloor's CelesTrak
   board (`tools/geo.py`) showed and step 4 did not move, so nothing is lost when Noisefloor's copy retires. Scope:
   CelesTrak's active GEO group (the day file's `active`), as Noisefloor's board, with Orbit's Space-Track sets.
   Class by drift (0.1 deg a day) and inclination (1 deg); close pairs of different owner codes within 100 km at the
   build time by SGP4 from each newest set (one owner code counted, not listed, unless a listed role); orbit changes
   by Orbit's rule (as C5 above) on every active object, ending in the last 7 days, labelled with Noisefloor's kinds
   from the drift and inclination of the sets either side (station-keeping folded; an inclination change of 0.02 deg
   or more on an inclined orbit is its own kind). Objects with under 10 pairs of sets are listed apart with their
   last two sets, not judged. About 10 s of the build (563 objects). Standard library tests (`test_geo_belt.py`,
   positions injected).
   **Checked against Noisefloor's live board, 18 Nov 2026 19:43Z (Noisefloor) and 19:48Z (Orbit):** same 563
   objects and the same classes (362 station-kept, 176 inclined, 25 drifting); close pairs of different owners 17
   of 18 shared, at the same distances; the other one each side differs only by owner code, not position: the
   day file (Space-Track) lists GALAXY 32 and GALAXY 36 as US where CelesTrak's catalogue says ITSO, so Orbit lists
   GALAXY 32 with INTELSAT 40E (28 km) and counts VIASAT 3-F1 with GALAXY 36 (51 km) as one owner; Noisefloor the
   reverse. Same-owner pairs 79 vs 78. Changes other than station-keeping: the same 7 objects (SIRIUS FM-6, TJS-24, HYLAS 2,
   IPSTAR 1, USA 149, QZS-2, BEIDOU 3 IGSO-3); Orbit adds EUTE 16A (0.90 m/s, mostly cross-track). Noisefloor's
   other three: IRNSS-1E (its change ends 11 Nov 17:06Z, 3 hours before the 7-day window), and USA 324 and USA
   325, which have 3 and 2 public sets since 19 Oct, too few for Orbit's rule; they are in the "not judged" list
   with their last two sets (USA 324's drift 0.68 to 0.02 deg a day east between 22 Oct and 15 Nov). Routine
   station-keeping: Orbit 284 against Noisefloor's 135; Orbit's rule marks smaller changes between consecutive sets
   than fixed thresholds on daily snapshots.
6. **The GEO globe's colours (`orbit-2.46`, 27 Nov 2026).** Points on the globe are compared with every other point,
   so each colour mode has to pass the dataviz validator with all pairs (`--pairs all`). The globe is a dark canvas
   in both page themes (`#0b0e12`), so its colours are checked once, in dark mode on that ground. The old palette of
   seven hues and a grey failed: worst colour-blind pair magenta and aqua, Delta E 1.6 (deuteranopia); worst
   normal-vision pair violet and blue, 9.8 (floor 15); the grey `#8e97a3` outside the lightness band. Of the
   reference palette's eight dark hues, no four pass all pairs on `#0b0e12`, and only eight sets of three pass with
   the grey `#616a75` (blue, orange and aqua among them). Each mode now uses at most the three owner hues and the
   grey, at the site's dark token values (`--g-us`, `--g-cn`, `--g-ru`, `--g-other`): worst pair 9.4 colour-blind
   (aqua and orange, deuteranopia) and 16.5 normal vision (grey and aqua), every colour at 3:1 or more on the ground.
   The grey is neutral by design, so the chroma floor is not applied to it.
   - **Owner:** US blue, PRC orange, CIS (Space-Track's code for Russia and the former USSR) aqua, all other owners
     grey, as on the site's other maps. The earlier mode coloured the seven owners with the most objects, so a
     colour followed a rank, not an owner. Any owner can still be found by typing its code in the search box, and
     the selected object's details name it.
   - **Where:** protected zone blue, graveyard orange, crossing the zone aqua; inclined and below the zone share the
     grey (one key entry, "Inclined or below the zone"). The Where filter still shows either alone, and the
     selected object's details name its region.
   - **Type:** payload blue, rocket body orange, debris aqua, other or unknown grey. **Active:** active blue, not
     listed as active orange.
   - **Key and labels:** the key sits under the canvas on the same dark ground, not over it, so no point, label or
     ring passes beneath it. A selected object's name takes the first spot (right, below, above or left of its
     point) that keeps 2 px clear of every other name, every selected point and the view's edge; a name with no
     clear spot is left off the globe, and the panel lists every selected object. With about 1,800 points in the
     belt a name cannot keep clear of every point; its dark halo keeps it readable over them.
   - **Not changed here:** the panel's line charts (up to five nearest objects, keyed by a numbered list) keep five
     line colours, and the overlay rings (RPO pairs, arrivals and departures, callouts C1-C8) keep their own
     colours; the rings are a second shape on the points, not a colour mode.

## Predicted reentries (`orbit-2.13`, 17 Nov 2026)
Tom's "let's get all three items done", 16 Nov 2026, about 9:15 PM CST. Lane `decay` (`orbit/tip.py`):
log in, one query of Space-Track's class `tip` (messages of the last 5 days, newest first), log out; three
requests a run on the shared account. TIP is not GP, so the account's once-an-hour GP rule and the wait for
Noisefloor's and the GEO run's queries do not apply. Reentry and decay data are basic SSA data under USSPACECOM's
blanket approval, conditioned on citation (`spacetrack-disclaimer.md`); the card and `decay.attribution` carry it.
1. **What is kept:** the newest message for each object (by message time, then message id), its predicted time
   (`DECAY_EPOCH`), `WINDOW` in minutes, direction, latitude and longitude (TIP's 0-360 east turned to east and
   west), inclination, revolution, hours to the next report and USSPACECOM's high-interest flag. GCAT's name, type,
   launch and owner where GCAT's index lists the NORAD number.
2. **Window:** read as plus or minus `WINDOW` minutes around the predicted time. In the first reply (17 Nov 2026)
   it ran at 16-19% of the time left to the predicted reentry, close to the usual rule of a fifth; Space-Track's
   own wording for the field was not found, so this reading is Orbit's. A prediction whose whole window has closed
   is kept for a day, marked closed, then dropped; GCAT dates the reentry itself later (the reentries card).
3. **Place:** where the object would be at the predicted time, not where debris falls. With a window of hours the
   object circles the Earth several times inside it. Not on the flat map or in COP (decision 7: reentries stay
   off the map). From `orbit-2.15`, on the globe only and only when picked: the ground track over the window
   (item 6).
4. USSPACECOM's predictions, quoted as issued: Orbit adds no probability, warning or judgment. Not in the feed;
   whether to add it, and under which requirement, is Tom's call.
5. Checked on the reply of 17 Nov 2026 03:3x UTC: 191 messages over 14 days, 7 objects with an open window
   (fixture `tests/fixtures/spacetrack_tip_20261117.json`). Early messages give the next report in 72 h, hence
   5 days and not 3.
6. **Reentry tracks on the globe (`orbit-2.15`, Tom's "Reentry tracks", 16 Nov 2026 about 10:30 PM CST).** The
   update run's one GP query (the watch list's, orbit changes item 1) also asks for the objects with an open TIP
   window, soonest first, at most 30: no extra request, and the hourly rule unchanged. Lane `decay` now runs
   before `maneuver` so the same run's predictions are used. Their newest sets go to snapshot block
   `reentry_sets` (mean elements plus BSTAR and the mean-motion rate), never into the watch list's store, history
   or report; a set says nothing of the watch list. The globe draws, for the one picked object, the ground track
   from the predicted time minus the window to plus the window (at most 24 h each side), one point a minute, SGP4
   with drag kept, and TIP's point at the predicted time. The object comes down somewhere along the line, not at
   the dot. Checked 17 Nov 2026 on Starlink 5046 (53892, TIP 08:59 UTC +-60 min) with CelesTrak's set of 16 Nov
   22:56 UTC: the line passes within about 100 km of TIP's point (one point a minute limits it) and reaches it about
   3 minutes before TIP's time; with drag left out, 130 km. A drawing for orientation, not a prediction of Orbit's.
7. **TIP against the reentry (`orbit-2.17`, Tom's "Yes, build it", 18 Nov 2026 about 9:40 AM CST).** Space-Track's
   reply covers 5 days and GCAT dated these reentries about 3 days later, so the TIP lane now hands every message of
   the reply on (`decay.all_messages`: NORAD number, message time, predicted time, window, message id) and Orbit's
   daily archive keeps each one once, on the day a run first saw it (`tip`, deduplicated over 10 days; carried or
   failed lanes add nothing). Each run then builds snapshot block `tip_check` (`tip.check`) for objects that came
   down in the last 30 days:
   - **TIP's time after the reentry:** the newest message issued after the time it gives, with a 1-minute window.
     In the 17 Nov reply every object that had come down had one, issued 2-8 hours after the time it gives. A message
     issued late with a wider window (10-60 minutes seen, e.g. 45755 at plus or minus 39) stays a prediction: GCAT
     marks those times uncertain and rounds them (01:00 for TIP's 00:48).
   - **Last prediction:** the newest message issued before that time. `offset_min` is TIP's time after the reentry
     minus the predicted time (positive: later than predicted), `inside` whether it falls within the window,
     `lead_h` the hours from the message to the reentry.
   - **GCAT:** GCAT's reentry time against TIP's time after the reentry (or, without one, the last prediction), with
     GCAT's own uncertain mark. GCAT often takes its time from that same TIP message, so a match is not an
     independent check; differences of a day or more are named on the card, each source as given, without saying
     which is right.
   Checked on the 17 Nov TIP fixture against GCAT's copy of 18 Nov 01:44 GMT: 20 objects with TIP's time after the
   reentry; 17 came down inside the last prediction's window (outside: 45223 +79 min against +-60, 61642 -131 min
   against +-60, 58706 2.3 days early against +-15 h, its last prediction issued 12 h before); GCAT gives the same
   minute for 18 of the 19 it has dated. **Starlink 30221 (57418):** TIP's time after the reentry is 10 Nov 2026
   17:37 UTC, GCAT's 17 Nov 2026 17:37 UTC, exactly 7 days apart. Shown as each gives it. Observations of the two
   records, not a rating of either.

## Daily lead (`orbit-2.18`, 18 Nov 2026)
Tom, 18 Nov 2026 about 10:30 AM CST: "capture all of those ideas and the plan, then begin with the daily lead
first"; readers are "mostly people with some amount of elevated knowledge but there will be people new to this topic
as well". Plan: the private planning notes. Built by `orbit/lead.py` from the
snapshot and the daily archive, no request, at the end of each run (`_archive_run`, after the TIP check).
1. **Lines, in this order, each only when it has something:** objects TIP predicts to reenter in the next 24 hours
   (USSPACECOM's high-interest flags first); objects TIP's messages after the reentry, issued in the last 24 hours,
   put down, with the offset from the last prediction (item 7 of "Predicted reentries"); orbit changes first listed
   in the last 24 hours (first day in the archive's `maneuver.listed`; without an archive, every listed change is
   new); GCAT breakups dated in the last 7 days (GCAT dates them late, so the line says 7 days); GCAT's new copy when
   its satcat stamp is under 24 hours old (new entries, late ones, changed, owner changes, the largest late group);
   orbital launches of the last 24 hours (until launches move to Launch); and the last 30 days against the two
   years before, only where a count falls outside every earlier 30-day window (`gcat._position`'s above or below).
   Names: at most 3 per line, then "and N more".
2. **No silence read as news:** GCAT's satcat stamp over 36 hours old gets its own line naming the copy's time and
   age; a TIP, orbit-change or GCAT lane not read on the run (failed or carried) is named in a last line. When no
   line but those has anything, the page says "Nothing new in the last 24 hours from the sources read on this run".
3. **Form:** each line is text with times, dates and country codes kept apart (`parts`), so the page writes times in
   the viewer's zone and countries by name; a link to its card; and its source. Observations only, in the words the
   cards use. The page puts a "New to this?" list of the terms the lines use (TIP, window, GCAT, orbit change, LEO and
   GEO, breakup, debris and rocket stage) under the lead.
4. **Kept:** snapshot block `lead`; the day's last lead in the daily archive (`days.<date>.lead`,
   `archive.keep_lead`), published with it at `/data/archive.json`, so each day's lead can be cited.
5. Checked on the live snapshot and archive of 18 Nov 2026 16:17 UTC: one object due in the next 24 hours (Starlink
   4334), two down by TIP's messages after the reentry (Starlink 4405, 21 min earlier than predicted; Starlink 1423,
   54 min earlier, both inside the window), GCAT's copy of 01:44 UTC (10 new entries, all late; 40 changed; 9 owner
   changes; largest group 5 pieces of debris from 2026-051), and 87 reentries in 30 days, fewer than in any 30-day
   stretch of the two years before (103-272). The two listed orbit changes, first listed 16 Nov, are not new.

## Per-source health in the feed (`orbit-2.19`, 18 Nov 2026)
A lane that fails keeps its last good copy in the feed, so a reader can't tell a kept item from a fresh one by the
item alone. The feed carries the doctrine kit's per-source `health` block (the form Headwind, Blackout and Elements
use), one entry per source id the items name, from the snapshot's lane records (`feed.source_health`):
`gcat-mcdowell` from `catalog`, `space-track` from `maneuver` (`ll2-thespacedevs` from `upcoming` until
`orbit-2.32`).
1. **Read on this run** (`state: up`, `last_ok` equal to `checked_at`): the lane was fetched, or GCAT said its files
   had not changed, and it was not carried from an earlier run (the archive's `_fresh` rule). Otherwise, in the kit's
   `health_state` words (feed contract revision 2.1): a failed lane is `failing` with its error; one fetched only on
   an earlier run (not run, or carried by `collect --only`) is `stale`; one never fetched or unconfigured (`off`) is
   `never`. The lane's own status stays in `detail`, and a kept copy adds "last good copy kept". A lane absent from
   the snapshot gets no entry.
2. **Why:** COP's ledger reads it, so a kept item neither ends nor counts as seen again (source-level sightings,
   built 15 Nov 2026, landed 18 Nov). A new source id on the items needs its line in `SOURCE_LANES`.

## Object pages (`orbit-2.20`, 18 Nov 2026)
Tom, 18 Nov 2026: "Yes, build it" (design the private planning notes, globe option A). Split
agreed the same day with the catalog session: the TIC satellite catalog (build step 6) supplies the data and the rules
note, Orbit draws the page.
1. **Address:** `object.html?n=<NORAD number>`, or `?j=<GCAT JCAT id>` for an object without one (GCAT's `S` ids are
   read as NORAD numbers). Keys only; names never move a page.
2. **Data:** the update run downloads `catalog-shards.tar.gz` from release `catalog` once (`tools/orbit.py
   object-data`, `orbit/objpage.py`) and unpacks it into `site/data/catalog/` (shards, `search.json`, `rules.json`,
   and Orbit's manifest `index.json`). Only the expected file names are written; anything else refuses the whole
   archive and the last copy stays. A missing archive does not stop the deploy; the page says the catalog is not on
   the site.
3. **Search** (`search.js`, on the main page and every object page): loads the index on first use; exact NORAD
   number or JCAT id, then COSPAR ID (a whole launch, "1998-067", lists its pieces in letter order, numbered ones
   first), then names from every source (exact, starting with, a word starting with, containing; payloads and
   objects in orbit first).
4. **The page:** header (each source's status, owner, state and launch date, side by side, with the source named);
   each source's orbit as it states it, never merged (GCAT with its elements' date, CelesTrak with its file's
   time) and the regime it reads as; the globe; what Orbit holds; names and sources; citations. Dates the sources
   give as days are written with their year and never moved to another time zone. A note when the catalog on the
   site is older than the rules note's `stale_after_hours` (36).
5. **Globe (option A):** drawn only from an element set Orbit already holds: a TIP object's set (its ground track over
   an open window, drag kept, with TIP's point), a listed orbit change's newest set, or a new launch's CelesTrak set;
   the newest by epoch, named with its source and epoch. Loaded only on request. Otherwise a to-scale drawing of the
   orbit's size, shape and tilt from the best-ranked source's perigee, apogee and inclination, saying the plane's
   orientation and the object's position are not known from these. No new request. The watch list's other sets
   are never drawn.
6. **What Orbit holds:** TIP messages kept in the daily archive and this run's reply, TIP's check against the
   reentry, GCAT's reentry, listed orbit changes (with the disclaimer's short form and the day first listed), SWF
   RPO rows (the other object linked), GCAT changes from the latest reading, breakups, the launch if within 30 days.
   The section always ends with what Orbit keeps and since when, so an empty section never reads as "nothing
   happened".
7. **Names and sources:** drawn from `rules.json`: names in the catalog's rank order with source, field, basis, read
   date and reference; each source's record side by side; "Sources differ" with the rules note's explanation; name
   swaps touching the object. A decay date is shown only from a source that says the object has left orbit (GCAT gives
   a date for docked and grouped objects too).
8. **Links:** every table row on the main page with a number, and each object named in the daily lead (lead parts
   `{"s": name, "o": key}`), links to its page.
9. Checked 18 Nov 2026 on a local build (live snapshot of 19:26 UTC, the catalog session's local shards): ISS, Prowler
   (A04907), Starlink 30221, USA 270 (globe drawn from its listed change's set), an unknown number, phone width and
   dark mode in headless Edge: no sideways scroll; console errors only a local `favicon.ico` 404 and Cesium's three
   inline-style CSP refusals, which the main page's globe shows too.

## Pages (`orbit-2.22`, 20 Nov 2026; ideas#71 and ideas#83)
Tom, 19 Nov 2026: every tab is its own page within the program. Orbit's one long page is split into pages that share
one header, one row of page links (the current page marked) and one script, `app.js`, which draws only the cards on
the page it runs on:
- `/` Map: the daily lead, tiles, object search and the satellite map (`orbit-2.24`).
- `/launches`: the launch map, globe and table of GCAT's launches of the last 7 days, and a card pointing to
  Launch for scheduled launches, closures and the ledger (`orbit-2.32`).
- `/reentries`: reentries of the last 7 days, predicted reentries (TIP) and TIP against the reentry. "Track on the
  globe" opens the launch page's globe with `launches.html?track=re-<NORAD>`.
- `/catalog`: catalog changes and owner codes, breakups and collisions, the 30-day baseline and archive note.
- `/changes`: orbit changes in watched satellites (with the Space-Track citation), SWF's RPO and ASAT histories.
- `/geo`: the GEO belt, as before. `/sources`: sources and freshness, and links to Orbit's data files (feed,
  snapshot, archive, sources), which moved there from the header.
- `/object`: as before, with the same page row.
A table in `app.js` (`PAGE_OF`) names the page that holds each card and each row-id prefix. A link to a card or row
not on the current page goes to its page; an old `/#section` link on the home page (feeds, COP, bookmarks made before
the split) is sent on to the page that now holds it. The feed's `visual.url` links name the page (`/catalog#breakups`).
A test checks that every card is on exactly one page and every feed and lead link lands on its card.

## The satellite map's data (`orbit-2.23`, 20 Nov 2026; ideas#71, Tom's yes to the map design)
Lane `sats` (`orbit/satmap.py`): CelesTrak's GP group `active` (working satellites; the 18th Space Defense
Squadron's GP data), FORMAT=csv, compressed, **once a UTC day**: a run on a day whose reading is already held asks
nothing. CelesTrak's usage policy (read 20 Nov 2026, updated 16 Nov 2026) states no redistribution or credit terms,
asks for compressed CSV and one download per update, and says to stop at any non-200 reply and leave it for a
person. Any reply but 200 (redirects are not followed) fails the lane, keeps the last file and is recorded in
`data/state/sats_stop.json`; the lane then asks nothing and its status says so. To clear it after looking at the
refusal, commit that record's `at` time as the only content of `orbit/sats_stop_clear.txt`: the push starts a run, the
record moves to `sats_stop_history.jsonl`, and an old clear can never lift a later stop. A timeout gets no reply, so
it is not a stop and the next run asks again. A reading with under 90% of the last reading's objects fails the lane
too. Source row `celestrak-gp-active` (A2, independence group `usspacecom`).

Each object is joined to Orbit's GCAT index by NORAD number for the owner (`group`: us, cn, ru with SU, other; `cc`
the ISO code or GCAT's state code), GCAT's type and launch date; an object GCAT has not numbered stays `other` with
no type. Orbit class from mean motion n (rev/day) and eccentricity e: `heo` from e 0.25; `leo` above n 11.25 (under
128 min a revolution); `geo` at n 0.9-1.1 (about a sidereal day, inclined orbits included); `meo` between; `other`
below n 0.9. Constellation by the start of CelesTrak's name only: Starlink, OneWeb, Kuiper, Iridium, GPS (NAVSTAR),
BeiDou, Galileo (GSAT0nnn). From `orbit-2.37`, also GLONASS (CelesTrak names them COSMOS nnnn with the series in
brackets, "COSMOS 2433 [GLONASS-M]"; a COSMOS name without the bracket is not counted), Guowang (HULIANWANG
DIGUI-nn; China SatNet's test satellites, HULIANWANG JISHU SHIYAN, are not counted) and Qianfan (QIANFAN-n, or
"QIANFAN 16 OBJECT A" before CelesTrak gives the number). On CelesTrak's reading of 26 Nov 2026: 27 GLONASS, 249
Guowang, 275 Qianfan. Published as `/data/sats.json` (`orbit-sats/1`: `fields` and `rows`, rounded to what SGP4 on a map needs);
the snapshot keeps counts only. The map that draws it is the next step of ideas#71; until then the file is unused.

## Rocket bodies and debris on the map (`orbit-2.51`, 27 Nov 2026)
CelesTrak publishes no whole-catalog, rocket-body or debris GP group, so these come from Space-Track: **one GP query a
UTC day** in `catalog.yml`'s run, its own step "Rocket bodies and debris (Space-Track GP, once a day)"
(`orbit/debrismap.py`, `python tools/orbit.py debris-gp`). The query asks class `gp` for `OBJECT_TYPE` ROCKET BODY or
DEBRIS, no decay date, an element set from the last 30 days, and only the columns the map draws (`predicates`); three
requests (log in, the query, log out). It is the account's third GP query, so the hourly rule now holds across three:
the update run's watch-list query and `geo.yml`'s GEO region query each also wait for this step, and this step waits
for both (`spacetrack.FOR_MANEUVER`, `FOR_GEO`, `FOR_DEBRIS`; the check runs after the clear-minute wait, just before
the query). A run that finds the day already read, or another GP query under an hour old, asks nothing; `catalog.yml`
starts three times a day, so a skipped start is read at the next. A reply with no usable row keeps the last file.

Rows take the map's own format (`orbit-sats/1`, the fields of `/data/sats.json`): type `R` or `D` in `type`;
Space-Track's COUNTRY_CODE read through the catalog's code table (`stcat.COUNTRY_TO_STATE`) to GCAT's state and ISO
code, so the owner groups and the owner search treat these rows as they treat payloads (CIS is the Russia/USSR group,
shown as SU); a code the table lacks is kept as written, group `other`. Space-Track's own LAUNCH_DATE. No
constellation. Published as `sats-rd.json.gz` on the public release `catalog`, with a dated copy a day on release
`sats-rd-archive-YYYY-MM`; the update run copies it to `/data/sats-rd.json`. Credit: the disclaimer's citation
(`doctrine/spacetrack-disclaimer.md` section 3), carried in the file and shown on the page when the rows are loaded.

On the map, an **Object type** filter: Payloads (on), Rocket bodies and Debris (**off by default**). The second file is
read only when Rocket bodies or Debris is on (link parameter `obj`, e.g. `?obj=p,r,d`); switching those on or off, or
Reset with them on, reloads the page with the new link. The card gives each object's type; an owner Space-Track does
not state reads "Not stated". Near-GEO rocket bodies and debris were already public in the GEO region files.

## Retention (18 Nov 2026: no program loses data; views may filter, storage keeps all)
Public releases, one per month and kind, unique asset names, never clobbered (`orbit/retention.py`, `tests/test_retention.py`);
only what is already public or open-licensed goes there. Nothing from Space-Track element sets or case reads.
- Launch ledger: the change log in `launch-ledger.json` is no longer cut at 200 entries.
- Daily archive: no 800-day cap. `update.yml` uploads a dated copy a day as `archive-YYYY-MM-DD.json.gz` to release
  `archive-YYYY-MM` (after the deploy; a failed upload keeps the files as a workflow artifact).
- GCAT catalog changes (CC BY 4.0): every reading's whole diff (added, removed, changed with field before and after,
  owner changes, late groups; no 50-item cut) as `catalog-changes-<read time>.jsonl.gz` on release `catalog-changes-YYYY-MM`.
  The published lists keep their cut of 50.
- TIC catalog: `catalog.yml` keeps `catalog-<Monday>.json.gz` once a week on release `catalog-archive-YYYY-MM`.
- Map rocket bodies and debris (`orbit-2.51`): `catalog.yml` keeps `sats-rd-<day>.json.gz` for each day read on
  release `sats-rd-archive-YYYY-MM` (Space-Track basic SSA data, published with the citation).
- Ended NAVAREA warnings: Cordon is the record (it commits `data/navarea.json` hourly and logs changes in its history
  log); Orbit's `navwarn` lane keeps only the areas in force and the daily archive's area keys. No second store.
- Needs a private store, not built (Space-Track data and the watch list may not go in a public repo): the element-set
  store past 120 days, the stored case reads and report (`data/state`), and raw Space-Track replies. Raw replies of
  open sources (NGA warnings, TIP excluded) could go to a public release; SWF sheets are CC BY-NC and CelesTrak
  has no stated redistribution licence, so those wait for a decision.

## Not built
ITU filings (BR IFIC, after ITU's legal office answers).

## The satellite map (`orbit-2.24`, 20 Nov 2026; ideas#71)
`site_src/satmap.js` draws every row of `/data/sats.json` on the home page's Cesium globe as one point, coloured by
owner group (the four validated tokens). Places are SGP4 from the row's element set with drag left out, refreshed
every 2 s in slices across frames. It is a drawing for orientation, not a tracking product. Larger, ringed points are
objects Orbit holds a finding on: a listed orbit change, an SWF RPO row matched to the object, a GCAT breakup, a
payload in CelesTrak's last-30-days group, or a TIP message not yet passed. A mark says Orbit has a record on the
object, nothing more. Filters: owner, orbit class, constellation, hide Starlink, launched in 30 days (GCAT's date or
the last-30-days group), with a finding only. Display: globe or flat map, the selected object's orbit line and ground
track, labels on marked objects when zoomed in. Filters and display options are kept in the URL. A table lists the
first 200 shown objects, those with a finding first. A missing file (Pages answers it with index.html) shows a note,
and without WebGL the filters and the list still work.
**Not built from the approved design:** colour by orbit class. (Rocket bodies and debris, not in the active group,
came in `orbit-2.51`: see "Rocket bodies and debris on the map" below.) Colour by orbit class was dropped on 26 Nov 2026: points on a map are compared with every other colour, not
only a neighbour, so the palette has to pass the dataviz validator with all pairs (`--pairs all`), in light (white
panel) and dark (`#131822`). No four hues from the reference palette's eight do so in both modes, and three hues
with the neutral grey fail too (the grey falls under 15 normal-vision Delta E, and under 6 for deuteranopia, against
magenta, violet or aqua in dark mode). The orbit class stays a filter and a column in the list.
**The owner colours, all pairs (`orbit-2.44`, 27 Nov 2026).** The four owner tokens now pass `--pairs all` in both
modes. The dark grey is `#616a75`, darker than the old `#7d8794`, which fell to 13.1 normal-vision and 5.2
deuteranopia Delta E against the aqua `#199e70`. Dark, on `#131822`: worst pair 9.4 for colour-blind vision (aqua
and orange) and 16.5 for normal vision (grey and aqua), every token at 3:1 or more. Light, on `#ffffff`, unchanged:
worst 8.2 (grey and aqua, protanopia) and 16.1. The grey is neutral by design, so the validator's chroma floor is not
applied to it. In light mode the aqua (2.8:1) and grey (2.3:1) sit under 3:1 on white; every owner chip carries its
flag and code, and each map's list and selected-object details name the owner, which is the relief the validator
asks for.
Rocket bodies and debris have no CelesTrak source. CelesTrak's GP groups (its Current Data page and GP
documentation, read 27 Nov 2026) hold no whole-catalog, rocket-body or debris group: the only debris groups are three
single clouds (FENGYUN 1C, IRIDIUM 33, COSMOS 2251), and the special sets are the GEO protected zone and potential
decays. The whole catalog's element sets come from Space-Track's GP class, whose blanket approval covers
redistribution of basic SSA data with citation; reading it would be a new daily query on Orbit's Space-Track account,
within the request limits Orbit keeps there, so the map does not show these objects until that query is set up. Rocket bodies
and debris near GEO are already published, with the citation, in the GEO region files (`geo-YYYY` releases).

## The satellite map's added options (`orbit-2.37`, 26 Nov 2026; ideas#138)
- **Owner search:** any owner code in the file, typed as the country's name or the code (GCAT's state codes for
  owners that are not countries, such as I-ESA). The owner's colour group is switched on with it. URL `cc`.
- **Launch date:** a from and a to day, both optional, and a "This year" button. An object with no launch date in
  GCAT is left out while a range is set. URL `from`, `to`.
- **Constellation:** GLONASS, Guowang and Qianfan join the list (the data section above).
- **Orbit lines:** the selected object (default), every object shown, or off. "Every object shown" draws the first
  300 in the list's order (objects with a finding first, then by name), each over one revolution centred on the
  map's time, in its owner colour, on the globe only; the line under the count says how many are drawn. URL
  `lines=all` or `lines=0`.
- **Time:** the places, lines and track can be shifted up to 24 h either way (10-minute steps), or run 60 times
  faster; "Now" returns to real time. A run stops at +24 h. The time shown is the viewer's zone, named. The
  further from now, the further SGP4 without drag moves from the real place, most in low orbits. The time is not
  kept in the URL, because a shared link should open on the reader's own now.

## Feed contract revision 2.1 (`orbit-2.25`, 23 Nov 2026)
Every feed item states `subject_id`, `event_start` and `last_change`. Ids that carry a day (the reentry count, late
catalog entries, owner changes) keep it; their `subject_id` does not, so one subject reads as one subject from day to
day. An orbit change keeps its date in `subject_id`, because that date is what tells two changes of one object apart.

Event times: a launch at its time (day precision when GCAT marks the time uncertain); a scheduled launch from NET to
the end of its window, at Launch Library's precision; reentries from the first to the last date in the count; a
breakup on GCAT's date; catalog changes over the two readings between which GCAT made them; an orbit change over the
element sets that show it, which bound the change and do not time a burn.

`last_change` comes from the source's own dates, because Orbit keeps no log of its feed items: `new` for a launch, a
breakup, an orbit change or a catalog change, and `changed` for a Launch Library record (its last edit, which may be
its creation) and for the rolling reentry count (its newest date). Orbit has no anomaly tier, so no item carries
`signal`.

## What a GEO change did, notable changes and other names (`orbit-2.26`, 23 Nov 2026; ideas#249, #250, #251)
Tom, 23 Nov 2026, after LUCH (OLYMP) 2 (55841) left 62 E: Orbit had listed "8.5 m/s between 15 Oct and 22 Nov" as
one routine row under GCAT's name, and he heard of the move elsewhere ("file all eight, then take on items 1-3").
Modules `orbit/notable.py` and `orbit/names.py`; step `_describe_changes` at the end of every collect, on new and
carried changes alike. No request: the element sets are the watch lane's, the names are the index the `rpo` lane
already reads, the roles are `site_src/geo_roles.json`.
1. **What happened** (a listed geostationary change only). From the set before and the set after: longitude and
   drift on each side (`maneuver.geo_position`), and the kind in the GEO board's words and at its line
   (`DRIFT_KEPT`, 0.1 deg a day; a test holds the two equal): station-keeping, started drifting, stopped drifting,
   drift rate changed (slowed, sped up or reversed). "Left" is used only when the two sets are 0.5 deg or more
   apart in longitude; under that the line says "began to drift from". The height above or below geostationary altitude is the one
   the drift rate implies, from the mean motion. The sentence is stored as lead parts in the change's `what`
   (times written in the viewer's zone on the page, UTC in the feed), and is on the row, in the lead and at the
   head of the feed summary. Measures gain `lon_before_deg`, `lon_after_deg`, `drift_before_deg_day`,
   `drift_after_deg_day`, `alt_after_km`.
2. **How long it had held the earlier longitude** is counted back through the sets Orbit holds for the object
   (every stored set, not the 120-day view) while each is under `DRIFT_KEPT` and within `HELD_LON` (0.5 deg) of
   that longitude. Orbit's sets start 60 days before it first read an object, so when the count reaches the first
   set the line says "in every element set Orbit holds since", never "since".
3. **Notable.** A listed change is notable when the object has a listed role on the GEO page (each role entry
   cites published reporting; a test holds that every entry has a source), the kind is not station-keeping, and
   the drift rate changed by `NOTABLE_RATE` (0.25 deg a day, about 0.7 m/s along track) or more. The floor keeps
   out a roaming inspector edging across the 0.1 line: on the live snapshot of 23 Nov 2026, without it, USA 270
   read as "started drifting" at 0.12 deg a day on a 0.9 m/s change; with it the snapshot's notable changes are
   55841 (62 E, 2.5 deg a day west) and USA 271 (4.4 to 8.9 deg a day west, 12.9 m/s).
   A notable change is the first line of the daily lead while it is new (first listed since the start of
   yesterday, UTC) or its newest set is under 24 hours old, and it is left out of the ordinary orbit-change line.
   The archive's listed row carries `notable` with the kind. `/data/notable.json` (`orbit-notable/1`) holds the
   notable changes of the 30-day window, each readable alone: names, role with its basis and sources, the
   sentence, the sets, the gap. The feed item's title begins "Notable orbit change:"; **its tier stays
   `routine`** and its id is unchanged. A higher tier, or a COP mark, is Tom's call.
4. **What it never says:** why, where the object is going, or which satellite it is near. No likelihood words.
   A pass-by table and a stop projection are ideas#248, with the wording put to Tom first.
5. **Other names.** A lane keeps the name it shows (GCAT's, for orbit changes). `names` on a listed change is
   every other name the TIC catalog's index gives the object: the catalog's display name first, then the
   index's order; a name differing only by case, spacing or punctuation from one already shown is left out, as
   are names a source marks uncertain (ending "?"), bare catalog numbers, and a joined form "A (B)" whose A is
   already shown and whose B is a name of its own ("USA 270 (Hornet 3)" beside "USA 270"). Titles and lead lines show two
   ("Luch-5Kh No. 3, also LUCH (OLYMP) 2 and LUCH-5X (OLYMP-K 2)"); the summary and the row show all. Nothing
   is merged: which source gives which name is on the object's page. A run where the index was not read keeps
   the names set on an earlier run.
6. **Known case** (`tests/test_notable.py`, fixture `luch2_sets_2026.json`: the 91 sets of 55841 in Orbit's public
   GEO release, 1 Jul to 22 Nov 2026): one change, 15 Oct 15:56Z to 22 Nov 15:37Z across an 887.7-hour gap;
   62.00 E to 58.19 E, drift -0.008 to -2.467 deg a day, about 193 km above geostationary altitude; kind
   "started drifting"; notable (role: inspection).
7. **Limits.** The simple longitude holds for low inclinations; an inclined object swings either side of it
   daily. A set fitted during a burn smears the rate. A change measured across a gap happened somewhere inside
   it, and the row and the lead say so. Objects with under 10 set pairs are not judged by that rule; the two-set rule (`orbit-2.38`) marks their changes apart.

## GEO relocation tracker (`orbit-2.27`, 25 Nov 2026; ideas#248, calibrated by ideas#256)
Tom, 23 Nov 2026, after LUCH (OLYMP) 2 left 62 E: Orbit could say that it moved, not where it is now, what it will
pass or where it stops. Module `tools/geo_tracker.py` (standard library, build time, no request); calibration
`tools/geo_relocations.py` and `docs/validation/luch2-relocations.md` (Luch 2's full history, 2023-2026, read once).
On the GEO page from 24 Nov 2026 (section "Listed satellites on the move", `#movers`), in `globe.json`'s
`belt.movers` and in `data/geo/movers.json`, which the object pages read (item 10).
1. **Scope.** Objects with a listed role (`site_src/geo_roles.json`) that the belt board classes as drifting
   (|drift| 0.1 deg a day or more), from the element sets the GEO run already publishes. Low-inclination longitudes
   (`maneuver.geo_position`); neighbours are station-kept objects (inclination under 1 deg), where the same formula
   holds.
2. **Newest set and now.** Longitude, drift and height above or below GEO at the newest set's epoch, with its age at
   the build time. "Now" is the newest set coasted at its own rate and is always marked extrapolated. A newest set
   older than 3 days (`maneuver.STALE_DAYS`) gives no position now, no pass-by dates and no stop projection: the
   entry says how old the set is and nothing more. On 24 Nov 2026 that held back USA 270, USA 271 and USA 325
   (newest sets 9-22 days old).
3. **Departure.** The last stop in Orbit's own sets (item 6) and its last held set. The start of the move is
   estimated twice, both assuming it sped up uniformly from rest, each naming its sets: from the first moving set's
   distance and rate (t = 2d / v), and, with two moving sets speeding up, from their change in rate (t = v / a).
   Both are clamped to the last held set. Luch 2, 24 Nov 2026: held 61.98 E to 15 Oct 15:56Z; estimates
   19 Nov 13:32Z and 18:04Z. Its feed item keeps its id (`orbit:maneuver:55841:2026-10-15`, the set pair Orbit's
   rule measured); the estimate is a separate field.
4. **Two cases.** "At the last measured rate" (coast): the newest rate held. "Still speeding up": the rate change
   between the last two sets held until 4.5 deg a day (just above Luch 2's fastest, 4.42 in May 2023), then
   coasting; only with 3 moving sets whose rates rise in turn, so two sets give the coast case only. Neither case
   includes braking. On Luch 2's three long moves braking took 10.2-11.8 days from full speed to the stop, so once
   an object brakes, dates further along come later than shown; the note says so once at the top of the section,
   and each table has a one-line reminder (from `orbit-2.28`).
5. **Pass-by table.** Station-kept active objects ahead in the drift direction, grouped into slots 0.3 deg wide, to
   45 days at the coast rate and under one turn of the belt, at most 40 slots; a date for each case. Slots the coast
   case has already passed by the build time are counted, not listed. Dropped once a stop is projected.
6. **Stops.** Held: |drift| under 0.1 deg a day for 2 days or more; runs within 0.2 deg with a break of under
   7 days merge. Turnaround: the drift reverses between two sets both under 0.5 deg a day, outside a stop. Each stop
   lists the three nearest station-kept objects at its departure (now, for a current stop), each placed by its last
   set before then. Checked on Luch 2's 2023-2026 history: all nine stops in Marco Langbroek's published table,
   held stops within 0.07 deg and 2 days; the 62 E stop's nearest is INTELSAT 39 at 0.01 deg.
7. **Brake detection.** From the fastest moving set on, each set's drift is compared with a set at least 0.5 days
   earlier; a fall of 0.05 deg a day or more projects a stop at constant braking (lon + v^2 / 2b in the drift
   direction). A projection is shown only when steady: within 1 deg of the one before it, with no set between
   them that showed no fall. Shown with the station-kept objects within 2 deg of it, the sets it rests on, and the
   object's own record: on Luch 2's long moves steady projections came 7.6-8.6 days before arrival, off by
   0.5-4.6 deg, and in 2025 later ones fell about 2 deg short (a two-stage brake).
8. **What it never says:** why, where the object is going, which satellite it means to approach, or how likely
   anything is. Every figure is arithmetic on public element sets and says how many sets it rests on; the page says
   so in one line (`geo_tracker.NOTE`). Feed tier, item kind and ids are unchanged (Tom's call).
9. **Wording (Tom, 24 Nov 2026: "Yes, use the default"):** a table headed "At the last measured rate", the two
   cases named as in item 4, no likelihood words, the braking note and Luch 2's record of steady projections
   beside it; the estimated start shown on the GEO page and the object page, not in the feed id. A test holds the
   section free of likelihood words.
10. **Where it shows.** The GEO page: one card per mover, those with a current set first; the pass-by table in the
   shared ten-row window (`tic-fold.js`, loaded on the GEO page from this version); stops in a closed list. The
   object page: newest set, now, departure and estimated start, a steady stop projection, and a link to the GEO
   page. Built in the update run by `tools/geo_page.py` (`movers`); a failure there leaves the belt board as it was
   and says the section was not built.

## GEO movers: chart, summary and phone tables (`orbit-2.28`, 24 Nov 2026; ideas#321)

Page only: no new computation beyond the chart's set list, no feed change, and Tom's wording for the tracker (item 9
above) stands.
1. **Summary.** A row per mover at the top of "Listed satellites on the move": name (linking to its card,
   `#movers-<norad>`), now (extrapolated) or "no position" for a stale entry, drift, the newest set's age, and its
   state: moving east or west, braking seen, braking with a steady stop projection, or no public set for over
   3 days. On a phone the rows stack.
2. **One caveat.** The not-a-forecast note, the two cases, the braking note and the 3-day rule appear once, under
   the summary; each card keeps a one-line note on its own case, the slots passed or left out, and "No braking
   included".
3. **Chart.** For each mover with a current set, longitude against time: `geo_tracker` adds `track`, the sets from
   7 days before the last held set (or the last 30 days when Orbit's sets show no stop) to the newest, at most 160,
   thinned evenly. Dots are the sets, joined only where the sets are under 2 days apart; a gap of 2 days or more is
   shaded "no public set" (labelled when the label fits inside it); the estimated start of the move is a dotted
   line (a band between the two estimates). From the newest set, the newest rate is carried forward dashed to now
   (a ring, "now") and 7 days on; with a steady stop projection, a dashed level line at the projected stop instead.
   Station-kept satellites passed at that rate are ticks on the dashed line, the nearest at most 4 named. Longitudes
   are unwrapped across 180 deg; east is up; axis dates are UTC days. A label that would touch a mark, a line or
   another label is left out (Tom's figure rule: nothing touches); the table lists every slot. Drawn as SVG at
   the box's own width (redrawn on resize), so text stays 12 px on a phone; no inline styles.
4. **Times and owners in the pass-by table.** Each time is shown in the viewer's zone with the zone named, date and
   time on two lines on a phone; a tap swaps it with UTC and back. Owner codes carry CelesTrak's full name on hover,
   and a closed list under each table names every code in it. On a phone the "Degrees ahead" column is hidden (the
   longitude gives it).

## GEO movers: terms in place, open stop history, last 24 hours (`orbit-2.29`, 24 Nov 2026; ideas#322)

1. **Terms.** The caveat block says what an element set is; each card's height above or below geostationary
   altitude says why it drifts (higher: a longer orbit than the Earth's turn, so west; lower, east; about
   0.013 deg a day for each km, from d(lon)/dt = -1.5 (da/a) x 360 deg a day).
2. **From now.** Each pass-by table has a "From now" column, worked out in the viewer's browser from the coast date
   (hours under 2 days, else days; "passed" once the date has gone by).
3. **Stops shown open.** The stop history is a table under its own heading, with the rule for a stop stated.
4. **Last 24 hours.** `geo_tracker` adds `last_day`: the sets in the 24 hours before the build, the drift of the
   newest set before them, and the brake state as of 24 hours ago. The card says how many new public sets came,
   whether the drift changed (by 0.01 deg a day or more), and whether the brake state changed. From the element
   sets themselves; no stored copy of yesterday's page.

## GEO relocation feed items (`orbit-2.30`, 24 Nov 2026; ideas#323)

One feed item per move of a listed-role GEO object, updated in place.

1. **Identity.** `orbit:relocation:<norad>:<estimated start day>`, the same as `subject_id`. The day is the start
   estimated from the first moving set's distance and rate (`geo_tracker.start_estimates`), fixed once that set
   exists; the estimate from the rate change needs a second set and would move the id. A move needs a held stop
   in Orbit's own sets before it: with none, no item.
2. **Steps** (`steps`, each with the sets it rests on): `move_began` (the last held set and the first moving set;
   `last_change` `new` at the first moving set); `braking` (`braking seen`, or `steady` once the stop projection
   holds, which sets `last_change` `changed` at that set); `stopped` (drift under 0.1 deg a day for 2 days, the
   tracker's stop rule; `last_change` `ended` at the stop's first set, `event_end` that day). A stopped move stays
   in the feed for 7 days after its stop began (`geo_tracker.ARRIVED_DAYS`).
3. **Form.** `observation`, `routine`, `geometry` null (off COP's maps, like orbit changes), `event_start` the
   estimated day (`event_time_precision` day). The summary gives the departure longitude, the newest set's time,
   age and drift "at the last measured rate", and the tracker's note. It names no destination: no stop
   projection longitude and no neighbouring satellite. No likelihood words.
4. **Wiring.** The tracker runs after the feed is built, so `tools/geo_page.py` replaces the feed's relocation
   items with this run's (`orbit/feed.merge_relocations`) before the check step lints the feed. A failed tracker
   adds none. Whether a relocation earns a tier above routine is a separate contract question; listed-role objects
   only, nothing from the private watch list.

## GEO slot search and who held a slot (`orbit-2.31`, 25 Nov 2026; ideas#366)

1. **A slot query.** `orbit.py find`, the GEO page's search box and the object search read "12.5W", "12.5° W",
   "12.5 W", "12 West", "36E", "36 East" or signed degrees east ("-12.5", "+36") as a GEO slot
   (`orbit/namepos.parse_slot`; the page scripts carry the same two patterns, checked by a test). The whole query
   must be the slot, so "Intelsat 37e" or "Astra 2E" stay name searches; a bare number stays a NORAD number.
2. **There now.** Objects within 0.5° of the slot (`--window` on the CLI), short way round, so 179.5° E and
   179.5° W are 1° apart. The CLI reads each object's longitude at the GEO page's build time (`globe.json` column
   `lon`, from its newest set; no SGP4 in the CLI); the page uses the time shown. Each with its region and drift.
3. **Named for it.** Names that state a position within 1° of the slot (`TOLERANCE_DEG`; naming schemes as in
   `orbit/namepos.py`), with where the object is now. A name is not a position: most such names are former names.
   Names round the slot to the whole degree, so a whole-degree query says so.
4. **Held it.** `globe.json` `held`: payloads that held a longitude, from every element set Orbit holds (the GEO
   history starts 1 Jul 2026; at most about a year is read). One sample a day at 12:00 UTC from the set in force,
   skipped when that set is over 10 days old or drifts 0.1° a day or more; a stay is a run of such days no more
   than 3 days apart, each within 0.5° of its first day, 7 days or longer. A slot lists the stays whose mean
   longitude is within the window. Librating objects with slow drift can show short stays; payloads only.
5. **The object search** answers a slot query with a link to the GEO page rather than its own list: positions and
   stays are in the GEO page's data, with its time control, and the name rules stay in one place.

## Launch lanes retired (`orbit-2.32`, 25 Nov 2026; ideas#69)
Launch Library 2's schedule, the launch news, the launch ledger and the launch closure areas are the suite's Launch
program's (launch.theintelligence.company), which reads Launch Library 2 and the closure notices itself. Before the lanes retired, Orbit's and Launch's
readings of Launch Library 2 ran side by side for two days (19-21 Nov 2026) and matched: 23 comparison rows, none
with an unexplained difference.
1. **Retired lanes:** `upcoming`, `news`, `ledger`, `navwarn` and `pairs`, with their modules. A collect makes no
   request to Launch Library 2, the Spaceflight News API, NGA or Launch; the snapshot has none of their keys.
2. **Feed:** no `orbit:upcoming:*` items, and the health block no longer names `ll2-thespacedevs`. Launch's feed
   carries scheduled launches as `launch:upcoming:*` (LA-PIR-3); COP ends Orbit's old items when Orbit is read.
   OR-PIR-3 stays in the register, noted, so older items still resolve.
3. **Ledger:** Orbit's last `launch-ledger.json` stays on its release `ledger`, frozen, with a "moved to Launch"
   note in the release text; the private archive keeps its dated copies. `ledger.yml` has no schedule and does nothing
   when started; it remains while the suite's dispatcher still starts it.
4. **Launches page:** the map and globe draw GCAT's launches of the last 7 days (each with its payloads and their
   orbits, and their paths on the globe); pads, hazard areas, ledger history and Launch's lines are gone. A card
   under the old ids `#upcoming`, `#hazards` and `#ledger` points to Launch, so older links still land.
5. **Daily archive:** `navwarn` days to 25 Nov 2026 stay as they are; no new ones are added.
6. **Sources:** `ll2-thespacedevs`, `snapi-thespacedevs`, `nga-msi` and `tic-launch` are `excluded`, each noted
   `retired: orbit-2.32`. Orbit still reads GCAT's launch list, and Launch still reads Orbit's GCAT `launches`.

## Current and former names (`orbit-2.33`, 26 Nov 2026; ideas#376)

1. **Where it comes from.** An alias-file name entry may say `status: current` or `status: former`, a former name
   with `until`, the day it stopped being the name. The status is TIC's reading of the entry's evidence; an entry
   without one says nothing either way.
2. **Search index.** `search.json` (`tic-catalog-search/1`) gains `name_status`, {key: [[name, status, until]]},
   holding only marked names; readers that ignore it are unaffected. The object shards carry `status` and `until`
   on the alias file's name records.
3. **Where it shows.** `orbit.py find` (name and slot queries), the object page's names table, and the GEO page:
   the "Names that state another position" table, the object card and the slot search list (`globe.json`
   `name_positions` columns `status` and `until`). Names match loosely (`namepos.compact`), so another source's
   spelling of the same name takes the mark. A name without a status shows as before.

## The current declared name beside the catalogue name (`orbit-2.34`, 26 Nov 2026; ideas#379)

1. **Rule.** The display name stays the ranked source's (Space-Track first); keys and joins are unchanged. When the
   alias file declares the object's current name (basis `declared`, status `current`) and it differs from the
   display name, it shows beside it as "now <name>". Example: 33459 reads "EUTE HOT BIRD 13C (HB 9) now Eutelsat 50
   West A".
2. **Data.** `search.json` (`tic-catalog-search/1`) gains `now_names`, {key: name}; `globe.json` carries the same
   for the GEO objects. Readers that ignore them are unaffected.
3. **Where it shows.** The object page heading, the site search results, and the GEO page's object card, search
   list and slot search list. A former name, an attributed name or no alias entry shows nothing new.

## Name swaps from the alias file, Prowler, and "PAYLOAD x" placeholders (`orbit-2.35`, 26 Nov 2026)

1. **Swap entries.** The alias file can record that sources give one payload name to different numbers: a `swap`
   entry names the disputed name and gives each source's claim (source, date read, NORAD number, the source's own
   spelling). It joins the name swaps the build finds by itself and shows on each object's page under "Name swaps".
   Nothing is reassigned; feeds and keys keep each source's numbers. First entries: Cosmos 2536, 2537 and 2538
   (44422-44424), which GCAT names one place over from Space-Track and CelesTrak.
2. **Prowler.** SWF's RPO row "Prowler" (1990-1998) links to GCAT's unnumbered object A04907 (1990-097E, launched
   1990-11-15 on STS-38, GEO), the piece Wikidata's Prowler item also gives. The NORAD number on that Wikidata item,
   20963, is USA 67 (1990-097B) in GCAT, Space-Track and CelesTrak, so it is not used.
3. **Placeholders.** Space-Track's "PAYLOAD A" to "PAYLOAD C" (for example SJ-15, 39210) are treated like
   "OBJECT A": shown, with the best-ranked real name beside them ("PAYLOAD C (Shi Jian 15)"), and not used to find
   name swaps.

## GEO uploads never lose what the releases hold (`orbit-2.36`, 26 Nov 2026)

Each GEO run (workflow `geo.yml`, `python tools/orbit.py geo --upload`) downloads the files it extends from the
public releases `geo-YYYY`, adds the day's element sets and replaces them. Until this version, a failed download
was treated as a missing file, so the month file was rebuilt from that one reply's sets and uploaded over the
release's copy (reproduced offline: 300 sets to 5). No loss had happened. The run now stops, exit 1 with nothing
uploaded, when:

1. **A file the release holds does not download whole:** an error, or a size other than the release lists. Absence
   is read from the release's own file list; a list that cannot be read stops the run too.
2. **A month's file is missing from its release when the month cannot be new.** A month file is started only in its
   own month (or later), never rebuilt for a month that has passed. From `orbit-2.41` (27 Nov 2026), a missing file
   of the current month stops the run too when the release holds a day file (`YYYY-MM-DD.geo-region.json`) of that
   month: the run that wrote that day file also wrote the month's element sets, so the file was there and has gone.
   Two ways there: `gh release upload --clobber` removes the old file before it uploads the new one, so an upload
   that fails in between leaves the release without the file; or a file removed by hand. Before this, the next run
   took the month as new and rebuilt it from its one reply (reproduced offline: November's 180 sets to 55, exit 0,
   nothing archived because nothing was replaced). The run's message points to the private archive's copies (lanes
   `geo-release` and `geo-reply`), from which a person restores the file before the next run. A month's first run,
   with no day file of the month on the release yet, still starts its file.
3. **An upload would drop an element set.** Before uploading, the release's copy is downloaded again, and a month
   file that would lose any (NORAD number, epoch) the release holds is refused.
4. **The private archive copy fails.** Each gp reply goes to the private repository `metacog-osint/tic-archive`
   (`tools/tic_archive.py`, lane `geo-reply`) right after the query, so a stopped run's sets are kept. Every release
   file is copied there (lane `geo-release`) before it is replaced: dated snapshots, nothing replaced in the
   archive. The raw replies stay private, as the update run's do.

`tools/geo_import.py` (the one-off import from Noisefloor) passes no archive, so a re-run cannot replace a file
the release holds. Tests: `tests/test_geo_region.py`, classes `ReleaseGuard` and `ArchiveCopy`.

## GEO two-set rule (`orbit-2.38`, 26 Nov 2026; ideas#252)
Orbit's rule ("Orbit changes in watched objects") judges an object against its own noise and needs 10 pairs of
sets. An object with fewer public sets could move along the belt unmarked: USA 324 stopped drifting inside a
24-day gap between its third and fourth sets. The belt board (`tools/geo_belt.py`, `globe.json`'s `belt.two_set`)
now runs a second rule on those objects only.
1. **Scope:** the objects the belt board lists as not judged (under 10 pairs), each pair of consecutive sets ending
   in the last 30 days. Listed apart from the board's orbit changes and never merged with them, so a reader cannot
   take a two-set mark for a change measured against the object's own noise. On the history from 1 Jul 2026,
   Orbit's rule listed every change the two-set rule found on objects it judges (280 of 280).
2. **What natural drift alone explains:** Earth's triaxiality accelerates an uncontrolled GEO object's drift by
   up to about 0.0017 deg a day² (`A_NAT`; Soop, *Handbook of Geostationary Orbits*, 1994). Over a gap of `t` days
   that changes the drift by up to `A_NAT x t`. With a constant acceleration the mean longitude follows the mean of
   the two drifts times the gap exactly; the rule allows `A_NAT x t² / 2` off that path for an acceleration that
   changes along the way.
3. **Tests** (drift from mean motion, as the board's classes; mean longitude = RAAN + argument of perigee + mean
   anomaly - GMST at each epoch):
   - drift: the drift changed by 0.088 deg a day (Orbit's 0.25 m/s GEO floor; 0.352 deg a day per m/s) plus
     `A_NAT x t`;
   - class: the object crossed 0.1 deg a day (held to drifting, or back) with a drift change of 0.02 deg a day
     plus `A_NAT x t`;
   - longitude: the second set's mean longitude is 0.5 deg plus `A_NAT x t² / 2` or more off the mean-of-drifts
     path from the first. This catches a move that started and stopped inside the gap, with both sets held.
   Any one test marks the pair. The mark carries the two epochs, the gap in hours, both drifts and longitudes,
   the natural path's longitude, the tests met and the allowances used, and a kind: started drifting, stopped
   drifting, drift rate changed, moved inside the gap, or drift changed with the object held either side.
4. **Limits:** two sets say that something changed between them, not when or how; the change can sit anywhere in
   the gap, and the mark carries the gap. A single set with a poor fit can mark a change and its return. A steady
   drift with no change (USA 325, 24.6 days) is not marked; the object stays in the drifting list. Never says why
   an object moved.
5. **Checks** (`docs/validation/geo-two-set.md`): 208,793 pairs of the 554 active objects, 1 Jul-26 Nov 2026,
   291 marked. On objects not judged at the time: USA 324's stop (found) and 10 marks in the first 8 days of the
   history, when every object had few sets. Luch (Olymp) 2's start across its 37-day gap is found by both rules
   from the same 21 Nov set. The page does not draw `belt.two_set` yet; the data is in `globe.json`.

## Gaps in public element sets (`orbit-2.40`, 27 Nov 2026)
Space-Track's public data holds element sets for some listed-role GEO satellites days or weeks apart. Luch (Olymp) 2
had none from 15 Oct to 21 Nov 2026 (37 days): the day files' "quiet" event of 22 Oct recorded the start, the GEO
page showed nothing, and when its sets came back it had left 62 E. Module `tools/geo_gaps.py` (standard library,
build time, no request), called by `tools/geo_page.py` into `globe.json`'s `set_gaps`; GEO page section "Listed
satellites with no recent public set" (`#set-gaps`); one line in the daily lead.
1. **Scope.** The objects with a listed role (`site_src/geo_roles.json`), in any region, whether or not CelesTrak
   lists them as active. The day files' "quiet" event covers active payloads in the zone only: USA 271 (in the
   graveyard) and SJ-21 and SJ-25 (crossing the zone) are outside it.
2. **Listed.** An object whose newest set in Orbit's files is 7 days old or more at the page's build time
   (`geo_region.QUIET_DAYS`, the age the "quiet" event uses), with the set's epoch, its age, the longitude and drift
   it gives (low-inclination formula, as the tracker), the day of the GEO run whose day file first carried it, and
   the object's earlier gaps of 7 days or more between consecutive sets in Orbit's files (how many, the longest).
   Every listed-role object's newest set is in a closed list below.
3. **A set again.** Each day file's newest epoch for the object is compared with the day file before it. A newer
   set counts when the newest set before it was 7 days old or more at the new file's read time (`fetched_utc`):
   when the list in item 2 would have held the object just before. That includes every gap of 7 days or more
   between two epochs, and also a set that reached Orbit's files late: MEV-1's set of 22 Nov 2026 23:29Z was first
   read on 24 Nov at 23:57Z, after its set of 16 Nov 18:43Z had passed 7 days old there; the two epochs are 6.2
   days apart, so the entry is marked `late`. The pair shown is the widest between consecutive sets from that
   newest set to the new file's. Listed for 30 days after the read. The day files imported from Noisefloor (to
   26 Oct 2026) hold no read time; there only sets 7 days or more apart count.
4. **Daily lead.** One line (kind `geo_sets`, after the notable lines, linked to `geo.html#set-gaps`) when, in the
   24 hours before the lead's time, a listed object's newest set passed 7 days old, or a set again (item 3) was
   first read; at most 3 names in each part, and the read time of Orbit's GEO files. The collect writes the lead
   before the update run downloads the GEO release, so the GEO page's build adds the line to the site's
   `snapshot.json` and to the day's lead in the daily archive (`data/state/daily_archive.json` and the site's
   copy) when that lead is this run's. Until then the lead carries a line saying the check was not made, which
   stays if the GEO step fails. GEO files read more than 36 hours before the lead give a line saying how old they
   are instead.
5. **Wording.** About the source, never the satellite: "no public set", never quiet, inactive or holding its slot,
   and never why no set was published. No public set is not the same as no movement. Across their gaps in Orbit's
   files, USA 325's longitude went from 154.76 E to 138.69 E (24.6 days), USA 324's from 108.54 E to 121.36 E
   (24.1 days), SJ-17's from 45.68 E to 34.96 E (7.2 days) and Luch 2's from 62.00 E to 60.29 E (37 days). A test
   holds the section, its note and the lead line free of "quiet", "inactive", "dormant" and likelihood words.
6. **Checks** (`tests/test_geo_gaps.py`; fixture `geo_set_gaps_2026.json`, the ten listed objects' sets
   1 Jul-26 Nov 2026 and their day-file entries from 1 Oct). Day file of 22 Oct: Luch 2 (newest set 15 Oct 15:56Z)
   and SJ-25 (15 Oct 18:06Z) pass 7 days that day and are the lead's names; the day file's own "quiet" event has
   Luch 2 only. Day file of 21 Nov (read 20:57Z): both come back after 37 days. Day file of 22 Nov: USA 324 and USA
   325 pass 7 days, as that file's "quiet" events also record. At 03:00Z on 27 Nov 2026, three are listed: USA 270
   (newest set 24.8 days old), USA 271 (24.6) and USA 325 (11.7).
## The GEO role list: claim and status (`orbit-2.45`, 27 Nov 2026)
`site_src/geo_roles.json` holds 20 objects (`docs/validation/geo-board.md`). Each entry carries, besides its role,
basis and sources, a `claim` (`declared`: the operator's or the state's own description; `attributed`: an
assessment by analysts, tracking firms or another government, named in the basis), a `status` (`active`,
`retired` or `uncertain`), a `status_date` (YYYY-MM or YYYY-MM-DD: the date of the newest source behind the status)
and a `status_note` saying who reports it. `uncertain` means no recent report was found, and the date is that of
the newest source. The GEO page shows the claim and the status in the role table and on the object card.
`check_roles` (`orbit/notable.py`) refuses an entry without a source as [label, https URL], a claim, a status,
a status date (not after today) or a note; `orbit.py check` runs it and `tests/test_geo_roles.py` holds it. The
status is the sources' word, never Orbit's reading of the element sets, except where the note says Orbit measured it.
## The GEO role list: sources that were opened (`orbit-2.48`, 27 Nov 2026)
Every entry in `site_src/geo_roles.json` rests on a source that was opened and says what the basis says. A source
the list cites but could not open (a paywall, an HTTP 403 to scripts) is written `[label, URL, "not opened"]`; the
page adds "(not opened)" to its label. An entry none of whose sources was opened is refused by `check_roles`
(`orbit/notable.py`, run by `orbit.py check` and held by `tests/test_geo_role_sources.py`) and, should one reach
the file, is left off the page and out of the notable rule. A role is never listed on a source nobody read.
SJ-17 (41838): its earlier basis cited a SpacePolicyOnline article (5 Feb 2022) that covers SJ-21 and never names
SJ-17. The basis now rests on SWF's fact sheet "Chinese Military and Intelligence Rendezvous and Proximity
Operations" (June 2026): China declared the satellite a test of advanced technologies; SWF reports it circumnavigated
ChinaSat-5A in Nov 2016, came within 1.5 km of ChinaSat-1C on 29 Jul 2018, and made RPO with ChinaSat-6B and
Shijian-20 in 2020. The Space Review (Matthew Mowthorpe and Markos Trichas, 1 Aug 2022) and Defense One (David D.
Chen and Peter W. Singer, 20 May 2024) report the same approaches.

## Names registered with the United Nations (`orbit-2.50`, 27 Nov 2026)
Source: the UN Register of Objects Launched into Outer Space, read through UNOOSA's Online Index
(`orbit/unregister.py`). The UN's terms permit personal, non-commercial use and bar redistributing or compiling the
Index, so Orbit publishes no register table and imports nothing in bulk.

1. **Requests.** On a person's request only: one request per COSPAR id, at most 10 ids a call, 3 s apart. Replies are
   kept a week in git-ignored `data/raw/unoosa/` and never published.
2. **Declared name.** Only the Index's registered-name field counts, without square brackets, on a record marked
   registered that carries a registration document. A name from the Index's other name field (information it did not
   receive as a registration) is never a declared name. The official mark on the international designator concerns the
   designator, not the name. The GSO location is kept only when marked official.
3. **Review.** A person adds each entry to `orbit/data/catalog/un-register.yml` with `reviewed_by` and `reviewed`.
   Only reviewed entries are written to `data/un-register.json`; a bad entry stops the build.
4. **Display.** Object pages join on the COSPAR id and show the name as declared by the state of registry to the UN
   Register, with the document symbol, a link to the document and the date read. It is the name at registration, never
   shown as the current name, and it changes no catalog name or number.
