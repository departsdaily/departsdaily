#!/usr/bin/env python3
"""Publish daily carousel + stories to @cltdeparts via Instagram Graph API.
Requires env: IG_USER_ID, IG_TOKEN, RAW_BASE (public URL of today's images)."""
import os, json, time, urllib.request, urllib.parse

IG_USER = os.environ["IG_USER_ID"]
TOKEN = os.environ["IG_TOKEN"]
RAW_BASE = os.environ["RAW_BASE"]
G = "https://graph.facebook.com/v21.0"

def post(path, **params):
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(G + "/" + path, data=data, timeout=60) as r:
        return json.load(r)

B = json.load(open("deals.json"))
lines = ["{} ${} ({}% below typical)".format(d["city"], d["price"], d["disc"])
         for d in B["deals"]]
skip = B.get("skip")
cap = "CLT DEPARTURES - today's verified board: " + " | ".join(lines)
if skip:
    cap += " | SKIP: {} ${}+, above typical right now.".format(skip["city"], skip["price"])
cap += (" Dates on every slide. Every fare verified before posting - fares change"
        " fast and are not guaranteed. Booking links in bio. New board daily at 7AM."
        " #CLT #Charlotte #CheapFlights #TravelDeals")

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
