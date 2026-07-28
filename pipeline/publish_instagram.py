#!/usr/bin/env python3
"""Publish the daily carousel + stories to the origin's Instagram account.

Requires env: IG_TOKEN, RAW_BASE (public URL of today's images), and ORIGIN
(defaults to CLT). Account name, caption lead and city hashtags all come from
config/origins.json — the token decides which account is actually posted to,
so a wrong secret posts to the wrong account. The guard below refuses to run
when the token's account handle does not match the origin we rendered for.
"""
import os, sys, json, time, datetime, urllib.request, urllib.parse, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import origins

ORG = origins.config()
ORIGIN = ORG["code"]

IG_USER = "me"  # Instagram-login tokens: "me" resolves to the connected account
TOKEN = os.environ["IG_TOKEN"]
RAW_BASE = os.environ["RAW_BASE"]
G = "https://graph.instagram.com/v21.0"

# A publish failure used to surface as a bare HTTP 400 with the useful part —
# Instagram's own explanation — thrown away inside the exception body. Every
# call now records what it asked for and what came back, and the trail is
# written to out/ig-error-<ORIGIN>.json when something goes wrong. The access
# token is never recorded.
TRAIL = []


def _redact(params):
    return {k: (v if k != "access_token" else "<redacted>") for k, v in params.items()}


def _fail(path, params, err):
    detail = {"call": path, "params": _redact(params)}
    if isinstance(err, urllib.error.HTTPError):
        raw = err.read().decode("utf-8", "replace")
        try:
            detail["response"] = json.loads(raw)
        except ValueError:
            detail["response"] = {"raw": raw[:1000]}
        detail["status"] = err.code
    else:
        detail["error"] = type(err).__name__ + ": " + str(err)
    TRAIL.append(detail)
    try:
        os.makedirs("out", exist_ok=True)
        with open("out/ig-error-%s.json" % ORIGIN, "w") as fh:
            json.dump({"origin": ORIGIN, "trail": TRAIL}, fh, indent=1)
    except OSError:
        pass
    print("IG CALL FAILED:", json.dumps(detail)[:1200])


def post(path, **params):
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(G + "/" + path, data=data, timeout=60) as r:
            body = json.load(r)
    except Exception as e:
        _fail(path, params, e)
        raise
    TRAIL.append({"call": path, "params": _redact(params), "response": body})
    return body

def get(path, **params):
    params["access_token"] = TOKEN
    url = G + "/" + path + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            body = json.load(r)
    except Exception as e:
        _fail(path, params, e)
        raise
    TRAIL.append({"call": path, "params": _redact(params), "response": body})
    return body


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

def line(d):
    """Deals earned their % claim; fillers are labelled as what they are —
    the best verified fare we found today, not a deal."""
    if d.get("deal", True):
        return "{} {} — ${} round trip ({}% below typical)".format(
            EMOJI.get(d["to"], "✈️"), d["city"], d["price"], d["disc"])
    return "{} {} — ${} round trip (best fare we found today)".format(
        EMOJI.get(d["to"], "✈️"), d["city"], d["price"])

cap = "✈️ {} — today's verified board · {}\n\n".format(ORG["caption_lead"], date_h)
cap += "\n".join(line(d) for d in B["deals"])
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

# Stories exist only for true deals — the renderer numbers them 1..N over the
# deal-flagged rows, so this loop must walk exactly the same list.
for i, d in enumerate([x for x in B["deals"] if x.get("deal", True)], 1):
    try:
        r = post(IG_USER + "/media",
                 image_url="{}/story_{}_{}.png".format(RAW_BASE, i, d["to"]),
                 media_type="STORIES")
        time.sleep(3)
        post(IG_USER + "/media_publish", creation_id=r["id"])
        print("story:", d["to"])
    except Exception as e:
        print("story failed", d["to"], e)
