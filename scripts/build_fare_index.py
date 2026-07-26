#!/usr/bin/env python3
"""
Departs Daily — Fare Finder index builder.

Builds site/data/idx-CLT.json: every cached fare for the next ~5 months on
all 30 tracked routes, so the Fare Finder can answer "cheapest long weekend
in September under $400" instantly in the browser.

Shape:
{
  "meta": {"built": iso8601_ET, "origin": "CLT", "routes": N},
  "dests": {
    "LAS": {
      "out":  {"YYYY-MM-DD": [price, stops, "HH:MM"]},   # one-way CLT->LAS
      "back": {"YYYY-MM-DD": [price, stops, "HH:MM"]},   # one-way LAS->CLT
      "rt":   {"YYYY-MM-DD|YYYY-MM-DD": [price, maxstops, "HH:MM"]}  # real round trips
    }, ...
  }
}

Honesty rules: every number is a real fare found in the Aviasales search
cache. One-way sums can differ from live round-trip pricing; the page says
so and every click runs a live search. Real RT fares (rt) are preferred by
the front end when both exist for a date pair.

Usage: TP_TOKEN=... python scripts/build_fare_index.py site/data/idx-CLT.json
"""
import json, os, sys, time, urllib.request, urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ORIGIN = "CLT"
TOKEN = os.environ.get("TP_TOKEN", "")
MONTHS_AHEAD = 5

# Same 30 tracked destinations as the board (city codes for metro areas).
DESTS = ["NYC","BOS","MIA","FLL","DCA","ORD","DFW","MCO","LAX","DEN","PHL","HOU",
         "LAS","PHX","TPA","BNA","MSY","SFO","SEA","AUS",
         "CUN","PUJ","MBJ","NAS","AUA","SJU","GCM","LON","PAR","ROM"]

def api(params):
    url = ("https://api.travelpayouts.com/aviasales/v3/prices_for_dates?"
           + urllib.parse.urlencode({**params, "currency": "usd", "market": "us",
                                     "limit": 1000, "sorting": "price", "token": TOKEN}))
    req = urllib.request.Request(url, headers={"User-Agent": "departsdaily-index"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r).get("data", [])
        except Exception as e:
            if attempt == 2:
                print("  api fail:", params.get("origin"), params.get("destination"),
                      params.get("departure_at"), e)
                return []
            time.sleep(2)

def hhmm(iso):
    return iso[11:16]

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
    cur = d.get(key)
    if cur is None or price < cur[0]:
        d[key] = [int(price), int(stops), t]

def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "site/data/idx-CLT.json"
    if not TOKEN:
        print("FATAL: TP_TOKEN not set"); sys.exit(1)
    today = datetime.now(ET).date().isoformat()
    dests, total = {}, 0
    for code in DESTS:
        node = {"out": {}, "back": {}, "rt": {}}
        for mon in months():
            # one-way legs, both directions
            for direction, o, d in (("out", ORIGIN, code), ("back", code, ORIGIN)):
                for f in api({"origin": o, "destination": d, "one_way": "true",
                              "departure_at": mon}):
                    dep = f.get("departure_at", "")
                    if dep[:10] <= today or not f.get("price"): continue
                    keep_min(node[direction], dep[:10], f["price"],
                             f.get("transfers", 0), hhmm(dep))
                time.sleep(0.12)
            # real round trips (often cheaper than one-way sums)
            for f in api({"origin": ORIGIN, "destination": code, "one_way": "false",
                          "departure_at": mon}):
                dep, ret = f.get("departure_at", ""), f.get("return_at", "")
                if not dep or not ret or dep[:10] <= today or not f.get("price"): continue
                keep_min(node["rt"], dep[:10] + "|" + ret[:10], f["price"],
                         max(f.get("transfers", 0), f.get("return_transfers", 0)), hhmm(dep))
            time.sleep(0.12)
        n = len(node["out"]) + len(node["back"]) + len(node["rt"])
        total += n
        print(f"  {code}: out={len(node['out'])} back={len(node['back'])} rt={len(node['rt'])}")
        dests[code] = node

    if total < 100:
        print(f"FATAL: index too thin ({total} fares) — keeping previous index.")
        sys.exit(1)

    now = datetime.now(ET)
    doc = {"meta": {"built": now.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "label": now.strftime("%a %b %d, %I:%M%p ET").upper(),
                    "origin": ORIGIN, "routes": len(DESTS)},
           "dests": dests}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    print(f"WROTE {out_path}: {total} fares across {len(DESTS)} routes, "
          f"{os.path.getsize(out_path)//1024}KB")

if __name__ == "__main__":
    main()
