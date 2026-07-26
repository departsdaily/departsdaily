#!/usr/bin/env python3
"""Departs Daily - fare fetch + verification. Runs daily via GitHub Actions.
Pulls cheapest fares (Travelpayouts data API), scores vs monthly baselines,
applies 6-day no-repeat, flags skips. Writes deals.json."""
import os, json, datetime, urllib.request, urllib.parse

TP_TOKEN = os.environ["TP_TOKEN"]
ORIGIN = "CLT"
ROUTES = json.load(open("state/baselines.json"))
HISTORY_FILE = "state/history.json"
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
board = {"date": today.isoformat(), "deals": deals[:4], "skip": skips[0] if skips else None}
json.dump(board, open("deals.json", "w"), indent=1)
for d in board["deals"]:
    hist[d["to"]] = today.isoformat()
json.dump(hist, open(HISTORY_FILE, "w"), indent=1)
print("deals:", [d["to"] for d in board["deals"]])
