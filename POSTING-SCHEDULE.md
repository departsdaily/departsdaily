# The weekly posting plan

**Owner's rule, July 28 2026.** People dream on weekends and buy on weekdays. So we sell early in the week and inspire late. Monday is the highest booking day, Saturday the lowest.

Everything below is driven by `config/schedule.json`. Retune that file after four weeks against your own analytics. Your audience beats any industry average.

## The week

| Day | Shape | Trip | Why |
|---|---|---|---|
| Monday | `week` | 6 to 9 nights | Peak booking day. Back at the desk, ready to escape. The money post. |
| Tuesday | `weekend` | 2 to 4 nights | Low stakes, easy yes. |
| Wednesday | `weekend` | 2 to 4 nights | Same, different cities. |
| Thursday | `urgent` | 2 to 4 nights, leaving within 21 days | Weekend getaways with urgency. |
| Friday | `friday` | 2 to 9 nights | Leans on Friday being the cheapest day to book and fly. |
| Saturday | *guide* | falls back to `weekend` | Planned city guide carousel. Renderer not built yet. |
| Sunday | *inspiration* | falls back to `week` | Planned inspiration plus Monday teaser. Renderer not built yet. |
| Every other Sunday | `twoweek` | 12 to 16 nights | ISO even weeks. Twice a month max so it stays special. |

## The safety property that matters

A shape is a **preference, never a filter that costs a deal.**

For every route, `fetch_fares.py` finds two real fares from the same price sorted list:

- the cheapest fare matching today's shape
- the cheapest fare in the wide sanity window, 2 to 14 nights leaving 3 to 150 days out, which is exactly what the board used before this existed

It shows the shaped fare **only when that fare still clears the 12% bar**. Otherwise it falls back to the wide one. So the plan changes *which* honest deal appears. It cannot lower `MIN_DISCOUNT`, pad the board, or knock a route off for having the wrong trip length on a Tuesday.

Verified offline against identical synthetic fares: deal count held at 14 across all four shapes, and `twoweek` fell back on the routes where a long trip did not clear the bar rather than dropping them. Each row carries `on_shape` true or false, and `deals.json` reports how many rows hit the shape, so drift is visible instead of silent.

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
