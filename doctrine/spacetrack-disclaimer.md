# Space-Track disclaimer (approved by Tom, 14 Nov 2026)

Tom approved the draft on 14 Nov 2026 and chose to name the 18th Space Defense Squadron. Published from orbit-2.4:
`PUBLISH = True` in `orbit/maneuver.py`, the `space-track` source's `use` is `ingest`, and the page card carries
the wording below. Change the wording only with Tom's yes.

## What Space-Track's terms say (read 14 Nov 2026)
- User Agreement (space-track.org/auth/createAccount): the user agrees "not to transfer any data or technical
  information received from this website, including the analysis of data, to any other entity without prior
  express approval."
- Documentation, "Redistribution of Basic SSA Information" (space-track.org/documentation): "USSPACECOM has provided
  express blanket approval for transfer/redistribution of basic SSA data and services" accessed via Space-Track,
  "conditioned on appropriate citation." And: "Publications of analysis based on USSPACECOM data also require
  appropriate citations."
- Space-Track gives no citation wording. The text below is Orbit's. Both quotes come from a fetch tool's reading
  of the pages, not yet checked word for word in a browser.

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
- The 18th Space Defense Squadron is named (Tom, 14 Nov 2026); the 19th is not.
- Space-Track's terms apply to the account holder. The account is Tom's, so this text is published under Tom's
  account terms.
- Raw element sets are not republished: the page shows changes and positions derived from them, and the stored
  sets stay in the private Actions cache.
