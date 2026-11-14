# Orbit (`D:\Projects\orbit`)

The space layer of The Intelligence Company (`tic-feed/2`, program id `orbit`, prefix `OR`): orbital launches,
scheduled launches, reentries and satellite catalog changes. Observations only: no probabilities, no warnings.

**State, 13 Nov 2026: first live slice and deploy workflow merged into `main` and pushed (`84190bb`, a
fast-forward, on Tom's "merge and push", 3:25 PM CST).** First GitHub run (43510613951) passed: tests, both lanes
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
`3788906`; COP shows Orbit fresh, 21 items, 20 on the map). Tom still has to add `orbit` to the `tic-dispatch`
token's repository access; until then the dispatcher's start 404s and Orbit runs on its own cron. Untracked and to stay that
way: `GEMINI.md` and `data/`.

**Planned scope** (`D:\Projects\_ideas\new-programs.md`, program row and roadmap step 14): catalog changes,
launches, manoeuvres, counterspace events; maneuver-detect, Secure World Foundation counterspace sheets, ITU
Space Explorer, optional 3D page. Built: launches, scheduled launches, reentries, catalog changes, owner-code
counts. Not built: manoeuvres, counterspace events, ITU, 3D page. Describe Orbit publicly from what is live.

## Commands
```bash
python tools/orbit.py collect              # every live lane into data/snapshot.json
python tools/orbit.py collect --only upcoming
python tools/orbit.py collect --force      # read GCAT even if unchanged
python tools/orbit.py build                # site/ from data/snapshot.json (refuses without one)
python tools/orbit.py check                # registers + feed lint
python -m unittest discover -s tests       # 29 offline tests, real fixtures from 13 Nov
python tools/serve.py                      # http://127.0.0.1:8761 with _headers (CSP); launch config "orbit-site"
```

## Lanes (method `orbit-2.2`; details in `doctrine/method.md`)
| Lane | Module | Source | Measured 13 Nov 2026, about 12:40 PM CST |
|---|---|---|---|
| `catalog` | `gcat.py` | GCAT, CC BY 4.0: `satcat`, `satcat100k`, `auxcat`, `tmpcat`, `launch`, `sites`, `orgs` (about 38 MB) | 83,476 objects across the four catalogs; 22 orbital launches in 30 days; 85 reentries in 30 days; 36,289 objects in orbit (RU 3,919, SU 3,029); 780 in orbit with no catalog number; 0 catalog numbers claimed twice in the US catalogs. First reading, so no changes yet |
| `upcoming` | `launches.py` | Launch Library 2, detailed mode (about 450 KB; only it carries provider countries), one request a run (free limit 15 an hour) | 14 launches in the next 14 days |
| `navwarn` | `navwarn.py` | NGA daily in-force memoranda (5 text files, about 140 KB) and NAVAREA XI (Japan Coast Guard: list XML plus one page per launch-related warning) | 13 Nov, 5:57 PM CST: 25 launch-related warnings in force (NGA 23 of 321, NAVAREA XI 3), 20 areas after grouping |

- **GCAT republishes once a day (about 00:20 UTC).** The lane asks Last-Modified first and downloads nothing if
  no file changed (status `unchanged`). Do not pass `--force` in a schedule: the files are on Jonathan
  McDowell's own server.
- **`satcat.tsv` stops at catalog number 69999.** Recent objects are in `satcat100k.tsv` and, before
  numbering, `tmpcat.tsv`. The seed build read only satcat.
- **`data/state/catalog_index.json.gz` (about 1.3 MB) must be carried between scheduled runs**, or every run is
  a first run. No `restore` command yet (Headwind has one to copy).
- **A failed lane keeps its last good copy** (`from_previous`). A GCAT reading with under 90% of the last
  reading's objects fails the lane.
- Raw copies (gzipped) and `index.jsonl` go to `data/raw/` (git-ignored), as in Headwind.

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
- **Not in the feed** yet, so COP is unchanged. A feed item per area (polygon geometry) would need COP's Orbit
  drawing entry to handle polygons.
- **Map** (`site_src/map.js`, Blackout's pattern): MapLibre GL JS 6.14.0 in `site_src/vendor/maplibre-gl/`
  (byte-identical to COP's integrity-checked copy; the build copies it unchanged), Natural Earth land
  (`data/world.geojson`, built from the kit's `geo/countries.json`, about 970 KB) below zoom 3.5, OpenFreeMap
  positron/dark above. Filled dots = launches of the last 7 days at the GCAT site (launching country's colour),
  rings = scheduled launches at the pad (provider's country), outlines = hazard areas (dashed for debris), using
  only the validated actor tokens plus ink. CSP now allows `tiles.openfreemap.org` (img, connect) and
  `worker-src 'self' blob:`, as COP and Blackout do. In a hidden or background browser tab MapLibre does not
  finish loading the style (seen in the browser pane); a visible tab draws it.
- **Whether GitHub's runners can reach msi.nga.mil (Akamai) and www1.kaiho.mlit.go.jp is untested** until the first
  run after the push.

## Not live: manoeuvres (`orbit/maneuver.py`, not run)
The seed engine differences consecutive element sets at a 0.35 m/s threshold that drag and fit noise exceed in
low orbit, and its "calibrated confidence" is a formula. Before any manoeuvre lane: run maneuver-detect (MIT,
v0.3.0, needs PyTorch) locally on SJ-21 / BeiDou-2 G2 (Jan 2022) with Tom's Space-Track account; read
Space-Track's terms (maneuver-detect's README says they bar redistributing data or derived analysis); keep the
watch list in private config. Tom sets any credentials himself.

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

## Open for Tom
Space-Track account and terms; the watch list; Launch Library 2 has no stated data licence (credited, images not
used); the deploy steps above.

## Rules
- Standard library only for the live lanes. Tests stay offline.
- Never `git add -A`: other sessions (Claude and Gemini) share these folders.
- No material from other work here. The plan's reuse of older code needs names stripped
  and no key files copied.
