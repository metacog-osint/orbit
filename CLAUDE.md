# Orbit (`[local path]`)

The space layer of The Intelligence Company (`tic-feed/2`, program id `orbit`, prefix `OR`): orbital launches,
scheduled launches, reentries and TIP predictions, catalog changes, breakups, orbit changes in watched satellites,
RPO and ASAT history, the GEO belt, a globe, a daily archive and a daily lead, plus the TIC satellite catalog.
Observations only: no probabilities, no warnings. Repo `metacog-osint/orbit` (**public**); live at
https://orbit.theintelligence.company (Cloudflare Pages project `orbit`, `orbit-q2t.pages.dev`).

Full earlier text: `.claude/notes-archive-2026-11-18.md`. **Current state and open items:
`.claude/HANDOFF.md`**; read it before starting work. Keep this file under 12 KB; state and narrative
go in the handoff, shas and "landed" notes are left to git.

## Where things are
- `doctrine/method.md`: the rules of every lane, card and page (method version `orbit-2.N` at its head; take the
  next free number, other sessions push to Orbit too). `doctrine/sources.json`: every source, grade, terms, use.
  `requirements.json`, `indicators.json`, `interests.json`, `ncf_map.json`: the registers `check` lints.
- `doctrine/spacetrack-disclaimer.md`: Tom's approved wording; change it only with his yes.
  `doctrine/geo-move-plan.md`: the GEO move from Noisefloor.
- Plans: `[local path]` (site: daily lead, a page per object with search,
  owner and constellation views), `sat-catalog-design-2026-11.md` (the catalog; sections 9-10 hold Tom's answers and
  the real counts; build record per step: `doctrine/catalog.md`),
  `space-programs-reorg-2026-11-16.md` (program boundaries), Orbit's row in `new-programs.md`.
- `orbit/` modules, `tools/orbit.py` CLI, `site_src/` source, `site/` build output, `tests/` with real fixtures. `.gitignore` ignores `data/` but re-includes `orbit/data/` (alias and link files).

## Commands
```bash
python tools/orbit.py collect              # every live lane into data/snapshot.json (--only LANE, --force)
python tools/orbit.py build                # site/ from data/snapshot.json (refuses without one)
python tools/orbit.py check                # registers + feed lint
python -m unittest discover -s tests       # offline tests
python tools/serve.py                      # http://127.0.0.1:8761 with _headers (CSP)
python tools/orbit.py catalog | spacetrack-catalog | catalog-sources   # the TIC catalog (local)
python tools/orbit.py geo [--day] [--out data/geo] [--upload]           # GEO region
python tools/orbit.py ledger | maneuver-report | maneuver-case
python tools/orbit.py object-data         # object pages: catalog shards into site/data/catalog (method.md)
```
GEO callouts and page: `pip install -r tools/requirements-callouts.txt`, then `tools/geo_callouts.py` and
`tools/geo_page.py build DIR site --snapshot data/snapshot.json` (local steps in `doctrine/method.md`, "The GEO page").

## Workflows and schedules
- `update.yml`: tests, state from the Actions cache, collect, build, check, GEO page data, save state, deploy to
  Pages. **Runs on every push to `main`, so a push deploys.** Cron `41 */6`; the hub's `tic-dispatch` starts it at :55
  past 00/06/12/18 UTC (the cron is the fallback). Timeout 22 min (Space-Track wait).
- `ledger.yml`: hourly Launch Library 2 ledger on release `ledger` (`launch-ledger.json`, `orbit-ledger/1`; dated daily copy in private `tic-archive`);
  dispatched at :45 (:55 at 01/05/09/13/17/21 UTC), own cron `45 * * * *`.
- `geo.yml`: GEO region at 03:15 and 15:15 UTC by tic-dispatch, own cron :17 (skips if today's file is under an hour
  old); releases `geo-YYYY`. `geo-import.yml`: one-off copy of Noisefloor's history.
- `catalog.yml`: cron 17:23, 19:23, 21:23 UTC, also started by the hub's tic-dispatch (17:30 UTC on 18 Nov);
  release `catalog` (its assets: `doctrine/catalog.md`).
- State (`data/snapshot.json`, `data/state/`) lives in the private Actions cache, or every run is a first run.
  Release-held stores (decay store, ledger) are never rebuilt from scratch: a release that holds a file the job cannot
  download stops the job.

## Lanes (rules and thresholds in `doctrine/method.md`)
| Lane | Module | Source (grade) | Notes |
|---|---|---|---|
| `catalog` | `gcat.py` | GCAT, CC BY 4.0 (A2) | Last-Modified first, nothing downloaded when unchanged; under 90% of last reading's objects fails. `satcat.tsv` stops at 69999: later objects in `satcat100k`, unnumbered in `tmpcat`. Baselines from GCAT's history (`#baseline`) |
| `upcoming` | `launches.py` | Launch Library 2 detailed (B2) | One request a run (free limit 15/h). NET countdowns never finer than LL2's precision |
| `news` | `news.py` | Spaceflight News API (B3) | Headline, outlet, date, link only; not in the feed |
| `pairs` | `launchpairs.py` | Launch's snapshot (`tic-launch`, B2) | Its place check on Orbit's areas |
| `ledger` | `ledger.py` | Orbit's own ledger release | One GitHub request, no LL2 request |
| `navwarn` | `navwarn.py` | NGA `broadcast-warn` API first, else daily memoranda | NAVAREA XI only by HYDROPAC / XII rebroadcast. Time coincidence is time, not place. Not in the feed (COP shows Cordon's copies) |
| `counterspace` | `counterspace.py` | SWF ASAT sheet, CC BY-NC 4.0 (B2) | Under 50 tests or a moved header fails. Not in the feed |
| `rpo` | `rpo.py` | SWF RPO sheet (B2, Tom: "I trust SWF") | Five requests; matched on catalog names plus alias pins |
| `paths` | `celestrak.py` | CelesTrak last-30-days GP (A2, same 18 SDS data) | Paths of new payloads only; a 403 keeps previous sets, no retry |
| `decay` | `tip.py` | Space-Track TIP | Card only, not in the feed; runs before `maneuver` |
| `maneuver` | `maneuver.py`, `spacetrack.py` | Space-Track GP, private watch list | Published with the disclaimer; feed items `orbit:maneuver:*` |
End-of-run blocks: `tip_check` (TIP against GCAT's reentry), `lead` (`lead.py`), `archive` (`archive.py`,
`orbit-archive/1`, every day kept, published at `/data/archive.json`). A failed lane keeps its last good copy
(`from_previous`); a failed, off or carried lane leaves no archive count that day, never a zero.

## Feed
`observation`, `routine`, `us_person_data: organizations`. Kinds: launches of the last 7 days at the GCAT site
(precision `approximate`), scheduled launches at the pad, one reentry summary (off-map), catalog changes for two
days, listed orbit changes (`geometry` null; OR-PIR-1, OR-EEI-1, OR-EEI-2 for `gap`), breakups (`orbit:breakup:<jcat>`,
OR-EEI-5, at most 10, link `/#breakups`). COP's gate lists `orbit:maneuver` as military context. On COP Orbit's mark
is launch pads only; ground tracks go only on the 3D globe; manoeuvres, reentries and catalog changes stay off maps.

## Source rules
- **Space-Track** (account shared by the update run and `geo.yml`; Noisefloor makes no GP query from 18 Nov 2026): GP at most once an hour, off :57-:03 and :27-:33
  (`spacetrack.shared_gp_busy` checks the other runs by step name; a test holds the names), at most 4 requests a run
  2.5 s apart, GP_HISTORY once per object. SATCAT once per UTC day after 17:00; DECAY's whole history was read once
  and is stored on the release: never download it again. Cite as in the disclaimer. Credentials and the watch list
  are Tom's secrets; the watch list never appears in output (queries recorded as "(watch list withheld)"); published
  output names only objects with a marked change. Stored case reads (`data/state/spacetrack/case_*`) are never
  fetched again.
- **Manoeuvre listing** (Tom): GEO from 0.25 m/s, elsewhere 0.05 m/s; LEO changes mainly cross-track or eccentricity
  from 1 m/s; a widest set pair of 48 h or more carries `gap`; a pair needing more than orbital speed is
  `implausible`, never listed. GEO orbit changes on the GEO page use Orbit's rule, not callout C5 (C5 kept as the
  scored v1 record).
- **GCAT**: never `--force` in a schedule (Jonathan McDowell's own server). Republishes about daily at no fixed time.
- **CelesTrak**: one download per 2-hour update; SATCAT only when `jsonDir.php` shows a new FILE_MTIME. **Wikidata**:
  one SPARQL query a week, UA names the repo. Any non-200 puts a catalog source on hold (`--clear-hold` by a person) and stops `sats` (clear: method.md).
- **Launch Library 2**: free to use and republish with credit (Tom, 15 Nov 2026); images never used (own licences).
- **Japan Coast Guard NAVAREA XI: not read** (robots.txt disallows `/TUHO/`; Tom, 14 Nov). `navwarn.JCG_READ = False`.
- **ITU**: TIES is closed to TIC; never use a government-affiliated TIES account. BR IFIC zips only after written
  permission from ITU's legal office. **CSIS**: all rights reserved, not used.
- **Catalog**: every value is {value, source, ref, read, basis} (the file leaves out defaults, `catshards`); NORAD keys from satcat/satcat100k only (auxcat's
  Satcat cell is not a claim); operator codes and TBD/UNKN never compared; alias `swap` entries refused until built.
  WMO OSCAR joins only through hand-reviewed link entries (no NORAD or COSPAR id in its API); read weekly.

## Page rules
- Country marks: flag + code + colour bar (flag-icons 7.6.0, MIT). SU gets its own mark, never Russia's flag;
  intergovernmental owners get their code only.
- Colour only for US blue, China orange, Russia/USSR aqua; everyone else neutral (`--g-us`, `--g-cn`, `--g-ru`,
  `--g-other`). A fourth colour failed the dataviz validator; never add one without re-running it.
- CSP stays strict: no 'unsafe-eval', no blob: scripts, no inline styles (`tests/test_globe.py`,
  `tests/test_geo_page.py`). Cesium 1.146.0 is patched once (`vendor/cesium/PATCHED.md`; redo on any upgrade). The
  GEO page's import-map sha256 lives in `_headers`: change one, change both.
- Cesium ion (Bing imagery) via variable `CESIUM_ION_TOKEN`, allowed only on the live hosts and 127.0.0.1:8761, so
  local previews show Natural Earth II. TIC is non-commercial; revisit the ion plan before any revenue.
- MapLibre doesn't finish loading in a hidden tab; check maps in a visible tab or headless browser.
- Describe Orbit publicly from what is live.

## Program boundaries (Tom, 16-17 Nov 2026)
- The GEO belt is Orbit's; Noisefloor keeps signals, sun outages and space weather.
- Decision 2 (17 Nov): Launch Library 2 schedule, ledger and news move to Launch, and Orbit retires its launch map
  layers and `pairs` lane, keeping the old ledger URL as a forward copy for a while. Not started; see the reorg plan.

## Not built, with the reason
ITU (permission first); NAVAREA XI direct (robots.txt), China MSA (403, list unknown), NautoShark (login, bars AI
crawlers), KHOA (robots.txt); CSIS (rights); maneuver-detect labels (its reading of Space-Track's terms conflicts
with USSPACECOM's citation clause); pass predictions.

## Rules
- Standard library only for the live lanes (numpy, sgp4, pyarrow pinned for callouts and import only). Tests offline.
- Commit, push and deploy each need Tom's yes (one question may bundle them). Never `git add -A`: other sessions
  (Claude and Gemini) share these folders. Stage by name; push by sha after listing what is ahead.
- **Repo swap, 15 Nov 2026:** shas before `8740711` exist only in `metacog-osint/orbit-archive`. Never push anything
  built on the old history; cut worktrees from origin/main.
- Untracked and staying so: `data/`, `GEMINI.md`, `private/`, `.env`, `.claude/`. Never print `.env`, `private/`
  or secret values. Tom sets every credential.
- The repo is public: no private or work material; nothing from the watch list.
- Don't pop the stash labelled "line-ending-only copies of site/tic-nav.*".
- No material from other work here; reused older code needs names stripped and no key files copied.
- Times stored UTC; the page shows the viewer's zone, named (`tic-time.js`).
- Emails to The Space Devs, ITU and the Japan Coast Guard stay drafts until Tom sends them.
