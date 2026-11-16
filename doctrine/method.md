# Orbit method (`orbit-2.11`, 16 Nov 2026)

## Purpose
The space layer of the suite: what changed in Earth orbit. Planned scope (`_ideas/new-programs.md`, program row
and roadmap step 14): catalog changes, launches, manoeuvres and counterspace events. `orbit-2.0` was the first
live slice: launches, scheduled launches, reentries and catalog changes. Launch hazard warnings (`orbit-2.2`), ASAT
test history (`orbit-2.3`), orbit changes in watched objects (`orbit-2.4`) and news headlines for scheduled
launches (`orbit-2.5`) followed; `orbit-2.6` splits orbit changes that disagree, and `orbit-2.7` adds SWF's
rendezvous and proximity operations history. `orbit-2.8` lists low-orbit plane and shape changes only from 1 m/s,
waits for Noisefloor's share of the Space-Track account, and adds baselines from GCAT's history. `orbit-2.9` adds
the launch ledger; `orbit-2.10` adds each payload's orbit from GCAT, Launch's place check on Orbit's hazard areas,
and the ledger's history and GCAT gap on the page; `orbit-2.11` starts Orbit's own daily archive.

Every item is an **observation** (measured or reported, no judgment) at tier **routine**. The GCAT baselines are
shown on the page only; Orbit has no baseline of its own readings yet, so no feed item is called an anomaly, and it
makes no warnings.

## Lanes

| Lane | Source | What Orbit takes |
|---|---|---|
| `catalog` | GCAT (J. McDowell, planet4589.org/space/gcat), CC BY 4.0: `satcat`, `satcat100k`, `auxcat`, `tmpcat`, `launch`, `sites`, `orgs` | Orbital launches in the last 30 days (feed: 7), reentries dated in the last 30 days (feed: 7), catalog changes between two readings, owner-code counts |
| `upcoming` | Launch Library 2 (The Space Devs), detailed mode | Launches scheduled in the next 14 days, with the provider's country |
| `ledger` (`orbit-2.9`) | Orbit's launch ledger from Launch Library 2, on Orbit's public release | Every launch since 1 Jan 2024, checked hourly; the launches GCAT hasn't listed yet |
| `pairs` (`orbit-2.10`) | The suite's Launch program (launch.theintelligence.company), its published snapshot | Launch's place check on Orbit's own hazard areas and scheduled launches: time and place, grouped, or time only, with azimuth, distance and implied inclination |
| `navwarn` (`orbit-2.2`) | NGA Maritime Safety Information, in-force daily memoranda (HYDROPAC, HYDROLANT, HYDROARC, NAVAREA IV, NAVAREA XII). Japan Coast Guard NAVAREA XI not read since 14 Nov 2026 (robots.txt) | Navigational warnings in force that name rocket launching, space debris or reentry: areas, windows, cancel times |
| `counterspace` (`orbit-2.3`) | Secure World Foundation, "History of ASAT Testing in Space" sheet (Global Counterspace Capabilities 2026, CC BY-NC 4.0), CSV export | Every anti-satellite test in space SWF lists since 1959, with debris created, re-entered and still on orbit; tests new since Orbit's last reading |
| `rpo` (`orbit-2.7`) | Secure World Foundation, "History of Robotic Rendezvous and Proximity Operations in Space" sheet (same report, CC BY-NC 4.0), CSV export of three data tabs and the About tab | Every rendezvous and proximity operation SWF lists (Commercial/Civil, Military/Intelligence, Planned), in SWF's words, with Orbit's reading of each date and GCAT matches |

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
   last reading and says why on the lane; if GitHub cannot be read it waits too. Noisefloor does not yet check
   Orbit's query (see `geo-move-plan.md`).
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

## Orbit's own daily archive (`orbit-2.11`, 16 Nov 2026)
Decision 8's second half (Tom, 15 Nov 2026). Each run adds itself to one entry per UTC day (`orbit/archive.py`,
schema `orbit-archive/1`), the newest 800 days kept:
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

## Not built
ITU filings (BR IFIC, after ITU's legal office answers),
an optional 3D page (Cesium ion decision).
