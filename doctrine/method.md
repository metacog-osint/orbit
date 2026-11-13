# Orbit method (`orbit-2.1`, 13 Nov 2026)

## Purpose
The space layer of the suite: what changed in Earth orbit. Planned scope (`_ideas/new-programs.md`, program row
and roadmap step 14): catalog changes, launches, manoeuvres and counterspace events. `orbit-2.0` was the first
live slice: launches, scheduled launches, reentries and catalog changes. Manoeuvres and counterspace events are
not built.

Every item is an **observation** (measured or reported, no judgment) at tier **routine**. Orbit has no
baseline of its own readings yet, so nothing is called an anomaly, and it makes no warnings.

## Lanes

| Lane | Source | What Orbit takes |
|---|---|---|
| `catalog` | GCAT (J. McDowell, planet4589.org/space/gcat), CC BY 4.0: `satcat`, `satcat100k`, `auxcat`, `tmpcat`, `launch`, `sites`, `orgs` | Orbital launches in the last 30 days (feed: 7), reentries dated in the last 30 days (feed: 7), catalog changes between two readings, owner-code counts |
| `upcoming` | Launch Library 2 (The Space Devs), detailed mode | Launches scheduled in the next 14 days, with the provider's country |

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

## Not live: manoeuvres
`orbit/maneuver.py` (from the 1 Nov seed build) is not run. It differences consecutive element sets with a
0.35 m/s threshold, which drag and fit noise exceed in low orbit, and its confidence is a formula, not a
calibration. Before any manoeuvre lane:
1. Run maneuver-detect (MIT, astro-tools, v0.3.0 on PyPI; depends on PyTorch) on a known case: SJ-21 moving the
   dead BeiDou-2 G2 to a graveyard orbit, January 2022. Local only.
2. Settle the history source. Space-Track's terms are reported (maneuver-detect's README) to bar redistributing
   data or derived analysis; not yet read by Orbit. The alternative is an archive Orbit builds itself, from a
   source whose terms allow republishing derived results (CelesTrak: not yet checked).
3. Keep the watch list in private config.

## Not built
Counterspace events (Secure World Foundation's counterspace reports), ITU Space Explorer filings, an optional 3D
page (Cesium ion decision), a scheduled workflow, deploy, DNS, the hub and COP entries.
