# Orbit Method (`orbit-1.0`)

## Purpose
Orbit tracks satellite catalog changes, owner-code hygiene, TLE tracking gaps, and orbital maneuvers (`Maneuver Compare`) across watched LEO, MEO, HEO, and GEO space objects.

## Key Analytic Rules (from `_ideas/sda-trackers.md`)
1. **Owner-Code Hygiene (`gcat_satcat`)**:
   - CelesTrak's `"CIS"` owner code merges 16,142 legacy Soviet (`SU`) objects with 9,016 Russian Federation (`RU`) objects. Orbit maps ownership through GCAT (`planet4589.org/space/gcat/`), preserving `SU` vs. `RU`, tracking active unnumbered objects (`NORAD == None`), and flagging duplicate NORAD catalog claims.
2. **Sibling Filtering (`launch_designator`)**:
   - Co-orbiting objects sharing the same international launch designator within 30 days of launch are tagged as `siblings` so multi-payload deployments are not misclassified as hostile co-orbital approaches.
3. **Maneuver Compare & Hypothesis Sentences (`celestrak_gp_history`)**:
   - Compares consecutive GP element sets to classify burns into `in-track` (semi-major axis / mean-motion phasing), `cross-track` (inclination / RAAN plane change), or `radial` (eccentricity / perigee adjustment) with $\Delta v$ in m/s and calibrated confidence.
   - Attaches a stock meaning sentence framed strictly as a hypothesis, never a finding.
   - Applies two-tier alerting: routine station-keeping stays `tier: "routine"`, while non-routine maneuvers ($\Delta v \ge 1.5\text{ m/s}$ and confidence $\ge 0.75$) emit `tier: "warning"`.
4. **Source Health (TLE Gap Flag)**:
   - Any watched object whose TLE history has a gap $\ge 48\text{ hours}$ is explicitly flagged (`OR-IND-4`), because an untracked gap looks identical to zero maneuvers.
