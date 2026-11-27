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

| NORAD | Object | Role | On the GEO page, 27 Nov 2026 | Main published source |
|---|---|---|---|---|
| 40099 | USA 253 (GSSAP 1) | inspection | 72.7° E, above the protected zone | GSSAP programme (Air & Space Forces Magazine, Wikipedia); SWF's GSSAP row |
| 40100 | USA 254 (GSSAP 2) | inspection | 154.4° W, above the protected zone | as GSSAP 1 |
| 40101 | USA 255 (ANGELS) | inspection | 118.3° E, above the protected zone | AFRL fact sheet; decommissioned Nov 2017 |
| 40258 | Luch (Olymp-K 1) | inspection | 162.6° E, above the protected zone | Wikipedia (SpaceNews 2015, Space.com 2026): moved to a graveyard orbit Oct 2025 |
| 43874 | TJS-3 | inspection | 175.6° E, in the zone | Breaking Defense, Oct 2021 (COMSPOC) |
| 43917 | TJS-3 AKM (TJS-3's companion) | inspection | 78.2° E, above the protected zone | as TJS-3 |
| 50321 | Shiyan 12 01 | inspection | 100.1° E, in the zone | SpaceNews (COMSPOC); Defense One, May 2024 |
| 50322 | Shiyan 12 02 | inspection | 164.2° E, in the zone | as Shiyan 12 01 |
| 55247 | LINUSS2 | inspection | 126.3° W, above the protected zone | Lockheed Martin, 18 Apr 2023; Aviation Week |
| 55264 | LDPE-3A | inspection | 56.1° W, above the protected zone | SWF's RPO sheet only (Oct 2024, with Shijian-23) |

Objects above the protected zone stay listed: a retired inspector that moves again is worth noticing. LDPE-3A rests
on a single source: no other published report of its approach to Shijian-23 was found on 27 Nov 2026.

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
