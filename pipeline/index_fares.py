#!/usr/bin/env python3
"""Fares from the NIGHTLY INDEX, for the Instagram pipeline.

The third supply source, after the site snapshot and the pipeline's own fetch.
site/data/idx-<ORIGIN>.json already holds ~1,250 real CLT trips built by
scripts/build_index.py, and until now the board never looked at a single one
of them. On Jul 29 the index held 162 DFW trips while the morning fetch saw 1
offer and the route was written off as "no fares in window".

Free supply: the calls were already made and paid for last night.

TWO HONESTY RULES ARE ENFORCED HERE, and neither is negotiable:

  1. SAME DAY ONLY. The index is stamped when it was built. If that stamp is
     not today, none of it is used. Publishing yesterday's price as today's
     board is exactly what the owner ruled out.

  2. NO COMPOSED TRIPS. Rows with the `composed` flag are two separate one-way
     tickets added together. The Fare Finder is allowed to show those because
     it LABELS them TWO ONE-WAYS on screen. A board row is read as one bookable
     round trip, so a composed sum there would be a price nobody can actually
     buy. They are dropped, not relabelled.

Everything that survives is still only a candidate: scored against the origin's
baseline and required to clear MIN_DISCOUNT in fetch_fares.py like any other.
"""
import json, os, datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# schema 2 row layout, from scripts/build_index.py:
#   [destIdx, dayOffset, nights, price, stopsOut, stopsBack,
#    depOutMin, arrOutMin, depBackMin, arrBackMin, airline, composed]
I_DEST, I_DAY, I_NIGHTS, I_PRICE, I_STOPS_OUT = 0, 1, 2, 3, 4
I_AIRLINE, I_COMPOSED = 10, 11

# Per route, so one dense market cannot crowd out the rest of the board.
MAX_PER_DEST = int(os.environ.get("INDEX_MAX_PER_DEST", "40"))


def path(code):
    return os.path.join(ROOT, "site", "data", f"idx-{code.upper()}.json")


def load(code, now=None):
    """(offers_by_dest, note). Never raises — a bad index must not stop a post."""
    now = now or datetime.datetime.now(ET)
    p = path(code)
    if not os.path.exists(p):
        return {}, f"no nightly index at {os.path.relpath(p, ROOT)}"
    try:
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
        if doc.get("schema") != 2:
            return {}, f"index schema {doc.get('schema')} not understood (want 2)"
        base = datetime.date.fromisoformat(doc["base"])
        dests = doc["dests"]
        rows = doc["rows"]
        airlines = doc.get("airlines") or {}
    except (OSError, ValueError, KeyError) as e:
        return {}, f"nightly index unreadable ({e})"

    built = _built_date(doc, base)
    if built != now.astimezone(ET).date():
        return {}, (f"nightly index was built {built}, not today — refusing it "
                    f"rather than posting stale prices")

    offers, dropped = {}, 0
    for r in rows:
        try:
            if r[I_COMPOSED]:
                dropped += 1
                continue                     # two one-ways, not a board fare
            dest = dests[r[I_DEST]]
            price = int(r[I_PRICE])
            nights = int(r[I_NIGHTS])
            d1 = base + datetime.timedelta(days=int(r[I_DAY]))
            if price <= 0 or nights < 0:
                continue
        except (IndexError, TypeError, ValueError):
            continue
        d2 = d1 + datetime.timedelta(days=nights)
        code_al = r[I_AIRLINE] if isinstance(r[I_AIRLINE], str) else ""
        offers.setdefault(dest, []).append({
            "departure_at": d1.isoformat(),
            "return_at": d2.isoformat(),
            "price": price,
            # Only claim a carrier on a nonstop, matching the site's rule: on a
            # connecting itinerary the indexed code is the validating carrier
            # and is frequently not who actually flies you.
            "airline": airlines.get(code_al, code_al) if r[I_STOPS_OUT] == 0 else "",
            "transfers": int(r[I_STOPS_OUT] or 0),
            "link": _search_link(code, dest, d1, d2),
            "_src": "index"})

    for dest in offers:
        offers[dest].sort(key=lambda o: o["price"])
        del offers[dest][MAX_PER_DEST:]

    total = sum(len(v) for v in offers.values())
    return offers, (f"nightly index {built}, {total} trips over {len(offers)} routes "
                    f"({dropped} composed rows dropped)")


def _built_date(doc, base):
    """`generated` is authoritative; `base` is the fallback for older files."""
    g = doc.get("generated")
    if g:
        try:
            return datetime.datetime.fromisoformat(g).astimezone(ET).date()
        except ValueError:
            pass
    return base


def _search_link(origin, dest, d1, d2):
    """A live Aviasales search for these dates. Query string is deliberate:
    fetch_fares appends '&marker=', so a bare path would drop the marker."""
    return (f"/search/{origin.upper()}{d1.day:02d}{d1.month:02d}"
            f"{dest.upper()}{d2.day:02d}{d2.month:02d}1?currency=usd")
