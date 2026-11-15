# Moving Noisefloor's GEO belt into Orbit: plan

Drafted 15 Nov 2026 after Tom's "yes, plan on moving it and keeping sun outages in noisefloor". Nothing here is
built. Each step needs Tom's yes before it is built, and its own yes to commit, push and deploy, in each repo.

## Why
The GEO belt is space domain awareness: who sits where in the geostationary belt, who moved, who parked beside
whom. That is Orbit's scope (`_ideas/new-programs.md`: catalog changes, launches, manoeuvres, counterspace).
Noisefloor's job is GPS and PNT interference. Two more reasons:
- Orbit's orbit-change lane watches GEO objects (USA 270 and USA 271 among them) with its own rules, and
  Noisefloor's callout C5 marks orbit changes of listed objects with different thresholds. Two TIC sites can
  publish different answers about the same satellite.
- Both repos log in to one Space-Track account (Tom, 15 Nov 2026). GP once an hour is the account's limit. Today
  Orbit checks Noisefloor's runs before its GP query (`orbit-2.8`), but Noisefloor does not check Orbit's.
  One collector in one repo ends that.

## What moves and what stays
| Noisefloor piece | Lines | What it does | Plan |
|---|---|---|---|
| `tools/geo_region.py` | 525 | One Space-Track GP query a day for the GEO region (mean motion 0.9-1.1, e < 0.3); membership events (arrived, left up, left down, went quiet); held `gp_history`; day files and monthly element parquet on `pnt-data-YYYY-MM` releases | Moves (step 2) |
| `tools/geo_callouts.py` | 619 | Pre-registered callouts C1-C8, scored on cases A1-A4 and others (`docs/validation/geo-callouts.md`) | Moves with its validation record unchanged (step 3) |
| `tools/geo.py` | 333 | The older GEO board from CelesTrak's active-GEO group | Retires once the Space-Track region covers it (step 5) |
| `tools/geo_globe.py`, `site_src/globe.js`, `geo.js`, `geo.html` | 195 + 1,312 + 142 + 98 | The /geo page: three.js globe, belt strip, look angles, relative motion, closest objects, callouts | Moves (step 4) |
| `site_src/geo_roles.json`, `satcat_owners.json` | | Listed roles and owner names | Move with the page |
| `tools/sun_transit.py`, `sun.html`, `sun.js`, `sunoutage.js` | | Sun outages: when the sun sits behind a GEO satellite for a receiver | **Stay in Noisefloor** (Tom). They use a nominal GEO radius and slot longitude, not the GEO data, so nothing they need moves. The /geo page also loads `sunoutage.js` for its look-angle panel: Orbit takes a copy |
| `tools/board.py` `geo_card` | | Noisefloor's home-page status board shows a GEO card from `site/data/geo.json` | Drops the card, or links to Orbit, at step 5 |
| `tools/sentinel_gnss.py` (`import geo_region as G`) | | Uses geo_region's Space-Track client for Sentinel `gp_history` reads | **Stays in Noisefloor**: it needs its own copy of the client before `geo_region.py` leaves, and its `gp_history` reads still use the shared account (no hourly GP limit, but the 30 a minute and 300 an hour totals are shared) |
| Registry rows `space-track`, `celestrak`, footprint rows (`satbeams`, `operator-coverage`, `fcc-space-filings`, `itu-space-filings`) | | Licences and terms already checked | Copied into `doctrine/sources.json` with their checks and dates |

## Steps
0. **Now, before the move (small, Noisefloor):** `geo_region.py pull` reads Orbit's last GP time from the public
   snapshot (`orbit.theintelligence.company/data/snapshot.json`, `maneuvers.read_at`) and skips its query within
   the hour, as Orbit already does the other way. About 15 lines and a test. This closes the shared-account gap
   until step 2 lands.
1. **Decide the open questions below** (Tom).
2. **Collector in Orbit:** lane `geo` (`orbit/geo_region.py`), standard library only, through Orbit's Space-Track
   client: one GP query a run for the GEO region and the watch list together where Space-Track allows it, else two
   queries spaced inside the run, never two runs inside the hour. The history Noisefloor already holds is read
   once from its public releases (no new Space-Track requests). Then Noisefloor's step "GEO region (Space-Track)"
   is switched off in the same change window, so only one repo queries.
3. **Callouts in Orbit:** C1-C8 ported with their pre-registered rules and scoring unchanged, and rerun on the
   same cases to show the same results before anything is published. Orbit's C5 and its own orbit-change lane are
   then compared object by object on the GEO watch list; where they disagree, Tom picks one rule.
4. **The page in Orbit:** the globe and belt strip as Orbit's GEO page, three.js and satellite.js self-hosted like
   MapLibre (Orbit's CSP has no CDN scripts). Feed items for callouts only with Tom's yes, held from joins by
   COP's gate like orbit changes.
5. **Noisefloor's Space tab:** points to Orbit's GEO page once it is live and checked; Sun outages stays as the
   tab's own page. Then `geo.py`, the GEO steps in `daily.yml` and the old page retire, and the hub's and COP's
   descriptions of both programs are updated.

## Open questions for Tom
1. **3D:** port Noisefloor's three.js globe as is (built and checked), or rebuild it in Cesium as part of Orbit's
   planned 3D page? Recommended: port it as is now, and fold it into the Cesium page when that is built for ground
   tracks.
2. **Storage:** Noisefloor publishes the GEO element sets and day files on its public `pnt-data` releases. Orbit
   is private and keeps state in its Actions cache (evicted after 7 days unused, 10 GB a repo). Options: releases
   on Orbit's own repo (private), or keep publishing to Noisefloor's releases from Orbit. Recommended: Orbit's own
   releases, with the element sets kept private as Orbit does now ("raw element sets are not republished").
3. **Dependencies:** `geo_callouts.py` uses numpy and sgp4, and the monthly element files are parquet (pyarrow).
   Orbit's live lanes are standard library only. Options: callouts run at build time with those packages pinned,
   or rewritten to the standard library (SGP4 in pure Python is slower but small at GEO's few thousand objects).
4. **Which rule wins for GEO orbit changes:** Orbit's (8 robust deviations of the object's own noise, 0.25 m/s
   floor) or Noisefloor's C5 (drift 0.02 deg/day, inclination 0.02 deg, or 0.15 deg longitude off prediction).
   Decided after step 3's comparison.
