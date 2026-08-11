#!/usr/bin/env python3
"""Post the 5-slide how-it-works explainer carousel for ORIGIN (CLT/ATL).
One-off promo publisher — the daily pipeline is untouched. Guards:
- aborts unless the token resolves to the expected handle
- retries slide containers on Meta media-fetch races (9004/36001)
- aborts on carousel container id "0" (hashtag-cap bug signature)
Env: ORIGIN, IG_TOKEN, ASSET_VER. Prints the permalink on success.
"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error

ORIGIN = os.environ.get("ORIGIN", "CLT").upper()
TOKEN = os.environ["IG_TOKEN"]
VER = os.environ.get("ASSET_VER", str(int(time.time())))
G = "https://graph.instagram.com/v21.0"
ORG = json.load(open("config/origins.json"))[ORIGIN]
EXPECT = ORG["handle"]
CITY = {"CLT": "Charlotte", "ATL": "Atlanta"}.get(ORIGIN, ORIGIN)
CITY_TAG = {"CLT": "#CharlotteNC", "ATL": "#Atlanta"}.get(ORIGIN, "")
TRAIL = []

def _fail(path, params, err):
    d = {"call": path}
    if isinstance(err, urllib.error.HTTPError):
        raw = err.read().decode("utf-8", "replace")
        try: d["response"] = json.loads(raw)
        except ValueError: d["response"] = {"raw": raw[:1000]}
        d["status"] = err.code
    else:
        d["error"] = type(err).__name__ + ": " + str(err)
    TRAIL.append(d)
    os.makedirs("out", exist_ok=True)
    json.dump({"origin": ORIGIN, "trail": TRAIL},
              open("out/explainer-error-%s.json" % ORIGIN, "w"), indent=1)

def call(path, method_post=True, **params):
    params["access_token"] = TOKEN
    try:
        if method_post:
            data = urllib.parse.urlencode(params).encode()
            r = urllib.request.urlopen(G + "/" + path, data=data, timeout=60)
        else:
            r = urllib.request.urlopen(G + "/" + path + "?" +
                                       urllib.parse.urlencode(params), timeout=30)
        body = json.load(r)
    except Exception as e:
        _fail(path, params, e); raise
    TRAIL.append({"call": path, "response": body})
    return body

def call_media(path, tries=6, wait=20, **params):
    for i in range(1, tries + 1):
        try:
            return call(path, **params)
        except urllib.error.HTTPError:
            code = None
            if TRAIL and isinstance(TRAIL[-1].get("response"), dict):
                code = (TRAIL[-1]["response"].get("error") or {}).get("code")
            if code in (9004, 36001) and i < tries:
                print("fetch race (code %s), retry %d in %ds" % (code, i, wait))
                time.sleep(wait); continue
            raise
    raise SystemExit("retries exhausted")

# Wrong-account guard — same rule as the daily publisher.
me = call("me", method_post=False, fields="username")
if me.get("username") != EXPECT:
    raise SystemExit("FATAL: token resolves to %r, expected %r — not posting"
                     % (me.get("username"), EXPECT))
print("account ok:", me["username"])

caption = (
    "How a $58 flight ends up on this page \U0001F9F5\n\n"
    "Our system scans 30 routes out of " + CITY + " every single night, "
    "checks every fare against official DOT airfare data, and only posts "
    "fares at least 12% below typical. No filler, no fake urgency, no "
    "expired deals.\n\n"
    "New board every morning at 7AM. Follow so you never miss one.\n\n"
    "departsdaily.com\n\n"
    "#CheapFlights #FlightDeals #TravelDeals #BudgetTravel " + CITY_TAG)

children = []
for n in range(1, 6):
    url = "https://departsdaily.com/promo/explainer-%s-%d.png?v=%s" % (ORIGIN, n, VER)
    r = call_media("me/media", image_url=url, is_carousel_item="true")
    children.append(r["id"]); time.sleep(2)

car = call("me/media", media_type="CAROUSEL",
           children=",".join(children), caption=caption)
if str(car.get("id")) == "0":
    raise SystemExit("FATAL: carousel container id 0 — see ig-hashtag-cap-note.md")
time.sleep(5)
pub = call("me/media_publish", creation_id=car["id"])
link = call(str(pub["id"]), method_post=False, fields="permalink")
print("PUBLISHED %s: %s" % (ORIGIN, link.get("permalink")))
os.makedirs("out", exist_ok=True)
open("out/explainer-posted-%s.txt" % ORIGIN, "w").write(
    "%s %s\n" % (pub["id"], link.get("permalink", "")))
