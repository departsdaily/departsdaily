#!/usr/bin/env python3
"""Which kind of post is today.

One resolver so fetch_fares, render_slides and publish_instagram can never
disagree about what today's post is supposed to be. Reads config/schedule.json.

Override for testing or a one off:
    POST_SHAPE=twoweek python pipeline/fetch_fares.py
    POST_DATE=2026-08-02 python pipeline/day_plan.py
"""
import datetime, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, "config", "schedule.json")


def _cfg():
    with open(CFG, encoding="utf-8") as fh:
        return json.load(fh)


def today():
    d = os.environ.get("POST_DATE")
    return datetime.date.fromisoformat(d) if d else datetime.date.today()


def plan(day=None):
    """Returns the resolved plan for a date.

    keys: shape, nights, depart_in, cover, angle, content, note, wide, day
    """
    cfg = _cfg()
    day = day or today()
    wd = day.weekday()                      # Monday = 0
    entry = dict(cfg["week"].get(str(wd), {}))

    shape_key = entry.get("shape", "week")
    content = entry.get("content", "board")
    reason = entry.get("note", "")

    # Every other Sunday the two week post takes over.
    alt = cfg.get("alternating") or {}
    if alt and wd == alt.get("weekday"):
        iso_week = day.isocalendar()[1]
        want_even = alt.get("when_iso_week_is", "even") == "even"
        if (iso_week % 2 == 0) == want_even:
            shape_key = alt["shape"]
            content = "board"
            reason = f"ISO week {iso_week}: the every other Sunday two week post."

    # Explicit override always wins, and says so.
    forced = (os.environ.get("POST_SHAPE") or "").strip()
    if forced:
        if forced not in cfg["shapes"]:
            raise SystemExit(
                f"FATAL: POST_SHAPE={forced} is not in config/schedule.json. "
                f"Known shapes: {', '.join(sorted(cfg['shapes']))}")
        shape_key = forced
        content = "board"
        reason = f"POST_SHAPE override: {forced}"

    shape = cfg["shapes"][shape_key]
    return _shape_plan(cfg, shape_key, shape, day, content, reason)


def _shape_plan(cfg, shape_key, shape, day, content, reason):
    return {
        "day": day.isoformat(),
        "weekday": day.strftime("%A"),
        "shape": shape_key,
        "nights": tuple(shape["nights"]),
        "depart_in": tuple(shape["depart_in"]),
        "depart_dow": set(shape["depart_dow"]) if shape.get("depart_dow") else None,
        "return_dow": set(shape["return_dow"]) if shape.get("return_dow") else None,
        "cover": shape["cover"],
        "angle": shape["angle"],
        "content": content,
        "note": reason,
        "min_on_shape": shape.get("min_on_shape"),
        "fallback_shape": shape.get("fallback_shape"),
        "wide": {"nights": tuple(cfg["wide"]["nights"]),
                 "depart_in": tuple(cfg["wide"]["depart_in"])},
    }


def plan_for_shape(shape_key, like):
    """The same day, rebuilt on a different shape. Used when a shape cannot be
    honoured by the day's real fares and has to step aside rather than let the
    cover slide claim something the board does not show."""
    cfg = _cfg()
    if shape_key not in cfg["shapes"]:
        raise SystemExit(f"FATAL: fallback_shape {shape_key} is not in "
                         f"config/schedule.json")
    day = datetime.date.fromisoformat(like["day"])
    return _shape_plan(cfg, shape_key, cfg["shapes"][shape_key], day,
                       like.get("content", "board"),
                       f"stepped down from {like['shape']}: too few real fares "
                       f"matched that shape today")


def sections(day=None):
    """The four sections every post carries, resolved for a date.

    ADDED 2026-08-13 (owner's rule). The carousel is no longer one trip shape
    per weekday — it is Long Weekend, Week Long, Two Weeks and Cheapest, seven
    rows each, every day. plan() above is untouched and still resolves the
    single daily shape, because the reel rotation still uses it.

    Each returned dict is what fetch_fares.build() needs to score one section:
      key, cover, angle, rows, deals_only, sort,
      nights, depart_in, depart_dow, return_dow, wide
    """
    cfg = _cfg()
    day = day or today()
    secs = cfg.get("sections")
    if not secs:
        raise SystemExit("FATAL: config/schedule.json has no `sections`. "
                         "The four-section carousel cannot be built without it.")
    # A single section can be forced for testing:  POST_SECTION=twoweek ...
    only = (os.environ.get("POST_SECTION") or "").strip()
    out = []
    for sec in secs:
        if only and sec["key"] != only:
            continue
        out.append({
            "day": day.isoformat(),
            "weekday": day.strftime("%A"),
            "key": sec["key"],
            "cover": sec["cover"],
            # A short qualifier printed next to the cover on the slide, so each
            # slide says what SHAPE of trip it is showing rather than all three
            # saying "ROUND TRIP". The Cheapest slide uses it to admit up front
            # that its fares need real days booked off.
            "tag": sec.get("tag", "ROUND TRIP"),
            "angle": sec["angle"],
            "rows": int(sec.get("rows", 7)),
            "deals_only": bool(sec.get("deals_only", True)),
            # The bar a row must clear to reach THIS slide. 0.12 for the trip
            # length sections, 0.0 for CHEAPEST — zero, never negative, so no
            # slide can ever showcase a fare above what the route normally costs.
            "min_discount": float(sec.get("min_discount", 0.12)),
            "sort": sec.get("sort", "discount"),
            "nights": tuple(sec["nights"]),
            "depart_in": tuple(sec["depart_in"]),
            "depart_dow": set(sec["depart_dow"]) if sec.get("depart_dow") else None,
            "return_dow": set(sec["return_dow"]) if sec.get("return_dow") else None,
            "wide": {"nights": tuple(cfg["wide"]["nights"]),
                     "depart_in": tuple(cfg["wide"]["depart_in"])},
        })
    if only and not out:
        raise SystemExit(f"FATAL: POST_SECTION={only} is not in "
                         f"config/schedule.json sections.")
    return out


if __name__ == "__main__":
    p = plan()
    print(f"{p['day']} ({p['weekday']})")
    print(f"  shape      {p['shape']}")
    print(f"  nights     {p['nights'][0]}-{p['nights'][1]}")
    print(f"  depart in  {p['depart_in'][0]}-{p['depart_in'][1]} days")
    print(f"  cover      {p['cover']}")
    print(f"  content    {p['content']}")
    print(f"  why        {p['note']}")
    print()
    print("SECTIONS (what the carousel actually posts):")
    for sec in sections():
        n0, n1 = sec["nights"]
        bar = "deals only" if sec["deals_only"] else "no discount claim"
        print(f"  {sec['key']:9} {sec['cover']:22} {n0}-{n1} nights  "
              f"{sec['rows']} rows  {bar}")
