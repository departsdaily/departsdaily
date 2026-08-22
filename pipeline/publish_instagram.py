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
import origins, trip_shape

ORG = origins.config()
ORIGIN = ORG["code"]

IG_USER = "me"  # Instagram-login tokens: "me" resolves to the connected account
TOKEN = os.environ["IG_TOKEN"]
RAW_BASE = os.environ["RAW_BASE"]
G = "https://graph.instagram.com/v21.0"

# WHY EVERY ASSET URL CARRIES ?v=  (root cause of the 2026-07-30 outage)
# Cloudflare Pages has no 404.html, so a path that does not exist YET returns
# HTTP 200 with index.html. The wait-for-Pages step only checked for 200, so it
# passed instantly, every time — there was effectively no wait at all. Meta then
# fetched the URL, got HTML, and returned code 36001 "the URL returned an error
# page instead of an image".
# Worse: /daily/* is served with max-age=86400, so that HTML response got cached
# at the edge UNDER THE CANONICAL URL for 24 hours. Once poisoned, no re-fire
# could ever succeed for that date — which is exactly the "re-fire no longer
# clears it" symptom. A version token puts every fetch on a fresh cache key, so
# a poisoned entry can never be handed to Instagram again.
ASSET_VER = os.environ.get("ASSET_VER") or str(int(time.time()))


def asset(name):
    return "%s/%s?v=%s" % (RAW_BASE, name, ASSET_VER)

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

# Meta fetches slide URLs from its OWN data centers. Our workflow probe can see
# a Pages deploy live while Meta's edge still serves stale HTML — that
# propagation gap is the 9004/36001 "media could not be fetched" failure
# (Jul 30, Aug 4, Aug 11). The only reliable place to retry is at Meta's own
# fetch layer: retry the container call itself with backoff. Fetch races are
# the ONLY codes retried — auth blocks (190/200) and everything else still
# fail fast per the runbooks.
FETCH_RACE_CODES = {9004, 36001}

def post_media(path, tries=6, wait=20, **params):
    last = None
    for i in range(1, tries + 1):
        try:
            return post(path, **params)
        except urllib.error.HTTPError as e:
            # _fail (inside post) already read the body and appended it to
            # TRAIL — an HTTPError body can only be read once, so the code
            # comes from the trail, never a second read.
            code = None
            if TRAIL and isinstance(TRAIL[-1].get("response"), dict):
                code = (TRAIL[-1]["response"].get("error") or {}).get("code")
            if code in FETCH_RACE_CODES and i < tries:
                print("media fetch race (code %s), retry %d/%d in %ds"
                      % (code, i, tries - 1, wait))
                last = e
                time.sleep(wait)
                continue
            raise
    raise last

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
    n = d.get("nights")
    stay = " · {} night{}".format(n, "" if n == 1 else "s") if n else ""
    if d.get("deal", True):
        return "{} {} — ${} round trip{} ({}% below typical)".format(
            EMOJI.get(d["to"], "✈️"), d["city"], d["price"], stay, d["disc"])
    return "{} {} — ${} round trip (best fare we found today)".format(
        EMOJI.get(d["to"], "✈️"), d["city"], d["price"])

# Today's angle comes from the weekly plan (config/schedule.json) via
# deals.json. Older boards have no "plan" key and fall back to the original
# generic lead, so a replayed run can never crash on a missing key.
PLAN = B.get("plan") or {}
HEAD = PLAN.get("cover") or "today's verified board"

SECS = B.get("sections") or []
if SECS:
    # FOUR SECTIONS (2026-08-13). The caption mirrors the carousel exactly, in
    # the same order, with the same headings, so someone reading the caption
    # and someone swiping the slides see the same post. A section that came up
    # short says so in its own heading rather than being quietly merged.
    # INSTAGRAM CAPTIONS HARD-CAP AT 2200 CHARACTERS. Four sections of seven
    # rows is about 2,250 — so the full board does not fit and a caption that
    # simply grew with the board would have been rejected, or silently cut
    # mid-fare, on the first genuinely full day. The rows are dropped from the
    # END of each section (they are already best-first), evenly, and the
    # caption says how many it dropped. The SLIDES always carry everything.

    def _render(per_section):
        c = "✈️ {} · {}\n".format(ORG["caption_lead"], date_h)
        c += "Three trip lengths and the cheapest fares out of {}, every morning.\n".format(ORIGIN)
        hidden = 0
        for sec in SECS:
            if not sec["deals"]:
                continue
            # The shape, spelled out, next to the heading. Not decoration: a
            # reader has to be able to tell a Long Weekend from an Extra Long
            # Weekend without counting dates, and this compact wording is the
            # only form of the explainer that fits inside 2200 characters
            # alongside four sections of fares.
            span = trip_shape.SPAN.get(sec["key"], sec.get("angle", ""))
            shown = sec["deals"][:per_section]
            hidden += len(sec["deals"]) - len(shown)
            c += "\n\n— {} ({}) —\n".format(sec["cover"], span)
            c += "\n".join(line(d) for d in shown)
        if hidden:
            c += "\n\n(+{} more on the slides — swipe)".format(hidden)
        for sec in SECS:
            if sec.get("angle") and sec["deals"]:
                c += "\n\n" + sec["angle"]
                break
        return c

    cap = SECTION_BLOCK = _render(99)
else:
    cap = "✈️ {} — {} · {}\n\n".format(ORG["caption_lead"], HEAD.lower(), date_h)
    cap += "\n".join(line(d) for d in B["deals"])
    if PLAN.get("angle"):
        cap += "\n\n" + PLAN["angle"]
cap += ("\n\n📅 Exact dates on every slide"
        "\n✅ Every fare verified before posting — fares move fast and aren't guaranteed"
        "\n🔎 Want different dates? Search every flight out of {} from the button"
        " on departsdaily.com"
        "\n🔗 Booking links in bio"
        "\n🌅 New board every morning at 7AM{}\n\n").format(
            ORIGIN,
            " — follow so you don't miss the next ${} flight".format(
                min(d["price"] for d in B["deals"])) if B["deals"] else "")

# HASHTAG CAP — lowered 15 -> 3 on 2026-08-20.
# WHY: Metricool's 2026 study (24.4M posts, 375,118 accounts, Jan-Feb 2025 vs
# Jan-Feb 2026) found posts using hashtags took 31.70% fewer views and 33.89%
# fewer interactions than posts without them. Instagram now reads topic from the
# caption and the media, not the tag list, and a long tag list looks like reach
# farming. We keep a SHORT local set because a Charlotte-only account still wants
# the geo signal — those are the tags with any remaining discovery value.
# THIS IS AN EXPERIMENT. Watch reach for two weeks in Instagram Insights. To
# revert, set TAG_CAP back to 15. Do not raise it past 30: past 30 tags the
# carousel container call returns id "0" and publish 500s (ig-hashtag-cap-note.md).
TAG_CAP = 3

# Owner rule (Jul 2026): top hashtags only, across ALL accounts — enough for
# discovery, never spammy. Also a hard technical reason: with 31+ tags the
# CAROUSEL container call returns id "0" and media_publish 500s (hit at ATL launch).
tags = list(ORG["hashtags"]) + [
        "#CheapFlights", "#FlightDeals", "#TravelDeals", "#BudgetTravel"]
# Every post now carries all three trip lengths, so it earns all three tags
# rather than the one the old single-shape plan picked.
tags += (["#WeekendGetaway", "#VacationMode", "#BigTrip"] if SECS else
         {"weekend":  ["#WeekendGetaway"],
          "urgent":   ["#LastMinuteTravel"],
          "week":     ["#VacationMode"],
          "friday":   ["#WeekendTrip"],
          "twoweek":  ["#BigTrip"],
          }.get(PLAN.get("shape"), ["#WeekendTrip"]))
for d in B["deals"][:4]:
    t = "#" + "".join(c for c in d["city"] if c.isalnum())
    if t not in tags:
        tags.append(t)
tags = tags[:TAG_CAP]
cap += " ".join(tags)

# FINAL LENGTH GUARD. Instagram rejects a caption over 2200 characters, and the
# limit applies to the WHOLE thing — the fare list plus the closing block plus
# the hashtags. Measured 2026-08-13: four full sections of seven came to 2,335
# and would have been refused on the first genuinely full day. Trimming has to
# happen here, where the real total is known, not while the fare list is being
# built. Rows come off the END of each section, which is the least valuable end
# because they are already sorted best-first, and the caption says how many it
# dropped. The slides always carry every row.
if SECS and len(cap) > 2150:
    _tail = cap[len(SECTION_BLOCK):]
    _per = 7
    while _per > 2 and len(cap) > 2150:
        _per -= 1
        cap = _render(_per) + _tail
    print("caption trimmed to %d rows per section (%d chars)" % (_per, len(cap)))

children = []
# Deal slides first, one promo slide last (owner's rule, Jul 2026). The
# renderer writes the exact order to slides.json because the number of board
# slides varies with the number of deals. Fallback covers a stale render.
try:
    SLIDES = json.load(open(os.path.join(origins.paths(ORIGIN)["out"], "slides.json")))["slides"]
except Exception:
    SLIDES = ["slide1_board.png", "slide2_cta.png"]
print("carousel:", SLIDES)
for s in SLIDES:
    r = post_media(IG_USER + "/media", image_url=asset(s), is_carousel_item="true")
    children.append(r["id"])
    time.sleep(2)
carousel = post(IG_USER + "/media", media_type="CAROUSEL",
                children=",".join(children), caption=cap)
time.sleep(5)
print("published:", post(IG_USER + "/media_publish", creation_id=carousel["id"]))

# Stories are the DRIP's job now (pipeline/post_story.py, owner's rule Jul 29:
# spaced through the day, not piled at 6:52). The loop stays for manual runs
# with STORIES=1.
#
# It reads the RENDERER'S manifest rather than rebuilding filenames from
# deals.json. It used to do the latter, which was fine while there was exactly
# one story per deal-flagged row — and silently wrong the moment the story list
# got capped (2026-08-13: four sections of seven can produce twenty-plus deals,
# far more story frames than the account should push in a day).
_want_stories = os.environ.get("STORIES", "0") == "1"
_stories = []
if _want_stories:
    try:
        _stories = json.load(open(os.path.join(
            origins.paths(ORIGIN)["out"], "slides.json")))["stories"]
    except (OSError, ValueError, KeyError):
        # Pre-manifest render: fall back to the old naming so an old out/ still
        # publishes rather than posting nothing.
        _stories = [{"file": "story_{}_{}.png".format(i, d["to"]), "to": d["to"]}
                    for i, d in enumerate(
                        [x for x in B["deals"] if x.get("deal", True)], 1)]
for st in _stories:
    try:
        r = post_media(IG_USER + "/media",
                 image_url=asset(st["file"]),
                 media_type="STORIES")
        time.sleep(3)
        post(IG_USER + "/media_publish", creation_id=r["id"])
        print("story:", st["to"])
    except Exception as e:
        print("story failed", st["to"], e)
