#!/usr/bin/env python3
"""
Departs Daily — baseline seeder.

Writes state/baselines-<ORIGIN>.json: the "typical cheap round trip" figure for
every tracked destination, month by month. The daily Instagram board scores each
live fare against these numbers to produce its "% BELOW TYPICAL" badge, so the
badge is only as honest as this file.

Method (identical to how Charlotte's curves were hand-tuned, now written down):

  monthly[m] = annual_level * shape[m]

  annual_level comes from the best statistic available for the route:
    DOT      - DOT Consumer Airfare Report city-pair average (round trip)
               x the domestic cheap-fare factor. Real government data.
    ESTIMATE - no DOT city-pair data exists (international, Puerto Rico), so a
               labelled estimate x the international factor. Must stay labelled.
    CLT      - the route already has a hand-tuned Charlotte curve and no
               origin-specific data justifies changing it; reuse it verbatim.

  shape is the seasonality profile for the destination type, derived from the
  original CLT curves. See config/seasonality.json for both.

Nothing here reads live fares. The nightly index is used only as a SANITY CHECK:
the script prints the cheapest fares actually seen on each route next to the
seeded floor, and flags any route where the seeded typical sits below what the
market is really charging — that combination would manufacture fake discounts,
so it should never ship silently.

Usage:
    python scripts/seed_baselines.py ATL
    python scripts/seed_baselines.py ATL --check-only
"""
import json, os, statistics, sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from update_deals import dests_for            # the origin's own top-30 list

CFG = os.path.join(ROOT, "config", "seasonality.json")
ORIGINS_CFG = os.path.join(ROOT, "config", "origins.json")
CLT_LEGACY = os.path.join(ROOT, "state", "baselines.json")

MIN_SAMPLES_FOR_CHECK = 10     # below this the index is too thin to say anything


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def observed(origin):
    """Cheapest real fares per destination from the nightly index, for the
    sanity check only. Returns {dest: {month: [prices]}}."""
    path = os.path.join(ROOT, "site", "data", f"idx-{origin}.json")
    if not os.path.exists(path):
        return {}
    doc = load(path)
    base = date.fromisoformat(doc["base"])
    dests = doc["dests"]
    out = {}
    for r in doc["rows"]:
        dep = base + timedelta(days=r[1])
        out.setdefault(dests[r[0]], {}).setdefault(dep.month, []).append(r[3])
    return out


def build(origin, cfg, legacy_clt):
    # state/baselines.json is Charlotte's original hand-seeded file. For CLT it
    # is that origin's own tuned data; for anyone else it is only a source of
    # international curves to reuse.
    own_tuned = legacy_clt if origin == "CLT" else {}
    shapes = cfg["shapes"]
    factor = cfg["cheap_fare_factor"]
    dot = cfg.get("dot_round_trip", {}).get(origin, {})
    shared = cfg.get("_dot_shared_market", {}).get(origin, {})
    est = cfg["intl_estimate_round_trip"]
    us_est = cfg.get("us_estimate_round_trip", {})

    routes, notes = {}, []
    # Every destination this origin actually tracks — not the union of all of
    # them. CLT's list and ATL's list differ (ATL flies DTW and AMS, CLT flies
    # AUS and ROM), and seeding a curve for a route an origin does not track
    # would put a city on its board that its own index never fetches fares for.
    for code in dests_for(origin):
        if code == origin:
            continue
        meta = cfg["destinations"].get(code)
        if not meta:
            notes.append(f"{code} is in this origin's top 30 but has no entry in "
                         f"config/seasonality.json destinations — skipped")
            continue
        shape = shapes[meta["shape"]]

        # An origin's own hand-tuned curve always wins. Charlotte's ten curves
        # are where this entire methodology came from; re-deriving them from
        # DOT would move live badges for no gain.
        if code in own_tuned:
            routes[code] = {"city": meta["city"],
                            "m": list(own_tuned[code]["m"]),
                            "basis": "TUNED",
                            "src": f"hand-tuned {origin} curve, unchanged — the "
                                   f"original curves this methodology was "
                                   f"derived from",
                            "intl": bool(meta["intl"]), "ig_board": True}
            continue

        if code in dot:
            level = dot[code] * factor["domestic"]
            src = (f"DOT Consumer Airfare Report Table 6, Q4 2025, "
                   f"{origin}-{code} ${dot[code]} round trip x {factor['domestic']}")
            basis = "DOT"
            if code in shared:
                src += f" ({shared[code]})"
        elif code in us_est:
            # DOMESTIC LABELLED ESTIMATE (2026-08-14). DOT only publishes city pairs
            # averaging 10+ passengers a day, so it has nothing for Nantucket, Aspen,
            # Jackson Hole, Key West or Destin — which are exactly the destinations a
            # leisure account exists to show. The number in us_estimate_round_trip IS
            # the typical cheap round trip, so NO cheap-fare factor is applied. It is
            # an estimate and it says so on every slide that carries it.
            level = us_est[code]
            src = (f"labelled ESTIMATE ${us_est[code]} typical cheap round trip — DOT "
                   f"publishes no city pair for {origin}-{code}")
            basis = "ESTIMATE"
        elif code in est:
            # A destination Charlotte already has a hand-tuned curve for, with
            # no origin-specific reason to move it, keeps that curve exactly.
            if origin != "CLT" and code in legacy_clt:
                routes[code] = {"city": meta["city"],
                                "m": list(legacy_clt[code]["m"]),
                                "basis": "CLT",
                                "src": "estimate — reuses the hand-tuned CLT curve; "
                                       "no DOT city-pair data exists for this market",
                                "intl": True, "ig_board": True}
                continue
            # Which cheap_fare_factor this shape uses. Was an inline
            # "europe if shape is europe else caribbean", which had no way to
            # express the 'latam' and 'pacific' shapes added 2026-08-13. The
            # map lives in config/seasonality.json now; the old rule is the
            # fallback so an unmapped shape still behaves exactly as before.
            fk = cfg.get("shape_factor", {}).get(
                meta["shape"],
                "europe" if meta["shape"] == "europe" else "caribbean")
            level = est[code] * factor[fk]
            src = (f"labelled ESTIMATE ${est[code]} round trip x {factor[fk]} "
                   f"({fk}) — no DOT city-pair data for this market")
            basis = "ESTIMATE"
        else:
            notes.append(f"no level source for {code} — skipped")
            continue

        routes[code] = {
            "city": meta["city"],
            "m": [int(round(level * s)) for s in shape],
            "basis": basis,
            "src": src,
            "intl": bool(meta["intl"]),
            "ig_board": True,
        }
    return routes, notes


def sanity_check(origin, routes):
    """Flag any route whose seeded typical sits at or below the cheapest fares
    the market is actually showing. That would print a discount badge on a fare
    that is not, in fact, a discount — so the route is benched off the Instagram
    board (ig_board: false) rather than shipped with a number we can't defend.
    It stays in the file: the Fare Finder and the site board still use it, and it
    returns to the board as soon as its level is corrected or the data improves."""
    obs = observed(origin)
    if not obs:
        print(f"  (no site/data/idx-{origin}.json — skipping the market check)")
        return []
    print(f"\n  {'DEST':5} {'BASIS':9} {'SEEDED':>7} {'MKT MED':>8} {'MKT MIN':>8}  {'n':>4}")
    problems = []
    for code, r in sorted(routes.items()):
        months = obs.get(code, {})
        prices = [p for ps in months.values() for p in ps]
        n = len(prices)
        r["check"] = f"n={n}"
        if n < MIN_SAMPLES_FOR_CHECK:
            r["check"] = f"n={n} — too thin to verify against the market"
            print(f"  {code:5} {r['basis']:9} {'':>7} {'':>8} {'':>8}  {n:>4}  thin")
            continue
        # Compare like with like: seeded typical for the months we saw fares in.
        seeded = statistics.mean(r["m"][m - 1] for m in months)
        med, mn = statistics.median(prices), min(prices)
        flag = ""
        if seeded <= med:
            flag = "  <-- BENCHED: seeded below market median"
            problems.append(code)
            r["ig_board"] = False
            r["ig_board_reason"] = (
                f"seeded typical ${seeded:.0f} sits at or below the ${med:.0f} median "
                f"of {n} real cached fares — a discount badge here would not be real")
        print(f"  {code:5} {r['basis']:9} {seeded:7.0f} {med:8.0f} {mn:8.0f}  {n:>4}{flag}")
    return problems


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    check_only = "--check-only" in sys.argv
    if not args:
        print(__doc__); sys.exit(1)
    origin = args[0].upper()

    origins = load(ORIGINS_CFG)
    if origin not in origins:
        print(f"FATAL: {origin} is not in config/origins.json — add it there first.")
        sys.exit(1)

    cfg = load(CFG)
    legacy_clt = load(CLT_LEGACY) if os.path.exists(CLT_LEGACY) else {}

    routes, notes = build(origin, cfg, legacy_clt)
    for n in notes:
        print("  NOTE:", n)

    by_basis = {}
    for r in routes.values():
        by_basis[r["basis"]] = by_basis.get(r["basis"], 0) + 1
    tracked = len([d for d in dests_for(origin) if d != origin])
    print(f"\n{origin}: {len(routes)}/{tracked} tracked destinations seeded — " +
          ", ".join(f"{v} {k}" for k, v in sorted(by_basis.items())))

    problems = sanity_check(origin, routes)
    if problems:
        print(f"\n  BENCHED off the Instagram board: {', '.join(problems)} — seeded "
              f"typical at or below the market median. They stay in the file for the "
              f"Fare Finder; raise the level in config/seasonality.json and re-run to "
              f"put them back on the board.")
    live = sum(1 for r in routes.values() if r.get("ig_board"))
    print(f"  {live}/{len(routes)} routes cleared for the Instagram board.")
    if live < 8:
        print("  WARNING: fewer than 8 board-eligible routes — with the 6-day "
              "no-repeat rule the board will run out of cities.")

    if check_only:
        print("\n--check-only: nothing written.")
        return

    doc = {
        "_generated_by": "scripts/seed_baselines.py from config/seasonality.json",
        "_meaning": "m[0..11] = typical CHEAP round-trip fare for that month, in USD. "
                    "Not an average fare — the board compares live fares against what a "
                    "good price normally looks like. Every route carries the source of "
                    "its level in `src`; ESTIMATE routes must stay labelled as estimates "
                    "wherever they are shown.",
        "_origin": origin,
        "routes": routes,
    }
    out = os.path.join(ROOT, "state", f"baselines-{origin}.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
    print(f"\nWROTE {out}")


if __name__ == "__main__":
    main()
