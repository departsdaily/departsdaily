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

deals, skips = [], []
for code in ROUTES:
    if code in recent:
        continue
    try:
        offers = cheapest(code)
    except Exception as e:
        print(code, "fetch failed", e); continue
    if not offers:
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
    (deals if disc >= MIN_DISCOUNT else skips).append(row)

deals.sort(key=lambda x: -x["disc"])
skips.sort(key=lambda x: x["disc"])
board = {"date": today.isoformat(), "origin": ORIGIN,
         "deals": deals[:4], "skip": skips[0] if skips else None}
if not board["deals"]:
    print(f"FATAL: {ORIGIN} produced no qualifying deals — not writing a board.")
    raise SystemExit(1)
json.dump(board, open(PATHS["deals"], "w"), indent=1)
for d in board["deals"]:
    hist[d["to"]] = today.isoformat()
os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
json.dump(hist, open(HISTORY_FILE, "w"), indent=1)
print(f"{ORIGIN} deals:", [d["to"] for d in board["deals"]])
