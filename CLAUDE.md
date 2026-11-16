# Orbit (`D:\Projects\orbit`)

The space layer of The Intelligence Company (`tic-feed/2`, program id `orbit`, prefix `OR`): orbital launches,
scheduled launches, reentries and satellite catalog changes. Observations only: no probabilities, no warnings.

**State, 16 Nov 2026, about 10 AM CST: live with `1d6e6ce` (method `orbit-2.11`), pushed on Tom's "Push both"
about 9:21 AM CST; update run 43895370439 passed.** Another session's `3100c21` (warning times) followed it.
Checked live 15:21-15:45 UTC 16 Nov: `#globe` loads Cesium ion (Bing) tiles in headless Edge and draws paths for
the 2 listed orbit changes from real Space-Track sets; `/data/archive.json` holds its first day; lane `pairs` ok
(11 time rows, none time-and-place yet). The hub's `tic-dispatch` (`ac2ac70`, deployed by run 43895428381) started
`ledger.yml` at 15:45 UTC (run 43899801160: 1 request, 13 added, 40 launches to 29 Feb 2024). Not seen yet:
payload `inc` and the launch card with orbits. The catalog lane carries the 15 Nov GCAT reading, built before
orbit-2.10, so they appear on the first run after GCAT republishes (satcat still 15 Nov 10:19 GMT at 15:57 UTC
16 Nov). Once `inc` is live, tell session "Launch mapper features 5-7". Emails to The Space Devs, ITU and the
Japan Coast Guard: still not sent (Tom, 16 Nov).

**State, 15 Nov 2026, about 7 PM CST: live at https://orbit.theintelligence.company with `8740711` (method
`orbit-2.8`), deployed by the new repo's first run 43768395830 (workflow_dispatch, passed 22:17 UTC 15 Nov, every
lane ok).** `orbit-2.8`, approved by Tom 15 Nov: swf-rpo regraded B2 ("I trust SWF"); low-orbit plane and shape
changes listed only from 1 m/s, with the semi-major-axis velocity beside each total; a wait for Noisefloor's GP
query on the shared Space-Track account (Tom: "they use the same account"); baselines from GCAT's history (card
`#baseline`); and `doctrine/geo-move-plan.md` for moving Noisefloor's GEO belt into Orbit, sun outages staying in
Noisefloor (plan only, nothing built).
**Repo swap, 15 Nov 2026:** the old repository is now `metacog-osint/orbit-archive`; `metacog-osint/orbit` is a
scrubbed copy with new shas (`8740711` holds the old `c899c2f`'s content). Every sha in these notes from before
`8740711` (`c9f3b9c`, `f9e81d7`, `32bbf31`, `c899c2f`, `84190bb`, `aa932dc` and the rest) exists only in
orbit-archive. Never push anything built on the old history. The new repo has secrets `SPACETRACK_IDENTITY`,
`SPACETRACK_PASSWORD`, `ORBIT_WATCH`, `CLOUDFLARE_PAGES_TOKEN` and variables `CLOUDFLARE_ACCOUNT_ID`,
`CESIUM_ION_TOKEN` (names checked, set by Tom), and Tom added it to the hub's `tic-dispatch` token about 4:40 PM CST
15 Nov. Emails to The Space Devs, ITU and the Japan Coast Guard: not sent as of 15 Nov (none in metacog@'s mail at
7 PM CST). Seven lanes (method `orbit-2.8` from 15 Nov 2026): `catalog` (GCAT), `upcoming` (Launch Library 2), `news`
(Spaceflight News API headlines, links only), `navwarn`
(NGA memoranda, API first), `counterspace` (SWF ASAT sheet), `rpo` (SWF RPO sheet), `maneuver` (Space-Track, published with Tom's approved
disclaimer). Orbit's feed carries GCAT and Launch Library 2 items and, from 15 Nov 2026 (Tom's "Yes, add them"),
the listed orbit changes (kind `maneuver`, off the map), which COP's gate holds from joins as military context. COP shows NGA's launch, debris and reentry
warnings under "Spectrum and space" from Cordon's copies, not Orbit's (COP `1a6c577`, live 14 Nov). The hub's
`tic-dispatch` starts Orbit at :55 past 00/06/12/18 UTC; on the new repo its first dispatched run was 43783187349
(00:55 UTC 16 Nov, passed in 1m25s, catalog unchanged because GCAT had not republished, every other lane ok), so
the token's access to the new repo works. Orbit's own cron (:41 every 6 h) is the fallback; its 00:41 UTC 16 Nov
start had not fired by 00:57 (GitHub runs schedules late).

Go-live record, 13 Nov 2026: first live slice and deploy workflow merged into `main` and pushed (`84190bb`, a
fast-forward, on Tom's "merge and push", 3:25 PM CST). First GitHub run (43510613951) passed: tests, both lanes
ok on GitHub's runners, check PASS, state saved to the Actions cache (1.34 MiB), deploy skipped because the
Cloudflare secrets were not yet set.
**Deployed 13 Nov:** Pages project `orbit` at **https://orbit-q2t.pages.dev** (created by Tom; his first manual
deploy ran from the Headwind folder and briefly put Headwind's site there). Tom set `CLOUDFLARE_PAGES_TOKEN` and
variable `CLOUDFLARE_ACCOUNT_ID`; run 43512732788 (3:40 PM CST) deployed Orbit, and every run now deploys.
Custom domain `orbit.theintelligence.company`: added through the Pages API and Squarespace `CNAME orbit ->
orbit-q2t.pages.dev` (4 hrs, after Tom's Google re-verification), about 3:55 PM CST;
**active with HTTPS and HSTS since 3:57 PM CST** (https://orbit.theintelligence.company checked: 200, Orbit's page). **Listed across the suite 13 Nov** (Tom's "approve, push and deploy"): house bar `tic-nav.js` v1.9 (`Space ·
orbital activity`, beta; Orbit's copy `aa932dc`), hub listing and `tic-dispatch` start at :55 past 00/06/12/18 UTC
(hub `c70271c`, `5cfa03a`), registry kit 0.4.8 (tic-doctrine `895fcf1`), COP layer (`a7c80ec`, open list
`3788906`; COP shows Orbit fresh, 21 items, 20 on the map). The `tic-dispatch` token's access to `orbit` was
added by 14 Nov (dispatched runs since 06:55 UTC). Untracked and to stay that way: `GEMINI.md` and `data/`; `site/`
changes stay unstaged (other sessions build there).

**Planned scope** (`D:\Projects\_ideas\new-programs.md`, program row and roadmap step 14): catalog changes,
launches, manoeuvres, counterspace events; maneuver-detect, Secure World Foundation counterspace sheets, ITU
Space Explorer, optional 3D page. Built: launches, scheduled launches, reentries, catalog changes, owner-code
counts, ASAT test history, orbit changes in watched satellites (Space-Track, 14 Nov 2026). Not built: ITU. 3D globe live 16 Nov 2026 (`orbit-2.11`). Describe Orbit publicly from what is live.

## Commands
```bash
python tools/orbit.py collect              # every live lane into data/snapshot.json
python tools/orbit.py collect --only upcoming
python tools/orbit.py collect --force      # read GCAT even if unchanged
python tools/orbit.py build                # site/ from data/snapshot.json (refuses without one)
python tools/orbit.py check                # registers + feed lint
python -m unittest discover -s tests       # offline tests (76 on 15 Nov), real fixtures from 13 Nov (manoeuvre tests synthetic)
python tools/serve.py                      # http://127.0.0.1:8761 with _headers (CSP); launch config "orbit-site"
```

## Lanes (method `orbit-2.7`; details in `doctrine/method.md`)
`counterspace` and `maneuver` are described in their own sections below.
| Lane | Module | Source | Measured 13 Nov 2026, about 12:40 PM CST |
|---|---|---|---|
| `catalog` | `gcat.py` | GCAT, CC BY 4.0: `satcat`, `satcat100k`, `auxcat`, `tmpcat`, `launch`, `sites`, `orgs` (about 38 MB) | 83,476 objects across the four catalogs; 22 orbital launches in 30 days; 85 reentries in 30 days; 36,289 objects in orbit (RU 3,919, SU 3,029); 780 in orbit with no catalog number; 0 catalog numbers claimed twice in the US catalogs. First reading, so no changes yet |
| `upcoming` | `launches.py` | Launch Library 2, detailed mode (about 450 KB; only it carries provider countries), one request a run (free limit 15 an hour) | 14 launches in the next 14 days |
| `pairs` | `launchpairs.py` | Launch's published snapshot (the suite's own program), one request: its place check on Orbit's areas | 16 Nov 2026: 14 rows, 11 launch-area pairs, all time only |
| `ledger` | `ledger.py` | Orbit's own launch ledger, read back from its public release (one GitHub request, no LL2 request); written hourly by `ledger.yml` | Not run yet (built 16 Nov 2026) |
| `navwarn` | `navwarn.py` | NGA daily in-force memoranda (5 text files, about 140 KB) and NAVAREA XI (Japan Coast Guard: list XML plus one page per launch-related warning) | 13 Nov, 5:57 PM CST: 25 launch-related warnings in force (NGA 23 of 321, NAVAREA XI 3), 20 areas after grouping |

- **GCAT republishes about once a day, at no fixed time** (file headers seen: 13 Nov 2026 00:21 UTC, 15 Nov 10:18
  UTC; the "about 00:20 UTC" first noted here was one sighting). Orbit's four runs a day pick an update up within
  six hours. The lane asks Last-Modified first and downloads nothing if
  no file changed (status `unchanged`). Do not pass `--force` in a schedule: the files are on Jonathan
  McDowell's own server.
- **`satcat.tsv` stops at catalog number 69999.** Recent objects are in `satcat100k.tsv` and, before
  numbering, `tmpcat.tsv`. The seed build read only satcat.
- **`data/state/catalog_index.json.gz` (about 1.3 MB) must be carried between scheduled runs**, or every run is
  a first run. No `restore` command yet (Headwind has one to copy).
- **A failed lane keeps its last good copy** (`from_previous`). A GCAT reading with under 90% of the last
  reading's objects fails the lane.
- Raw copies (gzipped) and `index.jsonl` go to `data/raw/` (git-ignored), as in Headwind.

## Launch ledger (16 Nov 2026, Tom's plan from his earlier launch mapper: "yes, build it")
- `orbit/ledger.py`, `python tools/orbit.py ledger`, workflow `.github/workflows/ledger.yml`, hourly: one Launch
  Library 2 pull of 14 launches (`launches/previous`, `ordering=net`, `net__gte` the newest saved launch's NET). The
  first is the newest saved launch, which verifies it (fields refreshed, changes logged); the rest are added. At most
  one more request: a by-id lookup of the newest saved launch when the pull doesn't hold it ("moved", or "missing",
  kept and marked), or else of the earliest launch in the last 14 days still without a final status (Go, TBC, In
  Flight), so an outcome posted after a launch was saved isn't lost. An error, a 429 included, changes nothing and
  is not retried. From 1 Jan 2024: 887 launches to 15 Nov 2026, so about 64 hours of pulls to catch up.
- Published on this repo's public release `ledger` as `launch-ledger.json` (schema `orbit-ledger/1`, about 780 bytes
  a launch), for every program to read: https://github.com/metacog-osint/orbit/releases/download/ledger/launch-ledger.json.
  The job creates the release on its first run; a release that holds a ledger it cannot download stops the job,
  so a bad read never starts the ledger over.
- Orbit's update run reads it back as lane `ledger`: snapshot block `ledger` (counts, last check, and `since_gcat`,
  the launches after GCAT's newest launch date, the 1-3 day gap the 15 Nov suite review found). Page display:
  card `#ledger` and the map's history layer (orbit-2.10, below).
- tic-dispatch starts `ledger.yml` at :45 past every UTC hour, :55 at 01, 05, 09, 13, 17 and 21 UTC (Blackout has
  :45 there); its own cron (`45 * * * *`) is the fallback. Hub change: the hub's `dispatch/dispatch.js`.

## Map, ledger and payload orbits (16 Nov 2026, `orbit-2.10`; Tom's "do all four")
Shipped 16 Nov 2026 as `3e5629f` (live with `1d6e6ce`). Details in `doctrine/method.md` ("Payload orbits", "Launch's place check").
1. **Payload orbits** (`gcat.orbit_of`): `inc`, `perigee`, `apogee`, `orbit_date` on every payload in `launches`
   and on every object record. Launch's notes asked for `inc`; it reads Orbit's snapshot. GCAT's `Inf` apogee
   (escape trajectories) is read as None: a plain float() round() crashed on the 13 Nov copy.
2. **Lane `pairs`** (`orbit/launchpairs.py`): Launch's published snapshot, its match rows on Orbit's areas
   (`area_source` `orbit-navwarn`), best row per launch and area. Source `tic-launch` (B2). The warnings table
   shows Launch's level under each time coincidence; the map draws a dotted great circle for time and place.
3. **Ledger on the page:** `ledger.history` (pads once, one short row per launch) in the snapshot's `ledger`
   block; pale dots at each pad sized by count with year and provider filters; card `#ledger` with the state
   and `since_gcat` (shown once the ledger has caught up past GCAT's newest launch date).
4. **Launch dot card:** selecting a launch of the last 7 days shows its payloads grouped by orbit, with a link to
   the same launch in Launch's history (`#history?st=launched&q=<GCAT tag>&sel=gcat:<GCAT tag>`; Launch's record id is `gcat:<tag>`).
Checked 16 Nov 2026 on a local build (live snapshot, launches re-derived from the 13 Nov GCAT copies on disk, lanes
`pairs` and `ledger` read live): 92 tests pass, no console errors, map draws with the history layer and filters,
launch cards for Tanluzhe (2026-254) and USSF-627 (2026-255). Not seen yet: a time-and-place line (Launch had only
time rows on 16 Nov) and a card with orbits on screen (checked in Node; the browser pane was hidden).

## Orbit's own daily archive (16 Nov 2026, `orbit-2.11`; decision 8's second half, Tom's "archive first")
Shipped 16 Nov 2026 as `ef9c5a6` (live with `1d6e6ce`). Rules in `doctrine/method.md` ("Orbit's own daily archive").
- `orbit/archive.py`: one entry per UTC day (schema `orbit-archive/1`, 800 days kept): listed orbit changes by
  NORAD:start date, warning areas in force by area key (with the newest memorandum date, so stale-memoranda days
  show), each GCAT reading's catalog changes by satcat stamp, and each lane's statuses (`carried` for a kept
  copy). A failed, off or carried lane leaves no count that day, never a zero. Nothing from the private watch list.
- `collect` adds each run (`_archive_run`) and puts the summary in the snapshot as `archive`; `build` publishes
  `data/state/daily_archive.json` as `/data/archive.json`. With no local copy, a run reads the published one back
  (one request to Orbit's own site) and merges it day by day. No workflow change: data/state is already cached.
- Page: a note under the GCAT baselines (`#archive-body`): days kept, days with no run, baselines from day 90
  (14 Feb 2027 if the first day is 16 Nov 2026). The 90-day baselines themselves are not built.
- Checked 16 Nov 2026 on a local build (local snapshot, lanes marked fresh for the check): 19 areas, 2 listed
  changes, the day marked as read from stale memoranda (13 Nov), note drawn, no console errors; 104 tests pass.

## The globe (16 Nov 2026, `orbit-2.11`; decisions 4 and 7, Tom's "then work the 3d page in cesium")
Shipped 16 Nov 2026 as `1d6e6ce`. Rules in `doctrine/method.md`
("The globe").
- A "Flat map | Globe (3D)" switch on the map card (`#globe` in the address opens it). `site_src/globe.js` has the
  same interface as `map.js` (`resize`, `setHistory`, `select`, `flyTo`), so the cards and filters work with either.
  Cesium loads only when the globe is chosen (Cesium.js 5.9 MB).
- Vendored: `site_src/vendor/cesium/` (CesiumJS 1.146.0 `Build/Cesium` minus `index.js`/`index.cjs`, 344 files,
  14 MB, LICENSE.md and ThirdParty.json; npm tarball sha256 9e4166f2...48d5) and `site_src/vendor/satellite.js/`
  (7.1.0, the non-wasm SGP4 files only, MIT; tarball sha256 b812da8a...a1b5). `build` now copies non-text files byte
  for byte (`TEXT_SUFFIXES`); the tests copy `site_src` without `cesium`.
- Satellite paths: the maneuver lane adds `elements` (newest stored set: epoch, n, e, i, raan, argp, ma) to each
  listed change; SGP4 with drag zeroed, one orbit (a day at GEO) around the page's open time. Only listed objects.
- Imagery: ion asset 2 (Bing aerial) with `data/cesium.json`'s token, written by `build` from `CESIUM_ION_TOKEN`
  (update.yml passes `vars.CESIUM_ION_TOKEN`); Natural Earth II otherwise. CSP adds `https://*.virtualearth.net`,
  `https://*.cesium.com` (img) and `api.cesium.com`, `assets.ion.cesium.com`, `*.virtualearth.net` (connect). The
  earlier note that the CSP was "opened for ion's hosts" was wrong: `_headers` had no ion host before this branch.
- CSP fixes, kept strict (no 'unsafe-eval', no blob: scripts; `tests/test_globe.py` holds them): Cesium.js is
  patched once (Knockout's `(0,eval)("this")` -> `globalThis`; `vendor/cesium/PATCHED.md` has both hashes, redo it
  on any upgrade); `globe.js` unsets `CESIUM_WORKERS` so workers load as modules from `Workers/`;
  `'wasm-unsafe-eval'` in script-src; two sha256 hashes for Cesium's credit `<style>` blocks.
- Checked 16 Nov 2026 on a local build (Natural Earth II, made-up element sets in the local snapshot only, the browser
  pane hidden so animation frames were stood in by a timer): globe, pads, history, areas, both test paths and the
  click card drawn; flat map unchanged; 110 tests pass. Seen live 16 Nov 2026 (headless Edge, 15:2x
  UTC): ion tiles (18, all 200) and paths for the 2 listed changes from real element sets.
- The ion token's allowed URLs (orbit.theintelligence.company, orbit-q2t.pages.dev, 127.0.0.1:8761) don't include
  the local preview ports, so local checks show Natural Earth II; ion imagery can only be seen live.

## Feed (`site/data/feed.geojson`)
Launches of the last 7 days at the launch site (GCAT site coordinates, precision `approximate`); scheduled
launches at the pad; one reentry summary (off-map); catalog-change items (new entries from launches over 30 days
old, by launch; owner changes) for two days after the reading that found them. All `observation`, `routine`,
`us_person_data: organizations` (they name agencies and companies). 21 items on 13 Nov, check PASS.

## Flags and actor colours (13 Nov 2026, `orbit-2.1`)
- **Every country mark is flag + code + a colour bar.** Flags: flag-icons 7.6.0 (MIT, licence in
  `site_src/flags/LICENSE.txt`), 4x3 SVGs copied unchanged for the 113 countries GCAT owners and launch
  agencies use, plus GF and MH (Launch Library 2 pad countries). A code with no flag file shows its code only
  (the image removes itself on error). GCAT has no flag for DD (East Germany) or DR. SU (Soviet Union) gets its
  own mark with no flag, never Russia's; intergovernmental owners (I-ESA and the rest) get their code, no flag.
- **Colour is kept for three actors: US blue, China orange, Russia and the USSR aqua; everyone else neutral.**
  Tokens `--g-us`, `--g-cn`, `--g-ru`, `--g-other` in `style.css`, light and dark. That set passes the dataviz
  validator with every pair compared, in both modes; adding a fourth or fifth colour (Europe, Japan, India) failed
  the colour-blind or normal-vision floor. Do not add colours without re-running it.
- **Where:** payloads grouped by owner, the vehicle's launching agency, the site's country, the scheduled launch's
  provider and pad, reentry owners, and the bar chart of objects in orbit by owner (`hygiene.in_orbit_owners`,
  top 20 kept, 15 drawn; payloads solid, the rest pale).

## Source grades and NET countdowns (13 Nov 2026, page only; method unchanged)
Committed `a7f1f94`, pushed on Tom's yes at 5:42 PM CST; run 43529070673 passed and deployed; checked live at
orbit.theintelligence.company (grades A2/B2, 14 countdowns, no console errors).
- **Sources and freshness shows each lane's Admiralty grade**: GCAT A2, Launch Library 2 B2. `build` writes
  `site/data/sources.json` from `doctrine/sources.json` (ingested sources only) with the wording from the kit's
  `vocab/grading.json`; `LANE_SOURCE` in `tools/orbit.py` ties each lane to its register id. The page draws
  without grades if that file fails to load.
- **Each scheduled launch has a countdown to its NET** on the viewer's clock, refreshed at the top of each
  minute, never finer than Launch Library 2's NET precision: Second/Minute to the minute, Hour (and
  Morning/Afternoon) as "about", Day as "about N days", Week or coarser no countdown. A passed NET reads
  "NET passed ... ago, status as last read" (the status is from Orbit's last read, up to 6 h old).

## Launch hazard warnings and the map (13 Nov 2026, `orbit-2.2`; Tom's "build the map, and yes to all")
- **Lane `navwarn`** (`orbit/navwarn.py`; rules in `doctrine/method.md`): warnings naming rocket launching, space
  debris or reentry, from NGA's daily memoranda and NAVAREA XI. NGA's MSI API is down (503 since at least 6 Nov);
  the memoranda come from its maintenance page (`msi.nga.mil/apology_objects/DailyMem*.txt`) and may vanish when
  the API returns. Since 13 Nov evening the lane reads `broadcast-warn` first (`navwarn.parse_api`; refused when
  empty or its newest warning is over 7 days old) and falls back to the memoranda; `sources.nga.form` says which.
  The API path is tested on the 13 Nov memoranda recast in the API's JSON form (Cordon's field names), not on a
  live API response: none has been seen since it went down.
- **NAVAREA XI is not read (since 14 Nov 2026, Tom's "stop the process, but then find another way").** The
  Japan Coast Guard's robots.txt has `Disallow: /TUHO/` for every crawler but `ndl-japan`, and the list and the
  messages both sit under it. Orbit read it from the 13 Nov deploy until the stop, without having checked robots.txt.
  `navwarn.JCG_READ = False`; the parsers and fixtures stay. `jcg-navarea11` is `excluded` in the register.
  Searched for another source, 14 Nov: China MSA (msa.gov.cn, no robots.txt) answers a script with 403 and its warning
  list URL is unknown; NautoShark needs a login and bars AI crawlers; KHOA's robots.txt disallows everything; no
  open archive found. HYDROPAC and NAVAREA XII rebroadcast some NAVAREA XI warnings (0504 = HYDROPAC 3257, 0507 =
  3256 on 13 Nov), so those still show. Cordon's NAVAREA XI build is on hold for the same reason.
  Old notes on the reader, kept for a source that permits reading. NAVAREA XI: `warnings.cgi` (GET works,
  `LANG=JP`; `E`/`EN` return nothing) for the list, `disp_warnings.cgi?TANA=` for each English text; titles
  filtered on ロケット/宇宙/再突入. Sources graded A2 each (Orbit's call; Tom may regrade).
- **Grouping:** one row per area, with every broadcast (NAVAREA XI first). 13 Nov: NAVAREA XI 0504 = NAVAREA XII
  788 = HYDROPAC 3257; NAVAREA XI 0507 = XII 787 = HYDROPAC 3256 with one vertex different (178-12E vs 178-21E).
  NAVAREA XI 0511/26 (13 Nov): "ROCKET LAUNCHING SUSPENDED. CANCEL 0508/26" for the East China Sea, western North
  Pacific and South Pacific (0508 itself was no longer listed).
- **Time coincidence only**, in the warnings table: scheduled launches whose NET falls in a window of four hours or
  less (or up to an hour before). It is time, not place: on 13 Nov it paired a Vostochny Soyuz with a North
  Atlantic debris box. It was taken out of the scheduled-launch rows for that reason.
- **Not in Orbit's feed.** COP shows the same NGA launch, debris and reentry warnings under "Spectrum and space"
  from Cordon's copies (COP `1a6c577`, live 14 Nov 2026), so an Orbit feed item per area would duplicate them.
- **Map** (`site_src/map.js`, Blackout's pattern): MapLibre GL JS 6.14.0 in `site_src/vendor/maplibre-gl/`
  (byte-identical to COP's integrity-checked copy; the build copies it unchanged), Natural Earth land
  (`data/world.geojson`, built from the kit's `geo/countries.json`, about 970 KB) below zoom 3.5, OpenFreeMap
  positron/dark above. Filled dots = launches of the last 7 days at the GCAT site (launching country's colour),
  rings = scheduled launches at the pad (provider's country), outlines = hazard areas (dashed for debris), using
  only the validated actor tokens plus ink. CSP now allows `tiles.openfreemap.org` (img, connect) and
  `worker-src 'self' blob:`, as COP and Blackout do. In a hidden or background browser tab MapLibre does not
  finish loading the style (seen in the browser pane); a visible tab draws it.
- **GitHub's runners reach msi.nga.mil** (lane `ok` on every run since 13 Nov; the API still answers 503, so the
  memoranda are read). The Japan Coast Guard site is no longer read.

## Anti-satellite test history (14 Nov 2026, `orbit-2.3`; Tom's "proceed with other options 1-3")
- **Lane `counterspace`** (`orbit/counterspace.py`): Secure World Foundation's "History of ASAT Testing in Space"
  Google Sheet, read as CSV with no key (`counterspace.URL`), from the 2026 Global Counterspace Capabilities report
  (CC BY-NC 4.0: `commercial_ok` false; graded B2, confirmed by Tom 15 Nov 2026). 14 Nov: 80 rows, 78 dated
  tests (Russia 33, USA 32, China 11, India 2), 6,874 pieces of debris created, 2,757 still on orbit; two rows
  dated as spans are listed apart and reconcile to SWF's totals (6,904 / 2,773). Sheet last updated 17 Feb 2026.
- Side columns (totals, footnotes, "Last Updated") are cut before parsing; fewer than 50 tests or a moved header
  fails the lane, which keeps its last good copy. Page card after the hazards card; nothing in the feed (no
  coordinates, no counterspace requirement in `doctrine/requirements.json`).
- **RPO sheet built 15 Nov 2026 (`orbit-2.7`, lane `rpo`, `orbit/rpo.py`):** SWF's
  `1pHzvC-zGjF34Jrd6TdmM4odTL_MinBBoS_ld9X3jsW4`, tabs Commercial/Civil gid 0 (14 rows), Military/Intelligence gid
  1789904048 (44), Planned gid 1403218889 (4), About gid 1782604784 ("Last Updated 17 February 2026"); five requests
  a run. 60 of 62 dates read; 78 of 143 names matched to GCAT. Source `swf-rpo` B2 (Tom, 15 Nov 2026:
  "I trust SWF"; Orbit had proposed B3). Card `#rpo` after the ASAT card; not in the feed. Fixtures `tests/fixtures/swf_rpo_*.csv`. ITU: Space Explorer needs a TIES login; the public BR IFIC zips (`itu.int/sns/ific10/ific3084.zip`,
  11 MB, biweekly) are unopened, and ITU's copyright page reserves rights (ask jur@itu.int). CSIS: all rights
  reserved, not used.

## Manoeuvre lane (orbit-2.4, published 14 Nov 2026 after Tom approved the disclaimer, naming the 18th SDS)
Tom, 14 Nov 2026 (relayed by the parent session): "proceed with the space-track work, we will just have a
disclaimer drafted as needed." No written question to Space-Track first. The draft is
`doctrine/spacetrack-disclaimer.md`; Tom approves it before anything is published.
- **Client** `orbit/spacetrack.py`: log in, GP for the watch list, GP_HISTORY (last 60 days) once only for objects
  with no stored history, log out. At most 4 requests a run, 2.5 s apart; no request within an hour of the last GP
  query; a run reaching Space-Track at :57-:03 or :27-:33 waits for a clear minute plus 0-60 s. The hub starts
  Orbit at :55, so the lane usually waits a few minutes (workflow timeout raised to 22 minutes).
- **Detector** `orbit/maneuver.py` (replaces the 1 Nov seed engine): per object, consecutive-set changes in a, i,
  node and e less the object's own median drift, turned into velocity terms; a change is marked at 8 robust
  deviations above the object's own median and at least 0.05 m/s, with 10 pairs minimum; marks under a day apart
  merge. Listed only at 0.25 m/s or more at GEO (Tom, 14 Nov 2026), 0.05 m/s elsewhere; smaller ones counted.
  In LEO a change mainly cross-track or eccentricity is listed only from 1 m/s (`LEO_OFF_TRACK_MS`, orbit-2.8);
  each listed change carries `dv_sma_ms`. The account is shared with Noisefloor: `spacetrack.shared_gp_busy`
  reads Noisefloor's `daily.yml` runs (GH_TOKEN in the collect step) and the lane waits, with a note, while its
  step "GEO region (Space-Track)" is under an hour old or a run is going, or when GitHub cannot be read.
  A change whose widest set pair spans 48 h or more carries `gap` and a page label (Tom, 14 Nov 2026).
  GEO objects also get longitude and drift.
- **Real-data check, run 14 Nov 2026** (Tom's account, `.env` in place): `python tools/orbit.py maneuver-case`,
  Shijian-21 (49330) and BeiDou-2 G2 (34779), 1 Dec 2021 to 1 Mar 2022, 423 sets, stored in
  `data/state/spacetrack/case_sj21_2022.json.gz` (never fetched again). G2 +1,720 km and SJ-21 +1,694 km from
  21-25 Jan, SJ-21 -1,732 km on 26-27 Jan; McDowell's 290 x 3,100 km above GEO averages about 1,695 km. At the
  old 0.05 m/s GEO floor the dead G2 drew four false marks (0.06-0.19 m/s), hence 0.25 m/s. Still open: the
  one-day merge joins SJ-21's approach, docking and tow into one 17-25 Jan change; no LEO known case yet.
- **Private:** credentials `SPACETRACK_IDENTITY`, `SPACETRACK_PASSWORD`; watch list `ORBIT_WATCH` (secrets, collect
  step only) or locally `.env` and `private/watch.txt` (both git-ignored; starter list of 12 checked against GCAT).
  Stored sets, the full report and the held lane record are in `data/state/spacetrack/` (private Actions cache).
  The query URLs list the watch list, so the snapshot records them as "(watch list withheld)". Published output
  names only objects with a marked change and counts the rest.
- **Published:** `maneuver.PUBLISH = True` (False holds it again), `space-track` `use` is `ingest`,
  `LANE_SOURCE["maneuver"] = ["space-track"]`, method orbit-2.4. The card `#maneuvers` carries the approved
  disclaimer at its head, the short credit on every row, and the footer credit; events show GCAT's name and owner
  beside Space-Track's. Change the wording only with Tom's yes. **In the feed from 15 Nov 2026** (Tom's "Yes, add
  them"): one item per listed change, id `orbit:maneuver:<norad>:<from date>`, `geometry` null (where to draw a
  satellite is the open ground-track decision), section 3's citation as the source licence and at the end of the
  summary, section 4's credit in the feed's attribution; requirements OR-PIR-1, OR-EEI-1 and OR-EEI-2 (gap). COP's
  `tools/gate.py` lists `orbit:maneuver` as military context and names Orbit's other kinds as open. GitHub secrets
  SPACETRACK_IDENTITY, SPACETRACK_PASSWORD and ORBIT_WATCH set by Tom 14 Nov 2026; the first run with them reads
  each watched object's 60-day history once.
- `python tools/orbit.py maneuver-report` prints the held report locally.

Earlier notes (13 Nov 2026), kept for the record:

**Terms research, 13 Nov 2026 evening (via a fetch tool's summaries, not checked against the raw pages):**
- Space-Track's User Agreement bars passing on data, but it gives USSPACECOM's "blanket approval" to redistribute
  basic SSA data "conditioned on appropriate citation". It adds that published analysis based on USSPACECOM data
  "also require[s] appropriate citations". API limits: under 30 requests a minute and 300 an hour, and GP/TLE
  queries once an hour, off the top and bottom of the hour.
- maneuver-detect (github.com/astro-tools/maneuver-detect, MIT, dataset CC BY 4.0, v0.3.0) reads that the terms
  bar redistributing analysis derived from Space-Track data. That conflicts with the clause above, so ask
  Space-Track in writing before publishing. Its v0.3 labels are QZSS Δv files, GOES navigation summaries and
  Galileo NAGUs; SJ-21 and BeiDou-2 G2 are not in its README.
- Licence-clean route: operator-announced manoeuvres (QZSS CC BY 4.0, NOAA GOES public domain) as labels, and
  CelesTrak GP snapshots that Orbit keeps itself, since CelesTrak serves no history. CelesTrak's usage policy
  (updated 12 Nov 2026) states no redistribution terms either way.

## Deploy prep (13 Nov 2026, about 1:25 PM CST)
- **`.github/workflows/update.yml`: Headwind's, first run on GitHub passed 13 Nov.** It is Headwind's working workflow with
  the names changed (diffed line by line): tests, last state from the Actions cache, collect, build, check, save
  state, deploy to Pages project `orbit`. Every 6 h at :41, on push to `main`, and by hand. It does nothing until
  it is on `main`; it deploys nothing until the Cloudflare secrets are set. No source needs a key.
- **State lives in the repository's private Actions cache**, as in Headwind: `data/snapshot.json` and
  `data/state/` (1.5 MB measured). Nothing to publish, and no `restore` command needed.
- **Simulated locally from two fresh clones** of `287802c`: run 1 (no state) tests OK, both lanes ok, check PASS;
  run 2 (state copied in, no raw copies) GCAT `unchanged`, check PASS. Whether GitHub's runners can reach
  planet4589.org and ll.thespacedevs.com is not tested until the first run.
- **Checked read-only:** `orbit.theintelligence.company` has no DNS record. Tom's Cloudflare account has no Pages
  project named `orbit`. `orbit.pages.dev` already answers (someone else's), so a new project `orbit` will get a
  suffixed address, as Headwind got `headwind-2lx.pages.dev`.

**Steps to go live, each needing Tom's yes:**
1. ~~Commit and push the workflow on `live/first-slice` (inert there).~~ Done 13 Nov on Tom's "commit and push".
2. ~~Merge `live/first-slice` into `main` and push.~~ Done 13 Nov, 3:25 PM CST; run 43510613951 passed, deploy skipped.
3. ~~Create the Pages project~~ (done by Tom 13 Nov; deploy from `D:\Projects\orbit`, since `pages deploy site`
   uploads the current folder's `site/`): `npx --yes wrangler@4.151.3 pages project create orbit --production-branch main
   --force` (without `--force`, wrangler 4.151.3 hands the command to Workers and creates nothing; Headwind's
   note). Then a first deploy by hand from a local build: `npx --yes wrangler@4.151.3 pages deploy site
   --project-name orbit --branch main`.
4. ~~Secrets~~ (set by Tom 13 Nov): `CLOUDFLARE_PAGES_TOKEN` (Pages: Edit; Headwind still lacks it too, so one token can
   serve both) and repo variable `CLOUDFLARE_ACCOUNT_ID` (Headwind's was copied from Blackout's).
5. ~~Custom domain~~ (done 13 Nov, about 3:55 PM CST): add `orbit.theintelligence.company` to the Pages project, then a Squarespace record
   `CNAME orbit -> <project>.pages.dev` (in the browser; Squarespace may ask Tom to sign in again).
6. Suite wiring, each in its own repo and session: `tic-dispatch` entry (hub repo, `dispatch/`), house bar
   `PROGRAMS` in `theintelligence-company\site\shared\tic-nav.js`, the suite registry row, COP's drawing entry
   and feed list. Describe Orbit there from what is live (launches, schedule, reentries, catalog changes; no
   manoeuvres).

## Open for Tom (14 Nov 2026; Space-Track account, secrets, case run and disclaimer are done)
Decided 15 Nov 2026: manoeuvres go into COP's feed, held from joins by COP's gate (Tom's "Yes, add them"); SWF's
ASAT sheet stays B2 (Tom's "Keep B2"; an RPO sheet would be graded on its own).
3. ~~Launch Library 2 has no stated data licence~~ Decided 15 Nov 2026 (Tom's "Keep, and ask them"): keep it
   (credited, images not used) and ask The Space Devs (support@thespacedevs.com, from their site) for a licence
   statement. Text drafted for Tom to send from his own account; not sent by Claude. Site still states none (15 Nov).
   **Superseded about 9:40 PM CST 15 Nov:** Tom: LL2 is freely available ("the entire database is accessible to
   everyone, for free"); drop the overly cautious rules, the programs need to read each other's data. Orbit uses
   and republishes LL2 data with credit (the ledger below); the email is optional, not a hold. Images still not
   used: each carries its photographer's or agency's own licence.
4. ~~A 3D page: Cesium ion, or tiles without ion.~~ Decided 15 Nov 2026: **Cesium ion** (Tom: "not a commercial
   venture. If the day comes that we start generating revenue, then we'll change our status with cesium"). Not
   built. When it is: Tom creates the ion account and token (restrict the token to orbit.theintelligence.company);
   CesiumJS self-hosted like MapLibre; token set by Tom 15 Nov 2026 as repo variable `CESIUM_ION_TOKEN` (public scope
   assets:read only, allowed URLs orbit.theintelligence.company, orbit-q2t.pages.dev, 127.0.0.1:8761); CSP opened for ion's hosts; revisit the ion plan before any revenue. Settle
   ground tracks (item 7) first, since both draw satellites.
5. ~~ITU route~~ Decided 15 Nov 2026: BR IFIC zips, after written permission from ITU's legal office (jur@itu.int;
   email drafted for Tom to send, not sent by Claude). TIES is closed to TIC: ITU's TIES page gives access only to
   staff of ITU Members (Member States, Sector Members, Associates, Academia, UN system) through the member's TIES
   Focal Point; an ITU User account alone does not qualify. Do not use a government-affiliated TIES account for TIC.
6. ~~A Spaceflight News lane~~ Built 15 Nov 2026, `orbit-2.5` (Tom's "Yes, links only"): lane `news`
   (`orbit/news.py`), source `snapi-thespacedevs` (B3, Orbit's call), one request a run filtered to the scheduled
   launches' LL2 ids; three newest headlines under each scheduled launch, headline, outlet, date and link only.
   No terms stated; question 4 added to the Space Devs email. Not in the feed.
7. ~~Ground tracks as Orbit's COP mark~~ Decided 15 Nov 2026 (Tom's "Pads on COP, tracks in 3D"): COP keeps launch
   pads as Orbit's mark (they join Launch's closure areas); ground tracks go only on the 3D page. A LEO track crosses
   most countries in a day and would make false joins on COP. Manoeuvres, reentries and catalog changes stay off the map.
8. ~~A baseline~~ Decided 15 Nov 2026 (Tom's "GCAT history now, rest later"): baseline launch cadence per country and
   per operator, catalog additions and reentries from GCAT's full history at once (e.g. a country's last 30 days
   against its prior 2 years); start a daily archive of Orbit's own counts (listed orbit changes per object, warnings
   per area) and add those baselines after 90 days. GCAT part built 15 Nov 2026 (`orbit-2.8`, `gcat.baseline`, card
   `#baseline`, page only; method.md "Baselines"); Orbit's own daily archive built 16 Nov 2026 (`orbit-2.11`, above), its baselines after 90 days.
9. ~~NAVAREA XI~~ Decided 15 Nov 2026 (Tom's "Ask JCG, rely on rebroadcasts"): Tom asks the Japan Coast Guard for
   permission to read the English list by script, at most hourly (draft in `private/email-jcg-navarea11.md`, to
   tuho@jodc.go.jp, an address from coordinator lists of uncertain date). Until they answer, HYDROPAC and NAVAREA XII
   rebroadcasts only, and the page says XI is not read.
10. **Decided 16 Nov 2026 (Tom):** CelesTrak's last-30-days group as a second element-set source, for paths of new
    launches' payloads only (Space-Track stays primary; one request a run; CelesTrak's terms checked before
    building). GEO move question 3: numpy, sgp4 and pyarrow pinned at build time for the callouts only; live
    lanes stay standard library (`doctrine/geo-move-plan.md`).
Approved 15 Nov 2026 (Tom's "Yes, build it" to each): (a) built 15 Nov, `orbit-2.6`, the merge fix, joining marks under a day
apart only when the dominant term and the sign of the semi-major-axis change agree (SJ-21's 17-25 Jan change);
(b) built 15 Nov (`maneuver-case iss`, stored read of 965 sets; 5 of 5 NASA reboosts hit, 9 cross-track or
eccentricity marks not in NASA's list, storm drew no drag mark; method.md orbit changes item 7), a LEO known case, the ISS over a 90-day window with at least 3 NASA-announced reboosts plus a window with the
10-11 May 2024 storm, one stored GP_HISTORY read (about 3 requests); (c) built 15 Nov (`orbit-2.7`, see the ASAT section), the SWF RPO sheet lane, after confirming the
2026 report links the sheet under CC BY-NC 4.0.

## Rules
- Standard library only for the live lanes. Tests stay offline.
- Never `git add -A`: other sessions (Claude and Gemini) share these folders.
- No material from other work here. The plan's reuse of older code needs names stripped
  and no key files copied.
