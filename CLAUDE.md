# Orbit (`[local path]`)

The space layer of The Intelligence Company (`tic-feed/2`, program id `orbit`, prefix `OR`): orbital launches,
scheduled launches, reentries and satellite catalog changes. Observations only: no probabilities, no warnings.

**State, 13 Nov 2026: first live slice built on branch `live/first-slice`, not committed** (Tom's yes needed for
commit and push, each). `main` and `origin/main` are the 1 Nov seed snapshot (`ee05012`). Not deployed: no Pages
project, no DNS record, no workflow, no hub, registry, COP or `tic-dispatch` entry. Untracked and to stay that
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

## Lanes (method `orbit-2.0`; details in `doctrine/method.md`)
| Lane | Module | Source | Measured 13 Nov 2026, about 12:40 PM CST |
|---|---|---|---|
| `catalog` | `gcat.py` | GCAT, CC BY 4.0: `satcat`, `satcat100k`, `auxcat`, `tmpcat`, `launch`, `sites` (about 37 MB) | 83,476 objects across the four catalogs; 22 orbital launches in 30 days; 85 reentries in 30 days; 36,289 objects in orbit (RU 3,919, SU 3,029); 780 in orbit with no catalog number; 0 catalog numbers claimed twice in the US catalogs. First reading, so no changes yet |
| `upcoming` | `launches.py` | Launch Library 2, one request a run (free limit 15 an hour) | 14 launches in the next 14 days |

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

## Not live: manoeuvres (`orbit/maneuver.py`, not run)
The seed engine differences consecutive element sets at a 0.35 m/s threshold that drag and fit noise exceed in
low orbit, and its "calibrated confidence" is a formula. Before any manoeuvre lane: run maneuver-detect (MIT,
v0.3.0, needs PyTorch) locally on SJ-21 / BeiDou-2 G2 (Jan 2022) with Tom's Space-Track account; read
Space-Track's terms (maneuver-detect's README says they bar redistributing data or derived analysis); keep the
watch list in private config. Tom sets any credentials himself.

## Open for Tom
Commit and push the branch; Space-Track account and terms; the watch list; Launch Library 2 has no stated data
licence (credited, images not used); deploy decisions (Pages project, DNS `orbit`, workflow on `tic-dispatch`,
hub and COP entries).

## Rules
- Standard library only for the live lanes. Tests stay offline.
- Never `git add -A`: other sessions (Claude and Gemini) share these folders.
- No material from other work here. The plan's reuse of older code needs names stripped
  and no key files copied.
