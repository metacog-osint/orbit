# Space-Track disclaimer (approved 14 Nov 2026)

The draft was approved on 14 Nov 2026, naming the 18th Space Defense Squadron. Published from orbit-2.4:
`PUBLISH = True` in `orbit/maneuver.py`, the `space-track` source's `use` is `ingest`, and the page card carries
the wording below. Change the wording only with the account holder's approval.

## What Space-Track's terms say (read 14 Nov 2026)
- User Agreement (space-track.org/auth/createAccount): the user agrees "not to transfer any data or technical
  information received from this website, or other U.S. Government source, including the analysis of data, to any
  other entity without prior express approval." It cites 10 USC 2274(c)(2).
- Documentation, "Redistribution of Basic SSA Information" (space-track.org/documentation): "USSPACECOM has provided
  express blanket approval for transfer/redistribution of basic SSA data and services" accessed via Space-Track,
  "conditioned on appropriate citation." And: "Publications of analysis based on USSPACECOM data also require
  appropriate citations."
- Space-Track gives no citation wording. The text below is Orbit's. **Both quotes checked word for word against
  the raw pages, 14 Nov 2026, 22:30 UTC:** the documentation quote matches; the User Agreement quote had dropped
  "or other U.S. Government source" (restored above). The blanket approval names basic SSA data only (TLEs, OMMs,
  SATCAT, decay and reentry data); for analysis it asks only for citation. maneuver-detect's README reads the terms
  as barring redistribution of derived analysis, which is the User Agreement clause read without the approval.

## 1. On the page, at the top of the manoeuvre card (every time the card shows)
> **Source: Space-Track.org, United States Space Command (USSPACECOM), 18th Space Defense Squadron.** Element sets are USSPACECOM's,
> redistributed under its blanket approval for basic space situational awareness data, which requires this
> citation. The orbit changes listed here are The Intelligence Company's own analysis of those element sets. They
> are not USSPACECOM's, and USSPACECOM and Space-Track have not reviewed, endorsed or checked them.
>
> A listed change means a watched object's published orbit moved by more than its element sets usually move. It is
> not a confirmed manoeuvre, a statement of intent or a warning: a re-fit after a tracking gap, a mislabelled
> element set or, in low orbit, storm-driven drag can do the same. Not for conjunction assessment, collision
> avoidance or any operational use. Satellite operators should use Space-Track's own services.

## 2. Beside each listed change (short form)
> Space-Track.org (USSPACECOM) element sets; Intelligence Company analysis.

## 3. In `snapshot.json` (`maneuvers.attribution`) and any COP feed item
> Element sets: Space-Track.org, United States Space Command (USSPACECOM), 18th Space Defense Squadron,
> redistributed under USSPACECOM's blanket approval for basic SSA data. Orbit-change analysis: The Intelligence Company, not reviewed or endorsed by
> USSPACECOM. Not for operational use.

## 4. Footer credit and README
> Satellite element sets from Space-Track.org, United States Space Command (USSPACECOM), 18th Space Defense
> Squadron; orbit-change analysis is Orbit's own.

## Settled
- The 18th Space Defense Squadron is named (14 Nov 2026); the 19th is not.
- Space-Track's terms apply to the account holder. This text is published under the account
  holder's account terms.
- Raw element sets are not republished: the page shows changes and positions derived from them, and the stored
  sets stay in the private Actions cache.
