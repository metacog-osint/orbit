# Space-Track disclaimer (DRAFT, 14 Nov 2026, for Tom's approval)

Nothing from Space-Track is published until Tom approves this text. Approval is one change: `PUBLISH = True` in
`orbit/maneuver.py`, the `space-track` source's `use` set to `ingest` in `doctrine/sources.json`, and the page
card built with the wording below.

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
> **Source: Space-Track.org, United States Space Command (USSPACECOM).** Element sets are USSPACECOM's,
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
> Element sets: Space-Track.org, United States Space Command (USSPACECOM), redistributed under USSPACECOM's blanket
> approval for basic SSA data. Orbit-change analysis: The Intelligence Company, not reviewed or endorsed by
> USSPACECOM. Not for operational use.

## 4. Footer credit and README
> Satellite element sets from Space-Track.org, United States Space Command (USSPACECOM); orbit-change analysis is
> Orbit's own.

## Open points for Tom
- Should the page name the 18th and 19th Space Defense Squadrons? Orbit's register used to. Space-Track's
  sign-up page refers operators to the 18th; the 19th has not been checked.
- Space-Track's terms apply to the account holder. The account is Tom's, so this text is published under Tom's
  account terms.
- Raw element sets are not republished: the page shows changes and positions derived from them, and the stored
  sets stay in the private Actions cache.
