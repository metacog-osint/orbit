# Orbit

The Intelligence Company's space layer: what changed in Earth orbit. Orbital launches, launches scheduled in the
next 14 days, reentries, and changes to the public satellite catalog between Orbit's own readings. Measured or
reported, never judged.

Sources: GCAT (data from J. McDowell, planet4589.org/space/gcat, CC BY 4.0) and Launch Library 2 (The Space
Devs). Method: `doctrine/method.md`.

Not live yet: manoeuvre detection, counterspace events. Not deployed.

## Commands

```bash
python tools/orbit.py collect              # fetch every live lane into data/snapshot.json
python tools/orbit.py collect --force      # read GCAT even if its files have not changed
python tools/orbit.py build                # build site/ from data/snapshot.json
python tools/orbit.py check                # validate the registers and lint the feed
python -m unittest discover -s tests       # offline tests against real fixtures
python tools/serve.py                      # site/ on http://127.0.0.1:8761 with the headers in _headers
```
