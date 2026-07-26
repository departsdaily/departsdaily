# Deals of the Week — diagnosis & fix

Checked against the live `site/js/deals-data.js` generated 2026-07-26 14:57 EDT.

## What was wrong

**1. Wrong airline names — visible to visitors**
8 of 10 weekly rows said **Frontier**, including **London $723**. Frontier operates no
transatlantic service. `prices_for_dates` returns the *first/validating* carrier, not the
operator of every leg, so a one-stop CLT→LON at that price is almost certainly a
self-transfer itinerary whose first hop is Frontier.

Two separate problems: the name is wrong, and a self-transfer connection is not protected
if the first leg is late. That is exactly the kind of claim a deals site gets held to.

**2. The weekly board was not weekly**
6 of 10 weekly rows were byte-identical to the daily board. Both were cut from the same
hourly snapshot, so "DEALS OF THE WEEK — TOP 10" actually meant "top 10 right now, plus
four." The label was not true.

**3. Expiry gaps**
`weekExp` was set to the current day, and weekly rows carried no `exp` at all — so if the
job stalled, weekly fares had nothing to expire them.

**Discount math was clean.** Every badge verified against the DOT/BTS averages in `ROUTES`.
Domestic 50–64% below average, international 10–37%. Nothing overstated.

## What changed in `scripts/update_deals.py`

| Fix | Behaviour |
|---|---|
| Airline honesty | `al` is only set when `stops == 0`. Connecting itineraries show no carrier rather than a wrong one. |
| Real weekly board | New `state/week_best.json` keeps the best fare per city **so far this week**. Each hourly run improves it; it resets Monday. The weekly board is now genuinely the week's best. |
| Weekly expiry | Weekly rows now carry `exp` = Sunday, so they expire with the week. |

Verified by dry run: a Monday $152 Miami fare survives a Wednesday $210; a Monday $723
London improves to $640 on Wednesday; the whole thing resets the next Monday.

## One thing to do when you deploy

`state/week_best.json` must be committed by the hourly workflow, the same way
`state/baselines.json` already is. If `state/` is not in the commit step, the weekly
board silently reverts to snapshot behaviour — it will look fine, and be wrong again.

## Still open — worth a look

**20 of 30 routes returned fares.** A third of the board is empty every run. Misses are
mostly international (MBJ, NAS, AUA, GCM). Same thin-cache problem as the Fare Finder
index. Worth densifying with the month-matrix endpoint.

**Self-transfer itineraries.** Beyond the label, consider flagging one-stop international
fares where legs are on unrelated carriers — "SELF-TRANSFER · connection not protected".
Honest, and it is the kind of detail that earns repeat visitors.
