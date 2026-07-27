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
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ORIGIN = "CLT"
TOKEN = os.environ.get("TP_TOKEN", "")

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
ORIGIN_DESTS = {
 "CLT": ["NYC","BOS","MIA","FLL","DCA","ORD","DFW","MCO","LAX","DEN",
         "PHL","HOU","LAS","PHX","TPA","BNA","MSY","SFO","SEA","AUS",
         "CUN","PUJ","MBJ","NAS","AUA","SJU","GCM","LON","PAR","ROM"],
 # Atlanta is the next board to open (see site-notes). Delta's hub, so the
 # domestic spread is wider and the transatlantic list leans AMS over ROM.
 "ATL": ["NYC","BOS","MIA","FLL","DCA","ORD","DFW","MCO","LAX","DEN",
         "PHL","HOU","LAS","PHX","TPA","BNA","MSY","SFO","SEA","DTW",
         "CUN","PUJ","MBJ","NAS","AUA","SJU","GCM","LON","PAR","AMS"],
}
# Origins without their own curated list yet fall back to the CLT 30, which is
# what every origin used before per-origin lists existed. No regression.
DEFAULT_DESTS = ORIGIN_DESTS["CLT"]

def dests_for(origin):
    return ORIGIN_DESTS.get(origin.upper(), DEFAULT_DESTS)


INTL = {"CUN","PUJ","MBJ","NAS","AUA","SJU","GCM","LON","PAR","ROM","AMS","MDE"}

# Board shape. International gets guaranteed slots because those bookings are
# worth several times a domestic one — bigger fares, and the traveller goes on
# to book hotels and tours through the city guide. Ordering only: prices and
# computed discount badges are never adjusted to favour them.
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

def fetch(dest):
    url = ("https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
           f"?origin={ORIGIN}&destination={dest}&currency=usd&market=us"
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

def pick(dest, fares, today):
    """Cheapest sane round trip. Domestic: 3-90 days out, 2-9 day trips.
    International: 3-120 days out, 4-21 day trips (how people actually fly)."""
    max_out, len_lo, len_hi = (120, 4, 21) if dest in INTL else (90, 2, 9)
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
        if best is None or price < best["price"]:
            stops = max(f.get("transfers", 0), f.get("return_transfers", 0))
            # The API returns the FIRST/validating carrier, not the operating
            # carrier for every leg. On a connecting itinerary that name is
            # frequently wrong (a $723 CLT-LON "Frontier" fare is a self-transfer
            # whose first hop is Frontier), so we only claim an airline when the
            # trip is nonstop and the carrier is therefore verifiable.
            al, self_transfer = carrier_label(f.get("airline", ""), int(stops), dest)
            best = {"to": dest, "city": ROUTES[dest][0], "price": int(price),
                    "d1": d1.date().isoformat(), "d2": d2.date().isoformat(),
                    "dep": dep_time(d1), "al": al, "stops": int(stops),
                    "xfer": 1 if self_transfer else 0}
    return best

def js_deal(d, exp=None):
    s = (f'{{to:"{d["to"]}",city:{json.dumps(d["city"], ensure_ascii=False)},'
         f'price:{d["price"]},d1:"{d["d1"]}",d2:"{d["d2"]}",dep:"{d["dep"]}",'
         f'al:{json.dumps(d["al"], ensure_ascii=False)},stops:{d["stops"]}')
    if d.get("xfer"): s += ',xfer:1' 
    if exp: s += f',exp:"{exp}"'
    return s + "}"

def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "site/js/deals-data.js"
    if not TOKEN:
        print("FATAL: TP_TOKEN env var not set"); sys.exit(1)

    now = datetime.now(ET)
    today = now.date()
    found, failed = [], []
    for dest in dests_for(ORIGIN):
        try:
            fares = fetch(dest)
            deal = pick(dest, fares, today)
            if deal:
                avg = ROUTES[dest][1]
                # No baseline -> no claim. pct 0 keeps it out of the "biggest
                # saving" ranking instead of inventing a discount.
                deal["pct"] = round((1 - deal["price"] / avg) * 100) if avg else 0
                found.append(deal)
                print(f"  {ORIGIN}->{dest} ${deal['price']} ({deal['pct']}% below avg) "
                      f"{deal['d1']} {deal['dep']} {deal['al']}")
            else:
                print(f"  {ORIGIN}->{dest} no qualifying fare in cache")
        except Exception as e:
            failed.append(dest); print(f"  {ORIGIN}->{dest} FETCH FAIL: {e}")
        time.sleep(0.4)  # be polite to the API

    if len(found) < 10:
        print(f"FATAL: only {len(found)} routes returned fares "
              f"({len(failed)} failed) — keeping yesterday's board.")
        sys.exit(1)

    # Daily rows expire after 2 days: cheap fares rarely live longer, and an
    # expired row removes itself rather than showing a price nobody can book.
    exp_daily = (today + timedelta(days=2)).isoformat()

    by_value = sorted(found, key=lambda d: -d["pct"])
    intl_found = [d for d in by_value if d["to"] in INTL]

    # Daily board: 8 rows, with 3 guaranteed international slots.
    # International trips are worth more to us (bigger fares, and the traveller
    # goes on to book hotels and tours) AND to the visitor planning a real
    # holiday rather than a weekend. This changes ORDERING ONLY — every price
    # and every computed "% below average" is untouched, so a guaranteed slot
    # can never turn into an overstated saving.
    cfg = load_weights()
    try:
        with open(ROTATION_STATE, encoding="utf-8") as fh:
            last_shown = json.load(fh)
    except (OSError, ValueError):
        last_shown = {}

    ranked = sorted(found, key=lambda d: -rotation_score(d, cfg, last_shown, today))
    intl_slots = [d for d in ranked if d["to"] in INTL][:DAILY_INTL]
    dom_slots  = [d for d in ranked if d not in intl_slots][:DAILY_ROWS - len(intl_slots)]
    daily = sorted(dom_slots + intl_slots, key=lambda d: -d["pct"])
    if len(daily) < DAILY_ROWS:                      # thin cache - backfill on value
        daily = by_value[:DAILY_ROWS]

    for d in daily:
        last_shown[d["to"]] = today.isoformat()
    os.makedirs(os.path.dirname(ROTATION_STATE), exist_ok=True)
    with open(ROTATION_STATE, "w", encoding="utf-8") as fh:
        json.dump(last_shown, fh, indent=1)

    sep = ",\n "
    daily_js = sep.join(js_deal(d, exp_daily) for d in daily)
    tz = now.strftime("%z")
    updated = now.strftime("%Y-%m-%dT%H:%M:%S") + tz[:3] + ":" + tz[3:]
    body = f"""/* =====================================================================
   DEPARTS DAILY — LIVE BOARD DATA
   GENERATED AUTOMATICALLY — do not hand-edit.
   Rewritten every hour by scripts/update_deals.py from
   live Travelpayouts/Aviasales fare data. Every fare below was found
   in a real search; departure times come from the fare itself.
   Generated {now.strftime("%Y-%m-%d %H:%M %Z")} · {len(found)}/{len(dests_for(ORIGIN))} routes returned fares.
   ===================================================================== */
const BOARD={{
 updated:"{updated}",
}};
const DEALS={{CLT:[
 {daily_js}]}};
"""
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(body)
    print(f"WROTE {out_path}: {len(daily)} daily deals, "
          f"stamp {now.strftime('%a %b %d %I:%M%p ET')}")

if __name__ == "__main__":
    main()
