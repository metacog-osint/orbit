# GEO board: the role list (`site_src/geo_roles.json`)

The list decides which objects the notable rule, the relocation tracker and the set-gaps card watch. An object is
listed only where published reporting supports its role, and each entry cites that reporting. Unlisted objects have
no listed role, which says nothing about what they are. The first check, of 26 Oct 2026, is in Noisefloor's history
([docs/validation/geo-board.md](https://github.com/metacog-osint/noise-floor/blob/main/docs/validation/geo-board.md));
it listed ten objects.

## 27 Nov 2026: widened from Secure World Foundation's RPO sheet

**Scope.** Every chaser in the GEO rows of Secure World Foundation's RPO sheet (CC BY-NC 4.0, sheet updated 17 Feb
2026, as Orbit's `rpo` lane read it at 05:21Z on 27 Nov 2026), matched to catalog numbers by the lane. Each was
checked against the GEO page's objects (globe.json built 05:22Z on 27 Nov 2026, 1,837 objects).

**Already listed (10):** USA 270, USA 271, USA 324, USA 325 (GSSAP 3 to 6), Shijian-17, Shijian-21, Shijian-25,
MEV-1, MEV-2 and Luch (Olymp-K 2).

**Added (10), each with its role, basis and sources in the file:**

| NORAD | Object | Role (claim) | Status, as of | On the GEO page, 27 Nov 2026 | Main published sources |
|---|---|---|---|---|---|
| 40099 | USA 253 (GSSAP 1) | inspection (declared) | active, 15 Feb 2026 | 72.7° E, above the protected zone | Air & Space Forces Magazine's GSSAP page; Designation-Systems.net; SWF's GSSAP row |
| 40100 | USA 254 (GSSAP 2) | inspection (declared) | retired, 14 Aug 2023 | 154.4° W, above the protected zone | SpaceNews, 15 Aug 2023; Air & Space Forces Magazine, 17 Aug 2023 and GSSAP page |
| 40101 | USA 255 (ANGELS) | inspection (declared) | retired, Nov 2017 | 118.3° E, above the protected zone | Wikipedia (AFRL fact sheet); Gunter's Space Page |
| 40258 | Luch (Olymp-K 1) | inspection (attributed) | retired, 30 Jan 2026 | 162.6° E, above the protected zone | Wikipedia (SpaceNews 2015, the French armed forces minister 2018); Space.com, 30 Jan 2026 |
| 43874 | TJS-3 | inspection (attributed) | active, 17 Feb 2026 | 175.6° E, in the zone | Space.com, 3 Mar 2023 (Orbital Focus, Satellite Dashboard); Breaking Defense, Oct 2021; SWF |
| 43917 | TJS-3 AKM (TJS-3's companion) | inspection (attributed) | uncertain, 20 May 2024 | 78.2° E, above the protected zone | Breaking Defense, Oct 2021 (COMSPOC); Wikipedia; Gunter's Space Page; Defense One |
| 50321 | Shiyan 12 01 | inspection (attributed) | uncertain, 20 May 2024 | 100.1° E, in the zone | SpaceNews, Jun 2022 (COMSPOC); Defense One, May 2024 (Satellite Dashboard) |
| 50322 | Shiyan 12 02 | inspection (attributed) | uncertain, 20 May 2024 | 164.2° E, in the zone | as Shiyan 12 01 |
| 55247 | LINUSS2 | inspection (declared; which CubeSat was the servicer is SWF's) | uncertain, 17 Apr 2023 | 126.3° W, above the protected zone | Lockheed Martin, 18 Apr 2023; Breaking Defense, 17 Apr 2023; Aviation Week |
| 55264 | LDPE-3A | inspection (attributed) | uncertain, 27 Aug 2026 | 56.1° W, above the protected zone | Gunter's Space Page; SWF's row, which cites it |

Objects above the protected zone stay listed: a retired inspector that moves again is worth noticing. LDPE-3A's
approach to Shijian-23 rests on one line of reporting: Gunter's Space Page, which SWF's row cites. No independent
report was found on 27 Nov 2026.

**Every source re-read, 27 Nov 2026.** Each cited source of the ten added entries was opened and checked for the
catalog number, the name, the role in the source's own words and the current status with its date. Two exceptions:
the AFRL ANGELS fact sheet refused the request (HTTP 403), so its claims are checked through Wikipedia, which cites
it; and SWF's rows were read from Orbit's copy of the 17 Feb 2026 sheet (`tests/fixtures/swf_rpo_*.csv`). The
catalog numbers and names were checked against Orbit's catalog index. The basis now
says who makes each claim: "declared" where the operator or state describes the role (GSSAP, ANGELS, LINUSS), and
"attributed", with the analyst, firm or government named, everywhere else. Changes from the first draft of the list:
- USA 254 (GSSAP 2) had been described as operating. Space Operations Command announced it out of service on
  2 Aug 2023, and Space Systems Command said on 14 Aug 2023 that it was passivated and in a graveyard orbit
  (SpaceNews, 15 Aug 2023).
- GSSAP's role is now in the programme's own terms: it tracks and characterises objects and can manoeuvre to
  observe them at close range or rendezvous. "Inspect" was the list's word.
- LDPE-3A cites Gunter's Space Page in its own hedged terms ("may have happened", about 30 km).
- LINUSS2: neither Lockheed Martin nor the press says which CubeSat was the servicer. SWF's sheet does, and the
  basis says so. "Above GEO" was dropped, since the sources say GEO. 400 m is the closest imagery, from 28 Feb 2023.
  SWF types the row "Servicing". No docking was reported, so the role stays inspection.
- Shiyan 12 01 now cites the support for its own role: SpaceNews calls the pair "Chinese inspection satellites",
  and Defense One, citing Satellite Dashboard, says both approached foreign communications satellites in 2021.
- TJS-3 cites its own approaches (USA 233 and USA 298, 2022-23, Space.com) and SWF's RPO with TJS-10.
- Second sources added: Gunter's Space Page (ANGELS, TJS-3 AKM), Space.com (Luch, TJS-3), Defense One (TJS-3 AKM),
  Breaking Defense (LINUSS2), SpaceNews and Air & Space Forces Magazine of Aug 2023 (USA 254), and
  Designation-Systems.net (the GSSAP satellites' status).

The ten entries listed before 27 Nov were given a claim and a status from their sources too. In MEV-2's basis,
"undocking planned for 2026" was replaced: Northrop Grumman said on 23 May 2024 that it would stay docked to
Intelsat 10-02 for four more years. A test (`tests/test_geo_roles.py`) and `orbit.py check` now fail when an entry
lacks a source, a claim, a status, a status date or a status note.

**Considered and left out (no public element set: not on the GEO page, so Orbit cannot see them move):**
- MiTEx (USA 187, USA 188);
- Mentor 4 (USA 202);
- PAN (USA 207);
- CLIO (USA 257);
- MYCROFT;
- Prowler;
- GSSAP 7 and 8 (USA 582, USA 583, launched 2026).

List them when a public set appears.

**Not in scope:**
- chasers in SWF's LEO rows, and its planned missions;
- targets and clients, for example LINUSS1, Shijian-23 and Intelsat 10-02, unless they are chasers themselves.

**Wording kept:** "Unlisted objects have no listed role, which says nothing about what they are."
