# Orbit

The Intelligence Company's space layer: what changed in Earth orbit. Orbital launches, launches scheduled in the
next 14 days, launch hazard and space-debris areas from navigational warnings, reentries, and changes to the public
satellite catalog between Orbit's own readings, orbit changes in a watch list of satellites, and the history of
anti-satellite tests in space, with a map of sites, pads and hazard areas. Measured or reported, never judged. Live at https://orbit.theintelligence.company.

Sources: GCAT (data from J. McDowell, planet4589.org/space/gcat, CC BY 4.0), Launch Library 2 (The Space Devs),
headlines from the Spaceflight News API (links to each outlet, headlines only), NGA Maritime Safety Information, the Secure World Foundation (ASAT test history, CC BY-NC 4.0), and satellite
element sets from Space-Track.org, United States Space Command (USSPACECOM), 18th Space Defense Squadron;
orbit-change analysis is Orbit's own (`doctrine/spacetrack-disclaimer.md`). Map: MapLibre
GL JS (BSD-3), Natural Earth, OpenFreeMap, OpenMapTiles, OpenStreetMap contributors. Method: `doctrine/method.md`.

Not live yet: counterspace events beyond SWF's ASAT test history.

## Commands

```bash
python tools/orbit.py collect              # fetch every live lane into data/snapshot.json
python tools/orbit.py collect --force      # read GCAT even if its files have not changed
python tools/orbit.py build                # build site/ from data/snapshot.json
python tools/orbit.py check                # validate the registers and lint the feed
python -m unittest discover -s tests       # offline tests against real fixtures
python tools/serve.py                      # site/ on http://127.0.0.1:8761 with the headers in _headers
```
