#!/usr/bin/env python3
"""Departs Daily - fare fetch + verification. Runs daily via GitHub Actions.
Pulls cheapest fares (Travelpayouts data API), scores vs monthly baselines,
applies 6-day no-repeat, flags skips. Writes deals.json.

Origin comes from the ORIGIN env var and defaults to CLT, so an unqualified run
behaves exactly as it did before the pipeline went multi-city."""
import os, sys, json, datetime, urllib.request, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import origins, day_plan, site_fares, index_fares

# WEEKLY PLAN (owner's rule, Jul 28 2026). Monday sells week long trips,
# Tue/Wed sell weekends, Thursday sells urgency, Friday leans on Friday being
# the cheapest day to book, and every other Sunday goes two weeks. The shape
# steers WHICH honest fare each route contributes. It never lowers
# MIN_DISCOUNT, never pads, and never drops a route that had a real deal —
# see pick_offer() below. Config: config/schedule.json.
PLAN = day_plan.plan()

# FOUR SECTIONS EVERY DAY (owner's rule, 2026-08-13). The carousel is no longer
# one trip shape per weekday. Every post carries Long Weekend, Week Long, Two
# Weeks and Cheapest, seven rows each, one slide each. PLAN above is kept
# because pipeline/render_reel.py still resolves a single daily shape for the
# reel rotation — it no longer steers the carousel.
SECTIONS = day_plan.sections()

TP_TOKEN = os.environ["TP_TOKEN"]
ORIGIN = origins.origin_code()
PATHS = origins.paths(ORIGIN)
ROUTES = origins.baselines(ORIGIN)
HISTORY_FILE = PATHS["history"]
# 3, not 6: the board now carries 5+ cities a day from a ~24-city pool, and a
# 6-day lockout at that rate (5 x 6 = 30) would starve it mathematically.
# NO-REPEAT IS A PREFERENCE, NOT AN HONESTY RULE (Jul 29 2026).
# It exists so the board doesn't show Miami seven days running. It was
# implemented as a HARD filter, and at a 7-row target that quietly guarantees
# failure: 7 rows x 3 days = 21 of CLT's 24 eligible routes locked out, leaving
# 3 routes to fill 7 slots. That is most of why today posted 3.
#
# So: variety first, deals always. Routes not shown recently are preferred, and
# a recently-shown route is only re-used when the board would otherwise come up
# short of BOARD_TARGET. A repeated route is still a REAL deal that still
# cleared the 12% bar — nothing about re-showing it is dishonest, whereas an
# empty slot filled with an overpayment would be. The 12% bar is untouched.
NO_REPEAT_DAYS = int(os.environ.get("NO_REPEAT_DAYS", "3"))
BOARD_TARGET = int(os.environ.get("BOARD_TARGET", "7"))
MIN_DISCOUNT = 0.12
# DEALS ONLY — owner's rule (Jul 2026): the board never shows a fare that
# isn't a real deal. No filler rows, no "typical fare" rows, and no SKIP row
# (it showcased an overpayment). Every fare clearing MIN_DISCOUNT makes the
# board, up to BOARD_MAX. That cap is no longer a slide-space limit: the
# renderer paginates the board across as many slides as the deals need
# (7 rows each), so a 14-deal day simply posts two deal slides. More real
# deals is always better — the only fixed rule is that exactly one slide in
# the post sells the site, and it is the last one.
#
# TARGET: at least a full 7-row first slide every day (owner's rule, Jul 28). We reach it
# by casting a WIDER NET for genuine deals — a deeper month scan, longer trips,
# and a further-out departure window (see cheapest() and the trip-window filter
# below) — NEVER by lowering the 12% bar or padding with non-deals. On a
# genuinely thin market day it still posts fewer real deals rather than an
# overpayment; a day with zero deals posts nothing.
# 14 = two full deal slides. Supply is the real limiter (a thin day still
# clears only 2-3 routes), so this is headroom, not a quota. Never padded.
BOARD_MAX = int(os.environ.get("BOARD_MAX", "14"))
today = datetime.date.today()

def tp(url, params):
    params["token"] = TP_TOKEN
    with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params), timeout=30) as r:
        return json.load(r)

def months_ahead(n):
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            m, y = 1, y + 1
    return out


def cheapest(dest):
    """Cheapest round-trip candidates, cheapest first.

    One unscoped query returns only the API's overall-cheapest handful, which
    on 2026-07-27 left 11 of CLT's 24 routes with zero usable candidates.
    Month-scoped queries (same trick as build_index.py) surface the cheapest
    fares in each month of the posting window, so a route with nothing in the
    global top-30 can still field its best August fare.

    WIDER NET (Jul 28 2026): scan 6 months out (was 4) and pull 50 candidates
    per query (was 30), so more routes can field a fare that clears the 12%
    deal bar and the board fills to its 7-row target more often."""
    seen, out, last_err = set(), [], None
    for month in [None] + months_ahead(6):
        params = {"origin": ORIGIN, "destination": dest, "unique": "false",
                  "sorting": "price", "direct": "false", "currency": "usd",
                  "limit": 50, "one_way": "false"}
        if month:
            params["departure_at"] = month
        try:
            data = tp("https://api.travelpayouts.com/aviasales/v3/prices_for_dates",
                      params)
        except Exception as e:
            last_err = e
            continue
        for o in data.get("data", []):
            key = (o.get("departure_at"), o.get("return_at"), o.get("price"))
            if key in seen:
                continue
            seen.add(key)
            out.append(o)
    if not out and last_err is not None:
        raise last_err
    out.sort(key=lambda o: o.get("price") or 1e9)
    return out

def _clock(dt):
    """12-hour clock, same format the site board prints."""
    h = dt.hour % 12 or 12
    return "%d:%02d%s" % (h, dt.minute, "AM" if dt.hour < 12 else "PM")


def dep_time(stamp):
    """Departure clock time straight off the fare's own timestamp."""
    try:
        dt = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return ""
    return "" if (dt.hour == 0 and dt.minute == 0) else _clock(dt)


def arr_time(stamp, duration_min):
    """Arrival = departure + leg duration. Identical derivation to
    scripts/update_deals.py and the Fare Finder, so a fare shown on the site
    and the same fare shown on a slide can never disagree.

    Returns "" when the API gave no duration. An unknown arrival is shown as
    unknown, never invented. A leg landing after midnight carries "+1", the
    site's established label for "next day or later"."""
    try:
        dt = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        m = int(duration_min)
    except (AttributeError, TypeError, ValueError):
        return ""
    if m <= 0:
        return ""
    total = dt.hour * 60 + dt.minute + m
    h24, mm = (total % 1440) // 60, total % 60
    h = h24 % 12 or 12
    return "%d:%02d%s%s" % (h, mm, "AM" if h24 < 12 else "PM",
                            "+1" if total >= 1440 else "")


def pick_offer(offers, nights, depart_in, depart_dow=None, return_dow=None):
    """Cheapest offer whose trip length, departure date and (optionally) the
    days of the week it flies out and back on all fit.

    `offers` is already price-sorted, so the first match is the cheapest match.
    A dow set of None means any day. Returns None when nothing fits.
    """
    n_lo, n_hi = nights
    d_lo, d_hi = depart_in
    for cand in offers:
        try:
            dd = datetime.date.fromisoformat(cand["departure_at"][:10])
            rr = datetime.date.fromisoformat((cand.get("return_at") or "")[:10])
        except ValueError:
            continue
        if not (d_lo <= (dd - today).days <= d_hi):
            continue
        if not (n_lo <= (rr - dd).days <= n_hi):
            continue
        if depart_dow is not None and dd.weekday() not in depart_dow:
            continue
        if return_dow is not None and rr.weekday() not in return_dow:
            continue
        return cand
    return None


hist = json.load(open(HISTORY_FILE)) if os.path.exists(HISTORY_FILE) else {}
recent = {d for d, ts in hist.items()
          if (today - datetime.date.fromisoformat(ts)).days < NO_REPEAT_DAYS}

# Why each route did or did not make the board. Written out every run, pass or
# fail, so "why was there no post today" is answerable from the repo instead of
# from a log that expires.
scan = {}

# ONE SET OF FARES (Jul 29 2026, owner's rule). The site board is rebuilt for
# this origin immediately before this script runs (see ig-post.yml), and it
# prices EVERY tracked route. We take that whole set as candidates instead of
# re-querying the API and getting a thinner, different answer — which is how
# the site came to publish 8 rows on a morning the post published 3.
# site_fares refuses anything not stamped today and inside MAX_FARE_AGE_MIN,
# so this can only ever add THIS MORNING's fares.
SITE_OFFERS, site_note = site_fares.load(ORIGIN)
print(f"{ORIGIN} site fares: {site_note}")
if not SITE_OFFERS:
    print(f"::warning::{ORIGIN} is posting without the site snapshot "
          f"({site_note}). Falling back to this pipeline's own fetch.")

INDEX_OFFERS, index_note = index_fares.load(ORIGIN)
print(f"{ORIGIN} index fares: {index_note}")

OFFERS = {}
for code in ROUTES:
    # Recently-shown routes are still PRICED. They are ranked last later, and
    # only reach the board if it would otherwise be short. Skipping them here
    # is what made a short board unrecoverable.
    try:
        offers = cheapest(code)
    except Exception as e:
        offers = []
        if code not in SITE_OFFERS and code not in INDEX_OFFERS:
            scan[code] = {"outcome": "fetch failed", "why": str(e)}
            print(code, "fetch failed", e); continue
        print(code, "own fetch failed, using site/index fares:", e)
    # Three sources, deduped on (out, back, price), cheapest first. All three
    # are reads of the same underlying Aviasales cache queried differently, so
    # the union is strictly more supply than any one of them alone. Every
    # merged offer is still only a CANDIDATE: it has to clear MIN_DISCOUNT
    # against this origin's baseline below to reach the board.
    merged, seen_keys = [], set()
    for o in offers + SITE_OFFERS.get(code, []) + INDEX_OFFERS.get(code, []):
        key = (o.get("departure_at", "")[:10], (o.get("return_at") or "")[:10],
               o.get("price"))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        merged.append(o)
    merged.sort(key=lambda o: o.get("price") or 1e9)
    if not merged:
        scan[code] = {"outcome": "no fares", "why": "the fare cache returned nothing"}
        continue
    OFFERS[code] = merged


def build(plan):
    """Score every fetched route against one section spec. Returns
    (qualifying, rest, scan_rows). Pure: safe to call once per section.

    `plan` needs: nights, depart_in, depart_dow, return_dow, wide, and
    optionally deals_only. A legacy day_plan.plan() dict satisfies it, which is
    what keeps the old single-shape path working."""
    deals, skips, rows = [], [], {}
    for code, offers in OFFERS.items():
        # THREE RUNGS, cheapest real fare at each, all from the same
        # price-sorted list. We take the best rung that still clears the bar:
        #   shape  — today's full shape: trip length AND the days of the week
        #            it flies out and back on (out Thu/Fri, back Sun/Mon for a
        #            long weekend, and so on)
        #   nights — same trip length, any days of the week
        #   wide   — 2-14 nights leaving 3-150 days out, exactly what the
        #            board used before the weekly plan existed
        # Day-of-week rules are what make a "long weekend" an actual long
        # weekend, but they are also the thinnest filter, so they must never
        # be the reason a route with a genuine deal falls off. Hence the ladder.
        # THE LADDER WIDENS THE WINDOW, NEVER THE TRIP LENGTH (2026-08-13).
        # It used to fall all the way back to the wide 2-14 night range, which
        # was safe when one shape owned the whole board and the cover slide
        # could step aside. It is NOT safe now: each section is its own slide
        # with its own title, so a 3 night fare reaching the TWO WEEKS slide
        # would make that slide lie. Trip length is the section's identity and
        # is held fixed; only the day-of-week rule and then the departure
        # window are relaxed.
        rungs = [
            ("shape", pick_offer(offers, plan["nights"], plan["depart_in"],
                                 plan["depart_dow"], plan["return_dow"])),
            ("nights", pick_offer(offers, plan["nights"], plan["depart_in"])),
            ("window", pick_offer(offers, plan["nights"],
                                  plan["wide"]["depart_in"])),
        ]
        if all(c is None for _, c in rungs):
            n0, n1 = plan["nights"]
            d0, d1 = plan["wide"]["depart_in"]
            rows[code] = {"outcome": "no fares in window",
                          "why": f"{len(offers)} offers, none leaving {d0}-{d1} "
                                 f"days out for a {n0}-{n1} night trip"}
            continue

        def score(cand, _code=code):
            p = round(cand["price"])
            dp = datetime.date.fromisoformat(cand["departure_at"][:10])
            b = ROUTES[_code]["m"][dp.month - 1]
            return p, dp, b, 1 - p / b

        o = rung = None
        for name, cand in rungs:
            if cand is not None and score(cand)[3] >= MIN_DISCOUNT:
                o, rung = cand, name
                break
        if o is None:                   # nothing clears the bar anywhere;
            for name, cand in rungs:    # keep the best available so the scan
                if cand is not None:    # can still report why it missed
                    o, rung = cand, name
                    break
        on_shape = rung == "shape"
        price, dep, base, disc = score(o)
        ret = (o.get("return_at") or "")[:10]
        nights = (datetime.date.fromisoformat(ret) - dep).days if ret else None
        row = {"to": code, "city": ROUTES[code]["city"], "price": price,
               "d1": o["departure_at"][:10], "d2": ret,
               "airline": o.get("airline", ""), "stops": o.get("transfers", 0),
               # Times only when the fare actually carried them. A slide has
               # never printed an invented time and must not start now.
               #
               # These used to read o["dep_time"] / o["ret_time"] / o["arr_time"]
               # / o["ret_arr"] — none of which are keys Travelpayouts returns.
               # Every one was silently "" on every deal ever posted, so the
               # Instagram board showed dates while the website showed full
               # departure and arrival times for the same fare. Derived here
               # exactly the way scripts/update_deals.py derives them.
               "dep": dep_time(o.get("departure_at")),
               "rdep": dep_time(o.get("return_at")),
               "arr": arr_time(o.get("departure_at"), o.get("duration_to")),
               "rarr": arr_time(o.get("return_at"), o.get("duration_back")),
               "baseline": base, "disc": round(disc * 100),
               "nights": nights, "on_shape": on_shape, "rung": rung,
               "link": "https://www.aviasales.com" + (o.get("link") or "") + "&marker=755800"}
        rows[code] = {"outcome": "qualified" if disc >= MIN_DISCOUNT else "not a deal",
                      "price": price, "typical": base, "disc_pct": round(disc * 100),
                      "d1": row["d1"], "d2": row["d2"],
                      "nights": nights, "on_shape": on_shape, "rung": rung}
        row["deal"] = disc >= MIN_DISCOUNT
        (deals if disc >= MIN_DISCOUNT else skips).append(row)
    deals.sort(key=lambda x: -x["disc"])
    skips.sort(key=lambda x: x["price"])
    return deals, skips, rows


def fill(spec, used_flights):
    """One section's rows, honestly.

    Deals-only sections take fares that cleared MIN_DISCOUNT, best discount
    first. The CHEAPEST section takes the lowest real prices at any discount —
    it claims nothing, which is exactly why it can always fill its slide and
    carry a thin day. A row there still wears the green badge if it genuinely
    cleared the bar, and stays silent if it did not.

    `used_flights` de-duplicates the EXACT SAME FLIGHT across sections: the
    same city on different dates is a different trip and is allowed (owner's
    call, 2026-08-13), but printing one identical fare twice in one post is
    just a repeated row.
    """
    qualifying, rest, rows = build(spec)
    bar = spec.get("min_discount", MIN_DISCOUNT)
    # Rows that cleared MIN_DISCOUNT are already in `qualifying`. A section with
    # a lower bar may also take from `rest` — but never below its own bar, and
    # never below zero. "Cheapest" is a promise about price, not permission to
    # print an overpayment.
    pool = qualifying + [r for r in rest if r["disc"] >= round(bar * 100)] \
           if bar < MIN_DISCOUNT else list(qualifying)
    if spec.get("sort") == "price":
        pool = sorted(pool, key=lambda x: x["price"])
    seen_dest = set()
    picked = []
    # Variety first, then fill. Every deal in `pool` for a deals-only section
    # already cleared MIN_DISCOUNT, so a backfilled repeat is a genuine deal —
    # just one we also showed in the last few days. Showing Miami twice in a
    # week beats showing an overpayment once.
    for wave in (0, 1):
        for r in pool:
            if len(picked) >= spec["rows"]:
                break
            if r["to"] in seen_dest:
                continue
            if (r["to"], r["d1"], r["d2"]) in used_flights:
                continue
            if wave == 0 and r["to"] in recent:
                continue
            if wave == 1:
                r["repeat"] = True
                r["last_shown"] = hist.get(r["to"])
            seen_dest.add(r["to"])
            used_flights.add((r["to"], r["d1"], r["d2"]))
            r["section"] = spec["key"]
            picked.append(r)
    return picked, rows


# ONE PASS PER SECTION. Each is scored independently against the same fetched
# offers, so Long Weekend and Two Weeks can pick different fares for the same
# city without competing for a single slot.
used_flights = set()
sections, deals = [], []
for spec in SECTIONS:
    picked, rows = fill(spec, used_flights)
    # The scan is the "why was there no post today" record. Merge, never
    # overwrite: a later section reporting "no fares in window" must not erase
    # an earlier section's "qualified" for the same route.
    for code, row in rows.items():
        row = dict(row, section=spec["key"])
        if scan.get(code, {}).get("outcome") != "qualified":
            scan[code] = row
    n_deal = sum(1 for r in picked if r.get("deal"))
    sections.append({"key": spec["key"], "cover": spec["cover"],
                     "tag": spec.get("tag", "ROUND TRIP"),
                     "angle": spec["angle"], "nights": list(spec["nights"]),
                     "deals_only": spec["deals_only"], "rows_target": spec["rows"],
                     "n": len(picked), "n_deals": n_deal,
                     "rungs": {r: sum(1 for d in picked if d.get("rung") == r)
                               for r in ("shape", "nights", "window")},
                     "deals": picked})
    deals.extend(picked)
    short = "" if len(picked) >= spec["rows"] else \
            f"  SHORT by {spec['rows'] - len(picked)}"
    print(f"{ORIGIN} section {spec['key']:9} {len(picked)}/{spec['rows']} rows, "
          f"{n_deal} of them real deals{short}")
    if len(picked) < spec["rows"]:
        print(f"::warning::{ORIGIN} {spec['key']} filled {len(picked)}/"
              f"{spec['rows']} rows. Not padded — every row cleared the "
              f"{MIN_DISCOUNT*100:.0f}% bar. Supply problem, not a code problem: "
              f"{len(ROUTES)} routes eligible.")

board = {"date": today.isoformat(), "origin": ORIGIN,
         # Flat union, section order. Everything downstream (the caption, the
         # stories, the reel) still reads board["deals"], so none of it had to
         # change — each row now just carries which section it came from.
         "deals": deals, "n_deals": sum(1 for d in deals if d.get("deal")),
         "n_rows": len(deals),
         "sections": sections,
         "skip": None,
         "plan": {"shape": PLAN["shape"], "cover": PLAN["cover"],
                  "angle": PLAN["angle"], "content": PLAN["content"],
                  "nights": list(PLAN["nights"]),
                  "sections": [s["key"] for s in sections],
                  "on_shape": sum(1 for d in deals if d.get("on_shape")),
                  "rungs": {r: sum(1 for d in deals if d.get("rung") == r)
                            for r in ("shape", "nights", "window")}}}
os.makedirs("out", exist_ok=True)
counts = {}
for v in scan.values():
    counts[v["outcome"]] = counts.get(v["outcome"], 0) + 1
json.dump({"date": today.isoformat(), "origin": ORIGIN,
           "routes_considered": len(ROUTES), "min_discount_pct": MIN_DISCOUNT * 100,
           "summary": counts, "routes": scan},
          open(f"out/scan-{ORIGIN}.json", "w"), indent=1)
print(f"{ORIGIN} sections: " + ", ".join(
    f"{s['key']} {s['n']}/{s['rows_target']}" for s in sections))
print(f"{ORIGIN} scan:", counts)
want = sum(s["rows_target"] for s in sections)
if len(deals) < want:
    print(f"::warning::{ORIGIN} filled {len(deals)}/{want} rows across "
          f"{len(sections)} sections. Not padded. {len(ROUTES)} routes eligible.")
for c, v in sorted(scan.items(), key=lambda kv: kv[1].get("disc_pct", -999), reverse=True):
    print(f"  {c:4} {v['outcome']:18}", v.get("why") or
          f"${v.get('price')} vs typical ${v.get('typical')} = {v.get('disc_pct')}%")

# The deal sections may all come up empty on a genuinely dead market day, and
# that is allowed to stop the post — a board with nothing on it is not a post.
# The CHEAPEST section claims no discount, so it alone is NOT enough to justify
# publishing: if no section found a single real deal, there is nothing to say.
if not board["deals"]:
    print(f"FATAL: {ORIGIN} produced no fares at all — nothing to post today.")
    raise SystemExit(1)
if not board["n_deals"]:
    print(f"FATAL: {ORIGIN} found cheap fares but not one real deal across any "
          f"section. The post sells verified deals, so there is nothing to "
          f"post today.")
    raise SystemExit(1)
json.dump(board, open(PATHS["deals"], "w"), indent=1)
for d in board["deals"]:
    hist[d["to"]] = today.isoformat()
os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
json.dump(hist, open(HISTORY_FILE, "w"), indent=1)
for s_ in sections:
    print(f"{ORIGIN} {s_['cover']}:", [(d["to"], f"${d['price']}",
          f"{d['disc']}%" if d.get("deal") else "-") for d in s_["deals"]])
