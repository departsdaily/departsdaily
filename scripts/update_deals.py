#!/usr/bin/env python3
"""
Departs Daily — hourly board refresh.

Pulls the cheapest real round-trip fares for all 30 tracked CLT routes from
the Travelpayouts/Aviasales prices API and rewrites site/js/deals-data.js
(BOARD stamp, daily DEALS board, weekly top-10 DEALS_WEEK board).

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

# 30 tracked destinations. avg/src mirror ROUTES in index.html (DOT/BTS 2025
# each-way x2 for domestic; labeled estimates for international).
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
}

# International routes: city codes (LON not LHR — the fare cache keys on cities),
# longer trip windows, and guaranteed board slots (higher-value bookings).
INTL = {"CUN","PUJ","MBJ","NAS","AUA","SJU","GCM","LON","PAR","ROM"}

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
            best = {"to": dest, "city": ROUTES[dest][0], "price": int(price),
                    "d1": d1.date().isoformat(), "d2": d2.date().isoformat(),
                    "dep": dep_time(d1),
                    "al": AIRLINES.get(f.get("airline", ""), f.get("airline", "")),
                    "stops": int(stops)}
    return best

def js_deal(d, exp=None):
    s = (f'{{to:"{d["to"]}",city:{json.dumps(d["city"], ensure_ascii=False)},'
         f'price:{d["price"]},d1:"{d["d1"]}",d2:"{d["d2"]}",dep:"{d["dep"]}",'
         f'al:{json.dumps(d["al"], ensure_ascii=False)},stops:{d["stops"]}')
    if exp: s += f',exp:"{exp}"'
    return s + "}"

def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "site/js/deals-data.js"
    if not TOKEN:
        print("FATAL: TP_TOKEN env var not set"); sys.exit(1)

    now = datetime.now(ET)
    today = now.date()
    found, failed = [], []
    for dest in ROUTES:
        try:
            fares = fetch(dest)
            deal = pick(dest, fares, today)
            if deal:
                deal["pct"] = round((1 - deal["price"] / ROUTES[dest][1]) * 100)
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

    by_value = sorted(found, key=lambda d: -d["pct"])
    intl_found = [d for d in by_value if d["to"] in INTL]

    # Daily board: 5 best values + the single best international deal.
    daily = by_value[:5]
    for d in intl_found:
        if d not in daily:
            daily.append(d); break
    if len(daily) < 6:
        daily = by_value[:6]

    # Weekly top 10: guarantee up to 3 international slots.
    intl_slots = intl_found[:3]
    weekly = [d for d in by_value if d not in intl_slots][:10 - len(intl_slots)] + intl_slots
    weekly = sorted(weekly, key=lambda d: -d["pct"])
    exp_daily = (today + timedelta(days=2)).isoformat()

    # Current Mon–Sun week label, e.g. "WEEK OF JUL 27–AUG 2"
    mon = today - timedelta(days=today.weekday())
    sun = mon + timedelta(days=6)
    M = lambda d: d.strftime("%b").upper()
    week_of = (f"WEEK OF {M(mon)} {mon.day}–{sun.day}" if mon.month == sun.month
               else f"WEEK OF {M(mon)} {mon.day}–{M(sun)} {sun.day}")

    sep = ",\n "
    daily_js = sep.join(js_deal(d, exp_daily) for d in daily)
    weekly_js = sep.join(js_deal(d) for d in weekly)
    tz = now.strftime("%z")
    updated = now.strftime("%Y-%m-%dT%H:%M:%S") + tz[:3] + ":" + tz[3:]
    body = f"""/* =====================================================================
   DEPARTS DAILY — LIVE BOARD DATA
   GENERATED AUTOMATICALLY — do not hand-edit.
   Rewritten every hour by scripts/update_deals.py from
   live Travelpayouts/Aviasales fare data. Every fare below was found
   in a real search; departure times come from the fare itself.
   Generated {now.strftime("%Y-%m-%d %H:%M %Z")} · {len(found)}/30 routes returned fares.
   ===================================================================== */
const BOARD={{
 updated:"{updated}",
 weekOf:"{week_of}",
 weekExp:"{sun.isoformat()}"
}};
const DEALS={{CLT:[
 {daily_js}]}};
const DEALS_WEEK={{CLT:[
 {weekly_js}]}};
"""
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(body)
    print(f"WROTE {out_path}: {len(daily)} daily deals, {len(weekly)} weekly, "
          f"stamp {now.strftime('%a %b %d %I:%M%p ET')}")

if __name__ == "__main__":
    main()
