#!/usr/bin/env python3
"""Departs Daily - fare fetch + verification. Runs daily via GitHub Actions.
Pulls cheapest fares (Travelpayouts data API), scores vs monthly baselines,
applies 6-day no-repeat, flags skips. Writes deals.json.

Origin comes from the ORIGIN env var and defaults to CLT, so an unqualified run
behaves exactly as it did before the pipeline went multi-city."""
import os, sys, json, datetime, urllib.request, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import origins

TP_TOKEN = os.environ["TP_TOKEN"]
ORIGIN = origins.origin_code()
PATHS = origins.paths(ORIGIN)
ROUTES = origins.baselines(ORIGIN)
HISTORY_FILE = PATHS["history"]
NO_REPEAT_DAYS = 6
MIN_DISCOUNT = 0.12
today = datetime.date.today()

def tp(url, params):
    params["token"] = TP_TOKEN
    with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params), timeout=30) as r:
        return json.load(r)

def cheapest(dest):
    data = tp("https://api.travelpayouts.com/aviasales/v3/prices_for_dates", {
        "origin": ORIGIN, "destination": dest, "unique": "false", "sorting": "price",
        "direct": "false", "currency": "usd", "limit": 30, "one_way": "false"})
    return data.get("data", [])

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
    # sanity filter: leaves 3-90 days out, sensible 2-9 day round trip
    o = None
    for cand in offers:
        try:
            dd = datetime.date.fromisoformat(cand["departure_at"][:10])
            rr = datetime.date.fromisoformat((cand.get("return_at") or "")[:10])
        except ValueError:
            continue
        if 3 <= (dd - today).days <= 90 and 2 <= (rr - dd).days <= 9:
            o = cand; break
    if o is None:
        scan[code] = {"outcome": "no fares in window",
                      "why": f"{len(offers)} offers, none leaving 3-90 days out "
                             f"for a 2-9 night trip"}
        continue
    price = round(o["price"])
    dep = datetime.date.fromisoformat(o["departure_at"][:10])
    base = ROUTES[code]["m"][dep.month - 1]
    disc = 1 - price / base
    row = {"to": code, "city": ROUTES[code]["city"], "price": price,
           "d1": o["departure_at"][:10], "d2": (o.get("return_at") or "")[:10],
           "airline": o.get("airline", ""), "stops": o.get("transfers", 0),
           "baseline": base, "disc": round(disc * 100),
           "link": "https://www.aviasales.com" + (o.get("link") or "") + "&marker=755800"}
    scan[code] = {"outcome": "qualified" if disc >= MIN_DISCOUNT else "not a deal",
                  "price": price, "typical": base, "disc_pct": round(disc * 100),
                  "d1": row["d1"], "d2": row["d2"]}
    (deals if disc >= MIN_DISCOUNT else skips).append(row)

deals.sort(key=lambda x: -x["disc"])
skips.sort(key=lambda x: x["disc"])
board = {"date": today.isoformat(), "origin": ORIGIN,
         "deals": deals[:4], "skip": skips[0] if skips else None}
os.makedirs("out", exist_ok=True)
counts = {}
for v in scan.values():
    counts[v["outcome"]] = counts.get(v["outcome"], 0) + 1
json.dump({"date": today.isoformat(), "origin": ORIGIN,
           "routes_considered": len(ROUTES), "min_discount_pct": MIN_DISCOUNT * 100,
           "summary": counts, "routes": scan},
          open(f"out/scan-{ORIGIN}.json", "w"), indent=1)
print(f"{ORIGIN} scan:", counts)
for c, v in sorted(scan.items(), key=lambda kv: kv[1].get("disc_pct", -999), reverse=True):
    print(f"  {c:4} {v['outcome']:18}", v.get("why") or
          f"${v.get('price')} vs typical ${v.get('typical')} = {v.get('disc_pct')}%")

if not board["deals"]:
    print(f"FATAL: {ORIGIN} produced no qualifying deals — not writing a board.")
    raise SystemExit(1)
json.dump(board, open(PATHS["deals"], "w"), indent=1)
for d in board["deals"]:
    hist[d["to"]] = today.isoformat()
os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
json.dump(hist, open(HISTORY_FILE, "w"), indent=1)
print(f"{ORIGIN} deals:", [d["to"] for d in board["deals"]])
