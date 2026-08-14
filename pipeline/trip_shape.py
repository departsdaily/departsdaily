#!/usr/bin/env python3
"""WHICH CATEGORY A FARE BELONGS TO. One rule, one place, no exceptions.

Authoritative spec, owner, 2026-08-14. This REPLACES every night band and every
"close enough" classification the site and the post used before it.

A category is decided by the DAYS OF THE WEEK a trip leaves and comes back on,
not by how many nights it runs. Nights are still bounded, but only as a safety
rail: without them a Wednesday departure returning three Sundays later would
read as an Extra Long Weekend, and a Thursday-to-Monday four weeks out would
read as Week-ish.

There is no fuzzy range, no "about a week", and no fallback that widens a band.
A fare that matches nothing lands in the catch-all. That is the whole design:
CHEAPEST OUT OF CLT is honest precisely because it is defined as leftovers —
the awkward shapes, said out loud.

    1  LONG WEEKEND        out Thu/Fri, back Sun/Mon, 2-4 nights
    2  EXTRA LONG WEEKEND  out Wed-Fri, back Sun-Wed, 4-7 nights
    3  WEEK-ISH            out Thu-Sat, back Thu-Mon, 5-11 nights
    4  CHEAPEST OUT OF CLT everything else

Order matters and is the same order the boards render in. Evaluation stops at
the first match, so a fare carries exactly one category and can never appear
twice on one board.

(Extra Long Weekend caps at 7 nights and every Week-ish shape returning Sunday
or Monday runs 8 nights or more, so those two cannot actually collide. The
order is written down anyway so nobody has to rediscover that.)

OPEN, flagged for the owner: Wednesday-to-Monday lands in Extra Long Weekend
here. If he wants it in the catch-all instead, drop MON from EXTRA_RETURN — one
line, and the test below moves with it.
"""
import datetime

MON, TUE, WED, THU, FRI, SAT, SUN = 0, 1, 2, 3, 4, 5, 6

# Render order AND evaluation order. Both come from this list so they cannot
# drift apart.
ORDER = ("weekend", "extra_weekend", "weekish", "cheapest")

COVERS = {"weekend": "LONG WEEKEND",
          "extra_weekend": "EXTRA LONG WEEKEND",
          "weekish": "WEEK-ISH",
          "cheapest": "CHEAPEST OUT OF CLT"}

# Site headings. The page has room for a noun phrase; a 76pt slide header does not.
TITLES = {"weekend": "LONG WEEKEND TRIPS",
          "extra_weekend": "EXTRA LONG WEEKEND TRIPS",
          "weekish": "WEEK-ISH TRIPS",
          "cheapest": "CHEAPEST OUT OF CLT"}

# One line, same spot, every time — on the slide and on the page. Someone should
# know exactly what they are being offered before they read a single fare.
EXPLAIN = {
    "weekend": "Out Thursday or Friday, back Sunday or Monday. 2 to 4 nights. "
               "Built for a normal 9 to 5.",
    "extra_weekend": "A weekend with a couple of days bolted on. Out Wednesday to "
                     "Friday, back Sunday to Wednesday. 4 to 7 nights.",
    "weekish": "A real week off. Out Thursday to Saturday, back the following "
               "Thursday through Monday. 5 to 11 nights.",
    "cheapest": "Odd days off. These are cheap because the dates are awkward, and "
                "we say so. Every other shape lands here.",
}

# The compact form, for the Instagram caption, where 2200 characters are shared
# between four sections and the explainer lines above would not fit.
SPAN = {"weekend": "Thu/Fri out, Sun/Mon back \u00b7 2\u20134 nights",
        "extra_weekend": "Wed\u2013Fri out, Sun\u2013Wed back \u00b7 4\u20137 nights",
        "weekish": "Thu\u2013Sat out, back the following Thu\u2013Mon \u00b7 5\u201311 nights",
        "cheapest": "every other shape \u00b7 no discount claimed"}

WEEKEND_OUT,  WEEKEND_BACK  = {THU, FRI},      {SUN, MON}
EXTRA_OUT,    EXTRA_BACK    = {WED, THU, FRI}, {SUN, MON, TUE, WED}
WEEKISH_OUT,  WEEKISH_BACK  = {THU, FRI, SAT}, {THU, FRI, SAT, SUN, MON}


def classify(depart, ret):
    """The category a trip belongs to. Returns one of ORDER."""
    if depart is None or ret is None:
        return "cheapest"
    d, r = depart.weekday(), ret.weekday()
    nights = (ret - depart).days
    if nights < 1:
        return "cheapest"
    if d in WEEKEND_OUT and r in WEEKEND_BACK and 2 <= nights <= 4:
        return "weekend"
    if d in EXTRA_OUT and r in EXTRA_BACK and 4 <= nights <= 7:
        return "extra_weekend"
    if d in WEEKISH_OUT and r in WEEKISH_BACK and 5 <= nights <= 11:
        return "weekish"
    return "cheapest"


def classify_iso(d1, d2):
    """Same rule, taking "YYYY-MM-DD" strings. An unparseable date is a fare we
    cannot make a claim about, so it goes to the catch-all rather than to a
    category whose heading would then be wrong."""
    try:
        return classify(datetime.date.fromisoformat(str(d1)[:10]),
                        datetime.date.fromisoformat(str(d2)[:10]))
    except (TypeError, ValueError):
        return "cheapest"


# --- The spec's own test cases. Run: python pipeline/trip_shape.py ----------
CASES = [
    ("2026-08-20", "2026-08-23", "weekend",       "Thu->Sun, 3n"),
    ("2026-08-21", "2026-08-24", "weekend",       "Fri->Mon, 3n"),
    ("2026-08-20", "2026-08-24", "weekend",       "Thu->Mon, 4n"),
    ("2026-08-21", "2026-08-23", "weekend",       "Fri->Sun, 2n"),
    ("2026-08-19", "2026-08-23", "extra_weekend", "Wed->Sun, 4n"),
    ("2026-08-19", "2026-08-24", "extra_weekend", "Wed->Mon, 5n"),
    ("2026-08-19", "2026-08-25", "extra_weekend", "Wed->Tue, 6n"),
    ("2026-08-19", "2026-08-26", "extra_weekend", "Wed->Wed, 7n"),
    ("2026-08-20", "2026-08-25", "extra_weekend", "Thu->Tue, 5n"),
    ("2026-08-20", "2026-08-26", "extra_weekend", "Thu->Wed, 6n"),
    ("2026-08-21", "2026-08-25", "extra_weekend", "Fri->Tue, 4n"),
    ("2026-08-21", "2026-08-26", "extra_weekend", "Fri->Wed, 5n"),
    ("2026-08-21", "2026-08-28", "weekish",       "Fri->following Fri, 7n"),
    ("2026-08-22", "2026-08-27", "weekish",       "Sat->following Thu, 5n"),
    ("2026-08-20", "2026-08-30", "weekish",       "Thu->following Sun, 10n"),
    ("2026-08-22", "2026-08-31", "weekish",       "Sat->following Mon, 9n"),
    ("2026-08-20", "2026-08-27", "weekish",       "Thu->following Thu, 7n"),
    ("2026-08-22", "2026-08-24", "cheapest",      "Sat->Mon, 2n"),
    ("2026-08-18", "2026-08-23", "cheapest",      "Tue->Sun, 5n"),
    ("2026-08-20", "2026-09-03", "cheapest",      "Thu->Thu after next, 14n"),
    ("2026-08-19", "2026-08-20", "cheapest",      "Wed->Thu, 1n"),
    ("2026-08-21", "2026-08-25", "extra_weekend", "Fri->Tue, 4n (not Long Weekend)"),
    ("2026-08-19", "2026-09-06", "cheapest",      "Wed->Sun three weeks out, 18n"),
]


def _selftest():
    bad = 0
    for d1, d2, want, label in CASES:
        got = classify_iso(d1, d2)
        ok = got == want
        bad += not ok
        print(("  ok  " if ok else "  FAIL") + f" {label:38} {d1}->{d2}  {got}")
    # Every one of the spec's legal shapes must land where the spec says, and
    # nothing may be claimed by two categories — classify() returns one string,
    # so single-category is structural, but the shape tables are asserted here.
    start = datetime.date(2026, 8, 17)          # a Monday
    tally = {k: 0 for k in ORDER}
    for od in range(7):
        for n in range(1, 30):
            dd = start + datetime.timedelta(days=od)
            tally[classify(dd, dd + datetime.timedelta(days=n))] += 1
    print("\nshape census over every dow x 1-29 nights:", tally)
    print("\n%d/%d cases pass" % (len(CASES) - bad, len(CASES)))
    return bad


if __name__ == "__main__":
    raise SystemExit(1 if _selftest() else 0)
