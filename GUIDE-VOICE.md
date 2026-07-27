# City guide voice — the rule

**Status: binding for every guide in `site/destinations/`, existing and future.**
Set July 27, 2026. Applies to all ~150 planned guides.

## The rule

A Departs Daily city guide has to read like it was written by somebody who has
actually been there and has opinions. If you could swap the city name out and
the paragraph would still make sense, **it is not finished** — delete it and
write the real thing.

We would rather ship 10 guides a month that people forward to a friend than 40
that read like the same guide with the nouns changed.

## What that means concretely

**Kill on sight — the copycat tells:**

- An opener that works for any city. "X is a vibrant destination with something
  for everyone" is not an opener, it is a placeholder.
- Interchangeable superlatives: world-class, hidden gem, bustling, vibrant,
  nestled, must-see, foodie paradise, melting pot.
- A hotel blurb that only describes the hotel category ("stylish boutique with
  a rooftop bar") and never the street, the neighbourhood, or why *this* one.
- The same three section headers in the same order in every guide when the city
  doesn't call for it. Nashville earns a "where the actual songwriters play"
  section. Grand Cayman does not.
- Advice that is really just general travel advice wearing a local hat.

**Required in every guide:**

- **A point of view in the first sentence.** Nashville's current opener — *"The
  bachelorette capital hides a real music town — skip the pedal taverns, find
  the songwriters"* — is the standard. It takes a side.
- **At least one thing that is specifically, verifiably true of this city and
  nowhere else** — a building, a street, a season, a rule, a local habit.
  Austin's *"a 1885 firehouse with bunks upstairs and a hidden lounge behind the
  bookcase"* is the standard.
- **The honest timing note.** When it is cheap, when it is miserable, what event
  triples the prices. Nashville's *"CMA Fest week (June) triples everything"* is
  the standard.
- **At least one thing we tell people NOT to do**, and why. A guide that likes
  everything is worth nothing.
- **Recommendations placed by neighbourhood**, so the reader can tell where they
  would actually be standing.

**Depth target:** 900–1,400 words of real editorial. The existing 30 guides
average ~627 words, which is thin — they are honest and city-specific, but they
stop just as they get interesting. Bring them up as they are revisited.

## What is allowed to be identical

Legal, affiliate, and pricing boilerplate is *supposed* to be identical across
every guide, word for word — the affiliate disclosure, the "rate at checkout is
the only rate that applies" line, the trademark note, the DOT/BTS methodology
line, and the CTA button labels. Consistency there is a compliance feature, not
laziness. The July 2026 audit found those are the only sentences shared across
5+ guides, which is exactly right.

Do not "vary" the disclosure language to make guides feel more distinct.

## Audit, July 27 2026

- 30 guides live in `site/destinations/`.
- 9 sentences appear in 5+ guides. All 9 are legal/affiliate boilerplate or
  button labels. **No editorial boilerplate found** — the voice is already
  city-specific.
- Average length 627 words — the real weakness. Depth, not sameness, is the gap.

## Expansion order

Guides follow the origin expansion, not the other way round. When an airport's
top-30 list goes live (`ORIGIN_DESTS` in `scripts/update_deals.py`), any city on
that list without a guide gets one written before the guide button can appear
for it — `Finder.GUIDES` in `site/js/finder.js` is the single list of written
guides, and a city missing from it simply shows no guide link rather than a 404.

Next up: Atlanta's top 30 adds **Detroit (DTW)** and **Amsterdam (AMS)**.
Those two need guides written before their buttons light up.
