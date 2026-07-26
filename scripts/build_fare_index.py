#!/usr/bin/env python3
"""
Departs Daily — Fare Finder index builder (v2, per-origin).

Builds site/data/idx-<ORIGIN>.json: every cached fare for the next ~5 months
on all tracked routes from one origin, so the Fare Finder can answer
"cheapest long weekend in September under $400" instantly in the browser.

v2 changes:
  * Origin is a parameter — `python scripts/build_fare_index.py ATL` writes
    site/data/idx-ATL.json. Default CLT. One index file per origin.
  * Densified: merges THREE cache endpoints instead of one —
      - aviasales/v3/prices_for_dates (one-ways both directions + real RTs,
        with departure times and stops)
      - v2/prices/month-matrix (round trips; no times — stored with time "")
      - v1/prices/calendar (round trips with times)
    All three read the same Aviasales search cache but aggregate it
    differently, so merging them surfaces fares any single endpoint misses.

Shape (unchanged from v1 — the finder page already speaks it):
{
  "meta": {"built": iso8601_ET, "label": "...", "origin": "CLT", "routes": N},
  "dests": {
    "LAS": {
      "out":  {"YYYY-MM-DD": [price, stops, "HH:MM"]},   # one-way ORIGIN->LAS
      "back": {"YYYY-MM-DD": [price, stops, "HH:MM"]},   # one-way LAS->ORIGIN
      "rt":   {"YYYY-MM-DD|YYYY-MM-DD": [price, maxstops, "HH:MM"]}
    }, ...
  }
}
Entries sourced from endpoints that don't report departure times carry "" as
the time; the finder can't time-filter those (they're excluded when a
time-of-day filter is on — honest, never guessed).

Honesty rules: every number is a real fare found in the Aviasales search
cache. One-way sums can differ from live round-trip pricing; the page says
so and every click runs a live search.

Usage: TP_TOKEN=... python scripts/build_fare_index.py [ORIGIN] [out_path]
"""
import json, os, sys, time, urllib.request, urllib.parse
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
TOKEN = os.environ.get("TP_TOKEN", "")
MONTHS_AHEAD = 5
MIN_FARES = 100  # per-origin guard: refuse to publish a uselessly thin index

# Tracked destinations per origin (city codes for metro areas).
# Adding a city = add a key here + add it to the workflow's origin list.
# Falls back to the CLT list for any origin without its own list yet.
CLT_DESTS = ["NYC","BOS","MIA","FLL","DCA","ORD","DFW","MCO","LAX","DEN","PHL","HOU",
             "LAS","PHX","TPA","BNA","MSY","SFO","SEA","AUS",
             "CUN","PUJ","MBJ","NAS","AUA","SJU","GCM","LON","PAR","ROM"]
DESTS_BY_ORIGIN = {"CLT": CLT_DESTS}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "departsdaily-index"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if attempt == 2:
                print("  api fail:", url.split("?")[0].rsplit("/", 1)[-1], e)
                return {}
            time.sleep(2)


def v3(params):
    url = ("https://api.travelpayouts.com/aviasales/v3/prices_for_dates?"
           + urllib.parse.urlencode({**params, "currency": "usd", "market": "us",
                                     "limit": 1000, "sorting": "price", "token": TOKEN}))
    return get(url).get("data", []) or []


def month_matrix(origin, dest, month_first_day):
    url = ("https://api.travelpayouts.com/v2/prices/month-matrix?"
           + urllib.parse.urlencode({"currency": "usd", "origin": origin,
                                     "destination": dest, "month": month_first_day,
                                     "one_way": "false", "token": TOKEN}))
    return get(url).get("data", []) or []


def calendar_rt(origin, dest, month):
    url = ("https://api.travelpayouts.com/v1/prices/calendar?"
           + urllib.parse.urlencode({"currency": "usd", "origin": origin,
                                     "destination": dest, "depart_date": month,
                                     "calendar_type": "departure_date", "token": TOKEN}))
    d = get(url).get("data", {})
    return d if isinstance(d, dict) else {}


def hhmm(iso):
    return iso[11:16] if iso and len(iso) >= 16 else ""


def months():
    now = datetime.now(ET)
    out = []
    y, m = now.year, now.month
    for _ in range(MONTHS_AHEAD + 1):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13: y, m = y + 1, 1
    return out


def keep_min(d, key, price, stops, t):
    """Keep the cheapest fare per key; on a price tie prefer the entry
    that knows its departure time."""
    cur = d.get(key)
    if cur is None or price < cur[0] or (price == cur[0] and t and not cur[2]):
        d[key] = [int(price), int(stops), t]


def build_origin(origin, out_path, today):
    dests_list = DESTS_BY_ORIGIN.get(origin, CLT_DESTS)
    dests, total = {}, 0
    print(f"=== {origin} ===")
    for code in dests_list:
        node = {"out": {}, "back": {}, "rt": {}}
        for mon in months():
            # 1) one-way legs, both directions (v3 — has times + stops)
            for direction, o, d in (("out", origin, code), ("back", code, origin)):
                for f in v3({"origin": o, "destination": d, "one_way": "true",
                             "departure_at": mon}):
                    dep = f.get("departure_at", "")
                    if dep[:10] <= today or not f.get("price"): continue
                    keep_min(node[direction], dep[:10], f["price"],
                             f.get("transfers", 0), hhmm(dep))
                time.sleep(0.12)
            # 2) real round trips (v3 — often cheaper than one-way sums)
            for f in v3({"origin": origin, "destination": code, "one_way": "false",
                         "departure_at": mon}):
                dep, ret = f.get("departure_at", ""), f.get("return_at", "")
                if not dep or not ret or dep[:10] <= today or not f.get("price"): continue
                keep_min(node["rt"], dep[:10] + "|" + ret[:10], f["price"],
                         max(f.get("transfers", 0), f.get("return_transfers", 0)), hhmm(dep))
            time.sleep(0.12)
            # 3) round trips from the month matrix (no times)
            for f in month_matrix(origin, code, mon + "-01"):
                dep, ret = f.get("depart_date", ""), f.get("return_date", "")
                if not dep or not ret or dep <= today or not f.get("value"): continue
                keep_min(node["rt"], dep + "|" + ret, f["value"],
                         f.get("number_of_changes", 0), "")
            time.sleep(0.12)
            # 4) round trips from the price calendar (has times)
            for dep_date, f in calendar_rt(origin, code, mon).items():
                dep, ret = f.get("departure_at", ""), f.get("return_at", "")
                if not dep or not ret or dep[:10] <= today or not f.get("price"): continue
                keep_min(node["rt"], dep[:10] + "|" + ret[:10], f["price"],
                         f.get("transfers", 0), hhmm(dep))
            time.sleep(0.12)

        # how many round-trip combos can the finder compose from one-way pairs?
        composed = 0
        backs = node["back"]
        for d1 in node["out"]:
            y, m_, dd = map(int, d1.split("-"))
            base = date(y, m_, dd)
            for n in range(1, 22):
                if (base + timedelta(days=n)).isoformat() in backs:
                    composed += 1
        n_fares = len(node["out"]) + len(node["back"]) + len(node["rt"])
        total += n_fares
        print(f"    {origin}->{code}: {len(node['rt'])} round-trips, "
              f"{len(node['out'])}/{len(node['back'])} legs, {composed} composed")
        dests[code] = node

    if total < MIN_FARES:
        print(f"FATAL: index too thin ({total} fares) — keeping previous index.")
        sys.exit(1)

    now = datetime.now(ET)
    doc = {"meta": {"built": now.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "label": now.strftime("%a %b %d, %I:%M%p ET").upper(),
                    "origin": origin, "routes": len(dests_list)},
           "dests": dests}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    kb = os.path.getsize(out_path) // 1024
    cities = sum(1 for n in dests.values() if n["out"] or n["back"] or n["rt"])
    print(f"  WROTE {out_path}: {total} fares, {cities} cities with data, {kb}KB")


def main():
    if not TOKEN:
        print("FATAL: TP_TOKEN not set"); sys.exit(1)
    origin = (sys.argv[1] if len(sys.argv) > 1 else "CLT").upper()
    out_path = sys.argv[2] if len(sys.argv) > 2 else f"site/data/idx-{origin}.json"
    today = datetime.now(ET).date().isoformat()
    build_origin(origin, out_path, today)


if __name__ == "__main__":
    main()
