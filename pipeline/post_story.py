#!/usr/bin/env python3
"""Post the NEXT story (or two) from today's board — the story drip.

Owner's rule (Jul 29 2026): stories go out spaced through the day, one deal at
a time, not dumped in a pile at 6:52AM. The account should look alive at 10AM
and 4PM, not just at breakfast. So the morning run publishes the carousel only
(publish_instagram.py, STORIES=0) and this script runs at each drip slot and
posts whatever is next in line.

Doubling rule, also the owner's: when there are more unposted deals than slots
left in the day, post two per slot until the backlog fits. Never more than two
— three stories at once is the pile we were told to stop making.

State lives in state/story-drip-<ORIGIN>.json ({"date", "posted": [codes]}).
A new date resets it. Everything is idempotent: a re-run in the same slot sees
the codes it already posted and moves on, so a retried workflow cannot
double-post a story.

Honesty guards carried over from the morning publisher:
- token must resolve to this origin's handle before anything posts
- stories come only from deal-flagged rows of TODAY's deals.json; a stale
  board (yesterday's date) posts nothing at all
"""
import os, sys, json, time, datetime, urllib.request, urllib.parse, urllib.error
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import origins

ET = ZoneInfo("America/New_York")
ORG = origins.config()
ORIGIN = ORG["code"]
TOKEN = os.environ["IG_TOKEN"]
RAW_BASE = os.environ["RAW_BASE"]
G = "https://graph.instagram.com/v21.0"
# See publish_instagram.py for why: an undeployed path returns 200+HTML and that
# response gets edge-cached under the canonical URL for a day. ?v= keeps every
# fetch on a fresh cache key.
ASSET_VER = os.environ.get("ASSET_VER") or str(int(time.time()))

# Drip slots, ET hours. The workflow cron should fire once inside each. Used
# only to know how many slots REMAIN, which drives the doubling rule.
SLOTS = [int(h) for h in os.environ.get("STORY_SLOTS", "10,13,16,19").split(",")]
MAX_PER_SLOT = 2

STATE = os.path.join("state", "story-drip-%s.json" % ORIGIN)


def call(path, params, method="POST"):
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        req = G + "/" + path + "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    with urllib.request.urlopen(G + "/" + path, data=data, timeout=60) as r:
        return json.load(r)


def _trail(stage, err):
    """A drip that dies unattended must leave evidence a git fetch can see —
    same philosophy as the morning publisher's out/ig-error files."""
    os.makedirs("out", exist_ok=True)
    detail = {"stage": stage, "error": type(err).__name__ + ": " + str(err)}
    if isinstance(err, urllib.error.HTTPError):
        try:
            detail["response"] = json.loads(err.read().decode("utf-8", "replace"))
        except Exception:
            pass
    json.dump({"origin": ORIGIN, "when": datetime.datetime.now(ET).isoformat(),
               "detail": detail},
              open("out/story-drip-error-%s.json" % ORIGIN, "w"), indent=1)


def main():
    now = datetime.datetime.now(ET)
    today = now.date().isoformat()

    B = json.load(open(origins.paths(ORIGIN)["deals"]))
    if B.get("date") != today:
        print("board is dated %s, not today — nothing to drip" % B.get("date"))
        return

    deals = [d for d in B["deals"] if d.get("deal", True)]
    if not deals:
        print("no deal rows — nothing to drip")
        return

    st = {"date": today, "posted": []}
    try:
        old = json.load(open(STATE))
        if old.get("date") == today:
            st = old
    except (OSError, ValueError):
        pass

    # The renderer's manifest is the only place story filenames are decided
    # (2026-08-13). Rebuilding them here from deals.json was safe while every
    # deal-flagged row got a story; it is not safe now that the story list is
    # capped at MAX_STORIES, because the index would point at a file that was
    # never rendered.
    try:
        manifest = json.load(open(os.path.join(
            origins.paths(ORIGIN)["out"], "slides.json")))["stories"]
    except (OSError, ValueError, KeyError):
        manifest = [{"file": "story_%d_%s.png" % (i, d["to"]), "to": d["to"]}
                    for i, d in enumerate(deals, 1)]
    backlog = [m for m in manifest if m["to"] not in st["posted"]]
    if not backlog:
        print("all %d stories already posted today" % len(manifest))
        return

    # Slots strictly after this hour are still to come; this one is in hand.
    slots_left = 1 + sum(1 for h in SLOTS if h > now.hour)
    per_slot = min(MAX_PER_SLOT, -(-len(backlog) // slots_left))  # ceil
    batch = backlog[:per_slot]
    print("backlog %d, slots left %d -> posting %d this slot"
          % (len(backlog), slots_left, len(batch)))

    # Wrong-account guard, same as the morning publisher: a bad secret must
    # fail loudly here, never post Charlotte fares to Atlanta's followers.
    me = call("me", {"fields": "username"}, "GET")
    if me.get("username", "").lower() != ORG["handle"].lower():
        raise SystemExit("FATAL: token resolves to @%s, expected @%s"
                         % (me.get("username"), ORG["handle"]))

    for d in batch:
        url = "%s/%s?v=%s" % (RAW_BASE, d["file"], ASSET_VER)
        try:
            r = call("me/media", {"image_url": url, "media_type": "STORIES"})
            time.sleep(3)
            call("me/media_publish", {"creation_id": r["id"]})
        except Exception as e:
            _trail("publish " + d["to"], e)
            raise
        print("story posted:", d["to"])
        st["posted"].append(d["to"])
        # Persist after EACH publish, not at the end — a crash between two
        # stories must not forget the one that already went out.
        os.makedirs("state", exist_ok=True)
        json.dump(st, open(STATE, "w"), indent=1)
        time.sleep(2)


if __name__ == "__main__":
    main()
