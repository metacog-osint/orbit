# ITU filings as GEO slot evidence (`orbit-2.42`, 27 Nov 2026)

This file holds the method for this part of Orbit. It sits beside `method.md`, as `catalog.md` does.

## What an ITU filing shows, and what it does not
- **A satellite network filing** is an administration's request to the ITU for an orbit position and spectrum.
  Administrations file advance publication, coordination requests, notifications for the Master International
  Frequency Register (MIFR), Resolution 49 due diligence, and plan entries and modifications under Appendices 30,
  30A and 30B.
- **A network name is the administration's label for a filing, not a satellite's name.** "EUTELSAT 3-12.5W" or
  "F-SAT-N3-12.5W" names a set of frequency assignments at a nominal longitude. One satellite may serve several
  filings, often from several administrations, and it may serve filings at other slots over its life. One filing
  may be served by different satellites over time.
- **A filing for a slot is not evidence that a satellite is, or ever was, at that slot.** Administrations file
  for slots they never use, file ahead of a launch, and keep filings after a satellite leaves.
- **Declarations to the ITU.** Two kinds of record are the administration's own statement that a space station was
  in position: a brought-into-use date in the MIFR, and a Resolution 40 statement that a station was in position
  for the filing from a date, and whether it came from another filing's slot. Orbit quotes them as the
  administration's statements. The ITU names no satellite and no NORAD number in either.
- **Matching a filing to an object is an attribution.** Orbit makes it only by review (below), and the ITU never
  makes it. A network name never becomes one of the object's names in the catalog, so declared names (operators,
  registers) and attributed names stay apart.

## Sources and terms
- ITU Space Explorer's public calls, which need no login:
  - `POST https://www.itu.int/itu-r/space/apps/ep/spaceexplorer/v1/queries` takes the GEO "orbital arc" filter
    that Space Explorer's own Space Stations list sends (`satNetworkTypes.geo`, `geoFrom`, `geoTo`, active
    notices, pages of 200). It returns one row per notice: network name, administration, organization, nominal
    longitude, provision, date received and notice id.
  - `https://www.itu.int/net/ITU-R/space/res40/res40_webtable.json` is the Resolution 40 table: network,
    administration, nominal longitude, the date in position, and whether the station came from another filing's
    slot (that slot, that filing and the date it left).
- **Terms** (itu.int terms of use, read 27 Nov 2026): "ITU grants you permission to download, copy and use content
  for personal, educational, or non-commercial purposes provided that you acknowledge the source and maintain all
  copyright and other proprietary notices. You may not modify, reproduce, distribute, sell, transmit, create
  derivative works or use the content for any commercial purpose without obtaining prior written permission from
  ITU." Orbit is non-commercial, and its use is as follows:
  - the slot lookup below is local, on a person's request;
  - replies are kept in git-ignored `data/raw/itu/` and never published;
  - pages show only filings linked to one object by review, each named, cited and linked to its own ITU page;
  - Orbit publishes no ITU table, list or download, and the repository holds none (the test fixture is made up in
    ITU's format).
- Not used: TIES, BR IFIC files, Space Explorer's registered RESTful API (it takes a token and its own terms of
  use), and anything behind an ITU login (beams, earth stations, Resolution 49 spacecraft details).
- Request limits: ITU states none for these calls, and robots.txt disallows nothing under them (read 27 Nov
  2026). Orbit's own limits:
  - calls run only on request, never in a schedule or the update run;
  - one request every 3 s;
  - a slot's reply and the Resolution 40 table are each reused for 7 days unless `--refresh` is given;
  - the User-Agent names the repository.

## The slot lookup: `python tools/orbit.py find 12.5W --itu`
`find` already prints three lists for a slot: who is there now, who is named for it, and who held it (`orbit-2.31`).
`--itu` adds two more.
1. **Filed for the slot:** the active GEO notices whose nominal longitude is within 0.1° of the slot, or within
   `--window` when one is given.
   - Notices are grouped by network name and filer, nearest the slot first.
   - Each notice gives its provision, in words and ITU's code, and the date ITU received it.
   - Each network carries a link to its ITU page.
2. **Resolution 40 statements:**
   - stations in position for a filing at the slot, with the date and where the station came from;
   - stations that left the slot for a filing elsewhere, with the date they left.

Both lists say what a filing is and is not, and that matching one to a satellite is TIC's inference. Read them
against the GEO record above them: dates of arrival, departure and stays.

## Linking a filing to an object: `orbit/data/catalog/itu-links.yml`
The file is hand-kept and works like `oscar-links.yml`, in the same YAML subset (`orbit/itu.py`, `load_links`).
- One entry links one filing to one object. It gives `norad`, `network`, `adm`, `org`, `slot`, `ntc_id`, optional
  `from` and `to` (the dates the object served the filing), `basis`, `evidence` (a list, each statement with its
  source), `proposed_by` and `proposed`.
- `basis` is one of:
  - `declared`: an operator's or administration's own document names both the satellite and the filing;
  - `res40-dates`: the Resolution 40 dates match this object's own move in public element sets;
  - `by-hand`.
- **Only entries with `reviewed_by` and `reviewed` reach a page.** A person adds both after checking the entry by
  diff. A wrong entry is withdrawn with `withdrawn` and `reason`, never edited to a new number. A bad entry stops
  the build.

## The object page
- The build writes the reviewed entries to `site/data/itu-links.json` (`orbit-itu-links/1`, by NORAD number).
- The object page shows them under "What Orbit holds on it" as **ITU filings linked by review**. Each row gives:
  - the network name, linked to its ITU page;
  - the administration (and organization);
  - the slot filed for;
  - the dates served, when the evidence gives them;
  - the basis, with the review date;
  - the evidence.
- The section opens with what a network name and a filing are, and with the statement that the link is TIC's,
  not the ITU's.
- Sources and citations name the ITU.
- An object with no reviewed entry shows nothing from the ITU.
