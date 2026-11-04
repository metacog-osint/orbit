# Orbit (`[local path]`)

Space Domain Awareness (SDA), Maneuver Compare, and GCAT catalog hygiene program for The Intelligence Company (`tic-feed/2`, program id: `orbit`, prefix: `OR`).

## Architecture
- **Standard library only** (Python 3.11+).
- **`doctrine/`**: Full `tic-doctrine 0.4.1` registers (`OR-REQ-*`, `OR-PIR-*`, `OR-EEI-*`, `OR-WP-*`, `OR-H-*`, `OR-IND-*`, `OR-ASM-*`).
- **`orbit/gcat.py`**: Implements GCAT owner-code hygiene (`SU` vs `RU` separation, unnumbered active object tracking, duplicate NORAD detection, and co-orbiting sibling grouping by international launch designator).
- **`orbit/maneuver.py`**: Implements **Maneuver Compare** over TLE epoch pairs (`in-track`, `cross-track`, `radial`), computes $\Delta v$ (m/s) via vis-viva / inclination-change approximations, attaches hypothesis-framed meaning sentences, flags TLE tracking gaps ($\ge 48$ h), and applies two-tier alerting.
- **`orbit/feed.py`**: Emits `site/data/feed.geojson` (`tic-feed/2`) with `ncf` mappings (`provide_satellite_access`, `provide_pnt`).
