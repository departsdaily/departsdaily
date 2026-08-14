#!/usr/bin/env python3
"""Departs Daily - fare fetch + verification. Runs daily via GitHub Actions.
Pulls cheapest fares (Travelpayouts data API), scores vs monthly baselines,
applies 6-day no-repeat, flags skips. Writes deals.json.

Origin comes from the ORIGIN env var and defaults to CLT, so an unqualified run
behaves exactly as it did before the pipeline went multi-city."""
import os, sys, json, datetime, urllib.request, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import origins, day_plan, site_fares, index_fares, trip_shape

# WEEKLY PLAN (owner's rule, Jul 28 2026). Monday sells week long trips,
# Tue/Wed sell weekends, Thursday sells urgency, Friday leans on Friday being
# the cheapest day to book, and every other Sunday goes two weeks. The shape
# steers WHICH honest fare each route contributes. It never lowers
# MIN_DISCOUNT, never pads, and never drops a route that had a real deal —
# see pick_offer() below. Config: config/schedule.json.
PLAN = day_plan.plan()

# TIERS = EXPOSURE, NOT ELIGIBILITY (owner's rule, 2026-08-14). Every destination in the
# leisure pool can reach a board; the tier decides how OFTEN. London, Aruba, Cancun, Paris,
# New York and Miami come round more than San Salvador, without San Salvador disappearing
# and without the feed showing the same seven cities every morning. Two levers, neither a
# hard filter: a shorter rest window, and a sort bonus that only ever reorders rows.
_TIERS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "config", "tiers.json")
try:
    TIERS = json.load(open(_TIERS_PATH, encoding="utf-8"))
except (OSError, ValueError):
    TIERS = {"tiers": {}, "tier": {}, "rank": {}}
def tier_of(code):
    return int(TIERS.get("tier", {}).get(code, 3))
def tier_cfg(code):
    return TIERS.get("tiers", {}).get(str(tier_of(code)), {"repeat_days": 8, "bonus": 0})

# WHICH ROUTES ARE INTERNATIONAL. Read from config/seasonality.json, which is the one
# authoritative place. It used to be read off origins.baselines(), which strips every
# entry down to {city, m} — so the flag was ALWAYS None, is_intl() always said False,
# and the 75% international quota on Week-ish silently did nothing at all. Caught by a
# summary line that reported "0 international" on a board with St. Maarten, Los Cabos,
# San Juan and Punta Cana on it.
_SEAS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "config", "seasonality.json")
try:
    INTL = {c for c, v in json.load(open(_SEAS_PATH, encoding="utf-8"))
            ["destinations"].items() if v.get("intl")}
except (OSError, ValueError, KeyError):
    INTL = set()

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


def pick_offer(offers, key, depart_in):
    """Cheapest offer that CLASSIFIES INTO this section and leaves inside the
    window. `offers` is already price-sorted, so the first match is the cheapest
    match. Returns None when nothing fits.

    This used to take a night band and two day-of-week sets and match on all
    three. It now asks one question — `trip_shape.classify(out, back) == key` —
    because the shape rule is authoritative and lives in exactly one file. The
    practical difference: a fare cannot be squeezed into a section it does not
    belong in by loosening a band, and every fare that fits nothing falls to
    CHEAPEST, which is defined as the leftovers and says so on the slide.
    """
    d_lo, d_hi = depart_in
    for cand in offers:
        try:
            dd = datetime.date.fromisoformat(cand["departure_at"][:10])
            rr = datetime.date.fromisoformat((cand.get("return_at") or "")[:10])
        except ValueError:
            continue
        if not (d_lo <= (dd - today).days <= d_hi):
            continue
        if trip_shape.classify(dd, rr) != key:
            continue
        return cand
    return None


hist = json.load(open(HISTORY_FILE)) if os.path.exists(HISTORY_FILE) else {}

def resting(code):
    """Has this destination been shown too recently FOR ITS TIER.

    Tier 1 rests 2 days, tier 3 rests 8. That single number is what makes Aruba roughly
    four times as frequent as San Salvador without ever excluding San Salvador — the rest
    window is a PREFERENCE, applied on the first pass only, so a genuine deal on a resting
    route still beats an empty slot on the second."""
    ts = hist.get(code)
    if not ts:
        return False
    days = (today - datetime.date.fromisoformat(ts)).days
    return days < int(tier_cfg(code).get("repeat_days", NO_REPEAT_DAYS))

recent = {d for d in hist if resting(d)}

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

    `plan` needs: key, depart_in, wide, and optionally deals_only. `key` is the
    category name from pipeline/trip_shape.py — that one string is now the whole
    definition of what belongs on this slide."""
    deals, skips, rows = [], [], {}
    for code, offers in OFFERS.items():
        # TWO RUNGS, cheapest real fare at each, both from the same price-sorted
        # list, and BOTH ARE THE SAME SHAPE:
        #   shape  — classifies into this section, leaving inside the section's
        #            own departure window
        #   window — classifies into this section, leaving inside the wide
        #            window (3-150 days)
        # The old ladder had a middle rung that dropped the day-of-week rule and
        # kept only the night count. That rung is DELETED. Under the owner's
        # 2026-08-14 spec the days of the week ARE the category: a Saturday to
        # Monday trip is not a slightly-off Long Weekend, it is a CHEAPEST, and
        # a slide headed LONG WEEKEND showing it would simply be wrong. So the
        # only thing that ever relaxes is how far out the departure may be —
        # never the shape. A fare that fits no shape is not lost; classify()
        # sends it to CHEAPEST, which exists precisely to carry it and says as
        # much on its own slide.
        rungs = [
            ("shape", pick_offer(offers, plan["key"], plan["depart_in"])),
            ("window", pick_offer(offers, plan["key"],
                                  plan["wide"]["depart_in"])),
        ]
        if all(c is None for _, c in rungs):
            d0, d1 = plan["wide"]["depart_in"]
            rows[code] = {"outcome": "no fares in window",
                          "why": f"{len(offers)} offers, none leaving {d0}-{d1} "
                                 f"days out in the {plan['key']} shape"}
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
    # TIER BONUS: ORDERING ONLY. It is added to the sort key so that when two fares are
    # close the better destination takes the slot. It never touches the price and never
    # touches the computed discount, so a favoured slot can never become an overstated
    # saving — the 12% bar decided who was eligible before this line runs.
    for r in pool:
        r["tier"] = tier_of(r["to"])
        r["tier_bonus"] = int(tier_cfg(r["to"]).get("bonus", 0))
    if spec.get("sort") == "price":
        # cheapest first, but a headliner beats a nobody at a similar price
        pool = sorted(pool, key=lambda x: x["price"] - x["tier_bonus"] * 4)
    else:
        pool = sorted(pool, key=lambda x: -(x["disc"] + x["tier_bonus"]))

    # TIER FLOOR: a preference, never a filter. Long Weekend wants headline cities and
    # beaches, not whatever happened to be cheap, so it asks for tier 1 and 2 first and
    # only reaches tier 3 if it would otherwise come up short.
    floor = int(spec.get("tier_floor", 3))
    # INTERNATIONAL QUOTA: Week-ish is a holiday people plan around, so it leans heavily
    # international. A quota, not a rule — if the international fares are not there, the
    # slots go to real domestic deals rather than sitting empty.
    intl_quota = float(spec.get("intl_quota", 0) or 0)
    want_intl = int(round(spec["rows"] * intl_quota))

    def is_intl(r):
        return r["to"] in INTL

    seen_dest = set()
    picked = []
    # Variety first, then fill. Every deal in `pool` for a deals-only section
    # already cleared MIN_DISCOUNT, so a backfilled repeat is a genuine deal —
    # just one we also showed in the last few days. Showing Miami twice in a
    # week beats showing an overpayment once.
    # Four passes, each one relaxing exactly one preference and nothing else:
    #   0  fresh, inside the tier floor, and honouring the international quota
    #   1  fresh, inside the tier floor, quota satisfied or unreachable
    #   2  fresh, any tier
    #   3  anything that cleared the bar, including recently shown
    # The 12% bar is never relaxed by any of them.
    for wave in (0, 1, 2, 3):
        for r in pool:
            if len(picked) >= spec["rows"]:
                break
            if r["to"] in seen_dest or (r["to"], r["d1"], r["d2"]) in used_flights:
                continue
            if wave < 3 and r["to"] in recent:
                continue
            if wave < 2 and r["tier"] > floor:
                continue
            if wave == 0 and want_intl:
                n_intl = sum(1 for p in picked if is_intl(p))
                # hold the remaining slots for international until the quota is met
                if not is_intl(r) and (len(picked) - n_intl) >= (spec["rows"] - want_intl):
                    continue
            if wave == 3:
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
    # EVERY ROW ON THIS SLIDE REALLY IS THIS SHAPE. build() only ever offers
    # fares that classify into the section, so this can only fire if someone
    # later adds a code path that bypasses it — which is exactly the mistake
    # worth catching before it reaches a slide headed LONG WEEKEND.
    wrong = [(r["to"], r["d1"], r["d2"], trip_shape.classify_iso(r["d1"], r["d2"]))
             for r in picked if trip_shape.classify_iso(r["d1"], r["d2"]) != spec["key"]]
    if wrong:
        raise SystemExit(f"FATAL: {spec['key']} picked rows of another shape: {wrong}")
    sections.append({"key": spec["key"], "cover": spec["cover"],
                     "explain": spec.get("explain", ""),
                     "tag": spec.get("tag", "ROUND TRIP"),
                     "angle": spec["angle"],
                     "deals_only": spec["deals_only"], "rows_target": spec["rows"],
                     "n": len(picked), "n_deals": n_deal,
                     "rungs": {r: sum(1 for d in picked if d.get("rung") == r)
                               for r in ("shape", "window")},
                     "tiers": {str(t): sum(1 for d in picked if d.get("tier") == t)
                               for t in (1, 2, 3)},
                     "n_intl": sum(1 for d in picked if d["to"] in INTL),
                     "deals": picked})
    deals.extend(picked)
    short = "" if len(picked) >= spec["rows"] else \
            f"  SHORT by {spec['rows'] - len(picked)}"
    _t = sections[-1]["tiers"]
    print(f"{ORIGIN} section {spec['key']:9} {len(picked)}/{spec['rows']} rows, "
          f"{n_deal} real deals, tiers 1/2/3 = {_t['1']}/{_t['2']}/{_t['3']}, "
          f"{sections[-1]['n_intl']} international{short}")
    if len(picked) < spec["rows"]:
        print(f"::warning::{ORIGIN} {spec['key']} filled {len(picked)}/"
              f"{spec['rows']} rows. Not padded — every row cleared the "
              f"{MIN_DISCOUNT*100:.0f}% bar. Supply problem, not a code problem: "
              f"{len(ROUTES)} routes eligible.")

# NO FARE TWICE ON ONE BOARD (owner's spec, 2026-08-14). used_flights already
# prevents it while filling; this proves it after the fact, because "the same
# fare printed under two different headings" is the single most embarrassing
# thing this pipeline could publish and it must never be discovered by a reader.
# A city on DIFFERENT dates in two sections is a different trip and is allowed.
_seen = {}
for d in deals:
    k = (d["to"], d["d1"], d["d2"])
    if k in _seen:
        raise SystemExit(f"FATAL: {k} appears in both {_seen[k]} and {d['section']}")
    _seen[k] = d["section"]

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
                            for r in ("shape", "window")}}}
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
