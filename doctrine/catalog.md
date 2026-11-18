# TIC satellite catalog: Orbit's build record

Moved from Orbit's CLAUDE.md on 18 Nov 2026 (Tom's yes: CLAUDE.md keeps what the program is, commands, rules and
pointers). Design, Tom's answers and the full build log: `[local path]`
(sections 9 and 10). This file is the per-step record of what was built in this repository.

Build steps 1-5 live 17 Nov 2026, published on the public release `catalog` by `.github/workflows/catalog.yml`;
the WMO OSCAR/Space link file on branch `feat/catalog-oscar` (18 Nov 2026).

Design and Tom's answers: `[local path]` (section 9). Branch `feat/sat-catalog`,
worktree `_worktrees\orbit-sat-catalog`, from origin/main `14c1579`.
- **Step 1:** `doctrine/sources.json` 2.5 adds the catalog's sources with the terms read 16 Nov 2026: planned
  ingest (`use` `excluded` with `planned_use` `ingest` until each build step lands, so the page lists only live
  sources) for `celestrak-satcat`, `wikidata`, `wmo-oscar-space`, `mccants-classfd`; `use` `link` (cited per object,
  never scraped) for `gunter-space-page`, `orbital-focus`, `unoosa-register`, `itu-space-explorer`, `wikipedia`,
  `nssdca`, `seesat-l`, `operator-pages`. Space-Track's note adds SATCAT and DECAY. The stale duplicate
  `celestrak-gp` entry ("Not yet checked", excluded) was removed; the live one stays.
- **Step 2:** `orbit/catalog.py` (schema `tic-catalog/1`) from GCAT alone; `python tools/orbit.py catalog`
  builds it locally from the GCAT copies in `data/raw` (no request) into `data/catalog/catalog.json.gz`. Keys:
  NORAD numbers from satcat and satcat100k only; auxcat and tmpcat stay keyed by JCAT (auxcat's Satcat cell cites a
  related US number, e.g. A00002 -> 00003, and is not a claim to it). Every value is {value, source, ref, read,
  basis}; names from Name, PLName and AltNames (`:JP`/`:RA` kept as `qualifier`, GCAT's `?` as `uncertain`);
  display rule "USA 253 (Hornet 1)" when the first name is a designation. On the 13 Nov GCAT copy: 70,731 numbered,
  12,745 without a number, 0 disagreements (one source), 95.5 MB JSON, 5.2 MB gzipped. Tests `tests/test_catalog.py`
  (18, on GCAT rows of the test objects); 167 tests pass, check PASS.
- **Step 3 (Tom's brief, 17 Nov 2026):** `orbit/stcat.py`, `python tools/orbit.py spacetrack-catalog` (local
  only; no workflow change). Space-Track's use policy (read 17 Nov 2026) lists SATCAT ("Once per day after 1700
  (UTC)") and DECAY (1 a day; store an object's history, never download it again) on their own rows; GP's hourly
  rule is GP's alone, so `shared_gp_busy` is not used. No other TIC program queries satcat or decay (Noisefloor
  reads CelesTrak's SATCAT and Space-Track gp/gp_history). `stcat.due` allows one read per UTC date from 17:00
  UTC; the run keeps off :57-:03 and :27-:33. 4 requests: log in, satcat `CURRENT/Y`, decay (the whole history the
  first time, then `MSG_EPOCH` since the last read less a day), log out. Raw replies gzipped in
  `data/raw/spacetrack-{satcat,decay}/`; decay store and state in `data/state/spacetrack-{decay.json.gz,catalog.json}`.
  `catalog.build(..., spacetrack=...)` adds Space-Track records (`intldes`, `launch_date`, `state` from COUNTRY,
  `names` from SATNAME, `decayed`, `decay_date` from SATCAT and Historical DECAY messages; predictions stay in the
  store only). COUNTRY is compared through `stcat.COUNTRY_TO_STATE` (built from a cross-tab on the real reading);
  operator codes (ORB, GLOB, SES, O3B, SEAL, ITSO, EUTE, IM, ABS, AC) and TBD/UNKN are kept, never compared; analyst
  objects' `YYYY-000x` and 1 January dates are placeholders; GCAT's pre-1963 Greek-letter pieces are not compared.
  `swaps()` now flags a name only when each source gives it to a number the other does not, all from one launch.
  `doctrine/sources.json` 2.6: Space-Track's note records the SATCAT and DECAY use.
- **First real read, 17 Nov 2026 18:09 UTC** (Tom's account, 4 requests): 71,335 SATCAT rows; 144,363 decay
  messages (whole history, stored). Built against GCAT of 15 Nov (`2026 Nov 15 1018:34`): 71,409 numbered entries
  (70,702 in both, 633 Space-Track only, mostly `OBJECT x` and new 101xxx debris; 74 GCAT only, e.g. USA 726-736
  SBST R-4); 2,560 with disagreements: decayed 1,093, launch date 863, state 744, intldes 41; 27 name swaps. Most are
  definitional, all listed: 534 of the 628 launch-date gaps over 31 days are objects deployed from the ISS
  (Space-Track gives Zarya's 1998-11-20, GCAT the deployment); 886 "decayed" are objects GCAT holds under its own
  status codes (DK 462, DSO 137, TFR 78, GRP 59, ATT 41, OX 31, DSA 28, ERR 22, others) while Space-Track gives a
  decay date, 207 the reverse; only 4 decayed after GCAT's file. State: Rocket Lab objects (GCAT NZ, Space-Track
  US, 176), Satellogic (UY/ARGN, 55), Galileo (I-EU/ESA, 42). Intldes: real piece swaps (Iridium 24/46, Starlink
  6115/6126, SL-6 platform/rocket body). Name swaps: Flock 1 (13), Globalstar M078/M095-97, RCM 2/3, SJ-2/2B, SSU
  2/3 and others. Display: "USA 257 (NEMESIS 2)", "USA 253 (Hornet 1)", 55841 "LUCH (OLYMP) 2" (SWF's spelling).
  153 MB JSON, 8.2 MB gzipped. Tests `tests/test_stcat.py` (23, on real rows cut unchanged into
  `tests/fixtures/spacetrack_{satcat,decay}_20261117.json` and `catalog_satcat_extra.tsv`); 190 tests pass, check PASS.
- **Workflow and release (Tom's "yes to all not done items", 17 Nov 2026 about 12:45 PM CST):** `catalog.yml`
  (cron 17:23, 19:23, 21:23 UTC and dispatch; `spacetrack-catalog --release`): decay store and state from the public
  release `catalog`, one read when `stcat.due` allows, GCAT's five tables (one request each), build, upload
  `catalog.json.gz`, `spacetrack-decay.json.gz` (the store between runs; Actions cache can be evicted) and
  `spacetrack-catalog.json`. If the release exists but the store will not download, or the history was read and
  the store is missing, nothing is read (never the whole history again). The release was seeded from the local read
  of 17 Nov 18:09 UTC. Not in the hub's `tic-dispatch` (hub change, not made). Still to do in step 6: the object
  card "Names and sources" section, and a smaller file (records repeat source, read and ref; 153 MB JSON).
- **Step 4 (17 Nov 2026, branch `feat/catalog-step4`, worktree `_worktrees\orbit-catalog-step4`; not committed):**
  `orbit/catsources.py`: CelesTrak SATCAT (`/pub/satcat.csv`, gzip, only when `satcat/jsonDir.php` shows a new
  FILE_MTIME and no read that UTC day) and Wikidata (one SPARQL query a week: P377 items, en and mul labels, en
  aliases, P247; UA names the repo, no person). No redirect is followed; any non-200 puts the source on hold in
  `data/state/catalog-sources.json` (5xx and 429 until the next UTC day, anything else until a person runs
  `--clear-hold`). `catalog.add_celestrak` / `add_wikidata`: OBJECT_NAME kept as given, OWNER compared as GCAT State
  through Space-Track's codes plus `catsources.CT_OWNER_TO_STATE` (ISS not compared), OPS_STATUS_CODE in a new
  field `ops_status` (FLAGGED; compared only where two sources give one), Wikidata names with the Q-id as ref,
  two items on one number noted as `wikidata_items`. `python tools/orbit.py catalog-sources` reads locally;
  `catalog --sources DIR` builds with them. In `catalog.yml` (drafted, not live) both are read only in the run that
  makes the Space-Track read; replies ride the Actions cache, the state rides the release (`catalog-sources.json`).
  **Merged and live 17 Nov 2026 as `ffb320c`** (update run 44154083184 passed); first scheduled read with it: 18 Nov
  after 17:23 UTC (17 Nov's read was made by hand before the merge, so no CelesTrak or Wikidata read that day),
  and the release notes are re-set each upload with both credits. `doctrine/sources.json` 2.7: both `ingest`
  (no page lane, so the page does not list them). WMO OSCAR/Space not built: no NORAD number or COSPAR ID in its
  API, so it cannot be matched on an id. **Tom, 17 Nov 2026:** a hand-reviewed slug-to-NORAD link file, the 414
  operational satellites first (not built). Real read and counts: design note section 10.
- **Step 5 (17 Nov 2026, Tom's "Step 5: aliases + rpo"; branch `feat/catalog-step5`, worktree
  `_worktrees\orbit-catalog-step5`; not committed):** `orbit/aliases.py` reads `orbit/data/catalog/aliases.yml`
  (standard library, a strict YAML subset: errors name the line; `.gitignore` re-includes `orbit/data/`). Entries:
  a name (`norad` or `jcat`, `name`, `basis`, `source` from doctrine/sources.json, `read`, `evidence` list, optional
  `swf_key` and `swf_date`) or a program (`swf_key`, `program`, `members`); `withdrawn` + `reason` keeps an entry and
  skips it; `swap` entries are refused until built. Five entries: 55841, 40258, 43917 (TJS-3 AKM), 40208 (CLIO), and
  program GSSAP (8 members). `catalog.build(..., alias_entries=)` adds name records (source `aliases`, `cited` the
  claim's source) and `program` records; `catalog.names_index` writes `catalog-names.json.gz` (schema
  `tic-catalog-names/1`, every payload plus alias targets: 31,658 rows, 0.87 MB gzipped), uploaded by `catalog.yml`
  with the catalog (code only, no workflow change). Lane `rpo` (method `orbit-2.16`) reads that asset from the
  release (one request) and matches on every source's names plus alias pins; without it, GCAT's names plus pins, with
  `names_note`. Card labels "Catalog: ..." and "Program GSSAP: 8 objects". Real comparison (SWF tabs of 15 Nov,
  catalog of 17 Nov): 99 of 143 names linked (78 before), 6 by alias, none moved to another object; dropped where
  sources disagree: Cosmos 2536 (Space-Track 44422, GCAT 44424) and Prowler (Wikidata 20963, GCAT A04907). Until
  the first `catalog.yml` run with this code (18 Nov), the lane falls back to GCAT plus the alias file. Tests
  `tests/test_aliases.py` (16, on the real alias file, SWF fixtures and 22 real name-index rows in
  `tests/fixtures/catalog_names_20261117.json`); 229 tests pass, check PASS; card checked in the browser pane on a
  local build (99 links, no console errors).
- **WMO OSCAR/Space link file (18 Nov 2026, Tom's pick; branch `feat/catalog-oscar`, worktree
  `_worktrees\orbit-catalog-oscar`):** `orbit/oscar.py`: `python tools/orbit.py oscar-read` reads the satellite list
  once (36 pages, 3 s apart, resumes; any non-200 stops) into git-ignored `data/raw/wmo-oscar/<stamp>/`; `oscar-propose
  --stamp S [--draft]` proposes NORAD candidates from launch date (within a day) and orbit only (CelesTrak SATCAT
  payloads; bounds in `oscar.orbit_fits`), names from the TIC name index listed beside them, never choosing.
  `orbit/oscarlinks.py` reads `orbit/data/catalog/oscar-links.yml` (aliases' YAML subset): per slug `norad` or
  `members`, `relation` same/hosted, `proposal`, evidence; **only entries with `reviewed_by` and `reviewed` join, and
  no join code exists yet** (the build would need OSCAR's values in `catalog.yml`: a workflow change for Tom).
  `--draft` appends unreviewed entries only for a single fit with an equal name or the one equal name among several.
  Read 18 Nov: 1,062 satellites, 414 operational; drafted 285, left 129 for a person (hosted instruments,
  constellation entries, operator names the catalogs lack, OSCAR values that do not fit). Never query CelesTrak for
  this: use catalog-sources' stored file. Tests `tests/test_oscar.py` (17); 247 pass. Details: design note section 10.
- **Step 6, data for the object page (18 Nov 2026, Tom's pick; branch `feat/catalog-step6`, worktree
  `_worktrees\orbit-catalog-step6`, from origin/main `aabfa10`):** `orbit/catshards.py`; no page code (the split
  agreed with the object-page session: the catalog supplies data and rules, Orbit's page draws them).
  - **Compact file, schema `tic-catalog/2`:** a record leaves out `read` when it equals its source's read in
    `sources`, `ref` when it is the object's own key in that source (GCAT: `jcat`; Space-Track, CelesTrak: the NORAD
    number) and `basis` when `attributed`; `record_defaults` in the file says so and `catshards.expand_entry` puts
    them back exactly (a test checks every fixture object, and the live 18 Nov file round-trips with 0 mismatches).
    `catalog.build` still returns full records; `catalog_local` writes the compact form.
  - **Orbit records** (field `orbit`, never compared, not in FLAGGED): GCAT's Perigee, Apogee, Inc as written, ODate as
    `elements_date`, OpOrbit; CelesTrak's PERIGEE, APOGEE, INCLINATION, PERIOD, ORBIT_CENTER, ORBIT_TYPE (codes kept,
    not decoded). GCAT's elements can be old (S25544 is dated 1998-12-20).
  - **Release assets added** (uploaded by `catalog_release` with the rest; code only, no workflow change):
    `catalog-shards.tar.gz` (one download; unpacks to `catalog/`: `n<NORAD//1000>.json`, `j<JCAT letter><number//1000>.json`,
    each `tic-catalog-shard/1` with the sources block, rank, record defaults and the swaps touching its objects, plus
    `search.json` and `rules.json`), `catalog-search.json.gz` (`tic-catalog-search/1`: every object as [key, name,
    other names, COSPAR ID, type code, gone]), `catalog-rules.json` (`tic-catalog-rules/1`: source labels and
    citations, basis wording, name fields, field notes, flags, disagreement and swap explanations, the shard rule).
    Bundles are byte-identical for the same catalog (gzip mtime 0).
  - **Sizes, local build** from the stored copies (GCAT 15 Nov, Space-Track, CelesTrak and Wikidata 17 Nov):
    241.3 MB JSON with every record in full (orbit records included), 147.7 MB compact, 7.8 MB gzipped (the live
    18 Nov file without orbit records: 210.1 MB, 11.2 MB gzipped); 117 shards (73 numbered, 44 unnumbered), largest
    2.1 MB, 154 MB unpacked, 8.6 MB as the tar; search index 84,160 rows, 6.1 MB JSON, 1.11 MB gzipped (under the
    page's 2 MB line, so one file); rules note 8 KB. Counts unchanged (2,686 with disagreements, 109 name swaps).
  - Tests `tests/test_catshards.py` (16, on the step 4 fixtures plus GCAT's auxcat and tmpcat rows and the real
    alias file); 300 tests pass, check PASS. `catalog.yml`'s test step runs them (Tom's yes, 18 Nov 2026).
- **OSCAR links reviewed (18 Nov 2026; branch `feat/catalog-oscar-review`):** all 285 drafted entries accepted by a
  TIC analyst, none withdrawn; each has `reviewed_by: "tic-analyst"` and `reviewed`. The review record is kept
  privately. Nothing joins yet: the join code and OSCAR's weekly read in `catalog.yml` are not built.
