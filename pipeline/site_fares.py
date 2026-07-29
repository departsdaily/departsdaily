#!/usr/bin/env python3
"""Fares from the SITE board, for the Instagram pipeline.

Why this exists (Jul 29 2026, owner's call):
    The site board and the Instagram board were two programs that queried the
    same API separately and got different answers. On Jul 29 the site published
    8 CLT rows while the post published 3, and the site's own run had already
    priced ~30 routes and discarded ~22 of them. Worse, the two could disagree
    in public: the site showed CLT-LAS at $251 the same morning the post showed
    $261.

    So scripts/update_deals.py now writes every route it priced to
    state/fares-<ORIGIN>.json, and this module hands those fares to
    pipeline/fetch_fares.py. One set of fares, one truth, and a big jump in
    supply for free.

FRESHNESS IS THE POINT (owner's rule): fares move overnight, so a snapshot
that is not from THIS MORNING must never reach a post. Anything older than
MAX_FARE_AGE_MIN, or stamped on an earlier date, is refused outright — we would
rather post fewer real deals than post last night's prices as today's.

Nothing here relaxes the honesty bar. These are candidate fares only: they are
still scored against the origin's baselines and still have to clear
MIN_DISCOUNT in fetch_fares.py to reach the board.
"""
import json, os, datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 180 min: the board refresh runs at 6:23am ET and the post fires at 6:52am, so
# a healthy morning snapshot is ~30 minutes old. Three hours leaves room for a
# dropped or delayed refresh (GitHub cron regularly runs late) while still
# making it arithmetically impossible to reach back past ~3:50am — i.e. into
# last night's prices, which is the failure the owner asked us to design out.
MAX_AGE_MIN = int(os.environ.get("MAX_FARE_AGE_MIN", "180"))


def path(code):
    return os.path.join(ROOT, "state", f"fares-{code.upper()}.json")


def load(code, now=None):
    """(offers_by_dest, note). Never raises: a missing or stale snapshot must
    degrade to 'post from the pipeline's own fetch', never crash the morning."""
    now = now or datetime.datetime.now(ET)
    p = path(code)
    if not os.path.exists(p):
        return {}, f"no site snapshot at {os.path.relpath(p, ROOT)}"
    try:
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
        stamp = datetime.datetime.fromisoformat(doc["generated"])
    except (OSError, ValueError, KeyError) as e:
        return {}, f"site snapshot unreadable ({e})"

    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=ET)
    age_min = (now - stamp).total_seconds() / 60.0

    # Two independent guards. The age check catches a slow morning; the date
    # check catches the pathological case of a clock or timezone surprise
    # making a 10pm snapshot look young.
    if stamp.astimezone(ET).date() != now.astimezone(ET).date():
        return {}, (f"site snapshot is from {stamp.astimezone(ET).date()}, not today "
                    f"— refusing to post yesterday's fares")
    if age_min > MAX_AGE_MIN:
        return {}, (f"site snapshot is {age_min:.0f} min old "
                    f"(limit {MAX_AGE_MIN}) — refusing it")

    offers = {}
    for dest, f in (doc.get("fares") or {}).items():
        o = as_offer(code, dest, f)
        if o:
            offers[dest] = [o]
    return offers, (f"site snapshot {stamp.astimezone(ET).strftime('%H:%M %Z')}, "
                    f"{age_min:.0f} min old, {len(offers)} routes")


def as_offer(origin, dest, f):
    """Site board row -> the Travelpayouts offer shape fetch_fares expects."""
    try:
        d1, d2 = f["d1"], f["d2"]
        datetime.date.fromisoformat(d1)
        datetime.date.fromisoformat(d2)
        price = int(f["price"])
    except (KeyError, TypeError, ValueError):
        return None
    if price <= 0:
        return None
    return {"departure_at": d1, "return_at": d2, "price": price,
            # The site resolves the carrier name and deliberately blanks it on
            # connecting itineraries it cannot verify (see carrier_label). We
            # keep that judgement rather than re-deriving a name we'd have to
            # defend.
            "airline": f.get("al") or "",
            "transfers": int(f.get("stops") or 0),
            # Departure times for both legs, straight off the site row. The
            # post should say the same thing the site says.
            "dep_time": f.get("dep") or "",
            "ret_time": f.get("rdep") or "",
            "arr_time": f.get("arr") or "",
            "ret_arr":  f.get("rarr") or "",
            "link": search_link(origin, dest, d1, d2),
            "_src": "site"}


def search_link(origin, dest, d1, d2):
    """A real Aviasales search for exactly these dates, cheapest first.

    The site snapshot has no signed deep link, so we build the standard search
    URL instead of inventing a fare-specific one. That is the honest object
    anyway: the visitor gets today's live prices for this trip, and the
    checkout price stays the only price. Marker is attached by fetch_fares.
    """
    def dm(s):
        d = datetime.date.fromisoformat(s)
        return f"{d.day:02d}{d.month:02d}"
    # The trailing query string is load-bearing: fetch_fares appends
    # "&marker=..." to whatever it gets, so a bare path would produce
    # ".../CLT1308MIA20081&marker=755800" and silently drop the marker —
    # exactly the class of bug that cost us every Fare Finder click before
    # commit dc05020. Verify the rendered href, never the code that builds it.
    return f"/search/{origin.upper()}{dm(d1)}{dest.upper()}{dm(d2)}1?currency=usd"
