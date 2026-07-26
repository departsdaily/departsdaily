#!/usr/bin/env python3
"""Publish daily carousel + stories to @cltdeparts via Instagram Graph API.
Requires env: IG_USER_ID, IG_TOKEN, RAW_BASE (public URL of today's images)."""
import os, json, time, datetime, urllib.request, urllib.parse

IG_USER = "me"  # Instagram-login tokens: "me" resolves to the connected account
TOKEN = os.environ["IG_TOKEN"]
RAW_BASE = os.environ["RAW_BASE"]
G = "https://graph.instagram.com/v21.0"

def post(path, **params):
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(G + "/" + path, data=data, timeout=60) as r:
        return json.load(r)

EMOJI = {"LAS": "🎰", "CUN": "🏖️", "FLL": "⛱️", "MIA": "🌴", "MCO": "🎢",
         "MSY": "🎷", "DEN": "🏔️", "BNA": "🎸", "SJU": "🏝️", "AUA": "🌺"}

B = json.load(open("deals.json"))
date_h = datetime.date.fromisoformat(B["date"]).strftime("%a, %b %d").upper()
skip = B.get("skip")

cap = "✈️ CLT DEPARTURES — today's verified board · {}\n\n".format(date_h)
cap += "\n".join("{} {} — ${} round trip ({}% below typical)".format(
    EMOJI.get(d["to"], "✈️"), d["city"], d["price"], d["disc"]) for d in B["deals"])
if skip:
    cap += "\n🚫 SKIP: {} — ${}+ right now, above typical. Wait it out.".format(
        skip["city"], skip["price"])
cap += ("\n\n📅 Exact dates on every slide"
        "\n✅ Every fare verified before posting — fares move fast and aren't guaranteed"
        "\n🎯 Want different dates? Build a custom search (budget, nonstop, trip"
        " length, weekends + more) with the Fare Finder on our site"
        "\n🔗 Booking links in bio"
        "\n🌅 New board every morning at 7AM\n\n")

tags = ["#CLT", "#Charlotte", "#QueenCity", "#CharlotteNC", "#CLTAirport",
        "#CheapFlights", "#FlightDeals", "#FlightDeal", "#TravelDeals",
        "#AirfareDeals", "#BudgetTravel", "#CheapTravel", "#TravelHacks",
        "#VacationDeals", "#WeekendTrip", "#Travel", "#TravelGram", "#Wanderlust"]
for d in B["deals"]:
    t = "#" + "".join(c for c in d["city"] if c.isalnum())
    if t not in tags:
        tags.append(t)
cap += " ".join(tags)

children = []
for s in ["slide1_cover.png", "slide2_board.png", "slide3_cta.png"]:
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
