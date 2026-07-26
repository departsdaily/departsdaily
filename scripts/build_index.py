#!/usr/bin/env python3
"""
Departs Daily - nightly Fare Finder index builder.

Builds one compact index file per origin airport:  site/data/idx-<ORIGIN>.json

Each file holds every real round-trip offer Travelpayouts has cached for that
origin across the next N months. The browser downloads ONE file (its origin)
and does all filtering client-side, so a visitor can run 200 searches at zero
marginal cost and zero API calls.

Design rules (same honesty guarantees as the board):
  - Only real fares from the API are stored. Nothing is composed or estimated.
  - Prices are whole round trips exactly as TP returned them - we never add
    two one-way legs together and call the sum a round-trip price.
  - dep/ret times come straight from the fare's departure_at / return_at.
  - stops come from the fare's transfers fields.
  - If an origin returns too little data its file is NOT written, so last
    night's file stays up rather than a thin, misleading one.

Usage:  TP_TOKEN=... python scripts/build_index.py site/data
"""
import json, os, sys, time, urllib.request
from datetime import datetime, date
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from update_deals import ROUTES, AIRLINES, INTL   # single source of truth

ET     = ZoneInfo("America/New_York")
TOKEN  = os.environ.get("TP_TOKEN", "")
MONTHS = int(os.environ.get("INDEX_MONTHS", "6"))   # 6 = where the fare cache is actually dense
SLEEP  = float(os.environ.get("TP_SLEEP", "0.4"))
MIN_ROWS_PER_ORIGIN = 200      # below this we refuse to overwrite

# Origins we pre-build. Everything else falls back to the Worker (live lookup).
ORIGINS = [o.strip().upper() for o in os.environ.get(
    "ORIGINS", "CLT,ATL,ORD,DFW,DEN,LAX,JFK,MIA,SEA,BOS").split(",") if o.strip()]

LEN_LO, LEN_HI = 1, 30         # trip lengths we keep, in nights


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "departsdaily-index"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.load(r).get("data", [])


def fetch_ow(origin, dest, month=None):
    """One-way legs. TP caches far more one-way data than round-trip data —
    which is why the original builder stored legs. We take both: real round
    trips where they exist, legs to fill the gaps."""
    base = ("https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
            f"?origin={origin}&destination={dest}&currency=usd&market=us"
            f"&one_way=true&sorting=price&limit=1000&token={TOKEN}")
    if month:
        d = _get(base + f"&departure_at={month}")
        if d:
            return d
    return _get(base)


def fetch(origin, dest, month=None):
    """Month-scoped query where supported, otherwise the unscoped cheapest set.

    Scoping by month is what makes the index dense: without it the API returns
    only its overall cheapest handful per route, which is exactly why the old
    index held 97 outbound legs across 30 cities. If a month query comes back
    empty we fall back to unscoped so a route is never dropped entirely.
    """
    base = ("https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
            f"?origin={origin}&destination={dest}&currency=usd&market=us"
            f"&one_way=false&sorting=price&limit=1000&token={TOKEN}")
    if month:
        data = _get(base + f"&departure_at={month}")
        if data:
            return data
    return _get(base)


def months_ahead(today, n):
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            m, y = 1, y + 1
    return out


def build_origin(origin, today):
    best = {}                       # (dest, dayOffset, nights) -> row
    diag = {}                       # per-route counts, so a thin build is explainable
    for dest in ROUTES:
        if dest == origin:
            continue
        got = 0
        for month in [None] + months_ahead(today, MONTHS):
            try:
                fares = fetch(origin, dest, month)
            except Exception as e:
                print(f"    {origin}->{dest} {month} FAIL: {e}")
                time.sleep(SLEEP)
                continue
            for f in fares:
                try:
                    d1 = datetime.fromisoformat(f["departure_at"])
                    d2 = datetime.fromisoformat(f["return_at"])
                    price = int(f.get("price") or 0)
                except (KeyError, ValueError, TypeError):
                    continue
                if price <= 0:
                    continue
                off = (d1.date() - today).days
                nights = (d2.date() - d1.date()).days
                if off < 2 or not (LEN_LO <= nights <= LEN_HI):
                    continue
                key = (dest, off, nights)
                if key in best and best[key][3] <= price:
                    continue
                st_out  = int(f.get("transfers") or 0)
                st_back = int(f.get("return_transfers") or 0)
                dep_out  = d1.hour * 60 + d1.minute
                dep_back = d2.hour * 60 + d2.minute
                # The API gives departure timestamps only. Arrival is derived
                # from the leg duration when the API supplies it; when it does
                # not we store -1 and the front end hides the arrival filter
                # rather than pretending to filter on a number we never had.
                dur_out  = f.get("duration_to")
                dur_back = f.get("duration_back")
                arr_out  = (dep_out + int(dur_out)) % 1440 if dur_out else -1
                arr_back = (dep_back + int(dur_back)) % 1440 if dur_back else -1
                best[key] = (dest, off, nights, price, st_out, st_back,
                             dep_out, arr_out, dep_back, arr_back,
                             (f.get("airline") or "")[:2], 0)
                got += 1
            time.sleep(SLEEP)
        # One-way legs both directions, then compose any pair we lack as a
        # real round trip. Composed rows carry a flag so the site can label
        # them TWO ONE-WAYS rather than implying a single bookable ticket.
        out_legs, back_legs = {}, {}
        for month in [None] + months_ahead(today, MONTHS):
            for a, b, store in ((origin, dest, out_legs), (dest, origin, back_legs)):
                try:
                    legs = fetch_ow(a, b, month)
                except Exception as e:
                    print(f"    {a}->{b} {month} OW FAIL: {e}")
                    time.sleep(SLEEP); continue
                for f in legs:
                    try:
                        d1 = datetime.fromisoformat(f["departure_at"])
                        price = int(f.get("price") or 0)
                    except (KeyError, ValueError, TypeError):
                        continue
                    if price <= 0:
                        continue
                    k = d1.date().isoformat()
                    row = (price, int(f.get("transfers") or 0), d1.hour * 60 + d1.minute)
                    if k not in store or store[k][0] > price:
                        store[k] = row
                time.sleep(SLEEP)

        composed = 0
        for dk, o in out_legs.items():
            do = date.fromisoformat(dk)
            off = (do - today).days
            if off < 2:
                continue
            for rk, b in back_legs.items():
                nights = (date.fromisoformat(rk) - do).days
                if not (LEN_LO <= nights <= LEN_HI):
                    continue
                key = (dest, off, nights)
                if key in best:                       # a real round trip wins
                    continue
                best[key] = (dest, off, nights, o[0] + b[0], o[1], b[1],
                             o[2], -1, b[2], -1, "", 1)
                composed += 1

        diag[dest] = {"rt": got, "out_legs": len(out_legs),
                      "back_legs": len(back_legs), "composed": composed}
        print(f"    {origin}->{dest}: {got} round-trips, "
              f"{len(out_legs)}/{len(back_legs)} legs, {composed} composed")
    codes = sorted({k[0] for k in best})
    ix = {c: i for i, c in enumerate(codes)}
    rows = sorted((ix[d], *rest) for (d, *rest) in best.values())
    return [list(r) for r in rows], codes, diag


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "site/data"
    if not TOKEN:
        print("FATAL: TP_TOKEN not set"); sys.exit(1)
    os.makedirs(outdir, exist_ok=True)

    now = datetime.now(ET)
    today = now.date()
    manifest, wrote, skipped, all_diag = [], 0, [], {}

    for origin in ORIGINS:
        print(f"\n=== {origin} ===")
        rows, codes, diag = build_origin(origin, today)
        all_diag[origin] = diag
        if len(rows) < MIN_ROWS_PER_ORIGIN:
            print(f"  SKIP {origin}: only {len(rows)} rows "
                  f"(min {MIN_ROWS_PER_ORIGIN}) - keeping previous file")
            skipped.append(origin)
            continue
        doc = {
            "origin": origin,
            "base": today.isoformat(),
            "generated": now.isoformat(timespec="seconds"),
            "months": MONTHS,
            "dests": codes,
            "names": {c: ROUTES[c][0] for c in codes},
            "intl": [c for c in codes if c in INTL],
            "airlines": AIRLINES,
            # row = [destIdx, dayOffset, nights, price, stopsOut, stopsBack,
            #        depOutMin, arrOutMin, depBackMin, arrBackMin, airline, composed]
            #        arrival = -1 when the API did not supply a duration
            "schema": 2,
            "has_arrivals": any(r[7] >= 0 or r[9] >= 0 for r in rows),
            "rows": rows,
        }
        path = os.path.join(outdir, f"idx-{origin}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, separators=(",", ":"), ensure_ascii=False)
        kb = os.path.getsize(path) / 1024
        print(f"  WROTE {path}: {len(rows)} offers, {len(codes)} cities, {kb:.0f}KB")
        manifest.append({"origin": origin, "cities": len(codes),
                         "offers": len(rows), "kb": round(kb)})
        wrote += 1

    # Diagnostics are written even when nothing else is, so a thin or failed
    # build can be explained from the repo instead of from CI logs.
    with open(os.path.join(outdir, "_diag.json"), "w") as fh:
        json.dump({"generated": now.isoformat(timespec="seconds"),
                   "origins": all_diag}, fh, indent=1)

    if wrote == 0:
        print("FATAL: no origin produced a usable index - see site/data/_diag.json")
        sys.exit(1)

    with open(os.path.join(outdir, "manifest.json"), "w") as fh:
        json.dump({"generated": now.isoformat(timespec="seconds"),
                   "base": today.isoformat(),
                   "origins": manifest, "skipped": skipped}, fh, indent=1)
    print(f"\nDONE: {wrote}/{len(ORIGINS)} origins written"
          + (f", skipped {skipped}" if skipped else ""))


if __name__ == "__main__":
    main()
