#!/usr/bin/env python3
"""Departs Daily - fare fetch + verification. Runs daily via GitHub Actions.
Pulls cheapest fares (Travelpayouts data API), scores vs monthly baselines,
applies 6-day no-repeat, flags skips. Writes deals.json.

Origin comes from the ORIGIN env var and defaults to CLT, so an unqualified run
behaves exactly as it did before the pipeline went multi-city."""
import os, sys, json, datetime, urllib.request, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import origins, day_plan

# WEEKLY PLAN (owner's rule, Jul 28 2026). Monday sells week long trips,
# Tue/Wed sell weekends, Thursday sells urgency, Friday leans on Friday being
# the cheapest day to book, and every other Sunday goes two weeks. The shape
# steers WHICH honest fare each route contributes. It never lowers
# MIN_DISCOUNT, never pads, and never drops a route that had a real deal —
# see pick_offer() below. Config: config/schedule.json.
PLAN = day_plan.plan()

TP_TOKEN = os.environ["TP_TOKEN"]
ORIGIN = origins.origin_code()
PATHS = origins.paths(ORIGIN)
ROUTES = origins.baselines(ORIGIN)
HISTORY_FILE = PATHS["history"]
# 3, not 6: the board now carries 5+ cities a day from a ~24-city pool, and a
# 6-day lockout at that rate (5 x 6 = 30) would starve it mathematically.
NO_REPEAT_DAYS = int(os.environ.get("NO_REPEAT_DAYS", "3"))
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

def pick_offer(offers, nights, depart_in):
    """Cheapest offer whose trip length and departure date fit a window.

    `offers` is already price-sorted, so the first match is the cheapest match.
    Returns None when nothing in the list fits.
    """
    n_lo, n_hi = nights
    d_lo, d_hi = depart_in
    for cand in offers:
        try:
            dd = datetime.date.fromisoformat(cand["departure_at"][:10])
            rr = datetime.date.fromisoformat((cand.get("return_at") or "")[:10])
        except ValueError:
            continue
        if d_lo <= (dd - today).days <= d_hi and n_lo <= (rr - dd).days <= n_hi:
            return cand
    return None


hist = json.load(open(HISTORY_FILE)) if os.path.exists(HISTORY_FILE) else {}
recent = {d for d, ts in hist.items()
          if (today - datetime.date.fromisoformat(ts)).days < NO_REPEAT_DAYS}

# Why each route did or did not make the board. Written out every run, pass or
# fail, so "why was there no post today" is answerable from the repo instead of
# from a log that expires.
scan = {}

deals, skips = [], []
for code in ROUTES:
    if code in recent:
        scan[code] = {"outcome": "locked out", "why": f"posted {hist.get(code)}"}
        continue
    try:
        offers = cheapest(code)
    except Exception as e:
        scan[code] = {"outcome": "fetch failed", "why": str(e)}
        print(code, "fetch failed", e); continue
    if not offers:
        scan[code] = {"outcome": "no fares", "why": "the fare cache returned nothing"}
        continue
    # Two candidates per route, both real fares from the same price-sorted list:
    #   shaped — cheapest fare matching TODAY'S trip shape (Monday wants a week,
    #            Tuesday wants a long weekend, and so on)
    #   wide   — cheapest fare in the broad sanity window (2-14 nights, leaving
    #            3-150 days out), which is exactly what the board used before
    #            the weekly plan existed
    # We show the shaped fare when it still clears the 12% bar. If it doesn't,
    # we fall back to the wide fare. So the plan can change WHICH honest deal
    # appears, but a route that had a genuine deal can never lose its place
    # because of what day of the week it is.
    shaped = pick_offer(offers, PLAN["nights"], PLAN["depart_in"])
    wide = pick_offer(offers, PLAN["wide"]["nights"], PLAN["wide"]["depart_in"])
    if shaped is None and wide is None:
        n0, n1 = PLAN["wide"]["nights"]
        d0, d1 = PLAN["wide"]["depart_in"]
        scan[code] = {"outcome": "no fares in window",
                      "why": f"{len(offers)} offers, none leaving {d0}-{d1} days out "
                             f"for a {n0}-{n1} night trip"}
        continue

    def score(cand):
        p = round(cand["price"])
        dp = datetime.date.fromisoformat(cand["departure_at"][:10])
        b = ROUTES[code]["m"][dp.month - 1]
        return p, dp, b, 1 - p / b

    on_shape = False
    if shaped is not None and score(shaped)[3] >= MIN_DISCOUNT:
        o, on_shape = shaped, True
    elif wide is not None:
        o = wide
    else:
        o, on_shape = shaped, True
    price, dep, base, disc = score(o)
    ret = (o.get("return_at") or "")[:10]
    nights = (datetime.date.fromisoformat(ret) - dep).days if ret else None
    row = {"to": code, "city": ROUTES[code]["city"], "price": price,
           "d1": o["departure_at"][:10], "d2": ret,
           "airline": o.get("airline", ""), "stops": o.get("transfers", 0),
           "baseline": base, "disc": round(disc * 100),
           "nights": nights, "on_shape": on_shape,
           "link": "https://www.aviasales.com" + (o.get("link") or "") + "&marker=755800"}
    scan[code] = {"outcome": "qualified" if disc >= MIN_DISCOUNT else "not a deal",
                  "price": price, "typical": base, "disc_pct": round(disc * 100),
                  "d1": row["d1"], "d2": row["d2"],
                  "nights": nights, "on_shape": on_shape}
    (deals if disc >= MIN_DISCOUNT else skips).append(row)

deals.sort(key=lambda x: -x["disc"])
for d in deals:
    d["deal"] = True

# Deals only, best first, as many as the slide holds. Non-qualifying fares
# exist solely in the scan diagnostics — never on the board.
board = {"date": today.isoformat(), "origin": ORIGIN,
         "deals": deals[:BOARD_MAX], "n_deals": len(deals[:BOARD_MAX]),
         "skip": None,
         "plan": {"shape": PLAN["shape"], "cover": PLAN["cover"],
                  "angle": PLAN["angle"], "content": PLAN["content"],
                  "nights": list(PLAN["nights"]),
                  "on_shape": sum(1 for d in deals[:BOARD_MAX] if d.get("on_shape"))}}
os.makedirs("out", exist_ok=True)
counts = {}
for v in scan.values():
    counts[v["outcome"]] = counts.get(v["outcome"], 0) + 1
json.dump({"date": today.isoformat(), "origin": ORIGIN,
           "routes_considered": len(ROUTES), "min_discount_pct": MIN_DISCOUNT * 100,
           "summary": counts, "routes": scan},
          open(f"out/scan-{ORIGIN}.json", "w"), indent=1)
print(f"{ORIGIN} plan: {PLAN['weekday']} -> {PLAN['shape']} "
      f"({PLAN['nights'][0]}-{PLAN['nights'][1]} nights, leaving "
      f"{PLAN['depart_in'][0]}-{PLAN['depart_in'][1]} days out) — {PLAN['note']}")
print(f"{ORIGIN} scan:", counts)
for c, v in sorted(scan.items(), key=lambda kv: kv[1].get("disc_pct", -999), reverse=True):
    print(f"  {c:4} {v['outcome']:18}", v.get("why") or
          f"${v.get('price')} vs typical ${v.get('typical')} = {v.get('disc_pct')}%")

if not board["deals"]:
    print(f"FATAL: {ORIGIN} produced no qualifying deals — deals-only board, "
          f"so there is nothing to post today.")
    raise SystemExit(1)
json.dump(board, open(PATHS["deals"], "w"), indent=1)
for d in board["deals"]:
    hist[d["to"]] = today.isoformat()
os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
json.dump(hist, open(HISTORY_FILE, "w"), indent=1)
print(f"{ORIGIN} board:", [(d["to"], "DEAL" if d["deal"] else "fare")
                           for d in board["deals"]])
