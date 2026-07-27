#!/usr/bin/env python3
"""Publish the daily carousel + stories to the origin's Instagram account.

Requires env: IG_TOKEN, RAW_BASE (public URL of today's images), and ORIGIN
(defaults to CLT). Account name, caption lead and city hashtags all come from
config/origins.json — the token decides which account is actually posted to,
so a wrong secret posts to the wrong account. The guard below refuses to run
when the token's account handle does not match the origin we rendered for.
"""
import os, sys, json, time, datetime, urllib.request, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import origins

ORG = origins.config()
ORIGIN = ORG["code"]

IG_USER = "me"  # Instagram-login tokens: "me" resolves to the connected account
TOKEN = os.environ["IG_TOKEN"]
RAW_BASE = os.environ["RAW_BASE"]
G = "https://graph.instagram.com/v21.0"

def post(path, **params):
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(G + "/" + path, data=data, timeout=60) as r:
        return json.load(r)

def get(path, **params):
    params["access_token"] = TOKEN
    url = G + "/" + path + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


# Posting a city's board to the wrong account is not recoverable — it goes out
# to real followers. Confirm the token belongs to the handle this origin claims
# before a single container is created.
me = get("me", fields="username")
if me.get("username", "").lower() != ORG["handle"].lower():
    raise SystemExit(
        "FATAL: token resolves to @{} but ORIGIN={} expects @{}. "
        "Check the {} secret.".format(me.get("username"), ORIGIN,
                                      ORG["handle"], ORG["token_secret"]))
print("posting as @{} for {}".format(me.get("username"), ORIGIN))

EMOJI = {
    "LAS": "🎰", "CUN": "🏖️", "FLL": "⛱️", "MIA": "🌴", "MCO": "🎢",
    "MSY": "🎷", "DEN": "🏔️", "BNA": "🎸", "SJU": "🏝️", "AUA": "🌺",
    "NYC": "🗽", "BOS": "🦞", "DCA": "🏛️", "ORD": "🌭", "DFW": "🤠",
    "LAX": "🌇", "PHL": "🔔", "HOU": "🚀", "PHX": "🌵", "TPA": "🏴‍☠️",
    "SFO": "🌉", "SEA": "☕", "AUS": "🎤", "PUJ": "🥥", "MBJ": "🇯🇲",
    "NAS": "🐚", "GCM": "🐢", "LON": "☂️", "PAR": "🥐", "ROM": "🏟️",
}

B = json.load(open(origins.paths(ORIGIN)["deals"]))
date_h = datetime.date.fromisoformat(B["date"]).strftime("%a, %b %d").upper()
skip = B.get("skip")

cap = "✈️ {} — today's verified board · {}\n\n".format(ORG["caption_lead"], date_h)
cap += "\n".join("{} {} — ${} round trip ({}% below typical)".format(
    EMOJI.get(d["to"], "✈️"), d["city"], d["price"], d["disc"]) for d in B["deals"])
if skip:
    cap += "\n🚫 SKIP: {} — ${}+ right now, above typical. Wait it out.".format(
        skip["city"], skip["price"])
cap += ("\n\n📅 Exact dates on every slide"
        "\n✅ Every fare verified before posting — fares move fast and aren't guaranteed"
        "\n🎯 Flexible dates? Tell the Fare Finder your trip shape — leave Friday,"
        " back Monday, anytime in the next 3 months, under $200 — and it finds the"
        " cheapest fare that fits. On departsdaily.com"
        "\n🔗 Booking links in bio"
        "\n🌅 New board every morning at 7AM\n\n")

tags = list(ORG["hashtags"]) + [
        "#CheapFlights", "#FlightDeals", "#FlightDeal", "#TravelDeals",
        "#AirfareDeals", "#BudgetTravel", "#CheapTravel", "#TravelHacks",
        "#VacationDeals", "#WeekendTrip", "#Travel", "#TravelGram", "#Wanderlust"]
for d in B["deals"]:
    t = "#" + "".join(c for c in d["city"] if c.isalnum())
    if t not in tags:
        tags.append(t)
cap += " ".join(tags)

children = []
for s in ["slide1_cover.png", "slide2_board.png", "slide3_finder.png", "slide4_cta.png"]:
    r = post(IG_USER + "/media", image_url=RAW_BASE + "/" + s, is_carousel_item="true")
    children.append(r["id"])
    time.sleep(2)
carousel = post(IG_USER + "/media", media_type="CAROUSEL",
                children=",".join(children), caption=cap)
time.sleep(5)
print("published:", post(IG_USER + "/media_publish", creation_id=carousel["id"]))

for i, d in enumerate(B["deals"], 1):
    try:
        r = post(IG_USER + "/media",
                 image_url="{}/story_{}_{}.png".format(RAW_BASE, i, d["to"]),
                 media_type="STORIES")
        time.sleep(3)
        post(IG_USER + "/media_publish", creation_id=r["id"])
        print("story:", d["to"])
    except Exception as e:
        print("story failed", d["to"], e)
