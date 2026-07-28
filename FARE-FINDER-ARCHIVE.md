# Fare Finder — ARCHIVED July 28, 2026

**Status: removed from the site. Code is intact in the repo and dormant.**
Nothing was deleted from git. This file is everything needed to bring it back,
plus the reason it was pulled, so the decision does not get re-litigated from
memory in six months.

Last live commit with the Finder on the site: **c328fca**.

---

## Why it was pulled

Not a bug. Not a UI problem. The data source is too thin to answer the
question the feature promises.

Travelpayouts' affiliate data API is a **cache of fares real people searched
on Aviasales**, not an inventory feed. Route coverage therefore tracks how
often that route gets searched, which has nothing to do with what our
audience wants.

Measured from `site/data/idx-CLT.json`, generated 2026-07-28T09:17 (this is
the whole Charlotte index, 1,252 rows across 25 destinations):

| dest | rows | | dest | rows |
|---|---|---|---|---|
| NYC | 522 | | SFO | 4 |
| ORD | 224 | | AUS | 3 |
| DFW | 162 | | FLL | 3 |
| DCA | 138 | | HOU | 3 |
| LON | 52 | | PUJ | 3 |
| PAR | 48 | | CUN | 2 |
| SEA | 22 | | MCO | 2 |
| LAS | 19 | | MSY | 2 |
| MIA | 11 | | PHX | 2 |
| LAX | 10 | | NAS | 1 |
| BOS | 5 | | ROM | 1 |
| SJU | 5 | | | |
| DEN | 4 | | | |
| PHL | 4 | | | |

Zero cached fares at all: **TPA, BNA, MBJ, AUA, GCM** (5 of the 30 tracked).

Six destinations hold 1,146 of the 1,252 rows. **Ninety two percent of the
data sits in six cities.** Thirteen destinations have fewer than five rows.

The pipeline is not losing anything. The July 28 manual probe of every TP
endpoint for CLT to LAS counted 19 composed rows, and the index holds exactly
19 for LAS. It extracts the entire well.

The cruel shape of it: the six data-rich routes (NYC, DCA, ORD, LAX, LON,
PAR) are almost exactly the six routes **benched** off the deal board for
having no honest discount story. The routes with data are the ones we cannot
sell, and the routes we sell have no data.

**What a visitor actually got:** a real search on 4 to 6 routes, a thin one on
another 4, and one to five results on everything else no matter how broad the
search. A six month, any length, any day, any stops, $1,500 budget search for
Austin returned 3 trips. That is the entire Austin cache, not a filter effect.

### Doors checked and closed (July 28, 2026)

- **Amadeus Self-Service: dead.** Portal fully decommissioned July 17, 2026;
  existing keys disabled. Only Amadeus Enterprise survives (contract, account
  manager). Do not recommend it again.
- **TP real-time Flight Search API:** gated at **50,000 MAU**, plus traffic
  screenshots, written justification, and UI prototypes. Also 30 to 60s per
  search and 100 requests/hour per user IP.
- **Kiwi via Travelpayouts:** same **50,000 MAU** gate. Its
  `nights_in_dst_from` / `nights_in_dst_to` params are literally the trip
  length filter server-side, so this is the right target once traffic exists.
- **Duffel:** self-serve signup, but 120 searches/60s and they expect you to
  sell the ticket through them, which fights the affiliate model.

**Traffic is the unlock, not the API.** Both real options gate at 50k MAU.
The TP real-time application is **on hold, not sent** — a "no" on record makes
the later "yes" harder.

---

## What replaced it

A single prominent panel on the homepage: **SEARCH EVERY FLIGHT FROM <ORIGIN>**,
linking to a tracked Aviasales search that carries the Travelpayouts marker.
It follows the origin chip, so picking ATL changes the link.

This is strictly better than what the Finder delivered on thin routes: the
visitor reaches a search that genuinely has every flight, and the click still
pays. It was always the honest answer, it was just buried at the bottom of a
results list as SEE EVERY FLIGHT.

---

## Everything that made up the feature

### Files still in the repo, dormant

| path | state |
|---|---|
| `site/js/finder.js` | **kept, no longer loaded by any page.** ~1,100 lines, the whole feature |
| `site/css/finder.css` | kept, still linked (also styles shared board bits — check before deleting) |
| `worker/custom-origin.js` | kept, Worker still deployed and live |
| `scripts/build_index.py` | kept, nightly workflow still runs |
| `site/data/idx-*.json` | kept, still regenerated nightly |
| `.github/workflows/deploy-worker.yml` | kept, unchanged |
| nightly fare index workflow | **still running** (10 7 * * *, all 10 origins) |

### Removed from the site

- `site/search.html` — deleted. `/search.html` and `/finder.html` now 301 to `/`
  via `site/_redirects`.
- `index.html`: the DEAL BOARD / FARE FINDER tab strip, the `#paneFind`
  tabpanel and its `<section id="finder">`, the `js/finder.js` script tag,
  the `window.DD_LIVE_URL` line, the tab-switching IIFE, and the FARE FINDER
  nav link.
- The `#paneBoard` wrapper div was left in place. It is inert and keeps the
  diff small.

### Live infrastructure still standing

- Worker: **https://departsdaily-fares.jmmcle95.workers.dev** (CF account
  jmmcle95@gmail.com, `TP_TOKEN` as a Worker secret, deployed by the
  "Deploy fares Worker" workflow using `CF_API_TOKEN`).
- Endpoint: `GET /api/fares?origin=CLT&dest=MIA&months=3&fresh=1`
- Cache API: 10 min fresh, 12h custom-origin. CORS `*`. LIMIT 400/request.
- Window scoping is `months + 1`, capped at 6 (the 50-subrequest ceiling).

---

## How to bring it back

1. `git show c328fca -- site/search.html > site/search.html`
2. In `index.html`, restore from the same commit: the tab strip, the
   `#paneFind` block, `window.DD_LIVE_URL`, the `js/finder.js` script tag,
   the tab IIFE, and the nav link.
3. Remove the `/search.html` and `/finder.html` rules from `site/_redirects`.
4. Confirm the Worker still answers and the nightly index is still building.
5. Verify a rendered affiliate `href` in a live page carries `marker=755800`.
   Never verify by reading the code that builds it (see the money bug below).

**Before restoring, ask the only question that matters: has the data source
changed?** If it is still the TP data cache, the feature will be exactly as
thin as it was on July 28 and pulling it back in accomplishes nothing.

---

## Behaviour contract as it stood at removal

Preserved so a rebuild does not have to rediscover any of this.

### WHEN — three modes, never ambiguous

| mode | means | inputs |
|---|---|---|
| `window` | anywhere in the next N months | months dropdown |
| `range` | leave any day between two dates, stay TRIP LENGTH | earliest / latest departure |
| `exact` | leave this day, come home that day | depart / return |

- Inputs **relabel themselves** per mode and carry a sentence saying which
  question they answer.
- `exact` derives nights from the gap and **locks TRIP LENGTH, dimmed not
  hidden**, so the number stays visible and the reason is on screen.
- Bad input is named, never swallowed: return on/before departure, over 30
  nights, only one date filled.
- The legacy mode string `"dates"` is still accepted as `range` so saved
  links keep working.
- `monthsParam()` must reach the **last day a visitor could travel** = latest
  departure plus longest stay, not just the latest departure.

### TRIP LENGTH
Always on. "Any length" is the first dropdown option. `S.lenOn` does not
exist; anything testing whether the filter is active tests the range itself
(`lo > 1 || hi < 30`).

### LEAVE ON / COME BACK
- Both rows start with **nothing selected**. Empty means any day, not an
  impossible one. `search()` tests `S.out.length && !S.out.includes(...)`.
- Deselecting the last day is allowed and widens back out.
- Auto-filled reachable return days are marked AUTO (dashed amber); a
  hand-picked set switches `retTouched` on and auto-fill stops.
- An arithmetically unreachable return day is struck through and disabled,
  never left silently killing every result.

### Results
- **Top 10, strictly cheapest first** (`CAP`). Rank numbers are positions in a
  price-sorted list, never a rating.
- Count reports matched vs shown separately: `24 TRIPS · TOP 10 CHEAPEST`.
  The cap is never a hidden filter.
- **Never a bare zero.** The relaxation ladder loosens one notch at a time and
  **names every rung applied** on screen. Rungs in order: nights ±3 → any day
  of week → time filters off → any stops → any trip length → no budget cap →
  wider window. Same-group rungs replace their earlier label.
- As of commit **c328fca** the ladder keeps loosening until the list is
  **full at 10**, not merely non-empty, and stops early only when the cache is
  genuinely exhausted. `searchBest` returns `exact` (how many met the filters
  untouched) so the banner distinguishes three cases: filled to ten from N
  exact matches, nothing matched at all, and "this is everything we hold".
- Every result set ends with **SEE EVERY FLIGHT**, a real Aviasales search
  prefilled with the route and dates, cheapest first, with the chosen dates
  printed on the button.

### Honesty rules that outranked any UI change
- Unknown times shown as unknown, never invented. Arrivals crossing midnight
  labelled +1 and described as "next day or later".
- Composed one-way sums labelled **TWO ONE-WAYS** — not a ticket anyone sells.
- FRESH PULL is a cache re-read, never exhaustive live inventory. The
  click-through runs the real search; checkout price is the only price.
- A relaxed search always says which filters were loosened.
- Every outbound flight link carries the Travelpayouts marker.

---

## The money bug, so it is never repeated

`const AFF = {...}` at the top level of a classic script binds in the global
**declarative** scope and **never lands on `window`**. finder.js guarded with
`window.AFF && AFF.tpMarker`, saw `undefined`, and fell through to an
untracked link. **Every Fare Finder flight click from launch until July 28
earned nothing.** Board rows were unaffected (different code path).

Fixed in commit `dc05020`: `affiliates.js` now ends with `window.AFF = AFF;`
and `affLink` reads both spellings.

**Rule: never guard a global with `window.X` when X was declared `const`/`let`.
Test an affiliate link's actual href in a real page, not the code that builds
it.**

---

## Other hard-won gotchas worth keeping

- **Cloudflare Pages was serving `/js/*` and `/css/*` with `max-age=14400`.**
  A deployed fix looks identical to a broken one from a stale tab. Fixed in
  `site/_headers` (commit `99ee868`) with `max-age=0, must-revalidate`. When
  verifying a deploy, fetch with `{cache:'no-store'}` and check for a string
  unique to the change before concluding anything.
- **Worker month-window bug:** it queried months 1..N for an N-month window,
  but a 2-month window runs 61 days out and lands in the **third** calendar
  month. Fixed to `months + 1`, capped at 6.
- **Month-matrix rows are one-way** — `return_date` is always empty. Requiring
  a return date silently produced `matrix: 0` on every route. They must feed
  the leg stores and compose into labelled TWO ONE-WAYS trips.
- **Time slider gotcha:** read handle values BEFORE raising `min`, or the
  browser silently clamps and you report "nothing moved".
- **Trip length select gotcha:** a non-preset range needs an option with a
  REAL value (`"custom"`). Disabled options cannot be set via `.value`,
  Chromium paints a selected `hidden` option blank, and assigning `""` sets
  `selectedIndex` to -1.
- **Local testing:** Playwright + Chromium are preinstalled. Serve `site/`
  over a local http server and drive it headless. To exercise the fresh-pull
  path without network access, `page.route('**/*.workers.dev/**')` and fulfil
  with a captured Worker JSON.
