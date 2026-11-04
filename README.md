# Orbit

**Orbit** (`orbit.theintelligence.company`) is The Intelligence Company's Space Domain Awareness (SDA), orbital maneuver comparison, and satellite catalog hygiene monitor.

Built from the architecture in `_ideas/sda-trackers.md`, it provides:
1. **Maneuver Compare (lead feature)** — Detects in-track, cross-track, and radial maneuvers ($\Delta v$ in m/s) across watched LEO/GEO satellites from public TLE/GP history, attaches stock meaning sentences framed as hypotheses, and separates routine station-keeping (`tier: "routine"`) from non-routine co-orbital or plane-change maneuvers (`tier: "warning"`).
2. **GCAT Catalog Snapshots & Owner-Code Hygiene** — Maps satellite ownership through Jonathan McDowell's GCAT (`planet4589.org`) rather than CelesTrak's `"CIS"` bucket (separating Soviet `SU` vs. Russian `RU` objects), tracks active unnumbered objects, flags duplicate NORAD catalog claims, and groups co-orbiting launch siblings (`launch_designator`).
3. **Source Health (TLE Gap Detection)** — Flags watched objects whose TLE history has a gap $\ge 48$ hours, since a tracking gap looks identical to zero maneuvers.

## Commands

```bash
python tools/orbit.py collect              # build normalized GCAT + TLE maneuver snapshot
python tools/orbit.py build                # build site/ and site/data/feed.geojson (tic-feed/2)
python tools/orbit.py check                # validate doctrine registers and lint contract-v2 feed
python -m unittest discover -s tests -v    # run offline test suite
```
