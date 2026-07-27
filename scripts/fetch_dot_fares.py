#!/usr/bin/env python3
"""
Departs Daily — DOT city-pair average fetcher.

Pulls the DOT Consumer Airfare Report, Table 6 (contiguous-state city-pair
markets averaging at least 10 passengers a day) straight from the federal open
data portal and writes the round-trip averages into config/seasonality.json,
where scripts/seed_baselines.py picks them up.

This exists because the numbers used to be transcribed by hand, one origin at a
time, which is how Charlotte ended up with ten routes while Atlanta had twenty.
Now every origin gets the same treatment from the same source in one run, and
the run is repeatable when DOT publishes a new quarter.

  source     data.transportation.gov resource yj5y-b2ir (Table 6)
  quarter    the most recent one present in the dataset, discovered at runtime
  fare       DOT reports an average ONE-WAY market fare, so it is doubled here
             to the round-trip figure the rest of the pipeline speaks in
  markets    DOT aggregates by city market, not airport: Ft. Lauderdale sits
             inside the Miami market, DCA inside Washington, and so on. Those
             collapses are recorded in `_dot_shared_market` so the site can say
             out loud which airport a number really covers.

Nothing is estimated here. A route DOT does not publish is simply absent, and
the seeder then either reuses a hand-tuned curve or falls back to a LABELLED
estimate — it never invents a government number.

Usage:
    python scripts/fetch_dot_fares.py              # every origin, writes config
    python scripts/fetch_dot_fares.py CLT ATL      # just these
    python scripts/fetch_dot_fares.py --dry-run    # print, write nothing
"""
import json, os, sys, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from update_deals import dests_for                     # single source of truth

CFG = os.path.join(ROOT, "config", "seasonality.json")
AUDIT = os.path.join(ROOT, "config", "dot-source.json")
RESOURCE = "https://data.transportation.gov/resource/yj5y-b2ir.json"

# Origins we hold data for. Mirrors ORIGINS in scripts/build_index.py.
ALL_ORIGINS = ["CLT", "ATL", "ORD", "DFW", "DEN", "LAX", "JFK", "MIA", "SEA", "BOS"]

# Airport -> the DOT city market that contains it, as "City, ST". DOT suffixes
# some of these with " (Metropolitan Area)"; that suffix is stripped before the
# comparison, so both spellings match. Airports sharing a value share a market
# and therefore share a fare — that is a fact about the data, not a shortcut,
# and it gets disclosed in _dot_shared_market.
MARKET = {
    "CLT": "Charlotte, NC",
    "ATL": "Atlanta, GA",
    "NYC": "New York City, NY",
    "JFK": "New York City, NY",
    "BOS": "Boston, MA",
    "MIA": "Miami, FL",
    "FLL": "Miami, FL",
    "DCA": "Washington, DC",
    "ORD": "Chicago, IL",
    "DFW": "Dallas/Fort Worth, TX",
    "MCO": "Orlando, FL",
    "LAX": "Los Angeles, CA",
    "DEN": "Denver, CO",
    "PHL": "Philadelphia, PA",
    "HOU": "Houston, TX",
    "LAS": "Las Vegas, NV",
    "PHX": "Phoenix, AZ",
    "TPA": "Tampa, FL",
    "BNA": "Nashville, TN",
    "MSY": "New Orleans, LA",
    "SFO": "San Francisco, CA",
    "SEA": "Seattle, WA",
    "AUS": "Austin, TX",
    "DTW": "Detroit, MI",
    "MSP": "Minneapolis/St. Paul, MN",
    "SAN": "San Diego, CA",
    "RDU": "Raleigh/Durham, NC",
}

# Airports the market label should name explicitly, because the market name
# does not contain the airport's own city.
COLLAPSE_NOTE = {
    "FLL": "Miami, FL metro area — DOT does not report Ft. Lauderdale separately",
    "DCA": "Washington, DC metro area — DOT does not report National separately",
    "JFK": "New York City, NY metro area — DOT does not report JFK separately",
    "SFO": "San Francisco, CA metro area — Bay Area airports are one DOT market",
}


def get(params):
    url = RESOURCE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "departsdaily-dot"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def field_names():
    """Socrata lower-cases most column names but not always. Ask, don't guess."""
    row = get({"$limit": 1})[0]
    keys = {k.lower(): k for k in row}
    missing = [n for n in ("year", "quarter", "city1", "city2", "fare") if n not in keys]
    if missing:
        raise SystemExit(f"FATAL: Table 6 is missing expected columns {missing}. "
                         f"Columns present: {sorted(row)}")
    return keys


def latest_quarter(f):
    row = get({"$select": f"{f['year']},{f['quarter']}",
               "$order": f"{f['year']} DESC,{f['quarter']} DESC",
               "$limit": 1})[0]
    return int(row[f["year"]]), int(row[f["quarter"]])


def pull_quarter(f, year, q):
    """Every city pair for one quarter. ~7,000 rows, so page it."""
    cols = ",".join(f[n] for n in ("city1", "city2", "fare", "passengers")
                    if n in f)
    rows, offset = [], 0
    while True:
        batch = get({"$select": cols,
                     "$where": f"{f['year']}={year} AND {f['quarter']}={q}",
                     "$limit": 5000, "$offset": offset})
        rows.extend(batch)
        if len(batch) < 5000:
            return rows
        offset += 5000


def norm(name):
    """'New York City, NY (Metropolitan Area)' -> 'New York City, NY'."""
    return name.split(" (")[0].strip()


def main():
    args = [a.upper() for a in sys.argv[1:] if not a.startswith("-")]
    dry = "--dry-run" in sys.argv
    origins = args or ALL_ORIGINS

    f = field_names()
    year, q = latest_quarter(f)
    print(f"DOT Consumer Airfare Report Table 6 — latest published quarter: "
          f"Q{q} {year}")

    rows = pull_quarter(f, year, q)
    print(f"pulled {len(rows)} city-pair markets\n")

    # Directionless: DOT adds both directions together, so key on the pair.
    pair = {}
    for r in rows:
        try:
            a, b = norm(r[f["city1"]]), norm(r[f["city2"]])
            pair[frozenset((a, b))] = (float(r[f["fare"]]),
                                       float(r.get(f.get("passengers", ""), 0) or 0))
        except (KeyError, TypeError, ValueError):
            continue

    cfg = json.load(open(CFG, encoding="utf-8"))
    audit = {"_source": ("DOT Consumer Airfare Report Table 6, "
                         "data.transportation.gov resource yj5y-b2ir"),
             "_quarter": f"Q{q} {year}",
             "_fare_note": ("`each_way` is DOT's published average market fare "
                            "(all passengers, all fare classes, one way). "
                            "`round_trip` is that figure doubled — the form the "
                            "rest of the pipeline uses."),
             "_generated_by": "scripts/fetch_dot_fares.py",
             "origins": {}}

    shared = cfg.setdefault("_dot_shared_market", {})
    dot = cfg.setdefault("dot_round_trip", {})

    for origin in origins:
        home = MARKET.get(origin)
        if not home:
            print(f"{origin}: no DOT market mapping — skipped")
            continue
        found, missing, notes, detail = {}, [], {}, {}
        for dest in dests_for(origin):
            market = MARKET.get(dest)
            if not market:
                continue                      # international: no Table 6 data
            if market == home:
                missing.append(f"{dest} (same DOT market as {origin})")
                continue
            hit = pair.get(frozenset((home, market)))
            if not hit:
                missing.append(f"{dest} (no published market)")
                continue
            fare, pax = hit
            found[dest] = int(round(fare * 2))
            detail[dest] = {"market": market, "each_way": round(fare, 2),
                            "round_trip": int(round(fare * 2)),
                            "passengers_per_day": round(pax, 1)}
            if dest in COLLAPSE_NOTE:
                notes[dest] = COLLAPSE_NOTE[dest]

        dot[origin] = dict(sorted(found.items()))
        if notes:
            shared[origin] = notes
        elif origin in shared:
            del shared[origin]
        audit["origins"][origin] = {"market": home, "routes": detail}

        print(f"{origin:4} ({home:26}) {len(found):2} routes"
              + (f"  |  no DOT data: {', '.join(missing)}" if missing else ""))

    cfg["_dot_note"] = (
        f"DOT Consumer Airfare Report, Table 6 (contiguous-state city-pair "
        f"markets), Q{q} {year} — the most recent quarter published on "
        f"data.transportation.gov (resource yj5y-b2ir), pulled by "
        f"scripts/fetch_dot_fares.py. Values below are ROUND TRIP: DOT reports "
        f"an average one-way market fare and it is doubled here. Per-route "
        f"provenance, including each-way fares and daily passenger counts, is "
        f"in config/dot-source.json.")

    if dry:
        print("\n--dry-run: nothing written.")
        return
    with open(CFG, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=1, ensure_ascii=False)
    with open(AUDIT, "w", encoding="utf-8") as fh:
        json.dump(audit, fh, indent=1, ensure_ascii=False)
    print(f"\nWROTE {CFG}\nWROTE {AUDIT}")


if __name__ == "__main__":
    main()
