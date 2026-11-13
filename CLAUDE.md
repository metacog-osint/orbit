# Orbit (`[local path]`)

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

**Planned scope** (`[local path]`, program row and roadmap step 14): catalog changes,
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
python -m unittest discover -s tests       # 16 offline tests, real fixtures from 13 Nov
python tools/serve.py                      # http://127.0.0.1:8761 with _headers (CSP); launch config "orbit-site"
```

## Lanes (method `orbit-2.1`; details in `doctrine/method.md`)
| Lane | Module | Source | Measured 13 Nov 2026, about 12:40 PM CST |
|---|---|---|---|
| `catalog` | `gcat.py` | GCAT, CC BY 4.0: `satcat`, `satcat100k`, `auxcat`, `tmpcat`, `launch`, `sites`, `orgs` (about 38 MB) | 83,476 objects across the four catalogs; 22 orbital launches in 30 days; 85 reentries in 30 days; 36,289 objects in orbit (RU 3,919, SU 3,029); 780 in orbit with no catalog number; 0 catalog numbers claimed twice in the US catalogs. First reading, so no changes yet |
| `upcoming` | `launches.py` | Launch Library 2, detailed mode (about 450 KB; only it carries provider countries), one request a run (free limit 15 an hour) | 14 launches in the next 14 days |

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

## Not live: manoeuvres (`orbit/maneuver.py`, not run)
The seed engine differences consecutive element sets at a 0.35 m/s threshold that drag and fit noise exceed in
low orbit, and its "calibrated confidence" is a formula. Before any manoeuvre lane: run maneuver-detect (MIT,
v0.3.0, needs PyTorch) locally on SJ-21 / BeiDou-2 G2 (Jan 2022) with Tom's Space-Track account; read
Space-Track's terms (maneuver-detect's README says they bar redistributing data or derived analysis); keep the
watch list in private config. Tom sets any credentials himself.

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
3. ~~Create the Pages project~~ (done by Tom 13 Nov; deploy from `[local path]`, since `pages deploy site`
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
