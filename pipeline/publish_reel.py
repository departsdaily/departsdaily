#!/usr/bin/env python3
"""Publish one Reel to the origin's Instagram account.

HOW THIS DIFFERS FROM THE CAROUSEL PUBLISHER, and why it needs its own file:
a video container is NOT ready the moment Instagram accepts it. Meta downloads
the MP4 and transcodes it, and media_publish on a container that is still
IN_PROGRESS fails with an unhelpful generic error. So this polls
GET /{container}?fields=status_code until FINISHED before publishing. That poll
is the whole reason reels get their own script instead of a branch in
publish_instagram.py.

Guards carried over from the morning publisher and the story drip:
  - the token must resolve to THIS origin's handle before anything is created,
    so a wrong secret can never post Atlanta fares to Charlotte's followers
  - the board must be dated today; a stale board publishes nothing
  - the slot is recorded in state/reel-log-<ORIGIN>.json BEFORE we return, so a
    re-fired workflow in the same slot sees the media id and exits instead of
    posting the same video twice
  - a failure writes out/reel-error-<ORIGIN>.json, because Actions logs age out
    and git is the only thing the ops sandbox can reliably read

Env: IG_TOKEN, RAW_BASE, ORIGIN, REEL_SLOT.
"""
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import origins

ET = ZoneInfo("America/New_York")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "config", "reels.json"), encoding="utf-8"))

ORG = origins.config()
ORIGIN = ORG["code"]
OUT = origins.paths(ORIGIN)["out"]
SLOT = int(os.environ.get("REEL_SLOT") or 0)
TOKEN = os.environ["IG_TOKEN"]
RAW_BASE = os.environ["RAW_BASE"].rstrip("/")
G = "https://graph.instagram.com/v21.0"

STATE = os.path.join("state", "reel-log-%s.json" % ORIGIN)
TRAIL = []

EMOJI = {
    "LAS": "🎰", "CUN": "🏖️", "FLL": "⛱️", "MIA": "🌴", "MCO": "🎢",
    "MSY": "🎷", "DEN": "🏔️", "BNA": "🎸", "SJU": "🏝️", "AUA": "🌺",
    "NYC": "🗽", "BOS": "🦞", "DCA": "🏛️", "ORD": "🌭", "DFW": "🤠",
    "LAX": "🌇", "PHL": "🔔", "HOU": "🚀", "PHX": "🌵", "TPA": "🏴‍☠️",
    "SFO": "🌉", "SEA": "☕", "AUS": "🎤", "PUJ": "🥥", "MBJ": "🇯🇲",
    "NAS": "🐚", "GCM": "🐢", "LON": "☂️", "PAR": "🥐", "ROM": "🏟️",
    "DTW": "🚗", "AMS": "🌷", "CDG": "🥐", "GRU": "⚽", "BOG": "☕",
    "LIM": "🦙", "MEX": "🌮", "GIG": "🏖️", "SAN": "🏄", "PDX": "🌲",
}


def _redact(p):
    return {k: (v if k != "access_token" else "<redacted>") for k, v in p.items()}


def _trail_write(stage, err=None, extra=None):
    d = {"stage": stage, "when": datetime.datetime.now(ET).isoformat()}
    if extra:
        d.update(extra)
    if isinstance(err, urllib.error.HTTPError):
        raw = err.read().decode("utf-8", "replace")
        try:
            d["response"] = json.loads(raw)
        except ValueError:
            d["response"] = {"raw": raw[:1000]}
        d["status"] = err.code
    elif err is not None:
        d["error"] = type(err).__name__ + ": " + str(err)
    TRAIL.append(d)
    try:
        os.makedirs("out", exist_ok=True)
        json.dump({"origin": ORIGIN, "slot": SLOT, "trail": TRAIL},
                  open("out/reel-error-%s.json" % ORIGIN, "w"), indent=1)
    except OSError:
        pass


def call(path, params, method="POST"):
    params = dict(params)
    params["access_token"] = TOKEN
    try:
        if method == "GET":
            url = G + "/" + path + "?" + urllib.parse.urlencode(params)
            with urllib.request.urlopen(url, timeout=45) as r:
                body = json.load(r)
        else:
            data = urllib.parse.urlencode(params).encode()
            with urllib.request.urlopen(G + "/" + path, data=data, timeout=120) as r:
                body = json.load(r)
    except Exception as e:
        _trail_write(path, e, {"params": _redact(params)})
        raise
    TRAIL.append({"call": path, "params": _redact(params), "response": body})
    return body


def load_state():
    try:
        st = json.load(open(STATE))
    except (OSError, ValueError):
        st = {}
    return st if isinstance(st, dict) else {}


def caption(man):
    """Built from the reel's own manifest, so the words can never describe a
    fare the video does not show."""
    feats = man["featured"]
    date_h = datetime.date.fromisoformat(man["date"]).strftime("%a, %b %d").upper()
    cap = "✈️ %s — %s · %s\n\n" % (ORG["caption_lead"], man["label"].lower(), date_h)
    cap += man["caption_lead"] + "\n\n"
    for f in feats:
        n = f.get("nights")
        stay = " · %d night%s" % (n, "" if n == 1 else "s") if n else ""
        cap += "%s %s — $%s round trip%s (%s%% below typical)\n" % (
            EMOJI.get(f["to"], "✈️"), f["city"], f["price"], stay, f["disc"])
    if man.get("plan_angle") and man["shape"] != "board":
        cap += "\n" + man["plan_angle"] + "\n"
    cap += ("\n📅 Exact dates on the site"
            "\n✅ Every fare verified this morning — fares move fast and aren't"
            " guaranteed. The checkout price is the only price."
            "\n🔎 Different dates? Search every flight out of %s on departsdaily.com"
            "\n🔗 Booking links in bio"
            "\n🌅 New verified board every morning at 7AM\n\n") % ORIGIN

    # Owner rule (Jul 2026), all accounts: top hashtags only, hard cap 15.
    # There is a technical floor under that rule too — past 30 tags the
    # container call returns id "0" and the publish 500s (hit at ATL launch).
    tags = list(ORG["hashtags"]) + ["#CheapFlights", "#FlightDeals",
                                    "#TravelDeals", "#BudgetTravel"]
    tags += {"board": ["#FlightDealsDaily"],
             "spotlight": ["#TravelDeal"],
             "destination": ["#TravelInspo"]}.get(man["shape"], ["#Travel"])
    for f in feats[:4]:
        t = "#" + "".join(c for c in f["city"] if c.isalnum())
        if t not in tags:
            tags.append(t)
    return cap + " ".join(tags[:15])


def wait_for_video(url, tries=40, gap=10):
    """Cloudflare Pages has to have deployed the MP4 before Meta fetches it.
    On 2026-07-29 the morning carousel failed exactly this way (code 36001,
    'the URL returned an error page instead of an image') because publish beat
    the Pages build by two seconds. A video is a bigger file, so the race is
    wider, and Meta's error for it is vaguer. Check ourselves first."""
    req = urllib.request.Request(url, method="HEAD")
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                ctype = r.headers.get("Content-Type", "")
                clen = int(r.headers.get("Content-Length") or 0)
                if r.status == 200 and "video" in ctype and clen > 50000:
                    print("video live: %s (%s, %.1fMB)" % (url, ctype, clen / 1e6))
                    return
                print("attempt %d: %s len=%s" % (i + 1, ctype or r.status, clen))
        except Exception as e:
            print("attempt %d: %s" % (i + 1, e))
        time.sleep(gap)
    _trail_write("wait_for_video", None, {"url": url})
    raise SystemExit("FATAL: %s never served as video — refusing to hand "
                     "Instagram a URL that 404s" % url)


def main():
    now = datetime.datetime.now(ET)
    today = now.date().isoformat()

    man_path = os.path.join(OUT, "reel_%d.json" % SLOT)
    if not os.path.exists(man_path):
        raise SystemExit("FATAL: no %s — run pipeline/render_reel.py first" % man_path)
    man = json.load(open(man_path, encoding="utf-8"))

    # A reel built from yesterday's board would post yesterday's prices under
    # today's date. Refuse rather than mislead.
    if man["date"] != today:
        raise SystemExit("FATAL: reel manifest is dated %s, today is %s — "
                         "not posting a stale board" % (man["date"], today))

    st = load_state()
    if st.get("date") == today and str(SLOT) in (st.get("slots") or {}):
        done = st["slots"][str(SLOT)]
        print("slot %d already posted today as media %s (%s) — nothing to do"
              % (SLOT, done.get("media_id"), done.get("shape")))
        return
    if st.get("date") != today:
        st = {"date": today, "slots": {}}

    url = "%s/%s" % (RAW_BASE, man["file"])
    wait_for_video(url)

    # Wrong-account guard first, before a single container exists.
    me = call("me", {"fields": "username"}, "GET")
    if me.get("username", "").lower() != ORG["handle"].lower():
        _trail_write("handle-guard", None,
                     {"resolved": me.get("username"), "expected": ORG["handle"]})
        raise SystemExit("FATAL: token resolves to @%s but ORIGIN=%s expects @%s. "
                         "Check the %s secret."
                         % (me.get("username"), ORIGIN, ORG["handle"],
                            ORG["token_secret"]))
    print("posting %s reel (%s, %.1fs) as @%s"
          % (ORIGIN, man["shape"], man["seconds"], me.get("username")))

    cap = caption(man)
    container = call("me/media", {"media_type": "REELS", "video_url": url,
                                 "caption": cap, "share_to_feed": "true"})
    cid = str(container.get("id") or "")
    # The ATL launch taught us that a container id of "0" is Instagram's way of
    # refusing without an error object. Catch it here rather than 500ing on
    # media_publish and having to reason backwards from a code 1.
    if not cid or cid == "0":
        _trail_write("container", None, {"id": cid, "tags": cap.count("#")})
        raise SystemExit("FATAL: container id %r — Instagram refused without an "
                         "error. Count the caption hashtags (%d here, cap is 15) "
                         "and see departsdaily/ig-hashtag-cap-note.md"
                         % (cid, cap.count("#")))

    # Transcode poll. This is the step images do not need.
    status, waited = "", 0
    for _ in range(60):
        s = call(cid, {"fields": "status_code,status"}, "GET")
        status = s.get("status_code", "")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            _trail_write("transcode", None, {"status": s})
            raise SystemExit("FATAL: Instagram could not process the video (%s): %s"
                             % (status, s.get("status")))
        print("  transcoding... %s (%ds)" % (status or "?", waited))
        time.sleep(5)
        waited += 5
    if status != "FINISHED":
        _trail_write("transcode-timeout", None, {"last": status, "seconds": waited})
        raise SystemExit("FATAL: container %s still %s after %ds"
                         % (cid, status or "unknown", waited))

    pub = call("me/media_publish", {"creation_id": cid})
    media_id = str(pub.get("id") or "")
    print("published reel:", media_id)

    # Record BEFORE returning. A crash after this point must not let a retry
    # post the same video again.
    st["slots"][str(SLOT)] = {"media_id": media_id, "shape": man["shape"],
                              "container": cid, "seconds": man["seconds"],
                              "at": datetime.datetime.now(ET).isoformat()}
    os.makedirs("state", exist_ok=True)
    json.dump(st, open(STATE, "w"), indent=1)


if __name__ == "__main__":
    main()
