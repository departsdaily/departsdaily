# The weekly posting plan

**Owner's rule, July 28 2026.** People dream on weekends and buy on weekdays. So we sell early in the week and inspire late. Monday is the highest booking day, Saturday the lowest.

Everything below is driven by `config/schedule.json`. Retune that file after four weeks against your own analytics. Your audience beats any industry average.

## The week

| Day | Shape | Trip | Why |
|---|---|---|---|
| Monday | `week` | 7 to 10 nights, out Thu to Sun, back Fri to Mon | Peak booking day. The money post. |
| Tuesday | `weekend` | 2 to 4 nights, out Thu or Fri, back Sun or Mon | Low stakes, easy yes. |
| Wednesday | `weekend` | same | Same, different cities. |
| Thursday | `urgent` | same shape, leaving within 30 days | Weekend getaways with urgency. |
| Friday | `friday` | 2 to 9 nights, out Thu to Sat | Leans on Friday being the cheapest day to book and fly. |
| Saturday | *guide* | falls back to `weekend` | Planned city guide carousel. Renderer not built yet. |
| Sunday | *inspiration* | falls back to `week` | Planned inspiration plus Monday teaser. Renderer not built yet. |
| Every other Sunday | `twoweek` | 12 to 17 nights, out Thu to Sun, back Fri to Mon | ISO even weeks. Twice a month max so it stays special. |

## Reels — one a day, per account

Added Jul 29 2026. Separate from the board plan above, on its own config
(`config/reels.json`) and its own workflow (`ig-reel.yml`), firing at
**11:40 AM ET** — a gap between the morning carousel and the story drip slots.
Shipped at two a day and cut to one on Jul 30, to keep the volume step change
small while both accounts are young. Live on both accounts since Aug 3.

Reels are built from the SAME board the morning carousel posted, never a fresh
fetch, so nothing in a day's feed can contradict anything else in it. Three
shapes rotate: the whole board, one spotlight deal with the price counting down
from typical, and three destination cards. Full writeup and failure modes in
`REELS.md`.

One thing to know going in: the publishing API cannot attach Instagram music,
so reels are silent until licensed audio is dropped into `assets/reel-audio/`.

## The three rung ladder

A shape is a **preference, never a filter that costs a deal.** For every route, `fetch_fares.py` finds the cheapest real fare at each of three rungs and takes the best one that still clears the 12% bar:

1. **shape** — the full thing. Trip length *and* the days of the week it flies out and back on.
2. **nights** — right trip length, any days.
3. **wide** — 2 to 14 nights leaving 3 to 150 days out. Exactly what the board used before any of this existed.

Day of week rules are what make a long weekend an actual long weekend. They are also the thinnest filter, so they must never be the reason a route with a genuine deal falls off. Hence the ladder. Every row records which rung it landed on in `row["rung"]`, and the board reports the split, so drift is visible instead of silent.

## Measured on real fares

Replayed against the cached fare index for all ten cities (Jul 28, 263 routes). **Deal count came out at 70 in every single shape** — the ladder fully protects supply. What changes is how often the board hits the shape exactly:

| shape | on shape | right length, wrong days | fallback |
|---|---|---|---|
| friday | 86% | 11% | 3% |
| weekend | 69% | 16% | 16% |
| week | 50% | 19% | 31% |
| urgent | 47% | 19% | 34% |
| twoweek | 41% | 7% | 51% |

Thursday's urgency post was the weak one at 30% until the departure window went from 21 days to 30. The tight window was the problem, not the day rules. Thirty days still reads as soon.

## The two week guard

Two week trips are genuinely scarce in the fare cache. Charlotte specifically had **zero** on shape in every variant tested. A cover slide reading TWO WEEKS GONE over a pile of long weekend fares is a claim the board does not support, so `twoweek` carries `min_on_shape: 2` and `fallback_shape: "week"`. Under two matching rows, the whole board rebuilds on the week shape and the cover changes with it. Verified: with no qualifying two week fare, the run printed the step down and posted WEEK LONG ESCAPES instead.

## The Friday claim, sourced

The Friday hook is real, and it is worth stating precisely because half stating it is the kind of thing that gets picked apart in comments. From Expedia's 2026 Air Hacks Report, released February 17 2026:

- Friday is the cheapest day to **book**, about 3% under Sunday, which is the most expensive
- Friday is the cheapest day to **fly** overall, up to 8% under a Sunday departure
- **But** for US domestic specifically, Tuesday is the cheapest day to actually fly, roughly 14% under Sunday

The caption says all three. Departs Daily is a site whose whole edge is claims that survive scrutiny, so the caveat ships with the hook.

Note also that "Monday is the highest booking day, Saturday the lowest" is about booking **volume**, which is audience behaviour, not price. It shapes when we post. It never goes on a slide as a fare claim.

## Saturday and Sunday are not built

The city guide carousel is a different content type from a fare board, and the pipeline cannot render it yet:

- 9 pages: hook, two tour pages, two food pages, three hotel tiers, one call to action at the end
- needs **real photos of the city**, and the current renderer draws navy panels with PIL, no photography at all
- so it needs a licensed image source, which is a decision before it is code

Until that exists, Saturday and Sunday post a normal board using the fallback shape in the table above. `config/schedule.json` already carries `"content": "guide"` and `"content": "inspiration"` on those days, and the resolver passes it through, so the renderer can start honouring it the day it can draw it.

## Knobs

```
POST_SHAPE=twoweek   force a shape for one run
POST_DATE=2026-08-09 resolve the plan for another date, for testing
python pipeline/day_plan.py    print today's plan and why
```

## Also fixed here

The Instagram caption still pitched the **Fare Finder**, which was removed from the site in the previous session. Every caption since then advertised a page that redirects away. Replaced with the search button that is actually on the site now.
