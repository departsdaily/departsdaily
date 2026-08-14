#!/usr/bin/env python3
"""
Departs Daily — hourly board refresh.

Pulls the cheapest real round-trip fares for all 30 tracked CLT routes from
the Travelpayouts/Aviasales prices API and rewrites site/js/deals-data.js
(BOARD stamp + the daily DEALS board).

Design rules (match the site's honesty guarantees):
  - Only real fares from the API ever reach the board — nothing is invented.
  - dep (departure time) comes straight from the fare's departure_at.
  - Day-of-week is computed by the site from d1/d2, never typed here.
  - If the API returns too little data, we exit non-zero WITHOUT writing,
    so yesterday's board (with its auto-expiry) stays up instead of junk.

Usage:  TP_TOKEN=... python scripts/update_deals.py site/js/deals-data.js
"""
import json, os, re, sys, time, urllib.request, urllib.error

# THE SHAPE RULE, imported not copied. pipeline/trip_shape.py is the single
# definition of what a Long Weekend is; the site would drift from the post
# within a week if this file kept its own copy.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "pipeline"))
import trip_shape
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
TOKEN = os.environ.get("TP_TOKEN", "")

# Every origin we hold a defensible baseline for. Boards are generated for all
# of them in one run and written into a single DEALS object keyed by origin.
# Override with ORIGINS=CLT,ATL to rebuild a subset by hand.
ALL_ORIGINS = ["CLT", "ATL", "ORD", "DFW", "DEN", "LAX", "JFK", "MIA", "SEA", "BOS"]
ORIGINS = [o.strip().upper() for o in
           (os.environ.get("ORIGINS") or ",".join(ALL_ORIGINS)).split(",") if o.strip()]
ORIGIN = ORIGINS[0]   # kept for log lines and any single-origin caller

# Baselines come from config/seasonality.json — the SAME file the Instagram
# pipeline seeds its curves from, so the site board and the IG board can never
# disagree about what "typical" means on a route.
#   dot_round_trip[origin][dest]  = DOT Consumer Airfare Report Table 6 city-pair
#                                   average, each-way doubled to round trip
#   intl_estimate_round_trip[dest] = labelled estimate (DOT covers contiguous
#                                    states only, so no city-pair data exists)
_CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "seasonality.json")
with open(_CFG, encoding="utf-8") as _fh:
    _SEAS = json.load(_fh)
DOT_AVG  = _SEAS["dot_round_trip"]
INTL_AVG = _SEAS["intl_estimate_round_trip"]
INTL_SCOPE = _SEAS.get("origin_intl", {})
DOM_SCOPE = _SEAS.get("origin_dom", {})

def avg_for(origin, dest):
    """Annual round-trip average for THIS origin. None means no defensible
    baseline, which means no percentage claim — the board shows HOT FARE."""
    o = DOT_AVG.get(origin.upper(), {})
    if dest in o:
        return o[dest]
    return INTL_AVG.get(dest)

# ---------------------------------------------------------------------------
# DESTINATION CATALOG. One entry per city we can track from anywhere.
# (name, annual_round_trip_avg)  -- avg mirrors ROUTES in index.html:
#   DOT/BTS 2025 each-way x2 for domestic CLT routes, labeled estimates for
#   international. avg=None means we do NOT have a defensible baseline for
#   that city yet, so nothing may print a "% below average" badge for it —
#   the site falls back to "HOT FARE" rather than inventing a comparison.
#   Baselines are per ORIGIN, not global: CLT->AUS averaging $648 says nothing
#   about ATL->AUS. New origins therefore ship searchable but un-badged until
#   their own DOT figures are entered.
# ---------------------------------------------------------------------------
ROUTES = {
 "NYC":("New York City",382),"BOS":("Boston",492),"MIA":("Miami",426),
 "FLL":("Ft. Lauderdale",426),"DCA":("Washington DC",412),"ORD":("Chicago",416),
 "DFW":("Dallas",548),"MCO":("Orlando",416),"LAX":("Los Angeles",662),
 "DEN":("Denver",440),"PHL":("Philadelphia",424),"HOU":("Houston",434),
 "LAS":("Las Vegas",646),"PHX":("Phoenix",660),"TPA":("Tampa",474),
 "BNA":("Nashville",434),"MSY":("New Orleans",462),"SFO":("San Francisco",738),
 "SEA":("Seattle",694),"AUS":("Austin",648),
 "CUN":("Cancún",520),"PUJ":("Punta Cana",560),"MBJ":("Montego Bay",540),
 "NAS":("Nassau",480),"AUA":("Aruba",620),"SJU":("San Juan, PR",420),
 "GCM":("Grand Cayman",640),"LON":("London",850),"PAR":("Paris",900),
 "ROM":("Rome",950),
 # --- added for the ATL top-30. No baseline yet -> no % badge, by design. ---
 "DTW":("Detroit",None),"AMS":("Amsterdam",None),
 "CLT":("Charlotte",None),"MSP":("Minneapolis",None),
 "SAN":("San Diego",None),"RDU":("Raleigh-Durham",None),"MDE":("Medellín",None),
}

# AUTO-EXTEND from the destination catalog (2026-08-13). The dict above is
# hand-maintained and stopped at 37 cities; Charlotte now tracks 115. Every
# unlisted destination used to raise KeyError inside board_for()'s try/except,
# which does not crash the run — it just quietly files the route under "FETCH
# FAIL" forever. So 81 of Charlotte's 115 routes would have burned an API call
# each and then been thrown away, and the expansion would have looked like it
# did nothing.
#
# setdefault, not update: a hand-tuned name above always wins. The avg here is
# always None because avg_for() reads the real number out of config anyway —
# the second tuple slot is legacy and nothing should start trusting it.
for _code, _meta in _SEAS.get("destinations", {}).items():
    if isinstance(_meta, dict) and _meta.get("city"):
        ROUTES.setdefault(_code, (_meta["city"], None))


# ---------------------------------------------------------------------------
# TOP 30 DESTINATIONS PER ORIGIN. This is a coverage statement — "these are the
# 30 destinations we track from this airport" — and the site says exactly that
# on the page. Lists deliberately overlap between airports; the leisure markets
# that matter out of CLT mostly matter out of ATL too. We expand ONE ORIGIN AT
# A TIME, writing that origin's city guides as we go, rather than bolting 300
# thin guides on at once.
# Anything added here for one origin becomes searchable from EVERY origin in
# the Fare Finder, because the nightly index is built per origin against that
# origin's own list.
# ---------------------------------------------------------------------------
# Destinations per origin = every city we hold a real baseline for out of that
# airport. Derived, not hand-typed: a route can never appear on a board without
# the number that justifies its badge. Adding DOT pairs to config/seasonality.json
# widens every affected origin automatically.
def dests_for(origin):
    o = origin.upper()
    # THE LEISURE POOL (owner's rule, 2026-08-14). For Charlotte the board no longer
    # draws from "every city pair DOT publishes" — it draws from the ranked leisure
    # list. Adopting every DOT pair was the right way to get real fare baselines and
    # the wrong way to pick holidays: DOT publishes what people fly, and what people
    # fly is largely work. It put Wichita, Des Moines and Rochester on a travel
    # account while missing Key West, Nantucket, Aspen and Jackson Hole.
    # Every dropped route keeps its baseline, so the Fare Finder still prices it.
    pool = (_SEAS.get("leisure_pool") or {}).get("codes")
    if pool and o == "CLT":
        keep = set(pool)
        return [d for d in sorted(keep) if d != o]
    # DOMESTIC IS SCOPED PER ORIGIN too, for the same reason as international
    # below. The --adopt run on 2026-08-13 pulled real DOT fares for ~65 city
    # pairs out of every origin. That data is right and worth keeping, but nine
    # of those ten boards are retired, so tracking all of it would have roughly
    # tripled the nightly index for cities we do not publish. CLT is absent
    # from origin_dom on purpose and therefore tracks everything DOT gives it.
    dom_allow = DOM_SCOPE.get(o)
    dom = (sorted(c for c in DOT_AVG.get(o, {}) if c in set(dom_allow))
           if dom_allow else sorted(DOT_AVG.get(o, {}).keys()))
    # INTERNATIONAL IS PER ORIGIN as of 2026-08-13. It used to be "every
    # international market we hold an estimate for, from every origin", which
    # was fine at 11 markets and is not fine at 50: the Charlotte expansion
    # would otherwise have quadrupled the international leg of the nightly
    # index for all ten origins overnight, for nine cities whose boards we no
    # longer publish. config/seasonality.json -> origin_intl names the list per
    # origin; anything unlisted falls back to "_default", and a missing map
    # means the old behaviour, so this can never silently empty a board.
    allow = INTL_SCOPE.get(o) or INTL_SCOPE.get("_default")
    intl = (sorted(c for c in INTL_AVG if c in set(allow)) if allow
            else sorted(INTL_AVG.keys()))
    return [d for d in dom + intl if d != o]


# WHICH ROUTES ARE INTERNATIONAL. Read from config/seasonality.json, the one
# authoritative place, exactly as pipeline/fetch_fares.py does. This used to be a
# hand-typed set of twelve codes written when the site tracked twelve international
# markets. Charlotte now tracks sixty-eight, so every one of the other fifty-six —
# St. Maarten, Los Cabos, Punta Cana, Lisbon — was being scored as domestic: wrong
# trip-length window in pick(), and locked out of the guaranteed international slots.
# The literal below survives only as a fallback if the config cannot be read.
_FALLBACK_INTL = {"CUN","PUJ","MBJ","NAS","AUA","SJU","GCM","LON","PAR","ROM","AMS","MDE"}
INTL = {c for c, v in (_SEAS.get("destinations") or {}).items()
        if isinstance(v, dict) and v.get("intl")} or _FALLBACK_INTL

# Board shape. International gets guaranteed slots because those bookings are
# worth several times a domestic one — bigger fares, and the traveller goes on
# to book hotels and tours through the city guide. Ordering only: prices and
# computed discount badges are never adjusted to favour them.
# THE WEBSITE MIRRORS THE POST (owner's rule, 2026-08-14). The morning carousel
# has three named categories, so the site shows the same three under the same
# names instead of one undifferentiated list. Read from config/schedule.json —
# the identical file pipeline/day_plan.py reads — so the two can never drift:
# change a night band once and the post and the page both move.
_SCHED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "config", "schedule.json")
def site_sections():
    try:
        with open(_SCHED_PATH, encoding="utf-8") as fh:
            secs = json.load(fh).get("sections") or []
    except (OSError, ValueError):
        return []
    out = []
    for sec in secs:
        out.append({"key": sec.get("key"),
                    "cover": sec.get("cover", ""),
                    # The page's heading and its one line of plain language both
                    # come from trip_shape, so the site and the slide say the
                    # same thing about the same category, word for word.
                    "title": trip_shape.TITLES.get(sec.get("key"), sec.get("cover", "")),
                    "explain": trip_shape.EXPLAIN.get(sec.get("key"), sec.get("angle", "")),
                    # deals_only sections must clear the bar; CHEAPEST claims
                    # nothing and is therefore allowed any real price.
                    "deals_only": bool(sec.get("deals_only", True)),
                    "min_pct": round(float(sec.get("min_discount", 0.12)) * 100),
                    "sort": sec.get("sort", "discount"),
                    "angle": sec.get("angle", "")})
    out = [o for o in out if o["key"]]
    # ONE ORDER for classification and display, taken from trip_shape so the
    # page cannot render the categories in a different order from the one the
    # classifier evaluates in.
    out.sort(key=lambda o: trip_shape.ORDER.index(o["key"])
             if o["key"] in trip_shape.ORDER else len(trip_shape.ORDER))
    return out

# THE NUMBER THE PAGE WILL ACTUALLY PRINT (2026-08-14). avg_for() returns the raw
# DOT city-pair average, which is every fare sold on the route including full-fare
# business. state/baselines-<ORIGIN>.json holds the CHEAP-fare curve — that same DOT
# figure after config/seasonality.json's cheap_fare_factor — and it is what
# ROUTES[].avg on the page and the Instagram post both compare against. Filtering a
# category on one number while the row prints a badge from the other is how a
# heading ends up reading "8 verified deals" above eight rows that all say HOT FARE.
# So the sections are filtered on the curve, and fall back to avg_for() only when a
# route has no curve at all.
_BASELINE_CACHE = {}
def baseline_avg(origin, dest):
    o = origin.upper()
    if o not in _BASELINE_CACHE:
        try:
            with open(os.path.join(SNAPSHOT_DIR, f"baselines-{o}.json"), encoding="utf-8") as fh:
                _BASELINE_CACHE[o] = (json.load(fh).get("routes") or {})
        except (OSError, ValueError):
            _BASELINE_CACHE[o] = {}
    m = (_BASELINE_CACHE[o].get(dest) or {}).get("m")
    if m:
        return sum(m) / len(m)
    return avg_for(origin, dest)

# TIERS, THE SAME ONES THE POST USES (config/tiers.json). Exposure, never
# eligibility: a tier reorders rows so London and Cancun beat San Salvador when
# both are on offer, and it can never put a fare on the page that did not earn
# its place, nor change a price or a percentage. Without this the CHEAPEST
# category degenerates into whatever obscure city happened to be $9 cheaper,
# which is exactly what the owner asked us to stop doing.
_TIERS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "config", "tiers.json")
try:
    with open(_TIERS_PATH, encoding="utf-8") as _fh:
        _TIERS = json.load(_fh)
except (OSError, ValueError):
    _TIERS = {"tiers": {}, "tier": {}}
def tier_of(code):
    return int(_TIERS.get("tier", {}).get(code, 3))
def tier_bonus(code):
    return int((_TIERS.get("tiers", {}).get(str(tier_of(code))) or {}).get("bonus", 0))

SITE_SECTIONS = site_sections()
SECTION_ROWS = int(os.environ.get("SITE_SECTION_ROWS", "8"))

MIN_ROUTES  = 8   # too few live routes -> keep the previous board
DAILY_ROWS  = 8
DAILY_INTL  = 3

AIRLINES = {
 "AA":"American","DL":"Delta","UA":"United","WN":"Southwest","B6":"JetBlue",
 "NK":"Spirit","F9":"Frontier","AS":"Alaska","G4":"Allegiant","SY":"Sun Country",
 "MX":"Breeze","XP":"Avelo","BA":"British Airways","VS":"Virgin Atlantic",
 "AF":"Air France","LH":"Lufthansa","IB":"Iberia","AZ":"ITA Airways",
 "TP":"TAP Portugal","EI":"Aer Lingus","AC":"Air Canada","AM":"Aeroméxico",
 "Y4":"Volaris","VB":"Viva Aerobus","CM":"Copa","AV":"Avianca","BW":"Caribbean",
 "KL":"KLM","LX":"SWISS","TK":"Turkish","FI":"Icelandair","WS":"WestJet",
 "YV":"American Eagle","OH":"American Eagle","MQ":"American Eagle","PT":"American Eagle",
 "9E":"Delta Connection","OO":"SkyWest","YX":"Republic","ZW":"Air Wisconsin","C5":"CommuteAir",
}

WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "config", "city-weights.json")
ROTATION_STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "..", "state", "rotation.json")

def load_weights():
    try:
        with open(WEIGHTS_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"default": 1.0, "weights": {}, "recency_penalty": {"days": [1.0]}}

def rotation_score(deal, cfg, last_shown, today):
    """Discount, weighted by how much people want the city and how recently
    we showed it. Popular cities surface more; nothing sits on the board
    forever; the 150th city still gets its turn."""
    w = cfg.get("weights", {}).get(deal["to"], cfg.get("default", 1.0))
    seen = last_shown.get(deal["to"])
    pen = 1.0
    if seen:
        try:
            days = (today - date.fromisoformat(seen)).days
            scale = cfg.get("recency_penalty", {}).get("days", [1.0])
            pen = scale[min(days, len(scale) - 1)]
        except ValueError:
            pass
    return deal["pct"] * w * pen

# --- Carrier plausibility -------------------------------------------------
# prices_for_dates returns the FIRST/validating carrier, not the operator of
# every leg. That is how a one-stop CLT-LON came back labelled "Frontier".
# Regional feeders never operate a whole trip alone, and no US ultra-low-cost
# carrier flies the Atlantic, so when the label is impossible for the route we
# say so instead of printing a wrong airline name.
REGIONAL = {"YV","OH","MQ","PT","9E","OO","YX","ZW","C5"}          # feeders only
NO_ATLANTIC = {"F9","WN","G4","SY","MX","XP","NK","AS","B6"}       # no CLT-Europe service
TRANSATLANTIC_DESTS = {"LON","PAR","ROM"}

def carrier_label(code, stops, dest):
    """Return (airline_name, self_transfer_flag)."""
    name = AIRLINES.get(code, code)
    if stops == 0:
        return name, False                      # single carrier, verifiable
    if code in REGIONAL:
        return "", False                        # this is a feeder leg, not the trip
    if dest in TRANSATLANTIC_DESTS and code in NO_ATLANTIC:
        # Cheapest transatlantic fares are often self-transfer itineraries whose
        # first hop is a domestic low-cost carrier. The connection is NOT
        # protected, and the traveller should know that before they book.
        return "", True
    return name, False

def fetch(origin, dest):
    url = ("https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
           f"?origin={origin}&destination={dest}&currency=usd&market=us"
           f"&one_way=false&sorting=price&limit=30&token={TOKEN}")
    req = urllib.request.Request(url, headers={"User-Agent": "departsdaily-updater"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("data", [])

def parse_dt(s):
    # "2026-10-02T17:04:00-04:00"
    return datetime.fromisoformat(s)

def dep_time(dt):
    h = dt.hour % 12 or 12
    return f"{h}:{dt.minute:02d}{'AM' if dt.hour < 12 else 'PM'}"

def arr_time(dt, duration_min):
    """Arrival clock time, derived dep + leg duration — the same derivation the
    nightly index and the Fare Finder already use. Returns "" when the API gave
    no duration: an unknown arrival is shown as unknown, never invented. A leg
    landing after midnight carries "+1", the site's established label for
    "next day or later"."""
    try:
        m = int(duration_min)
    except (TypeError, ValueError):
        return ""
    if m <= 0:
        return ""
    total = dt.hour * 60 + dt.minute + m
    h24, mm = (total % 1440) // 60, total % 60
    h = h24 % 12 or 12
    return (f"{h}:{mm:02d}{'AM' if h24 < 12 else 'PM'}"
            + ("+1" if total >= 1440 else ""))

def pick(dest, fares, today, shape=None):
    """Cheapest sane round trip. Domestic: 3-90 days out, 2-9 day trips.
    International: 3-120 days out, 4-21 day trips (how people actually fly).

    `shape` restricts the choice to fares that CLASSIFY into that category, so
    the same cached fares answer all four questions — a long weekend, an extra
    long weekend, a week-ish holiday and the leftovers — without a single extra
    API call. It only narrows WHICH fare is chosen; nothing about price or the
    discount computed from it changes."""
    max_out, len_lo, len_hi = (120, 4, 21) if dest in INTL else (90, 2, 9)
    if shape:
        # The category IS the filter. No night band, no day-of-week set — one
        # question, asked of pipeline/trip_shape.py, which is the only place
        # the rule lives. Trip length is left wide open here on purpose: the
        # classifier already bounds it, and bounding it twice is how the two
        # copies eventually disagree.
        len_lo, len_hi, max_out = 1, 400, 150
    best = None
    for f in fares:
        try:
            d1 = parse_dt(f["departure_at"]); d2 = parse_dt(f["return_at"])
        except (KeyError, ValueError):
            continue
        days_out = (d1.date() - today).days
        trip_len = (d2.date() - d1.date()).days
        price = f.get("price") or 0
        if not (3 <= days_out <= max_out and len_lo <= trip_len <= len_hi and price > 0):
            continue
        if shape and trip_shape.classify(d1.date(), d2.date()) != shape:
            continue
        if best is None or price < best["price"]:
            stops = max(f.get("transfers", 0), f.get("return_transfers", 0))
            # The API returns the FIRST/validating carrier, not the operating
            # carrier for every leg. On a connecting itinerary that name is
            # frequently wrong (a $723 CLT-LON "Frontier" fare is a self-transfer
            # whose first hop is Frontier), so we only claim an airline when the
            # trip is nonstop and the carrier is therefore verifiable.
            al, self_transfer = carrier_label(f.get("airline", ""), int(stops), dest)
            # rdep = the RETURN leg's departure time, straight from the fare.
            # It was always in the API response and always thrown away, so the
            # board could only ever tell you when you left, never when you flew
            # home. Carried, not invented: if the fare has no usable return
            # timestamp the key is omitted and the site prints no time rather
            # than guessing one.
            best = {"to": dest, "city": ROUTES[dest][0], "price": int(price),
                    "d1": d1.date().isoformat(), "d2": d2.date().isoformat(),
                    "dep": dep_time(d1), "al": al, "stops": int(stops),
                    "xfer": 1 if self_transfer else 0}
            if d2.hour or d2.minute:
                best["rdep"] = dep_time(d2)
            # Arrivals: derived from the durations when the API supplies them,
            # absent when it doesn't — identical policy to the Fare Finder.
            a1 = arr_time(d1, f.get("duration_to"))
            a2 = arr_time(d2, f.get("duration_back"))
            if a1: best["arr"] = a1
            if a2: best["rarr"] = a2
    return best

def js_deal(d, exp=None):
    s = (f'{{to:"{d["to"]}",city:{json.dumps(d["city"], ensure_ascii=False)},'
         f'price:{d["price"]},d1:"{d["d1"]}",d2:"{d["d2"]}",dep:"{d["dep"]}",'
         f'al:{json.dumps(d["al"], ensure_ascii=False)},stops:{d["stops"]}')
    if d.get("rdep"): s += f',rdep:"{d["rdep"]}"'
    if d.get("arr"): s += f',arr:"{d["arr"]}"'
    if d.get("rarr"): s += f',rarr:"{d["rarr"]}"'
    if d.get("xfer"): s += ',xfer:1' 
    if exp: s += f',exp:"{exp}"'
    return s + "}"

PREV_RX = re.compile(r"([A-Z]{3}):\[(.*?)\](?=,\s*[A-Z]{3}:\[|\}\s*;)", re.S)

def previous_boards(path):
    """Last run's board for each origin, so one origin's API blip cannot blank
    its board. A carried-forward row still expires on its own `exp` date, so
    this can never resurrect a fare nobody can book."""
    try:
        with open(path, encoding="utf-8") as fh:
            txt = fh.read()
    except OSError:
        return {}
    i = txt.find("const DEALS={")
    return dict(PREV_RX.findall(txt[i:])) if i >= 0 else {}


def previous_sections(path):
    """Last run's category boards, so a scoped or failed run cannot blank them.

    Stored as strict JSON inside the generated file precisely so it can be read
    back with json.loads rather than re-parsed out of JavaScript by regex.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            txt = fh.read()
    except OSError:
        return {}
    i = txt.find("const SECTIONS=")
    if i < 0:
        return {}
    j = txt.find("\n", i)
    raw = txt[i + len("const SECTIONS="):j].rstrip().rstrip(";")
    try:
        return json.loads(raw)
    except ValueError:
        return {}


SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "state")


def snapshot_path(origin):
    return os.path.join(SNAPSHOT_DIR, f"fares-{origin.upper()}.json")


def write_snapshot(origin, found, failed):
    """Every route this run actually priced, not just the 8 that made the board.

    `generated` is a timezone-aware ET stamp and the consumer is required to
    check it — the whole point is that the Instagram post must never be built
    from last night's fares. See pipeline/site_fares.py.
    """
    now = datetime.now(ET)
    doc = {"origin": origin.upper(),
           "generated": now.isoformat(timespec="seconds"),
           "source": "scripts/update_deals.py",
           "routes_priced": len(found),
           "routes_failed": sorted(failed),
           "fares": {d["to"]: d for d in found}}
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    with open(snapshot_path(origin), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    print(f"  {origin}: fare snapshot written — {len(found)} routes priced "
          f"({len(failed)} failed) at {now.strftime('%H:%M %Z')}")


def board_for(origin, today):
    """Build one origin's daily board. Returns [] if the cache was too thin."""
    found, failed = [], []
    # The raw offers per destination, held for the length of this run. board_for
    # already paid for them; the three site categories are then answered from the
    # same list rather than three more round trips to the API.
    offers = {}
    for dest in dests_for(origin):
        try:
            offers[dest] = fetch(origin, dest)
            deal = pick(dest, offers[dest], today)
            if deal:
                avg = avg_for(origin, dest)
                # No baseline -> no claim. pct 0 keeps it out of the "biggest
                # saving" ranking instead of inventing a discount.
                deal["pct"] = round((1 - deal["price"] / avg) * 100) if avg else 0
                found.append(deal)
                print(f"  {origin}->{dest} ${deal['price']} ({deal['pct']}% below avg) "
                      f"{deal['d1']} {deal['dep']} {deal['al']}")
            else:
                print(f"  {origin}->{dest} no qualifying fare in cache")
        except Exception as e:
            failed.append(dest); print(f"  {origin}->{dest} FETCH FAIL: {e}")
        time.sleep(0.4)  # be polite to the API

    # FARE SNAPSHOT (Jul 29 2026). This run just priced EVERY tracked route for
    # this origin and is about to throw ~22 of ~30 results away, because only 8
    # fit the board. The Instagram pipeline was separately re-querying the same
    # API minutes later and getting a thinner answer (Jul 29: the IG fetch saw
    # 1 DFW offer while the index held 162). So we write the whole set down.
    # pipeline/site_fares.py reads it, which means the post and the site are
    # built from ONE set of fares and can never disagree again.
    # Costs nothing: not a single extra API call, just data we already paid for.
    write_snapshot(origin, found, failed)

    if len(found) < MIN_ROUTES:
        print(f"  {origin}: only {len(found)} routes returned fares "
              f"({len(failed)} failed) — keeping the previous board.")
        return []

    by_value = sorted(found, key=lambda d: -d["pct"])

    # Daily board: 8 rows, with 3 guaranteed international slots.
    # International trips are worth more to us (bigger fares, and the traveller
    # goes on to book hotels and tours) AND to the visitor planning a real
    # holiday rather than a weekend. This changes ORDERING ONLY — every price
    # and every computed "% below average" is untouched, so a guaranteed slot
    # can never turn into an overstated saving.
    cfg = load_weights()
    try:
        with open(ROTATION_STATE, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        state = {}
    # Rotation is per origin: showing Cancún out of Charlotte says nothing
    # about whether Atlanta's board has shown it.
    last_shown = state.get(origin, {}) if isinstance(state.get(origin), dict) else {}

    ranked = sorted(found, key=lambda d: -rotation_score(d, cfg, last_shown, today))
    intl_slots = [d for d in ranked if d["to"] in INTL][:DAILY_INTL]
    dom_slots  = [d for d in ranked if d not in intl_slots][:DAILY_ROWS - len(intl_slots)]
    daily = sorted(dom_slots + intl_slots, key=lambda d: -d["pct"])
    if len(daily) < DAILY_ROWS:                      # thin cache - backfill on value
        daily = by_value[:DAILY_ROWS]

    for d in daily:
        last_shown[d["to"]] = today.isoformat()
    state[origin] = last_shown
    os.makedirs(os.path.dirname(ROTATION_STATE), exist_ok=True)
    with open(ROTATION_STATE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1)
    return daily, sections_for(origin, offers, today, cfg, last_shown)


def sections_for(origin, offers, today, cfg, last_shown):
    """The three named categories the morning post publishes, for the website.

    One pass per section over fares this run already fetched. A destination may
    appear in more than one category on the same day only with a DIFFERENT trip,
    which is the owner's rule for the post as well — the same city Thursday to
    Sunday and the same city for eleven nights are two different holidays. The
    exact same flight is never printed twice.

    Honesty is unchanged and non-negotiable: a row carries a "% below typical"
    badge only when it genuinely cleared that section's bar, and CHEAPEST, which
    claims nothing about savings, is the only section allowed to show a fare that
    did not — with no badge on it.
    """
    if not SITE_SECTIONS:
        return []
    used = set()          # exact flights already spoken for, across all sections
    out = []
    for spec in SITE_SECTIONS:
        rows = []
        for dest, fares in offers.items():
            deal = pick(dest, fares, today, shape=spec["key"])
            if not deal:
                continue
            avg = baseline_avg(origin, dest)
            deal["pct"] = round((1 - deal["price"] / avg) * 100) if avg else 0
            deal["nights"] = (date.fromisoformat(deal["d2"])
                              - date.fromisoformat(deal["d1"])).days
            if spec["deals_only"] and deal["pct"] < spec["min_pct"]:
                continue
            if not spec["deals_only"] and deal["pct"] < 0:
                # "Cheapest" is a promise about price, not permission to print an
                # overpayment. Same rule the post enforces.
                continue
            rows.append(deal)
        for d in rows:
            d["tier"] = tier_of(d["to"])
        if spec["sort"] == "price":
            # cheapest first, but a headline destination beats a nobody at a
            # similar price. Same weighting the post applies to its own
            # CHEAPEST slide, so the two lists read as one editorial voice.
            rows.sort(key=lambda d: d["price"] - tier_bonus(d["to"]) * 4)
        else:
            rows.sort(key=lambda d: -(rotation_score(d, cfg, last_shown, today)
                                      + tier_bonus(d["to"])))
        picked = []
        for d in rows:
            if len(picked) >= SECTION_ROWS:
                break
            if (d["to"], d["d1"], d["d2"]) in used:
                continue
            used.add((d["to"], d["d1"], d["d2"]))
            picked.append(d)
        # EVERY ROW REALLY IS THIS SHAPE. pick() only ever returns fares that
        # classify into the section, so this can only fire if a later change
        # bypasses it — which is exactly the mistake worth catching before a
        # heading reading LONG WEEKEND sits above a Saturday-to-Tuesday trip.
        wrong = [(d["to"], d["d1"], d["d2"]) for d in picked
                 if trip_shape.classify_iso(d["d1"], d["d2"]) != spec["key"]]
        if wrong:
            raise SystemExit(f"FATAL: {spec['key']} picked rows of another shape: {wrong}")
        out.append({"key": spec["key"], "cover": spec["cover"],
                    "title": spec["title"], "explain": spec["explain"],
                    "angle": spec["angle"],
                    "claims": spec["deals_only"], "rows": picked})
        print(f"  {origin} site section {spec['key']:14} {len(picked)} rows")
    # NO FARE TWICE ON ONE PAGE. `used` prevents it while filling; this proves
    # it afterwards, for the same reason the post asserts it — the same fare
    # under two different headings is the one error a reader would spot instantly.
    seen = {}
    for sec in out:
        for d in sec["rows"]:
            k = (d["to"], d["d1"], d["d2"])
            if k in seen:
                raise SystemExit(f"FATAL: {k} in both {seen[k]} and {sec['key']}")
            seen[k] = sec["key"]
    return out


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "site/js/deals-data.js"
    if not TOKEN:
        print("FATAL: TP_TOKEN env var not set"); sys.exit(1)

    now = datetime.now(ET)
    today = now.date()
    # Daily rows expire after 2 days: cheap fares rarely live longer, and an
    # expired row removes itself rather than showing a price nobody can book.
    exp_daily = (today + timedelta(days=2)).isoformat()

    prev = previous_boards(out_path)
    prev_secs = previous_sections(out_path)
    blocks, fresh, carried, counts = [], [], [], {}
    sec_out = {}

    for origin in ORIGINS:
        print(f"--- {origin} ({len(dests_for(origin))} destinations) ---")
        daily, secs = board_for(origin, today)
        if daily:
            sep = ",\n "
            blocks.append(f'{origin}:[\n ' + sep.join(js_deal(d, exp_daily) for d in daily) + "]")
            fresh.append(origin); counts[origin] = len(daily)
            if secs:
                sec_out[origin] = {"exp": exp_daily, "sections": secs}
        elif origin in prev:
            blocks.append(f'{origin}:[{prev[origin]}]')
            carried.append(origin)
            if origin in prev_secs:
                sec_out[origin] = prev_secs[origin]

    # Same carry-forward rule as the flat board: a scoped run must not erase the
    # categories of an origin it was never asked to rebuild. Rows still expire on
    # their own `exp`, so nothing stale can outlive its stamp.
    for origin, blob in prev_secs.items():
        if origin not in ORIGINS:
            sec_out.setdefault(origin, blob)

    # A SCOPED RUN MUST NOT ERASE EVERYONE ELSE. Found the hard way Jul 29:
    # the ATL posting job ran this script with ORIGINS=ATL and the file was
    # rewritten containing only ATL — Charlotte's board vanished from the
    # site until the next full hourly refresh. The loop above only visits the
    # origins it was asked to rebuild, so every other origin already in the
    # file is carried forward verbatim here. Their rows keep their own exp
    # dates and still expire themselves client-side, so nothing stale can
    # outlive its stamp.
    for origin, rows in prev.items():
        if origin not in ORIGINS:
            blocks.append(f'{origin}:[{rows}]')
            carried.append(origin)

    if not fresh:
        print("FATAL: no origin produced a board — leaving the file untouched.")
        sys.exit(1)

    tz = now.strftime("%z")
    updated = now.strftime("%Y-%m-%dT%H:%M:%S") + tz[:3] + ":" + tz[3:]
    body = f"""/* =====================================================================
   DEPARTS DAILY — LIVE BOARD DATA
   GENERATED AUTOMATICALLY — do not hand-edit.
   Rewritten every hour by scripts/update_deals.py from
   live Travelpayouts/Aviasales fare data. Every fare below was found
   in a real search; departure times come from the fare itself.
   Generated {now.strftime("%Y-%m-%d %H:%M %Z")}
   Rebuilt this run: {", ".join(f"{o} ({counts[o]})" for o in fresh) or "none"}
   Carried forward:  {", ".join(carried) or "none"}
   ===================================================================== */
const BOARD={{
 updated:"{updated}",
}};
const DEALS={{{",".join(blocks)}}};
const SECTIONS={json.dumps(sec_out, ensure_ascii=False, separators=(",", ":"))};
"""
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(body)
    print(f"WROTE {out_path}: {len(fresh)} boards rebuilt, {len(carried)} carried, "
          f"stamp {now.strftime('%a %b %d %I:%M%p ET')}")


if __name__ == "__main__":
    main()
